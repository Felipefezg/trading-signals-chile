"""
Universo Maestro de Activos.
Fuente única de verdad para todos los módulos del sistema.

Todos los módulos de análisis deben importar desde aquí:
- analisis_tecnico.py
- analisis_mtf.py
- soporte_resistencia.py
- mercado_local.py
- backtesting.py

Categorías:
- IPSA_30: acciones del índice principal chileno
- SMALL_CAPS: acciones de menor capitalización pero líquidas
- ADRS_CHILE: ADRs chilenos en NYSE
- ETFS_CHILE: ETFs relacionados con Chile
- COMMODITIES: futuros de commodities relevantes para Chile
- CRYPTO: Bitcoin y otros
- ETFS_USA: ETFs de mercado americano
"""

# ── IPSA 30 ───────────────────────────────────────────────────────────────────
IPSA_30 = {
    "SQM-B.SN":     {"nombre": "SQM",              "sector": "Minería",              "peso_ipsa": 9.5,  "ib": "SQM",        "tipo": "Acción Chile", "yf": "SQM-B.SN"},
    "COPEC.SN":     {"nombre": "Copec",             "sector": "Energía",              "peso_ipsa": 8.2,  "ib": "COPEC",      "tipo": "Acción Chile", "yf": "COPEC.SN"},
    "BCI.SN":       {"nombre": "Banco BCI",         "sector": "Bancos",               "peso_ipsa": 7.8,  "ib": "BCI",        "tipo": "Acción Chile", "yf": "BCI.SN"},
    "BSANTANDER.SN":{"nombre": "Santander Chile",   "sector": "Bancos",               "peso_ipsa": 7.1,  "ib": "BSAC",       "tipo": "Acción USA/Chile","yf": "BSANTANDER.SN"},
    "CHILE.SN":     {"nombre": "Banco de Chile",    "sector": "Bancos",               "peso_ipsa": 6.9,  "ib": "BCH",        "tipo": "Acción USA/Chile","yf": "CHILE.SN"},
    "FALABELLA.SN": {"nombre": "Falabella",         "sector": "Retail",               "peso_ipsa": 5.8,  "ib": "FALABELLA",  "tipo": "Acción Chile", "yf": "FALABELLA.SN"},
    "CENCOSUD.SN":  {"nombre": "Cencosud",          "sector": "Retail",               "peso_ipsa": 4.9,  "ib": "CENCOSUD",   "tipo": "Acción Chile", "yf": "CENCOSUD.SN"},
    "CMPC.SN":      {"nombre": "CMPC",              "sector": "Industria",            "peso_ipsa": 4.7,  "ib": "CMPC",       "tipo": "Acción Chile", "yf": "CMPC.SN"},
    "COLBUN.SN":    {"nombre": "Colbún",            "sector": "Energía",              "peso_ipsa": 3.8,  "ib": "COLBUN",     "tipo": "Acción Chile", "yf": "COLBUN.SN"},
    "ENELCHILE.SN": {"nombre": "Enel Chile",        "sector": "Energía",              "peso_ipsa": 3.5,  "ib": "ENELCHILE",  "tipo": "Acción Chile", "yf": "ENELCHILE.SN"},
    "ENELAM.SN":    {"nombre": "Enel Américas",     "sector": "Energía",              "peso_ipsa": 3.2,  "ib": "ENELAM",     "tipo": "Acción Chile", "yf": "ENELAM.SN"},
    "ENTEL.SN":     {"nombre": "Entel",             "sector": "Telecomunicaciones",   "peso_ipsa": 2.9,  "ib": "ENTEL",      "tipo": "Acción Chile", "yf": "ENTEL.SN"},
    "LTM.SN":       {"nombre": "LATAM Airlines",    "sector": "Transporte",           "peso_ipsa": 2.8,  "ib": "LTM",        "tipo": "Acción USA/Chile","yf": "LTM.SN"},
    "CAP.SN":       {"nombre": "CAP",               "sector": "Minería",              "peso_ipsa": 2.5,  "ib": "CAP",        "tipo": "Acción Chile", "yf": "CAP.SN"},
    "CCU.SN":       {"nombre": "CCU",               "sector": "Consumo",              "peso_ipsa": 2.4,  "ib": "CCU",        "tipo": "Acción Chile", "yf": "CCU.SN"},
    "ITAUCL.SN":    {"nombre": "Itaú Chile",        "sector": "Bancos",               "peso_ipsa": 2.2,  "ib": "ITAUCL",     "tipo": "Acción Chile", "yf": "ITAUCL.SN"},
    "PARAUCO.SN":   {"nombre": "Parque Arauco",     "sector": "Inmobiliario",         "peso_ipsa": 2.0,  "ib": "PARAUCO",    "tipo": "Acción Chile", "yf": "PARAUCO.SN"},
    "MALLPLAZA.SN": {"nombre": "Mall Plaza",        "sector": "Inmobiliario",         "peso_ipsa": 1.9,  "ib": "MALLPLAZA",  "tipo": "Acción Chile", "yf": "MALLPLAZA.SN"},
    "RIPLEY.SN":    {"nombre": "Ripley",            "sector": "Retail",               "peso_ipsa": 1.8,  "ib": "RIPLEY",     "tipo": "Acción Chile", "yf": "RIPLEY.SN"},
    "AGUAS-A.SN":   {"nombre": "Aguas Andinas",     "sector": "Utilities",            "peso_ipsa": 1.7,  "ib": "AGUAS-A",    "tipo": "Acción Chile", "yf": "AGUAS-A.SN"},
    "VAPORES.SN":   {"nombre": "CSAV",              "sector": "Transporte",           "peso_ipsa": 1.6,  "ib": "VAPORES",    "tipo": "Acción Chile", "yf": "VAPORES.SN"},
    "ANDINA-B.SN":  {"nombre": "Andina",            "sector": "Consumo",              "peso_ipsa": 1.5,  "ib": "ANDINA-B",   "tipo": "Acción Chile", "yf": "ANDINA-B.SN"},
    "ILC.SN":       {"nombre": "ILC",               "sector": "Financiero",           "peso_ipsa": 1.4,  "ib": "ILC",        "tipo": "Acción Chile", "yf": "ILC.SN"},
    "CONCHATORO.SN":{"nombre": "Concha y Toro",     "sector": "Consumo",              "peso_ipsa": 1.3,  "ib": "CONCHATORO", "tipo": "Acción Chile", "yf": "CONCHATORO.SN"},
    "FORUS.SN":     {"nombre": "Forus",             "sector": "Retail",               "peso_ipsa": 1.2,  "ib": "FORUS",      "tipo": "Acción Chile", "yf": "FORUS.SN"},
    "SMU.SN":       {"nombre": "SMU",               "sector": "Retail",               "peso_ipsa": 1.1,  "ib": "SMU",        "tipo": "Acción Chile", "yf": "SMU.SN"},
    "ECL.SN":       {"nombre": "ECL",               "sector": "Energía",              "peso_ipsa": 1.0,  "ib": "ECL",        "tipo": "Acción Chile", "yf": "ECL.SN"},
    "SONDA.SN":     {"nombre": "Sonda",             "sector": "Tecnología",           "peso_ipsa": 0.9,  "ib": "SONDA",      "tipo": "Acción Chile", "yf": "SONDA.SN"},
}

# ── SMALL CAPS ────────────────────────────────────────────────────────────────
SMALL_CAPS = {
    "BESALCO.SN":   {"nombre": "Besalco",       "sector": "Construcción",  "peso_ipsa": 0, "ib": "BESALCO",   "tipo": "Acción Chile", "yf": "BESALCO.SN"},
    "SALFACORP.SN": {"nombre": "Salfacorp",     "sector": "Construcción",  "peso_ipsa": 0, "ib": "SALFACORP", "tipo": "Acción Chile", "yf": "SALFACORP.SN"},
    "SOCOVESA.SN":  {"nombre": "Socovesa",      "sector": "Inmobiliario",  "peso_ipsa": 0, "ib": "SOCOVESA",  "tipo": "Acción Chile", "yf": "SOCOVESA.SN"},
    "INGEVEC.SN":   {"nombre": "Ingevec",       "sector": "Construcción",  "peso_ipsa": 0, "ib": "INGEVEC",   "tipo": "Acción Chile", "yf": "INGEVEC.SN"},
    "HITES.SN":     {"nombre": "Hites",         "sector": "Retail",        "peso_ipsa": 0, "ib": "HITES",     "tipo": "Acción Chile", "yf": "HITES.SN"},
    "MOLYMET.SN":   {"nombre": "Molymet",       "sector": "Minería",       "peso_ipsa": 0, "ib": "MOLYMET",   "tipo": "Acción Chile", "yf": "MOLYMET.SN"},
    "QUINENCO.SN":  {"nombre": "Quiñenco",      "sector": "Holding",       "peso_ipsa": 0, "ib": "QUINENCO",  "tipo": "Acción Chile", "yf": "QUINENCO.SN"},
    "MASISA.SN":    {"nombre": "Masisa",        "sector": "Industria",     "peso_ipsa": 0, "ib": "MASISA",    "tipo": "Acción Chile", "yf": "MASISA.SN"},
    "HABITAT.SN":   {"nombre": "AFP Habitat",   "sector": "Financiero",    "peso_ipsa": 0, "ib": "HABITAT",   "tipo": "Acción Chile", "yf": "HABITAT.SN"},
    "PROVIDA.SN":   {"nombre": "AFP Provida",   "sector": "Financiero",    "peso_ipsa": 0, "ib": "PROVIDA",   "tipo": "Acción Chile", "yf": "PROVIDA.SN"},
    "MARINSA.SN":   {"nombre": "Marinsa",       "sector": "Transporte",    "peso_ipsa": 0, "ib": "MARINSA",   "tipo": "Acción Chile", "yf": "MARINSA.SN"},
}

# ── ADRs CHILENOS EN NYSE ─────────────────────────────────────────────────────
ADRS_CHILE = {
    "SQM":  {"nombre": "SQM ADR",            "sector": "Minería",   "peso_ipsa": 0, "ib": "SQM",  "tipo": "Acción USA/Chile", "yf": "SQM"},
    "BSAC": {"nombre": "Santander Chile ADR", "sector": "Bancos",    "peso_ipsa": 0, "ib": "BSAC", "tipo": "Acción USA/Chile", "yf": "BSAC"},
    "BCH":  {"nombre": "Banco de Chile ADR",  "sector": "Bancos",    "peso_ipsa": 0, "ib": "BCH",  "tipo": "Acción USA/Chile", "yf": "BCH"},
    "LTM":  {"nombre": "LATAM Airlines ADR",  "sector": "Transporte","peso_ipsa": 0, "ib": "LTM",  "tipo": "Acción USA/Chile", "yf": "LTM"},
}

# ── ETFs ──────────────────────────────────────────────────────────────────────
ETFS = {
    "ECH":  {"nombre": "iShares MSCI Chile", "sector": "ETF Chile",  "peso_ipsa": 0, "ib": "ECH",  "tipo": "ETF", "yf": "ECH"},
    "SPY":  {"nombre": "S&P 500 ETF",        "sector": "ETF USA",    "peso_ipsa": 0, "ib": "SPY",  "tipo": "ETF", "yf": "SPY"},
    "TLT":  {"nombre": "20Y Treasury ETF",   "sector": "Renta Fija", "peso_ipsa": 0, "ib": "TLT",  "tipo": "ETF", "yf": "TLT"},
    "GLD":  {"nombre": "Gold ETF",           "sector": "Commodity",  "peso_ipsa": 0, "ib": "GLD",  "tipo": "ETF", "yf": "GLD"},
}

# ── COMMODITIES ───────────────────────────────────────────────────────────────
COMMODITIES = {
    "GC=F": {"nombre": "Oro",         "sector": "Commodity", "peso_ipsa": 0, "ib": "GC", "tipo": "Futuro", "yf": "GC=F"},
    "HG=F": {"nombre": "Cobre",       "sector": "Commodity", "peso_ipsa": 0, "ib": "HG", "tipo": "Futuro", "yf": "HG=F"},
    "CL=F": {"nombre": "Petróleo WTI","sector": "Commodity", "peso_ipsa": 0, "ib": "CL", "tipo": "Futuro", "yf": "CL=F"},
}

# ── CRYPTO ────────────────────────────────────────────────────────────────────
CRYPTO = {
    "BTC-USD": {"nombre": "Bitcoin", "sector": "Crypto", "peso_ipsa": 0, "ib": "BTC", "tipo": "Crypto", "yf": "BTC-USD"},
}

# ── UNIVERSO COMPLETO ─────────────────────────────────────────────────────────
UNIVERSO_COMPLETO = {
    **IPSA_30,
    **SMALL_CAPS,
    **ADRS_CHILE,
    **ETFS,
    **COMMODITIES,
    **CRYPTO,
}

# ── SUBCONJUNTOS ÚTILES ───────────────────────────────────────────────────────
def get_tickers_acciones_chile():
    """Todas las acciones chilenas (IPSA + small caps)"""
    return {**IPSA_30, **SMALL_CAPS}

def get_tickers_internacionales():
    """Activos internacionales"""
    return {**ADRS_CHILE, **ETFS, **COMMODITIES, **CRYPTO}

def get_tickers_at():
    """Activos para análisis técnico — los más líquidos"""
    # IPSA top 15 + internacionales
    ipsa_top = dict(list(IPSA_30.items())[:15])
    return {**ipsa_top, **ADRS_CHILE, **ETFS, **COMMODITIES, **CRYPTO}

def get_tickers_mtf():
    """Activos para análisis multi-timeframe — requieren suficientes datos"""
    ipsa_top = dict(list(IPSA_30.items())[:10])
    return {**ipsa_top, **ADRS_CHILE, **ETFS, **COMMODITIES, **CRYPTO}

def get_tickers_por_sector(sector):
    """Filtra activos por sector"""
    return {k: v for k, v in UNIVERSO_COMPLETO.items() if v.get("sector") == sector}

def get_tickers_ipsa_peso(min_peso=2.0):
    """IPSA filtrado por peso mínimo"""
    return {k: v for k, v in IPSA_30.items() if v.get("peso_ipsa", 0) >= min_peso}

if __name__ == "__main__":
    print(f"=== UNIVERSO MAESTRO ===")
    print(f"IPSA 30:      {len(IPSA_30)} acciones")
    print(f"Small caps:   {len(SMALL_CAPS)} acciones")
    print(f"ADRs Chile:   {len(ADRS_CHILE)} activos")
    print(f"ETFs:         {len(ETFS)} activos")
    print(f"Commodities:  {len(COMMODITIES)} activos")
    print(f"Crypto:       {len(CRYPTO)} activos")
    print(f"TOTAL:        {len(UNIVERSO_COMPLETO)} activos")

    print(f"\nPara AT:      {len(get_tickers_at())} activos")
    print(f"Para MTF:     {len(get_tickers_mtf())} activos")
    print(f"\nSectores:")
    sectores = {}
    for v in UNIVERSO_COMPLETO.values():
        s = v.get("sector", "Otros")
        sectores[s] = sectores.get(s, 0) + 1
    for s, n in sorted(sectores.items(), key=lambda x: -x[1]):
        print(f"  {s}: {n}")
