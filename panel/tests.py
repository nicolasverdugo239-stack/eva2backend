"""
=====================================================================
PRUEBAS DEL PANEL WEB (CRUD CON FORMULARIOS)
=====================================================================
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from flota.models import Asiento, Bus, Ciudad, Ruta, Servicio, Terminal
from usuarios.models import Usuario
from ventas import services
from ventas.models import Carro, ItemCarro, Venta


class PanelCrudTests(TestCase):

    def setUp(self):
        self.admin = Usuario.objects.create_user('admin', 'a@a.cl', 'Clave12345!', rol=Usuario.Rol.ADMIN_FLOTA)
        self.pasajero = Usuario.objects.create_user('pasajero', 'p@p.cl', 'Clave12345!')
        self.stgo = Ciudad.objects.create(nombre='Santiago', region='RM')
        self.t1 = Terminal.objects.create(nombre='Alameda', direccion='x', ciudad=self.stgo)
        self.t2 = Terminal.objects.create(nombre='Rodoviario', direccion='y', ciudad=Ciudad.objects.create(nombre='Valparaíso', region='V'))
        self.ruta = Ruta.objects.create(origen=self.t1, destino=self.t2, distancia_km=120, duracion_estimada=timedelta(hours=2))
        self.bus = Bus.objects.create(patente='AA1111', marca='Volvo', modelo='B', anio=2022, asientos_cama=2, asientos_semicama=2)

    # --- Bloque: acceso ------------------------------------------------
    def test_acceso_restringido(self):
        self.assertRedirects(self.client.get('/panel/ciudades/'), '/panel/login/?next=/panel/ciudades/')
        self.client.login(username='pasajero', password='Clave12345!')
        self.assertEqual(self.client.get('/panel/ciudades/').status_code, 403)

    # --- Bloque: CRUD completo de Ciudad -------------------------------
    def test_crud_ciudad(self):
        self.client.login(username='admin', password='Clave12345!')
        self.assertEqual(self.client.get('/panel/ciudades/').status_code, 200)
        self.client.post('/panel/ciudades/nuevo/', {'nombre': 'Talca', 'region': 'Maule'})
        talca = Ciudad.objects.get(nombre='Talca')
        self.client.post(f'/panel/ciudades/{talca.pk}/editar/', {'nombre': 'Talca', 'region': 'Del Maule'})
        talca.refresh_from_db()
        self.assertEqual(talca.region, 'Del Maule')
        self.client.post(f'/panel/ciudades/{talca.pk}/eliminar/')
        self.assertFalse(Ciudad.objects.filter(pk=talca.pk).exists())

    def test_eliminar_protegido(self):
        self.client.login(username='admin', password='Clave12345!')
        respuesta = self.client.post(f'/panel/ciudades/{self.stgo.pk}/eliminar/', follow=True)
        self.assertContains(respuesta, 'No se puede eliminar')
        self.assertTrue(Ciudad.objects.filter(pk=self.stgo.pk).exists())

    def test_ruta_origen_igual_destino_rechazada(self):
        self.client.login(username='admin', password='Clave12345!')
        respuesta = self.client.post('/panel/rutas/nuevo/', {
            'origen': self.t1.pk, 'destino': self.t1.pk, 'distancia_km': 10, 'duracion_estimada': '01:00:00',
        })
        self.assertEqual(respuesta.status_code, 200)  # vuelve a mostrar el formulario con errores
        self.assertEqual(Ruta.objects.count(), 1)

    # --- Bloque: Servicio (crear genera asientos) ----------------------
    def test_crear_servicio_genera_asientos(self):
        self.client.login(username='admin', password='Clave12345!')
        salida = (timezone.localtime() + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M')
        self.client.post('/panel/servicios/nuevo/', {
            'ruta': self.ruta.pk, 'bus': self.bus.pk, 'fecha_salida': salida,
            'tarifa_semicama': 5000, 'tarifa_cama': 8000,
        })
        servicio = Servicio.objects.get()
        self.assertEqual(servicio.asientos.count(), 4)
        self.assertEqual(self.client.get(f'/panel/servicios/{servicio.pk}/').status_code, 200)
        self.assertEqual(self.client.get('/panel/servicios/?origen=santiago').status_code, 200)

    # --- Bloque: Venta, cancelación desde el panel repone stock -------
    def test_cancelar_venta_desde_panel(self):
        servicio = Servicio.objects.create(ruta=self.ruta, bus=self.bus, fecha_salida=timezone.now() + timedelta(days=1),
                                           tarifa_semicama=5000, tarifa_cama=8000)
        asiento = servicio.asientos.first()
        ItemCarro.objects.create(carro=Carro.objects.get(usuario=self.pasajero), asiento=asiento,
                                 nombre_pasajero='Juan', documento_pasajero='11111111-1')
        venta = services.checkout(self.pasajero)

        self.client.login(username='admin', password='Clave12345!')
        self.assertEqual(self.client.get(f'/panel/ventas/{venta.pk}/').status_code, 200)
        self.client.post(f'/panel/ventas/{venta.pk}/estado/', {'estado': 'CANCELADO', 'observacion': 'x'})
        venta.refresh_from_db()
        asiento.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.CANCELADO)
        self.assertEqual(asiento.estado, Asiento.Estado.DISPONIBLE)
