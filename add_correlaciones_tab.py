"""
Script para agregar tab de correlaciones dinámicas al dashboard.
"""

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar import
if "correlaciones" not in content:
    content = content.replace(
        "from engine.nlp_sentiment import analizar_noticias_batch, get_resumen_sentiment, get_sentiment_por_activo",
        "from engine.nlp_sentiment import analizar_noticias_batch, get_resumen_sentiment, get_sentiment_por_activo\n"
        "from engine.correlaciones import get_correlaciones_ipsa_completo, get_correlacion_rodante, get_divergencias_correlacion, get_correlaciones_ipsa_interno, ACTIVOS_CHILE, ACTIVOS_MACRO"
    )
    print("✅ Import correlaciones agregado")

# 2. Agregar tab_corr a la lista de tabs
old_tabs_def = 'tab_señales, tab_perf, tab_arb, tab_opciones, tab_ib, tab_ipsa, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist, tab_bt = st.tabs(['
new_tabs_def = 'tab_señales, tab_perf, tab_arb, tab_corr, tab_opciones, tab_ib, tab_ipsa, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist, tab_bt = st.tabs(['
content = content.replace(old_tabs_def, new_tabs_def)

# 3. Agregar nombre del tab
old_tab_names = '"🔀 ARBITRAJE", "⚙️ OPCIONES"'
new_tab_names = '"🔀 ARBITRAJE", "📡 CORRELACIONES", "⚙️ OPCIONES"'
content = content.replace(old_tab_names, new_tab_names)

# 4. Insertar el tab antes de opciones
TAB_CORRELACIONES = '''
# ── TAB CORRELACIONES ────────────────────────────────────────────────────────
with tab_corr:
    st.markdown("### 📡 Correlaciones Dinámicas — Chile vs Macro Global")
    st.caption("Cómo se mueven los activos chilenos en relación a variables macro globales. Período: 90 días.")

    col_periodo, _ = st.columns([1, 3])
    with col_periodo:
        periodo_sel = st.selectbox("Período", ["30d", "60d", "90d", "180d"], index=2)

    with st.spinner("Calculando correlaciones..."):
        corrs_ech    = get_correlaciones_ipsa_completo(periodo_sel)
        corr_rodante = get_correlacion_rodante("ECH", "HG=F", 30, "180d")
        divergencias = get_divergencias_correlacion(periodo_sel)

    # ── Heatmap ECH vs Macro
    st.markdown("#### 📊 ECH (IPSA) vs Macro Global")
    if corrs_ech:
        for c in corrs_ech:
            v     = c["corr"]
            bg, fg = c["bg"], c["fg"]
            barra_pos = int(abs(v) * 10)
            barra = ("█" * barra_pos).ljust(10)
            sign  = "+" if v >= 0 else "-"
            color_bar = "#22c55e" if v > 0 else "#ef4444"
            st.markdown(
                f\'<div style="display:flex;align-items:center;gap:1rem;padding:0.3rem 0;border-bottom:1px solid #1e293b">\' +
                f\'<span style="color:{color_bar};font-family:monospace;font-size:0.85rem;width:120px">{sign}{barra} {v:+.3f}</span>\' +
                f\'<span style="color:#f1f5f9;font-size:0.82rem;width:140px">{c["nombre"]}</span>\' +
                f\'<span style="color:#64748b;font-size:0.75rem">{c["señal"]}</span></div>\',
                unsafe_allow_html=True
            )

    st.divider()

    # ── Correlación rodante ECH-Cobre
    st.markdown("#### 📈 Correlación Rodante ECH — Cobre (ventana 30 días)")
    if corr_rodante:
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("ACTUAL", f"{corr_rodante['actual']:+.3f}")
        with col2: st.metric("PROMEDIO", f"{corr_rodante['promedio']:+.3f}")
        with col3: st.metric("MÍNIMO", f"{corr_rodante['min']:+.3f}")
        with col4: st.metric("MÁXIMO", f"{corr_rodante['max']:+.3f}")

        # Gráfico de correlación rodante
        fechas  = corr_rodante["fechas"]
        valores = [v for v in corr_rodante["valores"] if v is not None]
        fechas_validas = corr_rodante["fechas"][-len(valores):]

        if valores:
            fig_rod = go.Figure()
            fig_rod.add_trace(go.Scatter(
                x=fechas_validas, y=valores, mode="lines",
                line=dict(color="#38bdf8", width=1.5),
                fill="tozeroy", fillcolor="rgba(56,189,248,0.06)",
                name="Correlación ECH-Cobre"
            ))
            fig_rod.add_hline(y=corr_rodante["promedio"], line_dash="dot",
                             line_color="#f59e0b",
                             annotation_text=f"Promedio: {corr_rodante['promedio']:.3f}",
                             annotation_font_color="#f59e0b")
            fig_rod.add_hline(y=0, line_color="#334155")
            fig_rod.update_layout(
                title="Correlación rodante ECH vs Cobre (30 días)",
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                font=dict(color="#94a3b8", size=10),
                margin=dict(t=40,b=30,l=40,r=20), height=250,
                xaxis=dict(gridcolor="#1e293b"),
                yaxis=dict(gridcolor="#1e293b", range=[-1,1]),
                showlegend=False,
            )
            st.plotly_chart(fig_rod, use_container_width=True)

    st.divider()

    # ── Divergencias de correlación
    st.markdown("#### ⚡ Divergencias de Correlación — Señales de Mispricing")
    st.caption("Cuando ECH se mueve diferente a lo que sugieren sus correlaciones históricas → oportunidad.")
    if divergencias:
        for d in divergencias:
            color = d["color"]
            señal = d["señal"]
            with st.expander(
                f"{'▲' if d['divergencia'] > 0 else '▼'} {señal}  ·  "
                f"ECH real: {d['ech_real']:+.2f}%  ·  "
                f"Esperado: {d['ech_esperado']:+.2f}%  ·  "
                f"Divergencia: {d['divergencia']:+.2f}%"
            ):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Variable macro:** {d['nombre']}")
                    st.markdown(f"**Movimiento hoy:** {d['macro_mov']:+.2f}%")
                with col2:
                    st.markdown(f"**Correlación histórica:** {d['corr_hist']:+.3f}")
                    st.markdown(f"**ECH esperado:** {d['ech_esperado']:+.3f}%")
                with col3:
                    st.markdown(f"**ECH real:** {d['ech_real']:+.2f}%")
                    st.markdown(
                        f\'<span style="color:{color};font-weight:700;font-size:1rem">{señal}</span>\',
                        unsafe_allow_html=True
                    )
                if d["divergencia"] > 0:
                    st.caption("💡 ECH cotiza por debajo de lo esperado → posible oportunidad de COMPRA")
                else:
                    st.caption("💡 ECH cotiza por encima de lo esperado → posible oportunidad de VENTA")
    else:
        st.info("Sin divergencias significativas detectadas hoy (mercado cerrado o movimientos < 0.5%)")

    st.divider()

    # ── Matriz correlaciones IPSA interno
    st.markdown("#### 🔗 Correlaciones entre Acciones Chilenas")
    st.caption("Útil para diversificación — activos con baja correlación reducen riesgo del portafolio.")
    with st.spinner("Calculando matriz..."):
        corr_interno = get_correlaciones_ipsa_interno(periodo_sel)

    if not corr_interno.empty:
        # Mostrar como heatmap con colores
        import plotly.figure_factory as ff
        fig_heat = go.Figure(go.Heatmap(
            z=corr_interno.values,
            x=corr_interno.columns.tolist(),
            y=corr_interno.index.tolist(),
            colorscale=[
                [0.0, "#7f1d1d"],
                [0.3, "#450a0a"],
                [0.5, "#1e293b"],
                [0.7, "#14532d"],
                [1.0, "#166534"],
            ],
            zmid=0,
            text=corr_interno.values.round(2),
            texttemplate="%{text}",
            textfont=dict(size=9, color="white"),
            showscale=True,
        ))
        fig_heat.update_layout(
            title="Matriz de correlaciones — Acciones IPSA",
            paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
            font=dict(color="#94a3b8", size=9),
            margin=dict(t=40,b=60,l=120,r=20), height=420,
        )
        st.plotly_chart(fig_heat, use_container_width=True)
        st.caption("Verde = correlación positiva alta | Rojo = correlación negativa | Negro = sin correlación")

'''

# Insertar antes de "# ── TAB OPCIONES"
old_marker = "# ── TAB OPCIONES"
if old_marker in content:
    content = content.replace(old_marker, TAB_CORRELACIONES + old_marker, 1)
    print("✅ Tab correlaciones insertado")
else:
    print("❌ Marker no encontrado")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
