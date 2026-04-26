"""
Módulo de performance y PnL.
Calcula métricas de rendimiento del sistema:
- PnL por posición abierta y cerrada
- Curva de equity
- Win rate, drawdown, Sharpe ratio
- Comparación vs benchmarks (IPSA, S&P500)
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
import yfinance as yf

DB_PATH         = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "historial.db")
POSICIONES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "posiciones.json")
TRADES_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trades_cerrados.json")

CAPITAL_INICIAL = 100_000  # USD

# ── TRADES CERRADOS ───────────────────────────────────────────────────────────
def _cargar_trades_cerrados():
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE) as f:
                return json.load(f)
    except:
        pass
    return []

def _guardar_trades_cerrados(trades):
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)

def registrar_trade_cerrado(ticker, accion, cantidad, precio_entrada,
                             precio_salida, fecha_entrada, fecha_salida=None):
    """Registra un trade cerrado para el cálculo de PnL histórico."""
    trades = _cargar_trades_cerrados()
    pnl_unit = precio_salida - precio_entrada if accion == "COMPRAR" else precio_entrada - precio_salida
    pnl_total = round(pnl_unit * cantidad, 2)
    pnl_pct   = round((pnl_unit / precio_entrada) * 100, 2) if precio_entrada > 0 else 0

    trades.append({
        "ticker":          ticker,
        "accion":          accion,
        "cantidad":        cantidad,
        "precio_entrada":  precio_entrada,
        "precio_salida":   precio_salida,
        "pnl_total":       pnl_total,
        "pnl_pct":         pnl_pct,
        "fecha_entrada":   str(fecha_entrada),
        "fecha_salida":    str(fecha_salida or datetime.now().isoformat()),
        "resultado":       "ganador" if pnl_total > 0 else "perdedor",
    })
    _guardar_trades_cerrados(trades)
    return pnl_total

# ── PnL POSICIONES ABIERTAS ───────────────────────────────────────────────────
def get_pnl_posiciones_abiertas():
    """Calcula PnL no realizado de posiciones abiertas."""
    try:
        if not os.path.exists(POSICIONES_FILE):
            return []
        with open(POSICIONES_FILE) as f:
            posiciones = json.load(f)
    except:
        return []

    resultado = []
    for ticker, pos in posiciones.items():
        precio_entrada = pos.get("precio_entrada", 0)
        cantidad       = pos.get("cantidad", 0)
        accion         = pos.get("accion", "COMPRAR")

        # Obtener precio actual
        yf_map = {
            "ECH": "ECH", "SQM": "SQM", "SPY": "SPY", "GLD": "GLD",
            "BTC": "BTC-USD", "HG": "HG=F", "CL": "CL=F", "GC": "GC=F",
        }
        yf_ticker = yf_map.get(ticker, ticker)
        try:
            h = yf.Ticker(yf_ticker).history(period="2d")
            precio_actual = float(h["Close"].iloc[-1]) if not h.empty else precio_entrada
        except:
            precio_actual = precio_entrada

        if accion == "COMPRAR":
            pnl_unit = precio_actual - precio_entrada
        else:
            pnl_unit = precio_entrada - precio_actual

        pnl_total = round(pnl_unit * cantidad, 2)
        pnl_pct   = round((pnl_unit / precio_entrada) * 100, 2) if precio_entrada > 0 else 0

        fecha_entrada = datetime.fromisoformat(pos["fecha_entrada"])
        dias = (datetime.now() - fecha_entrada).days

        resultado.append({
            "ticker":         ticker,
            "accion":         accion,
            "cantidad":       cantidad,
            "precio_entrada": round(precio_entrada, 2),
            "precio_actual":  round(precio_actual, 2),
            "pnl_total":      pnl_total,
            "pnl_pct":        pnl_pct,
            "dias_abierta":   dias,
            "sl":             pos.get("sl"),
            "tp":             pos.get("tp"),
            "horizonte":      pos.get("horizonte"),
        })

    return resultado

# ── MÉTRICAS DE PERFORMANCE ───────────────────────────────────────────────────
def get_metricas_performance():
    """Calcula métricas completas de performance del sistema."""
    trades = _cargar_trades_cerrados()
    posiciones_pnl = get_pnl_posiciones_abiertas()

    # PnL realizado (trades cerrados)
    pnl_realizado   = sum(t["pnl_total"] for t in trades)
    ganadores       = [t for t in trades if t["pnl_total"] > 0]
    perdedores      = [t for t in trades if t["pnl_total"] <= 0]

    # PnL no realizado (posiciones abiertas)
    pnl_no_realizado = sum(p["pnl_total"] for p in posiciones_pnl)

    # PnL total
    pnl_total = pnl_realizado + pnl_no_realizado

    # Win rate
    n_trades   = len(trades)
    win_rate   = round(len(ganadores) / n_trades * 100, 1) if n_trades > 0 else 0

    # Profit factor
    gross_profit = sum(t["pnl_total"] for t in ganadores)
    gross_loss   = abs(sum(t["pnl_total"] for t in perdedores))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    # Promedio ganador / perdedor
    avg_ganador  = round(gross_profit / len(ganadores), 2) if ganadores else 0
    avg_perdedor = round(gross_loss / len(perdedores), 2) if perdedores else 0

    # Ratio R/R real
    rr_real = round(avg_ganador / avg_perdedor, 2) if avg_perdedor > 0 else float("inf")

    # Drawdown máximo (simplificado sobre trades)
    equity_curve = [CAPITAL_INICIAL]
    for t in sorted(trades, key=lambda x: x["fecha_entrada"]):
        equity_curve.append(equity_curve[-1] + t["pnl_total"])

    max_drawdown = 0
    peak = equity_curve[0]
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100 if peak > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

    # Capital actual
    capital_actual = CAPITAL_INICIAL + pnl_total
    retorno_total  = round(pnl_total / CAPITAL_INICIAL * 100, 2)

    return {
        "capital_inicial":    CAPITAL_INICIAL,
        "capital_actual":     round(capital_actual, 2),
        "pnl_total":          round(pnl_total, 2),
        "pnl_realizado":      round(pnl_realizado, 2),
        "pnl_no_realizado":   round(pnl_no_realizado, 2),
        "retorno_total_pct":  retorno_total,
        "n_trades":           n_trades,
        "n_ganadores":        len(ganadores),
        "n_perdedores":       len(perdedores),
        "win_rate":           win_rate,
        "profit_factor":      profit_factor,
        "avg_ganador":        avg_ganador,
        "avg_perdedor":       avg_perdedor,
        "rr_real":            rr_real,
        "max_drawdown_pct":   round(max_drawdown, 2),
        "equity_curve":       equity_curve,
        "trades":             trades,
        "posiciones_abiertas": posiciones_pnl,
    }

def get_benchmark_retorno(ticker, dias=30):
    """Obtiene retorno del benchmark en los últimos N días."""
    try:
        h = yf.Ticker(ticker).history(period=f"{dias}d")
        if len(h) < 2:
            return 0
        retorno = ((h["Close"].iloc[-1] / h["Close"].iloc[0]) - 1) * 100
        return round(float(retorno), 2)
    except:
        return 0

def get_benchmarks():
    """Retorna retornos de benchmarks para comparación."""
    return {
        "IPSA (ECH)":    get_benchmark_retorno("ECH", 30),
        "S&P 500 (SPY)": get_benchmark_retorno("SPY", 30),
        "BTC":           get_benchmark_retorno("BTC-USD", 30),
        "Oro (GLD)":     get_benchmark_retorno("GLD", 30),
    }

if __name__ == "__main__":
    print("=== PERFORMANCE ===")
    m = get_metricas_performance()
    print(f"Capital inicial: USD {m['capital_inicial']:,.0f}")
    print(f"Capital actual:  USD {m['capital_actual']:,.0f}")
    print(f"PnL total:       USD {m['pnl_total']:+,.2f} ({m['retorno_total_pct']:+.2f}%)")
    print(f"PnL realizado:   USD {m['pnl_realizado']:+,.2f}")
    print(f"PnL no realizado:USD {m['pnl_no_realizado']:+,.2f}")
    print(f"Trades:          {m['n_trades']} ({m['n_ganadores']}G / {m['n_perdedores']}P)")
    print(f"Win rate:        {m['win_rate']}%")
    print(f"Profit factor:   {m['profit_factor']}")
    print(f"Drawdown máx:    {m['max_drawdown_pct']}%")
    print(f"\nPosiciones abiertas: {len(m['posiciones_abiertas'])}")
    for p in m['posiciones_abiertas']:
        icon = "🟢" if p['pnl_total'] >= 0 else "🔴"
        print(f"  {icon} {p['ticker']}: {p['pnl_pct']:+.2f}% | USD {p['pnl_total']:+,.2f}")
    print("\nBenchmarks (30 días):")
    for b, r in get_benchmarks().items():
        print(f"  {b}: {r:+.2f}%")
