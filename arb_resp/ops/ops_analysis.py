"""Cross-fork operator analysis on top of arb_operators.py output: (1) router-flow robustness of the six-regime latency
intercepts, (2) profile of router flow vs bot flow, (3) wallet rotation over time, (4) gas / position summary, (5) key numbers."""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))

import pandas as pd, numpy as np, glob, os, json, sys
sys.path.insert(0, ROOT + "/dex-lit/bnb_blocktime_pilot")
from arb_operators import build_operators, q_int, DT

OUT = ROOT + "/arb_resp/ops/out2"; os.makedirs(OUT, exist_ok=True)
CORE = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500"]
K = {}
frames = {}
for fork in ["Lorentz", "Maxwell", "Fermi"]:
    A = pd.concat([pd.read_parquet(f).assign(pool=os.path.basename(f).replace("_arbs_tx.parquet", "")) for f in sorted(glob.glob(ROOT + f"/arb_resp/ops/{fork}/arb_response/operators/*_arbs_tx.parquet"))], ignore_index=True)
    A["sender"] = A["sender"].astype(str)
    A, C, ops = build_operators(A, 30, 2, 20)
    A = A[A["days_from_fork"].abs() <= 30]
    frames[fork] = (A, C, ops)

# (1) latency intercepts with / without router flow, per pool x regime
rows = []
for fork, (A, C, ops) in frames.items():
    dt = {"pre": DT[fork][0] * 1000, "post": DT[fork][1] * 1000}
    for pool in CORE + ["WBNB-USDT-100"]:
        for reg in ("pre", "post"):
            x = A[(A["pool"] == pool) & (A["regime"] == reg)]
            c = x[(x["trigger"] == "cex") & x["tau_ms"].between(0, 60_000)]
            cb = c[~c["via_public"]]
            r = {"fork": fork, "pool": pool, "regime": reg, "router share (all strict arbs)": x["via_public"].mean(), "router share (CEX-triggered)": c["via_public"].mean(),
                 "q10 all": q_int(c["tau_ms"].to_numpy(float), .1, dt[reg]), "q10 bots": q_int(cb["tau_ms"].to_numpy(float), .1, dt[reg]),
                 "q50 all": q_int(c["tau_ms"].to_numpy(float), .5, dt[reg]), "q50 bots": q_int(cb["tau_ms"].to_numpy(float), .5, dt[reg]),
                 "P(first) all": (c["k_blocks"] == 1).mean(), "P(first) bots": (cb["k_blocks"] == 1).mean()}
            rows.append(r)
R1 = pd.DataFrame(rows)
K["R1_latency_router_robustness"] = R1.to_dict("records")
R1f = R1.copy()
for col in ["router share (all strict arbs)", "router share (CEX-triggered)", "P(first) all", "P(first) bots"]:
    R1f[col] = R1f[col].map(lambda v: f"{v:.2f}")
for col in ["q10 all", "q10 bots", "q50 all", "q50 bots"]:
    R1f[col] = R1f[col].map(lambda v: f"{v:.0f}")
open(os.path.join(OUT, "R1_latency_router_robustness.md"), "w").write(R1f.to_markdown(index=False, disable_numparse=True))

# (2) profile of the three flows per fork (4 pools pooled): share, size, overshoot, trigger mix, tau
rows = []
for fork, (A, C, ops) in frames.items():
    A = A.copy()
    A["flow"] = np.where(~A["via_public"], "bot contracts", np.where(A["operator"].str.startswith("e:") | A["operator"].str.startswith("c:"), "public router, persistent EOA", "public router, one-off EOA"))
    for flow, g in A.groupby("flow"):
        c = g[(g["trigger"] == "cex") & g["tau_ms"].between(0, 60_000)]
        rows.append({"fork": fork, "flow": flow, "share of strict arbs": len(g) / len(A), "EOAs": g["tx_from"].nunique(),
                     "median arbs per EOA": g.groupby("tx_from").size().median(), "median size (USDT)": g["volume_q"].median(),
                     "median overshoot (bp)": g["overshoot_bps"].median(), "same-block share": (g["trigger"] == "same_block").mean(),
                     "CEX-triggered share": (g["trigger"] == "cex").mean(), "median tau (ms, CEX-triggered)": c["tau_ms"].median(), "P(first block)": (c["k_blocks"] == 1).mean()})
R2 = pd.DataFrame(rows)
K["R2_flow_profiles"] = R2.to_dict("records")
R2f = R2.copy()
for col, fmt in [("share of strict arbs", "{:.3f}"), ("median arbs per EOA", "{:.0f}"), ("median size (USDT)", "{:.0f}"), ("median overshoot (bp)", "{:.2f}"), ("same-block share", "{:.2f}"), ("CEX-triggered share", "{:.2f}"), ("median tau (ms, CEX-triggered)", "{:.0f}"), ("P(first block)", "{:.2f}")]:
    R2f[col] = R2f[col].map(lambda v: fmt.format(v))
open(os.path.join(OUT, "R2_flow_profiles.md"), "w").write(R2f.to_markdown(index=False, disable_numparse=True))

# (3) wallet rotation over time: per fork x regime (5 bp pools pooled): share of arbs by contracts with >= 30 / >= 5 EOAs, EOAs of the top-5 contracts
rows = []
for fork, (A, C, ops) in frames.items():
    for reg in ("pre", "post"):
        x = A[(A["regime"] == reg) & A["pool"].isin(CORE) & ~A["via_public"]]
        e = x.groupby("sender")["tx_from"].nunique()
        n = x["sender"].value_counts()
        top = n.index[:5]
        rows.append({"fork": fork, "regime": reg, "bot arbs (5 bp pools)": len(x), "contracts ≥20 arbs": int((n >= 20).sum()),
                     "share by contracts with ≥30 EOAs": n[e.index[e >= 30]].sum() / n.sum(), "share by contracts with ≥5 EOAs": n[e.index[e >= 5]].sum() / n.sum(),
                     "EOAs of top-5 contracts": " / ".join(str(int(e[s])) for s in top), "median EOAs, contracts ≥20 arbs": e[n.index[n >= 20]].median()})
R3 = pd.DataFrame(rows)
K["R3_wallet_rotation"] = R3.to_dict("records")
R3f = R3.copy()
for col in ["share by contracts with ≥30 EOAs", "share by contracts with ≥5 EOAs"]:
    R3f[col] = R3f[col].map(lambda v: f"{v:.2f}")
R3f["median EOAs, contracts ≥20 arbs"] = R3f["median EOAs, contracts ≥20 arbs"].map(lambda v: f"{v:.0f}")
open(os.path.join(OUT, "R3_wallet_rotation.md"), "w").write(R3f.to_markdown(index=False, disable_numparse=True))

# (4) the largest bots across the six regimes: EOAs, ℓ̂ q10, share (5 bp pools pooled)
rows = {}
for fork, (A, C, ops) in frames.items():
    dt = {"pre": DT[fork][0] * 1000, "post": DT[fork][1] * 1000}
    for reg in ("pre", "post"):
        x = A[(A["regime"] == reg) & A["pool"].isin(CORE) & (A["operator"] != "anon")]
        vc = x["operator"].value_counts()
        for op in vc.index[:8]:
            y = x[x["operator"] == op]; c = y[(y["trigger"] == "cex") & y["tau_ms"].between(0, 60_000)]
            rows.setdefault(op, {})[f"{fork} {reg}"] = (int(y["tx_from"].nunique()), q_int(c["tau_ms"].to_numpy(float), .1, dt[reg]) if len(c) >= 50 else np.nan, vc[op] / vc.sum())
order = ["Lorentz pre", "Lorentz post", "Maxwell pre", "Maxwell post", "Fermi pre", "Fermi post"]
tab = []
for op, d in rows.items():
    if len(d) >= 3:
        r = {"operator": op[:16] + "…"}
        for k in order:
            v = d.get(k)
            r[k] = f"{v[0]} EOAs, {v[1]:.0f} ms, {v[2]:.2f}" if v and np.isfinite(v[1]) else (f"{v[0]} EOAs, —, {v[2]:.2f}" if v else "")
        tab.append(r)
R4 = pd.DataFrame(tab)
open(os.path.join(OUT, "R4_top_operators_six_regimes.md"), "w").write(R4.to_markdown(index=False, disable_numparse=True))
K["R4_top_operators"] = {op: {k: list(v) for k, v in d.items()} for op, d in rows.items() if len(d) >= 3}

# (5) gas: median gas price by fork x regime for CEX-triggered bot arbs; p90; cost at the window's BNB price; tx index
BNB = {}
for fork in frames:
    d = pd.read_parquet(ROOT + f"/arb_resp/{fork}/arb_response/WBNB-USDT-500/arbs_sample.parquet", columns=["p_cex", "regime"])
    BNB[fork] = {reg: float(d.loc[d["regime"] == reg, "p_cex"].median()) for reg in ("pre", "post")}
K["BNB_price_median"] = BNB
rows = []
for fork, (A, C, ops) in frames.items():
    for reg in ("pre", "post"):
        y = A[(A["regime"] == reg) & A["pool"].isin(CORE) & ~A["via_public"] & (A["trigger"] == "cex") & A["gas_price_wei"].notna() & (A["gas_price_wei"] > 0)]
        gp = y["gas_price_wei"].to_numpy(float) / 1e9
        cost = gp * y["gas_used"].to_numpy(float) / 1e9 * BNB[fork][reg]
        rows.append({"fork": fork, "regime": reg, "n": len(y), "BNB price (USDT)": BNB[fork][reg], "gas price gwei median": np.median(gp), "gas price gwei p90": np.quantile(gp, .9),
                     "share paying > 1.5x median": (gp > 1.5 * np.median(gp)).mean(),
                     "gas used median": y["gas_used"].median(), "tx index median": y["tx_index"].median(), "share tx index ≤ 2": (y["tx_index"] <= 2).mean(),
                     "gas cost USDT (median)": np.median(cost), "median arb loss (USDT)": y["arb_loss"].median(),
                     "gas / gross gain (mean ratio)": float(cost.sum() / y["arb_loss"].sum())})
R5 = pd.DataFrame(rows)
K["R5_gas"] = R5.to_dict("records")
R5f = R5.copy()
for col, fmt in [("BNB price (USDT)", "{:.0f}"), ("gas price gwei median", "{:.2f}"), ("gas price gwei p90", "{:.2f}"), ("share paying > 1.5x median", "{:.2f}"), ("gas used median", "{:.0f}"), ("tx index median", "{:.0f}"), ("share tx index ≤ 2", "{:.2f}"), ("gas cost USDT (median)", "{:.3f}"), ("median arb loss (USDT)", "{:.2f}"), ("gas / gross gain (mean ratio)", "{:.3f}")]:
    R5f[col] = R5f[col].map(lambda v: fmt.format(v))
open(os.path.join(OUT, "R5_gas.md"), "w").write(R5f.to_markdown(index=False, disable_numparse=True))

# (6) contracts vs operators on bot flow only (public-router arbs excluded), per pool x regime: the version consistent with the bots-only tables
from arb_operators import conc
rows = []
for fork, (A, C, ops) in frames.items():
    multi = set(ops.index[ops["contracts"] >= 2])
    for pool in CORE + ["WBNB-USDT-100"]:
        for reg in ("pre", "post"):
            x = A[(A["pool"] == pool) & (A["regime"] == reg) & ~A["via_public"]]
            if len(x) < 100:
                continue
            cc, co = conc(x["sender"].value_counts()), conc(x["operator"].value_counts())
            pools_per_op = A[(A["regime"] == reg) & ~A["via_public"]].groupby("operator")["pool"].nunique()
            cross = set(pools_per_op.index[pools_per_op >= 2])
            rows.append({"fork": fork, "pool": pool, "regime": reg, "bot arbs": len(x), "contracts": cc["n"], "operators": co["n"], "contracts ≥20": cc["n_ge20"], "operators ≥20": co["n_ge20"],
                         "HHI contracts": cc["hhi"], "HHI operators": co["hhi"], "top-1 c": cc["top1"], "top-1 o": co["top1"], "top-3 c": cc["top3"], "top-3 o": co["top3"],
                         "n90 c": cc["n90"], "n90 o": co["n90"], "share multi-contract operators": x["operator"].isin(multi).mean(), "share cross-pool operators": x["operator"].isin(cross).mean(),
                         "EOAs": x["tx_from"].nunique()})
R6 = pd.DataFrame(rows)
K["R6_contracts_vs_operators_bots"] = R6.to_dict("records")
R6f = R6.copy()
for col in ["HHI contracts", "HHI operators"]:
    R6f[col] = R6f[col].map(lambda v: f"{v:.3f}")
for col in ["top-1 c", "top-1 o", "top-3 c", "top-3 o", "share multi-contract operators", "share cross-pool operators"]:
    R6f[col] = R6f[col].map(lambda v: f"{v:.2f}")
open(os.path.join(OUT, "R6_contracts_vs_operators_bots.md"), "w").write(R6f.to_markdown(index=False, disable_numparse=True))

# (7) entry / exit and paired latencies at contract vs operator level, bot flow only (public-router arbs excluded)
rows = []
for fork, (A, C, ops) in frames.items():
    dt = {"pre": DT[fork][0] * 1000, "post": DT[fork][1] * 1000}
    B = A[~A["via_public"]]
    for pool in CORE + ["WBNB-USDT-100"]:
        g = B[B["pool"] == pool]
        pre, post = g[g["regime"] == "pre"], g[g["regime"] == "post"]
        r = {"fork": fork, "pool": pool}
        for level in ("sender", "operator"):
            a0 = set(pre[level].value_counts().loc[lambda v: v >= 20].index); a1 = set(post[level].value_counts().loc[lambda v: v >= 20].index)
            pc = post[level].value_counts()
            ent = float(pc[list(a1 - a0)].sum() / pc.sum())
            cp = pre[(pre["trigger"] == "cex") & pre["tau_ms"].between(0, 60_000)]; cq = post[(post["trigger"] == "cex") & post["tau_ms"].between(0, 60_000)]
            common = set(cp[level].value_counts().loc[lambda v: v >= 200].index) & set(cq[level].value_counts().loc[lambda v: v >= 200].index)
            d10, lower = [], []
            for sid in common:
                x, y = cp[cp[level] == sid]["tau_ms"].to_numpy(float), cq[cq[level] == sid]["tau_ms"].to_numpy(float)
                i0, i1 = q_int(x, .1, dt["pre"]), q_int(y, .1, dt["post"]); d10.append(i1 - i0); lower.append(i1 < i0 - 20)
            tag = "c" if level == "sender" else "o"
            r.update({f"stayers_{tag}": len(a0 & a1), f"entrants_{tag}": len(a1 - a0), f"exits_{tag}": len(a0 - a1), f"entrant_share_{tag}": ent, f"paired_{tag}": len(common),
                      f"d_q10_{tag}": float(np.median(d10)) if d10 else np.nan, f"lower_{tag}": float(np.mean(lower)) if lower else np.nan})
        rows.append(r)
R7 = pd.DataFrame(rows)
K["R7_entry_exit_bots"] = R7.to_dict("records")
R7f = R7.copy()
for c in R7f.columns:
    if c.startswith("entrant_share") or c.startswith("lower"):
        R7f[c] = R7f[c].map(lambda v: f"{v:.2f}")
    if c.startswith("d_q10"):
        R7f[c] = R7f[c].map(lambda v: f"{v:+.0f}" if np.isfinite(v) else "")
open(os.path.join(OUT, "R7_entry_exit_bots.md"), "w").write(R7f.to_markdown(index=False, disable_numparse=True))

json.dump(K, open(os.path.join(OUT, "key_numbers.json"), "w"), indent=1, default=float)
for f in sorted(glob.glob(os.path.join(OUT, "*.md"))):
    print(f"\n### {os.path.basename(f)}\n"); print(open(f).read())
