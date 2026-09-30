from django.apps import AppConfig


class FlotaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'flota'
    verbose_name = 'Flota y Servicios'

    def ready(self):
        # Registro de señales (generación automática de asientos).
        from . import signals  # noqa: F401
