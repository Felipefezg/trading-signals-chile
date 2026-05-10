"""
Motor de Trading Automático — Trading Terminal Chile
Ejecuta y cierra posiciones automáticamente con salvaguardas estrictas.

Salvaguardas:
- Máx 5 posiciones simultáneas
- Máx USD 10.000 por operación
- Máx USD 30.000 en riesgo total (30% del capital)
- Stop Loss obligatorio
- Convicción mínima 80%
- Mínimo 3 fuentes
- Riesgo máximo 5/10
- Pausa si PnL día < -3%
- Pausa si drawdown > 10%
- Pausa si 3 trades consecutivos perdedores
- Solo operar en horario de mercado
- Máx 2 posiciones mismo sector
- Máx 2 posiciones mismo bloque de correlación (Chile_macro / Commodities / USA_equity / Crypto)
- No duplicar ticker
"""

import json
import os
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
import pytz
import yfinance as yf

# ── PATHS ─────────────────────────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSICIONES_FILE   = os.path.join(BASE_DIR, "posiciones.json")
TRADES_FILE       = os.path.join(BASE_DIR, "trades_cerrados.json")
ESTADO_AUTO_FILE  = os.path.join(BASE_DIR, "estado_automatico.json")
LOG_AUTO_FILE     = os.path.join(BASE_DIR, "log_automatico.json")
LOG_APERTURAS_FILE = os.path.join(BASE_DIR, "log_aperturas.json")

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "trading_auto.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ── PARÁMETROS (todos en porcentaje del capital — agnósticos al monto) ────────
# Capital real se lee desde IB en runtime via get_capital_ib().
# Ningún límite está expresado en USD — escalan automáticamente con la cuenta.
PARAMS = {
    # ── Sizing — % del capital real de IB ────────────────────────────────────
    "max_posiciones":           5,     # Posiciones simultáneas máximas
    "max_pct_por_operacion":    8.0,   # % capital máx por operación (8% de $100k = $8k)
    "max_pct_riesgo_total":    20.0,   # % capital máx en riesgo simultáneo
    "min_pct_por_operacion":    2.0,   # % capital mínimo (floor para señales sin Kelly)
    # ── Filtros de calidad ────────────────────────────────────────────────────
    "conviccion_minima":       78,
    "riesgo_maximo":            7,
    "fuentes_minimas":          3,
    # ── Protección de capital ─────────────────────────────────────────────────
    "max_drawdown_pct":         8.0,   # Pausa si drawdown desde máximo >= 8%
    "pausa_pnl_dia_pct":       -2.0,   # Pausa si PnL día <= -2%
    "pausa_consecutivos":       3,     # Pausa tras N trades consecutivos perdedores
    # ── Diversificación ───────────────────────────────────────────────────────
    "max_mismo_sector":         2,
    "max_por_bloque":           2,   # máx posiciones abiertas del mismo bloque correlado
    # ── Horario ───────────────────────────────────────────────────────────────
    "horario_inicio":           "09:30",
    "horario_fin":              "15:45",
    "timezone":                 "America/New_York",
}

# ── BLACKLIST AUTO-TRADING ────────────────────────────────────────────────────
# Tickers PROHIBIDOS para ejecución automática por nocional masivo o liquidez insuficiente.
# CL (WTI crude futures): ~$95.000 USD/contrato (1.000 barriles × ~$95)
# HG (copper futures):    ~$25.000 USD/contrato (25.000 lbs × ~$1.00/lb)
# Ambos exceden max_usd_por_operacion y producen PnL completamente deformado.
# Para operar estos activos: hacerlo MANUALMENTE desde IB Gateway.
BLACKLIST_AUTO = {"CL", "HG", "GC"}  # Futuros con nocional masivo — operar via ETF (GLD/SLV/GDX)

# ── BLOQUES DE CORRELACIÓN ────────────────────────────────────────────────────
# Agrupa activos que responden al mismo factor macro subyacente.
# Cuando un factor macro golpea, todos los activos del bloque se mueven juntos
# → no diversifican el portafolio, amplifican el drawdown.
#
# Chile_macro: mineras, bancos y aerolíneas chilenas se correlacionan con
#   riesgo político Chile + precio cobre. IPSA -5% → todos bajan.
# Commodities_metales: GLD/SLV/GDX son el mismo trade (precio metal precioso).
# Renta_fija: TLT es el único activo del bloque — sin riesgo de concentración.
# Crypto: BTC 24/7, no correlacionado con Chile ni con ETFs USA.
# USA_equity: QQQ/IWM/XLE son ETFs USA pero distintos sectores. IWM y QQQ tienen
#   correlación alta en riesgo-off, por eso se incluyen en el mismo bloque.
#
# Lógica: máx PARAMS["max_por_bloque"] posiciones del mismo bloque simultáneamente.
BLOQUES_CORRELACION = {
    "Chile_macro":       {"SQM", "BSAC", "BCH", "LTM", "CMPC", "BSANTANDER",
                          "COPEC", "BCI", "FALABELLA", "CENCOSUD", "ECH"},
    "Commodities_metal": {"GLD", "SLV", "GDX"},
    "Renta_fija":        {"TLT"},
    "Crypto":            {"BTC", "ETH"},
    "USA_equity":        {"SPY", "QQQ", "IWM", "XLE"},
}

# Mapa inverso IB_ticker → bloque para lookup O(1)
_TICKER_A_BLOQUE: dict = {}
for _bloque, _tickers in BLOQUES_CORRELACION.items():
    for _t in _tickers:
        _TICKER_A_BLOQUE[_t] = _bloque

def _bloque_de(ib_ticker: str) -> Optional[str]:
    """Retorna el bloque de correlación del ticker, o None si no está clasificado."""
    return _TICKER_A_BLOQUE.get(ib_ticker)

# ── GRUPOS DE FUENTES (independencia de señal) ────────────────────────────────
# Cada grupo mide un fenómeno distinto. Una señal convincente debe tener al menos
# 2 grupos representados — previene aprobar señales puramente momentum (AT+MTF+
# Correlaciones son todas precio) sin respaldo de sentimiento o fundamental.
#
# Grupo TECNICO:      precio, tendencia, momentum — fuentes correlacionadas entre sí
# Grupo SENTIMIENTO:  opciones, fear/greed — estado emocional del mercado
# Grupo FUNDAMENTAL:  flujos reales, macro, institucionales — causas subyacentes
# Grupo PREDICCION:   mercados de predicción — probabilidades agregadas externas
# Grupo ALTERNATIVO:  datos alternativos — búsquedas, spreads locales, renta fija
#
# Si una fuente no está en ningún grupo, cuenta como OTRO (no suma diversidad).
GRUPOS_FUENTES = {
    # Nombres exactos tal como los usa recomendaciones.py en fuentes.append(...)
    "TECNICO":     {"Análisis Técnico", "MTF", "Correlaciones", "ML", "IB Data", "Volumen", "Momentum"},
    "SENTIMIENTO": {"IV Opciones", "Put/Call", "Fear&Greed", "VolAlertas"},
    "FUNDAMENTAL": {"Macro USA", "Noticias", "13F SEC", "Order Flow", "CMF", "Renta Fija"},
    "PREDICCION":  {"Polymarket", "Kalshi"},
    "ALTERNATIVO": {"Google Trends", "Mercado Local"},
}

# ── CLASIFICACIÓN FAST / SLOW ─────────────────────────────────────────────────
# Fast: fuentes de timing — capturan el estado del mercado en el ciclo actual.
# Slow: fuentes de contexto — lagging (horas, días, trimestres) o macroestructurales.
#
# Regla: toda señal ejecutable debe tener al menos MIN_FAST_SOURCES fuentes fast.
# Impide que 13F (trimestral) + Renta Fija (semanal) + Correlaciones (lagging)
# den el visto bueno a una entrada intraday sin ningún respaldo de timing.
FUENTES_FAST = {
    "Análisis Técnico", "MTF", "IV Opciones", "Order Flow",
    "IB Data", "Mercado Local", "ML", "Volumen", "CMF", "Momentum",
}
FUENTES_SLOW = {
    "Macro USA", "Fear&Greed", "Put/Call", "13F SEC", "Renta Fija",
    "Correlaciones", "Polymarket", "Kalshi", "Noticias", "Google Trends",
}
MIN_FAST_SOURCES = 1  # Mínimo de fuentes fast para ejecutar

# Construir mapa inverso fuente→grupo para lookup O(1)
_FUENTE_A_GRUPO: dict = {}
for _grupo, _fuentes in GRUPOS_FUENTES.items():
    for _f in _fuentes:
        _FUENTE_A_GRUPO[_f] = _grupo

def _grupos_presentes(fuentes: list) -> set:
    """Retorna el conjunto de grupos representados en la lista de fuentes."""
    return {_FUENTE_A_GRUPO.get(f, "OTRO") for f in fuentes} - {"OTRO"}

# Mínimo de grupos distintos para ejecutar (2 = técnico + al menos uno externo)
MIN_GRUPOS_FUENTES = 2

# Sectores por ticker IB — universo completo (51 activos)
# Fuente: engine/universo.py → campo "sector"
SECTORES = {
    # IPSA 30
    "SQM":        "Minería",
    "COPEC":      "Energía",
    "BCI":        "Bancos",
    "BSAC":       "Bancos",
    "BCH":        "Bancos",
    "FALABELLA":  "Retail",
    "CENCOSUD":   "Retail",
    "CMPC":       "Industria",
    "COLBUN":     "Energía",
    "ENELCHILE":  "Energía",
    "ENELAM":     "Energía",
    "ENTEL":      "Telecomunicaciones",
    "LTM":        "Transporte",
    "CAP":        "Minería",
    "CCU":        "Consumo",
    "ITAUCL":     "Bancos",
    "PARAUCO":    "Inmobiliario",
    "MALLPLAZA":  "Inmobiliario",
    "RIPLEY":     "Retail",
    "AGUAS-A":    "Utilities",
    "VAPORES":    "Transporte",
    "ANDINA-B":   "Consumo",
    "ILC":        "Financiero",
    "CONCHATORO": "Consumo",
    "FORUS":      "Retail",
    "SMU":        "Retail",
    "ECL":        "Energía",
    "SONDA":      "Tecnología",
    # Small caps
    "BESALCO":    "Construcción",
    "SALFACORP":  "Construcción",
    "SOCOVESA":   "Inmobiliario",
    "INGEVEC":    "Construcción",
    "HITES":      "Retail",
    "MOLYMET":    "Minería",
    "QUINENCO":   "Holding",
    "MASISA":     "Industria",
    "HABITAT":    "Financiero",
    "PROVIDA":    "Financiero",
    "MARINSA":    "Transporte",
    # ETFs Chile / Renta Fija / Commodities
    "ECH":        "ETF Chile",
    "SPY":        "ETF USA",
    "TLT":        "Renta Fija",
    "GLD":        "Commodities",
    "SLV":        "Commodities",   # Silver ETF
    "GDX":        "Commodities",   # Gold Miners ETF
    # ETFs USA — ejecutables, descorrelacionados de Chile
    "QQQ":        "ETF Tech USA",
    "IWM":        "ETF Small USA",
    "XLE":        "ETF Energía USA",
    # Commodities / Futuros
    "GC":         "Commodities",
    "HG":         "Commodities",
    "CL":         "Energía",
    # Crypto
    "BTC":        "Crypto",
    "ETH":        "Crypto",
}

# ── CAPITAL REAL DESDE IB ─────────────────────────────────────────────────────
# Archivo de caché donde ib_executor.py escribe el capital actualizado tras
# cada sync. Motor lo lee para que todos los límites escalen con el capital real.
_CAPITAL_CACHE_FILE = os.path.join(BASE_DIR, "data", "capital_ib.json")
_CAPITAL_FALLBACK   = 100_000.0   # Usado solo si IB no está conectado

def get_capital_ib() -> float:
    """
    Retorna el capital real de la cuenta IB (net liquidation en USD).

    Jerarquía:
      1. data/capital_ib.json — escrito por ib_executor tras cada sync
      2. estado_automatico.json campo "capital_ib" — fallback si el cache falta
      3. _CAPITAL_FALLBACK ($100k) — último recurso, registra advertencia

    Esta función es la ÚNICA fuente de capital para todos los cálculos del motor.
    Nunca usar un valor hardcodeado en ninguna otra parte del código.
    """
    # 1. Cache dedicado (más fresco — escrito por ib_executor)
    try:
        if os.path.exists(_CAPITAL_CACHE_FILE):
            with open(_CAPITAL_CACHE_FILE) as f:
                data = json.load(f)
            capital = float(data.get("net_liquidation", 0))
            if capital > 0:
                return capital
    except Exception:
        pass

    # 2. Fallback: estado_automatico.json
    try:
        estado = _cargar_estado()
        capital = float(estado.get("capital_ib", 0))
        if capital > 0:
            return capital
    except Exception:
        pass

    # 3. Último recurso — advertir en log
    logging.warning(
        f"get_capital_ib: no se pudo leer capital desde IB — usando fallback "
        f"${_CAPITAL_FALLBACK:,.0f}. Verificar conexión IB Gateway."
    )
    return _CAPITAL_FALLBACK

# ── ESTADO DEL MOTOR ──────────────────────────────────────────────────────────
COOLDOWN_MINUTOS = 240  # 4 horas — evita chasing intraday tras SL hit
                        # (era 60 min: SQM perdió x2 en el mismo día mismo lado)

def _cargar_estado():
    _defaults = {
        "activo":               False,
        "pausado":              False,
        "razon_pausa":          None,
        "consecutivos_perdedor": 0,
        "pnl_dia":              0.0,
        "ultima_verificacion":  None,
        "ordenes_hoy":          0,
        "log":                  [],
        "cooldown_tickers":     {},   # {ib_ticker: iso_timestamp_cierre}
        "perdedores_dia":       {},   # {ib_ticker: "YYYY-MM-DD"} — ban same-day tras pérdida
    }
    try:
        if os.path.exists(ESTADO_AUTO_FILE):
            with open(ESTADO_AUTO_FILE) as f:
                guardado = json.load(f)
            # Merge: defaults primero, luego valores guardados — garantiza que
            # claves nuevas (ej: cooldown_tickers) siempre estén presentes
            # aunque el archivo sea de una versión anterior del motor.
            merged = {**_defaults, **guardado}
            if not isinstance(merged.get("cooldown_tickers"), dict):
                merged["cooldown_tickers"] = {}
            if not isinstance(merged.get("perdedores_dia"), dict):
                merged["perdedores_dia"] = {}
            return merged
    except Exception:
        pass
    return dict(_defaults)

def _perdio_hoy_misma_direccion(ib_ticker: str, accion: str) -> bool:
    """
    Retorna True si el ticker ya tuvo un trade perdedor HOY en la misma
    dirección (accion = 'COMPRAR' o 'VENDER').

    Previene el patrón de chasing: SL tocado → re-entrada inmediata en el
    mismo lado → segundo SL. SQM lo hizo x2 el 2026-05-07.

    Lee trades_cerrados.json (confirmados_ib=True únicamente).
    """
    try:
        if not os.path.exists(TRADES_FILE):
            return False
        with open(TRADES_FILE) as f:
            trades = json.load(f)
        hoy = datetime.now().date().isoformat()
        for t in trades:
            if (t.get("ticker") == ib_ticker
                    and t.get("accion") == accion
                    and t.get("resultado") == "perdedor"
                    and t.get("confirmado_ib", False)
                    and str(t.get("fecha_salida", ""))[:10] == hoy):
                return True
    except Exception:
        pass
    return False


def _registrar_cierre_cooldown(estado, ib_ticker, fue_perdedor=False):
    """
    Registra timestamp de cierre para el cooldown del ticker.
    Si fue_perdedor=True, también registra un ban same-day para evitar
    re-entrada el mismo día de trading tras una pérdida.
    """
    if "cooldown_tickers" not in estado:
        estado["cooldown_tickers"] = {}
    if "perdedores_dia" not in estado:
        estado["perdedores_dia"] = {}
    estado["cooldown_tickers"][ib_ticker] = datetime.now().isoformat()
    if fue_perdedor:
        # Guardar la fecha del día (YYYY-MM-DD) — se compara contra la fecha actual
        estado["perdedores_dia"][ib_ticker] = datetime.now().strftime("%Y-%m-%d")

def _en_cooldown(estado, ib_ticker):
    """
    Retorna (True, razon) si el ticker está bloqueado, (False, "") si puede operarse.
    Dos checks independientes:
    1. Cooldown temporal (COOLDOWN_MINUTOS tras cualquier cierre)
    2. Ban same-day (si el ticker perdió en la sesión de trading actual)
    """
    # ── Check 1: same-day ban tras pérdida ────────────────────────────────────
    perdedores = estado.get("perdedores_dia", {})
    fecha_perdida = perdedores.get(ib_ticker)
    if fecha_perdida:
        hoy = datetime.now().strftime("%Y-%m-%d")
        if fecha_perdida == hoy:
            return True, f"{ib_ticker} perdió hoy — sin re-entrada hasta mañana"

    # ── Check 2: cooldown temporal ────────────────────────────────────────────
    cooldowns = estado.get("cooldown_tickers", {})
    ts_str = cooldowns.get(ib_ticker)
    if not ts_str:
        return False, ""
    try:
        ts_cierre = datetime.fromisoformat(ts_str)
        elapsed = (datetime.now() - ts_cierre).total_seconds() / 60
        if elapsed < COOLDOWN_MINUTOS:
            restantes = round(COOLDOWN_MINUTOS - elapsed, 1)
            return True, f"Cooldown {ib_ticker}: {restantes} min restantes"
    except Exception:
        pass
    return False, ""

def _guardar_estado(estado):
    with open(ESTADO_AUTO_FILE, "w") as f:
        json.dump(estado, f, indent=2, default=str)

def get_estado():
    return _cargar_estado()

def activar_motor(activo=True):
    estado = _cargar_estado()
    estado["activo"]      = activo
    estado["pausado"]     = False
    estado["razon_pausa"] = None
    _guardar_estado(estado)
    logging.info(f"Motor {'ACTIVADO' if activo else 'DESACTIVADO'}")

def pausar_motor(razon):
    estado = _cargar_estado()
    estado["pausado"]     = True
    estado["razon_pausa"] = razon
    _guardar_estado(estado)
    logging.warning(f"Motor PAUSADO: {razon}")
    _registrar_evento("PAUSA", razon, {})

def _registrar_evento(tipo, descripcion, datos):
    evento = {
        "timestamp":   datetime.now().isoformat(),
        "tipo":        tipo,
        "descripcion": descripcion,
        "datos":       datos,
    }

    # ── Log general (RECHAZADA, CIERRE, PAUSA, etc.) ──────────────────────────
    log = []
    if os.path.exists(LOG_AUTO_FILE):
        try:
            with open(LOG_AUTO_FILE) as f:
                log = json.load(f)
        except:
            pass
    log.append(evento)
    log = log[-200:]
    with open(LOG_AUTO_FILE, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # ── Log dedicado de aperturas — nunca desplazado por RECHAZADA ────────────
    if tipo in ("APERTURA", "APERTURA_FALLIDA"):
        aperturas = []
        if os.path.exists(LOG_APERTURAS_FILE):
            try:
                with open(LOG_APERTURAS_FILE) as f:
                    aperturas = json.load(f)
            except:
                pass
        aperturas.append(evento)
        aperturas = aperturas[-500:]   # guarda últimas 500 aperturas
        with open(LOG_APERTURAS_FILE, "w") as f:
            json.dump(aperturas, f, indent=2, default=str)

def get_log_auto(limit=50):
    if not os.path.exists(LOG_AUTO_FILE):
        return []
    try:
        with open(LOG_AUTO_FILE) as f:
            log = json.load(f)
        return list(reversed(log))[:limit]
    except:
        return []

# ── VALIDACIONES DE MERCADO ───────────────────────────────────────────────────
def es_horario_mercado(tipo_activo=None):
    """
    Verifica horario según tipo de activo.
    Crypto: 24/7
    Forex: lunes-viernes 24h
    Acciones/ETFs/Futuros: 9:30-15:45 ET lunes-viernes
    """
    import pytz
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)

    # Crypto opera 24/7
    if tipo_activo in ("Crypto",):
        return True, "Mercado Crypto abierto 24/7"

    # Forex opera lunes-viernes 24h
    if tipo_activo == "Forex":
        if now.weekday() < 5:
            return True, "Mercado Forex abierto"
        return False, "Mercado Forex cerrado (fin de semana)"

    # Acciones Chile locales — Bolsa de Santiago
    if tipo_activo == "Acción Chile":
        tz_cl = pytz.timezone("America/Santiago")
        now_cl = datetime.now(tz_cl)
        if now_cl.weekday() >= 5:
            return False, "Bolsa Santiago cerrada (fin de semana)"
        from datetime import time as dtime
        if dtime(9, 30) <= now_cl.time() <= dtime(17, 30):
            return True, "Bolsa Santiago abierta (9:30-17:30 hora Chile)"
        return False, "Bolsa Santiago fuera de horario"

    # Acciones USA, ETFs, Futuros — horario NYSE
    if now.weekday() >= 5:
        return False, f"Mercado cerrado (fin de semana)"
    from datetime import time as dtime
    inicio = dtime(int(PARAMS["horario_inicio"].split(":")[0]),
                   int(PARAMS["horario_inicio"].split(":")[1]))
    fin    = dtime(int(PARAMS["horario_fin"].split(":")[0]),
                   int(PARAMS["horario_fin"].split(":")[1]))
    if inicio <= now.time() <= fin:
        # Horario óptimo de entrada: primeras 2h y última hora
        from datetime import time as dtime2
        hora_actual = now.time()
        if dtime2(9, 30) <= hora_actual <= dtime2(11, 30):
            return True, f"Mercado NYSE abierto — HORARIO ÓPTIMO entrada"
        elif dtime2(14, 30) <= hora_actual <= dtime2(15, 45):
            return True, f"Mercado NYSE abierto — hora cierre"
        else:
            return True, f"Mercado NYSE abierto — horario normal"
    return False, f"Fuera de horario NYSE ({PARAMS['horario_inicio']}-{PARAMS['horario_fin']} ET)"

def es_horario_mercado_legacy():
    """Verifica si el mercado NYSE está abierto"""
    tz  = pytz.timezone(PARAMS["timezone"])
    now = datetime.now(tz)

    # Fin de semana
    if now.weekday() >= 5:
        return False, "Mercado cerrado (fin de semana)"

    # Horario
    inicio = datetime.strptime(PARAMS["horario_inicio"], "%H:%M").time()
    fin    = datetime.strptime(PARAMS["horario_fin"], "%H:%M").time()
    hora   = now.time()

    if not (inicio <= hora <= fin):
        return False, f"Fuera de horario ({PARAMS['horario_inicio']}-{PARAMS['horario_fin']} ET)"

    return True, "Mercado abierto"


def _en_ventana_bloqueada(tipo_activo=None):
    """
    Detecta ventanas de baja calidad de ejecución para nuevas APERTURAS.
    Los cierres/SL/TP NO pasan por este filtro.

    Ventanas bloqueadas:
      - 9:30–10:00 ET  : apertura NYSE — spreads amplios, market-makers ajustando,
                         fills impredecibles. Esperar a que se estabilice el libro.
      - 15:30–15:45 ET : pre-cierre NYSE — rebalanceos institucionales, MOC/LOC
                         distorsionan el precio. Nueva posición quedaría expuesta
                         al gap de apertura del día siguiente.

    Para Bolsa Santiago (Acción Chile) se aplican ventanas equivalentes en hora local:
      - 9:30–10:00 hora Chile  : apertura Bolsa Santiago
      - 17:15–17:30 hora Chile : pre-cierre Bolsa Santiago

    Retorna: (bloqueado: bool, razon: str)
    """
    import pytz
    from datetime import time as dtime

    # Crypto opera 24/7 y sus spreads no presentan este patrón intraday
    if tipo_activo == "Crypto":
        return False, ""

    tz_et  = pytz.timezone("America/New_York")
    hora_et = datetime.now(tz_et).time()

    # Apertura NYSE: primeros 30 min
    if dtime(9, 30) <= hora_et < dtime(10, 0):
        return True, "Ventana bloqueada — apertura NYSE (9:30–10:00 ET), spreads amplios"

    # Pre-cierre NYSE: últimos 15 min de sesión regular
    if dtime(15, 30) <= hora_et <= dtime(15, 45):
        return True, "Ventana bloqueada — pre-cierre NYSE (15:30–15:45 ET), rebalanceos institucionales"

    # Bolsa Santiago — ventanas en hora Chile
    if tipo_activo == "Acción Chile":
        tz_cl   = pytz.timezone("America/Santiago")
        hora_cl = datetime.now(tz_cl).time()
        if dtime(9, 30) <= hora_cl < dtime(10, 0):
            return True, "Ventana bloqueada — apertura Bolsa Santiago (9:30–10:00 hora Chile)"
        if dtime(17, 15) <= hora_cl <= dtime(17, 30):
            return True, "Ventana bloqueada — pre-cierre Bolsa Santiago (17:15–17:30 hora Chile)"

    return False, ""


# ── VALIDACIONES DE PORTAFOLIO ────────────────────────────────────────────────
def _cargar_posiciones():
    try:
        if os.path.exists(POSICIONES_FILE):
            with open(POSICIONES_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def _cargar_trades():
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE) as f:
                return json.load(f)
    except:
        pass
    return []

def _pnl_trade_usd(trade):
    """
    Normaliza el pnl_total de un trade a USD.
    Acciones Chile (tipo='Acción Chile') tienen precios en CLP — convertir.
    """
    pnl = trade.get("pnl_total", 0)
    if trade.get("tipo") == "Acción Chile":
        try:
            from engine.ib_executor import _get_usd_clp
            tasa = _get_usd_clp()
            if tasa and tasa > 0:
                pnl = pnl / tasa
        except Exception:
            pass  # mantener CLP si falla — peor caso: sobre-estimación
    return pnl


def calcular_pnl_dia():
    """
    Calcula PnL del día actual en USD.
    Solo considera trades confirmados por IB (confirmado_ib != False).
    Normaliza acciones Chile (CLP) a USD.
    """
    trades = _cargar_trades()
    hoy    = datetime.now().date().isoformat()
    pnl    = sum(
        _pnl_trade_usd(t)
        for t in trades
        if t.get("fecha_salida", "")[:10] == hoy
        and t.get("confirmado_ib", True) is not False   # excluir fantasmas explícitos
    )
    return pnl

def calcular_riesgo_total():
    """
    Calcula riesgo total en posiciones abiertas como % del capital IB real.
    (entrada - SL) × cantidad para cada posición, normalizado a USD y expresado
    como porcentaje del capital actual de la cuenta.
    """
    posiciones = _cargar_posiciones()
    riesgo_usd = 0.0
    for ticker, p in posiciones.items():
        entrada  = p.get("precio_entrada", 0)
        sl       = p.get("sl", entrada)
        cantidad = p.get("cantidad", 0)
        accion   = p.get("accion", "COMPRAR")
        tipo     = p.get("tipo", "ETF")
        if sl is None or entrada is None:
            continue
        if accion == "COMPRAR":
            riesgo_unit = max(0, entrada - sl)
        else:
            riesgo_unit = max(0, sl - entrada)
        riesgo_pos = riesgo_unit * cantidad
        # Normalizar CLP → USD para acciones Chile
        if tipo == "Acción Chile":
            try:
                from engine.ib_executor import _get_usd_clp
                tasa = _get_usd_clp()
                if tasa and tasa > 0:
                    riesgo_pos = riesgo_pos / tasa
            except Exception:
                pass
        riesgo_usd += riesgo_pos
    # Expresar como % del capital real
    capital = get_capital_ib()
    if capital <= 0:
        return 0.0
    return round(riesgo_usd / capital * 100, 2)

def calcular_drawdown_total():
    """
    Calcula drawdown total desde máximo histórico como % del capital IB real.
    Solo trades confirmados por IB.
    """
    trades = _cargar_trades()
    pnl    = sum(
        _pnl_trade_usd(t)
        for t in trades
        if t.get("confirmado_ib", True) is not False
    )
    if pnl >= 0:
        return 0.0
    capital = get_capital_ib()
    if capital <= 0:
        return 0.0
    return round(abs(pnl) / capital * 100, 2)

# ── LLM SINTETIZADOR DE TESIS ─────────────────────────────────────────────────
def _enriquecer_con_llm(recomendaciones: list) -> list:
    """
    Post-proceso LLM sobre recomendaciones ya generadas por el motor cuantitativo.

    El LLM actúa como analista senior que:
      1. Reescribe la tesis en lenguaje claro y accionable
      2. Identifica riesgos que el pipeline cuantitativo puede no detectar
      3. Provee validación conceptual (CONFIRMAR / CUESTIONAR / RECHAZAR)

    Principios:
      - NO modifica conviction — el score cuantitativo es la fuente de verdad
      - NO bloquea señales — solo enriquece metadata para auditoría y log
      - Falla gracefully — si Groq no disponible, retorna lista sin cambios
      - Timeout implícito: Groq/LLaMA responde en ~2s; max_activos=3 → ~8s total
    """
    if not recomendaciones:
        return recomendaciones

    try:
        from engine.llm_signals import analizar_señales_llm
        # Solo analizar top 3 por convicción para no ralentizar el ciclo
        analisis = analizar_señales_llm(recomendaciones, max_activos=3)
        if not analisis:
            return recomendaciones

        for rec in recomendaciones:
            key = rec.get("ib_ticker") or rec.get("activo", "")
            if key not in analisis:
                continue
            llm = analisis[key]
            # Reemplazar tesis con versión mejorada (más clara y accionable)
            if llm.get("tesis_mejorada"):
                rec["tesis"] = llm["tesis_mejorada"]
            # Agregar metadata LLM — disponible en log y dashboard
            rec["llm_validacion"]    = llm.get("validacion", "CONFIRMAR")
            rec["llm_riesgos"]       = llm.get("riesgos_principales", [])
            rec["llm_catalizadores"] = llm.get("catalizadores", [])
            rec["llm_razonamiento"]  = llm.get("razonamiento", "")
    except Exception:
        pass  # Fail gracefully — nunca bloquear el ciclo por el LLM

    return recomendaciones


# ── UMBRAL ADAPTATIVO POR VIX ─────────────────────────────────────────────────
_vix_cache: dict = {"valor": None, "ts": 0.0}
_VIX_TTL = 900  # seg — refrescar cada 15 minutos

def _umbral_conviccion_efectivo() -> int:
    """
    Umbral de convicción ajustado al régimen de volatilidad actual (VIX).

    VIX < 15  →  75%   mercado calmo, umbral relajado
    VIX 15-25 →  78%   régimen normal (valor base PARAMS)
    VIX 25-35 →  82%   stress, exigir mayor convicción
    VIX > 35  →  85%   crisis, umbral máximo conservador

    Caché de 15 minutos para no llamar yfinance en cada validación.
    Fallback a PARAMS["conviccion_minima"] si no se puede leer VIX.

    Calibración (mayo 2026):
    - Los datos del log muestran 8-10 activos consistentemente en 75-77%
      con 3+ fuentes independientes. Umbral 78% bloqueaba el funnel completo
      en régimen normal, dejando solo SQM ejecutable.
    - VIX < 15: mercado muy calmo → 72% (permite alta frecuencia)
    - VIX 15-25: régimen normal → 75% (calibración principal)
    - VIX 25-35: stress → 80% (más exigente)
    - VIX > 35: crisis → 85% (solo señales muy fuertes)
    """
    global _vix_cache
    base = PARAMS["conviccion_minima"]
    try:
        ahora = time.time()
        if _vix_cache["valor"] is None or (ahora - _vix_cache["ts"]) > _VIX_TTL:
            fi = yf.Ticker("^VIX").fast_info
            vix_val = getattr(fi, "last_price", None)
            if vix_val and float(vix_val) > 0:
                _vix_cache = {"valor": float(vix_val), "ts": ahora}

        vix = _vix_cache.get("valor")
        if not vix:
            return base

        if vix < 15:
            return 72
        elif vix < 25:
            return 75   # era 78 — bloqueaba funnel en VIX normal
        elif vix < 35:
            return 80   # era 82
        else:
            return 85
    except Exception:
        return base


# ── VALIDAR SEÑAL ─────────────────────────────────────────────────────────────
def validar_señal(recomendacion, estado=None, posiciones_cache=None):
    """
    Valida si una señal cumple todos los criterios para ejecutarse automáticamente.
    Retorna (bool, razon)

    posiciones_cache: dict opcional {ticker: {...}} que incluye posiciones ya
    abiertas en este ciclo pero aún no escritas a posiciones.json. Permite
    prevenir el race condition intra-ciclo donde múltiples señales ven el JSON
    vacío y todas pasan los checks simultáneamente.
    """
    # Usar cache intra-ciclo si se provee; si no, leer el archivo.
    # La cache refleja el estado REAL durante el ciclo actual (incluye
    # posiciones abiertas en iteraciones anteriores del mismo ciclo).
    posiciones = posiciones_cache if posiciones_cache is not None else _cargar_posiciones()
    if estado is None:
        estado = _cargar_estado()
    ticker     = recomendacion.get("ib_ticker", "")
    conviccion = recomendacion.get("conviccion", 0)
    riesgo     = recomendacion.get("riesgo", 10)
    fuentes_list = recomendacion.get("fuentes", [])
    n_fuentes  = recomendacion.get("n_fuentes", len(fuentes_list))
    sector     = SECTORES.get(ticker, "Otros")

    # 0a. Blacklist explícita — futuros con nocional masivo
    # CL (WTI crude futures) ~$95k/contrato, HG (copper futures) ~$25k/contrato.
    if ticker in BLACKLIST_AUTO:
        return False, f"{ticker} en blacklist auto-trading (nocional masivo — operar manualmente)"

    # 0b. Universo ejecutable — filtro de liquidez IB
    # Acciones .SN chilenas de bajo peso IPSA tienen spread 1–3% en IB y fills
    # muy lentos. Solo activos con liquidez verificada pueden ejecutarse.
    try:
        from engine.universo import is_ejecutable
        if not is_ejecutable(ticker):
            return False, f"{ticker} fuera del universo ejecutable (liquidez insuficiente en IB)"
    except Exception:
        pass  # Si falla el import, no bloquear — continuar con otras validaciones

    # 1. Convicción mínima (umbral adaptativo por VIX)
    _umbral = _umbral_conviccion_efectivo()
    _vix_str = f"VIX={_vix_cache['valor']:.1f}" if _vix_cache.get("valor") else "VIX=N/D"
    if conviccion < _umbral:
        return False, f"Convicción {conviccion}% < umbral {_umbral}% ({_vix_str})"

    # 2. Riesgo máximo
    if riesgo > PARAMS["riesgo_maximo"]:
        return False, f"Riesgo {riesgo}/10 > máximo {PARAMS['riesgo_maximo']}/10"

    # 3. Fuentes mínimas
    if n_fuentes < PARAMS["fuentes_minimas"]:
        return False, f"Solo {n_fuentes} fuentes < mínimo {PARAMS['fuentes_minimas']}"

    # 3b. Diversidad de grupos de fuentes
    # Exige al menos MIN_GRUPOS_FUENTES grupos distintos (ej: técnico + sentimiento).
    # Previene señales puramente momentum donde AT + MTF + Correlaciones cuentan
    # como 3 fuentes independientes midiendo exactamente lo mismo (precio).
    grupos = _grupos_presentes(fuentes_list)
    if len(grupos) < MIN_GRUPOS_FUENTES:
        grupos_str = ", ".join(sorted(grupos)) if grupos else "ninguno"
        return False, (
            f"Diversidad insuficiente: {len(grupos)} grupo(s) [{grupos_str}] "
            f"< mínimo {MIN_GRUPOS_FUENTES} — señal puramente {grupos_str or 'sin clasificar'}"
        )

    # 3c. Al menos 1 fuente fast (timing)
    # Bloquea señales compuestas únicamente de fuentes lagging (13F trimestral,
    # Renta Fija semanal, Correlaciones, etc.) que no tienen información del
    # estado actual del mercado en el ciclo de ejecución.
    fast_presentes = FUENTES_FAST & set(fuentes_list)
    if len(fast_presentes) < MIN_FAST_SOURCES:
        slow_str = ", ".join(sorted(set(fuentes_list) & FUENTES_SLOW)) or "ninguna"
        return False, (
            f"Sin fuente de timing: solo slow sources [{slow_str}] — "
            f"requiere ≥{MIN_FAST_SOURCES} fuente fast (AT/MTF/ML/IV/OrderFlow/etc.)"
        )

    # 4. No duplicar ticker
    if ticker in posiciones:
        return False, f"Ya existe posición abierta en {ticker}"

    # 4b. Cooldown post-cierre — evita el loop de reapertura inmediata
    en_cd, razon_cd = _en_cooldown(estado, ticker)
    if en_cd:
        return False, razon_cd

    # 4c. Bloqueo same-day misma dirección tras pérdida
    # Si el ticker ya perdió hoy en la misma dirección, no re-entrar.
    # Ejemplo real: SQM COMPRAR SL a las 11:58 → re-entrada COMPRAR 12:58 → SL x2.
    # El cooldown de 4h suele cubrir esto, pero como segunda línea de defensa
    # se bloquea explícitamente durante todo el día calendario.
    accion_señal = recomendacion.get("accion", "")
    if _perdio_hoy_misma_direccion(ticker, accion_señal):
        return False, (
            f"{ticker} ya tuvo pérdida hoy en {accion_señal} — "
            f"bloqueado re-entrada misma dirección hasta mañana"
        )

    # 5. Máximo posiciones (incluye las abiertas en iteraciones previas del ciclo)
    if len(posiciones) >= PARAMS["max_posiciones"]:
        return False, f"Máximo {PARAMS['max_posiciones']} posiciones alcanzado"

    # 6. Máximo mismo sector (incluye posiciones abiertas en este ciclo)
    sector_count = sum(1 for t, p in posiciones.items()
                      if SECTORES.get(t, "Otros") == sector)
    if sector_count >= PARAMS["max_mismo_sector"]:
        return False, f"Máximo {PARAMS['max_mismo_sector']} posiciones en sector {sector}"

    # 6b. Máximo por bloque de correlación
    # Impide concentrar el portafolio en activos que responden al mismo factor macro.
    # Ejemplo: BSAC + BCH + SQM están todos en "Chile_macro" — si entran las 3,
    # el portafolio no diversifica, amplifca el drawdown si Chile cae.
    bloque = _bloque_de(ticker)
    if bloque:
        abiertas_en_bloque = sum(1 for t in posiciones if _bloque_de(t) == bloque)
        if abiertas_en_bloque >= PARAMS["max_por_bloque"]:
            return False, (
                f"Bloque correlado '{bloque}': {abiertas_en_bloque} posiciones ya abiertas "
                f"(máx {PARAMS['max_por_bloque']}) — {ticker} no añade diversificación"
            )

    # 7. Riesgo total — expresado en % del capital IB real
    riesgo_actual_pct = calcular_riesgo_total()  # retorna %
    if riesgo_actual_pct >= PARAMS["max_pct_riesgo_total"]:
        return False, (
            f"Riesgo total {riesgo_actual_pct:.1f}% del capital "
            f">= límite {PARAMS['max_pct_riesgo_total']:.0f}%"
        )

    # 8. SL obligatorio
    if not recomendacion.get("stop_loss"):
        return False, "Stop Loss no definido — orden no permitida"

    # 9. Precio disponible — obtener si no está disponible
    if not recomendacion.get("precio_actual"):
        try:
            import yfinance as yf
            from engine.universo import UNIVERSO_COMPLETO
            activo = recomendacion.get("activo", "")
            yf_ticker = activo if activo in UNIVERSO_COMPLETO else activo.replace("_LOCAL_SPREAD","")
            h = yf.Ticker(yf_ticker if yf_ticker != "BTC" else "BTC-USD").history(period="1d")
            if not h.empty:
                recomendacion["precio_actual"] = float(h["Close"].iloc[-1])
        except:
            pass
    if not recomendacion.get("precio_actual"):
        return False, "Precio actual no disponible"

    # 10. Ventana horaria de calidad de ejecución
    # Bloquea NUEVAS APERTURAS en open (9:30–10:00 ET) y pre-cierre (15:30–15:45 ET).
    # Los cierres SL/TP son gestionados por cierre_automatico.py y no pasan por aquí.
    tipo_activo = recomendacion.get("tipo", "ETF")
    bloqueado, razon_ventana = _en_ventana_bloqueada(tipo_activo)
    if bloqueado:
        return False, razon_ventana

    # 11. Filtro earnings — evitar entrar con anuncio de resultados en T-1 o T
    # Riesgo: gap overnight que salta el stop-loss; IV crush que invalida la señal.
    # Fail-open: si yfinance no responde o no hay datos, NO se bloquea la señal.
    # Solo aplica a acciones individuales (ADRs y Acción Chile) — no a ETFs ni Crypto.
    try:
        from engine.earnings_filter import tiene_earnings_proximos
        bloq_earn, razon_earn = tiene_earnings_proximos(ticker, tipo_activo)
        if bloq_earn:
            return False, razon_earn
    except Exception:
        pass  # fallo silencioso — no penalizar por indisponibilidad de datos

    return True, "OK"

# ── EJECUTAR SEÑAL AUTOMÁTICA ─────────────────────────────────────────────────
def ejecutar_señal_automatica(recomendacion):
    """
    Ejecuta una señal validada automáticamente en IB.
    """
    from engine.ib_executor import ejecutar_señales
    resultado = ejecutar_señales([recomendacion], modo_test=False)
    return resultado

# ── CICLO PRINCIPAL ───────────────────────────────────────────────────────────
def ciclo_trading_automatico():
    """
    Ciclo principal del motor automático.
    Se llama cada 15 minutos desde el scheduler.
    """
    estado = _cargar_estado()

    if not estado.get("activo"):
        return {"ejecutado": False, "razon": "Motor no activo"}

    if estado.get("pausado"):
        return {"ejecutado": False, "razon": f"Motor pausado: {estado.get('razon_pausa')}"}

    resultados = {
        "timestamp":   datetime.now().isoformat(),
        "aperturas":   [],
        "cierres":     [],
        "rechazadas":  [],
        "pausas":      [],
    }

    # ── SINCRONIZAR CON IB PRIMERO (fuente de verdad) ─────────────────────────
    # Elimina posiciones fantasma antes de cualquier cálculo de riesgo/capital.
    try:
        from engine.ib_executor import sincronizar_desde_ib
        sincronizar_desde_ib()
    except Exception as e:
        logging.warning(f"Sync IB al inicio del ciclo falló: {e}")

    # ── VERIFICAR CONDICIONES DE PAUSA
    pnl_dia = calcular_pnl_dia()
    pnl_dia_pct = (pnl_dia / get_capital_ib()) * 100
    if pnl_dia_pct <= PARAMS["pausa_pnl_dia_pct"]:
        razon = f"PnL del día {pnl_dia_pct:.2f}% < límite {PARAMS['pausa_pnl_dia_pct']}%"
        pausar_motor(razon)
        resultados["pausas"].append(razon)
        try:
            from engine.telegram_alertas import alerta_riesgo
            alerta_riesgo("PAUSA", razon, {"PnL día": f"{pnl_dia_pct:+.2f}%", "Límite": f"{PARAMS['pausa_pnl_dia_pct']}%"})
        except Exception:
            pass
        return resultados

    drawdown = calcular_drawdown_total()
    if drawdown >= PARAMS["max_drawdown_pct"]:
        razon = f"Drawdown {drawdown:.2f}% >= límite {PARAMS['max_drawdown_pct']}%"
        pausar_motor(razon)
        resultados["pausas"].append(razon)
        try:
            from engine.telegram_alertas import alerta_riesgo
            alerta_riesgo("DRAWDOWN", razon, {"Drawdown": f"{drawdown:.2f}%", "Límite": f"{PARAMS['max_drawdown_pct']}%"})
        except Exception:
            pass
        return resultados

    if estado.get("consecutivos_perdedor", 0) >= PARAMS["pausa_consecutivos"]:
        razon = f"{estado['consecutivos_perdedor']} trades consecutivos perdedores"
        pausar_motor(razon)
        resultados["pausas"].append(razon)
        try:
            from engine.telegram_alertas import alerta_riesgo
            alerta_riesgo("PAUSA", razon, {"Consecutivos perdedores": estado['consecutivos_perdedor']})
        except Exception:
            pass
        return resultados

    # ── CERRAR POSICIONES (SL/TP/Horizonte/Trailing) ─────────────────────────
    # Se ejecuta ANTES del check de horario para NYSE/Santiago porque:
    # • Crypto opera 24/7 — BTC/ETH deben tener SL/TP monitoreado en todo momento.
    # • Acciones: si el precio tocó SL/TP fuera de horario, detectamos el estado
    #   y ejecutamos el cierre al primer ciclo dentro de horario.
    # verificar_posiciones() respeta internamente el tipo de activo y horario de
    # exchange al enviar la orden real a IB.
    try:
        from engine.cierre_automatico import verificar_posiciones
        resumen_cierre = verificar_posiciones(modo_test=False, auto_cerrar=True)
        for c in resumen_cierre.get("cierres", []):
            resultados["cierres"].append(c)
            _registrar_evento("CIERRE", c.get("razon",""), c)
            logging.info(
                f"CIERRE: {c['ticker']} | {c['razon']} | PnL {c.get('pnl_pct',0):+.2f}% "
                f"| IB={'OK' if c.get('confirmado_ib') else 'NO CONFIRMADO'}"
            )

            # Registrar cooldown para este ticker — evita reapertura inmediata en el
            # siguiente ciclo (causa del loop COPEC 23x / BTC 14x).
            # Se aplica a TODOS los cierres, independientemente de confirmación IB.
            ticker_cerrado = c.get("ticker", "")
            if ticker_cerrado:
                _fue_perdedor = c.get("confirmado_ib", False) and c.get("pnl_pct", 0) < 0
                _registrar_cierre_cooldown(estado, ticker_cerrado, fue_perdedor=_fue_perdedor)
                if _fue_perdedor:
                    logging.info(f"COOLDOWN+BAN DÍA: {ticker_cerrado} perdió hoy — sin re-entrada hasta mañana")
                else:
                    logging.info(f"COOLDOWN: {ticker_cerrado} bloqueado {COOLDOWN_MINUTOS} min")

            # Feedback loop: vincula APERTURA (evidencia fuentes) ↔ CIERRE (PnL).
            # Solo para trades confirmados por IB — no registrar cierres fantasma.
            if c.get("confirmado_ib", False) and ticker_cerrado:
                try:
                    from engine.feedback_loop import (
                        registrar_cierre_con_contexto,
                        actualizar_kelly_live,
                    )
                    registrar_cierre_con_contexto(
                        ib_ticker=ticker_cerrado,
                        pnl_pct=c.get("pnl_pct", 0),
                        razon=c.get("razon", ""),
                        precio_salida=c.get("precio_actual"),
                        confirmado_ib=True,
                    )
                    actualizar_kelly_live(min_trades=3)
                except Exception as _fe:
                    logging.warning(f"Feedback loop (no crítico): {_fe}")

            # Actualizar consecutivos perdedores SOLO si IB confirmó el cierre.
            # Un cierre no confirmado por IB no es un trade real — ignorar para
            # evitar que posiciones fantasma activen la pausa del motor.
            if c.get("confirmado_ib", False):
                if c.get("pnl_pct", 0) < 0:
                    estado["consecutivos_perdedor"] = estado.get("consecutivos_perdedor", 0) + 1
                else:
                    estado["consecutivos_perdedor"] = 0
    except Exception as e:
        logging.error(f"Error en cierre automático: {e}")

    # ── VERIFICAR HORARIO (informativo — NO retorna) ──────────────────────────
    # El filtro real se aplica por-activo en el bucle de recomendaciones (línea ~1169)
    # donde es_horario_mercado(tipo_activo) filtra NYSE/Santiago pero permite Crypto 24/7.
    # Retornar aquí habría bloqueado BTC-USD en fines de semana y noches.
    en_horario, msg_horario = es_horario_mercado()
    if not en_horario:
        logging.info(f"Fuera de horario NYSE: {msg_horario} — solo activos 24/7 son elegibles")

    # ── PIRÁMIDE: escalar posiciones ganadoras (antes de buscar aperturas nuevas)
    try:
        from engine.piramide import verificar_y_ejecutar_piramide
        _pirs = verificar_y_ejecutar_piramide()
        for _p in _pirs:
            _log_desc = (
                f"Pirámide {_p['accion']} +{_p['cantidad']}x {_p['ib_ticker']} "
                f"@ {_p.get('precio_actual', 0):.4f} | "
                f"PnL entrada {_p.get('pnl_pct', 0):+.2f}% | "
                f"SL→breakeven {_p.get('sl_nuevo', 0):.4f}"
            )
            estado_pir = "PIRAMIDE_OK" if _p["ok"] else "PIRAMIDE_ERROR"
            _registrar_evento(estado_pir, _log_desc, _p)
            resultados["aperturas"].append({**_p, "tipo": "PIRAMIDE"})
            if not _p["ok"]:
                logging.warning(f"Pirámide fallida {_p['ib_ticker']}: {_p.get('error')}")
    except Exception as _pe:
        logging.warning(f"Módulo pirámide (no crítico): {_pe}")

    # ── ABRIR POSICIONES NUEVAS
    try:
        from engine.data_loader import get_datos_para_motor
        from engine.recomendaciones import consolidar_señales, generar_recomendaciones

        # Cargar las 19 fuentes en paralelo — misma base que el dashboard
        datos = get_datos_para_motor(verbose=False)
        activos = consolidar_señales(
            datos["poly_df"],
            datos["kalshi_list"],
            datos["macro_corr"],
            datos["noticias"],
            fear_greed=datos.get("fear_greed"),
            cmf_hechos=datos.get("cmf_hechos"),
            vol_alertas=datos.get("vol_alertas"),
            put_call=datos.get("put_call"),
            analisis_tecnico=datos.get("analisis_tecnico"),
            google_trends=datos.get("google_trends"),
            ib_data=datos.get("ib_data"),
            mercado_local=datos.get("mercado_local"),
            renta_fija=datos.get("renta_fija"),
            mtf=datos.get("mtf"),
            sec_13f=datos.get("sec_13f"),
            order_flow=datos.get("order_flow"),
            correlaciones=datos.get("correlaciones"),
            iv_opciones=datos.get("iv_opciones"),
            ml=datos.get("ml"),
            momentum=datos.get("momentum"),
        )
        recomendaciones = generar_recomendaciones(activos)
        recomendaciones = _enriquecer_con_llm(recomendaciones)  # tesis + riesgos via LLM

        meta = datos.get("meta", {})
        logging.info(
            f"Fuentes cargadas: {len([k for k,v in datos.items() if v is not None and k != 'meta'])} | "
            f"Errores: {list(meta.get('errores', {}).keys()) or 'ninguno'} | "
            f"Tiempo: {meta.get('t_total', '?')}s"
        )

        # ── SOURCE HEALTH MONITOR: registrar estado de fuentes por ciclo ─────
        try:
            from engine.source_health import registrar_ciclo_fuentes
            _sh = registrar_ciclo_fuentes(datos, meta.get("errores", {}))
            if _sh.get("alertas"):
                for _f, _e, _c in _sh["alertas"]:
                    logging.warning(
                        f"[SourceHealth] ⚠ '{_f}' sin datos {_c} ciclos consecutivos ({_e})"
                    )
        except Exception as _she:
            logging.warning(f"Source health monitor (no crítico): {_she}")

        # ── CACHE INTRA-CICLO: previene race condition ────────────────────────────
        # Se inicializa con el estado REAL de IB (ya sincronizado arriba).
        # Después de cada apertura exitosa se inserta el ticker con un dict mínimo,
        # de modo que las señales siguientes del mismo ciclo ven el slot ocupado
        # aunque posiciones.json aún no se haya escrito.
        _posiciones_ciclo = _cargar_posiciones()

        for r in recomendaciones:
            # Check de horario por tipo de activo específico
            tipo_activo = r.get("tipo", "ETF")
            en_horario_activo, msg_horario_activo = es_horario_mercado(tipo_activo)
            if not en_horario_activo:
                resultados["rechazadas"].append({
                    "ticker": r.get("ib_ticker", ""),
                    "razon":  f"Fuera de horario ({tipo_activo}): {msg_horario_activo}",
                })
                continue

            # Pasar cache intra-ciclo: incluye posiciones ya abiertas este ciclo
            valida, razon = validar_señal(r, estado=estado, posiciones_cache=_posiciones_ciclo)
            if valida:
                # Alerta señal detectada antes de intentar ejecutar
                try:
                    from engine.telegram_alertas import alerta_señal_detectada
                    alerta_señal_detectada(r)
                except Exception:
                    pass

                logging.info(f"APERTURA: {r['accion']} {r['ib_ticker']} | Conv {r['conviccion']}% | Riesgo {r['riesgo']}/10")
                resultado = ejecutar_señal_automatica(r)
                if resultado.get("ordenes_enviadas"):
                    orden     = resultado["ordenes_enviadas"][0]
                    cantidad  = orden.get("cantidad", 0)
                    precio    = orden.get("precio", r.get("precio_actual", 0))
                    monto_usd = round(cantidad * precio, 0)
                    orden_id  = orden.get("orden_id")

                    # ── Actualizar cache intra-ciclo INMEDIATAMENTE ──────────
                    # Esto impide que el siguiente r en este mismo ciclo vea
                    # el slot vacío y abra una segunda posición sobre el mismo
                    # ticker o que exceda max_posiciones.
                    _posiciones_ciclo[r["ib_ticker"]] = {
                        "accion":        r["accion"],
                        "precio_entrada": precio,
                        "cantidad":      cantidad,
                        "sl":            r.get("stop_loss"),
                        "tipo":          r.get("tipo", "ETF"),
                        "_intra_ciclo":  True,  # marcador de trazabilidad
                    }

                    resultados["aperturas"].append({
                        "ticker":        r["ib_ticker"],
                        "accion":        r["accion"],
                        "conviccion":    r["conviccion"],
                        "riesgo":        r["riesgo"],
                        "confirmado_ib": True,
                        "orden_id":      orden_id,
                        "cantidad":      cantidad,
                        "precio":        precio,
                        "monto_usd":     monto_usd,
                    })
                    # Log con confirmado_ib=True y datos de ejecución real
                    _registrar_evento("APERTURA", f"{r['accion']} {r['ib_ticker']}", {
                        **r,
                        "confirmado_ib": True,
                        "orden_id":      orden_id,
                        "cantidad":      cantidad,
                        "precio":        precio,
                        "monto_usd":     monto_usd,
                    })
                    estado["ordenes_hoy"] = estado.get("ordenes_hoy", 0) + 1

                    # Alerta Telegram — orden ejecutada con confirmación IB
                    try:
                        from engine.telegram_alertas import alerta_orden_ejecutada
                        alerta_orden_ejecutada(r, cantidad, monto_usd)
                    except Exception:
                        pass
                else:
                    # ejecutar_señales() retorna {"ordenes_enviadas":[], "errores":[{...}], "total":0}
                    # El error real está en errores[0]["error"], no en el nivel raíz del dict.
                    _errores_ib = resultado.get("errores", [])
                    error_ib    = _errores_ib[0]["error"] if _errores_ib else resultado.get("error", "sin detalle")
                    logging.warning(f"APERTURA FALLIDA: {r['ib_ticker']} — {error_ib}")
                    # Loguear intento fallido para trazabilidad
                    _registrar_evento("APERTURA_FALLIDA", f"{r['accion']} {r['ib_ticker']}", {
                        **r,
                        "confirmado_ib": False,
                        "error_ib":      error_ib,
                    })
                    try:
                        from engine.telegram_alertas import alerta_riesgo
                        alerta_riesgo("ERROR", f"Apertura fallida: {r['accion']} {r['ib_ticker']}", {"Error": error_ib, "Convicción": f"{r['conviccion']}%"})
                    except Exception:
                        pass
            else:
                resultados["rechazadas"].append({
                    "ticker":    r.get("ib_ticker", ""),
                    "accion":    r.get("accion", ""),
                    "conviccion": r.get("conviccion", 0),
                    "razon":     razon,
                })
                logging.info(
                    f"RECHAZADA: {r.get('ib_ticker','')} ({r.get('accion','')}) "
                    f"conv={r.get('conviccion',0)}% — {razon}"
                )
                # Persistir en log para visibilidad en dashboard
                _registrar_evento("RECHAZADA", f"{r.get('accion','')} {r.get('ib_ticker','')}", {
                    "ticker":     r.get("ib_ticker", ""),
                    "activo":     r.get("activo", ""),
                    "accion":     r.get("accion", ""),
                    "razon":      razon,
                    "conviccion": r.get("conviccion", 0),
                    "n_fuentes":  r.get("n_fuentes", 0),
                    "riesgo":     r.get("riesgo", 0),
                    "fuentes":    r.get("fuentes", []),
                })

    except Exception as e:
        logging.error(f"Error en apertura automática: {e}", exc_info=True)

    estado["ultima_verificacion"] = datetime.now().isoformat()
    estado["pnl_dia"]             = pnl_dia
    _guardar_estado(estado)

    logging.info(f"Ciclo completado: {len(resultados['aperturas'])} aperturas, {len(resultados['cierres'])} cierres")
    return resultados

# ── RESUMEN DEL MOTOR ─────────────────────────────────────────────────────────
def get_resumen_motor():
    """Retorna resumen del estado del motor para el dashboard"""
    estado     = _cargar_estado()
    posiciones = _cargar_posiciones()
    trades     = _cargar_trades()
    log        = get_log_auto(10)

    pnl_dia    = calcular_pnl_dia()
    drawdown   = calcular_drawdown_total()
    riesgo     = calcular_riesgo_total()

    en_horario, msg_horario = es_horario_mercado()

    return {
        "activo":              estado.get("activo", False),
        "pausado":             estado.get("pausado", False),
        "razon_pausa":         estado.get("razon_pausa"),
        "en_horario":          en_horario,
        "msg_horario":         msg_horario,
        "posiciones_abiertas": len(posiciones),
        "max_posiciones":      PARAMS["max_posiciones"],
        "capital_ib":          round(get_capital_ib(), 0),
        "riesgo_total_pct":    round(riesgo, 2),       # % del capital IB
        "max_riesgo_pct":      PARAMS["max_pct_riesgo_total"],
        "pnl_dia":             round(pnl_dia, 2),
        "pnl_dia_pct":         round((pnl_dia / get_capital_ib()) * 100, 2),
        "drawdown_pct":        round(drawdown, 2),
        "consecutivos_perdedor": estado.get("consecutivos_perdedor", 0),
        "ordenes_hoy":         estado.get("ordenes_hoy", 0),
        "ultima_verificacion": estado.get("ultima_verificacion"),
        "trades_totales":      len(trades),
        "log_reciente":        log[:5],
        "params":              PARAMS,
    }

if __name__ == "__main__":
    print("=== MOTOR AUTOMÁTICO — TEST ===\n")
    resumen = get_resumen_motor()
    print(f"Estado: {'ACTIVO' if resumen['activo'] else 'INACTIVO'}")
    print(f"Pausado: {'SÍ — '+resumen['razon_pausa'] if resumen['pausado'] else 'NO'}")
    print(f"Horario: {resumen['msg_horario']}")
    print(f"Posiciones: {resumen['posiciones_abiertas']}/{resumen['max_posiciones']}")
    _cap = resumen.get("capital_ib", 100_000)
    print(f"Riesgo total: {resumen['riesgo_total_pct']:.1f}% (${_cap * resumen['riesgo_total_pct'] / 100:,.0f}) / límite {resumen['max_riesgo_pct']:.0f}%")
    print(f"PnL día: USD {resumen['pnl_dia']:+,.2f} ({resumen['pnl_dia_pct']:+.2f}%)")
    print(f"Drawdown: {resumen['drawdown_pct']:.2f}%")
    print(f"Consecutivos perdedores: {resumen['consecutivos_perdedor']}")
    print(f"\nParámetros activos:")
    for k, v in PARAMS.items():
        print(f"  {k}: {v}")
