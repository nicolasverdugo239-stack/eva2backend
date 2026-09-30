"""
=====================================================================
SEÑALES DE LA APP "ventas"
=====================================================================
crear_carro_usuario:
    post_save del modelo Usuario. Al crear un usuario nuevo se crea su
    Carro vacío, garantizando la relación 1 a 1 Usuario <-> Carro desde
    el primer momento. get_or_create evita duplicados si la señal se
    ejecutara más de una vez.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Carro


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def crear_carro_usuario(sender, instance, created, **kwargs):
    if created:
        Carro.objects.get_or_create(usuario=instance)
