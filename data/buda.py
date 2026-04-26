
import requests
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BUDA_API, COINGECKO_API, SPREAD_THRESHOLD

def get_btc_local():
    try:
        r = requests.get(f"{BUDA_API}/markets/btc-clp/ticker", timeout=10)
        r.raise_for_status()
        return float(r.json()["ticker"]["last_price"][0])
    except Exception as e:
        print(f"Error Buda: {e}")
        return None

def get_btc_usd():
    try:
        r = requests.get(f"{COINGECKO_API}/simple/price", params={"ids":"bitcoin","vs_currencies":"usd"}, timeout=10)
        r.raise_for_status()
        return float(r.json()["bitcoin"]["usd"])
    except Exception as e:
        print(f"Error CoinGecko: {e}")
        return None

def get_spread_btc(clp_usd):
    btc_local = get_btc_local()
    btc_usd   = get_btc_usd()
    if not btc_local or not btc_usd or not clp_usd:
        return {}
    btc_global = btc_usd * clp_usd
    spread_pct = ((btc_local - btc_global) / btc_global) * 100
    return {
        "btc_local_clp":  round(btc_local, 0),
        "btc_usd":        round(btc_usd, 0),
        "btc_global_clp": round(btc_global, 0),
        "spread_pct":     round(spread_pct, 2),
        "alerta":         abs(spread_pct) >= SPREAD_THRESHOLD,
        "direccion":      "LOCAL CARO" if spread_pct > 0 else "LOCAL BARATO",
        "timestamp":      datetime.now().strftime("%H:%M:%S"),
    }

if __name__ == "__main__":
    print("=== SPREAD BTC LOCAL vs GLOBAL ===")
    for k, v in get_spread_btc(930.0).items():
        print(f"  {k}: {v}")
