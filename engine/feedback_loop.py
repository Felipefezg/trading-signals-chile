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
LOG_FILE        = os.path.join(BASE_DIR, "log_automatico.json")

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)


# ── STORAGE ───────────────────────────────────────────────────────────────────

def _cargar_outcomes() -> List[dict]:
    try:
        if os.path.exists(OUTCOMES_FILE):
            with open(OUTCOMES_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _guardar_outcomes(outcomes: List[dict]):
    with open(OUTCOMES_FILE, "w") as f:
        json.dump(outcomes, f, indent=2, default=str)


# ── VINCULACIÓN APERTURA ↔ CIERRE ────────────────────────────────────────────

def _buscar_apertura_en_log(ib_ticker: str) -> Optional[dict]:
    """
    Busca la última APERTURA confirmada por IB para ib_ticker en log_automatico.json.
    Retorna el evento completo (con datos y evidencia) o None si no se encuentra.
    """
    try:
        with open(LOG_FILE) as f:
            log = json.load(f)
    except Exception:
        return None

    # Buscar la apertura más reciente, confirmada por IB, para este ticker
    for evento in reversed(log):
        if (
            evento.get("tipo") == "APERTURA"
            and evento.get("datos", {}).get("ib_ticker") == ib_ticker
            and evento.get("datos", {}).get("confirmado_ib", False)
        ):
            return evento

    return None


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

    outcome = {
        "ib_ticker":      ib_ticker,
        "fecha_cierre":   datetime.now().isoformat(),
        "fecha_apertura": apertura.get("timestamp") if apertura else None,
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

    outcomes = _cargar_outcomes()
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

    No modifica engine/kelly_sizing.py (no manipulación de código fuente en runtime).
    """
    stats = calcular_stats_por_ticker(min_trades=min_trades)
    if not stats:
        return

    try:
        # Merge con datos existentes (conservar tickers sin trades suficientes)
        existing: dict = {}
        if os.path.exists(KELLY_LIVE_FILE):
            with open(KELLY_LIVE_FILE) as f:
                existing = json.load(f)

        # Solo actualizar tickers con datos frescos
        existing.update(stats)
        existing["_updated"]  = datetime.now().isoformat()
        existing["_n_tickers"] = len([k for k in existing if not k.startswith("_")])

        with open(KELLY_LIVE_FILE, "w") as f:
            json.dump(existing, f, indent=2)

        logging.info(f"Kelly live actualizado: {len(stats)} tickers con ≥{min_trades} trades reales")
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
