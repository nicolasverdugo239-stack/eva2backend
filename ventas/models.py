"""
=====================================================================
MODELOS DE LA APP "ventas"
=====================================================================
Relaciones principales:

    Usuario 1 ──── 1 Carro             (OneToOne: un carro activo por usuario)
    Carro   1 ──< N ItemCarro >── N 1 Asiento
    Usuario 1 ──< N Venta              (historial de órdenes)
    Venta   1 ──< N DetalleVenta >── N 1 Asiento
    DetalleVenta 1 ──── 1 Boleto       (OneToOne: se emite al pagar, con UUID)

Ciclo de vida de una Venta (CHOICES):
    PENDIENTE -> PAGADO -> COMPLETADO
    PENDIENTE -> CANCELADO
    PAGADO    -> CANCELADO (repone los asientos)
"""

import uuid

from django.conf import settings
from django.db import models


class Carro(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Carro de Pasajes PERSISTENTE
    - OneToOneField con el usuario => relación 1 a 1 garantizada por un
      índice UNIQUE sobre usuario_id en PostgreSQL.
    - El carro y sus ítems son filas de la BD (tablas ventas_carro y
      ventas_itemcarro), NO datos de sesión ni del frontend. Por eso
      sobreviven a un logout, a la expiración del token o a un inicio de
      sesión desde otro dispositivo: el carro se recupera siempre con
      Carro.objects.get(usuario=request.user).
    - Se crea automáticamente al registrar el usuario (ventas/signals.py).
    - Estado implícito: ACTIVO mientras exista; en el checkout sus ítems
      se "liquidan" (pasan a la Venta) y el carro queda vacío.
    -----------------------------------------------------------------
    """

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='carro')
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Carro de pasajes'
        verbose_name_plural = 'Carros de pasajes'

    @property
    def total(self):
        """Total a precio ACTUAL del catálogo (aún no congelado)."""
        return sum(item.subtotal for item in self.items.select_related('asiento__servicio'))

    def __str__(self):
        return f'Carro de {self.usuario.username}'


class TipoDocumento(models.TextChoices):
    """Tipo de documento de identidad del ocupante del asiento."""

    RUT = 'RUT', 'RUT'
    PASAPORTE = 'PASAPORTE', 'Pasaporte'


class ItemCarro(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Ítem del carro = un asiento + datos del ocupante
    - Cada asiento seleccionado lleva el nombre completo y RUT/Pasaporte
      de quien viajará.
    - UniqueConstraint (carro, asiento): el mismo asiento no puede
      agregarse dos veces al mismo carro (validación de duplicados a
      nivel de base de datos).
    - Agregar al carro NO reserva ni descuenta el asiento: sigue
      DISPONIBLE para todos hasta que alguna venta se PAGUE.
    -----------------------------------------------------------------
    """

    carro = models.ForeignKey(Carro, on_delete=models.CASCADE, related_name='items')
    asiento = models.ForeignKey('flota.Asiento', on_delete=models.CASCADE, related_name='items_carro')
    nombre_pasajero = models.CharField(max_length=150)
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumento.choices, default=TipoDocumento.RUT)
    documento_pasajero = models.CharField(max_length=20)
    agregado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Ítem del carro'
        verbose_name_plural = 'Ítems del carro'
        ordering = ['agregado']
        constraints = [
            models.UniqueConstraint(fields=['carro', 'asiento'], name='asiento_unico_en_carro'),
        ]

    @property
    def subtotal(self):
        return self.asiento.tarifa

    def __str__(self):
        return f'{self.asiento} -> {self.nombre_pasajero}'


class Venta(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Venta (Orden / Transacción histórica)
    - codigo: UUID público de la transacción.
    - estado (CHOICES): PENDIENTE, PAGADO, COMPLETADO, CANCELADO.
    - total: suma de los precios CONGELADOS en DetalleVenta.
    - FK usuario con PROTECT: no se puede borrar un usuario con ventas
      (se preserva el registro histórico).
    Las transiciones de estado se realizan SOLO a través de
    ventas/services.py, donde se aplica el descuento/reposición de
    asientos de forma atómica.
    -----------------------------------------------------------------
    """

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente de pago'
        PAGADO = 'PAGADO', 'Pagado'
        COMPLETADO = 'COMPLETADO', 'Completado / Viaje realizado'
        CANCELADO = 'CANCELADO', 'Cancelado'

    codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ventas')
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    total = models.PositiveIntegerField(default=0)
    creada = models.DateTimeField(auto_now_add=True)
    pagada_en = models.DateTimeField(null=True, blank=True)
    actualizada = models.DateTimeField(auto_now=True)
    observacion = models.CharField(max_length=255, blank=True, help_text='Motivo de cancelación u observaciones.')

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        ordering = ['-creada']

    def __str__(self):
        return f'Venta #{self.id} ({self.get_estado_display()}) - {self.usuario.username}'


class DetalleVenta(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Detalle de la venta con PRECIO CONGELADO
    Al hacer checkout se copian los datos del ítem del carro y la tarifa
    vigente en ese instante (precio_unitario, tipo_asiento). Así, si
    luego el administrador cambia la tarifa del servicio, la venta
    histórica no se altera.
    FK a Asiento con PROTECT: no se puede borrar un asiento ya vendido.
    -----------------------------------------------------------------
    """

    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    asiento = models.ForeignKey('flota.Asiento', on_delete=models.PROTECT, related_name='detalles_venta')
    nombre_pasajero = models.CharField(max_length=150)
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumento.choices)
    documento_pasajero = models.CharField(max_length=20)
    tipo_asiento = models.CharField(max_length=10)
    precio_unitario = models.PositiveIntegerField()

    class Meta:
        verbose_name = 'Detalle de venta'
        verbose_name_plural = 'Detalles de venta'

    def __str__(self):
        return f'Venta #{self.venta_id} - Asiento {self.asiento.numero}'


class Boleto(models.Model):
    """
    -----------------------------------------------------------------
    BLOQUE: Boleto de viaje
    - Se EMITE únicamente cuando la venta pasa a PAGADO.
    - OneToOne con DetalleVenta: un boleto por asiento vendido.
    - codigo: UUID único (código del ticket / QR de abordaje).
    - estado (CHOICES): VIGENTE, UTILIZADO (viaje completado) o ANULADO
      (venta cancelada, el asiento se libera).
    -----------------------------------------------------------------
    """

    class Estado(models.TextChoices):
        VIGENTE = 'VIGENTE', 'Vigente'
        UTILIZADO = 'UTILIZADO', 'Utilizado'
        ANULADO = 'ANULADO', 'Anulado'

    detalle = models.OneToOneField(DetalleVenta, on_delete=models.CASCADE, related_name='boleto')
    codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.VIGENTE)
    emitido = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Boleto'
        verbose_name_plural = 'Boletos'
        ordering = ['-emitido']

    def __str__(self):
        return f'Boleto {self.codigo}'
