"""
Módulo de Renta Fija Chilena.
Analiza tasas de interés y bonos para generar señales de trading.

Fuentes:
- mindicador.cl: TPM, UF, IPC
- Yahoo Finance: Treasuries USA, ETFs de bonos
- Cálculo de spreads y curva de tasas

Señales generadas:
- Spread Chile-USA → atractivo relativo
- Curva de tasas USA → expectativas de recesión
- Movimiento TPM → impacto en bancos y utilities
"""

import requests
import yfinance as yf
import numpy as np
from datetime import datetime

# ── FUENTES ───────────────────────────────────────────────────────────────────
MINDICADOR_URL = "https://mindicador.cl/api"

# ETFs de renta fija disponibles en IB
ETFS_RENTA_FIJA = {
    "TLT":  {"nombre": "iShares 20Y Treasury",    "duracion": 20, "tipo": "Soberano USA"},
    "IEF":  {"nombre": "iShares 7-10Y Treasury",  "duracion": 7,  "tipo": "Soberano USA"},
    "SHY":  {"nombre": "iShares 1-3Y Treasury",   "duracion": 1,  "tipo": "Soberano USA"},
    "LQD":  {"nombre": "iShares Corp Bond",        "duracion": 9,  "tipo": "Corporativo USA"},
    "EMB":  {"nombre": "iShares EM Bond",          "duracion": 7,  "tipo": "Emergentes"},
    "AGG":  {"nombre": "iShares Core Bond",        "duracion": 6,  "tipo": "Agregado USA"},
}

# Impacto de tasas en activos chilenos
IMPACTO_TASAS = {
    "subida_tpm":   ["CHILE.SN", "BSANTANDER.SN", "BCI.SN", "ITAUCL.SN"],  # Bancos se benefician
    "bajada_tpm":   ["COLBUN.SN", "ENELCHILE.SN", "AGUAS-A.SN", "MALLPLAZA.SN"],  # Utilities/REITS
    "curva_invertida": ["ECH", "CLP/USD"],  # Riesgo recesión → presión sobre Chile
    "spread_alto":  ["ECH", "CLP/USD"],  # Mayor diferencial → presión emergentes
}

# ── DATOS DE TASAS ────────────────────────────────────────────────────────────
def get_tasas_bcch():
    """Obtiene tasas del Banco Central de Chile via mindicador.cl"""
    tasas = {}
    indicadores = {
        "tpm":  "Tasa Política Monetaria",
        "uf":   "UF",
        "ipc":  "IPC mensual",
    }
    for codigo, nombre in indicadores.items():
        try:
            r = requests.get(f"{MINDICADOR_URL}/{codigo}", timeout=8)
            if r.ok:
                data = r.json()
                serie = data.get("serie", [{}])
                if serie:
                    tasas[codigo] = {
                        "nombre": nombre,
                        "valor":  serie[0].get("valor"),
                        "fecha":  serie[0].get("fecha", "")[:10],
                    }
        except:
            pass
    return tasas

def get_tasas_usa():
    """Obtiene tasas del Tesoro USA via Yahoo Finance"""
    tasas = {}
    tickers = {
        "^IRX": {"nombre": "Treasury 3M", "plazo": 0.25},
        "^FVX": {"nombre": "Treasury 5Y",  "plazo": 5},
        "^TNX": {"nombre": "Treasury 10Y", "plazo": 10},
        "^TYX": {"nombre": "Treasury 30Y", "plazo": 30},
    }
    for ticker, info in tickers.items():
        try:
            h = yf.Ticker(ticker).history(period="10d")
            if not h.empty:
                actual   = float(h["Close"].iloc[-1])
                anterior = float(h["Close"].iloc[-2]) if len(h) > 1 else actual
                semana   = float(h["Close"].iloc[-5]) if len(h) >= 5 else actual
                tasas[ticker] = {
                    **info,
                    "valor":      round(actual, 3),
                    "cambio_1d":  round(actual - anterior, 3),
                    "cambio_5d":  round(actual - semana, 3),
                }
        except:
            pass
    return tasas

def get_etfs_renta_fija():
    """Analiza ETFs de renta fija"""
    resultados = {}
    for ticker, info in ETFS_RENTA_FIJA.items():
        try:
            h = yf.Ticker(ticker).history(period="20d")
            if len(h) < 10:
                continue
            precio    = float(h["Close"].iloc[-1])
            ret_1d    = float((h["Close"].iloc[-1]/h["Close"].iloc[-2]-1)*100)
            ret_5d    = float((h["Close"].iloc[-1]/h["Close"].iloc[-5]-1)*100)
            ret_20d   = float((h["Close"].iloc[-1]/h["Close"].iloc[-20]-1)*100)
            vol_ratio = float(h["Volume"].iloc[-1]/h["Volume"].iloc[:-1].mean())

            resultados[ticker] = {
                **info,
                "precio":   round(precio, 2),
                "ret_1d":   round(ret_1d, 2),
                "ret_5d":   round(ret_5d, 2),
                "ret_20d":  round(ret_20d, 2),
                "vol_ratio": round(vol_ratio, 2),
            }
        except:
            pass
    return resultados

# ── ANÁLISIS DE CURVA ─────────────────────────────────────────────────────────
def analizar_curva_tasas(tasas_usa):
    """
    Analiza la forma de la curva de tasas USA.
    Curva invertida (10Y < 3M) = señal de recesión.
    """
    t3m  = tasas_usa.get("^IRX", {}).get("valor", 0)
    t10y = tasas_usa.get("^TNX", {}).get("valor", 0)
    t30y = tasas_usa.get("^TYX", {}).get("valor", 0)

    if not t3m or not t10y:
        return {}

    spread_10y_3m = round(t10y - t3m, 3)
    spread_30y_10y = round(t30y - t10y, 3) if t30y else 0

    # Clasificar curva
    if spread_10y_3m < -0.5:
        forma       = "INVERTIDA SEVERA"
        señal       = "RECESIÓN INMINENTE"
        color       = "#ef4444"
        impacto_ech = "BAJA"
        score       = -3
    elif spread_10y_3m < 0:
        forma       = "INVERTIDA"
        señal       = "RIESGO RECESIÓN"
        color       = "#f97316"
        impacto_ech = "BAJA"
        score       = -2
    elif spread_10y_3m < 0.5:
        forma       = "PLANA"
        señal       = "CAUTELA"
        color       = "#f59e0b"
        impacto_ech = "NEUTRO"
        score       = 0
    elif spread_10y_3m < 1.5:
        forma       = "NORMAL"
        señal       = "CRECIMIENTO MODERADO"
        color       = "#22c55e"
        impacto_ech = "ALZA"
        score       = 1
    else:
        forma       = "EMPINADA"
        señal       = "CRECIMIENTO FUERTE"
        color       = "#16a34a"
        impacto_ech = "ALZA"
        score       = 2

    return {
        "t3m":           t3m,
        "t10y":          t10y,
        "t30y":          t30y,
        "spread_10y_3m": spread_10y_3m,
        "spread_30y_10y": spread_30y_10y,
        "forma":         forma,
        "señal":         señal,
        "color":         color,
        "impacto_ech":   impacto_ech,
        "score":         score,
        "descripcion":   f"Curva {forma}: spread 10Y-3M = {spread_10y_3m:+.3f}% → {señal}",
    }

def analizar_spread_chile_usa(tasas_bcch, tasas_usa):
    """
    Calcula el spread entre tasas Chile y USA.
    Spread alto → mayor atractivo de bonos chilenos vs USA.
    """
    tpm = tasas_bcch.get("tpm", {}).get("valor", 0)
    t10y_usa = tasas_usa.get("^TNX", {}).get("valor", 0)

    if not tpm or not t10y_usa:
        return {}

    spread = round(tpm - t10y_usa, 3)

    if spread > 2:
        señal  = "SPREAD ALTO → Chile muy atractivo"
        color  = "#22c55e"
        score  = 2
    elif spread > 0.5:
        señal  = "SPREAD POSITIVO → Chile atractivo"
        color  = "#86efac"
        score  = 1
    elif spread > -0.5:
        señal  = "SPREAD NEUTRO"
        color  = "#64748b"
        score  = 0
    else:
        señal  = "SPREAD NEGATIVO → USA más atractivo"
        color  = "#f97316"
        score  = -1

    return {
        "tpm_chile": tpm,
        "t10y_usa":  t10y_usa,
        "spread":    spread,
        "señal":     señal,
        "color":     color,
        "score":     score,
        "descripcion": f"TPM Chile {tpm}% vs T10Y USA {t10y_usa}% → spread {spread:+.3f}%",
    }

# ── SEÑALES PARA EL MOTOR ─────────────────────────────────────────────────────
def get_señales_renta_fija():
    """
    Genera señales de trading basadas en renta fija.
    Compatible con el motor de recomendaciones.
    """
    tasas_bcch = get_tasas_bcch()
    tasas_usa  = get_tasas_usa()
    curva      = analizar_curva_tasas(tasas_usa)
    spread     = analizar_spread_chile_usa(tasas_bcch, tasas_usa)

    señales = []

    # Señal por forma de curva
    if curva.get("score", 0) != 0:
        for activo in ["ECH", "CLP/USD"]:
            señales.append({
                "activo":      activo,
                "fuente":      "Renta Fija",
                "score":       abs(curva["score"]),
                "direccion":   curva["impacto_ech"],
                "descripcion": curva["descripcion"],
            })

    # Señal por spread Chile-USA
    if abs(spread.get("score", 0)) >= 1:
        señales.append({
            "activo":      "ECH",
            "fuente":      "Renta Fija",
            "score":       abs(spread["score"]),
            "direccion":   "ALZA" if spread["score"] > 0 else "BAJA",
            "descripcion": spread["descripcion"],
        })

    # Señal por movimiento de tasas USA (impacto en TLT/IEF)
    t10y = tasas_usa.get("^TNX", {})
    if t10y.get("cambio_5d", 0) > 0.3:
        # Tasas subiendo → TLT baja, bancos chilenos suben
        for activo in IMPACTO_TASAS["subida_tpm"]:
            señales.append({
                "activo":      activo,
                "fuente":      "Renta Fija",
                "score":       2,
                "direccion":   "ALZA",
                "descripcion": f"T10Y USA subió {t10y['cambio_5d']:+.3f}% → bancos favorecidos",
            })
    elif t10y.get("cambio_5d", 0) < -0.3:
        # Tasas bajando → utilities y REITs suben
        for activo in IMPACTO_TASAS["bajada_tpm"]:
            señales.append({
                "activo":      activo,
                "fuente":      "Renta Fija",
                "score":       2,
                "direccion":   "ALZA",
                "descripcion": f"T10Y USA bajó {t10y['cambio_5d']:+.3f}% → utilities favorecidas",
            })

    return señales

def get_resumen_renta_fija():
    """Resumen completo para el dashboard"""
    tasas_bcch = get_tasas_bcch()
    tasas_usa  = get_tasas_usa()
    curva      = analizar_curva_tasas(tasas_usa)
    spread     = analizar_spread_chile_usa(tasas_bcch, tasas_usa)
    etfs       = get_etfs_renta_fija()

    return {
        "timestamp":   datetime.now().isoformat(),
        "tasas_bcch":  tasas_bcch,
        "tasas_usa":   tasas_usa,
        "curva":       curva,
        "spread":      spread,
        "etfs":        etfs,
        "señales":     get_señales_renta_fija(),
    }

if __name__ == "__main__":
    print("=== RENTA FIJA CHILE ===\n")
    resumen = get_resumen_renta_fija()

    print("TASAS BCCH:")
    for k, v in resumen["tasas_bcch"].items():
        print(f"  {v['nombre']}: {v['valor']}")

    print("\nTASAS USA:")
    for k, v in resumen["tasas_usa"].items():
        print(f"  {v['nombre']}: {v['valor']}% (5d: {v['cambio_5d']:+.3f}%)")

    curva = resumen["curva"]
    print(f"\nCURVA: {curva.get('forma','N/D')} — {curva.get('señal','')}")
    print(f"  Spread 10Y-3M: {curva.get('spread_10y_3m',0):+.3f}%")

    spread = resumen["spread"]
    print(f"\nSPREAD CHILE-USA: {spread.get('spread',0):+.3f}%")
    print(f"  {spread.get('señal','')}")

    print(f"\nSEÑALES GENERADAS: {len(resumen['señales'])}")
    for s in resumen["señales"]:
        print(f"  [{s['direccion']}] {s['activo']} — {s['descripcion'][:70]}")
