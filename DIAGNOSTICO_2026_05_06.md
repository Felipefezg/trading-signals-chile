# Diagnóstico Integral del Motor de Trading
**Fecha:** 2026-05-06  
**Cuenta IB:** DUP838882 (paper trading, puerto 7497)

---

## Resumen Ejecutivo

El motor sufrió un ciclo catastrófico en el que abrió 7 posiciones simultáneas —incluyendo contratos de futuros con nocional 6× el límite por operación— derivado de una combinación de tres fallos concurrentes: un race condition de validación intra-ciclo, precios de futuros completamente corruptos, y una fórmula de convicción sin techo. El PnL resultante (-95.29% no realizado) fue una lectura deformada, no una pérdida real, pero el riesgo latente era real. Se ejecutó cierre de emergencia de todas las posiciones y se reescribió el motor con las correcciones descritas abajo.

---

## Problemas Identificados y Estado

### 1. Race condition en `validar_señal` — CRÍTICO [CORREGIDO]

**Síntoma:** 7 posiciones abiertas en un solo ciclo (límite: 8, pero la intención es 1–2/ciclo).

**Causa raíz:** `ciclo_trading_automatico()` itera sobre las recomendaciones en orden y llama `validar_señal()` en cada una. `validar_señal()` lee `posiciones.json` para contar posiciones abiertas y verificar el riesgo total. El problema es que `posiciones.json` solo se actualiza **después** de que `ib_executor.py` confirma la orden con IB (~2–30 segundos después). Las iteraciones 2–7 del mismo ciclo ven `posiciones.json` vacío y todas pasan los checks.

**Fix aplicado (`engine/motor_automatico.py`):**
- Se inicializa `_posiciones_ciclo = _cargar_posiciones()` una sola vez al inicio del loop.
- Después de cada apertura exitosa confirmada por IB, se inserta `_posiciones_ciclo[ticker] = {...}` inmediatamente.
- `validar_señal()` recibe `posiciones_cache=_posiciones_ciclo` y usa este dict en lugar de releer el archivo.
- Las iteraciones 2–7 del mismo ciclo ven los slots ya ocupados y son rechazadas.

---

### 2. Futuros CL y HG con nocional masivo — CRÍTICO [CORREGIDO]

**Síntoma:** Posición CL (WTI crude) mostraba PnL de -95.29%.

**Causa raíz:**
- CL (WTI crude): 1 contrato = 1.000 barriles × ~$95 = **~$95.000 USD/contrato**
- HG (copper): 1 contrato = 25.000 lbs × ~$1/lb = **~$25.000 USD/contrato**
- El sistema calculaba `precio_actual × cantidad` con el precio de yfinance que para futuros devuelve el valor del contrato completo en ciertos contextos.
- El `max_usd_por_operacion` es $15.000 — ambos lo exceden ampliamente.
- El PnL se calculaba como `(precio_cierre - precio_entrada) / precio_entrada`, donde `precio_entrada` era el valor del contrato ($95.000) pero `precio_cierre` era el precio spot ($95/barril) → ratio ≈ 0.001 → -99.9% aparente.

**Fix aplicado:**
1. `BLACKLIST_AUTO = {"CL", "HG"}` agregado en `motor_automatico.py`. `validar_señal()` rechaza estos tickers con mensaje explícito antes de cualquier otra validación.
2. `PRECIO_MAX` dict en `recomendaciones.py → _get_volatilidad()` que descarta precios de futuros por encima de rangos razonables (CL > $300 → dato corrupto).

**Nota operacional:** CL y HG siguen en el universo de análisis para generar señales de correlaciones y análisis técnico. Solo están bloqueados para ejecución automática. Para operar manualmente: IB Gateway → orden manual.

---

### 3. Fórmula de convicción sin techo — ALTO [CORREGIDO]

**Síntoma:** Señales apareciendo con 100% de convicción.

**Causa raíz:** `conviccion_pct = alza / (alza + baja) * 100`. Cuando `baja = 0` (todas las fuentes alcistas, ninguna bajista), el resultado es 100%. Esto ocurría habitualmente porque la mayoría de fuentes solo aportan a `alza` cuando detectan señal positiva, y simplemente no aportan a `baja` si no hay señal negativa.

**Fix aplicado (`engine/recomendaciones.py`):**
```python
CAP_FUENTES = {1: 60, 2: 72, 3: 82, 4: 88, 5: 93}
cap = CAP_FUENTES.get(n_fuentes, 95)
conviccion_pct = min(conviccion_pct, cap)
```
Una señal respaldada por solo 1 fuente no puede superar 60%, independientemente del ratio alza/baja. Requiere 5+ fuentes para acercarse a 93%.

---

### 4. Fear & Greed con efecto nulo — MEDIO [CORREGIDO]

**Síntoma:** Fear & Greed aparecía listado en `fuentes` de casi todas las señales, inflando artificialmente `n_fuentes`.

**Causa raíz:** La lógica anterior multiplicaba `baja * fg_mult`, pero si `baja = 0` (lo habitual), el efecto era nulo. Sin embargo se agregaba "Fear&Greed" a `fuentes` igualmente.

**Fix aplicado:** F&G solo actúa en valores extremos (≤25 o ≥70) y solo se agrega a `fuentes` cuando realmente modifica el score. Zona neutral (25–70): sin efecto, sin conteo de fuente.

---

### 5. Tipo incorrecto en fuentes: list vs dict — ALTO [CORREGIDO]

**Síntoma:** `AttributeError: 'list' object has no attribute 'get'` bloqueando todo el ciclo de señales.

**Causa raíz:** `sec_13f`, `correlaciones` e `iv_opciones` retornan listas, pero `recomendaciones.py` los trataba como dicts con `.items()` o `.get("pares", [])`.

**Fix aplicado:** Conversión defensiva con `isinstance()` en los tres iteradores.

---

### 6. Parámetros conservadores endurecidos — PREVENTIVO [APLICADO]

| Parámetro | Antes | Ahora | Razón |
|-----------|-------|-------|-------|
| `conviccion_minima` | 75% | **78%** | Reducir señales espurias hasta validar comportamiento |
| `fuentes_minimas` | 2 | **3** | Diversidad mínima de evidencia independiente |

---

### 7. SECTORES incompleto para SLV y GDX — BAJO [CORREGIDO]

SLV y GDX estaban en el universo de activos pero no en el dict `SECTORES` de `motor_automatico.py`. Resultaban en sector "Otros", rompiendo el control `max_mismo_sector` para el grupo Commodities. Agregados como `"SLV": "Commodities"` y `"GDX": "Commodities"`.

---

### 8. Motor pausado por trades fantasma — ALTO [CORREGIDO en sesiones previas]

**Causa raíz:** El contador `consecutivos_perdedor` se incrementaba con cierres no confirmados por IB. Fix previo: el contador solo sube cuando `confirmado_ib=True`.

---

### 9. `ib_sync.py` creaba posiciones fantasma — CRÍTICO [CORREGIDO en sesiones previas]

`sincronizar_posiciones_local()` construía posiciones locales desde datos parciales de IB, creando entradas con precios incorrectos o tickers mal resueltos. Fix: la función fue reescrita para solo sincronizar en una dirección (IB → local), con validación estricta de cada campo.

---

## Arquitectura Post-Diagnóstico

```
ciclo_trading_automatico()
    │
    ├── sincronizar_desde_ib()           ← IB es fuente de verdad
    │
    ├── verificar_posiciones()           ← SL/TP/Trailing
    │   └── usa posiciones reales de IB
    │
    └── Loop señales:
        ├── _posiciones_ciclo = _cargar_posiciones()  ← UNA SOLA VEZ
        │
        ├── for r in recomendaciones:
        │   ├── validar_señal(posiciones_cache=_posiciones_ciclo)
        │   │   ├── BLACKLIST_AUTO check  ← CL, HG rechazados
        │   │   ├── conviccion ≥ 78%
        │   │   ├── fuentes ≥ 3
        │   │   ├── ticker no en _posiciones_ciclo
        │   │   ├── len(_posiciones_ciclo) < max_posiciones
        │   │   └── sector count < max_mismo_sector
        │   │
        │   └── Si válida:
        │       ├── ejecutar_señal_automatica()
        │       └── _posiciones_ciclo[ticker] = {...}  ← UPDATE INMEDIATO
        │
        └── Señal siguiente ve slot ocupado → rechazada
```

---

## Checklist Post-Diagnóstico

- [x] Posiciones IB cerradas (script `cerrar_todas_posiciones.py`)
- [x] `posiciones.json` limpiado a `{}`
- [x] Race condition intra-ciclo corregido (`_posiciones_ciclo` cache)
- [x] `BLACKLIST_AUTO = {"CL", "HG"}` en producción
- [x] `CAP_FUENTES` limitando convicción máxima
- [x] Fear & Greed solo actúa en extremos reales
- [x] Iteradores `sec_13f`, `correlaciones`, `iv_opciones` corregidos (list/dict)
- [x] `fuentes_minimas` subido a 3
- [x] `conviccion_minima` subido a 78%
- [x] SLV y GDX en SECTORES
- [x] Precio máximo por futuro validado en `_get_volatilidad()`
- [ ] Verificar posición SQM en IB (estaba abierta antes del ciclo problemático)
- [ ] Monitorear primer ciclo completo post-reactivación
- [ ] Reactivar motor (comando: cambiar `activo=True` en estado_automatico.json o via dashboard)

---

## Reactivación del Motor

Una vez verificado que IB Gateway está conectado y posiciones IB = 0:

```bash
# Desde ~/trading_signals con venv activo
python -c "
import json
with open('estado_automatico.json') as f:
    e = json.load(f)
e['activo'] = True
e['pausado'] = False
e['razon_pausa'] = None
e['consecutivos_perdedor'] = 0
with open('estado_automatico.json', 'w') as f:
    json.dump(e, f, indent=2)
print('Motor reactivado')
"
```

O directamente desde el dashboard → toggle "Motor Activo".

---

*Informe generado automáticamente por diagnóstico integral — sesión 2026-05-06*
