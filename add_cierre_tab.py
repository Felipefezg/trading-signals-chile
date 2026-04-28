"""
Script para integrar cierre automático al dashboard.
Agrega:
1. Import del módulo
2. Verificación automática en cada refresh (tab Ejecución)
3. Historial de cierres automáticos
"""

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar import
if "cierre_automatico" not in content:
    content = content.replace(
        "from engine.performance import get_metricas_performance, get_benchmarks, CAPITAL_INICIAL",
        "from engine.performance import get_metricas_performance, get_benchmarks, CAPITAL_INICIAL\n"
        "from engine.cierre_automatico import verificar_posiciones, get_log_cierres"
    )
    print("✅ Import agregado")

# 2. Agregar verificación automática después del autorefresh
old_session = '''if "alertas_enviadas" not in st.session_state:
    st.session_state.alertas_enviadas = set()'''

new_session = '''if "alertas_enviadas" not in st.session_state:
    st.session_state.alertas_enviadas = set()

# Verificación automática de SL/TP en cada refresh
if "ultima_verificacion" not in st.session_state:
    st.session_state.ultima_verificacion = None

ahora = datetime.now()
ultima = st.session_state.ultima_verificacion
if ultima is None or (ahora - ultima).seconds > 300:  # cada 5 min
    try:
        resumen_cierre = verificar_posiciones(modo_test=False, auto_cerrar=True)
        st.session_state.ultima_verificacion = ahora
        st.session_state.resumen_cierre = resumen_cierre
        if resumen_cierre.get("cierres"):
            st.session_state.alertas_cierre = resumen_cierre["cierres"]
    except Exception as e:
        pass'''

content = content.replace(old_session, new_session)
print("✅ Verificación automática agregada")

# 3. Agregar alerta de cierre en el header si hay cierres
old_header = '# ── TABS ────────────────────────────────────────────────────────────────────────'
new_header = '''# Mostrar alerta si hubo cierres automáticos
if st.session_state.get("alertas_cierre"):
    for c in st.session_state.alertas_cierre:
        color = "#ef4444" if c["razon"] == "STOP LOSS" else "#22c55e"
        st.markdown(
            f\'<div style="background:{color}15;border:1px solid {color}44;border-radius:6px;\'
            f\'padding:0.4rem 0.9rem;margin-bottom:0.5rem;font-size:0.8rem">\'
            f\'<span style="color:{color};font-weight:700">CIERRE AUTOMÁTICO: {c["razon"]}</span>\'
            f\' — {c["ticker"]} | PnL: {c["pnl_pct"]:+.2f}%\'
            f\'{"  ✅ Ejecutado" if c.get("ejecutado") else "  ⚠️ "+str(c.get("error",""))}</div>\',
            unsafe_allow_html=True
        )
    st.session_state.alertas_cierre = []

# ── TABS ────────────────────────────────────────────────────────────────────────'''

content = content.replace(old_header, new_header)
print("✅ Alerta de cierre agregada")

# 4. Agregar sección en tab Ejecución - después de "sub_ib, sub_hist"
old_tabs_ej = '    sub_ib, sub_hist = st.tabs(["IB Paper Trading", "Historial de Órdenes"])'
new_tabs_ej = '    sub_ib, sub_hist, sub_cierre = st.tabs(["IB Paper Trading", "Historial de Órdenes", "Cierres Automáticos"])'
content = content.replace(old_tabs_ej, new_tabs_ej)

# 5. Agregar contenido del tab cierre al final del tab ejecución
old_end = "        else:\n            st.caption(\"Sin historial de señales aún.\")"
new_end = """        else:
            st.caption("Sin historial de señales aún.")

    with sub_cierre:
        st.markdown("**Cierre Automático de Posiciones — SL/TP/Horizonte**")
        st.caption("El sistema verifica cada 5 minutos si alguna posición debe cerrarse por Stop Loss, Take Profit o vencimiento del horizonte.")

        # Estado actual
        col1, col2 = st.columns([3, 1])
        with col2:
            modo_auto = st.toggle("Cierre automático activo", value=True)
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
                        f\'<div style="display:flex;justify-content:space-between;padding:0.25rem 0;border-bottom:1px solid #1a2535">\' +
                        f\'<span style="color:#94a3b8;font-size:0.82rem">{p["ticker"]}</span>\' +
                        f\'<span style="color:#64748b;font-size:0.78rem">Precio: {p["precio"]:,.2f}</span>\' +
                        f\'<span style="color:{color};font-family:monospace;font-size:0.82rem;font-weight:600">PnL: {p["pnl_pct"]:+.2f}%</span>\' +
                        f\'<span style="color:#475569;font-size:0.72rem">{p["dias"]} días</span></div>\',
                        unsafe_allow_html=True
                    )

            # Cierres ejecutados
            if resumen.get("cierres"):
                st.divider()
                st.markdown("**Cierres en esta sesión**")
                for c in resumen["cierres"]:
                    color = "#ef4444" if c["razon"] == "STOP LOSS" else "#22c55e"
                    st.markdown(
                        f\'<div style="background:{color}15;border:1px solid {color}33;border-radius:5px;padding:0.4rem 0.8rem;margin:0.2rem 0">\' +
                        f\'<span style="color:{color};font-weight:600">{c["razon"]}</span> — \' +
                        f\'<span style="color:#f1f5f9">{c["ticker"]}</span> | \' +
                        f\'<span style="color:{color}">PnL: {c["pnl_pct"]:+.2f}%</span>\' +
                        (f\' | ✅ Ejecutado\' if c.get("ejecutado") else f\' | ⚠️ {c.get("error","")}\') +
                        f\'</div>\',
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
            st.markdown("**Verificación:** Cada 5 minutos automáticamente")"""

content = content.replace(old_end, new_end)
print("✅ Tab cierres automáticos agregado")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
