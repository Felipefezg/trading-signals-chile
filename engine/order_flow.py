"""
Order Flow — Análisis de flujo de órdenes vía yfinance.

Calcula métricas de presión compradora/vendedora a partir de:
- Bid/Ask size (acciones USA cuando disponible vía yfinance info)
- Posición del precio en el rango intraday reciente (proxy universal)
- Volumen en barras recientes vs promedio

Solo disponible en horario de mercado (lunes-viernes 9:30-16:00 ET).

Reemplaza la versión IB Level 2 (clientId 70) que tenía 0/197 de éxito
por conflictos de reconexión. yfinance provee señal equivalente sin
gestión de conexiones ni dependencia del Gateway IB.
"""

import time
import yfinance as yf
from datetime import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

from engine.universo import get_tickers_at

# ── HORARIO ───────────────────────────────────────────────────────────────────
def es_horario_mercado():
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    from datetime import time as dtime
    return dtime(9, 30) <= now.time() <= dtime(16, 0)

# ── FETCH INDIVIDUAL ──────────────────────────────────────────────────────────
def _fetch_order_flow_ticker(yf_ticker, nombre, tipo):
    """
    Obtiene métricas de order flow para un ticker.

    Para acciones USA/ETF: intenta bid/ask/bidSize/askSize desde yfinance info.
    Si no disponibles (o acciones Chile): usa posición del precio en rango
    intraday reciente como proxy de imbalance.

    Retorna dict compatible con analizar_book() o None si sin datos.
    """
    try:
        tk = yf.Ticker(yf_ticker)

        # ── Intraday 1m — últimas 30 barras para señal de corto plazo ────
        h1m = tk.history(period="1d", interval="1m")
        if len(h1m) < 5:
            return None

        # Precio y rango reciente (últimas 15m)
        reciente = h1m.tail(15)
        last      = float(h1m["Close"].iloc[-1])
        high_rec  = float(reciente["High"].max())
        low_rec   = float(reciente["Low"].min())

        # ── Bid/Ask size si disponibles (solo USA en horario) ─────────────
        bid_size = 0
        ask_size = 0
        bid      = 0.0
        ask      = 0.0

        if tipo in ("Acción USA/Chile", "ETF"):
            try:
                info     = tk.info
                bid      = float(info.get("bid", 0) or 0)
                ask      = float(info.get("ask", 0) or 0)
                bid_size = int(info.get("bidSize", 0) or 0)
                ask_size = int(info.get("askSize", 0) or 0)
            except Exception:
                pass

        # Spread
        if bid > 0 and ask > 0 and ask > bid:
            spread     = round(ask - bid, 4)
            spread_pct = round(spread / bid * 100, 4)
        else:
            spread     = 0.0
            spread_pct = 0.0

        # ── Imbalance ─────────────────────────────────────────────────────
        # Preferencia: bid/ask size real → posición intraday reciente
        if bid_size > 0 or ask_size > 0:
            vol_total = bid_size + ask_size
            imbalance = (bid_size / vol_total * 100) if vol_total > 0 else 50.0
        else:
            rango_rec = high_rec - low_rec
            if rango_rec > 0:
                pos = (last - low_rec) / rango_rec
                imbalance = pos * 100  # 0-100
            else:
                # Usar pendiente del cierre reciente como proxy
                closes = list(reciente["Close"])
                if closes[-1] > closes[0]:
                    imbalance = 65.0
                elif closes[-1] < closes[0]:
                    imbalance = 35.0
                else:
                    imbalance = 50.0

        # ── Señal de dirección ────────────────────────────────────────────
        if imbalance > 65:
            direccion = "ALZA"
            señal     = f"Presión compradora ({imbalance:.1f}%)"
            score     = 3 if imbalance > 75 else 2
        elif imbalance < 35:
            direccion = "BAJA"
            señal     = f"Presión vendedora ({100-imbalance:.1f}% ask)"
            score     = 3 if imbalance < 25 else 2
        elif imbalance > 55:
            direccion = "ALZA"
            señal     = f"Leve presión compradora ({imbalance:.1f}%)"
            score     = 1
        elif imbalance < 45:
            direccion = "BAJA"
            señal     = f"Leve presión vendedora ({100-imbalance:.1f}%)"
            score     = 1
        else:
            direccion = "NEUTRO"
            señal     = f"Flujo neutro ({imbalance:.1f}%)"
            score     = 0

        # Penalizar spread ancho (baja liquidez)
        if spread_pct > 0.5 and score > 0:
            score = max(0, score - 1)
            señal += f" [spread {spread_pct:.2f}%]"

        return {
            "symbol":              nombre,
            "yf_ticker":           yf_ticker,
            "activo_motor":        yf_ticker,
            "imbalance":           round(imbalance, 1),
            "vol_bid":             bid_size,
            "vol_ask":             ask_size,
            "mejor_bid":           round(bid, 4),
            "mejor_ask":           round(ask, 4),
            "spread":              spread,
            "spread_pct":          spread_pct,
            "precio":              round(last, 4),
            "n_levels_bid":        bid_size,
            "n_levels_ask":        ask_size,
            "ordenes_grandes_bid": 0,
            "ordenes_grandes_ask": 0,
            "direccion":           direccion,
            "señal":               señal,
            "score":               score,
            "timestamp":           datetime.now().isoformat(),
        }
    except Exception:
        return None

# ── GET ORDER FLOW ────────────────────────────────────────────────────────────
def get_order_flow(max_activos=20, timeout_datos=35):
    """
    Obtiene order flow para los activos del universo.
    Solo disponible en horario de mercado.
    """
    if not es_horario_mercado():
        return {}

    universo = get_tickers_at()

    # Filtrar activos con datos de order flow confiables
    activos = {
        yf_t: info for yf_t, info in universo.items()
        if info.get("tipo") in ("Acción USA/Chile", "ETF", "Acción Chile")
    }
    activos = dict(list(activos.items())[:max_activos])

    if not activos:
        return {}

    resultados = {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {
            ex.submit(
                _fetch_order_flow_ticker,
                yf_t,
                info.get("nombre", yf_t),
                info.get("tipo", "ETF"),
            ): yf_t
            for yf_t, info in activos.items()
        }
        for fut in as_completed(futs, timeout=timeout_datos):
            yf_t = futs[fut]
            try:
                datos = fut.result(timeout=1.0)
                if datos:
                    resultados[yf_t] = datos
            except Exception:
                pass

    return resultados

# ── SEÑALES ───────────────────────────────────────────────────────────────────
def get_señales_order_flow(min_score=2):
    """
    Retorna señales del order flow compatibles con el motor.
    """
    datos = get_order_flow()
    señales = []

    for yf_t, d in datos.items():
        if d.get("score", 0) >= min_score:
            señales.append({
                "activo":      d["activo_motor"],
                "fuente":      "Order Flow",
                "score":       d["score"],
                "direccion":   d["direccion"],
                "imbalance":   d["imbalance"],
                "descripcion": f"Order Flow {d['symbol']}: {d['señal']}",
            })

    return sorted(señales, key=lambda x: x["score"], reverse=True)

def get_resumen_order_flow():
    """Resumen para el dashboard"""
    if not es_horario_mercado():
        return {
            "disponible": False,
            "razon":      "Order flow solo disponible en horario de mercado",
            "datos":      {},
        }

    datos   = get_order_flow()
    señales = get_señales_order_flow()

    return {
        "disponible":      len(datos) > 0,
        "total":           len(datos),
        "señales":         len(señales),
        "datos":           datos,
        "señales_detalle": señales,
        "timestamp":       datetime.now().isoformat(),
    }

if __name__ == "__main__":
    print("=== ORDER FLOW ===\n")
    if not es_horario_mercado():
        print("Mercado cerrado — Order Flow solo disponible en horario de trading")
        print("Lunes-viernes 9:30-16:00 ET")
    else:
        t0 = time.time()
        resumen = get_resumen_order_flow()
        print(f"Activos analizados: {resumen['total']}")
        print(f"Señales generadas:  {resumen['señales']}")
        for s in resumen["señales_detalle"]:
            print(f"  [{s['direccion']}] {s['activo']} score={s['score']} — {s['descripcion'][:70]}")
        print(f"\nTiempo: {time.time()-t0:.1f}s")
