"""Full-sample decomposition regressions from the component panels (arb_component_panel.py, three forks).
Outputs $REPL_ROOT/arb_resp/comp/out/: C1 (per pool, ±14/±30 d, all components), C2 (pooled core pools with pool FE),
C3 (placebo fake fork at −15 d), C4 (weights + Σwβ reconstruction), C5 (σ-elasticities by component), F5_full.png, key_numbers.json.
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))

import os, json, glob
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = ROOT + "/arb_resp/comp"; OUT = os.path.join(ROOT, "out"); os.makedirs(OUT, exist_ok=True)
FORKS = ["Lorentz", "Maxwell", "Fermi"]
DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
CORE = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-100"]
LABEL = {"WBNB-USDT-500": "WBNB/USDT 5 bp", "ETH-USDT-500": "ETH/USDT 5 bp", "BTCB-USDT-500": "BTCB/USDT 5 bp", "WBNB-USDT-100": "WBNB/USDT 1 bp"}
COMPS = [("overshoot_all", "all strict arbs"), ("cex", "CEX-triggered"), ("cex_jump", "CEX: jump"), ("cex_move", "CEX: move"),
         ("continuation", "continuation"), ("same_block", "same block")]
KEY = {}
S_SAMPLE = json.load(open(ROOT + "/arb_resp/cmp/key_numbers.json"))          # sample-based results (R2 τ-implied, R3c)
TAU = {f"{f}|{p}": S_SAMPLE["R2"][f"{f}|{p}"]["impl"] for f in FORKS for p in CORE}
PAPER = {f"{f}|{p}": S_SAMPLE["R2"][f"{f}|{p}"]["tick"] for f in FORKS for p in CORE}
PAPER_SE = {f"{f}|{p}": S_SAMPLE["R2"][f"{f}|{p}"]["tick_se"] for f in FORKS for p in CORE}


def load(f, p):
    d = pd.read_csv(os.path.join(ROOT, f, "arb_response", "component_panels", f"{p}.csv"))
    d["day"] = pd.to_datetime(d["day"]); d["pool"] = p; d["fork"] = f
    return d


def beta(d, y, days, center=0.0, min_n=5, controls="np.log(sigma_ps) + np.log(liq_mean) + np.log(volume)", pool_fe=False):
    x = d[((d["t_days"] - center).abs() <= days) & d[y].notna() & (d[y] > 0) & (d["sigma_ps"] > 0) & (d["volume"] > 0) & (d["liq_mean"] > 0)].copy()
    if y + "_n" in x:
        x = x[x[y + "_n"] >= min_n]
    x["post_"] = (x["t_days"] > center).astype(int)
    if len(x) < 60 or x["post_"].nunique() < 2:
        return np.nan, np.nan, int(len(x)), np.nan
    fe = " + C(pool)" if pool_fe else ""
    m = smf.ols(f"np.log({y}) ~ post_ + {controls} + C(hod){fe}", data=x).fit(cov_type="cluster", cov_kwds={"groups": x["day"]})
    return float(m.params["post_"]), float(m.bse["post_"]), int(len(x)), float(m.params["np.log(sigma_ps)"])


def share_beta(d, y, days, center=0.0, min_n=5):
    x = d[((d["t_days"] - center).abs() <= days) & (d["n"] >= min_n) & (d["sigma_ps"] > 0)].copy()
    x["post_"] = (x["t_days"] > center).astype(int)
    if len(x) < 60 or x["post_"].nunique() < 2:
        return np.nan, np.nan, int(len(x))
    m = smf.ols(f"{y} ~ post_ + np.log(sigma_ps) + C(hod)", data=x).fit(cov_type="cluster", cov_kwds={"groups": x["day"]})
    return float(m.params["post_"]), float(m.bse["post_"]), int(len(x))


def fmt(b, s, n=None):
    if not np.isfinite(b):
        return ""
    stars = "***" if abs(b / s) > 2.576 else "**" if abs(b / s) > 1.96 else "*" if abs(b / s) > 1.645 else ""
    return f"{b:+.3f}{stars} ({s:.3f})" + (f" [{n}]" if n is not None else "")


D = {(f, p): load(f, p) for f in FORKS for p in CORE}

# ---------------------------------------------------------------- C1 per pool
rows = []; C1 = {}
for f in FORKS:
    for p in CORE:
        d = D[(f, p)]
        for days in (14, 30):
            r = {"fork": f, "pool": LABEL[p], "window": f"±{days} d"}
            for y, lab in COMPS:
                b, s, n, _ = beta(d, y, days)
                C1[f"{f}|{p}|{days}|{y}"] = [b, s, n]; r[lab] = fmt(b, s, n)
            for y, lab in (("share_cex", "Δ share CEX"), ("share_same_block", "Δ share same-block"), ("share_continuation", "Δ share cont.")):
                b, s, n = share_beta(d, y, days); C1[f"{f}|{p}|{days}|{y}"] = [b, s, n]; r[lab] = fmt(b, s)
            r["τ-implied (move)"] = f"{TAU[f'{f}|{p}']:+.3f}"; r["√Δt law"] = f"{0.5 * np.log(DT[f][1] / DT[f][0]):+.3f}"
            r["paper Table 5 (±14 d)"] = f"{PAPER[f'{f}|{p}']:+.3f} ({PAPER_SE[f'{f}|{p}']:.3f})"
            rows.append(r)
T1 = pd.DataFrame(rows)
open(os.path.join(OUT, "C1_components_full.md"), "w").write(T1.to_markdown(index=False))
KEY["C1"] = C1

# ---------------------------------------------------------------- C2 pooled core 5 bp pools (pool FE)
rows = []; C2 = {}
for f in FORKS:
    d = pd.concat([D[(f, p)] for p in CORE[:3]], ignore_index=True)
    for days in (7, 14, 30):
        r = {"fork": f, "window": f"±{days} d"}
        for y, lab in COMPS:
            b, s, n, _ = beta(d, y, days, pool_fe=True)
            C2[f"{f}|{days}|{y}"] = [b, s, n]; r[lab] = fmt(b, s, n)
        r["√Δt law"] = f"{0.5 * np.log(DT[f][1] / DT[f][0]):+.3f}"
        rows.append(r)
T2 = pd.DataFrame(rows)
open(os.path.join(OUT, "C2_pooled_core.md"), "w").write(T2.to_markdown(index=False))
KEY["C2"] = C2

# ---------------------------------------------------------------- C3 placebo: fake fork at −15 d, ±14 d window inside the pre period
rows = []; C3 = {}
for f in FORKS:
    for p in CORE:
        d = D[(f, p)]
        r = {"fork": f, "pool": LABEL[p]}
        for y, lab in COMPS:
            b, s, n, _ = beta(d, y, 14, center=-15.0)
            C3[f"{f}|{p}|{y}"] = [b, s, n]; r[lab] = fmt(b, s, n)
        rows.append(r)
    d = pd.concat([D[(f, p)] for p in CORE[:3]], ignore_index=True)
    r = {"fork": f, "pool": "core pooled"}
    for y, lab in COMPS:
        b, s, n, _ = beta(d, y, 14, center=-15.0, pool_fe=True)
        C3[f"{f}|pooled|{y}"] = [b, s, n]; r[lab] = fmt(b, s, n)
    rows.append(r)
T3 = pd.DataFrame(rows)
open(os.path.join(OUT, "C3_placebo_fake_fork.md"), "w").write(T3.to_markdown(index=False))
KEY["C3"] = C3

# ---------------------------------------------------------------- C4 weights and Σwβ
rows = []; C4 = {}
for f in FORKS:
    W = json.load(open(os.path.join(ROOT, f, "arb_response", "component_panels", "component_summary.json")))["weights"]
    for p in CORE:
        w = W[p]["14d"]
        wts = {"cex_jump": w["w_cex_jump"], "cex_move": w["w_cex_move"], "continuation": w["w_continuation"], "same_block": w["w_same_block"], "onchain": w["w_onchain"], "long": w["w_long"]}
        b = {k: C1[f"{f}|{p}|14|{k}"][0] for k in ("cex_jump", "cex_move", "continuation", "same_block")}
        b = {k: (v if np.isfinite(v) else 0.0) for k, v in b.items()}
        swb = sum(wts[k] * b[k] for k in b)
        law = 0.5 * np.log(DT[f][1] / DT[f][0])
        C4[f"{f}|{p}"] = {"w": wts, "beta": b, "sum_w_beta": swb, "beta_total": C1[f"{f}|{p}|14|overshoot_all"][0], "paper": PAPER[f"{f}|{p}"],
                          "w_move_x_law": wts["cex_move"] * law, "w_move_x_beta_move": wts["cex_move"] * b["cex_move"], "n_strict_pre14": w["n"], "mean_overshoot_pre14": w["mean_overshoot_bps"],
                          "insensitive_share": wts["cex_jump"] + wts["same_block"]}
        rows.append({"fork": f, "pool": LABEL[p], "strict arbs (pre, ±14 d)": f"{w['n']:,}", "mean overshoot (bp)": f"{w['mean_overshoot_bps']:.2f}",
                     "w: jump": f"{wts['cex_jump']:.2f}", "w: move": f"{wts['cex_move']:.2f}", "w: continuation": f"{wts['continuation']:.2f}", "w: same block": f"{wts['same_block']:.2f}", "w: other": f"{wts['onchain'] + wts['long']:.2f}",
                     "β total (±14 d)": f"{C1[f'{f}|{p}|14|overshoot_all'][0]:+.3f}", "paper": f"{PAPER[f'{f}|{p}']:+.3f}", "Σ w·β": f"{swb:+.3f}",
                     "w_move × β_move": f"{wts['cex_move'] * b['cex_move']:+.3f}", "w_move × √law": f"{wts['cex_move'] * law:+.3f}", "w_cont × β_cont": f"{wts['continuation'] * b['continuation']:+.3f}"})
T4 = pd.DataFrame(rows)
open(os.path.join(OUT, "C4_weights_reconstruction.md"), "w").write(T4.to_markdown(index=False))
KEY["C4"] = C4
# fork means
means = {}
for f in FORKS:
    for k in ("sum_w_beta", "beta_total", "paper", "w_move_x_law", "w_move_x_beta_move", "insensitive_share"):
        means[f"{f}|{k}"] = float(np.mean([C4[f"{f}|{p}"][k] for p in CORE]))
        means[f"{f}|{k}|5bp"] = float(np.mean([C4[f"{f}|{p}"][k] for p in CORE[:3]]))
    for k in ("cex_jump", "cex_move", "continuation", "same_block"):
        means[f"{f}|w_{k}"] = float(np.mean([C4[f"{f}|{p}"]["w"][k] for p in CORE]))
for k in ("cex_jump", "cex_move", "continuation", "same_block"):
    means[f"all|w_{k}"] = float(np.mean([C4[f"{f}|{p}"]["w"][k] for f in FORKS for p in CORE]))
    means[f"all|w_{k}|range"] = [float(min(C4[f"{f}|{p}"]["w"][k] for f in FORKS for p in CORE)), float(max(C4[f"{f}|{p}"]["w"][k] for f in FORKS for p in CORE))]
KEY["C4_means"] = means

# ---------------------------------------------------------------- C5 σ-elasticity by component (±30 d, pooled core with pool FE)
rows = []; C5 = {}
for f in FORKS:
    d = pd.concat([D[(f, p)] for p in CORE[:3]], ignore_index=True)
    r = {"fork": f}
    for y, lab in COMPS:
        b, s, n, el = beta(d, y, 30, pool_fe=True)
        C5[f"{f}|{y}"] = el; r[lab] = f"{el:.2f}" if np.isfinite(el) else ""
    rows.append(r)
T5 = pd.DataFrame(rows)
open(os.path.join(OUT, "C5_sigma_elasticity.md"), "w").write(T5.to_markdown(index=False))
KEY["C5"] = C5

# ---------------------------------------------------------------- F5 (full sample)
fig, ax = plt.subplots(figsize=(7.4, 4.4))
labs = []
for i, (f, p) in enumerate([(f, p) for f in FORKS for p in CORE]):
    for y, col, off, mk in (("cex_move", "#2a78d6", -0.22, "o"), ("cex_jump", "#0b0b0b", 0.0, "s"), ("same_block", "#b0b0b0", 0.22, "^")):
        b, s, n = C1[f"{f}|{p}|14|{y}"]
        if np.isfinite(b):
            ax.errorbar(i + off, b, yerr=1.96 * s, fmt=mk, color=col, ms=4.5, capsize=2, lw=1,
                        label={"cex_move": "CEX move during τ", "cex_jump": "jump at the crossing tick", "same_block": "same-block (back-run)"}[y] if i == 0 else None)
    ax.plot(i - 0.22, 0.5 * np.log(DT[f][1] / DT[f][0]), "_", color="#eb6834", ms=12, mew=2, label="√Δt law ½·ln(Δt₁/Δt₀)" if i == 0 else None)
    labs.append(f"{f[:3]}\n{LABEL[p].split('/')[0]}{'1' if p.endswith('100') else ''}")
ax.axhline(0, color="#999", lw=0.8); ax.set_xticks(range(12)); ax.set_xticklabels(labs, fontsize=7)
ax.set_ylabel("fork effect, log points (±14 d, σ+L+vol, hour FE, day-clustered)", fontsize=8.5); ax.legend(fontsize=7, frameon=False); ax.grid(color="#e6e6e3", lw=0.6)
ax.set_title("Fork effect by component (full sample): the CEX move during τ falls, the crossing jump and back-runs do not", fontsize=8, loc="left")
for s_ in ("top", "right"):
    ax.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F5_component_effects_full.png"), dpi=170); plt.close(fig)

json.dump(KEY, open(os.path.join(OUT, "key_numbers.json"), "w"), indent=1, default=float)
for name in ("C1_components_full", "C2_pooled_core", "C3_placebo_fake_fork", "C4_weights_reconstruction", "C5_sigma_elasticity"):
    print(f"\n### {name}\n"); print(open(os.path.join(OUT, name + ".md")).read())
print(json.dumps(means, indent=0)[:3000])
