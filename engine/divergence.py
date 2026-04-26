import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RELEVANCIA_MULTIPLIER, SPREAD_THRESHOLD

def calcular_score(prob, volumen, relevancia):
    dist_50 = abs(prob - 50)
    try:
        vol_score = min(float(volumen or 0) / 3_000_000, 3.0)
    except:
        vol_score = 0
    multiplicador    = RELEVANCIA_MULTIPLIER.get(relevancia, 1.0)
    relevancia_bonus = relevancia * 1.5
    score = round((((dist_50 / 10) + vol_score) * multiplicador) + relevancia_bonus, 2)
    return score

def generar_tesis(pregunta, prob, activos, direccion):
    pregunta_lower = pregunta.lower()
    activos_str    = ", ".join(activos)

    if "taiwan" in pregunta_lower or "invade" in pregunta_lower:
        return (f"Conflicto China/Taiwan ({prob}% prob) implica interrupción supply chain global, "
                f"caída demanda cobre, presión sobre {activos_str}. "
                f"Posición defensiva recomendada si prob supera 60%.")
    if "recession" in pregunta_lower:
        return (f"Recesión USA ({prob}% prob) reduce demanda commodities, "
                f"presiona CLP por flight-to-quality hacia USD. "
                f"Activos afectados: {activos_str}.")
    if any(x in pregunta_lower for x in ["rate cut","rate hike","fomc","fed rate","federal reserve"]):
        if prob > 50:
            return (f"Alta probabilidad ({prob}%) de cambio Fed implica "
                    f"movimiento en tasas locales y CLP. Monitorear {activos_str}.")
        else:
            return (f"Baja probabilidad ({prob}%) de cambio Fed. "
                    f"Mercado descuenta estabilidad. Neutral en {activos_str}.")
    if any(x in pregunta_lower for x in ["copper","lithium"]):
        return (f"Señal directa en commodities chilenos ({prob}% prob). "
                f"Impacto inmediato en {activos_str}. Alta prioridad.")
    if any(x in pregunta_lower for x in ["bitcoin","btc","crypto"]):
        return (f"Señal cripto ({prob}% prob): monitorear spread BTC "
                f"local vs global en Buda.com. Buscar divergencia >1.5%.")
    if any(x in pregunta_lower for x in ["tariff","trade war","sanction"]):
        return (f"Riesgo comercial ({prob}% prob) afecta exportaciones chilenas. "
                f"Presión sobre {activos_str}.")
    if any(x in pregunta_lower for x in ["world war","nuclear","ukraine"]):
        return (f"Riesgo geopolítico ({prob}% prob) genera flight-to-quality, "
                f"presión sobre activos emergentes: {activos_str}.")
    if "russia" in pregunta_lower or "putin" in pregunta_lower:
        return (f"Geopolítica rusa ({prob}% prob): impacto secundario vía precio "
                f"petróleo y riesgo emergente. Monitorear {activos_str}.")
    if "argentina" in pregunta_lower:
        return (f"Evento Argentina ({prob}% prob): posible contagio regional "
                f"sobre CLP y ECH si hay turbulencia económica.")
    return (f"Señal Polymarket ({prob}% prob) implica presión {direccion} "
            f"sobre {activos_str} vía canales macro internacionales.")

def calcular_divergencias(df_polymarket, spread_btc=None):
    divergencias = []

    if df_polymarket is not None and not df_polymarket.empty:
        for _, row in df_polymarket.iterrows():
            prob       = row.get("probabilidad")
            impactos   = row.get("chile_impact", [])
            volumen    = row.get("volumen_usd", 0)
            relevancia = row.get("relevancia", 1)

            if prob is None or not impactos:
                continue

            score     = calcular_score(prob, volumen, relevancia)
            direccion = "📈 ALZA" if prob > 50 else "📉 BAJA"
            tesis     = generar_tesis(row.get("pregunta",""), prob, impactos, direccion)

            divergencias.append({
                "Señal":         row["pregunta"][:75],
                "Prob %":        prob,
                "Dirección":     direccion,
                "Activos Chile": ", ".join(impactos),
                "Relevancia":    relevancia,
                "Score":         score,
                "Volumen USD":   volumen,
                "Tesis":         tesis,
                "URL":           row.get("url",""),
            })

    if spread_btc and spread_btc.get("alerta"):
        spread_pct = spread_btc.get("spread_pct", 0)
        divergencias.append({
            "Señal":         f"BTC {spread_btc['direccion']} en mercado local chileno",
            "Prob %":        round(abs(spread_pct), 1),
            "Dirección":     "📉 BAJA local" if spread_pct < 0 else "📈 ALZA local",
            "Activos Chile": "BTC/CLP (Buda.com)",
            "Relevancia":    3,
            "Score":         round(abs(spread_pct) * 2, 2),
            "Volumen USD":   "N/A",
            "Tesis":         (f"Arbitraje: BTC cuesta {abs(spread_pct):.1f}% "
                             f"{'menos' if spread_pct < 0 else 'más'} en Buda vs mercado global. "
                             f"Ventana de arbitraje activa."),
            "URL":           "https://www.buda.com",
        })

    if not divergencias:
        return pd.DataFrame()

    df = pd.DataFrame(divergencias)
    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    return df