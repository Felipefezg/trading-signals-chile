#!/usr/bin/env python3
"""
Test rápido de conexión IB Gateway.
Verifica puerto, autenticación, cuenta y posiciones.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HOST = "127.0.0.1"
PORT = 7497

print("=" * 50)
print("  TEST IB GATEWAY")
print("=" * 50)

# ── 1. Puerto abierto? ────────────────────────────────────────────────────────
import socket
print("\n1. Verificando puerto 7497...")
try:
    s = socket.create_connection((HOST, PORT), timeout=3)
    s.close()
    print("   ✅ Puerto 7497 abierto — IB Gateway escuchando")
except Exception as e:
    print(f"   ❌ Puerto 7497 cerrado: {e}")
    print("   → Abrir IB Gateway y habilitar API (Edit → Global Config → API)")
    sys.exit(1)

# ── 2. ibapi disponible? ──────────────────────────────────────────────────────
print("\n2. Verificando ibapi...")
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    print("   ✅ ibapi instalada")
except ImportError:
    print("   ❌ ibapi no instalada")
    print("   → cd ~/trading_signals && source venv/bin/activate && pip install ibapi")
    sys.exit(1)

# ── 3. Conexión y cuenta ──────────────────────────────────────────────────────
print("\n3. Conectando a IB Gateway...")

class TestClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self._ready      = threading.Event()
        self._cuenta     = {}
        self._posiciones = {}
        self._done_pos   = threading.Event()
        self._done_acct  = threading.Event()
        self._order_id   = None

    def nextValidId(self, orderId):
        self._order_id = orderId
        self._ready.set()

    def managedAccounts(self, accountsList):
        self._cuenta["accounts"] = accountsList

    def updateAccountValue(self, key, val, currency, accountName):
        if key in ("NetLiquidation", "TotalCashValue", "BuyingPower", "UnrealizedPnL"):
            self._cuenta[key] = f"{float(val):,.2f} {currency}" if currency else val

    def accountDownloadEnd(self, accountName):
        self._done_acct.set()

    def position(self, account, contract, position, avgCost):
        if position != 0:
            self._posiciones[contract.symbol] = {
                "qty":     float(position),
                "avgCost": round(float(avgCost), 4),
                "type":    contract.secType,
            }

    def positionEnd(self):
        self._done_pos.set()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        # Ignorar mensajes informativos
        if errorCode in (2104, 2106, 2158, 2119, 2103, 2105):
            return
        print(f"   ⚠️  IB [{errorCode}]: {errorString}")

client = TestClient()
try:
    client.connect(HOST, PORT, clientId=99)
    t = threading.Thread(target=client.run, daemon=True)
    t.start()

    if not client._ready.wait(timeout=8):
        print("   ❌ Timeout — IB Gateway no responde (API no habilitada?)")
        print("   → Edit → Global Configuration → API → Enable ActiveX and Socket Clients")
        sys.exit(1)

    print(f"   ✅ Conectado — next order ID: {client._order_id}")

except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

# ── 4. Cuenta ─────────────────────────────────────────────────────────────────
print("\n4. Obteniendo datos de cuenta...")
account = client._cuenta.get("accounts", "").split(",")[0]
if account:
    print(f"   ✅ Cuenta: {account}")
    client.reqAccountUpdates(True, account)
    client._done_acct.wait(timeout=6)
    client.reqAccountUpdates(False, account)

    for k in ("NetLiquidation", "TotalCashValue", "BuyingPower", "UnrealizedPnL"):
        v = client._cuenta.get(k, "N/D")
        print(f"   {k:22}: {v}")
else:
    print("   ⚠️  No se obtuvo número de cuenta")

# ── 5. Posiciones ─────────────────────────────────────────────────────────────
print("\n5. Posiciones abiertas en IB...")
client.reqPositions()
client._done_pos.wait(timeout=6)

if client._posiciones:
    for sym, p in client._posiciones.items():
        print(f"   {sym:12} {p['qty']:>8.2f} unidades  @ avg {p['avgCost']:,.4f}  [{p['type']}]")
else:
    print("   (sin posiciones abiertas)")

# ── 6. Coherencia con posiciones.json ─────────────────────────────────────────
print("\n6. Coherencia IB vs posiciones.json local...")
import json
pos_file = os.path.join(os.path.dirname(__file__), "posiciones.json")
try:
    with open(pos_file) as f:
        pos_local = json.load(f)

    ib_syms    = set(client._posiciones.keys())
    local_syms = set(pos_local.keys())

    ok_syms      = ib_syms & local_syms
    solo_ib      = ib_syms - local_syms
    solo_local   = local_syms - ib_syms

    if ok_syms:
        print(f"   ✅ En ambos lados: {', '.join(ok_syms)}")
    if solo_ib:
        print(f"   ⚠️  Solo en IB (no registradas local): {', '.join(solo_ib)}")
    if solo_local:
        print(f"   ⚠️  Solo en local (posiciones fantasma): {', '.join(solo_local)}")
    if not solo_ib and not solo_local:
        print("   ✅ Estado local sincronizado con IB")
except FileNotFoundError:
    print("   ℹ️  posiciones.json no existe (normal si no hay posiciones)")

# ── FIN ───────────────────────────────────────────────────────────────────────
try:
    client.disconnect()
except:
    pass

print("\n" + "=" * 50)
print("  RESULTADO: IB Gateway operativo ✅")
print("=" * 50)
print()
print("El motor puede ejecutar órdenes automáticamente.")
print("Verifica también en el dashboard:")
print("  Tab Ejecución → Motor Automático → Estado conexión IB")
print()
