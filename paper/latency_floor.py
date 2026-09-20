"""Latency-floor model for the three tick-reference fork estimates.

Overshoot ∝ σ·sqrt(Δt + ℓ): the arbitrageur's effective delay is the block interval plus a fixed latency ℓ.
Predicted log change at a fork: ½·ln((Δt₁+ℓ)/(Δt₀+ℓ)); ℓ = 0 is the √Δt law.  ℓ is fitted by minimum χ² to the
placebo-clean strict-overshoot estimates (tick reference), with a profile-likelihood 95% CI, for three estimate sets.

    python latency_floor.py            -> three_forks_tick/latency_floor.md, latency_floor.json, fig_latency_floor.png
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os, json
import numpy as np, pandas as pd
from scipy import optimize, stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = ROOT + "/paper/three_forks_tick"
FORKS = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
C = {"Lorentz": "#2a9d8f", "Maxwell": "#2a78d6", "Fermi": "#eb6834"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e6e3"


def load_sets():
    """Placebo-clean tick estimates from tick_cmp/<fork>/key_numbers.json (same numbers as tableA)."""
    K = {f: json.load(open(ROOT + f"/tick_cmp/{f}/key_numbers.json")) for f in FORKS}
    g = lambda f, w, c: (K[f][f"tick|{w}|{c}|overshoot_strict_bps"]["b"], K[f][f"tick|{w}|{c}|overshoot_strict_bps"]["se"])
    sets = {
        "A (levels-type: Lorentz ±30 d trend, Maxwell ±14 d L+vol, Fermi ±14 d L+vol)":
            {"Lorentz": g("Lorentz", "±30 d", "σ+L+vol+趋势"), "Maxwell": g("Maxwell", "±14 d", "σ+L+vol"), "Fermi": g("Fermi", "±14 d", "σ+L+vol")},
        "B (RD-type: Lorentz ±30 d RD, Maxwell ±14 d RD, Fermi ±30 d RD)":
            {"Lorentz": g("Lorentz", "±30 d", "RD"), "Maxwell": g("Maxwell", "±14 d", "RD"), "Fermi": g("Fermi", "±30 d", "RD")},
    }
    pref = {"Lorentz": [g("Lorentz", "±30 d", "σ+L+vol+趋势"), g("Lorentz", "±30 d", "RD")],
            "Maxwell": [g("Maxwell", "±14 d", "σ"), g("Maxwell", "±14 d", "σ+L+vol"), g("Maxwell", "±14 d", "σ+L+vol+趋势"), g("Maxwell", "±14 d", "RD")],
            "Fermi": [g("Fermi", "±14 d", "σ+L+vol"), g("Fermi", "±30 d", "σ+L+vol+趋势"), g("Fermi", "±30 d", "RD")]}
    pooled = {}
    for f, l in pref.items():
        w = np.array([1 / s ** 2 for b, s in l]); b = np.array([b for b, s in l])
        pooled[f] = (float((w * b).sum() / w.sum()), float(np.sqrt(1 / w.sum())))
    sets["C (inverse-variance pool of each fork's placebo-clean specifications)"] = pooled
    return sets


def pred(l, f):
    d0, d1 = FORKS[f]; return 0.5 * np.log((d1 + l) / (d0 + l))


def main():
    sets = load_sets(); rows = []; res = {}
    for name, est in sets.items():
        chi2 = lambda l: sum(((est[f][0] - pred(l, f)) / est[f][1]) ** 2 for f in FORKS)
        r = optimize.minimize_scalar(chi2, bounds=(0, 10), method="bounded"); l, c = r.x, r.fun
        grid = np.linspace(0, 10, 10001); vals = np.array([chi2(g) for g in grid]); ci = grid[vals <= c + 3.84]
        c0 = chi2(0.0)
        res[name] = {"ell": l, "ci": [float(ci.min()), float(ci.max())], "chi2": c, "p": float(1 - stats.chi2.cdf(c, 2)),
                     "chi2_ell0": c0, "p_ell0": float(1 - stats.chi2.cdf(c0, 3)), "est": est,
                     "model": {f: pred(l, f) for f in FORKS}, "next_halving_0.45_to_0.225": 0.5 * np.log((0.225 + l) / (0.45 + l)),
                     "floor_rel_0.45s": float(np.sqrt(l / (0.45 + l))), "floor_rel_3s": float(np.sqrt(l / (3 + l)))}
        rows.append({"estimate set": name, "ℓ (s)": f"{l:.2f}", "95% CI": f"{ci.min():.2f}–{ci.max():.2f}", "χ²(2)": f"{c:.2f}", "p": f"{res[name]['p']:.2f}",
                     "χ² at ℓ=0 (√Δt law, 3 df)": f"{c0:.1f}", "p (ℓ=0)": f"{res[name]['p_ell0']:.3f}",
                     **{f"{f}: est / model / √law": f"{est[f][0]:+.3f} ({est[f][1]:.3f}) / {pred(l, f):+.3f} / {0.5 * np.log(FORKS[f][1] / FORKS[f][0]):+.3f}" for f in FORKS},
                     "next halving 0.45→0.225 s": f"{res[name]['next_halving_0.45_to_0.225']:+.3f}",
                     "floor as Δt→0, rel. to 0.45 s": f"{res[name]['floor_rel_0.45s']:.2f}"})
    t = pd.DataFrame(rows)
    open(os.path.join(OUT, "latency_floor.md"), "w").write(t.to_markdown(index=False))
    json.dump(res, open(os.path.join(OUT, "latency_floor.json"), "w"), indent=1, ensure_ascii=False)
    print(t.T.to_string())

    # figure: overshoot level relative to 3 s blocks, implied by chaining the fork estimates, vs models
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    dts = np.array([3.0, 1.5, 0.75, 0.45]); x = np.linspace(0.05, 3.2, 400)
    for name, r in res.items():
        l = r["ell"]; lab = name.split(" ")[0]
        ax.plot(x, np.sqrt((x + l) / (3 + l)), color={"A": "#7a7a7a", "B": INK, "C": "#b0b0b0"}[lab], lw=1.2,
                ls={"A": "--", "B": "-", "C": ":"}[lab], label=f"latency-floor model, set {lab}: ℓ = {l:.2f} s")
    ax.plot(x, np.sqrt(x / 3), color="#c33", lw=1, ls="-.", label="√Δt law (ℓ = 0)")
    # chained estimates (set B and set A)
    for name, r in res.items():
        lab = name.split(" ")[0]
        if lab == "C":
            continue
        lv = [1.0]; se2 = [0.0]
        for f in ("Lorentz", "Maxwell", "Fermi"):
            b, s = r["est"][f]; lv.append(lv[-1] * np.exp(b)); se2.append(se2[-1] + s ** 2)
        lv = np.array(lv); se = np.sqrt(np.array(se2))
        ax.errorbar(dts, lv, yerr=[lv - lv * np.exp(-1.96 * se), lv * np.exp(1.96 * se) - lv], fmt="o" if lab == "B" else "s",
                    color=INK if lab == "B" else "#7a7a7a", ms=4.5, capsize=2, lw=1, label=f"chained fork estimates, set {lab} (95% CI)")
    ax.set_xscale("log"); ax.set_xticks(dts); ax.set_xticklabels(["3.0", "1.5", "0.75", "0.45"])
    ax.set_xlabel("block interval Δt (s), log scale", fontsize=9, color=INK2)
    ax.set_ylabel("overshoot at arbitrage relative to 3-second blocks", fontsize=9, color=INK2)
    ax.set_title("Arbitrage overshoot along the block-interval roadmap: data vs. √Δt law and latency floor", fontsize=8.6, color=INK, loc="left")
    ax.set_ylim(0.3, 1.1); ax.grid(color=GRID, lw=0.6)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8); ax.legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_latency_floor.png"), dpi=200); plt.close(fig)


if __name__ == "__main__":
    main()
