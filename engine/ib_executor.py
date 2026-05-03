"""
Módulo de ejecución automática de órdenes en Interactive Brokers.
Opera en Paper Trading (puerto 7497) con política de inversión definida.

POLÍTICA:
- Capital: USD 100.000 asignado
- Máximo por operación: USD 10.000 (10%)
- Horizonte máximo: 3 días
- Convicción mínima: 75%
- Riesgo máximo: 6/10
- Máximo posiciones simultáneas: 5
- Cierre forzado: día 3
"""

import threading
import time
import json
import os
from datetime import datetime, timedelta
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
IB_HOST       = "127.0.0.1"
IB_PORT       = 7497  # Paper Trading
IB_CLIENT_ID  = 10

CAPITAL_TOTAL      = 100_000
MAX_POR_OPERACION  = 10_000
MAX_POSICIONES     = 5
MAX_CRYPTO_USD     = 15_000
MAX_FUTUROS_USD    = 10_000
HORIZONTE_MAX_DIAS = 3
MIN_CONVICCION     = 75
MAX_RIESGO         = 6

POSICIONES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "posiciones.json")

# ── CONTRATOS ─────────────────────────────────────────────────────────────────
def _crear_contrato(ib_ticker, tipo):
    c = Contract()
    if tipo in ("ETF", "Acción USA/Chile"):
        c.symbol   = ib_ticker
        c.secType  = "STK"
        c.exchange = "SMART"
        c.currency = "USD"
    elif tipo == "Acción Chile":
        c.symbol   = ib_ticker
        c.secType  = "STK"
        c.exchange = "SN"
        c.currency = "CLP"
    elif tipo == "Crypto":
        c.symbol   = "BTC"
        c.secType  = "CRYPTO"
        c.exchange = "PAXOS"
        c.currency = "USD"
    elif tipo == "Futuro":
        c.symbol   = ib_ticker
        c.secType  = "FUT"
        c.exchange = "SMART"
        c.currency = "USD"
        hoy = datetime.now()
        if hoy.day < 15:
            c.lastTradeDateOrContractMonth = hoy.strftime("%Y%m")
        else:
            siguiente = hoy.replace(day=1) + timedelta(days=32)
            c.lastTradeDateOrContractMonth = siguiente.strftime("%Y%m")
    elif tipo == "Forex":
        c.symbol   = "USD"
        c.secType  = "CASH"
        c.exchange = "IDEALPRO"
        c.currency = "CLP"
    return c

def _crear_orden(accion, cantidad, sl=None, tp=None):
    """Crea orden LMT con bracket SL+TP si están disponibles"""
    accion_ib = "BUY" if accion == "COMPRAR" else "SELL"
    accion_cierre = "SELL" if accion == "COMPRAR" else "BUY"

    def _base_order(action, qty, transmit):
        o = Order()
        o.action        = action
        o.totalQuantity = qty
        o.eTradeOnly    = False
        o.firmQuoteOnly = False
        o.transmit      = transmit
        return o

    if sl and tp:
        entrada = _base_order(accion_ib, cantidad, False)
        entrada.orderType = "MKT"

        orden_sl = _base_order(accion_cierre, cantidad, False)
        orden_sl.orderType = "STP"
        orden_sl.auxPrice  = round(sl, 2)

        orden_tp = _base_order(accion_cierre, cantidad, True)
        orden_tp.orderType = "LMT"
        orden_tp.lmtPrice  = round(tp, 2)

        return [entrada, orden_sl, orden_tp]
    else:
        entrada = _base_order(accion_ib, cantidad, True)
        entrada.orderType = "MKT"
        return [entrada]

# ── POSICIONES ────────────────────────────────────────────────────────────────
def _cargar_posiciones():
    try:
        if os.path.exists(POSICIONES_FILE):
            with open(POSICIONES_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def _guardar_posiciones(posiciones):
    with open(POSICIONES_FILE, "w") as f:
        json.dump(posiciones, f, indent=2, default=str)

def _posiciones_expiradas(posiciones):
    expiradas = []
    ahora = datetime.now()
    for ticker, pos in posiciones.items():
        try:
            fecha = datetime.fromisoformat(pos["fecha_entrada"])
            if (ahora - fecha).days >= HORIZONTE_MAX_DIAS:
                expiradas.append(ticker)
        except:
            pass
    return expiradas

def _calcular_cantidad(precio_actual, tipo, conviccion=75, stop_loss=None, take_profit=None):
    """
    Calcula cantidad usando Kelly Criterion.
    Invierte más cuando la convicción es alta y el R/R es favorable.
    """
    if not precio_actual or precio_actual <= 0:
        return 0
    try:
        from engine.kelly import calcular_kelly
        sizing = calcular_kelly(
            conviccion_pct=conviccion,
            precio_entrada=precio_actual,
            stop_loss=stop_loss,
            take_profit=take_profit,
            tipo_activo=tipo,
        )
        monto_usd = sizing["monto_usd"]
    except Exception:
        # Fallback al método original si Kelly falla
        monto_usd = MAX_POR_OPERACION
        if tipo == "Crypto":
            monto_usd = min(MAX_POR_OPERACION, MAX_CRYPTO_USD)
        elif tipo == "Futuro":
            monto_usd = min(MAX_POR_OPERACION, MAX_FUTUROS_USD)

    return max(1, int(monto_usd / precio_actual))

# ── CLIENTE IB ────────────────────────────────────────────────────────────────
class IBExecutor(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self._next_order_id = None
        self._cuenta_info   = {}
        self._ready         = threading.Event()
        self._precios       = {}
        self._precio_events = {}
        self.errores        = []
        self.order_status   = {}

    def nextValidId(self, orderId):
        self._next_order_id = orderId
        self._ready.set()

    def accountSummary(self, reqId, account, tag, value, currency):
        try:
            self._cuenta_info[tag] = float(value)
        except:
            pass

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType in (1, 2, 4) and price > 0:
            self._precios[reqId] = price
            if reqId in self._precio_events:
                self._precio_events[reqId].set()

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        self.order_status[orderId] = {
            "status": status, "filled": filled,
            "avgPrice": avgFillPrice
        }

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode not in (2104, 2106, 2158, 2119, 2100):
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

    def get_precio_actual(self, contrato, timeout=5):
        req_id = self._get_next_id()
        evento = threading.Event()
        self._precio_events[req_id] = evento
        self.reqMktData(req_id, contrato, "", True, False, [])
        evento.wait(timeout=timeout)
        return self._precios.get(req_id)

    def enviar_bracket(self, contrato, ordenes):
        ids = []
        parent_id = None
        for i, orden in enumerate(ordenes):
            oid = self._get_next_id()
            if i == 0:
                parent_id = oid
            elif parent_id:
                orden.parentId = parent_id
            self.placeOrder(oid, contrato, orden)
            ids.append(oid)
            time.sleep(0.2)
        return ids

    def cerrar_posicion(self, contrato, cantidad, accion_original):
        accion_cierre = "SELL" if accion_original == "COMPRAR" else "BUY"
        o = Order()
        o.action        = accion_cierre
        o.orderType     = "MKT"
        o.totalQuantity = cantidad
        o.transmit      = True
        o.eTradeOnly    = False
        o.firmQuoteOnly = False
        oid = self._get_next_id()
        self.placeOrder(oid, contrato, o)
        return oid

# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────────────────────────
def ejecutar_señales(recomendaciones, modo_test=False):
    posiciones = _cargar_posiciones()
    resumen = {
        "timestamp":          datetime.now().isoformat(),
        "ordenes_enviadas":   [],
        "ordenes_rechazadas": [],
        "posiciones_cerradas":[],
        "errores":            [],
        "modo":               "TEST" if modo_test else "PAPER",
    }

    señales_validas = [
        r for r in recomendaciones
        if r["conviccion"] >= MIN_CONVICCION
        and r["riesgo"] <= MAX_RIESGO
        and r["n_fuentes"] >= 2
    ]

    if not señales_validas:
        resumen["errores"].append("Sin señales que cumplan política")
        return resumen

    slots = MAX_POSICIONES - len(posiciones)

    if modo_test:
        for r in señales_validas[:slots]:
            ticker = r["ib_ticker"]
            if ticker in posiciones:
                resumen["ordenes_rechazadas"].append({"ticker": ticker, "razon": "Posición ya abierta"})
                continue
            precio = r.get("precio_actual", 100)
            cantidad = _calcular_cantidad(precio, r["tipo"], r.get("conviccion",75), r.get("stop_loss"), r.get("take_profit"))
            resumen["ordenes_enviadas"].append({
                "ticker":     ticker,
                "accion":     r["accion"],
                "cantidad":   cantidad,
                "precio_est": precio,
                "monto_usd":  round(cantidad * (precio or 0), 2),
                "sl":         r.get("stop_loss"),
                "tp":         r.get("take_profit"),
                "horizonte":  r.get("horizonte", {}).get("dias"),
                "conviccion": r["conviccion"],
                "riesgo":     r["riesgo"],
            })
        return resumen

    # Modo real
    ib = IBExecutor()
    if not ib.conectar():
        resumen["errores"].append("No se pudo conectar a IB. ¿Está TWS corriendo en puerto 7497?")
        return resumen

    time.sleep(1)

    try:
        # Cerrar posiciones expiradas
        for ticker in _posiciones_expiradas(posiciones):
            pos = posiciones[ticker]
            try:
                contrato = _crear_contrato(ticker, pos["tipo"])
                oid = ib.cerrar_posicion(contrato, pos["cantidad"], pos["accion"])
                resumen["posiciones_cerradas"].append({"ticker": ticker, "razon": "Vencido", "order_id": oid})
                del posiciones[ticker]
                slots += 1
            except Exception as e:
                resumen["errores"].append(f"Error cerrando {ticker}: {e}")

        # Abrir nuevas posiciones
        for r in señales_validas[:slots]:
            ticker = r["ib_ticker"]
            tipo   = r["tipo"]

            if ticker in posiciones:
                resumen["ordenes_rechazadas"].append({"ticker": ticker, "razon": "Posición ya abierta"})
                continue

            try:
                contrato = _crear_contrato(ticker, tipo)
                precio   = r.get("precio_actual") or ib.get_precio_actual(contrato)

                if not precio:
                    resumen["ordenes_rechazadas"].append({"ticker": ticker, "razon": "Sin precio"})
                    continue

                cantidad = _calcular_cantidad(precio, tipo, r.get("conviccion",75), r.get("stop_loss"), r.get("take_profit"))
                if cantidad == 0:
                    resumen["ordenes_rechazadas"].append({"ticker": ticker, "razon": "Cantidad=0"})
                    continue

                ordenes = _crear_orden(r["accion"], cantidad, r.get("stop_loss"), r.get("take_profit"))
                ids     = ib.enviar_bracket(contrato, ordenes)

                posiciones[ticker] = {
                    "accion":         r["accion"],
                    "cantidad":       cantidad,
                    "precio_entrada": precio,
                    "sl":             r.get("stop_loss"),
                    "tp":             r.get("take_profit"),
                    "tipo":           tipo,
                    "fecha_entrada":  datetime.now().isoformat(),
                    "horizonte":      r.get("horizonte", {}).get("dias"),
                    "conviccion":     r["conviccion"],
                    "order_ids":      ids,
                }

                resumen["ordenes_enviadas"].append({
                    "ticker":    ticker,
                    "accion":    r["accion"],
                    "cantidad":  cantidad,
                    "precio":    precio,
                    "monto_usd": round(cantidad * precio, 2),
                    "sl":        r.get("stop_loss"),
                    "tp":        r.get("take_profit"),
                    "order_ids": ids,
                })
                time.sleep(0.5)

            except Exception as e:
                resumen["errores"].append(f"Error en {ticker}: {str(e)}")

    finally:
        _guardar_posiciones(posiciones)
        time.sleep(1)
        ib.disconnect()

    resumen["posiciones_abiertas_total"] = len(posiciones)
    return resumen

def get_posiciones_abiertas():
    return _cargar_posiciones()

def get_resumen_cuenta():
    try:
        ib = IBExecutor()
        if not ib.conectar():
            return {}
        ib.reqAccountSummary(1, "All", "NetLiquidation,TotalCashValue,BuyingPower,UnrealizedPnL")
        time.sleep(3)
        ib.disconnect()
        return ib._cuenta_info
    except:
        return {}

if __name__ == "__main__":
    print("=== TEST CONEXIÓN IB ===")
    cuenta = get_resumen_cuenta()
    for k, v in cuenta.items():
        print(f"  {k}: USD {v:,.2f}")
    print("\n=== POSICIONES ABIERTAS ===")
    pos = get_posiciones_abiertas()
    if pos:
        for ticker, p in pos.items():
            print(f"  {ticker}: {p['accion']} {p['cantidad']} @ {p['precio_entrada']}")
    else:
        print("  Sin posiciones abiertas")
