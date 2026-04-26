
import yfinance as yf
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import USA_TICKERS, CHILE_TICKERS

def get_precios_actuales(tickers):
    resultados = []
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if hist.empty or len(hist) < 1:
                continue
            precio_actual = hist["Close"].iloc[-1]
            precio_ayer   = hist["Close"].iloc[-2] if len(hist) > 1 else precio_actual
            cambio_pct    = ((precio_actual - precio_ayer) / precio_ayer) * 100
            resultados.append({
                "ticker":     ticker,
                "precio":     round(precio_actual, 2),
                "cambio_pct": round(cambio_pct, 2),
                "volumen":    int(hist["Volume"].iloc[-1]),
                "timestamp":  datetime.now().strftime("%H:%M:%S"),
            })
        except Exception as e:
            print(f"  Error {ticker}: {e}")
    return pd.DataFrame(resultados)

def get_precios_usa():
    return get_precios_actuales(USA_TICKERS)

def get_precios_chile():
    df = get_precios_actuales(list(CHILE_TICKERS.keys()))
    if not df.empty:
        df["descripcion"] = df["ticker"].map(CHILE_TICKERS)
    return df

if __name__ == "__main__":
    print("=== PRECIOS USA ===")
    print(get_precios_usa().to_string(index=False))
    print("\n=== PRECIOS CHILE ===")
    print(get_precios_chile().to_string(index=False))
