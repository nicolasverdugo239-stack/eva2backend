"""
=====================================================================
VISTAS BASE DEL PROYECTO
=====================================================================
- InicioView: página HTML "/" con resumen de endpoints y footer del alumno.
- api_raiz:   GET /api/ en JSON, con el índice de endpoints y los datos
              del alumno (footer también en la respuesta de la API).
"""

from django.conf import settings
from django.views.generic import TemplateView
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# ---------------------------------------------------------------------
# BLOQUE: Índice de endpoints (matriz de roles del Proyecto 4)
# Se reutiliza en la página HTML y en la raíz JSON de la API.
# ---------------------------------------------------------------------
ENDPOINTS = [
    ('Público', 'GET', '/api/servicios/buscar/?origen=&destino=&fecha=', 'Buscar pasajes'),
    ('Público', 'GET', '/api/servicios/{id}/asientos/', 'Mapa de asientos de un servicio'),
    ('Público', 'GET', '/api/servicios/', 'Listado de servicios con filtros'),
    ('Público', 'GET', '/api/ciudades/ · /api/terminales/ · /api/rutas/', 'Catálogo'),
    ('Público', 'POST', '/api/auth/registro/ · /api/auth/login/ · /api/auth/refresh/', 'Registro y JWT'),
    ('Pasajero', 'GET/POST/DELETE', '/api/carro-pasajes/', 'Carro de pasajes persistente'),
    ('Pasajero', 'PATCH/DELETE', '/api/carro-pasajes/{item_id}/', 'Editar / quitar ítem'),
    ('Pasajero', 'POST', '/api/ventas/checkout/', 'Confirmar compra (checkout + pago)'),
    ('Pasajero', 'POST', '/api/ventas/{id}/pagar/', 'Pagar venta pendiente'),
    ('Pasajero', 'GET', '/api/mis-boletos/ · /api/mis-ventas/', 'Boletos e historial'),
    ('Admin Flota', 'POST/PUT/PATCH/DELETE', '/api/servicios/', 'Gestión de servicios'),
    ('Admin Flota', 'CRUD', '/api/buses/ · /api/ciudades/ · /api/terminales/ · /api/rutas/', 'Gestión de flota'),
    ('Admin Flota', 'GET', '/api/ventas/', 'Todas las ventas'),
    ('Admin Flota', 'PATCH', '/api/ventas/{id}/estado/', 'Cambiar estado de venta'),
    ('Admin Flota', 'WEB', '/panel/', 'CRUD web con formularios (ciudades, terminales, rutas, buses, servicios, ventas)'),
]


class InicioView(TemplateView):
    template_name = 'inicio.html'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['endpoints'] = ENDPOINTS
        return contexto


@extend_schema(exclude=True)
@api_view(['GET'])
@permission_classes([AllowAny])
def api_raiz(request):
    return Response({
        'proyecto': 'API Pasajes de Buses Interurbanos',
        'documentacion': request.build_absolute_uri('/api/docs/'),
        'endpoints': [
            {'rol': rol, 'metodo': metodo, 'ruta': ruta, 'descripcion': desc}
            for rol, metodo, ruta, desc in ENDPOINTS
        ],
        'alumno': settings.DATOS_ALUMNO,
    })
