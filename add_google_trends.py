"""
Integra Google Trends al motor de recomendaciones.
Trends no determina dirección sino que amplifica señales existentes.
"""

# ── MOTOR DE RECOMENDACIONES ──────────────────────────────────────────────────
with open("engine/recomendaciones.py", "r") as f:
    content = f.read()

# Agregar trends como parámetro
old_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None, put_call=None, analisis_tecnico=None):"
new_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None, put_call=None, analisis_tecnico=None, google_trends=None):"
content = content.replace(old_def, new_def)

# Agregar procesamiento trends antes de return activos
old_return = "    # Put/Call Ratio — Smart Money Positioning"
new_trends = '''    # Google Trends — Amplificador de señales existentes
    for trend in (google_trends or []):
        activo_gt = trend.get("activo")
        if not activo_gt or activo_gt not in activos:
            continue
        score_gt = trend.get("score", 0)
        if score_gt < 2:
            continue
        # Trends amplifica la señal dominante (no determina dirección)
        peso_gt = score_gt * 0.3
        # Amplificar la dirección que ya tiene más peso
        if activos[activo_gt]["alza"] >= activos[activo_gt]["baja"]:
            activos[activo_gt]["alza"] += peso_gt
            dir_gt = "ALZA"
        else:
            activos[activo_gt]["baja"] += peso_gt
            dir_gt = "BAJA"
        activos[activo_gt]["fuentes"].append("Google Trends")
        activos[activo_gt]["evidencia"].append({
            "fuente": "Google Trends",
            "señal":  trend.get("descripcion", "")[:80],
            "prob": None, "direccion": dir_gt, "peso": round(peso_gt, 2),
        })

    # Put/Call Ratio — Smart Money Positioning'''

content = content.replace(old_return, new_trends)

with open("engine/recomendaciones.py", "w") as f:
    f.write(content)
print("✅ Google Trends integrado en motor")

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
with open("dashboard.py", "r") as f:
    content = f.read()

# Import
if "google_trends" not in content:
    content = content.replace(
        "from engine.analisis_tecnico import get_señales_tecnicas, get_analisis_completo",
        "from engine.analisis_tecnico import get_señales_tecnicas, get_analisis_completo\n"
        "from data.google_trends import get_resumen_trends, get_señales_trends"
    )
    print("✅ Import Google Trends agregado")

# Agregar en llamada al motor
old_call = '''        try:
            at_señales = get_señales_tecnicas(min_conviccion=60)
        except:
            at_señales = None

        activos      = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias,
                                          fear_greed=fg_data, cmf_hechos=cmf_data,
                                          vol_alertas=vol_data, put_call=pc_señales,
                                          analisis_tecnico=at_señales)'''

new_call = '''        try:
            at_señales = get_señales_tecnicas(min_conviccion=60)
        except:
            at_señales = None
        try:
            gt_señales = get_señales_trends(min_score=2)
        except:
            gt_señales = None

        activos      = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias,
                                          fear_greed=fg_data, cmf_hechos=cmf_data,
                                          vol_alertas=vol_data, put_call=pc_señales,
                                          analisis_tecnico=at_señales,
                                          google_trends=gt_señales)'''

content = content.replace(old_call, new_call)
print("✅ Google Trends agregado al motor en dashboard")

with open("dashboard.py", "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
