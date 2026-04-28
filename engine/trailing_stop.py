"""
Módulo de Trailing Stop dinámico.
El trailing stop sigue el precio cuando la posición gana,
protegiendo las ganancias acumuladas.

Lógica para posición VENDER:
- Trail = precio_mínimo_alcanzado × (1 + trail_pct)
- Si precio actual >= trail → cierre (ganancia protegida)
- El trail solo se mueve hacia abajo (siguiendo el precio)

Lógica para posición COMPRAR:
- Trail = precio_máximo_alcanzado × (1 - trail_pct)
- Si precio actual <= trail → cierre (ganancia protegida)
- El trail solo se mueve hacia arriba (siguiendo el precio)
"""

import json
import os
from datetime import datetime
import yfinance as yf

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSICIONES_FILE = os.path.join(BASE_DIR, "posiciones.json")
TRAIL_FILE      = os.path.join(BASE_DIR, "trailing_stops.json")

# Porcentaje de trailing por tipo de activo
TRAIL_PCT = {
    "BTC":    0.05,   # 5% — crypto más volátil
    "SQM":    0.04,   # 4% — acción NYSE
    "COPEC":  0.03,   # 3% — acción local menos volátil
    "ECH":    0.03,
    "SPY":    0.025,
    "GLD":    0.03,
    "LTM":    0.04,
    "default": 0.04,
}

TICKER_YF_MAP = {
    "BTC":   "BTC-USD",
    "SQM":   "SQM",
    "COPEC": "COPEC.SN",
    "ECH":   "ECH",
    "SPY":   "SPY",
    "GLD":   "GLD",
    "LTM":   "LTM.SN",
}

# ── ESTADO TRAILING ───────────────────────────────────────────────────────────
def _cargar_trails():
    try:
        if os.path.exists(TRAIL_FILE):
            with open(TRAIL_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def _guardar_trails(trails):
    with open(TRAIL_FILE, "w") as f:
        json.dump(trails, f, indent=2, default=str)

def _cargar_posiciones():
    try:
        with open(POSICIONES_FILE) as f:
            return json.load(f)
    except:
        return {}

def get_precio_actual(ticker):
    yf_ticker = TICKER_YF_MAP.get(ticker, ticker)
    try:
        h = yf.Ticker(yf_ticker).history(period="1d", interval="1m")
        if not h.empty:
            return float(h["Close"].iloc[-1])
        h = yf.Ticker(yf_ticker).history(period="2d")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except:
        pass
    return None

# ── INICIALIZAR TRAILING STOP ─────────────────────────────────────────────────
def inicializar_trail(ticker, posicion):
    """
    Inicializa el trailing stop para una posición nueva.
    Se llama cuando se abre la posición.
    """
    trails     = _cargar_trails()
    accion     = posicion.get("accion", "COMPRAR")
    entrada    = posicion.get("precio_entrada", 0)
    trail_pct  = TRAIL_PCT.get(ticker, TRAIL_PCT["default"])

    if accion == "VENDER":
        # Para posición corta: trail = entrada × (1 + trail_pct)
        trail_nivel = round(entrada * (1 + trail_pct), 4)
        precio_extremo = entrada  # precio mínimo alcanzado
    else:
        # Para posición larga: trail = entrada × (1 - trail_pct)
        trail_nivel = round(entrada * (1 - trail_pct), 4)
        precio_extremo = entrada  # precio máximo alcanzado

    trails[ticker] = {
        "accion":        accion,
        "entrada":       entrada,
        "trail_pct":     trail_pct,
        "trail_nivel":   trail_nivel,
        "precio_extremo": precio_extremo,
        "activado":      False,  # True cuando el precio se aleja de la entrada
        "umbral_activacion": 0.01,  # 1% de ganancia para activar el trailing
        "historial":     [{
            "timestamp":    datetime.now().isoformat(),
            "precio":       entrada,
            "trail_nivel":  trail_nivel,
            "evento":       "INICIALIZADO",
        }],
        "fecha_inicio":  datetime.now().isoformat(),
    }

    _guardar_trails(trails)
    return trails[ticker]

def inicializar_trails_existentes():
    """
    Inicializa trailing stops para posiciones ya abiertas
    que no tienen trail configurado.
    """
    posiciones = _cargar_posiciones()
    trails     = _cargar_trails()
    nuevos     = 0

    for ticker, pos in posiciones.items():
        if ticker not in trails:
            inicializar_trail(ticker, pos)
            nuevos += 1
            print(f"Trail inicializado: {ticker}")

    return nuevos

# ── ACTUALIZAR TRAILING STOP ──────────────────────────────────────────────────
def actualizar_trail(ticker, precio_actual):
    """
    Actualiza el nivel del trailing stop según el precio actual.
    El trail solo se mueve a favor de la posición.

    Returns:
        dict con nuevo nivel y si se debe cerrar
    """
    trails = _cargar_trails()

    if ticker not in trails:
        posiciones = _cargar_posiciones()
        if ticker in posiciones:
            inicializar_trail(ticker, posiciones[ticker])
            trails = _cargar_trails()
        else:
            return None

    trail = trails[ticker]
    accion       = trail["accion"]
    trail_pct    = trail["trail_pct"]
    precio_ext   = trail["precio_extremo"]
    trail_nivel  = trail["trail_nivel"]
    activado     = trail["activado"]
    umbral       = trail.get("umbral_activacion", 0.01)
    entrada      = trail["entrada"]

    cerrar       = False
    razon_cierre = None
    trail_movido = False

    if accion == "VENDER":
        # Ganancia en posición corta = precio baja
        ganancia_pct = (entrada - precio_actual) / entrada

        # Activar trailing cuando hay 1% de ganancia
        if not activado and ganancia_pct >= umbral:
            trail["activado"] = True
            activado = True

        if activado:
            # Actualizar precio mínimo si el precio baja más
            if precio_actual < precio_ext:
                precio_ext = precio_actual
                nuevo_trail = round(precio_ext * (1 + trail_pct), 4)
                if nuevo_trail < trail_nivel:
                    trail_nivel  = nuevo_trail
                    trail_movido = True

            # Verificar si el precio tocó el trailing stop
            if precio_actual >= trail_nivel:
                cerrar       = True
                razon_cierre = f"TRAILING STOP activado — precio {precio_actual:,.2f} >= trail {trail_nivel:,.2f}"

    else:  # COMPRAR
        # Ganancia en posición larga = precio sube
        ganancia_pct = (precio_actual - entrada) / entrada

        # Activar trailing cuando hay 1% de ganancia
        if not activado and ganancia_pct >= umbral:
            trail["activado"] = True
            activado = True

        if activado:
            # Actualizar precio máximo si el precio sube más
            if precio_actual > precio_ext:
                precio_ext = precio_actual
                nuevo_trail = round(precio_ext * (1 - trail_pct), 4)
                if nuevo_trail > trail_nivel:
                    trail_nivel  = nuevo_trail
                    trail_movido = True

            # Verificar si el precio tocó el trailing stop
            if precio_actual <= trail_nivel:
                cerrar       = True
                razon_cierre = f"TRAILING STOP activado — precio {precio_actual:,.2f} <= trail {trail_nivel:,.2f}"

    # Calcular PnL actual
    if accion == "VENDER":
        pnl_pct = round((entrada - precio_actual) / entrada * 100, 2)
    else:
        pnl_pct = round((precio_actual - entrada) / entrada * 100, 2)

    # Actualizar estado
    trail["precio_extremo"] = precio_ext
    trail["trail_nivel"]    = trail_nivel
    trail["precio_actual"]  = precio_actual
    trail["pnl_pct"]        = pnl_pct
    trail["activado"]       = activado
    trail["ultima_actualizacion"] = datetime.now().isoformat()

    if trail_movido or cerrar:
        trail["historial"].append({
            "timestamp":   datetime.now().isoformat(),
            "precio":      precio_actual,
            "trail_nivel": trail_nivel,
            "evento":      "CIERRE" if cerrar else "TRAIL_MOVIDO",
        })
        trail["historial"] = trail["historial"][-50:]  # max 50 eventos

    trails[ticker] = trail
    _guardar_trails(trails)

    return {
        "ticker":        ticker,
        "accion":        accion,
        "precio_actual": precio_actual,
        "precio_extremo": precio_ext,
        "trail_nivel":   trail_nivel,
        "trail_pct":     trail_pct * 100,
        "pnl_pct":       pnl_pct,
        "activado":      activado,
        "trail_movido":  trail_movido,
        "cerrar":        cerrar,
        "razon_cierre":  razon_cierre,
    }

# ── VERIFICAR TODOS LOS TRAILS ────────────────────────────────────────────────
def verificar_trailing_stops():
    """
    Verifica todos los trailing stops activos.
    Retorna lista de posiciones que deben cerrarse.
    """
    # Inicializar trails para posiciones sin trail
    inicializar_trails_existentes()

    posiciones = _cargar_posiciones()
    resultados = []
    cierres    = []

    for ticker in posiciones:
        precio = get_precio_actual(ticker)
        if not precio:
            continue

        resultado = actualizar_trail(ticker, precio)
        if resultado:
            resultados.append(resultado)
            if resultado["cerrar"]:
                cierres.append(resultado)

    return {
        "timestamp":  datetime.now().isoformat(),
        "total":      len(resultados),
        "cierres":    cierres,
        "estados":    resultados,
    }

def get_estado_trails():
    """Retorna estado actual de todos los trailing stops"""
    trails     = _cargar_trails()
    posiciones = _cargar_posiciones()

    resultado = {}
    for ticker, trail in trails.items():
        if ticker not in posiciones:
            continue  # posición ya cerrada
        precio = get_precio_actual(ticker)
        resultado[ticker] = {
            **trail,
            "precio_actual": precio,
        }
    return resultado

if __name__ == "__main__":
    print("=== TRAILING STOPS ===\n")

    # Inicializar trails para posiciones existentes
    nuevos = inicializar_trails_existentes()
    print(f"Trails inicializados: {nuevos}")

    print("\nEstado actual:")
    resumen = verificar_trailing_stops()

    for estado in resumen["estados"]:
        icon  = "🔴" if estado["cerrar"] else ("🟡" if estado["activado"] else "⚪")
        print(f"\n{icon} {estado['ticker']} ({estado['accion']})")
        print(f"   Precio actual:  {estado['precio_actual']:,.2f}")
        print(f"   Trail nivel:    {estado['trail_nivel']:,.2f} ({estado['trail_pct']:.1f}%)")
        print(f"   Precio extremo: {estado['precio_extremo']:,.2f}")
        print(f"   PnL actual:     {estado['pnl_pct']:+.2f}%")
        print(f"   Trail activo:   {'Sí' if estado['activado'] else 'No (esperando 1% ganancia)'}")
        if estado["cerrar"]:
            print(f"   ⚠️  CERRAR: {estado['razon_cierre']}")

    if resumen["cierres"]:
        print(f"\n⚠️  {len(resumen['cierres'])} posición(es) requieren cierre por trailing stop")
    else:
        print("\n✅ Sin cierres por trailing stop necesarios")
