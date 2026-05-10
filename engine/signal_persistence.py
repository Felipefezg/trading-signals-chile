"""
Persistencia de señales entre ciclos del motor.

Rastrea cuántas veces consecutivas un ticker+dirección aparece en las
recomendaciones generadas. Las señales consistentes en múltiples ciclos
reciben un boost de convicción que les permite cruzar el umbral mínimo.

Lógica de boost:
  streak=1  →  +0%  (primera aparición, sin bonus)
  streak=2  →  +2%
  streak=3  →  +4%
  streak=4  →  +6%
  streak≥5  →  +8%  (máximo, para no inflar artificialmente)

Parámetros de ventana:
  CYCLE_WINDOW = 15 min  (ciclo cada 5 min + 10 min tolerancia para delays de red/IB)
  Un streak se corta si el activo no reaparece dentro de esa ventana.

Ejemplo de valor:
  SQM.SN COMPRAR aparece en ciclos 14:00, 14:05, 14:10 con convicción 74%.
  En el tercer ciclo acumula streak=3 → boost=+4% → convicción efectiva 78%.
  Si el umbral mínimo es 75%, la señal se ejecuta en el tercer ciclo.
"""

import json
import os
from datetime import datetime, timedelta

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
_BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STREAKS_FILE   = os.path.join(_BASE_DIR, "data", "signal_streaks.json")

CYCLE_WINDOW   = timedelta(minutes=15)  # ciclo 5min + 10min tolerancia (delay red/IB/crash)
MAX_BOOST_PCT  = 8.0                    # boost máximo en puntos de convicción
BOOST_PER_STEP = 2.0                    # puntos adicionales por ciclo extra


# ── I/O ───────────────────────────────────────────────────────────────────────
def _cargar():
    try:
        if os.path.exists(STREAKS_FILE):
            with open(STREAKS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _guardar(data: dict):
    try:
        os.makedirs(os.path.dirname(STREAKS_FILE), exist_ok=True)
        with open(STREAKS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ── API PÚBLICA ───────────────────────────────────────────────────────────────
def get_boost(activo: str, accion: str) -> float:
    """
    Retorna el boost de convicción (puntos %) para un activo+acción.
    0.0 si no hay streak activo o la entrada expiró.
    """
    streaks = _cargar()
    key     = f"{activo}|{accion}"
    info    = streaks.get(key)

    if not info:
        return 0.0

    try:
        last_seen = datetime.fromisoformat(info["last_seen"])
        if (datetime.now() - last_seen) > CYCLE_WINDOW:
            return 0.0                       # streak expirado
    except Exception:
        return 0.0

    streak = int(info.get("streak", 1))
    return min(MAX_BOOST_PCT, max(0.0, (streak - 1) * BOOST_PER_STEP))


def registrar_señales_ciclo(recomendaciones: list):
    """
    Registra las recomendaciones del ciclo actual y actualiza streaks.

    Llamar UNA vez al final de consolidar_señales() con la lista completa.

    Args:
        recomendaciones: lista de dicts con keys 'activo' y 'accion'.
    """
    ahora   = datetime.now()
    previos = _cargar()

    # Set de señales activas este ciclo
    activas = {
        f"{r['activo']}|{r['accion']}"
        for r in recomendaciones
        if r.get("activo") and r.get("accion")
    }

    nuevos: dict = {}

    # ── Actualizar streaks existentes ─────────────────────────────────────
    for key, info in previos.items():
        try:
            last_seen = datetime.fromisoformat(info["last_seen"])
        except Exception:
            continue

        dentro_ventana = (ahora - last_seen) <= CYCLE_WINDOW

        if key in activas and dentro_ventana:
            # Señal activa y dentro del ciclo → incrementar streak
            nuevos[key] = {
                "activo":    info["activo"],
                "accion":    info["accion"],
                "streak":    info["streak"] + 1,
                "last_seen": ahora.isoformat(),
            }
        # Si no está activa o expiró → streak se descarta (no se incluye)

    # ── Agregar señales nuevas (sin streak previo) ────────────────────────
    for key in activas:
        if key not in nuevos:
            partes = key.split("|", 1)
            if len(partes) == 2:
                nuevos[key] = {
                    "activo":    partes[0],
                    "accion":    partes[1],
                    "streak":    1,
                    "last_seen": ahora.isoformat(),
                }

    _guardar(nuevos)


def get_resumen_streaks() -> list:
    """
    Lista de streaks activos con boost actual. Para el dashboard.
    Solo incluye entradas con boost > 0 (streak ≥ 2).
    """
    streaks = _cargar()
    ahora   = datetime.now()
    activos = []

    for key, info in streaks.items():
        try:
            last_seen = datetime.fromisoformat(info["last_seen"])
            if (ahora - last_seen) > CYCLE_WINDOW:
                continue
            streak = int(info.get("streak", 1))
            boost  = min(MAX_BOOST_PCT, max(0.0, (streak - 1) * BOOST_PER_STEP))
            if boost > 0:
                activos.append({
                    "activo":  info["activo"],
                    "accion":  info["accion"],
                    "streak":  streak,
                    "boost":   boost,
                })
        except Exception:
            pass

    return sorted(activos, key=lambda x: x["streak"], reverse=True)
