"""
Script para agregar tab de optimización de portafolio al dashboard.
"""

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar import
if "portafolio" not in content:
    content = content.replace(
        "from engine.correlaciones import",
        "from engine.portafolio import get_analisis_portafolio, UNIVERSO_DEFAULT, TASA_LIBRE_RIESGO\nfrom engine.correlaciones import"
    )
    print("✅ Import portafolio agregado")

# 2. Agregar tab_port a la lista de tabs
content = content.replace(
    'tab_señales, tab_perf, tab_arb, tab_corr, tab_opciones,',
    'tab_señales, tab_perf, tab_arb, tab_corr, tab_port, tab_opciones,'
)

# 3. Agregar nombre del tab
content = content.replace(
    '"📡 CORRELACIONES", "⚙️ OPCIONES"',
    '"📡 CORRELACIONES", "🧮 PORTAFOLIO", "⚙️ OPCIONES"'
)

# 4. Insertar tab antes de opciones
TAB_PORTAFOLIO = '''
# ── TAB PORTAFOLIO ────────────────────────────────────────────────────────────
with tab_port:
    st.markdown("### 🧮 Optimización de Portafolio — Markowitz + VaR")
    st.caption(f"Universo: {', '.join(UNIVERSO_DEFAULT.values())} · Tasa libre riesgo: {TASA_LIBRE_RIESGO*100}% (TPM Chile)")

    col_p1, col_p2 = st.columns([1, 1])
    with col_p1:
        capital = st.number_input("Capital (USD)", value=100_000, step=10_000, min_value=10_000)
    with col_p2:
        periodo_port = st.selectbox("Período histórico", ["1y", "2y", "3y"], index=1)

    if st.button("🧮 Calcular Portafolio Óptimo", type="primary", use_container_width=True):
        with st.spinner("Optimizando portafolio con Markowitz..."):
            st.session_state.analisis_port = get_analisis_portafolio(capital, periodo_port)

    analisis = st.session_state.get("analisis_port")

    if not analisis:
        st.info("Haz click en 'Calcular Portafolio Óptimo' para ejecutar la optimización.")
        with st.spinner("Cargando análisis inicial..."):
            analisis = get_analisis_portafolio(capital=100_000, periodo="2y")
            st.session_state.analisis_port = analisis

    if analisis:
        # ── Comparación de portafolios
        st.divider()
        st.markdown("#### 📊 Comparación de Estrategias")
        col1, col2, col3 = st.columns(3)

        for col, port_key, titulo, color in [
            (col1, "port_sharpe",  "🏆 Máximo Sharpe",     "#38bdf8"),
            (col2, "port_min_vol", "🛡️ Mínima Volatilidad", "#22c55e"),
            (col3, "port_equal",   "⚖️ Pesos Iguales",      "#94a3b8"),
        ]:
            port = analisis[port_key]
            with col:
                st.markdown(
                    f\'<div style="background:#0d1117;border:1px solid {color}44;border-top:2px solid {color};\' +
                    f\'border-radius:8px;padding:0.75rem 1rem">\' +
                    f\'<div style="color:{color};font-weight:700;margin-bottom:0.5rem">{titulo}</div>\' +
                    f\'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.3rem">\' +
                    f\'<div style="color:#64748b;font-size:0.72rem">RETORNO</div><div style="color:#f1f5f9;font-family:monospace;font-size:0.85rem">{port["retorno"]*100:.1f}%</div>\' +
                    f\'<div style="color:#64748b;font-size:0.72rem">VOLATILIDAD</div><div style="color:#f1f5f9;font-family:monospace;font-size:0.85rem">{port["vol"]*100:.1f}%</div>\' +
                    f\'<div style="color:#64748b;font-size:0.72rem">SHARPE</div><div style="color:{color};font-family:monospace;font-weight:700;font-size:0.85rem">{port["sharpe"]:.2f}</div>\' +
                    f\'</div></div>\',
                    unsafe_allow_html=True
                )

        st.divider()

        # ── Pesos portafolio Sharpe + gráfico
        st.markdown("#### 🥧 Portafolio Óptimo — Máximo Sharpe")
        col1, col2 = st.columns([2, 3])
        port_sharpe = analisis["port_sharpe"]
        with col1:
            pesos_sorted = sorted(port_sharpe["pesos"].items(), key=lambda x: -x[1])
            for ticker, peso in pesos_sorted:
                nombre = UNIVERSO_DEFAULT.get(ticker, ticker)
                bar = "█" * int(peso * 25)
                color = "#38bdf8" if peso >= 0.15 else ("#22c55e" if peso >= 0.05 else "#475569")
                st.markdown(
                    f\'<div style="display:flex;justify-content:space-between;padding:0.25rem 0;border-bottom:1px solid #1e293b">\' +
                    f\'<span style="color:#94a3b8;font-size:0.82rem">{nombre}</span>\' +
                    f\'<span style="color:{color};font-family:monospace;font-weight:700">{peso*100:.1f}%</span></div>\',
                    unsafe_allow_html=True
                )
        with col2:
            labels = [UNIVERSO_DEFAULT.get(t, t) for t, p in pesos_sorted if p > 0.01]
            values = [p for t, p in pesos_sorted if p > 0.01]
            fig_pie = go.Figure(go.Pie(
                labels=labels, values=values,
                hole=0.4,
                marker=dict(colors=["#38bdf8","#22c55e","#f59e0b","#a78bfa","#fb923c","#34d399","#f472b6","#94a3b8"]),
                textfont=dict(size=10, color="white"),
            ))
            fig_pie.update_layout(
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                font=dict(color="#94a3b8"),
                margin=dict(t=20,b=20,l=20,r=20), height=280,
                showlegend=False,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()

        # ── VaR
        st.markdown("#### ⚠️ Value at Risk (VaR) — Portafolio Máximo Sharpe")
        var = analisis["var_sharpe"]
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("VaR 95% DIARIO", f"USD {var['var_95_usd']:,.0f}", delta=f"-{var['var_95_pct']}%")
        with col2: st.metric("VaR 99% DIARIO", f"USD {var['var_99_usd']:,.0f}", delta=f"-{var['var_99_pct']}%")
        with col3: st.metric("CVaR 95% (peor 5%)", f"USD {var['cvar_95_usd']:,.0f}", delta=f"-{var['cvar_95_pct']}%")
        with col4: st.metric("VaR ANUAL 95%", f"USD {var['var_95_usd']*np.sqrt(252):,.0f}")

        st.markdown(
            f\'<div style="background:#0d1117;border:1px solid #1e293b;border-radius:8px;padding:0.6rem 1rem;font-size:0.78rem;color:#64748b">\' +
            f\'Retorno diario esperado: <span style="color:#22c55e">{var["retorno_diario_pct"]:+.3f}%</span> &nbsp;·&nbsp; \' +
            f\'Volatilidad diaria: <span style="color:#f1f5f9">{var["vol_diaria_pct"]:.3f}%</span> &nbsp;·&nbsp; \' +
            f\'Retorno anual esperado: <span style="color:#22c55e">{var["retorno_anual_pct"]:+.1f}%</span> &nbsp;·&nbsp; \' +
            f\'Volatilidad anual: <span style="color:#f1f5f9">{var["vol_anual_pct"]:.1f}%</span> &nbsp;·&nbsp; \' +
            f\'Obs.: <span style="color:#f1f5f9">{var["n_obs"]} días</span></div>\',
            unsafe_allow_html=True
        )

        st.divider()

        # ── Contribución al riesgo
        st.markdown("#### 🎯 Contribución al Riesgo por Activo")
        contrib = analisis["contribucion"]
        if contrib:
            contrib_sorted = sorted(contrib.items(), key=lambda x: -x[1]["contrib_riesgo"])
            for ticker, c in contrib_sorted:
                peso_pct   = c["peso"]
                riesgo_pct = c["contrib_riesgo"]
                diff = riesgo_pct - peso_pct
                color_diff = "#ef4444" if diff > 5 else ("#22c55e" if diff < -5 else "#64748b")
                st.markdown(
                    f\'<div style="display:flex;align-items:center;gap:1rem;padding:0.3rem 0;border-bottom:1px solid #1e293b">\' +
                    f\'<span style="color:#94a3b8;font-size:0.82rem;width:160px">{c["nombre"]}</span>\' +
                    f\'<span style="color:#f1f5f9;font-family:monospace;font-size:0.82rem;width:80px">Peso: {peso_pct:.1f}%</span>\' +
                    f\'<span style="color:#38bdf8;font-family:monospace;font-size:0.82rem;width:100px">Riesgo: {riesgo_pct:.1f}%</span>\' +
                    f\'<span style="color:{color_diff};font-size:0.75rem">{("↑ concentra riesgo" if diff > 5 else ("↓ diversifica" if diff < -5 else "~neutral"))}</span>\' +
                    f\'</div>\',
                    unsafe_allow_html=True
                )

        st.divider()

        # ── Stats individuales
        st.markdown("#### 📈 Estadísticas por Activo")
        stats = analisis["retornos_stats"]
        rows = []
        for ticker, s in stats.items():
            nombre = UNIVERSO_DEFAULT.get(ticker, ticker)
            rows.append({
                "Activo": nombre,
                "Ticker": ticker,
                "Retorno anual": f"{s['retorno_anual']:+.1f}%",
                "Volatilidad": f"{s['vol_anual']:.1f}%",
                "Sharpe": f"{s['sharpe']:.2f}",
            })
        df_stats = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
        st.dataframe(df_stats, use_container_width=True, hide_index=True)

        st.divider()

        # ── Frontera eficiente
        st.markdown("#### 🌐 Frontera Eficiente de Markowitz")
        frontera = analisis.get("frontera", [])
        if frontera:
            vols     = [p["vol"] * 100 for p in frontera]
            retornos_f = [p["retorno"] * 100 for p in frontera]
            sharpes  = [p["sharpe"] for p in frontera]

            fig_frontera = go.Figure()
            fig_frontera.add_trace(go.Scatter(
                x=vols, y=retornos_f, mode="markers",
                marker=dict(
                    color=sharpes, colorscale="Viridis",
                    size=5, showscale=True,
                    colorbar=dict(title="Sharpe", tickfont=dict(color="#94a3b8")),
                ),
                name="Portafolios",
                hovertemplate="Vol: %{x:.1f}%<br>Ret: %{y:.1f}%<extra></extra>",
            ))
            # Marcar portafolio óptimo
            fig_frontera.add_trace(go.Scatter(
                x=[port_sharpe["vol"]*100], y=[port_sharpe["retorno"]*100],
                mode="markers", marker=dict(color="#ef4444", size=12, symbol="star"),
                name="Máx Sharpe",
            ))
            fig_frontera.update_layout(
                title="Frontera Eficiente — Retorno vs Volatilidad",
                xaxis_title="Volatilidad anual (%)",
                yaxis_title="Retorno anual (%)",
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                font=dict(color="#94a3b8", size=10),
                margin=dict(t=40,b=40,l=50,r=20), height=380,
                xaxis=dict(gridcolor="#1e293b"),
                yaxis=dict(gridcolor="#1e293b"),
                showlegend=True,
                legend=dict(bgcolor="#0d1117", font=dict(color="#94a3b8")),
            )
            st.plotly_chart(fig_frontera, use_container_width=True)
            st.caption("⭐ Estrella roja = portafolio de máximo Sharpe · Color = ratio Sharpe (amarillo=alto)")

'''

old_marker = "# ── TAB OPCIONES"
if old_marker in content:
    content = content.replace(old_marker, TAB_PORTAFOLIO + old_marker, 1)
    print("✅ Tab portafolio insertado")
else:
    print("❌ Marker no encontrado")

# Agregar import numpy si no existe
if "import numpy as np" not in content:
    content = content.replace(
        "import streamlit as st",
        "import streamlit as st\nimport numpy as np"
    )

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
