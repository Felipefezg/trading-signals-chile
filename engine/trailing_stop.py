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
    # Crypto / Futuros
    "BTC": "BTC-USD", "ETH": "ETH-USD",
    "GC": "GC=F", "CL": "CL=F", "HG": "HG=F",
    # ADRs NYSE / ETFs
    "SQM": "SQM", "BSAC": "BSAC", "BCH": "BCH", "LTM": "LTM",
    "ECH": "ECH", "SPY": "SPY", "GLD": "GLD", "TLT": "TLT",
    # Acciones Chile (.SN)
    "COPEC": "COPEC.SN", "FALABELLA": "FALABELLA.SN", "CMPC": "CMPC.SN",
    "BCI": "BCI.SN", "COLBUN": "COLBUN.SN", "ENELCHILE": "ENELCHILE.SN",
    "ENELAM": "ENELAM.SN", "ENTEL": "ENTEL.SN", "CAP": "CAP.SN",
    "CCU": "CCU.SN", "CENCOSUD": "CENCOSUD.SN", "ITAUCL": "ITAUCL.SN",
    "PARAUCO": "PARAUCO.SN", "MALLPLAZA": "MALLPLAZA.SN", "RIPLEY": "RIPLEY.SN",
    "AGUAS-A": "AGUAS-A.SN", "VAPORES": "VAPORES.SN", "ANDINA-B": "ANDINA-B.SN",
    "ILC": "ILC.SN", "CONCHATORO": "CONCHATORO.SN", "FORUS": "FORUS.SN",
    "SMU": "SMU.SN", "ECL": "ECL.SN", "SONDA": "SONDA.SN",
    "BESALCO": "BESALCO.SN", "SALFACORP": "SALFACORP.SN", "SOCOVESA": "SOCOVESA.SN",
    "MOLYMET": "MOLYMET.SN", "QUINENCO": "QUINENCO.SN", "MASISA": "MASISA.SN",
    "HABITAT": "HABITAT.SN", "PROVIDA": "PROVIDA.SN", "MARINSA": "MARINSA.SN",
}

def _calcular_trail_atr(ticker, precio_actual, trail_pct_default=0.03):
    try:
        import yfinance as yf
        yf_map = {
            "BTC": "BTC-USD", "SQM": "SQM", "COPEC": "COPEC.SN",
            "ECH": "ECH", "SPY": "SPY", "GLD": "GLD", "TLT": "TLT",
            "GC": "GC=F", "HG": "HG=F", "CL": "CL=F",
            "BSAC": "BSAC", "BCH": "BCH", "LTM": "LTM",
        }
        # Si tiene sufijo .SN en el ticker IB, buscar en Santiago
        if ticker.endswith(".SN"):
            yf_ticker = ticker
        else:
            yf_ticker = yf_map.get(ticker, ticker)
        h = yf.Ticker(yf_ticker).history(period="20d")
        if h.empty:
            return trail_pct_default
        tr = abs(h["High"] - h["Low"]).ewm(com=13, adjust=False).mean()
        atr = float(tr.iloc[-1])
        trail_atr = (atr * 1.5) / precio_actual
        return max(0.015, min(0.08, trail_atr))
    except:
        return trail_pct_default

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
    trail_pct  = _calcular_trail_atr(ticker, entrada, TRAIL_PCT.get(ticker, TRAIL_PCT.get("default", 0.03)))

    if accion == "VENDER":
        # Para posición corta: trail = entrada × (1 + trail_pct)
        trail_nivel = round(entrada * (1 + trail_pct), 4)
        precio_extremo = entrada  # precio mínimo alcanzado
    else:
        # Para posición larga: trail = entrada × (1 - trail_pct)
        trail_nivel = round(entrada * (1 - trail_pct), 4)
        precio_extremo = entrada  # precio máximo alcanzado

    # Umbral de activación por tipo de activo:
    # Crypto: 1.0% — se mueve rápido, trail debe activar pronto
    # ETFs:   1.2% — diversificados, spreads menores
    # Stocks/ADRs/Futuros: 1.5% — spread ~0.3-0.5%, necesita colchón
    _ticker_up = ticker.upper()
    if _ticker_up in ("BTC-USD", "BTC", "ETH-USD", "ETH"):
        umbral_activ = 0.010
    elif _ticker_up in ("SPY", "ECH", "GLD", "TLT", "SLV", "GDX"):
        umbral_activ = 0.012
    else:
        umbral_activ = 0.015   # acciones Chile, ADRs, futuros

    trails[ticker] = {
        "accion":        accion,
        "entrada":       entrada,
        "trail_pct":     trail_pct,
        "trail_nivel":   trail_nivel,
        "precio_extremo": precio_extremo,
        "activado":      False,
        "umbral_activacion": umbral_activ,
        "min_holding_minutos": 10,   # no activar trailing antes de 10 min
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
    También re-inicializa si el trail existente tiene una entrada diferente
    a la posición actual — señal de que es un trail stale de un trade anterior
    para el mismo ticker (bug: cerrar_posicion_local no limpiaba el trail).
    """
    posiciones = _cargar_posiciones()
    trails     = _cargar_trails()
    nuevos     = 0

    for ticker, pos in posiciones.items():
        precio_pos = pos.get("precio_entrada", 0)
        trail_existente = trails.get(ticker)

        # Re-inicializar si:
        # 1. No tiene trail, O
        # 2. El trail tiene entrada distinta a la posición actual (stale de trade anterior)
        if (trail_existente is None or
                abs(trail_existente.get("entrada", 0) - precio_pos) > precio_pos * 0.001):
            inicializar_trail(ticker, pos)
            nuevos += 1
            if trail_existente is not None:
                print(f"Trail re-inicializado (stale): {ticker} "
                      f"entrada_trail={trail_existente.get('entrada')} "
                      f"vs entrada_pos={precio_pos}")
            else:
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
    umbral       = trail.get("umbral_activacion", 0.015)
    entrada      = trail["entrada"]

    cerrar       = False
    razon_cierre = None
    trail_movido = False

    # Holding mínimo antes de activar trailing.
    # Evita cierres inmediatos por ruido de mercado en los primeros minutos.
    min_holding = trail.get("min_holding_minutos", 10)
    try:
        from datetime import datetime as _dt
        _inicio = _dt.fromisoformat(trail.get("fecha_inicio", "2000-01-01"))
        _minutos_abierto = (_dt.now() - _inicio).total_seconds() / 60
        if _minutos_abierto < min_holding:
            # Actualizar estado pero NO activar trailing ni cerrar aún
            trail["precio_actual"]          = precio_actual
            trail["ultima_actualizacion"]   = datetime.now().isoformat()
            trails[ticker] = trail
            _guardar_trails(trails)
            pnl = ((precio_actual - entrada) / entrada * 100 if accion == "COMPRAR"
                   else (entrada - precio_actual) / entrada * 100)
            return {
                "ticker": ticker, "accion": accion, "precio_actual": precio_actual,
                "precio_extremo": precio_ext, "trail_nivel": trail_nivel,
                "trail_pct": trail_pct * 100, "pnl_pct": round(pnl, 2),
                "activado": False, "trail_movido": False, "cerrar": False,
                "razon_cierre": None,
                "_holding_bloqueado": True,
                "_minutos_abierto": round(_minutos_abierto, 1),
            }
    except Exception:
        pass

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
