"""
=====================================================================
URLS PRINCIPALES DEL PROYECTO
=====================================================================
    /                 -> página HTML base (footer con datos del alumno)
    /admin/           -> panel de administración de Django
    /panel/           -> CRUD web con formularios (Administrador de Flota)
    /api/             -> raíz JSON de la API
    /api/auth/...     -> autenticación JWT
    /api/...          -> catálogo (router), carro, ventas y boletos
    /api/schema/      -> esquema OpenAPI 3 (YAML/JSON)
    /api/docs/        -> Swagger UI
    /api/redoc/       -> ReDoc
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from flota.views import BusViewSet, CiudadViewSet, RutaViewSet, ServicioViewSet, TerminalViewSet
from ventas.views import CarroItemView, CarroPasajesView, MisBoletosView, MisVentasView, VentaViewSet

from .views import InicioView, api_raiz

# ---------------------------------------------------------------------
# BLOQUE: Router DRF
# Genera automáticamente las rutas list/detail de cada ViewSet y las
# acciones extra (@action), por ejemplo:
#   /api/servicios/buscar/            (detail=False)
#   /api/servicios/{id}/asientos/     (detail=True)
#   /api/ventas/checkout/             (detail=False)
#   /api/ventas/{id}/estado/          (detail=True)
# ---------------------------------------------------------------------
router = DefaultRouter()
router.include_root_view = False
router.register('ciudades', CiudadViewSet, basename='ciudad')
router.register('terminales', TerminalViewSet, basename='terminal')
router.register('rutas', RutaViewSet, basename='ruta')
router.register('buses', BusViewSet, basename='bus')
router.register('servicios', ServicioViewSet, basename='servicio')
router.register('ventas', VentaViewSet, basename='venta')

urlpatterns = [
    path('', InicioView.as_view(), name='inicio'),
    path('admin/', admin.site.urls),
    path('panel/', include('panel.urls')),  # CRUD web con formularios
    path('api/', api_raiz, name='api-raiz'),
    path('api/auth/', include('usuarios.urls')),
    path('api/carro-pasajes/', CarroPasajesView.as_view(), name='carro-pasajes'),
    path('api/carro-pasajes/<int:item_id>/', CarroItemView.as_view(), name='carro-item'),
    path('api/mis-boletos/', MisBoletosView.as_view(), name='mis-boletos'),
    path('api/mis-ventas/', MisVentasView.as_view(), name='mis-ventas'),
    path('api/', include(router.urls)),
    # Documentación OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
