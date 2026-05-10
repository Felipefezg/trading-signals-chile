"""
Momentum Intraday — engine/momentum_intraday.py

Detecta aceleración de precio sostenida en las últimas barras de 1 minuto.
Es una fuente FAST: captura el estado del mercado en el ciclo actual.

Señal válida cuando:
  (a) El precio se movió significativamente relativo al ATR del día
  (b) El volumen aceleró en la misma dirección (descarta spikes aislados)
  (c) Las últimas N barras son consistentes (no solo una vela grande)

Universo: acciones USA/Chile + ETFs — excluye acciones .SN puras
(datos 1m de Santiago son esparsos y poco confiables en yfinance).

Parámetros:
  VENTANA_BARRAS   = 30   barras de 1m analizadas (= últimos 30 min)
  VOL_WINDOW_SPLIT = 15   barras para comparar vol reciente vs previo
  MIN_CONSISTENCIA = 0.60  fracción mínima de barras en la dirección principal
"""

from __future__ import annotations  # Python 3.9: permite dict | None en annotations

import time
import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

from engine.universo import get_tickers_at

# ── PARÁMETROS ────────────────────────────────────────────────────────────────
VENTANA_BARRAS   = 30    # barras de 1m a analizar
VOL_WINDOW_SPLIT = 15    # split para vol_accel: últimas N vs anteriores N
MIN_CONSISTENCIA = 0.60  # 60% de barras en la dirección dominante
MAX_ACTIVOS      = 25    # máx activos a analizar (limitar llamadas yfinance)

# Tipos de activo con datos 1m confiables en yfinance
TIPOS_CON_1M = {"Acción USA/Chile", "ETF"}

# ── HORARIO ───────────────────────────────────────────────────────────────────
def es_horario_mercado():
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    from datetime import time as dtime
    # Necesitamos al menos 30 min de datos: activo desde 10:00 ET
    return dtime(10, 0) <= now.time() <= dtime(16, 0)

# ── FETCH Y ANÁLISIS INDIVIDUAL ───────────────────────────────────────────────
def _analizar_momentum(yf_ticker: str, nombre: str) -> dict | None:
    """
    Analiza el momentum intraday de un ticker.
    Retorna dict con score/dirección o None si sin señal o datos insuficientes.
    """
    try:
        tk  = yf.Ticker(yf_ticker)
        h1m = tk.history(period="1d", interval="1m")

        if len(h1m) < VENTANA_BARRAS + 5:
            return None

        reciente = h1m.tail(VENTANA_BARRAS).copy()
        closes   = reciente["Close"]
        highs    = reciente["High"]
        lows     = reciente["Low"]
        volumes  = reciente["Volume"]

        precio_actual = float(closes.iloc[-1])
        precio_inicio = float(closes.iloc[0])
        if precio_inicio <= 0 or precio_actual <= 0:
            return None

        cambio_pct = (precio_actual - precio_inicio) / precio_inicio * 100

        # ── ATR (1m, últimas 14 barras) ───────────────────────────────────
        h_atr = h1m.tail(14)
        tr    = pd.concat([
            h_atr["High"] - h_atr["Low"],
            (h_atr["High"] - h_atr["Close"].shift(1)).abs(),
            (h_atr["Low"]  - h_atr["Close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.mean()) if len(tr) > 0 else 0

        if atr <= 0:
            return None

        # Momentum normalizado: cuántos ATR se movió en la ventana
        atr_pct         = atr / precio_actual * 100
        momentum_norm   = abs(cambio_pct) / atr_pct if atr_pct > 0 else 0

        # ── Consistencia — fracción de barras en la dirección dominante ───
        diffs      = closes.diff().dropna()
        n_alcistas = int((diffs > 0).sum())
        n_bajistas = int((diffs < 0).sum())
        n_total    = len(diffs)
        if n_total == 0:
            return None

        if cambio_pct > 0:
            consistencia = n_alcistas / n_total
        else:
            consistencia = n_bajistas / n_total

        if consistencia < MIN_CONSISTENCIA:
            return None  # Movimiento errático, no momentum sostenido

        # ── Aceleración de volumen ─────────────────────────────────────────
        vol_reciente = float(volumes.tail(VOL_WINDOW_SPLIT).sum())
        vol_previo   = float(volumes.head(VOL_WINDOW_SPLIT).sum())
        vol_accel    = vol_reciente / vol_previo if vol_previo > 0 else 1.0

        # ── Score ─────────────────────────────────────────────────────────
        # Requiere momentum normalizado mínimo Y aceleración de volumen
        if momentum_norm >= 2.0 and vol_accel >= 1.5:
            score = 3
            intensidad = "fuerte"
        elif momentum_norm >= 1.3 and vol_accel >= 1.2:
            score = 2
            intensidad = "moderado"
        elif momentum_norm >= 0.8 and vol_accel >= 1.1:
            score = 1
            intensidad = "leve"
        else:
            return None  # Insuficiente para generar señal

        direccion = "ALZA" if cambio_pct > 0 else "BAJA"
        descripcion = (
            f"Momentum {intensidad} {cambio_pct:+.2f}% en 30m "
            f"({momentum_norm:.1f}×ATR) | vol_accel={vol_accel:.1f}× "
            f"| consistencia={consistencia:.0%}"
        )

        return {
            "activo_motor":  yf_ticker,
            "nombre":        nombre,
            "score":         score,
            "direccion":     direccion,
            "cambio_pct":    round(cambio_pct, 3),
            "momentum_norm": round(momentum_norm, 2),
            "vol_accel":     round(vol_accel, 2),
            "consistencia":  round(consistencia, 2),
            "atr_pct":       round(atr_pct, 4),
            "descripcion":   descripcion,
            "timestamp":     datetime.now().isoformat(),
        }
    except Exception:
        return None

# ── GET SEÑALES ───────────────────────────────────────────────────────────────
def get_señales_momentum(min_score: int = 1, timeout: float = 30.0) -> list:
    """
    Retorna señales de momentum intraday para el universo líquido.
    Solo disponible a partir de las 10:00 ET (necesita ≥30 min de historia).

    Returns:
        Lista de dicts con keys: activo_motor, score, direccion, descripcion, ...
    """
    if not es_horario_mercado():
        return []

    universo = get_tickers_at()

    # Solo activos con datos 1m confiables
    activos = {
        yf_t: info for yf_t, info in universo.items()
        if info.get("tipo") in TIPOS_CON_1M
    }
    activos = dict(list(activos.items())[:MAX_ACTIVOS])

    if not activos:
        return []

    señales = []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {
            ex.submit(
                _analizar_momentum,
                yf_t,
                info.get("nombre", yf_t),
            ): yf_t
            for yf_t, info in activos.items()
        }
        for fut in as_completed(futs, timeout=timeout):
            try:
                resultado = fut.result(timeout=1.0)
                if resultado and resultado["score"] >= min_score:
                    señales.append(resultado)
            except Exception:
                pass

    return sorted(señales, key=lambda x: x["score"], reverse=True)

if __name__ == "__main__":
    print("=== MOMENTUM INTRADAY ===\n")
    if not es_horario_mercado():
        print("Mercado cerrado o aún antes de las 10:00 ET — datos insuficientes")
    else:
        t0 = time.time()
        señales = get_señales_momentum(min_score=1)
        print(f"Señales detectadas: {len(señales)}")
        for s in señales:
            print(f"  [{s['direccion']}] score={s['score']}  {s['nombre']:20s}  {s['descripcion'][:70]}")
        print(f"\nTiempo: {time.time()-t0:.1f}s")
