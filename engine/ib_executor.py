"""
Ejecutor IB — Rediseñado
IB es la única fuente de verdad.

FLUJO CORRECTO:
1. Motor genera señal
2. Verificar en IB si ya hay posición abierta en ese activo
3. Enviar orden a IB
4. ESPERAR confirmación de IB (Filled/Submitted)
5. Solo DESPUÉS registrar localmente
6. Monitoreo usa datos reales de IB, no locales

PRINCIPIOS:
- Nunca registrar localmente sin confirmación de IB
- Posiciones locales = espejo exacto de IB
- Si IB no confirma en 30s → orden fallida, no registrar
- Un solo cliente IB por sesión (evitar conflictos de clientId)
"""

import threading
import time
import json
import os
import yfinance as yf
from datetime import datetime

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSICIONES_FILE = os.path.join(BASE_DIR, "posiciones.json")

IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 10  # ID fijo para el ejecutor

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IB_DISPONIBLE = True
except:
    IB_DISPONIBLE = False

# ── CLIENTE IB ────────────────────────────────────────────────────────────────
if IB_DISPONIBLE:
    class IBEjecutor(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._ready         = threading.Event()
            self._orderId       = None
            self._lock          = threading.Lock()
            self._posiciones    = {}   # symbol → {position, avgCost}
            self._done_pos      = threading.Event()
            self._ordenes       = {}   # orderId → status
            self._filled        = {}   # orderId → {filled, avgPrice}
            self._open_orders   = {}   # orderId → True  (órdenes abiertas confirmadas en TWS)
            self._done_orders   = threading.Event()
            self._capital       = 0.0
            self._done_acct     = threading.Event()

        def nextValidId(self, orderId):
            with self._lock:
                self._orderId = orderId
            self._ready.set()

        def _next_id(self):
            with self._lock:
                oid = self._orderId
                self._orderId += 1
            return oid

        # ── POSICIONES ────────────────────────────────────────────────────────
        def position(self, account, contract, position, avgCost):
            if position != 0:
                self._posiciones[contract.symbol] = {
                    "position": float(position),
                    "avgCost":  round(float(avgCost), 4),
                    "secType":  contract.secType,
                    "currency": contract.currency,
                }

        def positionEnd(self):
            self._done_pos.set()

        # ── ESTADO DE ÓRDENES ─────────────────────────────────────────────────
        def orderStatus(self, orderId, status, filled, remaining,
                        avgFillPrice, *args):
            import logging as _log
            _log.info(f"orderStatus: id={orderId} status={status} filled={filled}")
            self._ordenes[orderId] = status
            if filled > 0:
                self._filled[orderId] = {
                    "filled":   float(filled),
                    "avgPrice": round(float(avgFillPrice), 4),
                }

        # ── ÓRDENES ABIERTAS (fallback) ───────────────────────────────────────
        def openOrder(self, orderId, contract, order, orderState):
            """
            TWS envía openOrder para cada orden activa.
            Usamos esto como fallback cuando orderStatus no llega a tiempo.
            """
            self._open_orders[orderId] = {
                "symbol": contract.symbol,
                "action": order.action,
                "qty":    float(order.totalQuantity),
                "status": orderState.status,
            }
            # También registrar el status en _ordenes si aún no llegó
            if orderId not in self._ordenes or not self._ordenes[orderId]:
                self._ordenes[orderId] = orderState.status

        def openOrderEnd(self):
            self._done_orders.set()

        def execDetails(self, reqId, contract, execution):
            # Registrar ejecuciones para detectar fills
            oid = execution.orderId
            self._filled[oid] = {
                "filled":   float(execution.shares),
                "avgPrice": round(float(execution.price), 4),
            }
            self._ordenes[oid] = "Filled"

        # ── CUENTA ────────────────────────────────────────────────────────────
        def accountSummary(self, reqId, account, tag, value, currency):
            if tag == "NetLiquidation":
                try:
                    self._capital = float(value)
                except:
                    pass

        def accountSummaryEnd(self, reqId):
            self._done_acct.set()

        # ── ERRORES ───────────────────────────────────────────────────────────
        def error(self, reqId, errorCode, errorString, *args):
            import logging as _log
            ignorar = {2104, 2106, 2158, 2103, 2119, 2110, 2105, 2157, 10349}
            if errorCode not in ignorar:
                if errorCode == 1104:
                    pass  # Pending orders — ignorar
                else:
                    _log.warning(f"IB Error [{errorCode}] reqId={reqId}: {errorString[:100]}")
                    print(f"  IB Error [{errorCode}]: {errorString[:80]}")

        def conectar(self, timeout=8):
            try:
                self.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
                t = threading.Thread(target=self.run, daemon=True)
                t.start()
                return self._ready.wait(timeout=timeout)
            except Exception as e:
                print(f"  Error conectando IB: {e}")
                return False

# ── CONTRATOS ─────────────────────────────────────────────────────────────────
def crear_contrato(ib_ticker, tipo):
    """Crea contrato IB según tipo de activo"""
    if not IB_DISPONIBLE:
        return None

    c = Contract()
    c.symbol = ib_ticker

    if tipo == "Crypto":
        c.secType  = "CRYPTO"
        c.exchange = "PAXOS"
        c.currency = "USD"
    elif tipo in ("Acción Chile",):
        c.secType  = "STK"
        c.exchange = "SN"
        c.currency = "CLP"
    elif tipo in ("Futuro",):
        c.secType  = "FUT"
        c.exchange = "NYMEX" if ib_ticker in ("CL", "NG") else "COMEX"
        c.currency = "USD"
        c.lastTradeDateOrContractMonth = _proximo_vencimiento()
    else:
        # Acción USA, ETF, ADR
        c.secType  = "STK"
        c.exchange = "SMART"
        c.currency = "USD"

    return c

def _proximo_vencimiento():
    """Retorna el próximo mes de vencimiento para futuros"""
    now = datetime.now()
    if now.day < 15:
        return now.strftime("%Y%m")
    else:
        mes = now.month + 1 if now.month < 12 else 1
        año = now.year if now.month < 12 else now.year + 1
        return f"{año}{mes:02d}"

# ── OBTENER PRECIO ACTUAL ─────────────────────────────────────────────────────
def get_precio_actual(ib_ticker, tipo):
    """Obtiene precio actual desde Yahoo Finance como fallback confiable"""
    yf_map = {
        # Futuros / Crypto
        "BTC": "BTC-USD", "GC": "GC=F", "HG": "HG=F", "CL": "CL=F",
        # ADRs chilenos en NYSE — ya tienen ticker USA directo
        # Acciones chilenas locales — sufijo .SN para Yahoo Finance
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
        "SQM": "SQM", "ECH": "ECH", "SPY": "SPY", "GLD": "GLD",
        "TLT": "TLT", "BSAC": "BSAC", "BCH": "BCH", "LTM": "LTM",
    }
    yf_ticker = yf_map.get(ib_ticker, f"{ib_ticker}.SN")
    try:
        h = yf.Ticker(yf_ticker).history(period="1d")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except:
        pass
    return None

# ── CALCULAR CANTIDAD ─────────────────────────────────────────────────────────
_USD_CLP_CACHE = {"rate": None, "ts": 0}

def _get_usd_clp():
    """Tipo de cambio USD/CLP con caché de 10 minutos."""
    import time as _t
    now = _t.time()
    if _USD_CLP_CACHE["rate"] and now - _USD_CLP_CACHE["ts"] < 600:
        return _USD_CLP_CACHE["rate"]
    try:
        h = yf.Ticker("CLP=X").history(period="2d")
        rate = float(h["Close"].iloc[-1]) if not h.empty else 950.0
    except Exception:
        rate = 950.0
    _USD_CLP_CACHE["rate"] = rate
    _USD_CLP_CACHE["ts"]   = now
    return rate


def calcular_cantidad(precio, tipo, conviccion=75, capital=100_000,
                      max_usd=15_000, sl=None):
    """
    Calcula cantidad usando Half-Kelly simplificado.

    - Acciones Chile: precio en CLP → convierte a USD antes de dividir.
    - Futuros: máximo 1 contrato (nocional enorme — CL=1000 bbl, GC=100 oz).
    - Crypto: sizing reducido al 30%.
    - Todo lo demás: tamaño basado en USD.
    """
    if not precio or precio <= 0:
        return 0

    # Sizing base según convicción (Half-Kelly simplificado)
    pct_capital = min(0.15, (conviccion - 50) / 100 * 0.3)
    usd_base    = capital * pct_capital
    usd_op      = min(usd_base, max_usd)

    # ── Futuros: máximo 1 contrato para controlar exposición nocional ──────────
    # CL (WTI) = 1000 barriles × ~$62 = $62k/contrato
    # GC (Oro) = 100 oz × ~$3300 = $330k/contrato
    # HG (Cobre) = 25000 lb × ~$4.80 = $120k/contrato
    if tipo == "Futuro":
        return 1

    # ── Crypto: sizing reducido ────────────────────────────────────────────────
    if tipo == "Crypto":
        usd_op  *= 0.3
        cantidad = usd_op / precio
        return round(max(0.001, cantidad), 4)

    # ── Acciones chilenas: precio en CLP → convertir a USD ────────────────────
    if tipo == "Acción Chile":
        clp_por_usd = _get_usd_clp()
        precio_usd  = precio / clp_por_usd      # CLP → USD
        if precio_usd <= 0:
            return 0
        cantidad = usd_op / precio_usd
        return max(1, int(cantidad))

    # ── Acciones USA / ETFs / ADRs ─────────────────────────────────────────────
    cantidad = usd_op / precio
    return max(1, int(cantidad))

# ── EJECUTAR ORDEN ────────────────────────────────────────────────────────────
def ejecutar_orden(señal, modo_test=False):
    """
    Ejecuta una orden en IB y espera confirmación real.
    
    Returns:
        dict con resultado: {exito, orden_id, precio_fill, cantidad, error}
    """
    if not IB_DISPONIBLE:
        return {"exito": False, "error": "ibapi no disponible"}

    ib_ticker = señal.get("ib_ticker", "")
    tipo      = señal.get("tipo", "ETF")
    accion    = señal.get("accion", "")
    conviccion = float(señal.get("conviccion", 75))
    sl        = señal.get("stop_loss")
    tp        = señal.get("take_profit")

    if not ib_ticker or not accion:
        return {"exito": False, "error": "Señal incompleta"}

    # Obtener precio actual
    precio = señal.get("precio_actual") or get_precio_actual(ib_ticker, tipo)
    if not precio:
        return {"exito": False, "error": "No se pudo obtener precio"}

    # Calcular cantidad
    cantidad = calcular_cantidad(precio, tipo, conviccion, sl=sl)
    if cantidad <= 0:
        return {"exito": False, "error": "Cantidad calculada = 0"}

    if modo_test:
        print(f"  [TEST] {accion} {cantidad} {ib_ticker} @ {precio:.4f}")
        return {"exito": True, "test": True, "cantidad": cantidad, "precio": precio}

    # Conectar a IB
    client = IBEjecutor()
    if not client.conectar():
        return {"exito": False, "error": "No conecta con TWS"}

    try:
        time.sleep(0.3)

        # Verificar posiciones actuales en IB
        client.reqPositions()
        client._done_pos.wait(timeout=5)

        # Si ya hay posición filled en IB → no duplicar
        if ib_ticker in client._posiciones:
            pos_actual = client._posiciones[ib_ticker]["position"]
            if (accion == "COMPRAR" and pos_actual > 0) or \
               (accion == "VENDER" and pos_actual < 0):
                return {"exito": False, "error": f"Ya hay posición {ib_ticker} en IB"}

        # Si ya hay orden abierta (Submitted/PreSubmitted) en IB → no duplicar
        client._done_orders.clear()
        client.reqAllOpenOrders()
        client._done_orders.wait(timeout=8)
        for oid, oi in client._open_orders.items():
            if oi.get("symbol") == ib_ticker:
                accion_ib_existente = oi.get("action", "")
                if (accion == "COMPRAR" and accion_ib_existente == "BUY") or \
                   (accion == "VENDER" and accion_ib_existente == "SELL"):
                    return {
                        "exito": False,
                        "error": f"Ya existe orden activa {accion_ib_existente} para {ib_ticker} en IB (ID:{oid})"
                    }

        # Crypto / Acción Chile: no permitir short sin posición larga previa.
        # Paper trading PAXOS rechaza (error 201) ventas en corto de crypto.
        # IB paper tampoco permite short en Bolsa Santiago (SN).
        if accion == "VENDER" and tipo in ("Crypto", "Acción Chile"):
            pos_existente = client._posiciones.get(ib_ticker, {}).get("position", 0)
            if pos_existente <= 0:
                return {
                    "exito": False,
                    "error": f"VENDER {ib_ticker} bloqueado: no hay posición larga en IB (short no permitido en paper trading para {tipo})"
                }

        # Crear contrato y orden
        contrato = crear_contrato(ib_ticker, tipo)
        if not contrato:
            return {"exito": False, "error": "No se pudo crear contrato"}

        # Tick size por tipo de instrumento (requerimiento IB error 110)
        TICK = {
            "Crypto":       1.0,     # BTC/ETH en PAXOS → $1.00 (precio > $1000)
            "Futuro":       0.01,    # CL, GC, HG — mínimo común
            "Acción Chile": 1.0,     # Bolsa Santiago → 1 CLP
        }
        tick = TICK.get(tipo, 0.01)  # default $0.01 para acciones USA/ETF/ADR

        def _redondear_tick(p, t):
            """Redondea precio al tick correcto usando Decimal (evita floating-point error 110)."""
            import decimal
            d_p = decimal.Decimal(str(round(p, 6)))
            d_t = decimal.Decimal(str(t))
            redondeado = (d_p / d_t).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP) * d_t
            return float(redondeado)

        # Calcular precio límite con 0.1% slippage + tick correcto
        if accion == "COMPRAR":
            precio_lmt = _redondear_tick(precio * 1.001, tick)
            accion_ib  = "BUY"
        else:
            precio_lmt = _redondear_tick(precio * 0.999, tick)
            accion_ib  = "SELL"

        # Orden principal LMT
        orden = Order()
        orden.action        = accion_ib
        orden.orderType     = "LMT"
        orden.lmtPrice      = precio_lmt
        orden.totalQuantity = cantidad
        orden.transmit      = True
        orden.eTradeOnly    = False
        orden.firmQuoteOnly = False
        orden.tif           = "GTC"

        orden_id = client._next_id()
        client.placeOrder(orden_id, contrato, orden)

        import logging as _log
        _log.info(f"Orden enviada: {accion} {cantidad} {ib_ticker} @ {precio_lmt:.4f} (ID:{orden_id})")
        print(f"  Orden enviada: {accion} {cantidad} {ib_ticker} @ {precio_lmt:.4f} (ID:{orden_id})")

        # ── FASE 1: esperar orderStatus hasta 15s ─────────────────────────────
        ESTADOS_OK  = {"Filled", "Submitted", "PreSubmitted", "ApiPending"}
        ESTADOS_MAL = {"Cancelled", "Inactive", "ApiCancelled"}

        t0 = time.time()
        confirmado = False
        status     = ""
        while time.time() - t0 < 15:
            status = client._ordenes.get(orden_id, "")
            if status in ESTADOS_OK:
                confirmado = True
                break
            elif status in ESTADOS_MAL:
                _log.warning(f"Orden {orden_id} rechazada por IB: {status}")
                return {"exito": False, "error": f"Orden rechazada por IB: {status}"}
            time.sleep(0.3)

        # ── FASE 2: fallback — consultar open orders en TWS ───────────────────
        # Paper trading a veces no envía orderStatus en tiempo real.
        # Si la orden existe en TWS como open order → está activa aunque no
        # haya llegado el callback.
        if not confirmado:
            _log.info(f"orderStatus no llegó en 15s para {orden_id} — consultando open orders TWS")
            client._done_orders.clear()
            client.reqAllOpenOrders()
            client._done_orders.wait(timeout=8)

            if orden_id in client._open_orders:
                confirmado = True
                status = client._open_orders[orden_id].get("status", "Submitted")
                _log.info(f"Orden {orden_id} confirmada vía open orders: {status}")
                print(f"  ✅ Confirmada vía open orders TWS: {status}")
            else:
                # La orden no existe en TWS — cancelar y reportar falla
                _log.warning(f"Orden {orden_id} no encontrada en TWS — cancelando")
                try:
                    client.cancelOrder(orden_id)
                except Exception:
                    pass
                return {"exito": False, "error": f"IB no registró la orden (status: {status or 'sin respuesta'})"}

        # Obtener precio de fill real
        fill_info  = client._filled.get(orden_id, {})
        precio_fill = fill_info.get("avgPrice", precio_lmt)
        filled_qty  = fill_info.get("filled", cantidad)

        return {
            "exito":      True,
            "orden_id":   orden_id,
            "precio_fill": precio_fill,
            "cantidad":   filled_qty or cantidad,
            "sl":         sl,
            "tp":         tp,
            "status":     client._ordenes.get(orden_id, "Submitted"),
        }

    except Exception as e:
        return {"exito": False, "error": str(e)}
    finally:
        try:
            client.disconnect()
        except:
            pass

# ── REGISTRAR POSICIÓN (SOLO DESPUÉS DE CONFIRMACIÓN IB) ─────────────────────
def registrar_posicion(señal, resultado_ib):
    """
    Registra posición localmente SOLO después de confirmación real de IB.
    """
    try:
        with open(POSICIONES_FILE) as f:
            posiciones = json.load(f)
    except:
        posiciones = {}

    ib_ticker = señal.get("ib_ticker", "")
    precio    = resultado_ib.get("precio_fill", señal.get("precio_actual", 0))
    cantidad  = resultado_ib.get("cantidad", 1)
    sl        = señal.get("stop_loss")
    tp        = señal.get("take_profit")

    posiciones[ib_ticker] = {
        "accion":        señal.get("accion"),
        "cantidad":      cantidad,
        "precio_entrada": precio,
        "sl":            sl,
        "tp":            tp,
        "tipo":          señal.get("tipo", "ETF"),
        "fecha_entrada": datetime.now().isoformat(),
        "horizonte":     señal.get("horizonte", "1-7 días"),
        "conviccion":    señal.get("conviccion", 75),
        "orden_id":      resultado_ib.get("orden_id"),
        "fuentes":       señal.get("fuentes", []),
        "tesis":         señal.get("tesis", ""),
        "confirmado_ib": True,  # Marca que fue confirmado por IB
    }

    with open(POSICIONES_FILE, "w") as f:
        json.dump(posiciones, f, indent=2)

    return posiciones[ib_ticker]

# ── SINCRONIZAR POSICIONES DESDE IB ──────────────────────────────────────────
def sincronizar_desde_ib():
    """
    Obtiene posiciones reales desde IB y actualiza el archivo local.
    IB manda — si IB dice que no hay posición, se elimina localmente.
    """
    if not IB_DISPONIBLE:
        return {}

    client = IBEjecutor()
    if not client.conectar():
        return {}

    try:
        time.sleep(0.3)

        # ── FASE 1: posiciones filled en IB ──────────────────────────────────
        client.reqPositions()
        client._done_pos.wait(timeout=8)
        posiciones_ib = client._posiciones  # solo posiciones con fill real

        # ── FASE 2: órdenes abiertas (Submitted/PreSubmitted sin fill) ────────
        client._done_orders.clear()
        client.reqAllOpenOrders()
        client._done_orders.wait(timeout=8)
        # Construir set de symbols con orden activa en IB
        open_order_symbols = {v["symbol"] for v in client._open_orders.values()}

        # ── Leer posiciones locales ────────────────────────────────────────────
        try:
            with open(POSICIONES_FILE) as f:
                pos_local = json.load(f)
        except:
            pos_local = {}

        # ── Construir nueva versión — IB manda ────────────────────────────────
        pos_nueva = {}
        for symbol, pos_ib in posiciones_ib.items():
            if symbol in pos_local and pos_local[symbol].get("confirmado_ib"):
                # Mantener datos locales (SL/TP/tesis) + actualizar precio IB
                pos_nueva[symbol] = {
                    **pos_local[symbol],
                    "cantidad":       abs(pos_ib["position"]),
                    "precio_entrada": pos_ib["avgCost"],
                }
            # No agregar posiciones de IB que no están en local
            # (pueden ser posiciones manuales — no interfiramos)

        # ── Reconciliar posiciones locales vs IB ─────────────────────────────
        for symbol in list(pos_local.keys()):
            if symbol in pos_nueva:
                continue  # ya procesado en el loop anterior

            if symbol in posiciones_ib:
                # Está en IB pero no tenía confirmado_ib=True → mantener tal cual
                pos_nueva[symbol] = pos_local[symbol]
            else:
                # No aparece en posiciones filled de IB
                pos_conf = pos_local[symbol].get("confirmado_ib", False)
                tiene_orden_abierta = symbol in open_order_symbols
                if pos_conf and tiene_orden_abierta:
                    # Orden LMT Submitted aún no ejecutada — es real, no fantasma
                    print(f"  Manteniendo posición pendiente (orden abierta en IB): {symbol}")
                    pos_nueva[symbol] = pos_local[symbol]
                else:
                    # No confirmada por IB ni tiene orden activa → fantasma
                    print(f"  Eliminando posición fantasma: {symbol}")

        with open(POSICIONES_FILE, "w") as f:
            json.dump(pos_nueva, f, indent=2)

        return pos_nueva

    except Exception as e:
        print(f"  Error en sincronizar_desde_ib: {e}")
        return {}
    finally:
        try:
            client.disconnect()
        except:
            pass

# ── CERRAR POSICIÓN EN IB ─────────────────────────────────────────────────────
def cerrar_posicion_ib(ib_ticker, tipo, cantidad, accion_original):
    """
    Cierra una posición en IB y espera confirmación.
    """
    if not IB_DISPONIBLE:
        return {"exito": False, "error": "ibapi no disponible"}

    accion_cierre = "BUY" if accion_original == "VENDER" else "SELL"
    precio        = get_precio_actual(ib_ticker, tipo)

    if not precio:
        return {"exito": False, "error": "No se pudo obtener precio de cierre"}

    client = IBEjecutor()
    if not client.conectar():
        return {"exito": False, "error": "No conecta con TWS"}

    try:
        time.sleep(0.3)
        contrato = crear_contrato(ib_ticker, tipo)

        # Precio límite para cierre — respetar tick size del contrato
        TICK = {"Crypto": 1.0, "Futuro": 0.01, "Acción Chile": 1.0}
        tick = TICK.get(tipo, 0.01)
        def _rt(p, t):
            import decimal
            d_p = decimal.Decimal(str(round(p, 6)))
            d_t = decimal.Decimal(str(t))
            return float((d_p / d_t).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP) * d_t)

        if accion_cierre == "BUY":
            precio_lmt = _rt(precio * 1.002, tick)
        else:
            precio_lmt = _rt(precio * 0.998, tick)

        orden = Order()
        orden.action        = accion_cierre
        orden.orderType     = "LMT"
        orden.lmtPrice      = precio_lmt
        orden.totalQuantity = cantidad
        orden.transmit      = True
        orden.eTradeOnly    = False
        orden.firmQuoteOnly = False
        orden.tif           = "GTC"

        orden_id = client._next_id()
        client.placeOrder(orden_id, contrato, orden)

        print(f"  Cierre enviado: {accion_cierre} {cantidad} {ib_ticker} @ {precio_lmt:.4f}")

        # Esperar confirmación
        t0 = time.time()
        while time.time() - t0 < 30:
            status = client._ordenes.get(orden_id, "")
            if status in ("Filled", "Submitted", "PreSubmitted"):
                fill  = client._filled.get(orden_id, {})
                return {
                    "exito":      True,
                    "orden_id":   orden_id,
                    "precio_fill": fill.get("avgPrice", precio_lmt),
                    "status":     status,
                }
            elif status in ("Cancelled", "Inactive"):
                return {"exito": False, "error": f"Orden cancelada: {status}"}
            time.sleep(0.5)

        return {"exito": False, "error": "Timeout esperando confirmación de cierre"}

    except Exception as e:
        return {"exito": False, "error": str(e)}
    finally:
        try:
            client.disconnect()
        except:
            pass

# ── FUNCIÓN PRINCIPAL (compatibilidad con código existente) ───────────────────
def ejecutar_señales(recomendaciones, modo_test=False):
    """
    Ejecuta lista de señales. Compatible con código existente.
    Usa el nuevo flujo: IB primero, local después.
    """
    ordenes_enviadas = []
    errores          = []

    for señal in recomendaciones:
        ib_ticker = señal.get("ib_ticker", "")
        accion    = señal.get("accion", "")

        print(f"  Ejecutando: {accion} {ib_ticker}")

        resultado = ejecutar_orden(señal, modo_test=modo_test)

        if resultado.get("exito"):
            if not modo_test:
                registrar_posicion(señal, resultado)
            ordenes_enviadas.append({
                "ticker":  ib_ticker,
                "accion":  accion,
                "precio":  resultado.get("precio_fill", 0),
                "cantidad": resultado.get("cantidad", 0),
                "orden_id": resultado.get("orden_id"),
            })
            print(f"  ✅ {accion} {ib_ticker} — confirmado por IB")
        else:
            error = resultado.get("error", "Error desconocido")
            errores.append({"ticker": ib_ticker, "error": error})
            print(f"  ❌ {accion} {ib_ticker} — {error}")

        time.sleep(0.5)

    return {
        "ordenes_enviadas": ordenes_enviadas,
        "errores":          errores,
        "total":            len(ordenes_enviadas),
    }

def get_posiciones_abiertas():
    """Obtiene posiciones desde IB (fuente de verdad)"""
    return sincronizar_desde_ib()

def get_resumen_cuenta():
    """Resumen de cuenta IB"""
    if not IB_DISPONIBLE:
        return {}

    client = IBEjecutor()
    if not client.conectar():
        return {}

    try:
        time.sleep(0.3)
        client.reqAccountSummary(1, "All", "NetLiquidation,TotalCashValue,UnrealizedPnL")
        client._done_acct.wait(timeout=8)
        return {"capital": client._capital}
    except:
        return {}
    finally:
        try:
            client.disconnect()
        except:
            pass
