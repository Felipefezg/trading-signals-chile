"""
Módulo de opciones para Interactive Brokers.
Estrategias:
1. Comprar call/put (alta convicción, corto plazo) — riesgo limitado al premium
2. Vender call cubierto (media convicción, posición existente) — generar ingreso

Subyacentes disponibles: SPY, SQM, GLD
"""

import threading
import time
import math
from datetime import datetime, timedelta
IB_DISPONIBLE = False
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IB_DISPONIBLE = True
except Exception:
    class EClient: pass
    class EWrapper: pass
    class Contract: pass
    class Order: pass

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 20  # ID distinto al executor principal

# Subyacentes con opciones disponibles en IB
SUBYACENTES_OPCIONES = {
    "SPY": {"nombre": "S&P 500 ETF",    "multiplicador": 100, "moneda": "USD"},
    "SQM": {"nombre": "SQM ADR (NYSE)", "multiplicador": 100, "moneda": "USD"},
    "GLD": {"nombre": "Gold ETF",        "multiplicador": 100, "moneda": "USD"},
}

# Parámetros de selección de opciones
DELTA_OBJETIVO   = 0.35   # Delta ~35 (ligeramente OTM)
MAX_PREMIUM_USD  = 500    # Máximo premium por contrato
MAX_CONTRATOS    = 5      # Máximo contratos por operación
DTE_MIN          = 7      # Días mínimos al vencimiento
DTE_MAX_COMPRA   = 45     # Días máximos para compra (no muy lejano)
DTE_MAX_VENTA    = 30     # Días máximos para venta cubierta

# ── CLIENTE IB OPCIONES ───────────────────────────────────────────────────────
if IB_DISPONIBLE:
    class OptionsClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self._next_order_id = None
        self._ready         = threading.Event()
        self._contratos     = []
        self._contrato_event = threading.Event()
        self._precio        = {}
        self._precio_event  = threading.Event()
        self._greeks        = {}
        self._greeks_event  = threading.Event()
        self.errores        = []

    def nextValidId(self, orderId):
        self._next_order_id = orderId
        self._ready.set()

    def contractDetails(self, reqId, details):
        c = details.contract
        self._contratos.append({
            "symbol":   c.symbol,
            "strike":   c.strike,
            "right":    c.right,
            "expiry":   c.lastTradeDateOrContractMonth,
            "exchange": c.exchange,
            "multiplier": c.multiplier or 100,
            "conId":    c.conId,
        })

    def contractDetailsEnd(self, reqId):
        self._contrato_event.set()

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType in (1, 2, 4) and price > 0:
            self._precio[reqId] = price
            self._precio_event.set()

    def tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol,
                               delta, optPrice, pvDividend, gamma, vega, theta, undPrice):
        if delta is not None and abs(delta) > 0:
            self._greeks[reqId] = {
                "delta": round(delta, 3),
                "gamma": round(gamma or 0, 4),
                "vega":  round(vega or 0, 4),
                "theta": round(theta or 0, 4),
                "iv":    round(impliedVol or 0, 3),
                "precio_subyacente": undPrice,
            }
            self._greeks_event.set()

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

# ── SELECCIÓN DE CONTRATOS ────────────────────────────────────────────────────
def _fecha_vencimiento_objetivo(dte_min, dte_max):
    """Genera lista de vencimientos dentro del rango DTE"""
    hoy = datetime.now()
    vencimientos = []
    # Generar viernes de los próximos meses (opciones mensuales expiran 3er viernes)
    for meses_adelante in range(1, 6):
        mes = hoy + timedelta(days=30 * meses_adelante)
        # Tercer viernes del mes
        primer_dia = mes.replace(day=1)
        primer_viernes = primer_dia + timedelta(days=(4 - primer_dia.weekday()) % 7)
        tercer_viernes = primer_viernes + timedelta(weeks=2)
        dte = (tercer_viernes - hoy).days
        if dte_min <= dte <= dte_max:
            vencimientos.append(tercer_viernes.strftime("%Y%m%d"))
    return vencimientos

def buscar_contrato_opcion(ib, symbol, right, precio_actual, dte_min, dte_max):
    """
    Busca el contrato de opción más apropiado (delta ~0.35, OTM).
    right: 'C' para call, 'P' para put
    """
    # Strike objetivo: ~5% OTM
    if right == "C":
        strike_obj = round(precio_actual * 1.05 / 5) * 5  # redondear a múltiplo de 5
    else:
        strike_obj = round(precio_actual * 0.95 / 5) * 5

    vencimientos = _fecha_vencimiento_objetivo(dte_min, dte_max)
    if not vencimientos:
        return None

    ib._contratos = []
    ib._contrato_event.clear()

    c = Contract()
    c.symbol   = symbol
    c.secType  = "OPT"
    c.exchange = "SMART"
    c.currency = "USD"
    c.right    = right
    c.strike   = strike_obj
    c.lastTradeDateOrContractMonth = vencimientos[0]

    req_id = ib._get_next_id()
    ib.reqContractDetails(req_id, c)
    ib._contrato_event.wait(timeout=8)

    if not ib._contratos:
        # Intentar sin fecha específica
        ib._contratos = []
        ib._contrato_event.clear()
        c2 = Contract()
        c2.symbol   = symbol
        c2.secType  = "OPT"
        c2.exchange = "SMART"
        c2.currency = "USD"
        c2.right    = right
        c2.strike   = strike_obj
        ib.reqContractDetails(req_id + 1, c2)
        ib._contrato_event.wait(timeout=8)

    if not ib._contratos:
        return None

    # Filtrar por DTE
    hoy = datetime.now()
    validos = []
    for ct in ib._contratos:
        exp = datetime.strptime(ct["expiry"][:8], "%Y%m%d")
        dte = (exp - hoy).days
        if dte_min <= dte <= dte_max:
            ct["dte"] = dte
            validos.append(ct)

    if not validos:
        # Tomar el más cercano dentro de rango ampliado
        for ct in ib._contratos:
            exp = datetime.strptime(ct["expiry"][:8], "%Y%m%d")
            ct["dte"] = (exp - hoy).days
        validos = sorted(ib._contratos, key=lambda x: x["dte"])
        validos = [v for v in validos if v["dte"] >= DTE_MIN]

    return validos[0] if validos else None

def get_precio_opcion(ib, contrato_dict, timeout=5):
    """Obtiene precio de mercado de una opción"""
    req_id = ib._get_next_id()
    ib._precio_event.clear()
    ib._precio.pop(req_id, None)

    c = Contract()
    c.symbol     = contrato_dict["symbol"]
    c.secType    = "OPT"
    c.exchange   = contrato_dict.get("exchange", "SMART")
    c.currency   = "USD"
    c.right      = contrato_dict["right"]
    c.strike     = contrato_dict["strike"]
    c.lastTradeDateOrContractMonth = contrato_dict["expiry"]
    c.multiplier = str(contrato_dict.get("multiplier", 100))

    ib.reqMktData(req_id, c, "", True, False, [])
    ib._precio_event.wait(timeout=timeout)
    return ib._precio.get(req_id)

# ── ESTRATEGIAS ───────────────────────────────────────────────────────────────
def estrategia_compra_opcion(symbol, accion, conviccion, precio_subyacente,
                              max_premium_total=1000):
    """
    Estrategia 1: Comprar call (COMPRAR) o put (VENDER) OTM.
    Para señales de alta convicción (≥80%) y corto plazo.

    Retorna dict con detalles de la estrategia o None si no aplica.
    """
    if conviccion < 80:
        return None
    if symbol not in SUBYACENTES_OPCIONES:
        return None

    right = "C" if accion == "COMPRAR" else "P"
    strike_objetivo = (
        round(precio_subyacente * 1.05 / 5) * 5 if right == "C"
        else round(precio_subyacente * 0.95 / 5) * 5
    )

    # Estimación del premium (aprox 2-4% del precio subyacente para OTM 5%)
    premium_est = precio_subyacente * 0.025
    max_contratos = min(MAX_CONTRATOS, int(max_premium_total / (premium_est * 100)))
    max_contratos = max(1, max_contratos)

    return {
        "estrategia":        "Comprar opción",
        "tipo":              f"Comprar {right} {'Call' if right=='C' else 'Put'}",
        "symbol":            symbol,
        "right":             right,
        "strike_objetivo":   strike_objetivo,
        "dte_objetivo":      f"{DTE_MIN}-{DTE_MAX_COMPRA} días",
        "contratos":         max_contratos,
        "premium_est_unit":  round(premium_est, 2),
        "costo_total_est":   round(premium_est * 100 * max_contratos, 2),
        "max_perdida":       round(premium_est * 100 * max_contratos, 2),
        "break_even":        round(strike_objetivo + premium_est if right=="C" else strike_objetivo - premium_est, 2),
        "razon":             f"Convicción {conviccion}% → comprar {right} OTM amplifica retorno con pérdida máxima conocida",
        "pros":              "Apalancamiento 5-10x, pérdida limitada al premium pagado",
        "contras":           "Theta decay, necesita movimiento rápido del subyacente",
    }

def estrategia_call_cubierto(symbol, precio_subyacente, cantidad_acciones):
    """
    Estrategia 2: Vender call cubierto sobre posición existente.
    Para generar ingreso adicional sobre acciones ya compradas.

    Retorna dict con detalles o None si no aplica.
    """
    if symbol not in SUBYACENTES_OPCIONES:
        return None
    if cantidad_acciones < 100:  # Necesita al menos 1 lote
        return None

    contratos = cantidad_acciones // 100
    strike_objetivo = round(precio_subyacente * 1.05 / 5) * 5  # 5% OTM
    premium_est = precio_subyacente * 0.015  # ~1.5% para call cubierto

    return {
        "estrategia":       "Vender call cubierto",
        "tipo":             "Vender Call (covered)",
        "symbol":           symbol,
        "right":            "C",
        "strike_objetivo":  strike_objetivo,
        "dte_objetivo":     f"15-{DTE_MAX_VENTA} días",
        "contratos":        contratos,
        "premium_est_unit": round(premium_est, 2),
        "ingreso_est":      round(premium_est * 100 * contratos, 2),
        "max_ganancia":     round((strike_objetivo - precio_subyacente + premium_est) * 100 * contratos, 2),
        "razon":            f"Posición en {symbol} abierta → vender call {strike_objetivo} genera ingreso con protección parcial",
        "pros":             "Ingreso inmediato, reduce costo base de la posición",
        "contras":          "Limita ganancia si el subyacente sube mucho",
    }

def get_estrategias_opciones(recomendaciones, posiciones_abiertas):
    """
    Evalúa todas las recomendaciones y posiciones abiertas
    y genera sugerencias de estrategias de opciones.
    """
    estrategias = []

    for r in recomendaciones:
        ticker_ib = r.get("ib_ticker", "")
        conviccion = r.get("conviccion", 0)
        precio = r.get("precio_actual")
        accion = r.get("accion")
        horizonte = r.get("horizonte", {}).get("label", "")

        if not precio:
            continue

        # Estrategia 1: Comprar opción para señales de alta convicción y corto plazo
        if conviccion >= 80 and "Corto" in horizonte and ticker_ib in SUBYACENTES_OPCIONES:
            est = estrategia_compra_opcion(ticker_ib, accion, conviccion, precio)
            if est:
                est["señal_origen"] = r.get("tesis", "")[:60]
                est["conviccion"]   = conviccion
                estrategias.append(est)

    # Estrategia 2: Call cubierto sobre posiciones abiertas
    for ticker, pos in posiciones_abiertas.items():
        if pos.get("accion") == "COMPRAR" and ticker in SUBYACENTES_OPCIONES:
            precio_entrada = pos.get("precio_entrada", 0)
            cantidad = pos.get("cantidad", 0)
            if cantidad >= 100:
                est = estrategia_call_cubierto(ticker, precio_entrada, cantidad)
                if est:
                    est["señal_origen"] = f"Posición abierta: {cantidad} acciones @ {precio_entrada}"
                    estrategias.append(est)

    return estrategias

def ejecutar_opcion_compra(symbol, right, strike, expiry, contratos, modo_test=False):
    """
    Ejecuta compra de opción en IB.
    """
    resultado = {
        "accion": f"COMPRAR {right}",
        "symbol": symbol, "strike": strike,
        "expiry": expiry, "contratos": contratos,
        "modo": "TEST" if modo_test else "PAPER",
        "ejecutado": False, "error": None,
    }

    if modo_test:
        resultado["ejecutado"] = True
        resultado["nota"] = "Simulación — no se envió orden real"
        return resultado

    ib = OptionsClient()
    if not ib.conectar():
        resultado["error"] = "No se pudo conectar a IB"
        return resultado

    try:
        time.sleep(1)
        c = Contract()
        c.symbol     = symbol
        c.secType    = "OPT"
        c.exchange   = "SMART"
        c.currency   = "USD"
        c.right      = right
        c.strike     = strike
        c.lastTradeDateOrContractMonth = expiry
        c.multiplier = "100"

        o = Order()
        o.action        = "BUY"
        o.orderType     = "MKT"
        o.totalQuantity = contratos
        o.transmit      = True
        o.eTradeOnly    = False
        o.firmQuoteOnly = False

        oid = ib._get_next_id()
        ib.placeOrder(oid, c, o)
        time.sleep(2)

        resultado["ejecutado"] = True
        resultado["order_id"]  = oid

    except Exception as e:
        resultado["error"] = str(e)
    finally:
        ib.disconnect()

    return resultado

if __name__ == "__main__":
    print("=== TEST MÓDULO OPCIONES ===")
    print("\nSubyacentes disponibles:")
    for s, meta in SUBYACENTES_OPCIONES.items():
        print(f"  {s}: {meta['nombre']}")

    print("\nEstrategia ejemplo — Comprar PUT SQM (señal VENDER, convicción 95%):")
    est = estrategia_compra_opcion("SQM", "VENDER", 95.0, 40.0)
    if est:
        for k, v in est.items():
            print(f"  {k}: {v}")
# ibapi opcional
