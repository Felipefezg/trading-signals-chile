"""
Motor de recomendaciones de trading.
Consolida señales de Polymarket, Kalshi, Macro USA y Noticias
en recomendaciones accionables con:
- Horizonte de inversión
- Stop loss / Take profit sugeridos
- Tipo de instrumento recomendado
- Clasificación de riesgo 1-10
- Alertas Telegram
"""

import requests
import yfinance as yf

# ── CONFIGURACIÓN TELEGRAM ────────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8648892135:AAHairDr4kx1IuRWkI0CL9FgKG6Sx_g_YlA"
TELEGRAM_CHAT_ID = "8481235797"

# Umbral para disparar alerta Telegram
ALERTA_MIN_CONVICCION = 80   # %
ALERTA_MAX_RIESGO     = 6    # /10

# ── INSTRUMENTOS ──────────────────────────────────────────────────────────────
INSTRUMENTOS_IB = {
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
    # ETFs adicionales
    "TLT":              {"ib": "TLT",       "tipo": "ETF",              "descripcion": "iShares 20Y Treasury",         "yf": "TLT"},
    "GLD":              {"ib": "GLD",       "tipo": "ETF",              "descripcion": "SPDR Gold ETF",                "yf": "GLD"},
    # IPSA 30 completo
    "SQM-B.SN":         {"ib": "SQM",       "tipo": "Acción USA/Chile", "descripcion": "SQM ADR NYSE",                 "yf": "SQM"},
    "CENCOSUD.SN":      {"ib": "CENCOSUD",  "tipo": "Acción Chile",     "descripcion": "Cencosud Santiago",            "yf": "CENCOSUD.SN"},
    "ENELAM.SN":        {"ib": "ENELAM",    "tipo": "Acción Chile",     "descripcion": "Enel Americas Santiago",       "yf": "ENELAM.SN"},
    "ENTEL.SN":         {"ib": "ENTEL",     "tipo": "Acción Chile",     "descripcion": "Entel Santiago",               "yf": "ENTEL.SN"},
    "CAP.SN":           {"ib": "CAP",       "tipo": "Acción Chile",     "descripcion": "CAP Santiago",                 "yf": "CAP.SN"},
    "CCU.SN":           {"ib": "CCU",       "tipo": "Acción Chile",     "descripcion": "CCU Santiago",                 "yf": "CCU.SN"},
    "ITAUCL.SN":        {"ib": "ITAUCL",    "tipo": "Acción Chile",     "descripcion": "Itau Chile Santiago",          "yf": "ITAUCL.SN"},
    "PARAUCO.SN":       {"ib": "PARAUCO",   "tipo": "Acción Chile",     "descripcion": "Parque Arauco Santiago",       "yf": "PARAUCO.SN"},
    "MALLPLAZA.SN":     {"ib": "MALLPLAZA", "tipo": "Acción Chile",     "descripcion": "Mall Plaza Santiago",          "yf": "MALLPLAZA.SN"},
    "RIPLEY.SN":        {"ib": "RIPLEY",    "tipo": "Acción Chile",     "descripcion": "Ripley Santiago",              "yf": "RIPLEY.SN"},
    "AGUAS-A.SN":       {"ib": "AGUAS-A",   "tipo": "Acción Chile",     "descripcion": "Aguas Andinas Santiago",       "yf": "AGUAS-A.SN"},
    "VAPORES.SN":       {"ib": "VAPORES",   "tipo": "Acción Chile",     "descripcion": "CSAV Santiago",                "yf": "VAPORES.SN"},
    "ANDINA-B.SN":      {"ib": "ANDINA-B",  "tipo": "Acción Chile",     "descripcion": "Andina Santiago",              "yf": "ANDINA-B.SN"},
    "ILC.SN":           {"ib": "ILC",       "tipo": "Acción Chile",     "descripcion": "ILC Santiago",                 "yf": "ILC.SN"},
    "CONCHATORO.SN":    {"ib": "CONCHATORO","tipo": "Acción Chile",     "descripcion": "Concha y Toro Santiago",       "yf": "CONCHATORO.SN"},
    "FORUS.SN":         {"ib": "FORUS",     "tipo": "Acción Chile",     "descripcion": "Forus Santiago",               "yf": "FORUS.SN"},
    "SMU.SN":           {"ib": "SMU",       "tipo": "Acción Chile",     "descripcion": "SMU Santiago",                 "yf": "SMU.SN"},
    "ECL.SN":           {"ib": "ECL",       "tipo": "Acción Chile",     "descripcion": "ECL Santiago",                 "yf": "ECL.SN"},
    "SONDA.SN":         {"ib": "SONDA",     "tipo": "Acción Chile",     "descripcion": "Sonda Santiago",               "yf": "SONDA.SN"},
    # Small caps
    "BESALCO.SN":       {"ib": "BESALCO",   "tipo": "Acción Chile",     "descripcion": "Besalco Santiago",             "yf": "BESALCO.SN"},
    "SALFACORP.SN":     {"ib": "SALFACORP", "tipo": "Acción Chile",     "descripcion": "Salfacorp Santiago",           "yf": "SALFACORP.SN"},
    "SOCOVESA.SN":      {"ib": "SOCOVESA",  "tipo": "Acción Chile",     "descripcion": "Socovesa Santiago",            "yf": "SOCOVESA.SN"},
    "MOLYMET.SN":       {"ib": "MOLYMET",   "tipo": "Acción Chile",     "descripcion": "Molymet Santiago",             "yf": "MOLYMET.SN"},
    "QUINENCO.SN":      {"ib": "QUINENCO",  "tipo": "Acción Chile",     "descripcion": "Quinenco Santiago",            "yf": "QUINENCO.SN"},
    "MASISA.SN":        {"ib": "MASISA",    "tipo": "Acción Chile",     "descripcion": "Masisa Santiago",              "yf": "MASISA.SN"},
    "HABITAT.SN":       {"ib": "HABITAT",   "tipo": "Acción Chile",     "descripcion": "AFP Habitat Santiago",         "yf": "HABITAT.SN"},
    "PROVIDA.SN":       {"ib": "PROVIDA",   "tipo": "Acción Chile",     "descripcion": "AFP Provida Santiago",         "yf": "PROVIDA.SN"},
    "MARINSA.SN":       {"ib": "MARINSA",   "tipo": "Acción Chile",     "descripcion": "Marinsa Santiago",             "yf": "MARINSA.SN"},
}

RIESGO_BASE = {
    "ETF":             3,
    "Acción Chile":    5,
    "Acción USA/Chile":4,
    "Forex":           4,
    "Crypto":          7,
    "Futuro":          6,
    "Índice":          5,
}

# ── HORIZONTE ─────────────────────────────────────────────────────────────────
def _calcular_horizonte(n_fuentes, conviccion, cierre_mas_proximo=None, tipo_producto=None):
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

    return h

# ── VOLATILIDAD Y SL/TP ───────────────────────────────────────────────────────
def _get_volatilidad(yf_ticker):
    """Obtiene volatilidad histórica 20 días (ATR simplificado)"""
    # Rangos de precio razonables por instrumento — rechaza datos corruptos
    PRECIO_MAX = {
        "CL=F": 300,    # Petróleo WTI — nunca superó $150/barril
        "HG=F": 20,     # Cobre — precio por libra, nunca > $15
        "GC=F": 5000,   # Oro — precio por onza, máximo razonable $5,000
        "BTC-USD": 500_000,
        "ETH-USD": 50_000,
    }
    try:
        t = yf.Ticker(yf_ticker)
        h = t.history(period="30d")
        if len(h) < 5:
            return None, None
        precio_actual = float(h["Close"].iloc[-1])

        # Validar que el precio no sea el valor nocional del contrato
        max_precio = PRECIO_MAX.get(yf_ticker, 100_000)
        if precio_actual > max_precio:
            import logging
            logging.warning(f"_get_volatilidad: precio {yf_ticker} = {precio_actual:.2f} excede máximo {max_precio} — dato corrupto, descartando")
            return None, None

        retornos = h["Close"].pct_change().dropna()
        vol_diaria = retornos.std()
        vol_20d = vol_diaria * (20 ** 0.5)
        return precio_actual, vol_20d
    except:
        return None, None

def _calcular_sl_tp(accion, precio, volatilidad, horizonte_dias, ticker=None):
    """
    SL/TP calibrado usando soporte/resistencia real.
    Fallback a volatilidad si no hay niveles disponibles.
    """
    if precio is None:
        return None, None, None

    # Intentar calibrar con soporte/resistencia
    if ticker:
        try:
            from engine.soporte_resistencia import calcular_sl_tp_calibrado
            atr = precio * volatilidad if volatilidad else None
            sl_sr, tp_sr = calcular_sl_tp_calibrado(ticker, accion, precio, atr)
            if sl_sr and tp_sr:
                return precio, sl_sr, tp_sr
        except:
            pass

    # Fallback: ATR
    if volatilidad is None:
        return None, None, None

    dias_map = {"1–7 días": 5, "1–4 semanas": 15, "1–3 meses": 45}
    dias = 10
    for k, v in dias_map.items():
        if k in horizonte_dias:
            dias = v
            break

    mov = precio * volatilidad * (dias / 20) ** 0.5

    if accion == "COMPRAR":
        sl = round(precio - mov, 2)
        tp = round(precio + mov * 2, 2)
    else:
        sl = round(precio + mov, 2)
        tp = round(precio - mov * 2, 2)

    return precio, sl, tp

# ── TIPO DE INSTRUMENTO ───────────────────────────────────────────────────────
def _sugerir_instrumento(tipo_base, accion, horizonte_label, riesgo, conviccion):
    """
    Sugiere el vehículo más apropiado para operar la señal en IB.
    """
    sugerencias = []

    if tipo_base == "ETF":
        sugerencias.append({
            "vehiculo": "ETF directo",
            "razon": "Líquido, diversificado, sin apalancamiento. Ideal para esta señal.",
            "cuando": "Siempre disponible",
            "pros": "Simple, bajo costo, sin vencimiento",
            "contras": "Retorno limitado vs acción directa",
        })
        if horizonte_label == "Corto plazo" and conviccion >= 80:
            sugerencias.append({
                "vehiculo": "Opción (comprar PUT/CALL)",
                "razon": "Alta convicción + corto plazo → opciones amplían retorno con riesgo definido.",
                "cuando": "Si quieres apalancamiento con pérdida máxima conocida",
                "pros": "Apalancamiento, riesgo limitado al premium",
                "contras": "Vencimiento, decay temporal (theta)",
            })

    elif tipo_base in ["Acción USA/Chile", "Acción Chile"]:
        sugerencias.append({
            "vehiculo": "Acción directa",
            "razon": "Exposición directa al activo. Recomendado para señales de medio/largo plazo.",
            "cuando": "Horizonte > 1 semana",
            "pros": "Sin vencimiento, dividendos, simplicidad",
            "contras": "Capital completo comprometido",
        })
        if horizonte_label == "Corto plazo" and conviccion >= 85:
            sugerencias.append({
                "vehiculo": "Opción (comprar PUT/CALL)",
                "razon": "Corto plazo + alta convicción → opción ATM amplifica el movimiento esperado.",
                "cuando": "Si el movimiento esperado es > 3% en pocos días",
                "pros": "Apalancamiento 5-10x, pérdida máxima = premium",
                "contras": "Requiere timing preciso",
            })
        if accion == "VENDER" and tipo_base == "Acción USA/Chile":
            sugerencias.append({
                "vehiculo": "Short selling",
                "razon": "Venta en corto directa disponible en IB para ADRs.",
                "cuando": "Si tienes margen habilitado en IB",
                "pros": "Sin vencimiento, exposición directa",
                "contras": "Riesgo ilimitado al alza, costo de préstamo",
            })

    elif tipo_base == "Crypto":
        sugerencias.append({
            "vehiculo": "Crypto directo (IB)",
            "razon": "Exposición directa. IB permite comprar/vender BTC y ETH.",
            "cuando": "Siempre disponible en IB",
            "pros": "Simplicidad, sin derivados",
            "contras": "Alta volatilidad, sin SL automático",
        })
        sugerencias.append({
            "vehiculo": "ETF de Crypto (IBIT, FBTC)",
            "razon": "Exposición a BTC vía ETF. Menor volatilidad operacional.",
            "cuando": "Si prefieres estructura regulada",
            "pros": "Liquidez de ETF, sin wallet",
            "contras": "Tracking error, comisión de gestión",
        })

    elif tipo_base == "Forex":
        sugerencias.append({
            "vehiculo": "Forex spot (IB)",
            "razon": "Par USD/CLP disponible en IB directamente.",
            "cuando": "Siempre disponible",
            "pros": "Mercado 24/5, alta liquidez",
            "contras": "Requiere cuenta Forex habilitada",
        })

    elif tipo_base == "Futuro":
        sugerencias.append({
            "vehiculo": "Futuro directo",
            "razon": "Exposición directa con apalancamiento. Solo para cuenta con margen.",
            "cuando": "Si tienes cuenta de futuros en IB",
            "pros": "Alta liquidez, apalancamiento",
            "contras": "Vencimiento mensual, margin calls",
        })
        sugerencias.append({
            "vehiculo": "ETF equivalente",
            "razon": "GLD (oro), USO (petróleo), CPER (cobre) como alternativa sin vencimiento.",
            "cuando": "Si prefieres no operar futuros",
            "pros": "Sin vencimiento, más simple",
            "contras": "Tracking error vs futuro",
        })

    return sugerencias

# ── RIESGO ────────────────────────────────────────────────────────────────────
def _calcular_riesgo(tipo, conviccion, n_fuentes):
    base = RIESGO_BASE.get(tipo, 5)
    ajuste_conv    = -2 if conviccion >= 80 else (-1 if conviccion >= 65 else +1 if conviccion < 60 else 0)
    ajuste_fuentes = -2 if n_fuentes >= 3 else (-1 if n_fuentes == 2 else +2)
    bonus          = -1 if (conviccion >= 80 and n_fuentes >= 3) else 0
    return max(1, min(10, base + ajuste_conv + ajuste_fuentes + bonus))

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def enviar_alerta_telegram(recomendacion):
    """Envía alerta Telegram para señales de alta convicción y bajo riesgo."""
    try:
        r = recomendacion
        emoji = "🟢" if r["accion"] == "COMPRAR" else "🔴"
        horizonte = r.get("horizonte", {})
        sl = r.get("stop_loss")
        tp = r.get("take_profit")
        precio = r.get("precio_actual")

        msg = (
            f"{emoji} *SEÑAL TRADING* {emoji}\n\n"
            f"*{r['accion']} {r['ib_ticker']}*\n"
            f"_{r['descripcion']}_\n\n"
            f"📊 Convicción: *{r['conviccion']}%*\n"
            f"⚠️ Riesgo: *{r['riesgo']}/10*\n"
            f"{horizonte.get('emoji','📅')} Horizonte: *{horizonte.get('dias','N/D')}*\n"
            f"🔗 Fuentes: {', '.join(r['fuentes'])}\n"
        )
        if precio:
            msg += f"\n💰 Precio actual: *{precio:,.2f}*\n"
        if sl and tp:
            msg += f"🛑 Stop Loss: *{sl:,.2f}*\n"
            msg += f"🎯 Take Profit: *{tp:,.2f}*\n"

        msg += f"\n_{r['tesis'][:100]}_"

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }, timeout=5)
        return True
    except Exception as e:
        print(f"Error Telegram: {e}")
        return False

def enviar_alertas_nuevas(recomendaciones, enviadas_cache=None):
    """Envía alertas solo para señales que superen umbrales y no hayan sido enviadas."""
    if enviadas_cache is None:
        enviadas_cache = set()
    enviadas = 0
    for r in recomendaciones:
        key = f"{r['accion']}_{r['ib_ticker']}"
        if (r["conviccion"] >= ALERTA_MIN_CONVICCION and
            r["riesgo"] <= ALERTA_MAX_RIESGO and
            key not in enviadas_cache):
            if enviar_alerta_telegram(r):
                enviadas_cache.add(key)
                enviadas += 1
    return enviadas, enviadas_cache

# ── CONSOLIDACIÓN ─────────────────────────────────────────────────────────────
def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None, put_call=None, analisis_tecnico=None, google_trends=None, ib_data=None, mercado_local=None, renta_fija=None, mtf=None, sec_13f=None, order_flow=None, correlaciones=None, iv_opciones=None, ml=None):
    # Cargar factores de calidad por fuente (win_rate histórico).
    # Dict vacío si aún no hay suficientes trades → factor default 1.0 por fuente.
    _source_quality: dict = {}
    try:
        from engine.feedback_loop import get_source_quality_factors
        _source_quality = get_source_quality_factors(min_trades=3)
    except Exception:
        pass

    # Inicializar todos los activos del universo maestro
    activos = {}
    try:
        from engine.universo import UNIVERSO_COMPLETO
        for yf_ticker in UNIVERSO_COMPLETO:
            activos[yf_ticker] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        # Agregar tickers IB también
        for yf_ticker, info in UNIVERSO_COMPLETO.items():
            ib_ticker = info.get("ib", "")
            if ib_ticker and ib_ticker not in activos:
                activos[ib_ticker] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
    except:
        pass

    # Polymarket
    if poly_df is not None and not poly_df.empty:
        for _, row in poly_df.iterrows():
            prob = row.get("probabilidad")
            if prob is None: continue
            for activo in row.get("chile_impact", []):
                if activo not in activos:
                    activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
                rel = row.get("relevancia", 1)
                peso = abs(prob - 50) * rel / 200  # reducido — Polymarket sin mercados financieros relevantes
                direccion = "alza" if prob > 50 else "baja"
                activos[activo][direccion] += peso
                activos[activo]["fuentes"].append("Polymarket")
                activos[activo]["evidencia"].append({
                    "fuente": "Polymarket", "señal": row.get("pregunta","")[:80],
                    "prob": prob, "direccion": direccion.upper(), "peso": round(peso, 2),
                })

    # Kalshi
    for s in (kalshi_list or []):
        for activo in s.get("activos_impacto", []):
            if activo not in activos:
                activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
            peso = s.get("score", 0) * 0.5
            direccion = s["direccion"].lower()
            activos[activo][direccion] += peso
            activos[activo]["fuentes"].append("Kalshi")
            activos[activo]["evidencia"].append({
                "fuente": "Kalshi", "señal": s.get("titulo","")[:80],
                "prob": s.get("prob_pct"), "direccion": s["direccion"], "peso": round(peso, 2),
            })

    # Macro USA
    for m in (macro_list or []):
        activo = m.get("activo_chile")
        if not activo: continue
        if activo not in activos:
            activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        peso = m.get("score", 0) * 0.8
        direccion = m["direccion"].lower()
        activos[activo][direccion] += peso
        activos[activo]["fuentes"].append("Macro USA")
        activos[activo]["evidencia"].append({
            "fuente": "Macro USA", "señal": m.get("tesis","")[:80],
            "prob": None, "direccion": m["direccion"], "peso": round(peso, 2),
        })

    # Noticias
    kw_activo = {
        "sqm": "SQM.SN", "litio": "SQM.SN",
        "codelco": "ECH", "cobre": "ECH",
        "copec": "COPEC.SN", "energia": "COPEC.SN",
        "ipsa": "ECH", "dolar": "CLP/USD",
        "banco central": "CLP/USD", "tasa": "CLP/USD",
    }
    for n in (noticias_list or [])[:10]:
        if n.get("score", 0) < 5: continue
        for kw in n.get("keywords", []):
            activo = kw_activo.get(kw.lower())
            if activo:
                if activo not in activos:
                    activos[activo] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
                activos[activo]["fuentes"].append("Noticias")
                activos[activo]["evidencia"].append({
                    "fuente": "Noticias", "señal": n.get("titulo","")[:80],
                    "prob": None, "direccion": "NEUTRAL", "peso": round(n.get("score",0) * 0.1, 2),
                })


    # Fear & Greed — ajusta peso global de señales
    # IMPORTANTE: aplica reducción real a señales contrarias, no solo multiplica baja=0
    if fear_greed:
        fg_score  = fear_greed.get("score", 50)
        fg_mult   = fear_greed.get("multiplicador", 1.0)
        fg_señal  = fear_greed.get("señal_trading", "NEUTRO")
        for activo in activos:
            if fg_señal == "COMPRAR" and fg_score <= 25:
                # Miedo extremo (≤25) → refuerza señales ALZA (oportunidad contrarian)
                if activos[activo]["alza"] > 0:
                    activos[activo]["alza"] *= fg_mult
                    activos[activo]["fuentes"].append("Fear&Greed")
                    activos[activo]["evidencia"].append({
                        "fuente": "Fear&Greed", "señal": f"Miedo extremo ({fg_score}/100) → oportunidad compra contrarian",
                        "prob": None, "direccion": "ALZA", "peso": round(fg_mult - 1, 2),
                    })
            elif fg_señal == "VENDER" and fg_score >= 70:
                # Codicia extrema (≥70) → penaliza señales ALZA y refuerza BAJA
                if activos[activo]["alza"] > 0:
                    activos[activo]["alza"] *= (2.0 - fg_mult)  # reduce alza
                activos[activo]["baja"] += activos[activo].get("baja", 0) * (fg_mult - 1)
                activos[activo]["fuentes"].append("Fear&Greed")
                activos[activo]["evidencia"].append({
                    "fuente": "Fear&Greed", "señal": f"Codicia extrema ({fg_score}/100) → reducir exposición larga",
                    "prob": None, "direccion": "BAJA", "peso": round(fg_mult - 1, 2),
                })
            # Entre 25-70: Fear&Greed neutro — no modifica señales, no se agrega a fuentes

    # CMF Hechos Esenciales — señales de alta convicción por empresa IPSA
    CMF_TICKER_MAP = {
        "SQM": "SQM.SN", "COPEC": "COPEC.SN", "FALABELLA": "COPEC.SN",
        "BCI": "ECH", "SANTANDER": "ECH", "CHILE": "ECH",
        "CMPC": "ECH", "LATAM": "ECH", "VAPORES": "ECH",
        "CAP": "ECH", "COLBUN": "ECH", "ENELCHILE": "ECH",
    }
    for hecho in (cmf_hechos or []):
        ticker_ipsa = hecho.get("ticker_ipsa")
        if not ticker_ipsa:
            continue
        activo_map = CMF_TICKER_MAP.get(ticker_ipsa, "ECH")
        if activo_map not in activos:
            activos[activo_map] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        relevancia = hecho.get("relevancia", "BAJA")
        impacto    = hecho.get("impacto", "NEUTRO")
        peso_cmf   = {"ALTA": 2.0, "MEDIA": 1.0, "BAJA": 0.3}.get(relevancia, 0.3)
        if impacto == "POSITIVO":
            activos[activo_map]["alza"] += peso_cmf
            direccion_cmf = "ALZA"
        elif impacto == "NEGATIVO":
            activos[activo_map]["baja"] += peso_cmf
            direccion_cmf = "BAJA"
        else:
            continue
        activos[activo_map]["fuentes"].append("CMF")
        activos[activo_map]["evidencia"].append({
            "fuente": "CMF", "señal": f"{ticker_ipsa}: {hecho.get('materia','')[:60]}",
            "prob": None, "direccion": direccion_cmf, "peso": peso_cmf,
        })

    # Volumen Anormal — confirma señales existentes o genera nuevas
    VOL_TICKER_MAP = {
        "SQM-B.SN": "SQM.SN", "COPEC.SN": "COPEC.SN",
        "BCI.SN": "ECH", "CHILE.SN": "ECH", "BSANTANDER.SN": "ECH",
        "FALABELLA.SN": "ECH", "CENCOSUD.SN": "ECH",
        "ECH": "ECH", "SQM": "SQM.SN",
    }
    for alerta in (vol_alertas or []):
        if alerta.get("nivel") not in ("ALTA", "MEDIA"):
            continue
        ticker_vol = alerta.get("ticker", "")
        activo_map = VOL_TICKER_MAP.get(ticker_vol, "ECH")
        if activo_map not in activos:
            activos[activo_map] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        señal_vol  = alerta.get("señal", "NORMAL")
        ratio      = alerta.get("ratio", 1.0)
        peso_vol   = min((ratio - 1.5) * 0.5, 2.0)  # peso proporcional al ratio
        if señal_vol == "ACUMULACIÓN":
            activos[activo_map]["alza"] += peso_vol
            direccion_vol = "ALZA"
        elif señal_vol == "DISTRIBUCIÓN":
            activos[activo_map]["baja"] += peso_vol
            direccion_vol = "BAJA"
        else:
            continue
        # Extra convicción si hay CMF correlacionado
        if alerta.get("conviccion_extra"):
            activos[activo_map]["alza" if direccion_vol == "ALZA" else "baja"] += 1.0
        activos[activo_map]["fuentes"].append("Volumen")
        activos[activo_map]["evidencia"].append({
            "fuente": "Volumen", "señal": f"{alerta.get('nombre',ticker_vol)}: {ratio:.1f}x promedio — {señal_vol}",
            "prob": None, "direccion": direccion_vol, "peso": round(peso_vol, 2),
        })

    # Análisis Técnico — RSI, MACD, Bollinger, MA
    for at in (analisis_tecnico or []):
        activo_map = at.get("activo_motor")
        if not activo_map:
            continue
        if activo_map not in activos:
            activos[activo_map] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}

        direccion_at = at.get("direccion", "NEUTRO")
        conviccion_at = at.get("conviccion", 0)
        puntos_at = at.get("puntos", 0)

        # Peso proporcional a la convicción y puntos técnicos
        peso_at = puntos_at * 1.5  # aumentado — AT es fuente más confiable actualmente

        if direccion_at == "ALZA" and peso_at > 0:
            activos[activo_map]["alza"] += peso_at
            activos[activo_map]["fuentes"].append("Análisis Técnico")
            señales_desc = " | ".join(s["descripcion"] for s in at.get("señales", [])[:2])
            activos[activo_map]["evidencia"].append({
                "fuente": "Análisis Técnico",
                "señal": f"{at['nombre']}: {señales_desc[:80]}",
                "prob": None, "direccion": "ALZA", "peso": round(peso_at, 2),
            })
        elif direccion_at == "BAJA" and peso_at > 0:
            activos[activo_map]["baja"] += peso_at
            activos[activo_map]["fuentes"].append("Análisis Técnico")
            señales_desc = " | ".join(s["descripcion"] for s in at.get("señales", [])[:2])
            activos[activo_map]["evidencia"].append({
                "fuente": "Análisis Técnico",
                "señal": f"{at['nombre']}: {señales_desc[:80]}",
                "prob": None, "direccion": "BAJA", "peso": round(peso_at, 2),
            })

    # Google Trends — Amplificador de señales existentes
    for trend in (google_trends or []):
        activo_gt = trend.get("activo")
        if not activo_gt or activo_gt not in activos:
            continue
        score_gt = trend.get("score", 0)
        if score_gt < 2:
            continue
        # Trends amplifica la señal dominante (no determina dirección)
        peso_gt = score_gt * 0.3
        # Amplificar la dirección que ya tiene más peso
        if activos[activo_gt]["alza"] >= activos[activo_gt]["baja"]:
            activos[activo_gt]["alza"] += peso_gt
            dir_gt = "ALZA"
        else:
            activos[activo_gt]["baja"] += peso_gt
            dir_gt = "BAJA"
        activos[activo_gt]["fuentes"].append("Google Trends")
        activos[activo_gt]["evidencia"].append({
            "fuente": "Google Trends",
            "señal":  trend.get("descripcion", "")[:80],
            "prob": None, "direccion": dir_gt, "peso": round(peso_gt, 2),
        })

    # Put/Call Ratio — Smart Money Positioning
    PC_PESO = {"ALZA": 1.5, "BAJA": 1.5, "NEUTRO": 0}
    for activo_pc, datos_pc in (put_call or {}).items():
        if activo_pc not in activos:
            activos[activo_pc] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        direccion_pc = datos_pc.get("direccion", "NEUTRO")
        score_pc     = datos_pc.get("score", 0)
        peso_pc      = score_pc * 0.3
        if direccion_pc == "ALZA" and peso_pc > 0:
            activos[activo_pc]["alza"] += peso_pc
            activos[activo_pc]["fuentes"].append("Put/Call")
            activos[activo_pc]["evidencia"].append({
                "fuente": "Put/Call", "señal": f"P/C {datos_pc['ticker']}: {datos_pc['ratio']:.3f} — {datos_pc['señal'][:50]}",
                "prob": None, "direccion": "ALZA", "peso": round(peso_pc, 2),
            })
        elif direccion_pc == "BAJA" and peso_pc > 0:
            activos[activo_pc]["baja"] += peso_pc
            activos[activo_pc]["fuentes"].append("Put/Call")
            activos[activo_pc]["evidencia"].append({
                "fuente": "Put/Call", "señal": f"P/C {datos_pc['ticker']}: {datos_pc['ratio']:.3f} — {datos_pc['señal'][:50]}",
                "prob": None, "direccion": "BAJA", "peso": round(peso_pc, 2),
            })

    # ── MERCADO LOCAL (Análisis técnico IPSA 30) ──────────────────────────────
    # Estructura: [{"ticker": "COPEC.SN", "nombre": "Copec", "direccion": "ALZA", "puntos": 5, "señales": [...]}]
    for ml_local in (mercado_local or []):
        activo_ml_local = ml_local.get("ticker") or ml_local.get("activo_motor")
        if not activo_ml_local:
            continue
        if activo_ml_local not in activos:
            activos[activo_ml_local] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        dir_ml_local   = ml_local.get("direccion", "NEUTRO")
        puntos_ml_local = ml_local.get("puntos", 0)
        peso_ml_local  = puntos_ml_local * 1.0
        if dir_ml_local in ("ALZA", "BAJA") and peso_ml_local > 0:
            activos[activo_ml_local][dir_ml_local.lower()] += peso_ml_local
            activos[activo_ml_local]["fuentes"].append("Mercado Local")
            señales_ml = " | ".join(
                (s if isinstance(s, str) else s.get("descripcion", ""))[:30]
                for s in ml_local.get("señales", [])[:2]
            )
            activos[activo_ml_local]["evidencia"].append({
                "fuente": "Mercado Local",
                "señal":  f"{ml_local.get('nombre', activo_ml_local)}: {señales_ml[:80]}",
                "prob":   None, "direccion": dir_ml_local, "peso": round(peso_ml_local, 2),
            })

    # ── MTF (Multi-TimeFrame — alineación 1h/4h/1d) ───────────────────────────
    # Estructura: [{"activo_motor": "SQM.SN", "direccion": "ALZA", "puntos": 8, "n_alineados": 3, "nombre": "SQM"}]
    for mtf_signal in (mtf or []):
        activo_mtf = mtf_signal.get("activo_motor") or mtf_signal.get("ticker")
        if not activo_mtf:
            continue
        if activo_mtf not in activos:
            activos[activo_mtf] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        dir_mtf      = mtf_signal.get("direccion", "NEUTRO")
        puntos_mtf   = mtf_signal.get("puntos", 0)
        n_alineados  = mtf_signal.get("n_alineados", 1)
        peso_mtf     = puntos_mtf * 1.2   # bonus por confirmación multi-timeframe
        if dir_mtf in ("ALZA", "BAJA") and peso_mtf > 0:
            activos[activo_mtf][dir_mtf.lower()] += peso_mtf
            activos[activo_mtf]["fuentes"].append("MTF")
            activos[activo_mtf]["evidencia"].append({
                "fuente": "MTF",
                "señal":  f"{mtf_signal.get('nombre', activo_mtf)}: {n_alineados} TF alineados — {dir_mtf}",
                "prob":   None, "direccion": dir_mtf, "peso": round(peso_mtf, 2),
            })

    # ── RENTA FIJA (curva de tasas, spreads, T10Y) ────────────────────────────
    # Estructura: [{"activo": "ECH", "score": 2, "direccion": "ALZA", "descripcion": "T10Y subió..."}]
    for rf in (renta_fija or []):
        activo_rf = rf.get("activo")
        if not activo_rf:
            continue
        if activo_rf not in activos:
            activos[activo_rf] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        score_rf = rf.get("score", 0)
        dir_rf   = rf.get("direccion", "")
        if score_rf < 1 or dir_rf not in ("ALZA", "BAJA"):
            continue
        peso_rf = score_rf * 0.4
        activos[activo_rf][dir_rf.lower()] += peso_rf
        activos[activo_rf]["fuentes"].append("Renta Fija")
        activos[activo_rf]["evidencia"].append({
            "fuente": "Renta Fija",
            "señal":  rf.get("descripcion", "")[:80],
            "prob":   None, "direccion": dir_rf, "peso": round(peso_rf, 2),
        })

    # ── SEC 13F (flujos institucionales — bullish por definición si score ≥ 1) ─
    # Estructura: lista de {"activo": "SQM.SN", "ticker": "SQM", "score": 3, "n_fondos": 8, ...}
    _sec_list = sec_13f if isinstance(sec_13f, list) else list((sec_13f or {}).values())
    for data_13f in _sec_list:
        activo_13f = data_13f.get("activo") or data_13f.get("activo_motor", "")
        ticker_13f = data_13f.get("ticker", activo_13f)
        score_13f  = data_13f.get("score", 0)
        if score_13f < 1 or not activo_13f:
            continue
        if activo_13f not in activos:
            activos[activo_13f] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        peso_13f = score_13f * 0.5
        activos[activo_13f]["alza"] += peso_13f
        activos[activo_13f]["fuentes"].append("13F SEC")
        activos[activo_13f]["evidencia"].append({
            "fuente": "13F SEC",
            "señal":  f"{ticker_13f}: {data_13f.get('descripcion', '')} ({data_13f.get('n_fondos', 0)} fondos)",
            "prob":   None, "direccion": "ALZA", "peso": round(peso_13f, 2),
        })

    # ── ORDER FLOW (Level 2 — bid/ask imbalance) ──────────────────────────────
    # Estructura: [{"activo_motor": "SQM.SN", "score": 2, "direccion": "ALZA", "descripcion": "..."}]
    for of_signal in (order_flow or []):
        activo_of = of_signal.get("activo_motor") or of_signal.get("activo", "")
        if not activo_of:
            continue
        if activo_of not in activos:
            activos[activo_of] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        score_of = of_signal.get("score", 0)
        dir_of   = of_signal.get("direccion", "")
        if score_of < 1 or dir_of not in ("ALZA", "BAJA"):
            continue
        peso_of = score_of * 0.5
        activos[activo_of][dir_of.lower()] += peso_of
        activos[activo_of]["fuentes"].append("Order Flow")
        activos[activo_of]["evidencia"].append({
            "fuente": "Order Flow",
            "señal":  of_signal.get("descripcion", "")[:80],
            "prob":   None, "direccion": dir_of, "peso": round(peso_of, 2),
        })

    # ── CORRELACIONES (divergencias entre pares relacionados) ─────────────────
    # Estructura: lista de {"activo": "ECH", "score": 4, "direccion": "ALZA", "descripcion": "..."}
    #
    # FIX: Un activo puede aparecer en N pares simultáneamente (ej. SQM en pares
    # vs ECH, vs GLD, vs cobre). Sumar todos los pares infla el peso con señales
    # que NO son independientes — todas miden la misma divergencia de correlación.
    # Solución: conservar solo el par de mayor score por ticker (best-of-N).
    # Multiplier bajado a 0.3 (era 0.4) — equiparado con Google Trends y Put/Call,
    # señales de validación de momentum relativo, no de momentum directo.
    _corr_list = correlaciones if isinstance(correlaciones, list) else (correlaciones or {}).get("pares", [])
    _corr_best: dict = {}  # ticker → {"score": int, "dir": str, "desc": str}
    for par in _corr_list:
        score_corr = par.get("score", 0)
        if score_corr < 2:
            continue
        ticker1  = par.get("activo") or par.get("ticker1")
        dir_corr = par.get("direccion", "").upper()
        if not ticker1 or dir_corr not in ("ALZA", "BAJA"):
            continue
        prev = _corr_best.get(ticker1)
        if prev is None or score_corr > prev["score"]:
            _corr_best[ticker1] = {
                "score": score_corr,
                "dir":   dir_corr,
                "desc":  par.get("descripcion", ""),
            }

    for ticker1, best in _corr_best.items():
        if ticker1 not in activos:
            activos[ticker1] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        peso_corr = best["score"] * 0.3   # reducido de 0.4 — señal de momentum relativo
        activos[ticker1][best["dir"].lower()] += peso_corr
        activos[ticker1]["fuentes"].append("Correlaciones")
        activos[ticker1]["evidencia"].append({
            "fuente": "Correlaciones",
            "señal":  best["desc"][:80],
            "prob":   None, "direccion": best["dir"], "peso": round(peso_corr, 2),
        })

    # ── IV OPCIONES (implied volatility + posicionamiento calls/puts) ─────────
    # Estructura: lista de {"activo": "SQM.SN", "score": 2, "direccion": "ALZA", "descripcion": "..."}
    _iv_list = iv_opciones if isinstance(iv_opciones, list) else list((iv_opciones or {}).values())
    for data_iv in _iv_list:
        score_iv = data_iv.get("score", 0)
        dir_iv   = data_iv.get("direccion", "").upper()
        activo_iv = data_iv.get("activo") or data_iv.get("activo_motor", "")
        if score_iv < 1 or dir_iv not in ("ALZA", "BAJA") or not activo_iv:
            continue
        if activo_iv not in activos:
            activos[activo_iv] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        peso_iv = score_iv * 0.6
        activos[activo_iv][dir_iv.lower()] += peso_iv
        activos[activo_iv]["fuentes"].append("IV Opciones")
        activos[activo_iv]["evidencia"].append({
            "fuente": "IV Opciones",
            "señal":  data_iv.get("descripcion", "")[:80],
            "prob":   None, "direccion": dir_iv, "peso": round(peso_iv, 2),
        })

    # ── ML (GradientBoosting con balanced accuracy) ───────────────────────────
    # Estructura: [{"activo": "COPEC.SN", "activo_motor": "COPEC.SN", "direccion": "ALZA", "score": 3, "prob_alza": 0.90, "auc": 0.61}]
    for señal_ml in (ml or []):
        activo_ml_key = señal_ml.get("activo_motor") or señal_ml.get("activo", "")
        dir_ml        = señal_ml.get("direccion", "")
        score_ml      = señal_ml.get("score", 0)
        if not activo_ml_key or dir_ml not in ("ALZA", "BAJA") or score_ml < 1:
            continue
        if activo_ml_key not in activos:
            activos[activo_ml_key] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        # Peso reducido de 0.7 → 0.55: el modelo ML usa solo datos técnicos
        # (mismo input que AT/MTF), con riesgo de overfitting en períodos cortos.
        # El score ya viene ajustado por AUC desde ml_signals.py.
        peso_ml_sig = score_ml * 0.55
        activos[activo_ml_key][dir_ml.lower()] += peso_ml_sig
        activos[activo_ml_key]["fuentes"].append("ML")
        activos[activo_ml_key]["evidencia"].append({
            "fuente": "ML",
            "señal":  señal_ml.get("descripcion",
                      f"ML: prob_alza={señal_ml.get('prob_alza', 0):.0%} AUC={señal_ml.get('auc', 0):.2f}")[:80],
            "prob":   round(señal_ml.get("prob_alza", 0.5) * 100, 1),
            "direccion": dir_ml, "peso": round(peso_ml_sig, 2),
        })

    # ── IB DATA (datos live de mercado durante horario activo) ────────────────
    # Estructura: [{"symbol": "SQM", "activo_motor": "SQM.SN", "score": 2, "direccion": "ALZA", "descripcion": "..."}]
    for ib_signal in (ib_data or []):
        activo_ib = ib_signal.get("activo_motor") or ib_signal.get("symbol", "")
        if not activo_ib:
            continue
        if activo_ib not in activos:
            activos[activo_ib] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        score_ib = ib_signal.get("score", 0)
        dir_ib   = ib_signal.get("direccion", "")
        if score_ib < 1 or dir_ib not in ("ALZA", "BAJA"):
            continue
        peso_ib = score_ib * 0.5
        activos[activo_ib][dir_ib.lower()] += peso_ib
        activos[activo_ib]["fuentes"].append("IB Data")
        activos[activo_ib]["evidencia"].append({
            "fuente": "IB Data",
            "señal":  ib_signal.get("descripcion", "")[:80],
            "prob":   None, "direccion": dir_ib, "peso": round(peso_ib, 2),
        })

    return activos


# ── GENERACIÓN ────────────────────────────────────────────────────────────────
def generar_recomendaciones(activos_dict):
    recomendaciones = []

    for activo, data in activos_dict.items():
        alza = data["alza"]
        baja = data["baja"]
        total = alza + baja
        if total < 0.5: continue

        if alza > baja * 1.3:
            accion, direccion, conviccion = "COMPRAR", "ALZA", alza / total
        elif baja > alza * 1.3:
            accion, direccion, conviccion = "VENDER", "BAJA", baja / total
        else:
            continue

        conviccion_pct = round(conviccion * 100, 1)
        fuentes_unicas = list(set(data["fuentes"]))
        n_fuentes = len(fuentes_unicas)

        # Cap de convicción por número de fuentes independientes
        # Con pocas fuentes no se puede llegar a convicción alta aunque estén alineadas
        CAP_FUENTES = {1: 60, 2: 72, 3: 82, 4: 88, 5: 93}
        cap = CAP_FUENTES.get(n_fuentes, 95)
        conviccion_pct = min(conviccion_pct, cap)

        ib_info   = INSTRUMENTOS_IB.get(activo, {})
        tipo      = ib_info.get("tipo", "ETF")
        riesgo    = _calcular_riesgo(tipo, conviccion_pct, n_fuentes)
        horizonte = _calcular_horizonte(n_fuentes, conviccion_pct, tipo_producto=tipo)

        # Volatilidad y SL/TP
        yf_ticker = ib_info.get("yf", activo)
        precio_actual, vol = _get_volatilidad(yf_ticker)
        precio_actual, sl, tp = _calcular_sl_tp(accion, precio_actual, vol, horizonte["dias"], ticker=yf_ticker)

        # Tipo de instrumento sugerido
        instrumentos_sugeridos = _sugerir_instrumento(tipo, accion, horizonte["label"], riesgo, conviccion_pct)

        # Aplicar filtro macro
        try:
            from engine.macro_filtro import evaluar_activo_vs_macro
            ib_info_actual = INSTRUMENTOS_IB.get(activo, {})
            sector_actual  = ib_info_actual.get("sector", "")
            macro_eval     = evaluar_activo_vs_macro(yf_ticker, accion, sector_actual)
            conviccion_pct += macro_eval["ajuste_conviccion"]
            conviccion_pct  = max(0, min(100, conviccion_pct))
            sizing_macro    = macro_eval["ajuste_sizing"]
        except:
            sizing_macro = 1.0

        # ── Ajuste por calidad histórica de fuentes ──────────────────────
        # Factor promedio de las fuentes activas; 1.0 si sin datos suficientes.
        # Rango: [0.85, 1.10] → máximo ajuste ±10% sobre convicción actual.
        factor_calidad = 1.0
        if _source_quality and fuentes_unicas:
            factores = [_source_quality.get(f, 1.0) for f in fuentes_unicas]
            factor_calidad = round(sum(factores) / len(factores), 3)
            conviccion_pct = round(min(cap, conviccion_pct * factor_calidad), 1)
            conviccion_pct = max(0, conviccion_pct)

        # ── Boost por señal persistente (mismo activo+dirección N ciclos) ──
        # streak=1 → +0%, streak=2 → +2%, streak=3 → +4%, streak≥5 → +8%
        boost_persistencia = 0.0
        try:
            from engine.signal_persistence import get_boost
            boost_persistencia = get_boost(activo, accion)
            if boost_persistencia > 0:
                conviccion_pct = min(cap, conviccion_pct + boost_persistencia)
                conviccion_pct = round(conviccion_pct, 1)
        except Exception:
            pass

        tesis = _generar_tesis_resumida(activo, accion, data["evidencia"], fuentes_unicas)

        recomendaciones.append({
            "activo":              activo,
            "ib_ticker":           ib_info.get("ib", activo),
            "tipo":                tipo,
            "descripcion":         ib_info.get("descripcion", activo),
            "accion":              accion,
            "direccion":           direccion,
            "conviccion":          conviccion_pct,
            "score":               round(conviccion_pct / 10, 1),
            "riesgo":              riesgo,
            "horizonte":           horizonte,
            "precio_actual":       precio_actual,
            "stop_loss":           sl,
            "take_profit":         tp,
            "instrumentos":        instrumentos_sugeridos,
            "fuentes":             fuentes_unicas,
            "n_fuentes":           n_fuentes,
            "evidencia":           data["evidencia"],
            "tesis":               tesis,
            "boost_persistencia":  round(boost_persistencia, 1),
            "factor_calidad":      factor_calidad,
        })

    # ── Registrar señales del ciclo para tracking de streaks ─────────────
    try:
        from engine.signal_persistence import registrar_señales_ciclo
        registrar_señales_ciclo(recomendaciones)
    except Exception:
        pass

    return sorted(recomendaciones, key=lambda x: (x["score"], -x["riesgo"]), reverse=True)

def _generar_tesis_resumida(activo, accion, evidencia, fuentes):
    def _ev(fuente): return [e for e in evidencia if e["fuente"] == fuente]
    at_ev      = _ev("Análisis Técnico")
    pc_ev      = _ev("Put/Call")
    poly_ev    = _ev("Polymarket")
    kalshi_ev  = _ev("Kalshi")
    macro_ev   = _ev("Macro USA")
    cmf_ev     = _ev("CMF")
    vol_ev     = _ev("Volumen")
    fg_ev      = _ev("Fear&Greed")
    ml_ev      = _ev("ML")
    iv_ev      = _ev("IV Opciones")
    mtf_ev     = _ev("MTF")
    f13_ev     = _ev("13F SEC")
    corr_ev    = _ev("Correlaciones")
    loc_ev     = _ev("Mercado Local")
    rf_ev      = _ev("Renta Fija")

    partes = []
    if poly_ev:  partes.append(f"Polymarket señala {poly_ev[0]['direccion'].lower()} ({poly_ev[0].get('prob','?')}%)")
    if kalshi_ev:partes.append(f"Kalshi confirma {kalshi_ev[0]['direccion'].lower()}")
    if macro_ev: partes.append(macro_ev[0]["señal"][:50])
    if cmf_ev:   partes.append(f"CMF: {cmf_ev[0]['señal'][:50]}")
    if vol_ev:   partes.append(f"Volumen: {vol_ev[0]['señal'][:40]}")
    if fg_ev:    partes.append(fg_ev[0]["señal"][:40])
    if at_ev:    partes.append(f"AT: {at_ev[0]['señal'][:50]}")
    if mtf_ev:   partes.append(f"MTF: {mtf_ev[0]['señal'][:50]}")
    if ml_ev:    partes.append(f"ML: {ml_ev[0]['señal'][:50]}")
    if iv_ev:    partes.append(f"IV: {iv_ev[0]['señal'][:40]}")
    if f13_ev:   partes.append(f"13F: {f13_ev[0]['señal'][:40]}")
    if corr_ev:  partes.append(f"Corr: {corr_ev[0]['señal'][:40]}")
    if loc_ev:   partes.append(f"Mdo.Local: {loc_ev[0]['señal'][:40]}")
    if rf_ev:    partes.append(f"RF: {rf_ev[0]['señal'][:40]}")
    if pc_ev:    partes.append(f"Put/Call: {pc_ev[0]['señal'][:40]}")
    if partes:
        return f"{accion} {activo}: " + " | ".join(partes[:4])
    return f"{accion} {activo} basado en {', '.join(fuentes)}"
