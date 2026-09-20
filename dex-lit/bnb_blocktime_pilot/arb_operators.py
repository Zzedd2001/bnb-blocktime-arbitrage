"""Operators behind the arbitrage contracts: merge sender contracts and EOAs (tx.from) into operators and redo the
address-level statistics of arb_response.py at the operator level.

Input: the folders written by fetch_tx_from.py (one per fork), each with <pool>_arbs_tx.parquet (strict arbitrages with
tx_from / tx_to / tx_index / gas); <pool>_contracts.csv (all swaps of the contract) is used only as extra columns when present.

Operator construction.  A contract is *public* (a router or aggregator used by many unrelated accounts) if at least
--public-eoas distinct EOAs sent strict arbitrages through it and the median EOA sent at most --public-median of them,
i.e. its typical user is a one-off account (PancakeSwap's SmartRouter: 500 EOAs, median 1).  Arbitrage bots that rotate
many hot wallets look different: each wallet sends tens to thousands of arbitrages (e.g. 41 EOAs with a median of 4,100,
or 200 EOAs with a median of 76), so they stay *private*.  Private contracts and EOAs form a bipartite graph (an edge for
every (contract, EOA) pair observed on a strict arbitrage, across all pools of the fork); its connected components are the
operators.  An arbitrage through a public contract is attributed to the EOA that sent it (which belongs to an operator
if it also uses a private contract, and is an operator of its own otherwise).

    python arb_operators.py --dir full_fermi/arb_response/operators --fork Fermi --out full_fermi/arb_response/operators/out
    python arb_operators.py --dir full_lorentz/... --fork Lorentz --dir full_maxwell/... --fork Maxwell --dir full_fermi/... --fork Fermi --out operators_out
"""
from __future__ import annotations
import argparse, glob, json, os
import numpy as np, pandas as pd

DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
ORDER = [("Lorentz", "pre"), ("Lorentz", "post"), ("Maxwell", "pre"), ("Maxwell", "post"), ("Fermi", "pre"), ("Fermi", "post")]


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def hhi(c):
    s = c / c.sum(); return float((s ** 2).sum())


def conc(counts: pd.Series) -> dict:
    counts = counts.sort_values(ascending=False); sh = counts / counts.sum()
    return {"n": int(len(counts)), "hhi": hhi(counts), "top1": float(sh.iloc[0]), "top3": float(sh.iloc[:3].sum()), "top5": float(sh.iloc[:5].sum()),
            "n90": int((sh.cumsum() < 0.9).sum() + 1), "n_ge20": int((counts >= 20).sum())}


def build_operators(arbs: pd.DataFrame, public_eoas: int, public_median: float, min_arbs: int = 20, extra: pd.DataFrame | None = None):
    """arbs: strict arbs of all pools of one fork with sender, tx_from.  Returns (arbs with operator column, contract table,
    operator table).  Arbitrages through a public contract by an EOA that is not linked to any private contract and sent
    fewer than `min_arbs` of them are labelled "anon" (one-off accounts behind routers; reported as a share, never as
    operators).  `extra` (optional): per-contract columns from the all-swaps contract tables."""
    pairs = arbs.dropna(subset=["tx_from"]).groupby(["sender", "tx_from"]).size().reset_index(name="n")
    per = pairs.groupby("sender").agg(distinct_eoas=("tx_from", "nunique"), arbs_with_tx=("n", "sum"), median_arbs_per_eoa=("n", "median"))
    top = pairs.sort_values(["sender", "n"], ascending=[True, False])
    per["top_eoa_share"] = top.groupby("sender").head(1).set_index("sender")["n"] / per["arbs_with_tx"]
    per["top3_eoa_share"] = top.groupby("sender").head(3).groupby("sender")["n"].sum() / per["arbs_with_tx"]
    per["strict_arbs"] = arbs["sender"].value_counts().reindex(per.index).fillna(0).astype(int)
    per["pools"] = arbs.groupby("sender")["pool"].nunique().reindex(per.index)
    per["tx_to_equals_sender_share"] = (arbs["tx_to"].str.lower() == arbs["sender"].str.lower()).groupby(arbs["sender"]).mean().reindex(per.index)
    contracts = per
    if extra is not None and len(extra):
        contracts = contracts.join(extra, how="left")
    contracts["public"] = (contracts["distinct_eoas"] >= public_eoas) & (contracts["median_arbs_per_eoa"] <= public_median)
    contracts["wallet_rotation"] = (contracts["distinct_eoas"] >= public_eoas) & ~contracts["public"]
    pub = set(contracts.index[contracts["public"]])
    uf = UF()
    for r in pairs.itertuples():
        if r.sender in pub:
            continue
        uf.union("c:" + r.sender, "e:" + r.tx_from)
    linked = {k for k in uf.p if k.startswith("e:")}                      # EOAs that also use a private contract
    n_pub_eoa = arbs[arbs["sender"].isin(pub)].groupby("tx_from").size()   # arbs sent through public contracts, per EOA
    heavy = set(n_pub_eoa.index[n_pub_eoa >= min_arbs])

    def op_of(sender, tx_from):
        if sender not in pub:
            return uf.find("c:" + sender)
        if not isinstance(tx_from, str):
            return "anon"
        if "e:" + tx_from in linked:
            return uf.find("e:" + tx_from)
        return "e:" + tx_from if tx_from in heavy else "anon"          # a steady EOA behind a router is an operator; a one-off one is anonymous flow
    arbs = arbs.copy()
    arbs["operator"] = [op_of(s, f) for s, f in zip(arbs["sender"].astype(str), arbs["tx_from"])]
    arbs["via_public"] = arbs["sender"].astype(str).isin(pub)
    # operator summary: contracts and EOAs per operator
    priv = pairs[~pairs["sender"].isin(pub)].copy(); priv["operator"] = [uf.find("c:" + s) for s in priv["sender"]]
    ops = priv.groupby("operator").agg(contracts=("sender", "nunique"), eoas=("tx_from", "nunique"), pairs=("n", "sum"))
    contracts["operator"] = [uf.find("c:" + s) if s not in pub else "public" for s in contracts.index]
    return arbs, contracts, ops


def q_int(tau, q, dt_ms):
    return float(np.quantile(tau, q) - q * dt_ms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="append", required=True); ap.add_argument("--fork", action="append", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--public-eoas", type=int, default=30)
    ap.add_argument("--public-median", type=float, default=2, help="a contract with >= --public-eoas EOAs whose median EOA sent at most this many strict arbs is public")
    ap.add_argument("--min-arbs", type=int, default=20); ap.add_argument("--min-pair", type=int, default=200); ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    K = {}; rows_conc, rows_ops, rows_pair, rows_gas, rows_top, rows_rot = [], [], [], [], [], []
    TOP = {}
    for d, fork in zip(a.dir, a.fork):
        files = sorted(glob.glob(os.path.join(d, "*_arbs_tx.parquet")))
        A = pd.concat([pd.read_parquet(f).assign(pool=os.path.basename(f).replace("_arbs_tx.parquet", "")) for f in files], ignore_index=True)
        A["sender"] = A["sender"].astype(str)
        C = pd.concat([pd.read_csv(f, index_col=0).assign(pool=os.path.basename(f).replace("_contracts.csv", "")) for f in sorted(glob.glob(os.path.join(d, "*_contracts.csv")))])
        extra = None
        if len(C) and C["distinct_eoas"].notna().any():          # all-swaps view of the contracts (v2.14.3+ of fetch_tx_from.py)
            extra = C.groupby(C.index).agg(swaps_all=("swaps", "sum"), distinct_eoas_all=("distinct_eoas", "max"), top3_eoa_share_all=("top3_eoa_share", "min"))
        A, Cagg, ops = build_operators(A, a.public_eoas, a.public_median, a.min_arbs, extra)
        A = A[A["days_from_fork"].abs() <= a.days]
        dt = {"pre": DT[fork][0] * 1000, "post": DT[fork][1] * 1000}
        K[fork] = {"n_contracts": int(Cagg.shape[0]), "n_public": int(Cagg["public"].sum()), "public_contracts": list(Cagg.index[Cagg["public"]]),
                   "n_wallet_rotation": int(Cagg["wallet_rotation"].sum()), "share_arbs_public": float(A["via_public"].mean()), "share_arbs_anon": float((A["operator"] == "anon").mean()),
                   "share_arbs_wallet_rotation": float(A["sender"].isin(set(Cagg.index[Cagg["wallet_rotation"]])).mean()),
                   "n_eoas": int(A["tx_from"].nunique()),
                   "coverage_tx": float(A["tx_from"].notna().mean()), "n_operators": int(ops.shape[0]),
                   "ops_multi_contract": int((ops["contracts"] >= 2).sum()), "ops_multi_eoa": int((ops["eoas"] >= 2).sum()),
                   "max_contracts": int(ops["contracts"].max()) if len(ops) else 0, "max_eoas": int(ops["eoas"].max()) if len(ops) else 0}
        Cagg.sort_values("strict_arbs", ascending=False).to_csv(os.path.join(a.out, f"contracts_{fork}.csv"))
        ops.sort_values("pairs", ascending=False).to_csv(os.path.join(a.out, f"operators_{fork}.csv"))
        # per pool × regime concentration: contracts vs operators
        for pool, g in A.groupby("pool"):
            for reg in ("pre", "post"):
                x = g[g["regime"] == reg]
                if len(x) < 100:
                    continue
                ident = x[x["operator"] != "anon"]
                cc, co = conc(x["sender"].value_counts()), conc(ident["operator"].value_counts())
                # share of arbs by operators with ≥ 2 contracts (in this fork, any pool) and by operators active in ≥ 2 pools
                multi = set(ops.index[ops["contracts"] >= 2])
                pools_per_op = A[(A["regime"] == reg) & (A["operator"] != "anon")].groupby("operator")["pool"].nunique()
                cross = set(pools_per_op.index[pools_per_op >= 2])
                rot = set(Cagg.index[Cagg["wallet_rotation"]])
                rows_conc.append({"fork": fork, "pool": pool, "regime": reg, "strict arbs": len(x), "tx data": f"{x['tx_from'].notna().mean():.2f}",
                                  "contracts": cc["n"], "EOAs": int(x["tx_from"].nunique()), "operators": co["n"], "contracts ≥20": cc["n_ge20"], "operators ≥20": co["n_ge20"],
                                  "HHI contracts": f"{cc['hhi']:.3f}", "HHI operators": f"{co['hhi']:.3f}", "top-1 contracts / operators": f"{cc['top1']:.2f} / {co['top1']:.2f}",
                                  "top-3 contracts / operators": f"{cc['top3']:.2f} / {co['top3']:.2f}", "for 90%: contracts / operators": f"{cc['n90']} / {co['n90']}",
                                  "share by multi-contract operators": f"{x['operator'].isin(multi).mean():.2f}", "share by cross-pool operators": f"{x['operator'].isin(cross).mean():.2f}",
                                  "share via public contracts": f"{x['via_public'].mean():.2f}", "anonymous share (one-off EOAs via public contracts)": f"{(x['operator'] == 'anon').mean():.2f}",
                                  "share by wallet-rotating contracts": f"{x['sender'].isin(rot).mean():.2f}"})
                K[f"{fork}|{pool}|{reg}"] = {"contracts": cc, "operators": co, "n_eoas": int(x["tx_from"].nunique()), "multi_share": float(x["operator"].isin(multi).mean()), "cross_share": float(x["operator"].isin(cross).mean()),
                                             "public_share": float(x["via_public"].mean()), "anon_share": float((x["operator"] == "anon").mean()), "rotation_share": float(x["sender"].isin(rot).mean())}
        # entrants / exits and paired response times at operator level (per pool)
        for pool, g in A.groupby("pool"):
            pre, post = g[g["regime"] == "pre"], g[g["regime"] == "post"]
            if len(pre) < 100 or len(post) < 100:
                continue
            for level in ("sender", "operator"):
                pre, post = g[(g["regime"] == "pre") & (g[level] != "anon")], g[(g["regime"] == "post") & (g[level] != "anon")]
                a0 = set(pre[level].value_counts().loc[lambda s: s >= a.min_arbs].index); a1 = set(post[level].value_counts().loc[lambda s: s >= a.min_arbs].index)
                pc = post[level].value_counts()
                ent = float(pc[list(a1 - a0)].sum() / pc.sum()) if len(pc) else np.nan
                cp = pre[(pre["trigger"] == "cex") & (pre["tau_ms"].between(0, 60_000))]; cq = post[(post["trigger"] == "cex") & (post["tau_ms"].between(0, 60_000))]
                common = set(cp[level].value_counts().loc[lambda s: s >= a.min_pair].index) & set(cq[level].value_counts().loc[lambda s: s >= a.min_pair].index)
                dq10, dq50, lower = [], [], []
                for s in common:
                    x, y = cp[cp[level] == s]["tau_ms"].to_numpy(float), cq[cq[level] == s]["tau_ms"].to_numpy(float)
                    i0, i1 = q_int(x, .1, dt["pre"]), q_int(y, .1, dt["post"]); m0, m1 = q_int(x, .5, dt["pre"]), q_int(y, .5, dt["post"])
                    dq10.append(i1 - i0); dq50.append(m1 - m0); lower.append(i1 < i0 - 20)
                rows_ops.append({"fork": fork, "pool": pool, "level": level, "stayers / entrants / exits": f"{len(a0 & a1)} / {len(a1 - a0)} / {len(a0 - a1)}",
                                 "entrants' share of post arbs": f"{ent:.2f}", "paired (≥%d each side)" % a.min_pair: len(common),
                                 "median Δ ℓ̂ q10 (ms)": f"{np.median(dq10):+.0f}" if dq10 else "", "median Δ ℓ̂ q50 (ms)": f"{np.median(dq50):+.0f}" if dq50 else "",
                                 "share with lower ℓ̂ q10": f"{np.mean(lower):.2f}" if lower else ""})
        # top operators per pool and regime, with their contracts / EOAs and response times
        for pool, g in A.groupby("pool"):
            for reg in ("pre", "post"):
                x = g[g["regime"] == reg]
                if len(x) < 100:
                    continue
                vc = x["operator"].value_counts()
                for op in [o for o in vc.index if o != "anon"][:5]:
                    y = x[x["operator"] == op]; c = y[(y["trigger"] == "cex") & (y["tau_ms"].between(0, 60_000))]
                    rows_top.append({"fork": fork, "pool": pool, "regime": reg, "operator": op[:14] + "…" if len(op) > 14 else op, "share": f"{vc[op] / vc.sum():.2f}", "strict arbs": int(vc[op]),
                                     "contracts": int(y["sender"].nunique()), "EOAs": int(y["tx_from"].nunique()),
                                     "ℓ̂ q10 / q50 (ms)": f"{q_int(c['tau_ms'].to_numpy(float), .1, dt[reg]):.0f} / {q_int(c['tau_ms'].to_numpy(float), .5, dt[reg]):.0f}" if len(c) >= 50 else "",
                                     "P(first block)": f"{(c['k_blocks'] == 1).mean():.2f}" if len(c) >= 50 else "", "same-block share": f"{(y['trigger'] == 'same_block').mean():.2f}",
                                     "median tx index": f"{y['tx_index'].median():.0f}" if y["tx_index"].notna().any() else ""})
                    TOP.setdefault((pool, op), {})[f"{fork} {reg}"] = (q_int(c['tau_ms'].to_numpy(float), .1, dt[reg]) if len(c) >= 50 else np.nan, float(vc[op] / vc.sum()))
        # wallet rotation vs response time: operators with >= 500 CEX-triggered arbs in the 5 bp pools (pooled), per regime
        core = A[A["pool"].isin(["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500"])]
        for reg in ("pre", "post"):
            c = core[(core["regime"] == reg) & (core["trigger"] == "cex") & core["tau_ms"].between(0, 60_000)]
            vc = c["operator"].value_counts(); big = [o for o in vc.index[vc >= 500] if o != "anon"]
            pts = []
            for op in big:
                y = c[c["operator"] == op]; allop = core[(core["regime"] == reg) & (core["operator"] == op)]
                pts.append({"fork": fork, "regime": reg, "operator": op[:14] + "…", "strict arbs": int(len(allop)), "contracts": int(allop["sender"].nunique()),
                            "EOAs": int(allop["tx_from"].nunique()), "EOAs with ≥20 arbs": int((allop["tx_from"].value_counts() >= 20).sum()),
                            "ℓ̂ q10": q_int(y["tau_ms"].to_numpy(float), .1, dt[reg]), "ℓ̂ q50": q_int(y["tau_ms"].to_numpy(float), .5, dt[reg]),
                            "P(first block)": float((y["k_blocks"] == 1).mean()), "median gas gwei": float(allop["gas_price_wei"].median() / 1e9) if allop["gas_price_wei"].notna().any() else np.nan})
            P = pd.DataFrame(pts)
            if len(P) >= 5:
                from scipy.stats import spearmanr
                rho, pv = spearmanr(np.log(P["EOAs"]), P["ℓ̂ q10"])
                K[f"{fork}|{reg}|rotation_vs_latency"] = {"n_operators": int(len(P)), "spearman_logEOAs_q10": float(rho), "p": float(pv),
                                                          "q10_median_multi_eoa": float(P.loc[P["EOAs"] >= 5, "ℓ̂ q10"].median()) if (P["EOAs"] >= 5).any() else np.nan,
                                                          "q10_median_single_eoa": float(P.loc[P["EOAs"] < 5, "ℓ̂ q10"].median()) if (P["EOAs"] < 5).any() else np.nan}
            for r in pts:
                r["ℓ̂ q10 / q50 (ms)"] = f"{r.pop('ℓ̂ q10'):.0f} / {r.pop('ℓ̂ q50'):.0f}"; r["P(first block)"] = f"{r['P(first block)']:.2f}"
                r["median gas gwei"] = f"{r['median gas gwei']:.2f}"
                rows_rot.append(r)
        # gas and block position by trigger type and regime (5 bp pools pooled)
        for reg in ("pre", "post"):
            for trig in ("cex", "same_block", "continuation"):
                y = core[(core["regime"] == reg) & (core["trigger"] == trig) & core["gas_price_wei"].notna() & (core["gas_price_wei"] > 0)]
                if len(y) < 100:
                    continue
                gp = y["gas_price_wei"].to_numpy(float) / 1e9
                rows_gas.append({"fork": fork, "regime": reg, "trigger": trig, "n": len(y), "gas price gwei: median / p90": f"{np.median(gp):.2f} / {np.quantile(gp, .9):.2f}",
                                 "gas used: median": f"{y['gas_used'].median():.0f}", "tx index in block: median / share = 0": f"{y['tx_index'].median():.0f} / {(y['tx_index'] == 0).mean():.2f}",
                                 "gas cost per arb (USDT at 600/BNB)": f"{np.median(gp * y['gas_used'].to_numpy(float)) / 1e9 * 600:.3f}"})
    T1 = pd.DataFrame(rows_conc); T2 = pd.DataFrame(rows_ops); T3 = pd.DataFrame(rows_top); T4 = pd.DataFrame(rows_gas); T6 = pd.DataFrame(rows_rot)
    for name, T in (("O1_concentration", T1), ("O2_entry_exit_paired", T2), ("O3_top_operators", T3), ("O4_gas_position", T4), ("O6_wallet_rotation", T6)):
        open(os.path.join(a.out, name + ".md"), "w").write(T.to_markdown(index=False, disable_numparse=True) if len(T) else "(empty)")
    # trajectories of operators present in ≥ 4 regimes (needs the three forks together)
    rows = []
    for (pool, op), regs in TOP.items():
        if len(regs) >= 4:
            r = {"pool": pool, "operator": op[:14] + "…"}
            for f, reg in ORDER:
                v = regs.get(f"{f} {reg}")
                r[f"{f} {reg}"] = f"{v[0]:.0f} ({v[1]:.2f})" if v and np.isfinite(v[0]) else (f"— ({v[1]:.2f})" if v else "")
            rows.append(r)
    open(os.path.join(a.out, "O5_operator_trajectories.md"), "w").write(pd.DataFrame(rows).to_markdown(index=False, disable_numparse=True) if rows else "(needs several forks)")
    json.dump(K, open(os.path.join(a.out, "key_numbers.json"), "w"), indent=1, default=float)
    for name in ("O1_concentration", "O2_entry_exit_paired", "O3_top_operators", "O4_gas_position", "O5_operator_trajectories", "O6_wallet_rotation"):
        print(f"\n### {name}\n"); print(open(os.path.join(a.out, name + ".md")).read())
    print(json.dumps({k: v for k, v in K.items() if "|" not in k}, indent=1)[:2000])


if __name__ == "__main__":
    main()
