"""
=====================================================================
FORMULARIOS DEL PANEL WEB (CRUD HTML)
=====================================================================
ModelForms que generan los formularios HTML del panel del
Administrador de Flota. Al validar, Django ejecuta:
  1. Validación de cada campo (tipos, requeridos, choices).
  2. Los métodos clean_<campo>() y clean() definidos aquí.
  3. model.full_clean(): Model.clean() y las constraints del modelo
     (UniqueConstraint / CheckConstraint), p. ej. ruta_origen_distinto_destino.
Si algo falla, el formulario se vuelve a mostrar con los errores.
"""

from django import forms
from django.utils import timezone

from flota.models import Bus, Ciudad, Ruta, Servicio, Terminal
from ventas.models import Venta
from ventas.services import TRANSICIONES


class EstiloMixin:
    """Agrega la clase CSS "campo" a todos los widgets para un estilo uniforme."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'campo')


class CiudadForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Ciudad
        fields = ['nombre', 'region']


class TerminalForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Terminal
        fields = ['nombre', 'direccion', 'ciudad']


class RutaForm(EstiloMixin, forms.ModelForm):
    """
    La duración se ingresa como HH:MM:SS (DurationField).
    La regla "origen distinto de destino" la valida Ruta.clean() y la
    CheckConstraint del modelo.
    """

    class Meta:
        model = Ruta
        fields = ['origen', 'destino', 'distancia_km', 'duracion_estimada']
        help_texts = {'duracion_estimada': 'Formato HH:MM:SS, por ejemplo 02:30:00'}


class BusForm(EstiloMixin, forms.ModelForm):
    """
    Nota: modificar la cantidad de asientos de un bus solo afecta a los
    servicios que se creen DESPUÉS; los asientos de servicios existentes
    ya fueron generados por la señal.
    """

    class Meta:
        model = Bus
        fields = ['patente', 'marca', 'modelo', 'anio', 'asientos_cama', 'asientos_semicama', 'activo']

    def clean_patente(self):
        return self.cleaned_data['patente'].upper().replace(' ', '')

    def clean(self):
        datos = super().clean()
        if (datos.get('asientos_cama') or 0) + (datos.get('asientos_semicama') or 0) == 0:
            raise forms.ValidationError('El bus debe tener al menos un asiento.')
        return datos


class ServicioForm(EstiloMixin, forms.ModelForm):
    """
    -----------------------------------------------------------------
    BLOQUE: Formulario de Servicio
    - fecha_salida usa un <input type="datetime-local">.
    - Al CREAR: la salida debe ser futura, solo buses activos, y el
      estado siempre inicia en PROGRAMADO (campo oculto).
    - Al EDITAR: el bus queda deshabilitado, porque los asientos del
      servicio se generaron con la distribución de ese bus.
    -----------------------------------------------------------------
    """

    fecha_salida = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        input_formats=['%Y-%m-%dT%H:%M'],
    )

    class Meta:
        model = Servicio
        fields = ['ruta', 'bus', 'fecha_salida', 'tarifa_semicama', 'tarifa_cama', 'estado']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['bus'].disabled = True
        else:
            self.fields['bus'].queryset = Bus.objects.filter(activo=True)
            del self.fields['estado']

    def clean_fecha_salida(self):
        valor = self.cleaned_data['fecha_salida']
        if not self.instance.pk and valor <= timezone.now():
            raise forms.ValidationError('La fecha de salida debe ser futura.')
        return valor


class CambioEstadoVentaForm(EstiloMixin, forms.Form):
    """
    Cambio de estado de una venta desde el panel. Las opciones se limitan
    a las transiciones permitidas por la máquina de estados (TRANSICIONES)
    según el estado actual de la venta.
    """

    estado = forms.ChoiceField()
    observacion = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, venta, **kwargs):
        super().__init__(*args, **kwargs)
        permitidos = TRANSICIONES[venta.estado]
        self.fields['estado'].choices = [
            (valor, etiqueta) for valor, etiqueta in Venta.Estado.choices if valor in permitidos
        ]
