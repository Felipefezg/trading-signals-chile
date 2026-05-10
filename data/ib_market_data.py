"""
Módulo de datos de mercado en tiempo real.
Obtiene VWAP, volumen, spread y presión de precio vía yfinance.

Solo disponible en horario de mercado (lunes-viernes 9:25-16:05 ET).
Fuera de horario retorna datos vacíos sin error.

Datos disponibles:
- Precio y volumen intraday → confirmación de movimientos
- VWAP → precio promedio ponderado por volumen del día
- Presión compradora/vendedora → posición del precio en rango intraday
- Volumen anormal → ratio vs promedio 90 días escalado por horas transcurridas

Reemplaza la versión IB (clientId 50) que tenía 0/197 de éxito por
conflictos de reconexión con daemon threads. yfinance es equivalente
en calidad de señal y elimina toda la gestión de conexiones.
"""

import time
import yfinance as yf
from datetime import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── UNIVERSO ──────────────────────────────────────────────────────────────────
# yf: ticker yfinance para fetching
# activo_motor: ticker usado internamente en el motor de señales
ACTIVOS_IB = {
    "SQM":  {"yf": "SQM",   "activo_motor": "SQM.SN"},
    "ECH":  {"yf": "ECH",   "activo_motor": "ECH"},
    "GLD":  {"yf": "GLD",   "activo_motor": "GC=F"},
    "SPY":  {"yf": "SPY",   "activo_motor": "SPY"},
    "QQQ":  {"yf": "QQQ",   "activo_motor": "QQQ"},
    "IWM":  {"yf": "IWM",   "activo_motor": "IWM"},
    "XLE":  {"yf": "XLE",   "activo_motor": "XLE"},
    "SLV":  {"yf": "SLV",   "activo_motor": "SLV"},
    "GC=F": {"yf": "GC=F",  "activo_motor": "GC=F"},
    "HG=F": {"yf": "HG=F",  "activo_motor": "HG=F"},
}

# ── HORARIO ───────────────────────────────────────────────────────────────────
def es_horario_mercado():
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    hora = now.time()
    from datetime import time as dtime
    return dtime(9, 25) <= hora <= dtime(16, 5)

# ── FETCH INDIVIDUAL ──────────────────────────────────────────────────────────
def _fetch_activo(symbol, config):
    """
    Obtiene datos de mercado para un activo vía yfinance.
    Usa barras de 5m del día actual para VWAP, volumen y presión de precio.
    """
    yf_ticker = config["yf"]
    try:
        tk   = yf.Ticker(yf_ticker)
        h1d  = tk.history(period="1d", interval="5m")

        if len(h1d) < 3:
            return None

        precio    = float(h1d["Close"].iloc[-1])
        if precio <= 0:
            return None

        # ── VWAP del día ──────────────────────────────────────────────────
        vol_sum = float(h1d["Volume"].sum())
        if vol_sum > 0:
            vwap = float((h1d["Close"] * h1d["Volume"]).sum() / vol_sum)
        else:
            vwap = precio

        # ── Volumen — ratio vs promedio 90 días escalado a horas abiertas ─
        today_vol  = int(vol_sum)
        fi         = tk.fast_info
        avg_vol_3m = getattr(fi, "three_month_average_volume", 0) or 0

        tz_ny   = pytz.timezone("America/New_York")
        now_ny  = datetime.now(tz_ny)
        open_ny = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        horas   = max(0.25, (now_ny - open_ny).total_seconds() / 3600)
        avg_dia = avg_vol_3m * (horas / 6.5) if avg_vol_3m > 0 else today_vol
        vol_ratio = today_vol / avg_dia if avg_dia > 0 else 1.0

        # ── Bid/Ask (proxy intraday si no disponibles) ────────────────────
        bid = float(h1d["Low"].iloc[-1])
        ask = float(h1d["High"].iloc[-1])
        spread_pct = ((ask - bid) / bid * 100) if bid > 0 else 0

        # ── Presión: posición del precio en el rango del día ──────────────
        high_day = float(h1d["High"].max())
        low_day  = float(h1d["Low"].min())
        rango    = high_day - low_day
        if rango > 0:
            pos = (precio - low_day) / rango
            if pos > 0.65:
                señal_presion = "COMPRADORES"
            elif pos < 0.35:
                señal_presion = "VENDEDORES"
            else:
                señal_presion = "NEUTRAL"
        else:
            señal_presion = "NEUTRAL"

        return {
            "symbol":       symbol,
            "activo_motor": config["activo_motor"],
            "precio":       round(precio, 4),
            "bid":          round(bid, 4),
            "ask":          round(ask, 4),
            "spread_pct":   round(spread_pct, 4),
            "last":         round(precio, 4),
            "volume":       today_vol,
            "avg_volume":   int(avg_dia),
            "vol_ratio":    round(vol_ratio, 2),
            "vwap":         round(vwap, 4),
            "iv":           0.0,
            "presion":      señal_presion,
            "timestamp":    datetime.now().isoformat(),
        }
    except Exception:
        return None

# ── OBTENER DATOS ─────────────────────────────────────────────────────────────
def get_datos_mercado_ib(symbols=None, timeout_datos=20):
    """
    Obtiene datos de mercado en tiempo real.

    Returns:
        dict con datos por símbolo, o {} si fuera de horario o sin datos
    """
    if not es_horario_mercado():
        return {}

    if symbols is None:
        symbols = list(ACTIVOS_IB.keys())

    resultados = {}

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {
            ex.submit(_fetch_activo, sym, ACTIVOS_IB[sym]): sym
            for sym in symbols if sym in ACTIVOS_IB
        }
        for fut in as_completed(futs, timeout=timeout_datos + 5):
            sym = futs[fut]
            try:
                datos = fut.result(timeout=1.0)
                if datos:
                    resultados[sym] = datos
            except Exception:
                pass

    return resultados

# ── SEÑALES DESDE DATOS ───────────────────────────────────────────────────────
def get_señales_ib():
    """
    Genera señales de trading basadas en datos de mercado.
    Compatible con el motor de recomendaciones.
    """
    datos = get_datos_mercado_ib()
    if not datos:
        return []

    señales = []
    for symbol, d in datos.items():
        score     = 0
        direccion = "NEUTRO"
        descripcion = []

        # Volumen anormal → amplifica señal
        if d["vol_ratio"] >= 2:
            score += 2
            descripcion.append(f"Volumen {d['vol_ratio']:.1f}x promedio")
        elif d["vol_ratio"] >= 1.5:
            score += 1
            descripcion.append(f"Volumen elevado {d['vol_ratio']:.1f}x promedio")

        # Presión compradora/vendedora
        if d["presion"] == "COMPRADORES":
            score += 1
            direccion = "ALZA"
            descripcion.append("Precio en zona alta del día")
        elif d["presion"] == "VENDEDORES":
            score += 1
            direccion = "BAJA"
            descripcion.append("Precio en zona baja del día")

        # VWAP → si precio > VWAP = alcista, precio < VWAP = bajista
        if d["vwap"] > 0 and d["precio"] > 0:
            if d["precio"] > d["vwap"] * 1.002:
                score += 1
                if direccion != "BAJA":
                    direccion = "ALZA"
                descripcion.append(f"Precio {d['precio']:.2f} sobre VWAP {d['vwap']:.2f}")
            elif d["precio"] < d["vwap"] * 0.998:
                score += 1
                if direccion != "ALZA":
                    direccion = "BAJA"
                descripcion.append(f"Precio {d['precio']:.2f} bajo VWAP {d['vwap']:.2f}")

        if score >= 2 and direccion != "NEUTRO":
            señales.append({
                "symbol":       symbol,
                "activo_motor": d["activo_motor"],
                "score":        score,
                "direccion":    direccion,
                "descripcion":  " | ".join(descripcion),
                "datos":        d,
            })

    return sorted(señales, key=lambda x: x["score"], reverse=True)

def get_resumen_ib():
    """Resumen para el dashboard"""
    if not es_horario_mercado():
        return {
            "disponible": False,
            "razon": "Mercado cerrado — datos solo disponibles en horario de trading",
            "datos": {},
        }

    datos = get_datos_mercado_ib()
    return {
        "disponible": len(datos) > 0,
        "razon": "Datos en tiempo real" if datos else "Sin datos disponibles",
        "datos": datos,
        "señales": get_señales_ib(),
        "timestamp": datetime.now().isoformat(),
    }

if __name__ == "__main__":
    print("=== DATOS DE MERCADO EN TIEMPO REAL ===\n")
    if not es_horario_mercado():
        print("Mercado cerrado — ejecutar en horario de trading (lunes-viernes 9:25-16:05 ET)")
        print("Módulo listo para el próximo horario de mercado")
    else:
        t0 = time.time()
        resumen = get_resumen_ib()
        if resumen["disponible"]:
            for symbol, d in resumen["datos"].items():
                print(f"{symbol}: ${d['precio']:.2f}  vol={d['vol_ratio']:.1f}x  presion={d['presion']}")
                if d["vwap"] > 0:
                    print(f"  VWAP={d['vwap']:.2f}")
            print(f"\nSeñales: {len(resumen['señales'])}")
            for s in resumen["señales"]:
                print(f"  [{s['direccion']}] {s['symbol']} score={s['score']} — {s['descripcion'][:70]}")
        else:
            print(f"Sin datos: {resumen['razon']}")
        print(f"\nTiempo: {time.time()-t0:.1f}s")
