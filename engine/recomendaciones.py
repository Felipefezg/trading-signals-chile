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

import logging
import requests
import yfinance as yf

# signal_decay: import condicional — fail-open si el módulo no está disponible
try:
    from engine.signal_decay import decay_earnings, decay_noticias, decay_cmf, decay_13f
except Exception:
    # Fallback: sin decay (factor 1.0 = señal fresca, sin penalización)
    def decay_earnings(fecha=None): return 1.0   # noqa: E301
    def decay_noticias(fecha=None): return 1.0
    def decay_cmf(fecha=None):      return 1.0
    def decay_13f(fecha=None):      return 1.0

# ── ESTADO DE RÉGIMEN (módulo-level) ─────────────────────────────────────────
# Actualizado por consolidar_señales() en cada ciclo.
# Leído por generar_recomendaciones() para annotar cada recomendación.
_ultimo_regimen: dict = {"regimen": "RANGING", "ok": False}

def get_ultimo_regimen() -> dict:
    """Retorna la info del último régimen detectado (para dashboard/logs)."""
    return _ultimo_regimen

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
    "CHILE.SN":         {"ib": "BCH",       "tipo": "Acción USA/Chile", "descripcion": "Banco de Chile ADR",           "yf": "BCH"},
    "BSANTANDER.SN":    {"ib": "BSAC",      "tipo": "Acción USA/Chile", "descripcion": "Santander Chile ADR",          "yf": "BSAC"},
    "LTM.SN":           {"ib": "LTM",       "tipo": "Acción USA/Chile", "descripcion": "LATAM Airlines ADR",           "yf": "LTM"},
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
    "BTC-USD":          {"ib": "BTC",       "tipo": "Crypto",           "descripcion": "Bitcoin (IBKR Crypto)",        "yf": "BTC-USD"},
    # Futuros commodities
    "GC=F":             {"ib": "GC",        "tipo": "Futuro",           "descripcion": "Oro (COMEX)",                  "yf": "GC=F"},
    "CL=F":             {"ib": "CL",        "tipo": "Futuro",           "descripcion": "Petróleo WTI (NYMEX)",         "yf": "CL=F"},
    "HG=F":             {"ib": "HG",        "tipo": "Futuro",           "descripcion": "Cobre (COMEX)",                "yf": "HG=F"},
    # ETFs adicionales — Renta Fija / Commodities
    "TLT":              {"ib": "TLT",       "tipo": "ETF",              "descripcion": "iShares 20Y Treasury",         "yf": "TLT"},
    "GLD":              {"ib": "GLD",       "tipo": "ETF",              "descripcion": "SPDR Gold ETF",                "yf": "GLD"},
    # ETFs USA ejecutables — descorrelacionados de Chile
    "QQQ":              {"ib": "QQQ",       "tipo": "ETF",              "descripcion": "Nasdaq 100 ETF",               "yf": "QQQ"},
    "IWM":              {"ib": "IWM",       "tipo": "ETF",              "descripcion": "Russell 2000 ETF",             "yf": "IWM"},
    "XLE":              {"ib": "XLE",       "tipo": "ETF",              "descripcion": "Energy Sector ETF",            "yf": "XLE"},
    # IPSA 30 completo
    "SQM-B.SN":         {"ib": "SQM",       "tipo": "Acción Chile",     "descripcion": "SQM (Bolsa Santiago)",          "yf": "SQM-B.SN"},
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

# ── MAPA IB_TICKER → SECTOR ───────────────────────────────────────────────────
# Derivado de UNIVERSO_COMPLETO (fuente única de verdad).
# Permite que macro_filtro aplique el BENCHMARK_SECTOR correcto a cada activo.
# Sin este mapa, sector_actual siempre era "" y todo el ajuste por sector
# quedaba inactivo — BENCHMARK_SECTOR nunca se consultaba.
try:
    from engine.universo import UNIVERSO_COMPLETO as _UC
    _IB_TO_SECTOR: dict = {v["ib"]: v.get("sector", "") for v in _UC.values() if v.get("ib")}
except Exception:
    _IB_TO_SECTOR = {}

# ── FUENTES APLICABLES POR TIPO DE ACTIVO ─────────────────────────────────────
# Previene phantom confirmations: CMF no confirma SPY, 13F no confirma COPEC.SN,
# IV Opciones no confirma acciones sin opciones líquidas, etc.
# Fuentes fuera del set para un tipo son excluidas del cálculo de convicción.
FUENTES_APLICABLES: dict = {
    "Acción Chile": {
        # Técnico y precio (Bolsa Santiago)
        "Análisis Técnico", "MTF", "Mercado Local", "Volumen",
        # Regulatorio chileno
        "CMF",
        # Macro e indirecto (Chile es precio-aceptante, no excluir)
        "Macro USA", "Fear&Greed", "Noticias",
        # Tasas (Chile sigue curva global via BCCh)
        "Renta Fija",
        # Cross-asset (CLP y cobre correlacionados con IPSA)
        "Correlaciones",
        # Cuantitativo entrenado sobre estos activos
        "ML",
        # Sentimiento macro indirecto
        "Polymarket", "Kalshi",
        # Earnings: aplica solo si la empresa reporta EPS (mayormente ADRs/cross-listadas)
        "Earnings Surprise",
        # Cobre: amplificador directo cuando HG=F se mueve (IPSA ~40% minería)
        "Cobre",
        # NO: 13F SEC, IV Opciones, Order Flow, Put/Call, IB Data, Momentum
        # (no hay opciones líquidas sobre .SN, 13F no cubre empresas solo listadas en Santiago)
    },
    "Acción USA/Chile": {
        # Técnico
        "Análisis Técnico", "MTF", "Momentum",
        # Chile (lado local del dual-listado)
        "CMF", "Mercado Local", "Volumen",
        # USA (lado NYSE del ADR)
        "13F SEC", "IV Opciones", "Order Flow", "Put/Call", "IB Data",
        # Macro
        "Macro USA", "Fear&Greed", "Noticias",
        # Tasas y cross-asset
        "Renta Fija", "Correlaciones",
        # Cuantitativo
        "ML",
        # Sentimiento
        "Polymarket", "Kalshi",
        # Earnings: señal post-evento de alta convicción para ADRs con cobertura de analistas
        "Earnings Surprise",
        # Cobre: amplificador directo (SQM, BCH dual-listadas son altamente copper-linked)
        "Cobre",
    },
    "ETF": {
        # Técnico
        "Análisis Técnico", "MTF", "Momentum",
        # USA (ETFs cotizan en NYSE, opciones líquidas)
        "13F SEC", "IV Opciones", "Order Flow", "Put/Call", "IB Data",
        # Macro y tasas
        "Macro USA", "Fear&Greed", "Renta Fija",
        # Cross-asset y volumen
        "Correlaciones", "Volumen",
        # Sentimiento
        "Polymarket", "Kalshi", "Noticias",
        # Cuantitativo
        "ML",
        # NO: CMF (regulador chileno), Mercado Local (flujo IPSA local)
    },
    "Futuro": {
        # Técnico
        "Análisis Técnico", "MTF",
        # Macro (commodities son esencialmente macro-driven)
        "Macro USA", "Fear&Greed",
        # Cross-asset (cobre ↔ USD, oro ↔ tasas)
        "Correlaciones",
        # Datos live
        "IB Data",
        # Sentimiento (geopolítica mueve commodities)
        "Polymarket", "Kalshi", "Noticias",
        # Cuantitativo
        "ML",
        # NO: CMF, Mercado Local, 13F, IV, Order Flow, Put/Call, Renta Fija, Volumen, Momentum
    },
    "Crypto": {
        # Técnico
        "Análisis Técnico", "MTF", "Momentum",
        # Macro (BTC correlaciona con risk-on/off y liquidez global)
        "Macro USA", "Fear&Greed",
        # Volumen significativo en crypto
        "Volumen",
        # Cross-asset (BTC vs USD, gold en períodos de stress)
        "Correlaciones",
        # Sentimiento (Polymarket/Kalshi cubren eventos crypto)
        "Polymarket", "Kalshi", "Noticias",
        # Cuantitativo
        "ML",
        # NO: CMF, Mercado Local, 13F, IV Opciones, Order Flow, Put/Call, Renta Fija
    },
    "Forex": {
        # Técnico
        "Análisis Técnico", "MTF",
        # Macro (Forex es determinado por macro y diferenciales de tasa)
        "Macro USA", "Fear&Greed",
        # Tasas (diferencial de tasas mueve FX)
        "Renta Fija",
        # Cross-asset
        "Correlaciones",
        # Sentimiento
        "Polymarket", "Kalshi", "Noticias",
        # Cuantitativo
        "ML",
        # NO: CMF, Mercado Local, 13F, IV, Order Flow, Put/Call, Volumen
    },
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

def _calcular_sl_tp(accion, precio, volatilidad, horizonte_dias, ticker=None, regimen=None):
    """
    SL/TP calibrado usando soporte/resistencia real.
    Fallback a volatilidad si no hay niveles disponibles.

    Cap base de SL por tipo de activo:
    - Crypto:   8%  — volatilidad estructuralmente alta
    - ETF:      4%  — instrumentos diversificados, gaps menores
    - Acciones: 5%  — red de seguridad ante caídas bruscas

    El cap y el multiplicador ATR se escalan según el régimen de mercado:

    Régimen       Cap Acciones  Cap ETF  Cap Crypto  Mult ATR
    BULL_TREND        4%          3%        6%         0.80
    RANGING           5%          4%        8%         1.00  ← baseline
    BEAR_TREND        6%          5%        9%         1.20
    HIGH_VOL          8%          6.5%     11%         1.50
    CRISIS           11%          9%       14%         2.00

    Racional: en HIGH_VOL/CRISIS la volatilidad realizada supera la histórica
    y el ATR de 20d subestima el ruido real — un SL demasiado ajustado se
    activa antes de que el trade pueda desarrollarse.
    """
    if precio is None:
        return None, None, None

    # ── Parámetros por régimen ───────────────────────────────────────────────
    # Cada entrada: (cap_acciones, cap_etf, cap_crypto, mult_atr)
    _REGIMEN_SL: dict = {
        "BULL_TREND": (0.04, 0.03, 0.06, 0.80),
        "RANGING":    (0.05, 0.04, 0.08, 1.00),
        "BEAR_TREND": (0.06, 0.05, 0.09, 1.20),
        "HIGH_VOL":   (0.08, 0.065, 0.11, 1.50),
        "CRISIS":     (0.11, 0.09, 0.14, 2.00),
    }
    _reg = regimen if regimen in _REGIMEN_SL else "RANGING"
    _cap_acc, _cap_etf, _cap_cry, _mult_atr = _REGIMEN_SL[_reg]

    # Cap según tipo de activo
    _ticker_str = (ticker or "").upper()
    if _ticker_str in ("BTC-USD", "ETH-USD", "BTC", "ETH"):
        _sl_cap_pct = _cap_cry
    elif _ticker_str in ("SPY", "ECH", "GLD", "TLT", "SLV", "GDX", "QQQ", "IWM", "XLE", "GC=F", "CL=F", "HG=F"):
        _sl_cap_pct = _cap_etf
    else:
        _sl_cap_pct = _cap_acc

    def _aplicar_cap(sl_raw, accion_):
        """Fuerza SL dentro del cap máximo adaptivo al régimen."""
        if sl_raw is None:
            return None
        if accion_ == "COMPRAR":
            sl_min = round(precio * (1 - _sl_cap_pct), 4)
            return max(sl_raw, sl_min)
        else:
            sl_max = round(precio * (1 + _sl_cap_pct), 4)
            return min(sl_raw, sl_max)

    # ── Soporte/resistencia calibrado ────────────────────────────────────────
    if ticker:
        try:
            from engine.soporte_resistencia import calcular_sl_tp_calibrado
            atr = precio * volatilidad * _mult_atr if volatilidad else None
            sl_sr, tp_sr = calcular_sl_tp_calibrado(ticker, accion, precio, atr)
            if sl_sr and tp_sr:
                sl_capped = _aplicar_cap(sl_sr, accion)
                return precio, sl_capped, tp_sr
        except:
            pass

    # ── Fallback: ATR escalado por régimen ───────────────────────────────────
    if volatilidad is None:
        return None, None, None

    dias_map = {"1–7 días": 5, "1–4 semanas": 15, "1–3 meses": 45}
    dias = 10
    for k, v in dias_map.items():
        if k in str(horizonte_dias):
            dias = v
            break

    # _mult_atr escala el movimiento esperado según el régimen:
    # en CRISIS el ATR histórico (20d) subestima la vol real → ampliar
    mov = precio * volatilidad * (dias / 20) ** 0.5 * _mult_atr

    if accion == "COMPRAR":
        sl = round(precio - mov, 2)
        tp = round(precio + mov * 2, 2)
    else:
        sl = round(precio + mov, 2)
        tp = round(precio - mov * 2, 2)

    sl = _aplicar_cap(sl, accion)
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
def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None, put_call=None, analisis_tecnico=None, google_trends=None, ib_data=None, mercado_local=None, renta_fija=None, mtf=None, sec_13f=None, order_flow=None, correlaciones=None, iv_opciones=None, ml=None, momentum=None, earnings_surprise=None):
    # _source_quality se carga en generar_recomendaciones() para que funcione
    # también cuando es llamado directamente desde el dashboard.

    # Inicializar SOLO los activos ejecutables del universo (25 activos).
    # Pre-filtrar aquí evita consolidar señales de los ~30 activos que nunca
    # pasan validar_señal() en motor_automatico (liquidez insuficiente en IB).
    # Antes: 55 activos de UNIVERSO_COMPLETO → 78% de rechazos eran ruido puro.
    # Ahora: solo UNIVERSO_EJECUTABLE → cero cómputo innecesario en consolidación.
    # Fuentes que agregan tickers dinámicamente (correlaciones, etc.) pasan
    # igualmente por el filtro de generar_recomendaciones() antes del cómputo pesado.
    activos = {}
    try:
        from engine.universo import UNIVERSO_EJECUTABLE
        for yf_ticker in UNIVERSO_EJECUTABLE:
            activos[yf_ticker] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
    except Exception:
        # Fallback: si UNIVERSO_EJECUTABLE no está disponible, usar UNIVERSO_COMPLETO
        try:
            from engine.universo import UNIVERSO_COMPLETO
            for yf_ticker in UNIVERSO_COMPLETO:
                activos[yf_ticker] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        except Exception:
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
                fecha_noticia  = n.get("fecha", "")
                _d_noticias    = decay_noticias(fecha_noticia)
                peso_noticia   = round(n.get("score", 0) * 0.1 * _d_noticias, 3)
                activos[activo]["fuentes"].append("Noticias")
                activos[activo]["evidencia"].append({
                    "fuente":       "Noticias",
                    "señal":        n.get("titulo", "")[:80],
                    "prob":         None,
                    "direccion":    "NEUTRAL",
                    "peso":         peso_noticia,
                    "fecha_señal":  fecha_noticia,
                    "decay":        round(_d_noticias, 3),
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
        # Cada empresa → su propio ticker .SN (no al ETF genérico ECH)
        "SQM":        "SQM-B.SN",
        "COPEC":      "COPEC.SN",
        "FALABELLA":  "FALABELLA.SN",
        "BCI":        "BCI.SN",
        "SANTANDER":  "BSANTANDER.SN",
        "CHILE":      "CHILE.SN",
        "CMPC":       "CMPC.SN",
        "LATAM":      "LTM.SN",
        "VAPORES":    "VAPORES.SN",
        "CAP":        "CAP.SN",
        "COLBUN":     "COLBUN.SN",
        "ENELCHILE":  "ENELCHILE.SN",
        "CENCOSUD":   "CENCOSUD.SN",
        "ENELAM":     "ENELAM.SN",
        "ITAUCL":     "ITAUCL.SN",
        "CCU":        "CCU.SN",
        "PARAUCO":    "PARAUCO.SN",
        "RIPLEY":     "RIPLEY.SN",
        "ANDINA-B":   "ANDINA-B.SN",
        "CONCHATORO": "CONCHATORO.SN",
        "ILC":        "ILC.SN",
        "SONDA":      "SONDA.SN",
        "ECL":        "ECL.SN",
        "SMU":        "SMU.SN",
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
        # Cada .SN → su propio ticker (señal de volumen específica por empresa)
        "SQM-B.SN":     "SQM-B.SN",
        "SQM":          "SQM-B.SN",
        "COPEC.SN":     "COPEC.SN",
        "BCI.SN":       "BCI.SN",
        "CHILE.SN":     "CHILE.SN",
        "BSANTANDER.SN":"BSANTANDER.SN",
        "FALABELLA.SN": "FALABELLA.SN",
        "CENCOSUD.SN":  "CENCOSUD.SN",
        "CMPC.SN":      "CMPC.SN",
        "COLBUN.SN":    "COLBUN.SN",
        "ENELCHILE.SN": "ENELCHILE.SN",
        "LTM.SN":       "LTM.SN",
        "CAP.SN":       "CAP.SN",
        "CCU.SN":       "CCU.SN",
        "ECH":          "ECH",
        "SPY":          "SPY",
        "QQQ":          "QQQ",
        "IWM":          "IWM",
        "XLE":          "XLE",
        "GLD":          "GLD",
        "SLV":          "SLV",
        "TLT":          "TLT",
        "BTC-USD":      "BTC-USD",
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
        # 13F es SLOW/lagging (archivos trimestrales de hace ≤45 días).
        # Peso reducido — solo contexto de posicionamiento institucional,
        # nunca debe ser la fuente determinante de timing de entrada.
        # Decay HL=720h: archivo de ayer → decay≈1.0, archivo de 30d → decay≈0.50
        fecha_13f  = data_13f.get("fecha_señal", "")
        _d_13f     = decay_13f(fecha_13f)
        peso_13f   = score_13f * 0.25 * _d_13f
        activos[activo_13f]["alza"] += peso_13f
        activos[activo_13f]["fuentes"].append("13F SEC")
        activos[activo_13f]["evidencia"].append({
            "fuente":      "13F SEC",
            "señal":       f"{ticker_13f}: {data_13f.get('descripcion', '')} ({data_13f.get('n_fondos', 0)} fondos)",
            "prob":        None,
            "direccion":   "ALZA",
            "peso":        round(peso_13f, 3),
            "fecha_señal": fecha_13f,
            "decay":       round(_d_13f, 3),
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

    # ── PROPAGACIÓN FUTURO → ETF EQUIVALENTE ─────────────────────────────────
    # Cuando un futuro tiene señal neta fuerte, propagar al ETF que lo replica.
    # Factor 0.5x: mismo subyacente pero vehículo diferente — no es señal independiente.
    # Esto cierra la brecha GC=F (87-93%) → GLD (~65%) que existe porque GLD solo recibe
    # AT/MTF de su propia serie de precio, sin capturar el consenso macro del futuro.
    _FUTURO_ETF_MAP = {
        "GC=F": ["GLD", "GDX"],   # Oro → SPDR Gold ETF + Gold Miners
        "SI=F": ["SLV"],          # Plata → iShares Silver ETF
        "CL=F": ["XLE"],          # Petróleo → Energy Select Sector ETF (ejecutable en IB)
        # USO eliminado — no está en universo ejecutable; XLE es mejor proxy (beta ~0.88 vs CL=F)
    }
    for futuro, etfs in _FUTURO_ETF_MAP.items():
        if futuro not in activos:
            continue
        f_data  = activos[futuro]
        neto_f  = f_data["alza"] - f_data["baja"]
        if abs(neto_f) < 1.0:   # solo propagar si la señal neta supera umbral mínimo
            continue
        dir_prop  = "alza" if neto_f > 0 else "baja"
        peso_prop = round(abs(neto_f) * 0.5, 2)   # 50% del diferencial neto
        for etf in etfs:
            if etf not in activos:
                activos[etf] = {"alza": 0.0, "baja": 0.0, "fuentes": [], "evidencia": []}
            activos[etf][dir_prop] += peso_prop
            activos[etf]["fuentes"].append("Correlaciones")
            activos[etf]["evidencia"].append({
                "fuente":    "Correlaciones",
                "señal":     f"{futuro}→{etf}: propagación señal futuro equivalente (neto {neto_f:+.2f})",
                "prob":      None,
                "direccion": dir_prop.upper(),
                "peso":      peso_prop,
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

    # ── MOMENTUM INTRADAY (aceleración precio + volumen últimos 30 min) ─────────
    # Fuente FAST: detecta movimientos sostenidos con confirmación de volumen.
    # Peso mayor que otras fuentes técnicas — señal directa de acción de precio.
    for mom in (momentum or []):
        activo_mom = mom.get("activo_motor", "")
        score_mom  = mom.get("score", 0)
        dir_mom    = mom.get("direccion", "")
        if not activo_mom or score_mom < 1 or dir_mom not in ("ALZA", "BAJA"):
            continue
        if activo_mom not in activos:
            activos[activo_mom] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        peso_mom = score_mom * 1.2   # Fast source — peso elevado
        activos[activo_mom][dir_mom.lower()] += peso_mom
        activos[activo_mom]["fuentes"].append("Momentum")
        activos[activo_mom]["evidencia"].append({
            "fuente":    "Momentum",
            "señal":     mom.get("descripcion", "")[:80],
            "prob":      None,
            "direccion": dir_mom,
            "peso":      round(peso_mom, 2),
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

    # ── EARNINGS SURPRISE (EPS post-evento, ventana T+0 a T+3) ──────────────────
    # Señal de alta convicción: sorpresa de EPS vs consenso en últimas 72h.
    # peso = score × 2.0  (score 1→2, score 2→4, score 3→6)
    # Fuente independiente — no correlacionada con técnico/macro.
    for señal_earn in (earnings_surprise or []):
        # Preferir activo (yf_ticker canónico) sobre activo_motor (ib_ticker)
        # La normalización post-acumulación (_ALIAS_CANONICAL) resuelve aliases residuales.
        activo_earn = señal_earn.get("activo") or señal_earn.get("activo_motor", "")
        if not activo_earn:
            continue
        if activo_earn not in activos:
            activos[activo_earn] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        score_earn = señal_earn.get("score", 0)
        dir_earn   = señal_earn.get("direccion", "")
        if score_earn < 1 or dir_earn not in ("COMPRAR", "VENDER"):
            continue
        # Mapear COMPRAR/VENDER → alza/baja (las otras fuentes usan ALZA/BAJA)
        dir_bucket    = "alza" if dir_earn == "COMPRAR" else "baja"
        dir_label     = "ALZA" if dir_earn == "COMPRAR" else "BAJA"
        fecha_reporte = señal_earn.get("fecha_reporte", "")
        _d_earn       = decay_earnings(fecha_reporte)
        peso_earn     = score_earn * 2.0 * _d_earn   # Decae a 50% a las 36h
        activos[activo_earn][dir_bucket] += peso_earn
        activos[activo_earn]["fuentes"].append("Earnings Surprise")
        activos[activo_earn]["evidencia"].append({
            "fuente":      "Earnings Surprise",
            "señal":       señal_earn.get("descripcion", "")[:80],
            "prob":        None,
            "direccion":   dir_label,
            "peso":        round(peso_earn, 3),
            "fecha_señal": fecha_reporte,
            "decay":       round(_d_earn, 3),
        })

    # ── Régimen de mercado — reponderación dinámica ───────────────────────────
    # Ajusta los pesos de evidencia según el régimen actual (BULL/BEAR/HIGH_VOL/RANGING/CRISIS).
    # Recalcula alza/baja desde la evidencia ajustada para mantener consistencia.
    # Fail-open: si market_regime falla → multiplicadores vacíos → sin cambio.
    global _ultimo_regimen
    _regime_info: dict = {}
    try:
        from engine.market_regime import get_multiplicadores, detectar_regimen
        _mult_regimen  = get_multiplicadores()   # {fuente: factor_float}
        _regime_info   = detectar_regimen()
        _ultimo_regimen = _regime_info          # exponer para dashboard
        _regimen_actual = _regime_info.get("regimen", "RANGING")

        if _mult_regimen:
            for _activo, _data in activos.items():
                _nueva_alza = 0.0
                _nueva_baja = 0.0
                for _ev in _data.get("evidencia", []):
                    _fuente_ev  = _ev.get("fuente", "")
                    _factor_ev  = _mult_regimen.get(_fuente_ev, 1.0)
                    _peso_orig  = _ev.get("peso", 0.0)
                    _peso_adj   = round(_peso_orig * _factor_ev, 3)
                    _ev["peso"]          = _peso_adj
                    _ev["regime_factor"] = _factor_ev
                    _dir_ev = _ev.get("direccion", "").upper()
                    if _dir_ev in ("ALZA", "COMPRAR"):
                        _nueva_alza += _peso_adj
                    elif _dir_ev in ("BAJA", "VENDER"):
                        _nueva_baja += _peso_adj
                _data["alza"] = round(_nueva_alza, 4)
                _data["baja"] = round(_nueva_baja, 4)

        logging.debug(f"[régimen] {_regimen_actual} aplicado — {len(_mult_regimen)} fuentes ajustadas")

    except Exception as _e_reg:
        logging.warning(f"[régimen] Reponderación falló: {_e_reg} — pesos sin cambio")

    # ── Cobre-linked: amplificación + descuento de co-linealidad ─────────────
    # Amplifica señales de activos con alta beta al cobre cuando HG=F se mueve.
    # Penaliza el peso (no el conteo) de fuentes co-lineales (Macro, Corr, etc.)
    # que probablemente reflejan el mismo driver macro, no información independiente.
    # Fail-open: si la detección de cobre falla → activos sin cambio.
    try:
        from engine.cobre_amplifier import amplificar_señales_cobre
        activos = amplificar_señales_cobre(activos)
    except Exception as _e_cu:
        logging.warning(f"[cobre] amplificador no aplicado: {_e_cu}")

    # ── Normalizar aliases — merge post-acumulación ───────────────────────────
    # Mismo activo puede haber acumulado señales bajo keys distintos porque
    # diferentes fuentes usan formatos distintos (SQM-B.SN vs SQM vs SQM.SN).
    # Este map consolida todo al ticker canónico antes de retornar.
    # Canónico = yf_ticker del UNIVERSO_COMPLETO (fuente de verdad).
    _ALIAS_CANONICAL = {
        # SQM: "SQM.SN" es un key erróneo en INSTRUMENTOS_IB que apunta al ADR.
        # Normalizar a "SQM" (ADR en UNIVERSO_COMPLETO/ADRS_CHILE).
        # "SQM-B.SN" (Santiago) y "SQM" (NYSE ADR) son instrumentos distintos → no mergeados.
        "SQM.SN":         "SQM",
        # Santander Chile
        "BSAC":           "BSANTANDER.SN",
        # Banco de Chile
        "BCH":            "CHILE.SN",
        # LATAM Airlines
        "LTM":            "LTM.SN",
        # S&P 500 index vs ETF
        "^GSPC":          "SPY",
        # Bitcoin (key alternativo)
        "BTC":            "BTC-USD",
        "BTC_LOCAL_SPREAD": "BTC-USD",
        # Futuros (ib ticker corto vs yf)
        "GC":             "GC=F",
        "HG":             "HG=F",
        "CL":             "CL=F",
        # Acciones Chile: ib_ticker corto → yf_ticker con .SN
        # (el segundo loop de init ya fue eliminado, pero sources dinámicas
        #  pueden haber creado estas keys)
        "COPEC":          "COPEC.SN",
        "BCI":            "BCI.SN",
        "FALABELLA":      "FALABELLA.SN",
        "CENCOSUD":       "CENCOSUD.SN",
        "CMPC":           "CMPC.SN",
        "COLBUN":         "COLBUN.SN",
        "ENELCHILE":      "ENELCHILE.SN",
        "ENELAM":         "ENELAM.SN",
        "ENTEL":          "ENTEL.SN",
        "CAP":            "CAP.SN",
        "CCU":            "CCU.SN",
        "ITAUCL":         "ITAUCL.SN",
        "PARAUCO":        "PARAUCO.SN",
        "MALLPLAZA":      "MALLPLAZA.SN",
        "RIPLEY":         "RIPLEY.SN",
        "AGUAS-A":        "AGUAS-A.SN",
        "VAPORES":        "VAPORES.SN",
        "ANDINA-B":       "ANDINA-B.SN",
        "ILC":            "ILC.SN",
        "CONCHATORO":     "CONCHATORO.SN",
        "FORUS":          "FORUS.SN",
        "SMU":            "SMU.SN",
        "ECL":            "ECL.SN",
        "SONDA":          "SONDA.SN",
        "BESALCO":        "BESALCO.SN",
        "SALFACORP":      "SALFACORP.SN",
        "SOCOVESA":       "SOCOVESA.SN",
        "INGEVEC":        "INGEVEC.SN",
        "HITES":          "HITES.SN",
        "MOLYMET":        "MOLYMET.SN",
        "QUINENCO":       "QUINENCO.SN",
        "MASISA":         "MASISA.SN",
        "HABITAT":        "HABITAT.SN",
        "PROVIDA":        "PROVIDA.SN",
        "MARINSA":        "MARINSA.SN",
    }

    for alias, canon in _ALIAS_CANONICAL.items():
        if alias not in activos:
            continue
        if alias == canon:
            continue
        # Asegurar que el canónico exista
        if canon not in activos:
            activos[canon] = {"alza": 0.0, "baja": 0.0, "fuentes": [], "evidencia": []}
        # Merge: sumar pesos y concatenar evidencia
        activos[canon]["alza"]     += activos[alias]["alza"]
        activos[canon]["baja"]     += activos[alias]["baja"]
        activos[canon]["fuentes"]  += activos[alias]["fuentes"]
        activos[canon]["evidencia"] += activos[alias]["evidencia"]
        del activos[alias]

    return activos


# ── GENERACIÓN ────────────────────────────────────────────────────────────────
def generar_recomendaciones(activos_dict):
    recomendaciones = []

    # Pre-cargar universo ejecutable para filtrar activos no ejecutables
    # antes de generar la recomendación completa (evita cómputo innecesario
    # para SMALL_CAPS y acciones .SN de bajo peso que siempre se rechazan en validar_señal).
    _ejecutables: set = set()
    try:
        from engine.universo import UNIVERSO_EJECUTABLE
        _ejecutables = {v["ib"] for v in UNIVERSO_EJECUTABLE.values()}
    except Exception:
        pass  # Si falla el import, no filtrar — fail-open

    # Cargar factores de calidad por fuente (win_rate histórico).
    # Se carga una vez aquí para que generar_recomendaciones() funcione tanto
    # cuando es llamado directamente (dashboard) como desde consolidar_señales().
    _source_quality: dict = {}
    try:
        from engine.feedback_loop import get_source_quality_factors
        _source_quality = get_source_quality_factors(min_trades=3)
    except Exception:
        pass

    for activo, data in activos_dict.items():
        # ── Filtro ejecutabilidad — descartar antes del cómputo pesado ─────
        # SMALL_CAPS y acciones .SN de bajo peso generan señales pero nunca
        # pasan validar_señal() (is_ejecutable=False). Filtrarlos aquí ahorra
        # cómputo de volatilidad, SL/TP y LLM, y elimina entradas RECHAZADA
        # del log que son ruido estructural (no errores reales).
        if _ejecutables:
            ib_ticker_check = INSTRUMENTOS_IB.get(activo, {}).get("ib", activo)
            if ib_ticker_check not in _ejecutables:
                continue  # no ejecutable — omitir silenciosamente

        # ── Filtro blacklist nocional — futuros que nunca se ejecutan ────────
        # GC (oro), HG (cobre), CL (petróleo) tienen nocional >$25k/contrato.
        # Están en BLACKLIST_AUTO en motor_automatico → nunca se ejecutan.
        # Filtrarlos aquí evita: (a) cómputo innecesario, (b) señales en DB
        # que distorsionan el hit rate y el conteo de fuentes_minimas.
        try:
            from engine.motor_automatico import BLACKLIST_AUTO as _BLACKLIST_AUTO
            if ib_ticker_check in _BLACKLIST_AUTO:
                continue  # futuro de nocional masivo — jamás ejecutable
        except Exception:
            pass  # fail-open: si no se puede importar, no filtrar

        # ── Tipo de activo → determinar fuentes aplicables ────────────────
        # Busca en INSTRUMENTOS_IB primero, luego en universo maestro.
        ib_info_pre = INSTRUMENTOS_IB.get(activo, {})
        tipo_pre    = ib_info_pre.get("tipo", "")
        if not tipo_pre:
            try:
                from engine.universo import UNIVERSO_COMPLETO
                tipo_pre = UNIVERSO_COMPLETO.get(activo, {}).get("tipo", "ETF")
            except Exception:
                tipo_pre = "ETF"

        fuentes_ok   = FUENTES_APLICABLES.get(tipo_pre, set())
        evidencia_raw = data.get("evidencia", [])

        # Separar evidencia aplicable de la no aplicable
        evidencia_ok  = [e for e in evidencia_raw if e["fuente"] in fuentes_ok]
        evidencia_out = [e for e in evidencia_raw if e["fuente"] not in fuentes_ok]

        # Restar contribuciones de fuentes no aplicables a los pesos acumulados.
        # Fear&Greed es multiplicativo (no aparece en evidencia_out si está en todos
        # los tipos), por eso se resta solo el peso aditivo registrado en evidencia.
        alza = data["alza"]
        baja = data["baja"]
        for e in evidencia_out:
            dir_e = e.get("direccion", "")
            peso_e = e.get("peso", 0.0)
            if dir_e == "ALZA":
                alza = max(0.0, alza - peso_e)
            elif dir_e == "BAJA":
                baja = max(0.0, baja - peso_e)

        total = alza + baja
        if total < 0.5: continue

        if alza > baja * 1.3:
            accion, direccion, conviccion = "COMPRAR", "ALZA", alza / total
        elif baja > alza * 1.3:
            accion, direccion, conviccion = "VENDER", "BAJA", baja / total
        else:
            continue

        # ── Filtro: short Crypto no disponible en paper trading ───────────────
        # IB paper trading no permite short directo sobre Crypto (BTC).
        # Si la señal es VENDER y no hay posición larga abierta, la orden
        # falla siempre → filtrar aquí evita cómputo pesado (SL/TP, LLM)
        # y el ruido de RECHAZADA en el log.
        if tipo_pre == "Crypto" and accion == "VENDER":
            continue  # short Crypto: omitir silenciosamente

        conviccion_pct = round(conviccion * 100, 1)
        # Fuentes y n_fuentes basados solo en evidencia aplicable al tipo
        fuentes_unicas = list(set(e["fuente"] for e in evidencia_ok))
        n_fuentes      = len(fuentes_unicas)
        # Fuentes descartadas por tipo (para trazabilidad en dashboard)
        fuentes_excluidas = list(set(e["fuente"] for e in evidencia_out))

        # ── Gate por calidad histórica: solo fuentes con WR suficiente ────────
        # Un factor_quality >= 0.90 equivale a WR >= 45% (apenas por encima del
        # azar). Fuentes por debajo de ese umbral siguen aportando evidencia y
        # se muestran en el dashboard, pero NO cuentan hacia n_fuentes para el
        # check de fuentes_minimas en validar_señal().
        # Fuentes sin historial suficiente (ausentes en _source_quality) reciben
        # factor 1.0 por defecto → pasan el gate (inocentes hasta no demostrar lo contrario).
        _MIN_QUALITY_GATE = 0.90   # factor ≈ WR 45%
        if _source_quality:
            fuentes_credibles      = [f for f in fuentes_unicas
                                      if _source_quality.get(f, 1.0) >= _MIN_QUALITY_GATE]
            fuentes_descartadas_wr = [f for f in fuentes_unicas
                                      if _source_quality.get(f, 1.0) < _MIN_QUALITY_GATE]
        else:
            # Sin datos de calidad → todas las fuentes pasan (comportamiento anterior)
            fuentes_credibles      = fuentes_unicas
            fuentes_descartadas_wr = []
        n_fuentes_credibles = len(fuentes_credibles)

        # Cap de convicción por fuentes CREDIBLES — solo confirmaciones con
        # track record positivo elevan el cap. Una señal con 3 fuentes pero
        # dos de baja calidad queda cappada igual que una de 1 fuente creíble.
        CAP_FUENTES = {1: 60, 2: 76, 3: 85, 4: 90, 5: 95}
        cap = CAP_FUENTES.get(n_fuentes_credibles, 95)
        conviccion_pct = min(conviccion_pct, cap)

        ib_info   = INSTRUMENTOS_IB.get(activo, {})
        # tipo_pre ya aplicó el fallback correcto a UNIVERSO_COMPLETO — reutilizarlo
        # evita que activos nuevos (añadidos al universo pero no a INSTRUMENTOS_IB)
        # reciban tipo="ETF" por default y pasen el filtro de horario incorrectamente.
        tipo      = tipo_pre if tipo_pre else ib_info.get("tipo", "ETF")
        riesgo    = _calcular_riesgo(tipo, conviccion_pct, n_fuentes_credibles)
        horizonte = _calcular_horizonte(n_fuentes_credibles, conviccion_pct, tipo_producto=tipo)

        # Volatilidad y SL/TP — adaptivo al régimen de mercado
        yf_ticker = ib_info.get("yf", activo)
        precio_actual, vol = _get_volatilidad(yf_ticker)
        precio_actual, sl, tp = _calcular_sl_tp(
            accion, precio_actual, vol, horizonte["dias"],
            ticker=yf_ticker,
            regimen=_ultimo_regimen.get("regimen", "RANGING"),
        )

        # Tipo de instrumento sugerido
        instrumentos_sugeridos = _sugerir_instrumento(tipo, accion, horizonte["label"], riesgo, conviccion_pct)

        # Aplicar filtro macro
        try:
            from engine.macro_filtro import evaluar_activo_vs_macro
            ib_info_actual = INSTRUMENTOS_IB.get(activo, {})
            # Derivar sector desde UNIVERSO_COMPLETO (fuente única de verdad).
            # INSTRUMENTOS_IB no tiene campo "sector", así que sin este lookup
            # sector_actual siempre era "" → BENCHMARK_SECTOR nunca se aplicaba.
            _ib_tk_actual  = ib_info_actual.get("ib", activo)
            sector_actual  = _IB_TO_SECTOR.get(_ib_tk_actual, "")
            macro_eval     = evaluar_activo_vs_macro(yf_ticker, accion, sector_actual)
            conviccion_pct += macro_eval["ajuste_conviccion"]
            conviccion_pct  = max(0, min(100, conviccion_pct))
            sizing_macro    = macro_eval["ajuste_sizing"]
        except:
            sizing_macro = 1.0

        # ── Ajuste por calidad histórica de fuentes ──────────────────────
        # Factor promedio solo sobre fuentes CREDIBLES — excluir las de baja calidad
        # del promedio evita que arrastren hacia abajo el factor de fuentes buenas.
        # Rango: [0.85, 1.10] → máximo ajuste ±10% sobre convicción actual.
        factor_calidad = 1.0
        _fuentes_para_factor = fuentes_credibles if fuentes_credibles else fuentes_unicas
        if _source_quality and _fuentes_para_factor:
            factores = [_source_quality.get(f, 1.0) for f in _fuentes_para_factor]
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

        tesis = _generar_tesis_resumida(activo, accion, evidencia_ok, fuentes_unicas)

        # Garantizar que convicción sea siempre un float limpio (1 decimal)
        # independientemente del camino que haya tomado (con o sin source_quality,
        # con o sin boost). Previene valores como 62.900000000000006 en logs.
        conviccion_pct = round(conviccion_pct, 1)

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
            "sl_regimen":          _ultimo_regimen.get("regimen", "RANGING"),
            "instrumentos":        instrumentos_sugeridos,
            "fuentes":             fuentes_unicas,
            "n_fuentes":           n_fuentes_credibles,   # fuentes con WR >= gate — lo que valida_señal() verifica
            "n_fuentes_total":     n_fuentes,             # todas las fuentes aplicables (para dashboard)
            "fuentes_credibles":   fuentes_credibles,
            "fuentes_descartadas_wr": fuentes_descartadas_wr,   # baja calidad histórica — no cuentan para fuentes_minimas
            "evidencia":           evidencia_ok,
            "fuentes_excluidas":   fuentes_excluidas,
            "tesis":               tesis,
            "boost_persistencia":  round(boost_persistencia, 1),
            "factor_calidad":      factor_calidad,
            "regimen_mercado":     _ultimo_regimen.get("regimen", "RANGING"),
        })

    # ── Dedup de seguridad: un ib_ticker → una recomendación ─────────────
    # El merge post-acumulación en consolidar_señales() debería haber eliminado
    # los duplicados. Este paso es red de seguridad para fuentes dinámicas que
    # hayan creado keys no cubiertos por _ALIAS_CANONICAL.
    # Si hay señales contradictorias (COMPRAR y VENDER mismo ib_ticker),
    # conservamos la de mayor convicción y marcamos el conflicto.
    visto_ib: dict = {}
    for r in recomendaciones:
        ib = r["ib_ticker"]
        if ib not in visto_ib:
            visto_ib[ib] = r
        else:
            prev = visto_ib[ib]
            if r["accion"] != prev["accion"]:
                # Conflicto de dirección — conservar mayor convicción, marcar
                mejor = r if r["conviccion"] > prev["conviccion"] else prev
                mejor = dict(mejor)  # copia para no mutar el original
                mejor["tesis"] = "[⚠ SEÑAL CONFLICTIVA] " + mejor["tesis"]
                visto_ib[ib] = mejor
            else:
                # Misma dirección — conservar el de mayor convicción
                if r["conviccion"] > prev["conviccion"]:
                    visto_ib[ib] = r

    recomendaciones = list(visto_ib.values())

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
