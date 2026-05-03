import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from streamlit_autorefresh import st_autorefresh
from data.polymarket import get_active_markets, get_mercados_chile
from data.yahoo_finance import get_precios_usa, get_precios_chile
from data.bcch import get_resumen_bcch
from data.bcch_completo import get_macro_chile_completo, get_contexto_macro, get_precios_cochilco
from data.buda import get_spread_btc
from data.noticias_chile import get_noticias_google
from data.historial import guardar_senales, get_historial, get_estadisticas, actualizar_resultado
from data.kalshi import get_kalshi_resumen
from data.macro_usa import get_macro_usa, get_correlaciones_chile
from data.ipsa import get_precios_ipsa, get_resumen_sectorial, get_top_bottom_ipsa, get_amplitud_mercado
from data.arbitraje import get_resumen_arbitraje, COSTOS
from data.cmf import get_hechos_esenciales, get_resumen_cmf
from data.volumen import get_resumen_volumen, correlacionar_con_cmf
from data.put_call import get_resumen_pc, get_señal_consolidada_pc
from engine.analisis_tecnico import get_señales_tecnicas, get_analisis_completo
from data.google_trends import get_resumen_trends, get_señales_trends
from engine.fear_greed import calcular_fear_greed, get_fear_greed_simple
from engine.divergence import calcular_divergencias
from engine.recomendaciones import consolidar_señales, generar_recomendaciones, enviar_alertas_nuevas
from engine.opciones import get_estrategias_opciones, SUBYACENTES_OPCIONES
from engine.backtesting import ejecutar_backtest, get_estadisticas_backtest
from engine.performance import get_metricas_performance, get_benchmarks, CAPITAL_INICIAL
from engine.cierre_automatico import verificar_posiciones, get_log_cierres
from engine.motor_automatico import activar_motor, pausar_motor, get_resumen_motor, ciclo_trading_automatico, PARAMS
from engine.correlaciones import get_correlaciones_ipsa_completo, get_correlacion_rodante, get_divergencias_correlacion, get_correlaciones_ipsa_interno
from engine.portafolio import get_analisis_portafolio, UNIVERSO_DEFAULT, TASA_LIBRE_RIESGO
from engine.nlp_sentiment import analizar_noticias_batch, get_resumen_sentiment, get_sentiment_por_activo

try:
    from engine.ib_executor import ejecutar_señales, get_posiciones_abiertas, get_resumen_cuenta
    IB_DISPONIBLE = True
except ImportError:
    IB_DISPONIBLE = False

# ── CONFIG ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Terminal Chile",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st_autorefresh(interval=15 * 60 * 1000, key="autorefresh")

if "alertas_enviadas" not in st.session_state:
    st.session_state.alertas_enviadas = set()

# Motor automático — ejecutar ciclo si está activo
if "ultima_verificacion" not in st.session_state:
    st.session_state.ultima_verificacion = None

ahora = datetime.now()
ultima = st.session_state.ultima_verificacion
if ultima is None or (ahora - ultima).seconds > 300:
    try:
        estado_motor = get_resumen_motor()
        if estado_motor.get("activo") and not estado_motor.get("pausado"):
            resultado_ciclo = ciclo_trading_automatico()
            st.session_state.resultado_ciclo = resultado_ciclo
        else:
            resumen_cierre = verificar_posiciones(modo_test=False, auto_cerrar=True)
            st.session_state.resumen_cierre = resumen_cierre
            if resumen_cierre.get("cierres"):
                st.session_state.alertas_cierre = resumen_cierre["cierres"]
        st.session_state.ultima_verificacion = ahora
    except Exception as e:
        pass

# Motor automático — ejecutar ciclo si está activo
if "ultima_verificacion" not in st.session_state:
    st.session_state.ultima_verificacion = None

ahora = datetime.now()
ultima = st.session_state.ultima_verificacion
if ultima is None or (ahora - ultima).seconds > 300:
    try:
        estado_motor = get_resumen_motor()
        if estado_motor.get("activo") and not estado_motor.get("pausado"):
            resultado_ciclo = ciclo_trading_automatico()
            st.session_state.resultado_ciclo = resultado_ciclo
        else:
            resumen_cierre = verificar_posiciones(modo_test=False, auto_cerrar=True)
            st.session_state.resumen_cierre = resumen_cierre
            if resumen_cierre.get("cierres"):
                st.session_state.alertas_cierre = resumen_cierre["cierres"]
        st.session_state.ultima_verificacion = ahora
    except Exception as e:
        pass

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #070d1a; color: #e2e8f0; }
[data-testid="stHeader"] { background-color: #070d1a; }
.block-container { padding-top: 1.2rem; padding-bottom: 1rem; max-width: 1400px; }

/* Tabs */
[data-testid="stTabs"] button {
    background: transparent;
    color: #475569;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 0.5rem 1.2rem;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #e2e8f0;
    border-bottom: 2px solid #3b82f6;
    background: transparent;
}
[data-testid="stTabs"] button:hover { color: #94a3b8; }
[data-testid="stTabs"] [data-testid="stTabsHeader"] {
    border-bottom: 1px solid #1e293b;
}

/* Métricas */
[data-testid="metric-container"] {
    background: #0d1521;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 0.65rem 0.9rem;
}
[data-testid="metric-container"] label {
    color: #475569 !important;
    font-size: 0.68rem !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 600;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #f1f5f9 !important;
    font-size: 1.3rem !important;
    font-weight: 700;
    font-family: 'SF Mono', 'Courier New', monospace;
}

/* Expanders */
[data-testid="stExpander"] {
    background: #0d1521;
    border: 1px solid #1e293b;
    border-radius: 6px;
    margin-bottom: 0.3rem;
}
[data-testid="stExpander"] summary {
    color: #cbd5e1;
    font-size: 0.83rem;
    padding: 0.55rem 0.8rem;
}

/* Botones */
[data-testid="baseButton-primary"] {
    background: #1d4ed8 !important;
    border: none !important;
    border-radius: 5px !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
}
[data-testid="baseButton-secondary"] {
    background: #0d1521 !important;
    border: 1px solid #1e293b !important;
    color: #64748b !important;
    border-radius: 5px !important;
    font-size: 0.8rem !important;
}

/* DataFrames */
[data-testid="stDataFrame"] { border: 1px solid #1e293b; border-radius: 6px; }
.stDataFrame td, .stDataFrame th { font-size: 0.8rem !important; }

hr { border-color: #1e293b; margin: 0.8rem 0; }
.stCaption { color: #475569 !important; font-size: 0.72rem !important; }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0d1521; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }

/* Alertas */
[data-testid="stAlert"] { border-radius: 6px; font-size: 0.82rem; }

/* Inputs */
[data-testid="stTextInput"] input, [data-testid="stSelectbox"] > div {
    background: #0d1521 !important;
    border-color: #1e293b !important;
    color: #e2e8f0 !important;
    font-size: 0.82rem !important;
}
</style>
""", unsafe_allow_html=True)

# ── HELPERS ───────────────────────────────────────────────────────────────────
PLOT_BASE = dict(
    paper_bgcolor="#0d1521", plot_bgcolor="#0d1521",
    font=dict(color="#64748b", size=10),
    margin=dict(t=35, b=30, l=40, r=15),
)

def card(titulo, valor, subtitulo=None, color="#3b82f6", ancho="100%"):
    sub = f'<div style="color:#475569;font-size:0.7rem;margin-top:3px">{subtitulo}</div>' if subtitulo else ""
    return f"""
    <div style="background:#0d1521;border:1px solid #1e293b;border-top:2px solid {color};
    border-radius:6px;padding:0.7rem 0.9rem;width:{ancho}">
        <div style="color:#475569;font-size:0.68rem;text-transform:uppercase;
        letter-spacing:0.1em;font-weight:600">{titulo}</div>
        <div style="color:#f1f5f9;font-size:1.25rem;font-weight:700;
        font-family:monospace;margin-top:4px">{valor}</div>
        {sub}
    </div>"""

def semaforo(estado, texto):
    colores = {"ACTUAR": "#22c55e", "MONITOREAR": "#f59e0b", "EVITAR": "#ef4444", "NEUTRAL": "#475569"}
    c = colores.get(estado, "#475569")
    return f'<span style="background:{c}22;color:{c};border:1px solid {c}44;border-radius:4px;padding:2px 10px;font-size:0.72rem;font-weight:700;letter-spacing:0.05em">{estado}</span>'

# ── HEADER ────────────────────────────────────────────────────────────────────
col_h1, col_h2, col_h3 = st.columns([3, 2, 2])
with col_h1:
    st.markdown(
        '<div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;letter-spacing:0.02em">'
        'Trading Terminal</div>'
        '<div style="font-size:0.72rem;color:#334155;margin-top:2px">'
        'Chile · Análisis integrado de mercados</div>',
        unsafe_allow_html=True
    )
with col_h2:
    now = datetime.now()
    st.markdown(
        f'<div style="text-align:right;padding-top:4px">'
        f'<span style="color:#94a3b8;font-family:monospace;font-size:0.9rem">{now.strftime("%H:%M")}</span>'
        f'<span style="color:#334155;font-size:0.72rem;margin-left:8px">{now.strftime("%d %b %Y")}</span></div>',
        unsafe_allow_html=True
    )
with col_h3:
    try:
        fg_score, fg_clase, fg_color = get_fear_greed_simple()
    except:
        fg_score, fg_clase, fg_color = 50, "NEUTRO", "#f59e0b"
    st.markdown(
        f'<div style="text-align:right;padding-top:4px">' +
        f'<span style="color:#22c55e;font-size:0.72rem;font-weight:600">● EN VIVO</span>' +
        f'<span style="color:#334155;font-size:0.68rem;margin-left:8px">Actualización: 15 min</span><br>' +
        f'<span style="background:{fg_color}22;color:{fg_color};border:1px solid {fg_color}44;' +
        f'border-radius:4px;padding:1px 8px;font-size:0.7rem;font-weight:700">' +
        f'F&G: {fg_score}/100 · {fg_clase}</span></div>',
        unsafe_allow_html=True
    )
st.markdown('<hr style="border-color:#1e293b;margin:0.5rem 0 0.8rem 0">', unsafe_allow_html=True)

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_resumen, tab_mercado, tab_oportunidades, tab_portafolio, tab_ejecucion = st.tabs([
    "Resumen Ejecutivo",
    "Mercado",
    "Oportunidades",
    "Portafolio",
    "Ejecución",
])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — RESUMEN EJECUTIVO
# ════════════════════════════════════════════════════════════════════════════════
with tab_resumen:
    with st.spinner("Cargando análisis..."):
        # Datos macro
        ctx_macro    = get_contexto_macro()
        macro_cl     = get_macro_chile_completo()
        bcch         = get_resumen_bcch()
        clp          = bcch.get("CLP/USD", 892.0)
        macro_usa    = get_macro_usa()
        macro_corr   = get_correlaciones_chile(macro_usa)

        # Señales
        poly_df      = get_mercados_chile(limit=200)
        kalshi_list  = get_kalshi_resumen()
        noticias_raw = get_noticias_google()
        noticias     = analizar_noticias_batch(noticias_raw) if noticias_raw else []
        # Obtener Fear & Greed, CMF y Volumen para motor integrado
        try:
            fg_data = calcular_fear_greed()
        except:
            fg_data = None
        try:
            cmf_data = get_hechos_esenciales(solo_ipsa=True, limit=20)
        except:
            cmf_data = None
        try:
            vol_resumen = get_resumen_volumen()
            vol_data = correlacionar_con_cmf(vol_resumen.get("top_alertas", []))
        except:
            vol_data = None

        try:
            pc_señales = get_señal_consolidada_pc()
        except:
            pc_señales = None

        try:
            at_señales = get_señales_tecnicas(min_conviccion=60)
        except:
            at_señales = None
        try:
            gt_señales = get_señales_trends(min_score=2)
        except:
            gt_señales = None

        activos      = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias,
                                          fear_greed=fg_data, cmf_hechos=cmf_data,
                                          vol_alertas=vol_data, put_call=pc_señales,
                                          analisis_tecnico=at_señales,
                                          google_trends=gt_señales)
        recomendaciones = generar_recomendaciones(activos)
        st.session_state.recomendaciones = recomendaciones

        # Alertas Telegram
        n_alertas, st.session_state.alertas_enviadas = enviar_alertas_nuevas(
            recomendaciones, st.session_state.alertas_enviadas)

        # Performance
        m_perf = get_metricas_performance()

        # Sentiment noticias
        sent_resumen = get_resumen_sentiment(noticias)

    # ── Bloque superior: ciclo + KPIs macro
    ciclo = ctx_macro.get("ciclo", "NEUTRO")
    ciclo_col = {"EXPANSIÓN":"#22c55e","MODERADO":"#f59e0b","NEUTRO":"#475569","CONTRACCIÓN":"#ef4444"}.get(ciclo,"#475569")

    col_ciclo, col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns([2,1,1,1,1])
    with col_ciclo:
        st.markdown(
            f'<div style="background:#0d1521;border:1px solid {ciclo_col}33;border-left:3px solid {ciclo_col};'
            f'border-radius:6px;padding:0.7rem 1rem;height:72px">'
            f'<div style="color:#475569;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em">Ciclo Económico</div>'
            f'<div style="color:{ciclo_col};font-size:1.1rem;font-weight:700;margin-top:4px">{ciclo}</div></div>',
            unsafe_allow_html=True
        )
    dolar = macro_cl.get("dolar",{}).get("valor")
    tpm   = macro_cl.get("tpm",{}).get("valor")
    cobre = macro_cl.get("libra_cobre",{}).get("valor")
    ipc   = macro_cl.get("ipc",{}).get("valor")
    with col_kpi1: st.metric("CLP / USD", f"${dolar:,.0f}" if dolar else "N/D")
    with col_kpi2: st.metric("TPM", f"{tpm}%" if tpm else "N/D")
    with col_kpi3: st.metric("Cobre USD/lb", f"{cobre:.2f}" if cobre else "N/D")
    with col_kpi4: st.metric("IPC Mensual", f"{ipc}%" if ipc else "N/D")

    st.divider()

    # ── Fear & Greed Index
    try:
        fg = calcular_fear_greed()
        fg_score = fg["score"]
        fg_color = fg["color"]
        fg_clase = fg["clasificacion"]

        # Barra visual
        barra_llena  = int(fg_score / 10)
        barra_vacia  = 10 - barra_llena
        barra_visual = "█" * barra_llena + "░" * barra_vacia

        st.markdown(
            f'<div style="background:#0d1521;border:1px solid #1e293b;border-radius:6px;padding:0.65rem 1rem;margin-bottom:0.5rem">' +
            f'<div style="display:flex;justify-content:space-between;align-items:center">' +
            f'<div>' +
            f'<span style="color:#475569;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em">Fear & Greed Index Chile</span><br>' +
            f'<span style="color:{fg_color};font-size:1.1rem;font-weight:700;font-family:monospace">{fg_score}/100</span>' +
            f'<span style="color:{fg_color};font-size:0.82rem;font-weight:600;margin-left:8px">{fg_clase}</span>' +
            f'</div>' +
            f'<div style="text-align:right">' +
            f'<span style="color:{fg_color};font-family:monospace;font-size:0.9rem;letter-spacing:2px">{barra_visual}</span><br>' +
            f'<span style="color:#475569;font-size:0.72rem">{fg["descripcion"]}</span>' +
            f'</div></div>' +
            f'<div style="display:flex;gap:1.5rem;margin-top:0.4rem">',
            unsafe_allow_html=True
        )
        for key, c in fg["componentes"].items():
            cc = "#22c55e" if c["score"] >= 55 else ("#ef4444" if c["score"] <= 45 else "#f59e0b")
            st.markdown(
                f'<span style="color:#475569;font-size:0.68rem">{c["nombre"].split("(")[0].strip()}: ' +
                f'<span style="color:{cc};font-weight:600">{c["score"]}</span></span> &nbsp;',
                unsafe_allow_html=True
            )
        st.markdown('</div>', unsafe_allow_html=True)
    except Exception as e:
        st.caption(f"Fear & Greed no disponible: {e}")

    st.divider()

    # ── Top 3 oportunidades
    st.markdown("#### Principales Oportunidades")
    st.caption("Señales consolidadas desde Polymarket, Kalshi, Macro USA y análisis de noticias.")

    if recomendaciones:
        top3 = recomendaciones[:3]
        for idx, r in enumerate(top3):
            accion = r["accion"]
            conv   = r["conviccion"]
            riesgo = r["riesgo"]
            h      = r.get("horizonte", {})
            precio = r.get("precio_actual")
            sl     = r.get("stop_loss")
            tp     = r.get("take_profit")

            # Estado semáforo
            if conv >= 80 and riesgo <= 4:
                estado = "ACTUAR"
            elif conv >= 65 and riesgo <= 6:
                estado = "MONITOREAR"
            else:
                estado = "NEUTRAL"

            color_accion = "#22c55e" if accion == "COMPRAR" else "#ef4444"
            rr_str = ""
            if precio and sl and tp and abs(precio-sl) > 0:
                rr = round(abs(tp-precio)/abs(precio-sl), 1)
                rr_str = f" · R/R 1:{rr}"

            with st.expander(
                f"[{idx+1}]  {accion} {r['ib_ticker']}  —  {r['descripcion'][:60]}  "
                f"·  Convicción {conv}%  ·  Riesgo {riesgo}/10"
            ):
                col_a, col_b, col_c = st.columns([2, 2, 1])
                with col_a:
                    st.markdown(
                        f'<div style="margin-bottom:0.5rem">{semaforo(estado, "")}</div>',
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        f'**Acción:** <span style="color:{color_accion};font-weight:700">{accion} {r["ib_ticker"]}</span>',
                        unsafe_allow_html=True
                    )
                    st.markdown(f"**Por qué:** {r['tesis']}")
                    st.markdown(f"**Horizonte:** {h.get('label','')} — {h.get('dias','')}")
                with col_b:
                    st.progress(conv/100, text=f"Convicción: {conv}%")
                    st.progress(riesgo/10, text=f"Riesgo: {riesgo}/10")
                    if precio and sl and tp:
                        st.caption(f"Entrada: {precio:,.2f}  ·  SL: {sl:,.2f}  ·  TP: {tp:,.2f}{rr_str}")
                    st.caption(f"Fuentes: {', '.join(r['fuentes'])}")
                with col_c:
                    if accion == "COMPRAR":
                        st.markdown('<div style="background:#22c55e15;border:1px solid #22c55e33;border-radius:5px;padding:0.6rem;text-align:center;color:#22c55e;font-weight:700;font-size:0.85rem">LARGO</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="background:#ef444415;border:1px solid #ef444433;border-radius:5px;padding:0.6rem;text-align:center;color:#ef4444;font-weight:700;font-size:0.85rem">CORTO</div>', unsafe_allow_html=True)
                    if r["ib_ticker"] in SUBYACENTES_OPCIONES:
                        st.caption("Opciones disponibles")

                st.divider()
                st.markdown("**Cómo ejecutar:**")
                inst = r.get("instrumentos", [{}])[0]
                st.caption(f"{inst.get('vehiculo','')} — {inst.get('razon','')}")
    else:
        st.info("No hay señales consolidadas en este momento.")

    st.divider()

    # ── Resumen de mercado y alertas activas
    col_sent, col_port, col_arb = st.columns(3)

    with col_sent:
        st.markdown("**Sentiment de Mercado**")
        sesgo = sent_resumen.get("sesgo", "NEUTRO")
        sc = {"ALCISTA":"#22c55e","BAJISTA":"#ef4444","NEUTRO":"#475569"}.get(sesgo,"#475569")
        st.markdown(
            f'<div style="color:{sc};font-weight:700;font-size:1rem">{sesgo}</div>'
            f'<div style="color:#475569;font-size:0.75rem;margin-top:4px">'
            f'{sent_resumen.get("positivas",0)} positivas · {sent_resumen.get("negativas",0)} negativas · '
            f'Ratio {sent_resumen.get("ratio_positivo",0)}%</div>',
            unsafe_allow_html=True
        )
        if sent_resumen.get("top_positiva"):
            st.caption(f"Mejor: {sent_resumen['top_positiva'][:60]}")
        if sent_resumen.get("top_negativa"):
            st.caption(f"Peor: {sent_resumen['top_negativa'][:60]}")

    with col_port:
        st.markdown("**Portafolio Paper Trading**")
        pnl = m_perf.get("pnl_total", 0)
        ret = m_perf.get("retorno_total_pct", 0)
        cap = m_perf.get("capital_actual", CAPITAL_INICIAL)
        color_pnl = "#22c55e" if pnl >= 0 else "#ef4444"
        st.markdown(
            f'<div style="color:#f1f5f9;font-weight:700;font-family:monospace">USD {cap:,.0f}</div>'
            f'<div style="color:{color_pnl};font-size:0.78rem;margin-top:2px">'
            f'PnL: USD {pnl:+,.0f} ({ret:+.2f}%)</div>'
            f'<div style="color:#475569;font-size:0.72rem;margin-top:2px">'
            f'{m_perf.get("n_trades",0)} trades · Win rate {m_perf.get("win_rate",0)}%</div>',
            unsafe_allow_html=True
        )

    with col_arb:
        st.markdown("**Arbitraje ADR**")
        with st.spinner(""):
            arb = get_resumen_arbitraje()
        n_op = arb.get("oportunidades", 0)
        mejor = arb.get("mejor_spread")
        color_arb = "#22c55e" if n_op > 0 else "#475569"
        st.markdown(
            f'<div style="color:{color_arb};font-weight:700">{n_op} oportunidades detectadas</div>',
            unsafe_allow_html=True
        )
        if mejor:
            st.caption(f"{mejor['nombre']}: spread {abs(mejor['spread_bruto_pct']):.3f}%")
        st.caption(f"CLP/USD: {arb.get('clp_usd',0):,.2f}")

    # Señales macro relevantes
    señales_macro = ctx_macro.get("señales", [])
    if señales_macro:
        st.divider()
        st.markdown("**Señales del Entorno Macro**")
        for s in señales_macro:
            st.caption(s)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — MERCADO
# ════════════════════════════════════════════════════════════════════════════════
with tab_mercado:
    sub_ipsa, sub_macro, sub_cmf, sub_vol, sub_at, sub_corr, sub_noticias = st.tabs([
        "IPSA", "Macro Chile", "CMF Hechos Esenciales", "Volumen Anormal", "Análisis Técnico", "Correlaciones", "Noticias"
    ])

    # ── Sub-tab IPSA
    with sub_ipsa:
        with st.spinner(""):
            df_ipsa = get_precios_ipsa()
        if not df_ipsa.empty:
            amp = get_amplitud_mercado(df_ipsa)
            sc_sesgo = {"ALCISTA":"#22c55e","BAJISTA":"#ef4444","NEUTRO":"#475569"}.get(amp["sesgo"],"#475569")
            col1,col2,col3,col4 = st.columns(4)
            with col1: st.metric("Subiendo", amp["subiendo"])
            with col2: st.metric("Bajando", amp["bajando"])
            with col3: st.metric("Neutras", amp["neutras"])
            with col4: st.metric("Sesgo del mercado", amp["sesgo"])

            st.divider()
            top5, bot5 = get_top_bottom_ipsa(df_ipsa, 5)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Mayores alzas**")
                for _, r in top5.iterrows():
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1a2535">'
                        f'<span style="color:#94a3b8;font-size:0.8rem">{r["nombre"]}</span>'
                        f'<span style="color:#22c55e;font-family:monospace;font-size:0.8rem;font-weight:600">{r["cambio_pct"]:+.2f}%</span></div>',
                        unsafe_allow_html=True
                    )
            with col2:
                st.markdown("**Mayores bajas**")
                for _, r in bot5.iterrows():
                    color_b = "#ef4444" if r["cambio_pct"] < 0 else "#22c55e"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1a2535">'
                        f'<span style="color:#94a3b8;font-size:0.8rem">{r["nombre"]}</span>'
                        f'<span style="color:{color_b};font-family:monospace;font-size:0.8rem;font-weight:600">{r["cambio_pct"]:+.2f}%</span></div>',
                        unsafe_allow_html=True
                    )

            st.divider()
            fig = go.Figure(go.Bar(
                x=df_ipsa["ticker"], y=df_ipsa["cambio_pct"],
                marker_color=["#22c55e" if x>0 else "#ef4444" for x in df_ipsa["cambio_pct"]],
                text=[f"{x:+.2f}%" for x in df_ipsa["cambio_pct"]],
                textposition="outside", textfont=dict(size=8, color="#64748b"),
            ))
            fig.update_layout(**PLOT_BASE, height=360, title="Variación porcentual del día", showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b", tickangle=-45, tickfont=dict(size=8)), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"))


            st.plotly_chart(fig, use_container_width=True)

            st.divider()
            df_sec = get_resumen_sectorial(df_ipsa)
            if not df_sec.empty:
                col1, col2 = st.columns([2,3])
                with col1:
                    st.markdown("**Por sector**")
                    for _, row in df_sec.iterrows():
                        color = "#22c55e" if row["variacion_prom"]>0 else "#ef4444"
                        st.markdown(
                            f'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1a2535">'
                            f'<span style="color:#94a3b8;font-size:0.79rem">{row["sector"]}</span>'
                            f'<span style="color:{color};font-family:monospace;font-size:0.79rem;font-weight:600">{row["variacion_prom"]:+.2f}%</span></div>',
                            unsafe_allow_html=True
                        )
                with col2:
                    fig_sec = go.Figure(go.Bar(
                        x=df_sec["sector"], y=df_sec["variacion_prom"],
                        marker_color=["#22c55e" if x>0 else "#ef4444" for x in df_sec["variacion_prom"]],
                        text=[f"{x:+.2f}%" for x in df_sec["variacion_prom"]],
                        textposition="outside", textfont=dict(size=9, color="#64748b"),
                    ))
                    fig_sec.update_layout(**PLOT_BASE, height=260, showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b", tickangle=-30, tickfont=dict(size=9)), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"))
                    fig_sec.update_xaxes(tickangle=-30, tickfont=dict(size=9))
                    st.plotly_chart(fig_sec, use_container_width=True)

            st.divider()
            sf = st.selectbox("Filtrar por sector", ["Todos"] + sorted(df_ipsa["sector"].unique().tolist()))
            dm = df_ipsa if sf=="Todos" else df_ipsa[df_ipsa["sector"]==sf]
            st.dataframe(
                dm[["nombre","ticker","sector","precio","cambio_pct","peso"]].rename(columns={
                    "nombre":"Empresa","ticker":"Ticker","sector":"Sector",
                    "precio":"Precio CLP","cambio_pct":"Var %","peso":"Peso IPSA"}),
                use_container_width=True, hide_index=True,
                column_config={
                    "Var %": st.column_config.NumberColumn(format="%+.2f%%"),
                    "Precio CLP": st.column_config.NumberColumn(format="%,.0f"),
                }
            )

    # ── Sub-tab Macro Chile
    with sub_macro:
        with st.spinner(""):
            macro_data_full = get_macro_chile_completo()
            ctx = get_contexto_macro()

        ciclo = ctx.get("ciclo","NEUTRO")
        cc = {"EXPANSIÓN":"#22c55e","MODERADO":"#f59e0b","NEUTRO":"#475569","CONTRACCIÓN":"#ef4444"}.get(ciclo,"#475569")
        senales_html = "".join([f'<div style="color:#64748b;font-size:0.77rem;margin-top:3px">{s}</div>' for s in ctx.get("señales",[])])
        st.markdown(
            f'<div style="background:#0d1521;border:1px solid {cc}33;border-left:3px solid {cc};'
            f'border-radius:6px;padding:0.75rem 1rem;margin-bottom:1rem">'
            f'<span style="color:{cc};font-weight:700">CICLO: {ciclo}</span>{senales_html}</div>',
            unsafe_allow_html=True
        )

        ids = ["dolar","uf","tpm","ipc","imacec","libra_cobre","tasa_desempleo","bitcoin"]
        cols = st.columns(4)
        for i, ind_id in enumerate(ids):
            dato = macro_data_full.get(ind_id)
            if not dato: continue
            with cols[i%4]:
                var = dato.get("variacion")
                st.metric(
                    dato["nombre"].upper(),
                    f"{dato['valor']:,.2f} {dato['unidad']}",
                    delta=f"{var:+.3f}%" if var else None
                )

        st.divider()
        col_g1, col_g2 = st.columns(2)
        for idx, ind_id in enumerate(["dolar","libra_cobre","tpm","uf"]):
            dato = macro_data_full.get(ind_id)
            if not dato or not dato.get("historico"): continue
            hist = dato["historico"]
            fechas = [h["fecha"] for h in reversed(hist)]
            valores = [h["valor"] for h in reversed(hist)]
            fig_m = go.Figure(go.Scatter(x=fechas, y=valores, mode="lines",
                line=dict(color="#3b82f6", width=1.5),
                fill="tozeroy", fillcolor="rgba(59,130,246,0.04)"))
            fig_m.update_layout(**PLOT_BASE, height=185, title=dato["nombre"], showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b", tickfont=dict(size=8)), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"))
            fig_m.update_xaxes(tickfont=dict(size=8))
            with col_g1 if idx%2==0 else col_g2:
                st.plotly_chart(fig_m, use_container_width=True)

        st.divider()
        with st.spinner(""):
            spread_btc = get_spread_btc(clp or 892.0)
        if spread_btc:
            col1,col2,col3,col4 = st.columns(4)
            with col1: st.metric("BTC Buda (CLP)", f"${spread_btc['btc_local_clp']:,.0f}")
            with col2: st.metric("BTC Global (CLP)", f"${spread_btc['btc_global_clp']:,.0f}")
            with col3: st.metric("Spread BTC", f"{spread_btc['spread_pct']}%", delta=spread_btc["direccion"])
            with col4: st.metric("BTC en USD", f"${spread_btc['btc_usd']:,.0f}")

    # ── Sub-tab CMF
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
                            f'<span style="background:{color}22;color:{color};border:1px solid {color}44;' +
                            f'border-radius:4px;padding:2px 8px;font-size:0.72rem;font-weight:600">' +
                            f'{h["relevancia"]} · Impacto: {h["impacto"]}</span>',
                            unsafe_allow_html=True
                        )
                    with col2:
                        if h.get("url"):
                            st.link_button("Ver documento →", h["url"])
                        if ticker:
                            st.markdown(f'<div style="background:#1e293b;border-radius:5px;padding:0.4rem;text-align:center;color:#38bdf8;font-weight:700">{ticker}</div>', unsafe_allow_html=True)
        else:
            st.info("Sin hechos esenciales para los filtros seleccionados.")

    # ── Sub-tab Volumen Anormal
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
                            f'<span style="background:{sc}22;color:{sc};border:1px solid {sc}44;' +
                            f'border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:700">' +
                            f'{a["señal"]}</span>',
                            unsafe_allow_html=True
                        )
                    with col2:
                        st.markdown(f"**Volumen hoy:** {a['vol_actual']:,}")
                        st.markdown(f"**Promedio 20d:** {a['vol_promedio']:,}")
                        st.markdown(
                            f'<span style="background:{color}22;color:{color};border:1px solid {color}44;' +
                            f'border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:700">' +
                            f'{a["ratio"]}x PROMEDIO · {a["nivel"]}</span>',
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

    # ── Sub-tab Análisis Técnico
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
                            f'<span style="background:{color_a}22;color:{color_a};border:1px solid {color_a}44;' +
                            f'border-radius:4px;padding:2px 8px;font-size:0.8rem;font-weight:700">' +
                            f'{s["accion"]}</span>',
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
                            f'<div style="color:{sc};font-size:0.78rem;padding:2px 0">'
                            f'{"↑" if señal["direccion"]=="ALZA" else "↓"} [{señal["indicador"]}] {señal["descripcion"]}</div>',
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
    with sub_corr:
        with st.spinner(""):
            corrs_ech    = get_correlaciones_ipsa_completo("90d")
            corr_rodante = get_correlacion_rodante("ECH", "HG=F", 30, "180d")
            divs_corr    = get_divergencias_correlacion("90d")

        if corrs_ech:
            st.markdown("**ECH (IPSA) vs Variables Macro Globales** — últimos 90 días")
            for c in corrs_ech:
                v = c["corr"]
                color = "#22c55e" if v>0 else "#ef4444"
                barra = ("█" * (int(abs(v)*10) if v is not None and v == v else 0)).ljust(10)
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:1rem;padding:0.25rem 0;border-bottom:1px solid #1a2535">'
                    f'<span style="color:{color};font-family:monospace;font-size:0.82rem;width:140px">{"+" if v>=0 else ""}{barra} {v:+.3f}</span>'
                    f'<span style="color:#94a3b8;font-size:0.8rem;width:140px">{c["nombre"]}</span>'
                    f'<span style="color:#475569;font-size:0.73rem">{c["señal"]}</span></div>',
                    unsafe_allow_html=True
                )

        if corr_rodante:
            st.divider()
            st.markdown("**Correlación Rodante ECH — Cobre (ventana 30 días)**")
            col1,col2,col3,col4 = st.columns(4)
            with col1: st.metric("Actual", f"{corr_rodante['actual']:+.3f}")
            with col2: st.metric("Promedio histórico", f"{corr_rodante['promedio']:+.3f}")
            with col3: st.metric("Mínimo", f"{corr_rodante['min']:+.3f}")
            with col4: st.metric("Máximo", f"{corr_rodante['max']:+.3f}")
            valores_rod = [v for v in corr_rodante["valores"] if v is not None]
            fechas_rod  = corr_rodante["fechas"][-len(valores_rod):]
            if valores_rod:
                fig_rod = go.Figure()
                fig_rod.add_trace(go.Scatter(x=fechas_rod, y=valores_rod, mode="lines",
                    line=dict(color="#3b82f6", width=1.5),
                    fill="tozeroy", fillcolor="rgba(59,130,246,0.05)"))
                fig_rod.add_hline(y=corr_rodante["promedio"], line_dash="dot", line_color="#f59e0b",
                    annotation_text=f"Promedio: {corr_rodante['promedio']:.3f}",
                    annotation_font_color="#f59e0b")
                fig_rod.add_hline(y=0, line_color="#1e293b")
                fig_rod.update_layout(**PLOT_BASE, height=220, title="Correlación rodante ECH vs Cobre", showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b", range=[-1,1]))
                st.plotly_chart(fig_rod, use_container_width=True)

        if divs_corr:
            st.divider()
            st.markdown("**Divergencias de Correlación — Señales de Mispricing**")
            for d in divs_corr:
                color = d["color"]
                with st.expander(
                    f"{d['señal']}  ·  ECH real {d['ech_real']:+.2f}%  ·  "
                    f"Esperado {d['ech_esperado']:+.2f}%  ·  Divergencia {d['divergencia']:+.2f}%"
                ):
                    col1,col2 = st.columns(2)
                    with col1:
                        st.caption(f"Variable: {d['nombre']} ({d['macro_mov']:+.2f}%)")
                        st.caption(f"Correlación histórica: {d['corr_hist']:+.3f}")
                    with col2:
                        st.markdown(f'<span style="color:{color};font-weight:700">{d["señal"]}</span>', unsafe_allow_html=True)
                        if d["divergencia"] > 0:
                            st.caption("ECH subvalorado respecto a fundamentales → posible compra")
                        else:
                            st.caption("ECH sobrevalorado respecto a fundamentales → posible venta")

    # ── Sub-tab Noticias
    with sub_noticias:
        if noticias:
            sent_r = get_resumen_sentiment(noticias)
            sc_n = {"ALCISTA":"#22c55e","BAJISTA":"#ef4444","NEUTRO":"#475569"}.get(sent_r.get("sesgo","NEUTRO"),"#475569")
            st.markdown(
                f'<div style="background:#0d1521;border:1px solid {sc_n}33;border-left:3px solid {sc_n};'
                f'border-radius:6px;padding:0.5rem 0.9rem;margin-bottom:0.75rem;font-size:0.8rem">'
                f'<span style="color:{sc_n};font-weight:700">Sentiment: {sent_r.get("sesgo","NEUTRO")}</span>'
                f'<span style="color:#475569;margin-left:12px">'
                f'{sent_r.get("positivas",0)} positivas · {sent_r.get("negativas",0)} negativas · '
                f'Ratio positivo: {sent_r.get("ratio_positivo",0)}%</span></div>',
                unsafe_allow_html=True
            )
            sent_activos = get_sentiment_por_activo(noticias)
            if sent_activos:
                cols_sa = st.columns(min(len(sent_activos), 5))
                for i, (activo, data) in enumerate(list(sent_activos.items())[:5]):
                    with cols_sa[i]:
                        c = data["color"]
                        st.markdown(
                            f'<div style="background:#0d1521;border:1px solid {c}33;border-radius:5px;'
                            f'padding:0.4rem 0.6rem;text-align:center">'
                            f'<div style="color:#475569;font-size:0.68rem">{activo.replace(".SN","")}</div>'
                            f'<div style="color:{c};font-weight:700;font-size:0.82rem">{data["tono"]}</div>'
                            f'<div style="color:#334155;font-size:0.65rem">{data["n_noticias"]} noticias</div></div>',
                            unsafe_allow_html=True
                        )
            st.divider()
            col_f1, col_f2, col_f3 = st.columns([2,2,2])
            with col_f1: min_sc = st.slider("Score mínimo", 0, 15, 3)
            with col_f2: busq = st.text_input("Buscar", placeholder="litio, cobre, tasa...")
            with col_f3: f_sent = st.selectbox("Sentiment", ["Todos","Positivo","Negativo","Neutro"])

            nf = [n for n in noticias if n["score"] >= min_sc]
            if busq: nf = [n for n in nf if busq.lower() in n["titulo"].lower()]
            if f_sent == "Positivo": nf = [n for n in nf if n.get("sentiment",{}).get("señal",0) > 0]
            elif f_sent == "Negativo": nf = [n for n in nf if n.get("sentiment",{}).get("señal",0) < 0]
            elif f_sent == "Neutro": nf = [n for n in nf if n.get("sentiment",{}).get("señal",0) == 0]
            st.caption(f"{len(nf)} noticias")

            for n in nf:
                sent = n.get("sentiment",{})
                tono = sent.get("tono","NEUTRO")
                c_sent = sent.get("color","#475569")
                with st.expander(f"[{n['score']}]  {n['titulo'][:95]}"):
                    col1, col2 = st.columns([4,1])
                    with col1:
                        st.caption(f"{n['fuente']} · {n.get('fecha','')[:25]}")
                        tags = " · ".join(n.get("keywords",[])) if n.get("keywords") else ""
                        if tags: st.caption(f"Temas: {tags}")
                    with col2:
                        st.markdown(
                            f'<div style="background:{c_sent}15;color:{c_sent};border:1px solid {c_sent}33;'
                            f'border-radius:4px;padding:2px 6px;font-size:0.7rem;font-weight:600;text-align:center">'
                            f'{tono}<br>{sent.get("estrellas",3)} estrellas</div>',
                            unsafe_allow_html=True
                        )
                        if n.get("url"): st.link_button("Leer", n["url"])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — OPORTUNIDADES
# ════════════════════════════════════════════════════════════════════════════════
with tab_oportunidades:
    sub_señales, sub_arbitraje, sub_pc, sub_opciones = st.tabs([
        "Señales de Trading", "Arbitraje ADR", "Put/Call Ratio", "Opciones"
    ])

    with sub_señales:
        recomendaciones = st.session_state.get("recomendaciones", [])
        if recomendaciones:
            compras = [r for r in recomendaciones if r["accion"]=="COMPRAR"]
            ventas  = [r for r in recomendaciones if r["accion"]=="VENDER"]
            avg_r   = round(sum(r["riesgo"] for r in recomendaciones)/len(recomendaciones),1)
            col1,col2,col3,col4 = st.columns(4)
            with col1: st.metric("Total señales", len(recomendaciones))
            with col2: st.metric("Comprar", len(compras))
            with col3: st.metric("Vender", len(ventas))
            with col4: st.metric("Riesgo promedio", f"{avg_r}/10")
            st.divider()
            for r in recomendaciones:
                accion = r["accion"]
                h = r.get("horizonte",{})
                color_a = "#22c55e" if accion=="COMPRAR" else "#ef4444"
                with st.expander(
                    f"{accion} {r['ib_ticker']}  ·  {r['descripcion'][:55]}  ·  "
                    f"Convicción {r['conviccion']}%  ·  Riesgo {r['riesgo']}/10"
                ):
                    col1,col2,col3 = st.columns([2,2,1])
                    with col1:
                        st.markdown(f'**Acción:** <span style="color:{color_a};font-weight:700">{accion} `{r["ib_ticker"]}`</span>', unsafe_allow_html=True)
                        st.markdown(f"**Tesis:** {r['tesis']}")
                        st.markdown(f"**Horizonte:** {h.get('label','')} — {h.get('dias','')}")
                    with col2:
                        st.progress(r["conviccion"]/100, text=f"Convicción: {r['conviccion']}%")
                        st.progress(r["riesgo"]/10, text=f"Riesgo: {r['riesgo']}/10")
                        precio = r.get("precio_actual"); sl = r.get("stop_loss"); tp = r.get("take_profit")
                        if precio and sl and tp and abs(precio-sl)>0:
                            rr = round(abs(tp-precio)/abs(precio-sl),1)
                            st.caption(f"Entrada: {precio:,.2f}  SL: {sl:,.2f}  TP: {tp:,.2f}  R/R 1:{rr}")
                    with col3:
                        if accion=="COMPRAR":
                            st.markdown('<div style="background:#22c55e15;border:1px solid #22c55e33;border-radius:5px;padding:0.5rem;text-align:center;color:#22c55e;font-weight:700">LARGO</div>', unsafe_allow_html=True)
                        else:
                            st.markdown('<div style="background:#ef444415;border:1px solid #ef444433;border-radius:5px;padding:0.5rem;text-align:center;color:#ef4444;font-weight:700">CORTO</div>', unsafe_allow_html=True)
                    st.divider()
                    for fuente in ["Polymarket","Kalshi","Macro USA","Noticias"]:
                        ev = [e for e in r["evidencia"] if e["fuente"]==fuente]
                        if not ev: continue
                        st.markdown(f"**{fuente}**")
                        for e in ev[:2]:
                            icon = "+" if e["direccion"]=="ALZA" else "-"
                            prob_str = f" ({e['prob']}%)" if e.get("prob") else ""
                            st.caption(f"[{icon}] {e['señal']}{prob_str} — peso {e['peso']}")
                    st.caption("Señal informativa. No constituye asesoría de inversión.")
        else:
            st.info("No hay señales disponibles en este momento.")

    with sub_arbitraje:
        with st.spinner(""):
            resumen_arb = get_resumen_arbitraje()
        col1,col2,col3,col4 = st.columns(4)
        with col1: st.metric("CLP/USD", f"{resumen_arb.get('clp_usd',0):,.2f}")
        with col2: st.metric("Pares monitoreados", len(resumen_arb.get("spreads_adr",[])))
        with col3: st.metric("Oportunidades netas", resumen_arb.get("oportunidades",0))
        with col4:
            mejor = resumen_arb.get("mejor_spread")
            if mejor: st.metric("Mayor spread bruto", f"{abs(mejor['spread_bruto_pct']):.3f}%")

        st.markdown(
            f'<div style="background:#0d1521;border:1px solid #1e293b;border-radius:5px;'
            f'padding:0.5rem 0.9rem;margin:0.5rem 0;font-size:0.72rem;color:#475569">'
            f'Costos estimados — Comisión IB: {COSTOS["comision_ib_pct"]}% · '
            f'Spread FX: {COSTOS["spread_fx_pct"]}% · '
            f'Total ida/vuelta: {COSTOS["costo_total_pct"]}% · '
            f'Umbral mínimo: {COSTOS["umbral_minimo_pct"]}%</div>',
            unsafe_allow_html=True
        )
        st.divider()
        for s in resumen_arb.get("spreads_adr",[]):
            spread_bruto = s["spread_bruto_pct"]
            op = s["oportunidad"]
            color_op = "#22c55e" if op in ("ALTA","MEDIA") else ("#f59e0b" if op=="BAJA" else "#475569")
            with st.expander(
                f"{s['nombre']}  ·  Spread bruto {spread_bruto:+.3f}%  ·  "
                f"Spread neto {s['spread_neto_pct']:+.3f}%  ·  {op}"
            ):
                col1,col2,col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Sector:** {s['sector']}")
                    st.markdown(f"**Ratio ADR:** 1 ADR = {s['ratio']} acción(es)")
                with col2:
                    st.markdown(f"NYSE: USD {s['precio_nyse_usd']:,.2f} → CLP {s['precio_nyse_clp']:,.0f}")
                    st.markdown(f"Santiago: CLP {s['precio_stgo_clp']:,.0f}")
                    st.markdown(f"Diferencia: CLP {s['precio_stgo_clp']-s['precio_nyse_clp']:+,.0f}")
                with col3:
                    st.markdown(f"Spread bruto: **{spread_bruto:+.3f}%**")
                    st.markdown(f"Costo: **-{COSTOS['costo_total_pct']}%**")
                    st.markdown(f'Spread neto: <span style="color:{color_op};font-weight:700">{s["spread_neto_pct"]:+.3f}%</span>', unsafe_allow_html=True)
                if op != "SIN OPORTUNIDAD":
                    st.caption(f"Acción sugerida: {s['accion_arbitraje']}")

    with sub_pc:
        st.markdown("**Put/Call Ratio — Smart Money Positioning**")
        st.caption("Relación entre opciones put (protección/bajista) y call (especulación/alcista). P/C alto = institucionales se protegen. P/C bajo = euforia.")

        with st.spinner("Calculando ratios..."):
            resumen_pc = get_resumen_pc()

        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Tickers analizados", resumen_pc.get("total", 0))
        with col2:
            spy = resumen_pc.get("spy_ratio")
            st.metric("SPY P/C ratio", f"{spy:.3f}" if spy else "N/D")
        with col3:
            sqm = resumen_pc.get("sqm_ratio")
            st.metric("SQM P/C ratio", f"{sqm:.3f}" if sqm else "N/D")

        st.divider()

        for r in resumen_pc.get("ratios", []):
            color = r["color"]
            with st.expander(
                f"{r['ticker']}  ·  P/C Vol: {r['pc_ratio_vol']:.3f}  ·  {r['señal']}"
            ):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**{r['nombre']}**")
                    st.markdown(f"Precio: `{r['precio']:,.2f}`" if r.get('precio') else "")
                    st.markdown(
                        f'<span style="background:{color}22;color:{color};border:1px solid {color}44;' +
                        f'border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:600">' +
                        f'{r["señal"]}</span>',
                        unsafe_allow_html=True
                    )
                with col2:
                    st.markdown("**Volumen opciones**")
                    st.markdown(f"Calls: `{r['calls_vol']:,}`")
                    st.markdown(f"Puts:  `{r['puts_vol']:,}`")
                    st.markdown(f"P/C Vol: **{r['pc_ratio_vol']:.3f}**")
                with col3:
                    st.markdown("**Open Interest**")
                    st.markdown(f"Calls OI: `{r['calls_oi']:,}`")
                    st.markdown(f"Puts OI:  `{r['puts_oi']:,}`")
                    st.markdown(f"P/C OI: **{r['pc_ratio_oi']:.3f}**")
                st.divider()
                st.caption(f"Impacto en: {r['impacto_activo']} · {r['vencimientos']} vencimientos analizados")

        st.divider()
        st.markdown("**Guía de interpretación**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("P/C > 2.0 → Capitulación → **Contrarian COMPRA fuerte**")
            st.markdown("P/C 1.5-2.0 → Miedo → Posible suelo")
            st.markdown("P/C 1.0-1.5 → Precaución → Institucionales se protegen")
        with col2:
            st.markdown("P/C 0.6-1.0 → Neutral")
            st.markdown("P/C 0.3-0.6 → Optimismo → Sesgo alcista")
            st.markdown("P/C < 0.3 → Codicia extrema → **Contrarian VENTA**")

    with sub_opciones:
        recomendaciones = st.session_state.get("recomendaciones", [])
        posiciones = get_posiciones_abiertas() if IB_DISPONIBLE else {}
        estrategias = get_estrategias_opciones(recomendaciones, posiciones)
        if estrategias:
            st.success(f"{len(estrategias)} estrategia(s) identificada(s)")
            for est in estrategias:
                with st.expander(f"{est['tipo']}  ·  {est['symbol']}  ·  Strike {est['strike_objetivo']}  ·  {est['dte_objetivo']}"):
                    col1,col2,col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**Subyacente:** `{est['symbol']}` · **Contratos:** {est['contratos']}")
                        st.markdown(f"**Vencimiento:** {est['dte_objetivo']}")
                    with col2:
                        if "costo_total_est" in est:
                            st.metric("Costo total est.", f"USD {est['costo_total_est']:,.0f}")
                            st.metric("Pérdida máxima", f"USD {est['max_perdida']:,.0f}")
                        elif "ingreso_est" in est:
                            st.metric("Ingreso estimado", f"USD {est['ingreso_est']:,.0f}")
                    with col3:
                        st.caption(f"Pros: {est['pros']}")
                        st.caption(f"Contras: {est['contras']}")
                    st.caption(f"Fundamento: {est['razon']}")
                    right = "Call" if est["right"]=="C" else "Put"
                    st.code(f"TWS → {est['symbol']} → Options → {right} Strike {est['strike_objetivo']}\n{'Comprar' if 'Comprar' in est['tipo'] else 'Vender'} {est['contratos']} contrato(s) — Orden LMT midpoint")
        else:
            st.info("Sin estrategias de opciones disponibles. Se activan con señales de convicción ≥80% sobre SPY, SQM o GLD.")
            col1,col2 = st.columns(2)
            with col1:
                st.markdown("**Comprar Call/Put:** Señal de alta convicción (≥80%) · Horizonte corto · Pérdida limitada al premium · Apalancamiento 5-10x")
            with col2:
                st.markdown("**Call Cubierto:** Posición larga existente ≥100 acciones · Genera ingreso 1-2% mensual · Strike ~5% sobre precio actual")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 — PORTAFOLIO
# ════════════════════════════════════════════════════════════════════════════════
with tab_portafolio:
    sub_pnl, sub_markowitz, sub_bt = st.tabs([
        "Posiciones y PnL", "Optimización", "Backtesting"
    ])

    with sub_pnl:
        with st.spinner(""):
            m = get_metricas_performance()
            benchmarks = get_benchmarks()

        col1,col2,col3,col4,col5 = st.columns(5)
        with col1: st.metric("Capital actual", f"USD {m['capital_actual']:,.0f}", delta=f"{m['retorno_total_pct']:+.2f}%")
        with col2: st.metric("PnL total", f"USD {m['pnl_total']:+,.0f}")
        with col3: st.metric("PnL realizado", f"USD {m['pnl_realizado']:+,.0f}")
        with col4: st.metric("PnL no realizado", f"USD {m['pnl_no_realizado']:+,.0f}")
        with col5: st.metric("Drawdown máx.", f"{m['max_drawdown_pct']:.1f}%")

        st.divider()
        col1,col2,col3,col4,col5 = st.columns(5)
        with col1: st.metric("Win rate", f"{m['win_rate']}%")
        with col2: st.metric("Trades totales", m["n_trades"])
        with col3: st.metric("Ganadores", m["n_ganadores"])
        with col4: st.metric("Perdedores", m["n_perdedores"])
        with col5:
            pf = m["profit_factor"]
            st.metric("Profit factor", f"{pf:.2f}" if pf != float("inf") else "∞")

        st.divider()
        st.markdown("**vs Benchmarks — últimos 30 días**")
        col1,col2 = st.columns([1,2])
        sistema_r = m["retorno_total_pct"]
        with col1:
            for nombre, retorno in benchmarks.items():
                color = "#22c55e" if retorno>0 else "#ef4444"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:0.25rem 0;border-bottom:1px solid #1a2535">'
                    f'<span style="color:#94a3b8;font-size:0.8rem">{nombre}</span>'
                    f'<span style="color:{color};font-family:monospace;font-weight:600;font-size:0.8rem">{retorno:+.2f}%</span></div>',
                    unsafe_allow_html=True
                )
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:0.3rem 0;margin-top:2px">'
                f'<span style="color:#3b82f6;font-size:0.8rem;font-weight:600">Sistema</span>'
                f'<span style="color:#3b82f6;font-family:monospace;font-weight:700;font-size:0.8rem">{sistema_r:+.2f}%</span></div>',
                unsafe_allow_html=True
            )
        with col2:
            bench_names  = list(benchmarks.keys()) + ["Sistema"]
            bench_values = list(benchmarks.values()) + [sistema_r]
            bench_colors = ["#22c55e" if v>=0 else "#ef4444" for v in bench_values]
            bench_colors[-1] = "#3b82f6"
            fig_b = go.Figure(go.Bar(x=bench_names, y=bench_values, marker_color=bench_colors,
                text=[f"{v:+.2f}%" for v in bench_values], textposition="outside",
                textfont=dict(size=10, color="#64748b")))
            fig_b.update_layout(**PLOT_BASE, height=240, showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"))
            st.plotly_chart(fig_b, use_container_width=True)

        st.divider()
        st.markdown("**Posiciones Abiertas**")
        posiciones_pnl = m["posiciones_abiertas"]
        if posiciones_pnl:
            for p in posiciones_pnl:
                pnl = p["pnl_total"]; pct = p["pnl_pct"]
                color = "#22c55e" if pnl>=0 else "#ef4444"
                with st.expander(f"{p['ticker']}  ·  PnL: USD {pnl:+,.2f} ({pct:+.2f}%)  ·  {p['dias_abierta']} días"):
                    col1,col2,col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**Acción:** {p['accion']} · **Cantidad:** {p['cantidad']}")
                        st.markdown(f"**Días abierta:** {p['dias_abierta']}")
                    with col2:
                        st.markdown(f"**Entrada:** {p['precio_entrada']:,.2f} → **Actual:** {p['precio_actual']:,.2f}")
                        st.markdown(f"**Monto:** USD {p['precio_entrada']*p['cantidad']:,.0f}")
                    with col3:
                        if p.get("sl"): st.markdown(f"SL: `{p['sl']:,.2f}`")
                        if p.get("tp"): st.markdown(f"TP: `{p['tp']:,.2f}`")
        else:
            st.caption("Sin posiciones abiertas. Ejecuta órdenes desde el tab Ejecución.")

        equity = m["equity_curve"]
        if len(equity) > 1:
            st.divider()
            st.markdown("**Curva de Equity**")
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(y=equity, mode="lines",
                line=dict(color="#3b82f6", width=1.5),
                fill="tozeroy", fillcolor="rgba(59,130,246,0.05)"))
            fig_eq.add_hline(y=CAPITAL_INICIAL, line_dash="dot", line_color="#1e293b",
                annotation_text=f"Capital inicial: ${CAPITAL_INICIAL:,.0f}",
                annotation_font_color="#475569")
            fig_eq.update_layout(**PLOT_BASE, height=250, title="Evolución del capital (USD)", showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"))
            st.plotly_chart(fig_eq, use_container_width=True)

    with sub_markowitz:
        st.caption(f"Universo: {', '.join(UNIVERSO_DEFAULT.values())} · Tasa libre riesgo: {TASA_LIBRE_RIESGO*100}% (TPM Chile)")
        col_p1, col_p2 = st.columns([1,1])
        with col_p1: capital_mk = st.number_input("Capital (USD)", value=100_000, step=10_000, min_value=10_000)
        with col_p2: periodo_mk = st.selectbox("Período histórico", ["1y","2y","3y"], index=1)

        if st.button("Calcular Portafolio Óptimo", type="primary", use_container_width=True):
            with st.spinner("Optimizando portafolio..."):
                st.session_state.analisis_port = get_analisis_portafolio(capital_mk, periodo_mk)

        analisis = st.session_state.get("analisis_port")
        if not analisis:
            with st.spinner("Cargando análisis..."):
                analisis = get_analisis_portafolio(100_000, "2y")
                st.session_state.analisis_port = analisis

        if analisis:
            st.divider()
            col1,col2,col3 = st.columns(3)
            for col, pk, titulo, color in [
                (col1,"port_sharpe","Máximo Sharpe","#3b82f6"),
                (col2,"port_min_vol","Mínima Volatilidad","#22c55e"),
                (col3,"port_equal","Pesos Iguales","#475569"),
            ]:
                port = analisis[pk]
                with col:
                    st.markdown(
                        f'<div style="background:#0d1521;border:1px solid {color}33;border-top:2px solid {color};'
                        f'border-radius:6px;padding:0.65rem 0.9rem">'
                        f'<div style="color:{color};font-weight:600;font-size:0.78rem;margin-bottom:0.4rem">{titulo}</div>'
                        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.25rem;font-size:0.78rem">'
                        f'<span style="color:#475569">Retorno</span><span style="color:#f1f5f9;font-family:monospace">{port["retorno"]*100:.1f}%</span>'
                        f'<span style="color:#475569">Volatilidad</span><span style="color:#f1f5f9;font-family:monospace">{port["vol"]*100:.1f}%</span>'
                        f'<span style="color:#475569">Sharpe</span><span style="color:{color};font-family:monospace;font-weight:700">{port["sharpe"]:.2f}</span>'
                        f'</div></div>',
                        unsafe_allow_html=True
                    )

            st.divider()
            col1,col2 = st.columns([2,3])
            ps = analisis["port_sharpe"]
            with col1:
                st.markdown("**Distribución — Máximo Sharpe**")
                for t, p in sorted(ps["pesos"].items(), key=lambda x:-x[1]):
                    nombre = UNIVERSO_DEFAULT.get(t,t)
                    color = "#3b82f6" if p>=0.15 else ("#22c55e" if p>=0.05 else "#334155")
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1a2535">'
                        f'<span style="color:#94a3b8;font-size:0.8rem">{nombre}</span>'
                        f'<span style="color:{color};font-family:monospace;font-weight:600;font-size:0.8rem">{p*100:.1f}%</span></div>',
                        unsafe_allow_html=True
                    )
            with col2:
                labels = [UNIVERSO_DEFAULT.get(t,t) for t,p in ps["pesos"].items() if p>0.01]
                values = [p for t,p in ps["pesos"].items() if p>0.01]
                fig_pie = go.Figure(go.Pie(labels=labels, values=values, hole=0.4,
                    marker=dict(colors=["#3b82f6","#22c55e","#f59e0b","#a78bfa","#fb923c","#34d399","#f472b6","#64748b"]),
                    textfont=dict(size=10)))
                fig_pie.update_layout(**PLOT_BASE, height=260, showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b"))
                st.plotly_chart(fig_pie, use_container_width=True)

            st.divider()
            st.markdown("**Value at Risk (VaR) — Portafolio Óptimo**")
            var = analisis["var_sharpe"]
            col1,col2,col3,col4 = st.columns(4)
            with col1: st.metric("VaR 95% diario", f"USD {var['var_95_usd']:,.0f}", delta=f"-{var['var_95_pct']}%")
            with col2: st.metric("VaR 99% diario", f"USD {var['var_99_usd']:,.0f}", delta=f"-{var['var_99_pct']}%")
            with col3: st.metric("CVaR 95%", f"USD {var['cvar_95_usd']:,.0f}", delta=f"-{var['cvar_95_pct']}%")
            with col4: st.metric("VaR anual 95%", f"USD {var['var_95_usd']*np.sqrt(252):,.0f}")

            st.divider()
            st.markdown("**Contribución al Riesgo**")
            contrib = analisis["contribucion"]
            for t, c in sorted(contrib.items(), key=lambda x:-x[1]["contrib_riesgo"]):
                diff = c["contrib_riesgo"] - c["peso"]
                color_d = "#ef4444" if diff>5 else ("#22c55e" if diff<-5 else "#475569")
                nota = "Concentra riesgo" if diff>5 else ("Diversifica" if diff<-5 else "Neutral")
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:1rem;padding:0.25rem 0;border-bottom:1px solid #1a2535">'
                    f'<span style="color:#94a3b8;font-size:0.8rem;width:150px">{c["nombre"]}</span>'
                    f'<span style="color:#64748b;font-size:0.78rem;width:100px">Peso: {c["peso"]:.1f}%</span>'
                    f'<span style="color:#3b82f6;font-size:0.78rem;width:110px">Riesgo: {c["contrib_riesgo"]:.1f}%</span>'
                    f'<span style="color:{color_d};font-size:0.72rem">{nota}</span></div>',
                    unsafe_allow_html=True
                )

            st.divider()
            st.markdown("**Frontera Eficiente**")
            frontera = analisis.get("frontera",[])
            if frontera:
                vols_f   = [p["vol"]*100 for p in frontera]
                rets_f   = [p["retorno"]*100 for p in frontera]
                sharps_f = [p["sharpe"] for p in frontera]
                fig_f = go.Figure()
                fig_f.add_trace(go.Scatter(x=vols_f, y=rets_f, mode="markers",
                    marker=dict(color=sharps_f, colorscale="Blues", size=4, showscale=True,
                        colorbar=dict(title="Sharpe", tickfont=dict(color="#64748b", size=9))),
                    hovertemplate="Vol: %{x:.1f}%<br>Ret: %{y:.1f}%<extra></extra>"))
                fig_f.add_trace(go.Scatter(x=[ps["vol"]*100], y=[ps["retorno"]*100],
                    mode="markers", marker=dict(color="#ef4444", size=10, symbol="star"),
                    name="Óptimo"))
                fig_f.update_layout(**PLOT_BASE, height=340, title="Retorno vs Volatilidad — portafolios simulados", showlegend=False, xaxis=dict(gridcolor="#1a2535", linecolor="#1e293b", title="Volatilidad anual (%)"), yaxis=dict(gridcolor="#1a2535", linecolor="#1e293b", title="Retorno anual (%)"))
                st.plotly_chart(fig_f, use_container_width=True)
                st.caption("Estrella roja = portafolio de máximo Sharpe · Escala de color: azul más oscuro = mayor Sharpe")

    with sub_bt:
        stats_bt = get_estadisticas_backtest()
        if stats_bt:
            col1,col2,col3,col4,col5 = st.columns(5)
            with col1: st.metric("Total señales", stats_bt.get("total",0))
            with col2: st.metric("Correctas", stats_bt.get("correctas",0))
            with col3: st.metric("Incorrectas", stats_bt.get("incorrectas",0))
            with col4: st.metric("Pendientes", stats_bt.get("pendientes",0))
            with col5: st.metric("Tasa de éxito", f"{stats_bt.get('tasa_exito',0)}%")
            st.divider()
            col1,col2 = st.columns([2,1])
            with col1: dias_bt = st.slider("Días mínimos para evaluar", 0, 7, 1)
            with col2:
                if st.button("Ejecutar backtesting", type="primary", use_container_width=True):
                    with st.spinner("Evaluando señales históricas..."):
                        res_bt = ejecutar_backtest(dias_minimos=dias_bt)
                    st.success(f"Evaluadas: {res_bt['evaluadas']} · Correctas: {res_bt['correctas']} · Tasa: {res_bt['tasa_exito']}%")
                    st.rerun()
            historial_bt = stats_bt.get("historial_bt",[])
            if historial_bt:
                st.divider()
                rows_bt = []
                for row in historial_bt:
                    fecha,senal,prob,direccion,activos_bt,score,resultado,p_e,p_s,mov,ticker = row
                    icon = {"correcto":"✓","incorrecto":"✗","neutral":"→","pendiente":"...","":"?"}.get(resultado,"?")
                    rows_bt.append({"":icon,"Fecha":fecha[:16],"Señal":senal[:55],"Dir.":direccion,
                        "P.Entrada":p_e,"P.Salida":p_s,
                        "Mov %":round(mov,2) if mov else None,"Resultado":resultado})
                st.dataframe(pd.DataFrame(rows_bt), use_container_width=True, hide_index=True,
                    column_config={"Mov %":st.column_config.NumberColumn(format="%+.2f%%")})

# ════════════════════════════════════════════════════════════════════════════════
# TAB 5 — EJECUCIÓN
# ════════════════════════════════════════════════════════════════════════════════
with tab_ejecucion:
    sub_motor, sub_ib, sub_hist, sub_cierre = st.tabs(["Motor Automático", "IB Manual", "Historial", "Cierres"])

    with sub_motor:
        st.markdown("### Motor de Trading Automático")
        st.caption("Ejecuta y cierra posiciones automáticamente según las señales del sistema y las salvaguardas configuradas.")

        resumen_motor = get_resumen_motor()

        # Estado principal
        activo  = resumen_motor.get("activo", False)
        pausado = resumen_motor.get("pausado", False)

        if pausado:
            st.error(f"⚠️ Motor PAUSADO — {resumen_motor.get('razon_pausa','')}")
        elif activo:
            st.success("● Motor ACTIVO — operando automáticamente")
        else:
            st.info("○ Motor INACTIVO — activar para operar automáticamente")

        # Controles
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Activar motor", type="primary", use_container_width=True, disabled=activo and not pausado):
                activar_motor(True)
                st.success("Motor activado")
                st.rerun()
        with col2:
            if st.button("Pausar motor", use_container_width=True, disabled=not activo or pausado):
                pausar_motor("Pausado manualmente por el usuario")
                st.warning("Motor pausado")
                st.rerun()
        with col3:
            if st.button("Desactivar motor", use_container_width=True, disabled=not activo):
                activar_motor(False)
                st.info("Motor desactivado")
                st.rerun()

        st.divider()

        # KPIs del motor
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: st.metric("Posiciones", f"{resumen_motor['posiciones_abiertas']}/{resumen_motor['max_posiciones']}")
        with col2: st.metric("Riesgo total", f"USD {resumen_motor['riesgo_total_usd']:,.0f}", delta=f"límite {resumen_motor['max_riesgo_usd']:,.0f}")
        with col3:
            pnl_d = resumen_motor["pnl_dia_pct"]
            st.metric("PnL del día", f"{pnl_d:+.2f}%", delta=f"límite {PARAMS['pausa_pnl_dia_pct']}%")
        with col4: st.metric("Drawdown", f"{resumen_motor['drawdown_pct']:.2f}%", delta=f"límite {PARAMS['max_drawdown_pct']}%")
        with col5: st.metric("Consecutivos perdedores", f"{resumen_motor['consecutivos_perdedor']}/{PARAMS['pausa_consecutivos']}")

        st.divider()

        # Semáforo de condiciones
        st.markdown("**Estado de condiciones**")
        condiciones = [
            ("Horario de mercado", resumen_motor["en_horario"], resumen_motor["msg_horario"]),
            ("Posiciones disponibles", resumen_motor["posiciones_abiertas"] < resumen_motor["max_posiciones"], f"{resumen_motor['posiciones_abiertas']}/{resumen_motor['max_posiciones']}"),
            ("Riesgo bajo límite", resumen_motor["riesgo_total_usd"] < resumen_motor["max_riesgo_usd"], f"USD {resumen_motor['riesgo_total_usd']:,.0f}"),
            ("PnL día aceptable", resumen_motor["pnl_dia_pct"] > PARAMS["pausa_pnl_dia_pct"], f"{resumen_motor['pnl_dia_pct']:+.2f}%"),
            ("Drawdown bajo límite", resumen_motor["drawdown_pct"] < PARAMS["max_drawdown_pct"], f"{resumen_motor['drawdown_pct']:.2f}%"),
            ("Consecutivos OK", resumen_motor["consecutivos_perdedor"] < PARAMS["pausa_consecutivos"], f"{resumen_motor['consecutivos_perdedor']} perdedores"),
        ]
        for nombre, ok, detalle in condiciones:
            color = "#22c55e" if ok else "#ef4444"
            icon  = "✓" if ok else "✗"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1a2535">' +
                f'<span style="color:{color};font-size:0.82rem">{icon} {nombre}</span>' +
                f'<span style="color:#64748b;font-size:0.78rem">{detalle}</span></div>',
                unsafe_allow_html=True
            )

        st.divider()

        # Parámetros
        st.markdown("**Parámetros del motor**")
        col1, col2 = st.columns(2)
        params_list = list(PARAMS.items())
        mid = len(params_list) // 2
        with col1:
            for k, v in params_list[:mid]:
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:0.15rem 0;border-bottom:1px solid #1a2535">' +
                    f'<span style="color:#64748b;font-size:0.75rem">{k.replace("_"," ").title()}</span>' +
                    f'<span style="color:#f1f5f9;font-family:monospace;font-size:0.75rem">{v}</span></div>',
                    unsafe_allow_html=True
                )
        with col2:
            for k, v in params_list[mid:]:
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:0.15rem 0;border-bottom:1px solid #1a2535">' +
                    f'<span style="color:#64748b;font-size:0.75rem">{k.replace("_"," ").title()}</span>' +
                    f'<span style="color:#f1f5f9;font-family:monospace;font-size:0.75rem">{v}</span></div>',
                    unsafe_allow_html=True
                )

        st.divider()

        # Log reciente
        st.markdown("**Actividad reciente del motor**")
        from engine.motor_automatico import get_log_auto
        log = get_log_auto(20)
        if log:
            for entry in log:
                tipo  = entry.get("tipo","")
                color = "#22c55e" if tipo == "APERTURA" else ("#ef4444" if tipo in ("CIERRE","PAUSA") else "#64748b")
                st.markdown(
                    f'<div style="display:flex;gap:1rem;padding:0.2rem 0;border-bottom:1px solid #1a2535;font-size:0.78rem">' +
                    f'<span style="color:#475569;width:130px">{entry.get("timestamp","")[:16]}</span>' +
                    f'<span style="color:{color};font-weight:600;width:80px">{tipo}</span>' +
                    f'<span style="color:#94a3b8">{entry.get("descripcion","")[:60]}</span></div>',
                    unsafe_allow_html=True
                )
        else:
            st.caption("Sin actividad registrada aún.")

    with sub_ib:
        if not IB_DISPONIBLE:
            st.error("ibapi no instalado. Ejecuta: pip install ibapi")
        else:
            st.markdown(
                '<div style="background:#0d1521;border:1px solid #1e293b;border-radius:5px;'
                'padding:0.5rem 0.9rem;margin-bottom:1rem;font-size:0.75rem;color:#475569">'
                '<span style="color:#3b82f6;font-weight:600">Política de Inversión</span>'
                ' — Capital: USD 100.000 · Máx por operación: USD 10.000 · '
                'Horizonte: 3 días · Posiciones máx: 5 · Convicción mínima: 75% · Riesgo máx: 6/10'
                '</div>',
                unsafe_allow_html=True
            )
            col1, col2 = st.columns([4,1])
            with col2:
                if st.button("Actualizar cuenta", use_container_width=True):
                    st.session_state.cuenta_ib = get_resumen_cuenta()

            if "cuenta_ib" in st.session_state and st.session_state.cuenta_ib:
                cuenta = st.session_state.cuenta_ib
                col1,col2,col3 = st.columns(3)
                with col1: st.metric("Liquidación neta", f"USD {cuenta.get('NetLiquidation',0):,.0f}")
                with col2: st.metric("Cash disponible", f"USD {cuenta.get('TotalCashValue',0):,.0f}")
                with col3: st.metric("Buying power", f"USD {cuenta.get('BuyingPower',0):,.0f}")

            st.divider()
            st.markdown("**Posiciones Abiertas**")
            posiciones = get_posiciones_abiertas()
            if posiciones:
                rows_pos = [{"Ticker":t,"Acción":p["accion"],"Cantidad":p["cantidad"],
                    "Precio entrada":p.get("precio_entrada","N/D"),
                    "SL":p.get("sl","N/D"), "TP":p.get("tp","N/D"),
                    "Días":(datetime.now()-datetime.fromisoformat(p["fecha_entrada"])).days,
                    "Vence en":f"{max(0,3-(datetime.now()-datetime.fromisoformat(p['fecha_entrada'])).days)} días"}
                    for t,p in posiciones.items()]
                st.dataframe(pd.DataFrame(rows_pos), use_container_width=True, hide_index=True)
            else:
                st.caption("Sin posiciones abiertas en este momento.")

            st.divider()
            st.markdown("**Señales disponibles para ejecutar**")
            recomendaciones = st.session_state.get("recomendaciones", [])
            sv = [r for r in recomendaciones if r["conviccion"]>=75 and r["riesgo"]<=6 and r["n_fuentes"]>=2]

            if sv:
                for r in sv:
                    color_a = "#22c55e" if r["accion"]=="COMPRAR" else "#ef4444"
                    st.markdown(
                        f'<div style="padding:0.25rem 0;border-bottom:1px solid #1a2535;font-size:0.82rem">'
                        f'<span style="color:{color_a};font-weight:600">{r["accion"]} {r["ib_ticker"]}</span>'
                        f'<span style="color:#475569;margin-left:12px">Convicción: {r["conviccion"]}% · Riesgo: {r["riesgo"]}/10</span></div>',
                        unsafe_allow_html=True
                    )
                st.divider()
                col1,col2 = st.columns(2)
                with col1:
                    if st.button("Simular (sin enviar)", use_container_width=True):
                        with st.spinner("Simulando..."):
                            res = ejecutar_señales(recomendaciones, modo_test=True)
                        st.json(res)
                with col2:
                    if st.button("Ejecutar en IB Paper Trading", type="primary", use_container_width=True):
                        with st.spinner("Conectando a IB y ejecutando órdenes..."):
                            res = ejecutar_señales(recomendaciones, modo_test=False)
                        if res["ordenes_enviadas"]:
                            st.success(f"{len(res['ordenes_enviadas'])} orden(es) enviada(s)")
                            for o in res["ordenes_enviadas"]:
                                st.caption(f"→ {o['accion']} {o['ticker']}")
                        if res.get("ordenes_rechazadas"):
                            for o in res["ordenes_rechazadas"]:
                                st.warning(f"Rechazada: {o['ticker']} — {o['razon']}")
                        if res["errores"]: st.error(" | ".join(res["errores"]))
                        st.rerun()
            else:
                st.caption("No hay señales que cumplan la política de inversión en este momento.")

    with sub_hist:
        stats = get_estadisticas()
        col1,col2,col3,col4 = st.columns(4)
        with col1: st.metric("Total señales", stats["total"])
        with col2: st.metric("Correctas", stats["correctas"])
        with col3: st.metric("Incorrectas", stats["incorrectas"])
        with col4: st.metric("Tasa de éxito", f"{stats['tasa_exito']}%")
        st.divider()
        rows_h = get_historial(limit=50)
        if rows_h:
            df_hist = pd.DataFrame(rows_h, columns=["Fecha","Señal","Prob %","Dirección","Activos","Score","Tesis","Resultado"])
            st.dataframe(df_hist, use_container_width=True, hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=20, format="%.2f"),
                    "Prob %": st.column_config.NumberColumn(format="%.1f%%"),
                    "Tesis": st.column_config.TextColumn(width="large"),
                })
            st.divider()
            pendientes = [r for r in rows_h if r[7]=="pendiente"]
            if pendientes:
                ops_h = [f"{r[0]} — {r[1][:55]}" for r in pendientes]
                sel_h = st.selectbox("Evaluar señal manualmente", ops_h)
                res_h = st.radio("Resultado real", ["correcto","incorrecto"], horizontal=True)
                if st.button("Guardar evaluación"):
                    idx_h = ops_h.index(sel_h)
                    actualizar_resultado(pendientes[idx_h][1], pendientes[idx_h][0][:10], res_h)
                    st.success("Guardado")
                    st.rerun()
        else:
            st.caption("Sin historial de señales aún.")

    with sub_cierre:
        st.markdown("**Cierre Automático de Posiciones — SL/TP/Horizonte**")
        st.caption("El sistema verifica cada 5 minutos si alguna posición debe cerrarse por Stop Loss, Take Profit o vencimiento del horizonte.")

        # Estado actual
        col1, col2 = st.columns([3, 1])
        with col2:
            modo_auto = st.toggle("Cierre automático activo", value=True, key="toggle_cierre_auto")
            if st.button("Verificar ahora", use_container_width=True):
                with st.spinner("Verificando posiciones..."):
                    resumen = verificar_posiciones(modo_test=False, auto_cerrar=modo_auto)
                    st.session_state.resumen_cierre = resumen
                st.rerun()

        resumen = st.session_state.get("resumen_cierre", {})
        if resumen:
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Posiciones activas", resumen.get("posiciones", 0))
            with col2: st.metric("Cierres ejecutados", len(resumen.get("cierres", [])))
            with col3: st.metric("Sin precio", len(resumen.get("sin_datos", [])))

            # Posiciones OK
            if resumen.get("ok"):
                st.divider()
                st.markdown("**Posiciones monitoreadas**")
                for p in resumen["ok"]:
                    color = "#22c55e" if p["pnl_pct"] >= 0 else "#ef4444"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:0.25rem 0;border-bottom:1px solid #1a2535">' +
                        f'<span style="color:#94a3b8;font-size:0.82rem">{p["ticker"]}</span>' +
                        f'<span style="color:#64748b;font-size:0.78rem">Precio: {p["precio"]:,.2f}</span>' +
                        f'<span style="color:{color};font-family:monospace;font-size:0.82rem;font-weight:600">PnL: {p["pnl_pct"]:+.2f}%</span>' +
                        f'<span style="color:#475569;font-size:0.72rem">{p["dias"]} días</span></div>',
                        unsafe_allow_html=True
                    )

            # Cierres ejecutados
            if resumen.get("cierres"):
                st.divider()
                st.markdown("**Cierres en esta sesión**")
                for c in resumen["cierres"]:
                    color = "#ef4444" if c["razon"] == "STOP LOSS" else "#22c55e"
                    st.markdown(
                        f'<div style="background:{color}15;border:1px solid {color}33;border-radius:5px;padding:0.4rem 0.8rem;margin:0.2rem 0">' +
                        f'<span style="color:{color};font-weight:600">{c["razon"]}</span> — ' +
                        f'<span style="color:#f1f5f9">{c["ticker"]}</span> | ' +
                        f'<span style="color:{color}">PnL: {c["pnl_pct"]:+.2f}%</span>' +
                        (f' | ✅ Ejecutado' if c.get("ejecutado") else f' | ⚠️ {c.get("error","")}') +
                        f'</div>',
                        unsafe_allow_html=True
                    )

        st.divider()

        # Historial de cierres
        st.markdown("**Historial de cierres automáticos**")
        log_cierres = get_log_cierres(20)
        if log_cierres:
            rows_log = []
            for entry in log_cierres:
                orden = entry.get("orden_ib", {})
                rows_log.append({
                    "Fecha":    entry.get("timestamp","")[:16],
                    "Ticker":   entry.get("ticker",""),
                    "Razón":    entry.get("razon",""),
                    "PnL %":    entry.get("pnl_pct", 0),
                    "Precio":   entry.get("precio", 0),
                    "Estado":   "✅" if orden.get("ejecutado") else "❌",
                })
            st.dataframe(pd.DataFrame(rows_log), use_container_width=True, hide_index=True,
                column_config={"PnL %": st.column_config.NumberColumn(format="%+.2f%%")})
        else:
            st.caption("Sin cierres automáticos registrados aún.")

        st.divider()
        st.markdown("**Configuración de cierre**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Stop Loss (SL):** Orden de mercado inmediata → protege capital")
            st.markdown("**Take Profit (TP):** Orden límite → captura ganancia objetivo")
        with col2:
            st.markdown("**Horizonte:** Cierre por tiempo cuando se cumple el plazo")
            st.markdown("**Verificación:** Cada 5 minutos automáticamente")

    with sub_cierre:
        st.markdown("**Cierre Automático de Posiciones — SL/TP/Horizonte**")
        st.caption("El sistema verifica cada 5 minutos si alguna posición debe cerrarse por Stop Loss, Take Profit o vencimiento del horizonte.")

        # Estado actual
        col1, col2 = st.columns([3, 1])
        with col2:
            modo_auto = st.toggle("Cierre automático activo", value=True, key="toggle_cierre_auto_2")
            if st.button("Verificar ahora", use_container_width=True, key="btn_verificar_ahora_2"):
                with st.spinner("Verificando posiciones..."):
                    resumen = verificar_posiciones(modo_test=False, auto_cerrar=modo_auto)
                    st.session_state.resumen_cierre = resumen
                st.rerun()

        resumen = st.session_state.get("resumen_cierre", {})
        if resumen:
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Posiciones activas", resumen.get("posiciones", 0))
            with col2: st.metric("Cierres ejecutados", len(resumen.get("cierres", [])))
            with col3: st.metric("Sin precio", len(resumen.get("sin_datos", [])))

            # Posiciones OK
            if resumen.get("ok"):
                st.divider()
                st.markdown("**Posiciones monitoreadas**")
                for p in resumen["ok"]:
                    color = "#22c55e" if p["pnl_pct"] >= 0 else "#ef4444"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:0.25rem 0;border-bottom:1px solid #1a2535">' +
                        f'<span style="color:#94a3b8;font-size:0.82rem">{p["ticker"]}</span>' +
                        f'<span style="color:#64748b;font-size:0.78rem">Precio: {p["precio"]:,.2f}</span>' +
                        f'<span style="color:{color};font-family:monospace;font-size:0.82rem;font-weight:600">PnL: {p["pnl_pct"]:+.2f}%</span>' +
                        f'<span style="color:#475569;font-size:0.72rem">{p["dias"]} días</span></div>',
                        unsafe_allow_html=True
                    )

            # Cierres ejecutados
            if resumen.get("cierres"):
                st.divider()
                st.markdown("**Cierres en esta sesión**")
                for c in resumen["cierres"]:
                    color = "#ef4444" if c["razon"] == "STOP LOSS" else "#22c55e"
                    st.markdown(
                        f'<div style="background:{color}15;border:1px solid {color}33;border-radius:5px;padding:0.4rem 0.8rem;margin:0.2rem 0">' +
                        f'<span style="color:{color};font-weight:600">{c["razon"]}</span> — ' +
                        f'<span style="color:#f1f5f9">{c["ticker"]}</span> | ' +
                        f'<span style="color:{color}">PnL: {c["pnl_pct"]:+.2f}%</span>' +
                        (f' | ✅ Ejecutado' if c.get("ejecutado") else f' | ⚠️ {c.get("error","")}') +
                        f'</div>',
                        unsafe_allow_html=True
                    )

        st.divider()

        # Historial de cierres
        st.markdown("**Historial de cierres automáticos**")
        log_cierres = get_log_cierres(20)
        if log_cierres:
            rows_log = []
            for entry in log_cierres:
                orden = entry.get("orden_ib", {})
                rows_log.append({
                    "Fecha":    entry.get("timestamp","")[:16],
                    "Ticker":   entry.get("ticker",""),
                    "Razón":    entry.get("razon",""),
                    "PnL %":    entry.get("pnl_pct", 0),
                    "Precio":   entry.get("precio", 0),
                    "Estado":   "✅" if orden.get("ejecutado") else "❌",
                })
            st.dataframe(pd.DataFrame(rows_log), use_container_width=True, hide_index=True,
                column_config={"PnL %": st.column_config.NumberColumn(format="%+.2f%%")})
        else:
            st.caption("Sin cierres automáticos registrados aún.")

        st.divider()
        st.markdown("**Configuración de cierre**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Stop Loss (SL):** Orden de mercado inmediata → protege capital")
            st.markdown("**Take Profit (TP):** Orden límite → captura ganancia objetivo")
        with col2:
            st.markdown("**Horizonte:** Cierre por tiempo cuando se cumple el plazo")
            st.markdown("**Verificación:** Cada 5 minutos automáticamente")
