#!/usr/bin/env python3
"""
Cierre de emergencia — todas las posiciones abiertas en IB.

Uso:
    python cerrar_todas_posiciones.py

Lee posiciones reales desde IB (no desde posiciones.json),
envía orden MKT de cierre para cada una y espera confirmación.
"""

import sys
import os
import time
import json
import threading
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 20   # ID exclusivo para cierre emergencia

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IB_OK = True
except ImportError:
    print("ERROR: ibapi no está instalado.")
    sys.exit(1)


class CierreCliente(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self._ready       = threading.Event()
        self._posiciones  = {}   # symbol → {position, avgCost, secType, exchange, currency}
        self._done_pos    = threading.Event()
        self._next_id_val = None
        self._filled      = {}
        self._orders_done = threading.Event()

    def nextValidId(self, orderId):
        self._next_id_val = orderId
        self._ready.set()

    def position(self, account, contract, position, avgCost):
        if abs(position) > 0:
            self._posiciones[contract.symbol] = {
                "position":  position,
                "avgCost":   avgCost,
                "secType":   contract.secType,
                "exchange":  contract.exchange,
                "currency":  contract.currency,
                "lastTrade": getattr(contract, "lastTradeDateOrContractMonth", ""),
            }

    def positionEnd(self):
        self._done_pos.set()

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, *args):
        if status in ("Filled", "Submitted", "PreSubmitted"):
            self._filled[orderId] = {
                "status":   status,
                "filled":   filled,
                "avgPrice": avgFillPrice,
            }
        if status == "Filled":
            self._orders_done.set()

    def error(self, reqId, errorCode, errorString, *args):
        ignorar = {2104, 2105, 2106, 2107, 2108, 2110, 2119, 2157, 2158, 2103, 10349}
        if errorCode not in ignorar:
            print(f"  IB [{errorCode}]: {errorString[:80]}")

    def _next_order_id(self):
        oid = self._next_id_val
        self._next_id_val += 1
        return oid


def _contrato_desde_posicion(symbol, info):
    c = Contract()
    c.symbol = symbol
    sec = info.get("secType", "STK")
    c.secType = sec

    if sec == "FUT":
        c.exchange  = info.get("exchange", "SMART")
        c.currency  = info.get("currency", "USD")
        c.lastTradeDateOrContractMonth = info.get("lastTrade", "")
    elif info.get("currency") == "CLP":
        c.exchange  = "SN"
        c.currency  = "CLP"
    elif sec == "CRYPTO":
        c.exchange  = "PAXOS"
        c.currency  = "USD"
    else:
        c.exchange  = "SMART"
        c.currency  = info.get("currency", "USD")

    return c


def cerrar_todas():
    client = CierreCliente()

    print("Conectando a IB Gateway...")
    client.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)

    t = threading.Thread(target=client.run, daemon=True)
    t.start()

    if not client._ready.wait(timeout=10):
        print("ERROR: No se pudo conectar a IB Gateway en 10s")
        print("  → Verifica que IB Gateway esté abierto en puerto 7497")
        return

    print("Conectado. Obteniendo posiciones reales de IB...")
    client.reqPositions()
    client._done_pos.wait(timeout=8)

    posiciones = client._posiciones
    if not posiciones:
        print("\nNo hay posiciones abiertas en IB. Nada que cerrar.")
        # Limpiar posiciones.json local también
        with open(os.path.join(BASE_DIR, "posiciones.json"), "w") as f:
            json.dump({}, f)
        print("posiciones.json local limpiado.")
        client.disconnect()
        return

    print(f"\nPositions encontradas: {len(posiciones)}")
    print("-" * 60)
    for sym, info in posiciones.items():
        lado = "LARGO" if info["position"] > 0 else "CORTO"
        print(f"  {sym:12} {lado:6}  qty={abs(info['position']):6.1f}  avgCost={info['avgCost']:.4f}")
    print("-" * 60)

    print("\nEnviando órdenes de cierre MKT...\n")
    ordenes = {}

    for symbol, info in posiciones.items():
        pos = info["position"]
        accion_cierre = "SELL" if pos > 0 else "BUY"
        qty = abs(pos)

        contrato = _contrato_desde_posicion(symbol, info)
        orden = Order()
        orden.action        = accion_cierre
        orden.orderType     = "MKT"
        orden.totalQuantity = qty
        orden.transmit      = True
        orden.eTradeOnly    = False
        orden.firmQuoteOnly = False

        oid = client._next_order_id()
        client.placeOrder(oid, contrato, orden)
        ordenes[oid] = symbol
        print(f"  ✓ Orden {accion_cierre} {qty:.0f}x {symbol} enviada (ID={oid})")
        time.sleep(0.3)

    # Esperar hasta 30s para confirmaciones
    print(f"\nEsperando confirmaciones ({len(ordenes)} órdenes)...")
    deadline = time.time() + 30
    while time.time() < deadline:
        filled = [oid for oid, sym in ordenes.items()
                  if client._filled.get(oid, {}).get("status") == "Filled"]
        if len(filled) == len(ordenes):
            break
        time.sleep(1)

    print("\nResultado:")
    print("-" * 60)
    todas_ok = True
    for oid, symbol in ordenes.items():
        fill = client._filled.get(oid, {})
        status = fill.get("status", "Sin respuesta")
        precio = fill.get("avgPrice", 0)
        print(f"  {symbol:12} → {status:15}  precio={precio:.4f}")
        if status != "Filled":
            todas_ok = False

    # Limpiar posiciones.json local
    with open(os.path.join(BASE_DIR, "posiciones.json"), "w") as f:
        json.dump({}, f)
    print("\nposiciones.json local limpiado.")

    if todas_ok:
        print("\n✅ Todas las posiciones cerradas correctamente.")
    else:
        print("\n⚠️  Algunas órdenes no confirmaron en 30s.")
        print("   Verifica en IB Gateway que se hayan ejecutado.")

    client.disconnect()


if __name__ == "__main__":
    cerrar_todas()
