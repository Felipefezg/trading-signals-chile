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
from data.bcch_completo import get_macro_chile_completo, get_contexto_macro, get_precios_cochilco
from data.ipsa import get_precios_ipsa, get_resumen_sectorial, get_top_bottom_ipsa, get_amplitud_mercado
from engine.divergence import calcular_divergencias
from engine.recomendaciones import consolidar_señales, generar_recomendaciones, enviar_alertas_nuevas
from engine.opciones import get_estrategias_opciones, SUBYACENTES_OPCIONES
from engine.backtesting import ejecutar_backtest, get_estadisticas_backtest
from engine.nlp_sentiment import analizar_noticias_batch, get_resumen_sentiment, get_sentiment_por_activo
from engine.performance import get_metricas_performance, get_benchmarks, CAPITAL_INICIAL
from data.arbitraje import get_resumen_arbitraje, COSTOS
from data.arbitraje import get_resumen_arbitraje, COSTOS
from data.arbitraje import get_resumen_arbitraje, COSTOS

try:
    from engine.ib_executor import ejecutar_señales, get_posiciones_abiertas, get_resumen_cuenta
    IB_DISPONIBLE = True
except ImportError:
    IB_DISPONIBLE = False

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Terminal",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS DARK MODE PROFESIONAL ─────────────────────────────────────────────────
st.markdown("""
<style>
/* Base */
[data-testid="stAppViewContainer"] {
    background-color: #0a0e1a;
    color: #e2e8f0;
}
[data-testid="stHeader"] { background-color: #0a0e1a; }
[data-testid="stSidebar"] { background-color: #0d1117; }
.block-container { padding-top: 1rem; padding-bottom: 1rem; }

/* Tabs */
[data-testid="stTabs"] button {
    background-color: #0d1117;
    color: #64748b;
    border: 1px solid #1e293b;
    border-radius: 6px 6px 0 0;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    padding: 0.4rem 0.8rem;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    background-color: #1e293b;
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
}
[data-testid="stTabs"] button:hover { color: #94a3b8; }

/* Métricas */
[data-testid="metric-container"] {
    background: #0d1117;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 0.75rem 1rem;
}
[data-testid="metric-container"] label {
    color: #64748b !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #f1f5f9 !important;
    font-size: 1.4rem !important;
    font-weight: 700;
    font-family: 'Courier New', monospace;
}
[data-testid="stMetricDelta"] svg { display: none; }

/* Cards / Expanders */
[data-testid="stExpander"] {
    background: #0d1117;
    border: 1px solid #1e293b;
    border-radius: 8px;
    margin-bottom: 0.4rem;
}
[data-testid="stExpander"]:hover { border-color: #334155; }
[data-testid="stExpander"] summary {
    color: #cbd5e1;
    font-size: 0.85rem;
    font-weight: 500;
    padding: 0.6rem 0.8rem;
}

/* DataFrames */
[data-testid="stDataFrame"] {
    border: 1px solid #1e293b;
    border-radius: 8px;
    overflow: hidden;
}

/* Botones */
[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #0ea5e9, #0284c7) !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
}
[data-testid="baseButton-secondary"] {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #94a3b8 !important;
    border-radius: 6px !important;
}

/* Progress bars */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #0ea5e9, #38bdf8);
    border-radius: 4px;
}

/* Info / Success / Error */
[data-testid="stAlert"] {
    border-radius: 8px;
    border-left-width: 3px;
    font-size: 0.85rem;
}

/* Divider */
hr { border-color: #1e293b; margin: 1rem 0; }

/* Text inputs */
[data-testid="stTextInput"] input {
    background: #0d1117;
    border: 1px solid #1e293b;
    color: #e2e8f0;
    border-radius: 6px;
}

/* Selectbox */
[data-testid="stSelectbox"] select {
    background: #0d1117;
    border: 1px solid #1e293b;
    color: #e2e8f0;
}

/* Slider */
[data-testid="stSlider"] [data-testid="stThumbValue"] { color: #38bdf8; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }

/* Número monospace en tablas */
.stDataFrame td { font-family: 'Courier New', monospace; font-size: 0.82rem; }

/* Caption */
.stCaption { color: #475569 !important; font-size: 0.75rem !important; }

/* Code blocks */
[data-testid="stCode"] {
    background: #0d1117 !important;
    border: 1px solid #1e293b !important;
    border-radius: 6px;
    font-size: 0.78rem;
}
</style>
""", unsafe_allow_html=True)

# ── HELPERS VISUALES ──────────────────────────────────────────────────────────
def badge(texto, color="#0ea5e9"):
    return f'<span style="background:{color}22;color:{color};border:1px solid {color}44;border-radius:4px;padding:2px 8px;font-size:0.72rem;font-weight:700;letter-spacing:0.05em">{texto}</span>'

def pnl_color(v):
    return "#22c55e" if v > 0 else ("#ef4444" if v < 0 else "#64748b")

def riesgo_color(r):
    return "#22c55e" if r <= 3 else ("#f59e0b" if r <= 6 else "#ef4444")

PLOT_LAYOUT = dict(
    paper_bgcolor="#0d1117",
    plot_bgcolor="#0d1117",
    font=dict(color="#94a3b8", size=11),
    margin=dict(t=40, b=40, l=40, r=20),
    xaxis=dict(gridcolor="#1e293b", linecolor="#1e293b", tickcolor="#334155"),
    yaxis=dict(gridcolor="#1e293b", linecolor="#1e293b", tickcolor="#334155"),
    showlegend=False,
)

# ── AUTOREFRESH ───────────────────────────────────────────────────────────────
st_autorefresh(interval=15 * 60 * 1000, key="autorefresh")

if "alertas_enviadas" not in st.session_state:
    st.session_state.alertas_enviadas = set()

# ── HEADER ────────────────────────────────────────────────────────────────────
col_logo, col_time, col_status = st.columns([3, 2, 2])
with col_logo:
    st.markdown("## 📡 Trading Terminal")
    st.markdown('<span style="color:#475569;font-size:0.78rem">Polymarket × Kalshi × IB Paper Trading</span>', unsafe_allow_html=True)
with col_time:
    now = datetime.now()
    st.markdown(f'<div style="text-align:right;padding-top:0.5rem"><span style="color:#38bdf8;font-family:monospace;font-size:1.1rem">{now.strftime("%H:%M:%S")}</span><br><span style="color:#475569;font-size:0.72rem">{now.strftime("%A %d %b %Y")}</span></div>', unsafe_allow_html=True)
with col_status:
    st.markdown('<div style="text-align:right;padding-top:0.5rem"><span style="color:#22c55e;font-size:0.78rem">● LIVE</span>&nbsp;<span style="color:#475569;font-size:0.72rem">Refresh: 15 min</span></div>', unsafe_allow_html=True)

st.markdown('<hr style="border-color:#1e293b;margin:0.5rem 0 1rem 0">', unsafe_allow_html=True)

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_señales, tab_perf, tab_arb, tab_opciones, tab_ib, tab_ipsa, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist, tab_bt = st.tabs([
    "🎯 SEÑALES", "💹 PERFORMANCE", "🔀 ARBITRAJE", "⚙️ OPCIONES", "🤖 IB TRADING",
    "🇨🇱 IPSA", "📊 CHILE", "🇺🇸 USA", "⚡ DIVERGENCIAS",
    "🎰 KALSHI", "📰 NOTICIAS", "📈 HISTORIAL", "🔬 BACKTESTING"
])

# ── TAB SEÑALES ───────────────────────────────────────────────────────────────
with tab_señales:
    with st.spinner(""):
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
            st.success(f"📱 {n_alertas} alerta(s) enviada(s) vía Telegram")

        compras = [r for r in recomendaciones if r["accion"] == "COMPRAR"]
        ventas  = [r for r in recomendaciones if r["accion"] == "VENDER"]
        avg_r   = round(sum(r["riesgo"] for r in recomendaciones) / len(recomendaciones), 1)

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("SEÑALES ACTIVAS", len(recomendaciones))
        with col2: st.metric("COMPRAR", len(compras), delta=f"+{len(compras)}" if compras else None)
        with col3: st.metric("VENDER", len(ventas), delta=f"-{len(ventas)}" if ventas else None)
        with col4: st.metric("RIESGO PROM.", f"{avg_r}/10")

        # Señal principal destacada
        top = recomendaciones[0]
        h   = top.get("horizonte", {})
        accion_color = "#22c55e" if top["accion"] == "COMPRAR" else "#ef4444"
        accion_icon  = "⬆" if top["accion"] == "COMPRAR" else "⬇"

        st.markdown(f"""
        <div style="background:#0d1117;border:1px solid {accion_color}44;border-left:3px solid {accion_color};
        border-radius:8px;padding:1rem 1.25rem;margin:1rem 0">
            <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem">
                <span style="color:{accion_color};font-size:1.4rem">{accion_icon}</span>
                <span style="color:{accion_color};font-size:1.1rem;font-weight:700;font-family:monospace">
                    {top['accion']} {top['ib_ticker']}</span>
                <span style="color:#94a3b8;font-size:0.85rem">— {top['descripcion']}</span>
            </div>
            <div style="display:flex;gap:1.5rem;flex-wrap:wrap">
                <span style="color:#64748b;font-size:0.78rem">CONVICCIÓN &nbsp;<span style="color:#38bdf8;font-weight:700">{top['conviccion']}%</span></span>
                <span style="color:#64748b;font-size:0.78rem">RIESGO &nbsp;<span style="color:{riesgo_color(top['riesgo'])};font-weight:700">{top['riesgo']}/10</span></span>
                <span style="color:#64748b;font-size:0.78rem">HORIZONTE &nbsp;<span style="color:#f1f5f9;font-weight:700">{h.get('emoji','')} {h.get('dias','N/D')}</span></span>
                <span style="color:#64748b;font-size:0.78rem">FUENTES &nbsp;<span style="color:#f1f5f9;font-weight:700">{', '.join(top['fuentes'])}</span></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Lista de señales
        for r in recomendaciones:
            accion = r["accion"]
            ac     = "#22c55e" if accion == "COMPRAR" else "#ef4444"
            ai     = "⬆" if accion == "COMPRAR" else "⬇"
            h      = r.get("horizonte", {})
            rc     = riesgo_color(r["riesgo"])
            ti     = " 📱" if f"{r['accion']}_{r['ib_ticker']}" in st.session_state.alertas_enviadas else ""
            opt    = " ⚙️" if r["ib_ticker"] in SUBYACENTES_OPCIONES else ""

            with st.expander(
                f"{ai} {r['accion']} {r['ib_ticker']}  ·  {r['descripcion']}  ·  "
                f"Conv: {r['conviccion']}%  ·  Riesgo: {r['riesgo']}/10  ·  "
                f"{h.get('label','')} {ti}{opt}"
            ):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f'<span style="color:{ac};font-size:1.2rem;font-weight:700">{ai} {accion}</span> &nbsp; <code style="background:#1e293b;padding:2px 8px;border-radius:4px">{r["ib_ticker"]}</code>', unsafe_allow_html=True)
                    st.markdown(f'**Tipo:** {r["tipo"]}  |  **Desc:** {r["descripcion"]}')
                with col2:
                    st.progress(r["conviccion"] / 100, text=f"Convicción: {r['conviccion']}%")
                    st.progress(r["riesgo"] / 10, text=f"Riesgo: {r['riesgo']}/10")
                    st.caption(f"Fuentes: {', '.join(r['fuentes'])}")
                with col3:
                    if accion == "COMPRAR":
                        st.markdown('<div style="background:#22c55e22;border:1px solid #22c55e44;border-radius:6px;padding:0.5rem;text-align:center;color:#22c55e;font-weight:700">⬆ LONG</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="background:#ef444422;border:1px solid #ef444444;border-radius:6px;padding:0.5rem;text-align:center;color:#ef4444;font-weight:700">⬇ SHORT</div>', unsafe_allow_html=True)

                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**⏱ Horizonte:** {h.get('emoji','')} {h.get('label','')} — {h.get('dias','')}")
                with col2:
                    precio = r.get("precio_actual"); sl = r.get("stop_loss"); tp = r.get("take_profit")
                    if precio and sl and tp:
                        rr = round(abs(tp-precio)/abs(precio-sl), 1) if abs(precio-sl) > 0 else "N/D"
                        st.markdown(f"**📐 SL/TP:** `{precio:,.2f}` → 🛑`{sl:,.2f}` / 🎯`{tp:,.2f}` · R/R **1:{rr}**")

                st.divider()
                for i, inst in enumerate(r.get("instrumentos", [])):
                    badge_txt = "⭐ RECOMENDADO" if i == 0 else "ALTERNATIVA"
                    badge_col = "#0ea5e9" if i == 0 else "#64748b"
                    st.markdown(f'<span style="background:{badge_col}22;color:{badge_col};border:1px solid {badge_col}44;border-radius:4px;padding:1px 6px;font-size:0.7rem;font-weight:700">{badge_txt}</span> &nbsp; **{inst["vehiculo"]}**', unsafe_allow_html=True)
                    col_a, col_b = st.columns(2)
                    with col_a: st.caption(f"📋 {inst['razon']}  ·  ✅ {inst['pros']}")
                    with col_b: st.caption(f"🕐 {inst['cuando']}  ·  ⚠️ {inst['contras']}")
                    if i < len(r.get("instrumentos", [])) - 1: st.markdown("---")

                st.divider()
                st.caption(f"📋 {r['tesis']}")
                for fuente in ["Polymarket", "Kalshi", "Macro USA", "Noticias"]:
                    ev = [e for e in r["evidencia"] if e["fuente"] == fuente]
                    if not ev: continue
                    st.markdown(f"**{fuente}**")
                    for e in ev[:3]:
                        icon = "📈" if e["direccion"] == "ALZA" else ("📉" if e["direccion"] == "BAJA" else "➡️")
                        prob_str = f" `{e['prob']}%`" if e.get("prob") else ""
                        st.caption(f"{icon} {e['señal']}{prob_str} — peso `{e['peso']}`")
                st.caption("⚠️ Señal informativa. No constituye asesoría de inversión.")
    else:
        st.info("Sin señales consolidadas en este momento.")

# ── TAB PERFORMANCE ───────────────────────────────────────────────────────────
with tab_perf:
    st.markdown("### 💹 Dashboard de Performance")
    st.caption(f"Capital paper trading: USD {CAPITAL_INICIAL:,.0f}")

    with st.spinner(""):
        m = get_metricas_performance()
        benchmarks = get_benchmarks()

    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("CAPITAL ACTUAL", f"${m['capital_actual']:,.0f}", delta=f"{m['retorno_total_pct']:+.2f}%")
    with col2: st.metric("PnL TOTAL", f"${m['pnl_total']:+,.0f}")
    with col3: st.metric("PnL REALIZADO", f"${m['pnl_realizado']:+,.0f}")
    with col4: st.metric("PnL NO REALIZADO", f"${m['pnl_no_realizado']:+,.0f}")
    with col5: st.metric("DRAWDOWN MÁX.", f"{m['max_drawdown_pct']:.1f}%")

    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("WIN RATE", f"{m['win_rate']}%")
    with col2: st.metric("TRADES", m["n_trades"])
    with col3: st.metric("GANADORES", m["n_ganadores"])
    with col4: st.metric("PERDEDORES", m["n_perdedores"])
    with col5:
        pf = m["profit_factor"]
        st.metric("PROFIT FACTOR", f"{pf:.2f}" if pf != float("inf") else "∞")

    st.divider()

    # Benchmarks
    st.markdown("### 📊 vs Benchmarks (30 días)")
    col1, col2 = st.columns([1, 2])
    with col1:
        sistema_r = m["retorno_total_pct"]
        for nombre, retorno in benchmarks.items():
            color = "#22c55e" if retorno > 0 else "#ef4444"
            vs_sistema = sistema_r - retorno
            vs_color = "#22c55e" if vs_sistema >= 0 else "#ef4444"
            st.markdown(f'<div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid #1e293b"><span style="color:#94a3b8;font-size:0.82rem">{nombre}</span><span style="color:{color};font-family:monospace;font-weight:700">{retorno:+.2f}%</span></div>', unsafe_allow_html=True)
        st.markdown(f'<div style="display:flex;justify-content:space-between;padding:0.4rem 0;margin-top:0.2rem"><span style="color:#38bdf8;font-size:0.82rem;font-weight:700">SISTEMA</span><span style="color:#38bdf8;font-family:monospace;font-weight:700">{sistema_r:+.2f}%</span></div>', unsafe_allow_html=True)
    with col2:
        bench_names  = list(benchmarks.keys()) + ["Sistema"]
        bench_values = list(benchmarks.values()) + [sistema_r]
        bench_colors = ["#22c55e" if v >= 0 else "#ef4444" for v in bench_values]
        bench_colors[-1] = "#38bdf8"
        fig = go.Figure(go.Bar(x=bench_names, y=bench_values, marker_color=bench_colors,
            text=[f"{v:+.2f}%" for v in bench_values], textposition="outside",
            textfont=dict(color="#94a3b8", size=11)))
        fig.update_layout(**PLOT_LAYOUT, height=250, title="Retorno 30 días (%)")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Posiciones con PnL
    st.markdown("### 📂 Posiciones Abiertas")
    posiciones_pnl = m["posiciones_abiertas"]
    if posiciones_pnl:
        for p in posiciones_pnl:
            pnl = p["pnl_total"]; pct = p["pnl_pct"]
            color = "#22c55e" if pnl >= 0 else "#ef4444"
            with st.expander(f"{'▲' if pnl>=0 else '▼'} {p['ticker']}  ·  PnL: {pnl:+,.2f} USD ({pct:+.2f}%)  ·  {p['dias_abierta']} días"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Acción:** {p['accion']} · **Cantidad:** {p['cantidad']}")
                    st.markdown(f"**Días abierta:** {p['dias_abierta']}")
                with col2:
                    st.markdown(f"**Entrada:** `{p['precio_entrada']:,.2f}`  →  **Actual:** `{p['precio_actual']:,.2f}`")
                    st.markdown(f"**Monto:** USD {p['precio_entrada']*p['cantidad']:,.0f}")
                with col3:
                    if p.get("sl"): st.markdown(f"🛑 **SL:** `{p['sl']:,.2f}`")
                    if p.get("tp"): st.markdown(f"🎯 **TP:** `{p['tp']:,.2f}`")
    else:
        st.info("Sin posiciones abiertas. Ejecuta órdenes en IB Trading para ver PnL en tiempo real.")

    # Curva equity
    st.divider()
    st.markdown("### 📈 Curva de Equity")
    equity = m["equity_curve"]
    if len(equity) > 1:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(y=equity, mode="lines",
            line=dict(color="#38bdf8", width=2),
            fill="tozeroy", fillcolor="rgba(56,189,248,0.06)"))
        fig_eq.add_hline(y=CAPITAL_INICIAL, line_dash="dot", line_color="#334155",
                         annotation_text=f"Capital inicial: ${CAPITAL_INICIAL:,.0f}",
                         annotation_font_color="#475569")
        fig_eq.update_layout(**PLOT_LAYOUT, height=280, title="Capital (USD)")
        st.plotly_chart(fig_eq, use_container_width=True)
    else:
        st.caption("La curva de equity se construye con el historial de trades cerrados.")


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

# ── TAB OPCIONES ──────────────────────────────────────────────────────────────
with tab_opciones:
    st.markdown("### ⚙️ Estrategias de Opciones")
    st.caption("Sugerencias automáticas basadas en señales activas. Disponible: SPY, SQM, GLD")

    recomendaciones = st.session_state.get("recomendaciones", [])
    posiciones = get_posiciones_abiertas() if IB_DISPONIBLE else {}
    estrategias = get_estrategias_opciones(recomendaciones, posiciones)

    if estrategias:
        st.success(f"✅ {len(estrategias)} estrategia(s) identificada(s)")
        for est in estrategias:
            icon = "⬆" if "Comprar" in est["estrategia"] else "💰"
            with st.expander(f"{icon} {est['tipo']}  ·  {est['symbol']}  ·  Strike {est['strike_objetivo']}  ·  {est['dte_objetivo']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Subyacente:** `{est['symbol']}` · **Strike:** `{est['strike_objetivo']}`")
                    st.markdown(f"**Contratos:** {est['contratos']} · **Venc.:** {est['dte_objetivo']}")
                with col2:
                    if "costo_total_est" in est:
                        st.metric("COSTO TOTAL", f"USD {est['costo_total_est']:,.0f}")
                        st.metric("PÉRDIDA MÁX.", f"USD {est['max_perdida']:,.0f}")
                    elif "ingreso_est" in est:
                        st.metric("INGRESO EST.", f"USD {est['ingreso_est']:,.0f}")
                with col3:
                    st.caption(f"✅ {est['pros']}")
                    st.caption(f"⚠️ {est['contras']}")
                st.caption(f"📋 {est['razon']}")
                right = "Call" if est["right"] == "C" else "Put"
                st.code(f"TWS → {est['symbol']} → Options → {right} Strike {est['strike_objetivo']}\n{'Comprar' if 'Comprar' in est['tipo'] else 'Vender'} {est['contratos']} contrato(s) → Orden LMT midpoint")
    else:
        st.info("Sin estrategias disponibles. Se activan con señales ≥80% convicción sobre SPY, SQM o GLD.")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🟢 Comprar Call/Put**")
        st.caption("Alta convicción ≥80% · Horizonte corto · Pérdida = premium · Apalancamiento 5-10x · Strike ~5% OTM")
    with col2:
        st.markdown("**💰 Call Cubierto**")
        st.caption("Posición larga ≥100 acciones · Ingreso 1-2% mensual · Strike 5% OTM · Venc. 15-30 días")

# ── TAB IB ────────────────────────────────────────────────────────────────────
with tab_ib:
    st.markdown("### 🤖 IB Paper Trading — Ejecución Automática")
    if not IB_DISPONIBLE:
        st.error("ibapi no instalado. Ejecuta: pip install ibapi")
    else:
        st.markdown("""
        <div style="background:#0d1117;border:1px solid #1e293b;border-radius:8px;padding:0.75rem 1rem;margin-bottom:1rem;font-size:0.78rem;color:#64748b">
        <span style="color:#38bdf8;font-weight:700">POLÍTICA ACTIVA</span> &nbsp;·&nbsp;
        Capital: <span style="color:#f1f5f9">USD 100.000</span> &nbsp;·&nbsp;
        Máx/op: <span style="color:#f1f5f9">USD 10.000</span> &nbsp;·&nbsp;
        Horizonte: <span style="color:#f1f5f9">3 días</span> &nbsp;·&nbsp;
        Posiciones: <span style="color:#f1f5f9">5 máx</span> &nbsp;·&nbsp;
        Convicción: <span style="color:#22c55e">≥75%</span> &nbsp;·&nbsp;
        Riesgo: <span style="color:#22c55e">≤6/10</span>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([4, 1])
        with col2:
            if st.button("🔄 Actualizar cuenta", use_container_width=True):
                st.session_state.cuenta_ib = get_resumen_cuenta()

        if "cuenta_ib" in st.session_state and st.session_state.cuenta_ib:
            cuenta = st.session_state.cuenta_ib
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("NET LIQUIDATION", f"USD {cuenta.get('NetLiquidation',0):,.0f}")
            with col2: st.metric("CASH", f"USD {cuenta.get('TotalCashValue',0):,.0f}")
            with col3: st.metric("BUYING POWER", f"USD {cuenta.get('BuyingPower',0):,.0f}")

        st.divider()
        st.markdown("**📂 Posiciones Abiertas**")
        posiciones = get_posiciones_abiertas()
        if posiciones:
            rows = [{"Ticker":t, "Acción":p["accion"], "Cantidad":p["cantidad"],
                     "Precio entr.":p.get("precio_entrada","N/D"),
                     "SL":p.get("sl","N/D"), "TP":p.get("tp","N/D"),
                     "Días":(datetime.now()-datetime.fromisoformat(p["fecha_entrada"])).days,
                     "Vence":f"{max(0,3-(datetime.now()-datetime.fromisoformat(p['fecha_entrada'])).days)}d"}
                    for t,p in posiciones.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("Sin posiciones abiertas")

        st.divider()
        st.markdown("**🚀 Ejecutar Señales**")
        recomendaciones = st.session_state.get("recomendaciones", [])
        sv = [r for r in recomendaciones if r["conviccion"]>=75 and r["riesgo"]<=6 and r["n_fuentes"]>=2]

        if sv:
            for r in sv:
                ac = "#22c55e" if r["accion"]=="COMPRAR" else "#ef4444"
                ai = "⬆" if r["accion"]=="COMPRAR" else "⬇"
                st.markdown(f'<span style="color:{ac}">{ai} **{r["accion"]} {r["ib_ticker"]}**</span> &nbsp; Conv: `{r["conviccion"]}%` · Riesgo: `{r["riesgo"]}/10`', unsafe_allow_html=True)

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🧪 Simular (sin enviar)", use_container_width=True):
                    with st.spinner("Simulando..."):
                        res = ejecutar_señales(recomendaciones, modo_test=True)
                    st.json(res)
            with col2:
                if st.button("🚀 EJECUTAR EN IB PAPER", type="primary", use_container_width=True):
                    with st.spinner("Conectando a IB y ejecutando..."):
                        res = ejecutar_señales(recomendaciones, modo_test=False)
                    if res["ordenes_enviadas"]:
                        st.success(f"✅ {len(res['ordenes_enviadas'])} orden(es) enviada(s)")
                        for o in res["ordenes_enviadas"]:
                            st.caption(f"→ {o['accion']} {o['ticker']} · {o.get('cantidad','?')} uds · USD {o.get('monto_usd','?'):,.0f}" if isinstance(o.get('monto_usd'), (int,float)) else f"→ {o['accion']} {o['ticker']}")
                    if res["ordenes_rechazadas"]:
                        for o in res["ordenes_rechazadas"]:
                            st.warning(f"⚠️ {o['ticker']}: {o['razon']}")
                    if res["errores"]: st.error(" | ".join(res["errores"]))
                    st.rerun()
        else:
            st.caption("Sin señales que cumplan la política de inversión en este momento.")

# ── TAB IPSA ──────────────────────────────────────────────────────────────────
with tab_ipsa:
    st.markdown("### 🇨🇱 S&P/CLX IPSA — 30 acciones")
    with st.spinner(""):
        df_ipsa = get_precios_ipsa()
    if not df_ipsa.empty:
        amp = get_amplitud_mercado(df_ipsa)
        sesgo_col = "#22c55e" if amp["sesgo"]=="ALCISTA" else ("#ef4444" if amp["sesgo"]=="BAJISTA" else "#f59e0b")
        col1,col2,col3,col4 = st.columns(4)
        with col1: st.metric("SUBIENDO", amp["subiendo"])
        with col2: st.metric("BAJANDO", amp["bajando"])
        with col3: st.metric("NEUTRAS", amp["neutras"])
        with col4: st.metric("SESGO", amp["sesgo"])

        st.divider()
        top5, bottom5 = get_top_bottom_ipsa(df_ipsa, n=5)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🏆 Top 5**")
            for _, row in top5.iterrows():
                st.markdown(f'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1e293b"><span style="color:#94a3b8;font-size:0.82rem">{row["nombre"]}</span><span style="color:#22c55e;font-family:monospace;font-weight:700">{row["cambio_pct"]:+.2f}%</span></div>', unsafe_allow_html=True)
        with col2:
            st.markdown("**📉 Bottom 5**")
            for _, row in bottom5.iterrows():
                color = "#ef4444" if row["cambio_pct"] < 0 else "#22c55e"
                st.markdown(f'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1e293b"><span style="color:#94a3b8;font-size:0.82rem">{row["nombre"]}</span><span style="color:{color};font-family:monospace;font-weight:700">{row["cambio_pct"]:+.2f}%</span></div>', unsafe_allow_html=True)

        st.divider()
        fig = go.Figure(go.Bar(x=df_ipsa["ticker"], y=df_ipsa["cambio_pct"],
            marker_color=["#22c55e" if x>0 else "#ef4444" for x in df_ipsa["cambio_pct"]],
            text=[f"{x:+.2f}%" for x in df_ipsa["cambio_pct"]],
            textposition="outside", textfont=dict(size=9, color="#94a3b8")))
        fig.update_layout(**PLOT_LAYOUT, height=380, title="IPSA — Variación % del día")
        fig.update_xaxes(tickangle=-45, tickfont=dict(size=9))
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        df_sec = get_resumen_sectorial(df_ipsa)
        if not df_sec.empty:
            col1, col2 = st.columns([2,3])
            with col1:
                for _, row in df_sec.iterrows():
                    color = "#22c55e" if row["variacion_prom"]>0 else "#ef4444"
                    st.markdown(f'<div style="display:flex;justify-content:space-between;padding:0.25rem 0;border-bottom:1px solid #1e293b"><span style="color:#94a3b8;font-size:0.82rem">{row["sector"]}</span><span style="color:{color};font-family:monospace;font-weight:700">{row["variacion_prom"]:+.2f}%</span></div>', unsafe_allow_html=True)
            with col2:
                fig_sec = go.Figure(go.Bar(x=df_sec["sector"], y=df_sec["variacion_prom"],
                    marker_color=["#22c55e" if x>0 else "#ef4444" for x in df_sec["variacion_prom"]],
                    text=[f"{x:+.2f}%" for x in df_sec["variacion_prom"]], textposition="outside",
                    textfont=dict(size=10, color="#94a3b8")))
                fig_sec.update_layout(**PLOT_LAYOUT, height=280)
                fig_sec.update_xaxes(tickangle=-30, tickfont=dict(size=9))
                st.plotly_chart(fig_sec, use_container_width=True)

        st.divider()
        sectores = ["Todos"] + sorted(df_ipsa["sector"].unique().tolist())
        sf = st.selectbox("Filtrar sector", sectores)
        dm = df_ipsa if sf=="Todos" else df_ipsa[df_ipsa["sector"]==sf]
        st.dataframe(dm[["señal","nombre","ticker","sector","precio","cambio_pct","peso"]].rename(
            columns={"señal":"","nombre":"Empresa","ticker":"Ticker","sector":"Sector",
                     "precio":"Precio CLP","cambio_pct":"Var %","peso":"Peso"}),
            use_container_width=True, hide_index=True,
            column_config={"Var %":st.column_config.NumberColumn(format="%+.2f%%"),
                           "Precio CLP":st.column_config.NumberColumn(format="%,.0f")})

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



# ── TAB USA ───────────────────────────────────────────────────────────────────
with tab_usa:
    st.markdown("### 🇺🇸 USA — Activos & Macro")
    with st.spinner(""):
        df_usa = get_precios_usa(); macro_data = get_macro_usa()
    if not df_usa.empty:
        cols = st.columns(3)
        for i,(_, row) in enumerate(df_usa.iterrows()):
            with cols[i%3]: st.metric(row["ticker"], f"${row['precio']:,.2f}", delta=f"{row['cambio_pct']:+.2f}%",
                delta_color="normal" if row['cambio_pct']>=0 else "inverse")
    if macro_data:
        st.divider()
        cols = st.columns(4)
        for i,m_item in enumerate(macro_data):
            with cols[i%4]: st.metric(m_item["nombre"].upper(), f"{m_item['precio']:,.2f}",
                delta=f"{m_item['cambio_pct']:+.2f}%",
                delta_color="inverse" if m_item["inverso"] else "normal")
        st.divider()
        st.markdown("**🔗 Correlaciones → Chile**")
        for c in get_correlaciones_chile(macro_data)[:6]:
            score = c["score"]
            color = "#ef4444" if score>=3 else ("#f59e0b" if score>=1.5 else "#22c55e")
            with st.expander(f"Score {score}  ·  {c['tesis']}"):
                col1,col2 = st.columns(2)
                with col1: st.caption(f"{c['indicador']} ({c['cambio_pct']:+.2f}%)")
                with col2: st.caption(f"{c['activo_chile']} → {c['direccion']}")

# ── TAB DIVERGENCIAS ──────────────────────────────────────────────────────────
with tab_div:
    st.markdown("### ⚡ Divergencias")
    with st.spinner(""):
        df_poly_div = get_mercados_chile(limit=200)
        bcch_div = get_resumen_bcch()
        spread_div = get_spread_btc(bcch_div.get("CLP/USD",892.0) or 892.0)
        df_result = calcular_divergencias(df_poly_div, spread_div)
    if not df_result.empty:
        nuevas = guardar_senales(df_result)
        if nuevas>0: st.success(f"✅ {nuevas} señal(es) guardada(s) en historial")
        top_d = df_result.iloc[0]
        st.markdown(f'<div style="background:#0d1117;border:1px solid #1e293b;border-left:3px solid #38bdf8;border-radius:8px;padding:0.75rem 1rem;margin-bottom:1rem"><span style="color:#38bdf8;font-weight:700">SEÑAL PRINCIPAL</span> &nbsp; {top_d["Señal"][:70]} &nbsp;·&nbsp; <span style="color:#f1f5f9">{top_d["Prob %"]}%</span> &nbsp;·&nbsp; {top_d["Dirección"]} &nbsp;·&nbsp; Score <span style="color:#38bdf8;font-weight:700">{top_d["Score"]}</span></div>', unsafe_allow_html=True)
        st.dataframe(df_result[["Señal","Prob %","Dirección","Activos Chile","Score","Tesis"]],
            use_container_width=True, hide_index=True,
            column_config={"Score":st.column_config.ProgressColumn("Score",min_value=0,max_value=20,format="%.2f"),
                           "Prob %":st.column_config.NumberColumn(format="%.1f%%"),
                           "Tesis":st.column_config.TextColumn(width="large")})
    else: st.info("Sin divergencias detectadas en este momento.")

# ── TAB KALSHI ────────────────────────────────────────────────────────────────
with tab_kalshi:
    st.markdown("### 🎰 Kalshi — CFTC Regulated")
    with st.spinner(""):
        senales_kalshi = get_kalshi_resumen()
    if senales_kalshi:
        col1,col2,col3 = st.columns(3)
        with col1: st.metric("SEÑALES ACTIVAS", len(senales_kalshi))
        with col2: st.metric("📈 ALZA", sum(1 for s in senales_kalshi if s["direccion"]=="ALZA"))
        with col3: st.metric("📉 BAJA", sum(1 for s in senales_kalshi if s["direccion"]=="BAJA"))
        st.divider()
        series_vistas = set()
        for s in senales_kalshi:
            if s["serie"] not in series_vistas:
                st.markdown(f"**{s['serie']}**")
                series_vistas.add(s["serie"])
            prob = s["prob_pct"]
            color = "#22c55e" if prob>65 else ("#ef4444" if prob<35 else "#f59e0b")
            with st.expander(f"{'▲' if prob>50 else '▼'} {s['titulo'][:85]}  ·  {prob}%  ·  Score {s['score']}"):
                col1,col2 = st.columns(2)
                with col1: st.caption(f"Prob: {prob}% · Dir: {s['direccion']} · Activos: {', '.join(s['activos_impacto'])}")
                with col2: st.caption(f"Score: {s['score']} · Cierre: {s['cierre']} · Vol: {s['volumen']}")

# ── TAB NOTICIAS ──────────────────────────────────────────────────────────────
with tab_noticias:
    st.markdown("### 📰 Noticias Chile — Análisis de Sentiment")
    with st.spinner("Cargando y analizando sentiment..."):
        noticias_raw = get_noticias_google()
        noticias = analizar_noticias_batch(noticias_raw) if noticias_raw else []

    if noticias:
        # Resumen sentiment
        resumen_sent = get_resumen_sentiment(noticias)
        sesgo_color = resumen_sent.get("sesgo_color", "#64748b")
        sesgo = resumen_sent.get("sesgo", "NEUTRO")

        st.markdown(
            f'<div style="background:#0d1117;border:1px solid {sesgo_color}44;'
            f'border-left:3px solid {sesgo_color};border-radius:8px;'
            f'padding:0.6rem 1rem;margin-bottom:0.75rem">'
            f'<span style="color:{sesgo_color};font-weight:700">SENTIMENT MERCADO: {sesgo}</span>'
            f' &nbsp;·&nbsp; <span style="color:#94a3b8;font-size:0.82rem">'
            f'🟢 {resumen_sent.get("positivas",0)} positivas &nbsp;'
            f'🔴 {resumen_sent.get("negativas",0)} negativas &nbsp;'
            f'⚪ {resumen_sent.get("neutras",0)} neutras'
            f' &nbsp;·&nbsp; Ratio positivo: {resumen_sent.get("ratio_positivo",0)}%</span></div>',
            unsafe_allow_html=True
        )

        # Sentiment por activo
        sent_activos = get_sentiment_por_activo(noticias)
        if sent_activos:
            st.markdown("**📊 Sentiment por Activo**")
            cols_sa = st.columns(min(len(sent_activos), 5))
            for i, (activo, data) in enumerate(list(sent_activos.items())[:5]):
                with cols_sa[i]:
                    color = data["color"]
                    st.markdown(
                        f'<div style="background:#0d1117;border:1px solid {color}44;'
                        f'border-radius:6px;padding:0.4rem 0.6rem;text-align:center">'
                        f'<div style="color:#64748b;font-size:0.68rem">{activo.replace(".SN","")}</div>'
                        f'<div style="color:{color};font-weight:700;font-size:0.9rem">{data["tono"]}</div>'
                        f'<div style="color:#475569;font-size:0.68rem">{data["n_noticias"]} noticias</div></div>',
                        unsafe_allow_html=True
                    )

        st.divider()

        # Filtros
        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        with col_f1: min_score = st.slider("Score mínimo", 0, 15, 3)
        with col_f2: busqueda_n = st.text_input("🔍 Buscar", placeholder="litio, cobre, tasa...")
        with col_f3:
            filtro_sent = st.selectbox("Filtrar sentiment", ["Todos", "🟢 Positivo", "🔴 Negativo", "⚪ Neutro"])

        noticias_filtradas = [n for n in noticias if n["score"] >= min_score]
        if busqueda_n:
            noticias_filtradas = [n for n in noticias_filtradas if busqueda_n.lower() in n["titulo"].lower()]
        if filtro_sent == "🟢 Positivo":
            noticias_filtradas = [n for n in noticias_filtradas if n.get("sentiment", {}).get("señal", 0) > 0]
        elif filtro_sent == "🔴 Negativo":
            noticias_filtradas = [n for n in noticias_filtradas if n.get("sentiment", {}).get("señal", 0) < 0]
        elif filtro_sent == "⚪ Neutro":
            noticias_filtradas = [n for n in noticias_filtradas if n.get("sentiment", {}).get("señal", 0) == 0]

        st.caption(f"{len(noticias_filtradas)} noticias")

        for n in noticias_filtradas:
            score = n["score"]
            sent  = n.get("sentiment", {})
            tono  = sent.get("tono", "NEUTRO")
            color_sent = sent.get("color", "#64748b")
            estrellas  = "⭐" * sent.get("estrellas", 3)
            tags  = " · ".join(n.get("keywords", [])) if n.get("keywords") else ""

            with st.expander(
                f'[{score}] ' +
                (f'🟢' if sent.get("señal",0) > 0 else (f'🔴' if sent.get("señal",0) < 0 else f'⚪')) +
                f' {n["titulo"][:90]}'
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"**{n['fuente']}** · {n.get('fecha','')[:30]}")
                    if tags: st.caption(f"🏷 {tags}")
                    st.markdown(
                        f'<span style="background:{color_sent}22;color:{color_sent};'
                        f'border:1px solid {color_sent}44;border-radius:4px;'
                        f'padding:2px 8px;font-size:0.72rem;font-weight:700">'
                        f'{tono} {estrellas} conf:{sent.get("confianza",0):.2f}</span>',
                        unsafe_allow_html=True
                    )
                with col2:
                    if n.get("url"): st.link_button("🔗 Leer", n["url"])

# ── TAB HISTORIAL ─────────────────────────────────────────────────────────────
with tab_hist:
    st.markdown("### 📈 Historial de Señales")
    stats = get_estadisticas()
    col1,col2,col3,col4 = st.columns(4)
    with col1: st.metric("TOTAL", stats["total"])
    with col2: st.metric("CORRECTAS", stats["correctas"])
    with col3: st.metric("INCORRECTAS", stats["incorrectas"])
    with col4:
        tasa = stats["tasa_exito"]
        st.metric("TASA ÉXITO", f"{tasa}%")
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
            sel = st.selectbox("Señal a evaluar", ops)
            res_radio = st.radio("Resultado real", ["correcto","incorrecto"], horizontal=True)
            if st.button("Guardar evaluación"):
                idx = ops.index(sel)
                actualizar_resultado(pendientes[idx][1], pendientes[idx][0][:10], res_radio)
                st.success("✅ Guardado"); st.rerun()

# ── TAB BACKTESTING ───────────────────────────────────────────────────────────
with tab_bt:
    st.markdown("### 🔬 Backtesting Automático")
    st.caption("Evalúa señales históricas comparando precio al momento de la señal vs precio actual.")
    stats_bt = get_estadisticas_backtest()
    if stats_bt:
        col1,col2,col3,col4,col5 = st.columns(5)
        with col1: st.metric("TOTAL", stats_bt.get("total",0))
        with col2: st.metric("CORRECTAS", stats_bt.get("correctas",0))
        with col3: st.metric("INCORRECTAS", stats_bt.get("incorrectas",0))
        with col4: st.metric("PENDIENTES", stats_bt.get("pendientes",0))
        with col5:
            tasa = stats_bt.get("tasa_exito",0)
            st.metric("TASA ÉXITO", f"{tasa}%")
        st.divider()
        col1,col2 = st.columns([2,1])
        with col1: dias_min = st.slider("Días mínimos para evaluar", 0, 7, 1)
        with col2:
            if st.button("🔬 Ejecutar Backtesting", type="primary", use_container_width=True):
                with st.spinner("Evaluando señales..."):
                    res_bt = ejecutar_backtest(dias_minimos=dias_min)
                st.success(f"✅ Evaluadas: {res_bt['evaluadas']} · Correctas: {res_bt['correctas']} · Incorrectas: {res_bt['incorrectas']} · Tasa: {res_bt['tasa_exito']}%")
                if res_bt["detalle"]:
                    df_bt_det = pd.DataFrame(res_bt["detalle"])
                    df_bt_det["icon"] = df_bt_det["resultado"].map({"correcto":"✅","incorrecto":"❌","neutral":"➡️","pendiente":"⏳"})
                    st.dataframe(df_bt_det[["icon","fecha","señal","direccion","ticker","precio_entrada","precio_salida","movimiento_pct","dias"]].rename(
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
