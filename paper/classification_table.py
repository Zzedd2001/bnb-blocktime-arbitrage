#!/usr/bin/env python3
"""classification_table.py — sensitivity of the fork effect to the arbitrage classification (referee M4).

Four definitions of the arbitrage overshoot, estimated with the same specifications on the same pool-hours
(three core 0.05% pools pooled with pool fixed effects, day-clustered standard errors):
  all      : all identified arbitrages (|dev_pre| > γ, trade toward the reference)          — hourly_panel overshoot_bps
  strict   : strict arbitrages (post-trade deviation inside the band)                        — hourly_panel overshoot_strict_bps (= Table 4)
  bot      : strict arbitrages of arbitrage contracts, public routers excluded (bot flow)    — component panels (bots) overshoot_all
  cex      : CEX-triggered bot arbitrages only (responses to a reference-price crossing)     — component panels (bots) cex
Specifications: the pre-registered main design (RD jump with separate slopes, ±30 d) and the other placebo-clean
designs (±30 d linear trend; ±14 d liquidity and volume; ±14 d linear trend).
Outputs: tables_v6/table_classification.md (main spec) and table_classification_full.md (all four specs), classification.json
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
FORKS = ["Lorentz", "Maxwell", "Fermi"]
DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
LAW = {f: 0.5 * np.log(d1 / d0) for f, (d0, d1) in DT.items()}
SPECS = [("RD jump, ±30 d (main)", 30, " + np.log(liq_mean) + np.log(volume)", " + t_days + post:t_days"),
         ("linear trend, ±30 d", 30, " + np.log(liq_mean) + np.log(volume) + t_days", ""),
         ("liquidity and volume, ±14 d", 14, " + np.log(liq_mean) + np.log(volume)", ""),
         ("linear trend, ±14 d", 14, " + np.log(liq_mean) + np.log(volume) + t_days", "")]
OUT = ROOT + "/paper/tables_v6"
os.makedirs(OUT, exist_ok=True)
um = lambda s: str(s).replace("-", "−")


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def load_main(fork):
    d = pd.read_parquet(ROOT + f"/{fork.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet")
    d = d[d["pool"].isin(CORE)].copy()
    return d


def load_bots(fork):
    frames = []
    for p in CORE:
        x = pd.read_csv(ROOT + f"/arb_resp/comp_bots/{fork}/arb_response_bots/component_panels/{p}.csv")
        x["pool"] = p
        frames.append(x)
    d = pd.concat(frames, ignore_index=True)
    return d


def fit(d, y, extra, rhs, days):
    d = d[(d.t_days >= -days) & (d.t_days < days)]
    d = d[(d[y] > 0) & (d["sigma_ps"] > 0) & (d["liq_mean"] > 0) & (d["volume"] > 0)].copy()
    d["yy"] = np.log(d[y])
    f = "yy ~ post + np.log(sigma_ps) + C(hod) + C(pool)" + extra + rhs
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return float(m.params["post"]), float(m.bse["post"]), float(m.pvalues["post"]), int(m.nobs)


DEFS = [("All identified arbitrages", "main", "overshoot_bps"), ("Strict arbitrages (headline)", "main", "overshoot_strict_bps"),
        ("Strict arbitrages, bot flow (public routers excluded)", "bots", "overshoot_all"),
        ("CEX-triggered bot arbitrages", "bots", "cex")]
res = {}
panels = {f: {"main": load_main(f), "bots": load_bots(f)} for f in FORKS}
for sname, days, extra, rhs in SPECS:
    for dname, src, col in DEFS:
        for f in FORKS:
            res[(sname, dname, f)] = fit(panels[f][src], col, extra, rhs, days)


def table(specs):
    rows = []
    for sname, days, extra, rhs in specs:
        for dname, src, col in DEFS:
            r = {"Specification": sname, "Arbitrage definition": dname}
            for f in FORKS:
                b, se, p, n = res[(sname, dname, f)]
                r[f"{f}: β (s.e.) [share of law]"] = um(f"{b:+.3f}{star(p)} ({se:.3f}) [{b / LAW[f]:.0%}]")
            rows.append(r)
    return pd.DataFrame(rows)


T1 = table(SPECS[:1])
T2 = table(SPECS)
open(f"{OUT}/table_classification.md", "w").write(T1.to_markdown(index=False, disable_numparse=True))
open(f"{OUT}/table_classification_full.md", "w").write(T2.to_markdown(index=False, disable_numparse=True))
json.dump({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in res.items()}, open(f"{OUT}/classification.json", "w"), indent=1)
print(T2.to_markdown(index=False, disable_numparse=True))
