"""
Signal Feedback Loop — engine/feedback_loop.py

Registra el outcome real de cada trade vinculando:
  APERTURA (evidencia de fuentes, convicción) ↔ CIERRE (PnL, razón)

Uso de los datos:
  - calcular_stats_por_fuente(): win_rate y EV por fuente → recalibrar pesos
  - calcular_stats_por_ticker(): win_rate y R/R por ticker → Kelly stats reales
  - actualizar_kelly_live():     escribe data/kelly_stats_live.json sin tocar código
  - get_resumen_feedback():      resumen para el dashboard

Diseño: no modifica código fuente en runtime.
  kelly_stats_live.json tiene prioridad sobre KELLY_STATS hardcodeado en kelly_sizing.py
  cuando n_trades >= MIN_TRADES_STATS para ese ticker.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTCOMES_FILE   = os.path.join(BASE_DIR, "data", "trade_outcomes.json")
KELLY_LIVE_FILE = os.path.join(BASE_DIR, "data", "kelly_stats_live.json")
LOG_FILE           = os.path.join(BASE_DIR, "log_automatico.json")
LOG_APERTURAS_FILE = os.path.join(BASE_DIR, "log_aperturas.json")

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)


# ── STORAGE ───────────────────────────────────────────────────────────────────

def _cargar_outcomes(excluir_artefactos: bool = True) -> List[dict]:
    """
    Carga trade_outcomes.json.

    Args:
        excluir_artefactos: si True (default), omite registros marcados con
                            _excluir_stats=True (p.ej. bug CLP/USD en BSAC).
    """
    try:
        if os.path.exists(OUTCOMES_FILE):
            with open(OUTCOMES_FILE) as f:
                data = json.load(f)
            if excluir_artefactos:
                data = [o for o in data if not o.get("_excluir_stats", False)]
            return data
    except Exception:
        pass
    return []


def _guardar_outcomes(outcomes: List[dict]):
    with open(OUTCOMES_FILE, "w") as f:
        json.dump(outcomes, f, indent=2, default=str)


# ── VINCULACIÓN APERTURA ↔ CIERRE ────────────────────────────────────────────

def _buscar_apertura_en_log(ib_ticker: str) -> Optional[dict]:
    """
    Busca la última APERTURA confirmada por IB para ib_ticker.
    Busca primero en log_aperturas.json (fuente dedicada, nunca desplazada)
    y cae al log general log_automatico.json como fallback.
    """
    def _buscar_en(filepath: str) -> Optional[dict]:
        try:
            with open(filepath) as f:
                log = json.load(f)
        except Exception:
            return None
        for evento in reversed(log):
            if (
                evento.get("tipo") == "APERTURA"
                and evento.get("datos", {}).get("ib_ticker") == ib_ticker
                and evento.get("datos", {}).get("confirmado_ib", False)
            ):
                return evento
        return None

    # Primero el log dedicado (prioritario — nunca truncado por RECHAZADA)
    resultado = _buscar_en(LOG_APERTURAS_FILE)
    if resultado:
        return resultado

    # Fallback al log general (útil para trades previos a este fix)
    return _buscar_en(LOG_FILE)


def registrar_cierre_con_contexto(
    ib_ticker:    str,
    pnl_pct:      float,
    razon:        str,
    precio_salida: Optional[float] = None,
    confirmado_ib: bool = True,
) -> bool:
    """
    Registra el outcome de un trade vinculando apertura + cierre.
    Llamar desde motor_automatico.py en el bloque de cierre, solo si confirmado_ib=True.

    Returns True si se registró correctamente.
    """
    if not confirmado_ib:
        return False  # No registrar cierres no confirmados por IB

    apertura = _buscar_apertura_en_log(ib_ticker)
    resultado = "GANADOR" if pnl_pct > 0 else "PERDEDOR"

    datos_ap = apertura.get("datos", {}) if apertura else {}

    fecha_cierre_dt   = datetime.now()
    fecha_apertura_ts = apertura.get("timestamp") if apertura else None

    # Sanity check: pnl_pct absurdo = posible bug CLP/USD
    # Si |pnl| > 30% y el trade duró < 10 min → marcar automáticamente como artefacto.
    # Umbral 30%: el máximo teórico en un trade real con TP=4xATR y SL=2xATR es ~20%.
    es_artefacto = False
    nota_artefacto = ""
    if abs(pnl_pct) > 30:
        duracion_s = 9999
        if fecha_apertura_ts:
            try:
                dt_ap = datetime.fromisoformat(fecha_apertura_ts)
                duracion_s = (fecha_cierre_dt - dt_ap).total_seconds()
            except Exception:
                pass
        if duracion_s < 600:  # < 10 minutos
            es_artefacto   = True
            nota_artefacto = (
                f"pnl={pnl_pct:+.1f}% en {duracion_s:.0f}s — "
                f"sospechoso bug CLP/USD (precio_entrada en una moneda, "
                f"precio_actual en otra). Revisar get_precio_actual({ib_ticker})."
            )
            logging.warning(
                f"[feedback] ARTEFACTO AUTO-DETECTADO: {ib_ticker} "
                f"pnl={pnl_pct:+.1f}% en {duracion_s:.0f}s → _excluir_stats=True"
            )

    outcome = {
        "ib_ticker":      ib_ticker,
        "fecha_cierre":   fecha_cierre_dt.isoformat(),
        "fecha_apertura": fecha_apertura_ts,
        "accion":         datos_ap.get("accion"),
        "activo":         datos_ap.get("activo", ib_ticker),
        "tipo":           datos_ap.get("tipo"),
        "precio_entrada": datos_ap.get("precio_actual"),
        "precio_salida":  precio_salida,
        "pnl_pct":        round(pnl_pct, 4),
        "resultado":      resultado,
        "razon_cierre":   razon,
        "conviccion":     datos_ap.get("conviccion"),
        "n_fuentes":      datos_ap.get("n_fuentes", 0),
        "fuentes":        datos_ap.get("fuentes", []),
        "evidencia":      datos_ap.get("evidencia", []),
        "tesis":          datos_ap.get("tesis"),
    }

    if es_artefacto:
        outcome["_artefacto"]    = f"PNL_ABSURDO_{fecha_cierre_dt.strftime('%Y-%m-%d')}"
        outcome["_excluir_stats"] = True
        outcome["_nota"]         = nota_artefacto

    # _cargar_outcomes(excluir_artefactos=False) para no perder el historial completo
    outcomes = _cargar_outcomes(excluir_artefactos=False)
    outcomes.append(outcome)
    _guardar_outcomes(outcomes)

    logging.info(
        f"Feedback: {ib_ticker} {resultado} PnL={pnl_pct:+.2f}% "
        f"razon={razon} fuentes={datos_ap.get('fuentes', [])}"
    )
    return True


# ── ANÁLISIS POR FUENTE ───────────────────────────────────────────────────────

def calcular_stats_por_fuente(min_trades: int = 3) -> List[dict]:
    """
    Calcula win_rate, R/R y EV por fuente de señal.
    Solo para fuentes con al menos min_trades registros.
    Retorna lista ordenada por EV descendente.
    """
    outcomes = _cargar_outcomes()
    if not outcomes:
        return []

    stats: Dict[str, dict] = {}

    for outcome in outcomes:
        for fuente in outcome.get("fuentes", []):
            if fuente not in stats:
                stats[fuente] = {
                    "n": 0, "wins": 0,
                    "pnl_ganadores": [], "pnl_perdedores": [],
                }
            s = stats[fuente]
            s["n"] += 1
            pnl = outcome.get("pnl_pct", 0)
            if outcome.get("resultado") == "GANADOR":
                s["wins"] += 1
                s["pnl_ganadores"].append(abs(pnl))
            else:
                s["pnl_perdedores"].append(abs(pnl))

    resultado = []
    for fuente, s in stats.items():
        if s["n"] < min_trades:
            continue
        win_rate = s["wins"] / s["n"]
        avg_gan  = sum(s["pnl_ganadores"]) / len(s["pnl_ganadores"]) if s["pnl_ganadores"] else 0
        avg_per  = sum(s["pnl_perdedores"]) / len(s["pnl_perdedores"]) if s["pnl_perdedores"] else 1
        rr       = round(avg_gan / avg_per, 2) if avg_per > 0 else 0
        ev       = round(win_rate * avg_gan - (1 - win_rate) * avg_per, 3)
        kelly    = round(win_rate - (1 - win_rate) / rr, 3) if rr > 0 else -1

        resultado.append({
            "fuente":    fuente,
            "n_trades":  s["n"],
            "win_rate":  round(win_rate, 3),
            "avg_gan":   round(avg_gan, 3),
            "avg_per":   round(avg_per, 3),
            "rr":        rr,
            "ev":        ev,
            "kelly_full": kelly,
        })

    return sorted(resultado, key=lambda x: -x["ev"])


# ── ANÁLISIS POR TICKER ───────────────────────────────────────────────────────

def calcular_stats_por_ticker(min_trades: int = 3) -> Dict[str, dict]:
    """
    Calcula win_rate y R/R por IB ticker a partir de trades reales.
    Retorna dict compatible con KELLY_STATS en kelly_sizing.py.
    """
    outcomes = _cargar_outcomes()
    if not outcomes:
        return {}

    raw: Dict[str, dict] = {}

    for outcome in outcomes:
        ticker = outcome.get("ib_ticker")
        if not ticker:
            continue
        if ticker not in raw:
            raw[ticker] = {"wins": 0, "n": 0, "pnl_ganadores": [], "pnl_perdedores": []}
        s = raw[ticker]
        s["n"] += 1
        pnl = outcome.get("pnl_pct", 0)
        if outcome.get("resultado") == "GANADOR":
            s["wins"] += 1
            s["pnl_ganadores"].append(abs(pnl))
        else:
            s["pnl_perdedores"].append(abs(pnl))

    result = {}
    for ticker, s in raw.items():
        if s["n"] < min_trades:
            continue
        win_rate = s["wins"] / s["n"]
        avg_gan  = sum(s["pnl_ganadores"]) / len(s["pnl_ganadores"]) if s["pnl_ganadores"] else 0
        avg_per  = sum(s["pnl_perdedores"]) / len(s["pnl_perdedores"]) if s["pnl_perdedores"] else 1
        rr       = round(avg_gan / avg_per, 2) if avg_per > 0 else 1.0
        result[ticker] = {
            "win_rate": round(win_rate, 3),
            "rr":       max(rr, 0.01),  # floor para evitar división por cero en Kelly
            "n_trades": s["n"],
        }

    return result


# ── ACTUALIZACIÓN KELLY LIVE ──────────────────────────────────────────────────

def actualizar_kelly_live(min_trades: int = 3):
    """
    Escribe data/kelly_stats_live.json con stats de trades reales.
    kelly_sizing.py lee este archivo en runtime — prioridad sobre KELLY_STATS hardcodeado
    cuando n_trades >= min_trades para ese ticker.

    DISEÑO: reconstruye el archivo COMPLETAMENTE desde trade_outcomes.json.
    NO mergea con datos preexistentes — evita que data contaminada (backtests,
    versiones anteriores, señales no ejecutadas) persista indefinidamente.
    Solo los tickers con ≥ min_trades trades REALES confirmados por IB quedan.

    No modifica engine/kelly_sizing.py (no manipulación de código fuente en runtime).
    """
    stats = calcular_stats_por_ticker(min_trades=min_trades)

    try:
        # Reconstrucción completa — sin merge con datos anteriores.
        # Si stats está vacío (< min_trades para todos los tickers), escribir
        # solo metadatos para que kelly_sizing.py use sus KELLY_STATS hardcodeados.
        nuevo: dict = {}
        nuevo.update(stats)
        nuevo["_updated"]           = datetime.now().isoformat()
        nuevo["_n_tickers"]         = len(stats)
        nuevo["_min_trades"]        = min_trades
        nuevo["_source"]            = "trade_outcomes_confirmados_ib"
        nuevo["_rebuild_completo"]  = True   # flag: este archivo no contiene data histórica ajena

        with open(KELLY_LIVE_FILE, "w") as f:
            json.dump(nuevo, f, indent=2)

        logging.info(
            f"Kelly live reconstruido desde cero: {len(stats)} tickers "
            f"con ≥{min_trades} trades reales confirmados IB"
        )
    except Exception as e:
        logging.error(f"Error actualizando kelly_stats_live: {e}")


# ── RESUMEN PARA DASHBOARD ────────────────────────────────────────────────────

def get_resumen_feedback() -> dict:
    """
    Resumen del feedback loop para el dashboard y para auditoría.
    """
    outcomes = _cargar_outcomes()
    if not outcomes:
        return {"disponible": False, "n_trades": 0}

    n     = len(outcomes)
    wins  = sum(1 for o in outcomes if o.get("resultado") == "GANADOR")
    pnls  = [o.get("pnl_pct", 0) for o in outcomes]

    pnl_gan = [abs(p) for p in pnls if p > 0]
    pnl_per = [abs(p) for p in pnls if p < 0]
    avg_gan = round(sum(pnl_gan) / len(pnl_gan), 3) if pnl_gan else 0
    avg_per = round(sum(pnl_per) / len(pnl_per), 3) if pnl_per else 1
    rr      = round(avg_gan / avg_per, 2) if avg_per > 0 else 0

    stats_fuente  = calcular_stats_por_fuente(min_trades=3)
    stats_tickers = calcular_stats_por_ticker(min_trades=3)

    return {
        "disponible":      True,
        "n_trades":        n,
        "n_ganadores":     wins,
        "n_perdedores":    n - wins,
        "win_rate":        round(wins / n, 3),
        "avg_pnl_pct":     round(sum(pnls) / n, 3),
        "avg_gan_pct":     avg_gan,
        "avg_per_pct":     avg_per,
        "rr_real":         rr,
        "stats_fuentes":   stats_fuente,
        "tickers_con_data": list(stats_tickers.keys()),
        "ultimo_trade":    outcomes[-1].get("fecha_cierre"),
        "timestamp":       datetime.now().isoformat(),
    }


# ── FACTORES DE CALIDAD POR FUENTE ───────────────────────────────────────────

def get_source_quality_factors(min_trades: int = 3) -> dict:
    """
    Retorna factores de calidad por fuente basados en win_rate histórico.

    Factor en [0.85, 1.10] interpolado linealmente:
      WR ≤ 0.40 → 0.85  (fuente de baja calidad — penalizar)
      WR = 0.50 → 0.90  (aleatorio — leve penalización)
      WR = 0.55 → 1.00  (neutral — ligeramente mejor que random)
      WR ≥ 0.65 → 1.10  (fuente con buen track record — premiar)

    Fuentes con < min_trades no se incluyen → el caller usa 1.0 por defecto
    (sin evidencia suficiente → sin ajuste).

    Returns:
        dict[str, float]  p.ej. {"Análisis Técnico": 1.08, "ML": 0.92, ...}
    """
    stats = calcular_stats_por_fuente(min_trades=min_trades)
    factores: Dict[str, float] = {}

    for s in stats:
        wr = s["win_rate"]
        # Interpolación lineal: [0.40, 0.65] → [0.85, 1.10]
        factor = 0.85 + (wr - 0.40) / (0.65 - 0.40) * 0.25
        factores[s["fuente"]] = round(max(0.85, min(1.10, factor)), 3)

    return factores


# ── DATOS DE ENTRENAMIENTO PARA ML ────────────────────────────────────────────

def get_training_data_ml() -> List[dict]:
    """
    Retorna los outcomes en formato listo para reentrenar el ML.
    Cada registro tiene:
      - features de la señal (conviccion, n_fuentes, fuentes presentes)
      - label: 1 si GANADOR, 0 si PERDEDOR

    Usar en ml_signals.py para reentrenamiento incremental.
    """
    outcomes = _cargar_outcomes()
    if not outcomes:
        return []

    todas_fuentes = [
        "Análisis Técnico", "MTF", "ML", "IV Opciones", "Correlaciones",
        "13F SEC", "Mercado Local", "Renta Fija", "Put/Call", "Fear&Greed",
        "Kalshi", "Polymarket", "Macro USA", "CMF", "Volumen",
        "Google Trends", "Order Flow", "IB Data", "Noticias",
    ]

    registros = []
    for o in outcomes:
        fuentes_set = set(o.get("fuentes", []))
        features = {
            "conviccion":  o.get("conviccion", 50) or 50,
            "n_fuentes":   o.get("n_fuentes", 0) or 0,
        }
        # One-hot encoding de fuentes
        for f in todas_fuentes:
            features[f"fuente_{f.replace(' ', '_').replace('/', '_')}"] = 1 if f in fuentes_set else 0

        registros.append({
            "ib_ticker":  o["ib_ticker"],
            "fecha":      o.get("fecha_cierre"),
            "features":   features,
            "label":      1 if o.get("resultado") == "GANADOR" else 0,
            "pnl_pct":    o.get("pnl_pct", 0),
        })

    return registros


# ── SINCRONIZACIÓN CON SOURCE_HEALTH ─────────────────────────────────────────

SOURCE_HEALTH_FILE = os.path.join(BASE_DIR, "data", "source_health.json")


def sincronizar_win_rate_source_health(min_trades: int = 3) -> int:
    """
    Escribe el win_rate real (calculado desde trade_outcomes) en source_health.json.

    Esto cierra el loop: source_health trackea disponibilidad de fuentes,
    feedback_loop trackea su predictive accuracy. Ahora ambos se consolidan.

    Solo actualiza fuentes con >= min_trades trades. Las demás quedan con
    win_rate=None (sin evidencia suficiente).

    Returns: número de fuentes actualizadas.
    """
    stats = calcular_stats_por_fuente(min_trades=min_trades)
    if not stats:
        return 0

    try:
        with open(SOURCE_HEALTH_FILE) as f:
            sh = json.load(f)
    except Exception:
        return 0

    # source_health puede tener estructura {fuentes: {...}} o directamente {fuente: {...}}
    fuentes_dict = sh.get("fuentes", sh)

    # Mapeo nombre_feedback → nombre_source_health (pueden diferir levemente)
    nombre_map = {
        "Análisis Técnico": "analisis_tecnico",
        "IV Opciones":      "iv_opciones",
        "Order Flow":       "order_flow",
        "Correlaciones":    "correlaciones",
        "Macro USA":        "macro_usa",
        "ML":               "ml",
        "MTF":              "mtf",
        "Mercado Local":    "mercado_local",
        "13F SEC":          "sec_13f",
        "Renta Fija":       "renta_fija",
        "Put/Call":         "put_call",
        "Fear&Greed":       "fear_greed",
        "Kalshi":           "kalshi",
        "Polymarket":       "polymarket",
        "Noticias":         "noticias",
        "CMF":              "cmf",
        "Volumen":          "volumen",
        "Google Trends":    "google_trends",
        "IB Data":          "ib_data",
        "Momentum":         "momentum",
    }

    actualizadas = 0
    for s in stats:
        fuente_feedback = s["fuente"]
        sh_key = nombre_map.get(fuente_feedback)
        if not sh_key or sh_key not in fuentes_dict:
            continue
        fuentes_dict[sh_key]["win_rate"]   = s["win_rate"]
        fuentes_dict[sh_key]["rr_real"]    = s["rr"]
        fuentes_dict[sh_key]["ev_real"]    = s["ev"]
        fuentes_dict[sh_key]["n_trades_feedback"] = s["n_trades"]
        fuentes_dict[sh_key]["_feedback_updated"] = datetime.now().isoformat()
        actualizadas += 1

    try:
        with open(SOURCE_HEALTH_FILE, "w") as f:
            json.dump(sh, f, indent=2, default=str)
        logging.info(f"[feedback] source_health actualizado: {actualizadas} fuentes con win_rate real")
    except Exception as e:
        logging.warning(f"[feedback] Error escribiendo source_health: {e}")

    return actualizadas


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== FEEDBACK LOOP — RESUMEN ===\n")
    resumen = get_resumen_feedback()

    if not resumen["disponible"]:
        print("Sin trades registrados todavía.")
        print("El sistema irá acumulando datos a medida que el motor opera.")
    else:
        print(f"Trades registrados: {resumen['n_trades']}")
        print(f"Win rate real:      {resumen['win_rate']:.1%}")
        print(f"R/R real:           {resumen['rr_real']:.2f}x")
        print(f"Avg PnL:            {resumen['avg_pnl_pct']:+.2f}%")
        print()

        if resumen["stats_fuentes"]:
            print(f"{'Fuente':<22} {'N':>4} {'WR%':>6} {'R/R':>5} {'EV':>7}")
            print("-" * 50)
            for s in resumen["stats_fuentes"]:
                print(
                    f"{s['fuente']:<22} {s['n_trades']:>4} "
                    f"{s['win_rate']*100:>5.1f}% {s['rr']:>5.2f}x "
                    f"{s['ev']:>+7.3f}"
                )
        else:
            print("Aún no hay suficientes trades (≥3) por fuente para estadísticas.")

        if resumen["tickers_con_data"]:
            print(f"\nTickers con Kelly recalibrable (≥3 trades): {resumen['tickers_con_data']}")
