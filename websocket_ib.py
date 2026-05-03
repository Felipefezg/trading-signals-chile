#!/usr/bin/env python3
"""
WebSocket IB — Datos de mercado en tiempo real.
Reemplaza Yahoo Finance durante horario de mercado.
Recibe precios tick a tick directamente desde IB TWS.

Datos disponibles:
- Bid/Ask en tiempo real
- Last price y tamaño
- Volumen acumulado del día
- VWAP
- Imbalance compra/venta

Corre como proceso separado en background.
Comparte datos via archivo JSON para el resto del sistema.
"""

import sys
import os
import json
import time
import threading
import logging
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

RT_DATA_FILE = os.path.join(BASE_DIR, "cache", "rt_data.json")
os.makedirs(os.path.join(BASE_DIR, "cache"), exist_ok=True)

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "websocket_ib.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 60

# Activos a monitorear en tiempo real
ACTIVOS_RT = {
    1:  {"symbol": "SQM",  "secType": "STK", "exchange": "NYSE",  "currency": "USD"},
    2:  {"symbol": "ECH",  "secType": "STK", "exchange": "NYSE",  "currency": "USD"},
    3:  {"symbol": "GLD",  "secType": "STK", "exchange": "NYSE",  "currency": "USD"},
    4:  {"symbol": "SPY",  "secType": "STK", "exchange": "NYSE",  "currency": "USD"},
    5:  {"symbol": "GC",   "secType": "FUT", "exchange": "COMEX", "currency": "USD"},
    6:  {"symbol": "HG",   "secType": "FUT", "exchange": "COMEX", "currency": "USD"},
    7:  {"symbol": "BTC",  "secType": "CRYPTO", "exchange": "PAXOS", "currency": "USD"},
}

IB_DISPONIBLE = False
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    IB_DISPONIBLE = True
except:
    pass

if IB_DISPONIBLE:
    class RTDataClient(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._ready   = threading.Event()
            self._datos   = {}
            self._lock    = threading.Lock()
            self.running  = True

        def nextValidId(self, orderId):
            self._ready.set()
            logging.info("Conectado a IB TWS")

        def tickPrice(self, reqId, tickType, price, attrib):
            if price <= 0:
                return
            mapa = {1: "bid", 2: "ask", 4: "last", 6: "high", 7: "low", 9: "close_prev"}
            if tickType in mapa:
                with self._lock:
                    if reqId not in self._datos:
                        self._datos[reqId] = {"symbol": ACTIVOS_RT.get(reqId, {}).get("symbol", "")}
                    self._datos[reqId][mapa[tickType]] = round(price, 4)
                    self._datos[reqId]["timestamp"] = datetime.now().isoformat()

        def tickSize(self, reqId, tickType, size):
            mapa = {0: "bid_size", 3: "ask_size", 5: "last_size", 8: "volume"}
            if tickType in mapa:
                with self._lock:
                    if reqId not in self._datos:
                        self._datos[reqId] = {"symbol": ACTIVOS_RT.get(reqId, {}).get("symbol", "")}
                    self._datos[reqId][mapa[tickType]] = int(size)

        def tickString(self, reqId, tickType, value):
            if tickType == 58 and value:  # RT Volume con VWAP
                try:
                    partes = value.split(";")
                    if len(partes) >= 5 and partes[4]:
                        with self._lock:
                            if reqId not in self._datos:
                                self._datos[reqId] = {}
                            self._datos[reqId]["vwap"] = round(float(partes[4]), 4)
                except:
                    pass

        def error(self, reqId, errorCode, errorString, *args):
            if errorCode not in (2104, 2106, 2158, 2103, 2119, 2110, 2105, 2157):
                logging.warning(f"IB Error [{errorCode}]: {errorString}")

        def get_snapshot(self):
            with self._lock:
                return dict(self._datos)

        def conectar(self):
            self.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
            t = threading.Thread(target=self.run, daemon=True)
            t.start()
            return self._ready.wait(timeout=10)

else:
    class RTDataClient:
        pass

# ── GUARDAR DATOS RT ──────────────────────────────────────────────────────────
def guardar_rt_data(datos):
    """Guarda datos en tiempo real en archivo JSON compartido"""
    try:
        output = {
            "timestamp": datetime.now().isoformat(),
            "activos":   {}
        }
        for req_id, d in datos.items():
            symbol = d.get("symbol") or ACTIVOS_RT.get(req_id, {}).get("symbol", "")
            if not symbol:
                continue

            bid  = d.get("bid", 0)
            ask  = d.get("ask", 0)
            last = d.get("last", 0)
            vol  = d.get("volume", 0)

            precio = last or ((bid + ask) / 2 if bid and ask else 0)
            spread_pct = ((ask - bid) / bid * 100) if bid > 0 else 0

            # Presión compradora/vendedora
            if bid > 0 and ask > 0 and last > 0 and (ask - bid) > 0:
                presion_pct = (last - bid) / (ask - bid) * 100
                if presion_pct > 70:
                    presion = "COMPRADORES"
                elif presion_pct < 30:
                    presion = "VENDEDORES"
                else:
                    presion = "NEUTRAL"
            else:
                presion = "N/D"
                presion_pct = 50

            output["activos"][symbol] = {
                "precio":      round(precio, 4),
                "bid":         round(bid, 4),
                "ask":         round(ask, 4),
                "spread_pct":  round(spread_pct, 4),
                "volume":      int(vol),
                "vwap":        round(d.get("vwap", 0), 4),
                "presion":     presion,
                "presion_pct": round(presion_pct, 1),
                "high":        round(d.get("high", 0), 4),
                "low":         round(d.get("low", 0), 4),
                "timestamp":   d.get("timestamp", datetime.now().isoformat()),
            }

        with open(RT_DATA_FILE, "w") as f:
            json.dump(output, f, indent=2)

    except Exception as e:
        logging.error(f"Error guardando RT data: {e}")

# ── LEER DATOS RT (para el resto del sistema) ─────────────────────────────────
def get_rt_data(max_age_seconds=30):
    """
    Lee datos en tiempo real guardados por el WebSocket.
    Retorna {} si los datos son muy antiguos o no existen.
    """
    try:
        if not os.path.exists(RT_DATA_FILE):
            return {}
        age = time.time() - os.path.getmtime(RT_DATA_FILE)
        if age > max_age_seconds:
            return {}
        with open(RT_DATA_FILE) as f:
            data = json.load(f)
        return data.get("activos", {})
    except:
        return {}

def get_precio_rt(symbol, fallback_fn=None):
    """
    Obtiene precio en tiempo real desde IB.
    Si no disponible, usa función de fallback (Yahoo Finance).
    """
    datos = get_rt_data()
    if symbol in datos and datos[symbol].get("precio", 0) > 0:
        return datos[symbol]["precio"]
    if fallback_fn:
        return fallback_fn(symbol)
    return None

# ── LOOP PRINCIPAL ────────────────────────────────────────────────────────────
def run_websocket():
    """Loop principal del WebSocket IB"""
    if not IB_DISPONIBLE:
        print("ibapi no disponible — instalar con: pip install ibapi")
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket IB iniciando...")
    print(f"Monitoreando: {[v['symbol'] for v in ACTIVOS_RT.values()]}")

    while True:
        try:
            client = RTDataClient()
            if not client.conectar():
                print("No se pudo conectar a IB TWS — reintentando en 30s...")
                time.sleep(30)
                continue

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Conectado a IB")

            # Suscribir a datos de mercado
            time.sleep(1)
            for req_id, config in ACTIVOS_RT.items():
                c = Contract()
                c.symbol   = config["symbol"]
                c.secType  = config["secType"]
                c.exchange = config["exchange"]
                c.currency = config["currency"]
                if config["secType"] == "FUT":
                    from datetime import timedelta
                    mes = (datetime.now() + timedelta(days=30)).strftime("%Y%m")
                    c.lastTradeDateOrContractMonth = mes
                # Solicitar datos: precios + volumen + VWAP (233)
                client.reqMktData(req_id, c, "233", False, False, [])
                time.sleep(0.1)

            # Loop de actualización
            while client.running:
                datos = client.get_snapshot()
                if datos:
                    guardar_rt_data(datos)
                    # Log cada minuto
                    if datetime.now().second < 5:
                        activos_con_precio = sum(1 for d in datos.values() if d.get("last", 0) > 0)
                        logging.info(f"RT Data: {activos_con_precio}/{len(ACTIVOS_RT)} activos con precio")
                time.sleep(2)  # Actualizar cada 2 segundos

        except Exception as e:
            logging.error(f"Error en WebSocket: {e}")
            print(f"Error: {e} — reconectando en 15s...")
            time.sleep(15)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Solo leer datos actuales")
    args = parser.parse_args()

    if args.test:
        datos = get_rt_data()
        if datos:
            print(f"Datos RT disponibles ({len(datos)} activos):")
            for symbol, d in datos.items():
                print(f"  {symbol}: {d['precio']:.2f} bid={d['bid']:.2f} ask={d['ask']:.2f} presion={d['presion']}")
        else:
            print("Sin datos RT — WebSocket no está corriendo o datos expirados")
    else:
        run_websocket()
