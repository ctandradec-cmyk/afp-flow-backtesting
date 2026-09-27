"""
Backtesting estimación de flujos AFP bajo el supuesto duro de herding.

Uso:  python backtest_flujos_afp.py Agregadas.xlsx Desagregadas.csv [salida.xlsx]

Lógica por mes de estimación t (misma que el Excel):
  MontoSistema_{n,t} = Total (= Total_MMQ * Precio * 1e6)
  AccNac_t           = SUM Total de TODOS los Nemos de t        (denominador correcto, 100%)
  PesoSistema_{n,t}  = MontoSistema / AccNac
  Benchmark_{n,t}    = promedio PesoSistema t-1..t-6 (meses disponibles, como AVERAGEIFS);
                       0 si no hay historia (BUSCARX(...;0))
  Grilla             = Nemos de la agregada en t  x  AFPs  (SUMAR.SI.CONJUNTO => 0 si no lo tiene)
  RVL_{a,t}          = SUM Monto de la AFP en t (todos sus Nemos)
  PesoAFP            = Monto_{a,n,t} / RVL_{a,t}
  GAP (convención Excel) = PesoAFP - Benchmark      (+ sobreponderada, - corta)
  FlujoEstimado      = -GAP * RVL = (Benchmark - PesoAFP) * RVL   (+ compra, - venta)
  FlujoObservado     = Monto_{a,n,t+1} - Monto_{a,n,t}            (0 si no está)
Meses excluidos: aquellos donde t o t+1 no tiene Monto válido (RVL de la AFP = 0 -> #DIV/0!)
"""
import sys
import numpy as np
import pandas as pd

MM = 1e6
AFPS = ["CAPITAL", "CUPRUM", "HABITAT", "MODELO", "PLANVITAL", "PROVIDA", "UNO"]


def _num(s):
    s = s.astype(str).str.strip()
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s.replace({"-": "0", "": "0", "nan": np.nan}), errors="coerce")


def load_agregadas(path):
    ag = pd.read_excel(path)
    ag["Nemo"] = ag["Nemo"].astype(str).str.strip()
    ag["MontoSistema"] = ag["Total_MMQ"] * ag["Precio"] * 1e6          # = col. Total
    ag["AccNac"] = ag.groupby("Fecha")["MontoSistema"].transform("sum")
    ag["PesoSistema"] = ag["MontoSistema"] / ag["AccNac"]
    ag["Mes"] = ag["Fecha"].dt.to_period("M")
    return ag


def load_desagregadas(path):
    de = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str)
    de.columns = [c.strip() for c in de.columns]
    if "Administrador" in de.columns and "AFP" not in de.columns:
        de = de.rename(columns={"Administrador": "AFP"})
    de["AFP"] = de["AFP"].str.strip().str.upper()
    de["Nemo"] = de["Nemo"].str.strip()
    de["Monto"] = _num(de["Monto"]).fillna(0.0)                       # '-' = 0, no se reemplaza
    de["Mes"] = pd.to_datetime(de["Fecha"], format="%d-%m-%Y").dt.to_period("M")
    return de[de["AFP"].isin(AFPS)].copy()                             # excluye 'INDUSTRIA AFP'


def benchmark(ag):
    piv = ag.pivot(index="Mes", columns="Nemo", values="PesoSistema").sort_index()
    piv = piv.reindex(pd.period_range(piv.index.min(), piv.index.max(), freq="M"))
    b = piv.shift(1).rolling(6, min_periods=1).mean()
    return b.stack().rename("Benchmark").reset_index().rename(columns={"level_0": "Mes"})


def build_panel(ag, de):
    pos = de.groupby(["Mes", "AFP", "Nemo"], as_index=False)["Monto"].sum()
    rvl = pos.groupby(["Mes", "AFP"], as_index=False)["Monto"].sum().rename(columns={"Monto": "RVL_AFP"})

    # meses válidos: todas las AFP con RVL > 0 y existe t+1 válido
    ok = rvl.groupby("Mes")["RVL_AFP"].min() > 0
    validos = set(ok[ok].index)
    meses_est = sorted(m for m in validos if (m + 1) in validos)
    excl = sorted(m for m in set(rvl["Mes"]) if m not in meses_est)

    grid = (ag[["Mes", "Nemo"]].drop_duplicates()
            .merge(rvl, on="Mes"))                                    # Nemos agregada x AFPs
    grid = grid[grid["Mes"].isin(meses_est)]
    grid = grid.merge(pos, on=["Mes", "AFP", "Nemo"], how="left").fillna({"Monto": 0.0})
    nxt = pos.assign(Mes=pos["Mes"] - 1).rename(columns={"Monto": "Monto_t1"})
    grid = grid.merge(nxt, on=["Mes", "AFP", "Nemo"], how="left").fillna({"Monto_t1": 0.0})
    grid = grid.merge(benchmark(ag), on=["Mes", "Nemo"], how="left").fillna({"Benchmark": 0.0})

    grid["PesoAFP"] = grid["Monto"] / grid["RVL_AFP"]
    grid["GAP"] = grid["PesoAFP"] - grid["Benchmark"]
    grid["FlujoEstimado"] = -grid["GAP"] * grid["RVL_AFP"]
    grid["FlujoObservado"] = grid["Monto_t1"] - grid["Monto"]
    grid["Tenencia_t"] = np.where(grid["Monto"] > 0, "Con posición en t", "Sin posición en t (cero Excel)")
    grid["AbsErr"] = (grid["FlujoEstimado"] - grid["FlujoObservado"]).abs()
    grid["AciertoDir"] = np.sign(grid["FlujoEstimado"]) == np.sign(grid["FlujoObservado"])
    return grid, meses_est, excl


def metricas(p):
    e, o = p["FlujoEstimado"], p["FlujoObservado"]
    nz = o != 0
    return pd.Series({
        "N": len(p),
        "MAE (MM CLP)": p["AbsErr"].mean() / MM,
        "Mediana (MM CLP)": p["AbsErr"].median() / MM,
        "P90 (MM CLP)": p["AbsErr"].quantile(.9) / MM,
        "P99 (MM CLP)": p["AbsErr"].quantile(.99) / MM,
        "Error rel. medio (% RVL AFP)": (p["AbsErr"] / p["RVL_AFP"]).mean() * 100,
        "Error rel. mediano (% RVL AFP)": (p["AbsErr"] / p["RVL_AFP"]).median() * 100,
        "Acierto direccional (%)": p["AciertoDir"].mean() * 100,
        "Acierto dir. si Obs≠0 (%)": p.loc[nz, "AciertoDir"].mean() * 100,
        "Corr(Est, Obs)": np.corrcoef(e, o)[0, 1],
        "MAE referencia 'flujo=0' (MM CLP)": o.abs().mean() / MM,
    })


def quintiles(p):
    p = p.copy()
    # Q1 = mayor sobreponderación (GAP más positivo) ... Q5 = mayor subponderación (GAP más negativo)
    p["Q"] = pd.qcut((-p["GAP"]).rank(method="first"), 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
    return p.groupby("Q", observed=True).agg(
        N=("GAP", "size"),
        GAP_prom_pct=("GAP", lambda s: s.mean() * 100),
        FlujoEst_prom_MM=("FlujoEstimado", lambda s: s.mean() / MM),
        FlujoObs_prom_MM=("FlujoObservado", lambda s: s.mean() / MM),
        Error_prom_MM=("AbsErr", lambda s: s.mean() / MM),
        Acierto_dir_pct=("AciertoDir", lambda s: s.mean() * 100)).reset_index()


def main(ag_path, de_path, out_path="resultados_backtest.xlsx"):
    ag, de = load_agregadas(ag_path), load_desagregadas(de_path)
    p, meses, excl = build_panel(ag, de)

    s = ag.groupby("Fecha")["PesoSistema"].sum()
    val = pd.Series({
        "V1 suma PesoSistema prom (%)": s.mean() * 100, "V1 min (%)": s.min() * 100, "V1 max (%)": s.max() * 100,
        "V2 benchmark prom (%)": p["Benchmark"].mean() * 100, "V2 mediana (%)": p["Benchmark"].median() * 100,
        "V2 max (%)": p["Benchmark"].max() * 100,
        "Suma PesoAFP (grilla) min (%)": p.groupby(["Mes", "AFP"])["PesoAFP"].sum().min() * 100,
        "Suma PesoAFP (grilla) max (%)": p.groupby(["Mes", "AFP"])["PesoAFP"].sum().max() * 100,
        "Meses estimados": len(meses), "Desde": str(meses[0]), "Hasta": str(meses[-1]),
        "Meses excluidos": ", ".join(map(str, excl)),
    })
    met = pd.DataFrame({"Total": metricas(p)})
    for k, g in p.groupby("Tenencia_t"):
        met[k] = metricas(g)
    por_afp = pd.DataFrame({a: metricas(g) for a, g in p.groupby("AFP")}).T
    q_all = quintiles(p)
    q_pos = quintiles(p[p["Monto"] > 0])

    with pd.ExcelWriter(out_path) as xw:
        val.to_frame("Valor").to_excel(xw, sheet_name="Validaciones")
        met.to_excel(xw, sheet_name="Metricas")
        q_all.to_excel(xw, sheet_name="Quintiles", index=False)
        q_pos.to_excel(xw, sheet_name="Quintiles_con_posicion", index=False)
        por_afp.to_excel(xw, sheet_name="Por_AFP")
        d = p.drop(columns=["AbsErr"]).copy(); d["Mes"] = d["Mes"].astype(str)
        d.to_excel(xw, sheet_name="Detalle", index=False)
    return p, val, met, q_all, q_pos, por_afp


if __name__ == "__main__":
    main(*sys.argv[1:])
