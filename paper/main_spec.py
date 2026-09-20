#!/usr/bin/env python3
"""main_spec.py — the pre-specified main specification of the revised paper (referee M1, M4, M6).

Main specification: RD-style jump at the fork with separate pre- and post-fork slopes, ±30-day window,
log y ~ Post + log σ + log L + log volume + t + Post×t + hour-of-day FE + pool FE, three core 0.05% pools,
standard errors clustered by calendar day.  Applied uniformly to the three forks and to every outcome:
  overshoot at strict arbitrage (headline), at all identified arbitrages, of bot flow (public routers excluded),
  of CEX-triggered bot arbitrages; arbitrageur profit; LPs' gross loss marked at the block timestamp and at t+30 s;
  number of arbitrages per hour; loss per identified arbitrage; the components J and M of CEX-triggered arbitrages.
Also: the fake-fork placebo of the same specification (pre-period split at its midpoint, RD around the fake fork),
the pre-fork slope, elasticities to Δt with their inverse-variance pooling and a χ² test of equality across forks.
Outputs: tables_v6/table_main.md, table_main_components.md, main_spec.json
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
OUT = ROOT + "/paper/tables_v6"
os.makedirs(OUT, exist_ok=True)
um = lambda s: str(s).replace("-", "−")


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def load_main(fork):
    d = pd.read_parquet(ROOT + f"/{fork.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet")
    d = d[d["pool"].isin(CORE)].copy()
    d["arb_loss_30s"] = d["fee_income"] - d["markout_30s"]
    return d


def load_bots(fork):
    frames = []
    for p in CORE:
        x = pd.read_csv(ROOT + f"/arb_resp/comp_bots/{fork}/arb_response_bots/component_panels/{p}.csv")
        x["pool"] = p
        frames.append(x)
    return pd.concat(frames, ignore_index=True)


def prep(d, y):
    d = d[(d.t_days >= -30) & (d.t_days < 30)]
    d = d[(d[y] > 0) & (d["sigma_ps"] > 0) & (d["liq_mean"] > 0) & (d["volume"] > 0)].copy()
    d["yy"] = np.log(d[y])
    return d


def fit_main(d, y):
    d = prep(d, y)
    f = "yy ~ post + np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + t_days + post:t_days + C(hod) + C(pool)"
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return {"b": float(m.params["post"]), "se": float(m.bse["post"]), "p": float(m.pvalues["post"]), "n": int(m.nobs),
            "pre_slope": float(m.params["t_days"]), "pre_slope_se": float(m.bse["t_days"]),
            "slope_change": float(m.params["post:t_days"]), "slope_change_se": float(m.bse["post:t_days"])}


def fit_placebo(d, y):
    """fake fork at the midpoint of the 30-day pre-period; RD with separate slopes around it (±15 d)."""
    d = prep(d, y)
    d = d[d["post"] == 0].copy()
    d["fake"] = (d["t_days"] >= -15).astype(int)
    d["tf"] = d["t_days"] + 15.0
    f = "yy ~ fake + np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + tf + fake:tf + C(hod) + C(pool)"
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return {"b": float(m.params["fake"]), "se": float(m.bse["fake"]), "p": float(m.pvalues["fake"]), "n": int(m.nobs)}


def pooled(res):
    """elasticities β/ln(Δt1/Δt0), inverse-variance pooled mean, t against 0.5 and χ²(2) equality test."""
    e = np.array([res[f]["b"] / LNR[f] for f in FORKS])
    s = np.array([res[f]["se"] / abs(LNR[f]) for f in FORKS])
    w = 1 / s ** 2
    eb = float((w * e).sum() / w.sum())
    se = float(np.sqrt(1 / w.sum()))
    chi = float((w * (e - eb) ** 2).sum())
    return {"elast": e.tolist(), "elast_se": s.tolist(), "pooled": eb, "pooled_se": se, "t_vs_half": (eb - 0.5) / se,
            "chi2_equal": chi, "p_equal": float(1 - stats.chi2.cdf(chi, 2))}


OUTCOMES = [  # (label, source, column, kind)  kind: "over" (elasticity rows), "other"
    ("Overshoot at strict arbitrage (headline)", "main", "overshoot_strict_bps", "over"),
    ("Overshoot at all identified arbitrages", "main", "overshoot_bps", "over"),
    ("Strict overshoot, bot flow (public routers excluded)", "bots", "overshoot_all", "over"),
    ("Overshoot of CEX-triggered bot arbitrages", "bots", "cex", "over"),
    ("Arbitrageur profit", "main", "arb_profit", "other"),
    ("LPs' gross loss, marked at the block timestamp", "main", "arb_loss", "other"),
    ("LPs' gross loss, marked 30 s after the block", "main", "arb_loss_30s", "other"),
    ("Identified arbitrages per hour", "main", "n_arb", "other"),
    ("Loss per identified arbitrage", "main", "loss_per_arb", "other"),
]
COMPONENTS = [("CEX-triggered, total", "bots", "cex"), ("Jump at the crossing (J)", "bots", "cex_jump"),
              ("Movement during τ (M)", "bots", "cex_move"), ("Continuation", "bots", "continuation"),
              ("Same-block back-run", "bots", "same_block")]

panels = {f: {"main": load_main(f), "bots": load_bots(f)} for f in FORKS}
res, plc = {}, {}
for label, src, col, kind in OUTCOMES + [(a, b, c, "comp") for a, b, c in COMPONENTS]:
    for f in FORKS:
        res[(label, f)] = fit_main(panels[f][src], col)
        plc[(label, f)] = fit_placebo(panels[f][src], col)

PRED_PROFIT = LAW
rows, rows_p = [], []
for label, src, col, kind in OUTCOMES:
    r = {"Outcome": label}
    for f in FORKS:
        x = res[(label, f)]
        share = f" [{x['b'] / LAW[f]:.0%}]" if kind == "over" or col == "arb_profit" else ""
        r[f"{f}: β (s.e.) [share of law]"] = um(f"{x['b']:+.3f}{star(x['p'])} ({x['se']:.3f}){share}")
    if kind == "over":
        q = pooled({f: res[(label, f)] for f in FORKS})
        r["Elasticity L / M / F"] = um(" / ".join(f"{v:.2f}" for v in q["elast"]))
        r["Pooled elasticity (s.e.)"] = um(f"{q['pooled']:.3f} ({q['pooled_se']:.3f})")
        r["t vs 0.5"] = um(f"{q['t_vs_half']:.1f}")
        r["Equal (p)"] = f"{q['p_equal']:.2f}"
        res[(label, "pooled")] = q
    else:
        r["Elasticity L / M / F"] = r["Pooled elasticity (s.e.)"] = r["t vs 0.5"] = r["Equal (p)"] = ""
    rows.append(r)
    rp = {"Outcome": label}
    for f in FORKS:
        x = plc[(label, f)]
        rp[f"{f}: β (s.e.) [share of law]"] = um(f"{x['b']:+.3f}{star(x['p'])} ({x['se']:.3f})")
    rp["Elasticity L / M / F"] = rp["Pooled elasticity (s.e.)"] = rp["t vs 0.5"] = rp["Equal (p)"] = ""
    rows_p.append(rp)
T = pd.DataFrame(rows)
P = pd.DataFrame(rows_p)
P["Outcome"] = "Placebo: " + P["Outcome"]

# pre-fork slopes of the headline outcome and of profit / loss
slopes = {f: {k: res[(lab, f)] for lab, k in [("Overshoot at strict arbitrage (headline)", "overshoot"), ("Arbitrageur profit", "profit"),
                                              ("LPs' gross loss, marked at the block timestamp", "loss")]} for f in FORKS}
srow = {"Outcome": "Pre-fork slope of the strict overshoot (per day)"}
for f in FORKS:
    x = slopes[f]["overshoot"]
    srow[f"{f}: β (s.e.) [share of law]"] = um(f"{x['pre_slope']:+.4f} ({x['pre_slope_se']:.4f})")
srow["Elasticity L / M / F"] = srow["Pooled elasticity (s.e.)"] = srow["t vs 0.5"] = srow["Equal (p)"] = ""

full = pd.concat([T, P, pd.DataFrame([srow])], ignore_index=True)
open(f"{OUT}/table_main.md", "w").write(full.to_markdown(index=False, disable_numparse=True))

# components under the main specification
crow = []
for label, src, col in COMPONENTS:
    r = {"Component": label}
    for f in FORKS:
        x = res[(label, f)]
        r[f"{f}: β (s.e.)"] = um(f"{x['b']:+.3f}{star(x['p'])} ({x['se']:.3f})")
        y = plc[(label, f)]
        r[f"{f}: placebo"] = um(f"{y['b']:+.3f}{star(y['p'])} ({y['se']:.3f})")
    crow.append(r)
C = pd.DataFrame(crow)
open(f"{OUT}/table_main_components.md", "w").write(C.to_markdown(index=False, disable_numparse=True))

json.dump({"main": {f"{k[0]}|{k[1]}": v for k, v in res.items()}, "placebo": {f"{k[0]}|{k[1]}": v for k, v in plc.items()}},
          open(f"{OUT}/main_spec.json", "w"), indent=1)
print(full.to_markdown(index=False, disable_numparse=True))
print()
print(C.to_markdown(index=False, disable_numparse=True))
