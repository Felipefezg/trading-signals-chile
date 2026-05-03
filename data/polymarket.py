import requests
import pandas as pd
import json, os
from datetime import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import POLYMARKET_API, POLYMARKET_CHILE_MAP

def detectar_impacto_chile(texto):
    texto_lower = texto.lower()
    impactos    = []
    relevancia  = 0
    for frase, datos in POLYMARKET_CHILE_MAP.items():
        if frase in texto_lower:
            impactos.extend(datos["activos"])
            relevancia = max(relevancia, datos["relevancia"])
    return list(set(impactos)), relevancia

def get_active_markets(limit=100):
    try:
        url    = f"{POLYMARKET_API}/markets"
        params = {"active": "true", "closed": "false", "limit": limit}
        r      = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        markets = r.json()
        results = []
        for m in markets:
            outcomes = m.get("outcomes", "[]")
            prices   = m.get("outcomePrices", "[]")
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                    prices   = json.loads(prices)
                except:
                    outcomes, prices = [], []
            prob                 = round(float(prices[0]) * 100, 1) if prices else None
            question             = m.get("question", "")
            impactos, relevancia = detectar_impacto_chile(question)
            results.append({
                "pregunta":     question,
                "probabilidad": prob,
                "volumen_usd":  m.get("volume"),
                "liquidez_usd": m.get("liquidity"),
                "cierre":       m.get("endDate", "")[:10],
                "chile_impact": impactos,
                "relevancia":   relevancia,
                "url":          f"https://polymarket.com/event/{m.get('slug','')}",
            })
        df = pd.DataFrame(results)
        df = df.sort_values("volumen_usd", ascending=False).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error Polymarket: {e}")
        return pd.DataFrame()

# Palabras que indican horizonte indefinido o no financiero
EXCLUIR_PALABRAS = [
    "world cup", "fifa", "oscar", "grammy",
    "super bowl", "nba champion", "nfl", "marvel", "movie",
    "tv show", "song", "album", "celebrity",
    "arrested", "married", "divorced",
]

# Palabras que confirman relevancia financiera
INCLUIR_PALABRAS = [
    "rate", "fed", "gdp", "inflation", "recession", "copper",
    "lithium", "bitcoin", "btc", "oil", "gold", "tariff",
    "trade", "market", "economy", "stock", "yield", "dollar",
    "china gdp", "emerging", "fomc", "cpi", "treasury",
]

def get_mercados_chile(limit=200):
    df = get_active_markets(limit=limit)
    if df.empty:
        return df

    # Filtrar solo mercados con impacto Chile
    df = df[df["chile_impact"].apply(len) > 0].copy()

    # Excluir mercados no financieros
    def es_financiero(pregunta):
        texto = pregunta.lower()
        # Excluir si contiene palabras no financieras
        for palabra in EXCLUIR_PALABRAS:
            if palabra in texto:
                return False
        return True

    df = df[df["pregunta"].apply(es_financiero)].copy()

    # Filtrar por relevancia mínima
    df = df[df["relevancia"] >= 2].copy()  # mínimo relevancia 2

    # Filtrar por volumen mínimo (descartar mercados sin liquidez)
    if "volumen_usd" in df.columns:
        df = df[df["volumen_usd"].fillna(0) >= 1_000].copy()

    df = df.sort_values(
        ["relevancia", "volumen_usd"],
        ascending=[False, False]
    ).reset_index(drop=True)
    return df

if __name__ == "__main__":
    print("=== POLYMARKET — Mercados con impacto Chile ===")
    df = get_mercados_chile()
    if not df.empty:
        print(f"Total: {len(df)} mercados relevantes")
        print(df[["pregunta","probabilidad","relevancia","chile_impact"]].to_string())
    else:
        print("Sin resultados")