from rest_framework import serializers
from .models import Venta, DetalleVenta, Productos, MovimientoInventario, Productos, Categoria, Proveedor, Ubicacion, Usuario, Rol, AjusteInventario, DetalleAjusteInventario, Venta, DetalleVenta, LogAuditoria
from decimal import Decimal

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from functools import wraps
from django.http import JsonResponse
import json
import logging

logger = logging.getLogger(__name__)


class ProductoCarritoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    cantidad = serializers.IntegerField()
    precio_unitario = serializers.DecimalField(max_digits=12, decimal_places=2)

class VentaSerializer(serializers.Serializer):
    productos = ProductoCarritoSerializer(many=True)
    medio_pago = serializers.CharField(default="efectivo")
    forzar = serializers.BooleanField(default=False)

    def validate(self, data):
        if not data.get("productos"):
            raise serializers.ValidationError({"error": "No se enviaron productos"})
        return data

    def create(self, validated_data):
        request = self.context["request"]
        productos = validated_data["productos"]
        medio_pago = validated_data.get("medio_pago", "efectivo")
        forzar = validated_data.get("forzar", False)

        from django.db import transaction
        total = sum(Decimal(str(p["precio_unitario"])) * int(p["cantidad"]) for p in productos)

        with transaction.atomic():
            venta = Venta.objects.create(
                usuario=request.user,
                total=total,
                medio_pago=medio_pago,
                estado="completada"
            )

            for p in productos:
                producto = Productos.objects.select_for_update().get(id=p["id"])
                cantidad = int(p["cantidad"])
                subtotal = Decimal(str(p["precio_unitario"])) * cantidad

                # Validación stock
                if producto.stock_actual < cantidad:
                    if not forzar:
                        raise serializers.ValidationError({
                            "error": f"Stock insuficiente para {producto.nombre}. Disponibles: {producto.stock_actual}",
                            "puede_forzar": True
                        })
                    MovimientoInventario.objects.create(
                        producto=producto,
                        tipo_movimiento="venta_forzada",
                        cantidad=cantidad,
                        usuario=request.user,
                        motivo="Venta forzada por falta de stock"
                    )
                else:
                    MovimientoInventario.objects.create(
                        producto=producto,
                        tipo_movimiento="salida",
                        cantidad=cantidad,
                        usuario=request.user,
                        motivo="Venta normal"
                    )

                producto.stock_actual -= cantidad
                producto.save()

                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unidad=p["precio_unitario"],
                    costo_unitario=producto.costo_unitario or 0,
                    subtotal=subtotal
                )

        return {
            "mensaje": "Venta registrada correctamente",
            "venta_id": venta.id,
            "total": float(total)
        }


# =====================================================
# =====================================================
"""
Sistema de auditoría automático con decoradores y signals.
Este módulo maneja todo el logging sin modificar las views.
"""

# =====================================================
# DECORADOR PARA AUDITORÍA MANUAL
# =====================================================

def auditar_accion(tabla, tipo_accion=None):
    """
    Decorador para capturar acciones en views.
    
    Uso:
    @login_required
    @auditar_accion('productos', 'create')
    def crear_producto(request):
        ...
    
    O sin especificar tipo_accion (se detecta automáticamente):
    @login_required
    @auditar_accion('productos')
    def cualquier_vista(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)
            
            # Solo auditar si fue exitoso y es POST/PUT/DELETE
            if request.method in ['POST', 'PUT', 'DELETE']:
                try:
                    # Obtener el tipo de acción
                    accion = tipo_accion or _detectar_accion(request.method, view_func.__name__)
                    
                    # Obtener datos del request
                    if request.method == 'POST':
                        datos = request.POST.dict() if hasattr(request, 'POST') else {}
                    elif request.method == 'DELETE':
                        datos = request.GET.dict()
                    else:
                        datos = request.POST.dict() if hasattr(request, 'POST') else {}
                    
                    # Obtener ID del registro si existe
                    id_registro = kwargs.get('id') or kwargs.get('pk') or kwargs.get('productos_id') or datos.get('id', 0)
                    
                    # Crear log
                    LogAuditoria.crear_log(
                        usuario=request.user,
                        tabla=tabla,
                        tipo_accion=accion,
                        id_registro=id_registro,
                        descripcion=f"{accion.upper()}: {tabla} #{id_registro}",
                        valores_nuevo=datos if accion == 'create' else None,
                        request=request
                    )
                    
                except Exception as e:
                    logger.error(f"Error en auditoría: {e}")
            
            return response
        
        return wrapper
    return decorator


def _detectar_accion(metodo, nombre_vista):
    """Detecta automáticamente el tipo de acción según el método y nombre de vista"""
    if metodo == 'POST':
        if 'crear' in nombre_vista or 'ingresar' in nombre_vista:
            return 'create'
        elif 'editar' in nombre_vista or 'actualizar' in nombre_vista:
            return 'update'
        return 'create'
    elif metodo == 'DELETE':
        return 'delete'
    elif metodo == 'GET':
        return 'view'
    return 'view'


# =====================================================
# SIGNALS AUTOMÁTICOS
# =====================================================

# Almacenar valores anteriores antes de guardar
_valores_anteriores = {}


@receiver(pre_save, sender=Productos)
def capturar_producto_anterior(sender, instance, **kwargs):
    """Captura valores del producto antes de actualizar"""
    if instance.pk:
        try:
            anterior = Productos.objects.get(pk=instance.pk)
            _valores_anteriores[f'Productos_{instance.pk}'] = {
                'nombre': anterior.nombre,
                'precio_unitario': str(anterior.precio_unitario),
                'stock_actual': anterior.stock_actual,
                'categoria': anterior.categoria.nombre,
                'sku': anterior.sku,
                'activo': anterior.activo,
            }
        except:
            pass


@receiver(post_save, sender=Productos)
def auditar_producto_guardado(sender, instance, created, **kwargs):
    """Audita creación o modificación de productos"""
    try:
        if created:
            # Es una creación
            LogAuditoria.crear_log(
                usuario=None,  # Se obtiene del request si es posible
                tabla='productos',
                tipo_accion='create',
                id_registro=instance.id,
                descripcion=f"Producto creado: {instance.nombre}",
                valores_nuevo={
                    'nombre': instance.nombre,
                    'sku': instance.sku,
                    'precio_unitario': str(instance.precio_unitario),
                    'stock_actual': instance.stock_actual,
                }
            )
        else:
            # Es una actualización
            clave = f'Productos_{instance.pk}'
            valores_ant = _valores_anteriores.pop(clave, {})
            
            if valores_ant:
                valores_nuevo = {
                    'nombre': instance.nombre,
                    'precio_unitario': str(instance.precio_unitario),
                    'stock_actual': instance.stock_actual,
                    'categoria': instance.categoria.nombre,
                    'sku': instance.sku,
                    'activo': instance.activo,
                }
                
                LogAuditoria.crear_log(
                    usuario=None,
                    tabla='productos',
                    tipo_accion='update',
                    id_registro=instance.id,
                    descripcion=f"Producto actualizado: {instance.nombre}",
                    valores_anterior=valores_ant,
                    valores_nuevo=valores_nuevo
                )
    except Exception as e:
        logger.error(f"Error auditando producto: {e}")


@receiver(post_delete, sender=Productos)
def auditar_producto_eliminado(sender, instance, **kwargs):
    """Audita eliminación de productos"""
    try:
        LogAuditoria.crear_log(
            usuario=None,
            tabla='productos',
            tipo_accion='delete',
            id_registro=instance.id,
            descripcion=f"Producto eliminado: {instance.nombre}",
            valores_anterior={
                'nombre': instance.nombre,
                'sku': instance.sku,
                'precio_unitario': str(instance.precio_unitario),
            }
        )
    except Exception as e:
        logger.error(f"Error auditando eliminación de producto: {e}")


# =====================================================
# SIMILAR PARA OTROS MODELOS
# =====================================================

@receiver(pre_save, sender=Categoria)
def capturar_categoria_anterior(sender, instance, **kwargs):
    if instance.pk:
        try:
            anterior = Categoria.objects.get(pk=instance.pk)
            _valores_anteriores[f'Categoria_{instance.pk}'] = {
                'nombre': anterior.nombre,
                'descripcion': anterior.descripcion,
            }
        except:
            pass


@receiver(post_save, sender=Categoria)
def auditar_categoria_guardada(sender, instance, created, **kwargs):
    try:
        if created:
            LogAuditoria.crear_log(
                usuario=None,
                tabla='categorias',
                tipo_accion='create',
                id_registro=instance.id,
                descripcion=f"Categoría creada: {instance.nombre}",
                valores_nuevo={'nombre': instance.nombre, 'descripcion': instance.descripcion}
            )
        else:
            clave = f'Categoria_{instance.pk}'
            valores_ant = _valores_anteriores.pop(clave, {})
            if valores_ant:
                LogAuditoria.crear_log(
                    usuario=None,
                    tabla='categorias',
                    tipo_accion='update',
                    id_registro=instance.id,
                    descripcion=f"Categoría actualizada: {instance.nombre}",
                    valores_anterior=valores_ant,
                    valores_nuevo={'nombre': instance.nombre, 'descripcion': instance.descripcion}
                )
    except Exception as e:
        logger.error(f"Error auditando categoría: {e}")


@receiver(post_delete, sender=Categoria)
def auditar_categoria_eliminada(sender, instance, **kwargs):
    try:
        LogAuditoria.crear_log(
            usuario=None,
            tabla='categorias',
            tipo_accion='delete',
            id_registro=instance.id,
            descripcion=f"Categoría eliminada: {instance.nombre}",
            valores_anterior={'nombre': instance.nombre}
        )
    except Exception as e:
        logger.error(f"Error auditando eliminación de categoría: {e}")


# =====================================================
# SEÑALES PARA USUARIOS
# =====================================================

@receiver(pre_save, sender=Usuario)
def capturar_usuario_anterior(sender, instance, **kwargs):
    if instance.pk:
        try:
            anterior = Usuario.objects.get(pk=instance.pk)
            _valores_anteriores[f'Usuario_{instance.pk}'] = {
                'nombre_completo': anterior.nombre_completo,
                'email': anterior.email,
                'rol': anterior.rol.nombre,
                'estado': anterior.estado,
            }
        except:
            pass


@receiver(post_save, sender=Usuario)
def auditar_usuario_guardado(sender, instance, created, **kwargs):
    try:
        if created:
            LogAuditoria.crear_log(
                usuario=None,
                tabla='usuarios',
                tipo_accion='create',
                id_registro=instance.id,
                descripcion=f"Usuario creado: {instance.nombre_completo or instance.user.username}",
                valores_nuevo={
                    'nombre_completo': instance.nombre_completo,
                    'email': instance.email,
                    'rol': instance.rol.nombre,
                }
            )
        else:
            clave = f'Usuario_{instance.pk}'
            valores_ant = _valores_anteriores.pop(clave, {})
            if valores_ant:
                LogAuditoria.crear_log(
                    usuario=None,
                    tabla='usuarios',
                    tipo_accion='update',
                    id_registro=instance.id,
                    descripcion=f"Usuario actualizado: {instance.nombre_completo}",
                    valores_anterior=valores_ant,
                    valores_nuevo={
                        'nombre_completo': instance.nombre_completo,
                        'email': instance.email,
                        'rol': instance.rol.nombre,
                        'estado': instance.estado,
                    }
                )
    except Exception as e:
        logger.error(f"Error auditando usuario: {e}")


@receiver(post_delete, sender=Usuario)
def auditar_usuario_eliminado(sender, instance, **kwargs):
    try:
        LogAuditoria.crear_log(
            usuario=None,
            tabla='usuarios',
            tipo_accion='delete',
            id_registro=instance.id,
            descripcion=f"Usuario eliminado: {instance.nombre_completo}",
            valores_anterior={'nombre_completo': instance.nombre_completo, 'email': instance.email}
        )
    except Exception as e:
        logger.error(f"Error auditando eliminación de usuario: {e}")


# =====================================================
# SEÑALES PARA AJUSTES DE INVENTARIO
# =====================================================

@receiver(post_save, sender=AjusteInventario)
def auditar_ajuste_guardado(sender, instance, created, **kwargs):
    try:
        if created:
            LogAuditoria.crear_log(
                usuario=instance.usuario,
                tabla='ajustes',
                tipo_accion='create',
                id_registro=instance.id,
                descripcion=f"Ajuste de inventario creado: {instance.ubicacion.direccion}",
                valores_nuevo={'ubicacion': str(instance.ubicacion), 'motivo': instance.motivo}
            )
        else:
            if instance.finalizado:
                LogAuditoria.crear_log(
                    usuario=instance.usuario,
                    tabla='ajustes',
                    tipo_accion='update',
                    id_registro=instance.id,
                    descripcion=f"Ajuste de inventario finalizado y aplicado",
                    valores_nuevo={'finalizado': True, 'productos_revisados': instance.productos_revisados}
                )
    except Exception as e:
        logger.error(f"Error auditando ajuste: {e}")


# =====================================================
# HELPER PARA OBTENER IP DEL REQUEST
# =====================================================

def obtener_ip_cliente(request):
    """Extrae la IP real del cliente considerando proxies"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# =====================================================
# MIDDLEWARE PARA CAPTURAR USER EN SIGNALS
# =====================================================

from django.utils.deprecation import MiddlewareMixin

_thread_locals = {}

class AuditoriaMiddleware(MiddlewareMixin):
    """Middleware que almacena el usuario actual para usar en signals"""
    
    def process_request(self, request):
        _thread_locals['user'] = request.user
        _thread_locals['ip'] = obtener_ip_cliente(request)
        return None
    
    def process_response(self, request, response):
        _thread_locals.pop('user', None)
        _thread_locals.pop('ip', None)
        return response


def obtener_usuario_actual():
    """Obtiene el usuario actual del middleware"""
    return _thread_locals.get('user')


def obtener_ip_actual():
    """Obtiene la IP actual del middleware"""
    return _thread_locals.get('ip')