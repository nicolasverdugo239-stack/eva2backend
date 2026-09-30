"""
=====================================================================
RUTAS DEL PANEL WEB (prefijo /panel/)
=====================================================================
Para cada entidad del catálogo se generan 4 rutas CRUD:
    /panel/<entidad>/                 listar
    /panel/<entidad>/nuevo/           crear
    /panel/<entidad>/<id>/editar/     editar
    /panel/<entidad>/<id>/eliminar/   eliminar
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'panel'


def rutas_crud(segmento, prefijo, lista, crear, editar, eliminar):
    """Genera las 4 rutas CRUD de una entidad con nombres <prefijo>_lista, _crear, _editar, _eliminar."""
    return [
        path(f'{segmento}/', lista.as_view(), name=f'{prefijo}_lista'),
        path(f'{segmento}/nuevo/', crear.as_view(), name=f'{prefijo}_crear'),
        path(f'{segmento}/<int:pk>/editar/', editar.as_view(), name=f'{prefijo}_editar'),
        path(f'{segmento}/<int:pk>/eliminar/', eliminar.as_view(), name=f'{prefijo}_eliminar'),
    ]


urlpatterns = [
    path('', views.PanelInicioView.as_view(), name='inicio'),
    path('login/', auth_views.LoginView.as_view(template_name='panel/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    *rutas_crud('ciudades', 'ciudad', views.CiudadLista, views.CiudadCrear, views.CiudadEditar, views.CiudadEliminar),
    *rutas_crud('terminales', 'terminal', views.TerminalLista, views.TerminalCrear, views.TerminalEditar, views.TerminalEliminar),
    *rutas_crud('rutas', 'ruta', views.RutaLista, views.RutaCrear, views.RutaEditar, views.RutaEliminar),
    *rutas_crud('buses', 'bus', views.BusLista, views.BusCrear, views.BusEditar, views.BusEliminar),
    *rutas_crud('servicios', 'servicio', views.ServicioLista, views.ServicioCrear, views.ServicioEditar, views.ServicioEliminar),
    path('servicios/<int:pk>/', views.ServicioDetalle.as_view(), name='servicio_detalle'),

    path('ventas/', views.VentaLista.as_view(), name='venta_lista'),
    path('ventas/<int:pk>/', views.VentaDetalle.as_view(), name='venta_detalle'),
    path('ventas/<int:pk>/estado/', views.VentaCambiarEstado.as_view(), name='venta_estado'),
]
