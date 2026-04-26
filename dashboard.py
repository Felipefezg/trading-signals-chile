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
from engine.divergence import calcular_divergencias
from engine.recomendaciones import consolidar_señales, generar_recomendaciones, enviar_alertas_nuevas

# IB executor — importar con fallback si no está disponible
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

tab_señales, tab_ib, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist = st.tabs([
    "🎯 Señales", "🤖 IB Trading", "🇨🇱 Chile", "🇺🇸 USA", "⚡ Divergencias", "🎰 Kalshi", "📰 Noticias", "📊 Historial"
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

    # Guardar recomendaciones en session_state para usar en tab IB
    st.session_state.recomendaciones = recomendaciones

    if recomendaciones:
        n_alertas, st.session_state.alertas_enviadas = enviar_alertas_nuevas(
            recomendaciones, st.session_state.alertas_enviadas)
        if n_alertas > 0:
            st.success(f"📱 {n_alertas} alerta(s) enviada(s) a Telegram")

        compras = [r for r in recomendaciones if r["accion"] == "COMPRAR"]
        ventas  = [r for r in recomendaciones if r["accion"] == "VENDER"]
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("📊 Total señales", len(recomendaciones))
        with col2: st.metric("🟢 Comprar", len(compras))
        with col3: st.metric("🔴 Vender", len(ventas))
        with col4:
            avg_r = round(sum(r["riesgo"] for r in recomendaciones) / len(recomendaciones), 1)
            st.metric("⚠️ Riesgo promedio", f"{avg_r}/10")

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
            riesgo_color = "🟢" if riesgo <= 3 else ("🟡" if riesgo <= 6 else "🔴")
            alerta_key = f"{r['accion']}_{r['ib_ticker']}"
            telegram_icon = "📱" if alerta_key in st.session_state.alertas_enviadas else ""

            with st.expander(
                f"{color} **{accion} {r['ib_ticker']}** — {r['descripcion']}  |  "
                f"Convicción: **{r['conviccion']}%**  |  "
                f"Riesgo: {riesgo_color} **{riesgo}/10**  |  "
                f"{h.get('emoji','')} **{h.get('label','')}** {telegram_icon}"
            ):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"### {color} {accion}")
                    st.markdown(f"**IB Ticker:** `{r['ib_ticker']}`")
                    st.markdown(f"**Tipo:** {r['tipo']}")
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
                    st.markdown("**⏱️ Horizonte**")
                    st.markdown(f"{h.get('emoji','')} **{h.get('label','')}** — {h.get('dias','')}")
                with col2:
                    st.markdown("**📐 Stop Loss / Take Profit**")
                    precio = r.get("precio_actual")
                    sl     = r.get("stop_loss")
                    tp     = r.get("take_profit")
                    if precio and sl and tp:
                        st.markdown(f"💰 Precio: **{precio:,.2f}**")
                        st.markdown(f"🛑 SL: **{sl:,.2f}**")
                        st.markdown(f"🎯 TP: **{tp:,.2f}**")
                        rr = round(abs(tp - precio) / abs(precio - sl), 1) if abs(precio - sl) > 0 else "N/D"
                        st.markdown(f"⚖️ R/R: **1:{rr}**")
                    else:
                        st.caption("SL/TP no disponible")

                st.divider()
                st.markdown("**🚗 Vehículos sugeridos**")
                for i, inst in enumerate(r.get("instrumentos", [])):
                    badge = "⭐ Recomendado" if i == 0 else "Alternativa"
                    st.markdown(f"**{badge}: {inst['vehiculo']}**")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown(f"📋 {inst['razon']}")
                        st.markdown(f"✅ **Pros:** {inst['pros']}")
                    with col_b:
                        st.markdown(f"🕐 **Cuándo:** {inst['cuando']}")
                        st.markdown(f"⚠️ **Contras:** {inst['contras']}")
                    if i < len(r.get("instrumentos", [])) - 1:
                        st.markdown("---")

                st.divider()
                st.markdown("**📋 Fundamentos**")
                st.markdown(f"*{r['tesis']}*")
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

# ── TAB IB TRADING ────────────────────────────────────────────────────────────
with tab_ib:
    st.subheader("🤖 IB Trading — Ejecución Automática Paper Trading")
    st.caption("Opera automáticamente en Interactive Brokers Paper Trading según las señales del sistema.")

    if not IB_DISPONIBLE:
        st.error("ibapi no está instalado. Ejecuta: `pip install ibapi`")
    else:
        # ── Estado cuenta IB
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("**Política de inversión activa:**")
            st.markdown("- Capital asignado: **USD 100.000** | Máx/operación: **USD 10.000**")
            st.markdown("- Horizonte máx: **3 días** | Posiciones máx: **5**")
            st.markdown("- Convicción mínima: **75%** | Riesgo máximo: **6/10**")
        with col2:
            if st.button("🔄 Actualizar cuenta"):
                st.session_state.cuenta_ib = get_resumen_cuenta()

        if "cuenta_ib" in st.session_state and st.session_state.cuenta_ib:
            cuenta = st.session_state.cuenta_ib
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("💰 Liquidación neta", f"USD {cuenta.get('NetLiquidation',0):,.0f}")
            with col2: st.metric("💵 Cash disponible", f"USD {cuenta.get('TotalCashValue',0):,.0f}")
            with col3: st.metric("📈 Buying Power", f"USD {cuenta.get('BuyingPower',0):,.0f}")

        st.divider()

        # ── Posiciones abiertas
        st.subheader("📂 Posiciones Abiertas")
        posiciones = get_posiciones_abiertas()
        if posiciones:
            rows = []
            for ticker, p in posiciones.items():
                fecha = datetime.fromisoformat(p["fecha_entrada"])
                dias  = (datetime.now() - fecha).days
                rows.append({
                    "Ticker":      ticker,
                    "Acción":      p["accion"],
                    "Cantidad":    p["cantidad"],
                    "Precio entr.":p.get("precio_entrada","N/D"),
                    "SL":          p.get("sl","N/D"),
                    "TP":          p.get("tp","N/D"),
                    "Días abierta":dias,
                    "Horizonte":   p.get("horizonte","N/D"),
                    "Vence en":    f"{max(0, 3-dias)} días",
                })
            df_pos = pd.DataFrame(rows)
            st.dataframe(df_pos, use_container_width=True, hide_index=True)

            # Cierre manual
            st.divider()
            st.markdown("**Cerrar posición manualmente:**")
            ticker_cerrar = st.selectbox("Selecciona posición", list(posiciones.keys()))
            if st.button("🔴 Cerrar posición", type="primary"):
                try:
                    from engine.ib_executor import IBExecutor, _crear_contrato, _cargar_posiciones, _guardar_posiciones
                    pos = posiciones[ticker_cerrar]
                    ib = IBExecutor()
                    if ib.conectar():
                        contrato = _crear_contrato(ticker_cerrar, pos["tipo"])
                        ib.cerrar_posicion(contrato, pos["cantidad"], pos["accion"])
                        time.sleep(2)
                        ib.disconnect()
                        del posiciones[ticker_cerrar]
                        _guardar_posiciones(posiciones)
                        st.success(f"✅ Posición {ticker_cerrar} cerrada")
                        st.rerun()
                    else:
                        st.error("No se pudo conectar a IB. ¿Está TWS corriendo?")
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.info("Sin posiciones abiertas")

        st.divider()

        # ── Ejecutar señales
        st.subheader("🚀 Ejecutar Señales")
        recomendaciones = st.session_state.get("recomendaciones", [])
        señales_validas = [r for r in recomendaciones if r["conviccion"] >= 75 and r["riesgo"] <= 6 and r["n_fuentes"] >= 2]

        if señales_validas:
            st.markdown(f"**{len(señales_validas)} señal(es) listas para ejecutar:**")
            for r in señales_validas:
                color = "🟢" if r["accion"] == "COMPRAR" else "🔴"
                precio = r.get("precio_actual")
                cantidad = int(10000 / precio) if precio else "N/D"
                monto = round(cantidad * precio, 0) if isinstance(cantidad, int) and precio else "N/D"
                st.markdown(
                    f"{color} **{r['accion']} {r['ib_ticker']}** — "
                    f"Conv: {r['conviccion']}% | Riesgo: {r['riesgo']}/10 | "
                    f"~{cantidad} unidades ≈ USD {monto:,.0f}" if isinstance(monto, float) else
                    f"{color} **{r['accion']} {r['ib_ticker']}** — Conv: {r['conviccion']}% | Riesgo: {r['riesgo']}/10"
                )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🧪 Simular (sin enviar)", use_container_width=True):
                    resultado = ejecutar_señales(recomendaciones, modo_test=True)
                    st.json(resultado)

            with col2:
                if st.button("🚀 EJECUTAR EN IB PAPER", type="primary", use_container_width=True):
                    with st.spinner("Conectando a IB y ejecutando órdenes..."):
                        resultado = ejecutar_señales(recomendaciones, modo_test=False)

                    if resultado["ordenes_enviadas"]:
                        st.success(f"✅ {len(resultado['ordenes_enviadas'])} orden(es) enviada(s) a IB")
                        for o in resultado["ordenes_enviadas"]:
                            st.markdown(f"- **{o['accion']} {o['ticker']}** — {o.get('cantidad','?')} unidades @ ~USD {o.get('monto_usd', o.get('precio_est','?'))}")
                    if resultado["ordenes_rechazadas"]:
                        st.warning(f"⚠️ {len(resultado['ordenes_rechazadas'])} rechazada(s)")
                        for o in resultado["ordenes_rechazadas"]:
                            st.markdown(f"- {o['ticker']}: {o['razon']}")
                    if resultado["errores"]:
                        st.error("Errores: " + " | ".join(resultado["errores"]))
                    st.rerun()
        else:
            st.info("Sin señales que cumplan la política de inversión en este momento.")

# ── TAB CHILE ─────────────────────────────────────────────────────────────────
with tab_chile:
    st.subheader("Indicadores Macro Chile")
    with st.spinner("Cargando..."):
        bcch = get_resumen_bcch()
    col1, col2, col3, col4 = st.columns(4)
    clp = bcch.get("CLP/USD")
    tpm = bcch.get("TPM_%")
    ipc = bcch.get("IPC_%")
    uf  = bcch.get("UF")
    with col1: st.metric("CLP/USD", f"${clp:,.0f}" if clp else "N/D")
    with col2: st.metric("TPM", f"{tpm}%" if tpm else "N/D")
    with col3: st.metric("IPC mensual", f"{ipc}%" if ipc else "N/D")
    with col4: st.metric("UF", f"${uf:,.2f}" if uf else "N/D")

    st.divider()
    st.subheader("⚡ Spread BTC")
    with st.spinner("Calculando..."):
        spread = get_spread_btc(clp or 892.0)
    if spread:
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("BTC Buda (CLP)", f"${spread['btc_local_clp']:,.0f}")
        with col2: st.metric("BTC Global (CLP)", f"${spread['btc_global_clp']:,.0f}")
        with col3: st.metric("Spread %", f"{spread['spread_pct']}%", delta=spread["direccion"])
        with col4: st.metric("BTC USD", f"${spread['btc_usd']:,.0f}")
        if spread.get("alerta"):
            st.error(f"🚨 ALERTA: BTC {spread['direccion']} un {abs(spread['spread_pct'])}%")
        else:
            st.success("✅ Spread normal")

    st.divider()
    st.subheader("📈 Activos Chile")
    with st.spinner("Cargando..."):
        df_cl = get_precios_chile()
    if not df_cl.empty:
        col_left, col_right = st.columns([2, 3])
        with col_left:
            for _, row in df_cl.iterrows():
                cambio = row["cambio_pct"]
                color  = "🟢" if cambio > 0 else "🔴"
                st.markdown(f"{color} **{row['ticker']}** — {row.get('descripcion','')}  \nPrecio: **{row['precio']:,.2f}** | Cambio: **{cambio:+.2f}%**")
        with col_right:
            fig = go.Figure(go.Bar(
                x=df_cl["ticker"], y=df_cl["cambio_pct"],
                marker_color=["#22c55e" if x > 0 else "#ef4444" for x in df_cl["cambio_pct"]],
                text=[f"{x:+.2f}%" for x in df_cl["cambio_pct"]], textposition="outside",
            ))
            fig.update_layout(title="Variación % del día", paper_bgcolor="#0f172a",
                plot_bgcolor="#0f172a", font_color="#e2e8f0", height=300,
                margin=dict(t=40,b=20), yaxis=dict(gridcolor="#1e293b"), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("🌐 Polymarket Chile")
    with st.spinner("Cargando..."):
        df_poly_cl = get_mercados_chile(limit=200)
    if not df_poly_cl.empty:
        for _, row in df_poly_cl.iterrows():
            prob = row["probabilidad"]
            if prob is None: continue
            color = "🟢" if prob > 65 else ("🔴" if prob < 35 else "🟡")
            rel   = row.get("relevancia", 1)
            with st.expander(f"{color} {row['pregunta'][:90]} — **{prob}%** {'⭐'*rel}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Prob:** {prob}% | **Activos:** {', '.join(row['chile_impact'])} | **Rel:** {rel}/5")
                with col2:
                    vol = row.get("volumen_usd", 0)
                    try: st.write(f"**Vol:** USD {float(vol):,.0f} | **Cierre:** {row.get('cierre','')}")
                    except: pass
                st.link_button("Ver en Polymarket", row.get("url",""))

# ── TAB USA ───────────────────────────────────────────────────────────────────
with tab_usa:
    st.subheader("📈 Activos USA")
    with st.spinner("Cargando..."):
        df_usa = get_precios_usa()
    if not df_usa.empty:
        cols = st.columns(3)
        for i, (_, row) in enumerate(df_usa.iterrows()):
            cambio = row["cambio_pct"]
            with cols[i % 3]:
                st.metric(row["ticker"], f"${row['precio']:,.2f}", delta=f"{cambio:+.2f}%",
                    delta_color="normal" if cambio >= 0 else "inverse")
        st.divider()
        fig = go.Figure(go.Bar(
            x=df_usa["ticker"], y=df_usa["cambio_pct"],
            marker_color=["#22c55e" if x > 0 else "#ef4444" for x in df_usa["cambio_pct"]],
            text=[f"{x:+.2f}%" for x in df_usa["cambio_pct"]], textposition="outside",
        ))
        fig.update_layout(title="Variación % — USA", paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a", font_color="#e2e8f0", height=350,
            margin=dict(t=40,b=20), yaxis=dict(gridcolor="#1e293b"), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("🌍 Macro USA")
    with st.spinner("Cargando..."):
        macro_data = get_macro_usa()
    if macro_data:
        cols = st.columns(4)
        for i, m in enumerate(macro_data):
            with cols[i % 4]:
                st.metric(m["nombre"] + (f" {m['alerta']}" if m["alerta"] else ""),
                    f"{m['precio']:,.2f}", delta=f"{m['cambio_pct']:+.2f}%",
                    delta_color="inverse" if m["inverso"] else "normal")
        st.divider()
        st.subheader("🔗 Correlaciones → Chile")
        for c in get_correlaciones_chile(macro_data)[:8]:
            score = c["score"]
            color = "🔴" if score >= 3 else ("🟡" if score >= 1.5 else "🟢")
            with st.expander(f"{color} [Score:{score}] {c['tesis']}"):
                col1, col2 = st.columns(2)
                with col1: st.write(f"**Indicador:** {c['indicador']} ({c['cambio_pct']:+.2f}%)")
                with col2: st.write(f"**Activo:** {c['activo_chile']} → {c['direccion']}")

    st.divider()
    st.subheader("🌐 Polymarket USA")
    with st.spinner("Cargando..."):
        df_poly = get_active_markets(limit=30)
    if not df_poly.empty:
        busqueda = st.text_input("🔍 Filtrar", placeholder="fed, bitcoin, china...")
        if busqueda:
            df_poly = df_poly[df_poly["pregunta"].str.lower().str.contains(busqueda.lower(), na=False)]
        for _, row in df_poly.iterrows():
            prob = row["probabilidad"]
            if prob is None: continue
            color = "🟢" if prob > 65 else ("🔴" if prob < 35 else "🟡")
            with st.expander(f"{color} {row['pregunta'][:90]} — **{prob}%**"):
                col1, col2 = st.columns(2)
                with col1: st.write(f"**Prob:** {prob}%")
                with col2:
                    vol = row.get("volumen_usd", 0)
                    try: st.write(f"**Vol:** USD {float(vol):,.0f}")
                    except: pass
                st.link_button("Ver en Polymarket", row.get("url",""))

# ── TAB DIVERGENCIAS ──────────────────────────────────────────────────────────
with tab_div:
    st.subheader("⚡ Divergencias")
    with st.spinner("Analizando..."):
        df_poly_div = get_mercados_chile(limit=200)
        bcch_div    = get_resumen_bcch()
        clp_div     = bcch_div.get("CLP/USD", 892.0)
        spread_div  = get_spread_btc(clp_div or 892.0)
        df_result   = calcular_divergencias(df_poly_div, spread_div)
    if not df_result.empty:
        nuevas = guardar_senales(df_result)
        if nuevas > 0: st.success(f"✅ {nuevas} señal(es) guardada(s)")
        top = df_result.iloc[0]
        st.info(f"**Principal:** {top['Señal']} — {top['Prob %']}% | {top['Dirección']} | Score: {top['Score']}")
        st.dataframe(df_result[["Señal","Prob %","Dirección","Activos Chile","Score","Tesis"]],
            use_container_width=True, hide_index=True)
    else:
        st.info("Sin divergencias")

# ── TAB KALSHI ────────────────────────────────────────────────────────────────
with tab_kalshi:
    st.subheader("🎰 Kalshi — CFTC")
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
                with col1: st.write(f"**Prob:** {prob}% | **Dir:** {s['direccion']} | **Activos:** {', '.join(s['activos_impacto'])}")
                with col2: st.write(f"**Score:** {s['score']} | **Cierre:** {s['cierre']}")
        st.divider()
        st.subheader("🔀 Triangulación")
        with st.spinner("..."):
            df_poly_tri = get_mercados_chile(limit=200)
        coincidencias = []
        for s in senales_kalshi:
            for _, row in df_poly_tri.iterrows():
                prob_poly = row.get("probabilidad")
                if prob_poly is None: continue
                dir_poly = "ALZA" if prob_poly > 50 else "BAJA"
                comunes = set(s["activos_impacto"]) & set(row.get("chile_impact", []))
                if comunes and s["direccion"] == dir_poly:
                    coincidencias.append({
                        "Kalshi": s["titulo"][:50], "Polymarket": row["pregunta"][:50],
                        "Dir": s["direccion"], "K%": f"{s['prob_pct']}%",
                        "P%": f"{prob_poly}%", "Activos": ", ".join(comunes),
                    })
        if coincidencias:
            st.success(f"✅ {len(coincidencias)} coincidencia(s)")
            st.dataframe(pd.DataFrame(coincidencias), use_container_width=True, hide_index=True)
        else:
            st.info("Sin coincidencias")

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
            kws   = n.get("keywords", [])
            color = "🔴" if score >= 10 else ("🟡" if score >= 5 else "🟢")
            tags  = " | ".join([f"`{k}`" for k in kws]) if kws else ""
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
    st.subheader("📊 Historial")
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
            opciones = [f"{r[0]} — {r[1][:60]}" for r in pendientes]
            seleccion = st.selectbox("Señal", opciones)
            resultado = st.radio("Resultado", ["correcto", "incorrecto"], horizontal=True)
            if st.button("Guardar"):
                idx = opciones.index(seleccion)
                actualizar_resultado(pendientes[idx][1], pendientes[idx][0][:10], resultado)
                st.success("✅ Guardado")
                st.rerun()
    else:
        st.info("Sin historial aún.")
