"""
=====================================================================
COMANDO: python manage.py poblar_datos
=====================================================================
Carga datos de demostración (idempotente, se puede ejecutar varias veces):
  - Usuarios:  admin_flota / Admin12345!   (rol ADMIN_FLOTA, superusuario)
               pasajero1   / Pasajero123!  (rol PASAJERO)
               pasajero2   / Pasajero123!  (rol PASAJERO)
  - Ciudades, terminales, rutas y buses.
  - Servicios de los próximos días (los asientos se generan por señal).
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from flota.models import Bus, Ciudad, Ruta, Servicio, Terminal
from usuarios.models import Usuario


class Command(BaseCommand):
    help = 'Carga datos de demostración para el sistema de pasajes.'

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Bloque: usuarios de prueba --------------------------------
        # Si el usuario ya existía (BD reutilizada), se restablecen su
        # contraseña y rol para que las credenciales de demo siempre sirvan.
        usuarios_demo = [
            ('admin_flota', 'admin@buses.cl', 'Admin12345!', Usuario.Rol.ADMIN_FLOTA, True),
            ('pasajero1', 'pasajero1@correo.cl', 'Pasajero123!', Usuario.Rol.PASAJERO, False),
            ('pasajero2', 'pasajero2@correo.cl', 'Pasajero123!', Usuario.Rol.PASAJERO, False),
        ]
        for username, email, clave, rol, es_super in usuarios_demo:
            usuario, _ = Usuario.objects.get_or_create(username=username, defaults={'email': email})
            usuario.rol = rol
            usuario.is_superuser = es_super
            usuario.is_staff = es_super
            usuario.is_active = True
            usuario.set_password(clave)
            usuario.save()

        # --- Bloque: ciudades y terminales -----------------------------
        datos_ciudades = [
            ('Santiago', 'Metropolitana', 'Terminal Alameda', 'Av. Libertador B. O\'Higgins 3750'),
            ('Valparaíso', 'Valparaíso', 'Terminal Rodoviario Valparaíso', 'Av. Pedro Montt 2800'),
            ('Concepción', 'Biobío', 'Terminal Collao', 'Tegualda 860'),
            ('La Serena', 'Coquimbo', 'Terminal La Serena', 'Amunátegui 1'),
            ('Temuco', 'La Araucanía', 'Terminal Rodoviario Temuco', 'Vicente Pérez Rosales 01609'),
        ]
        terminales = {}
        for ciudad_nombre, region, terminal_nombre, direccion in datos_ciudades:
            ciudad, _ = Ciudad.objects.get_or_create(nombre=ciudad_nombre, defaults={'region': region})
            terminales[ciudad_nombre], _ = Terminal.objects.get_or_create(
                ciudad=ciudad, nombre=terminal_nombre, defaults={'direccion': direccion}
            )

        # --- Bloque: rutas (ida y vuelta) ------------------------------
        datos_rutas = [
            ('Santiago', 'Valparaíso', 120, 2),
            ('Santiago', 'Concepción', 500, 7),
            ('Santiago', 'La Serena', 470, 6),
            ('Santiago', 'Temuco', 680, 9),
        ]
        rutas = []
        for origen, destino, km, horas in datos_rutas:
            for o, d in ((origen, destino), (destino, origen)):
                ruta, _ = Ruta.objects.get_or_create(
                    origen=terminales[o], destino=terminales[d],
                    defaults={'distancia_km': km, 'duracion_estimada': timedelta(hours=horas)},
                )
                rutas.append((ruta, km))

        # --- Bloque: buses ---------------------------------------------
        buses = [
            Bus.objects.get_or_create(patente='ABCD12', defaults={
                'marca': 'Mercedes-Benz', 'modelo': 'O500 RSD', 'anio': 2022,
                'asientos_cama': 12, 'asientos_semicama': 28})[0],
            Bus.objects.get_or_create(patente='EFGH34', defaults={
                'marca': 'Volvo', 'modelo': 'B450R', 'anio': 2023,
                'asientos_cama': 10, 'asientos_semicama': 32})[0],
            Bus.objects.get_or_create(patente='IJKL56', defaults={
                'marca': 'Scania', 'modelo': 'K410', 'anio': 2021,
                'asientos_cama': 0, 'asientos_semicama': 44})[0],
        ]

        # --- Bloque: servicios de los próximos 5 días ------------------
        # Solo se crean si aún no existen servicios futuros.
        if not Servicio.objects.filter(fecha_salida__gt=timezone.now()).exists():
            base = timezone.localtime().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
            contador = 0
            for dia in range(5):
                for indice, (ruta, km) in enumerate(rutas):
                    bus = buses[(indice + dia) % len(buses)]
                    salida = base + timedelta(days=dia, hours=(indice % 4) * 3, minutes=indice * 7)
                    tarifa = 3000 + km * 18
                    Servicio.objects.create(
                        ruta=ruta, bus=bus, fecha_salida=salida,
                        tarifa_semicama=round(tarifa, -2),
                        tarifa_cama=round(tarifa * 1.6, -2),
                    )
                    contador += 1
            self.stdout.write(f'Servicios creados: {contador}')

        self.stdout.write(self.style.SUCCESS(
            'Datos cargados. Usuarios: admin_flota/Admin12345!  pasajero1/Pasajero123!  pasajero2/Pasajero123!'
        ))
