"""
Módulo de datos de mercado en tiempo real desde Interactive Brokers.
Obtiene bid/ask, volumen, spread y datos de opciones directamente desde IB.

Solo disponible en horario de mercado (lunes-viernes 9:30-16:00 ET).
Fuera de horario retorna datos vacíos sin error.

Datos disponibles:
- Bid/Ask y spread → liquidez y presión compradora/vendedora
- Volumen en tiempo real → confirmación de movimientos
- VWAP → precio promedio ponderado por volumen
- Short interest → posicionamiento bajista institucional
- IV (Implied Volatility) → expectativa de movimiento en opciones
"""

import threading
import time
from datetime import datetime
import pytz

IB_HOST      = "127.0.0.1"
IB_PORT      = 7497
IB_CLIENT_ID = 50  # Cliente dedicado a datos de mercado

# Universo de activos para datos IB
ACTIVOS_IB = {
    "SQM":  {"secType": "STK", "exchange": "NYSE",  "currency": "USD", "activo_motor": "SQM.SN"},
    "ECH":  {"secType": "STK", "exchange": "NYSE",  "currency": "USD", "activo_motor": "ECH"},
    "GLD":  {"secType": "STK", "exchange": "NYSE",  "currency": "USD", "activo_motor": "GC=F"},
    "SPY":  {"secType": "STK", "exchange": "NYSE",  "currency": "USD", "activo_motor": "^GSPC"},
    "GC":   {"secType": "FUT", "exchange": "COMEX", "currency": "USD", "activo_motor": "GC=F"},
    "HG":   {"secType": "FUT", "exchange": "COMEX", "currency": "USD", "activo_motor": "HG=F"},
}

# ── VERIFICAR HORARIO ─────────────────────────────────────────────────────────
def es_horario_mercado():
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    hora = now.time()
    from datetime import time as dtime
    return dtime(9, 25) <= hora <= dtime(16, 5)

# ── CLIENTE IB DATOS ──────────────────────────────────────────────────────────
IB_DISPONIBLE = False
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    IB_DISPONIBLE = True
except Exception:
    pass

if IB_DISPONIBLE:
    class IBMarketData(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._ready      = threading.Event()
            self._datos      = {}
            self._errores    = []
            self._next_id    = None

        def nextValidId(self, orderId):
            self._next_id = orderId
            self._ready.set()

        def tickPrice(self, reqId, tickType, price, attrib):
            """
            tickType:
            1 = bid, 2 = ask, 4 = last
            6 = high, 7 = low, 9 = close prev
            """
            if price <= 0:
                return
            if reqId not in self._datos:
                self._datos[reqId] = {}
            mapa = {1: "bid", 2: "ask", 4: "last", 6: "high", 7: "low", 9: "close_prev"}
            if tickType in mapa:
                self._datos[reqId][mapa[tickType]] = round(price, 4)

        def tickSize(self, reqId, tickType, size):
            """
            tickType:
            0 = bid_size, 3 = ask_size, 5 = last_size
            8 = volume diario, 21 = avg_volume
            """
            if reqId not in self._datos:
                self._datos[reqId] = {}
            mapa = {0: "bid_size", 3: "ask_size", 5: "last_size", 8: "volume", 21: "avg_volume"}
            if tickType in mapa:
                self._datos[reqId][mapa[tickType]] = int(size)

        def tickGeneric(self, reqId, tickType, value):
            """
            tickType:
            23 = option IV (implied volatility)
            24 = option historical vol
            """
            if reqId not in self._datos:
                self._datos[reqId] = {}
            mapa = {23: "iv_opcion", 24: "vol_historica"}
            if tickType in mapa:
                self._datos[reqId][mapa[tickType]] = round(value, 4)

        def tickString(self, reqId, tickType, value):
            """
            tickType:
            45 = timestamp último trade
            58 = RT volume (precio;size;tiempo;volTotal;VWAP;single)
            """
            if reqId not in self._datos:
                self._datos[reqId] = {}
            if tickType == 58 and value:
                try:
                    partes = value.split(";")
                    if len(partes) >= 5 and partes[4]:
                        self._datos[reqId]["vwap"] = round(float(partes[4]), 4)
                except:
                    pass

        def error(self, reqId, errorCode, errorString, *args):
            if errorCode not in (2104, 2106, 2158, 2103, 2119, 2110, 2105, 2157):
                self._errores.append(f"[{errorCode}] {errorString}")

        def conectar(self, timeout=8):
            try:
                self.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
                t = threading.Thread(target=self.run, daemon=True)
                t.start()
                return self._ready.wait(timeout=timeout)
            except Exception:
                return False

else:
    class IBMarketData:
        pass

# ── OBTENER DATOS ─────────────────────────────────────────────────────────────
def get_datos_mercado_ib(symbols=None, timeout_datos=8):
    """
    Obtiene datos de mercado en tiempo real desde IB.

    Returns:
        dict con datos por símbolo, o {} si fuera de horario o sin conexión
    """
    if not es_horario_mercado():
        return {}

    if not IB_DISPONIBLE:
        return {}

    if symbols is None:
        symbols = list(ACTIVOS_IB.keys())

    ib = IBMarketData()
    if not ib.conectar():
        return {}

    try:
        time.sleep(0.5)

        # Solicitar datos para cada símbolo
        req_map = {}
        for i, symbol in enumerate(symbols):
            if symbol not in ACTIVOS_IB:
                continue
            config  = ACTIVOS_IB[symbol]
            req_id  = i + 1

            c = Contract()
            c.symbol   = symbol
            c.secType  = config["secType"]
            c.exchange = config["exchange"]
            c.currency = config["currency"]

            if config["secType"] == "FUT":
                c.lastTradeDateOrContractMonth = _proximo_vencimiento()

            # Solicitar datos: precios + volumen + IV + RT volume
            ib.reqMktData(req_id, c, "100,101,106,233", False, False, [])
            req_map[req_id] = symbol
            time.sleep(0.2)

        # Esperar datos
        time.sleep(timeout_datos)

        # Procesar resultados
        resultados = {}
        for req_id, symbol in req_map.items():
            datos = ib.get_datos_raw(req_id) if hasattr(ib, 'get_datos_raw') else ib._datos.get(req_id, {})
            if not datos:
                continue

            bid  = datos.get("bid", 0)
            ask  = datos.get("ask", 0)
            last = datos.get("last", 0)
            vol  = datos.get("volume", 0)
            avg_vol = datos.get("avg_volume", 0)

            precio = last or ((bid + ask) / 2 if bid and ask else 0)
            spread_pct = ((ask - bid) / bid * 100) if bid > 0 else 0
            vol_ratio  = vol / avg_vol if avg_vol > 0 else 1

            # Señal de presión compradora/vendedora
            if bid > 0 and ask > 0 and last > 0:
                mid = (bid + ask) / 2
                presion = (last - bid) / (ask - bid) if (ask - bid) > 0 else 0.5
                if presion > 0.7:
                    señal_presion = "COMPRADORES"
                elif presion < 0.3:
                    señal_presion = "VENDEDORES"
                else:
                    señal_presion = "NEUTRAL"
            else:
                señal_presion = "N/D"

            resultados[symbol] = {
                "symbol":        symbol,
                "activo_motor":  ACTIVOS_IB[symbol]["activo_motor"],
                "precio":        round(precio, 4),
                "bid":           round(bid, 4),
                "ask":           round(ask, 4),
                "spread_pct":    round(spread_pct, 4),
                "last":          round(last, 4),
                "volume":        int(vol),
                "avg_volume":    int(avg_vol),
                "vol_ratio":     round(vol_ratio, 2),
                "vwap":          round(datos.get("vwap", 0), 4),
                "iv":            round(datos.get("iv_opcion", 0), 4),
                "presion":       señal_presion,
                "timestamp":     datetime.now().isoformat(),
            }

        return resultados

    except Exception as e:
        print(f"Error obteniendo datos IB: {e}")
        return {}
    finally:
        try:
            ib.cancelAllMktData() if hasattr(ib, 'cancelAllMktData') else None
            ib.disconnect()
        except:
            pass

def _proximo_vencimiento():
    """Retorna el próximo vencimiento mensual de futuros (tercer viernes)"""
    from datetime import timedelta
    hoy = datetime.now()
    for meses in range(1, 4):
        mes = hoy.replace(day=1) + timedelta(days=32 * meses)
        mes = mes.replace(day=1)
        primer_viernes = mes + timedelta(days=(4 - mes.weekday()) % 7)
        tercer_viernes = primer_viernes + timedelta(weeks=2)
        if tercer_viernes > hoy:
            return tercer_viernes.strftime("%Y%m")
    return ""

# ── SEÑALES DESDE IB ──────────────────────────────────────────────────────────
def get_señales_ib():
    """
    Genera señales de trading basadas en datos de IB.
    Compatible con el motor de recomendaciones.
    """
    datos = get_datos_mercado_ib()
    if not datos:
        return []

    señales = []
    for symbol, d in datos.items():
        score = 0
        direccion = "NEUTRO"
        descripcion = []

        # Volumen anormal → amplifica señal
        if d["vol_ratio"] >= 2:
            score += 2
            descripcion.append(f"Volumen {d['vol_ratio']:.1f}x promedio IB")

        # Presión compradora/vendedora
        if d["presion"] == "COMPRADORES":
            score += 1
            direccion = "ALZA"
            descripcion.append(f"Presión compradora (last cerca del ask)")
        elif d["presion"] == "VENDEDORES":
            score += 1
            direccion = "BAJA"
            descripcion.append(f"Presión vendedora (last cerca del bid)")

        # Spread ancho → baja liquidez → cautela
        if d["spread_pct"] > 0.5:
            score = max(0, score - 1)
            descripcion.append(f"Spread ancho {d['spread_pct']:.3f}% → baja liquidez")

        # VWAP → si precio > VWAP = alcista, precio < VWAP = bajista
        if d["vwap"] > 0 and d["precio"] > 0:
            if d["precio"] > d["vwap"] * 1.002:
                score += 1
                if direccion != "BAJA":
                    direccion = "ALZA"
                descripcion.append(f"Precio {d['precio']:.2f} sobre VWAP {d['vwap']:.2f}")
            elif d["precio"] < d["vwap"] * 0.998:
                score += 1
                if direccion != "ALZA":
                    direccion = "BAJA"
                descripcion.append(f"Precio {d['precio']:.2f} bajo VWAP {d['vwap']:.2f}")

        if score >= 2 and direccion != "NEUTRO":
            señales.append({
                "symbol":        symbol,
                "activo_motor":  d["activo_motor"],
                "score":         score,
                "direccion":     direccion,
                "descripcion":   " | ".join(descripcion),
                "datos":         d,
            })

    return sorted(señales, key=lambda x: x["score"], reverse=True)

def get_resumen_ib():
    """Resumen para el dashboard"""
    if not es_horario_mercado():
        return {
            "disponible": False,
            "razon": "Mercado cerrado — datos IB solo disponibles en horario de trading",
            "datos": {},
        }

    datos = get_datos_mercado_ib()
    return {
        "disponible": len(datos) > 0,
        "razon": "Datos en tiempo real" if datos else "Sin conexión a IB",
        "datos": datos,
        "señales": get_señales_ib(),
        "timestamp": datetime.now().isoformat(),
    }

if __name__ == "__main__":
    print("=== DATOS IB EN TIEMPO REAL ===\n")
    if not es_horario_mercado():
        print("Mercado cerrado — ejecutar en horario de trading (lunes-viernes 9:30-16:00 ET)")
        print("Módulo listo para mañana lunes")
    else:
        resumen = get_resumen_ib()
        if resumen["disponible"]:
            for symbol, d in resumen["datos"].items():
                print(f"{symbol}: precio={d['precio']:.2f} bid={d['bid']:.2f} ask={d['ask']:.2f}")
                print(f"  vol={d['volume']:,} ratio={d['vol_ratio']:.1f}x presion={d['presion']}")
                if d['vwap'] > 0:
                    print(f"  vwap={d['vwap']:.2f}")
        else:
            print(f"Sin datos: {resumen['razon']}")
