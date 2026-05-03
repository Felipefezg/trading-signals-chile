"""
Cargador paralelo de fuentes de datos.
Usa ThreadPoolExecutor para cargar todas las fuentes simultáneamente.
Reduce el tiempo de ciclo de ~107s a ~20s.
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime

# Timeouts por fuente (segundos)
TIMEOUTS = {
    "polymarket":    15,
    "kalshi":        10,
    "macro_usa":     15,
    "noticias":      15,
    "fear_greed":    20,
    "cmf":           10,
    "put_call":      20,
    "analisis_tecnico": 30,
    "google_trends": 30,
    "ipsa":          15,
    "volumen":       20,
}

def _cargar_polymarket():
    from data.polymarket import get_mercados_chile
    return get_mercados_chile(limit=200)

def _cargar_kalshi():
    from data.kalshi import get_kalshi_resumen
    return get_kalshi_resumen()

def _cargar_macro_usa():
    from data.macro_usa import get_macro_usa, get_correlaciones_chile
    return get_correlaciones_chile(get_macro_usa())

def _cargar_noticias():
    from data.noticias_chile import get_noticias_google
    from engine.nlp_sentiment import analizar_noticias_batch
    return analizar_noticias_batch(get_noticias_google())

def _cargar_fear_greed():
    from engine.fear_greed import calcular_fear_greed
    return calcular_fear_greed()

def _cargar_cmf():
    from data.cmf import get_hechos_esenciales
    return get_hechos_esenciales(solo_ipsa=True, limit=20)

def _cargar_put_call():
    from data.put_call import get_señal_consolidada_pc
    return get_señal_consolidada_pc()

def _cargar_analisis_tecnico():
    from engine.analisis_tecnico import get_señales_tecnicas
    return get_señales_tecnicas(min_conviccion=60)

def _cargar_google_trends():
    from data.google_trends import get_señales_trends
    return get_señales_trends(min_score=2)

def _cargar_volumen():
    from data.volumen import get_resumen_volumen, correlacionar_con_cmf
    resumen = get_resumen_volumen()
    return correlacionar_con_cmf(resumen.get("top_alertas", []))

def _cargar_sec_13f():
    from data.sec_13f import get_señales_institucionales
    return get_señales_institucionales(min_score=1)

def _cargar_renta_fija():
    from data.renta_fija import get_señales_renta_fija
    return get_señales_renta_fija()

def _cargar_mtf():
    from engine.analisis_mtf import get_señales_mtf
    return get_señales_mtf(min_conviccion=65, solo_alineados=False)

def _cargar_mercado_local():
    from engine.mercado_local import get_señales_ipsa
    return get_señales_ipsa(min_conviccion=65)

def _cargar_correlaciones():
    from engine.correlaciones import get_señales_correlacion
    return get_señales_correlacion(min_score=2)

def _cargar_order_flow():
    from engine.order_flow import get_señales_order_flow
    return get_señales_order_flow(min_score=2)

def _cargar_ib_data():
    from data.ib_market_data import get_señales_ib, es_horario_mercado
    if not es_horario_mercado():
        return []
    return get_señales_ib()

# Mapa de fuentes
FUENTES = {
    "polymarket":       (_cargar_polymarket,       TIMEOUTS["polymarket"]),
    "kalshi":           (_cargar_kalshi,            TIMEOUTS["kalshi"]),
    "macro_usa":        (_cargar_macro_usa,         TIMEOUTS["macro_usa"]),
    "noticias":         (_cargar_noticias,          TIMEOUTS["noticias"]),
    "fear_greed":       (_cargar_fear_greed,        TIMEOUTS["fear_greed"]),
    "cmf":              (_cargar_cmf,               TIMEOUTS["cmf"]),
    "put_call":         (_cargar_put_call,          TIMEOUTS["put_call"]),
    "analisis_tecnico": (_cargar_analisis_tecnico,  TIMEOUTS["analisis_tecnico"]),
    "google_trends":    (_cargar_google_trends,     TIMEOUTS["google_trends"]),
    "volumen":          (_cargar_volumen,           TIMEOUTS["volumen"]),
    "ib_data":          (_cargar_ib_data,           15),
    "order_flow":       (_cargar_order_flow,        20),
    "correlaciones":    (_cargar_correlaciones,     30),
    "mercado_local":    (_cargar_mercado_local,    30),
    "mtf":              (_cargar_mtf,              45),
    "renta_fija":       (_cargar_renta_fija,        15),
    "sec_13f":          (_cargar_sec_13f,           30),
}

def cargar_todas_las_fuentes(fuentes=None, max_workers=8, verbose=False):
    """
    Carga todas las fuentes en paralelo.

    Args:
        fuentes: Lista de fuentes a cargar (None = todas)
        max_workers: Threads simultáneos
        verbose: Mostrar tiempos individuales

    Returns:
        dict con resultados por fuente
    """
    if fuentes is None:
        fuentes = list(FUENTES.keys())

    resultados = {f: None for f in fuentes}
    errores    = {}
    tiempos    = {}

    t_inicio = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Lanzar todas las tareas
        futures = {}
        for nombre in fuentes:
            if nombre not in FUENTES:
                continue
            fn, timeout = FUENTES[nombre]
            future = executor.submit(fn)
            futures[future] = (nombre, timeout, time.time())

        # Recoger resultados
        for future in as_completed(futures, timeout=60):
            nombre, timeout, t_start = futures[future]
            elapsed = time.time() - t_start
            tiempos[nombre] = round(elapsed, 1)
            try:
                resultado = future.result(timeout=0.1)
                resultados[nombre] = resultado
                if verbose:
                    print(f"  ✓ {nombre:<20} {elapsed:.1f}s")
            except Exception as e:
                errores[nombre] = str(e)
                if verbose:
                    print(f"  ✗ {nombre:<20} {elapsed:.1f}s — {str(e)[:50]}")

    t_total = time.time() - t_inicio

    if verbose:
        print(f"\n  Total paralelo: {t_total:.1f}s")
        if errores:
            print(f"  Errores: {list(errores.keys())}")

    return {
        "datos":     resultados,
        "errores":   errores,
        "tiempos":   tiempos,
        "t_total":   round(t_total, 1),
        "timestamp": datetime.now().isoformat(),
    }

def get_datos_para_motor(verbose=False):
    """
    Carga todos los datos necesarios para el motor de recomendaciones.
    Versión optimizada con carga paralela.

    Returns:
        dict compatible con consolidar_señales()
    """
    resultado = cargar_todas_las_fuentes(verbose=verbose)
    datos = resultado["datos"]

    return {
        "poly_df":          datos.get("polymarket"),
        "kalshi_list":      datos.get("kalshi"),
        "macro_corr":       datos.get("macro_usa"),
        "noticias":         datos.get("noticias"),
        "fear_greed":       datos.get("fear_greed"),
        "cmf_hechos":       datos.get("cmf"),
        "put_call":         datos.get("put_call"),
        "analisis_tecnico": datos.get("analisis_tecnico"),
        "google_trends":    datos.get("google_trends"),
        "vol_alertas":      datos.get("volumen"),
        "ib_data":          datos.get("ib_data"),
        "order_flow":       datos.get("order_flow"),
        "correlaciones":    datos.get("correlaciones"),
        "mercado_local":    datos.get("mercado_local"),
        "mtf":              datos.get("mtf"),
        "renta_fija":       datos.get("renta_fija"),
        "sec_13f":          datos.get("sec_13f"),
        "meta": {
            "t_total":  resultado["t_total"],
            "errores":  resultado["errores"],
            "tiempos":  resultado["tiempos"],
        }
    }

if __name__ == "__main__":
    print("=== CARGA PARALELA DE FUENTES ===\n")
    t0 = time.time()
    resultado = cargar_todas_las_fuentes(verbose=True)
    print(f"\nTiempo total: {time.time()-t0:.1f}s")
    print(f"Errores: {list(resultado['errores'].keys()) or 'ninguno'}")
    print("\nTiempos por fuente:")
    for k, v in sorted(resultado['tiempos'].items(), key=lambda x: -x[1]):
        estado = "✓" if k not in resultado['errores'] else "✗"
        print(f"  {estado} {k:<20} {v:.1f}s")
