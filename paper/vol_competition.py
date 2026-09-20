#!/usr/bin/env python3
"""vol_competition.py — does arbitrage competition respond to volatility within the hour? (referee M3)

For the three core 0.05% pools and the three forks, build an hourly panel of the response-time and
competition statistics of CEX-triggered bot arbitrages (public routers excluded) and estimate their
elasticity to the hour's Binance realised volatility σ within each block-interval regime
(log y ~ log σ + hour-of-day FE + pool FE, day-clustered standard errors), plus the elasticity of the
overshoot components J and M.  Outputs: vol_competition.md, vol_competition.json, fig_vol_competition.png
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import glob
import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

CORE = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500"]
DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
PILOT = ROOT + "/dex-lit/bnb_blocktime_pilot"
OUT = os.path.dirname(os.path.abspath(__file__))

rows = []
for fork in DT:
    public = set(pd.read_csv(f"{PILOT}/public_contracts_{fork}.csv")["sender"].str.lower())
    panel = pd.read_parquet(ROOT + f"/{fork.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet")
    panel = panel[panel["pool"].isin(CORE)].copy()
    panel["hour_ts"] = pd.to_datetime(panel["hour"], utc=True).dt.tz_localize(None)
    for pool in CORE:
        A = pd.read_parquet(ROOT + f"/arb_resp/ops/{fork}/arb_response/operators/{pool}_arbs_tx.parquet")
        A = A[A["days_from_fork"].abs() <= 30]
        A = A[~A["sender"].str.lower().isin(public)]
        A["hour_ts"] = pd.to_datetime(A["ts_ms"], unit="ms").dt.floor("h")
        c = A[(A["trigger"] == "cex") & A["tau_ms"].between(0, 60_000)]
        g = c.groupby("hour_ts")
        h = pd.DataFrame({
            "n_cex": g.size(),
            "tau_p10": g["tau_ms"].quantile(0.10),
            "tau_med": g["tau_ms"].median(),
            "sqrt_tau": g["tau_ms"].apply(lambda s: np.sqrt(s / 1000.0).mean()),
            "first_block": g["k_blocks"].apply(lambda s: (s == 1).mean()),
            "J": g["jump_bps"].mean(),
            "M": g["move_bps"].mean(),
            "overshoot_cex": g["overshoot_bps"].mean(),
        })
        ga = A.groupby("hour_ts")
        h["n_arbs"] = ga.size()
        h["n_senders"] = ga["sender"].nunique()
        h["top1_share"] = ga["sender"].apply(lambda s: s.value_counts(normalize=True).iloc[0])
        h["pool"] = pool
        h["fork"] = fork
        p = panel[panel["pool"] == pool].set_index("hour_ts")
        h = h.join(p[["sigma_ps", "post", "hod", "liq_mean", "volume", "day", "n_arb_strict"]], how="inner")
        h["regime"] = np.where(h["post"] == 1, "post", "pre")
        h["dt"] = np.where(h["post"] == 1, DT[fork][1], DT[fork][0])
        rows.append(h.reset_index())
H = pd.concat(rows, ignore_index=True)
H = H[(H["n_cex"] >= 20) & (H["sigma_ps"] > 0)].copy()
H["ell_med"] = H["tau_med"] - 0.5 * H["dt"] * 1000          # median response time net of the mechanical half-interval
H["ell_p10"] = H["tau_p10"] - 0.1 * H["dt"] * 1000
for c in ["sigma_ps", "tau_med", "tau_p10", "sqrt_tau", "n_senders", "n_arbs", "J", "M", "overshoot_cex", "volume", "liq_mean"]:
    H["log_" + c] = np.log(H[c].clip(lower=1e-9))
H.to_parquet(os.path.join(OUT, "vol_competition_panel.parquet"))


def fit(d, y, extra=""):
    m = smf.ols(f"{y} ~ log_sigma_ps {extra} + C(hod) + C(pool)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"]})
    return m.params["log_sigma_ps"], m.bse["log_sigma_ps"], int(m.nobs)


OUTCOMES = [("log_tau_med", "median response time τ (log)"), ("log_tau_p10", "10th-percentile τ (log)"),
            ("log_sqrt_tau", "E[√τ] (log)"), ("first_block", "share landing in the first block (level)"),
            ("log_n_senders", "active contracts in the hour (log)"), ("log_n_arbs", "bot arbitrages in the hour (log)"),
            ("top1_share", "share of the largest contract (level)"), ("log_M", "movement component M (log)"),
            ("log_J", "crossing jump J (log)"), ("log_overshoot_cex", "overshoot of CEX-triggered arbs (log)")]
res = {}
lines = ["# Arbitrage competition and volatility within the hour (three core pools, bot flow, CEX-triggered arbitrages)\n",
         "Elasticity (or level response for shares) of each hourly statistic to log σ within each block-interval regime; "
         "hour-of-day and pool fixed effects; day-clustered standard errors in parentheses. Hours with at least 20 CEX-triggered bot arbitrages.\n",
         "| Outcome | " + " | ".join(f"{f} {r}" for f in DT for r in ("pre", "post")) + " |",
         "|---|" + "---|" * 6]
for y, label in OUTCOMES:
    cells = []
    for fork in DT:
        for reg in ("pre", "post"):
            d = H[(H["fork"] == fork) & (H["regime"] == reg)]
            b, se, n = fit(d, y)
            cells.append(f"{b:+.2f} ({se:.2f})")
            res.setdefault(y, {})[f"{fork} {reg}"] = {"beta": b, "se": se, "n": n}
    lines.append(f"| {label} | " + " | ".join(cells) + " |")
# with volume and liquidity controls, pooled by fork with regime FE
lines.append("\nWith log volume and log liquidity added, pooled across the two regimes of each fork (regime fixed effect):\n")
lines.append("| Outcome | Lorentz | Maxwell | Fermi |")
lines.append("|---|---|---|---|")
for y, label in OUTCOMES:
    cells = []
    for fork in DT:
        d = H[H["fork"] == fork]
        b, se, n = fit(d, y, "+ log_volume + log_liq_mean + C(regime)")
        cells.append(f"{b:+.2f} ({se:.2f})")
        res.setdefault(y, {})[f"{fork} pooled+controls"] = {"beta": b, "se": se, "n": n}
    lines.append(f"| {label} | " + " | ".join(cells) + " |")

# terciles of σ within regime: medians of τ and first-block share
lines.append("\nMedian response time (ms) and first-block share by within-regime tercile of σ (hours pooled over the three pools):\n")
lines.append("| Regime | Δt (s) | τ median, low σ | mid | high | first block, low σ | mid | high | contracts/h, low | mid | high |")
lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
terc = {}
for fork in DT:
    for reg in ("pre", "post"):
        d = H[(H["fork"] == fork) & (H["regime"] == reg)].copy()
        d["terc"] = d.groupby("pool")["sigma_ps"].transform(lambda s: pd.qcut(s, 3, labels=["low", "mid", "high"]))
        t = d.groupby("terc", observed=True).agg(tau=("tau_med", "median"), fb=("first_block", "mean"), ns=("n_senders", "mean"))
        terc[f"{fork} {reg}"] = t.to_dict()
        lines.append(f"| {fork} {reg} | {d['dt'].iloc[0]:.2f} | " + " | ".join(f"{t.loc[k, 'tau']:.0f}" for k in ["low", "mid", "high"]) + " | " +
                     " | ".join(f"{t.loc[k, 'fb']:.2f}" for k in ["low", "mid", "high"]) + " | " + " | ".join(f"{t.loc[k, 'ns']:.1f}" for k in ["low", "mid", "high"]) + " |")
open(os.path.join(OUT, "vol_competition.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
json.dump({"elasticities": res, "terciles": {k: {kk: {str(a): b for a, b in vv.items()} for kk, vv in v.items()} for k, v in terc.items()},
           "n_hours": int(len(H))}, open(os.path.join(OUT, "vol_competition.json"), "w"), indent=1, default=float)
print("\n".join(lines))
