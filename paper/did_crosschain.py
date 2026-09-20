#!/usr/bin/env python3
"""did_crosschain.py — cross-chain control panel for the three BNB Chain forks (referee M2).

Stacks the treated hourly panels (PancakeSwap v3 core pools on BNB Chain, trade reference) with control panels of
the same asset pairs on another chain whose block interval did not change (e.g. Uniswap v3 on Ethereum, 12-second
slots), built by the same pipeline with the same Binance reference over the same ±30-day windows, and estimates

  (i)  the main specification on the control panel alone — the "jump" a market-wide shock at the fork date would
       produce on a chain that was not treated (the cleanest placebo for the before–after design);
  (ii) the difference-in-differences with chain-specific trends:
       log y = β·Post×Treated + λ·Post + δ·log σ + κ'X + (t + Post·t)×Treated + (t + Post·t) + hour FE + pool FE,
       standard errors clustered by calendar day; β is the DiD estimate of the fork effect.

Control panels are read from  <ROOT>/<fork>_ctrl/bundle/analysis_agg/hourly_panel.parquet  (produced by
full_analysis.py on the control chain's run_pilot output, with the BNB fork date as the "fork"); the pool names of
the control pools are given with --control-pools (they need not match the treated names).

    python3 did_crosschain.py [--control-dir-suffix _ctrl] [--control-pools ETH-USDT-500 WBTC-USDT-500]

Outputs: tables_v6/table_did_crosschain.md, did_crosschain.json
"""
from __future__ import annotations
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import argparse
import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = os.environ.get("REPL_ROOT", ROOT + "")
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
FORKS = ["Lorentz", "Maxwell", "Fermi"]
LAW = {"Lorentz": -0.3466, "Maxwell": -0.3466, "Fermi": -0.2554}
OUT = f"{ROOT}/paper/tables_v6"
OUTCOMES = [("Overshoot at strict arbitrage", "overshoot_strict_bps"), ("Overshoot at all identified arbitrages", "overshoot_bps"),
            ("Arbitrageur profit", "arb_profit"), ("LPs' gross loss (block timestamp)", "arb_loss"),
            ("LPs' gross loss (30 s mark-out)", "arb_loss_30s"), ("Identified arbitrages per hour", "n_arb")]
um = lambda s: str(s).replace("-", "−")


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def load(path, pools, treated):
    d = pd.read_parquet(path)
    d = d[d["pool"].isin(pools)].copy()
    d["arb_loss_30s"] = d["fee_income"] - d["markout_30s"]
    d["treated"] = int(treated)
    d["pool"] = d["pool"] + ("" if treated else "_ctrl")
    return d


def prep(d, y):
    d = d[(d.t_days >= -30) & (d.t_days < 30)]
    d = d[(d[y] > 0) & (d["sigma_ps"] > 0) & (d["liq_mean"] > 0) & (d["volume"] > 0)].copy()
    d["yy"] = np.log(d[y])
    return d


def fit_single(d, y):
    d = prep(d, y)
    f = "yy ~ post + np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + t_days + post:t_days + C(hod) + C(pool)"
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return {"b": float(m.params["post"]), "se": float(m.bse["post"]), "p": float(m.pvalues["post"]), "n": int(m.nobs)}


def fit_did(d, y):
    d = prep(d, y)
    f = ("yy ~ post:treated + post + np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + t_days + post:t_days"
         " + t_days:treated + post:t_days:treated + C(hod) + C(pool)")
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return {"b": float(m.params["post:treated"]), "se": float(m.bse["post:treated"]), "p": float(m.pvalues["post:treated"]),
            "control_post": float(m.params["post"]), "control_post_se": float(m.bse["post"]), "n": int(m.nobs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control-dir-suffix", default="_ctrl", help="control panels at <ROOT>/<fork><suffix>/bundle/analysis_agg/hourly_panel.parquet")
    ap.add_argument("--control-pools", nargs="+", default=["ETH-USDT-500", "WBTC-USDT-500"])
    ap.add_argument("--treated-pools", nargs="+", default=CORE)
    ap.add_argument("--tag", default="crosschain")
    a = ap.parse_args()
    rows, res = [], {}
    for fork in FORKS:
        tp = f"{ROOT}/{fork.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet"
        cp = f"{ROOT}/{fork.lower()}{a.control_dir_suffix}/bundle/analysis_agg/hourly_panel.parquet"
        if not os.path.exists(cp):
            print(f"{fork}: no control panel at {cp} — skipped")
            continue
        T = load(tp, a.treated_pools, True)
        C = load(cp, a.control_pools, False)
        S = pd.concat([T, C], ignore_index=True)
        for label, col in OUTCOMES:
            try:
                t1, c1, dd = fit_single(T, col), fit_single(C, col), fit_did(S, col)
            except Exception as e:  # thin control pools can lack an outcome
                print(f"{fork} {label}: {e}")
                continue
            res[f"{label}|{fork}"] = {"treated": t1, "control": c1, "did": dd}
            share = f" [{dd['b'] / LAW[fork]:.0%}]" if "Overshoot" in label or col == "arb_profit" else ""
            rows.append({"Fork": fork, "Outcome": label,
                         "Treated (main spec.)": um(f"{t1['b']:+.3f}{star(t1['p'])} ({t1['se']:.3f})"),
                         "Control alone": um(f"{c1['b']:+.3f}{star(c1['p'])} ({c1['se']:.3f})"),
                         "DiD (Post × Treated)": um(f"{dd['b']:+.3f}{star(dd['p'])} ({dd['se']:.3f}){share}"),
                         "N (stacked)": f"{dd['n']:,}"})
    if rows:
        os.makedirs(OUT, exist_ok=True)
        T = pd.DataFrame(rows)
        open(f"{OUT}/table_did_{a.tag}.md", "w").write(T.to_markdown(index=False, disable_numparse=True))
        json.dump(res, open(f"{OUT}/did_{a.tag}.json", "w"), indent=1)
        print(T.to_string())


if __name__ == "__main__":
    main()
