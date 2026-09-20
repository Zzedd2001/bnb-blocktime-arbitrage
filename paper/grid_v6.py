#!/usr/bin/env python3
"""grid_v6.py — the full grid of windows and specifications (robustness appendix of the revised paper).

Same panels and code as main_spec.py (three core 0.05% pools, pool fixed effects, day-clustered standard errors):
  windows ±30 d, ±14 d, ±7 d × specifications {log σ + hour FE; + log L + log volume; + linear trend; RD jump (±30, ±14 only)}
  outcomes: log strict overshoot, log arbitrageur profit, log LPs' gross loss
plus the fake-fork placebos (pre-period split at its midpoint) for every window × specification.
Outputs: tables_v6/table_grid_overshoot.md (with elasticities, pooled elasticity and equality test),
         table_grid_profit_loss.md, table_grid_placebo.md, grid_v6.json
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
FORKS = ["Lorentz", "Maxwell", "Fermi"]
DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
LAW = {f: 0.5 * np.log(d1 / d0) for f, (d0, d1) in DT.items()}
LNR = {f: np.log(d1 / d0) for f, (d0, d1) in DT.items()}
FAKE = {("Lorentz", 30): "2025-04-14 05:02", ("Lorentz", 14): "2025-04-22 05:32", ("Maxwell", 30): "2025-06-15 02:15", ("Maxwell", 14): "2025-06-23 02:45",
        ("Fermi", 30): "2025-12-30 02:15", ("Fermi", 14): "2026-01-07 02:45"}
OUT = ROOT + "/paper/tables_v6"
um = lambda s: str(s).replace("-", "−")
SPECS = [("log σ + hour FE", "", ""), ("+ log L + log volume", " + np.log(liq_mean) + np.log(volume)", ""),
         ("+ linear trend", " + np.log(liq_mean) + np.log(volume) + t_days", ""),
         ("RD jump (separate slopes)", " + np.log(liq_mean) + np.log(volume)", " + t_days + post:t_days")]
WINDOWS = [30, 14, 7]
OUTC = [("Overshoot", "overshoot_strict_bps"), ("Arb profit", "arb_profit"), ("LP loss", "arb_loss")]


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def load(fork):
    d = pd.read_parquet(ROOT + f"/{fork.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet")
    return d[d["pool"].isin(CORE)].copy()


def prep(d, y, days):
    d = d[(d.t_days >= -days) & (d.t_days < days)]
    d = d[(d[y] > 0) & (d["sigma_ps"] > 0) & (d["liq_mean"] > 0) & (d["volume"] > 0)].copy()
    d["yy"] = np.log(d[y])
    return d


def fit(d, y, days, extra, rhs):
    d = prep(d, y, days)
    f = "yy ~ post + np.log(sigma_ps) + C(hod) + C(pool)" + extra + rhs
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return {"b": float(m.params["post"]), "se": float(m.bse["post"]), "p": float(m.pvalues["post"]), "n": int(m.nobs)}


def placebo(d, y, days, extra, rhs):
    """fake fork at the midpoint of the pre-period of the window; RD variant uses separate slopes around the fake fork."""
    d = prep(d, y, days)
    d = d[d["post"] == 0].copy()
    d["fake"] = (d["t_days"] >= -days / 2).astype(int)
    d["tf"] = d["t_days"] + days / 2
    ex = extra.replace("t_days", "tf")
    rh = rhs.replace("post:t_days", "fake:tf").replace("t_days", "tf")
    f = "yy ~ fake + np.log(sigma_ps) + C(hod) + C(pool)" + ex + rh
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return {"b": float(m.params["fake"]), "se": float(m.bse["fake"]), "p": float(m.pvalues["fake"]), "n": int(m.nobs)}


def pooled(res):
    e = np.array([res[f]["b"] / LNR[f] for f in FORKS])
    s = np.array([res[f]["se"] / abs(LNR[f]) for f in FORKS])
    w = 1 / s ** 2
    eb = float((w * e).sum() / w.sum())
    se = float(np.sqrt(1 / w.sum()))
    chi = float((w * (e - eb) ** 2).sum())
    return e, eb, se, (eb - 0.5) / se, float(1 - stats.chi2.cdf(chi, 2))


P = {f: load(f) for f in FORKS}
R, PL = {}, {}
for days in WINDOWS:
    for sname, extra, rhs in SPECS:
        if days == 7 and rhs:
            continue
        for lab, y in OUTC:
            for f in FORKS:
                R[(days, sname, y, f)] = fit(P[f], y, days, extra, rhs)
                if days in (30, 14):
                    PL[(days, sname, y, f)] = placebo(P[f], y, days, extra, rhs)

rows_o, rows_pl_, rows_p = [], [], []
for days in WINDOWS:
    for sname, extra, rhs in SPECS:
        if days == 7 and rhs:
            continue
        r = {"Window": f"±{days} d", "Specification": sname}
        res = {f: R[(days, sname, "overshoot_strict_bps", f)] for f in FORKS}
        for f in FORKS:
            x = res[f]
            r[f"{f} β [share]"] = um(f"{x['b']:+.3f}{star(x['p'])} ({x['se']:.3f}) [{x['b'] / LAW[f]:.0%}]")
        e, eb, se, t, pe = pooled(res)
        r["Elasticity L / M / F"] = um(" / ".join(f"{v:.2f}" for v in e))
        r["Pooled elasticity"] = um(f"{eb:.3f} ({se:.3f})")
        r["t vs 0.5"] = um(f"{t:.1f}")
        r["Equal (p)"] = f"{pe:.2f}"
        rows_o.append(r)
        r2 = {"Window": f"±{days} d", "Specification": sname}
        for f in FORKS:
            for lab, y in OUTC[1:]:
                x = R[(days, sname, y, f)]
                r2[f"{f}: {lab.lower()}"] = um(f"{x['b']:+.3f}{star(x['p'])} ({x['se']:.3f})")
        rows_pl_.append(r2)
        if days in (30, 14):
            for f in FORKS:
                r3 = {"Fork": f, "Window": f"±{days} d", "Fake fork (UTC)": FAKE[(f, days)], "Specification": sname}
                for lab, y in OUTC:
                    x = PL[(days, sname, y, f)]
                    r3[lab] = um(f"{x['b']:+.3f}{star(x['p'])} ({x['se']:.3f})")
                rows_p.append(r3)
rows_p.sort(key=lambda r: (FORKS.index(r["Fork"]), -int(r["Window"][1:-2]), [s[0] for s in SPECS].index(r["Specification"])))
pd.DataFrame(rows_o).pipe(lambda t: open(f"{OUT}/table_grid_overshoot.md", "w").write(t.to_markdown(index=False, disable_numparse=True)))
pd.DataFrame(rows_pl_).pipe(lambda t: open(f"{OUT}/table_grid_profit_loss.md", "w").write(t.to_markdown(index=False, disable_numparse=True)))
pd.DataFrame(rows_p).pipe(lambda t: open(f"{OUT}/table_grid_placebo.md", "w").write(t.to_markdown(index=False, disable_numparse=True)))
json.dump({"estimates": {"|".join(map(str, k)): v for k, v in R.items()}, "placebos": {"|".join(map(str, k)): v for k, v in PL.items()}},
          open(f"{OUT}/grid_v6.json", "w"), indent=1)
print(open(f"{OUT}/table_grid_overshoot.md").read())
print()
print(open(f"{OUT}/table_grid_profit_loss.md").read())
print()
print(open(f"{OUT}/table_grid_placebo.md").read())
