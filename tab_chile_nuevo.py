# ── TAB CHILE ─────────────────────────────────────────────────────────────────
with tab_chile:
    st.markdown("### 📊 Macro Chile — Análisis Completo")
    with st.spinner(""):
        macro_cl = get_macro_chile_completo()
        ctx      = get_contexto_macro()
        bcch     = get_resumen_bcch()
        clp      = bcch.get("CLP/USD", 892.0)

    # Ciclo económico
    ciclo = ctx.get("ciclo", "NEUTRO")
    ciclo_colors = {
        "EXPANSIÓN":   "#22c55e",
        "MODERADO":    "#f59e0b",
        "NEUTRO":      "#64748b",
        "CONTRACCIÓN": "#ef4444",
    }
    ciclo_color = ciclo_colors.get(ciclo, "#64748b")
    senales_html = "".join([
        f'<div style="margin-top:3px;color:#94a3b8;font-size:0.78rem">{s}</div>'
        for s in ctx.get("señales", [])
    ])
    st.markdown(
        f'<div style="background:#0d1117;border:1px solid {ciclo_color}44;'
        f'border-left:3px solid {ciclo_color};border-radius:8px;'
        f'padding:0.75rem 1.25rem;margin-bottom:1rem">'
        f'<span style="color:{ciclo_color};font-size:1rem;font-weight:700">'
        f'CICLO ECONÓMICO: {ciclo}</span>{senales_html}</div>',
        unsafe_allow_html=True
    )

    # Indicadores principales
    ids_principales = ["dolar","uf","tpm","ipc","imacec","libra_cobre","tasa_desempleo","bitcoin"]
    cols_macro = st.columns(4)
    for i, ind_id in enumerate(ids_principales):
        dato = macro_cl.get(ind_id)
        if not dato:
            continue
        with cols_macro[i % 4]:
            var    = dato.get("variacion")
            alerta = dato.get("alerta")
            nombre = f"{dato['icono']} {dato['nombre']}"
            if alerta:
                nombre += f" {alerta['nivel']}"
            valor_fmt = f"{dato['valor']:,.2f} {dato['unidad']}"
            st.metric(nombre.upper(), valor_fmt, delta=f"{var:+.3f}%" if var else None)

    # Alertas activas
    alertas = ctx.get("alertas", [])
    if alertas:
        st.divider()
        st.markdown("**⚠️ Alertas Activas**")
        for a in alertas:
            st.markdown(
                f'<div style="background:{a["color"]}22;border:1px solid {a["color"]}44;'
                f'border-radius:6px;padding:0.4rem 0.8rem;margin:0.2rem 0;'
                f'color:{a["color"]};font-size:0.82rem">⚠️ {a["nivel"]}: {a["mensaje"]}</div>',
                unsafe_allow_html=True
            )

    st.divider()

    # Gráficos históricos
    col_g1, col_g2 = st.columns(2)
    for idx, ind_id in enumerate(["dolar", "libra_cobre", "tpm", "uf"]):
        dato = macro_cl.get(ind_id)
        if not dato or not dato.get("historico"):
            continue
        hist    = dato["historico"]
        fechas  = [h["fecha"] for h in reversed(hist)]
        valores = [h["valor"] for h in reversed(hist)]
        fig_cl = go.Figure(go.Scatter(
            x=fechas, y=valores, mode="lines",
            line=dict(color="#38bdf8", width=1.5),
            fill="tozeroy", fillcolor="rgba(56,189,248,0.05)"
        ))
        fig_cl.update_layout(
            title=f"{dato['icono']} {dato['nombre']}",
            paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
            font=dict(color="#94a3b8", size=10),
            margin=dict(t=35, b=20, l=40, r=10), height=200,
            xaxis=dict(gridcolor="#1e293b", tickfont=dict(size=8)),
            yaxis=dict(gridcolor="#1e293b"),
            showlegend=False,
        )
        with col_g1 if idx % 2 == 0 else col_g2:
            st.plotly_chart(fig_cl, use_container_width=True)

    st.divider()

    # Cochilco
    with st.spinner(""):
        cochilco = get_precios_cochilco()
    if cochilco:
        st.markdown("**🔶 Cobre — Cochilco**")
        cols_co = st.columns(min(len(cochilco), 4))
        for i, (k, v) in enumerate(list(cochilco.items())[:4]):
            with cols_co[i]:
                st.metric(k[:25], v)

    st.divider()

    # BTC Spread
    with st.spinner(""):
        spread = get_spread_btc(clp or 892.0)
    if spread:
        st.markdown("**₿ BTC Spread Local vs Global**")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("BTC BUDA", f"${spread['btc_local_clp']:,.0f}")
        with col2: st.metric("BTC GLOBAL", f"${spread['btc_global_clp']:,.0f}")
        with col3: st.metric("SPREAD %", f"{spread['spread_pct']}%", delta=spread["direccion"])
        with col4: st.metric("BTC USD", f"${spread['btc_usd']:,.0f}")
        if spread.get("alerta"):
            st.error(f"🚨 Spread BTC {spread['direccion']} {abs(spread['spread_pct'])}%")
        else:
            st.success("✅ Spread BTC en rango normal")

    st.divider()

    # Polymarket Chile
    st.markdown("**🌐 Polymarket Chile**")
    with st.spinner(""):
        df_poly_cl = get_mercados_chile(limit=200)
    if not df_poly_cl.empty:
        for _, row in df_poly_cl.iterrows():
            prob = row["probabilidad"]
            if prob is None:
                continue
            with st.expander(
                f"{'▲' if prob > 50 else '▼'} {row['pregunta'][:90]}  ·  "
                f"{prob}%  ·  {'⭐' * row.get('relevancia', 1)}"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"Prob: {prob}% · Activos: {', '.join(row['chile_impact'])}")
                with col2:
                    try:
                        st.caption(f"Vol: USD {float(row.get('volumen_usd', 0)):,.0f}")
                    except:
                        pass
                st.link_button("Ver →", row.get("url", ""))

