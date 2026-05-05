#!/usr/bin/env python3
"""
Trigger de ejecución continua.
Llama a ciclo_trading_automatico() cada INTERVALO segundos.

Arquitectura limpia:
- UN SOLO punto de entrada para ejecución: ciclo_trading_automatico()
- Toda la lógica de riesgo, validación, horario y deduplicación vive ahí
- Este proceso simplemente lo llama frecuentemente para reaccionar rápido

Deduplicación:
- IB rechaza órdenes duplicadas (reqAllOpenOrders check en ejecutar_orden)
- Estado local en posiciones.json evita re-ejecutar el mismo ticker
- Archivo señales_ejecutadas_hoy.json persiste entre reinicios del trigger

Corre en background: nohup python3 trigger.py > /tmp/trigger.log 2>&1 &
"""

import sys
import os
import time
import json
import logging
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "trigger.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
INTERVALO_MERCADO   = 90    # segundos entre ciclos en horario de mercado
INTERVALO_FUERA     = 300   # segundos entre ciclos fuera de horario (SL/TP/Crypto)
MAX_CICLOS_DIA      = 200   # límite de seguridad diario (evita bucle infinito)
SEÑALES_FILE        = os.path.join(BASE_DIR, "señales_ejecutadas_hoy.json")


# ── SEÑALES EJECUTADAS (PERSISTENTE) ─────────────────────────────────────────
def _cargar_señales_hoy():
    """Carga el set de señales ejecutadas hoy. Limpia automáticamente al nuevo día."""
    try:
        if os.path.exists(SEÑALES_FILE):
            with open(SEÑALES_FILE) as f:
                data = json.load(f)
            # Si el archivo es de otro día, resetear
            if data.get("fecha") != date.today().isoformat():
                return set()
            return set(data.get("señales", []))
    except Exception:
        pass
    return set()


def _guardar_señales_hoy(señales: set):
    """Persiste las señales ejecutadas hoy en disco."""
    try:
        with open(SEÑALES_FILE, "w") as f:
            json.dump({
                "fecha":   date.today().isoformat(),
                "señales": list(señales),
            }, f)
    except Exception as e:
        logging.warning(f"No se pudo guardar señales_hoy: {e}")


def _señales_ejecutadas_hoy() -> set:
    """Retorna tickers ya ejecutados hoy desde log_automatico.json."""
    try:
        log_path = os.path.join(BASE_DIR, "log_automatico.json")
        if not os.path.exists(log_path):
            return set()
        with open(log_path) as f:
            log = json.load(f)
        hoy = date.today().isoformat()
        return {
            e.get("datos", {}).get("ib_ticker", "")
            for e in log
            if e.get("tipo") == "APERTURA"
            and e.get("timestamp", "")[:10] == hoy
        }
    except Exception:
        return set()


# ── CICLO PRINCIPAL ───────────────────────────────────────────────────────────
def run_trigger():
    """
    Loop principal — llama ciclo_trading_automatico() continuamente.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Trigger iniciado")
    print(f"  Intervalo en horario: {INTERVALO_MERCADO}s")
    print(f"  Intervalo fuera:      {INTERVALO_FUERA}s")
    logging.info("Trigger iniciado")

    ciclos_hoy        = 0
    fecha_hoy         = date.today()
    fallos_ib         = 0          # ciclos consecutivos con error IB
    FALLOS_IB_ALERTA  = 3          # enviar Telegram después de N fallos seguidos
    alerta_ib_enviada = False      # para no spamear

    while True:
        try:
            # Resetear contador al nuevo día
            if date.today() != fecha_hoy:
                fecha_hoy         = date.today()
                ciclos_hoy        = 0
                fallos_ib         = 0
                alerta_ib_enviada = False
                logging.info("Nuevo día — contadores reseteados")

            # Límite de seguridad diario
            if ciclos_hoy >= MAX_CICLOS_DIA:
                logging.warning(f"Límite de ciclos diarios alcanzado ({MAX_CICLOS_DIA})")
                time.sleep(600)
                continue

            t0 = time.time()

            # ── EJECUTAR CICLO COMPLETO ──────────────────────────────────────
            try:
                from engine.motor_automatico import (
                    ciclo_trading_automatico,
                    es_horario_mercado,
                )

                resultado = ciclo_trading_automatico()
                ciclos_hoy += 1

                # Detectar errores IB en el ciclo (apertura fallida por IB)
                errores_ib = [
                    r for r in resultado.get("rechazadas", [])
                    if "IB" in r.get("razon", "") or "TWS" in r.get("razon", "")
                    or "conecta" in r.get("razon", "").lower()
                ]
                if errores_ib:
                    fallos_ib += 1
                    if fallos_ib >= FALLOS_IB_ALERTA and not alerta_ib_enviada:
                        try:
                            from engine.telegram_alertas import alerta_riesgo
                            alerta_riesgo(
                                "ERROR",
                                f"IB no responde — {fallos_ib} ciclos consecutivos sin conexión",
                                {"Último error": errores_ib[0].get("razon", "desconocido"),
                                 "Acción": "Verificar TWS/Gateway está corriendo"}
                            )
                            alerta_ib_enviada = True
                            logging.warning(f"IB sin respuesta por {fallos_ib} ciclos — Telegram enviado")
                        except Exception:
                            pass
                else:
                    # Ciclo exitoso — resetear contador
                    if fallos_ib > 0:
                        logging.info(f"IB reconectado tras {fallos_ib} fallos")
                        fallos_ib         = 0
                        alerta_ib_enviada = False

                aperturas  = resultado.get("aperturas", [])
                cierres    = resultado.get("cierres", [])
                rechazadas = resultado.get("rechazadas", [])
                pausas     = resultado.get("pausas", [])
                elapsed    = round(time.time() - t0, 1)

                ts = datetime.now().strftime("%H:%M:%S")

                if pausas:
                    logging.warning(f"Motor pausado: {pausas[0]}")
                    print(f"[{ts}] ⚠️  Motor PAUSADO: {pausas[0]}")

                if aperturas:
                    for a in aperturas:
                        msg = f"✅ APERTURA: {a['accion']} {a['ticker']} | Conv {a['conviccion']}%"
                        print(f"[{ts}] {msg}")
                        logging.info(msg)

                if cierres:
                    for c in cierres:
                        msg = f"🔒 CIERRE: {c['ticker']} | {c.get('razon','')} | PnL {c.get('pnl_pct',0):+.2f}%"
                        print(f"[{ts}] {msg}")
                        logging.info(msg)

                if not aperturas and not cierres and not pausas:
                    print(f"[{ts}] Ciclo #{ciclos_hoy} OK ({elapsed}s) — sin operaciones")

            except Exception as e:
                logging.error(f"Error en ciclo_trading_automatico: {e}", exc_info=True)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR ciclo: {e}")

            # ── INTERVALO ADAPTATIVO ─────────────────────────────────────────
            # En horario de mercado: scan frecuente (90s)
            # Fuera de horario (solo SL/TP/Crypto): scan menos frecuente (5min)
            try:
                from engine.motor_automatico import es_horario_mercado
                en_horario, _ = es_horario_mercado()
            except Exception:
                en_horario = False

            intervalo = INTERVALO_MERCADO if en_horario else INTERVALO_FUERA

            # Descontar tiempo ya consumido por el ciclo
            ya_pasado = time.time() - t0
            espera    = max(5, intervalo - ya_pasado)
            time.sleep(espera)

        except KeyboardInterrupt:
            print("\nTrigger detenido manualmente")
            logging.info("Trigger detenido (KeyboardInterrupt)")
            break
        except Exception as e:
            logging.error(f"Error inesperado en loop principal: {e}", exc_info=True)
            time.sleep(30)  # pausa breve antes de reintentar


if __name__ == "__main__":
    run_trigger()
