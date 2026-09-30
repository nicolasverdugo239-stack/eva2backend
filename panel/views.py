"""
=====================================================================
PANEL WEB DEL ADMINISTRADOR DE FLOTA (CRUD CON FORMULARIOS HTML)
=====================================================================
Complementa la API REST con vistas HTML basadas en clases (CBV):
    ListView   -> listar (con filtros django-filter y paginación)
    CreateView -> crear   (formulario vacío)
    UpdateView -> editar  (formulario con datos actuales)
    DeleteView -> eliminar (página de confirmación)
    DetailView -> detalle (servicio con mapa de asientos, venta)

Seguridad: el panel usa sesión de Django (login en /panel/login/) y
todas las vistas exigen rol ADMIN_FLOTA (AdminFlotaRequeridoMixin).
Las ventas NO se editan directamente: el cambio de estado pasa por
ventas.services.cambiar_estado, igual que en la API, para que el stock
de asientos se descuente/reponga correctamente.
"""

from django.contrib import messages
from django.forms import Form
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView
from rest_framework.exceptions import APIException

from flota.filters import ServicioFilter
from flota.models import Asiento, Bus, Ciudad, Ruta, Servicio, Terminal
from usuarios.models import Usuario
from ventas import services
from ventas.filters import VentaFilter
from ventas.models import DetalleVenta, Venta

from .forms import BusForm, CambioEstadoVentaForm, CiudadForm, RutaForm, ServicioForm, TerminalForm


# =====================================================================
# BLOQUE: Control de acceso
# - Sin sesión          -> redirige a /panel/login/ (LoginRequiredMixin).
# - Con sesión sin rol  -> 403 Prohibido (UserPassesTestMixin).
# =====================================================================
class AdminFlotaRequeridoMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.rol == Usuario.Rol.ADMIN_FLOTA


# =====================================================================
# BLOQUE: Vistas genéricas reutilizables del CRUD
# Cada entidad define: modelo, formulario, títulos, prefijo de URL y
# columnas a mostrar. Las plantillas son comunes a todas las entidades.
# =====================================================================
class PanelMixin(AdminFlotaRequeridoMixin):
    titulo_singular = ''
    titulo_plural = ''
    prefijo_url = ''  # ej. "ciudad" -> panel:ciudad_lista, panel:ciudad_crear...

    def url(self, accion):
        return f'panel:{self.prefijo_url}_{accion}'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            'titulo_singular': self.titulo_singular,
            'titulo_plural': self.titulo_plural,
            'url_lista': self.url('lista'),
            'url_crear': self.url('crear'),
            'url_editar': self.url('editar'),
            'url_eliminar': self.url('eliminar'),
            'url_detalle': getattr(self, 'url_detalle', None),
        })
        return contexto


def resolver_valor(obj, ruta):
    """Obtiene un valor recorriendo atributos con puntos ("ruta.origen") y llamando métodos."""
    valor = obj
    for parte in ruta.split('.'):
        valor = getattr(valor, parte, None)
        if callable(valor):
            valor = valor()
    return valor


class PanelListView(PanelMixin, ListView):
    """
    Listado genérico: aplica el FilterSet (si existe) sobre el queryset y
    arma las filas de la tabla según "columnas" = [(titulo, atributo), ...].
    """

    template_name = 'panel/lista.html'
    paginate_by = 15
    columnas = []
    filterset_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.filterset_class:
            self.filtro = self.filterset_class(self.request.GET, queryset=queryset)
            return self.filtro.qs
        self.filtro = None
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['filtro'] = self.filtro
        contexto['encabezados'] = [titulo for titulo, _ in self.columnas]
        contexto['filas'] = [
            (obj, [resolver_valor(obj, atributo) for _, atributo in self.columnas])
            for obj in contexto['object_list']
        ]
        # Conserva los filtros al cambiar de página.
        parametros = self.request.GET.copy()
        parametros.pop('page', None)
        contexto['parametros'] = parametros.urlencode()
        return contexto


class PanelCreateView(PanelMixin, SuccessMessageMixin, CreateView):
    template_name = 'panel/formulario.html'
    success_message = 'Registro creado correctamente.'

    def get_success_url(self):
        return reverse(self.url('lista'))


class PanelUpdateView(PanelMixin, SuccessMessageMixin, UpdateView):
    template_name = 'panel/formulario.html'
    success_message = 'Registro actualizado correctamente.'

    def get_success_url(self):
        return reverse(self.url('lista'))


class PanelDeleteView(PanelMixin, DeleteView):
    """
    Eliminación con confirmación. Si el registro está protegido por una
    FK con on_delete=PROTECT (ej. una ciudad con terminales), Django
    lanza ProtectedError: se captura y se informa al usuario.
    """

    template_name = 'panel/confirmar_eliminar.html'

    def get_form_class(self):
        # La confirmación usa un formulario vacío (solo CSRF), no el
        # ModelForm de la entidad definido en la clase de configuración.
        return Form

    def get_success_url(self):
        return reverse(self.url('lista'))

    def form_valid(self, form):
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, 'No se puede eliminar: existen registros que dependen de este elemento.')
            return redirect(self.get_success_url())
        messages.success(self.request, 'Registro eliminado correctamente.')
        return respuesta


# =====================================================================
# BLOQUE: Inicio del panel (resumen)
# =====================================================================
class PanelInicioView(AdminFlotaRequeridoMixin, TemplateView):
    template_name = 'panel/inicio.html'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['totales'] = [
            ('Ciudades', Ciudad.objects.count(), 'panel:ciudad_lista'),
            ('Terminales', Terminal.objects.count(), 'panel:terminal_lista'),
            ('Rutas', Ruta.objects.count(), 'panel:ruta_lista'),
            ('Buses', Bus.objects.count(), 'panel:bus_lista'),
            ('Servicios', Servicio.objects.count(), 'panel:servicio_lista'),
            ('Ventas', Venta.objects.count(), 'panel:venta_lista'),
        ]
        conteo = dict(Venta.objects.values_list('estado').annotate(n=Count('id')))
        contexto['ventas_por_estado'] = [(etiqueta, conteo.get(valor, 0)) for valor, etiqueta in Venta.Estado.choices]
        return contexto


# =====================================================================
# BLOQUE: CRUD Ciudades
# =====================================================================
class CiudadConfig:
    model = Ciudad
    form_class = CiudadForm
    titulo_singular, titulo_plural, prefijo_url = 'Ciudad', 'Ciudades', 'ciudad'


class CiudadLista(CiudadConfig, PanelListView):
    columnas = [('Nombre', 'nombre'), ('Región', 'region')]


class CiudadCrear(CiudadConfig, PanelCreateView):
    pass


class CiudadEditar(CiudadConfig, PanelUpdateView):
    pass


class CiudadEliminar(CiudadConfig, PanelDeleteView):
    pass


# =====================================================================
# BLOQUE: CRUD Terminales
# =====================================================================
class TerminalConfig:
    model = Terminal
    form_class = TerminalForm
    titulo_singular, titulo_plural, prefijo_url = 'Terminal', 'Terminales', 'terminal'


class TerminalLista(TerminalConfig, PanelListView):
    queryset = Terminal.objects.select_related('ciudad')
    columnas = [('Nombre', 'nombre'), ('Ciudad', 'ciudad'), ('Dirección', 'direccion')]


class TerminalCrear(TerminalConfig, PanelCreateView):
    pass


class TerminalEditar(TerminalConfig, PanelUpdateView):
    pass


class TerminalEliminar(TerminalConfig, PanelDeleteView):
    pass


# =====================================================================
# BLOQUE: CRUD Rutas
# =====================================================================
class RutaConfig:
    model = Ruta
    form_class = RutaForm
    titulo_singular, titulo_plural, prefijo_url = 'Ruta', 'Rutas', 'ruta'


class RutaLista(RutaConfig, PanelListView):
    queryset = Ruta.objects.select_related('origen__ciudad', 'destino__ciudad')
    columnas = [('Origen', 'origen'), ('Destino', 'destino'), ('Distancia (km)', 'distancia_km'), ('Duración', 'duracion_estimada')]


class RutaCrear(RutaConfig, PanelCreateView):
    pass


class RutaEditar(RutaConfig, PanelUpdateView):
    pass


class RutaEliminar(RutaConfig, PanelDeleteView):
    pass


# =====================================================================
# BLOQUE: CRUD Buses
# =====================================================================
class BusConfig:
    model = Bus
    form_class = BusForm
    titulo_singular, titulo_plural, prefijo_url = 'Bus', 'Buses', 'bus'


class BusLista(BusConfig, PanelListView):
    columnas = [
        ('Patente', 'patente'), ('Marca', 'marca'), ('Modelo', 'modelo'), ('Año', 'anio'),
        ('Cama', 'asientos_cama'), ('Semicama', 'asientos_semicama'), ('Activo', 'activo'),
    ]


class BusCrear(BusConfig, PanelCreateView):
    pass


class BusEditar(BusConfig, PanelUpdateView):
    pass


class BusEliminar(BusConfig, PanelDeleteView):
    pass


# =====================================================================
# BLOQUE: CRUD Servicios (+ detalle con mapa de asientos)
# El listado reutiliza el mismo ServicioFilter de la API (django-filter)
# y anota el conteo de asientos disponibles calculado en PostgreSQL.
# =====================================================================
class ServicioConfig:
    model = Servicio
    form_class = ServicioForm
    titulo_singular, titulo_plural, prefijo_url = 'Servicio', 'Servicios', 'servicio'
    url_detalle = 'panel:servicio_detalle'


class ServicioLista(ServicioConfig, PanelListView):
    filterset_class = ServicioFilter
    columnas = [
        ('Ruta', 'ruta'), ('Salida', 'fecha_salida'), ('Bus', 'bus.patente'),
        ('Semicama $', 'tarifa_semicama'), ('Cama $', 'tarifa_cama'),
        ('Estado', 'get_estado_display'), ('Disponibles', 'asientos_disponibles'),
    ]

    def get_queryset(self):
        self.queryset = Servicio.objects.select_related(
            'ruta__origen__ciudad', 'ruta__destino__ciudad', 'bus'
        ).annotate(
            asientos_disponibles=Count('asientos', filter=Q(asientos__estado=Asiento.Estado.DISPONIBLE))
        ).order_by('fecha_salida', 'id')
        return super().get_queryset()


class ServicioCrear(ServicioConfig, PanelCreateView):
    success_message = 'Servicio creado. Sus asientos se generaron automáticamente según el bus.'


class ServicioEditar(ServicioConfig, PanelUpdateView):
    pass


class ServicioEliminar(ServicioConfig, PanelDeleteView):
    pass


class ServicioDetalle(ServicioConfig, PanelMixin, DetailView):
    template_name = 'panel/servicio_detalle.html'
    queryset = Servicio.objects.select_related('ruta__origen__ciudad', 'ruta__destino__ciudad', 'bus')

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['asientos'] = self.object.asientos.all()
        return contexto


# =====================================================================
# BLOQUE: Ventas (listar, ver detalle y cambiar estado)
# No hay crear/editar/eliminar: las ventas nacen del checkout y son un
# registro histórico. Solo se cambia su estado mediante la capa de
# servicios, que descuenta o repone los asientos.
# =====================================================================
class VentaLista(PanelListView):
    model = Venta
    titulo_singular, titulo_plural, prefijo_url = 'Venta', 'Ventas', 'venta'
    url_detalle = 'panel:venta_detalle'
    filterset_class = VentaFilter
    queryset = Venta.objects.select_related('usuario')
    columnas = [
        ('N°', 'id'), ('Usuario', 'usuario.username'), ('Estado', 'get_estado_display'),
        ('Total $', 'total'), ('Creada', 'creada'), ('Pagada', 'pagada_en'),
    ]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # Las ventas no se crean/editan/eliminan desde el panel.
        contexto.update({'url_crear': None, 'url_editar': None, 'url_eliminar': None})
        return contexto


class VentaDetalle(AdminFlotaRequeridoMixin, DetailView):
    model = Venta
    template_name = 'panel/venta_detalle.html'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['detalles'] = DetalleVenta.objects.filter(venta=self.object).select_related('asiento__servicio__ruta__origen__ciudad', 'asiento__servicio__ruta__destino__ciudad', 'boleto')
        contexto['form'] = kwargs.get('form') or CambioEstadoVentaForm(venta=self.object)
        return contexto


class VentaCambiarEstado(AdminFlotaRequeridoMixin, View):
    """
    Procesa el formulario (POST) de cambio de estado. Si la regla de
    negocio lo rechaza (transición inválida, asiento ya vendido, bus ya
    salió) se muestra el mensaje de error y no se modifica nada.
    """

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk)
        form = CambioEstadoVentaForm(request.POST, venta=venta)
        if form.is_valid():
            try:
                services.cambiar_estado(venta.id, form.cleaned_data['estado'], form.cleaned_data['observacion'])
                messages.success(request, f'Venta #{venta.id} actualizada a {form.cleaned_data["estado"]}.')
            except APIException as error:
                detalle = error.detail
                if isinstance(detalle, dict):
                    detalle = ' '.join(str(x) for x in detalle.get('asientos', [])) or detalle.get('detail')
                messages.error(request, f'No se pudo cambiar el estado: {detalle}')
        else:
            messages.error(request, 'Seleccione un estado válido.')
        return redirect('panel:venta_detalle', pk=venta.id)
