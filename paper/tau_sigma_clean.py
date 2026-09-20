#!/usr/bin/env python3
"""tau_sigma_clean.py — does the response time still fall with volatility on the subsamples whose opening time is
unambiguous?  (Scientific Reports referee, optional point.)

Table 3 of the manuscript shows that, holding volume and liquidity fixed, the median response time τ and E[√τ] of
CEX-triggered bot arbitrages fall with the hour's realised volatility σ.  The last-crossing convention that dates the
opening can bias τ downward when the reference price hovers at the band edge, and hovering is more frequent in
volatile hours.  Two subsamples are immune to the convention: (i) sharp openings, in which the crossing trade
carried the reference price at least ½γ beyond the band edge (t_open unambiguous), and (ii) on-chain-triggered
arbitrages, whose τ is a difference of two block timestamps and involves no reference price at all.  Both are thin
(about 1% and 0.5–2% of bot arbitrages), so the estimation is at the arbitrage level rather than on the hourly panel:
log τ_i (and the first-block indicator) on log σ of the hour, with log volume, log active liquidity, hour-of-day and
pool fixed effects, within each block-interval regime, standard errors clustered by day.  The same regression on all
CEX-triggered arbitrages is reported for comparison.

Outputs: tables_v6/table_tau_sigma_clean.md, tables_v6/tau_sigma_clean.json
"""
import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

CORE = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500"]
DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
PILOT = "/home/claude/dex-lit/bnb_blocktime_pilot"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tables_v6")

rows = []
for fork in DT:
    public = set(pd.read_csv(f"{PILOT}/public_contracts_{fork}.csv")["sender"].str.lower())
    panel = pd.read_parquet(f"/home/claude/{fork.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet")
    panel = panel[panel["pool"].isin(CORE)].copy()
    panel["hour_ts"] = pd.to_datetime(panel["hour"], utc=True).dt.tz_localize(None)
    for pool in CORE:
        A = pd.read_parquet(f"/home/claude/arb_resp/ops/{fork}/arb_response/operators/{pool}_arbs_tx.parquet",
                            columns=["sender", "ts_ms", "days_from_fork", "trigger", "tau_ms", "k_blocks", "jump_bps", "fee_rate"])
        A = A[A["days_from_fork"].abs() <= 30]
        A = A[~A["sender"].str.lower().isin(public)]
        A = A[A["tau_ms"].between(1, 60_000)].copy()
        A["hour_ts"] = pd.to_datetime(A["ts_ms"], unit="ms").dt.floor("h")
        A["trigger"] = A["trigger"].astype(str)
        A = A[A["trigger"].isin(["cex", "onchain"])]
        A["sharp"] = (A["trigger"] == "cex") & (A["jump_bps"] >= 0.5 * A["fee_rate"] * 1e4)
        A["pool"] = pool
        A["fork"] = fork
        p = panel[panel["pool"] == pool].set_index("hour_ts")[["sigma_ps", "post", "hod", "liq_mean", "volume", "day"]]
        A = A.join(p, on="hour_ts", how="inner")
        rows.append(A)
D = pd.concat(rows, ignore_index=True)
D = D[(D["sigma_ps"] > 0) & (D["volume"] > 0) & (D["liq_mean"] > 0)].copy()
D["regime"] = np.where(D["post"] == 1, "post", "pre")
D["log_tau"] = np.log(D["tau_ms"])
D["first_block"] = (D["k_blocks"] == 1).astype(float)
for c in ["sigma_ps", "volume", "liq_mean"]:
    D["log_" + c] = np.log(D[c])

SAMPLES = [("cex", "All CEX-triggered arbitrages", D["trigger"] == "cex"),
           ("sharp", "Sharp openings (crossing trade ≥ ½γ beyond the edge)", D["sharp"]),
           ("onchain", "On-chain-triggered arbitrages (τ from block timestamps only)", D["trigger"] == "onchain")]
OUTS = [("log_tau", "log τ"), ("first_block", "first-block indicator")]
CTRL = [("", "no further controls"), (" + log_volume + log_liq_mean", "with log volume and log liquidity")]


def fp(p):
    """exact two-sided p-value: three decimals below 0.1, two above, '< 0.001' below that level"""
    if p < 0.001:
        return "< 0.001"
    return "= " + (f"{p:.3f}" if p < 0.1 else f"{p:.2f}")


def fit(d, y, extra):
    try:
        m = smf.ols(f"{y} ~ log_sigma_ps{extra} + C(hod) + C(pool)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
        return {"b": float(m.params["log_sigma_ps"]), "se": float(m.bse["log_sigma_ps"]), "p": float(m.pvalues["log_sigma_ps"]), "n": int(m.nobs),
                "clusters": int(d["day"].nunique())}
    except Exception as e:  # noqa: BLE001
        return {"b": np.nan, "se": np.nan, "p": np.nan, "n": int(len(d)), "clusters": 0, "err": str(e)}


res = {}
regs = [(f, r) for f in DT for r in ("pre", "post")]
L = ["# Response time and volatility on the subsamples with an unambiguous opening time (arbitrage level)\n",
     "Coefficient on log σ (the hour's Binance realised volatility) in a regression of the arbitrage-level outcome on log σ, hour-of-day and pool fixed "
     "effects within each block-interval regime, three core pools pooled, bot flow, ±30-day windows; standard errors clustered by day in parentheses, exact two-sided p-values; "
     "sample sizes in the last block. Rows with controls add the hour's log volume and log active liquidity.\n"]
hdr = "| Sample / outcome | " + " | ".join(f"{f} {r} ({DT[f][0 if r == 'pre' else 1]} s)" for f, r in regs) + " |"
sep = "|:--|" + ":--|" * len(regs)
for skey, slab, mask in SAMPLES:
    L += [f"\n**{slab}**\n", hdr, sep]
    for okey, olab in OUTS:
        for ckey, clab in CTRL:
            cells = []
            for f, r in regs:
                d = D[mask & (D["fork"] == f) & (D["regime"] == r)]
                x = fit(d, okey, ckey)
                res[f"{skey}|{okey}|{clab}|{f} {r}"] = x
                cells.append(f"{x['b']:+.3f} ({x['se']:.3f}), p {fp(x['p'])}" if np.isfinite(x["b"]) else "—")
            L.append(f"| {olab}, {clab} | " + " | ".join(cells) + " |")
# sample sizes and the share of sharp openings
L.append("\n**Sample sizes per regime (three core pools pooled)**\n")
L += ["| Regime | CEX-triggered | sharp openings (share) | on-chain-triggered |", "|:--|--:|--:|--:|"]
for f, r in regs:
    d = D[(D["fork"] == f) & (D["regime"] == r)]
    nc, ns, no = int((d["trigger"] == "cex").sum()), int(d["sharp"].sum()), int((d["trigger"] == "onchain").sum())
    L.append(f"| {f} {r} | {nc:,} | {ns:,} ({ns / max(nc, 1):.1%}) | {no:,} |")
    res[f"n|{f} {r}"] = {"cex": nc, "sharp": ns, "onchain": no}
open(os.path.join(OUT, "table_tau_sigma_clean.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
json.dump(res, open(os.path.join(OUT, "tau_sigma_clean.json"), "w"), indent=1)
print("\n".join(L))
