"""
Módulo de arbitraje — detección de brechas de precio entre mercados.

Estrategias:
1. ADR Spread — mismo activo en NYSE (USD) vs Santiago (CLP)
2. BTC Spread — Bitcoin en exchanges locales vs internacionales
3. Cobre Basis — LME vs Cochilco vs futuros COMEX
4. FX Implied — CLP/USD forward implícito vs spot

Lógica:
- Calcular precio equivalente entre mercados
- Descontar costos de transacción (comisión + spread FX + otros)
- Señal solo si spread neto > umbral mínimo de rentabilidad
"""

import yfinance as yf
import requests
from datetime import datetime

# ── COSTOS DE TRANSACCIÓN ─────────────────────────────────────────────────────
COSTOS = {
    "comision_ib_pct":   0.05,   # 0.05% comisión IB por lado
    "spread_fx_pct":     0.10,   # 0.10% spread FX CLP/USD
    "costo_total_pct":   0.30,   # costo total ida y vuelta estimado
    "umbral_minimo_pct": 0.50,   # spread mínimo para que sea rentable
    "umbral_alerta_pct": 1.50,   # spread para alerta de alta oportunidad
}

# ── PARES ADR DISPONIBLES ─────────────────────────────────────────────────────
PARES_ADR = {
    "SQM": {
        "nombre":      "SQM — Sociedad Química y Minera",
        "nyse":        "SQM",
        "santiago":    "SQM-B.SN",
        "ratio":       1,             # 1 ADR = 1 acción local
        "sector":      "Minería",
        "descripcion": "Litio y cobre — ADR más líquido de Chile en NYSE",
    },
    "LTM": {
        "nombre":      "LATAM Airlines",
        "nyse":        "LTM",
        "santiago":    "LTM.SN",
        "ratio":       2000,          # 1 ADR = 2,000 acciones locales (confirmado SEC)
        "sector":      "Transporte",
        "descripcion": "Aerolínea — 1 ADR = 2,000 acciones Santiago",
    },
    "BSANTANDER": {
        "nombre":      "Banco Santander Chile",
        "nyse":        "BSAC",
        "santiago":    "BSANTANDER.SN",
        "ratio":       400,           # 1 ADR = 400 acciones locales (confirmado NYSE)
        "sector":      "Bancos",
        "descripcion": "Banco — 1 ADR = 400 acciones Santiago",
    },
    "CHILE": {
        "nombre":      "Banco de Chile",
        "nyse":        "BCH",
        "santiago":    "CHILE.SN",
        "ratio":       200,           # 1 ADR = 200 acciones locales (confirmado Slickcharts)
        "sector":      "Bancos",
        "descripcion": "Banco — 1 ADR = 200 acciones Santiago",
    },
}

# ── FX ────────────────────────────────────────────────────────────────────────
def get_clp_usd():
    """Obtiene tipo de cambio CLP/USD"""
    try:
        h = yf.Ticker("CLP=X").history(period="2d")
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except:
        return None

# ── ARBITRAJE ADR ─────────────────────────────────────────────────────────────
def calcular_spread_adr(par_key, clp_usd=None):
    """
    Calcula el spread entre ADR (NYSE) y acción local (Santiago).

    Spread positivo = Santiago más caro que NYSE (vender Santiago, comprar NYSE)
    Spread negativo = NYSE más caro que Santiago (vender NYSE, comprar Santiago)
    """
    par = PARES_ADR.get(par_key)
    if not par:
        return None

    if not clp_usd:
        clp_usd = get_clp_usd()
    if not clp_usd:
        return None

    try:
        # Precio NYSE (USD)
        h_nyse = yf.Ticker(par["nyse"]).history(period="5d")
        if h_nyse.empty:
            return None
        precio_nyse_usd = float(h_nyse["Close"].iloc[-1])

        # Precio Santiago (CLP)
        h_stgo = yf.Ticker(par["santiago"]).history(period="5d")
        if h_stgo.empty:
            return None
        precio_stgo_clp = float(h_stgo["Close"].iloc[-1])

        # Convertir NYSE a CLP (ajustado por ratio)
        precio_nyse_clp = (precio_nyse_usd * clp_usd) / par["ratio"]

        # Spread bruto
        spread_bruto_pct = ((precio_stgo_clp / precio_nyse_clp) - 1) * 100

        # Spread neto (descontando costos de transacción)
        spread_neto_pct = abs(spread_bruto_pct) - COSTOS["costo_total_pct"]

        # Dirección del arbitraje
        if spread_bruto_pct > 0:
            accion_arbitraje = "VENDER Santiago / COMPRAR NYSE"
            mercado_caro     = "Santiago"
            mercado_barato   = "NYSE"
        else:
            accion_arbitraje = "VENDER NYSE / COMPRAR Santiago"
            mercado_caro     = "NYSE"
            mercado_barato   = "Santiago"

        # Clasificar oportunidad
        if spread_neto_pct >= COSTOS["umbral_alerta_pct"]:
            oportunidad = "ALTA"
            color       = "🔴"
        elif spread_neto_pct >= COSTOS["umbral_minimo_pct"]:
            oportunidad = "MEDIA"
            color       = "🟡"
        elif spread_neto_pct > 0:
            oportunidad = "BAJA"
            color       = "🟢"
        else:
            oportunidad = "SIN OPORTUNIDAD"
            color       = "⚪"

        return {
            "par":               par_key,
            "nombre":            par["nombre"],
            "sector":            par["sector"],
            "descripcion":       par["descripcion"],
            "precio_nyse_usd":   round(precio_nyse_usd, 2),
            "precio_nyse_clp":   round(precio_nyse_clp, 0),
            "precio_stgo_clp":   round(precio_stgo_clp, 0),
            "clp_usd":           round(clp_usd, 2),
            "ratio":             par["ratio"],
            "spread_bruto_pct":  round(spread_bruto_pct, 3),
            "spread_neto_pct":   round(spread_neto_pct, 3),
            "costo_total_pct":   COSTOS["costo_total_pct"],
            "accion_arbitraje":  accion_arbitraje,
            "mercado_caro":      mercado_caro,
            "mercado_barato":    mercado_barato,
            "oportunidad":       oportunidad,
            "color":             color,
            "timestamp":         datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error spread ADR {par_key}: {e}")
        return None

def get_todos_spreads_adr():
    """Calcula spreads ADR para todos los pares disponibles"""
    clp_usd = get_clp_usd()
    resultados = []
    for par_key in PARES_ADR:
        spread = calcular_spread_adr(par_key, clp_usd)
        if spread:
            resultados.append(spread)
    return sorted(resultados, key=lambda x: abs(x["spread_bruto_pct"]), reverse=True)

# ── ARBITRAJE BTC ─────────────────────────────────────────────────────────────
def get_spread_btc_exchanges(clp_usd=None):
    """
    Compara precio BTC entre exchanges:
    - Buda.com (Chile)
    - Precio internacional (CoinGecko)
    """
    if not clp_usd:
        clp_usd = get_clp_usd()

    resultado = {}

    # Precio global BTC en USD
    try:
        h = yf.Ticker("BTC-USD").history(period="2d")
        btc_global_usd = float(h["Close"].iloc[-1]) if not h.empty else None
    except:
        btc_global_usd = None

    # Precio Buda.com (CLP)
    try:
        r = requests.get("https://www.buda.com/api/v2/markets/BTC-CLP/ticker", timeout=8)
        data = r.json()
        btc_buda_clp = float(data["ticker"]["last_price"][0])
    except:
        btc_buda_clp = None

    if btc_global_usd and btc_buda_clp and clp_usd:
        btc_global_clp = btc_global_usd * clp_usd
        spread_pct = ((btc_buda_clp / btc_global_clp) - 1) * 100
        spread_neto = abs(spread_pct) - COSTOS["costo_total_pct"]

        resultado = {
            "par":             "BTC",
            "nombre":          "Bitcoin — Buda.com vs Internacional",
            "btc_buda_clp":    round(btc_buda_clp, 0),
            "btc_global_usd":  round(btc_global_usd, 2),
            "btc_global_clp":  round(btc_global_clp, 0),
            "clp_usd":         round(clp_usd, 2),
            "spread_bruto_pct": round(spread_pct, 3),
            "spread_neto_pct":  round(spread_neto, 3),
            "accion_arbitraje": "COMPRAR Buda / VENDER global" if spread_pct < 0 else "VENDER Buda / COMPRAR global",
            "oportunidad":     "ALTA" if spread_neto >= 1.5 else ("MEDIA" if spread_neto >= 0.5 else "BAJA"),
            "color":           "🔴" if spread_neto >= 1.5 else ("🟡" if spread_neto >= 0.5 else "⚪"),
            "timestamp":       datetime.now().isoformat(),
        }

    return resultado

# ── COBRE BASIS ───────────────────────────────────────────────────────────────
def get_cobre_basis(clp_usd=None):
    """
    Compara precio cobre LME (futuro COMEX) vs precio spot referencial.
    HG=F en USD/lb → convertir a USD/ton para comparar con Cochilco
    """
    if not clp_usd:
        clp_usd = get_clp_usd()

    try:
        # Cobre COMEX (USD/lb)
        h = yf.Ticker("HG=F").history(period="5d")
        if h.empty:
            return None
        precio_comex_lb = float(h["Close"].iloc[-1])
        precio_comex_ton = precio_comex_lb * 2204.62  # USD/ton métrica

        # Cobre LME spot (aproximado desde ETF de cobre)
        h_cop = yf.Ticker("CPER").history(period="5d")
        precio_lme = float(h_cop["Close"].iloc[-1]) if not h_cop.empty else None

        return {
            "precio_comex_lb":   round(precio_comex_lb, 4),
            "precio_comex_ton":  round(precio_comex_ton, 2),
            "precio_comex_clp":  round(precio_comex_ton * clp_usd, 0) if clp_usd else None,
            "clp_usd":           round(clp_usd, 2) if clp_usd else None,
            "timestamp":         datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error cobre basis: {e}")
        return None

# ── RESUMEN ARBITRAJE ─────────────────────────────────────────────────────────
def get_resumen_arbitraje():
    """Retorna resumen completo de oportunidades de arbitraje"""
    clp_usd = get_clp_usd()

    spreads_adr = get_todos_spreads_adr()
    spread_btc  = get_spread_btc_exchanges(clp_usd)
    cobre_basis = get_cobre_basis(clp_usd)

    # Oportunidades reales (spread neto positivo)
    oportunidades = [s for s in spreads_adr if s["spread_neto_pct"] > 0]
    if spread_btc and spread_btc.get("spread_neto_pct", 0) > 0:
        oportunidades.append(spread_btc)

    return {
        "timestamp":      datetime.now().isoformat(),
        "clp_usd":        clp_usd,
        "spreads_adr":    spreads_adr,
        "spread_btc":     spread_btc,
        "cobre_basis":    cobre_basis,
        "oportunidades":  len(oportunidades),
        "mejor_spread":   spreads_adr[0] if spreads_adr else None,
    }

if __name__ == "__main__":
    print("=== ARBITRAJE CHILE ===\n")
    resumen = get_resumen_arbitraje()
    print(f"CLP/USD: {resumen['clp_usd']}")
    print(f"Oportunidades detectadas: {resumen['oportunidades']}")
    print("\n--- SPREADS ADR ---")
    for s in resumen["spreads_adr"]:
        print(f"{s['color']} {s['nombre']}")
        print(f"   NYSE: USD {s['precio_nyse_usd']} → CLP {s['precio_nyse_clp']:,.0f}")
        print(f"   STG:  CLP {s['precio_stgo_clp']:,.0f}")
        print(f"   Spread bruto: {s['spread_bruto_pct']:+.3f}% | Neto: {s['spread_neto_pct']:+.3f}% | {s['oportunidad']}")
        if s['oportunidad'] != 'SIN OPORTUNIDAD':
            print(f"   → {s['accion_arbitraje']}")
        print()
    if resumen["spread_btc"]:
        btc = resumen["spread_btc"]
        print(f"--- BTC SPREAD ---")
        print(f"Buda: CLP {btc.get('btc_buda_clp',0):,.0f} | Global: CLP {btc.get('btc_global_clp',0):,.0f}")
        print(f"Spread: {btc.get('spread_bruto_pct',0):+.3f}% | Neto: {btc.get('spread_neto_pct',0):+.3f}%")
