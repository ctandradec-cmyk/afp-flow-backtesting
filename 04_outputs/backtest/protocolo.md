# Protocolo pre-registrado · Backtesting formal de M1 y M3

Proyecto: estimación de potenciales movimientos de las AFP en renta variable local (RVL).
Autora: Catalina Andrade (UAI · pasantía Sales Trading, Banchile Inversiones).
Versión: 1.0 (pre-registro, Fase 0). Fecha de redacción: 16-oct-2026.

Este documento fija, **antes de correr el test**, los datos, las variables, los modelos, las métricas,
las pruebas de significancia y las reglas de decisión del backtesting. El hash del commit que lo
introduce y su fecha quedan en `05_bitacora/registro_backtest.md`. Cualquier cambio posterior se
agrega como enmienda fechada al final (sección 12), sin borrar el texto original.

---

## 1. Pregunta y alcance

**Problema (impacto en el negocio):** capacidad limitada de la mesa de Sales Trading para anticipar
oportunamente los potenciales movimientos de las AFP en RVL. La reforma (Ley 21.735: fondos
generacionales e INFOCES desde abril de 2027) aumenta su relevancia.

**Pregunta del backtest:** ¿reducen M1 (econometría de panel en dos etapas) y M3 (gradient boosting en
dos partes) la incertidumbre sobre el flujo mensual de cada AFP en cada acción, frente a la línea base
del Avance 1 y a benchmarks simples, usando solo información publicada en la fecha de decisión?

**Causas que interviene:** causa 2 (falta de métricas sistemáticas, principal), causa 1 (rezago: se
combina la desagregada con 5 meses de rezago con la agregada y el valor cuota, más recientes) y causa 4
(movimientos no observables: se estiman). La causa 3 (automatización) se mide aparte (tiempo de
actualización), no en este backtest.

**Lenguaje:** los resultados se reportan como estimaciones de potenciales movimientos y reducción de
incertidumbre, nunca como predicción cierta. En esta etapa todo se expresa en **MM CLP nominales**;
no se traduce a días de volumen.

## 2. Datos

| Fuente | Uso | Período usable |
|---|---|---|
| Cartera desagregada (AFP × acción, fondo "T") | variable objetivo; posición de cada AFP | dic-2020 → abr-2026 (may-2026 reservado, ver §9) |
| Cartera agregada (sistema por fondo A–E) | precio de mercado; N° de acciones del sistema; flujo del sistema; pesos por fondo | ene-2016 → ago-2026 |
| Valor cuota y patrimonio (AFP × fondo, diario) | flujo neto implícito (caja) | ene-2016 → sep-2026 |
| Pesos históricos IPSA (Bloomberg, mensual) | cambios de peso en el índice | ene-2020 → ago-2026 |
| Pesos INFOCES | solo documentación (variable post abril 2027) | snapshot actual |

Entradas: salidas de `src.limpieza.pipeline` en `02_processed/` (`*_limpio.parquet`). `01_raw/` no se
modifica. El archivo de precios diarios no se usa (precios contradictorios). Los datos de Bloomberg
(IPSA) no se publican.

Reglas:

1. **Unidad de análisis:** AFP × acción × mes objetivo, para las 7 AFP válidas (CAPITAL, CUPRUM,
   HABITAT, MODELO, PLANVITAL, PROVIDA, UNO). Se excluyen las filas "INDUSTRIA AFP".
2. **Universo de evaluación del mes M (definido ex ante):** todas las acciones con N° de acciones del
   sistema > 0 en la agregada de M−1, cruzadas con las 7 AFP. Un par sin posición en la desagregada
   tiene 0 acciones. Como sensibilidad se reporta el subconjunto "con posición en M−1 o en M"
   (comparable con la prueba exploratoria, pero condicionado al resultado).
3. **Variable objetivo:** `Flujo(a,s,M) = (U1 − U0·f) × P̄`, con U0, U1 = acciones de la AFP a en la
   acción s al cierre de M−1 y M (desagregada), f = factor de evento corporativo confirmado y
   P̄ = promedio del precio de la agregada al cierre de M−1 (ajustado por f) y de M. Si falta uno de
   los dos precios (deslistada), se usa el disponible (`flag_precio_parcial`). Es la definición de
   `src/flujos/panel.py` (Flujo_v2).
4. **Meses con Monto = 0 (sep-2023 y jun-2024):** las unidades vienen; el monto se reconstruye como
   Unidades × Precio agregada. El flujo no usa el monto, así que estos meses entran a la muestra.
5. **Deslistadas:** se mantienen (sesgo de supervivencia). La salida de una acción con posición es una
   venta por el total.
6. **Eventos corporativos y anomalías (se marcan, no se borran):** ITAUCL abr–may 2023, LTM nov-2022,
   EDELPA dic-2022, LIPIGAS dic-2022, CAMANCHACA feb-2021, con ventana ±1 mes (`flag_evento`);
   diciembre 2022 completo (`flag_dic2022`, salto de 20–200x en acciones chicas). Además: SM-CHILE B
   y UNO antes de oct-2021 (`flag_otro`).
   - **Especificación principal:** se excluyen las observaciones marcadas, tanto de las etiquetas de
     entrenamiento como de la evaluación.
   - **Sensibilidad:** todas las métricas se reportan también sin exclusiones.
7. **Equivalencias de nemos:** LAN→LTM, CENCOSHOPP→CENCOMALLS, MULTIFOODS→MULTI X, BICECORP→BICE
   (`config/equivalencias_nemos.csv`).
8. **Moneda:** CLP nominales; resultados en MM CLP. No se convierte a USD.
9. **Reporte de calidad (Fase 1):** filas, nulos, duplicados, observaciones marcadas por tipo y cruce
   desagregada vs agregada (acciones) por mes.

## 3. Calendario de información y fecha de decisión

Publicación (regla estricta):

- Desagregada del cierre de K: día 10 de K+5 (si no es hábil, el siguiente día hábil).
- Agregada del cierre de K: desde el 5.º día hábil de K+1.
- Valor cuota y patrimonio del día t: usable desde t+1.
- Pesos IPSA del cierre de K: usables desde el día 1 de K+1.

**Fecha de decisión del mes objetivo M:** `D_M` = primer día hábil (calendario de feriados de Chile)
estrictamente posterior a la publicación de la desagregada de M−5, es decir, normalmente el día 11
de M. En `D_M` se cumple siempre que la agregada de M−1 ya está publicada (5.º día hábil ≤ día 9).

Información disponible en `D_M`:

- Desagregada hasta M−5 → **etiquetas de entrenamiento: meses ≤ M−5**; posición de cada AFP en M−5.
- Agregada hasta M−1 → precios, acciones del sistema y pesos por fondo hasta M−1.
- Valor cuota y patrimonio hasta el día hábil anterior a `D_M`. Por consistencia, las variables de
  caja usan el **mes M−1 completo**; los días transcurridos de M no se usan en esta versión.
- Pesos IPSA hasta M−1.

**Qué se estima:** el flujo del mes calendario M completo (cierre M−1 → cierre M). Implicancia de
negocio: la estimación está disponible alrededor del día 11 de M, cuando ha transcurrido cerca de un
tercio del mes; el resto del mes es la ventana accionable.

**Filas de entrenamiento:** cada etiqueta del mes K se acompaña de las variables calculadas como si
se decidiera en `D_K` (mismo rezago que en producción).

**Test automático de no anticipación (obligatorio, `tests/test_backtest_calendario.py`):**
(i) cada fila fuente lleva `Fecha_Disponible`; toda variable de `D_M` se construye solo con filas con
`Fecha_Disponible < D_M` y el test lo verifica variable por variable; (ii) prueba de invariancia por
truncamiento: para una muestra de meses M, recalcular las variables después de borrar toda la
información con `Fecha_Disponible ≥ D_M` debe dar resultados idénticos; (iii) toda etiqueta de
entrenamiento usada en `D_M` es de un mes ≤ M−5.

## 4. Variables candidatas (información en D_M)

| Variable | Definición | Fuente / rezago | Prior financiero |
|---|---|---|---|
| `caja_peso` | Σ_f FlujoNetoImplícito(a,f,M−1) × w(s,f,M−1), con w = valor de s en el fondo f del sistema / patrimonio del fondo f del sistema | valor cuota M−1; agregada M−1 | + (compra pasiva por aportes; recoge traspasos entre fondos) |
| `flujo_previo` | Flujo(a,s,M−5) | desagregada M−5 | sin prior (persistencia o reversión) |
| `flujo_sistema` | FlujoSistema(s,M−1) × participación(a,s,M−5); FlujoSistema = ΔAcciones del sistema (M−2→M−1) × precio promedio; participación = acciones de a / acciones del sistema en M−5 | agregada M−1; desagregada M−5 | + (herding / demanda común) |
| `delta_ipsa` | Cambio de peso no explicado por precio: w(s,M−1) − w(s,M−2)·(1+r_s)/(1+r_IPSA), × RVL(a,M−5) | IPSA M−1; agregada M−1 | + (rebalanceo hacia el índice) |
| `retorno` (solo M3) | P(s,M−1)/P(s,M−2) − 1 (agregada, ajustado por eventos) | agregada M−1 | sin prior (momentum o rebalanceo contrario) |

Todas las variables en MM CLP salvo `retorno`. **Distancia a INFOCES:** no aplica en el período
histórico (el índice no existía como referencia); se documenta como variable post abril 2027:
GAP(a,s) = peso de a en s − peso INFOCES de s, con efecto esperado negativo (−λ · GAP × RVL).

## 5. Benchmarks (misma fecha de decisión y mismo universo)

1. **Cero:** flujo estimado = 0.
2. **Persistencia:** Flujo(a,s,M−5) (último flujo observable de la AFP en la acción).
3. **Clase mayoritaria:** solo para acierto direccional. Se reporta (i) la del mismo período evaluado
   (referencia ex post, como pide el estándar del proyecto) y (ii) la de las etiquetas de entrenamiento
   (versión factible).
4. **Herding del Avance 1 con rezago real:** −(PesoAFP(a,s,M−5) − PesoPromedio6m del sistema(s, M−6..M−1))
   × RVL(a,M−5), con PesoAFP y RVL de la desagregada de M−5 y el peso del sistema de la agregada
   (`src/flujos/linea_base.py`, con el rezago corregido).
5. **Flujo reciente del sistema × participación:** = `flujo_sistema`.
6. **Caja × peso:** = `caja_peso`.

## 6. Modelos

Validación walk-forward con **ventana expansiva**: en cada `D_M` se reentrena con todas las etiquetas
observables (meses ≤ M−5, sin observaciones marcadas). Semilla global 42.

### M1 · Econometría de panel en dos etapas (statsmodels)

- Etapa 1: logit de P(opera) con opera = 1[ΔAcciones ≠ 0].
- Etapa 2: regresión por cuantiles (τ = 0,10; 0,50; 0,90) del flujo en MM CLP, solo en observaciones
  que operan. Los cuantiles se reordenan si se cruzan.
- Las mismas variables entran a ambas etapas; con intercepto; sin efectos fijos.
- **Dirección:** signo del cuantil 0,50 condicional.
- **Estimación puntual:** se elige en desarrollo entre dos reglas fijadas aquí: (a) umbral
  1[p̂ ≥ 0,5] × Q50 y (b) esperanza p̂ × Q50, según el MAE de desarrollo.
- **Puntaje de señal (top-10):** p̂ × |Q50|.
- **Ablación (orden fijo):** paso 0 = solo intercepto; paso 1 = + `caja_peso`; paso 2 = + `flujo_previo`;
  paso 3 = + `flujo_sistema`; paso 4 = + `delta_ipsa`. Un componente se conserva si cumple (i) **y** (ii):
  1. Mejora medible en desarrollo frente al último modelo conservado: el IC90 por bootstrap de bloques
     de mes de la diferencia de MAE excluye 0 a favor del componente, **o** el acierto direccional
     (flujos ≠ 0) sube ≥ 2 pp con IC90 que excluye 0 sin que el MAE empeore más de 0,5%.
  2. Sentido financiero: si la variable tiene prior, el coeficiente de Q50 (promedio de los meses de
     desarrollo) tiene el signo esperado.

### M3 · LightGBM en dos partes

- Clasificador multiclase: compra / venta / sin movimiento (signo de ΔAcciones).
- Regresor cuantílico (objetivo `quantile`, α = 0,10; 0,50; 0,90) del flujo en MM CLP, solo en
  observaciones que operan; cuantiles reordenados si se cruzan.
- **Variables:** las cuatro candidatas de M1 (todas, antes de la ablación) + `retorno`.
- **Monotonicidad:** + para `caja_peso`, `flujo_sistema` y `delta_ipsa`; sin restricción para
  `flujo_previo` y `retorno`. Se aplica al regresor; si LightGBM no admite restricciones en
  multiclase, el clasificador queda sin restricción y se documenta.
- **Dirección:** argmax entre P(compra) y P(venta). **Puntaje de señal:** (P(compra)+P(venta)) × |Q50|.
- **Estimación puntual:** misma regla elegible que M1 (umbral 0,5 o esperanza), con p̂ = P(compra)+P(venta).
- **Hiperparámetros (validación temporal interna, dentro del entrenamiento de cada `D_M`):** pliegues =
  los últimos k meses de etiqueta V, con k = máx(3, mín(6, n_meses_etiqueta − 12)); cada pliegue entrena
  con etiquetas ≤ V−5 (mismo rezago). Grilla fija (8 combinaciones): `num_leaves` ∈ {7, 15},
  `min_child_samples` ∈ {50, 200}, `n_estimators` ∈ {100, 300}; fijos: `learning_rate` 0,05,
  `subsample` 0,8 (`subsample_freq` 1), `colsample_bytree` 1,0, `reg_lambda` 1,0, `seed` 42,
  `deterministic` true. Criterio: log-loss multiclase para el clasificador; pérdida pinball promedio
  de los tres cuantiles para el regresor (un solo set para los tres).
- **Explicación:** SHAP (TreeExplainer) global por período y local para las 10 señales de cada mes.

### Especificación congelada (Fase 3)

Al cierre del desarrollo se congela, en este archivo (sección 11) y con commit: variables retenidas de
M1, regla de estimación puntual de M1 y M3, y para M3 la grilla y la regla de reajuste mensual de
hiperparámetros (se congela el **procedimiento**, que se reaplica en cada `D_M` del test, como ocurriría
en producción).

## 7. Períodos

| Período | Meses objetivo | Uso |
|---|---|---|
| Desarrollo | oct-2022 → abr-2025 (31 meses; 30 sin dic-2022) | ablación, reglas de estimación, diagnóstico |
| Test histórico | may-2025 → abr-2026 (12 meses) | una sola corrida con especificaciones congeladas |
| Test prospectivo | may-2026 (y jun-2026 al publicarse, ~10-nov-2026) | confirmación, no prueba estadística |

El primer mes de desarrollo (oct-2022) usa etiquetas ene-2021 → may-2022 (17 meses), igual que la
prueba exploratoria. Las etiquetas de ene–jul 2021 incluyen los retiros de fondos: se mantienen en el
entrenamiento (la caja los recoge) y se hace una sensibilidad sin ellas.

**Declaración de contaminación:** la prueba exploratoria del 10-oct-2026 evaluó oct-2022 → abr-2026, que
incluye los meses de desarrollo y de test. Las versiones exploratorias (M1 con 4 señales, M3 con pérdida
l1) se diseñaron con conocimiento de esos resultados agregados. Los meses de test **no** se usan para
elegir la especificación en este protocolo, pero no son estrictamente "no vistos". La única evidencia
fuera de muestra en sentido estricto es el test prospectivo (§9).

## 8. Métricas (desarrollo, test y prospectivo; todos los modelos)

Sea y el flujo observado y ŷ la estimación puntual (MM CLP), sobre el universo del §2.

1. **MAE relativo** = Σ|y − ŷ| / Σ|y| (frente al flujo cero). IC90 por bootstrap de bloques de mes.
2. **Acierto direccional** sobre (a) y ≠ 0 y (b) |y| > 1.000 MM CLP: % con dirección estimada = signo
   de y. Una estimación sin dirección (ŷ = 0 en benchmarks) cuenta como error; se reporta además el
   acierto sobre las observaciones con dirección emitida y su cobertura. Siempre junto a la clase
   mayoritaria del mismo período.
3. **Precisión top-10 por mes:** de las 10 observaciones con mayor puntaje de señal del mes, % con
   y ≠ 0 y dirección correcta; promedio de los meses. Benchmarks: puntaje = |ŷ|.
4. **MASE** = MAE / escala, con escala = MAE de la persistencia sobre las etiquetas de entrenamiento
   disponibles en la primera fecha de decisión del período (agrupada, no por serie, para evitar
   divisiones por cero).
5. **Sobreestimación media** = media(|ŷ| − |y|); se reporta también el sesgo media(ŷ − y).
6. **Cobertura P10–P90** (M1 y M3): % de observaciones con y ≠ 0 tales que Q10 ≤ y ≤ Q90
   (condicional a operar; nominal 80%).
7. **Error por AFP** (MAE y MAE relativo) y **concentración del error:** % del error absoluto total que
   proviene de las 10 acciones con mayor valor promedio en cartera del sistema (agregada) en el período.

**Metas del proyecto:** MAE relativo ≤ 1,0x; acierto direccional ≥ 70%.

## 9. Significancia y regla de decisión

- **Bootstrap por bloques de mes:** se remuestrean meses completos con reposición, B = 5.000,
  semilla 20261016, IC90 por percentiles. Para comparaciones, bootstrap pareado (mismos meses).
- **Diebold-Mariano:** pérdida mensual L_t = MAE del mes t; d_t = L_t(modelo) − L_t(comparado); varianza
  HAC Newey-West (Bartlett) con L = ⌊T^{1/3}⌋ rezagos (2 en el test); corrección de Harvey-Leybourne-
  Newbold y distribución t con T−1 g.l.
  - Familia principal (test, Holm, α = 0,05): M1 vs {cero, persistencia, herding A1, flujo sistema,
    caja} (unilateral: M1 menor pérdida) y M3 vs M1 (bilateral). 6 pruebas.
  - Familia secundaria (Holm): M3 vs los cinco benchmarks (unilateral).
  - Se reportan p-valores crudos y ajustados.
- **Bajo poder:** con 12 meses de test el poder es bajo; se reporta el efecto mínimo detectable
  aproximado y no se interpreta un resultado no significativo como ausencia de mejora.
- **Lectura de resultados (fijada ex ante):** un modelo "alcanza la meta de MAE" si su MAE relativo
  puntual ≤ 1,0 en el test, y "mejora de forma significativa" sobre un benchmark si la prueba de
  Holm lo rechaza. La elección M1 vs M3 considera además interpretabilidad y robustez a la reforma
  (matriz multicriterio del Avance 2), no solo el MAE.
- **Test prospectivo:** may-2026 se estima con los modelos congelados entrenados con etiquetas
  ≤ dic-2025 (fecha de decisión ~11-may-2026) y se compara con la desagregada de may-2026
  (`01_raw/cartera_desagregada_05_2026.xls`, publicada el 10-oct-2026). **Ese archivo no se abre hasta
  la Fase 5.** Se reporta como confirmación descriptiva (un mes), sin pruebas de significancia.

## 10. Sesgos y controles (Fase 6)

Supervivencia (deslistadas incluidas), eventos corporativos (con y sin), retiros 2020–2021
(sensibilidad), aportes netos y traspasos (caja por fondo), efecto precio (flujo en acciones),
concentración del error en pocas acciones, múltiples pruebas (Holm), quiebre de régimen (el test es
previo a la reforma: los resultados no validan el comportamiento post abril 2027). Control de calidad
con la skill validate-data: recálculo independiente de al menos tres cifras clave.

**Entregables:** `src/backtest/` (código), `04_outputs/backtest/` (CSV, una figura por métrica clave,
`resumen.md`), `05_bitacora/registro_backtest.md` (decisiones y hashes). Nada de `01_raw/`,
`02_processed/` ni datos de Bloomberg se sube al repositorio.

## 11. Especificación congelada

*Pendiente (se completa al cierre de la Fase 3, con commit propio).*

## 12. Enmiendas

*Ninguna.*
