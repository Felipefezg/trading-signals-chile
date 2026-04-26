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
IB_CLIENT_ID  = 10    # ID único para este módulo

CAPITAL_TOTAL      = 100_000   # USD asignado al sistema
MAX_POR_OPERACION  = 10_000    # USD máximo por trade
MAX_POSICIONES     = 5         # posiciones simultáneas
MAX_CRYPTO_USD     = 15_000    # máximo en crypto
MAX_FUTUROS_USD    = 10_000    # máximo en futuros
HORIZONTE_MAX_DIAS = 3         # cierre forzado día 3
MIN_CONVICCION     = 75        # % mínimo para operar
MAX_RIESGO         = 6         # /10 máximo

# Archivo para persistir posiciones abiertas
POSICIONES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "posiciones.json")

# ── CONTRATOS IB ──────────────────────────────────────────────────────────────
def _crear_contrato(ib_ticker, tipo):
    c = Contract()
    if tipo == "ETF" or tipo == "Acción USA/Chile":
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
        c.lastTradeDateOrContractMonth = _proximo_vencimiento()
    elif tipo == "Forex":
        c.symbol   = "USD"
        c.secType  = "CASH"
        c.exchange = "IDEALPRO"
        c.currency = "CLP"
    return c

def _proximo_vencimiento():
    """Retorna el mes de vencimiento más próximo para futuros (YYYYMM)"""
    hoy = datetime.now()
    if hoy.day < 15:
        return hoy.strftime("%Y%m")
    else:
        siguiente = hoy.replace(day=1) + timedelta(days=32)
        return siguiente.strftime("%Y%m")

def _crear_orden(accion, cantidad, sl=None, tp=None):
    """Crea orden de mercado con bracket (SL + TP) si están disponibles"""
    if sl and tp:
        # Orden bracket: entrada + SL + TP automáticos
        orden_entrada = Order()
        orden_entrada.action        = "BUY" if accion == "COMPRAR" else "SELL"
        orden_entrada.orderType     = "MKT"
        orden_entrada.totalQuantity = cantidad
        orden_entrada.transmit      = False  # No transmitir hasta adjuntar SL/TP

        orden_sl = Order()
        orden_sl.action        = "SELL" if accion == "COMPRAR" else "BUY"
        orden_sl.orderType     = "STP"
        orden_sl.auxPrice      = sl
        orden_sl.totalQuantity = cantidad
        orden_sl.transmit      = False

        orden_tp = Order()
        orden_tp.action        = "SELL" if accion == "COMPRAR" else "BUY"
        orden_tp.orderType     = "LMT"
        orden_tp.lmtPrice      = tp
        orden_tp.totalQuantity = cantidad
        orden_tp.transmit      = True  # Transmitir todo junto

        return [orden_entrada, orden_sl, orden_tp]
    else:
        orden = Order()
        orden.action        = "BUY" if accion == "COMPRAR" else "SELL"
        orden.orderType     = "MKT"
        orden.totalQuantity = cantidad
        orden.transmit      = True
        return [orden]

# ── GESTIÓN DE POSICIONES ─────────────────────────────────────────────────────
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
    """Retorna lista de tickers cuyo horizonte máximo ya venció"""
    expiradas = []
    ahora = datetime.now()
    for ticker, pos in posiciones.items():
        fecha_entrada = datetime.fromisoformat(pos["fecha_entrada"])
        dias = (ahora - fecha_entrada).days
        if dias >= HORIZONTE_MAX_DIAS:
            expiradas.append(ticker)
    return expiradas

def _calcular_cantidad(precio_actual, tipo):
    """Calcula cantidad de contratos/acciones según capital máximo por operación"""
    if precio_actual is None or precio_actual <= 0:
        return 0
    max_usd = MAX_POR_OPERACION
    if tipo == "Crypto":
        max_usd = min(MAX_POR_OPERACION, MAX_CRYPTO_USD)
    elif tipo == "Futuro":
        max_usd = min(MAX_POR_OPERACION, MAX_FUTUROS_USD)
    cantidad = int(max_usd / precio_actual)
    return max(1, cantidad)

# ── CLIENTE IB ────────────────────────────────────────────────────────────────
class IBExecutor(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self._next_order_id = None
        self._cuenta_info   = {}
        self._ready         = threading.Event()
        self._precios       = {}
        self._precio_event  = threading.Event()
        self.errores        = []
        self.ordenes_enviadas = []

    def nextValidId(self, orderId):
        self._next_order_id = orderId
        self._ready.set()

    def accountSummary(self, reqId, account, tag, value, currency):
        self._cuenta_info[tag] = float(value)

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType in (1, 2, 4) and price > 0:  # bid, ask, last
            self._precios[reqId] = price
            self._precio_event.set()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode not in (2104, 2106, 2158, 2119):  # ignorar mensajes info
            self.errores.append(f"[{errorCode}] {errorString}")

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        pass

    def _get_next_id(self):
        oid = self._next_order_id
        self._next_order_id += 1
        return oid

    def conectar(self):
        self.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        self._ready.wait(timeout=10)
        return self._next_order_id is not None

    def get_precio_actual(self, contrato, timeout=5):
        """Obtiene precio actual de mercado vía snapshot"""
        req_id = self._get_next_id()
        self._precio_event.clear()
        self._precios.pop(req_id, None)
        self.reqMktData(req_id, contrato, "", True, False, [])
        self._precio_event.wait(timeout=timeout)
        return self._precios.get(req_id)

    def enviar_orden(self, contrato, ordenes):
        """Envía bracket de órdenes y retorna lista de IDs"""
        ids = []
        parent_id = None
        for i, orden in enumerate(ordenes):
            oid = self._get_next_id()
            if i == 0:
                parent_id = oid
            elif i > 0 and parent_id:
                orden.parentId = parent_id
            self.placeOrder(oid, contrato, orden)
            ids.append(oid)
            time.sleep(0.1)
        return ids

    def cerrar_posicion(self, contrato, cantidad, accion_original):
        """Cierra posición abierta con orden de mercado"""
        accion_cierre = "SELL" if accion_original == "COMPRAR" else "BUY"
        orden = Order()
        orden.action        = accion_cierre
        orden.orderType     = "MKT"
        orden.totalQuantity = cantidad
        orden.transmit      = True
        oid = self._get_next_id()
        self.placeOrder(oid, contrato, orden)
        return oid

# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────────────────────────
def ejecutar_señales(recomendaciones, modo_test=False):
    """
    Ejecuta señales de trading en IB Paper Trading.

    Args:
        recomendaciones: lista de recomendaciones del motor
        modo_test: si True, simula sin enviar órdenes reales

    Returns:
        dict con resumen de ejecución
    """
    posiciones = _cargar_posiciones()
    resumen = {
        "timestamp": datetime.now().isoformat(),
        "ordenes_enviadas": [],
        "ordenes_rechazadas": [],
        "posiciones_cerradas": [],
        "errores": [],
        "modo": "TEST" if modo_test else "PAPER",
    }

    # Filtrar señales que cumplen política
    señales_validas = [
        r for r in recomendaciones
        if r["conviccion"] >= MIN_CONVICCION
        and r["riesgo"] <= MAX_RIESGO
        and r["n_fuentes"] >= 2
    ]

    if not señales_validas:
        resumen["errores"].append("Sin señales que cumplan política de inversión")
        return resumen

    # Verificar límite de posiciones
    posiciones_abiertas = len(posiciones)
    slots_disponibles = MAX_POSICIONES - posiciones_abiertas

    if slots_disponibles <= 0:
        resumen["errores"].append(f"Máximo de posiciones alcanzado ({MAX_POSICIONES})")

    if modo_test:
        # Modo test: simular sin conectar a IB
        for r in señales_validas[:slots_disponibles]:
            ticker = r["ib_ticker"]
            if ticker in posiciones:
                resumen["ordenes_rechazadas"].append({
                    "ticker": ticker, "razon": "Posición ya abierta"
                })
                continue
            precio = r.get("precio_actual", 100)
            cantidad = _calcular_cantidad(precio, r["tipo"])
            resumen["ordenes_enviadas"].append({
                "ticker":    ticker,
                "accion":    r["accion"],
                "cantidad":  cantidad,
                "precio_est": precio,
                "monto_usd": round(cantidad * (precio or 0), 2),
                "sl":        r.get("stop_loss"),
                "tp":        r.get("take_profit"),
                "horizonte": r.get("horizonte", {}).get("dias"),
                "conviccion": r["conviccion"],
                "riesgo":    r["riesgo"],
            })
        return resumen

    # Modo real: conectar a IB
    ib = IBExecutor()
    if not ib.conectar():
        resumen["errores"].append("No se pudo conectar a IB. ¿Está TWS corriendo?")
        return resumen

    time.sleep(1)

    try:
        # 1. Cerrar posiciones expiradas
        expiradas = _posiciones_expiradas(posiciones)
        for ticker in expiradas:
            pos = posiciones[ticker]
            try:
                contrato = _crear_contrato(ticker, pos["tipo"])
                oid = ib.cerrar_posicion(contrato, pos["cantidad"], pos["accion"])
                resumen["posiciones_cerradas"].append({
                    "ticker": ticker, "razon": "Horizonte máximo vencido", "order_id": oid
                })
                del posiciones[ticker]
            except Exception as e:
                resumen["errores"].append(f"Error cerrando {ticker}: {e}")

        # 2. Abrir nuevas posiciones
        for r in señales_validas[:slots_disponibles]:
            ticker = r["ib_ticker"]
            tipo   = r["tipo"]

            # No duplicar posición
            if ticker in posiciones:
                resumen["ordenes_rechazadas"].append({
                    "ticker": ticker, "razon": "Posición ya abierta"
                })
                continue

            try:
                contrato = _crear_contrato(ticker, tipo)

                # Obtener precio actual
                precio = r.get("precio_actual") or ib.get_precio_actual(contrato)
                if not precio:
                    resumen["ordenes_rechazadas"].append({
                        "ticker": ticker, "razon": "No se pudo obtener precio"
                    })
                    continue

                cantidad = _calcular_cantidad(precio, tipo)
                if cantidad == 0:
                    resumen["ordenes_rechazadas"].append({
                        "ticker": ticker, "razon": "Cantidad calculada = 0"
                    })
                    continue

                sl = r.get("stop_loss")
                tp = r.get("take_profit")
                ordenes = _crear_orden(r["accion"], cantidad, sl, tp)
                ids = ib.enviar_orden(contrato, ordenes)

                # Registrar posición
                posiciones[ticker] = {
                    "accion":        r["accion"],
                    "cantidad":      cantidad,
                    "precio_entrada": precio,
                    "sl":            sl,
                    "tp":            tp,
                    "tipo":          tipo,
                    "fecha_entrada": datetime.now().isoformat(),
                    "horizonte":     r.get("horizonte", {}).get("dias"),
                    "conviccion":    r["conviccion"],
                    "order_ids":     ids,
                }

                resumen["ordenes_enviadas"].append({
                    "ticker":    ticker,
                    "accion":    r["accion"],
                    "cantidad":  cantidad,
                    "precio":    precio,
                    "monto_usd": round(cantidad * precio, 2),
                    "sl":        sl,
                    "tp":        tp,
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
    """Retorna posiciones actualmente abiertas"""
    return _cargar_posiciones()

def get_resumen_cuenta():
    """Obtiene resumen de cuenta paper de IB"""
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
