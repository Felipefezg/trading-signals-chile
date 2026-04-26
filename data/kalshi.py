import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {"Accept": "application/json"}

# Series de Kalshi relevantes para Chile y macro global
SERIES_RELEVANTES = {
    "KXFED": {"nombre": "Fed Rate", "impacto": ["CLP/USD", "ECH", "COPEC.SN"], "peso": 5},
    "KXCPI": {"nombre": "CPI USA", "impacto": ["CLP/USD", "ECH"], "peso": 4},
    "KXGDP": {"nombre": "GDP USA", "impacto": ["ECH", "SQM.SN", "COPEC.SN"], "peso": 4},
    "KXBTC": {"nombre": "Bitcoin", "impacto": ["BTC_LOCAL_SPREAD"], "peso": 3},
    "KXUNEMP": {"nombre": "Desempleo USA", "impacto": ["CLP/USD", "ECH"], "peso": 3},
}

def get_mercados_kalshi(series_ticker, limit=5):
    """Obtiene mercados de una serie específica de Kalshi"""
    try:
        r = requests.get(
            f"{BASE_URL}/markets",
            params={"limit": limit, "status": "open", "series_ticker": series_ticker},
            headers=HEADERS,
            timeout=10
        )
        if r.status_code != 200:
            return []
        data = r.json()
        mercados = []
        for m in data.get("markets", []):
            # Precio: usar last_price_dollars o yes_ask_dollars
            precio_raw = m.get("last_price_dollars") or m.get("yes_ask_dollars") or "0"
            try:
                prob = round(float(precio_raw) * 100, 1)
            except:
                prob = None

            mercados.append({
                "ticker": m.get("ticker", ""),
                "titulo": m.get("title", ""),
                "prob_pct": prob,
                "yes_ask": m.get("yes_ask_dollars"),
                "no_bid": m.get("no_bid_dollars"),
                "volumen": m.get("volume_fp", 0),
                "cierre": m.get("close_time", "")[:10],
                "serie": series_ticker,
            })
        return mercados
    except Exception as e:
        print(f"Error Kalshi [{series_ticker}]: {e}")
        return []

def get_kalshi_macro():
    """Obtiene señales macro de Kalshi para triangular con Polymarket"""
    resultado = []
    for serie, meta in SERIES_RELEVANTES.items():
        mercados = get_mercados_kalshi(serie, limit=3)
        for m in mercados:
            if m["prob_pct"] is None:
                continue
            prob = m["prob_pct"]
            # Calcular score: distancia al 50% × peso de la serie
            distancia = abs(prob - 50)
            score = round(distancia * meta["peso"] / 10, 2)
            direccion = "ALZA" if prob > 50 else "BAJA"

            resultado.append({
                "fuente": "Kalshi",
                "serie": meta["nombre"],
                "titulo": m["titulo"],
                "ticker": m["ticker"],
                "prob_pct": prob,
                "direccion": direccion,
                "activos_impacto": meta["impacto"],
                "score": score,
                "cierre": m["cierre"],
                "volumen": m["volumen"],
            })

    return sorted(resultado, key=lambda x: x["score"], reverse=True)

def get_kalshi_resumen():
    """Retorna dict con señales clave para mostrar en dashboard"""
    señales = get_kalshi_macro()
    return señales[:10]

if __name__ == "__main__":
    print("=== KALSHI MACRO ===")
    señales = get_kalshi_resumen()
    for s in señales:
        print(f"[Score:{s['score']}] [{s['serie']}] {s['prob_pct']}% {s['direccion']}")
        print(f"  {s['titulo'][:80]}")
        print(f"  Impacto: {', '.join(s['activos_impacto'])}")
        print()
