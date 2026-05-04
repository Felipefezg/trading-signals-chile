"""
Módulo de cierre automático de posiciones.
Verifica precios actuales vs SL/TP y horizonte temporal.
Ejecuta órdenes de cierre en IB cuando se activan.

Lógica:
- Cada llamada verifica todas las posiciones abiertas
- Si precio toca SL → cierre inmediato con orden de mercado (proteger capital)
- Si precio toca TP → cierre con orden límite (capturar ganancia)
- Si días >= horizonte → cierre por tiempo (disciplina)
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta

import yfinance as yf

from engine.performance import registrar_trade_cerrado
from engine.trailing_stop import verificar_trailing_stops, actualizar_trail

POSICIONES_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "posiciones.json")
TRADES_FILE        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trades_cerrados.json")
LOG_FILE           = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cierre_log.json")

# IB disponible solo si está instalado
IB_DISPONIBLE = False
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IB_DISPONIBLE = True
except Exception:
    pass

IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 30  # Cliente distinto al executor y opciones

# Mapa de ticker IB → Yahoo Finance
TICKER_YF_MAP = {
    "BTC":    "BTC-USD",
    "SQM":    "SQM",
    "COPEC":  "COPEC.SN",
    "ECH":    "ECH",
    "SPY":    "SPY",
    "GLD":    "GLD",
    "LTM":    "LTM.SN",
    "BSAC":   "BSAC",
    "BCH":    "BCH",
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

# ── CLIENTE IB PARA CIERRE ────────────────────────────────────────────────────
if IB_DISPONIBLE:
    class CierreClient(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._next_order_id = None
            self._ready         = threading.Event()
            self.errores        = []
            self.ordenes_ok     = []

        def nextValidId(self, orderId):
            self._next_order_id = orderId
            self._ready.set()

        def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                        permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
            if status in ("Filled", "Submitted"):
                self.ordenes_ok.append({"orderId": orderId, "status": status, "avgFillPrice": avgFillPrice})

        def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
            if errorCode not in (2104, 2106, 2158, 2103, 2119):
                self.errores.append(f"[{errorCode}] {errorString}")

        def _get_next_id(self):
            oid = self._next_order_id
            self._next_order_id += 1
            return oid

        def conectar(self):
            self.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
            t = threading.Thread(target=self.run, daemon=True)
            t.start()
            return self._ready.wait(timeout=10)

else:
    class CierreClient:
        pass

# ── PRECIO ACTUAL ─────────────────────────────────────────────────────────────
def get_precio_actual(ticker_ib):
    """Obtiene precio actual de un ticker usando Yahoo Finance"""
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

# ── VERIFICAR CONDICIONES DE CIERRE ──────────────────────────────────────────
def verificar_condicion_cierre(ticker, posicion, precio_actual):
    """
    Verifica si una posición debe cerrarse.
    Retorna dict con razón de cierre o None si debe mantenerse.
    """
    accion         = posicion.get("accion", "COMPRAR")
    precio_entrada = posicion.get("precio_entrada", 0)
    sl             = posicion.get("sl")
    tp             = posicion.get("tp")
    horizonte_str  = posicion.get("horizonte", "1–7 días")
    fecha_entrada  = posicion.get("fecha_entrada", datetime.now().isoformat())

    if not precio_actual:
        return None

    # Calcular días abierta
    try:
        fecha = datetime.fromisoformat(fecha_entrada)
        dias  = (datetime.now() - fecha).days
    except:
        dias = 0

    # Horizonte máximo en días
    horizonte_max = 7  # default
    for key, val in HORIZONTE_DIAS.items():
        if key in horizonte_str:
            horizonte_max = val
            break

    # PnL actual
    if accion == "COMPRAR":
        pnl_pct = ((precio_actual - precio_entrada) / precio_entrada) * 100
    else:
        pnl_pct = ((precio_entrada - precio_actual) / precio_entrada) * 100

    # ── Verificar Stop Loss
    if sl:
        if accion == "COMPRAR" and precio_actual <= sl:
            return {
                "razon":      "STOP LOSS",
                "tipo":       "SL",
                "urgencia":   "ALTA",
                "precio":     precio_actual,
                "sl":         sl,
                "tp":         tp,
                "pnl_pct":   round(pnl_pct, 2),
                "dias":       dias,
                "mensaje":    f"Precio {precio_actual:,.2f} tocó SL {sl:,.2f} → pérdida {pnl_pct:+.2f}%",
            }
        elif accion == "VENDER" and precio_actual >= sl:
            return {
                "razon":      "STOP LOSS",
                "tipo":       "SL",
                "urgencia":   "ALTA",
                "precio":     precio_actual,
                "sl":         sl,
                "tp":         tp,
                "pnl_pct":   round(pnl_pct, 2),
                "dias":       dias,
                "mensaje":    f"Precio {precio_actual:,.2f} tocó SL {sl:,.2f} → pérdida {pnl_pct:+.2f}%",
            }

    # ── Verificar Take Profit
    if tp:
        if accion == "COMPRAR" and precio_actual >= tp:
            return {
                "razon":      "TAKE PROFIT",
                "tipo":       "TP",
                "urgencia":   "MEDIA",
                "precio":     precio_actual,
                "sl":         sl,
                "tp":         tp,
                "pnl_pct":   round(pnl_pct, 2),
                "dias":       dias,
                "mensaje":    f"Precio {precio_actual:,.2f} alcanzó TP {tp:,.2f} → ganancia {pnl_pct:+.2f}%",
            }
        elif accion == "VENDER" and precio_actual <= tp:
            return {
                "razon":      "TAKE PROFIT",
                "tipo":       "TP",
                "urgencia":   "MEDIA",
                "precio":     precio_actual,
                "sl":         sl,
                "tp":         tp,
                "pnl_pct":   round(pnl_pct, 2),
                "dias":       dias,
                "mensaje":    f"Precio {precio_actual:,.2f} alcanzó TP {tp:,.2f} → ganancia {pnl_pct:+.2f}%",
            }

    # ── Verificar horizonte temporal
    if dias >= horizonte_max:
        return {
            "razon":      "HORIZONTE CUMPLIDO",
            "tipo":       "TIME",
            "urgencia":   "BAJA",
            "precio":     precio_actual,
            "sl":         sl,
            "tp":         tp,
            "pnl_pct":   round(pnl_pct, 2),
            "dias":       dias,
            "mensaje":    f"Posición abierta {dias} días (máx {horizonte_max}) → cierre por tiempo | PnL {pnl_pct:+.2f}%",
        }

    return None

# ── EJECUTAR CIERRE EN IB ─────────────────────────────────────────────────────
def ejecutar_cierre_ib(ticker, posicion, condicion, modo_test=False):
    """
    Ejecuta la orden de cierre en IB.
    SL → orden de mercado (inmediata)
    TP → orden límite (al precio TP)
    TIME → orden de mercado
    """
    accion_cierre = "BUY" if posicion["accion"] == "VENDER" else "SELL"
    cantidad      = posicion.get("cantidad", 1)
    tipo_orden    = "MKT" if condicion["tipo"] in ("SL", "TIME") else "LMT"

    resultado = {
        "ticker":    ticker,
        "accion":    accion_cierre,
        "cantidad":  cantidad,
        "razon":     condicion["razon"],
        "precio":    condicion["precio"],
        "pnl_pct":  condicion["pnl_pct"],
        "timestamp": datetime.now().isoformat(),
        "ejecutado": False,
        "modo":      "TEST" if modo_test else "PAPER",
        "error":     None,
    }

    if modo_test:
        resultado["ejecutado"] = True
        resultado["nota"]      = f"Simulación: {accion_cierre} {cantidad} {ticker} ({tipo_orden})"
        return resultado

    if not IB_DISPONIBLE:
        resultado["error"] = "IB no disponible"
        return resultado

    ib = CierreClient()
    if not ib.conectar():
        resultado["error"] = "No se pudo conectar a IB TWS"
        return resultado

    try:
        time.sleep(1)

        # Construir contrato
        c = Contract()
        c.currency = "USD"

        if ticker == "BTC":
            c.symbol  = "BTC"
            c.secType = "CRYPTO"
            c.exchange = "PAXOS"
        elif ticker.endswith(".SN") or ticker in ("COPEC", "LTM", "SQM-B"):
            # Acciones chilenas — usar ADR si disponible o CFD
            c.symbol  = ticker.replace(".SN", "")
            c.secType = "STK"
            c.exchange = "SMART"
        else:
            c.symbol  = ticker
            c.secType = "STK"
            c.exchange = "SMART"

        # Construir orden
        o = Order()
        o.action        = accion_cierre
        o.orderType     = tipo_orden
        o.totalQuantity = cantidad
        o.transmit      = True
        o.eTradeOnly    = False
        o.firmQuoteOnly = False

        if tipo_orden == "LMT":
            o.lmtPrice = round(condicion["tp"], 2)

        oid = ib._get_next_id()
        ib.placeOrder(oid, c, o)
        time.sleep(3)

        resultado["ejecutado"] = True
        resultado["order_id"]  = oid
        resultado["tipo_orden"] = tipo_orden

    except Exception as e:
        resultado["error"] = str(e)
    finally:
        try:
            ib.disconnect()
        except:
            pass

    return resultado

# ── CIERRE DE POSICIÓN EN JSON ────────────────────────────────────────────────
def cerrar_posicion_local(ticker, posicion, condicion, resultado_ib):
    # Enviar alerta Telegram
    try:
        from engine.telegram_alertas import alerta_cierre_posicion
        precio_entrada = posicion.get("precio_entrada", 0)
        precio_salida  = condicion.get("precio", 0)
        pnl_pct        = condicion.get("pnl_pct", 0)
        cantidad       = posicion.get("cantidad", 1)
        pnl_usd        = (precio_salida - precio_entrada) * cantidad
        if posicion.get("accion") == "VENDER":
            pnl_usd = (precio_entrada - precio_salida) * cantidad
        alerta_cierre_posicion(ticker, condicion["razon"], pnl_pct, pnl_usd, precio_entrada, precio_salida)
    except:
        pass

    """
    Elimina la posición del JSON y registra el trade cerrado.
    """
    # Leer posiciones
    with open(POSICIONES_FILE) as f:
        posiciones = json.load(f)

    if ticker not in posiciones:
        return False

    # Registrar trade cerrado
    precio_salida = condicion["precio"]
    registrar_trade_cerrado(
        ticker         = ticker,
        accion         = posicion["accion"],
        cantidad       = posicion.get("cantidad", 1),
        precio_entrada = posicion.get("precio_entrada", 0),
        precio_salida  = precio_salida,
        fecha_entrada  = posicion.get("fecha_entrada", datetime.now().isoformat()),
        fecha_salida   = datetime.now().isoformat(),
    )

    # Eliminar de posiciones abiertas
    del posiciones[ticker]
    with open(POSICIONES_FILE, "w") as f:
        json.dump(posiciones, f, indent=2)

    # Guardar en log de cierres
    log = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                log = json.load(f)
        except:
            pass

    log.append({
        "timestamp":   datetime.now().isoformat(),
        "ticker":      ticker,
        "razon":       condicion["razon"],
        "pnl_pct":    condicion["pnl_pct"],
        "precio":      condicion["precio"],
        "orden_ib":    resultado_ib,
    })

    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2, default=str)

    return True

# ── VERIFICACIÓN COMPLETA ─────────────────────────────────────────────────────
def calcular_tp_parcial(precio_entrada, tp_original, accion, atr=None):
    """
    Calcula TP1 (50% cierre) y TP2 (dejar correr resto).
    TP1 = 60% del camino hacia TP original
    TP2 = TP original extendido 50%
    """
    distancia = abs(tp_original - precio_entrada)
    if accion == "COMPRAR":
        tp1 = round(precio_entrada + distancia * 0.6, 4)
        tp2 = round(precio_entrada + distancia * 1.5, 4)
    else:
        tp1 = round(precio_entrada - distancia * 0.6, 4)
        tp2 = round(precio_entrada - distancia * 1.5, 4)
    return tp1, tp2

def verificar_posiciones(modo_test=False, auto_cerrar=True):
    """
    Verifica todas las posiciones abiertas y ejecuta cierres si corresponde.

    Args:
        modo_test: Si True, no envía órdenes reales a IB
        auto_cerrar: Si True, cierra automáticamente. Si False, solo reporta.

    Returns:
        dict con resumen de la verificación
    """
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

    # Verificar trailing stops primero
    try:
        resumen_trail = verificar_trailing_stops()
        for cierre_trail in resumen_trail.get("cierres", []):
            ticker_t = cierre_trail["ticker"]
            if ticker_t in posiciones:
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
                resultado_ib = ejecutar_cierre_ib(ticker_t, posicion_t, condicion_trail, modo_test)
                cerrar_posicion_local(ticker_t, posicion_t, condicion_trail, resultado_ib)
                resumen["cierres"].append({
                    "ticker":    ticker_t,
                    "razon":     "TRAILING STOP",
                    "pnl_pct":  cierre_trail["pnl_pct"],
                    "ejecutado": resultado_ib.get("ejecutado", False),
                    "error":     resultado_ib.get("error"),
                })
    except Exception as e:
        print(f"Error trailing stops: {e}")

    for ticker, posicion in list(posiciones.items()):
        precio_actual = get_precio_actual(ticker)

        if not precio_actual:
            resumen["sin_datos"].append(ticker)
            continue

        condicion = verificar_condicion_cierre(ticker, posicion, precio_actual)

        if condicion:
            print(f"\n⚠️  CIERRE DETECTADO: {ticker}")
            print(f"   {condicion['mensaje']}")

            if auto_cerrar:
                resultado_ib = ejecutar_cierre_ib(ticker, posicion, condicion, modo_test)
                cerrar_posicion_local(ticker, posicion, condicion, resultado_ib)
                resumen["cierres"].append({
                    "ticker":    ticker,
                    "razon":     condicion["razon"],
                    "pnl_pct":  condicion["pnl_pct"],
                    "ejecutado": resultado_ib.get("ejecutado", False),
                    "error":     resultado_ib.get("error"),
                })
                print(f"   {'✅ Cerrado' if resultado_ib.get('ejecutado') else '❌ Error: '+str(resultado_ib.get('error'))}")
            else:
                resumen["cierres"].append({
                    "ticker":  ticker,
                    "razon":   condicion["razon"],
                    "pnl_pct": condicion["pnl_pct"],
                    "mensaje": condicion["mensaje"],
                })
        else:
            # Calcular PnL actual para reporte
            precio_entrada = posicion.get("precio_entrada", 0)
            accion         = posicion.get("accion", "COMPRAR")
            if accion == "COMPRAR":
                pnl = ((precio_actual - precio_entrada) / precio_entrada) * 100
            else:
                pnl = ((precio_entrada - precio_actual) / precio_entrada) * 100

            try:
                dias = (datetime.now() - datetime.fromisoformat(posicion["fecha_entrada"])).days
            except:
                dias = 0

            resumen["ok"].append({
                "ticker":  ticker,
                "precio":  precio_actual,
                "pnl_pct": round(pnl, 2),
                "dias":    dias,
            })

    return resumen

def get_log_cierres(limit=20):
    """Retorna historial de cierres automáticos"""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE) as f:
            log = json.load(f)
        return list(reversed(log))[:limit]
    except:
        return []

if __name__ == "__main__":
    print("=== VERIFICACIÓN DE POSICIONES ===\n")
    resumen = verificar_posiciones(modo_test=True, auto_cerrar=False)

    print(f"Posiciones activas: {resumen['posiciones']}")
    print(f"Sin datos de precio: {resumen['sin_datos']}")

    if resumen["cierres"]:
        print(f"\n⚠️  CIERRES NECESARIOS ({len(resumen['cierres'])}):")
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
            print(f"  {icon} {p['ticker']}: precio {p['precio']:,.2f} | PnL {p['pnl_pct']:+.2f}% | {p['dias']} días")
