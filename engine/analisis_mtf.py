"""
Análisis Multi-Timeframe (MTF)
Combina señales de 1h, 4h y D1 para mayor precisión.

Lógica:
- D1: tendencia principal (peso 40%)
- H4: momentum y confirmación (peso 35%)
- H1: timing de entrada (peso 25%)

Señal MTF de alta convicción = las 3 alineadas en misma dirección
Bonus de convicción:
- 3/3 alineados: +25%
- 2/3 alineados: +10%
- 1/3 o contradictorios: sin bonus
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import concurrent.futures

# Universo de activos para MTF
ACTIVOS_MTF = {
    "SQM":      {"nombre": "SQM ADR",       "activo_motor": "SQM.SN"},
    "ECH":      {"nombre": "IPSA ETF",       "activo_motor": "ECH"},
    "COPEC.SN": {"nombre": "Copec",          "activo_motor": "COPEC.SN"},
    "BTC-USD":  {"nombre": "Bitcoin",        "activo_motor": "BTC_LOCAL_SPREAD"},
    "GC=F":     {"nombre": "Oro",            "activo_motor": "GC=F"},
    "HG=F":     {"nombre": "Cobre",          "activo_motor": "HG=F"},
    "SPY":      {"nombre": "S&P 500 ETF",    "activo_motor": "^GSPC"},
    "BCI.SN":   {"nombre": "Banco BCI",      "activo_motor": "BCI.SN"},
    "CHILE.SN": {"nombre": "Banco de Chile", "activo_motor": "CHILE.SN"},
}

TIMEFRAMES = {
    "1h":  {"periodo": "60d",  "peso": 0.25, "label": "1 Hora"},
    "4h":  {"periodo": "60d",  "peso": 0.35, "label": "4 Horas"},
    "1d":  {"periodo": "6mo",  "peso": 0.40, "label": "Diario"},
}

# ── INDICADORES ───────────────────────────────────────────────────────────────
def _calcular_señal_tf(h):
    """Calcula señal técnica para un timeframe específico"""
    if len(h) < 20:
        return None

    close = h["Close"]

    # RSI
    delta = close.diff()
    g = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    p = (-delta).clip(lower=0).ewm(com=13, adjust=False).mean()
    rsi = float(100 - (100 / (1 + g/p)).iloc[-1])

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal= macd.ewm(span=9, adjust=False).mean()
    hist  = float((macd - signal).iloc[-1])
    hist_prev = float((macd - signal).iloc[-2]) if len(h) > 1 else hist

    # Bollinger
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_up = float((sma20 + 2*std20).iloc[-1])
    bb_lo = float((sma20 - 2*std20).iloc[-1])
    precio = float(close.iloc[-1])
    pct_b = (precio - bb_lo) / (bb_up - bb_lo) if (bb_up - bb_lo) > 0 else 0.5

    # MA
    ma20 = float(sma20.iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(h) >= 50 else ma20

    # Puntos por dirección
    puntos_alza = 0
    puntos_baja = 0
    señales = []

    # RSI
    if rsi < 30:
        puntos_alza += 3; señales.append(f"RSI {rsi:.1f} sobreventa")
    elif rsi < 40:
        puntos_alza += 1; señales.append(f"RSI {rsi:.1f} zona baja")
    elif rsi > 70:
        puntos_baja += 3; señales.append(f"RSI {rsi:.1f} sobrecompra")
    elif rsi > 60:
        puntos_baja += 1; señales.append(f"RSI {rsi:.1f} zona alta")

    # MACD cruce
    if hist > 0 and hist_prev <= 0:
        puntos_alza += 2; señales.append("MACD cruce alcista")
    elif hist < 0 and hist_prev >= 0:
        puntos_baja += 2; señales.append("MACD cruce bajista")
    elif hist > 0:
        puntos_alza += 1; señales.append("MACD positivo")
    elif hist < 0:
        puntos_baja += 1; señales.append("MACD negativo")

    # Bollinger
    if pct_b < 0.1:
        puntos_alza += 2; señales.append("Banda inferior BB")
    elif pct_b > 0.9:
        puntos_baja += 2; señales.append("Banda superior BB")

    # MA
    if precio > ma20 > ma50:
        puntos_alza += 1; señales.append("Sobre MA20/MA50")
    elif precio < ma20 < ma50:
        puntos_baja += 1; señales.append("Bajo MA20/MA50")

    # Dirección
    if puntos_alza > puntos_baja and puntos_alza >= 2:
        direccion = "ALZA"
        puntos    = puntos_alza
    elif puntos_baja > puntos_alza and puntos_baja >= 2:
        direccion = "BAJA"
        puntos    = puntos_baja
    else:
        direccion = "NEUTRO"
        puntos    = 0

    return {
        "direccion": direccion,
        "puntos":    puntos,
        "rsi":       round(rsi, 1),
        "macd_hist": round(hist, 4),
        "pct_b":     round(pct_b, 3),
        "ma20":      round(ma20, 4),
        "ma50":      round(ma50, 4),
        "precio":    round(precio, 4),
        "señales":   señales,
    }

# ── ANÁLISIS MTF ──────────────────────────────────────────────────────────────
def analizar_mtf(ticker, info):
    """
    Análisis multi-timeframe completo para un activo.
    Combina D1, H4 y H1.
    """
    try:
        resultados_tf = {}

        for tf, config in TIMEFRAMES.items():
            try:
                h = yf.Ticker(ticker).history(
                    period=config["periodo"],
                    interval=tf
                )
                if len(h) < 20:
                    continue
                señal = _calcular_señal_tf(h)
                if señal:
                    resultados_tf[tf] = {**señal, "peso": config["peso"], "label": config["label"]}
            except:
                continue

        if not resultados_tf:
            return None

        # Contar alineación de timeframes
        direcciones = [r["direccion"] for r in resultados_tf.values() if r["direccion"] != "NEUTRO"]
        n_alza = direcciones.count("ALZA")
        n_baja = direcciones.count("BAJA")
        n_total = len(direcciones)

        # Determinar dirección MTF ponderada
        score_alza = sum(r["puntos"] * r["peso"] for r in resultados_tf.values() if r["direccion"] == "ALZA")
        score_baja = sum(r["puntos"] * r["peso"] for r in resultados_tf.values() if r["direccion"] == "BAJA")

        if score_alza > score_baja and score_alza >= 1:
            direccion_mtf = "ALZA"
            accion_mtf    = "COMPRAR"
            score_total   = score_alza
            n_alineados   = n_alza
        elif score_baja > score_alza and score_baja >= 1:
            direccion_mtf = "BAJA"
            accion_mtf    = "VENDER"
            score_total   = score_baja
            n_alineados   = n_baja
        else:
            direccion_mtf = "NEUTRO"
            accion_mtf    = "MANTENER"
            score_total   = 0
            n_alineados   = 0

        # Convicción base + bonus por alineación
        conviccion_base = min(50 + score_total * 8, 85)

        if n_alineados == 3:
            bonus         = 25
            alineacion    = "PERFECTA (3/3)"
            color_alin    = "#22c55e"
        elif n_alineados == 2:
            bonus         = 10
            alineacion    = "BUENA (2/3)"
            color_alin    = "#f59e0b"
        else:
            bonus         = 0
            alineacion    = "DÉBIL (1/3)"
            color_alin    = "#ef4444"

        conviccion_mtf = min(conviccion_base + bonus, 95) if score_total > 0 else 0

        # Precio actual (desde D1)
        precio = resultados_tf.get("1d", {}).get("precio") or resultados_tf.get("4h", {}).get("precio") or 0

        return {
            "ticker":        ticker,
            "nombre":        info.get("nombre", ticker),
            "activo_motor":  info.get("activo_motor", ticker),
            "precio":        precio,
            "accion":        accion_mtf,
            "direccion":     direccion_mtf,
            "conviccion":    round(conviccion_mtf, 1),
            "alineacion":    alineacion,
            "color_alin":    color_alin,
            "n_alineados":   n_alineados,
            "bonus_conv":    bonus,
            "timeframes":    resultados_tf,
            "timestamp":     datetime.now().isoformat(),
        }

    except Exception as e:
        return None

def get_señales_mtf(min_conviccion=65, solo_alineados=False):
    """
    Analiza todos los activos en múltiples timeframes.
    Retorna señales ordenadas por convicción.
    """
    resultados = []

    def analizar(item):
        ticker, info = item
        return analizar_mtf(ticker, info)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(analizar, item): item for item in ACTIVOS_MTF.items()}
        for future in concurrent.futures.as_completed(futures):
            resultado = future.result()
            if resultado and resultado["conviccion"] >= min_conviccion:
                if solo_alineados and resultado["n_alineados"] < 2:
                    continue
                if resultado["accion"] != "MANTENER":
                    resultados.append(resultado)

    return sorted(resultados, key=lambda x: x["conviccion"], reverse=True)

def get_resumen_mtf():
    """Resumen MTF para el dashboard"""
    todos = []
    def analizar(item):
        return analizar_mtf(*item) if len(item) == 2 else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(analizar_mtf, t, i): (t,i) for t,i in ACTIVOS_MTF.items()}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            if r:
                todos.append(r)

    perfectos = [r for r in todos if r["n_alineados"] == 3 and r["accion"] != "MANTENER"]
    buenos    = [r for r in todos if r["n_alineados"] == 2 and r["accion"] != "MANTENER"]

    return {
        "timestamp":  datetime.now().isoformat(),
        "total":      len(todos),
        "perfectos":  len(perfectos),
        "buenos":     len(buenos),
        "señales":    sorted(perfectos + buenos, key=lambda x: x["conviccion"], reverse=True),
        "todos":      sorted(todos, key=lambda x: x["conviccion"], reverse=True),
    }

if __name__ == "__main__":
    import time
    print("=== ANÁLISIS MULTI-TIMEFRAME ===\n")
    t0 = time.time()
    resumen = get_resumen_mtf()
    elapsed = time.time() - t0

    print(f"Analizados: {resumen['total']} activos en {elapsed:.1f}s")
    print(f"Perfectamente alineados (3/3): {resumen['perfectos']}")
    print(f"Bien alineados (2/3): {resumen['buenos']}")

    if resumen["señales"]:
        print("\n--- SEÑALES MTF ---")
        for s in resumen["señales"]:
            print(f"\n[{s['accion']}] {s['nombre']} — Conv: {s['conviccion']}% | {s['alineacion']}")
            for tf, datos in s["timeframes"].items():
                icon = "↑" if datos["direccion"]=="ALZA" else ("↓" if datos["direccion"]=="BAJA" else "→")
                print(f"  {datos['label']:<10} {icon} RSI:{datos['rsi']:5.1f} MACD:{datos['macd_hist']:+.4f} — {', '.join(datos['señales'][:2])}")
