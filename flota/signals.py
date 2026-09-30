"""
=====================================================================
SEÑALES DE LA APP "flota"
=====================================================================
generar_asientos_servicio:
    Se dispara con post_save de Servicio. Cuando se CREA un servicio,
    genera automáticamente sus asientos a partir de la configuración del
    bus asignado:
        - Primero los asientos CAMA (números 1..N).
        - Luego los asientos SEMICAMA (números N+1..N+M).
    Se usa bulk_create para insertarlos en una sola consulta SQL.
    Todos los asientos nacen en estado DISPONIBLE.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Asiento, Servicio


@receiver(post_save, sender=Servicio)
def generar_asientos_servicio(sender, instance, created, **kwargs):
    if not created:
        return

    bus = instance.bus
    asientos = []
    numero = 1
    for _ in range(bus.asientos_cama):
        asientos.append(Asiento(servicio=instance, numero=numero, tipo=Asiento.Tipo.CAMA))
        numero += 1
    for _ in range(bus.asientos_semicama):
        asientos.append(Asiento(servicio=instance, numero=numero, tipo=Asiento.Tipo.SEMICAMA))
        numero += 1

    Asiento.objects.bulk_create(asientos)
