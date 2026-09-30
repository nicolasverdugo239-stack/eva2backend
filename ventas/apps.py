from django.apps import AppConfig


class VentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ventas'
    verbose_name = 'Ventas y Boletos'

    def ready(self):
        # Registro de señales (creación automática del carro 1:1).
        from . import signals  # noqa: F401
