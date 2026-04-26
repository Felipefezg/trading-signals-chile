"""
Módulo de backtesting automático.
Compara señales históricas contra precios reales para determinar
si la señal fue correcta, incorrecta o está pendiente.

Lógica:
1. Lee señales del historial con resultado 'pendiente'
2. Para cada señal, obtiene precio del activo principal al momento
   de la señal y precio actual (o al vencimiento del horizonte)
3. Compara dirección esperada vs movimiento real
4. Actualiza resultado en la base de datos
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta
import yfinance as yf

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "historial.db")
PRECIOS_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "precios_entrada.json")

# Mapa de activos a tickers Yahoo Finance
ACTIVO_TO_TICKER = {
    "ECH":              "ECH",
    "SQM.SN":           "SQM-B.SN",
    "SQM":              "SQM",
    "COPEC.SN":         "COPEC.SN",
    "CLP/USD":          "CLP=X",
    "BTC_LOCAL_SPREAD": "BTC-USD",
    "BTC":              "BTC-USD",
    "GC=F":             "GC=F",
    "CL=F":             "CL=F",
    "HG=F":             "HG=F",
    "SPY":              "SPY",
    # IPSA
    "BCI.SN":           "BCI.SN",
    "BSANTANDER.SN":    "BSANTANDER.SN",
    "CHILE.SN":         "CHILE.SN",
    "FALABELLA.SN":     "FALABELLA.SN",
    "CENCOSUD.SN":      "CENCOSUD.SN",
    "CCU.SN":           "CCU.SN",
    "CMPC.SN":          "CMPC.SN",
    "ENELCHILE.SN":     "ENELCHILE.SN",
    "COLBUN.SN":        "COLBUN.SN",
    "ENTEL.SN":         "ENTEL.SN",
    "LTM.SN":           "LTM.SN",
}

# Umbral mínimo de movimiento para considerar señal correcta
UMBRAL_MOVIMIENTO_PCT = 0.5  # 0.5% mínimo de movimiento

def _cargar_cache_precios():
    try:
        if os.path.exists(PRECIOS_CACHE_FILE):
            with open(PRECIOS_CACHE_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def _guardar_cache_precios(cache):
    with open(PRECIOS_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, default=str)

def _get_precio_historico(ticker_yf, fecha_str):
    """Obtiene precio de cierre de un ticker en una fecha específica."""
    try:
        fecha = datetime.fromisoformat(fecha_str[:10])
        inicio = fecha - timedelta(days=3)
        fin    = fecha + timedelta(days=3)
        h = yf.download(ticker_yf, start=inicio.strftime("%Y-%m-%d"),
                        end=fin.strftime("%Y-%m-%d"), progress=False)
        if h.empty:
            return None
        # Buscar el precio más cercano a la fecha
        h.index = h.index.tz_localize(None) if h.index.tz else h.index
        idx = h.index.searchsorted(fecha)
        idx = min(idx, len(h) - 1)
        return round(float(h["Close"].iloc[idx]), 4)
    except:
        return None

def _get_precio_actual(ticker_yf):
    """Obtiene precio actual de un ticker."""
    try:
        h = yf.Ticker(ticker_yf).history(period="2d")
        if h.empty:
            return None
        return round(float(h["Close"].iloc[-1]), 4)
    except:
        return None

def _extraer_activo_principal(activos_str):
    """
    Extrae el activo principal de la cadena de activos de la señal.
    Prioriza activos con ticker disponible.
    """
    if not activos_str:
        return None, None

    activos = [a.strip() for a in activos_str.split(",")]
    for activo in activos:
        if activo in ACTIVO_TO_TICKER:
            return activo, ACTIVO_TO_TICKER[activo]

    # Buscar coincidencia parcial
    for activo in activos:
        for key, val in ACTIVO_TO_TICKER.items():
            if key.lower() in activo.lower() or activo.lower() in key.lower():
                return activo, val

    return activos[0] if activos else None, None

def _evaluar_señal(direccion, precio_entrada, precio_salida):
    """
    Evalúa si la señal fue correcta basándose en el movimiento de precio.
    Retorna: 'correcto', 'incorrecto', 'neutral'
    """
    if not precio_entrada or not precio_salida:
        return "pendiente"

    movimiento_pct = ((precio_salida - precio_entrada) / precio_entrada) * 100

    if abs(movimiento_pct) < UMBRAL_MOVIMIENTO_PCT:
        return "neutral"  # Movimiento insignificante

    if direccion in ("ALZA", "COMPRAR"):
        return "correcto" if movimiento_pct > 0 else "incorrecto"
    elif direccion in ("BAJA", "VENDER"):
        return "correcto" if movimiento_pct < 0 else "incorrecto"

    return "pendiente"

def _dias_transcurridos(fecha_str):
    """Calcula días desde la fecha de la señal."""
    try:
        fecha = datetime.fromisoformat(fecha_str[:16])
        return (datetime.now() - fecha).days
    except:
        return 0

def get_señales_pendientes():
    """Retorna señales con resultado 'pendiente' de la base de datos."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, fecha, senal, prob_pct, direccion, activos, score, tesis
            FROM senales WHERE resultado = 'pendiente'
            ORDER BY id DESC
        """)
        rows = c.fetchall()
        conn.close()
        return rows
    except:
        return []

def _actualizar_resultado_backtest(senal_id, resultado, precio_entrada,
                                   precio_salida, movimiento_pct, ticker):
    """Actualiza el resultado de una señal con datos de backtesting."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Agregar columnas si no existen
        try:
            c.execute("ALTER TABLE senales ADD COLUMN precio_entrada_bt REAL")
            c.execute("ALTER TABLE senales ADD COLUMN precio_salida_bt REAL")
            c.execute("ALTER TABLE senales ADD COLUMN movimiento_pct REAL")
            c.execute("ALTER TABLE senales ADD COLUMN ticker_bt TEXT")
            c.execute("ALTER TABLE senales ADD COLUMN fecha_evaluacion TEXT")
            conn.commit()
        except:
            pass  # Columnas ya existen

        c.execute("""
            UPDATE senales SET
                resultado = ?,
                precio_entrada_bt = ?,
                precio_salida_bt = ?,
                movimiento_pct = ?,
                ticker_bt = ?,
                fecha_evaluacion = ?
            WHERE id = ?
        """, (resultado, precio_entrada, precio_salida,
              round(movimiento_pct, 2) if movimiento_pct else None,
              ticker, datetime.now().isoformat(), senal_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error actualizando señal {senal_id}: {e}")
        return False

def ejecutar_backtest(dias_minimos=1, dias_maximos=5):
    """
    Ejecuta backtesting automático sobre señales pendientes.

    Args:
        dias_minimos: mínimo días transcurridos para evaluar
        dias_maximos: máximo días para buscar precio de salida

    Returns:
        dict con resumen del backtesting
    """
    señales = get_señales_pendientes()
    cache   = _cargar_cache_precios()

    resumen = {
        "timestamp":    datetime.now().isoformat(),
        "total":        len(señales),
        "evaluadas":    0,
        "correctas":    0,
        "incorrectas":  0,
        "neutrales":    0,
        "pendientes":   0,
        "sin_ticker":   0,
        "detalle":      [],
    }

    for row in señales:
        senal_id, fecha, senal, prob_pct, direccion, activos, score, tesis = row
        dias = _dias_transcurridos(fecha)

        # Solo evaluar señales con al menos dias_minimos
        if dias < dias_minimos:
            resumen["pendientes"] += 1
            continue

        activo, ticker_yf = _extraer_activo_principal(activos)
        if not ticker_yf:
            resumen["sin_ticker"] += 1
            continue

        # Precio de entrada (al momento de la señal) — usar cache
        cache_key = f"{ticker_yf}_{fecha[:10]}"
        precio_entrada = cache.get(cache_key)
        if not precio_entrada:
            precio_entrada = _get_precio_historico(ticker_yf, fecha)
            if precio_entrada:
                cache[cache_key] = precio_entrada

        # Precio de salida (precio actual)
        precio_salida = _get_precio_actual(ticker_yf)

        if not precio_entrada or not precio_salida:
            resumen["pendientes"] += 1
            continue

        movimiento_pct = ((precio_salida - precio_entrada) / precio_entrada) * 100
        resultado = _evaluar_señal(direccion, precio_entrada, precio_salida)

        # Actualizar en DB
        _actualizar_resultado_backtest(
            senal_id, resultado, precio_entrada,
            precio_salida, movimiento_pct, ticker_yf
        )

        resumen["evaluadas"] += 1
        if resultado == "correcto":    resumen["correctas"] += 1
        elif resultado == "incorrecto": resumen["incorrectas"] += 1
        elif resultado == "neutral":    resumen["neutrales"] += 1

        resumen["detalle"].append({
            "id":             senal_id,
            "fecha":          fecha[:16],
            "señal":          senal[:60],
            "direccion":      direccion,
            "activo":         activo,
            "ticker":         ticker_yf,
            "precio_entrada": precio_entrada,
            "precio_salida":  precio_salida,
            "movimiento_pct": round(movimiento_pct, 2),
            "resultado":      resultado,
            "dias":           dias,
        })

    _guardar_cache_precios(cache)

    # Calcular tasa de éxito
    evaluadas_binarias = resumen["correctas"] + resumen["incorrectas"]
    resumen["tasa_exito"] = round(
        resumen["correctas"] / evaluadas_binarias * 100, 1
    ) if evaluadas_binarias > 0 else 0

    return resumen

def get_estadisticas_backtest():
    """Obtiene estadísticas completas del historial con datos de backtesting."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Estadísticas generales
        c.execute("SELECT COUNT(*) FROM senales")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM senales WHERE resultado='correcto'")
        correctas = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM senales WHERE resultado='incorrecto'")
        incorrectas = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM senales WHERE resultado='pendiente'")
        pendientes = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM senales WHERE resultado='neutral'")
        neutrales = c.fetchone()[0]

        # Movimiento promedio cuando correcto
        try:
            c.execute("""
                SELECT AVG(ABS(movimiento_pct)) FROM senales
                WHERE resultado='correcto' AND movimiento_pct IS NOT NULL
            """)
            mov_prom_correcto = c.fetchone()[0] or 0
        except:
            mov_prom_correcto = 0

        # Movimiento promedio cuando incorrecto
        try:
            c.execute("""
                SELECT AVG(ABS(movimiento_pct)) FROM senales
                WHERE resultado='incorrecto' AND movimiento_pct IS NOT NULL
            """)
            mov_prom_incorrecto = c.fetchone()[0] or 0
        except:
            mov_prom_incorrecto = 0

        # Señales con mayor score que fueron correctas
        try:
            c.execute("""
                SELECT senal, score, movimiento_pct, direccion FROM senales
                WHERE resultado='correcto' AND movimiento_pct IS NOT NULL
                ORDER BY score DESC LIMIT 5
            """)
            mejores = c.fetchall()
        except:
            mejores = []

        # Historial completo con datos BT
        try:
            c.execute("""
                SELECT fecha, senal, prob_pct, direccion, activos, score,
                       resultado, precio_entrada_bt, precio_salida_bt, movimiento_pct, ticker_bt
                FROM senales ORDER BY id DESC LIMIT 50
            """)
            historial_bt = c.fetchall()
        except:
            c.execute("""
                SELECT fecha, senal, prob_pct, direccion, activos, score,
                       resultado, NULL, NULL, NULL, NULL
                FROM senales ORDER BY id DESC LIMIT 50
            """)
            historial_bt = c.fetchall()

        conn.close()

        binarias = correctas + incorrectas
        return {
            "total":               total,
            "correctas":           correctas,
            "incorrectas":         incorrectas,
            "pendientes":          pendientes,
            "neutrales":           neutrales,
            "tasa_exito":          round(correctas / binarias * 100, 1) if binarias > 0 else 0,
            "mov_prom_correcto":   round(mov_prom_correcto, 2),
            "mov_prom_incorrecto": round(mov_prom_incorrecto, 2),
            "mejores_señales":     mejores,
            "historial_bt":        historial_bt,
        }
    except Exception as e:
        print(f"Error estadísticas backtest: {e}")
        return {}

if __name__ == "__main__":
    print("=== BACKTESTING AUTOMÁTICO ===")
    resultado = ejecutar_backtest(dias_minimos=0)  # 0 para test inmediato
    print(f"\nTotal señales: {resultado['total']}")
    print(f"Evaluadas: {resultado['evaluadas']}")
    print(f"Correctas: {resultado['correctas']}")
    print(f"Incorrectas: {resultado['incorrectas']}")
    print(f"Tasa de éxito: {resultado['tasa_exito']}%")
    print("\nDetalle:")
    for d in resultado["detalle"]:
        icon = "✅" if d["resultado"] == "correcto" else ("❌" if d["resultado"] == "incorrecto" else "➡️")
        print(f"  {icon} {d['señal'][:50]} | {d['direccion']} | {d['movimiento_pct']:+.2f}% | {d['resultado']}")
