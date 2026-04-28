"""
Script para integrar CMF Hechos Esenciales al dashboard.
Agrega sub-tab CMF dentro del tab Mercado.
"""

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar import
if "from data.cmf" not in content:
    content = content.replace(
        "from data.arbitraje import get_resumen_arbitraje, COSTOS",
        "from data.arbitraje import get_resumen_arbitraje, COSTOS\n"
        "from data.cmf import get_hechos_esenciales, get_resumen_cmf"
    )
    print("✅ Import CMF agregado")

# 2. Agregar sub-tab CMF en tab Mercado
old_subtabs = '    sub_ipsa, sub_macro, sub_corr, sub_noticias = st.tabs([\n        "IPSA", "Macro Chile", "Correlaciones", "Noticias"\n    ])'
new_subtabs = '    sub_ipsa, sub_macro, sub_cmf, sub_corr, sub_noticias = st.tabs([\n        "IPSA", "Macro Chile", "CMF Hechos Esenciales", "Correlaciones", "Noticias"\n    ])'
content = content.replace(old_subtabs, new_subtabs)
print("✅ Sub-tab CMF agregado")

# 3. Insertar contenido del tab CMF antes de sub_corr
old_corr = '    # ── Sub-tab Correlaciones\n    with sub_corr:'
new_cmf = '''    # ── Sub-tab CMF
    with sub_cmf:
        st.markdown("**CMF — Hechos Esenciales** · Actualización cada 1 minuto")
        st.caption("Hechos materiales de empresas fiscalizadas por la CMF. Fuente oficial: cmfchile.cl")

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            solo_ipsa = st.toggle("Solo empresas IPSA", value=True, key="toggle_cmf_ipsa")
        with col_f2:
            filtro_rel = st.selectbox("Relevancia", ["Todas", "ALTA", "MEDIA"], key="sel_cmf_rel")
        with col_f3:
            if st.button("Actualizar CMF", use_container_width=True, key="btn_cmf_refresh"):
                st.rerun()

        with st.spinner("Cargando hechos esenciales..."):
            resumen_cmf = get_resumen_cmf()

        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Total 7 días", resumen_cmf.get("total", 0))
        with col2: st.metric("Empresas IPSA", resumen_cmf.get("ipsa", 0))
        with col3: st.metric("Alta relevancia", resumen_cmf.get("alta_relevancia", 0))
        with col4: st.metric("IPSA + Alta rel.", resumen_cmf.get("ipsa_alta", 0))

        st.divider()

        # Listado de hechos
        hechos = get_hechos_esenciales(solo_ipsa=solo_ipsa, limit=100)
        if filtro_rel != "Todas":
            hechos = [h for h in hechos if h["relevancia"] == filtro_rel]

        if hechos:
            st.caption(f"{len(hechos)} hechos encontrados")
            for h in hechos:
                color = h["color"]
                ticker = h.get("ticker_ipsa", "")
                ticker_badge = f" [{ticker}]" if ticker else ""
                with st.expander(
                    f"{h['flecha']} {h['relevancia']}{ticker_badge}  ·  "
                    f"{h['entidad'][:50]}  ·  {h['materia'][:55]}"
                ):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**Entidad:** {h['entidad']}")
                        st.markdown(f"**Materia:** {h['materia']}")
                        st.caption(f"Fecha: {h['fecha']} · Nº {h['numero']}")
                        st.markdown(
                            f\'<span style="background:{color}22;color:{color};border:1px solid {color}44;\' +
                            f\'border-radius:4px;padding:2px 8px;font-size:0.72rem;font-weight:600">\' +
                            f\'{h["relevancia"]} · Impacto: {h["impacto"]}</span>\',
                            unsafe_allow_html=True
                        )
                    with col2:
                        if h.get("url"):
                            st.link_button("Ver documento →", h["url"])
                        if ticker:
                            st.markdown(f\'<div style="background:#1e293b;border-radius:5px;padding:0.4rem;text-align:center;color:#38bdf8;font-weight:700">{ticker}</div>\', unsafe_allow_html=True)
        else:
            st.info("Sin hechos esenciales para los filtros seleccionados.")

    # ── Sub-tab Correlaciones
    with sub_corr:'''

content = content.replace(old_corr, new_cmf)
print("✅ Contenido CMF insertado")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
