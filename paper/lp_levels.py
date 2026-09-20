#!/usr/bin/env python3
"""lp_levels.py — LP loss relative to fee income at two mark-out horizons, and the fee-tier margin (referee M6).

For the four liquid pools and the six block-interval regimes (±30-day half-windows):
  loss/fee at the block timestamp  = Σ(fee_income − lp_gain) / Σ fee_income      (= Σ arb_loss / Σ fee_income)
  loss/fee at t + 30 s             = Σ(fee_income − markout_30s) / Σ fee_income
  arbitrage share of swaps, and the share of WBNB/USDT volume and active liquidity in the 1 bp pool (vs the 5 bp pool).
Fee-tier migration test: main specification (RD jump, ±30 d, separate slopes, hour-of-day FE, day-clustered) on
log(volume_1bp / volume_5bp) and log(L_1bp / L_5bp) of the WBNB/USDT pair, and on the 1 bp pool's own log volume and log L.
Outputs: tables_v6/table_lp_levels.md, table_fee_tier.md, lp_levels.json
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

FORKS = ["Lorentz", "Maxwell", "Fermi"]
POOLS = ["ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-500", "WBNB-USDT-100"]
LAB = {"ETH-USDT-500": "ETH/USDT 0.05%", "BTCB-USDT-500": "BTCB/USDT 0.05%", "WBNB-USDT-500": "WBNB/USDT 0.05%", "WBNB-USDT-100": "WBNB/USDT 0.01%"}
REG = [("Lorentz", 0, "3 s (Lorentz pre)"), ("Lorentz", 1, "1.5 s (Lorentz post)"), ("Maxwell", 0, "1.5 s (Maxwell pre)"), ("Maxwell", 1, "0.75 s (Maxwell post)"),
       ("Fermi", 0, "0.75 s (Fermi pre)"), ("Fermi", 1, "0.45 s (Fermi post)")]
OUT = ROOT + "/paper/tables_v6"
os.makedirs(OUT, exist_ok=True)
um = lambda s: str(s).replace("-", "−")


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


P = {f: pd.read_parquet(ROOT + f"/{f.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet") for f in FORKS}
for f in FORKS:
    P[f] = P[f][(P[f].t_days >= -30) & (P[f].t_days < 30)].copy()

rows = {}
for stat in ["LP loss / fee income, marked at the block timestamp", "LP loss / fee income, marked 30 s after the block", "Arbitrage share of swaps"]:
    for p in POOLS:
        rows[(stat, p)] = {"Statistic": stat, "Pool": LAB[p]}
res = {}
for f, post, name in REG:
    d = P[f][P[f]["post"] == post]
    for p in POOLS:
        x = d[d["pool"] == p]
        fee, gain, m30 = x["fee_income"].sum(), x["lp_gain"].sum(), x["markout_30s"].sum()
        r0, r30 = (fee - gain) / fee, (fee - m30) / fee
        share = x["n_arb"].sum() / x["swaps"].sum()
        rows[("LP loss / fee income, marked at the block timestamp", p)][name] = f"{r0:.2f}"
        rows[("LP loss / fee income, marked 30 s after the block", p)][name] = f"{r30:.2f}"
        rows[("Arbitrage share of swaps", p)][name] = f"{share:.2f}"
        res[f"{name}|{p}"] = {"loss_fee_0": float(r0), "loss_fee_30": float(r30), "arb_share": float(share)}
T = pd.DataFrame(list(rows.values()))
open(f"{OUT}/table_lp_levels.md", "w").write(T.to_markdown(index=False, disable_numparse=True))

# ---------------------------------------------------------------- fee-tier margin: 1 bp versus 5 bp WBNB/USDT
frows = []
for f in FORKS:
    a = P[f][P[f]["pool"] == "WBNB-USDT-100"].set_index("hour")
    b = P[f][P[f]["pool"] == "WBNB-USDT-500"].set_index("hour")
    j = a[["volume", "liq_mean", "sigma_ps", "post", "hod", "day", "t_days"]].join(b[["volume", "liq_mean"]], rsuffix="_5", how="inner")
    j = j[(j["volume"] > 0) & (j["volume_5"] > 0) & (j["liq_mean"] > 0) & (j["liq_mean_5"] > 0) & (j["sigma_ps"] > 0)].copy()
    j["vshare"] = j["volume"] / (j["volume"] + j["volume_5"])
    j["lshare"] = j["liq_mean"] / (j["liq_mean"] + j["liq_mean_5"])
    j["lv"] = np.log(j["volume"] / j["volume_5"])
    j["ll"] = np.log(j["liq_mean"] / j["liq_mean_5"])
    j["lv1"] = np.log(j["volume"])
    j["ll1"] = np.log(j["liq_mean"])
    pre, post = j[j["post"] == 0], j[j["post"] == 1]
    r = {"Fork": f, "1 bp share of WBNB/USDT volume, pre → post": f"{pre['volume'].sum() / (pre['volume'].sum() + pre['volume_5'].sum()):.3f} → {post['volume'].sum() / (post['volume'].sum() + post['volume_5'].sum()):.3f}",
         "1 bp share of active liquidity, pre → post": f"{pre['lshare'].mean():.3f} → {post['lshare'].mean():.3f}"}
    for y, lab in [("lv", "RD jump: log(volume 1 bp / 5 bp)"), ("ll", "RD jump: log(L 1 bp / 5 bp)"), ("lv1", "RD jump: log volume, 1 bp pool"), ("ll1", "RD jump: log L, 1 bp pool")]:
        m = smf.ols(f"{y} ~ post + np.log(sigma_ps) + t_days + post:t_days + C(hod)", data=j).fit(cov_type="cluster", cov_kwds={"groups": j["day"].astype(str)})
        r[lab] = um(f"{m.params['post']:+.3f}{star(m.pvalues['post'])} ({m.bse['post']:.3f})")
        res[f"fee_tier|{f}|{y}"] = {"b": float(m.params["post"]), "se": float(m.bse["post"]), "p": float(m.pvalues["post"])}
    res[f"fee_tier|{f}|shares"] = {"vshare_pre": float(pre['volume'].sum() / (pre['volume'].sum() + pre['volume_5'].sum())),
                                   "vshare_post": float(post['volume'].sum() / (post['volume'].sum() + post['volume_5'].sum())),
                                   "lshare_pre": float(pre["lshare"].mean()), "lshare_post": float(post["lshare"].mean())}
    frows.append(r)
F = pd.DataFrame(frows)
open(f"{OUT}/table_fee_tier.md", "w").write(F.to_markdown(index=False, disable_numparse=True))
json.dump(res, open(f"{OUT}/lp_levels.json", "w"), indent=1)
print(T.to_markdown(index=False, disable_numparse=True))
print()
print(F.to_markdown(index=False, disable_numparse=True))
