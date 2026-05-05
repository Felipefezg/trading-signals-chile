"""
Módulo de cierre automático de posiciones.
Verifica precios actuales vs SL/TP y horizonte temporal.
Ejecuta órdenes de cierre en IB cuando se activan.

DISEÑO (IB como única fuente de verdad):
- verificar_posiciones() sincroniza con IB PRIMERO antes de leer posiciones locales.
- Los cierres reales delegan a ib_executor.cerrar_posicion_ib() — evita conflictos de clientId.
- Solo se elimina la posición local DESPUÉS de confirmación IB.
"""

import json
import os
from datetime import datetime

import yfinance as yf

from engine.performance import registrar_trade_cerrado
from engine.trailing_stop import verificar_trailing_stops

POSICIONES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "posiciones.json")
TRADES_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trades_cerrados.json")
LOG_FILE        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cierre_log.json")

# Mapa ticker IB → Yahoo Finance — universo completo
TICKER_YF_MAP = {
    # Crypto
    "BTC":        "BTC-USD",
    "ETH":        "ETH-USD",
    # Futuros
    "GC":         "GC=F",
    "CL":         "CL=F",
    "HG":         "HG=F",
    # ADRs NYSE
    "SQM":        "SQM",
    "BSAC":       "BSAC",
    "BCH":        "BCH",
    "LTM":        "LTM",
    # ETFs
    "ECH":        "ECH",
    "SPY":        "SPY",
    "GLD":        "GLD",
    "TLT":        "TLT",
    # Acciones Chile (Bolsa Santiago — sufijo .SN)
    "COPEC":      "COPEC.SN",
    "FALABELLA":  "FALABELLA.SN",
    "CMPC":       "CMPC.SN",
    "BCI":        "BCI.SN",
    "COLBUN":     "COLBUN.SN",
    "ENELCHILE":  "ENELCHILE.SN",
    "ENELAM":     "ENELAM.SN",
    "ENTEL":      "ENTEL.SN",
    "CAP":        "CAP.SN",
    "CCU":        "CCU.SN",
    "CENCOSUD":   "CENCOSUD.SN",
    "ITAUCL":     "ITAUCL.SN",
    "PARAUCO":    "PARAUCO.SN",
    "MALLPLAZA":  "MALLPLAZA.SN",
    "RIPLEY":     "RIPLEY.SN",
    "AGUAS-A":    "AGUAS-A.SN",
    "VAPORES":    "VAPORES.SN",
    "ANDINA-B":   "ANDINA-B.SN",
    "ILC":        "ILC.SN",
    "CONCHATORO": "CONCHATORO.SN",
    "FORUS":      "FORUS.SN",
    "SMU":        "SMU.SN",
    "ECL":        "ECL.SN",
    "SONDA":      "SONDA.SN",
    "BESALCO":    "BESALCO.SN",
    "SALFACORP":  "SALFACORP.SN",
    "SOCOVESA":   "SOCOVESA.SN",
    "MOLYMET":    "MOLYMET.SN",
    "QUINENCO":   "QUINENCO.SN",
    "MASISA":     "MASISA.SN",
    "HABITAT":    "HABITAT.SN",
    "PROVIDA":    "PROVIDA.SN",
    "MARINSA":    "MARINSA.SN",
}

# Horizonte máximo en días por tipo
HORIZONTE_DIAS = {
    "1–7 días":     7,
    "1-7 días":     7,
    "1–4 semanas":  28,
    "1-4 semanas":  28,
    "1–3 meses":    90,
    "1-3 meses":    90,
    "corto":        7,
    "medio":        30,
    "largo":        90,
}


# ── PRECIO ACTUAL ─────────────────────────────────────────────────────────────
def get_precio_actual(ticker_ib):
    """Obtiene precio actual via Yahoo Finance."""
    yf_ticker = TICKER_YF_MAP.get(ticker_ib, ticker_ib)
    try:
        h = yf.Ticker(yf_ticker).history(period="1d", interval="1m")
        if not h.empty:
            return float(h["Close"].iloc[-1])
        h = yf.Ticker(yf_ticker).history(period="2d")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception as e:
        print(f"Error precio {ticker_ib}: {e}")
    return None


# ── VERIFICAR CONDICIÓN DE CIERRE ─────────────────────────────────────────────
def verificar_condicion_cierre(ticker, posicion, precio_actual):
    """
    Verifica si la posición debe cerrarse por SL/TP/horizonte.
    Retorna dict con razón o None si debe mantenerse.
    """
    accion         = posicion.get("accion", "COMPRAR")
    precio_entrada = posicion.get("precio_entrada", 0)
    sl             = posicion.get("sl")
    tp             = posicion.get("tp")
    horizonte_str  = posicion.get("horizonte", "1-7 días")
    fecha_entrada  = posicion.get("fecha_entrada", datetime.now().isoformat())

    if not precio_actual or not precio_entrada:
        return None

    try:
        fecha = datetime.fromisoformat(fecha_entrada)
        dias  = (datetime.now() - fecha).days
    except Exception:
        dias = 0

    horizonte_max = 7
    for key, val in HORIZONTE_DIAS.items():
        if key in horizonte_str:
            horizonte_max = val
            break

    if accion == "COMPRAR":
        pnl_pct = ((precio_actual - precio_entrada) / precio_entrada) * 100
    else:
        pnl_pct = ((precio_entrada - precio_actual) / precio_entrada) * 100

    # Stop Loss
    if sl:
        if (accion == "COMPRAR" and precio_actual <= sl) or \
           (accion == "VENDER"  and precio_actual >= sl):
            return {
                "razon":    "STOP LOSS",
                "tipo":     "SL",
                "urgencia": "ALTA",
                "precio":   precio_actual,
                "sl":       sl,
                "tp":       tp,
                "pnl_pct":  round(pnl_pct, 2),
                "dias":     dias,
                "mensaje":  f"Precio {precio_actual:,.4f} tocó SL {sl:,.4f} → pérdida {pnl_pct:+.2f}%",
            }

    # Take Profit
    if tp:
        if (accion == "COMPRAR" and precio_actual >= tp) or \
           (accion == "VENDER"  and precio_actual <= tp):
            return {
                "razon":    "TAKE PROFIT",
                "tipo":     "TP",
                "urgencia": "MEDIA",
                "precio":   precio_actual,
                "sl":       sl,
                "tp":       tp,
                "pnl_pct":  round(pnl_pct, 2),
                "dias":     dias,
                "mensaje":  f"Precio {precio_actual:,.4f} alcanzó TP {tp:,.4f} → ganancia {pnl_pct:+.2f}%",
            }

    # Horizonte temporal
    if dias >= horizonte_max:
        return {
            "razon":    "HORIZONTE CUMPLIDO",
            "tipo":     "TIME",
            "urgencia": "BAJA",
            "precio":   precio_actual,
            "sl":       sl,
            "tp":       tp,
            "pnl_pct":  round(pnl_pct, 2),
            "dias":     dias,
            "mensaje":  f"Posición abierta {dias} días (máx {horizonte_max}) | PnL {pnl_pct:+.2f}%",
        }

    return None


# ── EJECUTAR CIERRE EN IB ─────────────────────────────────────────────────────
def ejecutar_cierre_ib(ticker, posicion, condicion, modo_test=False):
    """
    Cierra posición en IB delegando a ib_executor.cerrar_posicion_ib().
    Evita conflictos de clientId — ib_executor usa clientId=10 de forma controlada.
    """
    accion_original = posicion.get("accion", "COMPRAR")
    cantidad        = posicion.get("cantidad", 1)
    tipo            = posicion.get("tipo", "ETF")

    resultado = {
        "ticker":    ticker,
        "accion":    "BUY" if accion_original == "VENDER" else "SELL",
        "cantidad":  cantidad,
        "razon":     condicion["razon"],
        "precio":    condicion["precio"],
        "pnl_pct":   condicion["pnl_pct"],
        "timestamp": datetime.now().isoformat(),
        "ejecutado": False,
        "modo":      "TEST" if modo_test else "PAPER",
        "error":     None,
        "confirmado_ib": False,
    }

    if modo_test:
        resultado["ejecutado"]    = True
        resultado["confirmado_ib"] = False   # test no confirma IB real
        resultado["nota"]         = f"Simulación: cierre {ticker} @ {condicion['precio']:,.4f}"
        return resultado

    try:
        from engine.ib_executor import cerrar_posicion_ib
        res_ib = cerrar_posicion_ib(ticker, tipo, cantidad, accion_original)

        resultado["ejecutado"]    = res_ib.get("exito", False)
        resultado["confirmado_ib"] = res_ib.get("exito", False)
        resultado["orden_id"]     = res_ib.get("orden_id")
        resultado["precio_fill"]  = res_ib.get("precio_fill", condicion["precio"])
        if not res_ib.get("exito"):
            resultado["error"] = res_ib.get("error", "Error IB desconocido")

    except Exception as e:
        resultado["error"] = str(e)

    return resultado


# ── ELIMINAR POSICIÓN LOCAL (solo tras confirmación IB) ───────────────────────
def cerrar_posicion_local(ticker, posicion, condicion, resultado_ib):
    """
    Elimina la posición del JSON y registra el trade cerrado.
    SOLO se ejecuta si resultado_ib["confirmado_ib"] es True
    (o si es modo test).
    """
    # Alerta Telegram
    try:
        from engine.telegram_alertas import alerta_cierre_posicion
        precio_entrada = posicion.get("precio_entrada", 0)
        precio_salida  = resultado_ib.get("precio_fill", condicion.get("precio", 0))
        pnl_pct        = condicion.get("pnl_pct", 0)
        cantidad       = posicion.get("cantidad", 1)
        tipo_pos       = posicion.get("tipo", "ETF")
        if posicion.get("accion") == "VENDER":
            pnl_raw = (precio_entrada - precio_salida) * cantidad
        else:
            pnl_raw = (precio_salida - precio_entrada) * cantidad
        # Normalizar CLP → USD para acciones Chile
        if tipo_pos == "Acción Chile":
            try:
                from engine.ib_executor import _get_usd_clp
                tasa = _get_usd_clp()
                pnl_usd = pnl_raw / tasa if tasa else pnl_raw
            except Exception:
                pnl_usd = pnl_raw
        else:
            pnl_usd = pnl_raw
        alerta_cierre_posicion(ticker, condicion["razon"], pnl_pct, pnl_usd,
                               precio_entrada, precio_salida)
    except Exception:
        pass

    with open(POSICIONES_FILE) as f:
        posiciones = json.load(f)

    if ticker not in posiciones:
        return False

    precio_salida = resultado_ib.get("precio_fill", condicion["precio"])

    registrar_trade_cerrado(
        ticker         = ticker,
        accion         = posicion["accion"],
        cantidad       = posicion.get("cantidad", 1),
        precio_entrada = posicion.get("precio_entrada", 0),
        precio_salida  = precio_salida,
        fecha_entrada  = posicion.get("fecha_entrada", datetime.now().isoformat()),
        fecha_salida   = datetime.now().isoformat(),
        confirmado_ib  = resultado_ib.get("confirmado_ib", False),
        tipo           = posicion.get("tipo"),  # necesario para normalización CLP→USD
    )

    del posiciones[ticker]
    with open(POSICIONES_FILE, "w") as f:
        json.dump(posiciones, f, indent=2)

    # Log de cierres
    log = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                log = json.load(f)
        except Exception:
            pass

    log.append({
        "timestamp":   datetime.now().isoformat(),
        "ticker":      ticker,
        "razon":       condicion["razon"],
        "pnl_pct":     condicion["pnl_pct"],
        "precio":      precio_salida,
        "confirmado_ib": resultado_ib.get("confirmado_ib", False),
        "orden_ib":    resultado_ib,
    })

    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2, default=str)

    return True


# ── VERIFICACIÓN COMPLETA ─────────────────────────────────────────────────────
def verificar_posiciones(modo_test=False, auto_cerrar=True):
    """
    Ciclo completo de verificación:
    1. Sincroniza posiciones con IB (IB manda).
    2. Verifica trailing stops.
    3. Verifica SL/TP/horizonte para cada posición.
    4. Ejecuta cierres en IB y luego elimina localmente.

    Args:
        modo_test:  Si True, no envía órdenes reales a IB.
        auto_cerrar: Si True, cierra automáticamente.

    Returns:
        dict con resumen (cierres, ok, sin_datos).
    """
    # ── 1. SINCRONIZAR CON IB PRIMERO ─────────────────────────────────────────
    if not modo_test:
        try:
            from engine.ib_executor import sincronizar_desde_ib
            sincronizar_desde_ib()
        except Exception as e:
            print(f"  Advertencia: no se pudo sincronizar con IB: {e}")

    # ── 2. LEER POSICIONES (ya sincronizadas) ──────────────────────────────────
    if not os.path.exists(POSICIONES_FILE):
        return {"posiciones": 0, "cierres": [], "sin_datos": []}

    with open(POSICIONES_FILE) as f:
        posiciones = json.load(f)

    if not posiciones:
        return {"posiciones": 0, "cierres": [], "sin_datos": []}

    resumen = {
        "timestamp":  datetime.now().isoformat(),
        "posiciones": len(posiciones),
        "cierres":    [],
        "sin_datos":  [],
        "ok":         [],
    }

    # ── 3. TRAILING STOPS ─────────────────────────────────────────────────────
    try:
        resumen_trail = verificar_trailing_stops()
        for cierre_trail in resumen_trail.get("cierres", []):
            ticker_t   = cierre_trail["ticker"]
            if ticker_t not in posiciones:
                continue
            posicion_t = posiciones[ticker_t]
            condicion_trail = {
                "razon":    "TRAILING STOP",
                "tipo":     "TRAIL",
                "urgencia": "MEDIA",
                "precio":   cierre_trail["precio_actual"],
                "sl":       posicion_t.get("sl"),
                "tp":       posicion_t.get("tp"),
                "pnl_pct":  cierre_trail["pnl_pct"],
                "dias":     0,
                "mensaje":  cierre_trail["razon_cierre"],
            }
            if auto_cerrar:
                resultado_ib = ejecutar_cierre_ib(ticker_t, posicion_t, condicion_trail, modo_test)
                # Solo eliminar localmente si IB confirmó
                if resultado_ib.get("confirmado_ib") or modo_test:
                    cerrar_posicion_local(ticker_t, posicion_t, condicion_trail, resultado_ib)
            resumen["cierres"].append({
                "ticker":        ticker_t,
                "razon":         "TRAILING STOP",
                "pnl_pct":       cierre_trail["pnl_pct"],
                "ejecutado":     resultado_ib.get("ejecutado", False) if auto_cerrar else False,
                "confirmado_ib": resultado_ib.get("confirmado_ib", False) if auto_cerrar else False,
                "error":         resultado_ib.get("error") if auto_cerrar else None,
            })
    except Exception as e:
        print(f"Error trailing stops: {e}")

    # ── 4. SL / TP / HORIZONTE ────────────────────────────────────────────────
    for ticker, posicion in list(posiciones.items()):
        precio_actual = get_precio_actual(ticker)

        if not precio_actual:
            resumen["sin_datos"].append(ticker)
            continue

        condicion = verificar_condicion_cierre(ticker, posicion, precio_actual)

        if condicion:
            print(f"\n⚠️  CIERRE DETECTADO: {ticker} — {condicion['mensaje']}")

            if auto_cerrar:
                resultado_ib = ejecutar_cierre_ib(ticker, posicion, condicion, modo_test)
                # Solo eliminar localmente si IB confirmó (o modo test)
                if resultado_ib.get("confirmado_ib") or modo_test:
                    cerrar_posicion_local(ticker, posicion, condicion, resultado_ib)
                    print(f"   ✅ Cerrado en IB y eliminado localmente")
                else:
                    print(f"   ⚠️  IB no confirmó cierre — posición local mantenida: {resultado_ib.get('error')}")
                resumen["cierres"].append({
                    "ticker":        ticker,
                    "razon":         condicion["razon"],
                    "pnl_pct":       condicion["pnl_pct"],
                    "ejecutado":     resultado_ib.get("ejecutado", False),
                    "confirmado_ib": resultado_ib.get("confirmado_ib", False),
                    "error":         resultado_ib.get("error"),
                })
            else:
                resumen["cierres"].append({
                    "ticker":   ticker,
                    "razon":    condicion["razon"],
                    "pnl_pct":  condicion["pnl_pct"],
                    "mensaje":  condicion["mensaje"],
                })
        else:
            # PnL actual para reporte
            precio_entrada = posicion.get("precio_entrada", 0)
            accion         = posicion.get("accion", "COMPRAR")
            if precio_entrada:
                if accion == "COMPRAR":
                    pnl = ((precio_actual - precio_entrada) / precio_entrada) * 100
                else:
                    pnl = ((precio_entrada - precio_actual) / precio_entrada) * 100
            else:
                pnl = 0.0

            try:
                dias = (datetime.now() - datetime.fromisoformat(
                    posicion["fecha_entrada"])).days
            except Exception:
                dias = 0

            # Actualizar trailing
            try:
                from engine.trailing_stop import actualizar_trail
                actualizar_trail(ticker, posicion, precio_actual)
            except Exception:
                pass

            resumen["ok"].append({
                "ticker":  ticker,
                "precio":  precio_actual,
                "pnl_pct": round(pnl, 2),
                "dias":    dias,
            })

    return resumen


def get_log_cierres(limit=20):
    """Retorna historial de cierres automáticos."""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE) as f:
            log = json.load(f)
        return list(reversed(log))[:limit]
    except Exception:
        return []


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== VERIFICACIÓN DE POSICIONES ===\n")
    resumen = verificar_posiciones(modo_test=True, auto_cerrar=False)

    print(f"Posiciones activas: {resumen['posiciones']}")
    print(f"Sin datos de precio: {resumen['sin_datos']}")

    if resumen["cierres"]:
        print(f"\n⚠️  CIERRES DETECTADOS ({len(resumen['cierres'])}):")
        for c in resumen["cierres"]:
            print(f"  {c['ticker']}: {c['razon']} | PnL {c['pnl_pct']:+.2f}%")
            if c.get("mensaje"):
                print(f"    → {c['mensaje']}")
    else:
        print("\n✅ Sin cierres necesarios")

    if resumen["ok"]:
        print(f"\n📊 Posiciones activas:")
        for p in resumen["ok"]:
            icon = "🟢" if p["pnl_pct"] >= 0 else "🔴"
            print(f"  {icon} {p['ticker']}: {p['precio']:,.4f} | PnL {p['pnl_pct']:+.2f}% | {p['dias']} días")
