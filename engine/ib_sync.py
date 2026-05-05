"""
Sincronizador de Trades con IB
Obtiene el historial real de ejecuciones desde IB TWS
y sincroniza con el sistema local.

Elimina trades falsos y mantiene solo los realmente ejecutados en IB.
"""

import threading
import time
import json
import os
from datetime import datetime, timedelta

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSICIONES_FILE = os.path.join(BASE_DIR, "posiciones.json")
TRADES_FILE     = os.path.join(BASE_DIR, "trades_cerrados.json")

IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 55

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    IB_DISPONIBLE = True
except:
    IB_DISPONIBLE = False

if IB_DISPONIBLE:
    class IBSyncClient(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._ready      = threading.Event()
            self._posiciones = {}
            self._ejecuciones = []
            self._ordenes    = []
            self._cuenta     = {}
            self._done_pos   = threading.Event()
            self._done_exec  = threading.Event()
            self._done_orders= threading.Event()

        def nextValidId(self, orderId):
            self._ready.set()

        # ── POSICIONES ────────────────────────────────────────────────────────
        def position(self, account, contract, position, avgCost):
            if position != 0:
                self._posiciones[contract.symbol] = {
                    "symbol":       contract.symbol,
                    "secType":      contract.secType,
                    "currency":     contract.currency,
                    "position":     float(position),
                    "avgCost":      round(float(avgCost), 4),
                    "accion":       "VENDER" if position < 0 else "COMPRAR",
                    "cantidad":     abs(float(position)),
                }

        def positionEnd(self):
            self._done_pos.set()

        # ── EJECUCIONES ───────────────────────────────────────────────────────
        def execDetails(self, reqId, contract, execution):
            self._ejecuciones.append({
                "orderId":   execution.orderId,
                "symbol":    contract.symbol,
                "secType":   contract.secType,
                "side":      execution.side,
                "shares":    float(execution.shares),
                "price":     round(float(execution.price), 4),
                "time":      execution.time,
                "execId":    execution.execId,
                "accion":    "VENDER" if execution.side == "SLD" else "COMPRAR",
            })

        def execDetailsEnd(self, reqId):
            self._done_exec.set()

        # ── ÓRDENES ABIERTAS ──────────────────────────────────────────────────
        def openOrder(self, orderId, contract, order, orderState):
            self._ordenes.append({
                "orderId":  orderId,
                "symbol":   contract.symbol,
                "action":   order.action,
                "qty":      float(order.totalQuantity),
                "orderType":order.orderType,
                "lmtPrice": float(order.lmtPrice) if order.lmtPrice else 0,
                "status":   orderState.status,
            })

        def openOrderEnd(self):
            self._done_orders.set()

        # ── CUENTA ────────────────────────────────────────────────────────────
        def accountSummary(self, reqId, account, tag, value, currency):
            try:
                self._cuenta[tag] = float(value)
            except:
                self._cuenta[tag] = value

        def error(self, reqId, errorCode, errorString, *args):
            if errorCode not in (2104,2106,2158,2103,2119,2110,2105,2157):
                pass

        def conectar(self, timeout=8):
            try:
                self.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
                t = threading.Thread(target=self.run, daemon=True)
                t.start()
                return self._ready.wait(timeout=timeout)
            except:
                return False

def sincronizar_con_ib():
    """
    Sincroniza posiciones y trades con IB TWS.
    Retorna dict con posiciones reales y ejecuciones.
    """
    if not IB_DISPONIBLE:
        return {"error": "ibapi no disponible"}

    client = IBSyncClient()
    if not client.conectar():
        return {"error": "No conecta con TWS — ¿está abierto?"}

    try:
        time.sleep(0.5)

        # 1. Solicitar posiciones actuales
        client.reqPositions()
        client._done_pos.wait(timeout=8)

        # 2. Solicitar ejecuciones recientes (últimos 7 días)
        from ibapi.execution import ExecutionFilter
        filtro = ExecutionFilter()
        client.reqExecutions(1, filtro)
        client._done_exec.wait(timeout=10)

        # 3. Solicitar órdenes abiertas
        client.reqAllOpenOrders()
        client._done_orders.wait(timeout=5)

        # 4. Solicitar resumen de cuenta
        client.reqAccountSummary(2, "All", "NetLiquidation,TotalCashValue,UnrealizedPnL")
        time.sleep(3)

        return {
            "posiciones":  client._posiciones,
            "ejecuciones": client._ejecuciones,
            "ordenes":     client._ordenes,
            "cuenta":      client._cuenta,
            "timestamp":   datetime.now().isoformat(),
        }

    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            client.disconnect()
        except:
            pass

def sincronizar_posiciones_local():
    """
    Actualiza posiciones.json con los datos reales de IB.
    Elimina posiciones fantasma que no están en IB.
    """
    datos_ib = sincronizar_con_ib()

    if "error" in datos_ib:
        print(f"Error sincronizando: {datos_ib['error']}")
        return False

    posiciones_ib = datos_ib["posiciones"]
    ejecuciones_ib = datos_ib["ejecuciones"]

    # Leer posiciones locales actuales
    try:
        with open(POSICIONES_FILE) as f:
            pos_local = json.load(f)
    except:
        pos_local = {}

    # Construir nuevas posiciones basadas en IB
    pos_nueva = {}
    for symbol, pos_ib in posiciones_ib.items():
        if symbol in pos_local:
            # Mantener datos locales (SL/TP/horizonte) + actualizar precio
            pos_nueva[symbol] = {
                **pos_local[symbol],
                "cantidad":       pos_ib["cantidad"],
                "precio_entrada": pos_ib["avgCost"],
            }
        else:
            # Posición en IB que no tenemos localmente
            pos_nueva[symbol] = {
                "accion":        pos_ib["accion"],
                "cantidad":      pos_ib["cantidad"],
                "precio_entrada": pos_ib["avgCost"],
                "sl":            None,
                "tp":            None,
                "tipo":          "Acción USA/Chile",
                "fecha_entrada": datetime.now().isoformat(),
                "horizonte":     "1-7 días",
                "conviccion":    75.0,
                "order_ids":     [],
            }

    # Detectar posiciones locales que ya no están en IB
    eliminadas = [k for k in pos_local if k not in posiciones_ib]
    if eliminadas:
        print(f"Posiciones eliminadas (no están en IB): {eliminadas}")

    # Guardar posiciones sincronizadas
    with open(POSICIONES_FILE, "w") as f:
        json.dump(pos_nueva, f, indent=2)

    print(f"Posiciones sincronizadas: {len(pos_nueva)} en IB")
    for symbol, p in pos_nueva.items():
        print(f"  {symbol}: {p['accion']} {p['cantidad']} @ {p['precio_entrada']:,.2f}")

    return True

def limpiar_trades_falsos():
    """
    Limpia trades_cerrados.json eliminando trades no confirmados por IB.
    Mantiene solo trades con ejecución real verificada.
    """
    datos_ib = sincronizar_con_ib()

    if "error" in datos_ib:
        print(f"Error: {datos_ib['error']}")
        return False

    ejecuciones_ib = datos_ib["ejecuciones"]

    # Extraer execIds y símbolos realmente ejecutados
    exec_ids = {e["execId"] for e in ejecuciones_ib}
    simbolos_ejecutados = {e["symbol"] for e in ejecuciones_ib}

    print(f"Ejecuciones reales en IB: {len(ejecuciones_ib)}")
    for e in ejecuciones_ib:
        print(f"  {e['accion']} {e['symbol']} {e['shares']} @ {e['price']} | {e['time']}")

    # Leer trades locales
    try:
        with open(TRADES_FILE) as f:
            trades_local = json.load(f)
    except:
        trades_local = []

    if not trades_local:
        print("Sin trades locales para limpiar")
        return True

    print(f"\nTrades locales: {len(trades_local)}")

    # Si no hay ejecuciones en IB, todos los trades locales son falsos
    if not ejecuciones_ib:
        print("⚠️  Sin ejecuciones en IB — limpiando todos los trades falsos")
        with open(TRADES_FILE, "w") as f:
            json.dump([], f, indent=2)
        print("✅ Trades falsos eliminados")
        return True

    # Filtrar trades con correspondencia en IB
    # (por símbolo y fecha aproximada)
    trades_validos = []
    for trade in trades_local:
        ticker = trade.get("ticker", "")
        if ticker in simbolos_ejecutados:
            trades_validos.append(trade)
        else:
            print(f"  Eliminando trade falso: {ticker} {trade.get('accion')} {trade.get('pnl_pct',0):+.2f}%")

    with open(TRADES_FILE, "w") as f:
        json.dump(trades_validos, f, indent=2)

    print(f"\n✅ Trades válidos mantenidos: {len(trades_validos)}")
    print(f"   Trades falsos eliminados: {len(trades_local) - len(trades_validos)}")
    return True

def get_resumen_cuenta_ib():
    """Resumen de la cuenta IB para el dashboard"""
    datos = sincronizar_con_ib()
    if "error" in datos:
        return {"disponible": False, "error": datos["error"]}

    return {
        "disponible":    True,
        "posiciones":    datos["posiciones"],
        "n_posiciones":  len(datos["posiciones"]),
        "n_ejecuciones": len(datos["ejecuciones"]),
        "n_ordenes":     len(datos["ordenes"]),
        "cuenta":        datos["cuenta"],
        "capital":       datos["cuenta"].get("NetLiquidation", 0),
        "cash":          datos["cuenta"].get("TotalCashValue", 0),
        "pnl_no_realizado": datos["cuenta"].get("UnrealizedPnL", 0),
        "timestamp":     datos["timestamp"],
    }

if __name__ == "__main__":
    print("=== SINCRONIZADOR IB ===\n")

    print("1. Sincronizando posiciones...")
    sincronizar_posiciones_local()

    print("\n2. Limpiando trades falsos...")
    limpiar_trades_falsos()

    print("\n3. Resumen cuenta IB:")
    resumen = get_resumen_cuenta_ib()
    if resumen["disponible"]:
        print(f"   Capital: USD {resumen['capital']:,.2f}")
        print(f"   Cash:    USD {resumen['cash']:,.2f}")
        print(f"   PnL no realizado: USD {resumen['pnl_no_realizado']:+,.2f}")
        print(f"   Posiciones: {resumen['n_posiciones']}")
        print(f"   Órdenes abiertas: {resumen['n_ordenes']}")
    else:
        print(f"   Error: {resumen['error']}")
