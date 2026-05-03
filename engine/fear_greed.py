"""
Fear & Greed Index Chile
Indicador agregado de sentimiento de mercado 0-100.

Componentes (ponderados):
1. VIX (20%) — miedo global
2. Momentum IPSA (20%) — tendencia precio
3. Spread BTC local vs global (15%) — apetito por riesgo crypto
4. Sentiment noticias NLP (20%) — tono de prensa financiera
5. Amplitud mercado IPSA (15%) — % acciones subiendo
6. Cobre momentum (10%) — commodity clave Chile

Escala:
0-25:  Miedo Extremo  → oportunidad de compra contrarian
26-45: Miedo          → cautela, posibles oportunidades
46-55: Neutro         → sin sesgo claro
56-75: Codicia        → cautela al alza
76-100: Codicia Extrema → señal de venta contrarian
"""

import yfinance as yf
import requests
import numpy as np
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.cache_helper import cache_get, cache_set
from datetime import timedelta

# ── COMPONENTES ───────────────────────────────────────────────────────────────
PESOS = {
    "vix":          0.20,
    "momentum_ipsa": 0.20,
    "sentiment":    0.20,
    "amplitud":     0.15,
    "spread_btc":   0.15,
    "cobre":        0.10,
}

def _score_vix():
    """
    VIX alto = miedo → score bajo
    VIX < 15: euforia (score alto)
    VIX 15-20: normal
    VIX 20-30: miedo
    VIX > 30: miedo extremo (score bajo)
    """
    try:
        h = yf.Ticker("^VIX").history(period="5d")
        if h.empty:
            return 50, "N/D"
        vix = float(h["Close"].iloc[-1])
        if vix < 15:
            score = 85
        elif vix < 20:
            score = 65
        elif vix < 25:
            score = 45
        elif vix < 30:
            score = 30
        else:
            score = max(5, 30 - (vix - 30) * 2)
        return round(score), round(vix, 1)
    except:
        return 50, "N/D"

def _score_momentum_ipsa():
    """
    Momentum ECH: retorno 20 días vs retorno 5 días
    Tendencia alcista = score alto
    Tendencia bajista = score bajo
    """
    try:
        h = yf.Ticker("ECH").history(period="30d")
        if len(h) < 10:
            return 50, "N/D"
        ret_5d  = (h["Close"].iloc[-1] / h["Close"].iloc[-5] - 1) * 100
        ret_20d = (h["Close"].iloc[-1] / h["Close"].iloc[-20] - 1) * 100 if len(h) >= 20 else ret_5d

        # Combinar señales
        señal = (ret_5d * 0.6 + ret_20d * 0.4)
        score = 50 + np.clip(señal * 5, -45, 45)
        return round(score), round(ret_5d, 2)
    except:
        return 50, "N/D"

def _score_amplitud():
    """
    % acciones IPSA subiendo vs bajando
    >70% subiendo = euforia
    <30% subiendo = miedo
    """
    try:
        tickers = [
            "ECH", "SQM", "COPEC.SN", "BCI.SN", "CHILE.SN",
            "CMPC.SN", "FALABELLA.SN", "CENCOSUD.SN", "CCU.SN",
            "ENELCHILE.SN", "COLBUN.SN", "ENTEL.SN", "LTM.SN",
            "CAP.SN", "BSANTANDER.SN"
        ]
        subiendo = 0
        total    = 0
        for ticker in tickers:
            try:
                h = yf.Ticker(ticker).history(period="2d")
                if len(h) >= 2:
                    ret = h["Close"].iloc[-1] / h["Close"].iloc[-2] - 1
                    if ret > 0:
                        subiendo += 1
                    total += 1
            except:
                continue

        if total == 0:
            return 50, "N/D"

        pct = subiendo / total * 100
        score = np.clip(pct, 5, 95)
        return round(score), round(pct, 1)
    except:
        return 50, "N/D"

def _score_sentiment_noticias():
    """
    Ratio noticias positivas vs negativas (últimas 24h)
    """
    try:
        from data.noticias_chile import get_noticias_google
        from engine.nlp_sentiment import analizar_noticias_batch, get_resumen_sentiment

        noticias = get_noticias_google()
        if not noticias:
            return 50, "N/D"

        noticias_sent = analizar_noticias_batch(noticias[:20])
        resumen       = get_resumen_sentiment(noticias_sent)
        ratio         = resumen.get("ratio_positivo", 50)
        score         = np.clip(ratio, 5, 95)
        return round(score), f"{ratio:.0f}% positivas"
    except:
        return 50, "N/D"

def _score_spread_btc():
    """
    BTC local más caro que global = dinero fluyendo a Chile = apetito por riesgo
    BTC local más barato = capital saliendo = miedo
    """
    try:
        r = requests.get("https://www.buda.com/api/v2/markets/BTC-CLP/ticker", timeout=8)
        btc_local = float(r.json()["ticker"]["last_price"][0])

        h = yf.Ticker("BTC-USD").history(period="2d")
        if h.empty:
            return 50, "N/D"
        btc_usd = float(h["Close"].iloc[-1])

        h_fx = yf.Ticker("CLP=X").history(period="2d")
        clp_usd = float(h_fx["Close"].iloc[-1]) if not h_fx.empty else 890

        btc_global_clp = btc_usd * clp_usd
        spread_pct     = (btc_local / btc_global_clp - 1) * 100

        # Spread positivo = BTC local más caro = apetito por riesgo en Chile
        score = 50 + np.clip(spread_pct * 10, -40, 40)
        return round(score), f"{spread_pct:+.2f}%"
    except:
        return 50, "N/D"

def _score_cobre():
    """
    Momentum del cobre (5 días)
    Cobre subiendo = optimismo para Chile
    """
    try:
        h = yf.Ticker("HG=F").history(period="10d")
        if len(h) < 5:
            return 50, "N/D"
        ret_5d = (h["Close"].iloc[-1] / h["Close"].iloc[-5] - 1) * 100
        score  = 50 + np.clip(ret_5d * 8, -40, 40)
        return round(score), f"{ret_5d:+.2f}%"
    except:
        return 50, "N/D"

# ── CALCULAR ÍNDICE ───────────────────────────────────────────────────────────
def calcular_fear_greed():
    # Cache 30 minutos
    cached = cache_get("fear_greed", max_age_min=30)
    if cached:
        return cached

    """
    Calcula el Fear & Greed Index Chile.
    Retorna dict con score, clasificación y detalle de componentes.
    """
    componentes = {}

    score_vix,       val_vix      = _score_vix()
    score_mom,       val_mom      = _score_momentum_ipsa()
    score_amp,       val_amp      = _score_amplitud()
    score_sent,      val_sent     = _score_sentiment_noticias()
    score_btc,       val_btc      = _score_spread_btc()
    score_cobre,     val_cobre    = _score_cobre()

    componentes = {
        "vix":           {"score": score_vix,   "valor": val_vix,    "peso": PESOS["vix"],           "nombre": "VIX (Miedo global)"},
        "momentum_ipsa": {"score": score_mom,   "valor": val_mom,    "peso": PESOS["momentum_ipsa"], "nombre": "Momentum IPSA"},
        "amplitud":      {"score": score_amp,   "valor": val_amp,    "peso": PESOS["amplitud"],      "nombre": "Amplitud mercado"},
        "sentiment":     {"score": score_sent,  "valor": val_sent,   "peso": PESOS["sentiment"],     "nombre": "Sentiment noticias"},
        "spread_btc":    {"score": score_btc,   "valor": val_btc,    "peso": PESOS["spread_btc"],    "nombre": "Spread BTC local"},
        "cobre":         {"score": score_cobre, "valor": val_cobre,  "peso": PESOS["cobre"],         "nombre": "Momentum cobre"},
    }

    # Score ponderado final
    score_final = sum(
        c["score"] * c["peso"]
        for c in componentes.values()
    )
    score_final = round(np.clip(score_final, 0, 100))

    # Clasificación
    if score_final <= 25:
        clasificacion = "MIEDO EXTREMO"
        color         = "#ef4444"
        señal_trading = "COMPRAR"
        descripcion   = "Mercado en pánico — oportunidad contrarian de compra"
    elif score_final <= 45:
        clasificacion = "MIEDO"
        color         = "#f97316"
        señal_trading = "COMPRAR"
        descripcion   = "Pesimismo predominante — considerar posiciones largas"
    elif score_final <= 55:
        clasificacion = "NEUTRO"
        color         = "#f59e0b"
        señal_trading = "NEUTRO"
        descripcion   = "Sin sesgo claro — seguir señales individuales"
    elif score_final <= 75:
        clasificacion = "CODICIA"
        color         = "#22c55e"
        señal_trading = "VENDER"
        descripcion   = "Optimismo elevado — reducir exposición gradualmente"
    else:
        clasificacion = "CODICIA EXTREMA"
        color         = "#16a34a"
        señal_trading = "VENDER"
        descripcion   = "Euforia de mercado — señal contrarian de venta"

    # Multiplicador para el motor automático
    if score_final <= 25:
        multiplicador_señales = 1.3   # +30% peso a señales de compra
    elif score_final <= 45:
        multiplicador_señales = 1.15
    elif score_final <= 55:
        multiplicador_señales = 1.0
    elif score_final <= 75:
        multiplicador_señales = 0.85
    else:
        multiplicador_señales = 0.7   # -30% peso a señales de compra

    resultado = {
        "timestamp":           datetime.now().isoformat(),
        "score":               score_final,
        "clasificacion":       clasificacion,
        "color":               color,
        "señal_trading":       señal_trading,
        "descripcion":         descripcion,
        "multiplicador":       multiplicador_señales,
        "componentes":         componentes,
    }
    cache_set("fear_greed", resultado)
    return resultado

def get_fear_greed_simple():
    """Versión rápida para el header del dashboard"""
    try:
        resultado = calcular_fear_greed()
        return resultado["score"], resultado["clasificacion"], resultado["color"]
    except:
        return 50, "NEUTRO", "#f59e0b"

if __name__ == "__main__":
    print("=== FEAR & GREED INDEX CHILE ===\n")
    resultado = calcular_fear_greed()

    print(f"SCORE: {resultado['score']}/100")
    print(f"ESTADO: {resultado['clasificacion']}")
    print(f"SEÑAL: {resultado['señal_trading']}")
    print(f"CONTEXTO: {resultado['descripcion']}")
    print(f"MULTIPLICADOR: {resultado['multiplicador']}x")
    print("\nCOMPONENTES:")
    for key, c in resultado["componentes"].items():
        bar = "█" * (c["score"] // 10)
        print(f"  {c['nombre']:<25} {bar:<10} {c['score']:3d}/100  [{c['valor']}]  peso {c['peso']*100:.0f}%")
