"""
Order Flow IB — Level 2 Market Depth
Analiza el libro de órdenes en tiempo real para todos los activos.

Solo disponible en horario de mercado (lunes-viernes 9:30-16:00 ET).

Métricas calculadas:
- Bid/Ask imbalance — presión compradora vs vendedora
- Large orders — órdenes institucionales grandes
- Spread — liquidez del activo
- Profundidad — cuántas órdenes hay en el libro
"""

import threading
import time
from datetime import datetime
import pytz

IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 70

def es_horario_mercado():
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    from datetime import time as dtime
    return dtime(9, 30) <= now.time() <= dtime(16, 0)

IB_DISPONIBLE = False
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    IB_DISPONIBLE = True
except:
    pass

if IB_DISPONIBLE:
    class OrderFlowClient(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._ready  = threading.Event()
            self._books  = {}  # reqId -> {"bid": {}, "ask": {}, "symbol": ""}
            self._lock   = threading.Lock()

        def nextValidId(self, orderId):
            self._ready.set()

        def updateMktDepth(self, reqId, position, operation, side, price, size):
            """
            operation: 0=insert, 1=update, 2=delete
            side: 0=ask, 1=bid
            """
            if price <= 0:
                return
            with self._lock:
                if reqId not in self._books:
                    self._books[reqId] = {"bid": {}, "ask": {}}
                lado = "bid" if side == 1 else "ask"
                if operation == 2:
                    self._books[reqId][lado].pop(position, None)
                else:
                    self._books[reqId][lado][position] = {
                        "precio": round(price, 4),
                        "size":   int(size),
                    }

        def error(self, reqId, errorCode, errorString, *args):
            if errorCode not in (2104,2106,2158,2103,2119,2110,2105,2157):
                pass  # Silenciar errores no críticos

        def get_book(self, reqId):
            with self._lock:
                return dict(self._books.get(reqId, {"bid": {}, "ask": {}}))

        def conectar(self, timeout=8):
            try:
                self.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
                t = threading.Thread(target=self.run, daemon=True)
                t.start()
                return self._ready.wait(timeout=timeout)
            except:
                return False

# ── ANÁLISIS ORDER FLOW ───────────────────────────────────────────────────────
def analizar_book(book, symbol, precio_actual=None):
    """
    Analiza el libro de órdenes y calcula métricas de order flow.
    """
    bids = book.get("bid", {})
    asks = book.get("ask", {})

    if not bids and not asks:
        return None

    # Volumen total bid/ask
    vol_bid = sum(d["size"] for d in bids.values())
    vol_ask = sum(d["size"] for d in asks.values())
    vol_total = vol_bid + vol_ask

    if vol_total == 0:
        return None

    # Imbalance — % de órdenes compradoras
    imbalance = vol_bid / vol_total * 100

    # Mejor bid y ask
    mejor_bid = max((d["precio"] for d in bids.values()), default=0)
    mejor_ask = min((d["precio"] for d in asks.values()), default=0)
    spread     = round(mejor_ask - mejor_bid, 4) if mejor_bid and mejor_ask else 0
    spread_pct = round(spread / mejor_bid * 100, 4) if mejor_bid > 0 else 0

    # Órdenes grandes (institucionales) — top 10% por tamaño
    todos_sizes = [d["size"] for d in list(bids.values()) + list(asks.values())]
    if todos_sizes:
        umbral_grande = sorted(todos_sizes)[-max(1, len(todos_sizes)//5)]
        ordenes_grandes_bid = sum(1 for d in bids.values() if d["size"] >= umbral_grande)
        ordenes_grandes_ask = sum(1 for d in asks.values() if d["size"] >= umbral_grande)
    else:
        ordenes_grandes_bid = ordenes_grandes_ask = 0

    # Señal de dirección
    if imbalance > 65:
        direccion = "ALZA"
        señal     = f"Presión compradora fuerte ({imbalance:.1f}% bid)"
        score     = 3 if imbalance > 75 else 2
    elif imbalance < 35:
        direccion = "BAJA"
        señal     = f"Presión vendedora fuerte ({100-imbalance:.1f}% ask)"
        score     = 3 if imbalance < 25 else 2
    elif imbalance > 55:
        direccion = "ALZA"
        señal     = f"Leve presión compradora ({imbalance:.1f}% bid)"
        score     = 1
    elif imbalance < 45:
        direccion = "BAJA"
        señal     = f"Leve presión vendedora ({100-imbalance:.1f}% ask)"
        score     = 1
    else:
        direccion = "NEUTRO"
        señal     = f"Balance neutro ({imbalance:.1f}% bid)"
        score     = 0

    # Bonus por órdenes institucionales
    if ordenes_grandes_bid > ordenes_grandes_ask and score > 0:
        score += 1
        señal += " + órdenes institucionales compradoras"
    elif ordenes_grandes_ask > ordenes_grandes_bid and score > 0:
        score += 1
        señal += " + órdenes institucionales vendedoras"

    return {
        "symbol":       symbol,
        "imbalance":    round(imbalance, 1),
        "vol_bid":      vol_bid,
        "vol_ask":      vol_ask,
        "mejor_bid":    mejor_bid,
        "mejor_ask":    mejor_ask,
        "spread":       spread,
        "spread_pct":   spread_pct,
        "n_levels_bid": len(bids),
        "n_levels_ask": len(asks),
        "ordenes_grandes_bid": ordenes_grandes_bid,
        "ordenes_grandes_ask": ordenes_grandes_ask,
        "direccion":    direccion,
        "señal":        señal,
        "score":        score,
        "timestamp":    datetime.now().isoformat(),
    }

def get_order_flow(max_activos=15, timeout_datos=8):
    """
    Obtiene order flow para todos los activos del universo maestro.
    Solo disponible en horario de mercado.
    """
    if not es_horario_mercado():
        return {}

    if not IB_DISPONIBLE:
        return {}

    # Importar universo maestro
    from engine.universo import get_tickers_at, UNIVERSO_COMPLETO

    # Filtrar activos operables en IB con Level 2
    # Level 2 disponible para: STK (NYSE, NASDAQ), ETF, algunos Futuros
    activos_l2 = {
        yf: info for yf, info in get_tickers_at().items()
        if info.get("tipo") in ("Acción Chile", "Acción USA/Chile", "ETF")
    }

    # Limitar a los más líquidos (mayor peso IPSA o internacionales)
    activos_l2 = dict(list(activos_l2.items())[:max_activos])

    if not activos_l2:
        return {}

    client = OrderFlowClient()
    if not client.conectar():
        return {}

    try:
        time.sleep(0.5)
        req_map = {}

        for i, (yf_ticker, info) in enumerate(activos_l2.items()):
            req_id = i + 100
            ib_ticker = info.get("ib", yf_ticker.replace(".SN",""))
            tipo      = info.get("tipo", "ETF")

            c = Contract()
            c.symbol   = ib_ticker
            c.currency = "USD"

            if tipo == "Acción Chile":
                c.secType  = "STK"
                c.exchange = "SN"
                c.currency = "CLP"
            else:
                c.secType  = "STK"
                c.exchange = "SMART"

            try:
                client.reqMktDepth(req_id, c, 5, False, [])
                req_map[req_id] = {"symbol": info["nombre"], "yf": yf_ticker, "info": info}
                time.sleep(0.1)
            except:
                pass

        # Esperar datos
        time.sleep(timeout_datos)

        # Procesar resultados
        resultados = {}
        for req_id, meta in req_map.items():
            book = client.get_book(req_id)
            analisis = analizar_book(book, meta["symbol"])
            if analisis:
                analisis["yf_ticker"]    = meta["yf"]
                analisis["activo_motor"] = meta["yf"]
                resultados[meta["yf"]]   = analisis

        return resultados

    except Exception as e:
        return {}
    finally:
        try:
            client.disconnect()
        except:
            pass

def get_señales_order_flow(min_score=2):
    """
    Retorna señales del order flow compatibles con el motor.
    """
    datos = get_order_flow()
    señales = []

    for yf_ticker, d in datos.items():
        if d.get("score", 0) >= min_score:
            señales.append({
                "activo":      d["activo_motor"],
                "fuente":      "Order Flow",
                "score":       d["score"],
                "direccion":   d["direccion"],
                "imbalance":   d["imbalance"],
                "descripcion": f"Order Flow {d['symbol']}: {d['señal']}",
            })

    return sorted(señales, key=lambda x: x["score"], reverse=True)

def get_resumen_order_flow():
    """Resumen para el dashboard"""
    if not es_horario_mercado():
        return {
            "disponible": False,
            "razon":      "Order flow solo disponible en horario de mercado",
            "datos":      {},
        }

    datos  = get_order_flow()
    señales = get_señales_order_flow()

    return {
        "disponible": len(datos) > 0,
        "total":      len(datos),
        "señales":    len(señales),
        "datos":      datos,
        "señales_detalle": señales,
        "timestamp":  datetime.now().isoformat(),
    }

if __name__ == "__main__":
    print("=== ORDER FLOW IB ===\n")
    if not es_horario_mercado():
        print("Mercado cerrado — Order Flow solo disponible en horario de trading")
        print("Lunes-viernes 9:30-16:00 ET")
        print("\nMódulo listo — se activará automáticamente mañana al abrir el mercado")
    else:
        resumen = get_resumen_order_flow()
        print(f"Activos con datos: {resumen['total']}")
        print(f"Señales generadas: {resumen['señales']}")
        for s in resumen["señales_detalle"]:
            print(f"  [{s['direccion']}] {s['activo']} — {s['descripcion'][:70]}")
