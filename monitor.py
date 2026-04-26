import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.polymarket import get_mercados_chile
from data.bcch import get_resumen_bcch
from data.buda import get_spread_btc
from engine.divergence import calcular_divergencias
from alerts.telegram import enviar, alerta_divergencia, alerta_spread_btc, alerta_resumen_diario

# =============================================================
# CONFIGURACION
# =============================================================
INTERVALO_MINUTOS  = 15       # chequea cada 15 minutos
SCORE_MINIMO       = 8.0      # solo alerta si score supera este umbral
SPREAD_BTC_MINIMO  = 1.5      # % minimo para alerta BTC

# Memoria de señales ya alertadas (evita repetir)
senales_alertadas  = set()

def chequear_señales():
    print(f"\n[{time.strftime('%H:%M:%S')}] Chequeando señales...")

    # Datos frescos
    bcch       = get_resumen_bcch()
    clp        = bcch.get("CLP/USD", 892.0)
    spread     = get_spread_btc(clp or 892.0)
    df_poly    = get_mercados_chile(limit=200)
    df_div     = calcular_divergencias(df_poly, spread)

    alertas_enviadas = 0

    # Chequear divergencias
    if not df_div.empty:
        for _, row in df_div.iterrows():
            score  = row.get("Score", 0)
            señal  = row.get("Señal", row.get("Senal", ""))
            key    = f"{señal}_{round(score, 0)}"

            if score >= SCORE_MINIMO and key not in senales_alertadas:
                print(f"  ALERTA: {señal[:60]} — Score {score}")
                alerta_divergencia(row)
                senales_alertadas.add(key)
                alertas_enviadas += 1
                time.sleep(1)

    # Chequear spread BTC
    if spread and abs(spread.get("spread_pct", 0)) >= SPREAD_BTC_MINIMO:
        spread_key = f"btc_{round(spread['spread_pct'], 1)}"
        if spread_key not in senales_alertadas:
            print(f"  ALERTA BTC: spread {spread['spread_pct']}%")
            alerta_spread_btc(spread)
            senales_alertadas.add(spread_key)
            alertas_enviadas += 1

    if alertas_enviadas == 0:
        print(f"  Sin señales nuevas sobre umbral {SCORE_MINIMO}")

    return df_div, bcch, spread

def main():
    print("=" * 50)
    print("TRADING SIGNALS MONITOR — Iniciando")
    print(f"Intervalo: {INTERVALO_MINUTOS} min | Score minimo: {SCORE_MINIMO}")
    print("=" * 50)

    enviar("Monitor Trading Signals iniciado.\nIntervalo: {} min | Score minimo: {}".format(
        INTERVALO_MINUTOS, SCORE_MINIMO
    ))

    ciclo = 0
    while True:
        ciclo += 1
        df_div, bcch, spread = chequear_señales()

        # Resumen diario cada 48 ciclos (aprox 12 horas con intervalo 15 min)
        if ciclo % 48 == 0:
            print("  Enviando resumen diario...")
            alerta_resumen_diario(df_div, bcch, spread)

        print(f"  Próximo chequeo en {INTERVALO_MINUTOS} minutos...")
        time.sleep(INTERVALO_MINUTOS * 60)

if __name__ == "__main__":
    main()