"""
Módulo macro Chile completo.
Fuentes:
- mindicador.cl: UF, IVP, CLP/USD, Euro, IPC, UTM, IMACEC, TPM, Cobre, Desempleo, BTC
- Cochilco (scraping): Precio oficial cobre y litio
- Cálculos derivados: tendencias, alertas, contexto histórico
"""

import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

BASE_MINDICADOR = "https://mindicador.cl/api"

# ── INDICADORES DISPONIBLES ───────────────────────────────────────────────────
INDICADORES = {
    "uf":              {"nombre": "UF",                        "unidad": "CLP",    "icono": "💎", "frecuencia": "diaria"},
    "ivp":             {"nombre": "IVP",                       "unidad": "CLP",    "icono": "🏠", "frecuencia": "diaria"},
    "dolar":           {"nombre": "Dólar Observado",           "unidad": "CLP",    "icono": "💵", "frecuencia": "diaria"},
    "euro":            {"nombre": "Euro",                      "unidad": "CLP",    "icono": "💶", "frecuencia": "diaria"},
    "ipc":             {"nombre": "IPC mensual",               "unidad": "%",      "icono": "📈", "frecuencia": "mensual"},
    "utm":             {"nombre": "UTM",                       "unidad": "CLP",    "icono": "📋", "frecuencia": "mensual"},
    "imacec":          {"nombre": "IMACEC variación anual",    "unidad": "%",      "icono": "🏭", "frecuencia": "mensual"},
    "tpm":             {"nombre": "TPM",                       "unidad": "%",      "icono": "🏦", "frecuencia": "diaria"},
    "libra_cobre":     {"nombre": "Cobre (lb USD)",            "unidad": "USD/lb", "icono": "🔶", "frecuencia": "diaria"},
    "tasa_desempleo":  {"nombre": "Tasa de Desempleo",         "unidad": "%",      "icono": "👥", "frecuencia": "mensual"},
    "bitcoin":         {"nombre": "Bitcoin (CLP)",             "unidad": "CLP",    "icono": "₿",  "frecuencia": "diaria"},
}

# Umbrales de alerta
ALERTAS = {
    "tpm":            {"alto": 6.0,  "bajo": 3.0},
    "ipc":            {"alto": 0.5,  "muy_alto": 1.0},
    "tasa_desempleo": {"alto": 9.0,  "muy_alto": 11.0},
    "imacec":         {"bajo": -1.0, "muy_bajo": -3.0},
    "dolar":          {"alto": 950,  "muy_alto": 1000},
}

# ── OBTENER DATOS ─────────────────────────────────────────────────────────────
def get_indicador(indicador_id, dias_historico=30):
    """Obtiene valor actual e histórico de un indicador"""
    try:
        r = requests.get(f"{BASE_MINDICADOR}/{indicador_id}", timeout=8)
        data = r.json()
        serie = data.get("serie", [])

        if not serie:
            return None

        # Valor actual
        ultimo = serie[0]
        valor_actual = ultimo.get("valor")
        fecha_actual = ultimo.get("fecha", "")[:10]

        # Histórico
        historico = []
        for obs in serie[:dias_historico]:
            try:
                historico.append({
                    "fecha": obs["fecha"][:10],
                    "valor": obs["valor"],
                })
            except:
                continue

        # Variación vs período anterior
        variacion = None
        if len(serie) >= 2:
            anterior = serie[1].get("valor")
            if anterior and anterior != 0:
                variacion = round(((valor_actual - anterior) / abs(anterior)) * 100, 3)

        # Alerta
        alerta = _calcular_alerta(indicador_id, valor_actual)

        meta = INDICADORES.get(indicador_id, {})
        return {
            "id":           indicador_id,
            "nombre":       meta.get("nombre", indicador_id),
            "icono":        meta.get("icono", "📊"),
            "unidad":       meta.get("unidad", ""),
            "frecuencia":   meta.get("frecuencia", ""),
            "valor":        valor_actual,
            "fecha":        fecha_actual,
            "variacion":    variacion,
            "historico":    historico,
            "alerta":       alerta,
        }
    except Exception as e:
        print(f"Error {indicador_id}: {e}")
        return None

def _calcular_alerta(indicador_id, valor):
    """Determina si hay alerta para un indicador"""
    if indicador_id not in ALERTAS or valor is None:
        return None
    umbrales = ALERTAS[indicador_id]
    if "muy_alto" in umbrales and valor >= umbrales["muy_alto"]:
        return {"nivel": "CRÍTICO", "color": "#ef4444", "mensaje": f"{INDICADORES.get(indicador_id,{}).get('nombre',indicador_id)} en nivel muy alto"}
    if "alto" in umbrales and valor >= umbrales["alto"]:
        return {"nivel": "ALTO", "color": "#f59e0b", "mensaje": f"{INDICADORES.get(indicador_id,{}).get('nombre',indicador_id)} sobre umbral"}
    if "muy_bajo" in umbrales and valor <= umbrales["muy_bajo"]:
        return {"nivel": "CRÍTICO", "color": "#ef4444", "mensaje": f"{INDICADORES.get(indicador_id,{}).get('nombre',indicador_id)} en nivel muy bajo"}
    if "bajo" in umbrales and valor <= umbrales["bajo"]:
        return {"nivel": "BAJO", "color": "#f59e0b", "mensaje": f"{INDICADORES.get(indicador_id,{}).get('nombre',indicador_id)} bajo umbral"}
    return None

def get_macro_chile_completo():
    """Obtiene todos los indicadores macro Chile"""
    resultado = {}
    for ind_id in INDICADORES:
        dato = get_indicador(ind_id)
        if dato:
            resultado[ind_id] = dato
    return resultado

def get_resumen_macro():
    """Versión compacta para el header del dashboard"""
    ids_clave = ["dolar", "uf", "tpm", "ipc", "imacec", "libra_cobre", "tasa_desempleo"]
    resultado = {}
    for ind_id in ids_clave:
        dato = get_indicador(ind_id, dias_historico=5)
        if dato:
            resultado[ind_id] = dato
    return resultado

# ── COCHILCO ─────────────────────────────────────────────────────────────────
def get_precios_cochilco():
    """
    Obtiene precios oficiales de cobre y litio desde Cochilco.
    Usa scraping ligero del sitio web.
    """
    resultado = {}
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        r = requests.get(
            "https://www.cochilco.cl/mercado-de-metales/precio-de-metales.aspx",
            headers=headers, timeout=12
        )
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscar tablas con precios
        tablas = soup.find_all("table")
        for tabla in tablas:
            texto = tabla.get_text().lower()
            if "cobre" in texto or "litio" in texto:
                filas = tabla.find_all("tr")
                for fila in filas:
                    celdas = fila.find_all(["td", "th"])
                    if len(celdas) >= 2:
                        nombre = celdas[0].get_text(strip=True)
                        valor  = celdas[1].get_text(strip=True) if len(celdas) > 1 else ""
                        if nombre and valor and any(c.isdigit() for c in valor):
                            resultado[nombre] = valor
    except Exception as e:
        print(f"Error Cochilco: {e}")

    # Fallback: usar mindicador.cl para cobre
    if not resultado:
        try:
            cobre = get_indicador("libra_cobre")
            if cobre:
                resultado["Cobre (USD/lb) mindicador"] = f"{cobre['valor']}"
        except:
            pass

    return resultado

# ── ANÁLISIS MACRO ────────────────────────────────────────────────────────────
def get_contexto_macro():
    """
    Genera un análisis contextual del entorno macro Chile.
    Identifica el ciclo económico y señales para el mercado.
    """
    datos = get_resumen_macro()

    señales = []
    ciclo   = "NEUTRO"
    alertas = []

    tpm    = datos.get("tpm",    {}).get("valor")
    ipc    = datos.get("ipc",    {}).get("valor")
    imacec = datos.get("imacec", {}).get("valor")
    desemp = datos.get("tasa_desempleo", {}).get("valor")
    cobre  = datos.get("libra_cobre", {}).get("valor")
    dolar  = datos.get("dolar", {}).get("valor")

    # Ciclo económico
    if imacec is not None:
        if imacec >= 3:
            ciclo = "EXPANSIÓN"
            señales.append("✅ IMACEC en expansión → favorable para renta variable")
        elif imacec >= 0:
            ciclo = "MODERADO"
            señales.append("🟡 IMACEC moderado → cautela en renta variable")
        else:
            ciclo = "CONTRACCIÓN"
            señales.append("🔴 IMACEC negativo → riesgo recesión → defensivos y renta fija")

    # TPM y su impacto
    if tpm is not None:
        if tpm >= 5.5:
            señales.append(f"🔴 TPM alta ({tpm}%) → presión sobre valorizaciones → cuidado con growth")
        elif tpm <= 4.0:
            señales.append(f"🟢 TPM baja ({tpm}%) → favorable para renta variable y bonos")
        else:
            señales.append(f"🟡 TPM neutral ({tpm}%) → sin sesgo claro")

    # Inflación
    if ipc is not None:
        if ipc >= 0.8:
            señales.append(f"🔴 IPC alto ({ipc}%) → BCCh podría subir TPM → defensivo")
        elif ipc <= 0:
            señales.append(f"🟢 IPC deflacionario ({ipc}%) → espacio para bajar TPM → positivo")

    # Cobre
    if cobre is not None:
        if cobre >= 4.5:
            señales.append(f"🟢 Cobre fuerte (USD {cobre}/lb) → positivo para SQM, COPEC, Chile")
        elif cobre <= 3.5:
            señales.append(f"🔴 Cobre débil (USD {cobre}/lb) → presión sobre mineras y CLP")

    # Dólar
    if dolar is not None:
        if dolar >= 950:
            señales.append(f"🔴 CLP débil (${dolar}) → inflación importada, presión BCCh")
        elif dolar <= 850:
            señales.append(f"🟢 CLP fuerte (${dolar}) → positivo para importadores")

    # Alertas activas
    for ind_id, dato in datos.items():
        if dato and dato.get("alerta"):
            alertas.append(dato["alerta"])

    return {
        "ciclo":   ciclo,
        "señales": señales,
        "alertas": alertas,
        "datos":   datos,
    }

if __name__ == "__main__":
    print("=== MACRO CHILE COMPLETO ===\n")
    datos = get_macro_chile_completo()
    for ind_id, dato in datos.items():
        var_str = f" ({dato['variacion']:+.3f}%)" if dato.get("variacion") else ""
        alerta_str = f" ⚠️ {dato['alerta']['nivel']}" if dato.get("alerta") else ""
        print(f"{dato['icono']} {dato['nombre']}: {dato['valor']} {dato['unidad']} [{dato['fecha']}]{var_str}{alerta_str}")

    print("\n=== CONTEXTO MACRO ===")
    ctx = get_contexto_macro()
    print(f"Ciclo: {ctx['ciclo']}")
    for s in ctx["señales"]:
        print(f"  {s}")

    print("\n=== COCHILCO ===")
    cochilco = get_precios_cochilco()
    if cochilco:
        for k, v in cochilco.items():
            print(f"  {k}: {v}")
    else:
        print("  Sin datos disponibles")
