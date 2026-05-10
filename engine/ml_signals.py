"""
Motor de Machine Learning para Trading
Usa Gradient Boosting para predecir dirección del precio.

Features usados:
- RSI, MACD, Bollinger Bands, MA
- Retornos 1d, 5d, 10d, 20d
- Volumen ratio y tendencia
- Volatilidad histórica
- RSI multi-período (7, 21)

Target:
- 1 = precio sube > 2% en los próximos 5 días
- 0 = precio baja o sube menos de 2%

Metodología — Walk-forward real con TimeSeriesSplit:
- 5 folds de expansión temporal (sklearn TimeSeriesSplit)
- Métricas promediadas sobre los 5 folds → AUC estable, no suerte de split
- Filtro de estabilidad: auc_std < 0.15 (consistente entre regímenes)
- Modelo final entrenado en TODOS los datos (sin reservar test)
- Clases balanceadas con compute_sample_weight('balanced')
- Umbral: auc_mean >= 0.55 y auc_std < 0.15
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
import json
import time
from datetime import datetime
import concurrent.futures

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "cache", "ml_models")
os.makedirs(MODELS_DIR, exist_ok=True)

# ── FEATURES ──────────────────────────────────────────────────────────────────
def calcular_features(h):
    """Calcula todos los features técnicos para el modelo ML"""
    close  = h["Close"]
    high   = h["High"]
    low    = h["Low"]
    volume = h["Volume"]

    df = pd.DataFrame(index=h.index)

    # RSI
    delta = close.diff()
    g = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    p = (-delta).clip(lower=0).ewm(com=13, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + g/p))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal= macd.ewm(span=9, adjust=False).mean()
    df["macd_hist"] = macd - signal
    df["macd_norm"] = df["macd_hist"] / close  # normalizado por precio

    # Bollinger Bands
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["pct_b"] = (close - (sma20 - 2*std20)) / (4*std20)

    # Medias móviles — distancia relativa al precio
    df["dist_ma20"] = (close - sma20) / sma20
    df["dist_ma50"] = (close - close.rolling(50).mean()) / close.rolling(50).mean()

    # ATR normalizado
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr_norm"] = tr.ewm(com=13, adjust=False).mean() / close

    # Retornos
    df["ret_1d"]  = close.pct_change(1)
    df["ret_5d"]  = close.pct_change(5)
    df["ret_10d"] = close.pct_change(10)
    df["ret_20d"] = close.pct_change(20)

    # Momentum
    df["mom_5d"]  = close / close.shift(5) - 1
    df["mom_20d"] = close / close.shift(20) - 1

    # Volumen
    vol_ma20 = volume.rolling(20).mean()
    df["vol_ratio"]  = volume / vol_ma20
    df["vol_trend"]  = vol_ma20.pct_change(5)

    # Volatilidad histórica
    df["volatilidad"] = close.pct_change().rolling(20).std()

    # RSI en diferentes períodos
    for periodo in [7, 21]:
        g2 = delta.clip(lower=0).ewm(com=periodo-1, adjust=False).mean()
        p2 = (-delta).clip(lower=0).ewm(com=periodo-1, adjust=False).mean()
        df[f"rsi_{periodo}"] = 100 - (100 / (1 + g2/p2))

    return df.dropna()

def calcular_target(close, horizonte=5, umbral=0.02):
    """
    Target binario:
    1 = precio sube más de umbral% en los próximos horizonte días
    0 = precio baja o sube menos de umbral%
    """
    retorno_futuro = close.shift(-horizonte) / close - 1
    return (retorno_futuro > umbral).astype(int)

# ── ENTRENAMIENTO ─────────────────────────────────────────────────────────────
def entrenar_modelo(ticker, periodo="2y", horizonte=5, umbral=0.02):
    """
    Entrena modelo con walk-forward real (TimeSeriesSplit, 5 folds).

    Flujo:
    1. 5 folds temporales — métricas promediadas sobre distintos regímenes
    2. Filtro: auc_mean >= MIN_AUC y auc_std < MAX_AUC_STD
    3. Modelo final entrenado en TODOS los datos (máximo poder predictivo)

    Ventaja vs split único: un modelo que solo funciona en un período de mercado
    tendrá auc_std alto y será rechazado aunque tenga AUC puntual alto.
    """
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import roc_auc_score, balanced_accuracy_score
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.utils.class_weight import compute_sample_weight

        N_SPLITS       = 5      # folds walk-forward
        MIN_TRAIN      = 120    # mínimo de muestras de train por fold
        MIN_TEST       = 30     # mínimo de muestras de test por fold
        MIN_AUC        = 0.58   # AUC promedio mínimo — elevado de 0.55 (barely-random)
        MAX_AUC_STD    = 0.12   # estabilidad más exigente — reducido de 0.15
        MIN_FOLDS_VALIDOS = 3   # requiere al menos 3 períodos temporales (era 2)

        h = yf.Ticker(ticker).history(period=periodo)
        if len(h) < 200:
            return None

        # Target dinámico: umbral ajustado a la volatilidad del activo.
        # Un umbral fijo 2% es demasiado fácil para BTC (vol diaria ~3%) y
        # demasiado exigente para acciones de baja volatilidad (COPEC ~0.8%).
        # Se usa: max(1.5%, min(5%, σ_diaria × √5 × 0.8))
        # Esto equivale a "requiere que el movimiento sea ≥ 0.8σ en 5 días".
        if len(h) >= 60:
            vol_diaria = float(h["Close"].pct_change().dropna().std())
            umbral_dinamico = round(max(0.015, min(0.05, vol_diaria * (5 ** 0.5) * 0.8)), 4)
        else:
            umbral_dinamico = umbral

        features_df = calcular_features(h)
        target      = calcular_target(h["Close"], horizonte, umbral_dinamico)

        idx_comun = features_df.index.intersection(target.index)
        X = features_df.loc[idx_comun].values
        y = target.loc[idx_comun].values
        X = X[:-horizonte]
        y = y[:-horizonte]

        if len(X) < MIN_TRAIN + MIN_TEST:
            return None

        def _make_pipeline():
            return Pipeline([
                ("scaler", StandardScaler()),
                ("model", GradientBoostingClassifier(
                    n_estimators=100,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=42,
                ))
            ])

        # ── 1. Walk-forward cross-validation ──────────────────────────────────
        tscv = TimeSeriesSplit(n_splits=N_SPLITS)
        aucs, accs = [], []

        for train_idx, test_idx in tscv.split(X):
            X_tr, X_te = X[train_idx], X[test_idx]
            y_tr, y_te = y[train_idx], y[test_idx]

            # Saltar folds con datos insuficientes o sin ambas clases en test
            if len(X_tr) < MIN_TRAIN or len(X_te) < MIN_TEST:
                continue
            if len(set(y_te)) < 2:
                continue

            p = _make_pipeline()
            sw = compute_sample_weight("balanced", y_tr)
            p.fit(X_tr, y_tr, model__sample_weight=sw)

            y_prob = p.predict_proba(X_te)[:, 1]
            y_pred = p.predict(X_te)

            aucs.append(roc_auc_score(y_te, y_prob))
            accs.append(balanced_accuracy_score(y_te, y_pred))

        if len(aucs) < MIN_FOLDS_VALIDOS:
            # Menos de MIN_FOLDS_VALIDOS folds válidos — evidencia insuficiente
            return None

        auc_mean = float(np.mean(aucs))
        auc_std  = float(np.std(aucs))
        acc_mean = float(np.mean(accs))

        # ── 2. Filtro de calidad y estabilidad ────────────────────────────────
        if auc_mean < MIN_AUC or auc_std > MAX_AUC_STD:
            return None

        # ── 3. Modelo final — entrenado en TODOS los datos ────────────────────
        pipeline_final = _make_pipeline()
        sw_final = compute_sample_weight("balanced", y)
        pipeline_final.fit(X, y, model__sample_weight=sw_final)

        # Feature importance
        feature_names = [
            "rsi", "macd_hist", "macd_norm", "pct_b", "dist_ma20", "dist_ma50",
            "atr_norm", "ret_1d", "ret_5d", "ret_10d", "ret_20d",
            "mom_5d", "mom_20d", "vol_ratio", "vol_trend", "volatilidad",
            "rsi_7", "rsi_21",
        ]
        importances  = pipeline_final.named_steps["model"].feature_importances_
        top_features = sorted(
            zip(feature_names[:len(importances)], importances),
            key=lambda x: -x[1]
        )[:5]

        base_rate = float(y.mean())   # frecuencia real de la clase positiva

        return {
            "ticker":       ticker,
            "accuracy":     round(acc_mean, 3),
            "auc":          round(auc_mean, 3),
            "auc_std":      round(auc_std, 3),
            "n_folds":      len(aucs),
            "base_rate":    round(base_rate, 3),
            "n_total":      len(X),
            "top_features": top_features,
            "pipeline":     pipeline_final,
            "features_df":  features_df,
            "timestamp":    datetime.now().isoformat(),
            # Detalle por fold — útil para debug
            "aucs_folds":   [round(a, 3) for a in aucs],
            "accs_folds":   [round(a, 3) for a in accs],
        }

    except Exception:
        return None

# ── PREDICCIÓN ────────────────────────────────────────────────────────────────
def predecir_señal_ml(ticker, modelo_info):
    """
    Genera predicción ML para el próximo período.
    Retorna probabilidad de alza y señal.
    """
    try:
        pipeline    = modelo_info["pipeline"]
        features_df = modelo_info["features_df"]

        # Usar último punto de datos
        ultimo = features_df.iloc[-1:].values
        prob_alza = float(pipeline.predict_proba(ultimo)[0, 1])
        prediccion = int(pipeline.predict(ultimo)[0])

        # Umbrales elevados de 0.65/0.35 a 0.67/0.33:
        # Con MIN_AUC=0.58, una prob de 0.65 en un modelo marginal es señal débil.
        # Se requiere mayor separación de la probabilidad base (50%).
        if prob_alza >= 0.67:
            direccion  = "ALZA"
            accion     = "COMPRAR"
            conviccion = round(50 + prob_alza * 50)
        elif prob_alza <= 0.33:
            direccion  = "BAJA"
            accion     = "VENDER"
            conviccion = round(50 + (1 - prob_alza) * 50)
        else:
            direccion  = "NEUTRO"
            accion     = "MANTENER"
            conviccion = 0

        return {
            "ticker":      ticker,
            "prob_alza":   round(prob_alza, 3),
            "prediccion":  prediccion,
            "direccion":   direccion,
            "accion":      accion,
            "conviccion":  conviccion,
            "accuracy":    modelo_info["accuracy"],
            "auc":         modelo_info["auc"],
        }

    except Exception as e:
        return None

# ── ANÁLISIS COMPLETO UNIVERSO ────────────────────────────────────────────────
def get_señales_ml(min_accuracy=0.52, min_auc=0.55, max_auc_std=0.15, max_activos=26):
    """
    Entrena modelos y genera señales ML para el universo de activos.
    Retorna señales compatibles con el motor de recomendaciones.
    """
    # Cache de modelos — re-entrenar cada 24 horas
    cache_path = os.path.join(MODELS_DIR, "señales_ml.json")
    try:
        if os.path.exists(cache_path):
            age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
            if age_h < 24:
                with open(cache_path) as f:
                    return json.load(f)
    except:
        pass

    from engine.universo import UNIVERSO_COMPLETO

    # Seleccionar activos más líquidos para ML
    activos_ml = {}
    prioridad = [
        # ── ETFs USA ejecutables — alta liquidez, datos limpios para ML ────────
        "SPY", "QQQ", "IWM", "XLE", "TLT", "GLD", "SLV", "GDX",
        # ── ADRs Chile — dual-listed, datos NYSE ────────────────────────────────
        "SQM", "ECH",
        # ── Crypto y commodities ────────────────────────────────────────────────
        "BTC-USD", "GC=F", "HG=F",
        # ── Acciones Chile más líquidas ─────────────────────────────────────────
        "COPEC.SN", "FALABELLA.SN", "BCI.SN", "CHILE.SN", "BSANTANDER.SN",
        "CMPC.SN", "CENCOSUD.SN", "LTM.SN", "CAP.SN", "CCU.SN",
        "COLBUN.SN", "ENELCHILE.SN", "VAPORES.SN", "ANDINA-B.SN",
    ]

    for ticker in prioridad:
        if ticker in UNIVERSO_COMPLETO:
            activos_ml[ticker] = UNIVERSO_COMPLETO[ticker]
        if len(activos_ml) >= max_activos:
            break

    señales = []
    modelos_entrenados = 0

    def entrenar_y_predecir(item):
        yf_ticker, info = item
        modelo = entrenar_modelo(yf_ticker)
        if not modelo:
            return None
        # Filtros de calidad — entrenar_modelo ya los aplica internamente,
        # pero se repiten aquí como segunda línea de defensa
        if modelo["accuracy"] < min_accuracy:
            return None
        if modelo["auc"] < min_auc:
            return None
        if modelo.get("auc_std", 0) > max_auc_std:
            return None
        pred = predecir_señal_ml(yf_ticker, modelo)
        if not pred or pred["accion"] == "MANTENER":
            return None
        n_folds   = modelo.get("n_folds", 1)
        auc_std   = modelo.get("auc_std", 0)
        auc_val   = modelo.get("auc", 0.55)

        # Score ajustado por calidad del modelo:
        # - base_score depende de la probabilidad de predicción
        # - auc_factor escala el score según cuánto supera el modelo la línea base
        #   AUC=0.58 → factor≈0.4; AUC=0.65 → factor≈0.75; AUC=0.72+ → factor=1.0
        # Esto evita que modelos marginales (AUC≈0.58) contribuyan igual que
        # modelos bien calibrados (AUC≈0.70).
        base_score = max(1, round((pred["conviccion"] - 50) / 10))
        auc_factor = min(1.0, max(0.3, (auc_val - 0.50) / 0.22))
        score_ajustado = max(1, round(base_score * auc_factor))

        return {
            "activo":        yf_ticker,
            "activo_motor":  yf_ticker,
            "fuente":        "ML",
            "score":         score_ajustado,
            "direccion":     pred["direccion"],
            "prob_alza":     pred["prob_alza"],
            "conviccion_ml": pred["conviccion"],
            "accuracy":      pred["accuracy"],
            "auc":           pred["auc"],
            "auc_std":       auc_std,
            "n_folds":       n_folds,
            "descripcion": (
                f"ML {info['nombre']}: prob={pred['prob_alza']:.0%} "
                f"AUC={pred['auc']:.2f}±{auc_std:.2f} "
                f"({n_folds} folds)"
            ),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(entrenar_y_predecir, item): item
                  for item in activos_ml.items()}
        for future in concurrent.futures.as_completed(futures, timeout=120):
            resultado = future.result()
            if resultado:
                señales.append(resultado)
                modelos_entrenados += 1

    señales = sorted(señales, key=lambda x: x["conviccion_ml"], reverse=True)

    # Guardar cache (sin los objetos pipeline)
    señales_cache = [{k: v for k, v in s.items() if k != "pipeline"} for s in señales]
    try:
        with open(cache_path, "w") as f:
            json.dump(señales_cache, f)
    except:
        pass

    return señales_cache

def get_resumen_ml():
    """Resumen ML para el dashboard"""
    señales = get_señales_ml()
    return {
        "timestamp":  datetime.now().isoformat(),
        "n_señales":  len(señales),
        "compras":    len([s for s in señales if s["direccion"] == "ALZA"]),
        "ventas":     len([s for s in señales if s["direccion"] == "BAJA"]),
        "señales":    señales,
    }

if __name__ == "__main__":
    print("=== MOTOR ML TRADING ===\n")
    t0 = time.time()

    print("Entrenando modelos (esto puede tardar 2-3 min la primera vez)...")
    señales = get_señales_ml()

    print(f"\nModelos entrenados en {time.time()-t0:.1f}s")
    print(f"Señales ML generadas: {len(señales)}")

    for s in señales:
        icon = "🟢" if s["direccion"] == "ALZA" else "🔴"
        print(f"\n{icon} [{s['direccion']}] {s['activo']}")
        print(f"   Prob alza: {s['prob_alza']:.0%} | Accuracy: {s['accuracy']:.0%} | AUC: {s['auc']:.2f}")
        print(f"   {s['descripcion']}")
