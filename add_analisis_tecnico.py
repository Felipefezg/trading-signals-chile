"""
Integra análisis técnico al motor de recomendaciones.
El AT se suma como fuente adicional con peso alto
ya que usa precios reales en tiempo real.
"""

# ── 1. INTEGRAR EN MOTOR DE RECOMENDACIONES ───────────────────────────────────
with open("engine/recomendaciones.py", "r") as f:
    content = f.read()

# Agregar AT como parámetro de consolidar_señales
old_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None, put_call=None):"
new_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None, put_call=None, analisis_tecnico=None):"
content = content.replace(old_def, new_def)

# Agregar procesamiento AT antes de "return activos"
old_return = "    # Put/Call Ratio — Smart Money Positioning"
new_at = '''    # Análisis Técnico — RSI, MACD, Bollinger, MA
    for at in (analisis_tecnico or []):
        activo_map = at.get("activo_motor")
        if not activo_map:
            continue
        if activo_map not in activos:
            activos[activo_map] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}

        direccion_at = at.get("direccion", "NEUTRO")
        conviccion_at = at.get("conviccion", 0)
        puntos_at = at.get("puntos", 0)

        # Peso proporcional a la convicción y puntos técnicos
        peso_at = puntos_at * 0.8

        if direccion_at == "ALZA" and peso_at > 0:
            activos[activo_map]["alza"] += peso_at
            activos[activo_map]["fuentes"].append("Análisis Técnico")
            señales_desc = " | ".join(s["descripcion"] for s in at.get("señales", [])[:2])
            activos[activo_map]["evidencia"].append({
                "fuente": "Análisis Técnico",
                "señal": f"{at['nombre']}: {señales_desc[:80]}",
                "prob": None, "direccion": "ALZA", "peso": round(peso_at, 2),
            })
        elif direccion_at == "BAJA" and peso_at > 0:
            activos[activo_map]["baja"] += peso_at
            activos[activo_map]["fuentes"].append("Análisis Técnico")
            señales_desc = " | ".join(s["descripcion"] for s in at.get("señales", [])[:2])
            activos[activo_map]["evidencia"].append({
                "fuente": "Análisis Técnico",
                "señal": f"{at['nombre']}: {señales_desc[:80]}",
                "prob": None, "direccion": "BAJA", "peso": round(peso_at, 2),
            })

    # Put/Call Ratio — Smart Money Positioning'''

content = content.replace(old_return, new_at)

# Agregar AT en tesis
content = content.replace(
    '    pc_ev     = [e for e in evidencia if e["fuente"] == "Put/Call"]',
    '    at_ev     = [e for e in evidencia if e["fuente"] == "Análisis Técnico"]\n    pc_ev     = [e for e in evidencia if e["fuente"] == "Put/Call"]'
)
content = content.replace(
    '    if pc_ev:\n        partes.append(f"Put/Call: {pc_ev[0][\'señal\'][:40]}")',
    '    if at_ev:\n        partes.append(f"AT: {at_ev[0][\'señal\'][:50]}")\n    if pc_ev:\n        partes.append(f"Put/Call: {pc_ev[0][\'señal\'][:40]}")'
)

with open("engine/recomendaciones.py", "w") as f:
    f.write(content)
print("✅ Análisis técnico integrado en motor de recomendaciones")

# ── 2. INTEGRAR EN DASHBOARD ──────────────────────────────────────────────────
with open("dashboard.py", "r") as f:
    content = f.read()

# Import
if "analisis_tecnico" not in content:
    content = content.replace(
        "from data.put_call import get_resumen_pc, get_señal_consolidada_pc",
        "from data.put_call import get_resumen_pc, get_señal_consolidada_pc\n"
        "from engine.analisis_tecnico import get_señales_tecnicas, get_analisis_completo"
    )
    print("✅ Import análisis técnico agregado")

# Agregar AT en la llamada al motor
old_call = '''        activos      = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias,
                                          fear_greed=fg_data, cmf_hechos=cmf_data,
                                          vol_alertas=vol_data, put_call=pc_señales)'''
new_call = '''        try:
            at_señales = get_señales_tecnicas(min_conviccion=60)
        except:
            at_señales = None

        activos      = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias,
                                          fear_greed=fg_data, cmf_hechos=cmf_data,
                                          vol_alertas=vol_data, put_call=pc_señales,
                                          analisis_tecnico=at_señales)'''
content = content.replace(old_call, new_call)
print("✅ AT agregado al motor en dashboard")

# Agregar sub-tab AT en Mercado
old_subtabs = '    sub_ipsa, sub_macro, sub_cmf, sub_vol, sub_corr, sub_noticias = st.tabs([\n        "IPSA", "Macro Chile", "CMF Hechos Esenciales", "Volumen Anormal", "Correlaciones", "Noticias"\n    ])'
new_subtabs = '    sub_ipsa, sub_macro, sub_cmf, sub_vol, sub_at, sub_corr, sub_noticias = st.tabs([\n        "IPSA", "Macro Chile", "CMF Hechos Esenciales", "Volumen Anormal", "Análisis Técnico", "Correlaciones", "Noticias"\n    ])'
content = content.replace(old_subtabs, new_subtabs)

# Insertar tab AT antes de correlaciones
old_corr = '    # ── Sub-tab Correlaciones\n    with sub_corr:'
new_at_tab = '''    # ── Sub-tab Análisis Técnico
    with sub_at:
        st.markdown("**Análisis Técnico — RSI · MACD · Bollinger · Medias Móviles**")
        st.caption("Señales basadas en indicadores técnicos sobre precios reales. Actualización en cada refresh.")

        col1, col2 = st.columns([3,1])
        with col2:
            min_conv_at = st.slider("Convicción mínima", 50, 90, 60, key="slider_at")
            if st.button("Actualizar AT", use_container_width=True, key="btn_at_refresh"):
                st.rerun()

        with st.spinner("Calculando indicadores técnicos..."):
            todos_at = get_analisis_completo()
            señales_at = [a for a in todos_at if a["conviccion"] >= min_conv_at and a["accion"] != "MANTENER"]

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Activos analizados", len(todos_at))
        with col2: st.metric("Señales activas", len(señales_at))
        with col3: st.metric("Comprar", len([s for s in señales_at if s["accion"]=="COMPRAR"]))
        with col4: st.metric("Vender", len([s for s in señales_at if s["accion"]=="VENDER"]))

        st.divider()

        if señales_at:
            st.markdown("**Señales técnicas activas**")
            for s in señales_at:
                color_a = "#22c55e" if s["accion"] == "COMPRAR" else "#ef4444"
                with st.expander(
                    f"{s['accion']} {s['nombre']}  ·  Conv: {s['conviccion']}%  ·  "
                    f"RSI: {s['indicadores']['rsi']:.1f}  ·  Ret 5d: {s['indicadores']['ret_5d']:+.2f}%"
                ):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**Precio:** `{s['precio']:,.2f}`")
                        st.markdown(
                            f\'<span style="background:{color_a}22;color:{color_a};border:1px solid {color_a}44;\' +
                            f\'border-radius:4px;padding:2px 8px;font-size:0.8rem;font-weight:700">\' +
                            f\'{s["accion"]}</span>\',
                            unsafe_allow_html=True
                        )
                        st.progress(s["conviccion"]/100, text=f"Convicción: {s['conviccion']}%")
                    with col2:
                        ind = s["indicadores"]
                        st.markdown(f"**RSI:** {ind['rsi']:.1f} {'🔴 Sobrecompra' if ind['rsi']>70 else ('🟢 Sobreventa' if ind['rsi']<30 else '⚪ Neutral')}")
                        st.markdown(f"**MACD hist:** {ind['macd_hist']:+.4f}")
                        st.markdown(f"**%Bollinger:** {ind['pct_b']:.2f}")
                        st.markdown(f"**Volumen:** {ind['vol_ratio']:.1f}x promedio")
                    with col3:
                        if s["sl"] and s["tp"]:
                            st.markdown(f"**SL:** `{s['sl']:,.2f}`")
                            st.markdown(f"**TP:** `{s['tp']:,.2f}`")
                            st.markdown(f"**ATR:** `{s['atr']:,.2f}`")
                        st.markdown(f"**Ret 1d:** {ind['ret_1d']:+.2f}%")
                        st.markdown(f"**Ret 5d:** {ind['ret_5d']:+.2f}%")
                    st.divider()
                    for señal in s["señales"]:
                        sc = "#22c55e" if señal["direccion"]=="ALZA" else "#ef4444"
                        st.markdown(
                            f\'<div style="color:{sc};font-size:0.78rem;padding:2px 0">\'
                            f\'{"↑" if señal["direccion"]=="ALZA" else "↓"} [{señal["indicador"]}] {señal["descripcion"]}</div>\',
                            unsafe_allow_html=True
                        )

        st.divider()
        st.markdown("**Resumen de todos los activos**")
        rows_at = []
        for a in todos_at:
            ind = a["indicadores"]
            rows_at.append({
                "Activo":    a["nombre"],
                "Precio":   a["precio"],
                "Acción":   a["accion"],
                "Conv %":   a["conviccion"],
                "RSI":      ind["rsi"],
                "MACD":     ind["macd_hist"],
                "%B":       ind["pct_b"],
                "Ret 5d":   ind["ret_5d"],
                "Vol ratio": ind["vol_ratio"],
            })
        df_at = pd.DataFrame(rows_at)
        st.dataframe(df_at, use_container_width=True, hide_index=True,
            column_config={
                "Conv %": st.column_config.NumberColumn(format="%.1f%%"),
                "RSI": st.column_config.NumberColumn(format="%.1f"),
                "MACD": st.column_config.NumberColumn(format="%+.4f"),
                "%B": st.column_config.NumberColumn(format="%.2f"),
                "Ret 5d": st.column_config.NumberColumn(format="%+.2f%%"),
                "Vol ratio": st.column_config.NumberColumn(format="%.1fx"),
            })

    # ── Sub-tab Correlaciones
    with sub_corr:'''

content = content.replace(old_corr, new_at_tab)
print("✅ Tab Análisis Técnico insertado en Mercado")

with open("dashboard.py", "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
