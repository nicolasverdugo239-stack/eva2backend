"""
=====================================================================
VISTAS DE CARRO, VENTAS Y BOLETOS (app "ventas")
=====================================================================
Matriz de permisos aplicada:
  PASAJERO (IsAuthenticated + EsPasajero):
      GET/POST/DELETE  /api/carro-pasajes/          ver / agregar / vaciar
      PATCH/DELETE     /api/carro-pasajes/{item}/   editar ocupante / quitar
      POST             /api/ventas/checkout/        confirmar compra
      POST             /api/ventas/{id}/pagar/      pagar una venta PENDIENTE
      GET              /api/mis-boletos/            boletos emitidos
      GET              /api/mis-ventas/             historial de ventas
  ADMINISTRADOR DE FLOTA (EsAdministradorFlota):
      GET              /api/ventas/                 todas las ventas (filtros)
      PATCH            /api/ventas/{id}/estado/     PAGADO/COMPLETADO/CANCELADO
"""

from django.db import IntegrityError
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from usuarios.permissions import EsAdministradorFlota, EsPasajero, obtener_rol
from usuarios.models import Usuario

from . import services
from .filters import BoletoFilter, VentaFilter
from .models import Boleto, Carro, DetalleVenta, ItemCarro, Venta
from .serializers import (
    BoletoSerializer,
    CambioEstadoSerializer,
    CarroSerializer,
    CheckoutSerializer,
    ItemCarroSerializer,
    VentaSerializer,
)


# ---------------------------------------------------------------------
# BLOQUE: Consulta del carro persistente
# El carro se busca en PostgreSQL por el ID del usuario del token:
#   SELECT * FROM ventas_carro WHERE usuario_id = <request.user.id>
# No depende de la sesión ni del dispositivo: cualquier login del mismo
# usuario recupera exactamente el mismo carro con sus ítems.
# ---------------------------------------------------------------------
def obtener_carro(usuario):
    carro, _ = Carro.objects.prefetch_related(
        Prefetch(
            'items',
            queryset=ItemCarro.objects.select_related(
                'asiento__servicio__ruta__origen__ciudad',
                'asiento__servicio__ruta__destino__ciudad',
            ),
        )
    ).get_or_create(usuario=usuario)
    return carro


class CarroPasajesView(APIView):
    """Carro de pasajes del pasajero autenticado."""

    permission_classes = [IsAuthenticated, EsPasajero]

    @extend_schema(summary='Ver mi carro de pasajes', responses=CarroSerializer)
    def get(self, request):
        return Response(CarroSerializer(obtener_carro(request.user)).data)

    @extend_schema(
        summary='Agregar un asiento al carro (con datos del ocupante)',
        request=ItemCarroSerializer,
        responses={201: CarroSerializer},
    )
    def post(self, request):
        """
        Agrega un ítem al carro. NO modifica el estado del asiento:
        el stock solo se descuenta cuando la venta pasa a PAGADO.
        """
        carro = obtener_carro(request.user)
        serializer = ItemCarroSerializer(data=request.data, context={'carro': carro})
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save(carro=carro)
        except IntegrityError:
            # Respaldo del UniqueConstraint (carro, asiento) ante peticiones simultáneas.
            return Response({'asiento': ['Este asiento ya está en su carro.']}, status=status.HTTP_400_BAD_REQUEST)
        carro.save(update_fields=['actualizado'])
        return Response(CarroSerializer(obtener_carro(request.user)).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary='Vaciar el carro', responses={204: None}, operation_id='carro_pasajes_vaciar')
    def delete(self, request):
        carro = obtener_carro(request.user)
        carro.items.all().delete()
        carro.save(update_fields=['actualizado'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CarroItemView(APIView):
    """Edición o eliminación de un ítem puntual del carro (solo del propio carro)."""

    permission_classes = [IsAuthenticated, EsPasajero]

    def _obtener_item(self, request, item_id):
        # Filtrar por carro__usuario impide tocar ítems de otros usuarios.
        return get_object_or_404(ItemCarro, pk=item_id, carro__usuario=request.user)

    @extend_schema(summary='Editar datos del ocupante de un ítem', request=ItemCarroSerializer, responses=CarroSerializer)
    def patch(self, request, item_id):
        item = self._obtener_item(request, item_id)
        serializer = ItemCarroSerializer(item, data=request.data, partial=True, context={'carro': item.carro})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CarroSerializer(obtener_carro(request.user)).data)

    @extend_schema(summary='Quitar un ítem del carro', responses={204: None}, operation_id='carro_pasajes_item_eliminar')
    def delete(self, request, item_id):
        self._obtener_item(request, item_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VentaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    -----------------------------------------------------------------
    BLOQUE: Ventas
    - get_queryset(): el Administrador de Flota ve todas las ventas; un
      pasajero solo las suyas (un pasajero no puede ver ni pagar ventas
      ajenas: obtendría 404).
    - get_permissions(): permisos distintos por acción.
    - prefetch_related trae detalles y boletos en pocas consultas.
    -----------------------------------------------------------------
    """

    serializer_class = VentaSerializer
    filterset_class = VentaFilter
    ordering_fields = ['creada', 'total']

    def get_queryset(self):
        # Durante la generación del esquema OpenAPI no hay usuario real.
        if getattr(self, 'swagger_fake_view', False):
            return Venta.objects.none()
        queryset = Venta.objects.select_related('usuario').prefetch_related(
            Prefetch('detalles', queryset=DetalleVenta.objects.select_related('asiento', 'boleto'))
        )
        if obtener_rol(self.request) == Usuario.Rol.ADMIN_FLOTA:
            return queryset
        return queryset.filter(usuario=self.request.user)

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'estado'):
            return [EsAdministradorFlota()]
        return [IsAuthenticated(), EsPasajero()]

    @extend_schema(
        summary='Checkout: convertir el carro en una venta',
        request=CheckoutSerializer,
        responses={201: VentaSerializer},
    )
    @action(detail=False, methods=['post'], url_path='checkout')
    def checkout(self, request):
        """
        Liquida el carro y genera la Venta (con precios congelados).
        Con pagar=true (defecto) además procesa el pago: verifica los
        asientos bajo bloqueo, los marca OCUPADOS y emite los boletos.
        Si algún asiento ya fue vendido responde 409 y el carro queda intacto.
        """
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        venta = services.checkout(request.user, pagar=serializer.validated_data['pagar'])
        return Response(VentaSerializer(self.get_queryset().get(pk=venta.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary='Pagar una venta PENDIENTE propia', request=None, responses=VentaSerializer)
    @action(detail=True, methods=['post'], url_path='pagar')
    def pagar(self, request, pk=None):
        venta = self.get_object()  # queryset filtrado: solo ventas propias
        services.cambiar_estado(venta.id, Venta.Estado.PAGADO)
        return Response(VentaSerializer(self.get_queryset().get(pk=venta.pk)).data)

    @extend_schema(
        summary='Cambiar estado de una venta (Administrador de Flota)',
        request=CambioEstadoSerializer,
        responses=VentaSerializer,
    )
    @action(detail=True, methods=['patch'], url_path='estado')
    def estado(self, request, pk=None):
        """
        PENDIENTE -> PAGADO | CANCELADO ;  PAGADO -> COMPLETADO | CANCELADO.
        Al CANCELAR una venta pagada, los asientos se reponen como
        DISPONIBLES automáticamente y los boletos quedan ANULADOS.
        """
        venta = self.get_object()
        serializer = CambioEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cambiar_estado(
            venta.id,
            serializer.validated_data['estado'],
            serializer.validated_data.get('observacion', ''),
        )
        return Response(VentaSerializer(self.get_queryset().get(pk=venta.pk)).data)


class MisVentasView(generics.ListAPIView):
    """Historial de ventas (órdenes) del pasajero autenticado."""

    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated, EsPasajero]
    filterset_class = VentaFilter
    ordering_fields = ['creada', 'total']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Venta.objects.none()
        return Venta.objects.filter(usuario=self.request.user).select_related('usuario').prefetch_related(
            Prefetch('detalles', queryset=DetalleVenta.objects.select_related('asiento', 'boleto'))
        )


class MisBoletosView(generics.ListAPIView):
    """Boletos emitidos (ventas pagadas) del pasajero autenticado."""

    serializer_class = BoletoSerializer
    permission_classes = [IsAuthenticated, EsPasajero]
    filterset_class = BoletoFilter
    ordering_fields = ['emitido', 'detalle__asiento__servicio__fecha_salida']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Boleto.objects.none()
        return Boleto.objects.filter(detalle__venta__usuario=self.request.user).select_related(
            'detalle__asiento__servicio__ruta__origen__ciudad',
            'detalle__asiento__servicio__ruta__destino__ciudad',
            'detalle__asiento__servicio__bus',
        )
