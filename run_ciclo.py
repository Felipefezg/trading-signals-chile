#!/usr/bin/env python3
"""
Script standalone para el ciclo automático de trading.
Ejecutado por cron cada 15 minutos.
Independiente del dashboard Streamlit.
"""

import sys
import os
import fcntl
import errno
import logging
from contextlib import contextmanager
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

# ── LOCKFILE (compartido con trigger.py) ──────────────────────────────────────
LOCKFILE = "/tmp/trading_motor.lock"

@contextmanager
def _ciclo_lock():
    """Exclusión mutua por ciclo. Lanza IOError si el lock ya está tomado."""
    fd = open(LOCKFILE, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(f"{os.getpid()}\n")
        fd.flush()
        yield
    except IOError as e:
        fd.close()
        if e.errno in (errno.EACCES, errno.EAGAIN):
            raise RuntimeError("Ciclo ya en ejecución — lockfile activo (trigger.py corriendo)")
        raise
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except Exception:
            pass

def enviar_revision_semanal():
    """Envía reporte de revisión los lunes a las 9:00 AM ET"""
    import pytz
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    if now.weekday() == 0 and now.hour == 9 and now.minute < 5:
        try:
            from engine.revision_mejora import generar_reporte_revision, enviar_reporte_telegram
            reporte = generar_reporte_revision()
            enviar_reporte_telegram(reporte)
            logging.info("Reporte semanal enviado")
        except Exception as e:
            logging.error(f"Error reporte semanal: {e}")

def enviar_resumen_si_corresponde():
    """Envía resumen diario a las 9:00 AM y 4:00 PM ET"""
    import pytz
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    hora = now.hour
    min  = now.minute
    if (hora == 9 and min < 5) or (hora == 16 and min < 5):
        try:
            from engine.telegram_alertas import alerta_resumen_diario
            alerta_resumen_diario()
        except Exception as e:
            logging.error(f"Error resumen Telegram: {e}")

def main():
    logging.info("=== CICLO AUTOMÁTICO INICIADO ===")
    enviar_resumen_si_corresponde()
    enviar_revision_semanal()

    # ── LOCKFILE: abortar si trigger.py ya tiene un ciclo en curso ────────────
    try:
        lock_ctx = _ciclo_lock()
        lock_ctx.__enter__()
    except RuntimeError as e:
        logging.warning(str(e))
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏭  {e} — abortando run_ciclo")
        return

    try:
        _run_main_logic()
    finally:
        try:
            lock_ctx.__exit__(None, None, None)
        except Exception:
            pass


def _run_main_logic():
    """Lógica principal de main() — separada para usar con lockfile."""
    # Sincronizar con IB cada ciclo
    try:
        from engine.ib_sync import sincronizar_posiciones_local
        sincronizar_posiciones_local()
    except Exception as e:
        logging.error(f"Error sync IB: {e}")
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
        en_horario, msg = es_horario_mercado()  # Default NYSE
        print(f"Horario: {msg}")

        if not en_horario:
            # Fuera de horario NYSE.
            # Crypto opera 24/7 y se maneja dentro de ciclo_trading_automatico()
            # vía es_horario_mercado(tipo_activo="Crypto") → siempre True.
            # NO ejecutar señales aquí directamente para no saltarse
            # validaciones de riesgo, posiciones máximas y deduplicación.

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
                mercado_local=datos.get("mercado_local"),
                renta_fija=datos.get("renta_fija"),
                mtf=datos.get("mtf"),
                sec_13f=datos.get("sec_13f"),
                order_flow=datos.get("order_flow"),
                correlaciones=datos.get("correlaciones"),
                iv_opciones=datos.get("iv_opciones"),
                ml=datos.get("ml"),
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
        import traceback
        traceback.print_exc()
        print(f"ERROR en ciclo: {e}")
        logging.error(f"Error en ciclo automático: {e}", exc_info=True)

if __name__ == "__main__":
    main()
