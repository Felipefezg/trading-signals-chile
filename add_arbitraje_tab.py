"""
Script para agregar el tab de arbitraje al dashboard existente.
Modifica dashboard.py en ~/trading_signals/
"""
import re

dashboard_path = "/Users/felipefernandez/trading_signals/dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar import de arbitraje después de performance
old_import = "from engine.performance import get_metricas_performance, get_benchmarks, CAPITAL_INICIAL"
new_import = """from engine.performance import get_metricas_performance, get_benchmarks, CAPITAL_INICIAL
from data.arbitraje import get_resumen_arbitraje, COSTOS"""

content = content.replace(old_import, new_import)

# 2. Agregar tab_arb a la lista de tabs
old_tabs = 'tab_señales, tab_perf, tab_opciones, tab_ib, tab_ipsa, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist, tab_bt = st.tabs(['
new_tabs = 'tab_señales, tab_perf, tab_arb, tab_opciones, tab_ib, tab_ipsa, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist, tab_bt = st.tabs(['
content = content.replace(old_tabs, new_tabs)

# 3. Agregar "🔀 ARBITRAJE" en la lista de nombres de tabs
old_tab_names = '"🎯 SEÑALES", "💹 PERFORMANCE", "⚙️ OPCIONES"'
new_tab_names = '"🎯 SEÑALES", "💹 PERFORMANCE", "🔀 ARBITRAJE", "⚙️ OPCIONES"'
content = content.replace(old_tab_names, new_tab_names)

# 4. Agregar el contenido del tab arbitraje antes del tab opciones
tab_arbitraje = '''
# ── TAB ARBITRAJE ─────────────────────────────────────────────────────────────
with tab_arb:
    st.markdown("### 🔀 Arbitraje — Detección de Brechas de Precio")
    st.caption("Monitoreo de spreads entre NYSE y Bolsa Santiago. Alertas automáticas cuando el spread neto supera el umbral de rentabilidad.")

    with st.spinner("Calculando spreads..."):
        resumen_arb = get_resumen_arbitraje()

    # Header con tipo de cambio y oportunidades
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("CLP/USD", f"{resumen_arb.get('clp_usd', 0):,.2f}")
    with col2: st.metric("PARES ADR MONITOREADOS", len(resumen_arb.get("spreads_adr", [])))
    with col3: st.metric("OPORTUNIDADES NETAS", resumen_arb.get("oportunidades", 0))
    with col4:
        mejor = resumen_arb.get("mejor_spread")
        if mejor:
            st.metric("MAYOR SPREAD BRUTO", f"{abs(mejor['spread_bruto_pct']):.3f}%", delta=mejor['oportunidad'])

    st.markdown(f"""
    <div style="background:#0d1117;border:1px solid #1e293b;border-radius:8px;padding:0.6rem 1rem;margin:0.75rem 0;font-size:0.75rem;color:#64748b">
    <span style="color:#38bdf8;font-weight:700">COSTOS ESTIMADOS</span> &nbsp;·&nbsp;
    Comisión IB: <span style="color:#f1f5f9">{COSTOS['comision_ib_pct']}%</span> &nbsp;·&nbsp;
    Spread FX: <span style="color:#f1f5f9">{COSTOS['spread_fx_pct']}%</span> &nbsp;·&nbsp;
    Costo total ida/vuelta: <span style="color:#f1f5f9">{COSTOS['costo_total_pct']}%</span> &nbsp;·&nbsp;
    Umbral mínimo: <span style="color:#22c55e">{COSTOS['umbral_minimo_pct']}%</span> &nbsp;·&nbsp;
    Alerta alta: <span style="color:#ef4444">{COSTOS['umbral_alerta_pct']}%</span>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Spreads ADR
    st.markdown("#### 📊 Spreads ADR — NYSE vs Bolsa Santiago")
    spreads_adr = resumen_arb.get("spreads_adr", [])

    if spreads_adr:
        for s in spreads_adr:
            spread_bruto = s["spread_bruto_pct"]
            spread_neto  = s["spread_neto_pct"]
            op           = s["oportunidad"]
            color_op     = "#ef4444" if op == "ALTA" else ("#f59e0b" if op == "MEDIA" else ("#22c55e" if op == "BAJA" else "#334155"))
            color_spread = "#22c55e" if spread_bruto > 0 else "#ef4444"

            with st.expander(
                f"{s['color']} {s['nombre']}  ·  "
                f"Spread bruto: {spread_bruto:+.3f}%  ·  "
                f"Spread neto: {spread_neto:+.3f}%  ·  {op}"
            ):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Sector:** {s['sector']}")
                    st.markdown(f"**Descripción:** {s['descripcion']}")
                    st.markdown(f"**Ratio ADR:** 1 ADR = {s['ratio']} acción(es) local(es)")

                with col2:
                    st.markdown("**Precios**")
                    st.markdown(f"NYSE `{s['nyse_ticker'] if 'nyse_ticker' in s else ''}`: USD **{s['precio_nyse_usd']:,.2f}** → CLP **{s['precio_nyse_clp']:,.0f}**")
                    st.markdown(f"Santiago: CLP **{s['precio_stgo_clp']:,.0f}**")
                    diferencia_clp = s["precio_stgo_clp"] - s["precio_nyse_clp"]
                    st.markdown(f"Diferencia: CLP **{diferencia_clp:+,.0f}**")

                with col3:
                    st.markdown("**Análisis**")
                    st.markdown(f"Spread bruto: **{spread_bruto:+.3f}%**")
                    st.markdown(f"Costo transac: **-{COSTOS['costo_total_pct']}%**")
                    st.markdown(f"Spread neto: **{spread_neto:+.3f}%**")
                    st.markdown(f'<span style="color:{color_op};font-weight:700">{op}</span>', unsafe_allow_html=True)

                if op != "SIN OPORTUNIDAD":
                    st.divider()
                    st.markdown(f"**🎯 Acción sugerida:** `{s['accion_arbitraje']}`")
                    st.markdown(f"**Mercado caro:** {s['mercado_caro']} &nbsp; | &nbsp; **Mercado barato:** {s['mercado_barato']}")
                    st.caption("⚠️ Verificar liquidez en ambos mercados antes de ejecutar. El arbitraje requiere ejecución simultánea.")

    st.divider()

    # ── BTC Spread
    st.markdown("#### ₿ Spread BTC — Buda.com vs Internacional")
    btc = resumen_arb.get("spread_btc", {})
    if btc:
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("BTC BUDA (CLP)", f"${btc.get('btc_buda_clp',0):,.0f}")
        with col2: st.metric("BTC GLOBAL (CLP)", f"${btc.get('btc_global_clp',0):,.0f}")
        with col3: st.metric("SPREAD BRUTO", f"{btc.get('spread_bruto_pct',0):+.3f}%")
        with col4:
            neto = btc.get("spread_neto_pct", 0)
            color = "normal" if neto > 0 else "inverse"
            st.metric("SPREAD NETO", f"{neto:+.3f}%", delta=btc.get("oportunidad",""))

        if btc.get("oportunidad") in ("ALTA", "MEDIA"):
            st.warning(f"⚡ Oportunidad BTC: {btc['accion_arbitraje']} | Spread neto: {btc.get('spread_neto_pct',0):+.3f}%")

    st.divider()

    # ── Explicación arbitraje ADR
    st.markdown("#### 📚 Cómo funciona el arbitraje ADR")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **¿Qué es un ADR?**
        Un ADR (American Depositary Receipt) es un certificado que representa acciones de una empresa extranjera
        que cotiza en NYSE. Permite a inversores USA comprar acciones chilenas en dólares.

        **¿Por qué existen spreads?**
        - Diferencias horarias entre mercados
        - Costos de conversión FX
        - Liquidez diferente en cada mercado
        - Flujos de capital asimétricos
        - Noticias que impactan un mercado antes que el otro
        """)
    with col2:
        st.markdown("""
        **¿Cómo ejecutar el arbitraje?**
        1. Detectar spread > 0.5% neto
        2. Comprar en mercado barato
        3. Vender simultáneamente en mercado caro
        4. La ganancia = spread - costos

        **Riesgos:**
        - Riesgo de ejecución (no simultaneidad)
        - Movimiento FX entre compra y venta
        - Liquidez insuficiente en Santiago
        - Costos ocultos (custody, liquidación T+2)
        """)

'''

# Insertar tab arbitraje antes de "# ── TAB OPCIONES"
old_marker = "# ── TAB OPCIONES"
content = content.replace(old_marker, tab_arbitraje + old_marker, 1)

with open(dashboard_path, "w") as f:
    f.write(content)

print("✅ Tab arbitraje agregado al dashboard")
print(f"Líneas totales: {len(content.splitlines())}")
