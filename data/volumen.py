"""
Módulo de detección de volumen anormal en acciones IPSA.
Detecta cuando una acción transa significativamente más volumen
que su promedio histórico — señal de actividad inusual.

Lógica:
- Calcular volumen promedio 20 días
- Comparar con volumen actual
- Ratio > 2x → ALERTA
- Ratio > 3x → ALERTA ALTA
- Correlacionar con hechos CMF y noticias
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# Universo IPSA con tickers Yahoo Finance
IPSA_TICKERS = {
    "SQM-B.SN":      "SQM",
    "COPEC.SN":      "Copec",
    "BCI.SN":        "Banco BCI",
    "BSANTANDER.SN": "Santander Chile",
    "CHILE.SN":      "Banco de Chile",
    "FALABELLA.SN":  "Falabella",
    "CENCOSUD.SN":   "Cencosud",
    "CMPC.SN":       "CMPC",
    "COLBUN.SN":     "Colbún",
    "ENELCHILE.SN":  "Enel Chile",
    "ENELAM.SN":     "Enel Américas",
    "ENTEL.SN":      "Entel",
    "LTM.SN":        "LATAM Airlines",
    "CAP.SN":        "CAP",
    "CCU.SN":        "CCU",
    "ITAUCL.SN":     "Itaú Chile",
    "PARAUCO.SN":    "Parque Arauco",
    "MALLPLAZA.SN":  "Mall Plaza",
    "RIPLEY.SN":     "Ripley",
    "AGUAS-A.SN":    "Aguas Andinas",
    "ECH":           "IPSA ETF (ECH)",
    "SQM":           "SQM (NYSE)",
}

# Umbrales de alerta
UMBRAL_ALERTA      = 2.0   # 2x volumen promedio
UMBRAL_ALERTA_ALTA = 3.0   # 3x volumen promedio
PERIODO_PROMEDIO   = 20    # días para calcular promedio

def get_volumen_anormal(tickers=None, periodo_dias=30):
    """
    Detecta volumen anormal en acciones del IPSA.

    Args:
        tickers: lista de tickers a analizar (None = todos)
        periodo_dias: días de historia para calcular promedio

    Returns:
        Lista de dicts con alertas de volumen ordenadas por ratio
    """
    if tickers is None:
        tickers = list(IPSA_TICKERS.keys())

    alertas = []
    normales = []

    for ticker in tickers:
        nombre = IPSA_TICKERS.get(ticker, ticker)
        try:
            h = yf.Ticker(ticker).history(period=f"{periodo_dias}d")
            if len(h) < 5:
                continue

            vol_actual = float(h["Volume"].iloc[-1])
            if vol_actual == 0:
                continue

            # Volumen promedio (excluyendo hoy)
            vol_historico = h["Volume"].iloc[:-1]
            vol_promedio  = float(vol_historico.mean())
            vol_std       = float(vol_historico.std())

            if vol_promedio == 0:
                continue

            ratio = vol_actual / vol_promedio

            # Precio y variación
            precio_actual   = float(h["Close"].iloc[-1])
            precio_anterior = float(h["Close"].iloc[-2]) if len(h) >= 2 else precio_actual
            var_pct         = ((precio_actual / precio_anterior) - 1) * 100

            # Clasificar alerta
            if ratio >= UMBRAL_ALERTA_ALTA:
                nivel = "ALTA"
                color = "#ef4444"
            elif ratio >= UMBRAL_ALERTA:
                nivel = "MEDIA"
                color = "#f59e0b"
            else:
                nivel = "NORMAL"
                color = "#475569"

            # Señal combinada precio + volumen
            if ratio >= UMBRAL_ALERTA:
                if var_pct > 0:
                    señal = "ACUMULACIÓN"   # volumen alto + precio sube → compradores
                    señal_color = "#22c55e"
                elif var_pct < 0:
                    señal = "DISTRIBUCIÓN"  # volumen alto + precio baja → vendedores
                    señal_color = "#ef4444"
                else:
                    señal = "ACTIVIDAD"     # volumen alto + precio plano → indecisión
                    señal_color = "#f59e0b"
            else:
                señal = "NORMAL"
                señal_color = "#475569"

            dato = {
                "ticker":        ticker,
                "nombre":        nombre,
                "precio":        round(precio_actual, 2),
                "var_pct":       round(var_pct, 2),
                "vol_actual":    int(vol_actual),
                "vol_promedio":  int(vol_promedio),
                "ratio":         round(ratio, 2),
                "nivel":         nivel,
                "color":         color,
                "señal":         señal,
                "señal_color":   señal_color,
                "timestamp":     datetime.now().isoformat(),
            }

            if ratio >= UMBRAL_ALERTA:
                alertas.append(dato)
            else:
                normales.append(dato)

        except Exception as e:
            continue

    # Ordenar por ratio descendente
    alertas  = sorted(alertas,  key=lambda x: x["ratio"], reverse=True)
    normales = sorted(normales, key=lambda x: x["ratio"], reverse=True)

    return alertas + normales

def get_resumen_volumen():
    """Resumen ejecutivo de volumen anormal para el dashboard"""
    todos   = get_volumen_anormal()
    alertas = [a for a in todos if a["nivel"] in ("ALTA", "MEDIA")]
    altas   = [a for a in todos if a["nivel"] == "ALTA"]

    return {
        "timestamp":       datetime.now().isoformat(),
        "total_analizados": len(todos),
        "alertas":         len(alertas),
        "alertas_altas":   len(altas),
        "top_alertas":     alertas[:5],
        "todos":           todos,
    }

def correlacionar_con_cmf(alertas_volumen):
    """
    Correlaciona alertas de volumen con hechos esenciales CMF.
    Si hay hecho esencial + volumen anormal → señal de muy alta convicción.
    """
    try:
        from data.cmf import get_hechos_esenciales
        hechos = get_hechos_esenciales(limit=100)
    except:
        return alertas_volumen

    # Crear mapa ticker → hechos CMF
    hechos_por_ticker = {}
    for h in hechos:
        ticker = h.get("ticker_ipsa")
        if ticker:
            if ticker not in hechos_por_ticker:
                hechos_por_ticker[ticker] = []
            hechos_por_ticker[ticker].append(h)

    # Correlacionar
    for alerta in alertas_volumen:
        ticker_base = alerta["ticker"].replace(".SN","").replace("-B","").replace("-A","")
        hechos_match = hechos_por_ticker.get(ticker_base, [])
        if hechos_match:
            alerta["cmf_hechos"]    = len(hechos_match)
            alerta["cmf_materia"]   = hechos_match[0]["materia"][:60]
            alerta["cmf_relevancia"] = hechos_match[0]["relevancia"]
            alerta["conviccion_extra"] = True
        else:
            alerta["cmf_hechos"]       = 0
            alerta["cmf_materia"]      = None
            alerta["cmf_relevancia"]   = None
            alerta["conviccion_extra"] = False

    return alertas_volumen

if __name__ == "__main__":
    print("=== VOLUMEN ANORMAL IPSA ===\n")
    resumen = get_resumen_volumen()

    print(f"Analizados:    {resumen['total_analizados']}")
    print(f"Alertas:       {resumen['alertas']}")
    print(f"Alertas altas: {resumen['alertas_altas']}")

    if resumen["top_alertas"]:
        print("\n--- ALERTAS DE VOLUMEN ---")
        alertas_corr = correlacionar_con_cmf(resumen["top_alertas"])
        for a in alertas_corr:
            cmf_str = f" | CMF: {a['cmf_materia'][:40]}" if a.get("cmf_materia") else ""
            print(f"\n[{a['nivel']}] {a['nombre']} ({a['ticker']})")
            print(f"  Ratio: {a['ratio']}x promedio | Vol: {a['vol_actual']:,} vs prom {a['vol_promedio']:,}")
            print(f"  Precio: {a['precio']:,.2f} ({a['var_pct']:+.2f}%) | Señal: {a['señal']}")
            if cmf_str:
                print(f"  {cmf_str}")
            if a.get("conviccion_extra"):
                print(f"  ⭐ ALTA CONVICCIÓN: Volumen anormal + Hecho CMF simultáneos")
    else:
        print("\n✅ Sin alertas de volumen anormal en este momento")
