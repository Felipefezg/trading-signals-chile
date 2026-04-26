import yfinance as yf

# Indicadores macro USA y su impacto en Chile
MACRO_USA = {
    "^VIX":     {"nombre": "VIX (Volatilidad)",  "impacto_chile": ["ECH", "CLP/USD"], "inverso": True},
    "^TNX":     {"nombre": "Treasury 10Y (%)",   "impacto_chile": ["CLP/USD", "ECH"], "inverso": True},
    "DX-Y.NYB": {"nombre": "DXY (Dólar Index)",  "impacto_chile": ["CLP/USD", "SQM.SN"], "inverso": True},
    "GC=F":     {"nombre": "Oro (USD/oz)",        "impacto_chile": ["CLP/USD"], "inverso": False},
    "CL=F":     {"nombre": "Petróleo WTI",        "impacto_chile": ["COPEC.SN", "ECH"], "inverso": False},
    "HG=F":     {"nombre": "Cobre LME (USD/lb)",  "impacto_chile": ["SQM.SN", "COPEC.SN", "ECH"], "inverso": False},
    "^GSPC":    {"nombre": "S&P 500",             "impacto_chile": ["ECH", "SQM.SN"], "inverso": False},
}

# Umbrales para alertas
ALERTAS = {
    "^VIX":     {"alto": 25, "muy_alto": 35},
    "^TNX":     {"alto": 4.5, "muy_alto": 5.0},
    "DX-Y.NYB": {"alto": 105, "muy_alto": 110},
    "HG=F":     {"bajo": 3.5, "muy_bajo": 3.0},
}

def get_macro_usa():
    """Obtiene indicadores macro USA con cambio % y señal de impacto Chile"""
    resultado = []
    for ticker, meta in MACRO_USA.items():
        try:
            t = yf.Ticker(ticker)
            h = t.history(period="5d")
            if len(h) < 2:
                continue
            precio = round(h["Close"].iloc[-1], 2)
            cambio = round(((h["Close"].iloc[-1] / h["Close"].iloc[-2]) - 1) * 100, 2)

            # Señal de impacto en Chile
            if meta["inverso"]:
                impacto_dir = "NEGATIVO para Chile" if cambio > 0 else "POSITIVO para Chile"
            else:
                impacto_dir = "POSITIVO para Chile" if cambio > 0 else "NEGATIVO para Chile"

            # Alerta si corresponde
            alerta = None
            if ticker in ALERTAS:
                umbrales = ALERTAS[ticker]
                if "muy_alto" in umbrales and precio >= umbrales["muy_alto"]:
                    alerta = "🚨 NIVEL CRÍTICO"
                elif "alto" in umbrales and precio >= umbrales["alto"]:
                    alerta = "⚠️ NIVEL ALTO"
                elif "muy_bajo" in umbrales and precio <= umbrales["muy_bajo"]:
                    alerta = "🚨 NIVEL CRÍTICO"
                elif "bajo" in umbrales and precio <= umbrales["bajo"]:
                    alerta = "⚠️ NIVEL BAJO"

            resultado.append({
                "ticker": ticker,
                "nombre": meta["nombre"],
                "precio": precio,
                "cambio_pct": cambio,
                "impacto_chile": meta["impacto_chile"],
                "impacto_dir": impacto_dir,
                "alerta": alerta,
                "inverso": meta["inverso"],
            })
        except Exception as e:
            print(f"Error macro USA [{ticker}]: {e}")

    return resultado

def get_correlaciones_chile(macro_data):
    """
    Genera análisis de correlaciones entre macro USA y activos Chile.
    Retorna lista de señales con tesis de impacto.
    """
    señales = []
    for m in macro_data:
        cambio = m["cambio_pct"]
        if abs(cambio) < 0.3:  # Filtrar movimientos insignificantes
            continue

        for activo in m["impacto_chile"]:
            if m["inverso"]:
                dir_activo = "BAJA" if cambio > 0 else "ALZA"
            else:
                dir_activo = "ALZA" if cambio > 0 else "BAJA"

            magnitud = abs(cambio)
            score = round(magnitud * (2 if m["alerta"] else 1), 2)

            tesis = _generar_tesis(m["nombre"], cambio, activo, dir_activo)

            señales.append({
                "indicador": m["nombre"],
                "cambio_pct": cambio,
                "activo_chile": activo,
                "direccion": dir_activo,
                "score": score,
                "alerta": m["alerta"],
                "tesis": tesis,
            })

    return sorted(señales, key=lambda x: x["score"], reverse=True)

def _generar_tesis(indicador, cambio, activo, direccion):
    """Genera tesis de impacto legible"""
    dir_str = f"sube {cambio:+.1f}%" if cambio > 0 else f"baja {cambio:.1f}%"
    tesis_map = {
        "VIX": f"Volatilidad {dir_str} → flight-to-quality → {activo} {direccion}",
        "Treasury": f"Tasa 10Y {dir_str} → costo capital → {activo} {direccion}",
        "DXY": f"Dólar {dir_str} → commodities en USD → {activo} {direccion}",
        "Oro": f"Oro {dir_str} → apetito riesgo → {activo} {direccion}",
        "Petróleo": f"Petróleo {dir_str} → costos energía → {activo} {direccion}",
        "Cobre": f"Cobre LME {dir_str} → correlación directa → {activo} {direccion}",
        "S&P": f"SP500 {dir_str} → correlación global → {activo} {direccion}",
    }
    for kw, tesis in tesis_map.items():
        if kw.lower() in indicador.lower():
            return tesis
    return f"{indicador} {dir_str} → {activo} {direccion}"

if __name__ == "__main__":
    print("=== MACRO USA ===")
    datos = get_macro_usa()
    for d in datos:
        alerta = f" {d['alerta']}" if d["alerta"] else ""
        print(f"{d['nombre']}: {d['precio']} ({d['cambio_pct']:+.2f}%) — {d['impacto_dir']}{alerta}")

    print("\n=== CORRELACIONES CHILE ===")
    corr = get_correlaciones_chile(datos)
    for c in corr[:5]:
        print(f"[Score:{c['score']}] {c['tesis']}")
