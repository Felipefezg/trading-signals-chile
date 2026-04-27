"""
Script para integrar NLP sentiment al tab de noticias del dashboard.
"""
import re

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar import NLP
if "nlp_sentiment" not in content:
    content = content.replace(
        "from engine.backtesting import ejecutar_backtest, get_estadisticas_backtest",
        "from engine.backtesting import ejecutar_backtest, get_estadisticas_backtest\n"
        "from engine.nlp_sentiment import analizar_noticias_batch, get_resumen_sentiment, get_sentiment_por_activo"
    )
    print("✅ Import NLP agregado")

# 2. Reemplazar tab noticias con versión NLP
old_noticias = '''# ── TAB NOTICIAS ──────────────────────────────────────────────────────────────
with tab_noticias:
    st.markdown("### 📰 Noticias Chile — Mercados")
    with st.spinner(""):
        noticias = get_noticias_google()
    if noticias:
        col_f1,col_f2 = st.columns([2,3])
        with col_f1: min_score = st.slider("Score mínimo", 0, 15, 3)
        with col_f2: busqueda_n = st.text_input("🔍 Buscar", placeholder="litio, cobre, tasa, SQM...")
        noticias_filtradas = [n for n in noticias if n["score"]>=min_score]
        if busqueda_n: noticias_filtradas = [n for n in noticias_filtradas if busqueda_n.lower() in n["titulo"].lower()]
        st.caption(f"{len(noticias_filtradas)} noticias relevantes")
        for n in noticias_filtradas:
            score = n["score"]
            color = "🔴" if score>=10 else ("🟡" if score>=5 else "🟢")
            tags  = " · ".join(n.get("keywords",[])) if n.get("keywords") else ""
            with st.expander(f"[{score}]  {n['titulo'][:100]}"):
                col1,col2 = st.columns([3,1])
                with col1:
                    st.caption(f"**{n['fuente']}** · {n.get('fecha','')[:30]}")
                    if tags: st.caption(f"🏷 {tags}")
                with col2:
                    if n.get("url"): st.link_button("🔗 Leer", n["url"])'''

new_noticias = '''# ── TAB NOTICIAS ──────────────────────────────────────────────────────────────
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
            f\'<div style="background:#0d1117;border:1px solid {sesgo_color}44;\'
            f\'border-left:3px solid {sesgo_color};border-radius:8px;\'
            f\'padding:0.6rem 1rem;margin-bottom:0.75rem">\'
            f\'<span style="color:{sesgo_color};font-weight:700">SENTIMENT MERCADO: {sesgo}</span>\'
            f\' &nbsp;·&nbsp; <span style="color:#94a3b8;font-size:0.82rem">\'
            f\'🟢 {resumen_sent.get("positivas",0)} positivas &nbsp;\'
            f\'🔴 {resumen_sent.get("negativas",0)} negativas &nbsp;\'
            f\'⚪ {resumen_sent.get("neutras",0)} neutras\'
            f\' &nbsp;·&nbsp; Ratio positivo: {resumen_sent.get("ratio_positivo",0)}%</span></div>\',
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
                        f\'<div style="background:#0d1117;border:1px solid {color}44;\'
                        f\'border-radius:6px;padding:0.4rem 0.6rem;text-align:center">\'
                        f\'<div style="color:#64748b;font-size:0.68rem">{activo.replace(".SN","")}</div>\'
                        f\'<div style="color:{color};font-weight:700;font-size:0.9rem">{data["tono"]}</div>\'
                        f\'<div style="color:#475569;font-size:0.68rem">{data["n_noticias"]} noticias</div></div>\',
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
                f\'[{score}] \' +
                (f\'🟢\' if sent.get("señal",0) > 0 else (f\'🔴\' if sent.get("señal",0) < 0 else f\'⚪\')) +
                f\' {n["titulo"][:90]}\'
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"**{n[\'fuente\']}** · {n.get(\'fecha\',\'\')[:30]}")
                    if tags: st.caption(f"🏷 {tags}")
                    st.markdown(
                        f\'<span style="background:{color_sent}22;color:{color_sent};\'
                        f\'border:1px solid {color_sent}44;border-radius:4px;\'
                        f\'padding:2px 8px;font-size:0.72rem;font-weight:700">\'
                        f\'{tono} {estrellas} conf:{sent.get("confianza",0):.2f}</span>\',
                        unsafe_allow_html=True
                    )
                with col2:
                    if n.get("url"): st.link_button("🔗 Leer", n["url"])'''

if old_noticias in content:
    content = content.replace(old_noticias, new_noticias)
    print("✅ Tab noticias actualizado con NLP")
else:
    print("❌ No se encontró el bloque exacto — buscando por líneas...")
    lines = content.split('\n')
    start = next((i for i, l in enumerate(lines) if '# ── TAB NOTICIAS' in l), None)
    end   = next((i for i, l in enumerate(lines) if '# ── TAB HISTORIAL' in l), None)
    if start and end:
        content = '\n'.join(lines[:start]) + '\n' + new_noticias + '\n\n' + '\n'.join(lines[end:])
        print(f"✅ Tab noticias reemplazado por líneas ({start}-{end})")
    else:
        print(f"❌ start={start} end={end}")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard guardado")
