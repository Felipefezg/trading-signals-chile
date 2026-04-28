"""
Integra Put/Call ratio al motor de recomendaciones y dashboard.
"""
import re

# ── 1. INTEGRAR EN MOTOR DE RECOMENDACIONES ───────────────────────────────────
with open("engine/recomendaciones.py", "r") as f:
    content = f.read()

# Agregar Put/Call como fuente en consolidar_señales
old_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None):"
new_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None, put_call=None):"
content = content.replace(old_def, new_def)

# Agregar procesamiento de put_call antes de "return activos"
old_return = "    return activos\n"
new_pc = '''    # Put/Call Ratio — Smart Money Positioning
    PC_PESO = {"ALZA": 1.5, "BAJA": 1.5, "NEUTRO": 0}
    for activo_pc, datos_pc in (put_call or {}).items():
        if activo_pc not in activos:
            activos[activo_pc] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        direccion_pc = datos_pc.get("direccion", "NEUTRO")
        score_pc     = datos_pc.get("score", 0)
        peso_pc      = score_pc * 0.3
        if direccion_pc == "ALZA" and peso_pc > 0:
            activos[activo_pc]["alza"] += peso_pc
            activos[activo_pc]["fuentes"].append("Put/Call")
            activos[activo_pc]["evidencia"].append({
                "fuente": "Put/Call", "señal": f"P/C {datos_pc['ticker']}: {datos_pc['ratio']:.3f} — {datos_pc['señal'][:50]}",
                "prob": None, "direccion": "ALZA", "peso": round(peso_pc, 2),
            })
        elif direccion_pc == "BAJA" and peso_pc > 0:
            activos[activo_pc]["baja"] += peso_pc
            activos[activo_pc]["fuentes"].append("Put/Call")
            activos[activo_pc]["evidencia"].append({
                "fuente": "Put/Call", "señal": f"P/C {datos_pc['ticker']}: {datos_pc['ratio']:.3f} — {datos_pc['señal'][:50]}",
                "prob": None, "direccion": "BAJA", "peso": round(peso_pc, 2),
            })

    return activos
'''
content = content.replace(old_return, new_pc, 1)

# Actualizar tesis
content = content.replace(
    "    poly_ev  = [e for e in evidencia if e[\"fuente\"] == \"Polymarket\"]",
    "    pc_ev     = [e for e in evidencia if e[\"fuente\"] == \"Put/Call\"]\n    poly_ev  = [e for e in evidencia if e[\"fuente\"] == \"Polymarket\"]"
)
content = content.replace(
    "    if fg_ev:\n        partes.append(fg_ev[0][\"señal\"][:40])\n    if partes:",
    "    if fg_ev:\n        partes.append(fg_ev[0][\"señal\"][:40])\n    if pc_ev:\n        partes.append(f\"Put/Call: {pc_ev[0]['señal'][:40]}\")\n    if partes:"
)

with open("engine/recomendaciones.py", "w") as f:
    f.write(content)
print("✅ Put/Call integrado en motor de recomendaciones")

# ── 2. INTEGRAR EN DASHBOARD ──────────────────────────────────────────────────
with open("dashboard.py", "r") as f:
    content = f.read()

# Import
if "put_call" not in content:
    content = content.replace(
        "from data.volumen import get_resumen_volumen, correlacionar_con_cmf",
        "from data.volumen import get_resumen_volumen, correlacionar_con_cmf\n"
        "from data.put_call import get_resumen_pc, get_señal_consolidada_pc"
    )
    print("✅ Import put_call agregado")

# Agregar put_call en la llamada al motor
old_call = '''        activos      = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias,
                                          fear_greed=fg_data, cmf_hechos=cmf_data, vol_alertas=vol_data)'''
new_call = '''        try:
            pc_señales = get_señal_consolidada_pc()
        except:
            pc_señales = None

        activos      = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias,
                                          fear_greed=fg_data, cmf_hechos=cmf_data,
                                          vol_alertas=vol_data, put_call=pc_señales)'''
content = content.replace(old_call, new_call)
print("✅ Put/Call agregado al motor en dashboard")

# Agregar sub-tab Put/Call en Oportunidades
old_subtabs_op = '    sub_señales, sub_arbitraje, sub_opciones = st.tabs([\n        "Señales de Trading", "Arbitraje ADR", "Opciones"\n    ])'
new_subtabs_op = '    sub_señales, sub_arbitraje, sub_pc, sub_opciones = st.tabs([\n        "Señales de Trading", "Arbitraje ADR", "Put/Call Ratio", "Opciones"\n    ])'
content = content.replace(old_subtabs_op, new_subtabs_op)

# Insertar contenido del tab Put/Call antes de sub_opciones
old_opciones = '    with sub_opciones:'
new_pc_tab = '''    with sub_pc:
        st.markdown("**Put/Call Ratio — Smart Money Positioning**")
        st.caption("Relación entre opciones put (protección/bajista) y call (especulación/alcista). P/C alto = institucionales se protegen. P/C bajo = euforia.")

        with st.spinner("Calculando ratios..."):
            resumen_pc = get_resumen_pc()

        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Tickers analizados", resumen_pc.get("total", 0))
        with col2:
            spy = resumen_pc.get("spy_ratio")
            st.metric("SPY P/C ratio", f"{spy:.3f}" if spy else "N/D")
        with col3:
            sqm = resumen_pc.get("sqm_ratio")
            st.metric("SQM P/C ratio", f"{sqm:.3f}" if sqm else "N/D")

        st.divider()

        for r in resumen_pc.get("ratios", []):
            color = r["color"]
            with st.expander(
                f"{r['ticker']}  ·  P/C Vol: {r['pc_ratio_vol']:.3f}  ·  {r['señal']}"
            ):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**{r['nombre']}**")
                    st.markdown(f"Precio: `{r['precio']:,.2f}`" if r.get('precio') else "")
                    st.markdown(
                        f\'<span style="background:{color}22;color:{color};border:1px solid {color}44;\' +
                        f\'border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:600">\' +
                        f\'{r["señal"]}</span>\',
                        unsafe_allow_html=True
                    )
                with col2:
                    st.markdown("**Volumen opciones**")
                    st.markdown(f"Calls: `{r['calls_vol']:,}`")
                    st.markdown(f"Puts:  `{r['puts_vol']:,}`")
                    st.markdown(f"P/C Vol: **{r['pc_ratio_vol']:.3f}**")
                with col3:
                    st.markdown("**Open Interest**")
                    st.markdown(f"Calls OI: `{r['calls_oi']:,}`")
                    st.markdown(f"Puts OI:  `{r['puts_oi']:,}`")
                    st.markdown(f"P/C OI: **{r['pc_ratio_oi']:.3f}**")
                st.divider()
                st.caption(f"Impacto en: {r['impacto_activo']} · {r['vencimientos']} vencimientos analizados")

        st.divider()
        st.markdown("**Guía de interpretación**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("P/C > 2.0 → Capitulación → **Contrarian COMPRA fuerte**")
            st.markdown("P/C 1.5-2.0 → Miedo → Posible suelo")
            st.markdown("P/C 1.0-1.5 → Precaución → Institucionales se protegen")
        with col2:
            st.markdown("P/C 0.6-1.0 → Neutral")
            st.markdown("P/C 0.3-0.6 → Optimismo → Sesgo alcista")
            st.markdown("P/C < 0.3 → Codicia extrema → **Contrarian VENTA**")

    with sub_opciones:'''

content = content.replace(old_opciones, new_pc_tab)
print("✅ Tab Put/Call insertado en Oportunidades")

with open("dashboard.py", "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
