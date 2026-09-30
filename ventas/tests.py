"""
=====================================================================
PRUEBAS AUTOMÁTICAS DE LOS FLUJOS CRÍTICOS
Ejecutar con:  python manage.py test
(Django crea una base de datos PostgreSQL temporal "test_...")
=====================================================================
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from flota.models import Asiento, Bus, Ciudad, Ruta, Servicio, Terminal
from usuarios.models import Usuario
from ventas.models import Boleto, Carro, Venta


class FlujoPasajesTests(APITestCase):

    # -----------------------------------------------------------------
    # BLOQUE: Datos base (ruta Santiago -> Valparaíso, bus de 2+2)
    # -----------------------------------------------------------------
    def setUp(self):
        self.admin = Usuario.objects.create_user('admin', 'a@a.cl', 'Clave12345!', rol=Usuario.Rol.ADMIN_FLOTA)
        self.pasajero = Usuario.objects.create_user('pasajero', 'p@p.cl', 'Clave12345!')
        self.otro = Usuario.objects.create_user('otro', 'o@o.cl', 'Clave12345!')

        stgo = Terminal.objects.create(nombre='Alameda', direccion='x', ciudad=Ciudad.objects.create(nombre='Santiago', region='RM'))
        valpo = Terminal.objects.create(nombre='Rodoviario', direccion='y', ciudad=Ciudad.objects.create(nombre='Valparaíso', region='V'))
        ruta = Ruta.objects.create(origen=stgo, destino=valpo, distancia_km=120, duracion_estimada=timedelta(hours=2))
        bus = Bus.objects.create(patente='AA1111', marca='Volvo', modelo='B', anio=2022, asientos_cama=2, asientos_semicama=2)
        self.servicio = Servicio.objects.create(
            ruta=ruta, bus=bus, fecha_salida=timezone.now() + timedelta(days=2),
            tarifa_semicama=5000, tarifa_cama=8000,
        )
        self.asiento_cama = self.servicio.asientos.get(numero=1)
        self.asiento_semi = self.servicio.asientos.get(numero=3)

    def login(self, username):
        respuesta = self.client.post('/api/auth/login/', {'username': username, 'password': 'Clave12345!'})
        self.assertEqual(respuesta.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {respuesta.data["access"]}')
        return respuesta.data

    def agregar(self, asiento, rut='11.111.111-1', nombre='Juan Pérez'):
        return self.client.post('/api/carro-pasajes/', {
            'asiento': asiento.id, 'nombre_pasajero': nombre,
            'tipo_documento': 'RUT', 'documento_pasajero': rut,
        })

    # -----------------------------------------------------------------
    # BLOQUE: JWT y permisos
    # -----------------------------------------------------------------
    def test_login_incluye_claim_rol(self):
        datos = self.login('admin')
        self.assertEqual(AccessToken(datos['access'])['rol'], 'ADMIN_FLOTA')
        self.assertIn('refresh', datos)

    def test_asientos_generados_por_senal(self):
        self.assertEqual(self.servicio.asientos.count(), 4)
        self.assertEqual(self.servicio.asientos.filter(tipo=Asiento.Tipo.CAMA).count(), 2)

    def test_catalogo_publico_y_escritura_restringida(self):
        self.assertEqual(self.client.get('/api/servicios/buscar/?origen=santiago&destino=valpa').data['count'], 1)
        self.assertEqual(self.client.get(f'/api/servicios/{self.servicio.id}/asientos/').status_code, 200)
        self.assertEqual(self.client.delete(f'/api/servicios/{self.servicio.id}/').status_code, 401)
        self.login('pasajero')
        self.assertEqual(self.client.delete(f'/api/servicios/{self.servicio.id}/').status_code, 403)
        self.assertEqual(self.client.get('/api/carro-pasajes/').status_code, 200)

    def test_filtros_servicio(self):
        self.assertEqual(self.client.get('/api/servicios/?tarifa_max=4000').data['count'], 0)
        self.assertEqual(self.client.get('/api/servicios/?tarifa_min=4000&origen=Santiago').data['count'], 1)
        self.assertEqual(self.client.get('/api/servicios/?destino=Temuco').data['count'], 0)

    # -----------------------------------------------------------------
    # BLOQUE: Carro persistente
    # -----------------------------------------------------------------
    def test_carro_persiste_tras_logout(self):
        datos = self.login('pasajero')
        self.assertEqual(self.agregar(self.asiento_cama).status_code, 201)
        # Agregar al carro NO descuenta el asiento.
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, Asiento.Estado.DISPONIBLE)
        # Duplicado rechazado.
        self.assertEqual(self.agregar(self.asiento_cama, rut='22.222.222-2').status_code, 400)

        self.client.post('/api/auth/logout/', {'refresh': datos['refresh']})
        self.client.credentials()
        self.login('pasajero')  # "otro dispositivo"
        carro = self.client.get('/api/carro-pasajes/').data
        self.assertEqual(len(carro['items']), 1)
        self.assertEqual(carro['total'], 8000)
        self.assertEqual(Carro.objects.filter(usuario=self.pasajero).count(), 1)

    def test_rut_invalido(self):
        self.login('pasajero')
        self.assertEqual(self.agregar(self.asiento_cama, rut='11.111.111-2').status_code, 400)

    # -----------------------------------------------------------------
    # BLOQUE: Checkout, pago, stock y cancelación
    # -----------------------------------------------------------------
    def test_checkout_paga_descuenta_y_emite_boletos(self):
        self.login('pasajero')
        self.agregar(self.asiento_cama)
        self.agregar(self.asiento_semi, rut='22.222.222-2', nombre='Ana Soto')
        respuesta = self.client.post('/api/ventas/checkout/', {'pagar': True})
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data['estado'], 'PAGADO')
        self.assertEqual(respuesta.data['total'], 13000)
        self.assertEqual(Asiento.objects.filter(servicio=self.servicio, estado='OCUPADO').count(), 2)
        self.assertEqual(Boleto.objects.count(), 2)
        self.assertEqual(len(self.client.get('/api/carro-pasajes/').data['items']), 0)
        self.assertEqual(self.client.get('/api/mis-boletos/').data['count'], 2)

    def test_precio_congelado(self):
        self.login('pasajero')
        self.agregar(self.asiento_cama)
        venta_id = self.client.post('/api/ventas/checkout/', {'pagar': False}).data['id']
        Servicio.objects.filter(pk=self.servicio.pk).update(tarifa_cama=99999)
        self.assertEqual(Venta.objects.get(pk=venta_id).detalles.get().precio_unitario, 8000)

    def test_pago_rechazado_si_asiento_ya_vendido(self):
        # pasajero deja una venta PENDIENTE; "otro" compra y paga el mismo asiento.
        self.login('pasajero')
        self.agregar(self.asiento_cama)
        venta_id = self.client.post('/api/ventas/checkout/', {'pagar': False}).data['id']
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, 'DISPONIBLE')

        self.login('otro')
        self.agregar(self.asiento_cama, rut='22.222.222-2')
        self.assertEqual(self.client.post('/api/ventas/checkout/').status_code, 201)

        self.login('pasajero')
        respuesta = self.client.post(f'/api/ventas/{venta_id}/pagar/')
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(Venta.objects.get(pk=venta_id).estado, 'PENDIENTE')

    def test_checkout_rechazado_mantiene_carro(self):
        self.login('pasajero')
        self.agregar(self.asiento_cama)
        Asiento.objects.filter(pk=self.asiento_cama.pk).update(estado='OCUPADO')
        self.assertEqual(self.client.post('/api/ventas/checkout/').status_code, 409)
        self.assertEqual(Venta.objects.count(), 0)
        self.assertEqual(len(self.client.get('/api/carro-pasajes/').data['items']), 1)

    def test_admin_cancela_y_repone_stock(self):
        self.login('pasajero')
        self.agregar(self.asiento_cama)
        venta_id = self.client.post('/api/ventas/checkout/').data['id']
        # Un pasajero no puede cambiar estados.
        self.assertEqual(self.client.patch(f'/api/ventas/{venta_id}/estado/', {'estado': 'CANCELADO'}).status_code, 403)

        self.login('admin')
        respuesta = self.client.patch(f'/api/ventas/{venta_id}/estado/', {'estado': 'CANCELADO', 'observacion': 'test'})
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.asiento_cama.refresh_from_db()
        self.assertEqual(self.asiento_cama.estado, 'DISPONIBLE')
        self.assertEqual(Boleto.objects.get().estado, 'ANULADO')
        # CANCELADO es final.
        self.assertEqual(self.client.patch(f'/api/ventas/{venta_id}/estado/', {'estado': 'PAGADO'}).status_code, 400)

    def test_ventas_ajenas_no_visibles(self):
        self.login('pasajero')
        self.agregar(self.asiento_cama)
        venta_id = self.client.post('/api/ventas/checkout/', {'pagar': False}).data['id']
        self.login('otro')
        self.assertEqual(self.client.post(f'/api/ventas/{venta_id}/pagar/').status_code, 404)
