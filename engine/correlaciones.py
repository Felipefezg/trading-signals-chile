"""
Correlaciones Dinámicas y Arbitraje
Analiza correlaciones entre todos los activos del universo maestro.

Detecta:
1. Divergencias — activos que normalmente correlacionan pero se separan
2. Convergencias — activos que normalmente no correlacionan pero se juntan
3. Pares de arbitraje — spreads históricos que se han expandido
4. Rotación sectorial — sectores ganando/perdiendo correlación con el mercado

Metodología:
- Correlación histórica (6 meses) vs correlación reciente (30 días)
- Divergencia > 0.25 = señal de trading
- Rolling correlation para detectar cambios en tiempo real
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import concurrent.futures
import os, json, time

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "cache", "correlaciones.json")

# ── PARES DE CORRELACIÓN CONOCIDA ─────────────────────────────────────────────
# Definidos con correlación esperada histórica para detectar divergencias
PARES_CONOCIDOS = [
    # Acciones Chile vs commodities
    ("SQM-B.SN",    "HG=F",     "SQM vs Cobre",         0.75),
    ("SQM",         "HG=F",     "SQM ADR vs Cobre",      0.75),
    ("COPEC.SN",    "CL=F",     "Copec vs Petróleo",     0.70),
    ("ENELCHILE.SN","CL=F",     "Enel Chile vs Petróleo",0.55),
    ("CAP.SN",      "HG=F",     "CAP vs Cobre",          0.65),
    # ETF Chile vs mercado
    ("ECH",         "HG=F",     "ECH vs Cobre",          0.72),
    ("ECH",         "SPY",      "ECH vs S&P 500",        0.68),
    ("ECH",         "CL=F",     "ECH vs Petróleo",       0.55),
    # Bancos vs tasas
    ("CHILE.SN",    "^TNX",     "Banco Chile vs T10Y",   0.45),
    ("BSANTANDER.SN","^TNX",    "Santander vs T10Y",     0.45),
    ("BCI.SN",      "^TNX",     "BCI vs T10Y",           0.45),
    # Crypto vs oro
    ("BTC-USD",     "GC=F",     "BTC vs Oro",            0.40),
    ("BTC-USD",     "SPY",      "BTC vs S&P 500",        0.55),
    # Retail vs consumo
    ("FALABELLA.SN","CENCOSUD.SN","Falabella vs Cencosud",0.80),
    ("RIPLEY.SN",   "FALABELLA.SN","Ripley vs Falabella", 0.75),
    # Energía
    ("COLBUN.SN",   "ENELCHILE.SN","Colbún vs Enel Chile",0.70),
    ("ENELAM.SN",   "ENELCHILE.SN","Enel Am vs Enel Chile",0.85),
    # Cross-asset
    ("ECH",         "BTC-USD",  "ECH vs BTC",            0.35),
    ("GC=F",        "^TNX",     "Oro vs T10Y",           -0.60),
    ("SPY",         "^TNX",     "S&P 500 vs T10Y",       -0.45),
]

# ── CARGA DE DATOS ────────────────────────────────────────────────────────────
def _cargar_precios(tickers, periodo="6mo"):
    """Carga precios para lista de tickers en paralelo"""
    precios = {}

    def cargar(ticker):
        try:
            h = yf.Ticker(ticker).history(period=periodo)["Close"]
            if not h.empty:
                return ticker, h
        except:
            pass
        return ticker, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(cargar, t): t for t in tickers}
        for future in concurrent.futures.as_completed(futures):
            ticker, serie = future.result()
            if serie is not None:
                precios[ticker] = serie

    return precios

# ── ANÁLISIS DE CORRELACIONES ─────────────────────────────────────────────────
def analizar_par(t1, t2, nombre, corr_esperada, precios):
    """Analiza correlación entre dos activos"""
    if t1 not in precios or t2 not in precios:
        return None

    df = pd.DataFrame({"a": precios[t1], "b": precios[t2]}).dropna()
    if len(df) < 30:
        return None

    # Correlaciones por período
    corr_6m  = float(df["a"].corr(df["b"]))
    corr_30d = float(df.tail(30)["a"].corr(df.tail(30)["b"]))
    corr_10d = float(df.tail(10)["a"].corr(df.tail(10)["b"]))

    # Divergencia respecto al histórico esperado
    div_30d = abs(corr_esperada - corr_30d)
    div_10d = abs(corr_esperada - corr_10d)

    # Retornos recientes
    ret_t1_5d = float((df["a"].iloc[-1] / df["a"].iloc[-5] - 1) * 100) if len(df) >= 5 else 0
    ret_t2_5d = float((df["b"].iloc[-1] / df["b"].iloc[-5] - 1) * 100) if len(df) >= 5 else 0
    spread_retornos = abs(ret_t1_5d - ret_t2_5d)

    # Clasificar señal
    if div_30d > 0.35 and spread_retornos > 3:
        tipo  = "DIVERGENCIA FUERTE"
        score = 4
        color = "#ef4444"
    elif div_30d > 0.25:
        tipo  = "DIVERGENCIA MODERADA"
        score = 3
        color = "#f97316"
    elif div_30d > 0.15:
        tipo  = "DIVERGENCIA LEVE"
        score = 2
        color = "#f59e0b"
    elif abs(corr_6m) > 0.7 and abs(corr_30d) < 0.3:
        tipo  = "DESACOPLAMIENTO"
        score = 4
        color = "#ef4444"
    else:
        tipo  = "NORMAL"
        score = 0
        color = "#22c55e"

    # Dirección del trade de arbitraje
    # Si T1 bajó más que T2 (o subió menos) → COMPRAR T1, VENDER T2
    if score >= 2:
        if ret_t1_5d < ret_t2_5d:
            accion_t1 = "COMPRAR"
            accion_t2 = "VENDER"
            descripcion = f"{nombre}: {t1} rezagado vs {t2} → convergencia esperada"
        else:
            accion_t1 = "VENDER"
            accion_t2 = "COMPRAR"
            descripcion = f"{nombre}: {t1} adelantado vs {t2} → convergencia esperada"
    else:
        accion_t1 = accion_t2 = None
        descripcion = f"{nombre}: correlación normal"

    return {
        "par":           nombre,
        "ticker1":       t1,
        "ticker2":       t2,
        "corr_esperada": round(corr_esperada, 2),
        "corr_6m":       round(corr_6m, 3),
        "corr_30d":      round(corr_30d, 3),
        "corr_10d":      round(corr_10d, 3),
        "divergencia":   round(div_30d, 3),
        "ret_t1_5d":     round(ret_t1_5d, 2),
        "ret_t2_5d":     round(ret_t2_5d, 2),
        "spread_retornos": round(spread_retornos, 2),
        "tipo":          tipo,
        "score":         score,
        "color":         color,
        "accion_t1":     accion_t1,
        "accion_t2":     accion_t2,
        "descripcion":   descripcion,
        "timestamp":     datetime.now().isoformat(),
    }

# ── ANÁLISIS UNIVERSO COMPLETO ────────────────────────────────────────────────
def analizar_correlaciones_universo():
    """
    Analiza correlaciones para todo el universo de activos.
    Incluye pares conocidos + matriz de correlación completa.
    """
    # Obtener todos los tickers únicos
    tickers_unicos = list(set(
        [p[0] for p in PARES_CONOCIDOS] +
        [p[1] for p in PARES_CONOCIDOS]
    ))

    # Agregar universo maestro completo
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.universo import UNIVERSO_COMPLETO
    tickers_unicos += [v["yf"] for v in UNIVERSO_COMPLETO.values()]
    tickers_unicos  = list(set(tickers_unicos))

    print(f"  Cargando precios de {len(tickers_unicos)} activos...")
    precios = _cargar_precios(tickers_unicos)
    print(f"  Precios disponibles: {len(precios)}/{len(tickers_unicos)}")

    # Generar pares dinámicos desde el universo completo
    # Combinar cada acción chilena con sus benchmarks naturales
    pares_dinamicos = []
    benchmarks = {
        "Acción Chile":     [("ECH", 0.70), ("HG=F", 0.50), ("SPY", 0.55)],
        "Acción USA/Chile": [("ECH", 0.75), ("SPY", 0.65), ("HG=F", 0.55)],
        "ETF":              [("SPY", 0.80), ("ECH", 0.60)],
        "Futuro":           [("SPY", 0.45), ("GC=F", 0.50)],
        "Crypto":           [("SPY", 0.55), ("GC=F", 0.40)],
    }
    try:
        from engine.universo import UNIVERSO_COMPLETO
        for yf_ticker, info in UNIVERSO_COMPLETO.items():
            tipo = info.get("tipo", "")
            for benchmark, corr_esp in benchmarks.get(tipo, []):
                if yf_ticker != benchmark and benchmark in precios:
                    nombre = f"{info['nombre']} vs {benchmark}"
                    pares_dinamicos.append((yf_ticker, benchmark, nombre, corr_esp))
    except:
        pass

    todos_pares = PARES_CONOCIDOS + pares_dinamicos

    # Analizar pares conocidos
    resultados_pares = []
    for t1, t2, nombre, corr_esp in todos_pares:
        r = analizar_par(t1, t2, nombre, corr_esp, precios)
        if r:
            resultados_pares.append(r)

    # Matriz de correlación del universo completo
    tickers_disponibles = [t for t in precios if t in precios]
    if len(tickers_disponibles) >= 5:
        df_precios = pd.DataFrame({t: precios[t] for t in tickers_disponibles}).dropna()
        if len(df_precios) >= 20:
            matriz_corr = df_precios.pct_change().corr()
        else:
            matriz_corr = pd.DataFrame()
    else:
        matriz_corr = pd.DataFrame()

    return {
        "pares":       resultados_pares,
        "matriz_corr": matriz_corr,
        "n_activos":   len(precios),
        "timestamp":   datetime.now().isoformat(),
    }

def get_señales_correlacion(min_score=2):
    """
    Retorna señales de arbitraje para el motor de recomendaciones.
    """
    # Cache 30 minutos
    try:
        if os.path.exists(CACHE_FILE):
            age_min = (time.time() - os.path.getmtime(CACHE_FILE)) / 60
            if age_min < 30:
                with open(CACHE_FILE) as f:
                    data = json.load(f)
                pares = data.get("pares", [])
                señales = _extraer_señales(pares, min_score)
                return señales
    except:
        pass

    resultado = analizar_correlaciones_universo()
    pares = resultado["pares"]

    # Guardar cache (sin la matriz que no es serializable)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"pares": pares, "timestamp": resultado["timestamp"]}, f)
    except:
        pass

    return _extraer_señales(pares, min_score)

def _extraer_señales(pares, min_score):
    señales = []
    for p in pares:
        if p.get("score", 0) >= min_score and p.get("accion_t1"):
            señales.append({
                "activo":      p["ticker1"],
                "fuente":      "Correlación",
                "score":       p["score"],
                "direccion":   "ALZA" if p["accion_t1"] == "COMPRAR" else "BAJA",
                "descripcion": p["descripcion"][:80],
                "par":         p["par"],
            })
    return sorted(señales, key=lambda x: x["score"], reverse=True)

def get_resumen_correlaciones():
    """Resumen completo para el dashboard"""
    resultado = analizar_correlaciones_universo()
    pares     = resultado["pares"]
    alertas   = [p for p in pares if p["score"] >= 2]

    return {
        "timestamp":  resultado["timestamp"],
        "n_pares":    len(pares),
        "n_alertas":  len(alertas),
        "alertas":    sorted(alertas, key=lambda x: x["score"], reverse=True),
        "todos":      sorted(pares, key=lambda x: x["score"], reverse=True),
        "n_activos":  resultado["n_activos"],
    }

if __name__ == "__main__":
    print("=== CORRELACIONES DINÁMICAS ===\n")
    t0 = time.time()
    resumen = get_resumen_correlaciones()

    print(f"Activos analizados: {resumen['n_activos']}")
    print(f"Pares monitoreados: {resumen['n_pares']}")
    print(f"Alertas activas:    {resumen['n_alertas']}")

    if resumen["alertas"]:
        print("\n--- DIVERGENCIAS DETECTADAS ---")
        for p in resumen["alertas"]:
            print(f"\n[{p['tipo']}] {p['par']} — Score: {p['score']}")
            print(f"  Corr esperada: {p['corr_esperada']:+.2f} | "
                  f"Corr 30d: {p['corr_30d']:+.2f} | "
                  f"Divergencia: {p['divergencia']:.2f}")
            print(f"  Ret 5d: {p['ticker1']}={p['ret_t1_5d']:+.2f}% | "
                  f"{p['ticker2']}={p['ret_t2_5d']:+.2f}%")
            if p['accion_t1']:
                print(f"  Trade: {p['accion_t1']} {p['ticker1']} / "
                      f"{p['accion_t2']} {p['ticker2']}")
    else:
        print("\nSin divergencias significativas")

    print(f"\nTiempo: {time.time()-t0:.1f}s")
