"""
Filtro de Tendencia Macro
Analiza el contexto macro global y por sector para filtrar señales.

Lógica:
- Si el mercado global está en tendencia bajista fuerte → no abrir largos
- Si VIX > 30 → reducir tamaño de posición al 50%
- Si sector está en tendencia bajista → requerir mayor convicción
- Si activo va contra la tendencia de su benchmark → señal más débil

Cobertura:
- Todos los activos del universo maestro
- Benchmarks por sector
- Indicadores macro globales
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import os, json, time

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "cache", "macro_filtro.json")

# ── BENCHMARKS POR SECTOR ─────────────────────────────────────────────────────
BENCHMARK_SECTOR = {
    "Bancos":            {"benchmark": "^TNX",    "relacion": "directa"},
    "Retail":            {"benchmark": "ECH",      "relacion": "directa"},
    "Energía":           {"benchmark": "CL=F",     "relacion": "directa"},
    "Minería":           {"benchmark": "HG=F",     "relacion": "directa"},
    "Inmobiliario":      {"benchmark": "^TNX",     "relacion": "inversa"},
    "Utilities":         {"benchmark": "^TNX",     "relacion": "inversa"},
    "Consumo":           {"benchmark": "ECH",      "relacion": "directa"},
    "Transporte":        {"benchmark": "CL=F",     "relacion": "inversa"},
    "Telecomunicaciones":{"benchmark": "ECH",      "relacion": "directa"},
    "Tecnología":        {"benchmark": "SPY",      "relacion": "directa"},
    "Financiero":        {"benchmark": "ECH",      "relacion": "directa"},
    "Industria":         {"benchmark": "ECH",      "relacion": "directa"},
    "Holding":           {"benchmark": "ECH",      "relacion": "directa"},
    "Construcción":      {"benchmark": "ECH",      "relacion": "directa"},
    "Salud":             {"benchmark": "SPY",      "relacion": "directa"},
    "ETF Chile":         {"benchmark": "ECH",      "relacion": "directa"},
    "ETF USA":           {"benchmark": "SPY",      "relacion": "directa"},
    "Renta Fija":        {"benchmark": "^TNX",     "relacion": "inversa"},
    "Commodity":         {"benchmark": "HG=F",     "relacion": "directa"},
    "Crypto":            {"benchmark": "BTC-USD",  "relacion": "directa"},
}

# ── INDICADORES MACRO ─────────────────────────────────────────────────────────
INDICADORES_MACRO = {
    "SPY":       "S&P 500",
    "ECH":       "IPSA ETF",
    "HG=F":      "Cobre",
    "^VIX":      "VIX",
    "^TNX":      "T10Y USA",
    "DX-Y.NYB":  "DXY",
    "CL=F":      "Petróleo",
    "GC=F":      "Oro",
}

def _calcular_tendencia(serie, periodo_corto=20, periodo_largo=60):
    """
    Calcula tendencia de una serie de precios.
    Retorna: score entre -3 (bajista fuerte) y +3 (alcista fuerte)
    """
    if len(serie) < periodo_largo:
        return 0, "NEUTRO"

    precio   = float(serie.iloc[-1])
    ma20     = float(serie.rolling(periodo_corto).mean().iloc[-1])
    ma60     = float(serie.rolling(periodo_largo).mean().iloc[-1])
    ret_5d   = float((serie.iloc[-1]/serie.iloc[-5]-1)*100)
    ret_20d  = float((serie.iloc[-1]/serie.iloc[-20]-1)*100)

    score = 0

    # Precio vs medias móviles
    if precio > ma20 > ma60:
        score += 2   # Tendencia alcista confirmada
    elif precio > ma20:
        score += 1   # Por encima de MA corta
    elif precio < ma20 < ma60:
        score -= 2   # Tendencia bajista confirmada
    elif precio < ma20:
        score -= 1   # Por debajo de MA corta

    # Momentum
    if ret_20d > 5:
        score += 1
    elif ret_20d < -5:
        score -= 1

    # Clasificar
    if score >= 2:
        return score, "ALCISTA FUERTE"
    elif score == 1:
        return score, "ALCISTA"
    elif score == 0:
        return score, "NEUTRO"
    elif score == -1:
        return score, "BAJISTA"
    else:
        return score, "BAJISTA FUERTE"

def get_contexto_macro():
    """
    Calcula el contexto macro actual para todos los indicadores.
    """
    try:
        if os.path.exists(CACHE_FILE):
            age_min = (time.time() - os.path.getmtime(CACHE_FILE)) / 60
            if age_min < 30:
                with open(CACHE_FILE) as f:
                    return json.load(f)
    except:
        pass

    contexto = {}

    for ticker, nombre in INDICADORES_MACRO.items():
        try:
            h = yf.Ticker(ticker).history(period="3mo")
            if h.empty:
                continue
            close = h["Close"]
            score, tendencia = _calcular_tendencia(close)

            precio  = float(close.iloc[-1])
            ret_5d  = float((close.iloc[-1]/close.iloc[-5]-1)*100) if len(close) >= 5 else 0
            ret_20d = float((close.iloc[-1]/close.iloc[-20]-1)*100) if len(close) >= 20 else 0

            contexto[ticker] = {
                "nombre":    nombre,
                "precio":    round(precio, 4),
                "score":     score,
                "tendencia": tendencia,
                "ret_5d":    round(ret_5d, 2),
                "ret_20d":   round(ret_20d, 2),
            }
        except:
            pass

    # VIX especial — invertido (VIX alto = malo para riesgo)
    if "^VIX" in contexto:
        vix_precio = contexto["^VIX"]["precio"]
        if vix_precio > 30:
            contexto["^VIX"]["alerta"] = "MIEDO EXTREMO"
            contexto["^VIX"]["reducir_sizing"] = True
        elif vix_precio > 20:
            contexto["^VIX"]["alerta"] = "VOLATILIDAD ALTA"
            contexto["^VIX"]["reducir_sizing"] = False
        else:
            contexto["^VIX"]["alerta"] = "NORMAL"
            contexto["^VIX"]["reducir_sizing"] = False

    contexto["timestamp"] = datetime.now().isoformat()

    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(contexto, f)
    except:
        pass

    return contexto

def evaluar_activo_vs_macro(yf_ticker, accion, sector=None):
    """
    Evalúa si una señal de trading es consistente con el contexto macro.

    Returns:
        dict con:
        - permitido: bool
        - ajuste_conviccion: int (puede ser negativo)
        - ajuste_sizing: float (1.0 = normal, 0.5 = reducir a la mitad)
        - razon: str
    """
    contexto = get_contexto_macro()

    ajuste_conv   = 0
    ajuste_sizing = 1.0
    razones       = []
    permitido     = True

    # ── VIX — Miedo extremo ───────────────────────────────────────────────────
    vix = contexto.get("^VIX", {})
    if vix.get("reducir_sizing"):
        ajuste_sizing *= 0.5
        razones.append(f"VIX {vix['precio']:.1f} — sizing reducido al 50%")

    vix_precio = vix.get("precio", 15)
    if vix_precio > 35:
        if accion == "COMPRAR":
            ajuste_conv -= 15
            razones.append(f"VIX extremo {vix_precio:.1f} — reducir largos")
    elif vix_precio < 15:
        if accion == "COMPRAR":
            ajuste_conv += 5
            razones.append(f"VIX bajo {vix_precio:.1f} — ambiente favorable")

    # ── SPY — Tendencia mercado USA ───────────────────────────────────────────
    spy = contexto.get("SPY", {})
    spy_score = spy.get("score", 0)

    if accion == "COMPRAR" and spy_score <= -2:
        ajuste_conv -= 10
        razones.append(f"SPY bajista fuerte — reducir largos")
    elif accion == "VENDER" and spy_score >= 2:
        ajuste_conv -= 5
        razones.append(f"SPY alcista — cortos más riesgosos")
    elif accion == "COMPRAR" and spy_score >= 2:
        ajuste_conv += 5
        razones.append(f"SPY alcista — favorece largos")

    # ── ECH — Tendencia mercado Chile ────────────────────────────────────────
    ech = contexto.get("ECH", {})
    ech_score = ech.get("score", 0)

    # Para acciones chilenas locales
    if sector and sector not in ("Crypto", "ETF USA", "Renta Fija"):
        if accion == "COMPRAR" and ech_score <= -2:
            ajuste_conv -= 10
            razones.append(f"ECH bajista fuerte — mercado Chile en caída")
        elif accion == "COMPRAR" and ech_score >= 1:
            ajuste_conv += 5
            razones.append(f"ECH alcista — Chile favorece largos")

    # ── BENCHMARK SECTOR ─────────────────────────────────────────────────────
    if sector and sector in BENCHMARK_SECTOR:
        bench_config  = BENCHMARK_SECTOR[sector]
        bench_ticker  = bench_config["benchmark"]
        bench_relacion= bench_config["relacion"]
        bench_data    = contexto.get(bench_ticker, {})
        bench_score   = bench_data.get("score", 0)

        if bench_relacion == "directa":
            # Benchmark sube → activo debería subir
            if accion == "COMPRAR" and bench_score >= 1:
                ajuste_conv += 5
                razones.append(f"Benchmark {bench_ticker} alcista — favorece {sector}")
            elif accion == "COMPRAR" and bench_score <= -2:
                ajuste_conv -= 10
                razones.append(f"Benchmark {bench_ticker} bajista — desfavorece {sector}")
        else:
            # Relación inversa (ej: tasas vs utilities)
            if accion == "COMPRAR" and bench_score <= -1:
                ajuste_conv += 5
                razones.append(f"Benchmark {bench_ticker} bajista → favorece {sector} (rel. inversa)")
            elif accion == "COMPRAR" and bench_score >= 2:
                ajuste_conv -= 8
                razones.append(f"Benchmark {bench_ticker} alcista → desfavorece {sector} (rel. inversa)")

    # ── DXY — Dólar index ────────────────────────────────────────────────────
    dxy = contexto.get("DX-Y.NYB", {})
    dxy_score = dxy.get("score", 0)

    # DXY fuerte → presión sobre emergentes y commodities
    if sector in ("Minería", "Commodity", "ETF Chile", "Acción Chile"):
        if accion == "COMPRAR" and dxy_score >= 2:
            ajuste_conv -= 5
            razones.append(f"DXY fuerte — presión sobre {sector}")
        elif accion == "COMPRAR" and dxy_score <= -1:
            ajuste_conv += 3
            razones.append(f"DXY débil — favorable para {sector}")

    return {
        "permitido":        permitido,
        "ajuste_conviccion": ajuste_conv,
        "ajuste_sizing":    ajuste_sizing,
        "razones":          razones,
        "contexto_macro":   {k: v.get("tendencia") for k, v in contexto.items() if k != "timestamp"},
    }

def get_resumen_macro():
    """Resumen del contexto macro para el dashboard"""
    contexto = get_contexto_macro()

    # Score global del mercado
    spy_score = contexto.get("SPY", {}).get("score", 0)
    ech_score = contexto.get("ECH", {}).get("score", 0)
    vix_precio = contexto.get("^VIX", {}).get("precio", 20)
    cobre_score = contexto.get("HG=F", {}).get("score", 0)

    score_global = (spy_score + ech_score + cobre_score) / 3

    if score_global >= 1.5:
        ambiente = "MUY FAVORABLE"
        color    = "#22c55e"
    elif score_global >= 0.5:
        ambiente = "FAVORABLE"
        color    = "#86efac"
    elif score_global >= -0.5:
        ambiente = "NEUTRO"
        color    = "#64748b"
    elif score_global >= -1.5:
        ambiente = "DESFAVORABLE"
        color    = "#f97316"
    else:
        ambiente = "MUY DESFAVORABLE"
        color    = "#ef4444"

    return {
        "timestamp":    contexto.get("timestamp", ""),
        "ambiente":     ambiente,
        "color":        color,
        "score_global": round(score_global, 2),
        "vix":          vix_precio,
        "indicadores":  contexto,
        "recomendacion": "Operar con tamaño normal" if score_global >= 0 else "Reducir tamaño de posiciones",
    }

if __name__ == "__main__":
    print("=== FILTRO MACRO ===\n")

    resumen = get_resumen_macro()
    print(f"Ambiente: {resumen['ambiente']} (score: {resumen['score_global']:+.2f})")
    print(f"VIX: {resumen['vix']:.1f}")
    print(f"Recomendación: {resumen['recomendacion']}")

    print("\nIndicadores:")
    for ticker, datos in resumen["indicadores"].items():
        if ticker == "timestamp":
            continue
        if isinstance(datos, dict):
            print(f"  {datos.get('nombre',''):<20} {datos.get('tendencia',''):>20} ret20d:{datos.get('ret_20d',0):+.1f}%")

    print("\n=== TEST EVALUACIÓN POR ACTIVO ===")
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.universo import UNIVERSO_COMPLETO
    for yf_ticker, info in list(UNIVERSO_COMPLETO.items())[:10]:
        eval_compra = evaluar_activo_vs_macro(yf_ticker, "COMPRAR", info.get("sector"))
        adj = eval_compra["ajuste_conviccion"]
        sizing = eval_compra["ajuste_sizing"]
        if adj != 0 or sizing != 1.0:
            print(f"  {info['nombre']:<25} adj_conv:{adj:+d} sizing:{sizing:.1f}x {eval_compra['razones'][0] if eval_compra['razones'] else ''}")
