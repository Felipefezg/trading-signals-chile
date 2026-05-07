"""
engine/earnings_filter.py

Filtro de earnings para nuevas aperturas.

Riesgo específico de earnings en acciones individuales:
  - Gap overnight que puede perforar el stop-loss sin fill al precio indicado
  - IV crush post-anuncio que invalida la señal técnica
  - Volatilidad intraday impredecible el día del y el día previo al anuncio

Ventana bloqueada: T-1 y T (día previo + día del anuncio).
  T-1: el mercado empieza a mover el precio por IV implícita y opciones.
  T  : máxima incertidumbre — el anuncio puede salir AMC o BMO.

Activos no sujetos al filtro (sin earnings propios):
  - ETF  : SPY, TLT, GLD, SLV, GDX, ECH
  - Crypto: BTC
  - Futuro: GC, HG, CL (ya en BLACKLIST_AUTO, por completitud)

Fuente: yfinance .calendar
Cache:  data/earnings_cache.json — TTL 6h (los earnings dates no cambian intraday)

Fail-open: si yfinance falla o retorna datos vacíos, se permite la entrada.
"""

from __future__ import annotations

import os
import json
from datetime import datetime, date, timedelta

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_BASE_DIR, "..", "data", "earnings_cache.json")
_CACHE_TTL_HOURS = 6
_VENTANA_DIAS    = 2   # bloquear si earnings en [hoy, hoy + N días)

# Tipos de activo sin earnings — nunca bloquear
_TIPOS_SIN_EARNINGS = {"ETF", "Crypto", "Futuro", "Forex"}

# IB ticker → yfinance ticker (lazy-loaded desde universo)
_IB_TO_YF: dict[str, str] | None = None


def _get_ib_to_yf() -> dict[str, str]:
    """Construye mapping IB ticker → yf ticker una sola vez."""
    global _IB_TO_YF
    if _IB_TO_YF is None:
        try:
            from engine.universo import UNIVERSO_COMPLETO
            _IB_TO_YF = {
                v["ib"]: v["yf"]
                for v in UNIVERSO_COMPLETO.values()
                if v.get("ib") and v.get("yf")
            }
        except Exception:
            _IB_TO_YF = {}
    return _IB_TO_YF


def _cargar_cache() -> dict:
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _guardar_cache(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def _consultar_yfinance(yf_ticker: str) -> list[str]:
    """
    Consulta el calendario de earnings vía yfinance.
    Retorna lista de fechas YYYY-MM-DD. Lista vacía si no hay datos o error.

    yfinance.calendar cambia de formato entre versiones:
      - DataFrame con columna "Earnings Date" (versiones recientes)
      - dict {"Earnings Date": Timestamp, ...} (versiones antiguas)
    Se manejan ambos defensivamente.
    """
    try:
        import yfinance as yf
        cal = yf.Ticker(yf_ticker).calendar
        if cal is None:
            return []

        fechas: list[str] = []

        # ── Formato DataFrame ─────────────────────────────────────────────────
        try:
            import pandas as pd
            if isinstance(cal, pd.DataFrame):
                for col in cal.columns:
                    if "earn" in col.lower():
                        for val in cal[col].dropna():
                            try:
                                d = val.date() if hasattr(val, "date") else date.fromisoformat(str(val)[:10])
                                fechas.append(str(d))
                            except Exception:
                                pass
                return fechas
        except ImportError:
            pass

        # ── Formato dict ──────────────────────────────────────────────────────
        if isinstance(cal, dict):
            for key, val in cal.items():
                if "earn" in str(key).lower():
                    if hasattr(val, "date"):
                        fechas.append(str(val.date()))
                    elif isinstance(val, list):
                        for item in val:
                            try:
                                d = item.date() if hasattr(item, "date") else date.fromisoformat(str(item)[:10])
                                fechas.append(str(d))
                            except Exception:
                                pass
            return fechas

    except Exception:
        pass

    return []


def tiene_earnings_proximos(
    ib_ticker: str,
    tipo_activo: str = "ETF",
) -> tuple[bool, str]:
    """
    Verifica si el activo tiene earnings dentro de los próximos _VENTANA_DIAS días.

    Args:
        ib_ticker:   IB ticker del activo ("SQM", "BSAC", etc.)
        tipo_activo: Tipo de activo ("Acción Chile", "Acción USA/Chile", "ETF", "Crypto", ...)

    Returns:
        (bloqueado, razon)
          bloqueado = True  → rechazar la apertura
          bloqueado = False → continuar validación
    """
    # ETFs, Crypto y Futuros no tienen earnings propios
    if tipo_activo in _TIPOS_SIN_EARNINGS:
        return False, ""

    yf_map    = _get_ib_to_yf()
    yf_ticker = yf_map.get(ib_ticker)
    if not yf_ticker:
        return False, ""  # Sin ticker yf conocido → fail-open

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache   = _cargar_cache()
    entrada = cache.get(yf_ticker, {})
    ahora   = datetime.now()

    if entrada:
        try:
            ts = datetime.fromisoformat(entrada.get("ts", "2000-01-01T00:00:00"))
            if (ahora - ts).total_seconds() > _CACHE_TTL_HOURS * 3600:
                entrada = {}  # TTL expirado — refrescar
        except Exception:
            entrada = {}

    if not entrada:
        fechas  = _consultar_yfinance(yf_ticker)
        entrada = {"fechas": fechas, "ts": ahora.isoformat()}
        cache[yf_ticker] = entrada
        _guardar_cache(cache)

    # ── Evaluación ────────────────────────────────────────────────────────────
    hoy    = date.today()
    limite = hoy + timedelta(days=_VENTANA_DIAS - 1)  # inclusive

    for f_str in entrada.get("fechas", []):
        try:
            f_date = date.fromisoformat(f_str[:10])
            if hoy <= f_date <= limite:
                dias = (f_date - hoy).days
                when = {0: "HOY", 1: "MAÑANA"}.get(dias, f"en {dias} días")
                return True, (
                    f"Earnings {ib_ticker} {when} ({f_str[:10]}) — "
                    f"gap riesgo sobre SL, evitar apertura"
                )
        except Exception:
            continue

    return False, ""


def limpiar_cache_expirada() -> int:
    """
    Elimina entradas de cache con TTL expirado.
    Llamar periódicamente (ej. al inicio del ciclo).
    Retorna número de entradas eliminadas.
    """
    cache  = _cargar_cache()
    ahora  = datetime.now()
    claves = list(cache.keys())
    eliminadas = 0
    for k in claves:
        try:
            ts = datetime.fromisoformat(cache[k].get("ts", "2000-01-01T00:00:00"))
            if (ahora - ts).total_seconds() > _CACHE_TTL_HOURS * 3600 * 2:
                del cache[k]
                eliminadas += 1
        except Exception:
            del cache[k]
            eliminadas += 1
    if eliminadas:
        _guardar_cache(cache)
    return eliminadas


if __name__ == "__main__":
    """Test rápido — ejecutar desde ~/trading_signals con venv activo."""
    from engine.universo import UNIVERSO_EJECUTABLE

    print("=== EARNINGS FILTER — ESTADO ACTUAL ===\n")
    tickers_probados = set()
    for entry in UNIVERSO_EJECUTABLE.values():
        ib    = entry.get("ib", "")
        tipo  = entry.get("tipo", "ETF")
        if ib in tickers_probados:
            continue
        tickers_probados.add(ib)
        bloq, razon = tiene_earnings_proximos(ib, tipo)
        estado = f"⚠  BLOQUEADO — {razon}" if bloq else "✓  OK"
        print(f"  {ib:<12} [{tipo:<20}] {estado}")
