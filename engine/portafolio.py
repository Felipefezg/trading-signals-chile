"""
Módulo de optimización de portafolio.
Implementa:
1. Markowitz — Frontera eficiente y portafolio óptimo (máximo Sharpe)
2. VaR (Value at Risk) — Pérdida máxima esperada al 95% y 99%
3. CVaR (Conditional VaR) — Pérdida esperada en el peor 5%
4. Análisis de contribución al riesgo por activo
"""

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize
from datetime import datetime

# ── UNIVERSO DE ACTIVOS ───────────────────────────────────────────────────────
UNIVERSO_DEFAULT = {
    "ECH":       "IPSA ETF",
    "SQM":       "SQM (NYSE)",
    "COPEC.SN":  "Copec",
    "BCI.SN":    "Banco BCI",
    "CHILE.SN":  "Banco Chile",
    "CMPC.SN":   "CMPC",
    "GC=F":      "Oro",
    "SPY":       "S&P 500",
}

TASA_LIBRE_RIESGO = 0.045  # TPM Chile 4.5%

# ── DATOS ─────────────────────────────────────────────────────────────────────
def get_datos_portafolio(tickers=None, periodo="2y"):
    """Descarga precios y calcula retornos para el universo de activos"""
    if tickers is None:
        tickers = list(UNIVERSO_DEFAULT.keys())

    try:
        data = yf.download(tickers, period=periodo, progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            closes = data["Close"]
        else:
            closes = data

        closes = closes.dropna(how="all").ffill().dropna()
        retornos = closes.pct_change().dropna()
        return closes, retornos
    except Exception as e:
        print(f"Error descargando datos: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ── MÉTRICAS DE PORTAFOLIO ────────────────────────────────────────────────────
def calcular_metricas(pesos, retornos_mean, cov_matrix):
    """Calcula retorno, volatilidad y Sharpe de un portafolio"""
    retorno = np.dot(pesos, retornos_mean) * 252
    vol     = np.sqrt(np.dot(pesos.T, np.dot(cov_matrix * 252, pesos)))
    sharpe  = (retorno - TASA_LIBRE_RIESGO) / vol if vol > 0 else 0
    return retorno, vol, sharpe

# ── OPTIMIZACIÓN MARKOWITZ ────────────────────────────────────────────────────
def optimizar_portafolio(retornos, metodo="max_sharpe"):
    """
    Optimiza el portafolio según el método especificado.
    
    Métodos:
    - max_sharpe: maximiza el ratio Sharpe
    - min_vol: minimiza la volatilidad
    - equal_weight: pesos iguales (benchmark)
    """
    n = len(retornos.columns)
    mu  = retornos.mean()
    cov = retornos.cov()

    # Restricciones y límites
    constraints = [{"type": "eq", "fun": lambda x: np.sum(x) - 1}]
    bounds = tuple((0.02, 0.40) for _ in range(n))  # min 2%, max 40% por activo
    pesos_init = np.array([1/n] * n)

    if metodo == "max_sharpe":
        def neg_sharpe(pesos):
            r, v, s = calcular_metricas(pesos, mu, cov)
            return -s
        resultado = minimize(neg_sharpe, pesos_init, method="SLSQP",
                           bounds=bounds, constraints=constraints)

    elif metodo == "min_vol":
        def volatilidad(pesos):
            return np.sqrt(np.dot(pesos.T, np.dot(cov * 252, pesos)))
        resultado = minimize(volatilidad, pesos_init, method="SLSQP",
                           bounds=bounds, constraints=constraints)

    else:  # equal_weight
        class FakeResult:
            x = pesos_init
            success = True
        resultado = FakeResult()

    if not resultado.success and metodo != "equal_weight":
        resultado.x = pesos_init

    pesos_opt = resultado.x
    retorno, vol, sharpe = calcular_metricas(pesos_opt, mu, cov)

    return {
        "pesos":    dict(zip(retornos.columns, pesos_opt.round(4))),
        "retorno":  round(retorno, 4),
        "vol":      round(vol, 4),
        "sharpe":   round(sharpe, 4),
        "metodo":   metodo,
    }

# ── FRONTERA EFICIENTE ────────────────────────────────────────────────────────
def calcular_frontera_eficiente(retornos, n_puntos=50):
    """
    Calcula la frontera eficiente de Markowitz.
    Simula N portafolios aleatorios y encuentra la frontera.
    """
    n       = len(retornos.columns)
    mu      = retornos.mean()
    cov     = retornos.cov()
    results = []

    np.random.seed(42)
    for _ in range(max(n_puntos * 20, 2000)):
        pesos = np.random.dirichlet(np.ones(n))
        # Aplicar límites suaves
        pesos = np.clip(pesos, 0.01, 0.50)
        pesos /= pesos.sum()

        r, v, s = calcular_metricas(pesos, mu, cov)
        results.append({
            "retorno": round(r, 4),
            "vol":     round(v, 4),
            "sharpe":  round(s, 4),
            "pesos":   pesos.tolist(),
        })

    return sorted(results, key=lambda x: x["sharpe"], reverse=True)[:n_puntos]

# ── VaR y CVaR ────────────────────────────────────────────────────────────────
def calcular_var(retornos, pesos_dict, capital=100_000, confianza=0.95):
    """
    Calcula VaR (Value at Risk) y CVaR (Conditional VaR).
    
    VaR 95% = pérdida máxima en el 95% de los escenarios
    CVaR 95% = pérdida promedio en el peor 5%
    """
    tickers_disponibles = [t for t in pesos_dict if t in retornos.columns]
    if not tickers_disponibles:
        return {}

    pesos = np.array([pesos_dict.get(t, 0) for t in tickers_disponibles])
    ret_port = retornos[tickers_disponibles].dot(pesos)

    # VaR histórico
    var_95 = np.percentile(ret_port, (1 - confianza) * 100)
    var_99 = np.percentile(ret_port, 1)

    # CVaR (Expected Shortfall)
    cvar_95 = ret_port[ret_port <= var_95].mean()
    cvar_99 = ret_port[ret_port <= var_99].mean()

    # En USD
    var_95_usd  = abs(var_95 * capital)
    var_99_usd  = abs(var_99 * capital)
    cvar_95_usd = abs(cvar_95 * capital)
    cvar_99_usd = abs(cvar_99 * capital)

    # VaR paramétrico (normal)
    mu_port  = ret_port.mean()
    std_port = ret_port.std()
    var_param_95 = abs((mu_port - 1.645 * std_port) * capital)
    var_param_99 = abs((mu_port - 2.326 * std_port) * capital)

    return {
        "capital":        capital,
        "var_95_pct":     round(abs(var_95) * 100, 3),
        "var_99_pct":     round(abs(var_99) * 100, 3),
        "cvar_95_pct":    round(abs(cvar_95) * 100, 3),
        "cvar_99_pct":    round(abs(cvar_99) * 100, 3),
        "var_95_usd":     round(var_95_usd, 0),
        "var_99_usd":     round(var_99_usd, 0),
        "cvar_95_usd":    round(cvar_95_usd, 0),
        "cvar_99_usd":    round(cvar_99_usd, 0),
        "var_param_95":   round(var_param_95, 0),
        "var_param_99":   round(var_param_99, 0),
        "retorno_diario_pct": round(mu_port * 100, 3),
        "vol_diaria_pct":     round(std_port * 100, 3),
        "retorno_anual_pct":  round(mu_port * 252 * 100, 2),
        "vol_anual_pct":      round(std_port * np.sqrt(252) * 100, 2),
        "n_obs":          len(ret_port),
    }

# ── CONTRIBUCIÓN AL RIESGO ────────────────────────────────────────────────────
def calcular_contribucion_riesgo(retornos, pesos_dict):
    """
    Calcula cuánto contribuye cada activo al riesgo total del portafolio.
    Útil para saber cuál activo está dominando el riesgo.
    """
    tickers = [t for t in pesos_dict if t in retornos.columns]
    pesos   = np.array([pesos_dict[t] for t in tickers])
    cov     = retornos[tickers].cov().values * 252

    vol_port = np.sqrt(np.dot(pesos.T, np.dot(cov, pesos)))
    if vol_port == 0:
        return {}

    # Marginal contribution to risk
    mcr = np.dot(cov, pesos) / vol_port
    # Component contribution to risk
    ccr = pesos * mcr
    # % contribution
    pct_ccr = ccr / vol_port

    resultado = {}
    for i, ticker in enumerate(tickers):
        resultado[ticker] = {
            "peso":            round(pesos[i] * 100, 1),
            "contrib_riesgo":  round(pct_ccr[i] * 100, 1),
            "nombre":          UNIVERSO_DEFAULT.get(ticker, ticker),
        }
    return resultado

# ── ANÁLISIS COMPLETO ─────────────────────────────────────────────────────────
def get_analisis_portafolio(capital=100_000, periodo="2y"):
    """
    Ejecuta análisis completo de portafolio.
    Retorna optimización, VaR y frontera eficiente.
    """
    _, retornos = get_datos_portafolio(periodo=periodo)
    if retornos.empty:
        return {}

    # Portafolios optimizados
    port_sharpe   = optimizar_portafolio(retornos, "max_sharpe")
    port_min_vol  = optimizar_portafolio(retornos, "min_vol")
    port_equal    = optimizar_portafolio(retornos, "equal_weight")

    # VaR para cada portafolio
    var_sharpe  = calcular_var(retornos, port_sharpe["pesos"], capital)
    var_min_vol = calcular_var(retornos, port_min_vol["pesos"], capital)

    # Contribución al riesgo del portafolio Sharpe
    contrib = calcular_contribucion_riesgo(retornos, port_sharpe["pesos"])

    # Frontera eficiente (muestra)
    frontera = calcular_frontera_eficiente(retornos, n_puntos=100)

    return {
        "timestamp":       datetime.now().isoformat(),
        "capital":         capital,
        "periodo":         periodo,
        "n_activos":       len(retornos.columns),
        "activos":         list(retornos.columns),
        "port_sharpe":     port_sharpe,
        "port_min_vol":    port_min_vol,
        "port_equal":      port_equal,
        "var_sharpe":      var_sharpe,
        "var_min_vol":     var_min_vol,
        "contribucion":    contrib,
        "frontera":        frontera,
        "retornos_stats":  {
            t: {
                "retorno_anual": round(float(retornos[t].mean() * 252 * 100), 1),
                "vol_anual":     round(float(retornos[t].std() * np.sqrt(252) * 100), 1),
                "sharpe":        round(float((retornos[t].mean() * 252 - TASA_LIBRE_RIESGO) /
                                            (retornos[t].std() * np.sqrt(252))), 2),
            }
            for t in retornos.columns
        },
    }

if __name__ == "__main__":
    print("=== OPTIMIZACIÓN DE PORTAFOLIO ===\n")
    analisis = get_analisis_portafolio(capital=100_000)

    print("PORTAFOLIO MÁXIMO SHARPE:")
    port = analisis["port_sharpe"]
    print(f"  Retorno: {port['retorno']*100:.1f}% | Vol: {port['vol']*100:.1f}% | Sharpe: {port['sharpe']:.2f}")
    for t, p in sorted(port["pesos"].items(), key=lambda x: -x[1]):
        nombre = UNIVERSO_DEFAULT.get(t, t)
        print(f"  {nombre:<20} {p*100:5.1f}%")

    print("\nVaR 95% (Capital USD 100.000):")
    var = analisis["var_sharpe"]
    print(f"  Pérdida máx diaria (95%): USD {var['var_95_usd']:,.0f} ({var['var_95_pct']}%)")
    print(f"  Pérdida máx diaria (99%): USD {var['var_99_usd']:,.0f} ({var['var_99_pct']}%)")
    print(f"  CVaR 95% (peor 5%):       USD {var['cvar_95_usd']:,.0f} ({var['cvar_95_pct']}%)")

    print("\nCONTRIBUCIÓN AL RIESGO:")
    for t, c in sorted(analisis["contribucion"].items(), key=lambda x: -x[1]["contrib_riesgo"]):
        print(f"  {c['nombre']:<20} Peso: {c['peso']:5.1f}% | Riesgo: {c['contrib_riesgo']:5.1f}%")
