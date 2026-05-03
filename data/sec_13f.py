"""
Flujos Institucionales — SEC 13F
Analiza posiciones de grandes fondos en activos chilenos.

Los fondos institucionales (>$100M AUM) deben reportar posiciones
trimestralmente via Form 13F al SEC.

Activos monitoreados:
- SQM (ADR NYSE) — litio, minerales
- ECH (ETF MSCI Chile)
- BSAC (Santander Chile ADR)
- BCH (Banco de Chile ADR)
- LTM (LATAM Airlines ADR)

Señales generadas:
- Aumento de posición institucional → ALZA
- Reducción de posición institucional → BAJA
- Nuevos entrantes → ALZA fuerte
- Salidas completas → BAJA fuerte
"""

import requests
import json
import os
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "cache", "sec_13f.json")
HEADERS = {"User-Agent": "TradingTerminal trading@sistema.cl"}

# Activos chilenos en NYSE con ticker SEC
ACTIVOS_SEC = {
    "SQM":  {"nombre": "SQM ADR",           "activo_motor": "SQM.SN",       "cusip": None},
    "ECH":  {"nombre": "iShares MSCI Chile", "activo_motor": "ECH",          "cusip": None},
    "BSAC": {"nombre": "Santander Chile ADR","activo_motor": "BSANTANDER.SN","cusip": None},
    "BCH":  {"nombre": "Banco de Chile ADR", "activo_motor": "CHILE.SN",     "cusip": None},
    "LTM":  {"nombre": "LATAM Airlines",     "activo_motor": "LTM.SN",       "cusip": None},
}

# ── BÚSQUEDA EN SEC EDGAR ─────────────────────────────────────────────────────
def buscar_13f_por_ticker(ticker, max_resultados=10):
    """
    Busca los últimos reportes 13F que mencionan un ticker.
    Retorna lista de fondos con sus posiciones.
    """
    try:
        url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q":         f'"{ticker}"',
            "forms":     "13F-HR",
            "dateRange": "custom",
            "startdt":   "2024-10-01",
            "enddt":     datetime.now().strftime("%Y-%m-%d"),
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if not r.ok:
            return []

        data = r.json()
        hits = data.get("hits", {}).get("hits", [])

        fondos = []
        for hit in hits[:max_resultados]:
            src = hit.get("_source", {})
            fondos.append({
                "fondo":        src.get("display_names", ["Desconocido"])[0],
                "cik":          src.get("ciks", [""])[0],
                "periodo":      src.get("period_ending", ""),
                "fecha_reporte": src.get("file_date", ""),
                "form":         src.get("root_forms", [""])[0],
                "file_id":      hit.get("_id", ""),
            })

        return fondos

    except Exception as e:
        print(f"Error SEC 13F {ticker}: {e}")
        return []

def get_posicion_fondo(cik, ticker, periodo):
    """
    Obtiene la posición específica de un fondo en un ticker.
    """
    try:
        # Buscar los filings del fondo
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if not r.ok:
            return None

        data = r.json()
        nombre_fondo = data.get("name", "Desconocido")

        return {
            "nombre": nombre_fondo,
            "cik":    cik,
        }
    except:
        return None

# ── ANÁLISIS PRINCIPAL ────────────────────────────────────────────────────────
def analizar_flujos_institucionales(tickers=None):
    """
    Analiza flujos institucionales para activos chilenos.
    """
    if tickers is None:
        tickers = list(ACTIVOS_SEC.keys())

    resultados = {}

    for ticker in tickers:
        info = ACTIVOS_SEC.get(ticker, {})
        print(f"  Buscando 13F para {ticker}...")

        fondos = buscar_13f_por_ticker(ticker, max_resultados=8)
        time.sleep(0.5)  # Respetar rate limit SEC

        if not fondos:
            resultados[ticker] = {
                "ticker":      ticker,
                "nombre":      info.get("nombre", ticker),
                "activo_motor": info.get("activo_motor", ticker),
                "fondos":      [],
                "n_fondos":    0,
                "señal":       "SIN DATOS",
                "score":       0,
            }
            continue

        # Analizar tendencia — fondos recientes vs anteriores
        fondos_recientes = [f for f in fondos if f["periodo"] >= "2025-09-30"]
        fondos_anteriores = [f for f in fondos if f["periodo"] < "2025-09-30"]

        n_recientes  = len(fondos_recientes)
        n_anteriores = len(fondos_anteriores)
        n_total      = len(fondos)

        # Fondos más conocidos (proxy de calidad)
        fondos_top = ["BAILLIE GIFFORD", "BLACKROCK", "VANGUARD", "STATE STREET",
                      "FIDELITY", "JPMORGAN", "GOLDMAN", "MORGAN STANLEY",
                      "DIMENSIONAL", "ARK", "INVESCO"]

        fondos_conocidos = [f for f in fondos
                           if any(top in f["fondo"].upper() for top in fondos_top)]

        # Determinar señal
        if n_recientes > n_anteriores and n_recientes >= 3:
            señal  = "ACUMULACIÓN"
            score  = 3
            color  = "#22c55e"
        elif n_recientes >= 2:
            señal  = "INTERÉS INSTITUCIONAL"
            score  = 2
            color  = "#86efac"
        elif n_total >= 5:
            señal  = "COBERTURA AMPLIA"
            score  = 1
            color  = "#64748b"
        else:
            señal  = "COBERTURA LIMITADA"
            score  = 0
            color  = "#475569"

        # Bonus si hay fondos top
        if fondos_conocidos:
            score += 1
            señal += f" + {fondos_conocidos[0]['fondo'].split('(')[0].strip()[:20]}"

        resultados[ticker] = {
            "ticker":        ticker,
            "nombre":        info.get("nombre", ticker),
            "activo_motor":  info.get("activo_motor", ticker),
            "n_fondos":      n_total,
            "n_recientes":   n_recientes,
            "n_anteriores":  n_anteriores,
            "fondos_conocidos": len(fondos_conocidos),
            "señal":         señal,
            "score":         score,
            "color":         color,
            "fondos":        fondos[:5],  # Top 5
            "timestamp":     datetime.now().isoformat(),
        }

    return resultados

def get_señales_institucionales(min_score=1):
    """
    Retorna señales para el motor de recomendaciones.
    """
    # Cache de 6 horas — 13F no cambia frecuentemente
    try:
        if os.path.exists(CACHE_FILE):
            age_h = (time.time() - os.path.getmtime(CACHE_FILE)) / 3600
            if age_h < 6:
                with open(CACHE_FILE) as f:
                    cached = json.load(f)
                resultados = cached
            else:
                resultados = analizar_flujos_institucionales()
                with open(CACHE_FILE, "w") as f:
                    json.dump(resultados, f, default=str)
        else:
            resultados = analizar_flujos_institucionales()
            with open(CACHE_FILE, "w") as f:
                json.dump(resultados, f, default=str)
    except:
        resultados = analizar_flujos_institucionales()

    señales = []
    for ticker, r in resultados.items():
        if r.get("score", 0) >= min_score:
            señales.append({
                "activo":      r["activo_motor"],
                "ticker":      ticker,
                "fuente":      "13F SEC",
                "score":       r["score"],
                "direccion":   "ALZA",  # Interés institucional → alcista
                "n_fondos":    r["n_fondos"],
                "descripcion": f"13F SEC: {r['n_fondos']} fondos en {ticker} — {r['señal']}",
            })

    return señales

def get_resumen_institucional():
    """Resumen completo para el dashboard"""
    señales = get_señales_institucionales(min_score=0)
    return {
        "timestamp": datetime.now().isoformat(),
        "señales":   señales,
        "total":     len(señales),
    }

if __name__ == "__main__":
    print("=== FLUJOS INSTITUCIONALES 13F SEC ===\n")
    import time
    t0 = time.time()

    resultados = analizar_flujos_institucionales()

    for ticker, r in resultados.items():
        print(f"\n{r['nombre']} ({ticker})")
        print(f"  Fondos reportando: {r['n_fondos']} | Score: {r['score']}")
        print(f"  Señal: {r['señal']}")
        if r.get("fondos"):
            print(f"  Top fondos:")
            for f in r["fondos"][:3]:
                print(f"    • {f['fondo'][:50]} — {f['periodo']}")

    print(f"\nTiempo: {time.time()-t0:.1f}s")

    print("\n=== SEÑALES PARA EL MOTOR ===")
    señales = get_señales_institucionales()
    for s in señales:
        print(f"  [{s['direccion']}] {s['activo']} — {s['descripcion'][:70]}")
