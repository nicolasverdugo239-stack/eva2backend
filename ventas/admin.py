"""
=====================================================================
ADMIN DE VENTAS
=====================================================================
El estado de la Venta es de SOLO LECTURA en el panel: para cambiarlo se
usan las acciones del admin, que llaman a ventas.services.cambiar_estado
y así también se descuenta/repone el stock de asientos correctamente.
"""

from django.contrib import admin, messages
from rest_framework.exceptions import APIException

from . import services
from .models import Boleto, Carro, DetalleVenta, ItemCarro, Venta


class ItemCarroInline(admin.TabularInline):
    model = ItemCarro
    extra = 0


@admin.register(Carro)
class CarroAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'actualizado')
    inlines = [ItemCarroInline]


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    can_delete = False
    readonly_fields = ('asiento', 'nombre_pasajero', 'tipo_documento', 'documento_pasajero', 'tipo_asiento', 'precio_unitario')


def _accion_estado(nuevo_estado, descripcion):
    """Fabrica una acción de admin que cambia el estado vía la capa de servicios."""

    def accion(modeladmin, request, queryset):
        for venta in queryset:
            try:
                services.cambiar_estado(venta.id, nuevo_estado, 'Cambio desde el panel de administración')
                modeladmin.message_user(request, f'Venta #{venta.id} -> {nuevo_estado}', messages.SUCCESS)
            except APIException as error:
                modeladmin.message_user(request, f'Venta #{venta.id}: {error.detail}', messages.ERROR)

    accion.short_description = descripcion
    accion.__name__ = f'marcar_{nuevo_estado.lower()}'
    return accion


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'estado', 'total', 'creada', 'pagada_en')
    list_filter = ('estado',)
    readonly_fields = ('codigo', 'usuario', 'estado', 'total', 'creada', 'pagada_en')
    inlines = [DetalleVentaInline]
    actions = [
        _accion_estado(Venta.Estado.PAGADO, 'Marcar como PAGADO'),
        _accion_estado(Venta.Estado.COMPLETADO, 'Marcar como COMPLETADO'),
        _accion_estado(Venta.Estado.CANCELADO, 'CANCELAR (repone asientos)'),
    ]


@admin.register(Boleto)
class BoletoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'detalle', 'estado', 'emitido')
    list_filter = ('estado',)
    readonly_fields = ('codigo', 'detalle', 'estado', 'emitido')
