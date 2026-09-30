"""
=====================================================================
FILTROS (django-filter) DE VENTAS Y BOLETOS
=====================================================================
Ejemplos:
  /api/ventas/?estado=PAGADO&creada_desde=2026-10-01&total_min=20000
  /api/mis-boletos/?estado=VIGENTE&origen=santiago
"""

import django_filters

from .models import Boleto, Venta


class VentaFilter(django_filters.FilterSet):
    """Filtra ventas por estado, rango de fechas, rango de total y usuario."""

    estado = django_filters.ChoiceFilter(choices=Venta.Estado.choices)
    creada_desde = django_filters.DateFilter(field_name='creada', lookup_expr='date__gte')
    creada_hasta = django_filters.DateFilter(field_name='creada', lookup_expr='date__lte')
    total_min = django_filters.NumberFilter(field_name='total', lookup_expr='gte')
    total_max = django_filters.NumberFilter(field_name='total', lookup_expr='lte')
    usuario = django_filters.CharFilter(field_name='usuario__username', lookup_expr='iexact')

    class Meta:
        model = Venta
        fields = ['estado', 'usuario']


class BoletoFilter(django_filters.FilterSet):
    """Filtra los boletos del pasajero por estado, servicio, ciudad y fecha de viaje."""

    estado = django_filters.ChoiceFilter(choices=Boleto.Estado.choices)
    servicio = django_filters.NumberFilter(field_name='detalle__asiento__servicio')
    origen = django_filters.CharFilter(field_name='detalle__asiento__servicio__ruta__origen__ciudad__nombre', lookup_expr='icontains')
    destino = django_filters.CharFilter(field_name='detalle__asiento__servicio__ruta__destino__ciudad__nombre', lookup_expr='icontains')
    fecha_viaje = django_filters.DateFilter(field_name='detalle__asiento__servicio__fecha_salida', lookup_expr='date')

    class Meta:
        model = Boleto
        fields = ['estado']
