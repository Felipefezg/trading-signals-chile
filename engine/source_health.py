"""
Source Health Monitor — engine/source_health.py

Registra por ciclo el estado de cada una de las 19 fuentes:
  - ok:    retornó datos no vacíos
  - empty: retornó None, [] o {} (sin error explícito)
  - error: excepción capturada por data_loader

Persiste en data/source_health.json.
Genera warning en logging si una fuente lleva ≥ ALERTA_CONSECUTIVOS
ciclos consecutivos sin datos.

Diseño: zero-dependency externa. Solo inspecciona el dict `datos`
que data_loader ya construyó — no hace I/O adicional.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_FILE = os.path.join(BASE_DIR, "data", "source_health.json")

ALERTA_CONSECUTIVOS = 3   # ciclos vacíos/error consecutivos para generar warning

# 20 fuentes canónicas — en el mismo orden que data_loader.FUENTES
ALL_SOURCES: List[str] = [
    "polymarket", "kalshi", "macro_usa", "noticias", "fear_greed",
    "cmf", "put_call", "analisis_tecnico", "google_trends", "volumen",
    "ib_data", "order_flow", "correlaciones", "mercado_local", "mtf",
    "renta_fija", "sec_13f", "iv_opciones", "ml", "momentum",
]

# Mapeo de claves del dict datos → nombre canónico de fuente
_KEY_MAP: Dict[str, str] = {
    "poly_df":          "polymarket",
    "kalshi_list":      "kalshi",
    "macro_corr":       "macro_usa",
    "noticias":         "noticias",
    "fear_greed":       "fear_greed",
    "cmf_hechos":       "cmf",
    "put_call":         "put_call",
    "analisis_tecnico": "analisis_tecnico",
    "google_trends":    "google_trends",
    "vol_alertas":      "volumen",
    "ib_data":          "ib_data",
    "order_flow":       "order_flow",
    "correlaciones":    "correlaciones",
    "mercado_local":    "mercado_local",
    "mtf":              "mtf",
    "renta_fija":       "renta_fija",
    "sec_13f":          "sec_13f",
    "iv_opciones":      "iv_opciones",
    "ml":               "ml",
    "momentum":         "momentum",
}


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _es_vacio(v: Any) -> bool:
    """True si el valor es considerado 'sin datos': None, list vacía, dict vacío,
    o DataFrame vacío."""
    if v is None:
        return True
    try:
        import pandas as pd
        if isinstance(v, pd.DataFrame):
            return v.empty
    except ImportError:
        pass
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def _contar_items(v: Any) -> int:
    """Número de items retornados por la fuente (para métricas de densidad)."""
    if v is None:
        return 0
    try:
        import pandas as pd
        if isinstance(v, pd.DataFrame):
            return len(v)
    except ImportError:
        pass
    if isinstance(v, (list, dict)):
        return len(v)
    return 1  # scalar no-nulo


# ── PERSISTENCIA ───────────────────────────────────────────────────────────────

def _cargar_health() -> dict:
    try:
        if os.path.exists(HEALTH_FILE):
            with open(HEALTH_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"fuentes": {}, "ciclos_total": 0, "ultimo_ciclo": None}


def _guardar_health(h: dict) -> None:
    os.makedirs(os.path.dirname(HEALTH_FILE), exist_ok=True)
    with open(HEALTH_FILE, "w") as f:
        json.dump(h, f, indent=2, default=str)


# ── REGISTRO POR CICLO ─────────────────────────────────────────────────────────

def registrar_ciclo_fuentes(datos: dict, errores: Optional[dict] = None) -> dict:
    """
    Registra el estado de cada fuente tras un ciclo de carga.

    Args:
        datos:   dict retornado por get_datos_para_motor() — incluye clave 'meta'
        errores: dict {nombre_fuente: msg_error} de data_loader.
                 Si None, lo extrae de datos['meta']['errores'].

    Returns:
        Resumen del ciclo: {'ok': [...], 'empty': [...], 'error': [...],
                            'alertas': [(fuente, estado, n_consec), ...],
                            'ciclos': int}
    """
    if errores is None:
        errores = datos.get("meta", {}).get("errores", {}) or {}

    ahora  = datetime.now().isoformat()
    health = _cargar_health()
    health["ciclos_total"] = health.get("ciclos_total", 0) + 1
    health["ultimo_ciclo"] = ahora

    fuentes_h = health.setdefault("fuentes", {})
    resumen: Dict[str, List[str]] = {"ok": [], "empty": [], "error": []}
    alertas: List[Tuple[str, str, int]] = []

    for key, fuente in _KEY_MAP.items():
        valor = datos.get(key)

        # Determinar estado
        if fuente in errores:
            estado  = "error"
        elif _es_vacio(valor):
            estado = "empty"
        else:
            estado = "ok"

        n_items = _contar_items(valor)

        # Inicializar registro si no existe
        f = fuentes_h.setdefault(fuente, {
            "estado":              "ok",
            "consecutivos_vacios": 0,
            "ultimo_ok":           None,
            "n_ciclos":            0,
            "n_ok":                0,
            "n_vacios":            0,
            "n_errores":           0,
            "ultimo_n_items":      0,
        })

        f["estado"]         = estado
        f["n_ciclos"]       = f.get("n_ciclos", 0) + 1
        f["ultimo_n_items"] = n_items

        if estado == "ok":
            f["consecutivos_vacios"] = 0
            f["ultimo_ok"]           = ahora
            f["n_ok"]                = f.get("n_ok", 0) + 1
            resumen["ok"].append(fuente)

        elif estado == "error":
            f["consecutivos_vacios"] = f.get("consecutivos_vacios", 0) + 1
            f["n_errores"]           = f.get("n_errores", 0) + 1
            f["ultimo_error"]        = ahora
            f["ultimo_error_msg"]    = str(errores.get(fuente, ""))[:140]
            resumen["error"].append(fuente)

        else:  # empty
            f["consecutivos_vacios"] = f.get("consecutivos_vacios", 0) + 1
            f["n_vacios"]            = f.get("n_vacios", 0) + 1
            resumen["empty"].append(fuente)

        consec = f["consecutivos_vacios"]
        if consec >= ALERTA_CONSECUTIVOS:
            alertas.append((fuente, estado, consec))

    _guardar_health(health)

    # ── Log resumen compacto de ciclo
    logging.info(
        f"[SourceHealth] ok={len(resumen['ok'])}/{len(ALL_SOURCES)}  "
        f"empty={resumen['empty'] or '—'}  "
        f"error={resumen['error'] or '—'}"
    )

    # ── Warnings explícitos para fuentes persistentemente malas
    for fuente, estado, consec in alertas:
        logging.warning(
            f"[SourceHealth] ⚠  '{fuente}' lleva {consec} ciclos consecutivos "
            f"sin datos (estado={estado}) — verificar módulo"
        )

    return {
        "ok":      resumen["ok"],
        "empty":   resumen["empty"],
        "error":   resumen["error"],
        "alertas": alertas,
        "ciclos":  health["ciclos_total"],
    }


# ── RESUMEN PARA DASHBOARD / AUDITORÍA ────────────────────────────────────────

def get_resumen_health() -> dict:
    """
    Retorna estado completo de las 19 fuentes para dashboard y auditoría.
    Siempre retorna todas las fuentes, incluso las que aún no tienen datos.
    """
    health  = _cargar_health()
    fuentes = health.get("fuentes", {})
    filas   = []

    for fuente in ALL_SOURCES:
        f = fuentes.get(fuente, {})
        n  = f.get("n_ciclos", 0)
        ok = f.get("n_ok",     0)
        filas.append({
            "fuente":              fuente,
            "estado":              f.get("estado", "sin_datos"),
            "consecutivos_vacios": f.get("consecutivos_vacios", 0),
            "tasa_ok_pct":         round(ok / n * 100, 1) if n > 0 else None,
            "n_ciclos":            n,
            "n_ok":                ok,
            "n_vacios":            f.get("n_vacios",  0),
            "n_errores":           f.get("n_errores", 0),
            "ultimo_ok":           f.get("ultimo_ok", None),
            "ultimo_n_items":      f.get("ultimo_n_items", 0),
            "alerta":              f.get("consecutivos_vacios", 0) >= ALERTA_CONSECUTIVOS,
        })

    alertas = [f for f in filas if f["alerta"]]

    return {
        "fuentes":      filas,
        "ciclos_total": health.get("ciclos_total", 0),
        "ultimo_ciclo": health.get("ultimo_ciclo"),
        "n_alertas":    len(alertas),
        "fuentes_alerta": [f["fuente"] for f in alertas],
    }


def resetear_consecutivos(fuente: str) -> bool:
    """
    Resetea el contador de consecutivos vacíos para una fuente.
    Útil cuando se corrige un módulo y se quiere limpiar la alerta.
    """
    health = _cargar_health()
    f = health.get("fuentes", {}).get(fuente)
    if f is None:
        return False
    f["consecutivos_vacios"] = 0
    _guardar_health(health)
    logging.info(f"[SourceHealth] Contador de '{fuente}' reseteado manualmente")
    return True


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    resumen = get_resumen_health()

    print("=== SOURCE HEALTH MONITOR ===\n")
    print(f"Ciclos totales: {resumen['ciclos_total']}")
    print(f"Último ciclo:   {resumen['ultimo_ciclo'] or 'sin datos'}\n")

    if resumen["ciclos_total"] == 0:
        print("Sin ciclos registrados. El monitor se activa con el próximo ciclo del motor.")
    else:
        print(
            f"{'Fuente':<20} {'Estado':<8} {'Tasa%':>6} {'Items':>6} "
            f"{'Consec':>7} {'ok':>5} {'vac':>5} {'err':>5}"
        )
        print("─" * 72)
        for f in resumen["fuentes"]:
            alerta = " ◄ ALERTA" if f["alerta"] else ""
            tasa   = f"{f['tasa_ok_pct']:.0f}%" if f["tasa_ok_pct"] is not None else " N/A"
            print(
                f"{f['fuente']:<20} {f['estado']:<8} {tasa:>6} "
                f"{f['ultimo_n_items']:>6} {f['consecutivos_vacios']:>7} "
                f"{f['n_ok']:>5} {f['n_vacios']:>5} {f['n_errores']:>5}{alerta}"
            )

        if resumen["n_alertas"]:
            print(f"\n⚠  {resumen['n_alertas']} fuente(s) con alerta: {resumen['fuentes_alerta']}")
        else:
            print(f"\n✓  Sin alertas activas")
