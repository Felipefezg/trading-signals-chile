#!/usr/bin/env python3
"""
Script standalone para el ciclo automático de trading.
Ejecutado por cron cada 15 minutos.
Independiente del dashboard Streamlit.
"""

import sys
import os
import logging
from datetime import datetime

# Agregar directorio del proyecto al path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Logging
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "trading_auto.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def main():
    logging.info("=== CICLO AUTOMÁTICO INICIADO ===")
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando ciclo automático...")

    try:
        from engine.motor_automatico import ciclo_trading_automatico, get_resumen_motor, es_horario_mercado

        # Verificar estado del motor
        resumen = get_resumen_motor()

        if not resumen.get("activo"):
            print("Motor INACTIVO — sin acción")
            logging.info("Motor inactivo — ciclo omitido")
            return

        if resumen.get("pausado"):
            print(f"Motor PAUSADO — {resumen.get('razon_pausa')}")
            logging.info(f"Motor pausado: {resumen.get('razon_pausa')}")
            return

        # Verificar horario
        en_horario, msg = es_horario_mercado()
        print(f"Horario: {msg}")

        if not en_horario:
            # Fuera de horario — solo verificar SL/TP/Trailing
            logging.info(f"Fuera de horario: {msg} — solo verificando posiciones")
            from engine.cierre_automatico import verificar_posiciones
            from engine.trailing_stop import verificar_trailing_stops

            # Trailing stops
            resumen_trail = verificar_trailing_stops()
            if resumen_trail.get("cierres"):
                for c in resumen_trail["cierres"]:
                    print(f"TRAILING STOP: {c['ticker']} | PnL {c['pnl_pct']:+.2f}%")
                    logging.info(f"Trailing stop: {c['ticker']} PnL {c['pnl_pct']:+.2f}%")

            # Guardar señales AT en DB (disponible 24/7)
            try:
                import pandas as pd
                from engine.analisis_tecnico import get_señales_tecnicas
                from data.historial import guardar_senales
                at = get_señales_tecnicas(min_conviccion=70)
                rows_at = [{
                    'Señal': f"{a['accion']} {a['nombre']}: {', '.join(s['descripcion'] for s in a['señales'][:2])}",
                    'Prob %': a['conviccion'],
                    'Dirección': a['accion'],
                    'Activos Chile': a['activo_motor'],
                    'Score': a['conviccion'] / 10,
                    'Tesis': f"{a['accion']} {a['nombre']} — RSI:{a['indicadores']['rsi']:.1f} %B:{a['indicadores']['pct_b']:.2f}",
                } for a in at]
                if rows_at:
                    nuevas = guardar_senales(pd.DataFrame(rows_at))
                    print(f"Señales AT guardadas: {nuevas}")
            except Exception as e:
                print(f"Error AT DB: {e}")

            # SL/TP
            resumen_cierre = verificar_posiciones(modo_test=False, auto_cerrar=True)
            for c in resumen_cierre.get("cierres", []):
                print(f"CIERRE: {c['ticker']} | {c['razon']} | PnL {c['pnl_pct']:+.2f}%")
                logging.info(f"Cierre: {c['ticker']} {c['razon']} PnL {c['pnl_pct']:+.2f}%")

            # Mostrar estado posiciones
            for p in resumen_cierre.get("ok", []):
                print(f"Posición: {p['ticker']} | precio {p['precio']:,.2f} | PnL {p['pnl_pct']:+.2f}%")
            return

        # En horario — ejecutar ciclo completo
        print("Ejecutando ciclo completo...")

        # Generar señales — carga paralela
        try:
            from engine.data_loader import get_datos_para_motor
            from engine.recomendaciones import consolidar_señales, generar_recomendaciones
            from data.historial import guardar_senales
            import time
            t0 = time.time()
            datos = get_datos_para_motor(verbose=False)
            print(f"Datos cargados en {datos['meta']['t_total']}s")
            activos = consolidar_señales(
                datos["poly_df"], datos["kalshi_list"],
                datos["macro_corr"], datos["noticias"],
                fear_greed=datos["fear_greed"],
                cmf_hechos=datos["cmf_hechos"],
                vol_alertas=datos["vol_alertas"],
                put_call=datos["put_call"],
                analisis_tecnico=datos["analisis_tecnico"],
                google_trends=datos["google_trends"],
                ib_data=datos["ib_data"],
            )
            recomendaciones = generar_recomendaciones(activos)

            # Guardar en DB — convertir a DataFrame
            import pandas as pd
            señales_para_guardar = [
                {
                    "Señal":     r["tesis"][:100],
                    "Prob %":    r["conviccion"],
                    "Dirección": r["accion"],
                    "Activos Chile": r["ib_ticker"],
                    "Score":     r["score"],
                    "Tesis":     r["tesis"],
                }
                for r in recomendaciones if r["conviccion"] >= 70
            ]
            if señales_para_guardar:
                df_señales = pd.DataFrame(señales_para_guardar)
                guardar_senales(df_señales)
                print(f"Señales guardadas en DB: {len(señales_para_guardar)}")
            else:
                print("Sin señales con convicción >= 70% para guardar")
        except Exception as e:
            print(f"Error guardando señales: {e}")
            logging.error(f"Error guardando señales: {e}")

        resultado = ciclo_trading_automatico()

        # Reportar resultados
        aperturas  = resultado.get("aperturas", [])
        cierres    = resultado.get("cierres", [])
        rechazadas = resultado.get("rechazadas", [])
        pausas     = resultado.get("pausas", [])

        if pausas:
            print(f"⚠️  MOTOR PAUSADO: {pausas[0]}")

        if aperturas:
            print(f"✅ {len(aperturas)} apertura(s):")
            for a in aperturas:
                print(f"   {a['accion']} {a['ticker']} | Conv: {a['conviccion']}%")

        if cierres:
            print(f"🔒 {len(cierres)} cierre(s):")
            for c in cierres:
                print(f"   {c['ticker']} | {c['razon']} | PnL {c['pnl_pct']:+.2f}%")

        if rechazadas:
            print(f"❌ {len(rechazadas)} señal(es) rechazada(s):")
            for r in rechazadas[:3]:
                print(f"   {r['ticker']}: {r['razon']}")

        if not aperturas and not cierres:
            print("Sin operaciones en este ciclo — condiciones no cumplidas")

        logging.info(
            f"Ciclo completado: {len(aperturas)} aperturas, "
            f"{len(cierres)} cierres, {len(rechazadas)} rechazadas"
        )

    except Exception as e:
        print(f"ERROR en ciclo: {e}")
        logging.error(f"Error en ciclo automático: {e}", exc_info=True)

if __name__ == "__main__":
    main()
