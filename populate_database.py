"""
Script para poblar la base de datos con datos realistas
Ejecutar: python manage.py shell < populate_database.py
O copiar y pegar en: python manage.py shell
"""

from django.contrib.auth.models import User, Permission
from sitio1.models import (
    Rol, Proveedor, Categoria, Ubicacion, Productos, 
    Venta, DetalleVenta
)
from django.utils import timezone
from datetime import datetime, timedelta
import random
from decimal import Decimal

print("=" * 60)
print("INICIANDO POBLACIÓN DE BASE DE DATOS")
print("=" * 60)

# =====================================================
# 1. CREAR ROLES
# =====================================================
print("\n📋 Creando Roles...")

roles_data = [
    {
        'nombre': 'Administrador',
        'descripcion': 'Acceso total al sistema, gestión completa'
    },
    {
        'nombre': 'Ventas',
        'descripcion': 'Registro de ventas, consulta de productos e inventario'
    },
    {
        'nombre': 'Bodega',
        'descripcion': 'Gestión de inventario, ajustes, movimientos'
    },
    {
        'nombre': 'Data Analyst',
        'descripcion': 'Acceso a dashboards, reportes, análisis IA'
    },
]

roles_creados = {}
for rol_data in roles_data:
    rol, created = Rol.objects.get_or_create(
        nombre=rol_data['nombre'],
        defaults={'descripcion': rol_data['descripcion']}
    )
    roles_creados[rol.nombre] = rol
    if created:
        print(f"✅ Rol creado: {rol.nombre}")
    else:
        print(f"ℹ️  Rol existente: {rol.nombre}")

# =====================================================
# 2. CREAR PROVEEDORES
# =====================================================
print("\n🏭 Creando Proveedores...")

proveedores_data = [
    {
        'nombre': 'Distribuidora Global SPA',
        'telefono': '+56912345678',
        'correo': 'ventas@globaldist.cl',
        'direccion': 'Av. Libertador 1234, Santiago',
        'observaciones': 'Proveedor principal de productos de limpieza'
    },
    {
        'nombre': 'Importadora Wellness Ltda',
        'telefono': '+56987654321',
        'correo': 'contacto@wellness.cl',
        'direccion': 'Calle Nueva 567, Providencia',
        'observaciones': 'Especialistas en productos de spa y cosméticos'
    },
    {
        'nombre': 'Comercial Sur Chile',
        'telefono': '+56956781234',
        'correo': 'pedidos@surchile.cl',
        'direccion': 'Ruta 5 Sur Km 45, Rancagua',
        'observaciones': 'Proveedor secundario, buenos precios al por mayor'
    },
]

proveedores_creados = {}
for prov_data in proveedores_data:
    proveedor, created = Proveedor.objects.get_or_create(
        nombre=prov_data['nombre'],
        defaults=prov_data
    )
    proveedores_creados[proveedor.nombre] = proveedor
    if created:
        print(f"✅ Proveedor creado: {proveedor.nombre}")
    else:
        print(f"ℹ️  Proveedor existente: {proveedor.nombre}")

# =====================================================
# 3. CREAR CATEGORÍAS
# =====================================================
print("\n📦 Creando Categorías...")

categorias_data = [
    {'nombre': 'Productos de Limpieza', 'descripcion': 'Detergentes, desinfectantes, limpiadores'},
    {'nombre': 'Cosméticos', 'descripcion': 'Cremas, lociones, productos de belleza'},
    {'nombre': 'Aceites y Esencias', 'descripcion': 'Aceites esenciales, aromáticos'},
    {'nombre': 'Toallas y Textiles', 'descripcion': 'Toallas, sábanas, batas'},
    {'nombre': 'Equipamiento Spa', 'descripcion': 'Camillas, accesorios, equipos'},
    {'nombre': 'Consumibles', 'descripcion': 'Guantes, papel, consumibles varios'},
]

categorias_creadas = {}
for cat_data in categorias_data:
    categoria, created = Categoria.objects.get_or_create(
        nombre=cat_data['nombre'],
        defaults={'descripcion': cat_data['descripcion']}
    )
    categorias_creadas[categoria.nombre] = categoria
    if created:
        print(f"✅ Categoría creada: {categoria.nombre}")
    else:
        print(f"ℹ️  Categoría existente: {categoria.nombre}")

# =====================================================
# 4. CREAR UBICACIONES
# =====================================================
print("\n📍 Creando Ubicaciones...")

ubicaciones_data = [
    {
        'direccion': 'Bodega Principal',
        'comuna': 'Pirque',
        'region': 'Región Metropolitana',
        'descripcion': 'Almacén principal de productos'
    },
    {
        'direccion': 'Bodega Secundaria',
        'comuna': 'Pirque',
        'region': 'Región Metropolitana',
        'descripcion': 'Almacén de respaldo y productos de alta rotación'
    },
    {
        'direccion': 'Sala de Ventas',
        'comuna': 'Pirque',
        'region': 'Región Metropolitana',
        'descripcion': 'Exhibición y venta directa'
    },
]

ubicaciones_creadas = {}
for ub_data in ubicaciones_data:
    ubicacion, created = Ubicacion.objects.get_or_create(
        direccion=ub_data['direccion'],
        defaults=ub_data
    )
    ubicaciones_creadas[ubicacion.direccion] = ubicacion
    if created:
        print(f"✅ Ubicación creada: {ubicacion.direccion}")
    else:
        print(f"ℹ️  Ubicación existente: {ubicacion.direccion}")

# =====================================================
# 5. CREAR PRODUCTOS
# =====================================================
print("\n🛍️  Creando Productos...")

productos_data = [
    # Productos de Limpieza - Alta rotación
    {'sku': 'LIM-001', 'nombre': 'Desinfectante Multiuso 1L', 'categoria': 'Productos de Limpieza', 'precio': 3500, 'costo': 2000, 'stock': 45, 'stock_min': 20, 'ubicacion': 'Bodega Principal', 'proveedor': 'Distribuidora Global SPA'},
    {'sku': 'LIM-002', 'nombre': 'Detergente Líquido 5L', 'categoria': 'Productos de Limpieza', 'precio': 8900, 'costo': 5500, 'stock': 30, 'stock_min': 15, 'ubicacion': 'Bodega Principal', 'proveedor': 'Distribuidora Global SPA'},
    {'sku': 'LIM-003', 'nombre': 'Cloro Gel 1L', 'categoria': 'Productos de Limpieza', 'precio': 2500, 'costo': 1500, 'stock': 60, 'stock_min': 25, 'ubicacion': 'Bodega Principal', 'proveedor': 'Distribuidora Global SPA'},
    {'sku': 'LIM-004', 'nombre': 'Limpia Vidrios 500ml', 'categoria': 'Productos de Limpieza', 'precio': 2800, 'costo': 1600, 'stock': 25, 'stock_min': 10, 'ubicacion': 'Bodega Secundaria', 'proveedor': 'Comercial Sur Chile'},
    {'sku': 'LIM-005', 'nombre': 'Ambientador Spray 400ml', 'categoria': 'Productos de Limpieza', 'precio': 3200, 'costo': 1800, 'stock': 40, 'stock_min': 15, 'ubicacion': 'Sala de Ventas', 'proveedor': 'Distribuidora Global SPA'},
    
    # Cosméticos - Rotación media
    {'sku': 'COS-001', 'nombre': 'Crema Hidratante Facial 50ml', 'categoria': 'Cosméticos', 'precio': 12500, 'costo': 7000, 'stock': 35, 'stock_min': 12, 'ubicacion': 'Sala de Ventas', 'proveedor': 'Importadora Wellness Ltda'},
    {'sku': 'COS-002', 'nombre': 'Loción Corporal 250ml', 'categoria': 'Cosméticos', 'precio': 8900, 'costo': 5200, 'stock': 28, 'stock_min': 10, 'ubicacion': 'Sala de Ventas', 'proveedor': 'Importadora Wellness Ltda'},
    {'sku': 'COS-003', 'nombre': 'Exfoliante Facial 100ml', 'categoria': 'Cosméticos', 'precio': 9500, 'costo': 5500, 'stock': 22, 'stock_min': 8, 'ubicacion': 'Bodega Secundaria', 'proveedor': 'Importadora Wellness Ltda'},
    {'sku': 'COS-004', 'nombre': 'Mascarilla Hidratante Pack 5u', 'categoria': 'Cosméticos', 'precio': 6500, 'costo': 3500, 'stock': 50, 'stock_min': 20, 'ubicacion': 'Sala de Ventas', 'proveedor': 'Importadora Wellness Ltda'},
    {'sku': 'COS-005', 'nombre': 'Serum Facial 30ml', 'categoria': 'Cosméticos', 'precio': 15900, 'costo': 9000, 'stock': 18, 'stock_min': 6, 'ubicacion': 'Sala de Ventas', 'proveedor': 'Importadora Wellness Ltda'},
    
    # Aceites y Esencias - Rotación media-baja
    {'sku': 'ACE-001', 'nombre': 'Aceite Esencial Lavanda 15ml', 'categoria': 'Aceites y Esencias', 'precio': 7500, 'costo': 4200, 'stock': 30, 'stock_min': 10, 'ubicacion': 'Bodega Secundaria', 'proveedor': 'Importadora Wellness Ltda'},
    {'sku': 'ACE-002', 'nombre': 'Aceite Esencial Eucalipto 15ml', 'categoria': 'Aceites y Esencias', 'precio': 6900, 'costo': 3800, 'stock': 25, 'stock_min': 8, 'ubicacion': 'Bodega Secundaria', 'proveedor': 'Importadora Wellness Ltda'},
    {'sku': 'ACE-003', 'nombre': 'Aceite de Masaje Relajante 500ml', 'categoria': 'Aceites y Esencias', 'precio': 12000, 'costo': 7500, 'stock': 20, 'stock_min': 7, 'ubicacion': 'Bodega Principal', 'proveedor': 'Importadora Wellness Ltda'},
    {'sku': 'ACE-004', 'nombre': 'Velas Aromáticas Pack 3u', 'categoria': 'Aceites y Esencias', 'precio': 8500, 'costo': 5000, 'stock': 35, 'stock_min': 12, 'ubicacion': 'Sala de Ventas', 'proveedor': 'Comercial Sur Chile'},
    
    # Toallas y Textiles - Rotación baja
    {'sku': 'TEX-001', 'nombre': 'Toalla Facial Blanca 30x30cm', 'categoria': 'Toallas y Textiles', 'precio': 2500, 'costo': 1400, 'stock': 100, 'stock_min': 30, 'ubicacion': 'Bodega Principal', 'proveedor': 'Comercial Sur Chile'},
    {'sku': 'TEX-002', 'nombre': 'Toalla de Baño 70x140cm', 'categoria': 'Toallas y Textiles', 'precio': 9500, 'costo': 5800, 'stock': 45, 'stock_min': 15, 'ubicacion': 'Bodega Principal', 'proveedor': 'Comercial Sur Chile'},
    {'sku': 'TEX-003', 'nombre': 'Bata de Spa Talla M', 'categoria': 'Toallas y Textiles', 'precio': 15000, 'costo': 9500, 'stock': 12, 'stock_min': 5, 'ubicacion': 'Bodega Secundaria', 'proveedor': 'Comercial Sur Chile'},
    {'sku': 'TEX-004', 'nombre': 'Sábana Camilla Desechable Pack 10u', 'categoria': 'Toallas y Textiles', 'precio': 4500, 'costo': 2500, 'stock': 80, 'stock_min': 25, 'ubicacion': 'Bodega Principal', 'proveedor': 'Distribuidora Global SPA'},
    
    # Consumibles - Alta rotación
    {'sku': 'CON-001', 'nombre': 'Guantes Látex Caja 100u', 'categoria': 'Consumibles', 'precio': 8500, 'costo': 5000, 'stock': 55, 'stock_min': 20, 'ubicacion': 'Bodega Principal', 'proveedor': 'Distribuidora Global SPA'},
    {'sku': 'CON-002', 'nombre': 'Papel Higiénico Pack 12u', 'categoria': 'Consumibles', 'precio': 5500, 'costo': 3200, 'stock': 70, 'stock_min': 30, 'ubicacion': 'Bodega Principal', 'proveedor': 'Comercial Sur Chile'},
    {'sku': 'CON-003', 'nombre': 'Algodón en Rollo 500g', 'categoria': 'Consumibles', 'precio': 4200, 'costo': 2400, 'stock': 40, 'stock_min': 15, 'ubicacion': 'Bodega Secundaria', 'proveedor': 'Distribuidora Global SPA'},
    {'sku': 'CON-004', 'nombre': 'Papel Nova Rollo 80m', 'categoria': 'Consumibles', 'precio': 3500, 'costo': 2000, 'stock': 65, 'stock_min': 25, 'ubicacion': 'Bodega Principal', 'proveedor': 'Comercial Sur Chile'},
    {'sku': 'CON-005', 'nombre': 'Bolsas Basura 50L Pack 20u', 'categoria': 'Consumibles', 'precio': 3800, 'costo': 2200, 'stock': 50, 'stock_min': 20, 'ubicacion': 'Bodega Principal', 'proveedor': 'Comercial Sur Chile'},
]

productos_creados = []
for prod_data in productos_data:
    producto, created = Productos.objects.get_or_create(
        sku=prod_data['sku'],
        defaults={
            'nombre': prod_data['nombre'],
            'categoria': categorias_creadas[prod_data['categoria']],
            'precio_unitario': Decimal(str(prod_data['precio'])),
            'costo_unitario': Decimal(str(prod_data['costo'])),
            'stock_actual': prod_data['stock'],
            'stock_minimo': prod_data['stock_min'],
            'stock_maximo': prod_data['stock'] * 2,
            'ubicacion': ubicaciones_creadas[prod_data['ubicacion']],
            'proveedor': proveedores_creados[prod_data['proveedor']],
            'activo': True
        }
    )
    productos_creados.append(producto)
    if created:
        print(f"✅ Producto creado: {producto.sku} - {producto.nombre}")
    else:
        print(f"ℹ️  Producto existente: {producto.sku}")

# =====================================================
# 6. CREAR USUARIO DE PRUEBA PARA VENTAS
# =====================================================
print("\n👤 Creando usuario de ventas...")

user_ventas, created = User.objects.get_or_create(
    username='vendedor1',
    defaults={
        'first_name': 'Carlos',
        'last_name': 'Vendedor',
        'email': 'ventas@globalspa.cloud',
        'is_staff': True,
        'is_active': True
    }
)

if created:
    user_ventas.set_password('ventas123')
    user_ventas.save()
    print(f"✅ Usuario creado: {user_ventas.username} (password: ventas123)")
else:
    print(f"ℹ️  Usuario existente: {user_ventas.username}")

# =====================================================
# 7. CREAR VENTAS (90 días de historial)
# =====================================================
print("\n💰 Creando ventas (esto puede tardar un poco)...")

fecha_inicio = timezone.now() - timedelta(days=90)
fecha_actual = timezone.now()

# Definir patrones de venta por tipo de producto
patrones_venta = {
    'LIM-': {'frecuencia': 0.7, 'cantidad_min': 2, 'cantidad_max': 8},  # Alta rotación
    'CON-': {'frecuencia': 0.6, 'cantidad_min': 3, 'cantidad_max': 10},  # Alta rotación
    'COS-': {'frecuencia': 0.4, 'cantidad_min': 1, 'cantidad_max': 4},  # Media rotación
    'ACE-': {'frecuencia': 0.3, 'cantidad_min': 1, 'cantidad_max': 3},  # Media-baja
    'TEX-': {'frecuencia': 0.2, 'cantidad_min': 1, 'cantidad_max': 5},  # Baja rotación
}

medios_pago = ['Efectivo', 'Débito', 'Crédito', 'Transferencia']

ventas_creadas = 0
detalles_creados = 0

# Generar ventas para cada día
fecha_iter = fecha_inicio
while fecha_iter <= fecha_actual:
    # Más ventas en días laborales (Lun-Vie) y fines de semana
    es_dia_laboral = fecha_iter.weekday() < 5
    num_ventas_dia = random.randint(3, 8) if es_dia_laboral else random.randint(5, 12)
    
    for _ in range(num_ventas_dia):
        # Hora aleatoria del día (09:00 - 20:00)
        hora_venta = fecha_iter.replace(
            hour=random.randint(9, 20),
            minute=random.randint(0, 59),
            second=random.randint(0, 59)
        )
        
        # Crear venta
        venta = Venta.objects.create(
            fecha=hora_venta,
            usuario=user_ventas,
            total=0,  # Se calculará después
            medio_pago=random.choice(medios_pago),
            estado='completado'
        )
        
        total_venta = Decimal('0')
        
        # Agregar productos a la venta (entre 1 y 5 productos)
        num_productos = random.randint(1, 5)
        productos_en_venta = random.sample(productos_creados, min(num_productos, len(productos_creados)))
        
        for producto in productos_en_venta:
            # Determinar patrón según prefijo del SKU
            prefijo = producto.sku.split('-')[0] + '-'
            patron = patrones_venta.get(prefijo, {'frecuencia': 0.3, 'cantidad_min': 1, 'cantidad_max': 3})
            
            # Decidir si este producto se vende según su frecuencia
            if random.random() < patron['frecuencia']:
                cantidad = random.randint(patron['cantidad_min'], patron['cantidad_max'])
                subtotal = producto.precio_unitario * cantidad
                
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unidad=producto.precio_unitario,
                    costo_unitario=producto.costo_unitario,
                    subtotal=subtotal
                )
                
                total_venta += subtotal
                detalles_creados += 1
        
        # Actualizar total de la venta
        venta.total = total_venta
        venta.save()
        
        ventas_creadas += 1
    
    # Avanzar al siguiente día
    fecha_iter += timedelta(days=1)

print(f"\n✅ {ventas_creadas} ventas creadas")
print(f"✅ {detalles_creados} detalles de venta creados")

# =====================================================
# RESUMEN FINAL
# =====================================================
print("\n" + "=" * 60)
print("✅ POBLACIÓN DE BASE DE DATOS COMPLETADA")
print("=" * 60)

print(f"\n📊 RESUMEN:")
print(f"  • Roles: {Rol.objects.count()}")
print(f"  • Proveedores: {Proveedor.objects.count()}")
print(f"  • Categorías: {Categoria.objects.count()}")
print(f"  • Ubicaciones: {Ubicacion.objects.count()}")
print(f"  • Productos: {Productos.objects.count()}")
print(f"  • Ventas: {Venta.objects.count()}")
print(f"  • Detalles de Venta: {DetalleVenta.objects.count()}")

print(f"\n📈 DATOS PARA IA:")
print(f"  • Periodo de ventas: 90 días ({fecha_inicio.date()} a {fecha_actual.date()})")
print(f"  • Promedio de ventas por día: {ventas_creadas / 90:.1f}")
print(f"  • Productos promedio por venta: {detalles_creados / ventas_creadas:.1f}")

print(f"\n🔑 CREDENCIALES DE PRUEBA:")
print(f"  Usuario: vendedor1")
print(f"  Password: ventas123")

print(f"\n🚀 PRÓXIMOS PASOS:")
print(f"  1. Entrenar modelo IA: http://localhost:8000/dashboard-ia/?entrenar=1")
print(f"  2. Ver predicciones y alertas")
print(f"  3. Generar órdenes de compra automáticas")

print("\n" + "=" * 60)