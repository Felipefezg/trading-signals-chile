"""
Script para integrar Fear & Greed, CMF y Volumen Anormal
en el motor de recomendaciones como fuentes de señal.
"""

dashboard_path = "engine/recomendaciones.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Modificar consolidar_señales para aceptar nuevas fuentes
old_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list):"
new_def = "def consolidar_señales(poly_df, kalshi_list, macro_list, noticias_list, fear_greed=None, cmf_hechos=None, vol_alertas=None):"
content = content.replace(old_def, new_def)

# 2. Agregar procesamiento de nuevas fuentes al final de consolidar_señales
old_return_activos = "    return activos"
new_sources = '''
    # Fear & Greed — ajusta peso global de señales
    if fear_greed:
        fg_score  = fear_greed.get("score", 50)
        fg_mult   = fear_greed.get("multiplicador", 1.0)
        fg_señal  = fear_greed.get("señal_trading", "NEUTRO")
        # Si Fear & Greed indica compra/venta, refuerza señales alineadas
        for activo in activos:
            if fg_señal == "COMPRAR" and fg_score <= 45:
                activos[activo]["alza"] *= fg_mult
                activos[activo]["fuentes"].append("Fear&Greed")
                activos[activo]["evidencia"].append({
                    "fuente": "Fear&Greed", "señal": f"Miedo ({fg_score}/100) → oportunidad compra contrarian",
                    "prob": None, "direccion": "ALZA", "peso": round(fg_mult - 1, 2),
                })
            elif fg_señal == "VENDER" and fg_score >= 55:
                activos[activo]["baja"] *= fg_mult
                activos[activo]["fuentes"].append("Fear&Greed")
                activos[activo]["evidencia"].append({
                    "fuente": "Fear&Greed", "señal": f"Codicia ({fg_score}/100) → reducir exposición",
                    "prob": None, "direccion": "BAJA", "peso": round(fg_mult - 1, 2),
                })

    # CMF Hechos Esenciales — señales de alta convicción por empresa IPSA
    CMF_TICKER_MAP = {
        "SQM": "SQM.SN", "COPEC": "COPEC.SN", "FALABELLA": "COPEC.SN",
        "BCI": "ECH", "SANTANDER": "ECH", "CHILE": "ECH",
        "CMPC": "ECH", "LATAM": "ECH", "VAPORES": "ECH",
        "CAP": "ECH", "COLBUN": "ECH", "ENELCHILE": "ECH",
    }
    for hecho in (cmf_hechos or []):
        ticker_ipsa = hecho.get("ticker_ipsa")
        if not ticker_ipsa:
            continue
        activo_map = CMF_TICKER_MAP.get(ticker_ipsa, "ECH")
        if activo_map not in activos:
            activos[activo_map] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        relevancia = hecho.get("relevancia", "BAJA")
        impacto    = hecho.get("impacto", "NEUTRO")
        peso_cmf   = {"ALTA": 2.0, "MEDIA": 1.0, "BAJA": 0.3}.get(relevancia, 0.3)
        if impacto == "POSITIVO":
            activos[activo_map]["alza"] += peso_cmf
            direccion_cmf = "ALZA"
        elif impacto == "NEGATIVO":
            activos[activo_map]["baja"] += peso_cmf
            direccion_cmf = "BAJA"
        else:
            continue
        activos[activo_map]["fuentes"].append("CMF")
        activos[activo_map]["evidencia"].append({
            "fuente": "CMF", "señal": f"{ticker_ipsa}: {hecho.get('materia','')[:60]}",
            "prob": None, "direccion": direccion_cmf, "peso": peso_cmf,
        })

    # Volumen Anormal — confirma señales existentes o genera nuevas
    VOL_TICKER_MAP = {
        "SQM-B.SN": "SQM.SN", "COPEC.SN": "COPEC.SN",
        "BCI.SN": "ECH", "CHILE.SN": "ECH", "BSANTANDER.SN": "ECH",
        "FALABELLA.SN": "ECH", "CENCOSUD.SN": "ECH",
        "ECH": "ECH", "SQM": "SQM.SN",
    }
    for alerta in (vol_alertas or []):
        if alerta.get("nivel") not in ("ALTA", "MEDIA"):
            continue
        ticker_vol = alerta.get("ticker", "")
        activo_map = VOL_TICKER_MAP.get(ticker_vol, "ECH")
        if activo_map not in activos:
            activos[activo_map] = {"alza": 0, "baja": 0, "fuentes": [], "evidencia": []}
        señal_vol  = alerta.get("señal", "NORMAL")
        ratio      = alerta.get("ratio", 1.0)
        peso_vol   = min((ratio - 1.5) * 0.5, 2.0)  # peso proporcional al ratio
        if señal_vol == "ACUMULACIÓN":
            activos[activo_map]["alza"] += peso_vol
            direccion_vol = "ALZA"
        elif señal_vol == "DISTRIBUCIÓN":
            activos[activo_map]["baja"] += peso_vol
            direccion_vol = "BAJA"
        else:
            continue
        # Extra convicción si hay CMF correlacionado
        if alerta.get("conviccion_extra"):
            activos[activo_map]["alza" if direccion_vol == "ALZA" else "baja"] += 1.0
        activos[activo_map]["fuentes"].append("Volumen")
        activos[activo_map]["evidencia"].append({
            "fuente": "Volumen", "señal": f"{alerta.get('nombre',ticker_vol)}: {ratio:.1f}x promedio — {señal_vol}",
            "prob": None, "direccion": direccion_vol, "peso": round(peso_vol, 2),
        })

    return activos
'''

content = content.replace(old_return_activos, new_sources)
print("✅ Nuevas fuentes integradas en consolidar_señales")

# 3. Actualizar tesis para incluir nuevas fuentes
old_tesis = '''    poly_ev  = [e for e in evidencia if e["fuente"] == "Polymarket"]
    kalshi_ev = [e for e in evidencia if e["fuente"] == "Kalshi"]
    macro_ev = [e for e in evidencia if e["fuente"] == "Macro USA"]
    partes = []
    if poly_ev:
        partes.append(f"Polymarket señala {poly_ev[0]['direccion'].lower()} ({poly_ev[0].get('prob','?')}%)")
    if kalshi_ev:
        partes.append(f"Kalshi confirma {kalshi_ev[0]['direccion'].lower()}")
    if macro_ev:
        partes.append(macro_ev[0]["señal"][:60])
    if partes:
        return f"{accion} {activo}: " + " | ".join(partes[:2])
    return f"{accion} {activo} basado en {', '.join(fuentes)}"'''

new_tesis = '''    poly_ev  = [e for e in evidencia if e["fuente"] == "Polymarket"]
    kalshi_ev = [e for e in evidencia if e["fuente"] == "Kalshi"]
    macro_ev  = [e for e in evidencia if e["fuente"] == "Macro USA"]
    cmf_ev    = [e for e in evidencia if e["fuente"] == "CMF"]
    vol_ev    = [e for e in evidencia if e["fuente"] == "Volumen"]
    fg_ev     = [e for e in evidencia if e["fuente"] == "Fear&Greed"]
    partes = []
    if poly_ev:
        partes.append(f"Polymarket señala {poly_ev[0]['direccion'].lower()} ({poly_ev[0].get('prob','?')}%)")
    if kalshi_ev:
        partes.append(f"Kalshi confirma {kalshi_ev[0]['direccion'].lower()}")
    if macro_ev:
        partes.append(macro_ev[0]["señal"][:50])
    if cmf_ev:
        partes.append(f"CMF: {cmf_ev[0]['señal'][:50]}")
    if vol_ev:
        partes.append(f"Volumen: {vol_ev[0]['señal'][:40]}")
    if fg_ev:
        partes.append(fg_ev[0]["señal"][:40])
    if partes:
        return f"{accion} {activo}: " + " | ".join(partes[:3])
    return f"{accion} {activo} basado en {', '.join(fuentes)}"'''

content = content.replace(old_tesis, new_tesis)
print("✅ Tesis actualizada con nuevas fuentes")

with open(dashboard_path, "w") as f:
    f.write(content)
print("✅ Motor de recomendaciones actualizado")
