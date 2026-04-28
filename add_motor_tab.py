"""
Agrega panel de control del motor automático al tab Ejecución.
"""

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar imports
if "motor_automatico" not in content:
    content = content.replace(
        "from engine.cierre_automatico import verificar_posiciones, get_log_cierres",
        "from engine.cierre_automatico import verificar_posiciones, get_log_cierres\n"
        "from engine.motor_automatico import activar_motor, pausar_motor, get_resumen_motor, ciclo_trading_automatico, PARAMS"
    )
    print("✅ Import motor automático agregado")

# 2. Agregar verificación automática en cada refresh
old_session = '''# Verificación automática de SL/TP en cada refresh
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

new_session = '''# Motor automático — ejecutar ciclo si está activo
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
        pass'''

content = content.replace(old_session, new_session)
print("✅ Ciclo automático integrado en refresh")

# 3. Reemplazar tabs de ejecución para agregar tab Motor
old_tabs = '    sub_ib, sub_hist, sub_cierre = st.tabs(["IB Paper Trading", "Historial de Órdenes", "Cierres Automáticos"])'
new_tabs = '    sub_motor, sub_ib, sub_hist, sub_cierre = st.tabs(["Motor Automático", "IB Manual", "Historial", "Cierres"])'
content = content.replace(old_tabs, new_tabs)
print("✅ Tab Motor Automático agregado")

# 4. Insertar contenido del tab motor antes de sub_ib
old_ib_start = '''    with sub_ib:
        if not IB_DISPONIBLE:'''

new_motor_content = '''    with sub_motor:
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
                f\'<div style="display:flex;justify-content:space-between;padding:0.2rem 0;border-bottom:1px solid #1a2535">\' +
                f\'<span style="color:{color};font-size:0.82rem">{icon} {nombre}</span>\' +
                f\'<span style="color:#64748b;font-size:0.78rem">{detalle}</span></div>\',
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
                    f\'<div style="display:flex;justify-content:space-between;padding:0.15rem 0;border-bottom:1px solid #1a2535">\' +
                    f\'<span style="color:#64748b;font-size:0.75rem">{k.replace("_"," ").title()}</span>\' +
                    f\'<span style="color:#f1f5f9;font-family:monospace;font-size:0.75rem">{v}</span></div>\',
                    unsafe_allow_html=True
                )
        with col2:
            for k, v in params_list[mid:]:
                st.markdown(
                    f\'<div style="display:flex;justify-content:space-between;padding:0.15rem 0;border-bottom:1px solid #1a2535">\' +
                    f\'<span style="color:#64748b;font-size:0.75rem">{k.replace("_"," ").title()}</span>\' +
                    f\'<span style="color:#f1f5f9;font-family:monospace;font-size:0.75rem">{v}</span></div>\',
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
                    f\'<div style="display:flex;gap:1rem;padding:0.2rem 0;border-bottom:1px solid #1a2535;font-size:0.78rem">\' +
                    f\'<span style="color:#475569;width:130px">{entry.get("timestamp","")[:16]}</span>\' +
                    f\'<span style="color:{color};font-weight:600;width:80px">{tipo}</span>\' +
                    f\'<span style="color:#94a3b8">{entry.get("descripcion","")[:60]}</span></div>\',
                    unsafe_allow_html=True
                )
        else:
            st.caption("Sin actividad registrada aún.")

    with sub_ib:
        if not IB_DISPONIBLE:'''

content = content.replace(old_ib_start, new_motor_content)
print("✅ Panel motor automático insertado")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
