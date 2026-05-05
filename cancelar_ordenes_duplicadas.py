"""
Script para cancelar órdenes duplicadas de SQM en IB.
Ejecutar UNA SOLA VEZ:
  cd ~/trading_signals && source venv/bin/activate && python3 cancelar_ordenes_duplicadas.py
"""
import sys
import time

sys.path.insert(0, ".")

try:
    from engine.ib_executor import IBEjecutor, IB_DISPONIBLE
except Exception as e:
    print(f"Error importando: {e}")
    sys.exit(1)

if not IB_DISPONIBLE:
    print("ibapi no disponible")
    sys.exit(1)

# IDs duplicados de SQM que deben cancelarse
ORDENES_A_CANCELAR = [51, 55]

client = IBEjecutor()
if not client.conectar():
    print("❌ No conecta con TWS — verifica que TWS esté abierto en puerto 7497")
    sys.exit(1)

time.sleep(0.5)

# Ver qué órdenes hay abiertas
client._done_orders.clear()
client.reqAllOpenOrders()
client._done_orders.wait(timeout=10)

print("Órdenes abiertas en IB:")
if not client._open_orders:
    print("  (ninguna)")
else:
    for oid, info in sorted(client._open_orders.items()):
        print(f"  ID:{oid}  {info.get('action')} {info.get('qty')} {info.get('symbol')}  status={info.get('status')}")

print()
for oid_cancel in ORDENES_A_CANCELAR:
    if oid_cancel in client._open_orders:
        info = client._open_orders[oid_cancel]
        print(f"Cancelando orden {oid_cancel} ({info.get('action')} {info.get('qty')} {info.get('symbol')})...")
        client.cancelOrder(oid_cancel)
        time.sleep(1.5)
        print(f"  ✅ Cancelación enviada")
    else:
        print(f"  ℹ️  Orden {oid_cancel} ya no existe en IB (ejecutada o ya cancelada)")

time.sleep(1)
client.disconnect()
print("\nListo. Ahora puedes eliminar este script.")
