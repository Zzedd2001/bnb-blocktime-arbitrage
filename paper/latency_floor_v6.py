#!/usr/bin/env python3
"""latency_floor_v6.py — the latency-floor model fitted to the main-specification estimates (referee M5).

Overshoot ∝ σ√(Δt + ℓ); predicted log change at a fork ½·ln((Δt₁+ℓ)/(Δt₀+ℓ)); ℓ = 0 is the √Δt law.  ℓ is fitted by
minimum χ² to the three RD ±30 d estimates of tables_v6/main_spec.json for (a) the strict overshoot of all flow,
(b) the strict overshoot of bot flow and (c) the overshoot of CEX-triggered bot arbitrages, with profile-likelihood
95% intervals.  Also the composition route to the forward prediction (component weights × component responses).
Outputs: tables_v6/table_latency_floor.md, latency_floor_v6.json
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json
import os

import numpy as np
import pandas as pd
from scipy import optimize, stats

FORKS = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
OUT = ROOT + "/paper/tables_v6"
M = json.load(open(f"{OUT}/main_spec.json"))["main"]
SETS = {"Strict overshoot, all flow (headline)": "Overshoot at strict arbitrage (headline)",
        "Strict overshoot, bot flow": "Strict overshoot, bot flow (public routers excluded)",
        "CEX-triggered bot arbitrages": "Overshoot of CEX-triggered bot arbitrages"}
um = lambda s: str(s).replace("-", "−")


def pred(l, f):
    d0, d1 = FORKS[f]
    return 0.5 * np.log((d1 + l) / (d0 + l))


rows, res = [], {}
for name, key in SETS.items():
    est = {f: (M[f"{key}|{f}"]["b"], M[f"{key}|{f}"]["se"]) for f in FORKS}
    chi2 = lambda l: sum(((est[f][0] - pred(l, f)) / est[f][1]) ** 2 for f in FORKS)
    r = optimize.minimize_scalar(chi2, bounds=(0, 10), method="bounded")
    l, c = float(r.x), float(r.fun)
    grid = np.linspace(0, 10, 20001)
    vals = np.array([chi2(g) for g in grid])
    ci = grid[vals <= c + 3.84]
    c0 = chi2(0.0)
    nh = 0.5 * np.log((0.225 + l) / (0.45 + l))
    nh_ci = sorted([0.5 * np.log((0.225 + x) / (0.45 + x)) for x in (ci.min(), ci.max())])
    floor = float(np.sqrt(l / (0.45 + l)))
    floor_ci = sorted([float(np.sqrt(x / (0.45 + x))) for x in (ci.min(), ci.max())])
    res[name] = {"ell": l, "ci": [float(ci.min()), float(ci.max())], "chi2": c, "p": float(1 - stats.chi2.cdf(c, 2)), "chi2_ell0": c0,
                 "p_ell0": float(1 - stats.chi2.cdf(c0, 3)), "est": est, "model": {f: pred(l, f) for f in FORKS},
                 "next_halving": nh, "next_halving_ci": nh_ci, "floor_rel_0.45s": floor, "floor_ci": floor_ci}
    rows.append({"Estimate set (RD jump, ±30 d)": name, "ℓ (s)": f"{l:.2f}", "95% CI": f"{ci.min():.2f}–{ci.max():.2f}",
                 "χ²(2), p": f"{c:.2f}, {res[name]['p']:.2f}", "χ² at ℓ = 0 (3 df), p": f"{c0:.1f}, {res[name]['p_ell0']:.3f}",
                 **{f"{f}: est. / model / √law": um(f"{est[f][0]:+.3f} ({est[f][1]:.3f}) / {pred(l, f):+.3f} / {0.5 * np.log(FORKS[f][1] / FORKS[f][0]):+.3f}") for f in FORKS},
                 "Next halving 0.45 → 0.225 s (95% CI)": um(f"{nh:+.3f} ({nh_ci[0]:+.3f} to {nh_ci[1]:+.3f})"),
                 "Floor relative to 0.45 s (95% CI)": f"{floor:.2f} ({floor_ci[0]:.2f}–{floor_ci[1]:.2f})"})
T = pd.DataFrame(rows)
open(f"{OUT}/table_latency_floor.md", "w").write(T.to_markdown(index=False, disable_numparse=True))

# composition route: pre-Fermi component weights (four liquid pools, Table D3) and component responses at Fermi
W = {"J": [0.32, 0.18, 0.19, 0.30], "M": [0.29, 0.30, 0.20, 0.22], "cont": [0.31, 0.29, 0.33, 0.30], "same": [0.08, 0.22, 0.28, 0.17]}
w = {k: float(np.mean(v)) for k, v in W.items()}
law_half = 0.5 * np.log(0.5)
cont_resp_main = M["Continuation|Fermi"]["b"] / (0.5 * np.log(0.45 / 0.75))     # share of the law that continuations delivered at Fermi (main spec)
cont_resp_14 = 0.179 / 0.255                                                   # ±14 d estimate of Table 11
comp = {"weights": w, "M_only": w["M"] * law_half, "with_continuations_main": w["M"] * law_half + w["cont"] * cont_resp_main * law_half,
        "with_continuations_14d": w["M"] * law_half + w["cont"] * cont_resp_14 * law_half, "cont_response_share_main": cont_resp_main, "cont_response_share_14d": cont_resp_14,
        "unresponsive_share_preFermi": w["J"] + w["same"]}
res["composition_route"] = comp

# refit with the reference lagged 250 ms (Appendix C, Table C5, last block): lag-250 RD ±30 d estimates for Maxwell
# and Fermi from lag_cmp/tableL1_core_raw.csv, the lag-0 estimate for Lorentz (whole-second pre-fork timestamps)
lag_csv = os.path.join(os.path.dirname(OUT), "..", "lag_cmp", "tableL1_core_raw.csv")
if os.path.exists(lag_csv):
    L = pd.read_csv(lag_csv)
    L = L[(L["window"] == "±30 d") & (L["spec"] == "RD") & (L["outcome"] == "overshoot (strict)")].set_index("fork")
    key = SETS["Strict overshoot, all flow (headline)"]
    est = {"Lorentz": (M[f"{key}|Lorentz"]["b"], M[f"{key}|Lorentz"]["se"]),
           **{f: (float(L.loc[f, "_b_lag250"]), float(L.loc[f, "_se_lag250"])) for f in ("Maxwell", "Fermi")}}
    chi2 = lambda l: sum(((est[f][0] - pred(l, f)) / est[f][1]) ** 2 for f in FORKS)
    r = optimize.minimize_scalar(chi2, bounds=(0, 10), method="bounded")
    l, c = float(r.x), float(r.fun)
    grid = np.linspace(0, 10, 20001)
    ci = grid[np.array([chi2(g) for g in grid]) <= c + 3.84]
    res["lag250_refit_main_spec"] = {"ell": l, "ci": [float(ci.min()), float(ci.max())], "chi2": c, "p": float(1 - stats.chi2.cdf(c, 2)),
                                     "chi2_ell0": chi2(0.0), "est": est, "next_halving": 0.5 * np.log((0.225 + l) / (0.45 + l)),
                                     "floor_rel_0.45s": float(np.sqrt(l / (0.45 + l)))}
    print("lag-250 refit:", json.dumps(res["lag250_refit_main_spec"], indent=1))
json.dump(res, open(f"{OUT}/latency_floor_v6.json", "w"), indent=1)
print(T.T.to_string())
print(json.dumps(comp, indent=1))
