"""Registro de los modelos de flota en el panel /admin/."""

from django.contrib import admin

from .models import Asiento, Bus, Ciudad, Ruta, Servicio, Terminal


@admin.register(Ciudad)
class CiudadAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'region')
    search_fields = ('nombre',)


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ciudad', 'direccion')
    list_filter = ('ciudad',)


@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'distancia_km', 'duracion_estimada')


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ('patente', 'marca', 'modelo', 'asientos_cama', 'asientos_semicama', 'activo')


class AsientoInline(admin.TabularInline):
    model = Asiento
    extra = 0
    # El estado del asiento solo lo cambia el flujo de pago/cancelación.
    readonly_fields = ('numero', 'tipo', 'estado')
    can_delete = False


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'estado', 'tarifa_semicama', 'tarifa_cama')
    list_filter = ('estado', 'ruta')
    inlines = [AsientoInline]
