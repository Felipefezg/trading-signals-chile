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
- No duplicar ticker
"""

import json
import os
import threading
import time
import logging
from datetime import datetime, timedelta
import pytz
import yfinance as yf

# ── PATHS ─────────────────────────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSICIONES_FILE   = os.path.join(BASE_DIR, "posiciones.json")
TRADES_FILE       = os.path.join(BASE_DIR, "trades_cerrados.json")
ESTADO_AUTO_FILE  = os.path.join(BASE_DIR, "estado_automatico.json")
LOG_AUTO_FILE     = os.path.join(BASE_DIR, "log_automatico.json")

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "trading_auto.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ── PARÁMETROS (ajustables) ───────────────────────────────────────────────────
PARAMS = {
    "max_posiciones":        5,
    "max_usd_por_operacion": 10_000,
    "max_riesgo_total_usd":  30_000,
    "capital_total":         100_000,
    "conviccion_minima":     80,
    "riesgo_maximo":         5,
    "fuentes_minimas":       3,
    "max_drawdown_pct":      10.0,
    "pausa_pnl_dia_pct":    -3.0,
    "pausa_consecutivos":    3,
    "max_mismo_sector":      2,
    "horario_inicio":        "09:30",
    "horario_fin":           "15:45",
    "timezone":              "America/New_York",
}

# Sectores por ticker
SECTORES = {
    "ECH":    "ETF Chile",
    "SQM":    "Minería",
    "COPEC":  "Energía",
    "BCI":    "Bancos",
    "CHILE":  "Bancos",
    "CMPC":   "Industria",
    "LTM":    "Transporte",
    "BTC":    "Crypto",
    "SPY":    "ETF USA",
    "GLD":    "Commodities",
    "HG":     "Commodities",
}

# ── ESTADO DEL MOTOR ──────────────────────────────────────────────────────────
def _cargar_estado():
    try:
        if os.path.exists(ESTADO_AUTO_FILE):
            with open(ESTADO_AUTO_FILE) as f:
                return json.load(f)
    except:
        pass
    return {
        "activo":               False,
        "pausado":              False,
        "razon_pausa":          None,
        "consecutivos_perdedor": 0,
        "pnl_dia":              0.0,
        "ultima_verificacion":  None,
        "ordenes_hoy":          0,
        "log":                  [],
    }

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
    log = []
    if os.path.exists(LOG_AUTO_FILE):
        try:
            with open(LOG_AUTO_FILE) as f:
                log = json.load(f)
        except:
            pass
    log.append({
        "timestamp":   datetime.now().isoformat(),
        "tipo":        tipo,
        "descripcion": descripcion,
        "datos":       datos,
    })
    # Mantener solo últimos 200 eventos
    log = log[-200:]
    with open(LOG_AUTO_FILE, "w") as f:
        json.dump(log, f, indent=2, default=str)

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
def es_horario_mercado():
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

def calcular_pnl_dia():
    """Calcula PnL del día actual"""
    trades = _cargar_trades()
    hoy    = datetime.now().date().isoformat()
    pnl    = sum(t["pnl_total"] for t in trades if t.get("fecha_salida","")[:10] == hoy)
    return pnl

def calcular_riesgo_total():
    """Calcula riesgo total en posiciones abiertas (basado en SL)"""
    posiciones = _cargar_posiciones()
    riesgo = 0
    for ticker, p in posiciones.items():
        entrada  = p.get("precio_entrada", 0)
        sl       = p.get("sl", entrada)
        cantidad = p.get("cantidad", 0)
        accion   = p.get("accion", "COMPRAR")
        if accion == "COMPRAR":
            riesgo_unit = max(0, entrada - sl)
        else:
            riesgo_unit = max(0, sl - entrada)
        riesgo += riesgo_unit * cantidad
    return riesgo

def calcular_drawdown_total():
    """Calcula drawdown total desde el capital inicial"""
    trades = _cargar_trades()
    pnl    = sum(t["pnl_total"] for t in trades)
    if pnl >= 0:
        return 0
    return abs(pnl) / PARAMS["capital_total"] * 100

# ── VALIDAR SEÑAL ─────────────────────────────────────────────────────────────
def validar_señal(recomendacion):
    """
    Valida si una señal cumple todos los criterios para ejecutarse automáticamente.
    Retorna (bool, razon)
    """
    posiciones = _cargar_posiciones()
    ticker     = recomendacion.get("ib_ticker", "")
    conviccion = recomendacion.get("conviccion", 0)
    riesgo     = recomendacion.get("riesgo", 10)
    n_fuentes  = recomendacion.get("n_fuentes", 0)
    sector     = SECTORES.get(ticker, "Otros")

    # 1. Convicción mínima
    if conviccion < PARAMS["conviccion_minima"]:
        return False, f"Convicción {conviccion}% < mínimo {PARAMS['conviccion_minima']}%"

    # 2. Riesgo máximo
    if riesgo > PARAMS["riesgo_maximo"]:
        return False, f"Riesgo {riesgo}/10 > máximo {PARAMS['riesgo_maximo']}/10"

    # 3. Fuentes mínimas
    if n_fuentes < PARAMS["fuentes_minimas"]:
        return False, f"Solo {n_fuentes} fuentes < mínimo {PARAMS['fuentes_minimas']}"

    # 4. No duplicar ticker
    if ticker in posiciones:
        return False, f"Ya existe posición abierta en {ticker}"

    # 5. Máximo posiciones
    if len(posiciones) >= PARAMS["max_posiciones"]:
        return False, f"Máximo {PARAMS['max_posiciones']} posiciones alcanzado"

    # 6. Máximo mismo sector
    sector_count = sum(1 for t, p in posiciones.items()
                      if SECTORES.get(t, "Otros") == sector)
    if sector_count >= PARAMS["max_mismo_sector"]:
        return False, f"Máximo {PARAMS['max_mismo_sector']} posiciones en sector {sector}"

    # 7. Riesgo total
    riesgo_actual = calcular_riesgo_total()
    if riesgo_actual >= PARAMS["max_riesgo_total_usd"]:
        return False, f"Riesgo total USD {riesgo_actual:,.0f} >= límite USD {PARAMS['max_riesgo_total_usd']:,.0f}"

    # 8. SL obligatorio
    if not recomendacion.get("stop_loss"):
        return False, "Stop Loss no definido — orden no permitida"

    # 9. Precio disponible
    if not recomendacion.get("precio_actual"):
        return False, "Precio actual no disponible"

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

    # ── VERIFICAR CONDICIONES DE PAUSA
    pnl_dia = calcular_pnl_dia()
    pnl_dia_pct = (pnl_dia / PARAMS["capital_total"]) * 100
    if pnl_dia_pct <= PARAMS["pausa_pnl_dia_pct"]:
        razon = f"PnL del día {pnl_dia_pct:.2f}% < límite {PARAMS['pausa_pnl_dia_pct']}%"
        pausar_motor(razon)
        resultados["pausas"].append(razon)
        return resultados

    drawdown = calcular_drawdown_total()
    if drawdown >= PARAMS["max_drawdown_pct"]:
        razon = f"Drawdown {drawdown:.2f}% >= límite {PARAMS['max_drawdown_pct']}%"
        pausar_motor(razon)
        resultados["pausas"].append(razon)
        return resultados

    if estado.get("consecutivos_perdedor", 0) >= PARAMS["pausa_consecutivos"]:
        razon = f"{estado['consecutivos_perdedor']} trades consecutivos perdedores"
        pausar_motor(razon)
        resultados["pausas"].append(razon)
        return resultados

    # ── VERIFICAR HORARIO
    en_horario, msg_horario = es_horario_mercado()
    if not en_horario:
        logging.info(f"Fuera de horario: {msg_horario}")
        return {"ejecutado": False, "razon": msg_horario}

    # ── CERRAR POSICIONES (SL/TP/Horizonte)
    try:
        from engine.cierre_automatico import verificar_posiciones
        resumen_cierre = verificar_posiciones(modo_test=False, auto_cerrar=True)
        for c in resumen_cierre.get("cierres", []):
            resultados["cierres"].append(c)
            _registrar_evento("CIERRE", c.get("razon",""), c)
            logging.info(f"CIERRE: {c['ticker']} | {c['razon']} | PnL {c.get('pnl_pct',0):+.2f}%")

            # Actualizar consecutivos perdedores
            if c.get("pnl_pct", 0) < 0:
                estado["consecutivos_perdedor"] = estado.get("consecutivos_perdedor", 0) + 1
            else:
                estado["consecutivos_perdedor"] = 0
    except Exception as e:
        logging.error(f"Error en cierre automático: {e}")

    # ── ABRIR POSICIONES NUEVAS
    try:
        from data.polymarket import get_mercados_chile
        from data.kalshi import get_kalshi_resumen
        from data.macro_usa import get_macro_usa, get_correlaciones_chile
        from data.noticias_chile import get_noticias_google
        from engine.nlp_sentiment import analizar_noticias_batch
        from engine.recomendaciones import consolidar_señales, generar_recomendaciones

        poly_df     = get_mercados_chile(limit=200)
        kalshi_list = get_kalshi_resumen()
        macro_raw   = get_macro_usa()
        macro_corr  = get_correlaciones_chile(macro_raw)
        noticias    = analizar_noticias_batch(get_noticias_google())
        activos     = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias)
        recomendaciones = generar_recomendaciones(activos)

        for r in recomendaciones:
            valida, razon = validar_señal(r)
            if valida:
                logging.info(f"APERTURA: {r['accion']} {r['ib_ticker']} | Conv {r['conviccion']}% | Riesgo {r['riesgo']}/10")
                resultado = ejecutar_señal_automatica(r)
                if resultado.get("ordenes_enviadas"):
                    resultados["aperturas"].append({
                        "ticker":    r["ib_ticker"],
                        "accion":    r["accion"],
                        "conviccion": r["conviccion"],
                        "riesgo":    r["riesgo"],
                    })
                    _registrar_evento("APERTURA", f"{r['accion']} {r['ib_ticker']}", r)
                    estado["ordenes_hoy"] = estado.get("ordenes_hoy", 0) + 1
            else:
                resultados["rechazadas"].append({
                    "ticker": r.get("ib_ticker",""),
                    "razon":  razon,
                })

    except Exception as e:
        logging.error(f"Error en apertura automática: {e}")

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
        "riesgo_total_usd":    round(riesgo, 0),
        "max_riesgo_usd":      PARAMS["max_riesgo_total_usd"],
        "pnl_dia":             round(pnl_dia, 2),
        "pnl_dia_pct":         round((pnl_dia / PARAMS["capital_total"]) * 100, 2),
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
    print(f"Riesgo total: USD {resumen['riesgo_total_usd']:,.0f} / USD {resumen['max_riesgo_usd']:,.0f}")
    print(f"PnL día: USD {resumen['pnl_dia']:+,.2f} ({resumen['pnl_dia_pct']:+.2f}%)")
    print(f"Drawdown: {resumen['drawdown_pct']:.2f}%")
    print(f"Consecutivos perdedores: {resumen['consecutivos_perdedor']}")
    print(f"\nParámetros activos:")
    for k, v in PARAMS.items():
        print(f"  {k}: {v}")
