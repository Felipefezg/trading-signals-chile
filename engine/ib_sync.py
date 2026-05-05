"""
Sincronizador IB — Thin shim sobre ib_executor.
IB es la única fuente de verdad.

DISEÑO:
- Este módulo ya NO crea posiciones locales desde cero.
- Toda sincronización real delega a ib_executor.sincronizar_desde_ib()
  que garantiza: solo registra localmente lo que tiene confirmado_ib=True.
- Se mantienen los nombres de función originales para compatibilidad.
"""

import json
import os
from datetime import datetime

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSICIONES_FILE = os.path.join(BASE_DIR, "posiciones.json")
TRADES_FILE     = os.path.join(BASE_DIR, "trades_cerrados.json")

# ── API PÚBLICA ───────────────────────────────────────────────────────────────

def sincronizar_posiciones_local():
    """
    Sincroniza posiciones.json con el estado real de IB.
    Delega completamente a ib_executor.sincronizar_desde_ib().

    GARANTÍA: nunca crea posiciones locales sin confirmado_ib=True.
    Si IB no tiene una posición, se elimina localmente.
    """
    try:
        from engine.ib_executor import sincronizar_desde_ib
        pos = sincronizar_desde_ib()
        n   = len(pos)
        print(f"Posiciones sincronizadas con IB: {n}")
        for sym, p in pos.items():
            print(f"  {sym}: {p.get('accion','?')} {p.get('cantidad',0)} @ {p.get('precio_entrada',0):,.4f}")
        return True   # True también si 0 posiciones (sync OK)
    except Exception as e:
        print(f"Error sincronizando posiciones: {e}")
        return False


def limpiar_trades_falsos():
    """
    Limpia trades_cerrados.json eliminando registros marcados explícitamente
    como no confirmados por IB (confirmado_ib=False).

    No consulta IB activamente — limpia solo por flag local.
    Para reconciliación profunda usar sincronizar_posiciones_local().
    """
    try:
        with open(TRADES_FILE) as f:
            trades = json.load(f)
    except Exception:
        trades = []

    if not trades:
        print("Sin trades locales para limpiar")
        return True

    total_antes = len(trades)

    # Conservar trades con confirmación IB explícita o sin flag (historial previo)
    trades_validos = []
    eliminados     = []
    for t in trades:
        if t.get("confirmado_ib", None) is False:
            # Marcado explícitamente como no confirmado → fantasma
            eliminados.append(t.get("ticker", "?"))
        else:
            trades_validos.append(t)

    with open(TRADES_FILE, "w") as f:
        json.dump(trades_validos, f, indent=2, default=str)

    if eliminados:
        print(f"Trades fantasma eliminados: {eliminados}")
    print(f"Trades válidos: {len(trades_validos)} / {total_antes}")
    return True


def sincronizar_con_ib():
    """
    Obtiene snapshot de IB: posiciones y cuenta.
    Retorna dict compatible con el formato original para uso en dashboard.
    """
    try:
        from engine.ib_executor import sincronizar_desde_ib, get_resumen_cuenta

        posiciones = sincronizar_desde_ib()
        cuenta     = get_resumen_cuenta()

        # Transformar al formato extendido original
        pos_fmt = {}
        for sym, p in posiciones.items():
            pos_fmt[sym] = {
                "symbol":   sym,
                "secType":  p.get("tipo", "STK"),
                "currency": "USD",
                "position": p.get("cantidad", 0),
                "avgCost":  p.get("precio_entrada", 0),
                "accion":   p.get("accion", "COMPRAR"),
                "cantidad": p.get("cantidad", 0),
            }

        return {
            "posiciones":  pos_fmt,
            "ejecuciones": [],
            "ordenes":     [],
            "cuenta":      {"NetLiquidation": cuenta.get("capital", 0)},
            "timestamp":   datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


def get_resumen_cuenta_ib():
    """Resumen de la cuenta IB para el dashboard."""
    try:
        from engine.ib_executor import sincronizar_desde_ib, get_resumen_cuenta

        posiciones = sincronizar_desde_ib()
        cuenta     = get_resumen_cuenta()
        capital    = cuenta.get("capital", 0)

        return {
            "disponible":       True,
            "posiciones":       posiciones,
            "n_posiciones":     len(posiciones),
            "n_ejecuciones":    0,
            "n_ordenes":        0,
            "cuenta":           {"NetLiquidation": capital},
            "capital":          capital,
            "cash":             capital,
            "pnl_no_realizado": 0,
            "timestamp":        datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "disponible": False,
            "error":      str(e),
        }


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== SINCRONIZADOR IB ===\n")

    print("1. Sincronizando posiciones con IB...")
    sincronizar_posiciones_local()

    print("\n2. Limpiando trades fantasma...")
    limpiar_trades_falsos()

    print("\n3. Resumen cuenta IB:")
    resumen = get_resumen_cuenta_ib()
    if resumen["disponible"]:
        print(f"   Capital: USD {resumen['capital']:,.2f}")
        print(f"   Posiciones: {resumen['n_posiciones']}")
    else:
        print(f"   Error: {resumen['error']}")
