"""
Integra detección de volumen anormal al dashboard.
Agrega sub-tab en tab Mercado.
"""

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Import
if "from data.volumen" not in content:
    content = content.replace(
        "from data.cmf import get_hechos_esenciales, get_resumen_cmf",
        "from data.cmf import get_hechos_esenciales, get_resumen_cmf\n"
        "from data.volumen import get_resumen_volumen, correlacionar_con_cmf"
    )
    print("✅ Import volumen agregado")

# 2. Agregar sub-tab Volumen en Mercado
old_subtabs = '    sub_ipsa, sub_macro, sub_cmf, sub_corr, sub_noticias = st.tabs([\n        "IPSA", "Macro Chile", "CMF Hechos Esenciales", "Correlaciones", "Noticias"\n    ])'
new_subtabs = '    sub_ipsa, sub_macro, sub_cmf, sub_vol, sub_corr, sub_noticias = st.tabs([\n        "IPSA", "Macro Chile", "CMF Hechos Esenciales", "Volumen Anormal", "Correlaciones", "Noticias"\n    ])'
content = content.replace(old_subtabs, new_subtabs)
print("✅ Sub-tab Volumen agregado")

# 3. Insertar contenido antes de sub_corr
old_corr_marker = '    # ── Sub-tab Correlaciones\n    with sub_corr:'
new_vol_content = '''    # ── Sub-tab Volumen Anormal
    with sub_vol:
        st.markdown("**Volumen Anormal — IPSA**")
        st.caption("Detecta acciones con volumen significativamente mayor a su promedio histórico. Señal de actividad inusual.")

        col1, col2 = st.columns([3,1])
        with col2:
            if st.button("Actualizar volumen", use_container_width=True, key="btn_vol_refresh"):
                st.rerun()

        with st.spinner("Analizando volumen..."):
            resumen_vol = get_resumen_volumen()
            alertas_vol = correlacionar_con_cmf(resumen_vol.get("top_alertas", []))

        # KPIs
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Acciones analizadas", resumen_vol.get("total_analizados", 0))
        with col2: st.metric("Alertas de volumen", resumen_vol.get("alertas", 0))
        with col3: st.metric("Alertas altas (>3x)", resumen_vol.get("alertas_altas", 0))

        st.divider()

        if alertas_vol:
            st.markdown("**Alertas activas**")
            for a in alertas_vol:
                color    = a["color"]
                sc       = a["señal_color"]
                cmf_badge = ""
                if a.get("conviccion_extra"):
                    cmf_badge = " ⭐ CMF"
                with st.expander(
                    f"[{a['ratio']}x] {a['nombre']}  ·  {a['señal']}  ·  "
                    f"{a['var_pct']:+.2f}%{cmf_badge}"
                ):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**Ticker:** `{a['ticker']}`")
                        st.markdown(f"**Precio:** {a['precio']:,.2f} ({a['var_pct']:+.2f}%)")
                        st.markdown(
                            f\'<span style="background:{sc}22;color:{sc};border:1px solid {sc}44;\' +
                            f\'border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:700">\' +
                            f\'{a["señal"]}</span>\',
                            unsafe_allow_html=True
                        )
                    with col2:
                        st.markdown(f"**Volumen hoy:** {a['vol_actual']:,}")
                        st.markdown(f"**Promedio 20d:** {a['vol_promedio']:,}")
                        st.markdown(
                            f\'<span style="background:{color}22;color:{color};border:1px solid {color}44;\' +
                            f\'border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:700">\' +
                            f\'{a["ratio"]}x PROMEDIO · {a["nivel"]}</span>\',
                            unsafe_allow_html=True
                        )
                    with col3:
                        if a.get("conviccion_extra"):
                            st.markdown("**CMF correlacionado**")
                            st.caption(f"Hecho esencial: {a.get('cmf_materia','')}")
                            st.caption(f"Relevancia: {a.get('cmf_relevancia','')}")
                            st.markdown("⭐ **Alta convicción**")
                        else:
                            st.caption("Sin hecho CMF correlacionado")

                    st.divider()
                    if a["señal"] == "ACUMULACIÓN":
                        st.caption("Volumen alto + precio sube → compradores institucionales activos → posible señal de COMPRA")
                    elif a["señal"] == "DISTRIBUCIÓN":
                        st.caption("Volumen alto + precio baja → vendedores institucionales activos → posible señal de VENTA")
                    else:
                        st.caption("Volumen alto + precio plano → indecisión — esperar confirmación de dirección")

        else:
            st.info("Sin alertas de volumen anormal en este momento. Las alertas aparecen cuando una acción supera 2x su volumen promedio.")

        # Tabla completa
        st.divider()
        st.markdown("**Todas las acciones — Volumen relativo**")
        todos = resumen_vol.get("todos", [])
        if todos:
            rows_vol = []
            for a in todos:
                rows_vol.append({
                    "Acción":    a["nombre"],
                    "Ticker":    a["ticker"],
                    "Ratio":     a["ratio"],
                    "Vol hoy":   a["vol_actual"],
                    "Prom 20d":  a["vol_promedio"],
                    "Precio":    a["precio"],
                    "Var %":     a["var_pct"],
                    "Señal":     a["señal"],
                })
            df_vol = pd.DataFrame(rows_vol).sort_values("Ratio", ascending=False)
            st.dataframe(df_vol, use_container_width=True, hide_index=True,
                column_config={
                    "Ratio": st.column_config.NumberColumn("Ratio", format="%.2fx"),
                    "Var %": st.column_config.NumberColumn(format="%+.2f%%"),
                    "Vol hoy": st.column_config.NumberColumn(format="%,d"),
                    "Prom 20d": st.column_config.NumberColumn(format="%,d"),
                })

    # ── Sub-tab Correlaciones
    with sub_corr:'''

content = content.replace(old_corr_marker, new_vol_content)
print("✅ Tab volumen insertado")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
