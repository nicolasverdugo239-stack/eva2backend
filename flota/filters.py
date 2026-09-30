"""
=====================================================================
FILTROS (django-filter) DEL CATÁLOGO
=====================================================================
Cada FilterSet traduce parámetros GET a condiciones WHERE sobre el ORM.
Ejemplo:
  /api/servicios/?origen=santiago&destino=valpo&fecha=2026-10-05&tarifa_max=10000
  => WHERE ciudad_origen ILIKE '%santiago%' AND ciudad_destino ILIKE '%valpo%'
     AND fecha_salida::date = '2026-10-05' AND tarifa_semicama <= 10000
"""

import django_filters
from django.db.models import Exists, OuterRef

from .models import Asiento, Ruta, Servicio


class ServicioFilter(django_filters.FilterSet):
    """
    -----------------------------------------------------------------
    BLOQUE: Filtros de Servicios
    - origen / destino: nombre de la ciudad (búsqueda parcial, sin
      distinguir mayúsculas) recorriendo Ruta -> Terminal -> Ciudad.
    - fecha: día exacto de salida; fecha_desde / fecha_hasta: rango.
    - tarifa_min / tarifa_max: rango de precio (tarifa semicama, la base).
    - estado: CHOICES del servicio.
    - tipo_asiento: servicios que tengan asientos DISPONIBLES de ese tipo.
    - con_disponibilidad=true: solo servicios con al menos 1 asiento libre.
    -----------------------------------------------------------------
    """

    origen = django_filters.CharFilter(field_name='ruta__origen__ciudad__nombre', lookup_expr='icontains')
    destino = django_filters.CharFilter(field_name='ruta__destino__ciudad__nombre', lookup_expr='icontains')
    fecha = django_filters.DateFilter(field_name='fecha_salida', lookup_expr='date')
    fecha_desde = django_filters.DateFilter(field_name='fecha_salida', lookup_expr='date__gte')
    fecha_hasta = django_filters.DateFilter(field_name='fecha_salida', lookup_expr='date__lte')
    tarifa_min = django_filters.NumberFilter(field_name='tarifa_semicama', lookup_expr='gte')
    tarifa_max = django_filters.NumberFilter(field_name='tarifa_semicama', lookup_expr='lte')
    estado = django_filters.ChoiceFilter(choices=Servicio.Estado.choices)
    tipo_asiento = django_filters.ChoiceFilter(choices=Asiento.Tipo.choices, method='filtrar_tipo_asiento')
    con_disponibilidad = django_filters.BooleanFilter(method='filtrar_disponibilidad')

    class Meta:
        model = Servicio
        fields = ['ruta', 'bus', 'estado']

    def filtrar_tipo_asiento(self, queryset, name, value):
        # Subconsulta EXISTS: no agrega JOIN, así no altera los COUNT anotados.
        libres_del_tipo = Asiento.objects.filter(
            servicio=OuterRef('pk'), tipo=value, estado=Asiento.Estado.DISPONIBLE
        )
        return queryset.filter(Exists(libres_del_tipo))

    def filtrar_disponibilidad(self, queryset, name, value):
        # "asientos_disponibles" es una anotación (COUNT) agregada en la vista.
        if value:
            return queryset.filter(asientos_disponibles__gt=0)
        return queryset.filter(asientos_disponibles=0)


class AsientoFilter(django_filters.FilterSet):
    """Filtra los asientos de un servicio por tipo y estado."""

    tipo = django_filters.ChoiceFilter(choices=Asiento.Tipo.choices)
    estado = django_filters.ChoiceFilter(choices=Asiento.Estado.choices)

    class Meta:
        model = Asiento
        fields = ['tipo', 'estado']


class RutaFilter(django_filters.FilterSet):
    """Filtra rutas por ciudad de origen/destino y distancia máxima."""

    origen = django_filters.CharFilter(field_name='origen__ciudad__nombre', lookup_expr='icontains')
    destino = django_filters.CharFilter(field_name='destino__ciudad__nombre', lookup_expr='icontains')
    distancia_max = django_filters.NumberFilter(field_name='distancia_km', lookup_expr='lte')

    class Meta:
        model = Ruta
        fields = ['origen', 'destino']
