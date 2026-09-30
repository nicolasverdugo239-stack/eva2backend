"""
=====================================================================
MODELOS DE LA APP "usuarios"
=====================================================================
Define el usuario personalizado del sistema con un campo ROL basado en
CHOICES. El rol determina qué endpoints puede consumir cada usuario y
viaja dentro del token JWT como claim personalizado.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """
    -----------------------------------------------------------------
    BLOQUE: Usuario con ROL
    - Hereda de AbstractUser (username, password, email, etc.).
    - rol (CHOICES):
        PASAJERO    -> cliente que busca servicios, arma su carro y compra.
        ADMIN_FLOTA -> gestiona ciudades, rutas, buses, servicios y
                       cambia el estado de las ventas.
    - save(): sincroniza is_staff con el rol ADMIN_FLOTA para que la
      clase de permiso IsAdminUser de DRF también funcione y el
      administrador pueda entrar al panel /admin/.
    -----------------------------------------------------------------
    """

    class Rol(models.TextChoices):
        PASAJERO = 'PASAJERO', 'Pasajero'
        ADMIN_FLOTA = 'ADMIN_FLOTA', 'Administrador de Flota'

    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.PASAJERO,
        help_text='Rol del usuario dentro del sistema (se incluye en el JWT).',
    )
    rut = models.CharField(max_length=12, blank=True, help_text='RUT del usuario (opcional).')
    telefono = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def save(self, *args, **kwargs):
        # Un superusuario siempre es Administrador de Flota.
        if self.is_superuser:
            self.rol = self.Rol.ADMIN_FLOTA
        # El administrador de flota queda marcado como staff.
        if self.rol == self.Rol.ADMIN_FLOTA:
            self.is_staff = True
        super().save(*args, **kwargs)

    @property
    def es_admin_flota(self):
        return self.rol == self.Rol.ADMIN_FLOTA

    def __str__(self):
        return f'{self.username} ({self.get_rol_display()})'
