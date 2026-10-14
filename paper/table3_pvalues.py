#!/usr/bin/env python3
"""table3_pvalues.py — exact two-sided p-values for every cell of the within-regime volatility table
(article Table 5 = Scientific Reports Table 3; Supplementary Table S7).

Reads paper/vol_competition.json (coefficient and day-clustered standard error of log σ for each hourly statistic,
regime and control set, written by vol_competition.py) and refers each t-statistic to a t distribution with
G − 1 degrees of freedom, G being the number of day-clusters of the regime. G is taken from
paper/vol_competition_panel.parquet when vol_competition.py has been run in this checkout (it writes the panel
next to this script); otherwise the counts of the shipped panel are used (31, 30, 31, 31, 31, 31 for Lorentz pre,
Lorentz post, Maxwell pre, Maxwell post, Fermi pre, Fermi post).

Output: paper/tables_v6/table_volcomp_pvalues.md
"""
import json
import os

from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
REG = ["Lorentz pre", "Lorentz post", "Maxwell pre", "Maxwell post", "Fermi pre", "Fermi post"]
ROWS = [("log_tau_med", "Median τ (log)"), ("log_sqrt_tau", "E[√τ] (log)"), ("first_block", "First-block share (level)"),
        ("log_n_senders", "Active contracts (log)"), ("log_M", "Movement M (log)"), ("log_J", "Crossing jump J (log)"),
        ("log_overshoot_cex", "CEX-triggered overshoot (log)")]
SHIPPED_G = dict(zip(REG, [31, 30, 31, 31, 31, 31]))

vc = json.load(open(os.path.join(HERE, "vol_competition.json")))["elasticities"]
panel = os.path.join(HERE, "vol_competition_panel.parquet")
if os.path.exists(panel):
    import pandas as pd
    H = pd.read_parquet(panel)
    G = {f"{f} {r}": int(H[(H["fork"] == f) & (H["regime"] == r)]["day"].nunique()) for f in ("Lorentz", "Maxwell", "Fermi") for r in ("pre", "post")}
else:
    G = SHIPPED_G


def fp(p):
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}" if p < 0.1 else f"{p:.2f}"


L = ["**Exact two-sided p-values for every cell of the within-regime volatility table (article Table 5; Scientific Reports Table 3 and Supplementary Table S7).** "
     "Same regressions as the table (coefficient on log σ within each block-interval regime, hour-of-day and pool fixed effects, day-clustered standard errors); "
     "p-values refer the cluster-robust t-statistic to t(G − 1), G being the number of day-clusters (" + ", ".join(str(G[r]) for r in REG) + "), \"<0.001\" below that level.",
     "", "| Outcome | " + " | ".join(REG) + " |", "|:--|" + ":--|" * len(REG)]
for tag, suffix in [("*No further controls*", ""), ("*With log volume and log active liquidity*", " +controls")]:
    L.append(f"| {tag} |" + " |" * len(REG))
    for key, lab in ROWS:
        cells = []
        for r in REG:
            x = vc[key][r + suffix]
            cells.append(fp(2 * stats.t.sf(abs(x["beta"] / x["se"]), G[r] - 1)))
        L.append(f"| {lab} | " + " | ".join(cells) + " |")
out = os.path.join(HERE, "tables_v6", "table_volcomp_pvalues.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
