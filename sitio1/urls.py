from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    
    #Vista que lista la pestaña de productos y sus opciones
    path('productos', views.lista_productos, name="productos"),
    
    path('eliminar_productos/<int:productos_id>', views.eliminar_productos, name="eliminar_productos"),
    path('desactivar_producto/<int:productos_id>', views.desactivar_producto, name="desactivar_producto"),
    path('reactivar_producto/<int:productos_id>', views.reactivar_producto, name="reactivar_producto"),
    path('verificar_ventas_producto/<int:productos_id>', views.verificar_ventas_producto, name="verificar_ventas_producto"),
    #CRUD para productos
    path('ingresar_productos', views.ingresar_productos, name="ingresar_productos"),
    path('editar_productos/<int:productos_id>', views.editar_productos, name='editar_productos'),
    
    

    #Vista de las opciones de gestion
    path('gestion/', views.vista_gestion, name='gestion'),
    #Vista de las opciones de usuarios
    path('usuarios_gestion/', views.vista_usuarios, name='usuarios_gestion'),

    #CRUD para categorias
    path('categorias/', views.listar_categorias, name='listar_categorias'),
    path('categorias/crear/', views.crear_categoria, name='crear_categoria'),
    path('categorias/editar/<int:id>/', views.editar_categoria, name='editar_categoria'),
    path('categorias/eliminar/<int:id>/', views.eliminar_categoria, name='eliminar_categoria'),
    
    #CRUD para proveedores
    path('proveedores/', views.listar_proveedores, name='listar_proveedores'),
    path('proveedores/nuevo/', views.crear_proveedor, name='crear_proveedor'),
    path('proveedores/<int:pk>/editar/', views.editar_proveedor, name='editar_proveedor'),
    path('proveedores/<int:pk>/eliminar/', views.eliminar_proveedor, name='eliminar_proveedor'),

    #CRUD para ubicaciones
    path('ubicaciones/', views.listar_ubicaciones, name='listar_ubicaciones'),
    path('ubicaciones/nuevo/', views.crear_ubicacion, name='crear_ubicacion'),
    path('ubicaciones/editar/<int:pk>/', views.editar_ubicacion, name='editar_ubicacion'),
    path('ubicaciones/eliminar/<int:pk>/', views.eliminar_ubicacion, name='eliminar_ubicacion'),
    
    # CRUD para usuarios
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/crear/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/editar/<int:id>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/eliminar/<int:id>/', views.eliminar_usuario, name='eliminar_usuario'),

    # editar perfil
    path('mi-perfil/', views.ver_perfil, name='ver_perfil'), # Para VER
    path('editar-perfil/', views.editar_perfil, name='editar_perfil'), # Para EDITAR

    #CRUD para roles
    path('roles/', views.listar_roles, name='listar_roles'),
    path('roles/crear/', views.crear_rol, name='crear_rol'),
    path('roles/editar/<int:pk>/', views.editar_rol, name='editar_rol'),
    path('roles/eliminar/<int:pk>/', views.eliminar_rol, name='eliminar_rol'),
    path('registro/', views.registro, name="registro"),

    
    

    # VISTAS PARA LAS VENTAS
    path('ventas/', views.listar_ventas, name='listar_ventas'),
    path('ventas/<int:venta_id>/', views.detalle_venta, name='detalle_venta'),
    path('ventas/nueva/', views.crear_venta, name='crear_venta'),
    
    path('analytics/', views.panel_analytics_ia, name='panel_analytics_ia'),

    
    
    
    

    # Punto de Venta
    path('venta/', views.venta_view, name='venta'),
    path('api/productos/', views.api_productos, name='api_productos'),
    path('api/venta/', views.api_venta, name='api_venta'),
    path('api/productos-frecuentes/', views.api_productos_frecuentes, name='api_productos_frecuentes'),

    
    path('api/drf/venta/', views.VentaCreateAPIView.as_view(), name='api_venta_drf'),

    
    # Dashboard principal
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    
    # Dashboard IA
    path('dashboard/ia/', views.dashboard_ia_view, name='dashboard_ia'),
    path('prediccion/<int:producto_id>/', views.prediccion_producto_view, name='prediccion_producto'),
    
    # API Endpoints 
    path('api/prediccion/<int:producto_id>/', views.api_prediccion_producto, name='api_prediccion'),
    path('api/alertas/', views.api_alertas, name='api_alertas'),
    path('api/entrenar/', views.api_entrenar_modelo, name='api_entrenar'),

    path('ordenes-compra/', views.lista_ordenes_compra, name='lista_ordenes_compra'),
    path('ordenes-compra/generar/', views.generar_orden_compra_ia, name='generar_orden_compra_ia'),
    path('ordenes-compra/<int:orden_id>/', views.detalle_orden_compra, name='detalle_orden_compra'),

    # Sistema de recuperación de contraseña
    path('password-reset/', 
     auth_views.PasswordResetView.as_view(
         template_name='registration/password_reset.html',
         email_template_name='registration/password_reset_email.html',
         subject_template_name='registration/password_reset_subject.txt',
     ), 
     name='passsword_reset'),
    
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='registration/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='registration/password_reset_confirm.html'
         ), 
         name='password_reset_confirm'),
    
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='registration/password_reset_complete.html'
         ), 
         name='password_reset_complete'),

    # Inventario Físico
    path('inventario-fisico/', views.inventario_fisico_inicio, name='inventario_fisico_inicio'),
    path('inventario-fisico/<int:ubicacion_id>/', views.inventario_fisico_conteo, name='inventario_fisico_conteo'),
    path('inventario-fisico/guardar/', views.inventario_fisico_guardar, name='inventario_fisico_guardar'),
    path('inventario-fisico/confirmar/<int:ajuste_id>/', views.inventario_fisico_confirmar, name='inventario_fisico_confirmar'),

    # Historial de Movimientos
    path('historial-movimientos/', views.historial_movimientos, name='historial_movimientos'),
    
    # Historial de Ajustes  
    path('historial-ajustes/', views.historial_ajustes, name='historial_ajustes'),
    path('historial-ajustes/<int:ajuste_id>/', views.detalle_ajuste, name='detalle_ajuste'),

    #auditoria 
    path('auditoria/', views.auditoria_logs, name='auditoria_logs'),
    path('auditoria/detalle/<int:log_id>/', views.auditoria_detalle, name='auditoria_detalle'),
]
