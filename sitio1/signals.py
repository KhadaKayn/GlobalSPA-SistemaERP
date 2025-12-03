# sitio1/signals.py
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import User, Permission
from .models import Rol, Usuario
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .views import registrar_actividad

@receiver(post_migrate)
def create_superuser(sender, **kwargs):
    if sender.name == 'sitio1':
        # Verificar si ya existe un superusuario
        if not User.objects.filter(is_superuser=True).exists():
            # Crear un superusuario si no existe
            User.objects.create_superuser(username='admin', password='admin', email='admin@example.com')

@receiver(post_migrate)
def crear_roles_por_defecto(sender, **kwargs):
    if sender.name != 'sitio1':
        return

    roles_defecto = [
        ("Administrador", "Acceso completo al sistema."),
        ("Ventas", "Acceso al módulo de ventas."),
        ("Bodega", "Acceso al control de inventario."),
        ("Data Analysis", "Acceso a reportes y análisis."),
    ]

    for nombre, descripcion in roles_defecto:
        rol, created = Rol.objects.get_or_create(
            nombre=nombre,
            defaults={"descripcion": descripcion}
        )

    # Asegurar superusuario asociado
    admin = User.objects.filter(is_superuser=True).first()
    if admin:
        rol_admin = Rol.objects.get(nombre="Administrador")
        Usuario.objects.get_or_create(
            user=admin,
            defaults={
                "nombre_completo": "Administrador del Sistema",
                "rol": rol_admin,
                "estado": True
            }
        )

@receiver(user_logged_in)
def registro_login(sender, request, user, **kwargs):
    registrar_actividad(
        usuario=user,
        tipo_actividad='login',
        descripcion='Inicio de sesión exitoso',
        request=request
    )

@receiver(user_logged_out)
def registro_logout(sender, request, user, **kwargs):
    if user:
        registrar_actividad(
            usuario=user,
            tipo_actividad='logout',
            descripcion='Cierre de sesión',
            request=request
        )