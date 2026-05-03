"""
Alertas Telegram mejoradas para Trading Terminal Chile.

Tipos de alertas:
1. Orden ejecutada — inmediata al ejecutar
2. Cierre de posición — SL/TP/Trailing/Horizonte
3. Resumen diario — 9:00 AM y 4:00 PM
4. Alerta de riesgo — drawdown, pausa motor
5. Señal de alta convicción — sin ejecutar aún
"""

import requests
from datetime import datetime
import json
import os

TOKEN    = "8648892135:AAHairDr4kx1IuRWkI0CL9FgKG6Sx_g_YlA"
CHAT_ID  = "8481235797"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _enviar(mensaje, parse_mode="Markdown"):
    """Envía mensaje a Telegram"""
    try:
        r = requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": parse_mode},
            timeout=10
        )
        return r.ok
    except Exception as e:
        print(f"Error Telegram: {e}")
        return False

# ── ALERTA ORDEN EJECUTADA ────────────────────────────────────────────────────
def alerta_orden_ejecutada(recomendacion, cantidad, monto_usd):
    """Alerta inmediata cuando se ejecuta una orden en IB"""
    accion   = recomendacion.get("accion", "")
    ticker   = recomendacion.get("ib_ticker", "")
    conv     = recomendacion.get("conviccion", 0)
    riesgo   = recomendacion.get("riesgo", 0)
    precio   = recomendacion.get("precio_actual", 0)
    sl       = recomendacion.get("stop_loss")
    tp       = recomendacion.get("take_profit")
    tesis    = recomendacion.get("tesis", "")
    fuentes  = recomendacion.get("fuentes", [])
    horizonte= recomendacion.get("horizonte", {})

    icon = "🟢" if accion == "COMPRAR" else "🔴"
    accion_str = "LARGO" if accion == "COMPRAR" else "CORTO"

    msg = f"""⚡ *ORDEN EJECUTADA*
━━━━━━━━━━━━━━━━━━━━━━
{icon} *{accion} {ticker}* — {accion_str}
📊 Cantidad: *{cantidad}* acciones
💵 Monto: *USD {monto_usd:,.0f}*

📈 Convicción: *{conv}%* | Riesgo: *{riesgo}/10*
⏱ Horizonte: {horizonte.get('dias', 'N/D')}
🔗 Fuentes: {', '.join(fuentes[:4])}

💰 Precio entrada: *{precio:,.2f}*"""

    if sl and tp:
        rr = round(abs(tp-precio)/abs(precio-sl), 1) if abs(precio-sl) > 0 else 0
        msg += f"""
🛑 Stop Loss: *{sl:,.2f}*
🎯 Take Profit: *{tp:,.2f}*
⚖️ R/R: *1:{rr}*"""

    msg += f"""

📝 _{tesis[:100]}_
━━━━━━━━━━━━━━━━━━━━━━
_{datetime.now().strftime('%H:%M:%S')} ET_"""

    return _enviar(msg)

# ── ALERTA CIERRE DE POSICIÓN ─────────────────────────────────────────────────
def alerta_cierre_posicion(ticker, razon, pnl_pct, pnl_usd, precio_entrada, precio_salida):
    """Alerta cuando se cierra una posición automáticamente"""
    if pnl_pct >= 0:
        icon = "✅"
        resultado = "GANANCIA"
    else:
        icon = "❌"
        resultado = "PÉRDIDA"

    razones_icon = {
        "STOP LOSS":      "🛑",
        "TAKE PROFIT":    "🎯",
        "TRAILING STOP":  "📉",
        "HORIZONTE CUMPLIDO": "⏰",
    }
    razon_icon = razones_icon.get(razon, "🔒")

    msg = f"""{icon} *POSICIÓN CERRADA*
━━━━━━━━━━━━━━━━━━━━━━
{razon_icon} Razón: *{razon}*
📊 Ticker: *{ticker}*
💵 Resultado: *{resultado}*

💰 Entrada: *{precio_entrada:,.2f}*
💰 Salida: *{precio_salida:,.2f}*
📈 PnL: *{pnl_pct:+.2f}%* (*USD {pnl_usd:+,.0f}*)
━━━━━━━━━━━━━━━━━━━━━━
_{datetime.now().strftime('%H:%M:%S')} ET_"""

    return _enviar(msg)

# ── RESUMEN DIARIO ────────────────────────────────────────────────────────────
def alerta_resumen_diario():
    """Resumen completo del día — enviar a las 9:00 AM y 4:00 PM"""
    try:
        # Posiciones
        pos_path = os.path.join(BASE_DIR, "posiciones.json")
        with open(pos_path) as f:
            posiciones = json.load(f)

        # Trades cerrados hoy
        trades_path = os.path.join(BASE_DIR, "trades_cerrados.json")
        trades_hoy = []
        try:
            with open(trades_path) as f:
                trades = json.load(f)
            hoy = datetime.now().date().isoformat()
            trades_hoy = [t for t in trades if t.get("fecha_salida","")[:10] == hoy]
        except:
            pass

        # Fear & Greed
        fg_score = fg_clase = "N/D"
        try:
            from engine.fear_greed import calcular_fear_greed
            fg = calcular_fear_greed()
            fg_score = fg["score"]
            fg_clase = fg["clasificacion"]
        except:
            pass

        # Motor
        motor_activo = False
        try:
            from engine.motor_automatico import get_resumen_motor
            motor = get_resumen_motor()
            motor_activo = motor.get("activo") and not motor.get("pausado")
        except:
            pass

        # Performance
        pnl_total = 0
        capital   = 100_000
        try:
            from engine.performance import get_metricas_performance
            m = get_metricas_performance()
            pnl_total = m.get("pnl_total", 0)
            capital   = m.get("capital_actual", 100_000)
        except:
            pass

        hora = datetime.now().strftime("%H:%M")
        fecha = datetime.now().strftime("%A %d %B")

        # Posiciones activas
        pos_lines = ""
        if posiciones:
            import yfinance as yf
            for ticker, p in posiciones.items():
                try:
                    yf_map = {"SQM": "SQM", "COPEC": "COPEC.SN", "ECH": "ECH", "BTC": "BTC-USD"}
                    yf_ticker = yf_map.get(ticker, ticker)
                    precio_actual = float(yf.Ticker(yf_ticker).history(period="1d")["Close"].iloc[-1])
                    entrada = p.get("precio_entrada", 0)
                    accion  = p.get("accion", "")
                    if accion == "VENDER":
                        pnl = (entrada - precio_actual) / entrada * 100
                    else:
                        pnl = (precio_actual - entrada) / entrada * 100
                    icon = "🟢" if pnl >= 0 else "🔴"
                    pos_lines += f"\n  {icon} {ticker}: {pnl:+.2f}%"
                except:
                    pos_lines += f"\n  • {ticker}: precio N/D"
        else:
            pos_lines = "\n  Sin posiciones abiertas"

        # Trades del día
        trades_lines = ""
        pnl_dia = 0
        if trades_hoy:
            for t in trades_hoy:
                pnl_t = t.get("pnl_total", 0)
                pnl_dia += pnl_t
                icon = "✅" if pnl_t >= 0 else "❌"
                trades_lines += f"\n  {icon} {t['ticker']}: USD {pnl_t:+,.0f}"
        else:
            trades_lines = "\n  Sin trades cerrados hoy"

        motor_str = "🟢 ACTIVO" if motor_activo else "🔴 INACTIVO"

        msg = f"""📊 *RESUMEN DIARIO — {hora} ET*
_{fecha}_
━━━━━━━━━━━━━━━━━━━━━━
💼 *POSICIONES ABIERTAS*{pos_lines}

📈 *TRADES HOY*{trades_lines}
💵 PnL del día: *USD {pnl_dia:+,.0f}*

🧠 *SISTEMA*
Fear & Greed: *{fg_score}/100* — {fg_clase}
Motor: {motor_str}
Capital: *USD {capital:,.0f}*
PnL total: *USD {pnl_total:+,.0f}*
━━━━━━━━━━━━━━━━━━━━━━
_Trading Terminal Chile_"""

        return _enviar(msg)

    except Exception as e:
        return _enviar(f"⚠️ Error generando resumen: {e}")

# ── ALERTA SEÑAL ALTA CONVICCIÓN ──────────────────────────────────────────────
def alerta_señal_detectada(recomendacion):
    """Alerta cuando se detecta señal de alta convicción (sin ejecutar aún)"""
    accion  = recomendacion.get("accion", "")
    ticker  = recomendacion.get("ib_ticker", "")
    conv    = recomendacion.get("conviccion", 0)
    riesgo  = recomendacion.get("riesgo", 0)
    tesis   = recomendacion.get("tesis", "")
    fuentes = recomendacion.get("fuentes", [])

    icon = "🟢" if accion == "COMPRAR" else "🔴"

    msg = f"""🔍 *SEÑAL DETECTADA*
━━━━━━━━━━━━━━━━━━━━━━
{icon} *{accion} {ticker}*
📊 Convicción: *{conv}%* | Riesgo: *{riesgo}/10*
🔗 Fuentes: {', '.join(fuentes[:4])}
📝 _{tesis[:120]}_
━━━━━━━━━━━━━━━━━━━━━━
_Evaluando ejecución..._"""

    return _enviar(msg)

# ── ALERTA DE RIESGO ──────────────────────────────────────────────────────────
def alerta_riesgo(tipo, mensaje, datos=None):
    """Alerta de riesgo — drawdown, pausa motor, etc."""
    iconos = {
        "PAUSA":    "⚠️",
        "DRAWDOWN": "📉",
        "SL":       "🛑",
        "ERROR":    "❌",
        "INFO":     "ℹ️",
    }
    icon = iconos.get(tipo, "⚠️")

    msg = f"""{icon} *ALERTA: {tipo}*
━━━━━━━━━━━━━━━━━━━━━━
{mensaje}"""

    if datos:
        for k, v in datos.items():
            msg += f"\n• {k}: {v}"

    msg += f"\n━━━━━━━━━━━━━━━━━━━━━━\n_{datetime.now().strftime('%H:%M:%S')} ET_"

    return _enviar(msg)

# ── RESUMEN POSICIONES ────────────────────────────────────────────────────────
def alerta_posiciones_actuales():
    """Muestra estado actual de todas las posiciones"""
    try:
        from engine.cierre_automatico import verificar_posiciones
        resumen = verificar_posiciones(modo_test=True, auto_cerrar=False)

        msg = "📊 *POSICIONES ACTUALES*\n━━━━━━━━━━━━━━━━━━━━━━"

        if resumen.get("ok"):
            for p in resumen["ok"]:
                icon = "🟢" if p["pnl_pct"] >= 0 else "🔴"
                msg += f"\n{icon} *{p['ticker']}*: {p['pnl_pct']:+.2f}% | precio {p['precio']:,.2f} | {p['dias']}d"
        else:
            msg += "\nSin posiciones abiertas"

        msg += f"\n━━━━━━━━━━━━━━━━━━━━━━\n_{datetime.now().strftime('%H:%M:%S')}_"
        return _enviar(msg)
    except Exception as e:
        return _enviar(f"Error obteniendo posiciones: {e}")

if __name__ == "__main__":
    print("Enviando resumen diario de prueba...")
    ok = alerta_resumen_diario()
    print("OK" if ok else "Error")
