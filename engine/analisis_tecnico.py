"""
Módulo de Análisis Técnico
Genera señales de trading basadas en indicadores técnicos clásicos.

Indicadores:
- RSI: sobrecompra (>70) / sobreventa (<30)
- MACD: momentum y cruces de señal
- Bollinger Bands: reversión a la media
- Medias móviles 20/50 días: tendencia
- ATR: volatilidad para calibrar SL/TP
- Volumen: confirmación de señales

Genera señales compatibles con el motor de recomendaciones.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# Universo de activos — importado desde universo maestro
from engine.universo import get_tickers_at, UNIVERSO_COMPLETO

def _build_universo_at():
    u = get_tickers_at()
    return {yf: {"nombre": v["nombre"], "activo_motor": yf} for yf, v in u.items()}

UNIVERSO_AT = _build_universo_at()

# ── INDICADORES ───────────────────────────────────────────────────────────────
def calcular_rsi(precios, periodo=14):
    delta  = precios.diff()
    ganancia = delta.clip(lower=0)
    perdida  = (-delta).clip(lower=0)
    avg_g = ganancia.ewm(com=periodo-1, adjust=False).mean()
    avg_p = perdida.ewm(com=periodo-1, adjust=False).mean()
    rs    = avg_g / avg_p
    return 100 - (100 / (1 + rs))

def calcular_macd(precios, rapida=12, lenta=26, señal=9):
    ema_r  = precios.ewm(span=rapida, adjust=False).mean()
    ema_l  = precios.ewm(span=lenta,  adjust=False).mean()
    macd   = ema_r - ema_l
    signal = macd.ewm(span=señal, adjust=False).mean()
    hist   = macd - signal
    return macd, signal, hist

def calcular_bollinger(precios, periodo=20, std=2):
    sma    = precios.rolling(periodo).mean()
    desvio = precios.rolling(periodo).std()
    upper  = sma + std * desvio
    lower  = sma - std * desvio
    pct_b  = (precios - lower) / (upper - lower)
    return upper, sma, lower, pct_b

def calcular_atr(high, low, close, periodo=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=periodo-1, adjust=False).mean()

def calcular_medias(precios):
    ma20 = precios.rolling(20).mean()
    ma50 = precios.rolling(50).mean()
    return ma20, ma50

# ── ANÁLISIS COMPLETO ─────────────────────────────────────────────────────────
def analizar_activo(ticker, periodo="6mo"):
    """
    Análisis técnico completo de un activo.
    Retorna dict con indicadores y señal consolidada.
    """
    try:
        h = yf.Ticker(ticker).history(period=periodo)
        if len(h) < 50:
            return None

        close  = h["Close"]
        high   = h["High"]
        low    = h["Low"]
        volume = h["Volume"]

        # Calcular indicadores
        rsi          = calcular_rsi(close)
        macd, signal_macd, hist_macd = calcular_macd(close)
        bb_upper, bb_mid, bb_lower, pct_b = calcular_bollinger(close)
        atr          = calcular_atr(high, low, close)
        ma20, ma50   = calcular_medias(close)

        # Valores actuales
        precio_act   = float(close.iloc[-1])
        rsi_act      = float(rsi.iloc[-1])
        macd_act     = float(macd.iloc[-1])
        signal_act   = float(signal_macd.iloc[-1])
        hist_act     = float(hist_macd.iloc[-1])
        hist_prev    = float(hist_macd.iloc[-2])
        pct_b_act    = float(pct_b.iloc[-1])
        atr_act      = float(atr.iloc[-1])
        ma20_act     = float(ma20.iloc[-1])
        ma50_act     = float(ma50.iloc[-1])
        vol_act      = float(volume.iloc[-1])
        vol_prom     = float(volume.rolling(20).mean().iloc[-1])
        vol_ratio    = vol_act / vol_prom if vol_prom > 0 else 1

        # Retornos
        ret_1d  = float((close.iloc[-1] / close.iloc[-2] - 1) * 100)
        ret_5d  = float((close.iloc[-1] / close.iloc[-5] - 1) * 100)
        ret_20d = float((close.iloc[-1] / close.iloc[-20] - 1) * 100)

        # ── SEÑALES INDIVIDUALES ──────────────────────────────────────────────
        señales = []

        # RSI
        if rsi_act < 30:
            señales.append({"indicador": "RSI", "direccion": "ALZA",
                           "fuerza": min((30 - rsi_act) / 10, 3),
                           "descripcion": f"RSI {rsi_act:.1f} — sobreventa extrema"})
        elif rsi_act < 40:
            señales.append({"indicador": "RSI", "direccion": "ALZA",
                           "fuerza": 1,
                           "descripcion": f"RSI {rsi_act:.1f} — zona de sobreventa"})
        elif rsi_act > 70:
            señales.append({"indicador": "RSI", "direccion": "BAJA",
                           "fuerza": min((rsi_act - 70) / 10, 3),
                           "descripcion": f"RSI {rsi_act:.1f} — sobrecompra extrema"})
        elif rsi_act > 60:
            señales.append({"indicador": "RSI", "direccion": "BAJA",
                           "fuerza": 1,
                           "descripcion": f"RSI {rsi_act:.1f} — zona de sobrecompra"})

        # MACD — cruce de señal
        if hist_act > 0 and hist_prev <= 0:
            señales.append({"indicador": "MACD", "direccion": "ALZA",
                           "fuerza": 2,
                           "descripcion": f"MACD cruce alcista — histograma {hist_act:.4f}"})
        elif hist_act < 0 and hist_prev >= 0:
            señales.append({"indicador": "MACD", "direccion": "BAJA",
                           "fuerza": 2,
                           "descripcion": f"MACD cruce bajista — histograma {hist_act:.4f}"})
        elif hist_act > 0 and macd_act > 0:
            señales.append({"indicador": "MACD", "direccion": "ALZA",
                           "fuerza": 1,
                           "descripcion": f"MACD positivo y creciente"})
        elif hist_act < 0 and macd_act < 0:
            señales.append({"indicador": "MACD", "direccion": "BAJA",
                           "fuerza": 1,
                           "descripcion": f"MACD negativo y decreciente"})

        # Bollinger Bands
        if pct_b_act < 0.05:
            señales.append({"indicador": "Bollinger", "direccion": "ALZA",
                           "fuerza": 2,
                           "descripcion": f"Precio tocó banda inferior BB — reversión esperada"})
        elif pct_b_act < 0.2:
            señales.append({"indicador": "Bollinger", "direccion": "ALZA",
                           "fuerza": 1,
                           "descripcion": f"Precio cerca de banda inferior BB ({pct_b_act:.2f})"})
        elif pct_b_act > 0.95:
            señales.append({"indicador": "Bollinger", "direccion": "BAJA",
                           "fuerza": 2,
                           "descripcion": f"Precio tocó banda superior BB — reversión esperada"})
        elif pct_b_act > 0.8:
            señales.append({"indicador": "Bollinger", "direccion": "BAJA",
                           "fuerza": 1,
                           "descripcion": f"Precio cerca de banda superior BB ({pct_b_act:.2f})"})

        # Medias móviles — cruce dorado/muerte
        if ma20_act > ma50_act and precio_act > ma20_act:
            señales.append({"indicador": "MA", "direccion": "ALZA",
                           "fuerza": 1,
                           "descripcion": f"Precio sobre MA20 y MA50 — tendencia alcista"})
        elif ma20_act < ma50_act and precio_act < ma20_act:
            señales.append({"indicador": "MA", "direccion": "BAJA",
                           "fuerza": 1,
                           "descripcion": f"Precio bajo MA20 y MA50 — tendencia bajista"})

        # Volumen anormal confirma señal
        # Volumen: bonus si alto, penalización si muy bajo
        if vol_ratio >= 2.0:
            vol_bonus = 1.0   # Volumen alto confirma señal
        elif vol_ratio >= 1.2:
            vol_bonus = 0.3   # Volumen moderado
        elif vol_ratio < 0.5:
            vol_bonus = -2.0  # Volumen muy bajo → señal no confiable
        else:
            vol_bonus = 0

        # Filtro de liquidez mínima — no operar activos sin volumen
        if vol_prom < 1000 and vol_act < 1000:
            return None  # Sin liquidez suficiente

        # ── CONSOLIDAR SEÑAL ──────────────────────────────────────────────────
        puntos_alza = sum(s["fuerza"] for s in señales if s["direccion"] == "ALZA")
        puntos_baja = sum(s["fuerza"] for s in señales if s["direccion"] == "BAJA")

        if puntos_alza > puntos_baja and puntos_alza >= 2:
            direccion_final = "ALZA"
            accion_final    = "COMPRAR"
            puntos_total    = puntos_alza
        elif puntos_baja > puntos_alza and puntos_baja >= 2:
            direccion_final = "BAJA"
            accion_final    = "VENDER"
            puntos_total    = puntos_baja
        else:
            direccion_final = "NEUTRO"
            accion_final    = "MANTENER"
            puntos_total    = 0

        # Convicción basada en puntos y confirmación de volumen
        conviccion = min(50 + puntos_total * 10 + vol_bonus * 10, 95) if puntos_total > 0 else 0

        # SL/TP basado en ATR
        sl_dist = atr_act * 2.0
        tp_dist = atr_act * 3.5
        if accion_final == "COMPRAR":
            sl = round(precio_act - sl_dist, 4)
            tp = round(precio_act + tp_dist, 4)
        elif accion_final == "VENDER":
            sl = round(precio_act + sl_dist, 4)
            tp = round(precio_act - tp_dist, 4)
        else:
            sl = tp = None

        return {
            "ticker":         ticker,
            "nombre":         UNIVERSO_AT.get(ticker, {}).get("nombre", ticker),
            "activo_motor":   UNIVERSO_AT.get(ticker, {}).get("activo_motor", ticker),
            "precio":         round(precio_act, 4),
            "accion":         accion_final,
            "direccion":      direccion_final,
            "conviccion":     round(conviccion, 1),
            "puntos":         puntos_total,
            "sl":             sl,
            "tp":             tp,
            "atr":            round(atr_act, 4),
            "indicadores": {
                "rsi":        round(rsi_act, 2),
                "macd":       round(macd_act, 4),
                "macd_hist":  round(hist_act, 4),
                "pct_b":      round(pct_b_act, 3),
                "ma20":       round(ma20_act, 4),
                "ma50":       round(ma50_act, 4),
                "vol_ratio":  round(vol_ratio, 2),
                "ret_1d":     round(ret_1d, 2),
                "ret_5d":     round(ret_5d, 2),
                "ret_20d":    round(ret_20d, 2),
            },
            "señales":        señales,
            "timestamp":      datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"Error analizando {ticker}: {e}")
        return None

def get_señales_tecnicas(min_conviccion=60):
    """
    Analiza todos los activos y retorna señales técnicas.
    Compatible con el motor de recomendaciones.
    """
    resultados = []
    for ticker in UNIVERSO_AT:
        analisis = analizar_activo(ticker)
        if analisis and analisis["conviccion"] >= min_conviccion and analisis["accion"] != "MANTENER":
            resultados.append(analisis)

    return sorted(resultados, key=lambda x: x["conviccion"], reverse=True)

def get_analisis_completo():
    """Análisis completo de todos los activos para el dashboard"""
    resultados = []
    for ticker in UNIVERSO_AT:
        analisis = analizar_activo(ticker)
        if analisis:
            resultados.append(analisis)
    return sorted(resultados, key=lambda x: abs(x["conviccion"]), reverse=True)

if __name__ == "__main__":
    print("=== ANÁLISIS TÉCNICO ===\n")
    señales = get_señales_tecnicas(min_conviccion=55)

    if señales:
        print(f"Señales generadas: {len(señales)}\n")
        for s in señales:
            print(f"[{s['accion']}] {s['nombre']} ({s['ticker']})")
            print(f"  Precio: {s['precio']:,.2f} | Convicción: {s['conviccion']}%")
            print(f"  RSI: {s['indicadores']['rsi']:.1f} | MACD hist: {s['indicadores']['macd_hist']:.4f} | %B: {s['indicadores']['pct_b']:.2f}")
            print(f"  Ret 1d: {s['indicadores']['ret_1d']:+.2f}% | Ret 5d: {s['indicadores']['ret_5d']:+.2f}%")
            if s['sl'] and s['tp']:
                print(f"  SL: {s['sl']:,.2f} | TP: {s['tp']:,.2f}")
            print(f"  Señales: {', '.join(s2['descripcion'] for s2 in s['señales'])}")
            print()
    else:
        print("Sin señales técnicas en este momento")

    print("\n=== TODOS LOS ACTIVOS ===")
    todos = get_analisis_completo()
    for a in todos:
        icon = "↑" if a["direccion"]=="ALZA" else ("↓" if a["direccion"]=="BAJA" else "→")
        print(f"{icon} {a['nombre']:<20} RSI:{a['indicadores']['rsi']:5.1f} | MACD:{a['indicadores']['macd_hist']:+.4f} | %B:{a['indicadores']['pct_b']:.2f} | Conv:{a['conviccion']}%")
