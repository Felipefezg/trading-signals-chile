"""
Kelly Criterion — Sizing Dinámico de Posiciones
Calcula el tamaño óptimo de cada posición según:
- Convicción de la señal
- Ratio riesgo/recompensa (SL/TP)
- Win rate histórico del sistema
- Capital disponible y límites de riesgo

Usa Half-Kelly para mayor conservadorismo.
Se auto-calibra con el historial de trades reales.
"""

import json
import os
import sqlite3
from datetime import datetime

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_FILE   = os.path.join(BASE_DIR, "trades_cerrados.json")
DB_PATH       = os.path.join(BASE_DIR, "historial.db")
KELLY_FILE    = os.path.join(BASE_DIR, "kelly_config.json")

# ── PARÁMETROS BASE ───────────────────────────────────────────────────────────
DEFAULTS = {
    "capital":           100_000,   # Capital total USD
    "max_por_operacion": 10_000,    # Máximo USD por operación
    "min_por_operacion": 500,       # Mínimo USD por operación
    "kelly_fraction":    0.35,      # 35%-Kelly (más conservador aún sin historial)
    "win_rate_default":  0.55,      # Win rate asumido sin historial
    "rr_default":        2.0,       # R/R asumido sin SL/TP
    "max_kelly_pct":     0.08,      # Máximo 8% del capital por operación
    "min_kelly_pct":     0.005,     # Mínimo 0.5% del capital
}

# Ajuste por tipo de activo — reduce sizing en activos más volátiles
AJUSTE_TIPO = {
    "Crypto":           0.4,    # BTC → 40% del Kelly calculado
    "Futuro":           0.6,    # Futuros → 60%
    "Acción Chile":     0.7,    # Acciones locales → 70% (liquidez)
    "Acción USA/Chile": 1.0,    # ADRs → 100%
    "ETF":              1.0,    # ETFs → 100%
    "Forex":            0.7,    # Forex → 70%
}

# ── HISTORIAL ─────────────────────────────────────────────────────────────────
def get_win_rate_historico():
    """
    Calcula win rate real desde trades cerrados.
    Fallback a default si no hay suficiente historial.
    """
    try:
        if not os.path.exists(TRADES_FILE):
            return DEFAULTS["win_rate_default"], 0

        with open(TRADES_FILE) as f:
            trades = json.load(f)

        if len(trades) < 10:
            # Insuficiente historial — usar default con sesgo hacia convicción
            return DEFAULTS["win_rate_default"], len(trades)

        ganadores = sum(1 for t in trades if t["pnl_total"] > 0)
        win_rate  = ganadores / len(trades)
        return round(win_rate, 3), len(trades)

    except:
        return DEFAULTS["win_rate_default"], 0

def get_rr_historico():
    """
    Calcula ratio R/R real promedio desde trades cerrados.
    """
    try:
        if not os.path.exists(TRADES_FILE):
            return DEFAULTS["rr_default"]

        with open(TRADES_FILE) as f:
            trades = json.load(f)

        ganadores = [t["pnl_total"] for t in trades if t["pnl_total"] > 0]
        perdedores = [abs(t["pnl_total"]) for t in trades if t["pnl_total"] < 0]

        if not ganadores or not perdedores:
            return DEFAULTS["rr_default"]

        avg_g = sum(ganadores) / len(ganadores)
        avg_p = sum(perdedores) / len(perdedores)
        return round(avg_g / avg_p, 2) if avg_p > 0 else DEFAULTS["rr_default"]

    except:
        return DEFAULTS["rr_default"]

# ── KELLY CRITERION ───────────────────────────────────────────────────────────
def calcular_kelly(conviccion_pct, precio_entrada, stop_loss, take_profit,
                   tipo_activo="ETF", capital=None):
    """
    Calcula el tamaño óptimo de posición usando Half-Kelly.

    Args:
        conviccion_pct: Convicción de la señal (0-100)
        precio_entrada: Precio de entrada
        stop_loss: Nivel de stop loss
        take_profit: Nivel de take profit
        tipo_activo: Tipo de instrumento
        capital: Capital disponible (default: DEFAULTS)

    Returns:
        dict con monto USD, cantidad de unidades y detalles
    """
    capital = capital or DEFAULTS["capital"]

    # Win rate: combinar histórico con convicción de la señal
    win_rate_hist, n_trades = get_win_rate_historico()
    rr_hist = get_rr_historico()

    # Ajustar win rate con convicción (50% historial, 50% señal si hay historial)
    conviccion_decimal = conviccion_pct / 100
    if n_trades >= 10:
        p = win_rate_hist * 0.6 + conviccion_decimal * 0.4
    else:
        # Sin historial: confiar más en la convicción
        p = conviccion_decimal * 0.7 + win_rate_hist * 0.3

    p = min(0.95, max(0.05, p))  # Limitar entre 5% y 95%
    q = 1 - p

    # Calcular R/R desde SL/TP si están disponibles
    if precio_entrada and stop_loss and take_profit:
        riesgo_unit  = abs(precio_entrada - stop_loss)
        ganancia_unit = abs(precio_entrada - take_profit)
        b = ganancia_unit / riesgo_unit if riesgo_unit > 0 else rr_hist
    else:
        b = rr_hist

    b = max(0.5, b)  # R/R mínimo 0.5

    # Fórmula Kelly: f* = (p*b - q) / b
    kelly_full = (p * b - q) / b
    kelly_full = max(0, kelly_full)  # No puede ser negativo

    # Half-Kelly
    kelly_half = kelly_full * DEFAULTS["kelly_fraction"]

    # Aplicar ajuste por tipo de activo
    ajuste = AJUSTE_TIPO.get(tipo_activo, 1.0)
    kelly_ajustado = kelly_half * ajuste

    # Limitar entre min y max
    kelly_final = max(
        DEFAULTS["min_kelly_pct"],
        min(DEFAULTS["max_kelly_pct"], kelly_ajustado)
    )

    # Calcular monto en USD — escalar directamente con convicción
    # Sin historial: convicción 80%=4k, 85%=6k, 90%=8k, 95%=10k
    if n_trades < 10:
        escala = (conviccion_pct - 60) / 40  # 0 a 1 entre conv 60%-100%
        escala = max(0, min(1, escala))
        ajuste_tipo_val = AJUSTE_TIPO.get(tipo_activo, 1.0)
        monto_usd = round(DEFAULTS["min_por_operacion"] +
                         (DEFAULTS["max_por_operacion"] - DEFAULTS["min_por_operacion"]) *
                         escala * ajuste_tipo_val, -2)
    else:
        monto_usd = round(capital * kelly_final, 0)
    monto_usd = max(DEFAULTS["min_por_operacion"],
                    min(DEFAULTS["max_por_operacion"], monto_usd))

    # Calcular unidades
    unidades = None
    if precio_entrada and precio_entrada > 0:
        unidades = max(1, int(monto_usd / precio_entrada))

    # Clasificación del sizing
    if kelly_final >= 0.08:
        clasificacion = "ALTA"
        color = "#22c55e"
    elif kelly_final >= 0.04:
        clasificacion = "MEDIA"
        color = "#f59e0b"
    else:
        clasificacion = "BAJA"
        color = "#64748b"

    return {
        "monto_usd":        monto_usd,
        "unidades":         unidades,
        "kelly_pct":        round(kelly_final * 100, 2),
        "kelly_full_pct":   round(kelly_full * 100, 2),
        "kelly_half_pct":   round(kelly_half * 100, 2),
        "clasificacion":    clasificacion,
        "color":            color,
        "p_ganancia":       round(p * 100, 1),
        "q_perdida":        round(q * 100, 1),
        "ratio_rr":         round(b, 2),
        "win_rate_usado":   round(p * 100, 1),
        "win_rate_hist":    round(win_rate_hist * 100, 1),
        "n_trades_hist":    n_trades,
        "ajuste_tipo":      ajuste,
        "tipo_activo":      tipo_activo,
        "capital":          capital,
        "pct_capital":      round(kelly_final * 100, 2),
    }

def get_sizing_recomendacion(recomendacion, capital=None):
    """
    Calcula el sizing para una recomendación completa.
    Compatible con el formato del motor de recomendaciones.
    """
    return calcular_kelly(
        conviccion_pct = recomendacion.get("conviccion", 70),
        precio_entrada = recomendacion.get("precio_actual"),
        stop_loss      = recomendacion.get("stop_loss"),
        take_profit    = recomendacion.get("take_profit"),
        tipo_activo    = recomendacion.get("tipo", "ETF"),
        capital        = capital,
    )

def get_tabla_sizing(recomendaciones, capital=None):
    """
    Genera tabla de sizing para múltiples recomendaciones.
    """
    capital = capital or DEFAULTS["capital"]
    tabla   = []
    total_comprometido = 0

    for r in recomendaciones:
        sizing = get_sizing_recomendacion(r, capital)
        total_comprometido += sizing["monto_usd"]
        tabla.append({
            "ticker":      r.get("ib_ticker", ""),
            "accion":      r.get("accion", ""),
            "conviccion":  r.get("conviccion", 0),
            "riesgo":      r.get("riesgo", 5),
            "kelly_pct":   sizing["kelly_pct"],
            "monto_usd":   sizing["monto_usd"],
            "unidades":    sizing["unidades"],
            "ratio_rr":    sizing["ratio_rr"],
            "clasificacion": sizing["clasificacion"],
            "color":       sizing["color"],
        })

    return {
        "tabla":               tabla,
        "total_comprometido":  total_comprometido,
        "pct_capital":         round(total_comprometido / capital * 100, 1),
        "capital":             capital,
        "win_rate_hist":       get_win_rate_historico()[0] * 100,
        "n_trades_hist":       get_win_rate_historico()[1],
    }

if __name__ == "__main__":
    print("=== KELLY CRITERION — SIZING DINÁMICO ===\n")

    win_rate, n = get_win_rate_historico()
    rr = get_rr_historico()
    print(f"Win rate histórico: {win_rate*100:.1f}% ({n} trades)")
    print(f"R/R histórico: {rr:.2f}")

    print("\n--- EJEMPLOS DE SIZING ---")
    casos = [
        (90, 88.79, 96.0, 74.38, "Acción USA/Chile", "SQM alta convicción"),
        (70, 88.79, 96.0, 74.38, "Acción USA/Chile", "SQM media convicción"),
        (90, 77771, 83586, 66140, "Crypto", "BTC alta convicción"),
        (85, 6665, 6909, 6176,   "Acción Chile", "COPEC alta convicción"),
        (75, 42.81, 46.0, 38.0,  "ETF", "ECH media convicción"),
    ]

    for conv, entrada, sl, tp, tipo, desc in casos:
        k = calcular_kelly(conv, entrada, sl, tp, tipo)
        print(f"\n{desc} (Conv: {conv}%, {tipo})")
        print(f"  Kelly: {k['kelly_pct']}% del capital → USD {k['monto_usd']:,.0f}")
        print(f"  Unidades: {k['unidades']} @ {entrada:,.2f}")
        print(f"  p(ganar): {k['p_ganancia']}% | R/R: {k['ratio_rr']} | Sizing: {k['clasificacion']}")
