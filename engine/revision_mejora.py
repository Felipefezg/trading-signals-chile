"""
Loop de Revisión y Mejora Automática
Plan → Trade → Record → Review → Improve

Analiza todos los trades cerrados para:
1. Identificar qué fuentes predijeron correctamente
2. Ajustar pesos dinámicamente según historial de aciertos
3. Generar postmortem automático de cada trade
4. Detectar patrones en trades ganadores vs perdedores
5. Sugerir mejoras concretas a la estrategia
"""

import json
import os
import sqlite3
import numpy as np
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── CARGAR HISTORIAL DE TRADES ────────────────────────────────────────────────
def get_trades_cerrados():
    """Carga todos los trades cerrados"""
    try:
        path = os.path.join(BASE_DIR, "trades_cerrados.json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return json.load(f)
    except:
        return []

def get_señales_db():
    """Carga señales históricas de la DB"""
    try:
        db_path = os.path.join(BASE_DIR, "historial.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT fecha, senal, prob_pct, direccion, activos, score, tesis, resultado
            FROM senales ORDER BY fecha DESC LIMIT 200
        """)
        rows = c.fetchall()
        conn.close()
        return [{"fecha": r[0], "senal": r[1], "prob_pct": r[2],
                 "direccion": r[3], "activos": r[4], "score": r[5],
                 "tesis": r[6], "resultado": r[7]} for r in rows]
    except:
        return []

# ── POSTMORTEM DE TRADE ───────────────────────────────────────────────────────
def generar_postmortem(trade):
    """
    Genera análisis postmortem de un trade cerrado.
    """
    ticker       = trade.get("ticker", "")
    accion       = trade.get("accion", "")
    pnl_pct      = trade.get("pnl_pct", 0)
    pnl_usd      = trade.get("pnl_total", 0)
    razon_cierre = trade.get("razon", "")
    precio_entrada = trade.get("precio_entrada", 0)
    precio_salida  = trade.get("precio_salida", 0)
    fecha_entrada  = trade.get("fecha_entrada", "")
    fecha_salida   = trade.get("fecha_salida", "")
    fuentes        = trade.get("fuentes", [])
    conviccion     = trade.get("conviccion", 0)

    ganador = pnl_pct > 0

    # Días en posición
    try:
        dias = (datetime.fromisoformat(fecha_salida) -
                datetime.fromisoformat(fecha_entrada)).days
    except:
        dias = 0

    # Análisis de la razón de cierre
    if razon_cierre == "STOP LOSS":
        lecciones = [
            "El precio no respetó el nivel de soporte/resistencia esperado",
            "Considerar ampliar SL o reducir tamaño de posición",
            "Revisar si había señales contrarias ignoradas",
        ]
    elif razon_cierre == "TAKE PROFIT":
        lecciones = [
            "La tesis se cumplió correctamente",
            "Evaluar si el TP2 habría dado más rendimiento",
            "Documentar qué fuentes predijeron correctamente",
        ]
    elif razon_cierre == "TRAILING STOP":
        lecciones = [
            "La posición ganó pero el trail fue muy ajustado",
            "Considerar trail más amplio para dejar correr más",
            f"Trail activado con {pnl_pct:.1f}% de ganancia",
        ]
    elif razon_cierre == "HORIZONTE":
        if ganador:
            lecciones = ["Posición ganadora cerrada por tiempo — considerar extender horizonte"]
        else:
            lecciones = ["Posición perdedora cerrada por tiempo — la tesis no se materializó"]
    else:
        lecciones = ["Revisar condiciones de mercado al momento del cierre"]

    # Score del trade
    if pnl_pct > 10:
        calificacion = "EXCELENTE ⭐⭐⭐"
    elif pnl_pct > 5:
        calificacion = "BUENO ⭐⭐"
    elif pnl_pct > 0:
        calificacion = "POSITIVO ⭐"
    elif pnl_pct > -5:
        calificacion = "PÉRDIDA PEQUEÑA"
    elif pnl_pct > -10:
        calificacion = "PÉRDIDA MODERADA ⚠️"
    else:
        calificacion = "PÉRDIDA GRANDE ❌"

    return {
        "ticker":        ticker,
        "accion":        accion,
        "calificacion":  calificacion,
        "ganador":       ganador,
        "pnl_pct":       round(pnl_pct, 2),
        "pnl_usd":       round(pnl_usd, 2),
        "razon_cierre":  razon_cierre,
        "dias":          dias,
        "conviccion":    conviccion,
        "fuentes":       fuentes,
        "lecciones":     lecciones,
        "fecha_entrada": fecha_entrada,
        "fecha_salida":  fecha_salida,
    }

# ── ANÁLISIS DE FUENTES ───────────────────────────────────────────────────────
def analizar_efectividad_fuentes(trades):
    """
    Analiza qué fuentes tienen mejor track record.
    """
    fuentes_stats = {}

    for trade in trades:
        fuentes = trade.get("fuentes", [])
        ganador = trade.get("pnl_total", 0) > 0

        for fuente in fuentes:
            if fuente not in fuentes_stats:
                fuentes_stats[fuente] = {"aciertos": 0, "total": 0, "pnl_total": 0}
            fuentes_stats[fuente]["total"] += 1
            fuentes_stats[fuente]["pnl_total"] += trade.get("pnl_total", 0)
            if ganador:
                fuentes_stats[fuente]["aciertos"] += 1

    # Calcular win rate por fuente
    resultado = []
    for fuente, stats in fuentes_stats.items():
        if stats["total"] >= 2:
            win_rate = stats["aciertos"] / stats["total"] * 100
            resultado.append({
                "fuente":    fuente,
                "total":     stats["total"],
                "aciertos":  stats["aciertos"],
                "win_rate":  round(win_rate, 1),
                "pnl_total": round(stats["pnl_total"], 2),
                "peso_sugerido": round(min(2.0, max(0.3, win_rate / 50)), 2),
            })

    return sorted(resultado, key=lambda x: x["win_rate"], reverse=True)

# ── PATRONES DE TRADES ────────────────────────────────────────────────────────
def detectar_patrones(trades):
    """
    Detecta patrones en trades ganadores vs perdedores.
    """
    if len(trades) < 3:
        return {}

    ganadores = [t for t in trades if t.get("pnl_total", 0) > 0]
    perdedores = [t for t in trades if t.get("pnl_total", 0) <= 0]

    patrones = {}

    # Convicción promedio
    if ganadores:
        conv_gan = np.mean([t.get("conviccion", 0) for t in ganadores])
        patrones["conviccion_promedio_ganadores"] = round(conv_gan, 1)
    if perdedores:
        conv_per = np.mean([t.get("conviccion", 0) for t in perdedores])
        patrones["conviccion_promedio_perdedores"] = round(conv_per, 1)

    # Tipo de activo
    tipos_ganadores = {}
    tipos_perdedores = {}
    for t in ganadores:
        tipo = t.get("tipo", "desconocido")
        tipos_ganadores[tipo] = tipos_ganadores.get(tipo, 0) + 1
    for t in perdedores:
        tipo = t.get("tipo", "desconocido")
        tipos_perdedores[tipo] = tipos_perdedores.get(tipo, 0) + 1

    patrones["mejores_tipos"] = sorted(tipos_ganadores.items(), key=lambda x: -x[1])[:3]
    patrones["peores_tipos"]  = sorted(tipos_perdedores.items(), key=lambda x: -x[1])[:3]

    # Días promedio en posición
    if ganadores:
        dias_gan = np.mean([t.get("dias", 0) for t in ganadores if t.get("dias", 0) > 0])
        patrones["dias_promedio_ganadores"] = round(dias_gan, 1)
    if perdedores:
        dias_per = np.mean([t.get("dias", 0) for t in perdedores if t.get("dias", 0) > 0])
        patrones["dias_promedio_perdedores"] = round(dias_per, 1)

    return patrones

# ── SUGERENCIAS DE MEJORA ─────────────────────────────────────────────────────
def generar_sugerencias(trades, fuentes_stats, patrones):
    """
    Genera sugerencias concretas basadas en el análisis.
    """
    sugerencias = []
    n_trades = len(trades)

    if n_trades < 3:
        return ["Necesitas al menos 3 trades cerrados para generar sugerencias."]

    ganadores = [t for t in trades if t.get("pnl_total", 0) > 0]
    win_rate  = len(ganadores) / n_trades * 100

    # Win rate
    if win_rate < 40:
        sugerencias.append(f"⚠️ Win rate {win_rate:.1f}% bajo — subir umbral de convicción mínima a 85%")
    elif win_rate > 60:
        sugerencias.append(f"✅ Win rate {win_rate:.1f}% bueno — mantener parámetros actuales")

    # Fuentes con bajo win rate
    for f in fuentes_stats:
        if f["win_rate"] < 35 and f["total"] >= 3:
            sugerencias.append(f"⚠️ {f['fuente']} tiene win rate {f['win_rate']}% — reducir su peso")
        elif f["win_rate"] > 65 and f["total"] >= 3:
            sugerencias.append(f"✅ {f['fuente']} tiene win rate {f['win_rate']}% — aumentar su peso")

    # Trailing stop
    stops = [t for t in trades if t.get("razon") == "TRAILING STOP"]
    if stops:
        pnl_stops = np.mean([t.get("pnl_pct", 0) for t in stops])
        if pnl_stops < 1:
            sugerencias.append(f"⚠️ Trailing stops cerrando con solo {pnl_stops:.1f}% — ampliar trail a 3%")

    # Convicción
    conv_gan = patrones.get("conviccion_promedio_ganadores", 0)
    conv_per = patrones.get("conviccion_promedio_perdedores", 0)
    if conv_gan and conv_per and conv_gan > conv_per + 10:
        sugerencias.append(f"✅ Trades con conv>{conv_gan:.0f}% ganan más — subir umbral mínimo")

    return sugerencias

# ── REPORTE COMPLETO ──────────────────────────────────────────────────────────
def generar_reporte_revision():
    """
    Genera reporte completo de revisión y mejora.
    """
    trades = get_trades_cerrados()
    señales = get_señales_db()

    if not trades:
        return {
            "timestamp":  datetime.now().isoformat(),
            "n_trades":   0,
            "mensaje":    "Sin trades cerrados aún — el sistema necesita historial para mejorar",
            "sugerencias": [],
        }

    # Postmortems
    postmortems = [generar_postmortem(t) for t in trades]

    # Análisis de fuentes
    fuentes_stats = analizar_efectividad_fuentes(trades)

    # Patrones
    patrones = detectar_patrones(trades)

    # Sugerencias
    sugerencias = generar_sugerencias(trades, fuentes_stats, patrones)

    # Métricas generales
    ganadores = [t for t in trades if t.get("pnl_total", 0) > 0]
    perdedores = [t for t in trades if t.get("pnl_total", 0) <= 0]
    pnl_total  = sum(t.get("pnl_total", 0) for t in trades)
    win_rate   = len(ganadores) / len(trades) * 100 if trades else 0
    avg_gan    = np.mean([t.get("pnl_total", 0) for t in ganadores]) if ganadores else 0
    avg_per    = abs(np.mean([t.get("pnl_total", 0) for t in perdedores])) if perdedores else 1
    rr_ratio   = avg_gan / avg_per if avg_per > 0 else 0

    return {
        "timestamp":     datetime.now().isoformat(),
        "n_trades":      len(trades),
        "n_ganadores":   len(ganadores),
        "n_perdedores":  len(perdedores),
        "win_rate":      round(win_rate, 1),
        "pnl_total":     round(pnl_total, 2),
        "rr_ratio":      round(rr_ratio, 2),
        "avg_ganador":   round(avg_gan, 2),
        "avg_perdedor":  round(avg_per, 2),
        "fuentes_stats": fuentes_stats,
        "patrones":      patrones,
        "postmortems":   postmortems,
        "sugerencias":   sugerencias,
        "n_señales_db":  len(señales),
    }

def enviar_reporte_telegram(reporte):
    """Envía reporte de revisión por Telegram"""
    try:
        from engine.telegram_alertas import _enviar
        n = reporte["n_trades"]
        if n == 0:
            return

        msg = f"""📊 *REPORTE DE REVISIÓN SEMANAL*
━━━━━━━━━━━━━━━━━━━━━━
Trades analizados: *{n}*
Win rate: *{reporte['win_rate']}%*
PnL total: *USD {reporte['pnl_total']:+,.0f}*
R/R ratio: *{reporte['rr_ratio']:.2f}x*

*FUENTES MÁS EFECTIVAS:*"""

        for f in reporte["fuentes_stats"][:3]:
            msg += f"\n  {f['fuente']}: {f['win_rate']}% ({f['total']} trades)"

        msg += "\n\n*SUGERENCIAS:*"
        for s in reporte["sugerencias"][:3]:
            msg += f"\n  {s}"

        msg += f"\n━━━━━━━━━━━━━━━━━━━━━━\n_{datetime.now().strftime('%Y-%m-%d %H:%M')}_"
        _enviar(msg)
    except Exception as e:
        print(f"Error Telegram revisión: {e}")

if __name__ == "__main__":
    print("=== REPORTE DE REVISIÓN Y MEJORA ===\n")
    reporte = generar_reporte_revision()

    if reporte["n_trades"] == 0:
        print(reporte["mensaje"])
    else:
        print(f"Trades analizados: {reporte['n_trades']}")
        print(f"Win rate: {reporte['win_rate']}%")
        print(f"PnL total: USD {reporte['pnl_total']:+,.0f}")
        print(f"R/R ratio: {reporte['rr_ratio']:.2f}x")

        if reporte["fuentes_stats"]:
            print("\n--- EFECTIVIDAD POR FUENTE ---")
            for f in reporte["fuentes_stats"]:
                print(f"  {f['fuente']:<20} win:{f['win_rate']}% trades:{f['total']} pnl:{f['pnl_usd'] if 'pnl_usd' in f else f['pnl_total']:+,.0f}")

        if reporte["sugerencias"]:
            print("\n--- SUGERENCIAS DE MEJORA ---")
            for s in reporte["sugerencias"]:
                print(f"  {s}")

        if reporte["postmortems"]:
            print("\n--- POSTMORTEMS ---")
            for p in reporte["postmortems"]:
                print(f"  [{p['calificacion']}] {p['ticker']} {p['accion']} {p['pnl_pct']:+.2f}% | {p['razon_cierre']} | {p['dias']}d")
                for l in p["lecciones"][:1]:
                    print(f"    → {l}")
