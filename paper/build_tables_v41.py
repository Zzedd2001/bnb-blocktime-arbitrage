"""Tables for paper v4.1 that come from the tx.from (operator) data and do not depend on the bots-only rerun:
E4 contracts vs operators (bot flow only), E5 gas and block position, E6 wallet pools vs latency (Fermi)."""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json, os
import pandas as pd, numpy as np

OPS = ROOT + "/arb_resp/ops"
OUT = ROOT + "/paper/tables_v41"; os.makedirs(OUT, exist_ok=True)
POOL = {"WBNB-USDT-500": "WBNB/USDT 0.05%", "ETH-USDT-500": "ETH/USDT 0.05%", "BTCB-USDT-500": "BTCB/USDT 0.05%", "WBNB-USDT-100": "WBNB/USDT 0.01%"}
ORDER = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-100"]
FORKS = ["Lorentz", "Maxwell", "Fermi"]
m = lambda v: f"{v:+.2f}".replace("-", "−")
K2 = json.load(open(f"{OPS}/out2/key_numbers.json"))
K1 = json.load(open(f"{OPS}/out/key_numbers.json"))


def md(df):
    return df.to_markdown(index=False, disable_numparse=True)


# ---------------- E4: contracts vs operators (bot flow), per pool x regime, pre -> post in one row per pool-fork
R6 = pd.DataFrame(K2["R6_contracts_vs_operators_bots"])
rows = []
for f in FORKS:
    for p in ORDER:
        a, b = [R6[(R6.fork == f) & (R6.pool == p) & (R6.regime == r)].iloc[0] for r in ("pre", "post")]
        rows.append({"Fork": f, "Pool": POOL[p], "Bot arbitrages, pre → post": f"{int(a['bot arbs']):,} → {int(b['bot arbs']):,}",
                     "Contracts / operators active (≥ 20 arbs), pre": f"{int(a['contracts ≥20'])} / {int(a['operators ≥20'])}",
                     "post": f"{int(b['contracts ≥20'])} / {int(b['operators ≥20'])}",
                     "HHI contracts / operators, pre": f"{a['HHI contracts']:.3f} / {a['HHI operators']:.3f}", "post ": f"{b['HHI contracts']:.3f} / {b['HHI operators']:.3f}",
                     "Top-1 share contracts / operators, pre": f"{a['top-1 c']:.2f} / {a['top-1 o']:.2f}", "post  ": f"{b['top-1 c']:.2f} / {b['top-1 o']:.2f}",
                     "Top-3 share contracts / operators, pre": f"{a['top-3 c']:.2f} / {a['top-3 o']:.2f}", "post   ": f"{b['top-3 c']:.2f} / {b['top-3 o']:.2f}",
                     "Covering 90%: contracts / operators, pre → post": f"{int(a['n90 c'])} / {int(a['n90 o'])} → {int(b['n90 c'])} / {int(b['n90 o'])}",
                     "Share of multi-contract operators, pre → post": f"{a['share multi-contract operators']:.2f} → {b['share multi-contract operators']:.2f}",
                     "EOAs (signing wallets), pre → post": f"{int(a['EOAs']):,} → {int(b['EOAs']):,}"})
E4 = pd.DataFrame(rows)
open(f"{OUT}/E4_contracts_vs_operators.md", "w").write(md(E4))

# ---------------- E4b: entry/exit and paired latency at contract vs operator level, bot flow only (R7)
R7 = pd.DataFrame(K2["R7_entry_exit_bots"])
rows = []
for f in FORKS:
    for p in ORDER:
        r = R7[(R7.fork == f) & (R7.pool == p)].iloc[0]
        fm = lambda v: (f"{v:+.0f}" if np.isfinite(v) else "—").replace("-", "−")
        rows.append({"Fork": f, "Pool": POOL[p], "Stayers / entrants / exits: contracts": f"{int(r.stayers_c)} / {int(r.entrants_c)} / {int(r.exits_c)}",
                     "operators": f"{int(r.stayers_o)} / {int(r.entrants_o)} / {int(r.exits_o)}",
                     "Entrants' share of post-fork arbs: contracts / operators": f"{r.entrant_share_c:.2f} / {r.entrant_share_o:.2f}",
                     "Paired (≥ 200 CEX-triggered arbs each side): contracts / operators": f"{int(r.paired_c)} / {int(r.paired_o)}",
                     "Median Δℓ̂ 10th pct. (ms): contracts / operators": f"{fm(r.d_q10_c)} / {fm(r.d_q10_o)}",
                     "Share with a lower ℓ̂: contracts / operators": f"{r.lower_c:.2f} / {r.lower_o:.2f}"})
E4b = pd.DataFrame(rows)
open(f"{OUT}/E4b_entry_exit_operators.md", "w").write(md(E4b))

# ---------------- E5: gas and block position (R5)
R5 = pd.DataFrame(K2["R5_gas"])
rows = []
for r in R5.itertuples():
    rows.append({"Regime": f"{r.fork}, {r.regime}", "CEX-triggered bot arbitrages": f"{int(r.n):,}", "BNB price (USDT)": f"{r._4:.0f}",
                 "Gas price, median / 90th pct. (gwei)": f"{r._5:.2f} / {r._6:.2f}", "Share paying > 1.5× the median": f"{r._7:.2f}",
                 "Gas used, median": f"{int(r._8):,}", "Position in block, median": f"{int(r._9)}", "Share in the first three positions": f"{r._10:.2f}",
                 "Gas cost per arbitrage, median (USDT)": f"{r._11:.3f}", "Gross gain per arbitrage, median (USDT)": f"{r._12:.2f}", "Gas / gross gain": f"{r._13:.3f}"})
E5 = pd.DataFrame(rows)
open(f"{OUT}/E5_gas_position.md", "w").write(md(E5))

# ---------------- E6: wallet pools of the largest operators across the six regimes (R4) + rotation-vs-latency stats
R4 = K2["R4_top_operators"]
order = ["Lorentz pre", "Lorentz post", "Maxwell pre", "Maxwell post", "Fermi pre", "Fermi post"]
rows = []
for op, d in R4.items():
    r = {"Operator (contract)": op[2:12] + "…" + op[-4:]}
    for k in order:
        v = d.get(k)
        r[k.replace(" pre", ", pre").replace(" post", ", post")] = f"{v[0]} / {v[1]:.0f} / {v[2]:.2f}" if v and np.isfinite(v[1]) else (f"{v[0]} / — / {v[2]:.2f}" if v else "")
    rows.append(r)
E6 = pd.DataFrame(rows)
open(f"{OUT}/E6_wallet_pools.md", "w").write(md(E6))

# rotation shares (R3) and correlation (K1)
R3 = pd.DataFrame(K2["R3_wallet_rotation"])
rows = []
for r in R3.itertuples():
    k = K1.get(f"{r.fork}|{r.regime}|rotation_vs_latency", {})
    rows.append({"Regime": f"{r.fork}, {r.regime}", "Bot arbitrages (core pools)": f"{int(r._3):,}", "Contracts with ≥ 20 arbs": int(r._4),
                 "Share by contracts with ≥ 30 wallets": f"{r._5:.2f}", "Share by contracts with ≥ 5 wallets": f"{r._6:.2f}", "Wallets of the five largest contracts": r._7,
                 "Operators with ≥ 500 CEX-triggered arbs": k.get("n_operators", ""), "Spearman ρ (log wallets, ℓ̂ 10th pct.)": (f"{k['spearman_logEOAs_q10']:+.2f} (p = {k['p']:.2f})".replace("-", "−") if k else ""),
                 "Median ℓ̂ 10th pct.: ≥ 5 wallets / fewer (ms)": (f"{k['q10_median_multi_eoa']:.0f} / {k['q10_median_single_eoa']:.0f}" if k else "")})
E6b = pd.DataFrame(rows)
open(f"{OUT}/E6b_wallet_rotation.md", "w").write(md(E6b))

# ---------------- flow shares table (for §4.5): R2
R2 = pd.DataFrame(K2["R2_flow_profiles"])
rows = []
for r in R2.itertuples():
    rows.append({"Fork": r.fork, "Flow": r.flow.replace("bot contracts", "Bot contracts").replace("public router, one-off EOA", "Public routers, one-off accounts").replace("public router, persistent EOA", "Public routers, persistent accounts (≥ 20 arbs)"),
                 "Share of strict arbitrages": f"{r._3:.3f}", "Accounts (EOAs)": f"{int(r.EOAs):,}", "Median arbitrages per account": f"{r._5:.0f}", "Median size (USDT)": f"{r._6:,.0f}",
                 "Median overshoot (bp)": f"{r._7:.2f}", "Same-block share": f"{r._8:.2f}", "CEX-triggered share": f"{r._9:.2f}", "P(first block), CEX-triggered": f"{r._11:.2f}"})
E7 = pd.DataFrame(rows)
open(f"{OUT}/E7_flow_profiles.md", "w").write(md(E7))
for f in ["E4_contracts_vs_operators", "E4b_entry_exit_operators", "E5_gas_position", "E6_wallet_pools", "E6b_wallet_rotation", "E7_flow_profiles"]:
    print(f"\n{f}\n"); print(open(f"{OUT}/{f}.md").read()[:1500])
