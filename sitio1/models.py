from django.db import models
from django.contrib.auth.models import AbstractUser, AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import FileExtensionValidator
from django.contrib.auth.models import Permission
from django.db.models import JSONField
import json

class Rol(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=200, blank=True, null=True)

    # Permisos del sistema (Django ya trae CRUD por modelo)
    permisos = models.ManyToManyField(Permission, blank=True)

    def __str__(self):
        return self.nombre

    

class Usuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    nombre_completo = models.CharField(max_length=150, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    imagen = models.ImageField(upload_to='usuarios/', blank=True, null=True)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT)
    estado = models.BooleanField(default=True)
    fecha_ingreso = models.DateField(auto_now_add=True)
    ultima_conexion = models.DateTimeField(blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.user.username if self.user else "Usuario sin cuenta"

    
    def save(self, *args, **kwargs):
        if self.user and self.email:
            self.user.email = self.email
            self.user.save()
        super().save(*args, **kwargs)



# =====================
# MODELOS PRINCIPALES
# =====================

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.nombre


class Ubicacion(models.Model):
    direccion = models.CharField(max_length=100, blank=True, null=True)
    comuna = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.direccion or 'Sin dirección'} - {self.comuna or 'Sin comuna'} - {self.region or 'Sin región'}"


class Proveedor(models.Model):
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=50, blank=True, null=True)
    correo = models.EmailField(max_length=100, blank=True, null=True)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.nombre


class Productos(models.Model):
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    nombre = models.CharField(max_length=150)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock_actual = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=0, blank=True, null=True)
    stock_maximo = models.IntegerField(default=0, blank=True, null=True)
    unidad_medida = models.CharField(max_length=50, default='unidad')
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.SET_NULL, null=True, blank=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True)
    activo = models.BooleanField(default=True)
    
    

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['-activo', 'nombre']

    def __str__(self):
        return self.nombre
    
    @property
    def stock_bajo(self):
        """Verifica si el stock está bajo"""
        if self.stock_minimo:
            return self.stock_actual <= self.stock_minimo
        return False
    
    @property
    def margen_ganancia(self):
        """Calcula el margen de ganancia"""
        if self.costo_unitario and self.costo_unitario > 0:
            return ((self.precio_unitario - self.costo_unitario) / self.costo_unitario) * 100
        return 0
    
    @property
    def valor_inventario(self):
        """Valor total del inventario de este producto"""
        return self.precio_unitario * self.stock_actual

# =====================
# MOVIMIENTOS Y VENTAS
# =====================

class MovimientoInventario(models.Model):
    TIPOS = [
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
        ('ajuste', 'Ajuste'),
        ('venta_forzada', 'Venta forzada'),
    ]

    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    tipo_movimiento = models.CharField(max_length=50, choices=TIPOS)
    cantidad = models.IntegerField()
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    motivo = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.tipo_movimiento} - {self.producto.nombre} ({self.cantidad})"


class Venta(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    medio_pago = models.CharField(max_length=50)
    estado = models.CharField(max_length=50, default='pendiente')

    def __str__(self):
        return f"Venta {self.id} - {self.fecha.date()}"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Productos, on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    precio_unidad = models.DecimalField(max_digits=10, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.producto.nombre} x {self.cantidad}"


class OrdenCompra(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('aprobada', 'Aprobada'),
        ('rechazada', 'Rechazada'),
        ('recibida', 'Recibida'),
    ]

    producto = models.ForeignKey(Productos, on_delete=models.PROTECT)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=50, choices=ESTADOS, default='pendiente')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Orden #{self.id} - {self.proveedor.nombre}"


# =====================
# ALERTAS Y CAMBIOS DE PRECIO
# =====================

class Alerta(models.Model):
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=100)  # ej: Bajo stock, Demanda alta
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    recomendacion = models.CharField(max_length=255, blank=True, null=True)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tipo} - {self.producto.nombre}"


class CambioPrecio(models.Model):
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    precio_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    nuevo_precio = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.producto.nombre}: {self.precio_anterior} → {self.nuevo_precio}"


# =====================
# TABLAS PARA ANALISIS Y PREDICCION
# =====================

class HistorialInventario(models.Model):
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    fecha = models.DateField(default=timezone.now)
    stock = models.IntegerField()
    ventas_dia = models.IntegerField(default=0)     # unidades vendidas
    entradas_dia = models.IntegerField(default=0)   # unidades ingresadas (compras, ajustes positivos)

    class Meta:
        unique_together = ('producto', 'fecha')

    def __str__(self):
        return f"{self.producto.nombre} - {self.fecha}"


class RegistroAnalisis(models.Model):
    fecha = models.DateTimeField(default=timezone.now)
    tipo_analisis = models.CharField(max_length=100)  # 'prediccion_demanda', 'precio_optimo', etc.
    parametros = models.JSONField(blank=True, null=True)
    resultado = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.tipo_analisis} - {self.fecha}"


class Permiso(models.Model):
    pass

class ActividadUsuario(models.Model):
    TIPOS_ACTIVIDAD = [
        ('login', 'Inicio de sesión'),
        ('logout', 'Cierre de sesión'),
        ('editar_perfil', 'Actualización de perfil'),
        ('cambio_password', 'Cambio de contraseña'),
        ('crear_producto', 'Creación de producto'),
        ('editar_producto', 'Edición de producto'),
        ('eliminar_producto', 'Eliminación de producto'),
        ('crear_venta', 'Nueva venta'),
    ]
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='actividades')
    tipo_actividad = models.CharField(max_length=50, choices=TIPOS_ACTIVIDAD)
    descripcion = models.CharField(max_length=255)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detalles = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = "Actividad de Usuario"
        verbose_name_plural = "Actividades de Usuarios"
    
    def __str__(self):
        return f"{self.usuario.username} - {self.get_tipo_actividad_display()} - {self.fecha_hora}"
    
class OrdenCompraIA(models.Model):
    """
    Orden de compra generada automáticamente por IA
    """
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('revision', 'En Revisión'),
        ('aprobada', 'Aprobada'),
        ('enviada', 'Enviada'),
        ('recibida_parcial', 'Recibida Parcial'),
        ('recibida_completa', 'Recibida Completa'),
        ('cancelada', 'Cancelada'),
    ]
    
    numero_orden = models.CharField(max_length=50, unique=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    fecha_envio = models.DateTimeField(null=True, blank=True)
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    
    # Usuario que genera/aprueba
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='ordenes_creadas')
    aprobado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ordenes_aprobadas')
    
    # Observaciones
    observaciones_ia = models.TextField(blank=True, help_text="Análisis automático de la IA")
    observaciones_usuario = models.TextField(blank=True, help_text="Notas del usuario")
    
    # Totales
    total_productos = models.IntegerField(default=0)
    total_unidades = models.IntegerField(default=0)
    total_estimado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Email
    email_enviado = models.BooleanField(default=False)
    email_enviado_fecha = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = "Orden de Compra IA"
        verbose_name_plural = "Órdenes de Compra IA"
        
    def __str__(self):
        return f"Orden {self.numero_orden} - {self.get_estado_display()}"
    
    def generar_numero_orden(self):
        """Genera número de orden único: OC-YYYYMMDD-XXXX"""
        from datetime import datetime
        fecha = datetime.now().strftime('%Y%m%d')
        ultimo = OrdenCompraIA.objects.filter(
            numero_orden__startswith=f'OC-{fecha}'
        ).count()
        return f'OC-{fecha}-{str(ultimo + 1).zfill(4)}'
    
    def calcular_totales(self):
        """Recalcula totales basado en items"""
        items = self.items.all()
        self.total_productos = items.count()
        self.total_unidades = sum(item.cantidad_solicitada for item in items)
        self.total_estimado = sum(item.subtotal for item in items)
        self.save()
    
    def aprobar(self, usuario):
        """Aprueba la orden"""
        self.estado = 'aprobada'
        self.aprobado_por = usuario
        self.fecha_aprobacion = timezone.now()
        self.save()
    
    def marcar_como_enviada(self):
        """Marca orden como enviada al proveedor"""
        self.estado = 'enviada'
        self.fecha_envio = timezone.now()
        self.email_enviado = True
        self.email_enviado_fecha = timezone.now()
        self.save()


class ItemOrdenCompraIA(models.Model):
    """
    Item individual de una orden de compra IA
    """
    orden = models.ForeignKey(OrdenCompraIA, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey('Productos', on_delete=models.CASCADE)
    proveedor = models.ForeignKey('Proveedor', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Datos de la predicción IA
    stock_actual = models.IntegerField(help_text="Stock al momento de generar orden")
    demanda_estimada_14d = models.IntegerField(help_text="Demanda estimada 14 días")
    dias_hasta_agotamiento = models.IntegerField(help_text="Días estimados hasta agotamiento")
    nivel_criticidad = models.CharField(max_length=20, help_text="crítico, alto, medio, bajo")
    
    # Cantidades
    cantidad_sugerida_ia = models.IntegerField(help_text="Cantidad sugerida por IA")
    cantidad_solicitada = models.IntegerField(help_text="Cantidad final solicitada (editable)")
    
    # Precios
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Recepción
    cantidad_recibida = models.IntegerField(default=0)
    fecha_recepcion = models.DateTimeField(null=True, blank=True)
    observaciones_recepcion = models.TextField(blank=True)
    
    class Meta:
        ordering = ['nivel_criticidad', '-demanda_estimada_14d']
        verbose_name = "Item Orden Compra"
        verbose_name_plural = "Items Orden Compra"
    
    def __str__(self):
        return f"{self.producto.nombre} - {self.cantidad_solicitada} unidades"
    
    def save(self, *args, **kwargs):
        # Calcular subtotal
        self.subtotal = self.cantidad_solicitada * self.precio_unitario
        super().save(*args, **kwargs)
        # Recalcular totales de la orden
        self.orden.calcular_totales()
    
    @property
    def diferencia_recepcion(self):
        """Diferencia entre solicitado y recibido"""
        return self.cantidad_solicitada - self.cantidad_recibida
    
    @property
    def porcentaje_recibido(self):
        """% recibido vs solicitado"""
        if self.cantidad_solicitada == 0:
            return 0
        return (self.cantidad_recibida / self.cantidad_solicitada) * 100


class LogOrdenCompraIA(models.Model):
    """
    Registro de cambios y acciones sobre órdenes de compra
    """
    orden = models.ForeignKey(OrdenCompraIA, on_delete=models.CASCADE, related_name='logs')
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    accion = models.CharField(max_length=50)  # 'creada', 'editada', 'aprobada', 'enviada', etc
    detalle = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-fecha']
        verbose_name = "Log Orden Compra"
        verbose_name_plural = "Logs Órdenes Compra"
    
    def __str__(self):
        return f"{self.orden.numero_orden} - {self.accion} - {self.fecha}"
    
class AjusteInventario(models.Model):
    """
    Registro de ajustes de inventario físico
    """
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.PROTECT)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField(help_text="Razón del ajuste de inventario")
    
    # Estadísticas del ajuste
    productos_revisados = models.IntegerField(default=0)
    productos_con_diferencias = models.IntegerField(default=0)
    
    # Estado
    finalizado = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = "Ajuste de Inventario"
        verbose_name_plural = "Ajustes de Inventario"
    
    def __str__(self):
        return f"Ajuste #{self.id} - {self.ubicacion.direccion} - {self.fecha_hora.strftime('%d/%m/%Y')}"
    
    def calcular_estadisticas(self):
        """Recalcula las estadísticas del ajuste"""
        detalles = self.detalles.all()
        self.productos_revisados = detalles.count()
        self.productos_con_diferencias = detalles.filter(
            diferencia__gt=0
        ).count() + detalles.filter(diferencia__lt=0).count()
        self.save()


class DetalleAjusteInventario(models.Model):
    """
    Detalle de cada producto ajustado en el inventario
    """
    ajuste = models.ForeignKey(AjusteInventario, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    
    # Stocks
    stock_sistema = models.IntegerField(help_text="Stock en el sistema antes del ajuste")
    stock_fisico = models.IntegerField(help_text="Stock contado físicamente")
    diferencia = models.IntegerField(help_text="Diferencia (físico - sistema)")
    
    # Ubicación específica dentro del almacén
    ubicacion_especifica = models.CharField(max_length=100, blank=True, null=True, 
                                           help_text="Ej: A1-B2")
    
    class Meta:
        ordering = ['producto__nombre']
        verbose_name = "Detalle Ajuste Inventario"
        verbose_name_plural = "Detalles Ajuste Inventario"
    
    def __str__(self):
        return f"{self.producto.nombre} - Dif: {self.diferencia}"
    
    def save(self, *args, **kwargs):
        # Calcular diferencia automáticamente
        self.diferencia = self.stock_fisico - self.stock_sistema
        
        # Guardar el detalle
        super().save(*args, **kwargs)
        
        # Si la diferencia no es 0, crear movimiento y actualizar stock
        if self.diferencia != 0 and self.ajuste.finalizado:
            # Crear movimiento de inventario
            MovimientoInventario.objects.create(
                producto=self.producto,
                tipo_movimiento='ajuste',
                cantidad=abs(self.diferencia),
                usuario=self.ajuste.usuario,
                motivo=f"Ajuste inventario físico #{self.ajuste.id}: {self.ajuste.motivo}"
            )
            
            # Actualizar stock del producto
            self.producto.stock_actual = self.stock_fisico
            self.producto.save()
        
        # Recalcular estadísticas del ajuste
        self.ajuste.calcular_estadisticas()

class LogAuditoria(models.Model):
    """
    Registro de auditoría para todas las acciones del sistema
    """
    TIPOS_ACCION = [
        ('create', 'Creación'),
        ('update', 'Modificación'),
        ('delete', 'Eliminación'),
        ('view', 'Visualización'),
    ]

    TABLAS = [
        ('productos', 'Productos'),
        ('categorias', 'Categorías'),
        ('usuarios', 'Usuarios'),
        ('roles', 'Roles'),
        ('ajustes', 'Ajustes de Inventario'),
        ('proveedores', 'Proveedores'),
        ('ubicaciones', 'Ubicaciones'),
        ('ventas', 'Ventas'),
    ]

    # Información de la acción
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    tabla = models.CharField(max_length=50, choices=TABLAS)
    tipo_accion = models.CharField(max_length=10, choices=TIPOS_ACCION)
    id_registro = models.IntegerField(help_text="ID del registro modificado")
    
    # Detalles
    descripcion = models.TextField(help_text="Descripción de la acción")
    valores_anterior = JSONField(blank=True, null=True, help_text="Valores antes del cambio")
    valores_nuevo = JSONField(blank=True, null=True, help_text="Valores después del cambio")
    
    # Información técnica
    fecha_hora = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['usuario', '-fecha_hora']),
            models.Index(fields=['tabla', '-fecha_hora']),
            models.Index(fields=['tipo_accion', '-fecha_hora']),
        ]
        verbose_name = "Log de Auditoría"
        verbose_name_plural = "Logs de Auditoría"
    
    def __str__(self):
        username = self.usuario.username if self.usuario else "Sistema / Usuario no disponible"
        return f"{username} - {self.get_tipo_accion_display()} - {self.tabla} #{self.id_registro}"
    
    def get_nombre_tabla(self):
        """Obtiene el nombre legible de la tabla"""
        return dict(self.TABLAS).get(self.tabla, self.tabla)
    
    @staticmethod
    def obtener_ip(request):
        """Obtiene la IP del cliente desde la request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def crear_log(usuario, tabla, tipo_accion, id_registro, descripcion, 
                  valores_anterior=None, valores_nuevo=None, request=None):
        """
        Método helper para crear logs fácilmente
        """
        log = LogAuditoria.objects.create(
            usuario=usuario,
            tabla=tabla,
            tipo_accion=tipo_accion,
            id_registro=id_registro,
            descripcion=descripcion,
            valores_anterior=valores_anterior,
            valores_nuevo=valores_nuevo,
            ip_address=LogAuditoria.obtener_ip(request) if request else None,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500] if request else None
        )
        return log
    
    def get_nombre_usuario(self):
        if self.usuario:
            return self.usuario.get_full_name() or self.usuario.username
        return "Sistema / Usuario no disponible"
    
    # =====================================================
# MODELOS PARA AJUSTES DE INVENTARIO FÍSICO
# =====================================================

class AjusteInventario(models.Model):
    """Registro de auditoría/conteo físico de inventario"""
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.PROTECT)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    motivo = models.CharField(max_length=255)
    finalizado = models.BooleanField(default=False)
    productos_revisados = models.IntegerField(default=0)
    productos_con_diferencias = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = "Ajuste de Inventario"
        verbose_name_plural = "Ajustes de Inventario"
    
    def __str__(self):
        return f"Ajuste #{self.id} - {self.ubicacion} - {self.fecha_hora.date()}"


class DetalleAjusteInventario(models.Model):
    """Detalle de cada producto en un ajuste"""
    ajuste = models.ForeignKey(AjusteInventario, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Productos, on_delete=models.PROTECT)
    stock_sistema = models.IntegerField()  # Stock que tenía el sistema
    stock_fisico = models.IntegerField()   # Stock contado físicamente
    ubicacion_especifica = models.CharField(max_length=100, blank=True, null=True)  # Ej: "Pasillo A-3"
    
    class Meta:
        unique_together = ('ajuste', 'producto')
    
    @property
    def diferencia(self):
        """Calcula la diferencia entre físico y sistema"""
        return self.stock_fisico - self.stock_sistema
    
    def __str__(self):
        return f"{self.producto.nombre} - Sistema: {self.stock_sistema} | Físico: {self.stock_fisico}"