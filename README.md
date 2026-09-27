# Backtest de flujos AFP en renta variable local

Evaluación histórica de un supuesto de convergencia utilizado como proxy para analizar potenciales flujos de las AFP en acciones chilenas: **cada AFP tendería a converger hacia la cartera del sistema**, por lo que una diferencia (GAP) respecto al peso promedio histórico del sistema puede interpretarse como una señal potencial de compra o venta.

El backtest reconstruye, para cada mes, el flujo que habría proyectado este supuesto y lo compara con el flujo efectivamente observado al mes siguiente.

## Metodología

Para cada AFP $a$, acción $i$ y mes $t$:

| Concepto | Definición |
|---|---|
| Cartera accionaria | $RVL_{a,t} = \sum_i Monto_{a,i,t}$ |
| Peso AFP | $PesoAFP_{a,i,t} = Monto_{a,i,t} / RVL_{a,t}$ |
| Peso sistema | $PesoSistema_{i,t} = MontoSistema_{i,t} / \sum_j MontoSistema_{j,t}$ |
| Benchmark | Promedio de $PesoSistema_{i}$ en los 6 meses anteriores |
| GAP | $GAP_{a,i,t} = PesoAFP_{a,i,t} - Benchmark_{i,t}$ |
| Flujo proyectado | $-GAP_{a,i,t} \cdot RVL_{a,t}$ (positivo = compra) |
| Flujo observado | $Monto_{a,i,t+1} - Monto_{a,i,t}$ |

Se evalúan las observaciones con movimiento efectivo (flujo observado distinto de cero).

**KPI principal: MAE relativo**, el MAE del modelo dividido por el MAE del escenario
sin cambio (asumir que cada AFP mantiene su posición). Bajo 1 el modelo mejora la
estimación; sobre 1 la empeora.

Métricas complementarias: MAE en MM CLP, error como % de la cartera accionaria y de la
posición, relación proporcional, acierto direccional frente a la clase mayoritaria,
correlación, análisis por quintiles de GAP y cierre del GAP por tramo.

## Datos

Carteras publicadas por la Superintendencia de Pensiones:

```
data/
├── Agregadas.xlsx      # posición consolidada del sistema por acción (fondos A–E)
└── Desagregadas.csv    # posición por AFP y acción (separador ';', formato numérico chileno)
```

Columnas requeridas:
- `Agregadas.xlsx`: `Fecha`, `Nemo`, `Total_MMQ`, `Precio`
- `Desagregadas.csv`: `Fecha` (dd-mm-aaaa), `AFP`, `Nemo`, `Monto`

Los meses en que la SP publicó la cartera desagregada sin montos se excluyen
automáticamente de la evaluación.

## Uso

```bash
pip install -r requirements.txt
python backtest_flujos_afp.py
```

Con rutas distintas:

```bash
python backtest_flujos_afp.py --agregadas ruta/Agregadas.xlsx --desagregadas ruta/Desagregadas.csv --out resultados
```

## Salidas

```
outputs/
├── grafico1_mae_vs_flujo_real.png    # MAE del modelo vs flujo observado promedio
├── grafico2_quintiles.png            # flujo proyectado vs observado por quintil de GAP
├── grafico3_boxplot_error_pct.png    # distribución del error como % de la cartera, por AFP
└── resultados_backtest.xlsx          # validaciones, métricas, tablas y detalle por observación
```

## Tipografía

Los gráficos usan [Montserrat](https://github.com/JulietaUla/Montserrat) (licencia OFL).
Para replicarlos exactamente, descarga los archivos `.ttf` en la carpeta `fonts/`
(o instálala en el sistema). Si no está disponible, el script usa DejaVu Sans.

## Limitaciones

- El benchmark usa el promedio histórico de 6 meses del sistema como proxy de la
  referencia de mercado, ya que los pesos históricos del índice de referencia oficial
  no están disponibles.
- El flujo observado es la variación del monto invertido e incluye efecto precio.
- La cartera desagregada se publica con aproximadamente 5 meses de rezago; el backtest
  evalúa el supuesto con información del mismo mes, que corresponde al mejor caso posible.
