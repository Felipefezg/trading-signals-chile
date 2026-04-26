POLYMARKET_API = "https://gamma-api.polymarket.com"
BUDA_API       = "https://www.buda.com/api/v2"
COINGECKO_API  = "https://api.coingecko.com/api/v3"

USA_TICKERS = ["SPY", "QQQ", "TLT", "GLD", "BTC-USD", "ETH-USD"]

CHILE_TICKERS = {
    "ECH":           "ETF Chile (NYSE)",
    "SQM":           "SQM ADR (NYSE)",
    "COPEC.SN":      "Copec (Bolsa Stgo)",
    "BSANTANDER.SN": "Banco Santander CL",
    "CHILE.SN":      "Banco de Chile",
}

POLYMARKET_CHILE_MAP = {
    # Fed / Tasas
    "federal reserve":   {"activos": ["ECH","CHILE.SN","BSANTANDER.SN","CLP/USD"], "relevancia": 5},
    "fed rate":          {"activos": ["ECH","CHILE.SN","BSANTANDER.SN","CLP/USD"], "relevancia": 5},
    "rate cut":          {"activos": ["ECH","CHILE.SN","BSANTANDER.SN","CLP/USD"], "relevancia": 5},
    "rate hike":         {"activos": ["ECH","CHILE.SN","BSANTANDER.SN","CLP/USD"], "relevancia": 5},
    "fomc":              {"activos": ["ECH","CHILE.SN","BSANTANDER.SN","CLP/USD"], "relevancia": 5},
    "interest rate":     {"activos": ["ECH","CHILE.SN","BSANTANDER.SN","CLP/USD"], "relevancia": 4},
    # Recesion
    "recession":         {"activos": ["ECH","SQM","COPEC.SN","CLP/USD"],           "relevancia": 5},
    "us economy":        {"activos": ["ECH","SQM","CLP/USD"],                      "relevancia": 3},
    "gdp growth":        {"activos": ["ECH","SQM","CLP/USD"],                      "relevancia": 3},
    # China y geopolitica Asia
    "china gdp":         {"activos": ["SQM","ECH","CLP/USD"],                      "relevancia": 4},
    "china economy":     {"activos": ["SQM","ECH","CLP/USD"],                      "relevancia": 4},
    "taiwan":            {"activos": ["SQM","ECH","CLP/USD","COPEC.SN"],           "relevancia": 5},
    "invade taiwan":     {"activos": ["SQM","ECH","CLP/USD","COPEC.SN"],           "relevancia": 5},
    # Commodities
    "copper":            {"activos": ["SQM","ECH","CLP/USD"],                      "relevancia": 5},
    "lithium":           {"activos": ["SQM","ECH"],                                "relevancia": 5},
    "commodity":         {"activos": ["SQM","ECH","COPEC.SN"],                     "relevancia": 3},
    # Petroleo frases exactas
    "oil price":         {"activos": ["COPEC.SN","ECH"],                           "relevancia": 4},
    "crude oil":         {"activos": ["COPEC.SN","ECH"],                           "relevancia": 4},
    "opec":              {"activos": ["COPEC.SN","ECH"],                           "relevancia": 4},
    "brent":             {"activos": ["COPEC.SN","ECH"],                           "relevancia": 3},
    # Cripto
    "bitcoin":           {"activos": ["BTC_LOCAL_SPREAD"],                         "relevancia": 3},
    "btc":               {"activos": ["BTC_LOCAL_SPREAD"],                         "relevancia": 3},
    "crypto":            {"activos": ["BTC_LOCAL_SPREAD"],                         "relevancia": 2},
    # Inflacion
    "inflation":         {"activos": ["ECH","CHILE.SN","CLP/USD"],                 "relevancia": 4},
    "cpi":               {"activos": ["ECH","CHILE.SN","CLP/USD"],                 "relevancia": 4},
    # Comercio y aranceles
    "tariff":            {"activos": ["ECH","SQM","CLP/USD"],                      "relevancia": 4},
    "trade war":         {"activos": ["ECH","SQM","CLP/USD"],                      "relevancia": 5},
    "trade deal":        {"activos": ["ECH","SQM","CLP/USD"],                      "relevancia": 3},
    "sanctions":         {"activos": ["ECH","SQM","CLP/USD"],                      "relevancia": 3},
    # Geopolitica frases exactas
    "world war":         {"activos": ["ECH","COPEC.SN","CLP/USD"],                 "relevancia": 5},
    "nuclear war":       {"activos": ["ECH","CLP/USD","SQM"],                      "relevancia": 5},
    "nuclear weapon":    {"activos": ["ECH","CLP/USD","SQM"],                      "relevancia": 5},
    "ukraine ceasefire": {"activos": ["COPEC.SN","ECH","CLP/USD"],                 "relevancia": 4},
    "russia":            {"activos": ["COPEC.SN","ECH","CLP/USD"],                 "relevancia": 2},
    # Emergentes y Chile
    "emerging market":   {"activos": ["ECH","CLP/USD"],                            "relevancia": 4},
    "latin america":     {"activos": ["ECH","CLP/USD"],                            "relevancia": 4},
    "argentina":         {"activos": ["ECH","CLP/USD"],                            "relevancia": 1},
    "dollar index":      {"activos": ["CLP/USD","ECH"],                            "relevancia": 3},
    "dxy":               {"activos": ["CLP/USD","ECH"],                            "relevancia": 4},
}

DIVERGENCE_THRESHOLD = 5.0
SPREAD_THRESHOLD     = 1.5

RELEVANCIA_MULTIPLIER = {5: 3.0, 4: 2.0, 3: 1.2, 2: 0.8, 1: 0.5}