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

st.set_page_config(page_title="Trading Signals", page_icon="📊", layout="wide")
st_autorefresh(interval=15 * 60 * 1000, key="autorefresh")

# Cache de alertas enviadas (se resetea al reiniciar)
if "alertas_enviadas" not in st.session_state:
    st.session_state.alertas_enviadas = set()

st.title("📊 Trading Signals — Polymarket × Kalshi × Mercados")
col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.caption("Detección de divergencias entre mercados de predicción y activos financieros")
with col_refresh:
    st.caption(f"🔄 Actualizado: {datetime.now().strftime('%H:%M:%S')} | Refresh: 15 min")

tab_señales, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist = st.tabs([
    "🎯 Señales", "🇨🇱 Chile", "🇺🇸 USA", "⚡ Divergencias", "🎰 Kalshi", "📰 Noticias", "📊 Historial"
])

# ── TAB SEÑALES ───────────────────────────────────────────────────────────────
with tab_señales:
    st.subheader("🎯 Señales de Trading — Panel Ejecutivo")
    st.caption("Recomendaciones consolidadas desde Polymarket, Kalshi, Macro USA y Noticias Chile. Para operar en Interactive Brokers.")

    with st.spinner("Analizando todas las fuentes..."):
        poly_df     = get_mercados_chile(limit=200)
        kalshi_list = get_kalshi_resumen()
        macro_raw   = get_macro_usa()
        macro_corr  = get_correlaciones_chile(macro_raw)
        noticias    = get_noticias_google()
        activos     = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias)
        recomendaciones = generar_recomendaciones(activos)

    # Enviar alertas Telegram si corresponde
    if recomendaciones:
        n_alertas, st.session_state.alertas_enviadas = enviar_alertas_nuevas(
            recomendaciones, st.session_state.alertas_enviadas
        )
        if n_alertas > 0:
            st.success(f"📱 {n_alertas} alerta(s) enviada(s) a Telegram")

    if recomendaciones:
        compras = [r for r in recomendaciones if r["accion"] == "COMPRAR"]
        ventas  = [r for r in recomendaciones if r["accion"] == "VENDER"]

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("📊 Total señales", len(recomendaciones))
        with col2: st.metric("🟢 Comprar", len(compras))
        with col3: st.metric("🔴 Vender", len(ventas))
        with col4:
            avg_riesgo = round(sum(r["riesgo"] for r in recomendaciones) / len(recomendaciones), 1)
            st.metric("⚠️ Riesgo promedio", f"{avg_riesgo}/10")

        st.divider()

        # Señal principal
        top = recomendaciones[0]
        color_top = "🟢" if top["accion"] == "COMPRAR" else "🔴"
        h = top.get("horizonte", {})
        st.info(
            f"**Señal principal:** {color_top} **{top['accion']} {top['ib_ticker']}** "
            f"({top['descripcion']})  \n"
            f"Convicción: **{top['conviccion']}%** | Riesgo: **{top['riesgo']}/10** | "
            f"{h.get('emoji','')} Horizonte: **{h.get('dias','N/D')}** | "
            f"Fuentes: **{', '.join(top['fuentes'])}**"
        )

        st.divider()

        # Listado completo
        for r in recomendaciones:
            accion  = r["accion"]
            color   = "🟢" if accion == "COMPRAR" else "🔴"
            riesgo  = r["riesgo"]
            h       = r.get("horizonte", {})

            if riesgo <= 3:   riesgo_color = "🟢"
            elif riesgo <= 6: riesgo_color = "🟡"
            else:             riesgo_color = "🔴"

            # Indicador de alerta Telegram
            alerta_key = f"{r['accion']}_{r['ib_ticker']}"
            telegram_icon = "📱" if alerta_key in st.session_state.alertas_enviadas else ""

            header = (
                f"{color} **{accion} {r['ib_ticker']}** — {r['descripcion']}  |  "
                f"Convicción: **{r['conviccion']}%**  |  "
                f"Riesgo: {riesgo_color} **{riesgo}/10**  |  "
                f"{h.get('emoji','')} **{h.get('label','')}** {telegram_icon}"
            )

            with st.expander(header):
                # ── Fila 1: Acción + Métricas + Dirección
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"### {color} {accion}")
                    st.markdown(f"**Instrumento IB:** `{r['ib_ticker']}`")
                    st.markdown(f"**Tipo:** {r['tipo']}")
                    st.markdown(f"**Descripción:** {r['descripcion']}")
                with col2:
                    st.markdown("**Métricas**")
                    st.progress(r["conviccion"] / 100, text=f"Convicción: {r['conviccion']}%")
                    st.progress(riesgo / 10, text=f"Riesgo: {riesgo}/10")
                    st.markdown(f"**Fuentes ({r['n_fuentes']}):** {', '.join(r['fuentes'])}")
                with col3:
                    if accion == "COMPRAR":
                        st.success("⬆️ LONG")
                    else:
                        st.error("⬇️ SHORT")

                st.divider()

                # ── Fila 2: Horizonte + SL/TP
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**⏱️ Horizonte de inversión**")
                    st.markdown(f"{h.get('emoji','')} **{h.get('label','')}** — {h.get('dias','')}")

                with col2:
                    st.markdown("**📐 Stop Loss / Take Profit**")
                    precio = r.get("precio_actual")
                    sl     = r.get("stop_loss")
                    tp     = r.get("take_profit")
                    if precio and sl and tp:
                        st.markdown(f"💰 Precio actual: **{precio:,.2f}**")
                        st.markdown(f"🛑 Stop Loss: **{sl:,.2f}**")
                        st.markdown(f"🎯 Take Profit: **{tp:,.2f}**")
                        riesgo_recompensa = round(abs(tp - precio) / abs(precio - sl), 1) if abs(precio - sl) > 0 else "N/D"
                        st.markdown(f"⚖️ Ratio R/R: **1:{riesgo_recompensa}**")
                    else:
                        st.caption("SL/TP no disponible para este instrumento")

                st.divider()

                # ── Fila 3: Vehículos sugeridos
                st.markdown("**🚗 Vehículos de inversión sugeridos**")
                instrumentos = r.get("instrumentos", [])
                for i, inst in enumerate(instrumentos):
                    badge = "⭐ Recomendado" if i == 0 else "Alternativa"
                    with st.container():
                        st.markdown(f"**{badge}: {inst['vehiculo']}**")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown(f"📋 {inst['razon']}")
                            st.markdown(f"✅ **Pros:** {inst['pros']}")
                        with col_b:
                            st.markdown(f"🕐 **Cuándo:** {inst['cuando']}")
                            st.markdown(f"⚠️ **Contras:** {inst['contras']}")
                        if i < len(instrumentos) - 1:
                            st.markdown("---")

                st.divider()

                # ── Fila 4: Fundamentos
                st.markdown("**📋 Fundamentos de la señal**")
                st.markdown(f"*{r['tesis']}*")

                fuentes_orden = ["Polymarket", "Kalshi", "Macro USA", "Noticias"]
                for fuente in fuentes_orden:
                    ev_fuente = [e for e in r["evidencia"] if e["fuente"] == fuente]
                    if not ev_fuente: continue
                    st.markdown(f"**{fuente}**")
                    for e in ev_fuente[:3]:
                        prob_str  = f" ({e['prob']}%)" if e.get("prob") else ""
                        dir_icon  = "📈" if e["direccion"] == "ALZA" else ("📉" if e["direccion"] == "BAJA" else "➡️")
                        st.markdown(f"- {dir_icon} {e['señal']}{prob_str} — Peso: `{e['peso']}`")

                st.divider()
                st.caption("⚠️ Señal informativa. No constituye asesoría de inversión. Opere bajo su propio criterio y gestión de riesgo.")

    else:
        st.info("Sin señales suficientemente consolidadas en este momento.")

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
    st.subheader("⚡ Spread BTC Local vs Global")
    with st.spinner("Calculando..."):
        spread = get_spread_btc(clp or 892.0)
    if spread:
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("BTC Buda (CLP)", f"${spread['btc_local_clp']:,.0f}")
        with col2: st.metric("BTC Global (CLP)", f"${spread['btc_global_clp']:,.0f}")
        with col3: st.metric("Spread %", f"{spread['spread_pct']}%", delta=spread["direccion"])
        with col4: st.metric("BTC USD", f"${spread['btc_usd']:,.0f}")
        if spread.get("alerta"):
            st.error(f"🚨 ALERTA: BTC {spread['direccion']} un {abs(spread['spread_pct'])}% vs precio global")
        else:
            st.success("✅ Spread BTC dentro de rango normal")

    st.divider()
    st.subheader("📈 Activos Chile")
    with st.spinner("Cargando precios..."):
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
    st.subheader("🌐 Señales Polymarket con impacto en Chile")
    with st.spinner("Cargando Polymarket..."):
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
                    st.write(f"**Probabilidad:** {prob}%")
                    st.write(f"**Activos Chile:** {', '.join(row['chile_impact'])}")
                    st.write(f"**Relevancia:** {rel}/5")
                with col2:
                    vol = row.get("volumen_usd", 0)
                    try: st.write(f"**Volumen:** USD {float(vol):,.0f}")
                    except: st.write(f"**Volumen:** {vol}")
                    st.write(f"**Cierre:** {row.get('cierre','')}")
                st.link_button("Ver en Polymarket", row.get("url",""))
    else:
        st.info("Sin mercados Polymarket con impacto Chile detectado")

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
                st.metric(row["ticker"], f"${row['precio']:,.2f}",
                    delta=f"{cambio:+.2f}%",
                    delta_color="normal" if cambio >= 0 else "inverse")
        st.divider()
        fig = go.Figure(go.Bar(
            x=df_usa["ticker"], y=df_usa["cambio_pct"],
            marker_color=["#22c55e" if x > 0 else "#ef4444" for x in df_usa["cambio_pct"]],
            text=[f"{x:+.2f}%" for x in df_usa["cambio_pct"]], textposition="outside",
        ))
        fig.update_layout(title="Variación % del día — Activos USA", paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a", font_color="#e2e8f0", height=350,
            margin=dict(t=40,b=20), yaxis=dict(gridcolor="#1e293b"), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("🌍 Macro USA — Indicadores Clave")
    with st.spinner("Cargando macro USA..."):
        macro_data = get_macro_usa()
    if macro_data:
        cols = st.columns(4)
        for i, m in enumerate(macro_data):
            with cols[i % 4]:
                alerta_txt = f" {m['alerta']}" if m["alerta"] else ""
                st.metric(m["nombre"] + alerta_txt, f"{m['precio']:,.2f}",
                    delta=f"{m['cambio_pct']:+.2f}%",
                    delta_color="inverse" if m["inverso"] else "normal")
        st.divider()
        st.subheader("🔗 Correlaciones Macro USA → Chile")
        correlaciones = get_correlaciones_chile(macro_data)
        for c in correlaciones[:8]:
            score = c["score"]
            color = "🔴" if score >= 3 else ("🟡" if score >= 1.5 else "🟢")
            with st.expander(f"{color} [Score:{score}] {c['tesis']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Indicador:** {c['indicador']}")
                    st.write(f"**Cambio:** {c['cambio_pct']:+.2f}%")
                with col2:
                    st.write(f"**Activo Chile:** {c['activo_chile']}")
                    st.write(f"**Dirección:** {c['direccion']}")

    st.divider()
    st.subheader("🌐 Mercados Polymarket — Top por Volumen")
    with st.spinner("Cargando..."):
        df_poly = get_active_markets(limit=30)
    if not df_poly.empty:
        busqueda = st.text_input("🔍 Filtrar mercados", placeholder="fed, bitcoin, china...")
        if busqueda:
            df_poly = df_poly[df_poly["pregunta"].str.lower().str.contains(busqueda.lower(), na=False)]
        for _, row in df_poly.iterrows():
            prob = row["probabilidad"]
            if prob is None: continue
            color = "🟢" if prob > 65 else ("🔴" if prob < 35 else "🟡")
            with st.expander(f"{color} {row['pregunta'][:90]} — **{prob}%**"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Probabilidad (Yes):** {prob}%")
                    impactos = row.get("chile_impact", [])
                    if impactos: st.write(f"**Impacto Chile:** {', '.join(impactos)}")
                with col2:
                    vol = row.get("volumen_usd", 0)
                    try: st.write(f"**Volumen:** USD {float(vol):,.0f}")
                    except: st.write(f"**Volumen:** {vol}")
                    st.write(f"**Cierre:** {row.get('cierre','')}")
                st.link_button("Ver en Polymarket", row.get("url",""))

# ── TAB DIVERGENCIAS ──────────────────────────────────────────────────────────
with tab_div:
    st.subheader("⚡ Divergencias y Oportunidades Detectadas")
    with st.spinner("Analizando divergencias..."):
        df_poly_div = get_mercados_chile(limit=200)
        bcch_div    = get_resumen_bcch()
        clp_div     = bcch_div.get("CLP/USD", 892.0)
        spread_div  = get_spread_btc(clp_div or 892.0)
        df_result   = calcular_divergencias(df_poly_div, spread_div)
    if not df_result.empty:
        nuevas = guardar_senales(df_result)
        if nuevas > 0:
            st.success(f"✅ {nuevas} señal(es) nueva(s) guardada(s) en historial")
        top = df_result.iloc[0]
        st.info(f"**Señal principal:** {top['Señal']} — {top['Prob %']}% | {top['Dirección']} | Score: {top['Score']}")
        st.dataframe(df_result[["Señal","Prob %","Dirección","Activos Chile","Relevancia","Score","Tesis"]],
            use_container_width=True, hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=20, format="%.2f"),
                "Prob %": st.column_config.NumberColumn("Prob %", format="%.1f%%"),
                "Tesis": st.column_config.TextColumn("Tesis", width="large"),
            })
    else:
        st.info("Sin divergencias detectadas")

# ── TAB KALSHI ────────────────────────────────────────────────────────────────
with tab_kalshi:
    st.subheader("🎰 Kalshi — Mercados de Predicción Regulados (CFTC)")
    with st.spinner("Cargando Kalshi..."):
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
                with col1:
                    st.write(f"**Prob:** {prob}% | **Dir:** {s['direccion']}")
                    st.write(f"**Activos:** {', '.join(s['activos_impacto'])}")
                with col2:
                    st.write(f"**Score:** {s['score']} | **Cierre:** {s['cierre']}")
        st.divider()
        st.subheader("🔀 Triangulación Kalshi × Polymarket")
        with st.spinner("Triangulando..."):
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
                        "Dirección": s["direccion"], "Prob K": f"{s['prob_pct']}%",
                        "Prob P": f"{prob_poly}%", "Activos": ", ".join(comunes),
                    })
        if coincidencias:
            st.success(f"✅ {len(coincidencias)} señal(es) confirmada(s)")
            st.dataframe(pd.DataFrame(coincidencias), use_container_width=True, hide_index=True)
        else:
            st.info("Sin coincidencias en este momento")

# ── TAB NOTICIAS ──────────────────────────────────────────────────────────────
with tab_noticias:
    st.subheader("📰 Noticias Chile — Mercados y Economía")
    with st.spinner("Cargando noticias..."):
        noticias = get_noticias_google()
    if noticias:
        col_f1, col_f2 = st.columns([2, 3])
        with col_f1: min_score = st.slider("Score mínimo", 0, 15, 3)
        with col_f2: busqueda_n = st.text_input("🔍 Buscar", placeholder="litio, cobre, tasa...")
        noticias_filtradas = [n for n in noticias if n["score"] >= min_score]
        if busqueda_n:
            noticias_filtradas = [n for n in noticias_filtradas if busqueda_n.lower() in n["titulo"].lower()]
        st.caption(f"Mostrando {len(noticias_filtradas)} noticias")
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
    st.subheader("📊 Historial de Señales")
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
        senales_pendientes = [r for r in rows if r[7] == "pendiente"]
        if senales_pendientes:
            opciones = [f"{r[0]} — {r[1][:60]}" for r in senales_pendientes]
            seleccion = st.selectbox("Selecciona señal", opciones)
            resultado = st.radio("Resultado", ["correcto", "incorrecto"], horizontal=True)
            if st.button("Guardar resultado"):
                idx = opciones.index(seleccion)
                actualizar_resultado(senales_pendientes[idx][1], senales_pendientes[idx][0][:10], resultado)
                st.success("✅ Guardado")
                st.rerun()
    else:
        st.info("Sin historial aún.")
