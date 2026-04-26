"""
Motor de recomendaciones de trading.
Consolida señales de Polymarket, Kalshi, Macro USA y Noticias
en recomendaciones accionables con clasificación de riesgo 1-10.
"""

# Mapa de instrumentos operables en Interactive Brokers
INSTRUMENTOS_IB = {
    "SQM.SN":        {"ib": "SQM",    "tipo": "Acción USA/Chile", "descripcion": "SQM ADR (NYSE)"},
    "ECH":           {"ib": "ECH",    "tipo": "ETF",              "descripcion": "iShares MSCI Chile ETF"},
    "COPEC.SN":      {"ib": "COPEC",  "tipo": "Acción Chile",     "descripcion": "Copec (Santiago)"},
    "CLP/USD":       {"ib": "USD.CLP","tipo": "Forex",            "descripcion": "Dólar / Peso Chileno"},
    "BTC_LOCAL_SPREAD": {"ib": "BTC", "tipo": "Crypto",           "descripcion": "Bitcoin (IBKR Crypto)"},
    "GC=F":          {"ib": "GC",     "tipo": "Futuro",           "descripcion": "Oro (COMEX)"},
    "CL=F":          {"ib": "CL",     "tipo": "Futuro",           "descripcion": "Petróleo WTI (NYMEX)"},
    "HG=F":          {"ib": "HG",     "tipo": "Futuro",           "descripcion": "Cobre (COMEX)"},
    "^VIX":          {"ib": "VIX",    "tipo": "Índice",           "descripcion": "CBOE VIX (via opciones SPY)"},
    "^GSPC":         {"ib": "SPY",    "tipo": "ETF",              "descripcion": "S&P 500 ETF"},
}

# Clasificación de riesgo por tipo de instrumento
RIESGO_BASE = {
    "ETF":           3,
    "Acción Chile":  5,
    "Acción USA/Chile": 4,
    "Forex":         4,
    "Crypto":        8,
    "Futuro":        7,
    "Índice":        5,
}

def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list):
    """
    Consolida todas las fuentes en señales por activo.
    Retorna dict: activo -> {direccion, score_total, fuentes, evidencia}
    """
    activos = {}

    # 1. Polymarket
    if poly_df is not None and not poly_df.empty:
        for _, row in poly_df.iterrows():
            prob = row.get("probabilidad")
            if prob is None:
                continue
            for activo in row.get("chile_impact", []):
                if activo not in activos:
                    activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
                rel = row.get("relevancia", 1)
                peso = abs(prob - 50) * rel / 100
                direccion = "alza" if prob > 50 else "baja"
                activos[activo][direccion] += peso
                activos[activo]["fuentes"].append("Polymarket")
                activos[activo]["evidencia"].append({
                    "fuente": "Polymarket",
                    "señal": row.get("pregunta", "")[:80],
                    "prob": prob,
                    "direccion": direccion.upper(),
                    "peso": round(peso, 2),
                })

    # 2. Kalshi
    for s in (kalshi_list or []):
        for activo in s.get("activos_impacto", []):
            if activo not in activos:
                activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
            peso = s.get("score", 0) * 0.5
            direccion = s["direccion"].lower()
            activos[activo][direccion] += peso
            activos[activo]["fuentes"].append("Kalshi")
            activos[activo]["evidencia"].append({
                "fuente": "Kalshi",
                "señal": s.get("titulo", "")[:80],
                "prob": s.get("prob_pct"),
                "direccion": s["direccion"],
                "peso": round(peso, 2),
            })

    # 3. Macro USA
    for m in (macro_list or []):
        activo = m.get("activo_chile")
        if not activo:
            continue
        if activo not in activos:
            activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        peso = m.get("score", 0) * 0.8
        direccion = m["direccion"].lower()
        activos[activo][direccion] += peso
        activos[activo]["fuentes"].append("Macro USA")
        activos[activo]["evidencia"].append({
            "fuente": "Macro USA",
            "señal": m.get("tesis", "")[:80],
            "prob": None,
            "direccion": m["direccion"],
            "peso": round(peso, 2),
        })

    # 4. Noticias — boost si hay keywords relevantes
    for n in (noticias_list or [])[:10]:
        score_n = n.get("score", 0)
        if score_n < 5:
            continue
        kws = n.get("keywords", [])
        # Mapear keywords a activos
        kw_activo = {
            "sqm": "SQM.SN", "litio": "SQM.SN",
            "codelco": "ECH", "cobre": "ECH",
            "copec": "COPEC.SN", "energia": "COPEC.SN",
            "ipsa": "ECH", "dolar": "CLP/USD",
            "banco central": "CLP/USD", "tasa": "CLP/USD",
        }
        for kw in kws:
            activo = kw_activo.get(kw.lower())
            if activo:
                if activo not in activos:
                    activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
                activos[activo]["fuentes"].append("Noticias")
                activos[activo]["evidencia"].append({
                    "fuente": "Noticias",
                    "señal": n.get("titulo", "")[:80],
                    "prob": None,
                    "direccion": "NEUTRAL",
                    "peso": round(score_n * 0.1, 2),
                })

    return activos

def generar_recomendaciones(activos_dict):
    """
    Genera recomendaciones finales por activo.
    Retorna lista ordenada por convicción.
    """
    recomendaciones = []

    for activo, data in activos_dict.items():
        alza = data["alza"]
        baja = data["baja"]
        total = alza + baja
        if total < 0.5:
            continue

        # Dirección neta
        if alza > baja * 1.3:
            accion = "COMPRAR"
            direccion = "ALZA"
            conviccion = alza / total
        elif baja > alza * 1.3:
            accion = "VENDER"
            direccion = "BAJA"
            conviccion = baja / total
        else:
            accion = "MANTENER"
            direccion = "NEUTRAL"
            conviccion = 0.5

        if accion == "MANTENER":
            continue

        # Score de convicción (0-10)
        score_conv = round(conviccion * 10, 1)

        # Fuentes únicas
        fuentes_unicas = list(set(data["fuentes"]))
        n_fuentes = len(fuentes_unicas)

        # Riesgo: base del instrumento + ajuste por n° fuentes y convicción
        ib_info = INSTRUMENTOS_IB.get(activo, {})
        tipo = ib_info.get("tipo", "ETF")
        riesgo_base = RIESGO_BASE.get(tipo, 5)
        # Más fuentes = más convicción = menos riesgo relativo
        ajuste_fuentes = max(0, 2 - n_fuentes)
        # Baja convicción = más riesgo
        ajuste_conv = round((1 - conviccion) * 3)
        riesgo = min(10, max(1, riesgo_base + ajuste_fuentes + ajuste_conv))

        # Generar tesis resumida
        tesis = _generar_tesis_resumida(activo, accion, data["evidencia"], fuentes_unicas)

        recomendaciones.append({
            "activo": activo,
            "ib_ticker": ib_info.get("ib", activo),
            "tipo": tipo,
            "descripcion": ib_info.get("descripcion", activo),
            "accion": accion,
            "direccion": direccion,
            "conviccion": round(conviccion * 100, 1),
            "score": score_conv,
            "riesgo": riesgo,
            "fuentes": fuentes_unicas,
            "n_fuentes": n_fuentes,
            "evidencia": data["evidencia"],
            "tesis": tesis,
        })

    # Ordenar: primero alta convicción, luego menor riesgo
    return sorted(recomendaciones,
                  key=lambda x: (x["score"], -x["riesgo"]),
                  reverse=True)

def _generar_tesis_resumida(activo, accion, evidencia, fuentes):
    """Genera tesis legible de 1-2 líneas"""
    poly_ev = [e for e in evidencia if e["fuente"] == "Polymarket"]
    kalshi_ev = [e for e in evidencia if e["fuente"] == "Kalshi"]
    macro_ev = [e for e in evidencia if e["fuente"] == "Macro USA"]

    partes = []
    if poly_ev:
        partes.append(f"Polymarket señala {poly_ev[0]['direccion'].lower()} ({poly_ev[0].get('prob','?')}%)")
    if kalshi_ev:
        partes.append(f"Kalshi confirma {kalshi_ev[0]['direccion'].lower()}")
    if macro_ev:
        partes.append(macro_ev[0]["señal"][:60])

    if partes:
        return f"{accion} {activo}: " + " | ".join(partes[:2])
    return f"{accion} {activo} basado en {', '.join(fuentes)}"
