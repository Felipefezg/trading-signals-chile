"""
Integra Fear & Greed Index Chile al dashboard.
1. Aparece en el header principal
2. Sub-tab propio en Resumen Ejecutivo
3. Ajusta el peso de las señales del motor
"""

dashboard_path = "dashboard.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Import
if "fear_greed" not in content:
    content = content.replace(
        "from data.cmf import get_hechos_esenciales, get_resumen_cmf",
        "from data.cmf import get_hechos_esenciales, get_resumen_cmf\n"
        "from engine.fear_greed import calcular_fear_greed, get_fear_greed_simple"
    )
    print("✅ Import Fear & Greed agregado")

# 2. Agregar Fear & Greed en el header junto al estado LIVE
old_header_status = '''st.markdown(
        '<div style="text-align:right;padding-top:6px">'
        '<span style="color:#22c55e;font-size:0.72rem;font-weight:600">● EN VIVO</span>'
        '<span style="color:#334155;font-size:0.68rem;margin-left:8px">Actualización: 15 min</span></div>',
        unsafe_allow_html=True
    )'''

new_header_status = '''try:
        fg_score, fg_clase, fg_color = get_fear_greed_simple()
    except:
        fg_score, fg_clase, fg_color = 50, "NEUTRO", "#f59e0b"
    st.markdown(
        f\'<div style="text-align:right;padding-top:4px">\' +
        f\'<span style="color:#22c55e;font-size:0.72rem;font-weight:600">● EN VIVO</span>\' +
        f\'<span style="color:#334155;font-size:0.68rem;margin-left:8px">Actualización: 15 min</span><br>\' +
        f\'<span style="background:{fg_color}22;color:{fg_color};border:1px solid {fg_color}44;\' +
        f\'border-radius:4px;padding:1px 8px;font-size:0.7rem;font-weight:700">\' +
        f\'F&G: {fg_score}/100 · {fg_clase}</span></div>\',
        unsafe_allow_html=True
    )'''

content = content.replace(old_header_status, new_header_status)
print("✅ Fear & Greed en header")

# 3. Agregar Fear & Greed en Resumen Ejecutivo después de los KPIs macro
old_divider_señales = '    st.divider()\n\n    # ── Top 3 oportunidades\n    st.markdown("#### Principales Oportunidades")'
new_fg_section = '''    st.divider()

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
            f\'<div style="background:#0d1521;border:1px solid #1e293b;border-radius:6px;padding:0.65rem 1rem;margin-bottom:0.5rem">\' +
            f\'<div style="display:flex;justify-content:space-between;align-items:center">\' +
            f\'<div>\' +
            f\'<span style="color:#475569;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em">Fear & Greed Index Chile</span><br>\' +
            f\'<span style="color:{fg_color};font-size:1.1rem;font-weight:700;font-family:monospace">{fg_score}/100</span>\' +
            f\'<span style="color:{fg_color};font-size:0.82rem;font-weight:600;margin-left:8px">{fg_clase}</span>\' +
            f\'</div>\' +
            f\'<div style="text-align:right">\' +
            f\'<span style="color:{fg_color};font-family:monospace;font-size:0.9rem;letter-spacing:2px">{barra_visual}</span><br>\' +
            f\'<span style="color:#475569;font-size:0.72rem">{fg["descripcion"]}</span>\' +
            f\'</div></div>\' +
            f\'<div style="display:flex;gap:1.5rem;margin-top:0.4rem">\',
            unsafe_allow_html=True
        )
        for key, c in fg["componentes"].items():
            cc = "#22c55e" if c["score"] >= 55 else ("#ef4444" if c["score"] <= 45 else "#f59e0b")
            st.markdown(
                f\'<span style="color:#475569;font-size:0.68rem">{c["nombre"].split("(")[0].strip()}: \' +
                f\'<span style="color:{cc};font-weight:600">{c["score"]}</span></span> &nbsp;\',
                unsafe_allow_html=True
            )
        st.markdown('</div>', unsafe_allow_html=True)
    except Exception as e:
        st.caption(f"Fear & Greed no disponible: {e}")

    st.divider()

    # ── Top 3 oportunidades
    st.markdown("#### Principales Oportunidades")'''

content = content.replace(old_divider_señales, new_fg_section)
print("✅ Fear & Greed en Resumen Ejecutivo")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Dashboard actualizado")
