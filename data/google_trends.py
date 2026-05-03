"""
Módulo Google Trends Chile
Analiza tendencias de búsqueda para anticipar movimientos de mercado.

Lógica:
- Aumento súbito en búsquedas de "SQM" o "litio" → posible noticia inminente
- Aumento en "dólar chile" → preocupación por tipo de cambio
- Aumento en "IPSA" o "bolsa chile" → mayor interés retail
- Spike > 2x promedio = señal de alerta
"""

from pytrends.request import TrendReq
from data.cache_helper import cache_get, cache_set
import pandas as pd
import numpy as np
from datetime import datetime
import time

# Grupos de búsqueda por activo
TERMINOS_ACTIVOS = {
    "SQM.SN": {
        "terminos": ["SQM", "litio chile", "lithium chile"],
        "nombre":   "SQM / Litio",
        "peso":     1.5,
    },
    "COPEC.SN": {
        "terminos": ["Copec", "bencina chile", "petroleo chile"],
        "nombre":   "Copec / Energía",
        "peso":     1.0,
    },
    "ECH": {
        "terminos": ["IPSA", "bolsa chile", "acciones chile"],
        "nombre":   "IPSA / Mercado Chile",
        "peso":     1.2,
    },
    "CLP/USD": {
        "terminos": ["dolar chile", "tipo de cambio", "peso chileno"],
        "nombre":   "Dólar / CLP",
        "peso":     1.3,
    },
    "BTC_LOCAL_SPREAD": {
        "terminos": ["bitcoin chile", "crypto chile", "BTC"],
        "nombre":   "Bitcoin Chile",
        "peso":     0.8,
    },
}

def get_trends(terminos, periodo="now 7-d", geo="CL"):
    """Obtiene datos de Google Trends para una lista de términos"""
    try:
        pt = TrendReq(hl="es-CL", tz=240, timeout=(10, 25))
        pt.build_payload(terminos[:5], timeframe=periodo, geo=geo)
        df = pt.interest_over_time()
        if df.empty:
            return None
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        return df
    except Exception as e:
        print(f"Error Trends {terminos}: {e}")
        return None

def analizar_grupo(activo, config, periodo="now 7-d"):
    """
    Analiza un grupo de términos para un activo.
    Detecta spikes y tendencias.
    """
    df = get_trends(config["terminos"], periodo=periodo)
    if df is None or df.empty:
        return None

    resultados = []
    for termino in config["terminos"]:
        if termino not in df.columns:
            continue

        serie = df[termino].astype(float)
        if len(serie) < 6:
            continue

        # Valor actual vs promedio
        actual   = float(serie.iloc[-2]) if len(serie) > 1 else float(serie.iloc[-1])
        promedio = float(serie[:-1].mean())
        maximo   = float(serie.max())

        if promedio == 0:
            continue

        ratio = actual / promedio if promedio > 0 else 1

        # Tendencia últimas 24h
        if len(serie) >= 24:
            tendencia_24h = float(serie.iloc[-24:].mean()) - float(serie.iloc[-48:-24].mean()) if len(serie) >= 48 else 0
        else:
            tendencia_24h = 0

        resultados.append({
            "termino":      termino,
            "actual":       round(actual, 1),
            "promedio":     round(promedio, 1),
            "maximo":       round(maximo, 1),
            "ratio":        round(ratio, 2),
            "tendencia_24h": round(tendencia_24h, 1),
        })

    if not resultados:
        return None

    # Señal consolidada del grupo
    ratio_max  = max(r["ratio"] for r in resultados)
    ratio_prom = sum(r["ratio"] for r in resultados) / len(resultados)
    tend_prom  = sum(r["tendencia_24h"] for r in resultados) / len(resultados)

    # Clasificar señal
    if ratio_max >= 3.0:
        señal     = "SPIKE EXTREMO"
        color     = "#ef4444"
        score     = 9
    elif ratio_max >= 2.0:
        señal     = "SPIKE ALTO"
        color     = "#f97316"
        score     = 6
    elif ratio_max >= 1.5:
        señal     = "ALZA MODERADA"
        color     = "#f59e0b"
        score     = 3
    elif tend_prom > 5:
        señal     = "TENDENCIA CRECIENTE"
        color     = "#22c55e"
        score     = 2
    else:
        señal     = "NORMAL"
        color     = "#475569"
        score     = 0

    return {
        "activo":         activo,
        "nombre":         config["nombre"],
        "señal":          señal,
        "color":          color,
        "score":          score,
        "ratio_max":      round(ratio_max, 2),
        "ratio_promedio": round(ratio_prom, 2),
        "tendencia_24h":  round(tend_prom, 1),
        "terminos":       resultados,
        "timestamp":      datetime.now().isoformat(),
    }

def get_trends_chile(periodo="now 7-d"):
    # Cache 60 minutos — Google Trends tiene rate limit
    cached = cache_get("google_trends", max_age_min=60)
    if cached:
        return cached

    """
    Analiza Google Trends para todos los activos chilenos.
    Retorna señales ordenadas por score.
    """
    resultados = []
    for activo, config in TERMINOS_ACTIVOS.items():
        resultado = analizar_grupo(activo, config, periodo)
        if resultado:
            resultados.append(resultado)
        time.sleep(1)  # Evitar rate limit de Google

    resultado = sorted(resultados, key=lambda x: x["score"], reverse=True)
    cache_set("google_trends", resultado)
    return resultado

def get_señales_trends(min_score=2):
    """
    Retorna señales de Trends compatibles con el motor de recomendaciones.
    """
    trends = get_trends_chile()
    señales = []
    for t in trends:
        if t["score"] >= min_score:
            # Mayor búsqueda = mayor atención = posible movimiento
            # No determina dirección, solo amplifica otras señales
            señales.append({
                "activo":    t["activo"],
                "nombre":    t["nombre"],
                "score":     t["score"],
                "ratio":     t["ratio_max"],
                "señal":     t["señal"],
                "descripcion": f"Google Trends: {t['nombre']} ratio {t['ratio_max']}x promedio — {t['señal']}",
            })
    return señales

def get_resumen_trends():
    """Resumen ejecutivo para el dashboard"""
    trends = get_trends_chile()
    alertas = [t for t in trends if t["score"] >= 2]
    return {
        "timestamp": datetime.now().isoformat(),
        "total":     len(trends),
        "alertas":   len(alertas),
        "trends":    trends,
    }

if __name__ == "__main__":
    print("=== GOOGLE TRENDS CHILE ===\n")
    trends = get_trends_chile()
    for t in trends:
        print(f"[{t['señal']}] {t['nombre']}")
        print(f"  Ratio: {t['ratio_max']}x | Tendencia 24h: {t['tendencia_24h']:+.1f}")
        for term in t["terminos"]:
            print(f"  '{term['termino']}': actual {term['actual']} | prom {term['promedio']} | ratio {term['ratio']}x")
        print()
