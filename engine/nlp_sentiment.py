"""
Módulo NLP — Análisis de sentiment de noticias financieras Chile.
Usa modelo BERT multilingüe (nlptown/bert-base-multilingual-uncased-sentiment)
para clasificar noticias en escala 1-5 estrellas → convertido a señal -1/0/+1.

Características:
- Corre localmente sin API key
- Soporte español nativo
- Cache de resultados para evitar re-procesar
- Integración con módulo de noticias existente
- Score de impacto por activo
"""

import os
import json
import hashlib
from datetime import datetime

# Cache de sentiments para evitar re-procesar
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sentiment_cache.json")

# Modelo NLP — carga lazy para no ralentizar el arranque
_modelo = None

def _get_modelo():
    """Carga el modelo NLP en memoria (lazy loading)"""
    global _modelo
    if _modelo is None:
        try:
            from transformers import pipeline
            _modelo = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment",
                truncation=True,
                max_length=512,
            )
        except Exception as e:
            print(f"Error cargando modelo NLP: {e}")
            _modelo = None
    return _modelo

# ── CACHE ─────────────────────────────────────────────────────────────────────
def _cargar_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def _guardar_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except:
        pass

def _hash_texto(texto):
    return hashlib.md5(texto.encode()).hexdigest()[:12]

# ── CONVERSIÓN ESTRELLAS → SEÑAL ──────────────────────────────────────────────
def _estrellas_a_señal(label, score):
    """
    Convierte rating 1-5 estrellas a señal de mercado.
    1-2 estrellas = NEGATIVO (-1)
    3 estrellas   = NEUTRO (0)
    4-5 estrellas = POSITIVO (+1)
    """
    try:
        estrellas = int(label.split()[0])
    except:
        return 0, "NEUTRO", "#64748b"

    if estrellas <= 2:
        return -1, "NEGATIVO", "#ef4444"
    elif estrellas == 3:
        return 0, "NEUTRO", "#64748b"
    else:
        return 1, "POSITIVO", "#22c55e"

# ── ANÁLISIS INDIVIDUAL ───────────────────────────────────────────────────────
def analizar_sentiment(texto, usar_cache=True):
    """
    Analiza el sentiment de un texto financiero en español.
    
    Returns:
        dict con señal (-1/0/1), tono, confianza, estrellas
    """
    if not texto or len(texto.strip()) < 10:
        return {"señal": 0, "tono": "NEUTRO", "color": "#64748b", "confianza": 0, "estrellas": 3}

    # Verificar cache
    cache = _cargar_cache()
    key = _hash_texto(texto[:200])
    if usar_cache and key in cache:
        return cache[key]

    # Fallback si el modelo no está disponible
    modelo = _get_modelo()
    if modelo is None:
        resultado = _sentiment_keywords(texto)
    else:
        try:
            res = modelo(texto[:512])[0]
            señal, tono, color = _estrellas_a_señal(res["label"], res["score"])
            resultado = {
                "señal":      señal,
                "tono":       tono,
                "color":      color,
                "confianza":  round(res["score"], 3),
                "estrellas":  int(res["label"].split()[0]),
                "metodo":     "BERT",
            }
        except Exception as e:
            resultado = _sentiment_keywords(texto)

    # Guardar en cache
    cache[key] = resultado
    _guardar_cache(cache)
    return resultado

def _sentiment_keywords(texto):
    """
    Fallback: análisis por keywords financieros en español.
    Se usa si el modelo BERT no está disponible.
    """
    POSITIVOS = [
        "sube", "alza", "gana", "récord", "record", "expansión", "crecimiento",
        "supera", "mejora", "positivo", "favorable", "fuerte", "impulsa",
        "recupera", "aumenta", "beneficio", "utilidad", "dividendo", "acuerdo",
        "inversión", "producción récord", "contrato", "nuevo proyecto",
        "resultados positivos", "mayor demanda", "precio alto",
    ]
    NEGATIVOS = [
        "baja", "cae", "pierde", "pérdida", "contracción", "recesión",
        "huelga", "conflicto", "riesgo", "presión", "débil", "crisis",
        "disminuye", "reducción", "cierre", "quiebra", "multa", "demanda",
        "accidente", "catástrofe", "caída", "déficit", "deuda", "escándalo",
        "investigación", "fraude", "suspensión",
    ]

    t = texto.lower()
    pos = sum(1 for k in POSITIVOS if k in t)
    neg = sum(1 for k in NEGATIVOS if k in t)
    total = pos + neg

    if total == 0:
        return {"señal": 0, "tono": "NEUTRO", "color": "#64748b", "confianza": 0.5, "estrellas": 3, "metodo": "keywords"}

    ratio = pos / total
    if ratio >= 0.6:
        return {"señal": 1, "tono": "POSITIVO", "color": "#22c55e", "confianza": round(ratio, 2), "estrellas": 4, "metodo": "keywords"}
    elif ratio <= 0.4:
        return {"señal": -1, "tono": "NEGATIVO", "color": "#ef4444", "confianza": round(1-ratio, 2), "estrellas": 2, "metodo": "keywords"}
    else:
        return {"señal": 0, "tono": "NEUTRO", "color": "#64748b", "confianza": 0.5, "estrellas": 3, "metodo": "keywords"}

# ── ANÁLISIS BATCH ────────────────────────────────────────────────────────────
def analizar_noticias_batch(noticias):
    """
    Analiza sentiment de una lista de noticias.
    Agrega campo 'sentiment' a cada noticia.
    
    Args:
        noticias: lista de dicts con campo 'titulo'
    Returns:
        lista con campo 'sentiment' agregado
    """
    resultado = []
    for n in noticias:
        titulo = n.get("titulo", "")
        sent = analizar_sentiment(titulo)
        n_nuevo = dict(n)
        n_nuevo["sentiment"] = sent
        # Score combinado: score original + boost sentiment
        score_base = n.get("score", 0)
        boost = sent["señal"] * 2  # +2 positivo, -2 negativo, 0 neutro
        n_nuevo["score_sentiment"] = score_base + boost
        resultado.append(n_nuevo)

    return sorted(resultado, key=lambda x: abs(x.get("score_sentiment", 0)), reverse=True)

# ── RESUMEN SENTIMENT ─────────────────────────────────────────────────────────
def get_resumen_sentiment(noticias_con_sentiment):
    """
    Genera resumen estadístico del sentiment del mercado.
    """
    if not noticias_con_sentiment:
        return {}

    positivas  = [n for n in noticias_con_sentiment if n.get("sentiment", {}).get("señal", 0) > 0]
    negativas  = [n for n in noticias_con_sentiment if n.get("sentiment", {}).get("señal", 0) < 0]
    neutras    = [n for n in noticias_con_sentiment if n.get("sentiment", {}).get("señal", 0) == 0]
    total      = len(noticias_con_sentiment)

    ratio_positivo = len(positivas) / total if total > 0 else 0

    if ratio_positivo >= 0.6:
        sesgo = "ALCISTA"
        sesgo_color = "#22c55e"
    elif ratio_positivo <= 0.4:
        sesgo = "BAJISTA"
        sesgo_color = "#ef4444"
    else:
        sesgo = "NEUTRO"
        sesgo_color = "#64748b"

    return {
        "total":          total,
        "positivas":      len(positivas),
        "negativas":      len(negativas),
        "neutras":        len(neutras),
        "ratio_positivo": round(ratio_positivo * 100, 1),
        "sesgo":          sesgo,
        "sesgo_color":    sesgo_color,
        "top_positiva":   positivas[0]["titulo"][:80] if positivas else None,
        "top_negativa":   negativas[0]["titulo"][:80] if negativas else None,
        "timestamp":      datetime.now().isoformat(),
    }

# ── IMPACTO POR ACTIVO ────────────────────────────────────────────────────────
ACTIVO_KEYWORDS = {
    "SQM.SN":    ["sqm", "litio", "lithium", "salar"],
    "ECH":       ["ipsa", "bolsa santiago", "mercado chileno", "chile"],
    "COPEC.SN":  ["copec", "energía", "combustible", "bencina"],
    "BCI.SN":    ["bci", "banco bci"],
    "CHILE.SN":  ["banco de chile", "bancodechile"],
    "CMPC.SN":   ["cmpc", "celulosa", "papel"],
    "FALABELLA.SN": ["falabella", "retail", "consumo"],
    "LTM.SN":    ["latam", "aerolínea", "aviación"],
    "CLP/USD":   ["dólar", "tipo de cambio", "peso chileno", "clp"],
}

def get_sentiment_por_activo(noticias_con_sentiment):
    """
    Calcula sentiment agregado por activo basado en noticias relevantes.
    """
    resultado = {}
    for activo, keywords in ACTIVO_KEYWORDS.items():
        noticias_activo = []
        for n in noticias_con_sentiment:
            titulo = n.get("titulo", "").lower()
            if any(k in titulo for k in keywords):
                noticias_activo.append(n)

        if not noticias_activo:
            continue

        señales = [n.get("sentiment", {}).get("señal", 0) for n in noticias_activo]
        avg_señal = sum(señales) / len(señales)

        resultado[activo] = {
            "n_noticias":  len(noticias_activo),
            "señal_avg":   round(avg_señal, 2),
            "tono":        "POSITIVO" if avg_señal > 0.2 else ("NEGATIVO" if avg_señal < -0.2 else "NEUTRO"),
            "color":       "#22c55e" if avg_señal > 0.2 else ("#ef4444" if avg_señal < -0.2 else "#64748b"),
            "noticias":    noticias_activo[:3],
        }

    return resultado

if __name__ == "__main__":
    print("=== TEST NLP SENTIMENT ===\n")

    textos = [
        "SQM sube con fuerza impulsada por menor oferta de litio en mercado global",
        "Codelco reporta caída en producción y pérdidas récord en primer trimestre",
        "Banco Central mantiene tasa de política monetaria en 4.5%",
        "Huelga en mina Escondida amenaza producción de cobre en Chile",
        "IPSA alcanza máximo histórico impulsado por mineras y bancos",
        "LATAM Airlines anuncia cierre de rutas y reducción de personal",
    ]

    print("Analizando con modelo BERT...")
    for texto in textos:
        s = analizar_sentiment(texto)
        icono = "🟢" if s["señal"] > 0 else ("🔴" if s["señal"] < 0 else "⚪")
        print(f"{icono} [{s['tono']}] {s['estrellas']}⭐ conf:{s['confianza']:.2f} — {texto[:60]}")
