import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from streamlit_autorefresh import st_autorefresh
from data.polymarket import get_active_markets, get_mercados_chile
from data.yahoo_finance import get_precios_usa, get_precios_chile
from data.bcch import get_resumen_bcch
from data.buda import get_spread_btc
from data.noticias_chile import get_noticias_google
from data.historial import guardar_senales, get_historial, get_estadisticas, actualizar_resultado
from data.kalshi import get_kalshi_resumen
from data.macro_usa import get_macro_usa, get_correlaciones_chile
from data.ipsa import get_precios_ipsa, get_resumen_sectorial, get_top_bottom_ipsa, get_amplitud_mercado
from engine.divergence import calcular_divergencias
from engine.recomendaciones import consolidar_señales, generar_recomendaciones, enviar_alertas_nuevas
from engine.opciones import get_estrategias_opciones, SUBYACENTES_OPCIONES
from engine.backtesting import ejecutar_backtest, get_estadisticas_backtest

try:
    from engine.ib_executor import ejecutar_señales, get_posiciones_abiertas, get_resumen_cuenta
    IB_DISPONIBLE = True
except ImportError:
    IB_DISPONIBLE = False

st.set_page_config(page_title="Trading Signals", page_icon="📊", layout="wide")
st_autorefresh(interval=15 * 60 * 1000, key="autorefresh")

if "alertas_enviadas" not in st.session_state:
    st.session_state.alertas_enviadas = set()

st.title("📊 Trading Signals — Polymarket × Kalshi × Mercados")
col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.caption("Detección de divergencias entre mercados de predicción y activos financieros")
with col_refresh:
    st.caption(f"🔄 Actualizado: {datetime.now().strftime('%H:%M:%S')} | Refresh: 15 min")

tab_señales, tab_opciones, tab_ib, tab_ipsa, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist, tab_bt = st.tabs([
    "🎯 Señales", "⚙️ Opciones", "🤖 IB Trading", "🇨🇱 IPSA", "📊 Chile Macro",
    "🇺🇸 USA", "⚡ Divergencias", "🎰 Kalshi", "📰 Noticias", "📈 Historial", "🔬 Backtesting"
])

# ── TAB SEÑALES ───────────────────────────────────────────────────────────────
with tab_señales:
    st.subheader("🎯 Señales de Trading — Panel Ejecutivo")
    st.caption("Recomendaciones consolidadas desde Polymarket, Kalshi, Macro USA y Noticias Chile.")

    with st.spinner("Analizando todas las fuentes..."):
        poly_df     = get_mercados_chile(limit=200)
        kalshi_list = get_kalshi_resumen()
        macro_raw   = get_macro_usa()
        macro_corr  = get_correlaciones_chile(macro_raw)
        noticias    = get_noticias_google()
        activos     = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias)
        recomendaciones = generar_recomendaciones(activos)

    st.session_state.recomendaciones = recomendaciones

    if recomendaciones:
        n_alertas, st.session_state.alertas_enviadas = enviar_alertas_nuevas(
            recomendaciones, st.session_state.alertas_enviadas)
        if n_alertas > 0:
            st.success(f"📱 {n_alertas} alerta(s) enviada(s) a Telegram")

        compras = [r for r in recomendaciones if r["accion"] == "COMPRAR"]
        ventas  = [r for r in recomendaciones if r["accion"] == "VENDER"]
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("📊 Total", len(recomendaciones))
        with col2: st.metric("🟢 Comprar", len(compras))
        with col3: st.metric("🔴 Vender", len(ventas))
        with col4:
            avg_r = round(sum(r["riesgo"] for r in recomendaciones) / len(recomendaciones), 1)
            st.metric("⚠️ Riesgo prom.", f"{avg_r}/10")

        st.divider()
        top = recomendaciones[0]
        color_top = "🟢" if top["accion"] == "COMPRAR" else "🔴"
        h = top.get("horizonte", {})
        st.info(
            f"**Señal principal:** {color_top} **{top['accion']} {top['ib_ticker']}** "
            f"({top['descripcion']})  \n"
            f"Convicción: **{top['conviccion']}%** | Riesgo: **{top['riesgo']}/10** | "
            f"{h.get('emoji','')} **{h.get('dias','N/D')}** | Fuentes: **{', '.join(top['fuentes'])}**"
        )
        st.divider()

        for r in recomendaciones:
            accion = r["accion"]
            color  = "🟢" if accion == "COMPRAR" else "🔴"
            riesgo = r["riesgo"]
            h      = r.get("horizonte", {})
            rc     = "🟢" if riesgo <= 3 else ("🟡" if riesgo <= 6 else "🔴")
            ak     = f"{r['accion']}_{r['ib_ticker']}"
            ti     = "📱" if ak in st.session_state.alertas_enviadas else ""
            opt_badge = "⚙️" if r["ib_ticker"] in SUBYACENTES_OPCIONES else ""

            with st.expander(
                f"{color} **{accion} {r['ib_ticker']}** — {r['descripcion']}  |  "
                f"Conv: **{r['conviccion']}%**  |  Riesgo: {rc} **{riesgo}/10**  |  "
                f"{h.get('emoji','')} **{h.get('label','')}** {ti} {opt_badge}"
            ):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"### {color} {accion}")
                    st.markdown(f"**IB:** `{r['ib_ticker']}` | **Tipo:** {r['tipo']}")
                    st.markdown(f"**Descripción:** {r['descripcion']}")
                with col2:
                    st.progress(r["conviccion"] / 100, text=f"Convicción: {r['conviccion']}%")
                    st.progress(riesgo / 10, text=f"Riesgo: {riesgo}/10")
                    st.markdown(f"**Fuentes:** {', '.join(r['fuentes'])}")
                with col3:
                    if accion == "COMPRAR": st.success("⬆️ LONG")
                    else: st.error("⬇️ SHORT")

                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**⏱️ Horizonte:** {h.get('emoji','')} {h.get('label','')} — {h.get('dias','')}")
                with col2:
                    precio = r.get("precio_actual")
                    sl, tp = r.get("stop_loss"), r.get("take_profit")
                    if precio and sl and tp:
                        rr = round(abs(tp-precio)/abs(precio-sl), 1) if abs(precio-sl) > 0 else "N/D"
                        st.markdown(f"**📐 SL/TP:** 💰{precio:,.2f} | 🛑{sl:,.2f} | 🎯{tp:,.2f} | R/R 1:{rr}")
                    else:
                        st.caption("SL/TP no disponible")

                st.divider()
                st.markdown("**🚗 Vehículos sugeridos**")
                for i, inst in enumerate(r.get("instrumentos", [])):
                    badge = "⭐ Recomendado" if i == 0 else "Alternativa"
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown(f"**{badge}: {inst['vehiculo']}** — {inst['razon']}")
                        st.markdown(f"✅ {inst['pros']}")
                    with col_b:
                        st.markdown(f"🕐 {inst['cuando']}")
                        st.markdown(f"⚠️ {inst['contras']}")
                    if i < len(r.get("instrumentos", [])) - 1:
                        st.markdown("---")

                st.divider()
                st.markdown(f"**📋 Fundamentos:** *{r['tesis']}*")
                for fuente in ["Polymarket", "Kalshi", "Macro USA", "Noticias"]:
                    ev = [e for e in r["evidencia"] if e["fuente"] == fuente]
                    if not ev: continue
                    st.markdown(f"**{fuente}**")
                    for e in ev[:3]:
                        prob_str = f" ({e['prob']}%)" if e.get("prob") else ""
                        icon = "📈" if e["direccion"] == "ALZA" else ("📉" if e["direccion"] == "BAJA" else "➡️")
                        st.markdown(f"- {icon} {e['señal']}{prob_str} — Peso: `{e['peso']}`")
                st.caption("⚠️ Señal informativa. No constituye asesoría de inversión.")
    else:
        st.info("Sin señales consolidadas en este momento.")

# ── TAB OPCIONES ──────────────────────────────────────────────────────────────
with tab_opciones:
    st.subheader("⚙️ Opciones — Estrategias Sugeridas")
    st.caption("Estrategias derivadas de las señales. Disponible para SPY, SQM y GLD.")

    recomendaciones = st.session_state.get("recomendaciones", [])
    posiciones = get_posiciones_abiertas() if IB_DISPONIBLE else {}

    with st.spinner("Evaluando estrategias..."):
        estrategias = get_estrategias_opciones(recomendaciones, posiciones)

    if estrategias:
        st.success(f"✅ {len(estrategias)} estrategia(s) identificada(s)")
        for est in estrategias:
            icon = "🟢" if "Comprar" in est["estrategia"] else "💰"
            with st.expander(f"{icon} **{est['tipo']}** — {est['symbol']} | Strike: {est['strike_objetivo']} | {est['dte_objetivo']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"### {icon} {est['tipo']}")
                    st.markdown(f"**Subyacente:** `{est['symbol']}` | **Strike:** `{est['strike_objetivo']}`")
                    st.markdown(f"**Vencimiento:** {est['dte_objetivo']} | **Contratos:** {est['contratos']}")
                with col2:
                    if "costo_total_est" in est:
                        st.markdown(f"💰 Premium/contrato: **USD {est['premium_est_unit']:,.2f}**")
                        st.markdown(f"Costo total: **USD {est['costo_total_est']:,.0f}**")
                        st.markdown(f"Pérdida máx: **USD {est['max_perdida']:,.0f}**")
                        st.markdown(f"Break-even: **{est['break_even']:,.2f}**")
                    elif "ingreso_est" in est:
                        st.markdown(f"💰 Ingreso est.: **USD {est['ingreso_est']:,.0f}**")
                        st.markdown(f"Ganancia máx: **USD {est['max_ganancia']:,.0f}**")
                with col3:
                    st.markdown(f"✅ {est['pros']}")
                    st.markdown(f"⚠️ {est['contras']}")
                st.divider()
                st.markdown(f"**Fundamento:** *{est['razon']}*")
                right_nombre = "Call" if est["right"] == "C" else "Put"
                st.code(
                    f"TWS → {est['symbol']} → Trade Options\n"
                    f"Strike: {est['strike_objetivo']} | {right_nombre} | {est['dte_objetivo']}\n"
                    f"{'Comprar' if 'Comprar' in est['tipo'] else 'Vender'} {est['contratos']} contrato(s) | Orden LMT midpoint"
                )
    else:
        st.info("Sin estrategias de opciones disponibles. Se activan con señales ≥80% convicción sobre SPY, SQM o GLD.")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🟢 Comprar Call/Put:** Alta convicción ≥80% | Horizonte corto | Pérdida = premium | Apalancamiento 5-10x")
    with col2:
        st.markdown("**💰 Call Cubierto:** Posición larga ≥100 acciones | Ingreso 1-2% mensual | Strike 5% OTM | 15-30 días")

# ── TAB IB TRADING ────────────────────────────────────────────────────────────
with tab_ib:
    st.subheader("🤖 IB Trading — Paper Trading")
    if not IB_DISPONIBLE:
        st.error("ibapi no instalado.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("**Política:** USD 100.000 | Máx USD 10.000/op | 3 días | 5 pos. | Conv ≥75% | Riesgo ≤6/10")
        with col2:
            if st.button("🔄 Cuenta"):
                st.session_state.cuenta_ib = get_resumen_cuenta()
        if "cuenta_ib" in st.session_state and st.session_state.cuenta_ib:
            cuenta = st.session_state.cuenta_ib
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("💰 Net Liq.", f"USD {cuenta.get('NetLiquidation',0):,.0f}")
            with col2: st.metric("💵 Cash", f"USD {cuenta.get('TotalCashValue',0):,.0f}")
            with col3: st.metric("📈 Buying Power", f"USD {cuenta.get('BuyingPower',0):,.0f}")
        st.divider()
        st.subheader("📂 Posiciones")
        posiciones = get_posiciones_abiertas()
        if posiciones:
            rows = []
            for ticker, p in posiciones.items():
                dias = (datetime.now() - datetime.fromisoformat(p["fecha_entrada"])).days
                rows.append({"Ticker": ticker, "Acción": p["accion"], "Cantidad": p["cantidad"],
                    "Precio": p.get("precio_entrada","N/D"), "SL": p.get("sl","N/D"),
                    "TP": p.get("tp","N/D"), "Días": dias, "Vence": f"{max(0,3-dias)}d"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Sin posiciones abiertas")
        st.divider()
        st.subheader("🚀 Ejecutar")
        recomendaciones = st.session_state.get("recomendaciones", [])
        sv = [r for r in recomendaciones if r["conviccion"] >= 75 and r["riesgo"] <= 6 and r["n_fuentes"] >= 2]
        if sv:
            for r in sv:
                color = "🟢" if r["accion"] == "COMPRAR" else "🔴"
                st.markdown(f"{color} **{r['accion']} {r['ib_ticker']}** — Conv: {r['conviccion']}% | Riesgo: {r['riesgo']}/10")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🧪 Simular", use_container_width=True):
                    st.json(ejecutar_señales(recomendaciones, modo_test=True))
            with col2:
                if st.button("🚀 EJECUTAR PAPER", type="primary", use_container_width=True):
                    with st.spinner("Ejecutando..."):
                        resultado = ejecutar_señales(recomendaciones, modo_test=False)
                    if resultado["ordenes_enviadas"]:
                        st.success(f"✅ {len(resultado['ordenes_enviadas'])} orden(es) enviada(s)")
                    if resultado["errores"]:
                        st.error(" | ".join(resultado["errores"]))
                    st.rerun()
        else:
            st.info("Sin señales que cumplan política.")

# ── TAB IPSA ──────────────────────────────────────────────────────────────────
with tab_ipsa:
    st.subheader("🇨🇱 IPSA — 30 acciones")
    with st.spinner("Cargando..."):
        df_ipsa = get_precios_ipsa()
    if not df_ipsa.empty:
        amp = get_amplitud_mercado(df_ipsa)
        sesgo_color = "🟢" if amp["sesgo"] == "ALCISTA" else ("🔴" if amp["sesgo"] == "BAJISTA" else "🟡")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("📈 Subiendo", amp["subiendo"])
        with col2: st.metric("📉 Bajando", amp["bajando"])
        with col3: st.metric("➡️ Neutras", amp["neutras"])
        with col4: st.metric(f"{sesgo_color} Sesgo", amp["sesgo"])
        st.divider()
        top5, bottom5 = get_top_bottom_ipsa(df_ipsa, n=5)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🏆 Top 5")
            for _, row in top5.iterrows():
                st.markdown(f"🟢 **{row['nombre']}** ({row['ticker']}) — `{row['cambio_pct']:+.2f}%` | {row['precio']:,.0f} CLP")
        with col2:
            st.markdown("### 📉 Bottom 5")
            for _, row in bottom5.iterrows():
                st.markdown(f"🔴 **{row['nombre']}** ({row['ticker']}) — `{row['cambio_pct']:+.2f}%` | {row['precio']:,.0f} CLP")
        st.divider()
        fig = go.Figure(go.Bar(x=df_ipsa["ticker"], y=df_ipsa["cambio_pct"],
            marker_color=["#22c55e" if x > 0 else "#ef4444" for x in df_ipsa["cambio_pct"]],
            text=[f"{x:+.2f}%" for x in df_ipsa["cambio_pct"]], textposition="outside"))
        fig.update_layout(title="IPSA — Variación %", paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
            font_color="#e2e8f0", height=400, margin=dict(t=50,b=80), xaxis=dict(tickangle=-45),
            yaxis=dict(gridcolor="#1e293b"), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        st.divider()
        df_sec = get_resumen_sectorial(df_ipsa)
        if not df_sec.empty:
            col1, col2 = st.columns([2,3])
            with col1:
                for _, row in df_sec.iterrows():
                    color = "🟢" if row["variacion_prom"] > 0 else "🔴"
                    st.markdown(f"{color} **{row['sector']}** `{row['variacion_prom']:+.2f}%` | Mejor: `{row['mejor']:+.2f}%`")
            with col2:
                fig_sec = go.Figure(go.Bar(x=df_sec["sector"], y=df_sec["variacion_prom"],
                    marker_color=["#22c55e" if x > 0 else "#ef4444" for x in df_sec["variacion_prom"]],
                    text=[f"{x:+.2f}%" for x in df_sec["variacion_prom"]], textposition="outside"))
                fig_sec.update_layout(paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
                    font_color="#e2e8f0", height=300, margin=dict(t=30,b=60), xaxis=dict(tickangle=-30),
                    yaxis=dict(gridcolor="#1e293b"), showlegend=False)
                st.plotly_chart(fig_sec, use_container_width=True)
        st.divider()
        sectores = ["Todos"] + sorted(df_ipsa["sector"].unique().tolist())
        sector_filtro = st.selectbox("Filtrar sector", sectores)
        df_mostrar = df_ipsa if sector_filtro == "Todos" else df_ipsa[df_ipsa["sector"] == sector_filtro]
        st.dataframe(df_mostrar[["señal","nombre","ticker","sector","precio","cambio_pct","peso"]].rename(
            columns={"señal":"","nombre":"Empresa","ticker":"Ticker","sector":"Sector",
                     "precio":"Precio CLP","cambio_pct":"Var %","peso":"Peso"}),
            use_container_width=True, hide_index=True,
            column_config={"Var %": st.column_config.NumberColumn(format="%+.2f%%"),
                           "Precio CLP": st.column_config.NumberColumn(format="%,.0f")})

# ── TAB CHILE ─────────────────────────────────────────────────────────────────
with tab_chile:
    st.subheader("📊 Macro Chile")
    with st.spinner("Cargando..."):
        bcch = get_resumen_bcch()
    clp = bcch.get("CLP/USD"); tpm = bcch.get("TPM_%"); ipc = bcch.get("IPC_%"); uf = bcch.get("UF")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("CLP/USD", f"${clp:,.0f}" if clp else "N/D")
    with col2: st.metric("TPM", f"{tpm}%" if tpm else "N/D")
    with col3: st.metric("IPC", f"{ipc}%" if ipc else "N/D")
    with col4: st.metric("UF", f"${uf:,.2f}" if uf else "N/D")
    st.divider()
    with st.spinner("BTC..."):
        spread = get_spread_btc(clp or 892.0)
    if spread:
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("BTC Buda", f"${spread['btc_local_clp']:,.0f}")
        with col2: st.metric("BTC Global", f"${spread['btc_global_clp']:,.0f}")
        with col3: st.metric("Spread %", f"{spread['spread_pct']}%", delta=spread["direccion"])
        with col4: st.metric("BTC USD", f"${spread['btc_usd']:,.0f}")
        if spread.get("alerta"): st.error(f"🚨 {spread['direccion']} {abs(spread['spread_pct'])}%")
        else: st.success("✅ Normal")
    st.divider()
    with st.spinner("Polymarket..."):
        df_poly_cl = get_mercados_chile(limit=200)
    if not df_poly_cl.empty:
        for _, row in df_poly_cl.iterrows():
            prob = row["probabilidad"]
            if prob is None: continue
            color = "🟢" if prob > 65 else ("🔴" if prob < 35 else "🟡")
            with st.expander(f"{color} {row['pregunta'][:90]} — **{prob}%** {'⭐'*row.get('relevancia',1)}"):
                col1, col2 = st.columns(2)
                with col1: st.write(f"**Prob:** {prob}% | **Activos:** {', '.join(row['chile_impact'])}")
                with col2:
                    try: st.write(f"**Vol:** USD {float(row.get('volumen_usd',0)):,.0f}")
                    except: pass
                st.link_button("Ver", row.get("url",""))

# ── TAB USA ───────────────────────────────────────────────────────────────────
with tab_usa:
    st.subheader("📈 USA")
    with st.spinner("Cargando..."):
        df_usa = get_precios_usa()
        macro_data = get_macro_usa()
    if not df_usa.empty:
        cols = st.columns(3)
        for i, (_, row) in enumerate(df_usa.iterrows()):
            with cols[i % 3]:
                st.metric(row["ticker"], f"${row['precio']:,.2f}", delta=f"{row['cambio_pct']:+.2f}%",
                    delta_color="normal" if row['cambio_pct'] >= 0 else "inverse")
    if macro_data:
        st.divider()
        cols = st.columns(4)
        for i, m in enumerate(macro_data):
            with cols[i % 4]:
                st.metric(m["nombre"], f"{m['precio']:,.2f}", delta=f"{m['cambio_pct']:+.2f}%",
                    delta_color="inverse" if m["inverso"] else "normal")
        st.divider()
        for c in get_correlaciones_chile(macro_data)[:6]:
            score = c["score"]
            color = "🔴" if score >= 3 else ("🟡" if score >= 1.5 else "🟢")
            with st.expander(f"{color} {c['tesis']}"):
                col1, col2 = st.columns(2)
                with col1: st.write(f"**{c['indicador']}** ({c['cambio_pct']:+.2f}%)")
                with col2: st.write(f"**{c['activo_chile']}** → {c['direccion']}")

# ── TAB DIVERGENCIAS ──────────────────────────────────────────────────────────
with tab_div:
    st.subheader("⚡ Divergencias")
    with st.spinner("Analizando..."):
        df_poly_div = get_mercados_chile(limit=200)
        bcch_div = get_resumen_bcch()
        spread_div = get_spread_btc(bcch_div.get("CLP/USD", 892.0) or 892.0)
        df_result = calcular_divergencias(df_poly_div, spread_div)
    if not df_result.empty:
        nuevas = guardar_senales(df_result)
        if nuevas > 0: st.success(f"✅ {nuevas} señal(es) guardada(s)")
        st.info(f"**Principal:** {df_result.iloc[0]['Señal']} — {df_result.iloc[0]['Prob %']}% | Score: {df_result.iloc[0]['Score']}")
        st.dataframe(df_result[["Señal","Prob %","Dirección","Activos Chile","Score","Tesis"]], use_container_width=True, hide_index=True)
    else:
        st.info("Sin divergencias")

# ── TAB KALSHI ────────────────────────────────────────────────────────────────
with tab_kalshi:
    st.subheader("🎰 Kalshi")
    with st.spinner("Cargando..."):
        senales_kalshi = get_kalshi_resumen()
    if senales_kalshi:
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Señales", len(senales_kalshi))
        with col2: st.metric("📈 ALZA", sum(1 for s in senales_kalshi if s["direccion"] == "ALZA"))
        with col3: st.metric("📉 BAJA", sum(1 for s in senales_kalshi if s["direccion"] == "BAJA"))
        st.divider()
        series_vistas = set()
        for s in senales_kalshi:
            if s["serie"] not in series_vistas:
                st.markdown(f"### {s['serie']}")
                series_vistas.add(s["serie"])
            prob = s["prob_pct"]
            color = "🟢" if prob > 65 else ("🔴" if prob < 35 else "🟡")
            with st.expander(f"{color} {s['titulo'][:90]} — **{prob}%** | Score: {s['score']}"):
                col1, col2 = st.columns(2)
                with col1: st.write(f"**{prob}%** | {s['direccion']} | {', '.join(s['activos_impacto'])}")
                with col2: st.write(f"Score: {s['score']} | Cierre: {s['cierre']}")

# ── TAB NOTICIAS ──────────────────────────────────────────────────────────────
with tab_noticias:
    st.subheader("📰 Noticias Chile")
    with st.spinner("Cargando..."):
        noticias = get_noticias_google()
    if noticias:
        col_f1, col_f2 = st.columns([2, 3])
        with col_f1: min_score = st.slider("Score mínimo", 0, 15, 3)
        with col_f2: busqueda_n = st.text_input("🔍 Buscar", placeholder="litio, cobre, tasa...")
        noticias_filtradas = [n for n in noticias if n["score"] >= min_score]
        if busqueda_n:
            noticias_filtradas = [n for n in noticias_filtradas if busqueda_n.lower() in n["titulo"].lower()]
        st.caption(f"{len(noticias_filtradas)} noticias")
        for n in noticias_filtradas:
            score = n["score"]
            color = "🔴" if score >= 10 else ("🟡" if score >= 5 else "🟢")
            tags = " | ".join([f"`{k}`" for k in n.get("keywords", [])]) if n.get("keywords") else ""
            with st.expander(f"{color} **[{score}]** {n['titulo'][:100]}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Fuente:** {n['fuente']}")
                    if n.get("fecha"): st.write(f"**Fecha:** {n['fecha'][:30]}")
                    if tags: st.markdown(f"**Keywords:** {tags}")
                with col2:
                    if n.get("url"): st.link_button("🔗 Leer", n["url"])

# ── TAB HISTORIAL ─────────────────────────────────────────────────────────────
with tab_hist:
    st.subheader("📈 Historial")
    stats = get_estadisticas()
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total", stats["total"])
    with col2: st.metric("✅ Correctas", stats["correctas"])
    with col3: st.metric("❌ Incorrectas", stats["incorrectas"])
    with col4: st.metric("🎯 Éxito", f"{stats['tasa_exito']}%")
    st.divider()
    rows = get_historial(limit=50)
    if rows:
        df_hist = pd.DataFrame(rows, columns=["Fecha","Señal","Prob %","Dirección","Activos","Score","Tesis","Resultado"])
        st.dataframe(df_hist, use_container_width=True, hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=20, format="%.2f"),
                "Prob %": st.column_config.NumberColumn("Prob %", format="%.1f%%"),
                "Tesis": st.column_config.TextColumn("Tesis", width="large"),
            })
        st.divider()
        pendientes = [r for r in rows if r[7] == "pendiente"]
        if pendientes:
            opciones_sel = [f"{r[0]} — {r[1][:60]}" for r in pendientes]
            seleccion = st.selectbox("Señal", opciones_sel)
            resultado = st.radio("Resultado", ["correcto", "incorrecto"], horizontal=True)
            if st.button("Guardar"):
                idx = opciones_sel.index(seleccion)
                actualizar_resultado(pendientes[idx][1], pendientes[idx][0][:10], resultado)
                st.success("✅ Guardado")
                st.rerun()

# ── TAB BACKTESTING ───────────────────────────────────────────────────────────
with tab_bt:
    st.subheader("🔬 Backtesting Automático")
    st.caption("Evaluación automática de señales históricas comparando precios reales antes y después de la señal.")

    # Estadísticas generales
    stats_bt = get_estadisticas_backtest()

    if stats_bt:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: st.metric("📊 Total señales", stats_bt.get("total", 0))
        with col2: st.metric("✅ Correctas", stats_bt.get("correctas", 0))
        with col3: st.metric("❌ Incorrectas", stats_bt.get("incorrectas", 0))
        with col4: st.metric("⏳ Pendientes", stats_bt.get("pendientes", 0))
        with col5:
            tasa = stats_bt.get("tasa_exito", 0)
            color_tasa = "🟢" if tasa >= 60 else ("🟡" if tasa >= 40 else "🔴")
            st.metric(f"{color_tasa} Tasa éxito", f"{tasa}%")

        if stats_bt.get("correctas", 0) + stats_bt.get("incorrectas", 0) > 0:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📈 Mov. prom. correcto", f"{stats_bt.get('mov_prom_correcto',0):+.2f}%")
            with col2:
                st.metric("📉 Mov. prom. incorrecto", f"{stats_bt.get('mov_prom_incorrecto',0):+.2f}%")

        st.divider()

        # Botón para ejecutar backtesting
        col1, col2 = st.columns([2, 1])
        with col1:
            dias_min = st.slider("Días mínimos desde la señal para evaluar", 0, 7, 1)
        with col2:
            if st.button("🔬 Ejecutar Backtesting", type="primary", use_container_width=True):
                with st.spinner("Evaluando señales históricas..."):
                    resultado_bt = ejecutar_backtest(dias_minimos=dias_min)
                st.success(f"✅ Evaluadas: {resultado_bt['evaluadas']} | Correctas: {resultado_bt['correctas']} | Incorrectas: {resultado_bt['incorrectas']}")
                if resultado_bt["detalle"]:
                    df_bt = pd.DataFrame(resultado_bt["detalle"])
                    df_bt["resultado_icon"] = df_bt["resultado"].map(
                        {"correcto": "✅", "incorrecto": "❌", "neutral": "➡️", "pendiente": "⏳"})
                    st.dataframe(
                        df_bt[["resultado_icon","fecha","señal","direccion","ticker","precio_entrada","precio_salida","movimiento_pct","dias"]].rename(columns={
                            "resultado_icon":"","fecha":"Fecha","señal":"Señal","direccion":"Dir.",
                            "ticker":"Ticker","precio_entrada":"P. Entrada","precio_salida":"P. Salida",
                            "movimiento_pct":"Mov %","dias":"Días"}),
                        use_container_width=True, hide_index=True,
                        column_config={"Mov %": st.column_config.NumberColumn(format="%+.2f%%")}
                    )
                st.rerun()

        st.divider()

        # Historial con datos de backtesting
        st.subheader("📋 Historial con evaluación")
        historial_bt = stats_bt.get("historial_bt", [])
        if historial_bt:
            rows_bt = []
            for row in historial_bt:
                fecha, senal, prob, direccion, activos, score, resultado, p_entrada, p_salida, mov_pct, ticker = row
                icon = {"correcto": "✅", "incorrecto": "❌", "neutral": "➡️", "pendiente": "⏳"}.get(resultado, "❓")
                rows_bt.append({
                    "": icon, "Fecha": fecha[:16], "Señal": senal[:60],
                    "Dir.": direccion, "Activos": activos[:30],
                    "Score": score, "P.Entrada": p_entrada,
                    "P.Salida": p_salida,
                    "Mov %": round(mov_pct, 2) if mov_pct else None,
                    "Resultado": resultado,
                })
            df_hist_bt = pd.DataFrame(rows_bt)
            st.dataframe(df_hist_bt, use_container_width=True, hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=20, format="%.2f"),
                    "Mov %": st.column_config.NumberColumn("Mov %", format="%+.2f%%"),
                })

        # Mejores señales
        mejores = stats_bt.get("mejores_señales", [])
        if mejores:
            st.divider()
            st.subheader("🏆 Mejores señales correctas")
            for m in mejores:
                senal, score, mov_pct, direccion = m
                st.markdown(f"✅ **{senal[:70]}** — Score: `{score}` | Movimiento: `{mov_pct:+.2f}%` | Dir: {direccion}")

    else:
        st.info("Sin datos de historial aún. Las señales se generan automáticamente al cargar el tab ⚡ Divergencias.")
        if st.button("🔬 Ejecutar Backtesting ahora"):
            with st.spinner("Evaluando..."):
                resultado_bt = ejecutar_backtest(dias_minimos=0)
            st.success(f"Evaluadas: {resultado_bt['evaluadas']}")
            st.rerun()
