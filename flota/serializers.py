"""
=====================================================================
SERIALIZADORES DE LA APP "flota"
=====================================================================
Convierten los modelos del catálogo a JSON y validan los datos de
entrada cuando el Administrador de Flota crea o modifica registros.
"""

from django.utils import timezone
from rest_framework import serializers

from .models import Asiento, Bus, Ciudad, Ruta, Servicio, Terminal


class CiudadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ciudad
        fields = ('id', 'nombre', 'region')


class TerminalSerializer(serializers.ModelSerializer):
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)

    class Meta:
        model = Terminal
        fields = ('id', 'nombre', 'direccion', 'ciudad', 'ciudad_nombre')


class RutaSerializer(serializers.ModelSerializer):
    """
    Serializa una ruta mostrando además los nombres de ciudad de origen
    y destino (lectura) para no obligar al cliente a hacer más consultas.
    """

    origen_ciudad = serializers.CharField(source='origen.ciudad.nombre', read_only=True)
    destino_ciudad = serializers.CharField(source='destino.ciudad.nombre', read_only=True)

    class Meta:
        model = Ruta
        fields = ('id', 'origen', 'origen_ciudad', 'destino', 'destino_ciudad', 'distancia_km', 'duracion_estimada')

    def validate(self, attrs):
        origen = attrs.get('origen', getattr(self.instance, 'origen', None))
        destino = attrs.get('destino', getattr(self.instance, 'destino', None))
        if origen and destino and origen == destino:
            raise serializers.ValidationError('El origen y el destino deben ser terminales distintos.')
        return attrs


class BusSerializer(serializers.ModelSerializer):
    capacidad_total = serializers.IntegerField(read_only=True)

    class Meta:
        model = Bus
        fields = ('id', 'patente', 'marca', 'modelo', 'anio', 'asientos_cama', 'asientos_semicama', 'capacidad_total', 'activo')

    def validate(self, attrs):
        cama = attrs.get('asientos_cama', getattr(self.instance, 'asientos_cama', 0))
        semicama = attrs.get('asientos_semicama', getattr(self.instance, 'asientos_semicama', 0))
        if cama + semicama == 0:
            raise serializers.ValidationError('El bus debe tener al menos un asiento.')
        return attrs


class AsientoSerializer(serializers.ModelSerializer):
    """Asiento con su tarifa vigente calculada según el tipo."""

    tarifa = serializers.IntegerField(read_only=True)

    class Meta:
        model = Asiento
        fields = ('id', 'numero', 'tipo', 'estado', 'tarifa')


class ServicioSerializer(serializers.ModelSerializer):
    """
    -----------------------------------------------------------------
    BLOQUE: Serializador de Servicio
    Lectura: agrega datos de la ruta, del bus y el conteo de asientos
    disponibles (anotaciones calculadas por la BD en la vista).
    Escritura (Admin Flota):
      - La fecha de salida debe ser futura al crear.
      - El bus debe estar activo.
      - No se permite cambiar el bus de un servicio ya creado, porque
        sus asientos se generaron con la distribución de ese bus.
    -----------------------------------------------------------------
    """

    origen = serializers.CharField(source='ruta.origen.ciudad.nombre', read_only=True)
    destino = serializers.CharField(source='ruta.destino.ciudad.nombre', read_only=True)
    terminal_origen = serializers.CharField(source='ruta.origen.nombre', read_only=True)
    terminal_destino = serializers.CharField(source='ruta.destino.nombre', read_only=True)
    bus_patente = serializers.CharField(source='bus.patente', read_only=True)
    fecha_llegada_estimada = serializers.DateTimeField(read_only=True)
    asientos_disponibles = serializers.IntegerField(read_only=True)
    disponibles_cama = serializers.IntegerField(read_only=True)
    disponibles_semicama = serializers.IntegerField(read_only=True)

    class Meta:
        model = Servicio
        fields = (
            'id', 'ruta', 'origen', 'destino', 'terminal_origen', 'terminal_destino',
            'bus', 'bus_patente', 'fecha_salida', 'fecha_llegada_estimada',
            'tarifa_semicama', 'tarifa_cama', 'estado',
            'asientos_disponibles', 'disponibles_cama', 'disponibles_semicama',
        )

    def validate_fecha_salida(self, value):
        if self.instance is None and value <= timezone.now():
            raise serializers.ValidationError('La fecha de salida debe ser futura.')
        return value

    def validate_bus(self, value):
        if self.instance is not None and self.instance.bus_id != value.id:
            raise serializers.ValidationError('No se puede cambiar el bus de un servicio existente.')
        if not value.activo:
            raise serializers.ValidationError('El bus seleccionado no está activo.')
        return value
