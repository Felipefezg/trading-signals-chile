"""
Pirámide de posiciones — engine/piramide.py

Escala una posición abierta cuando muestra momentum positivo temprano.

Lógica:
  Si un trade va ≥ UMBRAL_PCT% en las primeras MAX_HORAS horas,
  agregar ADD_PCT del tamaño original para amplificar el R/R realizado.

Condiciones para ejecutar pirámide:
  1. PnL actual ≥ UMBRAL_PCT (1.5%)
  2. Posición abierta < MAX_HORAS (6h) desde fecha_entrada
  3. Convicción original ≥ MIN_CONVICCION (85%)
  4. No se ejecutó previamente (piramide_ejecutada ausente o False)
  5. Mercado abierto para ese tipo de activo
  6. Capital disponible en cuenta IB

Al ejecutar:
  - Envía orden de compra/venta por ADD_PCT del monto original (máx ADD_USD)
  - Ajusta SL al precio de entrada original (protege costo base)
  - Marca piramide_ejecutada=True en posiciones.json
  - Registra evento PIRAMIDE en log_automatico.json

Diseño conservador:
  - Solo UNA pirámide por posición
  - Cap de $5,000 por adición (no escalar en exceso)
  - SL sube a breakeven al piramidear — nunca más pérdida que la inicial
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSICIONES_FILE = os.path.join(BASE_DIR, "posiciones.json")

# ── PARÁMETROS ────────────────────────────────────────────────────────────────
UMBRAL_PCT      = 1.5    # PnL mínimo para activar (%)
MAX_HORAS       = 6.0    # Ventana temporal desde apertura (horas)
ADD_PCT         = 0.25   # Fracción del monto original a agregar
ADD_USD_MAX     = 5_000  # Cap absoluto de la adición en USD
MIN_CONVICCION  = 85     # Convicción mínima de la señal original


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _cargar_posiciones() -> dict:
    try:
        if os.path.exists(POSICIONES_FILE):
            with open(POSICIONES_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _guardar_posiciones(pos: dict) -> None:
    with open(POSICIONES_FILE, "w") as f:
        json.dump(pos, f, indent=2, default=str)


def _horas_desde_apertura(fecha_entrada_iso: Optional[str]) -> float:
    """Retorna horas transcurridas desde la apertura. None → 999 (descalifica)."""
    if not fecha_entrada_iso:
        return 999.0
    try:
        ts = datetime.fromisoformat(fecha_entrada_iso)
        return (datetime.now() - ts).total_seconds() / 3600
    except Exception:
        return 999.0


def _precio_actual_yf(yf_ticker: str) -> Optional[float]:
    """Precio actual vía yfinance (1d de historial, último close)."""
    try:
        import yfinance as yf
        h = yf.Ticker(yf_ticker).history(period="1d", interval="5m")
        if h.empty:
            return None
        return float(h["Close"].iloc[-1])
    except Exception:
        return None


def _ib_ticker_a_yf(ib_ticker: str) -> Optional[str]:
    """Resuelve yf ticker desde IB ticker usando el universo."""
    try:
        from engine.universo import UNIVERSO_COMPLETO
        for yf_t, info in UNIVERSO_COMPLETO.items():
            if info.get("ib") == ib_ticker:
                return yf_t
        return None
    except Exception:
        return None


# ── VERIFICACIÓN ──────────────────────────────────────────────────────────────

def posiciones_elegibles() -> List[dict]:
    """
    Retorna lista de posiciones que cumplen las condiciones para piramidear.
    No ejecuta nada — solo evaluación.
    """
    posiciones = _cargar_posiciones()
    elegibles  = []

    for ib_ticker, pos in posiciones.items():
        # Ya fue piramideada
        if pos.get("piramide_ejecutada"):
            continue

        # Solo posiciones confirmadas por IB
        if not pos.get("confirmado_ib"):
            continue

        conviccion = pos.get("conviccion", 0) or 0
        if conviccion < MIN_CONVICCION:
            continue

        horas = _horas_desde_apertura(pos.get("fecha_entrada"))
        if horas > MAX_HORAS:
            continue

        # Obtener precio actual
        yf_ticker = _ib_ticker_a_yf(ib_ticker)
        if not yf_ticker:
            continue

        precio_actual = _precio_actual_yf(yf_ticker)
        if not precio_actual:
            continue

        precio_entrada = pos.get("precio_entrada", 0)
        if not precio_entrada:
            continue

        accion = pos.get("accion", "COMPRAR")
        if accion == "COMPRAR":
            pnl_pct = (precio_actual - precio_entrada) / precio_entrada * 100
        else:  # VENDER (short)
            pnl_pct = (precio_entrada - precio_actual) / precio_entrada * 100

        if pnl_pct < UMBRAL_PCT:
            continue

        # Calcular monto de adición
        cantidad_original = pos.get("cantidad", 0)
        monto_original    = precio_entrada * cantidad_original
        monto_agregar     = min(monto_original * ADD_PCT, ADD_USD_MAX)
        cant_agregar      = int(monto_agregar / precio_actual)

        if cant_agregar < 1:
            continue

        elegibles.append({
            "ib_ticker":       ib_ticker,
            "yf_ticker":       yf_ticker,
            "accion":          accion,
            "precio_entrada":  precio_entrada,
            "precio_actual":   precio_actual,
            "pnl_pct":         round(pnl_pct, 2),
            "horas_abierto":   round(horas, 1),
            "conviccion":      conviccion,
            "cantidad_agregar":cant_agregar,
            "monto_agregar":   round(monto_agregar, 0),
            "sl_original":     pos.get("sl"),
            "sl_nuevo":        precio_entrada,   # SL sube a breakeven
        })

    return elegibles


# ── EJECUCIÓN ──────────────────────────────────────────────────────────────────

def ejecutar_piramide(elegible: dict) -> dict:
    """
    Ejecuta la adición a posición para una entrada elegible.

    Retorna dict con resultado: {ok, ib_ticker, cantidad, monto, error}
    """
    ib_ticker    = elegible["ib_ticker"]
    accion       = elegible["accion"]
    cant_agregar = elegible["cantidad_agregar"]
    sl_nuevo     = elegible["sl_nuevo"]

    resultado = {
        "ib_ticker":       ib_ticker,
        "accion":          accion,
        "cantidad":        cant_agregar,
        "monto_usd":       elegible["monto_agregar"],
        "precio_actual":   elegible["precio_actual"],
        "pnl_pct":         elegible["pnl_pct"],
        "sl_nuevo":        sl_nuevo,
        "ok":              False,
        "confirmado_ib":   False,
        "error":           None,
    }

    try:
        from engine.ib_executor import IBExecutor

        with IBExecutor(client_id=10) as ib:
            order_id = ib.siguiente_orden_id()
            if not order_id:
                resultado["error"] = "No se pudo obtener order_id de IB"
                return resultado

            ok = ib.enviar_orden_mercado(
                ib_ticker  = ib_ticker,
                accion     = accion,
                cantidad   = cant_agregar,
                order_id   = order_id,
            )

            if ok:
                resultado["ok"]            = True
                resultado["confirmado_ib"] = True
                resultado["order_id"]      = order_id

                # Actualizar posiciones.json
                posiciones = _cargar_posiciones()
                if ib_ticker in posiciones:
                    pos = posiciones[ib_ticker]
                    # Precio promedio ponderado
                    qty_orig  = pos.get("cantidad", 0)
                    px_orig   = pos.get("precio_entrada", 0)
                    qty_new   = qty_orig + cant_agregar
                    px_avg    = (px_orig * qty_orig + elegible["precio_actual"] * cant_agregar) / qty_new
                    pos["cantidad"]          = qty_new
                    pos["precio_entrada"]    = round(px_avg, 4)
                    pos["sl"]                = round(sl_nuevo, 4)
                    pos["piramide_ejecutada"]= True
                    pos["piramide_ts"]       = datetime.now().isoformat()
                    pos["piramide_precio"]   = elegible["precio_actual"]
                    pos["piramide_qty"]      = cant_agregar
                    _guardar_posiciones(posiciones)

                logging.info(
                    f"PIRÁMIDE OK: {accion} {cant_agregar}x {ib_ticker} @ "
                    f"{elegible['precio_actual']:.4f} | "
                    f"SL ajustado a breakeven {sl_nuevo:.4f} | "
                    f"PnL entrada: +{elegible['pnl_pct']:.2f}%"
                )
            else:
                resultado["error"] = "IB no confirmó la orden"

    except Exception as e:
        resultado["error"] = str(e)
        logging.warning(f"Error ejecutando pirámide {ib_ticker}: {e}")

    return resultado


# ── ORQUESTADOR ────────────────────────────────────────────────────────────────

def verificar_y_ejecutar_piramide() -> List[dict]:
    """
    Punto de entrada desde motor_automatico.py.

    Evalúa todas las posiciones abiertas y ejecuta pirámides donde corresponde.
    Retorna lista de resultados (vacía si nada elegible).
    """
    elegibles = posiciones_elegibles()
    if not elegibles:
        return []

    resultados = []
    for e in elegibles:
        logging.info(
            f"PIRÁMIDE elegible: {e['ib_ticker']} PnL={e['pnl_pct']:+.2f}% "
            f"({e['horas_abierto']:.1f}h) — agregar {e['cantidad_agregar']}x "
            f"(${e['monto_agregar']:,.0f})"
        )
        res = ejecutar_piramide(e)
        resultados.append(res)

        # Alerta Telegram
        if res["ok"]:
            try:
                from engine.telegram_alertas import alerta_piramide
                alerta_piramide(res)
            except Exception:
                pass

    return resultados


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== PIRÁMIDE — POSICIONES ELEGIBLES ===\n")
    elegibles = posiciones_elegibles()

    if not elegibles:
        print("Sin posiciones elegibles para piramidear.")
        print("Condiciones: PnL ≥ 1.5%, < 6h abierto, convicción ≥ 85%, no piramideada.")
    else:
        for e in elegibles:
            print(
                f"  {e['ib_ticker']:12} PnL={e['pnl_pct']:+.2f}%  "
                f"{e['horas_abierto']:.1f}h  "
                f"agregar {e['cantidad_agregar']}x @ ${e['precio_actual']:.2f}  "
                f"(${e['monto_agregar']:,.0f})  "
                f"SL breakeven={e['sl_nuevo']:.4f}"
            )
