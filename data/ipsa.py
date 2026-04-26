"""
Módulo IPSA completo — 30 acciones del S&P/CLX IPSA.
Obtiene precios, variaciones y clasificación por sector.
"""

import yfinance as yf
import pandas as pd

# ── COMPONENTES IPSA ──────────────────────────────────────────────────────────
IPSA_COMPONENTES = {
    # Bancos
    "BCI.SN":        {"nombre": "Banco BCI",           "sector": "Bancos",     "peso": "alto"},
    "BSANTANDER.SN": {"nombre": "Banco Santander",     "sector": "Bancos",     "peso": "alto"},
    "CHILE.SN":      {"nombre": "Banco de Chile",      "sector": "Bancos",     "peso": "alto"},
    "ITAUCL.SN":     {"nombre": "Itaú Chile",          "sector": "Bancos",     "peso": "medio"},

    # Minería
    "SQM-B.SN":      {"nombre": "SQM",                 "sector": "Minería",    "peso": "alto"},
    "CAP.SN":        {"nombre": "CAP",                  "sector": "Minería",    "peso": "medio"},

    # Energía
    "COPEC.SN":      {"nombre": "Copec",               "sector": "Energía",    "peso": "alto"},
    "COLBUN.SN":     {"nombre": "Colbún",              "sector": "Energía",    "peso": "medio"},
    "ENELCHILE.SN":  {"nombre": "Enel Chile",          "sector": "Energía",    "peso": "medio"},
    "ENELAM.SN":     {"nombre": "Enel Américas",       "sector": "Energía",    "peso": "medio"},
    "ECL.SN":        {"nombre": "ECL",                  "sector": "Energía",    "peso": "bajo"},
    "IAM.SN":        {"nombre": "Aguas Andinas (IAM)", "sector": "Utilities",  "peso": "bajo"},
    "AGUAS-A.SN":    {"nombre": "Aguas Andinas",       "sector": "Utilities",  "peso": "medio"},

    # Retail
    "FALABELLA.SN":  {"nombre": "Falabella",           "sector": "Retail",     "peso": "alto"},
    "CENCOSUD.SN":   {"nombre": "Cencosud",            "sector": "Retail",     "peso": "alto"},
    "CENCOMALLS.SN": {"nombre": "Cencosud Shopping",   "sector": "Retail",     "peso": "medio"},
    "RIPLEY.SN":     {"nombre": "Ripley",               "sector": "Retail",     "peso": "bajo"},
    "HITES.SN":      {"nombre": "Hites",                "sector": "Retail",     "peso": "bajo"},
    "FORUS.SN":      {"nombre": "Forus",                "sector": "Retail",     "peso": "bajo"},
    "SMU.SN":        {"nombre": "SMU",                  "sector": "Retail",     "peso": "bajo"},

    # Telecom
    "ENTEL.SN":      {"nombre": "Entel",               "sector": "Telecom",    "peso": "medio"},

    # Industria / Papel
    "CMPC.SN":       {"nombre": "CMPC",                "sector": "Industria",  "peso": "alto"},

    # Transporte
    "LTM.SN":        {"nombre": "LATAM Airlines",      "sector": "Transporte", "peso": "medio"},
    "VAPORES.SN":    {"nombre": "CSAV",                "sector": "Transporte", "peso": "bajo"},

    # Inmobiliario / Malls
    "MALLPLAZA.SN":  {"nombre": "Mall Plaza",          "sector": "Inmobiliario","peso": "medio"},
    "PARAUCO.SN":    {"nombre": "Parque Arauco",       "sector": "Inmobiliario","peso": "medio"},

    # Bebidas / Alimentos
    "CCU.SN":        {"nombre": "CCU",                  "sector": "Consumo",    "peso": "alto"},
    "ANDINA-B.SN":   {"nombre": "Embotelladora Andina","sector": "Consumo",    "peso": "medio"},
    "CONCHATORO.SN": {"nombre": "Concha y Toro",       "sector": "Consumo",    "peso": "bajo"},

    # Salud / Financiero
    "ILC.SN":        {"nombre": "ILC",                  "sector": "Financiero", "peso": "medio"},
}

# Sectores del IPSA con su impacto macro
SECTORES_IMPACTO = {
    "Bancos":       ["TPM", "CLP/USD"],
    "Minería":      ["cobre", "litio", "CLP/USD"],
    "Energía":      ["petróleo", "sequía", "tarifas"],
    "Utilities":    ["tarifas", "sequía"],
    "Retail":       ["consumo", "IPC", "empleo"],
    "Telecom":      ["regulación", "competencia"],
    "Industria":    ["celulosa", "exportaciones"],
    "Transporte":   ["petróleo", "turismo"],
    "Inmobiliario": ["tasas", "construcción"],
    "Consumo":      ["IPC", "empleo", "tipo de cambio"],
    "Financiero":   ["TPM", "pensiones"],
}

def get_precios_ipsa():
    """
    Obtiene precios y variaciones del día para las 30 acciones del IPSA.
    Retorna DataFrame ordenado por variación descendente.
    """
    resultados = []
    tickers = list(IPSA_COMPONENTES.keys())

    try:
        # Descarga en batch para eficiencia
        data = yf.download(tickers, period="5d", progress=False, threads=True)
        closes = data["Close"] if "Close" in data else data.get("Adj Close", pd.DataFrame())

        for ticker in tickers:
            meta = IPSA_COMPONENTES[ticker]
            try:
                serie = closes[ticker].dropna()
                if len(serie) < 2:
                    continue
                precio = round(serie.iloc[-1], 0)
                cambio = round(((serie.iloc[-1] / serie.iloc[-2]) - 1) * 100, 2)
                resultados.append({
                    "ticker":   ticker,
                    "nombre":   meta["nombre"],
                    "sector":   meta["sector"],
                    "peso":     meta["peso"],
                    "precio":   precio,
                    "cambio_pct": cambio,
                    "señal":    "🟢" if cambio > 0 else "🔴",
                })
            except:
                continue
    except Exception as e:
        print(f"Error batch IPSA: {e}")
        # Fallback individual
        for ticker, meta in IPSA_COMPONENTES.items():
            try:
                h = yf.Ticker(ticker).history(period="5d")
                if len(h) < 2:
                    continue
                precio = round(h["Close"].iloc[-1], 0)
                cambio = round(((h["Close"].iloc[-1] / h["Close"].iloc[-2]) - 1) * 100, 2)
                resultados.append({
                    "ticker":   ticker,
                    "nombre":   meta["nombre"],
                    "sector":   meta["sector"],
                    "peso":     meta["peso"],
                    "precio":   precio,
                    "cambio_pct": cambio,
                    "señal":    "🟢" if cambio > 0 else "🔴",
                })
            except:
                continue

    df = pd.DataFrame(resultados)
    if not df.empty:
        df = df.sort_values("cambio_pct", ascending=False)
    return df

def get_resumen_sectorial(df_ipsa):
    """
    Agrupa el IPSA por sector y calcula variación promedio.
    """
    if df_ipsa.empty:
        return pd.DataFrame()

    resumen = df_ipsa.groupby("sector").agg(
        variacion_prom=("cambio_pct", "mean"),
        n_acciones=("ticker", "count"),
        mejor=("cambio_pct", "max"),
        peor=("cambio_pct", "min"),
    ).round(2).reset_index()

    resumen = resumen.sort_values("variacion_prom", ascending=False)
    resumen["señal"] = resumen["variacion_prom"].apply(lambda x: "🟢" if x > 0 else "🔴")
    return resumen

def get_top_bottom_ipsa(df_ipsa, n=5):
    """Retorna top N ganadoras y bottom N perdedoras del día."""
    if df_ipsa.empty:
        return pd.DataFrame(), pd.DataFrame()
    top = df_ipsa.nlargest(n, "cambio_pct")
    bottom = df_ipsa.nsmallest(n, "cambio_pct")
    return top, bottom

def get_amplitud_mercado(df_ipsa):
    """
    Calcula amplitud del mercado: % acciones subiendo vs bajando.
    Indicador de salud del mercado.
    """
    if df_ipsa.empty:
        return {}
    subiendo = len(df_ipsa[df_ipsa["cambio_pct"] > 0])
    bajando  = len(df_ipsa[df_ipsa["cambio_pct"] < 0])
    neutras  = len(df_ipsa[df_ipsa["cambio_pct"] == 0])
    total    = len(df_ipsa)
    return {
        "subiendo": subiendo,
        "bajando":  bajando,
        "neutras":  neutras,
        "total":    total,
        "ratio":    round(subiendo / total * 100, 1),
        "sesgo":    "ALCISTA" if subiendo > bajando else ("BAJISTA" if bajando > subiendo else "NEUTRO"),
    }

if __name__ == "__main__":
    print("=== IPSA COMPLETO ===")
    df = get_precios_ipsa()
    if not df.empty:
        print(df[["ticker","nombre","sector","precio","cambio_pct"]].to_string(index=False))
        print("\n=== SECTORES ===")
        print(get_resumen_sectorial(df).to_string(index=False))
        print("\n=== AMPLITUD ===")
        amp = get_amplitud_mercado(df)
        print(f"Subiendo: {amp['subiendo']} | Bajando: {amp['bajando']} | Sesgo: {amp['sesgo']}")
