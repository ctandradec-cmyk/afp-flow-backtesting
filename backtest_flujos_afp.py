"""
Backtest del supuesto de convergencia al sistema en los flujos de las AFP
en renta variable local (RVL).

Supuesto evaluado
-----------------
Cada AFP tiende a replicar la cartera del sistema. Si en el mes t una AFP está
sobreponderada o subponderada en una acción respecto al promedio histórico del
sistema, en el mes t+1 cerrará esa diferencia (GAP) comprando o vendiendo.

Para cada AFP a, acción i y mes t:
    RVL_{a,t}          = sum_i Monto_{a,i,t}
    PesoAFP_{a,i,t}    = Monto_{a,i,t} / RVL_{a,t}
    PesoSistema_{i,t}  = MontoSistema_{i,t} / sum_j MontoSistema_{j,t}
    Benchmark_{i,t}    = promedio de PesoSistema_{i,t-1..t-6} (meses en que la acción estuvo en cartera)
    GAP_{a,i,t}        = PesoAFP_{a,i,t} - Benchmark_{i,t}          (+ sobreponderada, - subponderada)
    FlujoProyectado    = -GAP_{a,i,t} * RVL_{a,t}                   (+ compra, - venta)
    FlujoObservado     = Monto_{a,i,t+1} - Monto_{a,i,t}

La evaluación se hace sobre las observaciones con movimiento efectivo
(FlujoObservado != 0). KPI principal: MAE relativo = MAE del modelo / MAE del
escenario sin cambio (asumir que cada AFP mantiene su posición, flujo = 0).

Datos
-----
Carteras publicadas por la Superintendencia de Pensiones (SP):
    data/Agregadas.xlsx     posición consolidada del sistema por acción (fondos A-E)
    data/Desagregadas.csv   posición por AFP y acción

Uso
---
    python backtest_flujos_afp.py
    python backtest_flujos_afp.py --agregadas data/Agregadas.xlsx --desagregadas data/Desagregadas.csv --out outputs

Salidas (carpeta outputs/)
--------------------------
    grafico1_mae_vs_flujo_real.png
    grafico2_quintiles.png
    grafico3_boxplot_error_pct.png
    resultados_backtest.xlsx
"""

import argparse
import glob
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# =============================================================================
# Configuración
# =============================================================================
ROOT = Path(__file__).resolve().parent
DEFAULT_AGREGADAS = ROOT / "data" / "Agregadas.xlsx"
DEFAULT_DESAGREGADAS = ROOT / "data" / "Desagregadas.csv"
DEFAULT_OUT = ROOT / "outputs"
FONTS_DIR = ROOT / "fonts"

AFPS = ["CAPITAL", "CUPRUM", "HABITAT", "MODELO", "PLANVITAL", "PROVIDA", "UNO"]
VENTANA_BENCHMARK = 6          # meses
MM = 1e6                       # millones de CLP
TRAMOS_GAP_PP = [0, 0.05, 0.10, 0.25, 0.50, 1.00, np.inf]

NAVY, CELESTE, GRID = "#0B1F4B", "#6EC1E4", "#D9DEE7"


# =============================================================================
# Utilidades
# =============================================================================
def fmt_cl(x, dec=0):
    """Formato numérico chileno: punto de miles y coma decimal."""
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_num_cl(s):
    """Convierte texto con formato chileno ('1.234,5', ' - ') a float. '-' se interpreta como 0."""
    s = s.astype(str).str.strip()
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s.replace({"-": "0", "": "0", "nan": np.nan}), errors="coerce")


def configurar_estilo():
    """Estilo de gráficos: Montserrat si está disponible (carpeta fonts/ o sistema)."""
    for f in glob.glob(str(FONTS_DIR / "Montserrat-*.ttf")):
        fm.fontManager.addfont(f)
    disponibles = {f.name for f in fm.fontManager.ttflist}
    familia = "Montserrat" if "Montserrat" in disponibles else "DejaVu Sans"
    if familia != "Montserrat":
        print("Aviso: Montserrat no encontrada; se usa DejaVu Sans. Ver README para instalarla.")
    plt.rcParams.update({
        "font.family": familia, "font.size": 10.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.titleweight": "bold", "axes.titlesize": 14,
    })


# =============================================================================
# Carga de datos
# =============================================================================
def cargar_agregadas(path):
    """Cartera agregada: monto y peso de cada acción en el sistema AFP."""
    ag = pd.read_excel(path)
    ag["Nemo"] = ag["Nemo"].astype(str).str.strip()
    ag["Fecha"] = pd.to_datetime(ag["Fecha"])
    ag["Mes"] = ag["Fecha"].dt.to_period("M")
    ag["MontoSistema"] = ag["Total_MMQ"] * ag["Precio"] * 1e6
    ag["AccNacSistema"] = ag.groupby("Mes")["MontoSistema"].transform("sum")
    ag["PesoSistema"] = ag["MontoSistema"] / ag["AccNacSistema"]
    return ag


def cargar_desagregadas(path):
    """Cartera desagregada: monto por AFP y acción. Excluye la fila de total industria."""
    de = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str)
    de.columns = [c.strip() for c in de.columns]
    if "Administrador" in de.columns and "AFP" not in de.columns:
        de = de.rename(columns={"Administrador": "AFP"})
    de["AFP"] = de["AFP"].str.strip().str.upper()
    de["Nemo"] = de["Nemo"].str.strip()
    de["Monto"] = parse_num_cl(de["Monto"]).fillna(0.0)
    de["Mes"] = pd.to_datetime(de["Fecha"], format="%d-%m-%Y").dt.to_period("M")
    return de[de["AFP"].isin(AFPS)].copy()


# =============================================================================
# Modelo
# =============================================================================
def calcular_benchmark(ag):
    """Promedio del peso del sistema en los 6 meses anteriores (solo meses con la acción en cartera)."""
    piv = ag.pivot(index="Mes", columns="Nemo", values="PesoSistema").sort_index()
    piv = piv.reindex(pd.period_range(piv.index.min(), piv.index.max(), freq="M"))
    bench = piv.shift(1).rolling(VENTANA_BENCHMARK, min_periods=1).mean()
    bench = bench.stack().rename("Benchmark").reset_index()
    return bench.rename(columns={"level_0": "Mes"})


def construir_panel(ag, de):
    """
    Panel AFP x acción x mes con flujo proyectado y observado.

    Universo: acciones de la cartera agregada en t, para cada AFP. Si la AFP no
    mantiene la acción, su monto es 0. Se excluyen los meses en que alguna AFP
    no tiene montos publicados en t o t+1.
    """
    pos = de.groupby(["Mes", "AFP", "Nemo"], as_index=False)["Monto"].sum()
    rvl = (pos.groupby(["Mes", "AFP"], as_index=False)["Monto"].sum()
              .rename(columns={"Monto": "RVL_AFP"}))

    con_datos = rvl.groupby("Mes")["RVL_AFP"].min() > 0
    validos = set(con_datos[con_datos].index)
    meses_est = sorted(m for m in validos if (m + 1) in validos)
    excluidos = sorted(m for m in set(rvl["Mes"]) if m not in meses_est)

    panel = ag[["Mes", "Nemo"]].drop_duplicates().merge(rvl, on="Mes")
    panel = panel[panel["Mes"].isin(meses_est)]
    panel = panel.merge(pos, on=["Mes", "AFP", "Nemo"], how="left").fillna({"Monto": 0.0})

    siguiente = pos.assign(Mes=pos["Mes"] - 1).rename(columns={"Monto": "Monto_t1"})
    panel = panel.merge(siguiente, on=["Mes", "AFP", "Nemo"], how="left").fillna({"Monto_t1": 0.0})
    panel = panel.merge(calcular_benchmark(ag), on=["Mes", "Nemo"], how="left").fillna({"Benchmark": 0.0})

    panel["PesoAFP"] = panel["Monto"] / panel["RVL_AFP"]
    panel["GAP"] = panel["PesoAFP"] - panel["Benchmark"]
    panel["FlujoProyectado"] = -panel["GAP"] * panel["RVL_AFP"]
    panel["FlujoObservado"] = panel["Monto_t1"] - panel["Monto"]
    panel["Error"] = panel["FlujoObservado"] - panel["FlujoProyectado"]
    panel["ErrorAbs"] = panel["Error"].abs()
    panel["AciertoDir"] = np.sign(panel["FlujoProyectado"]) == np.sign(panel["FlujoObservado"])
    return panel, meses_est, excluidos


# =============================================================================
# Métricas
# =============================================================================
def metricas(p):
    """Métricas de desempeño del supuesto sobre un conjunto de observaciones."""
    est, obs = p["FlujoProyectado"], p["FlujoObservado"]
    con_pos = p["Monto"] > 0
    signos = np.sign(obs[obs != 0]).value_counts(normalize=True)
    rho = np.corrcoef(est, obs)[0, 1]
    mae, mae_sin_cambio = p["ErrorAbs"].mean(), obs.abs().mean()
    return pd.Series({
        "N": len(p),
        "MAE (MM CLP)": mae / MM,
        "Mediana error (MM CLP)": p["ErrorAbs"].median() / MM,
        "P90 error (MM CLP)": p["ErrorAbs"].quantile(0.90) / MM,
        "P99 error (MM CLP)": p["ErrorAbs"].quantile(0.99) / MM,
        "MAE escenario sin cambio (MM CLP)": mae_sin_cambio / MM,
        "MAE relativo (x)": mae / mae_sin_cambio,
        "Error % cartera accionaria (mediana, pp)": (p["ErrorAbs"] / p["RVL_AFP"]).median() * 100,
        "Error % posición (mediana, %)": (p.loc[con_pos, "ErrorAbs"] / p.loc[con_pos, "Monto"]).median() * 100,
        "Error relativo al flujo observado (mediana, %)": (p["ErrorAbs"] / obs.abs()).median() * 100,
        "Relación proporcional (x)": (est.abs() / obs.abs()).median(),
        "Acierto direccional (%)": p["AciertoDir"].mean() * 100,
        "Clase mayoritaria": {1.0: "Compra", -1.0: "Venta"}[signos.idxmax()],
        "Clase mayoritaria (%)": signos.max() * 100,
        "Correlación (rho)": rho,
        "R2": rho ** 2,
    })


def tabla_quintiles(p):
    """Q1 = mayor sobreponderación (GAP más positivo); Q5 = mayor subponderación."""
    q = p.copy()
    q["Quintil"] = pd.qcut((-q["GAP"]).rank(method="first"), 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
    return q.groupby("Quintil", observed=True).agg(
        N=("GAP", "size"),
        GAP_prom_pp=("GAP", lambda s: s.mean() * 100),
        FlujoProyectado_prom_MM=("FlujoProyectado", lambda s: s.mean() / MM),
        FlujoObservado_prom_MM=("FlujoObservado", lambda s: s.mean() / MM),
        Error_prom_MM=("ErrorAbs", lambda s: s.mean() / MM),
        AciertoDir_pct=("AciertoDir", lambda s: s.mean() * 100),
    ).reset_index()


def tabla_cierre_gap(p):
    """Fracción del GAP cerrada en el mes, por tramo de magnitud del GAP."""
    v = p[p["FlujoProyectado"] != 0].copy()
    v["Cierre"] = v["FlujoObservado"] / v["FlujoProyectado"]
    v["Tramo GAP (pp)"] = pd.cut(v["GAP"].abs() * 100, TRAMOS_GAP_PP)

    def resumen(d):
        return pd.Series({
            "N": len(d),
            "Acierto direccional (%)": (d["Cierre"] > 0).mean() * 100,
            "Cierre mediano cuando acierta (%)": d.loc[d["Cierre"] > 0, "Cierre"].median() * 100,
            "Cierre neto (%)": (d["FlujoObservado"] * np.sign(d["FlujoProyectado"])).sum()
                               / d["FlujoProyectado"].abs().sum() * 100,
        })

    return v.groupby("Tramo GAP (pp)", observed=True).apply(resumen, include_groups=False).reset_index()


# =============================================================================
# Gráficos
# =============================================================================
MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def mes_es(periodo):
    return f"{MESES_ES[periodo.month - 1]}-{periodo.year}"


def nota_pie(p, meses):
    return (f"Backtest mensual {mes_es(meses[0])} a {mes_es(meses[-1])} · {p['AFP'].nunique()} AFP · "
            f"{fmt_cl(len(p))} obs. AFP-Nemo-mes con movimiento · Fuente: SP, carteras agregadas y desagregadas")


def grafico_mae(p, nota, path):
    mae = p["ErrorAbs"].mean() / MM
    obs = p["FlujoObservado"].abs().mean() / MM
    fig, ax = plt.subplots(figsize=(8, 5.5))
    barras = ax.bar(["Flujo supuesto\n(MAE del modelo)", "Flujo observado\n(promedio en valor absoluto)"],
                    [mae, obs], color=[NAVY, CELESTE], width=0.55)
    for r, v in zip(barras, [mae, obs]):
        ax.text(r.get_x() + r.get_width() / 2, v * 1.02, fmt_cl(v) + " MM",
                ha="center", va="bottom", fontweight="bold")
    ax.set_ylabel("MM CLP")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: fmt_cl(x)))
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.set_ylim(0, mae * 1.12)
    ax.set_title("Error del modelo vs flujo real promedio")
    fig.text(0.01, 0.01, nota, fontsize=7.5, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=220)
    plt.close(fig)


def grafico_quintiles(q, nota, path):
    est = q["FlujoProyectado_prom_MM"].values
    obs = q["FlujoObservado_prom_MM"].values
    etiquetas = ["Q1\nMás sobreponderada", "Q2", "Q3", "Q4", "Q5\nMás subponderada"]
    x, w = np.arange(5), 0.38
    fig, ax = plt.subplots(figsize=(10, 6))
    b1 = ax.bar(x - w / 2, est, w, color=NAVY, label="Flujo supuesto")
    b2 = ax.bar(x + w / 2, obs, w, color=CELESTE, label="Flujo observado")
    for barras in (b1, b2):
        for r in barras:
            v = r.get_height()
            ax.text(r.get_x() + r.get_width() / 2, v + (250 if v >= 0 else -250), fmt_cl(v),
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=9)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x, [f"{e}\nGAP prom. {fmt_cl(g, 2)} pp" for e, g in zip(etiquetas, q["GAP_prom_pp"])])
    ax.set_ylabel("MM CLP (promedio por AFP-Nemo-mes)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_cl(v)))
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.set_ylim(est.min() * 1.25, est.max() * 1.25)
    ax.set_title("Flujo supuesto vs flujo observado por quintil de GAP")
    ax.legend(frameon=False, loc="upper left")
    fig.text(0.01, 0.01, nota + " · GAP = PesoAFP − Benchmark 6M", fontsize=7.5, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=220)
    plt.close(fig)


def grafico_boxplot(p, nota, path):
    err_pct = p["ErrorAbs"] / p["RVL_AFP"] * 100
    afps = sorted(p["AFP"].unique())
    datos = [err_pct.clip(lower=1e-4).values] + \
            [err_pct[p["AFP"] == a].clip(lower=1e-4).values for a in afps]
    nombres = ["Total"] + [a.title() for a in afps]
    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.boxplot(datos, tick_labels=nombres, patch_artist=True, widths=0.55,
               medianprops=dict(color=CELESTE, lw=2),
               flierprops=dict(marker="o", ms=2.5, mfc=NAVY, mec="none", alpha=0.35),
               boxprops=dict(facecolor=NAVY, edgecolor=NAVY),
               whiskerprops=dict(color=NAVY), capprops=dict(color=NAVY))
    ax.set_yscale("log")
    ax.set_ylim(1e-3, 40)
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: fmt_cl(v, 3 if v < 0.01 else 2 if v < 0.1 else 1 if v < 1 else 0) + "%"))
    for i, d in enumerate(datos, 1):
        m = np.median(d)
        ax.text(i + 0.32, m, fmt_cl(m, 2) + "%", va="center", fontsize=8.5, color=NAVY, fontweight="bold")
    ax.axvline(1.5, color=GRID, lw=1)
    ax.grid(axis="y", color=GRID, which="major")
    ax.set_axisbelow(True)
    ax.set_ylabel("Error / cartera accionaria AFP (escala log)")
    ax.set_title("Error de estimación como % de la cartera accionaria de cada AFP")
    fig.text(0.01, 0.01, nota + " · Caja = P25–P75, línea celeste = mediana, puntos = outliers (>1,5×IQR)",
             fontsize=6.8, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=220)
    plt.close(fig)


# =============================================================================
# Ejecución
# =============================================================================
def main(agregadas, desagregadas, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    configurar_estilo()

    ag = cargar_agregadas(agregadas)
    de = cargar_desagregadas(desagregadas)
    panel, meses, excluidos = construir_panel(ag, de)
    mov = panel[panel["FlujoObservado"] != 0].copy()          # muestra evaluada

    # Validaciones
    suma_pesos = ag.groupby("Mes")["PesoSistema"].sum()
    validaciones = pd.Series({
        "Suma PesoSistema por mes, mín (%)": suma_pesos.min() * 100,
        "Suma PesoSistema por mes, máx (%)": suma_pesos.max() * 100,
        "Benchmark promedio (%)": mov["Benchmark"].mean() * 100,
        "Benchmark mediana (%)": mov["Benchmark"].median() * 100,
        "Benchmark máximo (%)": mov["Benchmark"].max() * 100,
        "Meses estimados": len(meses),
        "Primer mes": str(meses[0]),
        "Último mes": str(meses[-1]),
        "Meses excluidos (sin montos en t o t+1)": ", ".join(map(str, excluidos)),
        "Obs. grilla completa": len(panel),
        "Obs. con movimiento (evaluadas)": len(mov),
    })

    # Métricas
    resumen = pd.DataFrame({"Con movimiento": metricas(mov), "Grilla completa": metricas(panel)})
    por_afp = pd.DataFrame({a.title(): metricas(g) for a, g in mov.groupby("AFP")}).T
    por_afp.loc["Total"] = metricas(mov)
    quintiles = tabla_quintiles(mov)
    cierre = tabla_cierre_gap(mov)

    # Gráficos
    nota = nota_pie(mov, meses)
    grafico_mae(mov, nota, out_dir / "grafico1_mae_vs_flujo_real.png")
    grafico_quintiles(quintiles, nota, out_dir / "grafico2_quintiles.png")
    grafico_boxplot(mov, nota, out_dir / "grafico3_boxplot_error_pct.png")

    # Excel de resultados
    with pd.ExcelWriter(out_dir / "resultados_backtest.xlsx") as xw:
        validaciones.to_frame("Valor").to_excel(xw, sheet_name="Validaciones")
        resumen.to_excel(xw, sheet_name="Metricas")
        por_afp.to_excel(xw, sheet_name="Por_AFP")
        quintiles.to_excel(xw, sheet_name="Quintiles", index=False)
        cierre.assign(**{"Tramo GAP (pp)": cierre["Tramo GAP (pp)"].astype(str)}) \
              .to_excel(xw, sheet_name="Cierre_GAP", index=False)
        detalle = mov.drop(columns=["ErrorAbs"]).assign(Mes=mov["Mes"].astype(str))
        detalle.to_excel(xw, sheet_name="Detalle", index=False)

    # Resumen en consola
    m = resumen["Con movimiento"]
    print(f"\nBacktest {meses[0]} a {meses[-1]} · {fmt_cl(m['N'])} observaciones con movimiento")
    print(f"  MAE relativo:          {fmt_cl(m['MAE relativo (x)'], 2)}x")
    print(f"  MAE:                   {fmt_cl(m['MAE (MM CLP)'])} MM CLP "
          f"(escenario sin cambio: {fmt_cl(m['MAE escenario sin cambio (MM CLP)'])})")
    print(f"  Acierto direccional:   {fmt_cl(m['Acierto direccional (%)'], 1)}% "
          f"(clase mayoritaria {m['Clase mayoritaria']}: {fmt_cl(m['Clase mayoritaria (%)'], 1)}%)")
    print(f"  Relación proporcional: {fmt_cl(m['Relación proporcional (x)'], 1)}x")
    print(f"  Correlación:           {fmt_cl(m['Correlación (rho)'], 3)}")
    print(f"\nResultados en {out_dir.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest del supuesto de convergencia de flujos AFP en RVL.")
    parser.add_argument("--agregadas", default=DEFAULT_AGREGADAS, help="Cartera agregada SP (.xlsx)")
    parser.add_argument("--desagregadas", default=DEFAULT_DESAGREGADAS, help="Cartera desagregada SP (.csv)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Carpeta de salida")
    args = parser.parse_args()
    main(args.agregadas, args.desagregadas, args.out)
