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
from engine.recomendaciones import consolidar_señales, generar_recomendaciones

st.set_page_config(page_title="Trading Signals", page_icon="📊", layout="wide")
st_autorefresh(interval=15 * 60 * 1000, key="autorefresh")

st.title("📊 Trading Signals — Polymarket × Kalshi × Mercados")
col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.caption("Detección de divergencias entre mercados de predicción y activos financieros")
with col_refresh:
    st.caption(f"🔄 Actualizado: {datetime.now().strftime('%H:%M:%S')} | Refresh: 15 min")

tab_señales, tab_chile, tab_usa, tab_div, tab_kalshi, tab_noticias, tab_hist = st.tabs([
    "🎯 Señales", "🇨🇱 Chile", "🇺🇸 USA", "⚡ Divergencias", "🎰 Kalshi", "📰 Noticias", "📊 Historial"
])

# ── TAB SEÑALES ──────────────────────────────────────────────────────────────
with tab_señales:
    st.subheader("🎯 Señales de Trading — Panel Ejecutivo")
    st.caption("Recomendaciones consolidadas desde Polymarket, Kalshi, Macro USA y Noticias Chile. Para operar en Interactive Brokers.")

    with st.spinner("Analizando todas las fuentes..."):
        poly_df     = get_mercados_chile(limit=200)
        kalshi_list = get_kalshi_resumen()
        macro_raw   = get_macro_usa()
        macro_corr  = get_correlaciones_chile(macro_raw)
        noticias    = get_noticias_google()

        activos = consolidar_señales(poly_df, kalshi_list, macro_corr, noticias)
        recomendaciones = generar_recomendaciones(activos)

    if recomendaciones:
        # Resumen ejecutivo
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

        # Señal principal destacada
        top = recomendaciones[0]
        color_top = "🟢" if top["accion"] == "COMPRAR" else "🔴"
        st.info(
            f"**Señal principal:** {color_top} **{top['accion']} {top['ib_ticker']}** "
            f"({top['descripcion']})  \n"
            f"Convicción: **{top['conviccion']}%** | Riesgo: **{top['riesgo']}/10** | "
            f"Fuentes: **{', '.join(top['fuentes'])}**"
        )

        st.divider()

        # Listado completo
        for r in recomendaciones:
            accion  = r["accion"]
            color   = "🟢" if accion == "COMPRAR" else "🔴"
            riesgo  = r["riesgo"]

            # Barra de riesgo visual
            riesgo_bar = "█" * riesgo + "░" * (10 - riesgo)

            # Color riesgo
            if riesgo <= 3:
                riesgo_color = "🟢"
            elif riesgo <= 6:
                riesgo_color = "🟡"
            else:
                riesgo_color = "🔴"

            header = (
                f"{color} **{accion} {r['ib_ticker']}** — {r['descripcion']}  |  "
                f"Convicción: **{r['conviccion']}%**  |  "
                f"Riesgo: {riesgo_color} **{riesgo}/10**"
            )

            with st.expander(header):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"### {color} {accion}")
                    st.markdown(f"**Instrumento:** `{r['ib_ticker']}` en Interactive Brokers")
                    st.markdown(f"**Tipo:** {r['tipo']}")
                    st.markdown(f"**Descripción:** {r['descripcion']}")
                with col2:
                    st.markdown("**Métricas**")
                    st.progress(r["conviccion"] / 100, text=f"Convicción: {r['conviccion']}%")
                    st.progress(riesgo / 10, text=f"Riesgo: {riesgo}/10 ({riesgo_bar})")
                    st.markdown(f"**Fuentes ({r['n_fuentes']}):** {', '.join(r['fuentes'])}")
                with col3:
                    if accion == "COMPRAR":
                        st.success("⬆️ LONG")
                    else:
                        st.error("⬇️ SHORT")

                st.divider()
                st.markdown("#### 📋 Fundamentos")
                st.markdown(f"*{r['tesis']}*")

                # Evidencia por fuente
                fuentes_orden = ["Polymarket", "Kalshi", "Macro USA", "Noticias"]
                for fuente in fuentes_orden:
                    ev_fuente = [e for e in r["evidencia"] if e["fuente"] == fuente]
                    if not ev_fuente:
                        continue
                    st.markdown(f"**{fuente}**")
                    for e in ev_fuente[:3]:
                        prob_str = f" ({e['prob']}%)" if e.get("prob") else ""
                        dir_icon = "📈" if e["direccion"] == "ALZA" else ("📉" if e["direccion"] == "BAJA" else "➡️")
                        st.markdown(f"- {dir_icon} {e['señal']}{prob_str} — Peso: `{e['peso']}`")

                st.divider()
                st.caption("⚠️ Esta señal es informativa. No constituye asesoría de inversión. Opere bajo su propio criterio y gestión de riesgo.")

    else:
        st.info("Sin señales de trading suficientemente consolidadas en este momento. Vuelve en 15 minutos.")

# ── TAB CHILE ────────────────────────────────────────────────────────────────
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

# ── TAB USA ──────────────────────────────────────────────────────────────────
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
    st.caption("Indicadores que impactan directamente en activos chilenos vía correlaciones globales.")
    with st.spinner("Cargando macro USA..."):
        macro_data = get_macro_usa()
    if macro_data:
        cols = st.columns(4)
        for i, m in enumerate(macro_data):
            cambio = m["cambio_pct"]
            with cols[i % 4]:
                alerta_txt = f" {m['alerta']}" if m["alerta"] else ""
                st.metric(
                    m["nombre"] + alerta_txt,
                    f"{m['precio']:,.2f}",
                    delta=f"{cambio:+.2f}%",
                    delta_color="inverse" if m["inverso"] else "normal"
                )
        st.divider()
        st.subheader("🔗 Correlaciones Macro USA → Chile")
        correlaciones = get_correlaciones_chile(macro_data)
        if correlaciones:
            for c in correlaciones[:8]:
                score = c["score"]
                color = "🔴" if score >= 3 else ("🟡" if score >= 1.5 else "🟢")
                alerta = f" **{c['alerta']}**" if c["alerta"] else ""
                with st.expander(f"{color} [Score:{score}] {c['tesis']}{alerta}"):
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

# ── TAB DIVERGENCIAS ─────────────────────────────────────────────────────────
with tab_div:
    st.subheader("⚡ Divergencias y Oportunidades Detectadas")
    st.caption("Score = distancia al 50% × volumen × multiplicador de relevancia geopolítica")
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
        st.info(
            f"**Señal principal:** {top['Señal']}  \n"
            f"Probabilidad: **{top['Prob %']}%** | {top['Dirección']} | "
            f"Activos: **{top['Activos Chile']}** | Score: **{top['Score']}**"
        )
        st.dataframe(
            df_result[["Señal","Prob %","Dirección","Activos Chile","Relevancia","Score","Tesis"]],
            use_container_width=True, hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=20, format="%.2f"),
                "Prob %": st.column_config.NumberColumn("Prob %", format="%.1f%%"),
                "Tesis": st.column_config.TextColumn("Tesis", width="large"),
            }
        )
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Variables Chile**")
            st.write(f"- CLP/USD: **{bcch_div.get('CLP/USD','N/D')}**")
            st.write(f"- TPM: **{bcch_div.get('TPM_%','N/D')}%**")
            st.write(f"- IPC: **{bcch_div.get('IPC_%','N/D')}%**")
            st.write(f"- UF: **${bcch_div.get('UF','N/D'):,}**")
        with col2:
            st.markdown("**Spread BTC**")
            if spread_div:
                st.write(f"- Local: **${spread_div.get('btc_local_clp',0):,.0f} CLP**")
                st.write(f"- Global: **${spread_div.get('btc_global_clp',0):,.0f} CLP**")
                st.write(f"- Spread: **{spread_div.get('spread_pct',0)}%**")
    else:
        st.info("Sin divergencias detectadas en este momento")

# ── TAB KALSHI ───────────────────────────────────────────────────────────────
with tab_kalshi:
    st.subheader("🎰 Kalshi — Mercados de Predicción Regulados (CFTC)")
    st.caption("Kalshi es el primer exchange de predicción regulado por la CFTC en USA.")
    with st.spinner("Cargando Kalshi..."):
        senales_kalshi = get_kalshi_resumen()
    if senales_kalshi:
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Señales activas", len(senales_kalshi))
        alza = sum(1 for s in senales_kalshi if s["direccion"] == "ALZA")
        baja = sum(1 for s in senales_kalshi if s["direccion"] == "BAJA")
        with col2: st.metric("📈 ALZA", alza)
        with col3: st.metric("📉 BAJA", baja)
        st.divider()
        series_vistas = set()
        for s in senales_kalshi:
            serie = s["serie"]
            if serie not in series_vistas:
                st.markdown(f"### {serie}")
                series_vistas.add(serie)
            prob = s["prob_pct"]
            color = "🟢" if prob > 65 else ("🔴" if prob < 35 else "🟡")
            with st.expander(f"{color} {s['titulo'][:90]} — **{prob}%** | Score: {s['score']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Probabilidad:** {prob}%")
                    st.write(f"**Dirección:** {s['direccion']}")
                    st.write(f"**Activos:** {', '.join(s['activos_impacto'])}")
                with col2:
                    st.write(f"**Score:** {s['score']}")
                    st.write(f"**Cierre:** {s['cierre']}")
                    st.write(f"**Volumen:** {s['volumen']}")
        st.divider()
        st.subheader("🔀 Triangulación Kalshi × Polymarket")
        with st.spinner("Triangulando..."):
            df_poly_tri = get_mercados_chile(limit=200)
        if not df_poly_tri.empty:
            coincidencias = []
            for s in senales_kalshi:
                for _, row in df_poly_tri.iterrows():
                    prob_poly = row.get("probabilidad")
                    if prob_poly is None: continue
                    dir_poly = "ALZA" if prob_poly > 50 else "BAJA"
                    comunes = set(s["activos_impacto"]) & set(row.get("chile_impact", []))
                    if comunes and s["direccion"] == dir_poly:
                        coincidencias.append({
                            "Kalshi": s["titulo"][:50],
                            "Polymarket": row["pregunta"][:50],
                            "Dirección": s["direccion"],
                            "Prob Kalshi": f"{s['prob_pct']}%",
                            "Prob Poly": f"{prob_poly}%",
                            "Activos": ", ".join(comunes),
                        })
            if coincidencias:
                st.success(f"✅ {len(coincidencias)} señal(es) confirmada(s) en ambas plataformas")
                st.dataframe(pd.DataFrame(coincidencias), use_container_width=True, hide_index=True)
            else:
                st.info("Sin señales coincidentes en este momento")

# ── TAB NOTICIAS ─────────────────────────────────────────────────────────────
with tab_noticias:
    st.subheader("📰 Noticias Chile — Mercados y Economía")
    with st.spinner("Cargando noticias..."):
        noticias = get_noticias_google()
    if noticias:
        col_f1, col_f2 = st.columns([2, 3])
        with col_f1:
            min_score = st.slider("Score mínimo", 0, 15, 3)
        with col_f2:
            busqueda_n = st.text_input("🔍 Buscar", placeholder="litio, cobre, tasa...")
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
            }
        )
        st.divider()
        st.subheader("✏️ Marcar resultado")
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
