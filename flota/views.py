"""
=====================================================================
VISTAS DEL CATÁLOGO (app "flota")
=====================================================================
Matriz de permisos aplicada:
    PÚBLICO (sin token):
        GET /api/servicios/                 listado con filtros
        GET /api/servicios/buscar/          búsqueda origen/destino
        GET /api/servicios/{id}/            detalle
        GET /api/servicios/{id}/asientos/   mapa de asientos
        GET /api/ciudades/, /api/terminales/, /api/rutas/
    ADMINISTRADOR DE FLOTA (claim rol = ADMIN_FLOTA):
        POST/PUT/PATCH/DELETE /api/servicios/  (y ciudades, terminales, rutas)
        CRUD completo de /api/buses/
"""

from django.db.models import Count, ProtectedError, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from usuarios.permissions import EsAdministradorFlota, LecturaPublicaEscrituraAdmin

from .filters import AsientoFilter, RutaFilter, ServicioFilter
from .models import Asiento, Bus, Ciudad, Ruta, Servicio, Terminal
from .serializers import (
    AsientoSerializer,
    BusSerializer,
    CiudadSerializer,
    RutaSerializer,
    ServicioSerializer,
    TerminalSerializer,
)


class BorradoProtegidoMixin:
    """
    Convierte el ProtectedError (FK con on_delete=PROTECT) en una
    respuesta 409 legible, en vez de un error 500.
    """

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar: existen registros relacionados que dependen de este elemento.'},
                status=status.HTTP_409_CONFLICT,
            )


class CiudadViewSet(BorradoProtegidoMixin, viewsets.ModelViewSet):
    queryset = Ciudad.objects.all()
    serializer_class = CiudadSerializer
    permission_classes = [LecturaPublicaEscrituraAdmin]
    filterset_fields = ['region']
    search_fields = ['nombre', 'region']


class TerminalViewSet(BorradoProtegidoMixin, viewsets.ModelViewSet):
    queryset = Terminal.objects.select_related('ciudad')
    serializer_class = TerminalSerializer
    permission_classes = [LecturaPublicaEscrituraAdmin]
    filterset_fields = ['ciudad']
    search_fields = ['nombre', 'ciudad__nombre']


class RutaViewSet(BorradoProtegidoMixin, viewsets.ModelViewSet):
    queryset = Ruta.objects.select_related('origen__ciudad', 'destino__ciudad')
    serializer_class = RutaSerializer
    permission_classes = [LecturaPublicaEscrituraAdmin]
    filterset_class = RutaFilter
    ordering_fields = ['distancia_km', 'duracion_estimada']


class BusViewSet(BorradoProtegidoMixin, viewsets.ModelViewSet):
    """Gestión de buses: exclusiva del Administrador de Flota (incluida la lectura)."""

    queryset = Bus.objects.all()
    serializer_class = BusSerializer
    permission_classes = [EsAdministradorFlota]
    filterset_fields = ['activo', 'marca']
    search_fields = ['patente', 'marca', 'modelo']


class ServicioViewSet(BorradoProtegidoMixin, viewsets.ModelViewSet):
    """
    -----------------------------------------------------------------
    BLOQUE: Servicios / Itinerarios
    get_queryset():
      - select_related evita consultas N+1 al serializar ruta/bus.
      - annotate agrega COUNTs condicionales calculados en PostgreSQL:
          asientos_disponibles, disponibles_cama, disponibles_semicama
        (se usan en el JSON y en el filtro con_disponibilidad).
    -----------------------------------------------------------------
    """

    serializer_class = ServicioSerializer
    permission_classes = [LecturaPublicaEscrituraAdmin]
    filterset_class = ServicioFilter
    search_fields = ['ruta__origen__ciudad__nombre', 'ruta__destino__ciudad__nombre', 'bus__patente']
    ordering_fields = ['fecha_salida', 'tarifa_semicama', 'tarifa_cama']

    def get_queryset(self):
        disponible = Q(asientos__estado=Asiento.Estado.DISPONIBLE)
        return Servicio.objects.select_related(
            'ruta__origen__ciudad', 'ruta__destino__ciudad', 'bus'
        ).annotate(
            asientos_disponibles=Count('asientos', filter=disponible),
            disponibles_cama=Count('asientos', filter=disponible & Q(asientos__tipo=Asiento.Tipo.CAMA)),
            disponibles_semicama=Count('asientos', filter=disponible & Q(asientos__tipo=Asiento.Tipo.SEMICAMA)),
        ).order_by('fecha_salida', 'id')  # con GROUP BY, Django no aplica Meta.ordering

    @extend_schema(
        summary='Buscar pasajes por origen y destino (público)',
        parameters=[
            OpenApiParameter('origen', OpenApiTypes.STR, required=True, description='Ciudad de origen'),
            OpenApiParameter('destino', OpenApiTypes.STR, required=True, description='Ciudad de destino'),
        ],
    )
    @action(detail=False, methods=['get'], url_path='buscar', permission_classes=[AllowAny])
    def buscar(self, request):
        """
        -----------------------------------------------------------------
        BLOQUE: Búsqueda pública de pasajes
        Exige origen y destino. Devuelve solo servicios vendibles:
        PROGRAMADOS, con salida futura y con al menos un asiento libre.
        Admite además todos los filtros de ServicioFilter (fecha,
        tarifa_min, tarifa_max, tipo_asiento...).
        -----------------------------------------------------------------
        """
        if not request.query_params.get('origen') or not request.query_params.get('destino'):
            return Response(
                {'detail': 'Debe indicar los parámetros "origen" y "destino".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = self.filter_queryset(self.get_queryset()).filter(
            estado=Servicio.Estado.PROGRAMADO,
            fecha_salida__gt=timezone.now(),
            asientos_disponibles__gt=0,
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Mapa de asientos de un servicio (público)',
        responses=AsientoSerializer(many=True),
        parameters=[
            OpenApiParameter('tipo', OpenApiTypes.STR, enum=Asiento.Tipo.values),
            OpenApiParameter('estado', OpenApiTypes.STR, enum=Asiento.Estado.values),
        ],
    )
    @action(detail=True, methods=['get'], url_path='asientos', permission_classes=[AllowAny])
    def asientos(self, request, pk=None):
        """Lista los asientos del servicio con su tipo, estado y tarifa (filtrables)."""
        servicio = self.get_object()
        asientos = AsientoFilter(
            request.query_params,
            queryset=servicio.asientos.select_related('servicio'),
        ).qs
        return Response(AsientoSerializer(asientos, many=True).data)
