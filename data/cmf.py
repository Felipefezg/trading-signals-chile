"""
Módulo CMF — Hechos Esenciales del Mercado de Valores Chile.
Fuente: cmfchile.cl — actualización cada 1 minuto.

Provee:
- Hechos esenciales de los últimos 7 días
- Filtrado por empresas del IPSA
- Clasificación por relevancia e impacto
- Análisis de materias relevantes para trading
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

CMF_URL       = "https://www.cmfchile.cl/institucional/hechos/hechos_portada.php"
CMF_HEADERS   = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
CMF_TIMEOUT   = 12

# Empresas IPSA con sus nombres en CMF
EMPRESAS_IPSA = {
    "SQM":          ["SOCIEDAD QUIMICA Y MINERA", "SQM"],
    "COPEC":        ["EMPRESAS COPEC", "COPEC"],
    "FALABELLA":    ["S.A.C.I. FALABELLA", "FALABELLA"],
    "BCI":          ["BANCO DE CREDITO E INVERSIONES", "BCI"],
    "SANTANDER":    ["BANCO SANTANDER", "SANTANDER-CHILE"],
    "CHILE":        ["BANCO DE CHILE"],
    "ITAU":         ["ITAU CORPBANCA", "ITAUCORPBANCA"],
    "CMPC":         ["EMPRESAS CMPC", "CMPC"],
    "COLBUN":       ["COLBUN"],
    "ENELCHILE":    ["ENEL CHILE"],
    "ENELAM":       ["ENEL AMERICAS"],
    "ENTEL":        ["EMPRESA NACIONAL DE TELECOMUNICACIONES", "ENTEL"],
    "CENCOSUD":     ["CENCOSUD"],
    "CCU":          ["COMPAÑIA DE CERVECERIAS UNIDAS", "CCU"],
    "LATAM":        ["LATAM AIRLINES", "LAN CHILE"],
    "CAP":          ["CAP S.A.", "COMPAÑIA DE ACERO"],
    "PARAUCO":      ["PARQUE ARAUCO"],
    "MALLPLAZA":    ["MALL PLAZA"],
    "ANDINA":       ["EMBOTELLADORA ANDINA"],
    "AGUAS":        ["AGUAS ANDINAS"],
    "ILC":          ["INVERSIONES LA CONSTRUCCION", "ILC"],
    "VAPORES":      ["COMPAÑIA SUD AMERICANA DE VAPORES", "CSAV"],
    "RIPLEY":       ["RIPLEY"],
    "HITES":        ["EMPRESAS HITES"],
    "CONCHATORO":   ["VINA CONCHA Y TORO"],
    "ECL":          ["ECL"],
    "FORUS":        ["FORUS"],
    "SMU":          ["SMU S.A."],
}

# Materias de alta relevancia para trading
MATERIAS_BAJA_RELEVANCIA = [
    "junta ordinaria", "junta extraordinaria", "citaciones",
    "junta de accionistas",
]

MATERIAS_ALTA_RELEVANCIA = [
    "fusión", "adquisición", "compra", "venta de activos",
    "acuerdo", "contrato relevante", "resultado", "utilidad",
    "pérdida", "dividendo", "recompra de acciones",
    "aumento de capital", "reducción de capital",
    "cambio de controlador", "oferta pública de adquisición",
    "opa", "litigio relevante", "multa", "sanción",
    "huelga", "paralización", "accidente grave",
    "cambio en clasificación de riesgo",
    "inversión relevante", "proyecto nuevo",
]

MATERIAS_MEDIA_RELEVANCIA = [
    "cambios en la administración", "junta extraordinaria",
    "nombramiento", "renuncia", "política de dividendos",
    "emisión de bonos", "colocación de acciones",
    "refinanciamiento", "reestructuración de deuda",
]

def _clasificar_relevancia(materia_texto):
    """Clasifica la relevancia de un hecho esencial"""
    texto = materia_texto.lower()
    for m in MATERIAS_BAJA_RELEVANCIA:
        if m in texto:
            return "BAJA", "#475569"
    for m in MATERIAS_ALTA_RELEVANCIA:
        if m in texto:
            return "ALTA", "#ef4444"
    for m in MATERIAS_MEDIA_RELEVANCIA:
        if m in texto:
            return "MEDIA", "#f59e0b"
    return "BAJA", "#475569"

def _identificar_empresa_ipsa(entidad_texto):
    """Identifica si la entidad es del IPSA y retorna el ticker"""
    texto = entidad_texto.upper()
    for ticker, nombres in EMPRESAS_IPSA.items():
        for nombre in nombres:
            if nombre.upper() in texto:
                return ticker
    return None

def _clasificar_impacto(materia_texto, ticker):
    """Determina el impacto potencial en el precio"""
    texto = materia_texto.lower()
    impacto_positivo = ["dividendo", "acuerdo", "contrato", "inversión", "proyecto", "utilidad", "compra"]
    impacto_negativo = ["pérdida", "multa", "sanción", "huelga", "paralización", "accidente", "litigio"]

    for p in impacto_positivo:
        if p in texto:
            return "POSITIVO", "↑"
    for n in impacto_negativo:
        if n in texto:
            return "NEGATIVO", "↓"
    return "NEUTRO", "→"

def get_hechos_esenciales(solo_ipsa=False, limit=50):
    """
    Obtiene hechos esenciales de los últimos 7 días desde CMF.

    Args:
        solo_ipsa: Si True, retorna solo hechos de empresas del IPSA
        limit: Número máximo de hechos a retornar

    Returns:
        Lista de dicts con hechos esenciales
    """
    try:
        r = requests.get(CMF_URL, headers=CMF_HEADERS, timeout=CMF_TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        tabla = soup.find("table")
        if not tabla:
            return []

        hechos = []
        filas  = tabla.find_all("tr")

        for fila in filas[3:]:  # Saltar headers
            celdas = fila.find_all("td")
            if len(celdas) < 4:
                continue

            fecha   = celdas[0].get_text(strip=True)
            numero  = celdas[1].get_text(strip=True)
            entidad = celdas[2].get_text(strip=True)
            materia = celdas[3].get_text(strip=True)

            if not fecha or not entidad:
                continue

            # Obtener URL del documento
            link = celdas[1].find("a")
            url_doc = link.get("href", "") if link else ""
            if url_doc and not url_doc.startswith("http"):
                url_doc = "https://www.cmfchile.cl" + url_doc

            # Identificar empresa IPSA
            ticker_ipsa = _identificar_empresa_ipsa(entidad)

            if solo_ipsa and not ticker_ipsa:
                continue

            # Clasificar relevancia e impacto
            relevancia, color_rel = _clasificar_relevancia(materia)
            impacto, flecha = _clasificar_impacto(materia, ticker_ipsa)

            hechos.append({
                "fecha":        fecha,
                "numero":       numero,
                "entidad":      entidad,
                "materia":      materia,
                "url":          url_doc,
                "ticker_ipsa":  ticker_ipsa,
                "es_ipsa":      ticker_ipsa is not None,
                "relevancia":   relevancia,
                "color":        color_rel,
                "impacto":      impacto,
                "flecha":       flecha,
            })

            if len(hechos) >= limit:
                break

        return hechos

    except Exception as e:
        print(f"Error CMF: {e}")
        return []

def get_hechos_ipsa(limit=20):
    """Retorna solo hechos esenciales de empresas del IPSA"""
    return get_hechos_esenciales(solo_ipsa=True, limit=limit)

def get_resumen_cmf():
    """Resumen ejecutivo de hechos esenciales para el dashboard"""
    hechos = get_hechos_esenciales(limit=100)

    total       = len(hechos)
    ipsa        = [h for h in hechos if h["es_ipsa"]]
    alta_rel    = [h for h in hechos if h["relevancia"] == "ALTA"]
    ipsa_alta   = [h for h in ipsa if h["relevancia"] == "ALTA"]

    return {
        "timestamp":        datetime.now().isoformat(),
        "total":            total,
        "ipsa":             len(ipsa),
        "alta_relevancia":  len(alta_rel),
        "ipsa_alta":        len(ipsa_alta),
        "hechos_ipsa":      ipsa[:10],
        "hechos_alta":      alta_rel[:5],
        "hechos_recientes": hechos[:5],
    }

if __name__ == "__main__":
    print("=== CMF HECHOS ESENCIALES ===\n")
    resumen = get_resumen_cmf()

    print(f"Total últimos 7 días: {resumen['total']}")
    print(f"Empresas IPSA:        {resumen['ipsa']}")
    print(f"Alta relevancia:      {resumen['alta_relevancia']}")
    print(f"IPSA + Alta rel.:     {resumen['ipsa_alta']}")

    print("\n--- EMPRESAS IPSA ---")
    for h in resumen["hechos_ipsa"]:
        print(f"[{h['relevancia']}] {h['flecha']} {h['ticker_ipsa']} — {h['materia'][:60]}")
        print(f"  {h['fecha']} | {h['entidad'][:50]}")

    print("\n--- ALTA RELEVANCIA ---")
    for h in resumen["hechos_alta"]:
        icon = "🏢" if h["es_ipsa"] else "📋"
        print(f"{icon} {h['entidad'][:45]} | {h['materia'][:55]}")
        print(f"  {h['fecha']}")
