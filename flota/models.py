"""
=====================================================================
MODELOS DE LA APP "flota" (CATÁLOGO / INVENTARIO)
=====================================================================
Estructura relacional (integridad referencial con Foreign Keys):

    Ciudad 1 ──< N Terminal
    Terminal 1 ──< N Ruta (como origen)   Terminal 1 ──< N Ruta (como destino)
    Ruta 1 ──< N Servicio >── N 1 Bus
    Servicio 1 ──< N Asiento

El "stock" de este sistema son los ASIENTOS de cada Servicio: cada
asiento tiene un estado (DISPONIBLE / OCUPADO). Un asiento solo pasa a
OCUPADO cuando la venta se valida como PAGADO, y vuelve a DISPONIBLE si
la venta es CANCELADA (ver ventas/services.py).
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Ciudad(models.Model):
    """Ciudad donde existen terminales de buses (ej. Santiago, Valparaíso)."""

    nombre = models.CharField(max_length=100, unique=True)
    region = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'Ciudad'
        verbose_name_plural = 'Ciudades'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Terminal(models.Model):
    """
    Terminal de buses perteneciente a una Ciudad.
    FK con on_delete=PROTECT: no se puede borrar una ciudad con terminales.
    """

    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=255)
    ciudad = models.ForeignKey(Ciudad, on_delete=models.PROTECT, related_name='terminales')

    class Meta:
        verbose_name = 'Terminal'
        verbose_name_plural = 'Terminales'
        ordering = ['ciudad__nombre', 'nombre']
        constraints = [
            models.UniqueConstraint(fields=['ciudad', 'nombre'], name='terminal_unica_por_ciudad'),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.ciudad})'


class Ruta(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Ruta Origen -> Destino
    Dos FK hacia Terminal (origen y destino). related_name distintos
    para poder navegar: terminal.rutas_salida / terminal.rutas_llegada.
    Restricciones:
      - No puede repetirse el par (origen, destino).
      - Origen y destino deben ser distintos (CheckConstraint en BD).
    -----------------------------------------------------------------
    """

    origen = models.ForeignKey(Terminal, on_delete=models.PROTECT, related_name='rutas_salida')
    destino = models.ForeignKey(Terminal, on_delete=models.PROTECT, related_name='rutas_llegada')
    distancia_km = models.PositiveIntegerField()
    duracion_estimada = models.DurationField(help_text='Duración estimada del viaje (HH:MM:SS).')

    class Meta:
        verbose_name = 'Ruta'
        verbose_name_plural = 'Rutas'
        ordering = ['origen__ciudad__nombre', 'destino__ciudad__nombre']
        constraints = [
            models.UniqueConstraint(fields=['origen', 'destino'], name='ruta_unica'),
            models.CheckConstraint(
                condition=~models.Q(origen=models.F('destino')),
                name='ruta_origen_distinto_destino',
            ),
        ]

    def clean(self):
        if self.origen_id and self.origen_id == self.destino_id:
            raise ValidationError('El origen y el destino deben ser terminales distintos.')

    def __str__(self):
        return f'{self.origen.ciudad} -> {self.destino.ciudad}'


class Bus(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Bus de la flota
    Define la distribución física de asientos: cuántos son CAMA y
    cuántos SEMICAMA. Con estos números se generan automáticamente los
    asientos de cada Servicio (señal en flota/signals.py).
    -----------------------------------------------------------------
    """

    patente = models.CharField(max_length=10, unique=True)
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=60)
    anio = models.PositiveIntegerField(verbose_name='Año')
    asientos_cama = models.PositiveIntegerField(default=0)
    asientos_semicama = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Bus'
        verbose_name_plural = 'Buses'
        ordering = ['patente']

    @property
    def capacidad_total(self):
        return self.asientos_cama + self.asientos_semicama

    def __str__(self):
        return f'{self.patente} - {self.marca} {self.modelo}'


class Servicio(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Servicio / Itinerario
    Vincula una Ruta + un Bus + fecha/hora de salida, y define la tarifa
    por tipo de asiento (Semicama / Cama).
    estado (CHOICES): PROGRAMADO -> EN_RUTA -> FINALIZADO (o CANCELADO).
    Solo se venden pasajes de servicios PROGRAMADOS cuya salida es futura.
    Las tarifas se guardan en pesos chilenos (enteros, sin decimales).
    -----------------------------------------------------------------
    """

    class Estado(models.TextChoices):
        PROGRAMADO = 'PROGRAMADO', 'Programado'
        EN_RUTA = 'EN_RUTA', 'En ruta'
        FINALIZADO = 'FINALIZADO', 'Finalizado'
        CANCELADO = 'CANCELADO', 'Cancelado'

    ruta = models.ForeignKey(Ruta, on_delete=models.PROTECT, related_name='servicios')
    bus = models.ForeignKey(Bus, on_delete=models.PROTECT, related_name='servicios')
    fecha_salida = models.DateTimeField()
    tarifa_semicama = models.PositiveIntegerField(help_text='Tarifa en CLP para asiento Semicama.')
    tarifa_cama = models.PositiveIntegerField(help_text='Tarifa en CLP para asiento Cama.')
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.PROGRAMADO)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'
        ordering = ['fecha_salida']
        constraints = [
            models.UniqueConstraint(fields=['bus', 'fecha_salida'], name='bus_sin_doble_salida'),
        ]

    @property
    def fecha_llegada_estimada(self):
        return self.fecha_salida + self.ruta.duracion_estimada

    @property
    def esta_a_la_venta(self):
        """True si el servicio está PROGRAMADO y aún no ha salido."""
        return self.estado == self.Estado.PROGRAMADO and self.fecha_salida > timezone.now()

    def tarifa_para(self, tipo_asiento):
        """Devuelve la tarifa vigente según el tipo de asiento."""
        if tipo_asiento == Asiento.Tipo.CAMA:
            return self.tarifa_cama
        return self.tarifa_semicama

    def __str__(self):
        return f'{self.ruta} | {timezone.localtime(self.fecha_salida):%d-%m-%Y %H:%M} | {self.bus.patente}'


class Asiento(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Asiento de un Servicio (unidad de "stock")
    - tipo (CHOICES): SEMICAMA / CAMA -> determina la tarifa.
    - estado (CHOICES): DISPONIBLE / OCUPADO.
    - (servicio, numero) es único: no existen dos asientos 12 en el
      mismo viaje.
    El cambio a OCUPADO lo realiza EXCLUSIVAMENTE el proceso de pago
    (ventas.services.procesar_pago) bajo bloqueo SELECT ... FOR UPDATE.
    -----------------------------------------------------------------
    """

    class Tipo(models.TextChoices):
        SEMICAMA = 'SEMICAMA', 'Semicama'
        CAMA = 'CAMA', 'Cama'

    class Estado(models.TextChoices):
        DISPONIBLE = 'DISPONIBLE', 'Disponible'
        OCUPADO = 'OCUPADO', 'Ocupado'

    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='asientos')
    numero = models.PositiveIntegerField()
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.DISPONIBLE)

    class Meta:
        verbose_name = 'Asiento'
        verbose_name_plural = 'Asientos'
        ordering = ['servicio', 'numero']
        constraints = [
            models.UniqueConstraint(fields=['servicio', 'numero'], name='asiento_unico_por_servicio'),
        ]

    @property
    def tarifa(self):
        """Precio actual del asiento según la tarifa del servicio."""
        return self.servicio.tarifa_para(self.tipo)

    def __str__(self):
        return f'Asiento {self.numero} ({self.get_tipo_display()}) - {self.servicio}'
