"""
Cobertura completa mercado accionario chileno.
- IPSA 30: las 30 acciones del índice principal
- Small caps: 20 acciones de menor capitalización pero líquidas
- Análisis técnico integrado para cada acción
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ── IPSA 30 COMPLETO ──────────────────────────────────────────────────────────
IPSA_30 = {
    "SQM-B.SN":     {"nombre": "SQM",              "sector": "Minería",        "peso": 9.5},
    "COPEC.SN":     {"nombre": "Copec",             "sector": "Energía",        "peso": 8.2},
    "BCI.SN":       {"nombre": "Banco BCI",         "sector": "Bancos",         "peso": 7.8},
    "BSANTANDER.SN":{"nombre": "Santander Chile",   "sector": "Bancos",         "peso": 7.1},
    "CHILE.SN":     {"nombre": "Banco de Chile",    "sector": "Bancos",         "peso": 6.9},
    "FALABELLA.SN": {"nombre": "Falabella",         "sector": "Retail",         "peso": 5.8},
    "CENCOSUD.SN":  {"nombre": "Cencosud",          "sector": "Retail",         "peso": 4.9},
    "CMPC.SN":      {"nombre": "CMPC",              "sector": "Industria",      "peso": 4.7},
    "COLBUN.SN":    {"nombre": "Colbún",            "sector": "Energía",        "peso": 3.8},
    "ENELCHILE.SN": {"nombre": "Enel Chile",        "sector": "Energía",        "peso": 3.5},
    "ENELAM.SN":    {"nombre": "Enel Américas",     "sector": "Energía",        "peso": 3.2},
    "ENTEL.SN":     {"nombre": "Entel",             "sector": "Telecomunicaciones","peso": 2.9},
    "LTM.SN":       {"nombre": "LATAM Airlines",    "sector": "Transporte",     "peso": 2.8},
    "CAP.SN":       {"nombre": "CAP",               "sector": "Minería",        "peso": 2.5},
    "CCU.SN":       {"nombre": "CCU",               "sector": "Consumo",        "peso": 2.4},
    "ITAUCL.SN":    {"nombre": "Itaú Chile",        "sector": "Bancos",         "peso": 2.2},
    "PARAUCO.SN":   {"nombre": "Parque Arauco",     "sector": "Inmobiliario",   "peso": 2.0},
    "MALLPLAZA.SN": {"nombre": "Mall Plaza",        "sector": "Inmobiliario",   "peso": 1.9},
    "RIPLEY.SN":    {"nombre": "Ripley",            "sector": "Retail",         "peso": 1.8},
    "AGUAS-A.SN":   {"nombre": "Aguas Andinas",     "sector": "Utilities",      "peso": 1.7},
    "VAPORES.SN":   {"nombre": "CSAV",              "sector": "Transporte",     "peso": 1.6},
    "ANDINA-B.SN":  {"nombre": "Andina",            "sector": "Consumo",        "peso": 1.5},
    "ILC.SN":       {"nombre": "ILC",               "sector": "Financiero",     "peso": 1.4},
    "CONCHATORO.SN":{"nombre": "Concha y Toro",     "sector": "Consumo",        "peso": 1.3},
    "FORUS.SN":     {"nombre": "Forus",             "sector": "Retail",         "peso": 1.2},
    "SMU.SN":       {"nombre": "SMU",               "sector": "Retail",         "peso": 1.1},
    "ECL.SN":       {"nombre": "ECL",               "sector": "Energía",        "peso": 1.0},
    "SONDA.SN":     {"nombre": "Sonda",             "sector": "Tecnología",     "peso": 0.9},
}

# ── SMALL CAPS CHILENOS ───────────────────────────────────────────────────────
SMALL_CAPS = {
    "BESALCO.SN":   {"nombre": "Besalco",           "sector": "Construcción"},
    "SALFACORP.SN": {"nombre": "Salfacorp",         "sector": "Construcción"},
    "CFR.SN":       {"nombre": "CFR Pharma",        "sector": "Salud"},
    "SOCOVESA.SN":  {"nombre": "Socovesa",          "sector": "Inmobiliario"},
    "INGEVEC.SN":   {"nombre": "Ingevec",           "sector": "Construcción"},
    "HITES.SN":     {"nombre": "Hites",             "sector": "Retail"},
    "MOLYMET.SN":   {"nombre": "Molymet",           "sector": "Minería"},
    "QUINENCO.SN":  {"nombre": "Quiñenco",          "sector": "Holding"},
    "MASISA.SN":    {"nombre": "Masisa",            "sector": "Industria"},
    "ENDESA.SN":    {"nombre": "Endesa Chile",      "sector": "Energía"},
    "BANMEDICA.SN": {"nombre": "Bánmedica",         "sector": "Salud"},
    "HABITAT.SN":   {"nombre": "AFP Habitat",       "sector": "Financiero"},
    "PROVIDA.SN":   {"nombre": "AFP Provida",       "sector": "Financiero"},
    "SCHWAGER.SN":  {"nombre": "Schwager",          "sector": "Industria"},
    "MARINSA.SN":   {"nombre": "Marinsa",           "sector": "Transporte"},
}

# ── ANÁLISIS TÉCNICO RÁPIDO ───────────────────────────────────────────────────
def analizar_accion(ticker, info, periodo="3mo"):
    """Análisis técnico rápido para una acción"""
    try:
        h = yf.Ticker(ticker).history(period=periodo)
        if len(h) < 20:
            return None

        close  = h["Close"]
        volume = h["Volume"]

        precio    = float(close.iloc[-1])
        precio_1d = float(close.iloc[-2]) if len(close) > 1 else precio
        precio_5d = float(close.iloc[-5]) if len(close) > 4 else precio
        precio_20d= float(close.iloc[-20]) if len(close) > 19 else precio

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
        hist_prev = float((macd - signal).iloc[-2])

        # Bollinger
        sma20  = close.rolling(20).mean()
        std20  = close.rolling(20).std()
        bb_up  = float((sma20 + 2*std20).iloc[-1])
        bb_low = float((sma20 - 2*std20).iloc[-1])
        pct_b  = (precio - bb_low) / (bb_up - bb_low) if (bb_up - bb_low) > 0 else 0.5

        # Volumen
        vol_actual = float(volume.iloc[-1])
        vol_prom   = float(volume.rolling(20).mean().iloc[-1])
        vol_ratio  = vol_actual / vol_prom if vol_prom > 0 else 1

        # Retornos
        ret_1d  = (precio / precio_1d - 1) * 100
        ret_5d  = (precio / precio_5d - 1) * 100
        ret_20d = (precio / precio_20d - 1) * 100

        # MA
        ma20 = float(sma20.iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20

        # ── SEÑAL ────────────────────────────────────────────────────────────
        puntos_alza = 0
        puntos_baja = 0
        señales = []

        if rsi < 30:
            puntos_alza += 3
            señales.append(f"RSI {rsi:.1f} sobreventa")
        elif rsi < 40:
            puntos_alza += 1
            señales.append(f"RSI {rsi:.1f} zona baja")
        elif rsi > 70:
            puntos_baja += 3
            señales.append(f"RSI {rsi:.1f} sobrecompra")
        elif rsi > 60:
            puntos_baja += 1
            señales.append(f"RSI {rsi:.1f} zona alta")

        if hist > 0 and hist_prev <= 0:
            puntos_alza += 2
            señales.append("MACD cruce alcista")
        elif hist < 0 and hist_prev >= 0:
            puntos_baja += 2
            señales.append("MACD cruce bajista")

        if pct_b < 0.05:
            puntos_alza += 2
            señales.append("Precio en banda inferior BB")
        elif pct_b > 0.95:
            puntos_baja += 2
            señales.append("Precio en banda superior BB")

        if precio > ma20 > ma50:
            puntos_alza += 1
            señales.append("Sobre MA20 y MA50")
        elif precio < ma20 < ma50:
            puntos_baja += 1
            señales.append("Bajo MA20 y MA50")

        if vol_ratio >= 2:
            if ret_1d > 0:
                puntos_alza += 2
                señales.append(f"Volumen {vol_ratio:.1f}x + alza")
            else:
                puntos_baja += 2
                señales.append(f"Volumen {vol_ratio:.1f}x + baja")
        elif vol_ratio < 0.4:
            # Volumen muy bajo — reducir puntos
            puntos_alza = max(0, puntos_alza - 1)
            puntos_baja = max(0, puntos_baja - 1)
            señales.append(f"Volumen bajo {vol_ratio:.1f}x — señal débil")

        # Filtro liquidez mínima
        if vol_prom < 500:
            return None

        # Dirección
        if puntos_alza > puntos_baja and puntos_alza >= 2:
            accion    = "COMPRAR"
            direccion = "ALZA"
            puntos    = puntos_alza
        elif puntos_baja > puntos_alza and puntos_baja >= 2:
            accion    = "VENDER"
            direccion = "BAJA"
            puntos    = puntos_baja
        else:
            accion    = "MANTENER"
            direccion = "NEUTRO"
            puntos    = 0

        conviccion = min(50 + puntos * 8, 92) if puntos > 0 else 0

        # ATR para SL/TP
        tr = pd.concat([
            h["High"] - h["Low"],
            (h["High"] - close.shift()).abs(),
            (h["Low"] - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = float(tr.ewm(com=13, adjust=False).mean().iloc[-1])

        if accion == "COMPRAR":
            sl = round(precio - atr * 1.5, 2)
            tp = round(precio + atr * 3.0, 2)
        elif accion == "VENDER":
            sl = round(precio + atr * 1.5, 2)
            tp = round(precio - atr * 3.0, 2)
        else:
            sl = tp = None

        return {
            "ticker":     ticker,
            "nombre":     info.get("nombre", ticker),
            "sector":     info.get("sector", ""),
            "peso_ipsa":  info.get("peso", 0),
            "precio":     round(precio, 2),
            "accion":     accion,
            "direccion":  direccion,
            "conviccion": round(conviccion, 1),
            "puntos":     puntos,
            "sl":         sl,
            "tp":         tp,
            "atr":        round(atr, 2),
            "indicadores": {
                "rsi":       round(rsi, 2),
                "macd_hist": round(hist, 4),
                "pct_b":     round(pct_b, 3),
                "ma20":      round(ma20, 2),
                "ma50":      round(ma50, 2),
                "vol_ratio": round(vol_ratio, 2),
                "ret_1d":    round(ret_1d, 2),
                "ret_5d":    round(ret_5d, 2),
                "ret_20d":   round(ret_20d, 2),
            },
            "señales":    señales,
            "timestamp":  datetime.now().isoformat(),
        }
    except Exception as e:
        return None

def get_analisis_ipsa_completo(incluir_small_caps=True, min_conviccion=0):
    """
    Análisis técnico completo de IPSA 30 + small caps.
    Retorna lista ordenada por convicción.
    """
    import concurrent.futures

    todos_tickers = {**IPSA_30}
    if incluir_small_caps:
        todos_tickers.update(SMALL_CAPS)

    resultados = []

    def analizar(item):
        ticker, info = item
        return analizar_accion(ticker, info)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(analizar, item): item for item in todos_tickers.items()}
        for future in concurrent.futures.as_completed(futures):
            resultado = future.result()
            if resultado and resultado["conviccion"] >= min_conviccion:
                resultados.append(resultado)

    return sorted(resultados, key=lambda x: x["conviccion"], reverse=True)

def get_señales_ipsa(min_conviccion=65):
    """Señales de trading del IPSA para el motor"""
    todos = get_analisis_ipsa_completo(min_conviccion=min_conviccion)
    return [a for a in todos if a["accion"] != "MANTENER"]

def get_resumen_mercado_local():
    """Resumen del mercado local para el dashboard"""
    todos = get_analisis_ipsa_completo(min_conviccion=0)
    subiendo  = [a for a in todos if a["indicadores"]["ret_1d"] > 0]
    bajando   = [a for a in todos if a["indicadores"]["ret_1d"] < 0]
    señales   = [a for a in todos if a["accion"] != "MANTENER" and a["conviccion"] >= 65]
    compras   = [a for a in señales if a["accion"] == "COMPRAR"]
    ventas    = [a for a in señales if a["accion"] == "VENDER"]

    return {
        "timestamp":  datetime.now().isoformat(),
        "total":      len(todos),
        "subiendo":   len(subiendo),
        "bajando":    len(bajando),
        "señales":    len(señales),
        "compras":    len(compras),
        "ventas":     len(ventas),
        "top_alzas":  sorted(todos, key=lambda x: x["indicadores"]["ret_1d"], reverse=True)[:5],
        "top_bajas":  sorted(todos, key=lambda x: x["indicadores"]["ret_1d"])[:5],
        "top_señales": señales[:10],
        "todos":      todos,
    }

if __name__ == "__main__":
    print("=== ANÁLISIS IPSA 30 + SMALL CAPS ===\n")
    import time
    t0 = time.time()
    resumen = get_resumen_mercado_local()
    elapsed = time.time() - t0

    print(f"Analizados: {resumen['total']} acciones en {elapsed:.1f}s")
    print(f"Subiendo: {resumen['subiendo']} | Bajando: {resumen['bajando']}")
    print(f"Señales: {resumen['señales']} (Compras: {resumen['compras']} | Ventas: {resumen['ventas']})")

    if resumen["top_señales"]:
        print("\n--- SEÑALES DESTACADAS ---")
        for s in resumen["top_señales"][:5]:
            print(f"[{s['accion']}] {s['nombre']:<20} Conv:{s['conviccion']}% RSI:{s['indicadores']['rsi']:.1f} Ret5d:{s['indicadores']['ret_5d']:+.2f}%")
            print(f"  {' | '.join(s['señales'][:3])}")
