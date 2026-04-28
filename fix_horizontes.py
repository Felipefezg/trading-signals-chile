"""
Fix horizontes por tipo de producto y ampliar universo de instrumentos.
"""

with open("engine/recomendaciones.py", "r") as f:
    content = f.read()

# 1. Pasar tipo_producto a _calcular_horizonte
content = content.replace(
    "        horizonte = _calcular_horizonte(n_fuentes, conviccion_pct)",
    "        horizonte = _calcular_horizonte(n_fuentes, conviccion_pct, tipo_producto=tipo)"
)

# 2. Reemplazar funcion _calcular_horizonte
old_fn = '''def _calcular_horizonte(n_fuentes, conviccion, cierre_mas_proximo=None):
    """
    Horizonte basado en convergencia de señales y convicción.
    - Alta convicción + muchas fuentes → corto plazo (señal ya consolidada)
    - Convicción media → medio plazo
    - Pocas fuentes → largo plazo (esperar confirmación)
    """
    if conviccion >= 80 and n_fuentes >= 3:
        return {"label": "Corto plazo", "dias": "1–7 días",   "emoji": "⚡"}
    elif conviccion >= 65 and n_fuentes >= 2:
        return {"label": "Medio plazo", "dias": "1–4 semanas","emoji": "📅"}
    else:
        return {"label": "Largo plazo", "dias": "1–3 meses",  "emoji": "🗓️"}'''

new_fn = '''def _calcular_horizonte(n_fuentes, conviccion, cierre_mas_proximo=None, tipo_producto=None):
    """
    Horizonte ajustado por convicción, fuentes Y tipo de producto.
    Cada producto tiene restricciones naturales de horizonte.
    """
    # Horizonte base por convicción y fuentes
    if conviccion >= 80 and n_fuentes >= 3:
        h = {"label": "Corto plazo", "dias": "1–7 días",   "emoji": "⚡"}
    elif conviccion >= 65 and n_fuentes >= 2:
        h = {"label": "Medio plazo", "dias": "1–4 semanas", "emoji": "📅"}
    else:
        h = {"label": "Largo plazo", "dias": "1–3 meses",   "emoji": "🗓️"}

    # Restricciones por tipo de producto
    if tipo_producto == "Crypto":
        # BTC muy volátil — máximo medio plazo
        if h["dias"] == "1–3 meses":
            h = {"label": "Medio plazo", "dias": "1–4 semanas", "emoji": "📅",
                 "nota": "Ajustado: Crypto máx 4 semanas"}
    elif tipo_producto == "Futuro":
        # Futuros tienen vencimiento mensual — no pasar de 3 semanas
        if h["dias"] == "1–3 meses":
            h = {"label": "Medio plazo", "dias": "1–4 semanas", "emoji": "📅",
                 "nota": "Ajustado: Futuro vence mensualmente"}
    elif tipo_producto == "Forex":
        # Forex muy sensible a eventos macro — máximo medio plazo
        if h["dias"] == "1–3 meses":
            h = {"label": "Medio plazo", "dias": "1–4 semanas", "emoji": "📅",
                 "nota": "Ajustado: Forex sensible a macro"}
    elif tipo_producto == "Acción Chile":
        # Acciones locales — liquidez limitada, horizonte mínimo 1 semana
        if h["dias"] == "1–7 días":
            h = {"label": "Corto-medio", "dias": "1–2 semanas", "emoji": "📅",
                 "nota": "Ajustado: Acción Chile liquidez limitada"}

    return h'''

if old_fn in content:
    content = content.replace(old_fn, new_fn)
    print("✅ Función _calcular_horizonte actualizada")
else:
    print("❌ No se encontró función _calcular_horizonte")

# 3. Ampliar universo de instrumentos
old_instr = '''INSTRUMENTOS_IB = {
    "SQM.SN":           {"ib": "SQM",     "tipo": "Acción USA/Chile", "descripcion": "SQM ADR (NYSE)",          "yf": "SQM"},
    "ECH":              {"ib": "ECH",     "tipo": "ETF",              "descripcion": "iShares MSCI Chile ETF",   "yf": "ECH"},
    "COPEC.SN":         {"ib": "COPEC",   "tipo": "Acción Chile",     "descripcion": "Copec (Santiago)",         "yf": "COPEC.SN"},
    "CLP/USD":          {"ib": "USD.CLP", "tipo": "Forex",            "descripcion": "Dólar / Peso Chileno",     "yf": "CLP=X"},
    "BTC_LOCAL_SPREAD": {"ib": "BTC",     "tipo": "Crypto",           "descripcion": "Bitcoin (IBKR Crypto)",    "yf": "BTC-USD"},
    "GC=F":             {"ib": "GC",      "tipo": "Futuro",           "descripcion": "Oro (COMEX)",              "yf": "GC=F"},
    "CL=F":             {"ib": "CL",      "tipo": "Futuro",           "descripcion": "Petróleo WTI (NYMEX)",     "yf": "CL=F"},
    "HG=F":             {"ib": "HG",      "tipo": "Futuro",           "descripcion": "Cobre (COMEX)",            "yf": "HG=F"},
    "^GSPC":            {"ib": "SPY",     "tipo": "ETF",              "descripcion": "S&P 500 ETF",              "yf": "^GSPC"},
}'''

new_instr = '''INSTRUMENTOS_IB = {
    # ETFs Chile y USA
    "ECH":              {"ib": "ECH",       "tipo": "ETF",              "descripcion": "iShares MSCI Chile ETF",       "yf": "ECH"},
    "^GSPC":            {"ib": "SPY",       "tipo": "ETF",              "descripcion": "S&P 500 ETF",                  "yf": "^GSPC"},
    # Acciones Chile con ADR
    "SQM.SN":           {"ib": "SQM",       "tipo": "Acción USA/Chile", "descripcion": "SQM ADR (NYSE)",               "yf": "SQM"},
    "CHILE.SN":         {"ib": "BCH",       "tipo": "Acción USA/Chile", "descripcion": "Banco de Chile ADR",           "yf": "CHILE.SN"},
    "BSANTANDER.SN":    {"ib": "BSAC",      "tipo": "Acción USA/Chile", "descripcion": "Santander Chile ADR",          "yf": "BSANTANDER.SN"},
    "LTM.SN":           {"ib": "LTM",       "tipo": "Acción USA/Chile", "descripcion": "LATAM Airlines ADR",           "yf": "LTM.SN"},
    # Acciones Chile locales
    "COPEC.SN":         {"ib": "COPEC",     "tipo": "Acción Chile",     "descripcion": "Copec (Santiago)",             "yf": "COPEC.SN"},
    "BCI.SN":           {"ib": "BCI",       "tipo": "Acción Chile",     "descripcion": "Banco BCI (Santiago)",         "yf": "BCI.SN"},
    "FALABELLA.SN":     {"ib": "FALABELLA", "tipo": "Acción Chile",     "descripcion": "Falabella (Santiago)",         "yf": "FALABELLA.SN"},
    "CMPC.SN":          {"ib": "CMPC",      "tipo": "Acción Chile",     "descripcion": "CMPC (Santiago)",              "yf": "CMPC.SN"},
    "ENELCHILE.SN":     {"ib": "ENELCHILE", "tipo": "Acción Chile",     "descripcion": "Enel Chile (Santiago)",        "yf": "ENELCHILE.SN"},
    "COLBUN.SN":        {"ib": "COLBUN",    "tipo": "Acción Chile",     "descripcion": "Colbún (Santiago)",            "yf": "COLBUN.SN"},
    # Forex
    "CLP/USD":          {"ib": "USD.CLP",   "tipo": "Forex",            "descripcion": "Dólar / Peso Chileno",         "yf": "CLP=X"},
    # Crypto
    "BTC_LOCAL_SPREAD": {"ib": "BTC",       "tipo": "Crypto",           "descripcion": "Bitcoin (IBKR Crypto)",        "yf": "BTC-USD"},
    # Futuros commodities
    "GC=F":             {"ib": "GC",        "tipo": "Futuro",           "descripcion": "Oro (COMEX)",                  "yf": "GC=F"},
    "CL=F":             {"ib": "CL",        "tipo": "Futuro",           "descripcion": "Petróleo WTI (NYMEX)",         "yf": "CL=F"},
    "HG=F":             {"ib": "HG",        "tipo": "Futuro",           "descripcion": "Cobre (COMEX)",                "yf": "HG=F"},
}'''

if old_instr in content:
    content = content.replace(old_instr, new_instr)
    print("✅ Universo de instrumentos ampliado a 17 productos")
else:
    print("❌ No se encontró INSTRUMENTOS_IB")

with open("engine/recomendaciones.py", "w") as f:
    f.write(content)

# Verificar
from engine.recomendaciones import _calcular_horizonte, INSTRUMENTOS_IB
print(f"\nInstrumentos disponibles: {len(INSTRUMENTOS_IB)}")
print("\nTest horizontes por producto:")
casos = [
    ("Crypto",      3, 90),
    ("Futuro",      3, 90),
    ("Forex",       3, 90),
    ("Acción Chile",3, 90),
    ("ETF",         3, 90),
    ("ETF",         2, 65),
    ("ETF",         1, 55),
]
for tipo, n, conv in casos:
    h = _calcular_horizonte(n, conv, tipo_producto=tipo)
    nota = f" ← {h.get('nota','')}" if h.get('nota') else ""
    print(f"  {tipo:<20} conv:{conv}% fuentes:{n} → {h['label']} ({h['dias']}){nota}")
