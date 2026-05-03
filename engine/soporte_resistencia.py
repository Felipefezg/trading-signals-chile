"""
Módulo de Soporte y Resistencia Automático.
Detecta niveles clave usando múltiples métodos:

1. Máximos/mínimos locales (pivots) — niveles donde el precio rebotó
2. Fibonacci Retracement — niveles 23.6%, 38.2%, 50%, 61.8%
3. Niveles redondos — precios psicológicos (100, 500, 1000, etc.)
4. VWAP semanal — precio promedio ponderado por volumen

Uso principal:
- Calibrar SL/TP en niveles reales del mercado
- Identificar zonas de alta probabilidad de rebote
- Detectar cuando el precio está cerca de un nivel clave
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# Universo de activos
ACTIVOS_SR = {
    "SQM":      "SQM ADR",
    "ECH":      "IPSA ETF",
    "COPEC.SN": "Copec",
    "BTC-USD":  "Bitcoin",
    "GC=F":     "Oro",
    "HG=F":     "Cobre",
    "SPY":      "S&P 500",
    "BCI.SN":   "Banco BCI",
    "CHILE.SN": "Banco de Chile",
    "FALABELLA.SN": "Falabella",
    "CENCOSUD.SN":  "Cencosud",
}

# ── PIVOTS (máximos/mínimos locales) ─────────────────────────────────────────
def detectar_pivots(h, ventana=5, n_niveles=5):
    """
    Detecta máximos y mínimos locales significativos.
    Un pivot es un punto donde el precio revirtió dirección.
    """
    highs = h["High"]
    lows  = h["Low"]

    # Pivot high: máximo local en ventana de 'ventana' velas
    pivot_highs = []
    pivot_lows  = []

    for i in range(ventana, len(h) - ventana):
        # Pivot high
        if highs.iloc[i] == highs.iloc[i-ventana:i+ventana+1].max():
            pivot_highs.append(float(highs.iloc[i]))
        # Pivot low
        if lows.iloc[i] == lows.iloc[i-ventana:i+ventana+1].min():
            pivot_lows.append(float(lows.iloc[i]))

    # Eliminar niveles muy cercanos (agrupar en clusters)
    def agrupar_niveles(niveles, tolerancia_pct=0.01):
        if not niveles:
            return []
        niveles = sorted(set(niveles))
        agrupados = [niveles[0]]
        for n in niveles[1:]:
            if abs(n - agrupados[-1]) / agrupados[-1] > tolerancia_pct:
                agrupados.append(n)
        return agrupados

    resistencias = agrupar_niveles(sorted(pivot_highs, reverse=True))[:n_niveles]
    soportes     = agrupar_niveles(sorted(pivot_lows))[:n_niveles]

    return resistencias, soportes

# ── FIBONACCI ─────────────────────────────────────────────────────────────────
def calcular_fibonacci(h, periodo=60):
    """
    Calcula niveles de Fibonacci Retracement.
    Usa el rango máximo-mínimo del período.
    """
    h_periodo = h.tail(periodo)
    maximo = float(h_periodo["High"].max())
    minimo = float(h_periodo["Low"].min())
    rango  = maximo - minimo

    niveles_fib = {
        "0.0%":   round(maximo, 4),
        "23.6%":  round(maximo - 0.236 * rango, 4),
        "38.2%":  round(maximo - 0.382 * rango, 4),
        "50.0%":  round(maximo - 0.500 * rango, 4),
        "61.8%":  round(maximo - 0.618 * rango, 4),
        "78.6%":  round(maximo - 0.786 * rango, 4),
        "100.0%": round(minimo, 4),
    }

    return niveles_fib, maximo, minimo

# ── NIVELES PSICOLÓGICOS ──────────────────────────────────────────────────────
def niveles_psicologicos(precio_actual, n=3):
    """
    Detecta niveles redondos cercanos al precio actual.
    Los traders concentran órdenes en números redondos.
    """
    # Determinar magnitud del precio
    if precio_actual > 50000:
        step = 5000
    elif precio_actual > 5000:
        step = 500
    elif precio_actual > 500:
        step = 50
    elif precio_actual > 50:
        step = 5
    elif precio_actual > 5:
        step = 0.5
    else:
        step = 0.1

    base = round(precio_actual / step) * step
    niveles = []
    for i in range(-n, n+1):
        niveles.append(round(base + i * step, 4))

    return sorted(niveles)

# ── ANÁLISIS COMPLETO ─────────────────────────────────────────────────────────
def analizar_soporte_resistencia(ticker, nombre=None, periodo="6mo"):
    """
    Análisis completo de soporte y resistencia para un activo.
    """
    try:
        h = yf.Ticker(ticker).history(period=periodo)
        if len(h) < 30:
            return None

        precio_actual = float(h["Close"].iloc[-1])

        # 1. Pivots
        resistencias_pivot, soportes_pivot = detectar_pivots(h, ventana=5, n_niveles=5)

        # 2. Fibonacci
        niveles_fib, maximo, minimo = calcular_fibonacci(h)

        # 3. Niveles psicológicos
        niv_psicologicos = niveles_psicologicos(precio_actual)

        # Combinar y clasificar todos los niveles
        todos_resistencias = []
        todos_soportes     = []

        for nivel in resistencias_pivot:
            if nivel > precio_actual * 1.001:
                distancia_pct = (nivel - precio_actual) / precio_actual * 100
                todos_resistencias.append({
                    "nivel":        round(nivel, 4),
                    "tipo":         "Pivot",
                    "distancia_pct": round(distancia_pct, 2),
                    "fuerza":       "ALTA",
                })

        for nivel in soportes_pivot:
            if nivel < precio_actual * 0.999:
                distancia_pct = (precio_actual - nivel) / precio_actual * 100
                todos_soportes.append({
                    "nivel":        round(nivel, 4),
                    "tipo":         "Pivot",
                    "distancia_pct": round(distancia_pct, 2),
                    "fuerza":       "ALTA",
                })

        # Agregar Fibonacci
        for pct, nivel in niveles_fib.items():
            if nivel > precio_actual * 1.001:
                dist = (nivel - precio_actual) / precio_actual * 100
                todos_resistencias.append({
                    "nivel":        nivel,
                    "tipo":         f"Fib {pct}",
                    "distancia_pct": round(dist, 2),
                    "fuerza":       "MEDIA",
                })
            elif nivel < precio_actual * 0.999:
                dist = (precio_actual - nivel) / precio_actual * 100
                todos_soportes.append({
                    "nivel":        nivel,
                    "tipo":         f"Fib {pct}",
                    "distancia_pct": round(dist, 2),
                    "fuerza":       "MEDIA",
                })

        # Agregar psicológicos
        for nivel in niv_psicologicos:
            if nivel > precio_actual * 1.001:
                dist = (nivel - precio_actual) / precio_actual * 100
                todos_resistencias.append({
                    "nivel":        nivel,
                    "tipo":         "Psicológico",
                    "distancia_pct": round(dist, 2),
                    "fuerza":       "MEDIA",
                })
            elif nivel < precio_actual * 0.999:
                dist = (precio_actual - nivel) / precio_actual * 100
                todos_soportes.append({
                    "nivel":        nivel,
                    "tipo":         "Psicológico",
                    "distancia_pct": round(dist, 2),
                    "fuerza":       "MEDIA",
                })

        # Ordenar por cercanía al precio
        todos_resistencias = sorted(todos_resistencias, key=lambda x: x["distancia_pct"])[:5]
        todos_soportes     = sorted(todos_soportes,     key=lambda x: x["distancia_pct"])[:5]

        # Resistencia y soporte más cercanos
        res_cercana = todos_resistencias[0] if todos_resistencias else None
        sop_cercano = todos_soportes[0]     if todos_soportes     else None

        # Señal: ¿está el precio cerca de un nivel clave?
        señal = "NEUTRO"
        if res_cercana and res_cercana["distancia_pct"] < 1.5:
            señal = "CERCA_RESISTENCIA"  # Posible rechazo → vender
        elif sop_cercano and sop_cercano["distancia_pct"] < 1.5:
            señal = "CERCA_SOPORTE"      # Posible rebote → comprar

        return {
            "ticker":        ticker,
            "nombre":        nombre or ticker,
            "precio_actual": round(precio_actual, 4),
            "resistencias":  todos_resistencias,
            "soportes":      todos_soportes,
            "res_cercana":   res_cercana,
            "sop_cercano":   sop_cercano,
            "fibonacci":     niveles_fib,
            "maximo_6m":     round(maximo, 4),
            "minimo_6m":     round(minimo, 4),
            "señal":         señal,
            "timestamp":     datetime.now().isoformat(),
        }

    except Exception as e:
        return None

# ── SL/TP CALIBRADO ───────────────────────────────────────────────────────────
def calcular_sl_tp_calibrado(ticker, accion, precio_actual, atr=None):
    """
    Calcula SL/TP usando niveles de soporte/resistencia reales.
    Más preciso que el método basado solo en ATR.
    """
    analisis = analizar_soporte_resistencia(ticker)
    if not analisis:
        return None, None

    if accion == "COMPRAR":
        # SL debajo del soporte más cercano
        sop = analisis["sop_cercano"]
        res = analisis["res_cercana"]
        if sop:
            sl = round(sop["nivel"] * 0.99, 4)  # 1% debajo del soporte
        elif atr:
            sl = round(precio_actual - atr * 1.5, 4)
        else:
            sl = round(precio_actual * 0.95, 4)

        if res:
            tp = round(res["nivel"] * 0.99, 4)  # 1% debajo de la resistencia
        elif atr:
            tp = round(precio_actual + atr * 3.0, 4)
        else:
            tp = round(precio_actual * 1.08, 4)

    else:  # VENDER
        # SL encima de la resistencia más cercana
        res = analisis["res_cercana"]
        sop = analisis["sop_cercano"]
        if res:
            sl = round(res["nivel"] * 1.01, 4)  # 1% sobre la resistencia
        elif atr:
            sl = round(precio_actual + atr * 1.5, 4)
        else:
            sl = round(precio_actual * 1.05, 4)

        if sop:
            tp = round(sop["nivel"] * 1.01, 4)  # 1% sobre el soporte
        elif atr:
            tp = round(precio_actual - atr * 3.0, 4)
        else:
            tp = round(precio_actual * 0.92, 4)

    return sl, tp

def get_resumen_sr(tickers=None):
    """Resumen de soporte/resistencia para el dashboard"""
    if tickers is None:
        tickers = list(ACTIVOS_SR.keys())

    import concurrent.futures
    resultados = []

    def analizar(item):
        ticker, nombre = item
        return analizar_soporte_resistencia(ticker, nombre)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(analizar, item): item
                  for item in ACTIVOS_SR.items() if item[0] in tickers}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            if r:
                resultados.append(r)

    alertas = [r for r in resultados if r["señal"] != "NEUTRO"]

    return {
        "timestamp": datetime.now().isoformat(),
        "total":     len(resultados),
        "alertas":   len(alertas),
        "niveles":   sorted(resultados, key=lambda x: x["ticker"]),
        "alertas_detalle": alertas,
    }

if __name__ == "__main__":
    import time
    print("=== SOPORTE Y RESISTENCIA ===\n")
    t0 = time.time()

    for ticker, nombre in list(ACTIVOS_SR.items())[:5]:
        r = analizar_soporte_resistencia(ticker, nombre)
        if not r:
            continue
        print(f"\n{nombre} ({ticker}) — ${r['precio_actual']:,.2f}")
        if r["res_cercana"]:
            print(f"  Resistencia más cercana: {r['res_cercana']['nivel']:,.2f} "
                  f"({r['res_cercana']['distancia_pct']:+.2f}%) [{r['res_cercana']['tipo']}]")
        if r["sop_cercano"]:
            print(f"  Soporte más cercano:     {r['sop_cercano']['nivel']:,.2f} "
                  f"({r['sop_cercano']['distancia_pct']:+.2f}%) [{r['sop_cercano']['tipo']}]")
        if r["señal"] != "NEUTRO":
            print(f"  ⚠️  SEÑAL: {r['señal']}")

        # SL/TP calibrado
        sl, tp = calcular_sl_tp_calibrado(ticker, "VENDER", r["precio_actual"])
        if sl and tp:
            print(f"  SL/TP calibrado (VENDER): SL={sl:,.2f} TP={tp:,.2f}")

    print(f"\nTiempo: {time.time()-t0:.1f}s")
