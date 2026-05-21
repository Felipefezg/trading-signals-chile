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
    # win_rate con ajuste Bayesiano Beta(2,2): para n/n victorias con n pequeño,
    # posterior = (n+2)/(n+4) en vez de 1.0 — evita Kelly irreal de 50%+.
    # El cap de MAX_PCT_POSICION (8%) aplica igual, pero los valores honestos
    # permiten que kelly_sizing escale correctamente con convicción baja.
    "VAPORES":   {"win_rate": 0.80, "rr": 1.67, "n_trades": 5},   # CSAV  +34.7%
    "SMU":       {"win_rate": 0.667,"rr": 5.37, "n_trades": 3},   # SMU   +18.9%
    "CMPC":      {"win_rate": 0.65, "rr": 2.00, "n_trades": 3},   # CMPC  +12.7% (3/3 → wr ajustado 0.65)
    "FALABELLA": {"win_rate": 1.00, "rr": 2.00, "n_trades": 2},   # FAL   +12.4% (n<3 → fallback 7.5%)
    "SQM-B":     {"win_rate": 0.60, "rr": 1.23, "n_trades": 5},   # SQM   +9.9%
    "HABITAT":   {"win_rate": 0.65, "rr": 2.00, "n_trades": 3},   # AFP Habitat +9.6% (3/3 → wr ajustado 0.65)
    "COPEC":     {"win_rate": 0.65, "rr": 2.00, "n_trades": 3},   # COPEC +8.1% (3/3 → wr ajustado 0.65)
    "COLBUN":    {"win_rate": 1.00, "rr": 2.00, "n_trades": 2},   # Colbún +7.7% (n<3 → fallback 7.5%)
    "RIPLEY":    {"win_rate": 0.50, "rr": 2.10, "n_trades": 4},   # Ripley +7.2%
    "ENELAM":    {"win_rate": 1.00, "rr": 2.00, "n_trades": 1},   # Enel Américas (n<3 → fallback 7.5%)
    "ENELCHILE": {"win_rate": 0.667,"rr": 0.66, "n_trades": 6},   # Enel Chile +4.0% (R/R bajo → Kelly ~0)
    "PARAUCO":   {"win_rate": 0.571,"rr": 0.89, "n_trades": 7},   # Parque Arauco +3.0% (Kelly ~0)
    "AGUAS-A":   {"win_rate": 0.667,"rr": 0.75, "n_trades": 6},   # Aguas Andinas +2.9% (Kelly ~0)
    "BSAC":      {"win_rate": 0.50, "rr": 1.10, "n_trades": 4},   # Santander CL  +0.8%
    # Losers conocidos — Kelly negativo → floor mínimo
    "CHILE":     {"win_rate": 0.333,"rr": 1.37, "n_trades": 3},   # Banco Chile -0.9%
    "CENCOSUD":  {"win_rate": 0.50, "rr": 0.87, "n_trades": 4},   # Cencosud -1.0%
    "ANDINA-B":  {"win_rate": 0.50, "rr": 0.62, "n_trades": 2},   # Andina -1.5% (n<3 → fallback)
    "CCU":       {"win_rate": 0.333,"rr": 0.73, "n_trades": 3},   # CCU -6.4%

    # ── ACCIONES USA / ADRs ─────────────────────────────────────────────────
    "SQM":       {"win_rate": 0.60, "rr": 1.27, "n_trades": 5},   # SQM ADR +8.5%
    "BCH":       {"win_rate": 0.50, "rr": 1.44, "n_trades": 2},   # BdCh ADR +0.3% (n<3 → fallback)
    "LTM":       {"win_rate": 0.25, "rr": 3.10, "n_trades": 4},   # LATAM ADR +0.4%

    # ── ETFs ────────────────────────────────────────────────────────────────
    "GLD":       {"win_rate": 0.50, "rr": 2.34, "n_trades": 4},   # Gold ETF +10.0%
    "SPY":       {"win_rate": 1.00, "rr": 2.00, "n_trades": 1},   # S&P 500 (n<3 → fallback)
    "TLT":       {"win_rate": 1.00, "rr": 2.00, "n_trades": 1},   # 20Y Treasury (n<3 → fallback)
    "ECH":       {"win_rate": 0.20, "rr": 1.61, "n_trades": 5},   # iShares Chile (Kelly negativo → floor)

    # ── CRYPTO ──────────────────────────────────────────────────────────────
    "BTC":       {"win_rate": 0.50, "rr": 2.60, "n_trades": 8},   # BTC +30.8%
    "ETH":       {"win_rate": 0.50, "rr": 2.00, "n_trades": 0},   # ETH: sin stats (n<3 → fallback)

    # ── FUTUROS ─────────────────────────────────────────────────────────────
    "GC":        {"win_rate": 0.333,"rr": 6.36, "n_trades": 3},   # Oro futuro +4.0%
    "HG":        {"win_rate": 0.50, "rr": 2.00, "n_trades": 0},   # Cobre futuro — sin historial (fallback)
    # CL excluido del universo activo (R/R=0.44x, estructuralmente roto en señal diaria)

    # ── ETF commodities ───────────────────────────────────────────────────────
    "SLV":       {"win_rate": 0.50, "rr": 2.34, "n_trades": 0},   # Silver ETF — sin historial (fallback)
    "GDX":       {"win_rate": 0.50, "rr": 2.00, "n_trades": 0},   # Gold Miners ETF — sin historial (fallback)

    # ── ETFs USA diversificadores ──────────────────────────────────────────────
    # n_trades=0 → fallback 7.5% hasta acumular ≥3 trades reales.
    "QQQ":       {"win_rate": 0.55, "rr": 1.80, "n_trades": 0},   # Nasdaq 100
    "IWM":       {"win_rate": 0.50, "rr": 1.70, "n_trades": 0},   # Russell 2000
    "XLE":       {"win_rate": 0.50, "rr": 1.90, "n_trades": 0},   # Energy ETF
}

# ── PARÁMETROS DE SIZING (en % del capital — agnósticos al monto) ────────────
KELLY_FRACTION    = 0.5    # Half-Kelly — estándar conservador para live trading
MIN_TRADES_STATS  = 3      # Mínimo de trades para confiar en stats propios
MIN_PCT_POSICION  = 2.0    # Floor mínimo: 2% del capital (era $2k fijo en $100k)
MAX_PCT_POSICION  = 8.0    # Cap máximo:   8% del capital (era $15k fijo en $100k)
KELLY_MIN_EDGE    = 0.02   # Kelly < 2% → no hay edge suficiente, usar floor

# Compatibilidad hacia atrás — calcular USD desde capital real si algún módulo
# antiguo los referencia directamente. Se eliminarán en la próxima limpieza.
# NO usar en código nuevo — usar MIN_PCT_POSICION / MAX_PCT_POSICION.
def _min_usd(capital: float) -> float: return capital * MIN_PCT_POSICION / 100
def _max_usd(capital: float) -> float: return capital * MAX_PCT_POSICION / 100


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


# ── CURVA DE CONVICCIÓN → ESCALA DE SIZING ───────────────────────────────────
# Puntos de anclaje: (convicción %, factor multiplicador sobre Kelly base)
# Interpolación lineal por segmentos.
# Racional:
#   75%  → 0.35×  — señal en umbral mínimo, exposición reducida
#   82%  → 0.65×  — señal moderada
#   88%  → 0.90×  — señal fuerte
#   93%  → 1.10×  — señal de alta convicción (pequeño boost sobre Kelly)
#   100% → 1.30×  — convicción máxima (cap absoluto aplicado después)
_CONV_ANCHORS = [
    (75.0,  0.35),
    (82.0,  0.65),
    (88.0,  0.90),
    (93.0,  1.10),
    (100.0, 1.30),
]

def _conv_scale(conviccion: float, conv_min: float = 75.0) -> float:
    """
    Interpola linealmente la curva de convicción → factor de sizing.
    Retorna el factor multiplicador para aplicar sobre el monto Kelly base.
    """
    if conviccion <= conv_min:
        return _CONV_ANCHORS[0][1]
    if conviccion >= 100.0:
        return _CONV_ANCHORS[-1][1]
    for i in range(len(_CONV_ANCHORS) - 1):
        c0, s0 = _CONV_ANCHORS[i]
        c1, s1 = _CONV_ANCHORS[i + 1]
        if c0 <= conviccion <= c1:
            t = (conviccion - c0) / (c1 - c0)
            return round(s0 + t * (s1 - s0), 4)
    return 1.0


# ── BONUS POR NÚMERO DE FUENTES INDEPENDIENTES ───────────────────────────────
# Más fuentes confirmando → mayor confianza en la señal → sizing más agresivo.
# Solo cuenta fuentes_credibles (post quality-gate del motor).
# Cap en 5 fuentes para no inflar indefinidamente.
_FUENTES_BONUS: dict[int, float] = {
    1: 0.88,   # señal débil — una sola fuente
    2: 1.00,   # baseline (2 fuentes = mínimo operativo normal)
    3: 1.06,   # señal bien confirmada
    4: 1.10,   # señal muy confirmada
    5: 1.14,   # consenso multi-fuente
}
_FUENTES_BONUS_MAX = 1.14  # cap para n ≥ 5


def calcular_kelly_usd(
    ib_ticker:     str,
    capital:       float = None,
    max_pct:       float = MAX_PCT_POSICION,
    min_pct:       float = MIN_PCT_POSICION,
    conviccion:    float = 75.0,
    n_fuentes:     int   = 2,
    factor_calidad: float = 1.0,
) -> float:
    """
    Retorna el monto en USD óptimo para una posición dado el capital REAL de IB.

    Position sizing = f(Kelly base, convicción, n_fuentes, calidad histórica)

    Parámetros:
        ib_ticker:      IB ticker (ej. "VAPORES", "BTC", "SQM")
        capital:        Capital real de IB en USD. Si None → lee desde get_capital_ib().
        max_pct:        % máximo del capital por operación (default 8%)
        min_pct:        % mínimo del capital por operación (default 2%)
        conviccion:     Convicción del motor (0–100) — escala el sizing en curva
                        no-lineal [0.35× @ 75% → 1.30× @ 100%]
        n_fuentes:      Fuentes independientes confirmando la señal (post quality-gate)
                        2 = baseline; bonus hasta +14% en 5+ fuentes
        factor_calidad: Factor de win-rate histórico de las fuentes [0.85, 1.10]
                        calculado por feedback_loop.py

    Retorna: float — USD a invertir, escalado al capital real.

    Ejemplo ($100k capital, SQM, kelly_frac=0.075):
        conv=75, n=2, q=1.0 → $7,500 × 0.35 × 1.00 × 1.00 = $2,625 → floor $2,000
        conv=82, n=3, q=1.0 → $7,500 × 0.65 × 1.06 × 1.00 = $5,163
        conv=88, n=4, q=1.0 → $7,500 × 0.90 × 1.10 × 1.00 = $7,425
        conv=93, n=5, q=1.05→ $7,500 × 1.10 × 1.14 × 1.05 = $9,920 → cap $8,000
    """
    # Capital real desde IB si no se pasa explícitamente
    if capital is None or capital <= 0:
        from engine.motor_automatico import get_capital_ib
        capital = get_capital_ib()

    min_usd = capital * min_pct / 100
    max_usd = capital * max_pct / 100

    kelly_frac = calcular_kelly(ib_ticker)

    if kelly_frac == 0.0:
        # Kelly negativo o sin edge → floor mínimo
        return round(min_usd, 0)

    # ── 1. Convicción → escala no-lineal ─────────────────────────────────────
    conv_factor = _conv_scale(conviccion)

    # ── 2. Bonus por n_fuentes independientes ─────────────────────────────────
    fuentes_bonus = _FUENTES_BONUS.get(min(n_fuentes, 5), _FUENTES_BONUS_MAX)

    # ── 3. Ajuste por calidad histórica de fuentes (win-rate feedback loop) ──
    quality_adj = max(0.88, min(1.10, float(factor_calidad)))

    # ── 4. Sizing final ───────────────────────────────────────────────────────
    usd_kelly = capital * kelly_frac * conv_factor * fuentes_bonus * quality_adj
    usd_final = max(min_usd, min(usd_kelly, max_usd))

    return round(usd_final, 0)


def get_kelly_resumen(capital: float = 100_000) -> list[dict]:
    """
    Retorna tabla de todos los activos con Kelly calculado.
    Útil para el dashboard y para auditoría.
    Muestra el sizing a distintos niveles de convicción y n_fuentes.
    """
    filas = []
    for ticker, stats in sorted(KELLY_STATS.items()):
        win   = stats["win_rate"]
        rr    = stats["rr"]
        n     = stats["n_trades"]
        k_full = (win - (1 - win) / rr) if rr > 0 else -99
        k_half = calcular_kelly(ticker)

        # Ejemplos representativos: (conv, n_fuentes, label)
        usd_min  = calcular_kelly_usd(ticker, capital=capital, conviccion=75, n_fuentes=2)   # umbral
        usd_mod  = calcular_kelly_usd(ticker, capital=capital, conviccion=82, n_fuentes=3)   # moderado
        usd_full = calcular_kelly_usd(ticker, capital=capital, conviccion=90, n_fuentes=4)   # fuerte
        usd_prem = calcular_kelly_usd(ticker, capital=capital, conviccion=95, n_fuentes=5)   # premium
        ev = round(win * rr - (1 - win), 3)

        filas.append({
            "ticker":       ticker,
            "win_rate":     f"{win*100:.1f}%",
            "rr":           f"{rr:.2f}x",
            "n_trades":     n,
            "kelly_full":   f"{k_full*100:.1f}%" if k_full > -10 else "N/A",
            "half_kelly":   f"{k_half*100:.1f}%",
            "usd_75_n2":    f"${usd_min:,.0f}",    # conv=75, 2 fuentes
            "usd_82_n3":    f"${usd_mod:,.0f}",    # conv=82, 3 fuentes
            "usd_90_n4":    f"${usd_full:,.0f}",   # conv=90, 4 fuentes
            "usd_95_n5":    f"${usd_prem:,.0f}",   # conv=95, 5 fuentes
            "ev_por_trade": f"{ev:+.3f}",
            "n_suficiente": "✓" if n >= MIN_TRADES_STATS else "→ fallback",
        })
    return filas


if __name__ == "__main__":
    print("=== KELLY SIZING — RESUMEN POR ACTIVO (capital $100k) ===\n")
    print(
        f"{'Ticker':<12} {'Win%':>6} {'R/R':>6} {'N':>4} {'½K':>6}"
        f"  {'@75/2f':>9} {'@82/3f':>9} {'@90/4f':>9} {'@95/5f':>9}"
        f"  {'EV':>7}  Stats"
    )
    print("-" * 95)
    for f in get_kelly_resumen(capital=100_000):
        print(
            f"{f['ticker']:<12} {f['win_rate']:>6} {f['rr']:>6} {f['n_trades']:>4} {f['half_kelly']:>6}"
            f"  {f['usd_75_n2']:>9} {f['usd_82_n3']:>9} {f['usd_90_n4']:>9} {f['usd_95_n5']:>9}"
            f"  {f['ev_por_trade']:>7}  {f['n_suficiente']}"
        )
    print()
    print("Columnas: @Conv%/Nfuentes → USD asignado")
    print(f"Cap por operación: ${100_000 * MAX_PCT_POSICION / 100:,.0f} | "
          f"Floor: ${100_000 * MIN_PCT_POSICION / 100:,.0f}")
