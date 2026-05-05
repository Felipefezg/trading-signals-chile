"""
Reduce la posición SQM en IB a exactamente 159 acciones.
Vende el excedente via orden LMT con 0.2% slippage.

Ejecutar:
  cd ~/trading_signals && source venv/bin/activate && python3 reducir_sqm.py
"""
import sys, time, decimal
sys.path.insert(0, ".")

try:
    from ibapi.client  import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order    import Order
    import threading
except ImportError:
    print("❌ ibapi no disponible")
    sys.exit(1)

TARGET_SHARES = 159   # cantidad que queremos conservar
IB_HOST       = "127.0.0.1"
IB_PORT       = 7497
CLIENT_ID     = 99    # ID único para este script

class ReducirSQM(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self._ready    = threading.Event()
        self._orderId  = None
        self._lock     = threading.Lock()
        self._pos      = {}
        self._done_pos = threading.Event()
        self._ordenes  = {}

    def nextValidId(self, orderId):
        with self._lock:
            self._orderId = orderId
        self._ready.set()

    def _next_id(self):
        with self._lock:
            oid = self._orderId
            self._orderId += 1
        return oid

    def position(self, account, contract, position, avgCost):
        if position != 0:
            self._pos[contract.symbol] = {
                "qty":     float(position),
                "avgCost": float(avgCost),
            }

    def positionEnd(self):
        self._done_pos.set()

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, *args):
        self._ordenes[orderId] = status
        if filled > 0:
            print(f"  Fill parcial: {filled} acciones @ {avgFillPrice:.2f}")

    def error(self, reqId, errorCode, errorString, *args):
        ignorar = {2104, 2106, 2158, 2103, 2119, 2110, 2105, 2157, 10349, 1104}
        if errorCode not in ignorar:
            print(f"  IB Error [{errorCode}]: {errorString[:100]}")

    def conectar(self):
        self.connect(IB_HOST, IB_PORT, CLIENT_ID)
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return self._ready.wait(timeout=8)


def _rt(p, t=0.01):
    """Redondea precio al tick correcto."""
    d_p = decimal.Decimal(str(round(p, 6)))
    d_t = decimal.Decimal(str(t))
    return float((d_p / d_t).quantize(decimal.Decimal("1"),
                  rounding=decimal.ROUND_HALF_UP) * d_t)


client = ReducirSQM()
if not client.conectar():
    print("❌ No conecta con TWS — verifica que esté abierto en puerto 7497")
    sys.exit(1)

time.sleep(0.5)
client.reqPositions()
client._done_pos.wait(timeout=8)

sqm = client._pos.get("SQM")
if not sqm:
    print("✅ No hay posición SQM en IB — nada que hacer")
    client.disconnect()
    sys.exit(0)

qty_actual = int(sqm["qty"])
excedente  = qty_actual - TARGET_SHARES

print(f"Posición SQM en IB: {qty_actual} acciones")
print(f"Objetivo:           {TARGET_SHARES} acciones")
print(f"A vender:           {excedente} acciones")

if excedente <= 0:
    print(f"✅ Ya tienes {qty_actual} acciones — nada que vender")
    client.disconnect()
    sys.exit(0)

# Obtener precio actual via yfinance
try:
    import yfinance as yf
    h = yf.Ticker("SQM").history(period="2d")
    precio = float(h["Close"].iloc[-1]) if not h.empty else sqm["avgCost"]
except:
    precio = sqm["avgCost"]

precio_lmt = _rt(precio * 0.998)  # 0.2% bajo mercado para fill rápido
print(f"Precio referencia:  ${precio:.2f}")
print(f"Precio límite SELL: ${precio_lmt:.2f}")
print()
confirm = input(f"¿Confirmas vender {excedente} SQM @ LMT {precio_lmt:.2f}? (s/n): ").strip().lower()
if confirm != "s":
    print("Cancelado por el usuario.")
    client.disconnect()
    sys.exit(0)

# Construir orden
contrato           = Contract()
contrato.symbol    = "SQM"
contrato.secType   = "STK"
contrato.exchange  = "SMART"
contrato.currency  = "USD"

orden               = Order()
orden.action        = "SELL"
orden.orderType     = "LMT"
orden.lmtPrice      = precio_lmt
orden.totalQuantity = excedente
orden.transmit      = True
orden.eTradeOnly    = False
orden.firmQuoteOnly = False
orden.tif           = "GTC"

orden_id = client._next_id()
client.placeOrder(orden_id, contrato, orden)
print(f"\n📤 Orden enviada (ID:{orden_id}): SELL {excedente} SQM @ LMT {precio_lmt:.2f}")

# Esperar confirmación 20s
t0 = time.time()
while time.time() - t0 < 20:
    st = client._ordenes.get(orden_id, "")
    if st in {"Submitted", "PreSubmitted", "Filled"}:
        print(f"✅ Orden confirmada por IB: {st}")
        break
    elif st in {"Cancelled", "Inactive"}:
        print(f"❌ Orden rechazada: {st}")
        break
    time.sleep(0.5)
else:
    print("⚠️  Sin respuesta de IB en 20s — verifica en TWS (la orden puede estar activa)")

time.sleep(1)
client.disconnect()
print("\nListo. Verifica en TWS que la posición quedó en 159 acciones.")
