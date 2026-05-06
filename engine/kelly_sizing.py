"""
Kelly Sizing Dinámico — engine/kelly_sizing.py

Calcula el tamaño óptimo de posición por activo usando la fórmula de Kelly:
    K = win_rate - (1 - win_rate) / rr_ratio

Se aplica Half-Kelly (K/2) como estándar para trading en vivo, que balancea
crecimiento de capital con control de drawdown.

Stats derivados del backtest de 2 años (última ejecución calibrada).
Se actualizan con cada corrida de backtesting.

Mapeo: IB ticker → stats de backtest.
Cuando un activo no tiene stats (nuevo, sin historial suficiente), se usa
el fallback basado en convicción del motor.
"""

from __future__ import annotations
import os as _os
import json as _json

# ── KELLY STATS LIVE (trades reales — prioridad sobre backtest) ───────────────
# Generado por engine/feedback_loop.py → actualizar_kelly_live()
# Prioridad sobre KELLY_STATS cuando n_trades >= MIN_TRADES_STATS.
_KELLY_LIVE_FILE = _os.path.join(_os.path.dirname(__file__), "..", "data", "kelly_stats_live.json")

def _cargar_kelly_live() -> dict:
    """Stats de trades reales. Prioridad sobre KELLY_STATS hardcodeado."""
    try:
        if _os.path.exists(_KELLY_LIVE_FILE):
            with open(_KELLY_LIVE_FILE) as f:
                data = _json.load(f)
            return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        pass
    return {}

# ── STATS DE BACKTEST POR TICKER IB ──────────────────────────────────────────
# Formato: "IB_TICKER": {"win_rate": float (0-1), "rr": float, "n_trades": int}
# win_rate: fracción de trades ganadores
# rr: R/R real calculado en % de retorno (avg_ganador_pct / avg_perdedor_pct)
# n_trades: número de trades en el backtest (confiabilidad estadística)
#
# Criterio de confiabilidad: n_trades >= 3 para usar stats propios.
# Con 1-2 trades: demasiado ruido, usar fallback convicción.

KELLY_STATS: dict[str, dict] = {
    # ── ACCIONES CHILE (IB ticker) ──────────────────────────────────────────
    "VAPORES":   {"win_rate": 0.80, "rr": 1.67, "n_trades": 5},   # CSAV  +34.7%
    "SMU":       {"win_rate": 0.667,"rr": 5.37, "n_trades": 3},   # SMU   +18.9%
    "CMPC":      {"win_rate": 1.00, "rr": 2.00, "n_trades": 3},   # CMPC  +12.7%
    "FALABELLA": {"win_rate": 1.00, "rr": 2.00, "n_trades": 2},   # FAL   +12.4% (solo 2 trades → usar fallback)
    "SQM-B":     {"win_rate": 0.60, "rr": 1.23, "n_trades": 5},   # SQM   +9.9%
    "HABITAT":   {"win_rate": 1.00, "rr": 2.00, "n_trades": 3},   # AFP Habitat +9.6%
    "COPEC":     {"win_rate": 1.00, "rr": 2.00, "n_trades": 3},   # COPEC +8.1%
    "COLBUN":    {"win_rate": 1.00, "rr": 2.00, "n_trades": 2},   # Colbún +7.7% (2 trades → fallback)
    "RIPLEY":    {"win_rate": 0.50, "rr": 2.10, "n_trades": 4},   # Ripley +7.2%
    "ENELAM":    {"win_rate": 1.00, "rr": 2.00, "n_trades": 1},   # Enel Américas (1 trade → fallback)
    "ENELCHILE": {"win_rate": 0.667,"rr": 0.66, "n_trades": 6},   # Enel Chile +4.0% (R/R bajo)
    "PARAUCO":   {"win_rate": 0.571,"rr": 0.89, "n_trades": 7},   # Parque Arauco +3.0%
    "AGUAS-A":   {"win_rate": 0.667,"rr": 0.75, "n_trades": 6},   # Aguas Andinas +2.9%
    "BSAC":      {"win_rate": 0.50, "rr": 1.10, "n_trades": 4},   # Santander CL  +0.8%
    # Losers conocidos — Kelly negativo → floor mínimo
    "CHILE":     {"win_rate": 0.333,"rr": 1.37, "n_trades": 3},   # Banco Chile -0.9%
    "CENCOSUD":  {"win_rate": 0.50, "rr": 0.87, "n_trades": 4},   # Cencosud -1.0%
    "ANDINA-B":  {"win_rate": 0.50, "rr": 0.62, "n_trades": 2},   # Andina -1.5% (2 trades → fallback)
    "CCU":       {"win_rate": 0.333,"rr": 0.73, "n_trades": 3},   # CCU -6.4%

    # ── ACCIONES USA / ADRs ─────────────────────────────────────────────────
    "SQM":       {"win_rate": 0.60, "rr": 1.27, "n_trades": 5},   # SQM ADR +8.5%
    "BCH":       {"win_rate": 0.50, "rr": 1.44, "n_trades": 2},   # BdCh ADR +0.3% (2 → fallback)
    "LTM":       {"win_rate": 0.25, "rr": 3.10, "n_trades": 4},   # LATAM ADR +0.4%

    # ── ETFs ────────────────────────────────────────────────────────────────
    "GLD":       {"win_rate": 0.50, "rr": 2.34, "n_trades": 4},   # Gold ETF +10.0%
    "SPY":       {"win_rate": 1.00, "rr": 2.00, "n_trades": 1},   # S&P 500 (1 trade → fallback)
    "TLT":       {"win_rate": 1.00, "rr": 2.00, "n_trades": 1},   # 20Y Treasury (1 → fallback)
    "ECH":       {"win_rate": 0.20, "rr": 1.61, "n_trades": 5},   # iShares Chile -7.4%

    # ── CRYPTO ──────────────────────────────────────────────────────────────
    "BTC":       {"win_rate": 0.50, "rr": 2.60, "n_trades": 8},   # BTC +30.8%
    "ETH":       {"win_rate": 0.50, "rr": 2.00, "n_trades": 0},   # ETH: sin stats propios

    # ── FUTUROS ─────────────────────────────────────────────────────────────
    "GC":        {"win_rate": 0.333,"rr": 6.36, "n_trades": 3},   # Oro futuro +4.0%
    # CL excluido del universo activo (R/R=0.44x, estructuralmente roto en señal diaria)
}

# ── PARÁMETROS DE SIZING ─────────────────────────────────────────────────────
KELLY_FRACTION    = 0.5    # Half-Kelly — estándar conservador para live trading
MIN_TRADES_STATS  = 3      # Mínimo de trades para confiar en stats propios
MIN_USD_POSICION  = 2_000  # Floor mínimo — cualquier señal que pase filtros merece al menos esto
MAX_USD_POSICION  = 15_000 # Cap máximo (coincide con PARAMS["max_usd_por_operacion"])
KELLY_MIN_EDGE    = 0.02   # Kelly < 2% → no hay edge suficiente, usar floor


def calcular_kelly(ib_ticker: str) -> float:
    """
    Calcula la fracción de Kelly para un activo dado su IB ticker.

    Retorna: fracción Kelly (0.0 a 1.0)
      - 0.0 si no hay stats o Kelly negativo
      - Half-Kelly si stats válidos con n_trades >= MIN_TRADES_STATS
      - Fallback 0.075 (= convicción 75% en el esquema anterior) si n_trades < MIN_TRADES_STATS

    Prioridad de stats:
      1. kelly_stats_live.json (trades reales confirmados por IB)
      2. KELLY_STATS (backtest 2 años — fallback)
    """
    # 1. Stats live de trades reales (prioridad)
    live = _cargar_kelly_live()
    stats = live.get(ib_ticker)

    # 2. Fallback a backtest si no hay datos live suficientes
    if not stats or stats.get("n_trades", 0) < MIN_TRADES_STATS:
        stats = KELLY_STATS.get(ib_ticker)

    if not stats or stats["n_trades"] < MIN_TRADES_STATS:
        # Sin datos suficientes — fallback neutro (7.5% del capital = $7,500 en $100k)
        return 0.075

    win  = stats["win_rate"]
    rr   = stats["rr"]

    if rr <= 0:
        return 0.0

    kelly_full = win - (1 - win) / rr

    if kelly_full <= 0:
        # Kelly negativo = edge negativo — usar solo el floor mínimo
        return 0.0

    return kelly_full * KELLY_FRACTION  # Half-Kelly


def calcular_kelly_usd(
    ib_ticker:  str,
    capital:    float = 100_000,
    max_usd:    float = MAX_USD_POSICION,
    conviccion: float = 75,
) -> float:
    """
    Retorna el monto en USD óptimo para una posición en un activo dado.

    Parámetros:
        ib_ticker:  IB ticker del activo (ej. "VAPORES", "BTC", "SQM")
        capital:    Capital total de la cuenta en USD
        max_usd:    Límite máximo por operación
        conviccion: Convicción del motor (0-100) — se usa como multiplicador
                    de ajuste fino sobre el Kelly base: activos con Kelly bajo
                    se escalan más con convicción que activos con Kelly alto.

    Retorna: float — USD a invertir en la posición
    """
    kelly_frac = calcular_kelly(ib_ticker)

    if kelly_frac == 0.0:
        # Kelly negativo o sin edge → mínimo absoluto (señal pasó filtros pero no tiene historial)
        return float(MIN_USD_POSICION)

    # Ajuste por convicción: amplifica linealmente entre 0.8x (conv=75%) y 1.2x (conv=95%)
    # Esto evita que convicción alta sobreestime un activo con Kelly bajo
    conv_factor = 0.8 + (conviccion - 75) / 100.0
    conv_factor = max(0.7, min(1.3, conv_factor))

    usd_kelly = capital * kelly_frac * conv_factor

    # Aplicar floor y cap
    usd_final = max(MIN_USD_POSICION, min(usd_kelly, max_usd))

    return round(usd_final, 0)


def get_kelly_resumen() -> list[dict]:
    """
    Retorna tabla de todos los activos con Kelly calculado.
    Útil para el dashboard y para auditoría.
    """
    filas = []
    for ticker, stats in sorted(KELLY_STATS.items()):
        win = stats["win_rate"]
        rr  = stats["rr"]
        n   = stats["n_trades"]
        k_full = (win - (1 - win) / rr) if rr > 0 else -99
        k_half = calcular_kelly(ticker)
        usd_75  = calcular_kelly_usd(ticker, conviccion=75)
        usd_90  = calcular_kelly_usd(ticker, conviccion=90)
        ev = round(win * rr - (1 - win), 3)
        filas.append({
            "ticker":      ticker,
            "win_rate":    f"{win*100:.1f}%",
            "rr":          f"{rr:.2f}x",
            "n_trades":    n,
            "kelly_full":  f"{k_full*100:.1f}%" if k_full > -10 else "N/A",
            "half_kelly":  f"{k_half*100:.1f}%",
            "usd_conv75":  f"${usd_75:,.0f}",
            "usd_conv90":  f"${usd_90:,.0f}",
            "ev_por_trade": f"{ev:+.3f}",
            "n_suficiente": "✓" if n >= MIN_TRADES_STATS else "→ fallback",
        })
    return filas


if __name__ == "__main__":
    print("=== KELLY SIZING — RESUMEN POR ACTIVO ===\n")
    print(f"{'Ticker':<12} {'Win%':>6} {'R/R':>6} {'N':>4} {'½Kelly':>8} {'USD@75%':>10} {'USD@90%':>10} {'EV':>8} {'Stats'}")
    print("-" * 80)
    for f in get_kelly_resumen():
        print(
            f"{f['ticker']:<12} {f['win_rate']:>6} {f['rr']:>6} {f['n_trades']:>4} "
            f"{f['half_kelly']:>8} {f['usd_conv75']:>10} {f['usd_conv90']:>10} "
            f"{f['ev_por_trade']:>8}  {f['n_suficiente']}"
        )
