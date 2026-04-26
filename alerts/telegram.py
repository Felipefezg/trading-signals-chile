import requests
from datetime import datetime

TOKEN   = "8648892135:AAHairDr4kx1IuRWkI0CL9FgKG6Sx_g_YlA"
CHAT_ID = "8481235797"

def enviar(texto):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r   = requests.post(url, data={"chat_id": CHAT_ID, "text": texto, "parse_mode": "Markdown"}, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def alerta_divergencia(row):
    texto = (
        "*SENAL TRADING - Score {}*\n\n"
        "Senal: *{}*\n"
        "Probabilidad: *{}%* | {}\n"
        "Activos Chile: *{}*\n\n"
        "Tesis: {}\n\n"
        "Hora: {}"
    ).format(
        row.get("Score", 0),
        row.get("Senal", row.get("Señal", "")),
        row.get("Prob %", 0),
        row.get("Direccion", row.get("Dirección", "")),
        row.get("Activos Chile", ""),
        row.get("Tesis", ""),
        datetime.now().strftime("%d/%m/%Y %H:%M")
    )
    return enviar(texto)

def alerta_spread_btc(spread):
    texto = (
        "ALERTA SPREAD BTC\n\n"
        "BTC {}: {:.2f}% vs precio global\n\n"
        "Local Buda: ${:,.0f} CLP\n"
        "Global: ${:,.0f} CLP\n"
        "BTC/USD: ${:,.0f}\n\n"
        "Ventana de arbitraje activa\n"
        "Hora: {}"
    ).format(
        spread.get("direccion", ""),
        abs(spread.get("spread_pct", 0)),
        spread.get("btc_local_clp", 0),
        spread.get("btc_global_clp", 0),
        spread.get("btc_usd", 0),
        datetime.now().strftime("%d/%m/%Y %H:%M")
    )
    return enviar(texto)

def alerta_resumen_diario(df_div, bcch, spread):
    clp     = bcch.get("CLP/USD", "N/D")
    tpm     = bcch.get("TPM_%", "N/D")
    senales = ""
    if df_div is not None and not df_div.empty:
        for i, row in df_div.head(3).iterrows():
            senales += "  {}. {} - Score {}\n".format(
                i + 1,
                str(row.get("Senal", row.get("Señal", "")))[:50],
                row.get("Score", 0)
            )
    spread_txt = ""
    if spread:
        spread_txt = "\nSpread BTC: {:.2f}% ({})".format(
            spread.get("spread_pct", 0),
            "ALERTA" if spread.get("alerta") else "Normal"
        )
    texto = (
        "RESUMEN DIARIO - Trading Signals\n\n"
        "CLP/USD: {} | TPM: {}%\n\n"
        "Top Senales:\n{}"
        "{}\n\n"
        "Hora: {}"
    ).format(
        clp, tpm, senales, spread_txt,
        datetime.now().strftime("%d/%m/%Y %H:%M")
    )
    return enviar(texto)

if __name__ == "__main__":
    print("Probando Telegram...")
    ok = enviar("Trading Signals Chile conectado correctamente.")
    print("Mensaje enviado OK" if ok else "ERROR al enviar")