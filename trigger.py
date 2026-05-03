#!/usr/bin/env python3
"""
Trigger de ejecución inmediata.
Monitorea señales continuamente y ejecuta órdenes al instante
cuando detecta convicción >= umbral, sin esperar el cron.

Corre en background como proceso separado.
"""

import sys
import os
import time
import logging
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "trigger.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Configuración
CONVICCION_TRIGGER  = 85   # % mínimo para ejecución inmediata
INTERVALO_SCAN      = 60   # segundos entre scans (1 minuto)
MAX_ORDENES_DIA     = 10   # límite diario de órdenes automáticas
SEÑALES_EJECUTADAS  = set() # evitar duplicados en misma sesión

def es_horario_mercado():
    import pytz
    tz  = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    from datetime import time as dtime
    return dtime(9, 30) <= now.time() <= dtime(15, 45)

def get_ordenes_hoy():
    """Cuenta órdenes ejecutadas hoy"""
    try:
        import json
        log_path = os.path.join(BASE_DIR, "log_automatico.json")
        if not os.path.exists(log_path):
            return 0
        with open(log_path) as f:
            log = json.load(f)
        hoy = datetime.now().date().isoformat()
        return sum(1 for e in log
                  if e.get("tipo") == "APERTURA"
                  and e.get("timestamp", "")[:10] == hoy)
    except:
        return 0

def scan_y_ejecutar():
    """
    Escanea señales y ejecuta inmediatamente si hay alta convicción.
    Retorna número de órdenes ejecutadas.
    """
    if not es_horario_mercado():
        return 0

    ordenes_hoy = get_ordenes_hoy()
    if ordenes_hoy >= MAX_ORDENES_DIA:
        logging.info(f"Límite diario alcanzado: {ordenes_hoy} órdenes")
        return 0

    try:
        from engine.data_loader import get_datos_para_motor
        from engine.recomendaciones import consolidar_señales, generar_recomendaciones
        from engine.motor_automatico import get_resumen_motor, validar_señal
        from engine.ib_executor import ejecutar_señales

        # Verificar motor activo
        estado = get_resumen_motor()
        if not estado.get("activo") or estado.get("pausado"):
            return 0

        # Cargar datos en paralelo
        datos = get_datos_para_motor(verbose=False)
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
        )
        recomendaciones = generar_recomendaciones(activos)

        # Filtrar señales de alta convicción no ejecutadas
        señales_trigger = [
            r for r in recomendaciones
            if r["conviccion"] >= CONVICCION_TRIGGER
            and f"{r['accion']}_{r['ib_ticker']}" not in SEÑALES_EJECUTADAS
        ]

        if not señales_trigger:
            return 0

        ordenes_ejecutadas = 0
        for señal in señales_trigger:
            key = f"{señal['accion']}_{señal['ib_ticker']}"

            # Validar con salvaguardas del motor
            valida, razon = validar_señal(señal)
            if not valida:
                logging.info(f"Trigger rechazado: {key} — {razon}")
                continue

            # Ejecutar inmediatamente
            logging.info(f"TRIGGER EJECUTANDO: {key} Conv:{señal['conviccion']}%")
            print(f"\n⚡ TRIGGER: {señal['accion']} {señal['ib_ticker']} "
                  f"Conv:{señal['conviccion']}% — ejecutando ahora...")

            resultado = ejecutar_señales([señal], modo_test=False)

            if resultado.get("ordenes_enviadas"):
                SEÑALES_EJECUTADAS.add(key)
                ordenes_ejecutadas += 1
                logging.info(f"TRIGGER OK: {key} ejecutado")
                print(f"✅ Orden enviada a IB")
            else:
                logging.warning(f"TRIGGER FALLÓ: {key} — {resultado.get('errores')}")

        return ordenes_ejecutadas

    except Exception as e:
        logging.error(f"Error en trigger: {e}")
        return 0

def run_trigger():
    """Loop principal del trigger"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Trigger iniciado")
    print(f"Convicción mínima: {CONVICCION_TRIGGER}%")
    print(f"Scan cada: {INTERVALO_SCAN}s")
    print(f"Máx órdenes/día: {MAX_ORDENES_DIA}")
    logging.info("Trigger iniciado")

    while True:
        try:
            if es_horario_mercado():
                t0 = time.time()
                ordenes = scan_y_ejecutar()
                elapsed = time.time() - t0
                if ordenes > 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"{ordenes} orden(es) ejecutada(s) en {elapsed:.1f}s")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"Scan completado en {elapsed:.1f}s — sin señales trigger")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"Fuera de horario — esperando...")

        except Exception as e:
            logging.error(f"Error en loop: {e}")

        time.sleep(INTERVALO_SCAN)

if __name__ == "__main__":
    run_trigger()
