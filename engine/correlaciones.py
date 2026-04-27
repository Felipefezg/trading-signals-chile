"""
Módulo de correlaciones dinámicas.
Calcula correlaciones en tiempo real entre activos chilenos
y variables macro globales, con ventanas móviles para detectar
cambios de régimen.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ── UNIVERSO DE ACTIVOS ───────────────────────────────────────────────────────
ACTIVOS_CHILE = {
    "ECH":       "IPSA ETF",
    "SQM":       "SQM (NYSE)",
    "COPEC.SN":  "Copec",
    "BCI.SN":    "Banco BCI",
    "CHILE.SN":  "Banco Chile",
    "CMPC.SN":   "CMPC",
    "FALABELLA.SN": "Falabella",
    "LTM.SN":    "LATAM",
}

ACTIVOS_MACRO = {
    "HG=F":      "Cobre (LME)",
    "CL=F":      "Petróleo WTI",
    "GC=F":      "Oro",
    "^VIX":      "VIX",
    "DX-Y.NYB":  "DXY (Dólar)",
    "SPY":       "S&P 500",
    "BTC-USD":   "Bitcoin",
    "^TNX":      "Treasury 10Y",
}

# Colores para el heatmap
def _corr_color(v):
    if v >= 0.7:  return "#166534", "#bbf7d0"   # verde oscuro fondo, texto
    if v >= 0.4:  return "#14532d", "#86efac"
    if v >= 0.1:  return "#1e293b", "#64748b"
    if v >= -0.1: return "#1e293b", "#475569"
    if v >= -0.4: return "#450a0a", "#fca5a5"
    if v >= -0.7: return "#7f1d1d", "#f87171"
    return "#450a0a", "#ef4444"

# ── DESCARGA DE DATOS ─────────────────────────────────────────────────────────
def _descargar_datos(tickers, periodo="90d"):
    """Descarga precios históricos para múltiples tickers"""
    try:
        data = yf.download(tickers, period=periodo, progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            closes = data["Close"]
        else:
            closes = data[["Close"]] if "Close" in data.columns else data
        return closes.dropna(how="all")
    except Exception as e:
        print(f"Error descargando datos: {e}")
        return pd.DataFrame()

# ── CORRELACIONES ─────────────────────────────────────────────────────────────
def get_correlaciones_chile_macro(periodo="90d"):
    """
    Calcula correlaciones entre activos chilenos y variables macro globales.
    Retorna matriz de correlaciones y análisis de señales.
    """
    todos = list(ACTIVOS_CHILE.keys()) + list(ACTIVOS_MACRO.keys())
    df = _descargar_datos(todos, periodo)

    if df.empty:
        return {}

    # Retornos diarios
    retornos = df.pct_change().dropna()
    corr = retornos.corr().round(3)

    resultado = {}
    for activo_cl in ACTIVOS_CHILE:
        if activo_cl not in corr.columns:
            continue
        fila = {}
        for activo_macro in ACTIVOS_MACRO:
            if activo_macro in corr.columns:
                fila[activo_macro] = corr.loc[activo_cl, activo_macro]
        resultado[activo_cl] = {
            "nombre":       ACTIVOS_CHILE[activo_cl],
            "correlaciones": fila,
        }

    return resultado

def get_correlaciones_ipsa_completo(periodo="90d"):
    """
    Correlaciones entre ECH y todos los activos macro.
    La más importante para análisis de mercado Chile.
    """
    tickers = ["ECH"] + list(ACTIVOS_MACRO.keys())
    df = _descargar_datos(tickers, periodo)
    if df.empty or "ECH" not in df.columns:
        return []

    retornos = df.pct_change().dropna()
    corr_ech = retornos.corr()["ECH"].drop("ECH").sort_values(ascending=False)

    resultado = []
    for ticker, corr_val in corr_ech.items():
        nombre = ACTIVOS_MACRO.get(ticker, ticker)
        bg, fg = _corr_color(corr_val)
        resultado.append({
            "ticker":  ticker,
            "nombre":  nombre,
            "corr":    round(corr_val, 3),
            "bg":      bg,
            "fg":      fg,
            "señal":   _interpretar_correlacion(ticker, corr_val),
        })
    return resultado

def _interpretar_correlacion(ticker, corr):
    """Genera interpretación de la correlación para el mercado"""
    abs_c = abs(corr)
    fuerza = "fuerte" if abs_c >= 0.7 else ("moderada" if abs_c >= 0.4 else "débil")
    direccion = "positiva" if corr > 0 else "negativa"

    interpretaciones = {
        "HG=F":     f"Cobre {direccion} {fuerza} → Chile depende del cobre",
        "CL=F":     f"Petróleo {direccion} {fuerza} → impacta costos energía",
        "GC=F":     f"Oro {direccion} {fuerza} → activo refugio vs Chile",
        "^VIX":     f"VIX {direccion} {fuerza} → {'miedo global daña Chile' if corr < 0 else 'inusual'}",
        "DX-Y.NYB": f"DXY {direccion} {fuerza} → {'dólar fuerte = CLP débil' if corr < 0 else 'inusual'}",
        "SPY":      f"S&P500 {direccion} {fuerza} → correlación con mercado global",
        "BTC-USD":  f"Bitcoin {direccion} {fuerza} → apetito por riesgo",
        "^TNX":     f"Treasury 10Y {direccion} {fuerza} → tasas USA vs Chile",
    }
    return interpretaciones.get(ticker, f"Correlación {direccion} {fuerza}")

# ── CORRELACIONES ENTRE ACCIONES CHILENAS ────────────────────────────────────
def get_correlaciones_ipsa_interno(periodo="60d"):
    """
    Matriz de correlaciones entre acciones del IPSA.
    Útil para diversificación de portafolio.
    """
    tickers = list(ACTIVOS_CHILE.keys())
    df = _descargar_datos(tickers, periodo)
    if df.empty:
        return pd.DataFrame()

    retornos = df.pct_change().dropna()
    corr = retornos.corr().round(3)

    # Renombrar con nombres legibles
    nombres = {t: ACTIVOS_CHILE.get(t, t) for t in corr.columns if t in ACTIVOS_CHILE}
    corr = corr.rename(columns=nombres, index=nombres)
    return corr

# ── CORRELACIONES RODANTES ────────────────────────────────────────────────────
def get_correlacion_rodante(ticker1="ECH", ticker2="HG=F", ventana=30, periodo="180d"):
    """
    Calcula correlación rodante entre dos activos para detectar
    cambios de régimen de correlación.
    """
    df = _descargar_datos([ticker1, ticker2], periodo)
    if df.empty or ticker1 not in df.columns or ticker2 not in df.columns:
        return None

    retornos = df.pct_change().dropna()
    corr_rodante = retornos[ticker1].rolling(window=ventana).corr(retornos[ticker2])

    return {
        "ticker1":   ticker1,
        "ticker2":   ticker2,
        "nombre1":   ACTIVOS_CHILE.get(ticker1, ACTIVOS_MACRO.get(ticker1, ticker1)),
        "nombre2":   ACTIVOS_MACRO.get(ticker2, ACTIVOS_CHILE.get(ticker2, ticker2)),
        "ventana":   ventana,
        "actual":    round(float(corr_rodante.iloc[-1]), 3),
        "promedio":  round(float(corr_rodante.mean()), 3),
        "max":       round(float(corr_rodante.max()), 3),
        "min":       round(float(corr_rodante.min()), 3),
        "fechas":    [str(d.date()) for d in corr_rodante.index],
        "valores":   [round(v, 3) if not np.isnan(v) else None for v in corr_rodante.values],
    }

# ── SEÑALES DE DIVERGENCIA ────────────────────────────────────────────────────
def get_divergencias_correlacion(periodo="90d"):
    """
    Detecta cuando la correlación histórica se rompe → señal de trading.
    Ejemplo: Si cobre sube pero ECH baja, hay divergencia.
    """
    tickers = ["ECH", "HG=F", "CL=F", "^VIX", "DX-Y.NYB", "SPY"]
    df = _descargar_datos(tickers, periodo)
    if df.empty:
        return []

    retornos_hoy = df.pct_change().iloc[-1]
    corr_hist    = df.pct_change().dropna().corr()

    divergencias = []
    ech_hoy = retornos_hoy.get("ECH", 0)

    for ticker in ["HG=F", "CL=F", "^VIX", "DX-Y.NYB", "SPY"]:
        if ticker not in retornos_hoy or ticker not in corr_hist.columns:
            continue
        corr_hist_val = corr_hist.loc["ECH", ticker]
        macro_hoy     = retornos_hoy[ticker]

        # Movimiento esperado de ECH dado el macro
        ech_esperado = corr_hist_val * macro_hoy

        # Divergencia = diferencia entre esperado y real
        divergencia = ech_hoy - ech_esperado

        if abs(divergencia) > 0.005:  # >0.5% de divergencia
            nombre = ACTIVOS_MACRO.get(ticker, ticker)
            señal = "ECH SUBVALUED" if divergencia > 0 else "ECH OVERVALUED"
            divergencias.append({
                "ticker":       ticker,
                "nombre":       nombre,
                "corr_hist":    round(corr_hist_val, 3),
                "macro_mov":    round(float(macro_hoy) * 100, 2),
                "ech_esperado": round(float(ech_esperado) * 100, 3),
                "ech_real":     round(float(ech_hoy) * 100, 3),
                "divergencia":  round(float(divergencia) * 100, 3),
                "señal":        señal,
                "color":        "#22c55e" if divergencia > 0 else "#ef4444",
            })

    return sorted(divergencias, key=lambda x: abs(x["divergencia"]), reverse=True)

if __name__ == "__main__":
    print("=== CORRELACIONES ECH vs MACRO ===")
    corrs = get_correlaciones_ipsa_completo()
    for c in corrs:
        bar = "█" * int(abs(c["corr"]) * 10)
        sign = "+" if c["corr"] >= 0 else "-"
        print(f"  {sign}{bar:<10} {c['corr']:+.3f}  {c['nombre']:<20} {c['señal']}")

    print("\n=== CORRELACIÓN RODANTE ECH-COBRE (30d) ===")
    rod = get_correlacion_rodante("ECH", "HG=F", 30, "180d")
    if rod:
        print(f"  Actual: {rod['actual']} | Prom: {rod['promedio']} | Min: {rod['min']} | Max: {rod['max']}")

    print("\n=== DIVERGENCIAS HOY ===")
    divs = get_divergencias_correlacion()
    for d in divs:
        print(f"  {d['señal']}: ECH real {d['ech_real']:+.2f}% vs esperado {d['ech_esperado']:+.2f}% (dif {d['divergencia']:+.2f}%)")
