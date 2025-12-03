"""
Módulo de Machine Learning para Predicción de Demanda y Análisis de Inventario
==============================================================================

Este módulo implementa tres componentes principales de IA:
1. Modelo de Regresión (Random Forest) para predicción de demanda
2. Clustering (K-Means) para segmentación automática de productos
3. Sistema de alertas inteligentes basado en predicciones ML

Autor: [Marcelo Ponce]
Fecha: 2025
Propósito: Tesis - Aplicación de IA en gestión de inventario 
"""

import pandas as pd
import numpy as np
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Avg, Count, F
from sklearn.ensemble import RandomForestRegressor
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    mean_squared_error, 
    mean_absolute_error, 
    r2_score,
    silhouette_score
)
import pickle
import os
import logging
import warnings

from .models import Productos, DetalleVenta, Venta

# Configuración de logging
logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')

# Constantes del modelo
ML_MODELS_DIR = 'sitio1/ml_models/'
DEMANDA_MODEL_PATH = os.path.join(ML_MODELS_DIR, 'demanda_model.pkl')
SCALER_PATH = os.path.join(ML_MODELS_DIR, 'scaler.pkl')
CLUSTER_MODEL_PATH = os.path.join(ML_MODELS_DIR, 'cluster_model.pkl')

# Parámetros de configuración
MIN_VENTAS_ENTRENAMIENTO = 20  # Mínimo de registros para entrenar
DIAS_HISTORICO = 90  # Ventana temporal de análisis
RANDOM_STATE = 42  # Para reproducibilidad


# =====================================================
# UTILIDADES Y FUNCIONES AUXILIARES
# =====================================================

def _crear_directorio_modelos():
    """Crea el directorio para almacenar modelos ML si no existe."""
    os.makedirs(ML_MODELS_DIR, exist_ok=True)


def _extraer_features_temporales(fecha):
    """
    Extrae características temporales avanzadas de una fecha.
    
    Justificación académica:
    Las features temporales capturan patrones cíclicos en la demanda 
    (estacionalidad semanal, mensual). Se usan encoding cíclico (seno/coseno)
    para representar la naturaleza circular del tiempo.
    
    Args:
        fecha: datetime object
        
    Returns:
        dict con features temporales
    """
    dia_anio = fecha.timetuple().tm_yday
    
    return {
        'dia_semana': fecha.weekday(),
        'mes': fecha.month,
        'dia_mes': fecha.day,
        'es_fin_semana': 1 if fecha.weekday() >= 5 else 0,
        # Encoding cíclico para capturar periodicidad
        'dia_semana_sin': np.sin(2 * np.pi * fecha.weekday() / 7),
        'dia_semana_cos': np.cos(2 * np.pi * fecha.weekday() / 7),
        'mes_sin': np.sin(2 * np.pi * fecha.month / 12),
        'mes_cos': np.cos(2 * np.pi * fecha.month / 12),
    }


def _preparar_dataset_ventas(dias_atras=DIAS_HISTORICO):
    """
    Prepara el dataset de ventas con features enriquecidas.
    
    Justificación académica:
    Se construye un dataset estructurado con features relevantes para
    aprendizaje supervisado: características del producto, temporales
    y de contexto de venta.
    
    Returns:
        DataFrame de pandas con features y target
    """
    fecha_limite = timezone.now() - timedelta(days=dias_atras)
    
    ventas = DetalleVenta.objects.filter(
        venta__fecha__gte=fecha_limite
    ).select_related('producto', 'venta')
    
    if not ventas.exists():
        logger.warning("No hay datos de ventas en el período especificado")
        return None
    
    data = []
    for detalle in ventas:
        fecha = detalle.venta.fecha
        features_temp = _extraer_features_temporales(fecha)
        
        data.append({
            'producto_id': detalle.producto.id,
            'precio': float(detalle.precio_unidad),
            'categoria_id': detalle.producto.categoria.id,
            'cantidad': detalle.cantidad,  # Target variable
            **features_temp
        })
    
    df = pd.DataFrame(data)
    logger.info(f"Dataset creado con {len(df)} registros de ventas")
    
    return df


# =====================================================
# 1. PREDICCIÓN DE DEMANDA (Aprendizaje Supervisado)
# =====================================================

def entrenar_modelo_demanda():
    """
    Entrena un modelo Random Forest Regressor para predecir demanda de productos.
    
    Justificación académica:
    - Random Forest es un ensemble method robusto que reduce overfitting
    - Captura relaciones no lineales entre features
    - Resistente a outliers y features irrelevantes
    - No requiere normalización de datos (tree-based)
    
    Proceso:
    1. Extracción de features temporales y de producto
    2. División train/test (80/20)
    3. Entrenamiento con validación cruzada
    4. Evaluación con múltiples métricas
    5. Persistencia del modelo entrenado
    
    Returns:
        tuple: (modelo_entrenado, mensaje_resultado, metricas_dict)
    """
    logger.info("Iniciando entrenamiento de modelo de predicción de demanda")
    _crear_directorio_modelos()
    
    # 1. Preparar datos
    df = _preparar_dataset_ventas()
    
    if df is None or len(df) < MIN_VENTAS_ENTRENAMIENTO:
        mensaje = f"Insuficientes datos para entrenar (mínimo {MIN_VENTAS_ENTRENAMIENTO} registros)"
        logger.warning(mensaje)
        return None, mensaje, {}
    
    # 2. Definir features y target
    feature_columns = [
        'producto_id', 'precio', 'categoria_id',
        'dia_semana', 'mes', 'dia_mes', 'es_fin_semana',
        'dia_semana_sin', 'dia_semana_cos', 'mes_sin', 'mes_cos'
    ]
    
    X = df[feature_columns]
    y = df['cantidad']
    
    # 3. División train/test estratificada
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, 
        test_size=0.2, 
        random_state=RANDOM_STATE,
        shuffle=True
    )
    
    logger.info(f"Train: {len(X_train)} | Test: {len(X_test)}")
    
    # 4. Configuración del modelo
    # Parámetros optimizados para evitar overfitting
    modelo = RandomForestRegressor(
        n_estimators=100,           # Número de árboles
        max_depth=15,               # Profundidad máxima (regularización)
        min_samples_split=5,        # Mínimo para dividir nodo
        min_samples_leaf=2,         # Mínimo en hoja
        max_features='sqrt',        # Features por split
        random_state=RANDOM_STATE,
        n_jobs=-1,                  # Paralelización
        oob_score=True              # Out-of-bag score
    )
    
    # 5. Entrenamiento
    logger.info("Entrenando Random Forest...")
    modelo.fit(X_train, y_train)
    
    # 6. Validación cruzada (k-fold)
    cv_scores = cross_val_score(
        modelo, X_train, y_train, 
        cv=5, 
        scoring='neg_mean_squared_error'
    )
    cv_rmse = np.sqrt(-cv_scores.mean())
    
    # 7. Predicciones y evaluación
    y_pred_train = modelo.predict(X_train)
    y_pred_test = modelo.predict(X_test)
    
    # Métricas en conjunto de entrenamiento
    train_metrics = {
        'rmse': np.sqrt(mean_squared_error(y_train, y_pred_train)),
        'mae': mean_absolute_error(y_train, y_pred_train),
        'r2': r2_score(y_train, y_pred_train)
    }
    
    # Métricas en conjunto de prueba (más importante)
    test_metrics = {
        'rmse': np.sqrt(mean_squared_error(y_test, y_pred_test)),
        'mae': mean_absolute_error(y_test, y_pred_test),
        'r2': r2_score(y_test, y_pred_test)
    }
    
    # 8. Importancia de features
    feature_importance = dict(zip(
        feature_columns,
        modelo.feature_importances_
    ))
    top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # 9. Guardar modelo
    with open(DEMANDA_MODEL_PATH, 'wb') as f:
        pickle.dump(modelo, f)
    
    logger.info(f"Modelo guardado en {DEMANDA_MODEL_PATH}")
    
    # 10. Construir mensaje de resultado
    mensaje = f"""
    ✅ Modelo entrenado exitosamente
    
    📊 Métricas de Evaluación:
    - Test RMSE: {test_metrics['rmse']:.2f} unidades
    - Test MAE: {test_metrics['mae']:.2f} unidades
    - Test R²: {test_metrics['r2']:.3f}
    - CV RMSE: {cv_rmse:.2f}
    - OOB Score: {modelo.oob_score_:.3f}
    
    📈 Datos:
    - Registros totales: {len(df)}
    - Train: {len(X_train)} | Test: {len(X_test)}
    
    🎯 Top 3 Features:
    {chr(10).join([f"  - {feat}: {imp:.3f}" for feat, imp in top_features[:3]])}
    """
    
    metricas = {
        'train': train_metrics,
        'test': test_metrics,
        'cv_rmse': cv_rmse,
        'oob_score': modelo.oob_score_,
        'n_samples': len(df),
        'top_features': top_features
    }
    
    logger.info("Entrenamiento completado exitosamente")
    
    return modelo, mensaje, metricas


def predecir_demanda_producto(producto_id, dias_adelante=7):
    """
    Predice la demanda futura de un producto específico.
    
    Justificación académica:
    Utiliza el modelo entrenado para generar predicciones prospectivas,
    extrapolando patrones históricos a fechas futuras con features
    temporales conocidas.
    
    Args:
        producto_id: ID del producto a predecir
        dias_adelante: Horizonte de predicción en días
        
    Returns:
        tuple: (dict_resultado, mensaje_error)
    """
    # 1. Validar existencia del modelo
    if not os.path.exists(DEMANDA_MODEL_PATH):
        return None, "❌ Modelo no entrenado. Entrena el modelo primero."
    
    # 2. Cargar modelo
    try:
        with open(DEMANDA_MODEL_PATH, 'rb') as f:
            modelo = pickle.load(f)
    except Exception as e:
        logger.error(f"Error cargando modelo: {e}")
        return None, f"Error al cargar modelo: {str(e)}"
    
    # 3. Validar producto
    try:
        producto = Productos.objects.get(id=producto_id)
    except Productos.DoesNotExist:
        return None, "Producto no encontrado"
    
    # 4. Preparar features para predicción
    predicciones = []
    fecha_actual = timezone.now()
    
    features_list = []
    fechas = []
    
    for i in range(dias_adelante):
        fecha_futura = fecha_actual + timedelta(days=i)
        features_temp = _extraer_features_temporales(fecha_futura)
        
        features_list.append({
            'producto_id': producto.id,
            'precio': float(producto.precio_unitario),
            'categoria_id': producto.categoria.id,
            **features_temp
        })
        fechas.append(fecha_futura.date())
    
    # 5. Crear DataFrame con las mismas columnas del entrenamiento
    X_pred = pd.DataFrame(features_list)
    
    # 6. Predicción batch (más eficiente que loop)
    try:
        cantidades_pred = modelo.predict(X_pred)
        cantidades_pred = np.maximum(0, cantidades_pred).astype(int)  # No negativos
    except Exception as e:
        logger.error(f"Error en predicción: {e}")
        return None, f"Error al predecir: {str(e)}"
    
    # 7. Estructurar resultados
    for fecha, cantidad in zip(fechas, cantidades_pred):
        predicciones.append({
            'fecha': fecha,
            'cantidad_estimada': int(cantidad)
        })
    
    total_estimado = int(cantidades_pred.sum())
    
    resultado = {
        'producto': producto,
        'predicciones_diarias': predicciones,
        'total_estimado': total_estimado,
        'stock_actual': producto.stock_actual,
        'alerta': total_estimado > producto.stock_actual,
        'deficit': max(0, total_estimado - producto.stock_actual)
    }
    
    logger.info(f"Predicción generada para {producto.nombre}: {total_estimado} unidades en {dias_adelante} días")
    
    return resultado, None


def predecir_demanda_batch(producto_ids, dias_adelante=7):
    """
    Predicción batch optimizada para múltiples productos.
    
    Mejora de rendimiento:
    Predice para múltiples productos en una sola pasada,
    evitando cargar el modelo repetidamente.
    
    Args:
        producto_ids: Lista de IDs de productos
        dias_adelante: Horizonte de predicción
        
    Returns:
        dict: {producto_id: resultado_prediccion}
    """
    if not os.path.exists(DEMANDA_MODEL_PATH):
        return {}
    
    with open(DEMANDA_MODEL_PATH, 'rb') as f:
        modelo = pickle.load(f)
    
    productos = Productos.objects.filter(id__in=producto_ids, activo=True)
    resultados = {}
    
    for producto in productos:
        # Preparar features
        features_list = []
        fechas = []
        fecha_actual = timezone.now()
        
        for i in range(dias_adelante):
            fecha_futura = fecha_actual + timedelta(days=i)
            features_temp = _extraer_features_temporales(fecha_futura)
            
            features_list.append({
                'producto_id': producto.id,
                'precio': float(producto.precio_unitario),
                'categoria_id': producto.categoria.id,
                **features_temp
            })
            fechas.append(fecha_futura.date())
        
        X_pred = pd.DataFrame(features_list)
        cantidades_pred = np.maximum(0, modelo.predict(X_pred)).astype(int)
        
        predicciones = [
            {'fecha': fecha, 'cantidad_estimada': int(cant)}
            for fecha, cant in zip(fechas, cantidades_pred)
        ]
        
        total_estimado = int(cantidades_pred.sum())
        
        resultados[producto.id] = {
            'producto': producto,
            'predicciones_diarias': predicciones,
            'total_estimado': total_estimado,
            'stock_actual': producto.stock_actual,
            'alerta': total_estimado > producto.stock_actual,
            'deficit': max(0, total_estimado - producto.stock_actual)
        }
    
    return resultados


# =====================================================
# 2. CLUSTERING DE PRODUCTOS (Aprendizaje No Supervisado)
# =====================================================

def clasificar_productos_ml():
    """
    Aplica K-Means clustering para segmentar productos automáticamente.
    
    Justificación académica:
    - K-Means es un algoritmo de clustering particional eficiente
    - Agrupa productos con comportamiento de venta similar
    - Permite estrategias diferenciadas por segmento (ABC analysis)
    - Usa StandardScaler para normalizar features de diferente escala
    
    Proceso:
    1. Extracción de métricas de ventas por producto
    2. Normalización con StandardScaler
    3. Determinación de K óptimo (silhouette score)
    4. Clustering y etiquetado interpretable
    5. Persistencia de modelo y scaler
    
    Returns:
        tuple: (DataFrame_resultados, mensaje_error)
    """
    logger.info("Iniciando clustering de productos")
    _crear_directorio_modelos()
    
    hace_30_dias = timezone.now() - timedelta(days=30)
    productos = Productos.objects.filter(activo=True)
    
    if productos.count() < 3:
        return None, "Se necesitan al menos 3 productos activos para clustering"
    
    # 1. Extracción de features
    data = []
    for prod in productos:
        ventas = DetalleVenta.objects.filter(
            producto=prod,
            venta__fecha__gte=hace_30_dias
        ).aggregate(
            total_vendido=Sum('cantidad'),
            num_ventas=Count('id'),
            ingreso_total=Sum('subtotal')
        )
        
        # Calcular velocidad de rotación
        dias_desde_ultima_venta = 30  # default
        ultima_venta = DetalleVenta.objects.filter(producto=prod).order_by('-venta__fecha').first()
        if ultima_venta:
            dias_desde_ultima_venta = (timezone.now() - ultima_venta.venta.fecha).days
        
        data.append({
            'producto_id': prod.id,
            'nombre': prod.nombre,
            'total_vendido': ventas['total_vendido'] or 0,
            'num_ventas': ventas['num_ventas'] or 0,
            'ingreso_total': float(ventas['ingreso_total'] or 0),
            'stock_actual': prod.stock_actual,
            'precio': float(prod.precio_unitario),
            'dias_sin_venta': dias_desde_ultima_venta
        })
    
    df = pd.DataFrame(data)
    
    if len(df) < 3:
        return None, "Datos insuficientes después de filtrado"
    
    # 2. Features para clustering
    feature_columns = ['total_vendido', 'num_ventas', 'ingreso_total', 'stock_actual', 'dias_sin_venta']
    X = df[feature_columns].fillna(0)  # Manejar NaN
    
    # 3. Normalización (crítico para K-Means)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # 4. Determinar K óptimo (método del codo + silhouette)
    silhouette_scores = []
    K_range = range(2, min(6, len(df)))  # K entre 2 y 5
    
    for k in K_range:
        kmeans_temp = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels_temp = kmeans_temp.fit_predict(X_scaled)
        score = silhouette_score(X_scaled, labels_temp)
        silhouette_scores.append(score)
    
    # Elegir K con mejor silhouette score
    if silhouette_scores:
        mejor_k = K_range[np.argmax(silhouette_scores)]
        mejor_score = max(silhouette_scores)
    else:
        mejor_k = 3  # default
        mejor_score = 0
    
    logger.info(f"K óptimo seleccionado: {mejor_k} (silhouette: {mejor_score:.3f})")
    
    # 5. Clustering final con K óptimo
    kmeans = KMeans(
        n_clusters=mejor_k,
        random_state=RANDOM_STATE,
        n_init=10,
        max_iter=300
    )
    df['cluster'] = kmeans.fit_predict(X_scaled)
    
    # 6. Interpretación de clusters basada en ventas
    cluster_stats = df.groupby('cluster').agg({
        'total_vendido': 'mean',
        'ingreso_total': 'mean',
        'num_ventas': 'mean'
    }).reset_index()
    
    # Ordenar por ventas para etiquetar
    cluster_stats = cluster_stats.sort_values('total_vendido', ascending=False)
    
    # Etiquetas interpretables según rendimiento
    if mejor_k == 3:
        cluster_labels = {
            cluster_stats.iloc[0]['cluster']: 'Alta Rotación',
            cluster_stats.iloc[1]['cluster']: 'Media Rotación',
            cluster_stats.iloc[2]['cluster']: 'Baja Rotación'
        }
    elif mejor_k == 2:
        cluster_labels = {
            cluster_stats.iloc[0]['cluster']: 'Alta Rotación',
            cluster_stats.iloc[1]['cluster']: 'Baja Rotación'
        }
    else:
        cluster_labels = {i: f'Grupo {i+1}' for i in range(mejor_k)}
    
    df['categoria_ia'] = df['cluster'].map(cluster_labels)
    
    # 7. Guardar modelo y scaler
    with open(CLUSTER_MODEL_PATH, 'wb') as f:
        pickle.dump(kmeans, f)
    
    with open(SCALER_PATH, 'wb') as f:
        pickle.dump(scaler, f)
    
    logger.info(f"Clustering completado. Silhouette Score: {mejor_score:.3f}")
    
    resultado = df[[
        'producto_id', 'nombre', 'categoria_ia', 
        'total_vendido', 'ingreso_total', 'num_ventas'
    ]]
    
    return resultado, None


# =====================================================
# 3. SISTEMA DE ALERTAS INTELIGENTE
# =====================================================

def generar_alertas_ia():
    """
    Genera alertas de inventario usando predicciones ML.
    
    Justificación académica:
    Sistema de soporte a decisiones basado en predicciones ML.
    Combina aprendizaje automático con reglas de negocio para
    generar recomendaciones accionables.
    
    Tipos de alerta:
    - Crítica: Demanda estimada > Stock actual
    - Preventiva: Demanda estimada > 70% del stock
    - Oportunidad: Alta rotación con exceso de stock
    
    Returns:
        list: Lista de diccionarios con alertas priorizadas
    """
    logger.info("Generando alertas inteligentes")
    
    if not os.path.exists(DEMANDA_MODEL_PATH):
        logger.warning("Modelo no entrenado, no se pueden generar alertas")
        return []
    
    productos = Productos.objects.filter(activo=True)
    producto_ids = list(productos.values_list('id', flat=True))
    
    # Predicción batch optimizada
    predicciones = predecir_demanda_batch(producto_ids, dias_adelante=7)
    
    alertas = []
    
    for prod_id, resultado in predicciones.items():
        demanda_estimada = resultado['total_estimado']
        stock_actual = resultado['stock_actual']
        producto = resultado['producto']
        
        # Alerta crítica: stock insuficiente
        if demanda_estimada > stock_actual:
            deficit = demanda_estimada - stock_actual
            alertas.append({
                'producto': producto,
                'tipo': 'critico',
                'prioridad': 1,
                'mensaje': f'Stock insuficiente. Faltan {deficit} unidades para cubrir demanda estimada (7 días)',
                'demanda_estimada': demanda_estimada,
                'stock_actual': stock_actual,
                'deficit': deficit,
                'accion_sugerida': f'🚨 URGENTE: Reabastecer {deficit + 10} unidades',
                'dias_hasta_agotamiento': int(stock_actual / (demanda_estimada / 7)) if demanda_estimada > 0 else 999
            })
        
        # Alerta preventiva: stock ajustado
        elif demanda_estimada > stock_actual * 0.7:
            alertas.append({
                'producto': producto,
                'tipo': 'preventivo',
                'prioridad': 2,
                'mensaje': f'Stock ajustado. Considera reabastecer pronto',
                'demanda_estimada': demanda_estimada,
                'stock_actual': stock_actual,
                'deficit': 0,
                'accion_sugerida': f'⚠️ Monitorear y preparar orden de compra',
                'dias_hasta_agotamiento': int(stock_actual / (demanda_estimada / 7)) if demanda_estimada > 0 else 999
            })
        
        # Alerta de oportunidad: exceso de stock en producto de baja rotación
        elif stock_actual > demanda_estimada * 3 and demanda_estimada > 0:
            alertas.append({
                'producto': producto,
                'tipo': 'oportunidad',
                'prioridad': 3,
                'mensaje': f'Exceso de stock. Considera promoción',
                'demanda_estimada': demanda_estimada,
                'stock_actual': stock_actual,
                'deficit': 0,
                'accion_sugerida': f'💡 Aplicar descuento o promoción para rotar inventario',
                'dias_hasta_agotamiento': 999
            })
    
    # Ordenar por prioridad y días hasta agotamiento
    alertas_ordenadas = sorted(alertas, key=lambda x: (x['prioridad'], x['dias_hasta_agotamiento']))
    
    logger.info(f"Generadas {len(alertas_ordenadas)} alertas ({sum(1 for a in alertas if a['tipo']=='critico')} críticas)")
    
    return alertas_ordenadas


# =====================================================
# FUNCIONES DE EVALUACIÓN Y MONITOREO
# =====================================================

def evaluar_modelo_actual():
    """
    Evalúa el rendimiento del modelo actual con datos recientes.
    
    Útil para:
    - Monitorear degradación del modelo (model drift)
    - Decidir cuándo reentrenar
    - Métricas de rendimiento en producción
    
    Returns:
        dict: Métricas de evaluación
    """
    if not os.path.exists(DEMANDA_MODEL_PATH):
        return {'error': 'Modelo no encontrado'}
    
    with open(DEMANDA_MODEL_PATH, 'rb') as f:
        modelo = pickle.load(f)
    
    # Obtener datos recientes (últimos 14 días)
    df_reciente = _preparar_dataset_ventas(dias_atras=14)
    
    if df_reciente is None or len(df_reciente) < 5:
        return {'error': 'Datos insuficientes para evaluación'}
    
    feature_columns = [
        'producto_id', 'precio', 'categoria_id',
        'dia_semana', 'mes', 'dia_mes', 'es_fin_semana',
        'dia_semana_sin', 'dia_semana_cos', 'mes_sin', 'mes_cos'
    ]
    
    X = df_reciente[feature_columns]
    y_real = df_reciente['cantidad']
    
    y_pred = modelo.predict(X)
    
    metricas = {
        'rmse': np.sqrt(mean_squared_error(y_real, y_pred)),
        'mae': mean_absolute_error(y_real, y_pred),
        'r2': r2_score(y_real, y_pred),
        'n_samples': len(df_reciente),
        'fecha_evaluacion': timezone.now().isoformat()
    }
    
    return metricas


def obtener_estadisticas_modelo():
    """
    Retorna estadísticas y metadatos del modelo actual.
    
    Returns:
        dict: Información del modelo
    """
    if not os.path.exists(DEMANDA_MODEL_PATH):
        return {'error': 'Modelo no entrenado'}
    
    stats = {
        'modelo_existe': True,
        'ruta': DEMANDA_MODEL_PATH,
        'fecha_modificacion': os.path.getmtime(DEMANDA_MODEL_PATH),
        'tamano_kb': os.path.getsize(DEMANDA_MODEL_PATH) / 1024
    }
    
    return stats