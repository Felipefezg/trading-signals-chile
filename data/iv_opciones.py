"""
Volatilidad Implícita y Análisis de Opciones
Analiza cadenas de opciones para detectar expectativas institucionales.

Métricas clave:
- IV ATM (at-the-money): volatilidad esperada del activo
- IV Skew (puts vs calls): dirección esperada del movimiento
- IV Percentil: qué tan alta/baja está la IV vs histórico
- Put/Call Open Interest: posicionamiento institucional
- Unusual options activity: órdenes grandes inusuales

Señales:
- Skew puts > calls en 10%+ → institucionales comprando protección → BAJISTA
- Skew calls > puts en 10%+ → institucionales apostando al alza → ALCISTA
- IV muy baja (< percentil 20) → movimiento grande inminente → prepararse
- IV spike súbito → noticia inminente → cautela
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os, json, time

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "cache", "iv_opciones.json")

# Activos con opciones disponibles en USA
ACTIVOS_OPCIONES = {
    "SQM":  {"nombre": "SQM ADR",        "activo_motor": "SQM.SN",        "impacto": ["SQM.SN", "SQM-B.SN"]},
    "ECH":  {"nombre": "iShares Chile",   "activo_motor": "ECH",           "impacto": ["ECH", "BSANTANDER.SN", "CHILE.SN"]},
    "GLD":  {"nombre": "Gold ETF",        "activo_motor": "GC=F",          "impacto": ["GC=F"]},
    "GDX":  {"nombre": "Gold Miners ETF", "activo_motor": "GC=F",          "impacto": ["GC=F", "CAP.SN"]},
    "SPY":  {"nombre": "S&P 500 ETF",     "activo_motor": "^GSPC",         "impacto": ["ECH", "^GSPC"]},
    "TLT":  {"nombre": "20Y Treasury",    "activo_motor": "TLT",           "impacto": ["COLBUN.SN", "AGUAS-A.SN", "MALLPLAZA.SN"]},
    "EEM":  {"nombre": "Emerging Markets","activo_motor": "ECH",           "impacto": ["ECH", "CLP/USD"]},
    "USO":  {"nombre": "Oil ETF",         "activo_motor": "CL=F",          "impacto": ["COPEC.SN", "CL=F"]},
}

# ── ANÁLISIS DE CADENA DE OPCIONES ────────────────────────────────────────────
def analizar_opciones(ticker, info):
    """
    Analiza la cadena de opciones completa para un activo.
    """
    try:
        t = yf.Ticker(ticker)
        expirations = t.options

        if not expirations:
            return None

        precio_actual = float(t.history(period="1d")["Close"].iloc[-1])
        if precio_actual <= 0:
            return None

        # Analizar los 2 primeros vencimientos (más líquidos)
        resultados_venc = []
        for exp in expirations[:2]:
            try:
                chain = t.option_chain(exp)
                calls = chain.calls
                puts  = chain.puts

                if calls.empty or puts.empty:
                    continue

                # ── IV ATM ────────────────────────────────────────────────────
                rango_atm = precio_actual * 0.05
                calls_atm = calls[abs(calls["strike"] - precio_actual) <= rango_atm]
                puts_atm  = puts[abs(puts["strike"]  - precio_actual) <= rango_atm]

                iv_calls_atm = float(calls_atm["impliedVolatility"].mean()) if not calls_atm.empty else 0
                iv_puts_atm  = float(puts_atm["impliedVolatility"].mean())  if not puts_atm.empty else 0
                iv_skew      = iv_puts_atm - iv_calls_atm

                # ── OPEN INTEREST ─────────────────────────────────────────────
                oi_calls = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
                oi_puts  = int(puts["openInterest"].sum())  if "openInterest" in puts.columns else 0
                oi_ratio = oi_puts / oi_calls if oi_calls > 0 else 1

                # ── VOLUMEN ───────────────────────────────────────────────────
                vol_calls = int(calls["volume"].fillna(0).sum()) if "volume" in calls.columns else 0
                vol_puts  = int(puts["volume"].fillna(0).sum())  if "volume" in puts.columns else 0
                vol_ratio = vol_puts / vol_calls if vol_calls > 0 else 1

                # ── UNUSUAL ACTIVITY ──────────────────────────────────────────
                # Volumen >> Open Interest = actividad inusual
                calls["vol_oi"] = calls["volume"].fillna(0) / calls["openInterest"].replace(0, 1).fillna(1)
                puts["vol_oi"]  = puts["volume"].fillna(0)  / puts["openInterest"].replace(0, 1).fillna(1)

                unusual_calls = calls[calls["vol_oi"] > 5]
                unusual_puts  = puts[puts["vol_oi"]  > 5]

                resultados_venc.append({
                    "expiracion":    exp,
                    "iv_calls_atm":  round(iv_calls_atm * 100, 1),
                    "iv_puts_atm":   round(iv_puts_atm * 100, 1),
                    "iv_skew":       round(iv_skew * 100, 1),
                    "oi_calls":      oi_calls,
                    "oi_puts":       oi_puts,
                    "oi_ratio":      round(oi_ratio, 2),
                    "vol_calls":     vol_calls,
                    "vol_puts":      vol_puts,
                    "vol_ratio":     round(vol_ratio, 2),
                    "unusual_calls": len(unusual_calls),
                    "unusual_puts":  len(unusual_puts),
                })
            except:
                continue

        if not resultados_venc:
            return None

        # Consolidar vencimientos
        iv_skew_prom   = np.mean([r["iv_skew"]   for r in resultados_venc])
        iv_calls_prom  = np.mean([r["iv_calls_atm"] for r in resultados_venc])
        iv_puts_prom   = np.mean([r["iv_puts_atm"]  for r in resultados_venc])
        oi_ratio_prom  = np.mean([r["oi_ratio"]   for r in resultados_venc])
        vol_ratio_prom = np.mean([r["vol_ratio"]  for r in resultados_venc])
        unusual_puts   = sum(r["unusual_puts"]   for r in resultados_venc)
        unusual_calls  = sum(r["unusual_calls"]  for r in resultados_venc)

        # ── SEÑAL ─────────────────────────────────────────────────────────────
        score_baja = 0
        score_alza = 0
        señales    = []

        # IV Skew — puts más caros que calls → bajista
        if iv_skew_prom > 15:
            score_baja += 3
            señales.append(f"Skew puts {iv_skew_prom:+.1f}% — protección bajista extrema")
        elif iv_skew_prom > 8:
            score_baja += 2
            señales.append(f"Skew puts {iv_skew_prom:+.1f}% — sesgo bajista")
        elif iv_skew_prom < -10:
            score_alza += 3
            señales.append(f"Skew calls {abs(iv_skew_prom):.1f}% — apuesta alcista fuerte")
        elif iv_skew_prom < -5:
            score_alza += 2
            señales.append(f"Skew calls {abs(iv_skew_prom):.1f}% — sesgo alcista")

        # OI ratio — más puts que calls → bajista
        if oi_ratio_prom > 1.5:
            score_baja += 2
            señales.append(f"P/C OI ratio {oi_ratio_prom:.2f} — más puts abiertas")
        elif oi_ratio_prom < 0.7:
            score_alza += 2
            señales.append(f"P/C OI ratio {oi_ratio_prom:.2f} — más calls abiertas")

        # Actividad inusual
        if unusual_puts > unusual_calls * 2:
            score_baja += 2
            señales.append(f"Actividad inusual en puts ({unusual_puts} strikes)")
        elif unusual_calls > unusual_puts * 2:
            score_alza += 2
            señales.append(f"Actividad inusual en calls ({unusual_calls} strikes)")

        # IV alta → mercado nervioso → volatilidad esperada alta
        iv_promedio = (iv_calls_prom + iv_puts_prom) / 2
        if iv_promedio > 60:
            señales.append(f"IV muy alta {iv_promedio:.1f}% — mercado espera movimiento grande")
        elif iv_promedio < 20:
            señales.append(f"IV muy baja {iv_promedio:.1f}% — mercado complaciente")

        # Dirección final
        if score_baja > score_alza and score_baja >= 2:
            direccion = "BAJA"
            accion    = "VENDER"
            score     = score_baja
        elif score_alza > score_baja and score_alza >= 2:
            direccion = "ALZA"
            accion    = "COMPRAR"
            score     = score_alza
        else:
            direccion = "NEUTRO"
            accion    = "MANTENER"
            score     = 0

        return {
            "ticker":        ticker,
            "nombre":        info["nombre"],
            "activo_motor":  info["activo_motor"],
            "impacto":       info["impacto"],
            "precio":        round(precio_actual, 4),
            "iv_calls":      round(iv_calls_prom, 1),
            "iv_puts":       round(iv_puts_prom, 1),
            "iv_skew":       round(iv_skew_prom, 1),
            "iv_promedio":   round(iv_promedio, 1),
            "oi_ratio":      round(oi_ratio_prom, 2),
            "vol_ratio":     round(vol_ratio_prom, 2),
            "unusual_puts":  unusual_puts,
            "unusual_calls": unusual_calls,
            "direccion":     direccion,
            "accion":        accion,
            "score":         score,
            "señales":       señales,
            "vencimientos":  resultados_venc,
            "timestamp":     datetime.now().isoformat(),
        }

    except Exception as e:
        return None

def get_señales_iv(min_score=2):
    """
    Retorna señales de IV para el motor de recomendaciones.
    Genera señales para el activo directo Y para activos impactados.
    """
    # Cache 60 minutos — IV cambia lentamente
    try:
        if os.path.exists(CACHE_FILE):
            age_min = (time.time() - os.path.getmtime(CACHE_FILE)) / 60
            if age_min < 60:
                with open(CACHE_FILE) as f:
                    cached = json.load(f)
                return _extraer_señales(cached, min_score)
    except:
        pass

    resultados = {}
    for ticker, info in ACTIVOS_OPCIONES.items():
        r = analizar_opciones(ticker, info)
        if r:
            resultados[ticker] = r
        time.sleep(0.3)

    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(resultados, f, default=str)
    except:
        pass

    return _extraer_señales(resultados, min_score)

def _extraer_señales(resultados, min_score):
    señales = []
    for ticker, r in resultados.items():
        if r.get("score", 0) >= min_score and r.get("accion") != "MANTENER":
            # Señal para el activo principal
            señales.append({
                "activo":      r["activo_motor"],
                "fuente":      "IV Opciones",
                "score":       r["score"],
                "direccion":   r["direccion"],
                "descripcion": f"IV {r['nombre']}: {r['señales'][0] if r['señales'] else ''}",
                "iv_skew":     r["iv_skew"],
                "iv_promedio": r["iv_promedio"],
            })
            # Señales para activos impactados
            for activo_impactado in r.get("impacto", []):
                if activo_impactado != r["activo_motor"]:
                    señales.append({
                        "activo":      activo_impactado,
                        "fuente":      "IV Opciones",
                        "score":       max(1, r["score"] - 1),
                        "direccion":   r["direccion"],
                        "descripcion": f"IV {r['nombre']} impacta {activo_impactado}: {r['señales'][0][:50] if r['señales'] else ''}",
                        "iv_skew":     r["iv_skew"],
                        "iv_promedio": r["iv_promedio"],
                    })
    return sorted(señales, key=lambda x: x["score"], reverse=True)

def get_resumen_iv():
    """Resumen completo para el dashboard"""
    resultados = {}
    for ticker, info in ACTIVOS_OPCIONES.items():
        r = analizar_opciones(ticker, info)
        if r:
            resultados[ticker] = r
        time.sleep(0.3)

    alertas = [r for r in resultados.values() if r.get("score", 0) >= 2]
    return {
        "timestamp": datetime.now().isoformat(),
        "total":     len(resultados),
        "alertas":   len(alertas),
        "datos":     resultados,
        "señales":   get_señales_iv(),
    }

if __name__ == "__main__":
    print("=== VOLATILIDAD IMPLÍCITA Y OPCIONES ===\n")
    import time
    t0 = time.time()

    for ticker, info in ACTIVOS_OPCIONES.items():
        r = analizar_opciones(ticker, info)
        if not r:
            print(f"❌ {info['nombre']} ({ticker}) — sin datos")
            continue

        icon = "🔴" if r["accion"] == "VENDER" else ("🟢" if r["accion"] == "COMPRAR" else "⚪")
        print(f"{icon} {r['nombre']:<20} IV:{r['iv_promedio']:.1f}% Skew:{r['iv_skew']:+.1f}% P/C:{r['oi_ratio']:.2f} Score:{r['score']}")
        for s in r["señales"]:
            print(f"   → {s}")
        print()

    print(f"\nTiempo: {time.time()-t0:.1f}s")
    print("\n=== SEÑALES PARA EL MOTOR ===")
    señales = get_señales_iv()
    for s in señales[:10]:
        print(f"  [{s['direccion']}] {s['activo']} Score:{s['score']} — {s['descripcion'][:70]}")
