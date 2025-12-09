from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from sitio1.models import Productos, Categoria, Proveedor, Ubicacion, Usuario, Rol, User, Venta, DetalleVenta, MovimientoInventario, ActividadUsuario, OrdenCompraIA, ItemOrdenCompraIA, LogOrdenCompraIA, Productos, Ubicacion, AjusteInventario, DetalleAjusteInventario, MovimientoInventario, LogAuditoria
from .forms import ProductosForm, UsuarioForm, CategoriaForm, ProveedorForm, UbicacionForm, UsuarioRegistroForm, RolForm, VentaForm, DetalleVentaFormSet, EditarPerfilForm
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.urls import reverse
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from decimal import Decimal
from django.db.models import Q, Sum, Count, F, ExpressionWrapper, DecimalField, Avg, ProtectedError
from django.utils.safestring import mark_safe
from django.utils import timezone
from datetime import timedelta, datetime

from django.db import models

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.forms.models import model_to_dict

from django.core.serializers.json import DjangoJSONEncoder


from django.views.decorators.http import require_http_methods

from django.core.paginator import Paginator

from django.db.models.functions import ExtractWeekDay, ExtractHour

from django.db.models.functions import TruncDate
from .ml_analytics import (
    entrenar_modelo_demanda,
    predecir_demanda_producto,
    clasificar_productos_ml,
    generar_alertas_ia,
    evaluar_modelo_actual,
    obtener_estadisticas_modelo
)
from .models import Productos, DetalleVenta, Venta

import logging

logger = logging.getLogger(__name__)

from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .serializers import VentaSerializer    
from rest_framework import serializers

def model_to_json_safe(instance):
    """
    Convierte un modelo a dict compatible con JSON (Decimal, fechas, etc.)
    """
    data = model_to_dict(instance)
    # DjangoJSONEncoder convierte Decimal, date, datetime, etc.
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))



#                                                       LOGIN DE USUARIO
def login_view(request):
    form = UsuarioForm()

    if request.method == 'POST':
        form = UsuarioForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['nombre_usuario']  # <- corregido
            password = form.cleaned_data['contrasena']      # <- corregido

            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('home')  # o donde quieras redirigir
            else:
                form.add_error(None, 'Nombre de usuario o contraseña incorrectos.')

    return render(request, 'registration/login.html', {'form': form})

#                                                       PAGINA DE INICIO
@login_required
def home(request):
    """
    Vista principal del home con menú adaptativo según permisos
    """
    hoy = timezone.now().date()
    
    # Quick Stats
    ventas_hoy = Venta.objects.filter(fecha__date=hoy).aggregate(
        total=Sum('total')
    )['total'] or 0
    
    transacciones_hoy = Venta.objects.filter(fecha__date=hoy).count()
    
    productos_activos = Productos.objects.filter(activo=True).count()
    
    from django.db.models import F
    alertas_stock = Productos.objects.filter(
        stock_actual__lte=F('stock_minimo'),
        activo=True
    ).count()
    
    quick_stats = {
        'ventas_hoy': ventas_hoy,
        'transacciones_hoy': transacciones_hoy,
        'productos_activos': productos_activos,
        'alertas_stock': alertas_stock
    }
    
    # Actividad Reciente (últimas 10 acciones)
    actividad_reciente = []
    
    # Últimas ventas
    ultimas_ventas = Venta.objects.order_by('-fecha')[:5]
    for venta in ultimas_ventas:
        actividad_reciente.append({
            'tipo': 'success',
            'icono': 'cart-check-fill',
            'titulo': f'Venta #{venta.id} - ${venta.total} ({venta.medio_pago})',
            'fecha': venta.fecha
        })
    
    # Últimos movimientos de inventario
    ultimos_movimientos = MovimientoInventario.objects.select_related('producto').order_by('-fecha_hora')[:5]
    for mov in ultimos_movimientos:
        icono_map = {
            'entrada': 'box-arrow-in-down-left',
            'salida': 'box-arrow-up-right',
            'ajuste': 'wrench',
            'venta_forzada': 'exclamation-triangle-fill'
        }
        tipo_map = {
            'entrada': 'info',
            'salida': 'warning',
            'ajuste': 'info',
            'venta_forzada': 'warning'
        }
        actividad_reciente.append({
            'tipo': tipo_map.get(mov.tipo_movimiento, 'info'),
            'icono': icono_map.get(mov.tipo_movimiento, 'box'),
            'titulo': f'{mov.get_tipo_movimiento_display()}: {mov.producto.nombre} ({mov.cantidad} unid.)',
            'fecha': mov.fecha_hora
        })
    
    # Ordenar por fecha
    actividad_reciente = sorted(actividad_reciente, key=lambda x: x['fecha'], reverse=True)[:10]
    
    context = {
        'quick_stats': quick_stats,
        'actividad_reciente': actividad_reciente,
    }
    
    return render(request, 'sitio1/home.html', context)



# ==============================
# CRUD PARA PRODUCTOS
# ==============================

@login_required
def lista_productos(request):
    """Lista todos los productos con relaciones optimizadas"""
    productos = Productos.objects.select_related(
        'categoria', 
        'ubicacion', 
        'proveedor'
    ).all().order_by('-activo', 'nombre')  # Activos primero, luego por nombre
    
    context = {
        'datos': productos,
        'total_productos': productos.count(),
    }
    
    return render(request, 'sitio1/DataModelApp/Productos/ver_productos.html', context)


@login_required
def ingresar_productos(request):
    """Crear nuevo producto"""
    if request.method == "POST":
        form = ProductosForm(request.POST, request.FILES)
        if form.is_valid():
            producto = form.save()

            # Log de creación (JSON-safe)
            LogAuditoria.crear_log(
                usuario=request.user,
                tabla='productos',
                tipo_accion='create',
                id_registro=producto.id,
                descripcion=f'Se creó el producto "{producto.nombre}"',
                valores_nuevo=model_to_json_safe(producto),
                request=request,
            )

            messages.success(request, f'✓ Producto "{producto.nombre}" creado exitosamente.')
            return redirect("productos")
        else:
            messages.error(request, '❌ Error al crear el producto. Revisa los campos.')
    else:
        form = ProductosForm()

    return render(request, 'sitio1/DataModelApp/Productos/ingresar_productos.html', {'form': form})


@login_required
def editar_productos(request, productos_id):
    """Editar producto existente"""
    producto = get_object_or_404(Productos, id=productos_id)
    
    if request.method == "POST":
        # Estado antes del cambio (JSON-safe)
        datos_antes = model_to_json_safe(producto)

        form = ProductosForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            producto = form.save()

            # Log de actualización (JSON-safe)
            LogAuditoria.crear_log(
                usuario=request.user,
                tabla='productos',
                tipo_accion='update',
                id_registro=producto.id,
                descripcion=f'Se actualizó el producto "{producto.nombre}"',
                valores_anterior=datos_antes,
                valores_nuevo=model_to_json_safe(producto),
                request=request,
            )

            messages.success(request, f'✓ Producto "{producto.nombre}" actualizado correctamente.')
            return redirect("productos")
        else:
            messages.error(request, '❌ Error al actualizar el producto.')
    else:
        form = ProductosForm(instance=producto)

    return render(request, 'sitio1/DataModelApp/Productos/editar_productos.html', {
        'form': form,
        'producto': producto
    })


@login_required
def eliminar_productos(request, productos_id):
    """Eliminación inteligente de productos"""
    producto = get_object_or_404(Productos, id=productos_id)
    
    if request.method == 'POST':
        forzar_eliminacion = request.POST.get('forzar_eliminacion') == 'true'
        # Snapshot antes (JSON-safe)
        datos_antes = model_to_json_safe(producto)
        nombre = producto.nombre
        
        try:
            producto.delete()

            # Log de eliminación normal
            LogAuditoria.crear_log(
                usuario=request.user,
                tabla='productos',
                tipo_accion='delete',
                id_registro=productos_id,
                descripcion=f'Se eliminó el producto "{nombre}"',
                valores_anterior=datos_antes,
                valores_nuevo=None,
                request=request,
            )

            messages.success(request, f'✓ Producto "{nombre}" eliminado correctamente.')
            return redirect('productos')
            
        except ProtectedError as e:
            ventas_asociadas = list(e.protected_objects)
            
            if forzar_eliminacion:
                # Eliminar ventas y producto
                for venta in ventas_asociadas:
                    venta.delete()
                producto.delete()

                # Log de eliminación forzada
                LogAuditoria.crear_log(
                    usuario=request.user,
                    tabla='productos',
                    tipo_accion='delete',
                    id_registro=productos_id,
                    descripcion=(
                        f'Se eliminó el producto "{nombre}" junto a '
                        f'{len(ventas_asociadas)} ventas asociadas (eliminación forzada).'
                    ),
                    valores_anterior=datos_antes,
                    valores_nuevo=None,
                    request=request,
                )

                messages.warning(
                    request, 
                    f'⚠️ Producto "{nombre}" y sus {len(ventas_asociadas)} ventas asociadas han sido eliminados.'
                )
                return redirect('productos')
            else:
                # Mostrar modal de confirmación (sin log todavía)
                return render(request, 'sitio1/DataModelApp/Productos/confirmar_eliminacion.html', {
                    'producto': producto,
                    'ventas_count': len(ventas_asociadas),
                    'ventas': ventas_asociadas[:10]  # Máximo 10 para mostrar
                })
    
    return redirect('productos')


@login_required
def desactivar_producto(request, productos_id):
    """Desactiva un producto en lugar de eliminarlo"""
    producto = get_object_or_404(Productos, id=productos_id)
    
    datos_antes = model_to_json_safe(producto)

    producto.activo = False
    producto.save()

    datos_despues = model_to_json_safe(producto)

    # Log de desactivación
    LogAuditoria.crear_log(
        usuario=request.user,
        tabla='productos',
        tipo_accion='update',
        id_registro=producto.id,
        descripcion=f'Se desactivó el producto "{producto.nombre}"',
        valores_anterior=datos_antes,
        valores_nuevo=datos_despues,
        request=request,
    )

    messages.info(request, f'🔒 Producto "{producto.nombre}" desactivado. No aparecerá en nuevas ventas.')
    return redirect('productos')


@login_required
def reactivar_producto(request, productos_id):
    """Reactiva un producto desactivado"""
    producto = get_object_or_404(Productos, id=productos_id)

    # Snapshot ANTES (JSON-safe)
    datos_antes = model_to_json_safe(producto)

    producto.activo = True
    producto.save()

    # Snapshot DESPUÉS (JSON-safe)
    datos_despues = model_to_json_safe(producto)

    # Log de reactivación
    LogAuditoria.crear_log(
        usuario=request.user,
        tabla='productos',
        tipo_accion='update',
        id_registro=producto.id,
        descripcion=f'Se reactivó el producto \"{producto.nombre}\"',
        valores_anterior=datos_antes,
        valores_nuevo=datos_despues,
        request=request,
    )

    messages.success(request, f'✓ Producto \"{producto.nombre}\" reactivado correctamente.')
    return redirect('productos')

def verificar_ventas_producto(request, productos_id):
    """API para verificar si un producto tiene ventas (AJAX)"""
    producto = get_object_or_404(Productos, id=productos_id)
    
    # Verificar si tiene ventas
    tiene_ventas = hasattr(producto, 'detalleventa_set') and producto.detalleventa_set.exists()
    
    if tiene_ventas:
        ventas_count = producto.detalleventa_set.count()
        return JsonResponse({
            'tiene_ventas': True,
            'ventas_count': ventas_count,
            'mensaje': f'Este producto tiene {ventas_count} venta(s) registrada(s).'
        })
    else:
        return JsonResponse({
            'tiene_ventas': False,
            'mensaje': 'Este producto puede eliminarse sin problemas.'
        })


# ==============================
# Gestion de datos
# ==============================

#OPciones de gestion    
def vista_gestion(request):
    
    return render(request, 'sitio1/DataModelApp/Gestion/opciones_gestion.html')

#Opciones de usuario
def vista_usuarios(request):
    
    return render(request, 'sitio1/DataModelApp/Gestion/opciones_usuario.html')


# ==============================
# CRUD PARA PROVEEDORES 
# ==============================

# Listado
def listar_proveedores(request):
    proveedores = Proveedor.objects.all()
    return render(request, 'sitio1/DataModelApp/Proveedores/listar.html', {'proveedores': proveedores})

# Crear
def crear_proveedor(request):
    if request.method == 'POST':
        form = ProveedorForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('listar_proveedores')
    else:
        form = ProveedorForm()
    return render(request, 'sitio1/DataModelApp/Proveedores/form.html', {'form': form, 'titulo': 'Crear Proveedor'})

# Editar
def editar_proveedor(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    if request.method == 'POST':
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            return redirect('listar_proveedores')
    else:
        form = ProveedorForm(instance=proveedor)
    return render(request, 'sitio1/DataModelApp/Proveedores/form.html', {'form': form, 'titulo': 'Editar Proveedor'})

# Eliminar
def eliminar_proveedor(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    if request.method == 'POST':
        proveedor.delete()
        return redirect('listar_proveedores')
    return render(request, 'sitio1/DataModelApp/Proveedores/eliminar.html', {'proveedor': proveedor})
#=============================
# CRUD PARA UBICACIONES 
# ==============================

# Listar ubicaciones
def listar_ubicaciones(request):
    ubicaciones = Ubicacion.objects.all()
    return render(request, 'sitio1/DataModelApp/Ubicaciones/listar.html', {'ubicaciones': ubicaciones})

# Crear ubicación
def crear_ubicacion(request):
    if request.method == 'POST':
        form = UbicacionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('listar_ubicaciones')
    else:
        form = UbicacionForm()
    return render(request, 'sitio1/DataModelApp/Ubicaciones/form.html', {'form': form, 'titulo': 'Crear Ubicación'})

# Editar Ubicacion
def editar_ubicacion(request, pk):
    ubicacion = get_object_or_404(Ubicacion, pk=pk)
    if request.method == 'POST':
        form = UbicacionForm(request.POST, instance=ubicacion)
        if form.is_valid():
            form.save()
            return redirect('listar_ubicaciones')
    else:
        form = UbicacionForm(instance=ubicacion)
    return render(request, 'sitio1/DataModelApp/Ubicaciones/form.html', {'form': form, 'titulo': 'Editar Ubicación'})
# Eliminar ubicación
def eliminar_ubicacion(request, pk):
    ubicacion = get_object_or_404(Ubicacion, pk=pk)
    if request.method == 'POST':
        ubicacion.delete()
        return redirect('listar_ubicaciones')
    return render(request, 'sitio1/ubicaciones/eliminar.html', {'ubicacion': ubicacion})

# ==============================
# Crud para Categorias
# ==============================
# Listado
def listar_categorias(request):
    categorias = Categoria.objects.all()
    return render(request, 'sitio1/DataModelApp/Categoria/listar.html', {'categorias': categorias})
# Crear
def crear_categoria(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('listar_categorias')
    else:
        form = CategoriaForm()
    return render(request, 'sitio1/DataModelApp/Categoria/editar.html', {'form': form, 'accion': 'Crear'})
# Editar
def editar_categoria(request, id):
    categoria = get_object_or_404(Categoria, id=id)
    if request.method == 'POST':
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            return redirect('listar_categorias')
    else:
        form = CategoriaForm(instance=categoria)
    return render(request, 'sitio1/DataModelApp/Categoria/editar.html', {'form': form, 'accion': 'Editar'})
# Eliminar
def eliminar_categoria(request, id):
    categoria = get_object_or_404(Categoria, id=id)
    if request.method == 'POST':
        categoria.delete()
        return redirect('listar_categorias')
    return render(request, 'sitio1/DataModelApp/Categoria/eliminar.html', {'categoria': categoria})

# ==============================
# CRUD PARA USUARIOS
# ==============================

            #listado de usuarios
def lista_usuarios(request):
    usuarios = Usuario.objects.all()
    
    context = {
        'usuarios': usuarios,
        'total_usuarios': usuarios.count(),
        'usuarios_activos': usuarios.filter(estado=True).count(),
        'usuarios_inactivos': usuarios.filter(estado=False).count(),
    }
    
    return render(request, 'sitio1/DataModelApp/Users/lista.html', context)

def crear_usuario(request):
    if request.method == 'POST':
        form = UsuarioRegistroForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')  # después de crear, lo mandas al login
    else:
        form = UsuarioRegistroForm()
    return render(request, 'sitio1/DataModelApp/Users/form.html', {'form': form})

def editar_usuario(request, id):
    user_instance = get_object_or_404(User, id=id)
    usuario_instance = get_object_or_404(Usuario, user=user_instance)

    if request.method == 'POST':
        form = UsuarioRegistroForm(
            request.POST,
            instance=user_instance,
            usuario_instance=usuario_instance
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario actualizado exitosamente')
            return redirect('lista_usuarios')
    else:
        form = UsuarioRegistroForm(
            instance=user_instance,
            usuario_instance=usuario_instance,
            initial={
                'nombre_completo': usuario_instance.nombre_completo,
                'rol': usuario_instance.rol
            }
        )

    return render(request, 'sitio1/DataModelApp/Users/form.html', {'form': form})


def eliminar_usuario(request, id):
    # Obtener la instancia de User
    user_instance = get_object_or_404(User, id=id)
    
    # También obtenemos el perfil Usuario por si quieres usar info en el template
    usuario_instance = get_object_or_404(Usuario, user=user_instance)

    if request.method == 'POST':
        # Borra User (y el perfil Usuario se borrará automáticamente por OneToOneField)
        user_instance.delete()
        return redirect('lista_usuarios')

    return render(request, 'sitio1/DataModelApp/Users/eliminar.html', {'usuario': usuario_instance})


            
            
# ==============================
# CRUD PARA ROLES
# ==============================
def es_admin(user):
    return user.is_superuser  # puedes reemplazar por validar rol

@user_passes_test(es_admin)
def crear_rol(request):
    if request.method == "POST":
        form = RolForm(request.POST)
        if form.is_valid():
            rol = form.save()
            rol.permisos.set(form.cleaned_data['permisos'])
            rol.save()
            messages.success(request, f'Rol "{rol.nombre}" creado exitosamente')
            return redirect('listar_roles')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario')
    else:
        form = RolForm()

    context = {
        'form': form,
        'accion': 'Crear'
    }
    return render(request, "sitio1/DataModelApp/Rol/crear_rol.html", context)


@user_passes_test(es_admin)
def editar_rol(request, pk):
    rol = get_object_or_404(Rol, pk=pk)
    if request.method == 'POST':
        form = RolForm(request.POST, instance=rol)
        if form.is_valid():
            rol = form.save()
            rol.permisos.set(form.cleaned_data['permisos'])
            rol.save()
            messages.success(request, f'Rol "{rol.nombre}" actualizado exitosamente')
            return redirect('listar_roles')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario')
    else:
        form = RolForm(instance=rol)
    
    context = {
        'form': form,
        'accion': 'Editar'
    }
    return render(request, 'sitio1/DataModelApp/Rol/crear_rol.html', context)

@user_passes_test(es_admin)
def listar_roles(request):
    roles = Rol.objects.all()
    return render(request, "sitio1/DataModelApp/Rol/listar_roles.html", {"roles": roles})
            




# Eliminar rol
def eliminar_rol(request, pk):
    rol = get_object_or_404(Rol, pk=pk)
    if request.method == 'POST':
        rol.delete()
        return redirect('listar_roles')
    return render(request, 'sitio1/DataModelApp/Rol/eliminar.html', {'rol': rol})
            
            


# ==============================
# VISTAS PARA LAS VENTAS
# ==============================

#Listar ventas
@login_required
def listar_ventas(request):
    """
    Vista mejorada del listado de ventas con filtros y estadísticas
    """
    # Obtener todas las ventas
    ventas_query = Venta.objects.select_related('usuario').prefetch_related('detalles__producto').order_by('-fecha')
    
    # ==========================================
    # FILTROS
    # ==========================================
    q = request.GET.get('q', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    medio_pago = request.GET.get('medio_pago', '')
    estado = request.GET.get('estado', '')
    
    if q:
        ventas_query = ventas_query.filter(
            Q(id__icontains=q) |
            Q(usuario__username__icontains=q)
        )
    
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d')
            ventas_query = ventas_query.filter(fecha__date__gte=fecha_desde_dt.date())
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d')
            ventas_query = ventas_query.filter(fecha__date__lte=fecha_hasta_dt.date())
        except ValueError:
            pass
    
    if medio_pago:
        ventas_query = ventas_query.filter(medio_pago=medio_pago)
    
    if estado:
        ventas_query = ventas_query.filter(estado=estado)
    
    # ==========================================
    # ESTADÍSTICAS
    # ==========================================
    todas_ventas = Venta.objects.all()
    
    total_ventas = todas_ventas.aggregate(total=Sum('total'))['total'] or 0
    cantidad_ventas = todas_ventas.count()
    
    # Ventas de hoy
    hoy = timezone.now().date()
    ventas_hoy_query = todas_ventas.filter(fecha__date=hoy)
    ventas_hoy = ventas_hoy_query.aggregate(total=Sum('total'))['total'] or 0
    cantidad_hoy = ventas_hoy_query.count()
    
    # Ticket promedio
    ticket_promedio = todas_ventas.aggregate(promedio=Avg('total'))['promedio'] or 0
    
    # Última venta
    ultima_venta = Venta.objects.order_by('-fecha').first()
    
    # ==========================================
    # PAGINACIÓN
    # ==========================================
    paginator = Paginator(ventas_query, 20)  # 20 ventas por página
    page_number = request.GET.get('page', 1)
    ventas_paginadas = paginator.get_page(page_number)
    
    context = {
        'ventas': ventas_paginadas,
        'total_ventas': total_ventas,
        'cantidad_ventas': cantidad_ventas,
        'ventas_hoy': ventas_hoy,
        'cantidad_hoy': cantidad_hoy,
        'ticket_promedio': ticket_promedio,
        'ultima_venta': ultima_venta,
    }
    
    return render(request, 'sitio1/DataModelApp/Ventas/listar_ventas.html', context)


#detalles
def detalle_venta(request, venta_id):
    venta = get_object_or_404(Venta, id=venta_id)
    detalles = DetalleVenta.objects.filter(venta=venta)
    return render(request, 'sitio1/DataModelApp/Ventas/detalle_venta.html', {
        'venta': venta,
        'detalles': detalles
    })

#Crear una venta
@login_required
@transaction.atomic
def crear_venta(request):
    productos = Productos.objects.all()  # todos los productos disponibles

    if request.method == 'POST':
        venta_form = VentaForm(request.POST)

        if venta_form.is_valid():
            venta = venta_form.save(commit=False)
            venta.usuario = request.user
            venta.total = 0
            venta.save()

            formset = DetalleVentaFormSet(request.POST, instance=venta)

            if formset.is_valid():
                total = 0
                for form in formset:
                    detalle = form.save(commit=False)
                    detalle.subtotal = detalle.cantidad * detalle.precio_unidad
                    total += detalle.subtotal

                    producto = detalle.producto
                    producto.stock_actual -= detalle.cantidad
                    producto.save()
                    detalle.save()

                venta.total = total
                venta.save()
                messages.success(request, f"Venta #{venta.id} registrada correctamente.")
                return redirect('listar_ventas')

            else:
                messages.error(request, "Hay errores en los detalles de la venta.")
        else:
            formset = DetalleVentaFormSet(request.POST, instance=Venta())
    else:
        venta_form = VentaForm()
        formset = DetalleVentaFormSet(instance=Venta())

    return render(request, 'sitio1/DataModelApp/Ventas/form.html', {
        'venta_form': venta_form,
        'formset': formset,
        'productos': productos  # <-- pasamos productos
    })


# ==============================
# Analisis
# ==============================
from django.db.models import Sum
from sitio1.models import Venta, DetalleVenta, Productos

def panel_analytics_ia(request):
    """Panel principal de Analytics e IA"""
    return render(request, 'sitio1/DataModelApp/Gestion/opciones_analisis.html')

# ==============================
# API Ventas JSON
# ==============================
def venta_view(request):
    return render(request, 'sitio1/DataModelApp/Ventas/aaa.html')

def api_productos(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse([], safe=False)

    productos = Productos.objects.filter(
        Q(nombre__icontains=q) | Q(sku__icontains=q)
    )[:10]

    data = [
        {
            'id': p.id,
            'sku': p.sku,
            'nombre': p.nombre,
            'precio_unitario': float(p.precio_unitario or 0),
            'stock_actual': p.stock_actual,
        }
        for p in productos
    ]
    return JsonResponse(data, safe=False)





@login_required
def api_productos(request):
    """
    API para buscar productos en tiempo real
    """
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    try:
        productos = Productos.objects.filter(
            Q(nombre__icontains=query) | Q(sku__icontains=query),
            activo=True
        ).values(
            'id', 'sku', 'nombre', 'precio_unitario', 
            'stock_actual', 'costo_unitario'
        )[:10]  # Limitar a 10 resultados
        
        return JsonResponse(list(productos), safe=False)
    
    except Exception as e:
        logger.error(f"Error en búsqueda de productos: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@login_required
def api_venta(request):
    """
    API para procesar ventas en mostrador
    
    Mejoras:
    - Validación de stock completa
    - Manejo de ventas forzadas
    - Registro detallado de movimientos
    - Transacciones atómicas
    - Logging de errores
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        productos = data.get('productos', [])
        medio_pago = data.get('medio_pago', 'efectivo')
        forzar = data.get('forzar', False)

        # Validaciones básicas
        if not productos:
            return JsonResponse({'error': 'No se enviaron productos'}, status=400)

        # Validar que medio_pago sea válido
        medios_validos = ['efectivo', 'tarjeta', 'transferencia']
        if medio_pago not in medios_validos:
            return JsonResponse({'error': 'Medio de pago inválido'}, status=400)

        # ==========================================
        # FASE 1: Validar stock de todos los productos
        # ==========================================
        productos_insuficientes = []
        
        for p in productos:
            try:
                producto = Productos.objects.get(id=p['id'], activo=True)
                cantidad = int(p['cantidad'])
                
                if cantidad <= 0:
                    return JsonResponse({
                        'error': f'Cantidad inválida para {producto.nombre}'
                    }, status=400)

                if producto.stock_actual < cantidad and not forzar:
                    productos_insuficientes.append({
                        'nombre': producto.nombre,
                        'stock': producto.stock_actual,
                        'solicitado': cantidad
                    })
                    
            except Productos.DoesNotExist:
                return JsonResponse({
                    'error': f'Producto con ID {p["id"]} no encontrado'
                }, status=404)
            except ValueError:
                return JsonResponse({
                    'error': 'Cantidad debe ser un número entero'
                }, status=400)

        # Si hay productos con stock insuficiente y no se forzó
        if productos_insuficientes and not forzar:
            mensaje_error = "Stock insuficiente:\n"
            for prod in productos_insuficientes:
                mensaje_error += f"\n• {prod['nombre']}: Disponible {prod['stock']}, Solicitado {prod['solicitado']}"
            
            return JsonResponse({
                'error': mensaje_error,
                'puede_forzar': True,
                'productos_insuficientes': productos_insuficientes
            }, status=400)

        # ==========================================
        # FASE 2: Procesar venta (transacción atómica)
        # ==========================================
        with transaction.atomic():
            # Calcular total
            total = Decimal('0.00')
            detalles_venta = []
            
            for p in productos:
                cantidad = int(p['cantidad'])
                precio = Decimal(str(p['precio_unitario']))
                subtotal = precio * cantidad
                total += subtotal
                
                detalles_venta.append({
                    'producto_id': p['id'],
                    'cantidad': cantidad,
                    'precio': precio,
                    'subtotal': subtotal
                })

            # Crear venta
            venta = Venta.objects.create(
                usuario=request.user,
                total=total,
                medio_pago=medio_pago,
                estado='completada'
            )

            # Procesar cada producto
            for detalle in detalles_venta:
                producto = Productos.objects.select_for_update().get(
                    id=detalle['producto_id']
                )
                cantidad = detalle['cantidad']
                
                # Determinar tipo de movimiento
                if forzar and producto.stock_actual < cantidad:
                    tipo_mov = 'venta_forzada'
                    motivo = f"Venta forzada por falta de stock. Stock: {producto.stock_actual}, Vendido: {cantidad}"
                else:
                    tipo_mov = 'salida'
                    motivo = f"Venta en mostrador #{venta.id}"

                # Registrar movimiento de inventario
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo_movimiento=tipo_mov,
                    cantidad=cantidad,
                    usuario=request.user,
                    motivo=motivo
                )

                # Actualizar stock
                producto.stock_actual -= cantidad
                producto.save()

                # Crear detalle de venta
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unidad=detalle['precio'],
                    costo_unitario=producto.costo_unitario or Decimal('0.00'),
                    subtotal=detalle['subtotal']
                )

            # Log de éxito
            logger.info(
                f"Venta #{venta.id} procesada. Usuario: {request.user.username}, "
                f"Total: ${total}, Productos: {len(detalles_venta)}, "
                f"Forzada: {forzar}"
            )

            # Respuesta exitosa
            return JsonResponse({
                'success': True,
                'mensaje': 'Venta registrada correctamente',
                'venta_id': venta.id,
                'total': float(total),
                'fecha': venta.fecha.isoformat(),
                'medio_pago': medio_pago,
                'productos_vendidos': len(detalles_venta),
                'forzada': forzar
            })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    except Exception as e:
        logger.error(f"Error al procesar venta: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error al procesar venta: {str(e)}'
        }, status=500)


@login_required
def api_productos_frecuentes(request):
    """
    API para obtener productos más vendidos (para mostrar sugerencias)
    """
    try:
        from django.db.models import Sum, Count
        from datetime import timedelta
        from django.utils import timezone
        
        hace_30_dias = timezone.now() - timedelta(days=30)
        
        productos_frecuentes = (
            DetalleVenta.objects
            .filter(venta__fecha__gte=hace_30_dias)
            .values('producto__id', 'producto__nombre', 'producto__sku', 
                   'producto__precio_unitario', 'producto__stock_actual')
            .annotate(
                total_vendido=Sum('cantidad'),
                veces_vendido=Count('id')
            )
            .order_by('-total_vendido')[:8]
        )
        
        resultado = []
        for p in productos_frecuentes:
            resultado.append({
                'id': p['producto__id'],
                'nombre': p['producto__nombre'],
                'sku': p['producto__sku'],
                'precio_unitario': float(p['producto__precio_unitario']),
                'stock_actual': p['producto__stock_actual'],
                'total_vendido': p['total_vendido'],
                'veces_vendido': p['veces_vendido']
            })
        
        return JsonResponse(resultado, safe=False)
    
    except Exception as e:
        logger.error(f"Error obteniendo productos frecuentes: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# ==============================
            
            #registro de usuario
def registro(request):
    data = {'form': UsuarioForm()}

    if request.method == 'POST':
        formulario = UsuarioForm(request.POST)
        if formulario.is_valid():
            usuario = formulario.save(commit=False)
            # Encriptar contraseña antes de guardar
            from django.contrib.auth.hashers import make_password
            usuario.contrasena = make_password(formulario.cleaned_data['contrasena'])
            usuario.save()

            messages.success(request, "Usuario registrado exitosamente.")
            return redirect('login')  # o redirige a donde prefieras

        data['form'] = formulario

    return render(request, 'registration/registro.html', data)




# ==============================
class VentaCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VentaSerializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
            data = serializer.save()
            return Response(data, status=status.HTTP_200_OK)

        except serializers.ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        


# =====================================================
# DASHBOARD PRINCIPAL CON ANÁLISIS
# =====================================================

def dashboard_view(request):
    """
    Dashboard principal con análisis completos
    """
    
    
    # Métricas básicas
    total_ventas = Venta.objects.aggregate(total=Sum('total'))['total'] or 0
    cantidad_ventas = Venta.objects.count()
    
    # Productos
    total_productos_activos = Productos.objects.filter(activo=True).count()
    productos_sin_stock = Productos.objects.filter(stock_actual=0, activo=True).count()
    
    # Stock bajo (query base)
    productos_stock_bajo_qs = Productos.objects.filter(
        activo=True,
        stock_minimo__gt=0,                 # sólo productos con mínimo definido
        stock_actual__lte=F('stock_minimo')
    ).order_by('stock_actual')

    # Conteo total para la tarjeta
    productos_stock_bajo = productos_stock_bajo_qs.count()

    
    # Fechas
    hace_30_dias = timezone.now() - timedelta(days=30)
    hace_60_dias = timezone.now() - timedelta(days=60)
    
    # Ventas mes actual
    ventas_mes = Venta.objects.filter(fecha__gte=hace_30_dias).aggregate(
        total=Sum('total')
    )['total'] or 0
    
    # Ventas mes anterior (para comparación)
    ventas_mes_anterior = Venta.objects.filter(
        fecha__gte=hace_60_dias,
        fecha__lt=hace_30_dias
    ).aggregate(total=Sum('total'))['total'] or 0
    
    # Crecimiento
    if ventas_mes_anterior > 0:
        crecimiento_ventas = ((ventas_mes - ventas_mes_anterior) / ventas_mes_anterior) * 100
    else:
        crecimiento_ventas = 0
    
    # Ticket promedio
    if cantidad_ventas > 0:
        ticket_promedio = total_ventas / cantidad_ventas
    else:
        ticket_promedio = 0
    
    # ==========================================
    # KPIs ADICIONALES
    # ==========================================
    
    # Margen promedio
    ventas_con_costo = DetalleVenta.objects.filter(
        costo_unitario__isnull=False
    ).aggregate(
        total_costo=Sum(F('cantidad') * F('costo_unitario')),
        total_ingreso=Sum('subtotal')
    )
    
    if ventas_con_costo['total_costo'] and ventas_con_costo['total_ingreso']:
        margen_promedio = ((ventas_con_costo['total_ingreso'] - ventas_con_costo['total_costo']) / 
                          ventas_con_costo['total_ingreso']) * 100
    else:
        margen_promedio = 0
    
    # Productos vendidos en el mes
    productos_vendidos_mes = DetalleVenta.objects.filter(
        venta__fecha__gte=hace_30_dias
    ).values('producto').distinct().count()
    
    porcentaje_productos_vendidos = (productos_vendidos_mes / total_productos_activos * 100) if total_productos_activos > 0 else 0
    
    # Rotación promedio
    rotacion_promedio = 15  # Placeholder - cálculo complejo
    
    # Valor del inventario
    valor_inventario_total = Productos.objects.filter(activo=True).aggregate(
        total=Sum(F('stock_actual') * F('precio_unitario'))
    )['total'] or 0
    
    # Mejor día de la semana
    ventas_por_dia_semana = Venta.objects.annotate(
        dia_semana=ExtractWeekDay('fecha')
    ).values('dia_semana').annotate(
        total=Sum('total')
    ).order_by('-total').first()
    
    dias_nombres = ['', 'Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
    if ventas_por_dia_semana:
        mejor_dia_semana = dias_nombres[ventas_por_dia_semana['dia_semana']]
        mejor_dia_ventas = ventas_por_dia_semana['total']
    else:
        mejor_dia_semana = 'N/A'
        mejor_dia_ventas = 0
    
    # Hora pico
    ventas_por_hora = Venta.objects.annotate(
        hora=ExtractHour('fecha')
    ).values('hora').annotate(
        cantidad=Count('id')
    ).order_by('-cantidad').first()
    
    hora_pico = ventas_por_hora['hora'] if ventas_por_hora else 12
    
    # ==========================================
    # GRÁFICOS
    # ==========================================
    
    # GRÁFICO 1: Top 5 Productos (Ventas + Stock)
    productos_populares = (
        DetalleVenta.objects
        .values('producto__nombre', 'producto__stock_actual')
        .annotate(
            cantidad_vendida=Sum('cantidad'),
            ingresos_totales=Sum('subtotal')
        )
        .order_by('-cantidad_vendida')[:5]
    )
    
    labels_productos = [p['producto__nombre'] for p in productos_populares]
    data_ventas_productos = [int(p['cantidad_vendida']) for p in productos_populares]
    data_stock_productos = [int(p['producto__stock_actual']) for p in productos_populares]
    
    # GRÁFICO 2: Ventas por día (Monto + Cantidad transacciones)
    ventas_por_dia = []
    for i in range(6, -1, -1):
        dia = timezone.now() - timedelta(days=i)
        stats_dia = Venta.objects.filter(fecha__date=dia.date()).aggregate(
            total=Sum('total'),
            cantidad=Count('id')
        )
        ventas_por_dia.append({
            'fecha': dia.strftime('%d/%m'),
            'total': float(stats_dia['total'] or 0),
            'cantidad': stats_dia['cantidad'] or 0
        })
    
    labels_ventas = [v['fecha'] for v in ventas_por_dia]
    data_monto_ventas = [v['total'] for v in ventas_por_dia]
    data_cant_ventas = [v['cantidad'] for v in ventas_por_dia]
    
    # GRÁFICO 3: Rentabilidad por producto (Top 5)
    rentabilidad = (
        DetalleVenta.objects
        .values('producto__nombre')
        .annotate(
            total_costo=Sum(F('cantidad') * F('costo_unitario')),
            total_ingreso=Sum('subtotal'),
            ganancia=ExpressionWrapper(
                Sum('subtotal') - Sum(F('cantidad') * F('costo_unitario')),
                output_field=DecimalField()
            )
        )
        .filter(costo_unitario__isnull=False)
        .order_by('-ganancia')[:5]
    )
    
    labels_rentabilidad = [r['producto__nombre'] for r in rentabilidad]
    data_costos = [float(r['total_costo'] or 0) for r in rentabilidad]
    data_ganancias = [float(r['ganancia'] or 0) for r in rentabilidad]
    
    # GRÁFICO 4: Distribución por categorías
    ventas_categorias = (
        DetalleVenta.objects
        .filter(venta__fecha__gte=hace_30_dias)
        .values('producto__categoria__nombre')
        .annotate(total=Sum('subtotal'))
        .order_by('-total')[:6]
    )
    
    labels_categorias = [vc['producto__categoria__nombre'] for vc in ventas_categorias]
    data_categorias = [float(vc['total']) for vc in ventas_categorias]
    
    # GRÁFICO 5: Tendencia últimos 30 días
    ventas_tendencia = []
    for i in range(29, -1, -1):
        dia = timezone.now() - timedelta(days=i)
        total_dia = Venta.objects.filter(fecha__date=dia.date()).aggregate(
            total=Sum('total')
        )['total'] or 0
        ventas_tendencia.append({
            'fecha': dia.strftime('%d/%m'),
            'total': float(total_dia)
        })
    
    labels_tendencia = [vt['fecha'] for vt in ventas_tendencia]
    data_tendencia = [vt['total'] for vt in ventas_tendencia]
    
    # ==========================================
    # ALERTAS Y RECOMENDACIONES
    # ==========================================
    
    
   # Productos críticos (mismas reglas que la tarjeta)
    productos_criticos = list(productos_stock_bajo_qs[:10])  # top 10 para el panel
    
    # Productos sin movimiento (más de 30 días)
    productos_sin_movimiento = []
    for prod in Productos.objects.filter(activo=True):
        ultima_venta = DetalleVenta.objects.filter(producto=prod).order_by('-venta__fecha').first()
        if ultima_venta:
            dias_sin_venta = (timezone.now() - ultima_venta.venta.fecha).days
        else:
            dias_sin_venta = 999
        
        if dias_sin_venta > 30:
            prod.dias_sin_venta = dias_sin_venta
            productos_sin_movimiento.append(prod)
    
    productos_sin_movimiento = sorted(productos_sin_movimiento, key=lambda x: x.dias_sin_venta, reverse=True)[:10]
    
    # Productos más rentables
    productos_rentables = []
    for prod in Productos.objects.filter(activo=True, costo_unitario__isnull=False):
        if prod.costo_unitario > 0:
            margen = ((prod.precio_unitario - prod.costo_unitario) / prod.precio_unitario) * 100
            prod.margen = margen
            productos_rentables.append(prod)
    
    productos_mas_rentables = sorted(productos_rentables, key=lambda x: x.margen, reverse=True)[:10]
    
    # ==========================================
    # RESUMEN POR CATEGORÍA
    # ==========================================
    
    from django.db.models import Q
    
    categorias = Categoria.objects.all()
    resumen_categorias = []
    
    for cat in categorias:
        # Ventas del mes actual
        ventas_cat_mes = DetalleVenta.objects.filter(
            producto__categoria=cat,
            venta__fecha__gte=hace_30_dias
        ).aggregate(
            unidades=Sum('cantidad'),
            ingresos=Sum('subtotal'),
            costo_total=Sum(F('cantidad') * F('costo_unitario'))
        )
        
        # Ventas mes anterior
        ventas_cat_anterior = DetalleVenta.objects.filter(
            producto__categoria=cat,
            venta__fecha__gte=hace_60_dias,
            venta__fecha__lt=hace_30_dias
        ).aggregate(
            ingresos=Sum('subtotal')
        )
        
        ingresos_mes = ventas_cat_mes['ingresos'] or 0
        ingresos_anterior = ventas_cat_anterior['ingresos'] or 0
        
        # Calcular tendencia
        if ingresos_anterior > 0:
            tendencia = ((ingresos_mes - ingresos_anterior) / ingresos_anterior) * 100
        else:
            tendencia = 0 if ingresos_mes == 0 else 100
        
        # Calcular margen
        costo_total = ventas_cat_mes['costo_total'] or 0
        if ingresos_mes > 0 and costo_total > 0:
            margen = ((ingresos_mes - costo_total) / ingresos_mes) * 100
        else:
            margen = 0
        
        # Porcentaje del total
        porcentaje = (ingresos_mes / ventas_mes * 100) if ventas_mes > 0 else 0
        
        cantidad_productos = Productos.objects.filter(categoria=cat, activo=True).count()
        
        if ingresos_mes > 0:  # Solo categorías con ventas
            resumen_categorias.append({
                'nombre': cat.nombre,
                'cantidad_productos': cantidad_productos,
                'unidades_vendidas': ventas_cat_mes['unidades'] or 0,
                'ingresos': ingresos_mes,
                'porcentaje': porcentaje,
                'margen': margen,
                'tendencia': tendencia
            })
    
    # Ordenar por ingresos
    resumen_categorias = sorted(resumen_categorias, key=lambda x: x['ingresos'], reverse=True)
    
    # ==========================================
    # CONTEXTO
    # ==========================================
    
    context = {
        # Métricas principales
        'total_ventas': total_ventas,
        'cantidad_ventas': cantidad_ventas,
        'ventas_mes': ventas_mes,
        'productos_stock_bajo': productos_stock_bajo,
        
        # KPIs adicionales
        'total_productos_activos': total_productos_activos,
        'productos_sin_stock': productos_sin_stock,
        'crecimiento_ventas': crecimiento_ventas,
        'ticket_promedio': ticket_promedio,
        'margen_promedio': margen_promedio,
        'productos_vendidos_mes': productos_vendidos_mes,
        'porcentaje_productos_vendidos': porcentaje_productos_vendidos,
        'rotacion_promedio': rotacion_promedio,
        'valor_inventario_total': valor_inventario_total,
        'mejor_dia_semana': mejor_dia_semana,
        'mejor_dia_ventas': mejor_dia_ventas,
        'hora_pico': hora_pico,
        
        # Gráfico 1: Top Productos
        'labels_productos': labels_productos,
        'data_ventas_productos': data_ventas_productos,
        'data_stock_productos': data_stock_productos,
        
        # Gráfico 2: Ventas 7 días
        'labels_ventas': labels_ventas,
        'data_monto_ventas': data_monto_ventas,
        'data_cant_ventas': data_cant_ventas,
        
        # Gráfico 3: Rentabilidad
        'labels_rentabilidad': labels_rentabilidad,
        'data_costos': data_costos,
        'data_ganancias': data_ganancias,
        
        # Gráfico 4: Categorías
        'labels_categorias': labels_categorias,
        'data_categorias': data_categorias,
        
        # Gráfico 5: Tendencia
        'labels_tendencia': labels_tendencia,
        'data_tendencia': data_tendencia,
        
        # Alertas
        'productos_criticos': productos_criticos,
        'productos_sin_movimiento': productos_sin_movimiento,
        'productos_mas_rentables': productos_mas_rentables,
        
        # Resumen categorías
        'resumen_categorias': resumen_categorias,
    }
    
    return render(request, "sitio1/DataModelApp/Dashboard/dashboard.html", context)


# =====================================================
# VISTAS DE INTELIGENCIA ARTIFICIAL
# =====================================================

def dashboard_ia_view(request):
    """
    Dashboard con predicciones de IA y análisis avanzados.
    
    Incluye:
    - Entrenamiento de modelos
    - Alertas inteligentes
    - Clasificación automática de productos
    - Estadísticas del modelo
    """
    context = {
        'seccion': 'ia'
    }
    
    # ==========================================
    # ENTRENAR MODELO
    # ==========================================
    if request.GET.get('entrenar'):
        try:
            logger.info("Iniciando entrenamiento desde dashboard")
            modelo, mensaje, metricas = entrenar_modelo_demanda()
            
            if modelo:
                messages.success(request, mensaje, extra_tags="ia")
                context['metricas_entrenamiento'] = metricas
            else:
                messages.warning(request, mensaje, extra_tags="ia")
                
        except Exception as e:
            logger.error(f"Error en entrenamiento: {e}")
            messages.error(
                request,
                f"Error al entrenar modelo: {str(e)}",
                extra_tags="ia"
            )
    
    # ==========================================
    # EVALUAR MODELO ACTUAL
    # ==========================================
    if request.GET.get('evaluar'):
        try:
            metricas_eval = evaluar_modelo_actual()
            if 'error' not in metricas_eval:
                context['metricas_evaluacion'] = metricas_eval
                messages.info(
                    request,
                    f"Modelo evaluado. RMSE: {metricas_eval['rmse']:.2f}",
                    extra_tags="ia"
                )
            else:
                messages.warning(
                    request,
                    metricas_eval['error'],
                    extra_tags="ia"
                )
        except Exception as e:
            logger.error(f"Error en evaluación: {e}")
            messages.error(
                request,
                f"Error al evaluar: {str(e)}",
                extra_tags="ia"
            )
    
    # ==========================================
    # GENERAR ALERTAS IA
    # ==========================================
    try:
        alertas = generar_alertas_ia()
        context['alertas_ia'] = alertas
        
        # Estadísticas de alertas
        context['stats_alertas'] = {
            'total': len(alertas),
            'criticas': sum(1 for a in alertas if a['tipo'] == 'critico'),
            'preventivas': sum(1 for a in alertas if a['tipo'] == 'preventivo'),
            'oportunidades': sum(1 for a in alertas if a['tipo'] == 'oportunidad')
        }
        
    except Exception as e:
        logger.error(f"Error generando alertas: {e}")
        context['error_alertas'] = str(e)
        messages.error(
            request,
            f"Error al generar alertas: {str(e)}",
            extra_tags="ia"
        )
    
    # ==========================================
    # CLASIFICACIÓN DE PRODUCTOS (CLUSTERING)
    # ==========================================
    try:
        clasificacion_df, error = clasificar_productos_ml()
        
        if clasificacion_df is not None:
            context['clasificacion'] = clasificacion_df.to_dict('records')
            
            # Estadísticas de clustering
            context['stats_clustering'] = {
                'total_productos': len(clasificacion_df),
                'alta_rotacion': len(clasificacion_df[clasificacion_df['categoria_ia'] == 'Alta Rotación']),
                'media_rotacion': len(clasificacion_df[clasificacion_df['categoria_ia'] == 'Media Rotación']),
                'baja_rotacion': len(clasificacion_df[clasificacion_df['categoria_ia'] == 'Baja Rotación'])
            }
        else:
            context['error_clasificacion'] = error
            messages.warning(
                request,
                error,
                extra_tags="ia"
            )
            
    except Exception as e:
        logger.error(f"Error en clustering: {e}")
        context['error_clasificacion'] = str(e)
        messages.error(
            request,
            f"Error al clasificar productos: {str(e)}",
            extra_tags="ia"
        )
    
    # ==========================================
    # ESTADÍSTICAS DEL MODELO
    # ==========================================
    try:
        stats_modelo = obtener_estadisticas_modelo()
        context['stats_modelo'] = stats_modelo
    except Exception as e:
        logger.error(f"Error obteniendo stats del modelo: {e}")
    
    return render(request, 'sitio1/DataModelApp/IA/dashboard_ia.html', context)


def prediccion_producto_view(request, producto_id):
    """
    Vista detallada de predicción para un producto específico.
    
    Muestra:
    - Predicción diaria para los próximos 14 días
    - Comparación stock vs demanda
    - Recomendaciones de reabastecimiento
    - Gráfico interactivo de tendencias
    """
    try:
        # Generar predicción a 14 días
        resultado, error = predecir_demanda_producto(producto_id, dias_adelante=14)
        
        if error:
            messages.error(request, error, extra_tags="ia")
            resultado = None
        else:
            # Calcular métricas adicionales
            if resultado:
                # Velocidad de consumo promedio
                velocidad_diaria = resultado['total_estimado'] / 14
                
                # Días hasta agotamiento
                if velocidad_diaria > 0:
                    dias_agotamiento = resultado['stock_actual'] / velocidad_diaria
                else:
                    dias_agotamiento = 999
                
                resultado['velocidad_diaria'] = round(velocidad_diaria, 2)
                resultado['dias_agotamiento'] = int(dias_agotamiento)
                
                # Nivel de criticidad
                if dias_agotamiento < 3:
                    resultado['nivel_criticidad'] = 'crítico'
                elif dias_agotamiento < 7:
                    resultado['nivel_criticidad'] = 'alto'
                elif dias_agotamiento < 14:
                    resultado['nivel_criticidad'] = 'medio'
                else:
                    resultado['nivel_criticidad'] = 'bajo'
        
        # Preparar datos para gráfico
        if resultado:
            labels = [p['fecha'].strftime('%d/%m') for p in resultado['predicciones_diarias']]
            data = [p['cantidad_estimada'] for p in resultado['predicciones_diarias']]
        else:
            labels = []
            data = []
        
        context = {
            'resultado': resultado,
            'labels_prediccion': labels,
            'data_prediccion': data
        }
        
    except Exception as e:
        logger.error(f"Error en predicción de producto {producto_id}: {e}")
        messages.error(
            request,
            f"Error inesperado: {str(e)}",
            extra_tags="ia"
        )
        context = {
            'resultado': None,
            'labels_prediccion': [],
            'data_prediccion': []
        }
    
    return render(request, 'sitio1/DataModelApp/IA/prediccion_producto.html', context)


# =====================================================
# API ENDPOINTS PARA DATOS DINÁMICOS (OPCIONAL)
# =====================================================

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET"])
def api_prediccion_producto(request, producto_id):
    """
    API endpoint para obtener predicción en formato JSON.
    
    Útil para:
    - Integración con frontend JavaScript
    - Aplicaciones móviles
    - Dashboards externos
    """
    try:
        dias = int(request.GET.get('dias', 7))
        resultado, error = predecir_demanda_producto(producto_id, dias_adelante=dias)
        
        if error:
            return JsonResponse({'error': error}, status=400)
        
        # Serializar resultado
        response_data = {
            'producto_id': producto_id,
            'producto_nombre': resultado['producto'].nombre,
            'stock_actual': resultado['stock_actual'],
            'total_estimado': resultado['total_estimado'],
            'alerta': resultado['alerta'],
            'predicciones': resultado['predicciones_diarias']
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error en API predicción: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_alertas(request):
    """
    API endpoint para obtener todas las alertas activas.
    """
    try:
        alertas = generar_alertas_ia()
        
        # Serializar alertas
        alertas_json = []
        for alerta in alertas:
            alertas_json.append({
                'producto_id': alerta['producto'].id,
                'producto_nombre': alerta['producto'].nombre,
                'tipo': alerta['tipo'],
                'prioridad': alerta['prioridad'],
                'mensaje': alerta['mensaje'],
                'demanda_estimada': alerta['demanda_estimada'],
                'stock_actual': alerta['stock_actual'],
                'accion_sugerida': alerta['accion_sugerida']
            })
        
        return JsonResponse({
            'alertas': alertas_json,
            'total': len(alertas_json)
        })
        
    except Exception as e:
        logger.error(f"Error en API alertas: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def api_entrenar_modelo(request):
    """
    API endpoint para entrenar el modelo (requiere autenticación).
    """
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'No autorizado'}, status=403)
    
    try:
        modelo, mensaje, metricas = entrenar_modelo_demanda()
        
        if modelo:
            return JsonResponse({
                'success': True,
                'mensaje': mensaje,
                'metricas': metricas
            })
        else:
            return JsonResponse({
                'success': False,
                'mensaje': mensaje
            }, status=400)
            
    except Exception as e:
        logger.error(f"Error entrenando modelo via API: {e}")
        return JsonResponse({'error': str(e)}, status=500)
    

# =====================================================
# editar user
# =====================================================

# =====================================================
# VER PERFIL (solo mostrar información)
# =====================================================
@login_required
def ver_perfil(request):
    """Vista para MOSTRAR el perfil del usuario"""
    
    # Obtener o crear el usuario
    usuario, created = Usuario.objects.get_or_create(
        user=request.user,
        defaults={'rol_id': 1}
    )
    
    # Obtener las últimas 10 actividades
    actividades = ActividadUsuario.objects.filter(
        usuario=request.user
    ).order_by('-fecha_hora')[:10]
    
    context = {
        'actividades': actividades
    }
    
    return render(request, "sitio1/DataModelApp/Users/ver_perfil.html", context)


# =====================================================
# EDITAR PERFIL (formulario para editar)
# =====================================================
@login_required
def editar_perfil(request):
    """Vista para EDITAR el perfil del usuario"""
    
    usuario, created = Usuario.objects.get_or_create(
        user=request.user,
        defaults={'rol_id': 1}
    )

    if request.method == "POST":
        form = EditarPerfilForm(request.POST, request.FILES, instance=usuario)
        if form.is_valid():
            form.save()
            
            # Registrar actividad
            registrar_actividad(
                usuario=request.user,
                tipo_actividad='editar_perfil',
                descripcion='Actualización de información del perfil',
                request=request,
                detalles={
                    'campos_modificados': list(form.changed_data)
                }
            )
            
            messages.success(request, 'Perfil actualizado correctamente')
            return redirect('ver_perfil')  # ⚠️ Nota: redirige a ver_perfil
    else:
        form = EditarPerfilForm(instance=usuario)

    return render(request, "sitio1/DataModelApp/Users/editar_perfil.html", {"form": form})


# =====================================================
# FUNCIÓN HELPER PARA REGISTRAR ACTIVIDAD
# =====================================================
def registrar_actividad(usuario, tipo_actividad, descripcion, request=None, detalles=None):
    """Registra una actividad del usuario"""
    ip_address = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
    
    ActividadUsuario.objects.create(
        usuario=usuario,
        tipo_actividad=tipo_actividad,
        descripcion=descripcion,
        ip_address=ip_address,
        detalles=detalles
    )


# =====================================================
# VISTAS DE ÓRDENES DE COMPRA IA
# =====================================================

@login_required
def generar_orden_compra_ia(request):
    """
    Genera automáticamente una orden de compra con los productos críticos y preventivos,
    y en GET muestra el preview con todos los cálculos hechos.
    """

    # ================================
    # POST → CREAR ORDEN DEFINITIVA
    # ================================
    if request.method == 'POST':
        try:
            with transaction.atomic():

                # Crear orden
                orden = OrdenCompraIA()
                orden.numero_orden = orden.generar_numero_orden()
                orden.creado_por = request.user
                orden.estado = 'borrador'
                orden.save()

                # Obtener alertas con datos procesados
                alertas = generar_alertas_ia()

                productos_agregados = 0
                observaciones_ia = []

                for alerta in alertas:
                    if alerta['tipo'] not in ['critico', 'preventivo']:
                        continue

                    producto = alerta['producto']
                    demanda = alerta['demanda_estimada']
                    stock = alerta['stock_actual']

                    # Cálculos corregidos
                    deficit = max(demanda - stock, 0)
                    stock_seguridad = int(demanda * 0.20)
                    cantidad_sugerida = deficit + stock_seguridad

                    if cantidad_sugerida <= 0:
                        continue

                    precio = (
                        producto.costo_unitario
                        if producto.costo_unitario
                        else producto.precio_unitario
                    )

                    ItemOrdenCompraIA.objects.create(
                        orden=orden,
                        producto=producto,
                        proveedor=producto.proveedor,
                        stock_actual=stock,
                        demanda_estimada_14d=demanda,
                        dias_hasta_agotamiento=alerta.get('dias_hasta_agotamiento', 999),
                        nivel_criticidad=alerta['tipo'],
                        cantidad_sugerida_ia=cantidad_sugerida,
                        cantidad_solicitada=cantidad_sugerida,
                        precio_unitario=precio,
                        subtotal=precio * cantidad_sugerida
                    )

                    productos_agregados += 1

                    observaciones_ia.append(
                        f"• {producto.nombre}: {cantidad_sugerida} unidades "
                        f"(Déficit {deficit}, Stock seg {stock_seguridad})"
                    )

                # Guardar observaciones IA
                orden.observaciones_ia = "\n".join([
                    f"🤖 Orden generada automáticamente el {timezone.now().strftime('%d/%m/%Y %H:%M')}",
                    f"📊 Se analizaron {len(alertas)} productos",
                    f"🟡 {productos_agregados} productos agregados",
                    "",
                    "Detalle:",
                    *observaciones_ia
                ])
                orden.save()

                # Recalcular totales
                orden.calcular_totales()

                # Log de auditoría
                LogOrdenCompraIA.objects.create(
                    orden=orden,
                    usuario=request.user,
                    accion='creada',
                    detalle=f'Orden generada con {productos_agregados} productos'
                )

                if productos_agregados > 0:
                    messages.success(
                        request,
                        f"✅ Orden {orden.numero_orden} creada con {productos_agregados} productos"
                    )
                    return redirect('detalle_orden_compra', orden_id=orden.id)
                else:
                    orden.delete()
                    messages.warning(
                        request, "⚠️ No hay productos que requieran reabastecimiento"
                    )
                    return redirect('dashboard_ia')

        except Exception as e:
            logger.error(f"Error al generar orden: {e}")
            messages.error(request, f"❌ Error al generar la orden: {str(e)}")
            return redirect('dashboard_ia')

    # ================================
    # GET → PREVIEW DE ALERTAS
    # ================================
    try:
        alertas_raw = generar_alertas_ia()
        alertas_procesadas = []

        for alerta in alertas_raw:
            if alerta['tipo'] not in ['critico', 'preventivo']:
                continue

            producto = alerta['producto']
            demanda = alerta['demanda_estimada']
            stock = alerta['stock_actual']

            deficit = max(demanda - stock, 0)
            stock_seguridad = int(demanda * 0.20)
            cantidad_sugerida = deficit + stock_seguridad

            precio = (
                producto.costo_unitario
                if producto.costo_unitario
                else producto.precio_unitario
            )

            alertas_procesadas.append({
                "producto": producto,
                "tipo": alerta['tipo'],
                "demanda": demanda,
                "stock": stock,
                "deficit": deficit,
                "stock_seguridad": stock_seguridad,
                "cantidad_sugerida": cantidad_sugerida,
                "precio": precio,
                "subtotal": cantidad_sugerida * precio,
            })

        context = {
            "alertas": alertas_procesadas,
            "total_productos": len(alertas_procesadas),
            "total_criticos": sum(1 for a in alertas_procesadas if a["tipo"] == "critico"),
            "total_preventivos": sum(1 for a in alertas_procesadas if a["tipo"] == "preventivo"),
        }

    except Exception as e:
        logger.error(f"Error cargando alertas IA: {e}")
        messages.error(request, "Error obteniendo información de IA")

        context = {
            "alertas": [],
            "total_productos": 0,
            "total_criticos": 0,
            "total_preventivos": 0,
        }

    return render(request, "sitio1/DataModelApp/IA/preview_orden_ia.html", context)



@login_required
def detalle_orden_compra(request, orden_id):
    """
    Vista de detalle de orden de compra - permite editar antes de enviar
    """
    orden = get_object_or_404(OrdenCompraIA, id=orden_id)
    
    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        if accion == 'actualizar_cantidades':
            # Actualizar cantidades editadas por el usuario
            try:
                with transaction.atomic():
                    items_actualizados = 0
                    for item in orden.items.all():
                        nueva_cantidad = request.POST.get(f'cantidad_{item.id}')
                        observaciones = request.POST.get(f'obs_{item.id}', '')
                        
                        if nueva_cantidad:
                            nueva_cantidad = int(nueva_cantidad)
                            if nueva_cantidad != item.cantidad_solicitada:
                                item.cantidad_solicitada = nueva_cantidad
                                item.observaciones_recepcion = observaciones
                                item.save()
                                items_actualizados += 1
                    
                    # Log
                    LogOrdenCompraIA.objects.create(
                        orden=orden,
                        usuario=request.user,
                        accion='editada',
                        detalle=f'{items_actualizados} items actualizados'
                    )
                    
                    messages.success(request, f'✅ {items_actualizados} productos actualizados')
                    
            except Exception as e:
                logger.error(f"Error actualizando cantidades: {e}")
                messages.error(request, f'❌ Error: {str(e)}')
        
        elif accion == 'aprobar':
            if orden.estado == 'borrador':
                orden.aprobar(request.user)
                
                LogOrdenCompraIA.objects.create(
                    orden=orden,
                    usuario=request.user,
                    accion='aprobada',
                    detalle='Orden aprobada y lista para envío'
                )
                
                messages.success(request, f'✅ Orden {orden.numero_orden} aprobada')
            else:
                messages.warning(request, '⚠️ La orden ya fue aprobada')
        
        elif accion == 'enviar_email':
            if orden.estado in ['aprobada', 'borrador']:
                # Enviar email al proveedor
                resultado = enviar_email_orden_compra(orden)
                
                if resultado['success']:
                    orden.marcar_como_enviada()
                    
                    LogOrdenCompraIA.objects.create(
                        orden=orden,
                        usuario=request.user,
                        accion='enviada',
                        detalle=f'Email enviado a: {resultado["emails"]}'
                    )
                    
                    messages.success(request, f'✅ Orden enviada por email a proveedor(es)')
                else:
                    messages.error(request, f'❌ Error al enviar email: {resultado["error"]}')
            else:
                messages.warning(request, '⚠️ La orden debe estar aprobada para enviarla')
        
        return redirect('detalle_orden_compra', orden_id=orden.id)
    
    # Agrupar items por proveedor
    items_por_proveedor = {}
    for item in orden.items.select_related('producto', 'proveedor').all():
        proveedor_nombre = item.proveedor.nombre if item.proveedor else 'Sin Proveedor'
        if proveedor_nombre not in items_por_proveedor:
            items_por_proveedor[proveedor_nombre] = {
                'proveedor': item.proveedor,
                'items': [],
                'total': 0
            }
        items_por_proveedor[proveedor_nombre]['items'].append(item)
        items_por_proveedor[proveedor_nombre]['total'] += float(item.subtotal)
    
    context = {
        'orden': orden,
        'items_por_proveedor': items_por_proveedor,
        'logs': orden.logs.all()[:10],
        'puede_editar': orden.estado in ['borrador', 'revision'],
        'puede_aprobar': orden.estado == 'borrador',
        'puede_enviar': orden.estado in ['borrador', 'aprobada'] and not orden.email_enviado,
    }
    
    return render(request, 'sitio1/DataModelApp/IA/detalle_orden_compra.html', context)


@login_required
def lista_ordenes_compra(request):
    """
    Lista todas las órdenes de compra generadas
    """
    ordenes = OrdenCompraIA.objects.all()

    # Filtros
    estado = request.GET.get('estado')
    if estado:
        ordenes = ordenes.filter(estado=estado)

    # Conteos por estado (ya sin filtros en el template)
    count_borrador = ordenes.filter(estado='borrador').count()
    count_aprobada = ordenes.filter(estado='aprobada').count()
    count_enviada = ordenes.filter(estado='enviada').count()

    context = {
        'ordenes': ordenes,
        'estados': OrdenCompraIA.ESTADO_CHOICES,

        # Conteos
        'count_borrador': count_borrador,
        'count_aprobada': count_aprobada,
        'count_enviada': count_enviada,
    }
    
    return render(request, 'sitio1/DataModelApp/IA/lista_ordenes_compra.html', context)



def enviar_email_orden_compra(orden):
    """
    Envía email profesional al proveedor con la orden de compra
    """
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.conf import settings
    
    try:
        # Agrupar por proveedor
        items_por_proveedor = {}
        for item in orden.items.select_related('producto', 'proveedor').all():
            proveedor = item.proveedor
            # Nota: El campo de email en tu modelo se llama 'correo'
            if not proveedor or not proveedor.correo:
                continue
                
            if proveedor.correo not in items_por_proveedor:
                items_por_proveedor[proveedor.correo] = {
                    'proveedor': proveedor,
                    'items': []
                }
            items_por_proveedor[proveedor.correo]['items'].append(item)
        
        if not items_por_proveedor:
            return {
                'success': False,
                'error': 'No hay proveedores con email configurado'
            }
        
        emails_enviados = []
        
        # Enviar email a cada proveedor
        for email_proveedor, datos in items_por_proveedor.items():
            proveedor = datos['proveedor']
            items = datos['items']
            
            # Contexto para template
            context = {
                'orden': orden,
                'proveedor': proveedor,
                'items': items,
                'total': sum(item.subtotal for item in items),
                'total_unidades': sum(item.cantidad_solicitada for item in items),
            }
            
            # Renderizar HTML
            html_content = render_to_string('sitio1/DataModelApp/IA/email_orden_compra.html', context)
            text_content = render_to_string('sitio1/DataModelApp/IA/email_orden_compra.txt', context)
            
            # Crear email
            subject = f'Orden de Compra {orden.numero_orden} - {orden.creado_por.get_full_name() if orden.creado_por.get_full_name() else orden.creado_por.username}'
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email_proveedor],
                reply_to=[orden.creado_por.email] if orden.creado_por.email else []
            )
            email.attach_alternative(html_content, "text/html")
            email.send()
            
            emails_enviados.append(email_proveedor)
        
        return {
            'success': True,
            'emails': ', '.join(emails_enviados)
        }
        
    except Exception as e:
        logger.error(f"Error enviando email: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    
# ==========================================
# INVENTARIO FÍSICO
# ==========================================

@login_required
def inventario_fisico_inicio(request):
    """Pantalla inicial para seleccionar ubicación"""
    ubicaciones = Ubicacion.objects.all()
    
    context = {
        'ubicaciones': ubicaciones
    }
    return render(request, 'sitio1/DataModelApp/Inventario/inventario_fisico_inicio.html', context)


@login_required
def inventario_fisico_conteo(request, ubicacion_id):
    """Pantalla de conteo de productos"""
    ubicacion = get_object_or_404(Ubicacion, id=ubicacion_id)
    
    productos = Productos.objects.filter(
        ubicacion=ubicacion,
        activo=True
    ).select_related('categoria', 'ubicacion')
    
    context = {
        'ubicacion': ubicacion,
        'productos': productos
    }
    return render(request, 'sitio1/DataModelApp/Inventario/inventario_fisico_conteo.html', context)


@login_required
def inventario_fisico_conteo(request, ubicacion_id):
    """Pantalla de conteo de productos"""
    ubicacion = get_object_or_404(Ubicacion, id=ubicacion_id)
    
    productos = Productos.objects.filter(
        ubicacion=ubicacion,
        activo=True
    ).select_related('categoria', 'ubicacion')
    
    context = {
        'ubicacion': ubicacion,
        'productos': productos
    }
    return render(request, 'sitio1/DataModelApp/Inventario/inventario_fisico_conteo.html', context)


@login_required
@transaction.atomic
def inventario_fisico_guardar(request):
    """Guarda el ajuste de inventario"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        ubicacion_id = data.get('ubicacion_id')
        motivo = data.get('motivo')
        productos_contados = data.get('productos', [])
        
        # Validaciones
        if not motivo or not motivo.strip():
            return JsonResponse({'error': 'El motivo es requerido'}, status=400)
        
        if not productos_contados:
            return JsonResponse({'error': 'Debes contar al menos un producto'}, status=400)
        
        ubicacion = get_object_or_404(Ubicacion, id=ubicacion_id)
        
        # Crear el ajuste
        ajuste = AjusteInventario.objects.create(
            ubicacion=ubicacion,
            usuario=request.user,
            motivo=motivo,
            finalizado=False
        )
        
        # Crear detalles del ajuste
        productos_con_diferencias = 0
        for item in productos_contados:
            producto = get_object_or_404(Productos, id=item['producto_id'])
            stock_fisico = int(item['stock_fisico'])
            
            detalle = DetalleAjusteInventario.objects.create(
                ajuste=ajuste,
                producto=producto,
                stock_sistema=producto.stock_actual,
                stock_fisico=stock_fisico,
                ubicacion_especifica=item.get('ubicacion_especifica', '')
            )
            
            if detalle.diferencia != 0:
                productos_con_diferencias += 1
        
        # Actualizar estadísticas
        ajuste.productos_revisados = len(productos_contados)
        ajuste.productos_con_diferencias = productos_con_diferencias
        ajuste.save()
        
        return JsonResponse({
            'success': True,
            'ajuste_id': ajuste.id,
            'mensaje': 'Ajuste guardado exitosamente'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@transaction.atomic
def inventario_fisico_confirmar(request, ajuste_id):
    """Confirma y aplica el ajuste al stock"""
    ajuste = get_object_or_404(AjusteInventario, id=ajuste_id)
    
    if ajuste.finalizado:
        messages.warning(request, 'Este ajuste ya fue finalizado')
        return redirect('historial_ajustes')
    
    # Marcar como finalizado
    ajuste.finalizado = True
    ajuste.save()
    
    # Aplicar cambios a cada producto
    for detalle in ajuste.detalles.all():
        if detalle.diferencia != 0:
            # Crear movimiento
            MovimientoInventario.objects.create(
                producto=detalle.producto,
                tipo_movimiento='ajuste',
                cantidad=abs(detalle.diferencia),
                usuario=request.user,
                motivo=f"Ajuste inventario físico #{ajuste.id}: {ajuste.motivo}"
            )
            
            # IMPORTANTE: Actualizar el stock del producto
            detalle.producto.stock_actual = detalle.stock_fisico
            detalle.producto.save()
    
    messages.success(request, f'Ajuste de inventario #{ajuste.id} aplicado exitosamente')
    return redirect('detalle_ajuste', ajuste_id=ajuste.id)


# ==========================================
# HISTORIAL DE AJUSTES
# ==========================================

@login_required
def historial_ajustes(request):
    """Lista todos los ajustes de inventario"""
    fecha_filtro = request.GET.get('fecha', 'todos')
    ubicacion_id = request.GET.get('ubicacion', 'todas')
    
    ajustes = AjusteInventario.objects.select_related(
        'ubicacion', 'usuario'
    ).order_by('-fecha_hora')
    
    # Filtros
    if ubicacion_id != 'todas':
        ajustes = ajustes.filter(ubicacion_id=ubicacion_id)
    
    if fecha_filtro == 'hoy':
        ajustes = ajustes.filter(fecha_hora__date=datetime.now().date())
    elif fecha_filtro == 'semana':
        hace_7_dias = datetime.now() - timedelta(days=7)
        ajustes = ajustes.filter(fecha_hora__gte=hace_7_dias)
    elif fecha_filtro == 'mes':
        hace_30_dias = datetime.now() - timedelta(days=30)
        ajustes = ajustes.filter(fecha_hora__gte=hace_30_dias)
    
    # Estadísticas
    total_ajustes = ajustes.count()
    total_productos = sum(a.productos_revisados for a in ajustes)
    total_diferencias = sum(a.productos_con_diferencias for a in ajustes)
    
    ubicaciones = Ubicacion.objects.all()
    
    context = {
        'ajustes': ajustes,
        'ubicaciones': ubicaciones,
        'total_ajustes': total_ajustes,
        'total_productos': total_productos,
        'total_diferencias': total_diferencias,
        'fecha_filtro': fecha_filtro,
        'ubicacion_filtro': ubicacion_id,
    }
    return render(request, 'sitio1/DataModelApp/Inventario/historial_ajustes.html', context)


@login_required
def detalle_ajuste(request, ajuste_id):
    """Muestra el detalle completo de un ajuste"""
    ajuste = get_object_or_404(
        AjusteInventario.objects.select_related('ubicacion', 'usuario'),
        id=ajuste_id
    )
    
    detalles = ajuste.detalles.select_related('producto').all()
    
    context = {
        'ajuste': ajuste,
        'detalles': detalles
    }
    return render(request, 'sitio1/DataModelApp/Inventario/detalle_ajuste.html', context)

# ==========================================
# Modulo de Auditoría
# ==========================================
@login_required
def auditoria_logs(request):
    """Vista principal de auditoría"""
    # Obtener todos los logs
    logs = LogAuditoria.objects.select_related('usuario').all()
    
    # Aplicar filtros
    tabla = request.GET.get('tabla')
    if tabla:
        logs = logs.filter(tabla=tabla)
    
    tipo_accion = request.GET.get('tipo')
    if tipo_accion:
        logs = logs.filter(tipo_accion=tipo_accion)
    
    usuario = request.GET.get('usuario')
    if usuario:
        logs = logs.filter(usuario__username=usuario)
    
    fecha = request.GET.get('fecha')
    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            logs = logs.filter(fecha_hora__date=fecha_obj)
        except ValueError:
            pass
    
    ip_address = request.GET.get('ip')
    if ip_address:
        logs = logs.filter(ip_address=ip_address)
    
    # Estadísticas
    total_logs = logs.count()
    total_create = logs.filter(tipo_accion='create').count()
    total_update = logs.filter(tipo_accion='update').count()
    total_delete = logs.filter(tipo_accion='delete').count()
    
    # Obtener lista de usuarios para el filtro
    usuarios = User.objects.all().order_by('username')
    
    # Paginación
    paginator = Paginator(logs, 50)  # 50 logs por página
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'logs': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'usuarios': usuarios,
        'total_logs': total_logs,
        'total_create': total_create,
        'total_update': total_update,
        'total_delete': total_delete,
    }
    
    return render(request, 'sitio1/DataModelApp/Logs/logs.html', context)


@login_required
def auditoria_detalle(request, log_id):
    """Detalle de un log específico (devuelve HTML para modal)"""
    log = get_object_or_404(LogAuditoria, id=log_id)
    
    # Convertir JSON a diccionarios si existen
    valores_anterior = log.valores_anterior or {}
    valores_nuevo = log.valores_nuevo or {}
    
    # Manejar usuario None
    if log.usuario:
        nombre_usuario = log.usuario.get_full_name() or log.usuario.username
    else:
        nombre_usuario = "Sistema / Usuario no disponible"
    
    html = f"""
    <div class="detail-item">
        <div class="detail-label">Tabla</div>
        <div class="detail-value">{log.get_nombre_tabla()}</div>
    </div>
    
    <div class="detail-item">
        <div class="detail-label">Tipo de Acción</div>
        <div class="detail-value">{log.get_tipo_accion_display()}</div>
    </div>
    
    <div class="detail-item">
        <div class="detail-label">ID del Registro</div>
        <div class="detail-value">#{log.id_registro}</div>
    </div>
    
    <div class="detail-item">
        <div class="detail-label">Usuario</div>
        <div class="detail-value">{nombre_usuario}</div>
    </div>
    
    <div class="detail-item">
        <div class="detail-label">Descripción</div>
        <div class="detail-value">{log.descripcion}</div>
    </div>
    
    <div class="detail-item">
        <div class="detail-label">Fecha y Hora</div>
        <div class="detail-value">{log.fecha_hora.strftime('%d/%m/%Y %H:%M:%S')}</div>
    </div>
    
    <div class="detail-item">
        <div class="detail-label">IP Address</div>
        <div class="detail-value">{log.ip_address or 'N/A'}</div>
    </div>
    """
    
    if log.tipo_accion == 'update' and (valores_anterior or valores_nuevo):
        html += """
        <div class="detail-item">
            <div class="detail-label">Cambios Realizados</div>
        """
        
        todas_las_claves = set(valores_anterior.keys()) | set(valores_nuevo.keys())
        for clave in sorted(todas_las_claves):
            anterior = valores_anterior.get(clave, 'N/A')
            nuevo = valores_nuevo.get(clave, 'N/A')
            
            if anterior != nuevo:
                html += f"""
                <div style="margin: 1rem 0; padding: 1rem; background: #F9FAFB; border-radius: 8px;">
                    <div style="font-weight: 600; margin-bottom: 0.5rem; text-transform: capitalize;">
                        {clave.replace('_', ' ')}
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr auto 1fr; gap: 1rem; align-items: center;">
                        <div style="background: #FEE2E2; padding: 0.5rem; border-radius: 6px; border-left: 3px solid #DC2626;">
                            <small style="color: #7F1D1D;">Antes:</small><br>
                            <code style="color: #1F2937;">{anterior}</code>
                        </div>
                        <div style="text-align: center; color: #F59E0B; font-weight: 700;">→</div>
                        <div style="background: #D1FAE5; padding: 0.5rem; border-radius: 6px; border-left: 3px solid #10B981;">
                            <small style="color: #065F46;">Después:</small><br>
                            <code style="color: #1F2937;">{nuevo}</code>
                        </div>
                    </div>
                </div>
                """
        
        html += "</div>"
    
    # 👇 AQUÍ EL CAMBIO: devolvemos directamente el HTML
    return HttpResponse(html)

# ==========================================
# HISTORIAL DE MOVIMIENTOS
# ==========================================

@login_required
def historial_movimientos(request):
    """Muestra todo el historial de movimientos de stock"""
    # Filtros
    tipo_filtro = request.GET.get('tipo', 'todos')
    fecha_filtro = request.GET.get('fecha', 'todos')
    producto_buscar = request.GET.get('producto', '')
    
    # Query base
    movimientos = MovimientoInventario.objects.select_related(
        'producto', 'usuario'
    ).order_by('-fecha_hora')
    
    # Aplicar filtro de tipo
    if tipo_filtro != 'todos':
        movimientos = movimientos.filter(tipo_movimiento=tipo_filtro)
    
    # Aplicar filtro de fecha
    if fecha_filtro == 'hoy':
        movimientos = movimientos.filter(fecha_hora__date=datetime.now().date())
    elif fecha_filtro == 'semana':
        hace_7_dias = datetime.now() - timedelta(days=7)
        movimientos = movimientos.filter(fecha_hora__gte=hace_7_dias)
    elif fecha_filtro == 'mes':
        hace_30_dias = datetime.now() - timedelta(days=30)
        movimientos = movimientos.filter(fecha_hora__gte=hace_30_dias)
    
    # Aplicar filtro de producto
    if producto_buscar:
        movimientos = movimientos.filter(
            producto__nombre__icontains=producto_buscar
        ) | movimientos.filter(
            producto__sku__icontains=producto_buscar
        )
    
    # Estadísticas
    total_entradas = movimientos.filter(tipo_movimiento='entrada').aggregate(
        total=models.Sum('cantidad')
    )['total'] or 0
    
    total_salidas = movimientos.filter(tipo_movimiento='salida').aggregate(
        total=models.Sum('cantidad')
    )['total'] or 0
    
    total_ajustes = movimientos.filter(tipo_movimiento='ajuste').count()
    
    context = {
        'movimientos': movimientos[:100],  # Limitar a 100 registros
        'total_entradas': total_entradas,
        'total_salidas': total_salidas,
        'total_ajustes': total_ajustes,
        'tipo_filtro': tipo_filtro,
        'fecha_filtro': fecha_filtro,
        'producto_buscar': producto_buscar,
    }
    return render(request, 'sitio1/DataModelApp/Inventario/historial_movimientos.html', context)