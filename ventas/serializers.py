"""
=====================================================================
SERIALIZADORES DE LA APP "ventas"
=====================================================================
- ItemCarroSerializer: agregar/editar asientos del carro con los datos
  del ocupante, con validaciones de negocio.
- CarroSerializer: carro completo con ítems y total.
- VentaSerializer / DetalleVentaSerializer / BoletoSerializer: historial.
- CambioEstadoSerializer / CheckoutSerializer: entradas de acciones.
"""

from rest_framework import serializers

from flota.models import Asiento

from .models import Boleto, Carro, DetalleVenta, ItemCarro, TipoDocumento, Venta
from .validators import normalizar_rut


class AsientoResumenSerializer(serializers.ModelSerializer):
    """Datos del asiento y de su servicio para mostrar dentro del carro."""

    servicio = serializers.IntegerField(source='servicio.id')
    origen = serializers.CharField(source='servicio.ruta.origen.ciudad.nombre')
    destino = serializers.CharField(source='servicio.ruta.destino.ciudad.nombre')
    fecha_salida = serializers.DateTimeField(source='servicio.fecha_salida')
    tarifa = serializers.IntegerField()

    class Meta:
        model = Asiento
        fields = ('id', 'numero', 'tipo', 'estado', 'tarifa', 'servicio', 'origen', 'destino', 'fecha_salida')
        read_only_fields = fields


class ItemCarroSerializer(serializers.ModelSerializer):
    """
    -----------------------------------------------------------------
    BLOQUE: Validaciones al agregar un asiento al carro
    1. El asiento debe estar DISPONIBLE y su servicio a la venta
       (PROGRAMADO y con salida futura).
    2. No se puede agregar el mismo asiento dos veces al carro
       (también lo garantiza el UniqueConstraint en la BD).
    3. Un mismo pasajero (documento) no puede ocupar dos asientos del
       mismo servicio dentro del carro.
    4. Si el documento es RUT, se valida su dígito verificador.
    Recuerde: agregar al carro NO cambia el estado del asiento.
    -----------------------------------------------------------------
    """

    asiento = serializers.PrimaryKeyRelatedField(queryset=Asiento.objects.select_related('servicio'))
    asiento_detalle = AsientoResumenSerializer(source='asiento', read_only=True)
    subtotal = serializers.IntegerField(read_only=True)

    class Meta:
        model = ItemCarro
        fields = (
            'id', 'asiento', 'asiento_detalle', 'nombre_pasajero',
            'tipo_documento', 'documento_pasajero', 'subtotal', 'agregado',
        )
        read_only_fields = ('id', 'agregado')

    def validate_asiento(self, asiento):
        if self.instance is not None and self.instance.asiento_id != asiento.id:
            raise serializers.ValidationError('Para cambiar de asiento elimine el ítem y agregue uno nuevo.')
        if asiento.estado != Asiento.Estado.DISPONIBLE:
            raise serializers.ValidationError('El asiento seleccionado ya está ocupado.')
        if not asiento.servicio.esta_a_la_venta:
            raise serializers.ValidationError('El servicio de este asiento ya no está a la venta.')
        return asiento

    def validate(self, attrs):
        carro = self.context['carro']
        asiento = attrs.get('asiento', getattr(self.instance, 'asiento', None))
        tipo_doc = attrs.get('tipo_documento', getattr(self.instance, 'tipo_documento', TipoDocumento.RUT))
        documento = attrs.get('documento_pasajero', getattr(self.instance, 'documento_pasajero', ''))

        # Normaliza/valida el RUT o limpia el pasaporte.
        if tipo_doc == TipoDocumento.RUT:
            documento = normalizar_rut(documento)
        else:
            documento = documento.strip().upper()
        attrs['documento_pasajero'] = documento

        otros_items = carro.items.exclude(pk=getattr(self.instance, 'pk', None))
        if self.instance is None and otros_items.filter(asiento=asiento).exists():
            raise serializers.ValidationError({'asiento': 'Este asiento ya está en su carro.'})
        if otros_items.filter(asiento__servicio=asiento.servicio_id, documento_pasajero=documento).exists():
            raise serializers.ValidationError(
                {'documento_pasajero': 'Este pasajero ya tiene un asiento en el mismo servicio dentro del carro.'}
            )
        return attrs


class CarroSerializer(serializers.ModelSerializer):
    """Carro completo: ítems, cantidad y total a precio actual."""

    usuario = serializers.CharField(source='usuario.username', read_only=True)
    items = ItemCarroSerializer(many=True, read_only=True)
    cantidad_items = serializers.SerializerMethodField()
    total = serializers.IntegerField(read_only=True)

    class Meta:
        model = Carro
        fields = ('id', 'usuario', 'items', 'cantidad_items', 'total', 'actualizado')

    def get_cantidad_items(self, obj) -> int:
        return obj.items.count()


class BoletoSerializer(serializers.ModelSerializer):
    """
    Boleto emitido con su código UUID y los datos del viaje, obtenidos
    recorriendo Boleto -> DetalleVenta -> Asiento -> Servicio -> Ruta.
    """

    venta = serializers.IntegerField(source='detalle.venta_id', read_only=True)
    pasajero = serializers.CharField(source='detalle.nombre_pasajero', read_only=True)
    documento = serializers.CharField(source='detalle.documento_pasajero', read_only=True)
    asiento = serializers.IntegerField(source='detalle.asiento.numero', read_only=True)
    tipo_asiento = serializers.CharField(source='detalle.tipo_asiento', read_only=True)
    precio = serializers.IntegerField(source='detalle.precio_unitario', read_only=True)
    servicio = serializers.IntegerField(source='detalle.asiento.servicio_id', read_only=True)
    origen = serializers.CharField(source='detalle.asiento.servicio.ruta.origen.ciudad.nombre', read_only=True)
    destino = serializers.CharField(source='detalle.asiento.servicio.ruta.destino.ciudad.nombre', read_only=True)
    terminal_origen = serializers.CharField(source='detalle.asiento.servicio.ruta.origen.nombre', read_only=True)
    fecha_salida = serializers.DateTimeField(source='detalle.asiento.servicio.fecha_salida', read_only=True)
    bus = serializers.CharField(source='detalle.asiento.servicio.bus.patente', read_only=True)

    class Meta:
        model = Boleto
        fields = (
            'id', 'codigo', 'estado', 'emitido', 'venta', 'pasajero', 'documento', 'asiento',
            'tipo_asiento', 'precio', 'servicio', 'origen', 'destino', 'terminal_origen',
            'fecha_salida', 'bus',
        )


class DetalleVentaSerializer(serializers.ModelSerializer):
    asiento_numero = serializers.IntegerField(source='asiento.numero', read_only=True)
    servicio = serializers.IntegerField(source='asiento.servicio_id', read_only=True)
    boleto = serializers.SerializerMethodField()

    class Meta:
        model = DetalleVenta
        fields = (
            'id', 'servicio', 'asiento', 'asiento_numero', 'tipo_asiento', 'nombre_pasajero',
            'tipo_documento', 'documento_pasajero', 'precio_unitario', 'boleto',
        )

    def get_boleto(self, obj) -> dict | None:
        # El boleto solo existe si la venta fue pagada.
        boleto = getattr(obj, 'boleto', None)
        if boleto is None:
            return None
        return {'codigo': str(boleto.codigo), 'estado': boleto.estado}


class VentaSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(source='usuario.username', read_only=True)
    detalles = DetalleVentaSerializer(many=True, read_only=True)

    class Meta:
        model = Venta
        fields = ('id', 'codigo', 'usuario', 'estado', 'total', 'creada', 'pagada_en', 'actualizada', 'observacion', 'detalles')
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    """
    pagar=true (por defecto): confirma y paga en un solo paso.
    pagar=false: solo genera la venta PENDIENTE (se paga luego en
    /api/ventas/{id}/pagar/).
    """

    pagar = serializers.BooleanField(default=True)


class CambioEstadoSerializer(serializers.Serializer):
    """Entrada del PATCH /api/ventas/{id}/estado/ (Administrador de Flota)."""

    estado = serializers.ChoiceField(choices=Venta.Estado.choices)
    observacion = serializers.CharField(required=False, allow_blank=True, max_length=255)
