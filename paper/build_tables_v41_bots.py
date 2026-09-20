"""Paper v4.1 tables that change with the bots-only rerun (public-router flow excluded): Tables 18, 19, 20, 21, 21b,
E1 (per-pool latency), E2 (addresses), E3 (sender trajectories).  Sources: $REPL_ROOT/arb_resp/cmp_bots (compare_bots.py)
and $REPL_ROOT/arb_resp/comp_bots/out (full_components_bots.py).  Formats mirror tables_v4/."""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json, os, re
import pandas as pd, numpy as np

CMP = ROOT + "/arb_resp/cmp_bots"; COMP = ROOT + "/arb_resp/comp_bots/out"; BOTS = ROOT + "/arb_resp/bots"
OUT = ROOT + "/paper/tables_v41"; os.makedirs(OUT, exist_ok=True)
POOLN = {"WBNB/USDT 5 bp": "WBNB/USDT 0.05%", "ETH/USDT 5 bp": "ETH/USDT 0.05%", "BTCB/USDT 5 bp": "BTCB/USDT 0.05%", "WBNB/USDT 1 bp": "WBNB/USDT 0.01%"}
PKEY = {"WBNB-USDT-500": "WBNB/USDT 0.05%", "ETH-USDT-500": "ETH/USDT 0.05%", "BTCB-USDT-500": "BTCB/USDT 0.05%", "WBNB-USDT-100": "WBNB/USDT 0.01%"}
CORE = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500"]
FORKS = ["Lorentz", "Maxwell", "Fermi"]
LAW = {"Lorentz": -0.346, "Maxwell": -0.347, "Fermi": -0.255}
K = json.load(open(f"{CMP}/key_numbers.json"))
KC = json.load(open(f"{COMP}/key_numbers.json"))
um = lambda s: str(s).replace("-", "−")


def md(df):
    return df.to_markdown(index=False, disable_numparse=True)


def read_md(path):
    L = [l for l in open(path).read().splitlines() if l.startswith("|")]
    hdr = [c.strip() for c in L[0].strip("|").split("|")]
    return pd.DataFrame([[c.strip() for c in l.strip("|").split("|")] for l in L[2:]], columns=hdr)


def rng(vals, fmt="{:.0f}"):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return f"{fmt.format(min(vals))}–{fmt.format(max(vals))}" if vals else ""


# ---------------- sharp openings (R7) per pool-regime
R7 = read_md(f"{CMP}/R7_sensitivity.md")
sharp = {}
for _, r in R7.iterrows():
    m = re.match(r"^(-?\d+) / (-?\d+)", r.iloc[6])
    sharp[(r.iloc[0], r.iloc[1], r.iloc[2])] = (int(m.group(1)), int(m.group(2))) if m else (np.nan, np.nan)

# ---------------- Table 18: six regimes, three core pools
rows = []
for f in FORKS:
    for reg in ("pre", "post"):
        ks = [K["R1"][f"{f}|{p}|{reg}"] for p in CORE]
        pn = [{"WBNB-USDT-500": "WBNB/USDT 5 bp", "ETH-USDT-500": "ETH/USDT 5 bp", "BTCB-USDT-500": "BTCB/USDT 5 bp"}[p] for p in CORE]
        s10 = [sharp[(f, p, reg)][0] for p in pn]; s50 = [sharp[(f, p, reg)][1] for p in pn]
        rows.append({"Regime": f"{f}, {reg}", "Δt (s)": f"{ks[0]['dt']:.2f}", "CEX-triggered arbitrages": f"{sum(k['n'] for k in ks):,}",
                     "ℓ̂, 10th percentile (ms)": rng([k["q10"] for k in ks]), "ℓ̂, median (ms)": rng([k["q50"] for k in ks], "{:,.0f}"),
                     "Turnbull median (ms)": rng([k["tb_med"] for k in ks]), "Sharp openings: ℓ̂ 10th / median (ms)": f"{rng(s10)} / {rng(s50)}",
                     "P(first block)": rng([k["pk1"] for k in ks], "{:.2f}"), "On-chain triggers: P(ℓ ≤ Δt)": rng([k["oc1"] for k in ks], "{:.2f}")})
T18 = pd.DataFrame(rows)
open(f"{OUT}/table18_six_regimes.md", "w").write(md(T18))

# ---------------- Table 19: implied by τ (R2)
R2 = read_md(f"{CMP}/R2_implied_vs_tick.md")
rows = []
for _, r in R2.iterrows():
    pool = r.iloc[1].strip()
    if pool not in POOLN:
        continue
    rows.append({"Fork": r.iloc[0], "Pool": POOLN[pool], "√Δt law": um(f"{float(r.iloc[2]):.3f}"), "Implied by τ": um(f"{float(r.iloc[3]):.3f}"),
                 "Fixed-latency counterfactual": um(f"{float(r.iloc[4]):.3f}"), "Latency-change component": um(f"{float(r.iloc[5]):+.3f}"),
                 "ℓ (paper convention, s)": f"{float(r.iloc[6]):.2f}", "Δ median τ / mechanical (ms)": um(r.iloc[10]), "Δ 10th pct. τ / mechanical (ms)": um(r.iloc[11]),
                 "P(first block) post: actual / fixed-latency": r.iloc[12], "Overshoot estimate (Table 8)": um(r.iloc[8])})
T19 = pd.DataFrame(rows)
open(f"{OUT}/table19_tau_implied.md", "w").write(md(T19))

# ---------------- Table 20: pooled core (C2) + placebo pooled rows (C3)
C2 = read_md(f"{COMP}/C2_pooled_core.md")
C3 = read_md(f"{COMP}/C3_placebo_fake_fork.md")
strip_n = lambda s: um(re.sub(r"\s*\[\d+\]$", "", s))
rows = []
for f in FORKS:
    for _, r in C2[C2.fork == f].iterrows():
        rows.append({"Fork": f, "Window": r.iloc[1], "All strict arbitrages": strip_n(r.iloc[2]), "CEX-triggered, total": strip_n(r.iloc[3]), "Jump at the crossing (J)": strip_n(r.iloc[4]),
                     "Movement during τ (M)": strip_n(r.iloc[5]), "Continuation": strip_n(r.iloc[6]), "Same-block back-run": strip_n(r.iloc[7]), "√Δt law": um(f"{LAW[f]:.3f}")})
for f in FORKS:
    r = C3[(C3.fork == f) & (C3.pool == "core pooled")].iloc[0]
    rows.append({"Fork": f, "Window": "placebo: fake fork 15 d before, ±14 d", "All strict arbitrages": strip_n(r.iloc[2]), "CEX-triggered, total": strip_n(r.iloc[3]),
                 "Jump at the crossing (J)": strip_n(r.iloc[4]), "Movement during τ (M)": strip_n(r.iloc[5]), "Continuation": strip_n(r.iloc[6]), "Same-block back-run": strip_n(r.iloc[7]), "√Δt law": "—"})
T20 = pd.DataFrame(rows)
open(f"{OUT}/table20_components_pooled.md", "w").write(md(T20))

# ---------------- Table 21: per pool ±14 d (C1) + weights and Σwβ (C4)
C1 = read_md(f"{COMP}/C1_components_full.md")
C4 = read_md(f"{COMP}/C4_weights_reconstruction.md")
rows = []
for f in FORKS:
    for pool in ["WBNB/USDT 5 bp", "ETH/USDT 5 bp", "BTCB/USDT 5 bp", "WBNB/USDT 1 bp"]:
        r = C1[(C1.fork == f) & (C1.pool == pool) & (C1.window == "±14 d")].iloc[0]
        w = C4[(C4.fork == f) & (C4.pool == pool)].iloc[0]
        rows.append({"Fork": f, "Pool": POOLN[pool], "All strict arbitrages (bot flow)": strip_n(r["all strict arbs"]), "J": strip_n(r["CEX: jump"]), "M": strip_n(r["CEX: move"]),
                     "Continuation": strip_n(r["continuation"]), "Same-block": strip_n(r["same block"]), "Δ share same-block": um(r["Δ share same-block"]), "Δ share continuation": um(r["Δ share cont."]),
                     "Pre-fork weights J / M / cont. / same": f"{float(w['w: jump']):.2f} / {float(w['w: move']):.2f} / {float(w['w: continuation']):.2f} / {float(w['w: same block']):.2f}",
                     "Σ w·β": um(f"{float(w['Σ w·β']):.3f}"), "Table 8 (all flow)": um(r["paper Table 5 (±14 d)"])})
T21 = pd.DataFrame(rows)
open(f"{OUT}/table21_components_per_pool.md", "w").write(md(T21))

# ---------------- Table 21b: sigma elasticity (C5)
C5 = read_md(f"{COMP}/C5_sigma_elasticity.md")
rows = [{"Fork": r.iloc[0], "All strict arbitrages": um(r.iloc[1]), "CEX-triggered, total": um(r.iloc[2]), "J": um(r.iloc[3]), "M": um(r.iloc[4]), "Continuation": um(r.iloc[5]), "Same-block": um(r.iloc[6])} for _, r in C5.iterrows()]
open(f"{OUT}/table21b_sigma_elasticity_components.md", "w").write(md(pd.DataFrame(rows)))

# ---------------- Table E1: per pool x regime (R1 + sharp + median tau)
rows = []
for p in CORE + ["WBNB-USDT-100"]:
    for f in FORKS:
        for reg in ("pre", "post"):
            k = K["R1"][f"{f}|{p}|{reg}"]
            pn = {"WBNB-USDT-500": "WBNB/USDT 5 bp", "ETH-USDT-500": "ETH/USDT 5 bp", "BTCB-USDT-500": "BTCB/USDT 5 bp", "WBNB-USDT-100": "WBNB/USDT 1 bp"}[p]
            s = sharp[(f, pn, reg)]
            rows.append({"Pool": PKEY[p], "Regime": f"{f} {reg}", "Δt (s)": f"{k['dt']:.2f}", "CEX-triggered arbs": f"{k['n']:,}", "Median τ (ms)": f"{k['p50_tau']:.0f}",
                         "ℓ̂ (10th pct.)": f"{k['q10']:.0f} ({k['se10']:.0f})", "ℓ̂ (median)": f"{k['q50']:.0f} ({k['se50']:.0f})", "Turnbull median": f"{k['tb_med']:.0f}",
                         "Sharp openings: ℓ̂ 10th / median": f"{s[0]:.0f} / {s[1]:.0f}", "P(first block)": f"{k['pk1']:.2f}", "On-chain triggers: P(ℓ ≤ Δt)": f"{k['oc1']:.2f}", "n on-chain": f"{k['n_on']:,}"})
open(f"{OUT}/tableF1_latency_per_pool.md", "w").write(md(pd.DataFrame(rows)))

# ---------------- Table E2: addresses (R5)
R5 = read_md(f"{CMP}/R5_addresses.md")
rows = []
for _, r in R5.iterrows():
    if r.iloc[1].strip() not in POOLN:
        continue
    g = lambda i: r.iloc[i]
    rows.append({"Fork": g(0), "Pool": POOLN[g(1).strip()], "Sender contracts, pre → post": g(2), "Active (≥ 20 strict arbs)": g(3), "HHI": g(4), "Top-3 share": g(5),
                 "Contracts covering 90%": g(6), "Stayers / entrants / exits": g(7), "Entrants' share of post-fork arbs": f"{float(g(8)):.2f}",
                 "Paired senders (≥ 200 CEX-triggered arbs on each side)": g(9), "Median change of ℓ̂ (10th pct., ms)": um(f"{float(g(10)):+.0f}") if g(10) not in ("", "nan") else "",
                 "Median change of ℓ̂ (median, ms)": um(f"{float(g(11)):+.0f}") if g(11) not in ("", "nan") else "", "Share with a lower ℓ̂ after the fork": (f"{float(g(12)):.2f}" if g(12) not in ("", "nan") else ""),
                 "P(first block) of paired senders, pre → post": g(13)})
open(f"{OUT}/tableF3_addresses.md", "w").write(md(pd.DataFrame(rows)))

# ---------------- Table E3: sender trajectories (R6b)
R6b = read_md(f"{CMP}/R6b_sender_trajectories.md")
rows = []
for _, r in R6b.iterrows():
    if r.iloc[0].strip() not in POOLN:
        continue
    rows.append({"Pool": POOLN[r.iloc[0].strip()], "Sender contract": r.iloc[1], "Lorentz, pre (3 s)": um(r.iloc[2]), "Lorentz, post (1.5 s)": um(r.iloc[3]), "Maxwell, pre (1.5 s)": um(r.iloc[4]),
                 "Maxwell, post (0.75 s)": um(r.iloc[5]), "Fermi, pre (0.75 s)": um(r.iloc[6]), "Fermi, post (0.45 s)": um(r.iloc[7])})
open(f"{OUT}/tableE3_sender_trajectories.md", "w").write(md(pd.DataFrame(rows)))

for f in ["table18_six_regimes", "table19_tau_implied", "table20_components_pooled", "table21_components_per_pool", "table21b_sigma_elasticity_components", "tableF1_latency_per_pool", "tableF3_addresses", "tableE3_sender_trajectories"]:
    print(f"\n### {f}\n"); print(open(f"{OUT}/{f}.md").read())
