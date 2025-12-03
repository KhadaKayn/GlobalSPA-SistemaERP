from django.apps import AppConfig


class Sitio1Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sitio1'
    verbose_name = "dominio Web Pizza Sitio1"

    def ready(self):
        import sitio1.signals

