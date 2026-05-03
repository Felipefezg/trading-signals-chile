"""
Módulo Put/Call Ratio — Smart Money Positioning
Analiza el posicionamiento en opciones para detectar
qué están haciendo los inversores institucionales.

Tickers disponibles: SPY, SQM, GLD, ECH (si tiene opciones)

Interpretación:
P/C < 0.5:  Codicia extrema en calls → señal bajista contrarian
P/C 0.5-0.7: Optimismo → mercado alcista
P/C 0.7-1.0: Neutral
P/C 1.0-1.5: Precaución → institucionales comprando protección
P/C > 1.5:  Miedo → muchos puts → posible suelo (contrarian alcista)
P/C > 2.0:  Capitulación → señal contrarian de compra fuerte
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# Tickers con opciones líquidas
TICKERS_OPCIONES = {
    "SPY": {"nombre": "S&P 500 ETF",    "impacto": "ECH",    "tipo": "índice"},
    "SQM": {"nombre": "SQM ADR (NYSE)", "impacto": "SQM.SN", "tipo": "acción"},
    "GLD": {"nombre": "Gold ETF",       "impacto": "GC=F",   "tipo": "commodity"},
    "QQQ": {"nombre": "Nasdaq ETF",     "impacto": "ECH",    "tipo": "índice"},
}

# Umbrales de señal
UMBRALES = {
    "capitulacion_compra":  2.0,   # P/C > 2.0 → contrarian compra
    "miedo":                1.5,
    "precaucion":           1.0,
    "neutral_alto":         0.8,
    "neutral_bajo":         0.6,
    "optimismo":            0.5,
    "codicia_extrema":      0.3,   # P/C < 0.3 → contrarian venta
}

def get_put_call_ratio(ticker, incluir_todos_vencimientos=False):
    """
    Calcula el Put/Call ratio para un ticker.
    
    Args:
        ticker: Ticker con opciones (SPY, SQM, etc.)
        incluir_todos_vencimientos: Si True, suma todos los vencimientos
    
    Returns:
        dict con ratio, volumen, OI y señal
    """
    try:
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return None

        total_calls_vol = 0
        total_puts_vol  = 0
        total_calls_oi  = 0
        total_puts_oi   = 0
        vencimientos_usados = 0

        # Usar todos o solo los próximos 3 vencimientos
        fechas = expirations[:2]  # Solo 2 proximos vencimientos — mas rapido

        for fecha in fechas:
            try:
                chain = t.option_chain(fecha)
                calls = chain.calls
                puts  = chain.puts

                # Volumen
                vol_c = calls["volume"].fillna(0).sum()
                vol_p = puts["volume"].fillna(0).sum()
                total_calls_vol += vol_c
                total_puts_vol  += vol_p

                # Open Interest
                oi_c = calls["openInterest"].fillna(0).sum()
                oi_p = puts["openInterest"].fillna(0).sum()
                total_calls_oi += oi_c
                total_puts_oi  += oi_p

                vencimientos_usados += 1
            except:
                continue

        if total_calls_vol == 0 and total_calls_oi == 0:
            return None

        # Ratios
        pc_ratio_vol = total_puts_vol / total_calls_vol if total_calls_vol > 0 else 0
        pc_ratio_oi  = total_puts_oi  / total_calls_oi  if total_calls_oi  > 0 else 0

        # Señal basada en volumen (más relevante para smart money)
        señal, color, direccion = _clasificar_ratio(pc_ratio_vol)

        # Precio actual
        h = t.history(period="2d")
        precio = float(h["Close"].iloc[-1]) if not h.empty else None

        meta = TICKERS_OPCIONES.get(ticker, {})
        return {
            "ticker":           ticker,
            "nombre":           meta.get("nombre", ticker),
            "impacto_activo":   meta.get("impacto", ticker),
            "precio":           precio,
            "pc_ratio_vol":     round(pc_ratio_vol, 3),
            "pc_ratio_oi":      round(pc_ratio_oi, 3),
            "calls_vol":        int(total_calls_vol),
            "puts_vol":         int(total_puts_vol),
            "calls_oi":         int(total_calls_oi),
            "puts_oi":          int(total_puts_oi),
            "vencimientos":     vencimientos_usados,
            "señal":            señal,
            "color":            color,
            "direccion":        direccion,
            "timestamp":        datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"Error P/C {ticker}: {e}")
        return None

def _clasificar_ratio(ratio):
    """Clasifica el ratio P/C y retorna señal, color y dirección"""
    if ratio >= UMBRALES["capitulacion_compra"]:
        return "CAPITULACIÓN — Contrarian COMPRA", "#22c55e", "ALZA"
    elif ratio >= UMBRALES["miedo"]:
        return "MIEDO — Posible suelo", "#86efac", "ALZA"
    elif ratio >= UMBRALES["precaucion"]:
        return "PRECAUCIÓN — Protección institucional", "#f59e0b", "BAJA"
    elif ratio >= UMBRALES["neutral_alto"]:
        return "NEUTRAL ALTO", "#64748b", "NEUTRO"
    elif ratio >= UMBRALES["neutral_bajo"]:
        return "NEUTRAL", "#64748b", "NEUTRO"
    elif ratio >= UMBRALES["optimismo"]:
        return "OPTIMISMO — Sesgo alcista", "#fb923c", "ALZA"
    elif ratio >= UMBRALES["codicia_extrema"]:
        return "CODICIA — Cautela al alza", "#ef4444", "BAJA"
    else:
        return "CODICIA EXTREMA — Contrarian VENTA", "#7f1d1d", "BAJA"

def get_todos_ratios():
    """Calcula P/C ratio para todos los tickers disponibles"""
    resultados = []
    for ticker in TICKERS_OPCIONES:
        ratio = get_put_call_ratio(ticker)
        if ratio:
            resultados.append(ratio)
    return sorted(resultados, key=lambda x: abs(x["pc_ratio_vol"] - 1), reverse=True)

def get_señal_consolidada_pc():
    """
    Genera señal consolidada de Put/Call para el motor de recomendaciones.
    Retorna dict compatible con las otras fuentes.
    """
    ratios = get_todos_ratios()
    if not ratios:
        return {}

    señales = {}
    for r in ratios:
        activo = r["impacto_activo"]
        if activo not in señales:
            señales[activo] = {
                "direccion": r["direccion"],
                "ratio":     r["pc_ratio_vol"],
                "señal":     r["señal"],
                "ticker":    r["ticker"],
                "score":     _ratio_to_score(r["pc_ratio_vol"], r["direccion"]),
            }
    return señales

def _ratio_to_score(ratio, direccion):
    """Convierte el ratio a score de convicción 0-10"""
    if direccion == "ALZA":
        if ratio >= 2.0: return 9
        if ratio >= 1.5: return 7
        return 4
    elif direccion == "BAJA":
        if ratio <= 0.3: return 9
        if ratio <= 0.5: return 7
        if ratio >= 1.0: return 5
        return 3
    return 0

def get_resumen_pc():
    """Resumen para el dashboard"""
    ratios = get_todos_ratios()
    señales_alza = [r for r in ratios if r["direccion"] == "ALZA"]
    señales_baja = [r for r in ratios if r["direccion"] == "BAJA"]

    return {
        "timestamp":    datetime.now().isoformat(),
        "total":        len(ratios),
        "alza":         len(señales_alza),
        "baja":         len(señales_baja),
        "ratios":       ratios,
        "spy_ratio":    next((r["pc_ratio_vol"] for r in ratios if r["ticker"] == "SPY"), None),
        "sqm_ratio":    next((r["pc_ratio_vol"] for r in ratios if r["ticker"] == "SQM"), None),
    }

if __name__ == "__main__":
    print("=== PUT/CALL RATIO — SMART MONEY ===\n")
    resumen = get_resumen_pc()

    print(f"Tickers analizados: {resumen['total']}")
    print(f"Señales ALZA: {resumen['alza']} | Señales BAJA: {resumen['baja']}")
    print(f"SPY P/C: {resumen['spy_ratio']} | SQM P/C: {resumen['sqm_ratio']}")
    print()

    for r in resumen["ratios"]:
        print(f"[{r['ticker']}] {r['nombre']}")
        print(f"  P/C Vol: {r['pc_ratio_vol']:.3f} | P/C OI: {r['pc_ratio_oi']:.3f}")
        print(f"  Calls: {r['calls_vol']:,} | Puts: {r['puts_vol']:,}")
        print(f"  Señal: {r['señal']}")
        print(f"  Impacto en: {r['impacto_activo']}")
        print()
