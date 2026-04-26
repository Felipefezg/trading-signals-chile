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
from engine.performance import get_metricas_performance, get_benchmarks, CAPITAL_INICIAL

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
    st.caption(f"🔄 {datetime.now().strftime('%H:%M:%S')} | Refresh: 15 min")

tab_señales, tab_perf, tab_opciones, tab_ib, tab_ipsa, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist, tab_bt = st.tabs([
    "🎯 Señales", "💹 Performance", "⚙️ Opciones", "🤖 IB Trading",
    "🇨🇱 IPSA", "📊 Chile", "🇺🇸 USA", "⚡ Divergencias",
    "🎰 Kalshi", "📰 Noticias", "📈 Historial", "🔬 Backtesting"
])

# ── TAB SEÑALES ───────────────────────────────────────────────────────────────
with tab_señales:
    st.subheader("🎯 Señales de Trading — Panel Ejecutivo")
    with st.spinner("Analizando..."):
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
            st.success(f"📱 {n_alertas} alerta(s) → Telegram")

        compras = [r for r in recomendaciones if r["accion"] == "COMPRAR"]
        ventas  = [r for r in recomendaciones if r["accion"] == "VENDER"]
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Total", len(recomendaciones))
        with col2: st.metric("🟢 Comprar", len(compras))
        with col3: st.metric("🔴 Vender", len(ventas))
        with col4: st.metric("⚠️ Riesgo prom.", f"{round(sum(r['riesgo'] for r in recomendaciones)/len(recomendaciones),1)}/10")

        st.divider()
        top = recomendaciones[0]
        h = top.get("horizonte", {})
        color_top = "🟢" if top["accion"] == "COMPRAR" else "🔴"
        st.info(f"**Principal:** {color_top} **{top['accion']} {top['ib_ticker']}** ({top['descripcion']})  \n"
                f"Conv: **{top['conviccion']}%** | Riesgo: **{top['riesgo']}/10** | {h.get('emoji','')} **{h.get('dias','N/D')}** | {', '.join(top['fuentes'])}")
        st.divider()

        for r in recomendaciones:
            accion = r["accion"]
            color  = "🟢" if accion == "COMPRAR" else "🔴"
            riesgo = r["riesgo"]
            h      = r.get("horizonte", {})
            rc     = "🟢" if riesgo <= 3 else ("🟡" if riesgo <= 6 else "🔴")
            ti     = "📱" if f"{r['accion']}_{r['ib_ticker']}" in st.session_state.alertas_enviadas else ""
            opt    = "⚙️" if r["ib_ticker"] in SUBYACENTES_OPCIONES else ""

            with st.expander(f"{color} **{accion} {r['ib_ticker']}** — {r['descripcion']} | Conv: **{r['conviccion']}%** | {rc} **{riesgo}/10** | {h.get('emoji','')} {h.get('label','')} {ti}{opt}"):
                col1, col2, col3 = st.columns([2,2,1])
                with col1:
                    st.markdown(f"### {color} {accion} `{r['ib_ticker']}`")
                    st.markdown(f"**Tipo:** {r['tipo']} | **Desc:** {r['descripcion']}")
                with col2:
                    st.progress(r["conviccion"]/100, text=f"Convicción: {r['conviccion']}%")
                    st.progress(riesgo/10, text=f"Riesgo: {riesgo}/10")
                    st.markdown(f"**Fuentes:** {', '.join(r['fuentes'])}")
                with col3:
                    if accion == "COMPRAR": st.success("⬆️ LONG")
                    else: st.error("⬇️ SHORT")
                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**⏱️** {h.get('emoji','')} {h.get('label','')} — {h.get('dias','')}")
                with col2:
                    precio = r.get("precio_actual"); sl = r.get("stop_loss"); tp = r.get("take_profit")
                    if precio and sl and tp:
                        rr = round(abs(tp-precio)/abs(precio-sl),1) if abs(precio-sl)>0 else "N/D"
                        st.markdown(f"**SL/TP:** 💰{precio:,.2f} | 🛑{sl:,.2f} | 🎯{tp:,.2f} | R/R 1:{rr}")
                st.divider()
                for i, inst in enumerate(r.get("instrumentos",[])):
                    badge = "⭐" if i==0 else "Alt."
                    col_a, col_b = st.columns(2)
                    with col_a: st.markdown(f"**{badge} {inst['vehiculo']}:** {inst['razon']} | ✅ {inst['pros']}")
                    with col_b: st.markdown(f"🕐 {inst['cuando']} | ⚠️ {inst['contras']}")
                    if i < len(r.get("instrumentos",[]))-1: st.markdown("---")
                st.divider()
                st.markdown(f"*{r['tesis']}*")
                for fuente in ["Polymarket","Kalshi","Macro USA","Noticias"]:
                    ev = [e for e in r["evidencia"] if e["fuente"]==fuente]
                    if not ev: continue
                    st.markdown(f"**{fuente}**")
                    for e in ev[:3]:
                        icon = "📈" if e["direccion"]=="ALZA" else ("📉" if e["direccion"]=="BAJA" else "➡️")
                        prob_str = f" ({e['prob']}%)" if e.get("prob") else ""
                        st.markdown(f"- {icon} {e['señal']}{prob_str} — Peso: `{e['peso']}`")
                st.caption("⚠️ Señal informativa. No asesoría de inversión.")
    else:
        st.info("Sin señales en este momento.")

# ── TAB PERFORMANCE ───────────────────────────────────────────────────────────
with tab_perf:
    st.subheader("💹 Dashboard de Performance")
    st.caption(f"Capital asignado: USD {CAPITAL_INICIAL:,.0f} | Paper Trading IB")

    with st.spinner("Calculando performance..."):
        m = get_metricas_performance()
        benchmarks = get_benchmarks()

    # ── Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    pnl_color = "normal" if m["pnl_total"] >= 0 else "inverse"
    with col1:
        st.metric("💰 Capital actual", f"USD {m['capital_actual']:,.0f}",
                  delta=f"{m['retorno_total_pct']:+.2f}%")
    with col2:
        st.metric("📈 PnL Total", f"USD {m['pnl_total']:+,.0f}")
    with col3:
        st.metric("✅ PnL Realizado", f"USD {m['pnl_realizado']:+,.0f}")
    with col4:
        st.metric("⏳ PnL No Realizado", f"USD {m['pnl_no_realizado']:+,.0f}")
    with col5:
        st.metric("📉 Drawdown máx.", f"{m['max_drawdown_pct']:.1f}%")

    st.divider()

    # ── Métricas de calidad
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("🎯 Win Rate", f"{m['win_rate']}%")
    with col2: st.metric("📊 Trades totales", m["n_trades"])
    with col3: st.metric("🟢 Ganadores", m["n_ganadores"])
    with col4: st.metric("🔴 Perdedores", m["n_perdedores"])
    with col5:
        pf = m["profit_factor"]
        pf_str = f"{pf:.2f}" if pf != float("inf") else "∞"
        st.metric("⚡ Profit Factor", pf_str)

    st.divider()

    # ── Comparación vs benchmarks
    st.subheader("📊 Comparación vs Benchmarks (30 días)")
    col1, col2 = st.columns([2, 3])
    with col1:
        sistema_retorno = m["retorno_total_pct"]
        for nombre, retorno in benchmarks.items():
            color = "🟢" if retorno > 0 else "🔴"
            vs = "↑" if sistema_retorno >= retorno else "↓"
            st.markdown(f"{color} **{nombre}:** `{retorno:+.2f}%` {vs}")
        st.markdown(f"{'🟢' if sistema_retorno >= 0 else '🔴'} **Sistema:** `{sistema_retorno:+.2f}%`")

    with col2:
        bench_names  = list(benchmarks.keys()) + ["Sistema"]
        bench_values = list(benchmarks.values()) + [sistema_retorno]
        bench_colors = ["#22c55e" if v >= 0 else "#ef4444" for v in bench_values]
        bench_colors[-1] = "#3b82f6"  # Azul para el sistema

        fig_bench = go.Figure(go.Bar(
            x=bench_names, y=bench_values,
            marker_color=bench_colors,
            text=[f"{v:+.2f}%" for v in bench_values],
            textposition="outside",
        ))
        fig_bench.update_layout(
            title="Retorno 30 días (%)",
            paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
            font_color="#e2e8f0", height=280,
            margin=dict(t=40,b=20), yaxis=dict(gridcolor="#1e293b"),
            showlegend=False,
        )
        st.plotly_chart(fig_bench, use_container_width=True)

    st.divider()

    # ── Posiciones abiertas con PnL
    st.subheader("📂 Posiciones Abiertas — PnL en tiempo real")
    posiciones_pnl = m["posiciones_abiertas"]
    if posiciones_pnl:
        for p in posiciones_pnl:
            pnl = p["pnl_total"]
            pnl_pct = p["pnl_pct"]
            color = "🟢" if pnl >= 0 else "🔴"
            with st.expander(f"{color} **{p['ticker']}** — PnL: **USD {pnl:+,.2f}** ({pnl_pct:+.2f}%) | {p['dias_abierta']} días"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Acción:** {p['accion']}")
                    st.markdown(f"**Cantidad:** {p['cantidad']}")
                    st.markdown(f"**Días abierta:** {p['dias_abierta']}")
                with col2:
                    st.markdown(f"**Precio entrada:** {p['precio_entrada']:,.2f}")
                    st.markdown(f"**Precio actual:** {p['precio_actual']:,.2f}")
                    st.markdown(f"**Monto entrada:** USD {p['precio_entrada']*p['cantidad']:,.0f}")
                with col3:
                    if p.get("sl"): st.markdown(f"🛑 **SL:** {p['sl']:,.2f}")
                    if p.get("tp"): st.markdown(f"🎯 **TP:** {p['tp']:,.2f}")
                    if p.get("horizonte"): st.markdown(f"⏱️ {p['horizonte']}")
    else:
        st.info("Sin posiciones abiertas. Las posiciones aparecen aquí cuando se ejecutan órdenes en IB.")

    st.divider()

    # ── Curva de equity
    st.subheader("📈 Curva de Equity")
    equity = m["equity_curve"]
    if len(equity) > 1:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            y=equity, mode="lines+markers",
            line=dict(color="#3b82f6", width=2),
            marker=dict(size=6),
            fill="tozeroy", fillcolor="rgba(59,130,246,0.1)",
            name="Equity"
        ))
        fig_eq.add_hline(y=CAPITAL_INICIAL, line_dash="dash",
                         line_color="#94a3b8", annotation_text="Capital inicial")
        fig_eq.update_layout(
            title="Evolución del capital (USD)",
            paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
            font_color="#e2e8f0", height=300,
            margin=dict(t=40,b=20), yaxis=dict(gridcolor="#1e293b"),
            showlegend=False,
        )
        st.plotly_chart(fig_eq, use_container_width=True)
    else:
        st.info("La curva de equity se construye con el historial de trades cerrados. Ejecuta operaciones en IB para ver la evolución.")

    st.divider()

    # ── Historial de trades cerrados
    st.subheader("📋 Trades Cerrados")
    trades = m["trades"]
    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades["icon"] = df_trades["pnl_total"].apply(lambda x: "✅" if x > 0 else "❌")
        st.dataframe(
            df_trades[["icon","ticker","accion","cantidad","precio_entrada","precio_salida",
                       "pnl_total","pnl_pct","fecha_entrada","fecha_salida"]].rename(columns={
                "icon":"","ticker":"Ticker","accion":"Acción","cantidad":"Cantidad",
                "precio_entrada":"P.Entrada","precio_salida":"P.Salida",
                "pnl_total":"PnL USD","pnl_pct":"PnL %",
                "fecha_entrada":"Entrada","fecha_salida":"Salida"
            }),
            use_container_width=True, hide_index=True,
            column_config={
                "PnL USD": st.column_config.NumberColumn(format="$%+,.2f"),
                "PnL %":   st.column_config.NumberColumn(format="%+.2f%%"),
            }
        )
    else:
        st.info("Sin trades cerrados aún. El historial se completa cuando se cierran posiciones.")

    # ── Métricas avanzadas
    if m["n_trades"] > 0:
        st.divider()
        st.subheader("🔢 Métricas Avanzadas")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Promedio por trade**")
            st.markdown(f"- Ganador promedio: **USD {m['avg_ganador']:+,.2f}**")
            st.markdown(f"- Perdedor promedio: **USD {m['avg_perdedor']:+,.2f}**")
            st.markdown(f"- Ratio R/R real: **1:{m['rr_real']}**")
        with col2:
            st.markdown("**Distribución**")
            st.markdown(f"- Win Rate: **{m['win_rate']}%**")
            st.markdown(f"- Profit Factor: **{m['profit_factor']}**")
            st.markdown(f"- Drawdown máx: **{m['max_drawdown_pct']}%**")
        with col3:
            st.markdown("**Capital**")
            st.markdown(f"- Inicial: **USD {CAPITAL_INICIAL:,.0f}**")
            st.markdown(f"- Actual: **USD {m['capital_actual']:,.0f}**")
            st.markdown(f"- Retorno: **{m['retorno_total_pct']:+.2f}%**")

# ── TAB OPCIONES ──────────────────────────────────────────────────────────────
with tab_opciones:
    st.subheader("⚙️ Opciones")
    recomendaciones = st.session_state.get("recomendaciones", [])
    posiciones = get_posiciones_abiertas() if IB_DISPONIBLE else {}
    estrategias = get_estrategias_opciones(recomendaciones, posiciones)
    if estrategias:
        st.success(f"✅ {len(estrategias)} estrategia(s)")
        for est in estrategias:
            icon = "🟢" if "Comprar" in est["estrategia"] else "💰"
            with st.expander(f"{icon} **{est['tipo']}** — {est['symbol']} | Strike: {est['strike_objetivo']} | {est['dte_objetivo']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**{est['symbol']}** | Strike: `{est['strike_objetivo']}` | Contratos: {est['contratos']}")
                with col2:
                    if "costo_total_est" in est:
                        st.markdown(f"💰 Costo: **USD {est['costo_total_est']:,.0f}** | Pérd. máx: **USD {est['max_perdida']:,.0f}**")
                    elif "ingreso_est" in est:
                        st.markdown(f"💰 Ingreso: **USD {est['ingreso_est']:,.0f}**")
                with col3:
                    st.markdown(f"✅ {est['pros']}")
                st.markdown(f"*{est['razon']}*")
                st.code(f"TWS → {est['symbol']} → Options → Strike {est['strike_objetivo']} | {'Comprar' if 'Comprar' in est['tipo'] else 'Vender'} {est['contratos']} contratos LMT")
    else:
        st.info("Sin estrategias disponibles. Se activan con señales ≥80% convicción sobre SPY, SQM o GLD.")

# ── TAB IB ────────────────────────────────────────────────────────────────────
with tab_ib:
    st.subheader("🤖 IB Paper Trading")
    if not IB_DISPONIBLE:
        st.error("ibapi no instalado.")
    else:
        col1, col2 = st.columns([3,1])
        with col1: st.markdown("**Política:** USD 100k | Máx USD 10k/op | 3 días | 5 pos. | Conv ≥75% | Riesgo ≤6/10")
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
        posiciones = get_posiciones_abiertas()
        if posiciones:
            rows = [{"Ticker":t,"Acción":p["accion"],"Cantidad":p["cantidad"],
                     "Precio":p.get("precio_entrada","N/D"),"SL":p.get("sl","N/D"),
                     "TP":p.get("tp","N/D"),"Días":(datetime.now()-datetime.fromisoformat(p["fecha_entrada"])).days}
                    for t,p in posiciones.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Sin posiciones abiertas")
        st.divider()
        recomendaciones = st.session_state.get("recomendaciones", [])
        sv = [r for r in recomendaciones if r["conviccion"]>=75 and r["riesgo"]<=6 and r["n_fuentes"]>=2]
        if sv:
            for r in sv:
                color = "🟢" if r["accion"]=="COMPRAR" else "🔴"
                st.markdown(f"{color} **{r['accion']} {r['ib_ticker']}** — Conv:{r['conviccion']}% Riesgo:{r['riesgo']}/10")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🧪 Simular", use_container_width=True):
                    st.json(ejecutar_señales(recomendaciones, modo_test=True))
            with col2:
                if st.button("🚀 EJECUTAR PAPER", type="primary", use_container_width=True):
                    with st.spinner("Ejecutando..."):
                        res = ejecutar_señales(recomendaciones, modo_test=False)
                    if res["ordenes_enviadas"]: st.success(f"✅ {len(res['ordenes_enviadas'])} orden(es)")
                    if res["errores"]: st.error(" | ".join(res["errores"]))
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
        sc = "🟢" if amp["sesgo"]=="ALCISTA" else ("🔴" if amp["sesgo"]=="BAJISTA" else "🟡")
        col1,col2,col3,col4 = st.columns(4)
        with col1: st.metric("📈 Subiendo", amp["subiendo"])
        with col2: st.metric("📉 Bajando", amp["bajando"])
        with col3: st.metric("➡️ Neutras", amp["neutras"])
        with col4: st.metric(f"{sc} Sesgo", amp["sesgo"])
        st.divider()
        top5, bottom5 = get_top_bottom_ipsa(df_ipsa, n=5)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🏆 Top 5")
            for _, row in top5.iterrows():
                st.markdown(f"🟢 **{row['nombre']}** — `{row['cambio_pct']:+.2f}%` | {row['precio']:,.0f} CLP")
        with col2:
            st.markdown("### 📉 Bottom 5")
            for _, row in bottom5.iterrows():
                st.markdown(f"🔴 **{row['nombre']}** — `{row['cambio_pct']:+.2f}%` | {row['precio']:,.0f} CLP")
        st.divider()
        fig = go.Figure(go.Bar(x=df_ipsa["ticker"], y=df_ipsa["cambio_pct"],
            marker_color=["#22c55e" if x>0 else "#ef4444" for x in df_ipsa["cambio_pct"]],
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
                    color = "🟢" if row["variacion_prom"]>0 else "🔴"
                    st.markdown(f"{color} **{row['sector']}** `{row['variacion_prom']:+.2f}%`")
            with col2:
                fig_sec = go.Figure(go.Bar(x=df_sec["sector"], y=df_sec["variacion_prom"],
                    marker_color=["#22c55e" if x>0 else "#ef4444" for x in df_sec["variacion_prom"]],
                    text=[f"{x:+.2f}%" for x in df_sec["variacion_prom"]], textposition="outside"))
                fig_sec.update_layout(paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
                    font_color="#e2e8f0", height=280, margin=dict(t=30,b=60),
                    xaxis=dict(tickangle=-30), yaxis=dict(gridcolor="#1e293b"), showlegend=False)
                st.plotly_chart(fig_sec, use_container_width=True)
        st.divider()
        sectores = ["Todos"] + sorted(df_ipsa["sector"].unique().tolist())
        sf = st.selectbox("Sector", sectores)
        dm = df_ipsa if sf=="Todos" else df_ipsa[df_ipsa["sector"]==sf]
        st.dataframe(dm[["señal","nombre","ticker","sector","precio","cambio_pct","peso"]].rename(
            columns={"señal":"","nombre":"Empresa","ticker":"Ticker","sector":"Sector",
                     "precio":"Precio CLP","cambio_pct":"Var %","peso":"Peso"}),
            use_container_width=True, hide_index=True,
            column_config={"Var %":st.column_config.NumberColumn(format="%+.2f%%"),
                           "Precio CLP":st.column_config.NumberColumn(format="%,.0f")})

# ── TAB CHILE ─────────────────────────────────────────────────────────────────
with tab_chile:
    st.subheader("📊 Macro Chile")
    with st.spinner("Cargando..."):
        bcch = get_resumen_bcch()
    clp=bcch.get("CLP/USD"); tpm=bcch.get("TPM_%"); ipc=bcch.get("IPC_%"); uf=bcch.get("UF")
    col1,col2,col3,col4 = st.columns(4)
    with col1: st.metric("CLP/USD", f"${clp:,.0f}" if clp else "N/D")
    with col2: st.metric("TPM", f"{tpm}%" if tpm else "N/D")
    with col3: st.metric("IPC", f"{ipc}%" if ipc else "N/D")
    with col4: st.metric("UF", f"${uf:,.2f}" if uf else "N/D")
    st.divider()
    with st.spinner("BTC..."):
        spread = get_spread_btc(clp or 892.0)
    if spread:
        col1,col2,col3,col4 = st.columns(4)
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
            color = "🟢" if prob>65 else ("🔴" if prob<35 else "🟡")
            with st.expander(f"{color} {row['pregunta'][:90]} — **{prob}%** {'⭐'*row.get('relevancia',1)}"):
                col1,col2 = st.columns(2)
                with col1: st.write(f"**Prob:** {prob}% | **Activos:** {', '.join(row['chile_impact'])}")
                with col2:
                    try: st.write(f"**Vol:** USD {float(row.get('volumen_usd',0)):,.0f}")
                    except: pass
                st.link_button("Ver", row.get("url",""))

# ── TAB USA ───────────────────────────────────────────────────────────────────
with tab_usa:
    st.subheader("🇺🇸 USA")
    with st.spinner("Cargando..."):
        df_usa = get_precios_usa(); macro_data = get_macro_usa()
    if not df_usa.empty:
        cols = st.columns(3)
        for i,(_, row) in enumerate(df_usa.iterrows()):
            with cols[i%3]: st.metric(row["ticker"], f"${row['precio']:,.2f}", delta=f"{row['cambio_pct']:+.2f}%",
                delta_color="normal" if row['cambio_pct']>=0 else "inverse")
    if macro_data:
        st.divider()
        cols = st.columns(4)
        for i,m in enumerate(macro_data):
            with cols[i%4]: st.metric(m["nombre"], f"{m['precio']:,.2f}", delta=f"{m['cambio_pct']:+.2f}%",
                delta_color="inverse" if m["inverso"] else "normal")
        st.divider()
        for c in get_correlaciones_chile(macro_data)[:6]:
            score = c["score"]
            color = "🔴" if score>=3 else ("🟡" if score>=1.5 else "🟢")
            with st.expander(f"{color} {c['tesis']}"):
                col1,col2 = st.columns(2)
                with col1: st.write(f"**{c['indicador']}** ({c['cambio_pct']:+.2f}%)")
                with col2: st.write(f"**{c['activo_chile']}** → {c['direccion']}")

# ── TAB DIVERGENCIAS ──────────────────────────────────────────────────────────
with tab_div:
    st.subheader("⚡ Divergencias")
    with st.spinner("Analizando..."):
        df_poly_div = get_mercados_chile(limit=200)
        bcch_div = get_resumen_bcch()
        spread_div = get_spread_btc(bcch_div.get("CLP/USD",892.0) or 892.0)
        df_result = calcular_divergencias(df_poly_div, spread_div)
    if not df_result.empty:
        nuevas = guardar_senales(df_result)
        if nuevas>0: st.success(f"✅ {nuevas} señal(es) guardada(s)")
        st.info(f"**Principal:** {df_result.iloc[0]['Señal']} — {df_result.iloc[0]['Prob %']}% | Score: {df_result.iloc[0]['Score']}")
        st.dataframe(df_result[["Señal","Prob %","Dirección","Activos Chile","Score","Tesis"]], use_container_width=True, hide_index=True)
    else: st.info("Sin divergencias")

# ── TAB KALSHI ────────────────────────────────────────────────────────────────
with tab_kalshi:
    st.subheader("🎰 Kalshi")
    with st.spinner("Cargando..."):
        senales_kalshi = get_kalshi_resumen()
    if senales_kalshi:
        col1,col2,col3 = st.columns(3)
        with col1: st.metric("Señales", len(senales_kalshi))
        with col2: st.metric("📈 ALZA", sum(1 for s in senales_kalshi if s["direccion"]=="ALZA"))
        with col3: st.metric("📉 BAJA", sum(1 for s in senales_kalshi if s["direccion"]=="BAJA"))
        st.divider()
        series_vistas = set()
        for s in senales_kalshi:
            if s["serie"] not in series_vistas:
                st.markdown(f"### {s['serie']}")
                series_vistas.add(s["serie"])
            prob = s["prob_pct"]
            color = "🟢" if prob>65 else ("🔴" if prob<35 else "🟡")
            with st.expander(f"{color} {s['titulo'][:90]} — **{prob}%** | Score: {s['score']}"):
                col1,col2 = st.columns(2)
                with col1: st.write(f"**{prob}%** | {s['direccion']} | {', '.join(s['activos_impacto'])}")
                with col2: st.write(f"Score: {s['score']} | Cierre: {s['cierre']}")

# ── TAB NOTICIAS ──────────────────────────────────────────────────────────────
with tab_noticias:
    st.subheader("📰 Noticias Chile")
    with st.spinner("Cargando..."):
        noticias = get_noticias_google()
    if noticias:
        col_f1,col_f2 = st.columns([2,3])
        with col_f1: min_score = st.slider("Score mín.", 0, 15, 3)
        with col_f2: busqueda_n = st.text_input("🔍", placeholder="litio, cobre, tasa...")
        noticias_filtradas = [n for n in noticias if n["score"]>=min_score]
        if busqueda_n: noticias_filtradas = [n for n in noticias_filtradas if busqueda_n.lower() in n["titulo"].lower()]
        st.caption(f"{len(noticias_filtradas)} noticias")
        for n in noticias_filtradas:
            score = n["score"]
            color = "🔴" if score>=10 else ("🟡" if score>=5 else "🟢")
            tags = " | ".join([f"`{k}`" for k in n.get("keywords",[])]) if n.get("keywords") else ""
            with st.expander(f"{color} **[{score}]** {n['titulo'][:100]}"):
                col1,col2 = st.columns([3,1])
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
    col1,col2,col3,col4 = st.columns(4)
    with col1: st.metric("Total", stats["total"])
    with col2: st.metric("✅ Correctas", stats["correctas"])
    with col3: st.metric("❌ Incorrectas", stats["incorrectas"])
    with col4: st.metric("🎯 Éxito", f"{stats['tasa_exito']}%")
    st.divider()
    rows = get_historial(limit=50)
    if rows:
        df_hist = pd.DataFrame(rows, columns=["Fecha","Señal","Prob %","Dirección","Activos","Score","Tesis","Resultado"])
        st.dataframe(df_hist, use_container_width=True, hide_index=True,
            column_config={"Score":st.column_config.ProgressColumn("Score",min_value=0,max_value=20,format="%.2f"),
                           "Prob %":st.column_config.NumberColumn(format="%.1f%%"),
                           "Tesis":st.column_config.TextColumn(width="large")})
        st.divider()
        pendientes = [r for r in rows if r[7]=="pendiente"]
        if pendientes:
            ops = [f"{r[0]} — {r[1][:60]}" for r in pendientes]
            sel = st.selectbox("Señal", ops)
            res = st.radio("Resultado", ["correcto","incorrecto"], horizontal=True)
            if st.button("Guardar"):
                idx = ops.index(sel)
                actualizar_resultado(pendientes[idx][1], pendientes[idx][0][:10], res)
                st.success("✅ Guardado"); st.rerun()

# ── TAB BACKTESTING ───────────────────────────────────────────────────────────
with tab_bt:
    st.subheader("🔬 Backtesting Automático")
    stats_bt = get_estadisticas_backtest()
    if stats_bt:
        col1,col2,col3,col4,col5 = st.columns(5)
        with col1: st.metric("Total", stats_bt.get("total",0))
        with col2: st.metric("✅ Correctas", stats_bt.get("correctas",0))
        with col3: st.metric("❌ Incorrectas", stats_bt.get("incorrectas",0))
        with col4: st.metric("⏳ Pendientes", stats_bt.get("pendientes",0))
        with col5:
            tasa = stats_bt.get("tasa_exito",0)
            st.metric(f"{'🟢' if tasa>=60 else '🟡' if tasa>=40 else '🔴'} Tasa éxito", f"{tasa}%")
        st.divider()
        col1,col2 = st.columns([2,1])
        with col1: dias_min = st.slider("Días mínimos para evaluar", 0, 7, 1)
        with col2:
            if st.button("🔬 Ejecutar Backtesting", type="primary", use_container_width=True):
                with st.spinner("Evaluando..."):
                    res_bt = ejecutar_backtest(dias_minimos=dias_min)
                st.success(f"✅ Evaluadas: {res_bt['evaluadas']} | ✅: {res_bt['correctas']} | ❌: {res_bt['incorrectas']}")
                if res_bt["detalle"]:
                    df_bt = pd.DataFrame(res_bt["detalle"])
                    df_bt["icon"] = df_bt["resultado"].map({"correcto":"✅","incorrecto":"❌","neutral":"➡️","pendiente":"⏳"})
                    st.dataframe(df_bt[["icon","fecha","señal","direccion","ticker","precio_entrada","precio_salida","movimiento_pct","dias"]].rename(
                        columns={"icon":"","fecha":"Fecha","señal":"Señal","direccion":"Dir.","ticker":"Ticker",
                                 "precio_entrada":"P.Entrada","precio_salida":"P.Salida","movimiento_pct":"Mov %","dias":"Días"}),
                        use_container_width=True, hide_index=True,
                        column_config={"Mov %":st.column_config.NumberColumn(format="%+.2f%%")})
                st.rerun()
        st.divider()
        historial_bt = stats_bt.get("historial_bt",[])
        if historial_bt:
            rows_bt = []
            for row in historial_bt:
                fecha,senal,prob,direccion,activos,score,resultado,p_e,p_s,mov,ticker = row
                icon = {"correcto":"✅","incorrecto":"❌","neutral":"➡️","pendiente":"⏳"}.get(resultado,"❓")
                rows_bt.append({"":icon,"Fecha":fecha[:16],"Señal":senal[:60],"Dir.":direccion,
                    "Score":score,"P.Entrada":p_e,"P.Salida":p_s,
                    "Mov %":round(mov,2) if mov else None,"Resultado":resultado})
            st.dataframe(pd.DataFrame(rows_bt), use_container_width=True, hide_index=True,
                column_config={"Score":st.column_config.ProgressColumn("Score",min_value=0,max_value=20,format="%.2f"),
                               "Mov %":st.column_config.NumberColumn(format="%+.2f%%")})
