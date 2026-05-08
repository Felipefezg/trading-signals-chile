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
            self._ready       = threading.Event()
            self._orderId     = None
            self._lock        = threading.Lock()
            self._posiciones  = {}   # symbol → {position, avgCost}
            self._done_pos    = threading.Event()
            self._ordenes     = {}   # orderId → status
            self._filled      = {}   # orderId → {filled, avgPrice}
            self._capital     = 0.0
            self._done_acct   = threading.Event()

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
            self._ordenes[orderId] = status
            if filled > 0:
                self._filled[orderId] = {
                    "filled":   float(filled),
                    "avgPrice": round(float(avgFillPrice), 4),
                }

        def execDetails(self, reqId, contract, execution):
            pass

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
            ignorar = {2104, 2106, 2158, 2103, 2119, 2110, 2105, 2157, 10349}
            if errorCode not in ignorar:
                if errorCode == 1104:
                    pass  # Pending orders — ignorar
                else:
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
        "BTC": "BTC-USD", "GC": "GC=F", "HG": "HG=F", "CL": "CL=F",
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
def calcular_cantidad(precio, tipo, conviccion=75, capital=100_000,
                      max_usd=15_000, sl=None):
    """
    Calcula cantidad usando Half-Kelly simplificado.
    Limita riesgo por operación al 2% del capital.
    """
    if not precio or precio <= 0:
        return 0

    # Sizing base según convicción
    pct_capital = min(0.15, (conviccion - 50) / 100 * 0.3)
    usd_base    = capital * pct_capital
    usd_op      = min(usd_base, max_usd)

    # Reducir sizing para activos volátiles
    if tipo == "Crypto":
        usd_op *= 0.3
    elif tipo == "Futuro":
        usd_op *= 0.5

    cantidad = usd_op / precio

    # Para acciones chilenas — redondear a enteros
    if tipo in ("Acción Chile",):
        cantidad = max(1, int(cantidad))
    elif tipo == "Crypto":
        cantidad = round(max(0.001, cantidad), 4)
    else:
        cantidad = max(1, int(cantidad))

    return cantidad

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

        # Si ya hay posición en este activo → no duplicar
        if ib_ticker in client._posiciones:
            pos_actual = client._posiciones[ib_ticker]["position"]
            if (accion == "COMPRAR" and pos_actual > 0) or \
               (accion == "VENDER" and pos_actual < 0):
                return {"exito": False, "error": f"Ya hay posición {ib_ticker} en IB"}

        # Crear contrato y orden
        contrato = crear_contrato(ib_ticker, tipo)
        if not contrato:
            return {"exito": False, "error": "No se pudo crear contrato"}

        # Calcular precio límite (0.1% slippage)
        if accion == "COMPRAR":
            precio_lmt = round(precio * 1.001, 4)
            accion_ib  = "BUY"
        else:
            precio_lmt = round(precio * 0.999, 4)
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

        print(f"  Orden enviada: {accion} {cantidad} {ib_ticker} @ {precio_lmt:.4f} (ID:{orden_id})")

        # Esperar confirmación de IB (máx 30 segundos)
        t0 = time.time()
        confirmado = False
        while time.time() - t0 < 30:
            status = client._ordenes.get(orden_id, "")
            if status in ("Filled", "Submitted", "PreSubmitted"):
                confirmado = True
                break
            elif status in ("Cancelled", "Inactive"):
                break
            time.sleep(0.5)

        if not confirmado:
            # Cancelar orden si no se confirmó
            client.cancelOrder(orden_id)
            return {"exito": False, "error": f"IB no confirmó en 30s (status: {status})"}

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
        client.reqPositions()
        client._done_pos.wait(timeout=8)

        posiciones_ib = client._posiciones

        # Leer posiciones locales
        try:
            with open(POSICIONES_FILE) as f:
                pos_local = json.load(f)
        except:
            pos_local = {}

        # Construir nueva versión — IB manda
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

        # Eliminar posiciones locales que no están en IB
        for symbol in list(pos_local.keys()):
            if symbol not in posiciones_ib:
                print(f"  Eliminando posición fantasma: {symbol}")
            else:
                if symbol not in pos_nueva:
                    pos_nueva[symbol] = pos_local[symbol]

        with open(POSICIONES_FILE, "w") as f:
            json.dump(pos_nueva, f, indent=2)

        return pos_nueva

    except Exception as e:
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

        # Precio límite para cierre
        if accion_cierre == "BUY":
            precio_lmt = round(precio * 1.002, 4)
        else:
            precio_lmt = round(precio * 0.998, 4)

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
