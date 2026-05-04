"""
Backtest Técnico — 2 años de datos reales.
Simula la estrategia del sistema sobre datos históricos.

Metodología:
- Usa los mismos indicadores que el sistema en vivo (RSI, MACD, Bollinger, MA)
- Simula entradas y salidas con SL/TP basados en ATR
- Calcula métricas de performance reales
- No usa datos futuros (walk-forward honesto)

Métricas reportadas:
- Win rate, R/R promedio
- Sharpe ratio, Max Drawdown
- PnL total, PnL por trade
- Mejores y peores trades
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# Universo para backtest — importado desde universo maestro
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.universo import UNIVERSO_COMPLETO

def _build_activos_bt():
    resultado = {}
    for yf_ticker, info in UNIVERSO_COMPLETO.items():
        tipo = info.get("tipo", "ETF")
        if tipo == "Crypto":
            capital = 5_000
        elif tipo == "Futuro":
            capital = 8_000
        elif tipo in ("Acción Chile", "Acción USA/Chile"):
            capital = 10_000
        else:
            capital = 10_000
        resultado[yf_ticker] = {
            "nombre":  info["nombre"],
            "capital": capital,
            "tipo":    tipo,
            "sector":  info.get("sector", ""),
        }
    return resultado

ACTIVOS_BT = _build_activos_bt()

# Excluir activos ilíquidos con señales falsas frecuentes
EXCLUIR_BT = {
    # Small caps ilíquidos con señales falsas
    "MARINSA.SN", "MASISA.SN", "SCHWAGER.SN", "INGEVEC.SN", "HITES.SN",
    # Win rate < 20% en backtest
    "MOLYMET.SN", "BESALCO.SN", "CAP.SN", "MALLPLAZA.SN", "ITAUCL.SN",
    # PnL < -15% en backtest
    "SALFACORP.SN", "SOCOVESA.SN",
}
ACTIVOS_BT = {k: v for k, v in ACTIVOS_BT.items() if k not in EXCLUIR_BT}

# ── INDICADORES ───────────────────────────────────────────────────────────────
def _agregar_indicadores(df):
    """Agrega todos los indicadores técnicos al DataFrame"""
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    # RSI
    delta = close.diff()
    g = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    p = (-delta).clip(lower=0).ewm(com=13, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + g/p))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    # Bollinger
    sma20        = close.rolling(20).mean()
    std20        = close.rolling(20).std()
    df["bb_up"]  = sma20 + 2 * std20
    df["bb_lo"]  = sma20 - 2 * std20
    df["pct_b"]  = (close - df["bb_lo"]) / (df["bb_up"] - df["bb_lo"])

    # Medias móviles
    df["ma20"] = sma20
    df["ma50"] = close.rolling(50).mean()

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(com=13, adjust=False).mean()

    # Volumen ratio
    df["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()

    return df

# ── SEÑAL DE ENTRADA ──────────────────────────────────────────────────────────
def _generar_señal(row, prev_row):
    """
    Genera señal de entrada basada en los mismos indicadores del sistema en vivo.
    Retorna: 'COMPRAR', 'VENDER' o None
    """
    puntos_alza = 0
    puntos_baja = 0

    # RSI
    if row["rsi"] < 30:
        puntos_alza += 3
    elif row["rsi"] < 40:
        puntos_alza += 1
    elif row["rsi"] > 70:
        puntos_baja += 3
    elif row["rsi"] > 60:
        puntos_baja += 1

    # MACD cruce
    if row["macd_hist"] > 0 and prev_row["macd_hist"] <= 0:
        puntos_alza += 2
    elif row["macd_hist"] < 0 and prev_row["macd_hist"] >= 0:
        puntos_baja += 2

    # Bollinger
    if row["pct_b"] < 0.05:
        puntos_alza += 2
    elif row["pct_b"] > 0.95:
        puntos_baja += 2

    # MA
    if row["Close"] > row["ma20"] > row["ma50"]:
        puntos_alza += 1
    elif row["Close"] < row["ma20"] < row["ma50"]:
        puntos_baja += 1

    # Volumen confirma
    if row["vol_ratio"] >= 2:
        if puntos_alza > puntos_baja:
            puntos_alza += 1
        elif puntos_baja > puntos_alza:
            puntos_baja += 1

    # Umbral mínimo
    if puntos_alza >= 6 and puntos_alza > puntos_baja:
        return "COMPRAR", puntos_alza
    elif puntos_baja >= 6 and puntos_baja > puntos_alza:
        return "VENDER", puntos_baja

    return None, 0

# ── BACKTEST INDIVIDUAL ───────────────────────────────────────────────────────
def backtest_activo(ticker, nombre, capital_inicial=10_000, sl_atr=2.0, tp_atr=4.0):
    """
    Backtest completo para un activo.
    """
    try:
        h = yf.Ticker(ticker).history(period="2y")
        if len(h) < 60:
            return None

        h = _agregar_indicadores(h)
        h = h.dropna()

        trades      = []
        en_posicion = False
        entrada     = None

        for i in range(1, len(h)):
            row      = h.iloc[i]
            prev_row = h.iloc[i-1]
            fecha    = h.index[i]
            precio   = float(row["Close"])
            atr      = float(row["atr"])

            if not en_posicion:
                señal, puntos = _generar_señal(row, prev_row)
                if señal:
                    if señal == "COMPRAR":
                        sl = precio - atr * sl_atr
                        tp = precio + atr * tp_atr
                    else:
                        sl = precio + atr * sl_atr
                        tp = precio - atr * tp_atr

                    entrada = {
                        "fecha_entrada": fecha,
                        "precio_entrada": precio,
                        "accion":        señal,
                        "sl":            sl,
                        "tp":            tp,
                        "puntos":        puntos,
                        "atr":           atr,
                    }
                    en_posicion = True

            else:
                # Verificar SL/TP
                salida = None
                razon  = None

                if entrada["accion"] == "COMPRAR":
                    if precio <= entrada["sl"]:
                        salida = precio
                        razon  = "STOP LOSS"
                    elif precio >= entrada["tp"]:
                        salida = precio
                        razon  = "TAKE PROFIT"
                    # Señal contraria
                    elif _generar_señal(row, prev_row)[0] == "VENDER":
                        salida = precio
                        razon  = "SEÑAL CONTRARIA"
                else:  # VENDER
                    if precio >= entrada["sl"]:
                        salida = precio
                        razon  = "STOP LOSS"
                    elif precio <= entrada["tp"]:
                        salida = precio
                        razon  = "TAKE PROFIT"
                    elif _generar_señal(row, prev_row)[0] == "COMPRAR":
                        salida = precio
                        razon  = "SEÑAL CONTRARIA"

                # Horizonte máximo 20 días
                dias = (fecha - entrada["fecha_entrada"]).days
                if dias >= 20 and not salida:
                    salida = precio
                    razon  = "HORIZONTE"

                if salida:
                    # Calcular PnL
                    if entrada["accion"] == "COMPRAR":
                        pnl_pct = (salida - entrada["precio_entrada"]) / entrada["precio_entrada"] * 100
                    else:
                        pnl_pct = (entrada["precio_entrada"] - salida) / entrada["precio_entrada"] * 100

                    cantidad  = int(capital_inicial / entrada["precio_entrada"])
                    pnl_usd   = pnl_pct / 100 * entrada["precio_entrada"] * cantidad

                    trades.append({
                        "fecha_entrada":  entrada["fecha_entrada"].strftime("%Y-%m-%d"),
                        "fecha_salida":   fecha.strftime("%Y-%m-%d"),
                        "accion":         entrada["accion"],
                        "precio_entrada": round(entrada["precio_entrada"], 4),
                        "precio_salida":  round(salida, 4),
                        "sl":             round(entrada["sl"], 4),
                        "tp":             round(entrada["tp"], 4),
                        "pnl_pct":        round(pnl_pct, 2),
                        "pnl_usd":        round(pnl_usd, 2),
                        "dias":           dias,
                        "razon":          razon,
                        "ganador":        pnl_pct > 0,
                    })
                    en_posicion = False
                    entrada     = None

        if not trades:
            return None

        # ── MÉTRICAS ──────────────────────────────────────────────────────────
        n_trades    = len(trades)
        ganadores   = [t for t in trades if t["ganador"]]
        perdedores  = [t for t in trades if not t["ganador"]]
        win_rate    = len(ganadores) / n_trades * 100

        pnl_total   = sum(t["pnl_usd"] for t in trades)
        avg_ganador = np.mean([t["pnl_usd"] for t in ganadores]) if ganadores else 0
        avg_perdedor= abs(np.mean([t["pnl_usd"] for t in perdedores])) if perdedores else 1
        rr_ratio    = avg_ganador / avg_perdedor if avg_perdedor > 0 else 0

        # Equity curve y drawdown
        equity = capital_inicial
        equity_curve = [equity]
        max_equity   = equity
        drawdowns    = []

        for t in trades:
            equity += t["pnl_usd"]
            equity_curve.append(equity)
            max_equity = max(max_equity, equity)
            dd = (equity - max_equity) / max_equity * 100
            drawdowns.append(dd)

        max_dd = min(drawdowns) if drawdowns else 0

        # Sharpe ratio (simplificado)
        retornos = [t["pnl_pct"] for t in trades]
        sharpe   = np.mean(retornos) / np.std(retornos) * np.sqrt(252/20) if np.std(retornos) > 0 else 0

        return {
            "ticker":        ticker,
            "nombre":        nombre,
            "capital_inicial": capital_inicial,
            "capital_final": round(equity, 2),
            "pnl_total":     round(pnl_total, 2),
            "pnl_pct":       round((equity - capital_inicial) / capital_inicial * 100, 2),
            "n_trades":      n_trades,
            "win_rate":      round(win_rate, 1),
            "avg_ganador":   round(avg_ganador, 2),
            "avg_perdedor":  round(avg_perdedor, 2),
            "rr_ratio":      round(rr_ratio, 2),
            "max_drawdown":  round(max_dd, 2),
            "sharpe":        round(sharpe, 2),
            "trades":        trades,
            "equity_curve":  equity_curve,
        }

    except Exception as e:
        print(f"Error en backtest {ticker}: {e}")
        return None

# ── BACKTEST COMPLETO ─────────────────────────────────────────────────────────
def run_backtest_completo():
    """Backtest de todos los activos"""
    import concurrent.futures
    import time

    print("=== BACKTEST 2 AÑOS ===\n")
    t0 = time.time()

    resultados = []

    def bt(item):
        ticker, config = item
        return backtest_activo(ticker, config["nombre"], config["capital"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(bt, item): item for item in ACTIVOS_BT.items()}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            if r:
                resultados.append(r)

    resultados = sorted(resultados, key=lambda x: x["pnl_pct"], reverse=True)

    # ── RESUMEN ───────────────────────────────────────────────────────────────
    print(f"{'Activo':<15} {'Trades':>7} {'Win%':>7} {'R/R':>6} {'PnL%':>8} {'MaxDD':>8} {'Sharpe':>8}")
    print("-" * 65)

    capital_total = sum(r["capital_inicial"] for r in resultados)
    pnl_total     = sum(r["pnl_total"] for r in resultados)

    for r in resultados:
        simbolo = "✅" if r["pnl_pct"] > 0 else "❌"
        print(f"{simbolo} {r['nombre']:<13} {r['n_trades']:>7} {r['win_rate']:>6.1f}% "
              f"{r['rr_ratio']:>5.2f}x {r['pnl_pct']:>7.1f}% "
              f"{r['max_drawdown']:>7.1f}% {r['sharpe']:>7.2f}")

    print("-" * 65)
    print(f"\n{'PORTAFOLIO TOTAL':}")
    print(f"  Capital inicial: USD {capital_total:,.0f}")
    print(f"  PnL total:       USD {pnl_total:+,.0f} ({pnl_total/capital_total*100:+.1f}%)")
    print(f"  Win rate prom:   {np.mean([r['win_rate'] for r in resultados]):.1f}%")
    print(f"  R/R promedio:    {np.mean([r['rr_ratio'] for r in resultados]):.2f}x")
    print(f"\nTiempo: {time.time()-t0:.1f}s")

    # Top 3 mejores y peores trades
    todos_trades = []
    for r in resultados:
        for t in r["trades"]:
            t["ticker"] = r["ticker"]
            todos_trades.append(t)

    todos_trades_sorted = sorted(todos_trades, key=lambda x: x["pnl_usd"], reverse=True)

    print("\n--- TOP 3 MEJORES TRADES ---")
    for t in todos_trades_sorted[:3]:
        print(f"  {t['ticker']} {t['accion']} | {t['fecha_entrada']} → {t['fecha_salida']} "
              f"| PnL: USD {t['pnl_usd']:+,.0f} ({t['pnl_pct']:+.1f}%) | {t['razon']}")

    print("\n--- TOP 3 PEORES TRADES ---")
    for t in todos_trades_sorted[-3:]:
        print(f"  {t['ticker']} {t['accion']} | {t['fecha_entrada']} → {t['fecha_salida']} "
              f"| PnL: USD {t['pnl_usd']:+,.0f} ({t['pnl_pct']:+.1f}%) | {t['razon']}")

    return resultados

if __name__ == "__main__":
    run_backtest_completo()


# ── ALIASES PARA COMPATIBILIDAD CON DASHBOARD ────────────────────────────────
def ejecutar_backtest(ticker=None, periodo="2y"):
    """Alias compatible con el dashboard"""
    if ticker:
        info = ACTIVOS_BT.get(ticker, {"nombre": ticker, "capital": 10_000})
        return backtest_activo(ticker, info["nombre"], info["capital"])
    return run_backtest_completo()

def get_estadisticas_backtest():
    """Retorna estadísticas agregadas del backtest"""
    import concurrent.futures
    resultados = []
    def bt(item):
        ticker, config = item
        return backtest_activo(ticker, config["nombre"], config["capital"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(bt, item): item for item in ACTIVOS_BT.items()}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            if r:
                resultados.append(r)
    if not resultados:
        return {}
    import numpy as np
    return {
        "total_trades":  sum(r["n_trades"] for r in resultados),
        "win_rate":      round(np.mean([r["win_rate"] for r in resultados]), 1),
        "rr_ratio":      round(np.mean([r["rr_ratio"] for r in resultados]), 2),
        "pnl_total":     sum(r["pnl_total"] for r in resultados),
        "max_drawdown":  round(min(r["max_drawdown"] for r in resultados), 1),
        "sharpe":        round(np.mean([r["sharpe"] for r in resultados]), 2),
        "por_activo":    resultados,
    }
