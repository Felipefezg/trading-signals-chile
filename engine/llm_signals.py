"""
Análisis LLM con Groq (LLaMA 3.3 70B)
Sintetiza señales de 19 fuentes y genera razonamiento explicable.

El LLM actúa como un analista senior que:
1. Revisa todas las señales del motor
2. Detecta confirmaciones y contradicciones
3. Genera una tesis de inversión clara
4. Da una recomendación final con convicción ajustada

Costo: GRATIS (Groq tier gratuito)
Velocidad: ~2 segundos por análisis
Modelo: LLaMA 3.3 70B Versatile
"""

import os
import json
import time
from datetime import datetime

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
def get_api_key():
    """Obtiene API key de Groq desde config.json o variable de entorno"""
    # 1. Variable de entorno
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    # 2. config.json
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        return config.get("groq_api_key")
    except:
        return None

def guardar_api_key(api_key):
    """Guarda API key en config.json"""
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        config["groq_api_key"] = api_key
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✅ API key guardada en {CONFIG_FILE}")
    except Exception as e:
        print(f"Error guardando key: {e}")

# ── ANÁLISIS LLM ──────────────────────────────────────────────────────────────
def analizar_señales_llm(recomendaciones, contexto_macro=None, max_activos=5):
    """
    Usa LLaMA 3.3 via Groq para analizar las señales más importantes.
    Solo analiza activos con convicción >= 75% para ahorrar tokens.
    
    Returns:
        dict con análisis LLM por activo
    """
    api_key = get_api_key()
    if not api_key:
        return {}

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except:
        return {}

    # Filtrar señales de alta convicción
    señales_importantes = [
        r for r in recomendaciones
        if r.get("conviccion", 0) >= 75
    ][:max_activos]

    if not señales_importantes:
        return {}

    resultados = {}

    for señal in señales_importantes:
        try:
            # Construir contexto para el LLM
            activo    = señal.get("ib_ticker", señal.get("activo", ""))
            accion    = señal.get("accion", "")
            conviccion = señal.get("conviccion", 0)
            fuentes   = señal.get("fuentes", [])
            evidencia = señal.get("evidencia", [])
            tesis     = señal.get("tesis", "")

            # Construir prompt
            evidencia_texto = "\n".join([
                f"- {e.get('fuente','')}: {e.get('señal','')[:100]}"
                for e in evidencia[:8]
            ])

            macro_texto = ""
            if contexto_macro:
                macro_texto = f"""
CONTEXTO MACRO:
- SPY: {contexto_macro.get('SPY', {}).get('tendencia', 'N/A')}
- VIX: {contexto_macro.get('^VIX', {}).get('precio', 'N/A')}
- ECH (Chile): {contexto_macro.get('ECH', {}).get('tendencia', 'N/A')}
- Cobre: {contexto_macro.get('HG=F', {}).get('tendencia', 'N/A')}
"""

            prompt = f"""Eres un analista senior de trading especializado en mercados latinoamericanos y chilenos.
Analiza la siguiente señal de trading y proporciona tu evaluación crítica.

SEÑAL:
- Activo: {activo}
- Acción recomendada: {accion}
- Convicción del sistema: {conviccion}%
- Fuentes confirmando: {', '.join(fuentes[:6])}

EVIDENCIA:
{evidencia_texto}

{macro_texto}

TESIS INICIAL: {tesis}

Proporciona en español y en formato JSON exacto (sin markdown, sin explicaciones adicionales):
{{
    "validacion": "CONFIRMAR" o "CUESTIONAR" o "RECHAZAR",
    "conviccion_ajustada": número entre 0 y 100,
    "tesis_mejorada": "tesis de inversión clara y concisa en 1 oración",
    "riesgos_principales": ["riesgo 1", "riesgo 2"],
    "catalizadores": ["catalizador 1", "catalizador 2"],
    "horizonte_recomendado": "1-3 días" o "3-7 días" o "1-2 semanas",
    "razonamiento": "explicación breve de 2-3 oraciones"
}}"""

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1,  # Baja temperatura para consistencia
            )

            texto = response.choices[0].message.content.strip()

            # Parsear JSON
            try:
                # Limpiar posibles markdown fences
                texto_limpio = texto.replace("```json", "").replace("```", "").strip()
                analisis = json.loads(texto_limpio)
                analisis["activo"] = activo
                analisis["timestamp"] = datetime.now().isoformat()
                resultados[activo] = analisis
            except:
                resultados[activo] = {
                    "activo":             activo,
                    "validacion":         "CONFIRMAR",
                    "conviccion_ajustada": conviccion,
                    "tesis_mejorada":     tesis,
                    "razonamiento":       texto[:200],
                    "timestamp":          datetime.now().isoformat(),
                }

            time.sleep(0.5)  # Respetar rate limit Groq

        except Exception as e:
            continue

    return resultados

def sintetizar_portafolio_llm(recomendaciones, posiciones_actuales=None):
    """
    Análisis global del portafolio — cuáles ejecutar, en qué orden, riesgo total.
    Un solo llamado LLM para todo el portafolio.
    """
    api_key = get_api_key()
    if not api_key:
        return None

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except:
        return None

    try:
        # Construir resumen de señales
        señales_texto = "\n".join([
            f"- {r.get('ib_ticker','')}: {r.get('accion','')} Conv:{r.get('conviccion',0)}% Fuentes:{len(r.get('fuentes',[]))} Riesgo:{r.get('riesgo',0)}"
            for r in recomendaciones[:10]
        ])

        pos_texto = ""
        if posiciones_actuales:
            pos_texto = "\nPOSICIONES ABIERTAS:\n" + "\n".join([
                f"- {k}: {v.get('accion','')} @ {v.get('precio_entrada',0):,.2f}"
                for k, v in posiciones_actuales.items()
            ])

        prompt = f"""Eres el gestor de portafolio de un fondo de trading algorítmico chileno.
Analiza las siguientes señales y recomienda cuáles ejecutar considerando gestión de riesgo.

SEÑALES DISPONIBLES:
{señales_texto}
{pos_texto}

Responde en JSON exacto:
{{
    "ejecutar": ["ticker1", "ticker2"],
    "evitar": ["ticker3"],
    "razon_seleccion": "explicación breve",
    "riesgo_portafolio": "BAJO" o "MEDIO" o "ALTO",
    "sesgo_mercado": "ALCISTA" o "BAJISTA" o "NEUTRO",
    "max_posiciones_recomendadas": número
}}"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
        )

        texto = response.choices[0].message.content.strip()
        texto_limpio = texto.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_limpio)

    except Exception as e:
        return None

def get_analisis_llm_completo(recomendaciones, contexto_macro=None, posiciones=None):
    """
    Análisis LLM completo — por activo + síntesis de portafolio.
    Se llama solo cuando hay señales de alta convicción.
    """
    if not recomendaciones:
        return {"disponible": False}

    # Solo activar si hay señales >= 75%
    señales_altas = [r for r in recomendaciones if r.get("conviccion", 0) >= 75]
    if not señales_altas:
        return {"disponible": False, "razon": "Sin señales de alta convicción"}

    t0 = time.time()

    # Análisis por activo
    analisis_activos = analizar_señales_llm(
        recomendaciones, contexto_macro, max_activos=3
    )

    # Síntesis de portafolio
    sintesis = sintetizar_portafolio_llm(recomendaciones, posiciones)

    return {
        "disponible":      True,
        "analisis_activos": analisis_activos,
        "sintesis":        sintesis,
        "n_analizados":    len(analisis_activos),
        "tiempo":          round(time.time() - t0, 1),
        "timestamp":       datetime.now().isoformat(),
    }

if __name__ == "__main__":
    # Test con señales simuladas
    print("=== TEST ANÁLISIS LLM ===\n")

    api_key = get_api_key()
    if not api_key:
        print("Sin API key — guardando...")
        # Guardar key de prueba
        guardar_api_key("TU_API_KEY_GROQ")

    señales_test = [
        {
            "ib_ticker": "COPEC",
            "activo": "COPEC.SN",
            "accion": "COMPRAR",
            "conviccion": 90.0,
            "fuentes": ["Análisis Técnico", "MTF", "Mercado Local", "Correlaciones", "ML"],
            "tesis": "COPEC sobreventa RSI 35 con confirmación MTF y cobre alcista",
            "evidencia": [
                {"fuente": "AT", "señal": "RSI 35 sobreventa, MACD positivo"},
                {"fuente": "MTF", "señal": "3/3 timeframes alineados alcista"},
                {"fuente": "ML", "señal": "prob alza 86%, accuracy 60%"},
                {"fuente": "Correlaciones", "señal": "Cobre +7.9% en 20d favorece COPEC"},
            ],
            "riesgo": 4,
        },
        {
            "ib_ticker": "BTC",
            "activo": "BTC-USD",
            "accion": "VENDER",
            "conviccion": 85.0,
            "fuentes": ["ML", "IV Opciones", "Polymarket", "Kalshi"],
            "tesis": "BTC sobrecompra con puts institucionales y ML bajista",
            "evidencia": [
                {"fuente": "ML", "señal": "prob alza 30%, bajista"},
                {"fuente": "IV", "señal": "Skew puts extremo"},
                {"fuente": "Polymarket", "señal": "55% prob caída BTC"},
            ],
            "riesgo": 6,
        },
    ]

    contexto_test = {
        "SPY":   {"tendencia": "ALCISTA FUERTE"},
        "^VIX":  {"precio": 17.0},
        "ECH":   {"tendencia": "BAJISTA"},
        "HG=F":  {"tendencia": "ALCISTA FUERTE"},
    }

    t0 = time.time()
    resultado = get_analisis_llm_completo(señales_test, contexto_test)

    print(f"Tiempo: {time.time()-t0:.1f}s")
    print(f"Activos analizados: {resultado.get('n_analizados', 0)}")

    for activo, analisis in resultado.get("analisis_activos", {}).items():
        print(f"\n{'='*50}")
        print(f"[{analisis.get('validacion')}] {activo}")
        print(f"Convicción ajustada: {analisis.get('conviccion_ajustada')}%")
        print(f"Tesis: {analisis.get('tesis_mejorada','')}")
        print(f"Horizonte: {analisis.get('horizonte_recomendado','')}")
        print(f"Razonamiento: {analisis.get('razonamiento','')}")
        if analisis.get("riesgos_principales"):
            print(f"Riesgos: {', '.join(analisis['riesgos_principales'])}")

    if resultado.get("sintesis"):
        s = resultado["sintesis"]
        print(f"\n{'='*50}")
        print(f"SÍNTESIS PORTAFOLIO")
        print(f"Ejecutar: {s.get('ejecutar', [])}")
        print(f"Evitar: {s.get('evitar', [])}")
        print(f"Riesgo: {s.get('riesgo_portafolio','')}")
        print(f"Sesgo: {s.get('sesgo_mercado','')}")
        print(f"Razón: {s.get('razon_seleccion','')}")
