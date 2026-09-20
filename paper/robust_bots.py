"""Robustness of the pooled core-pool overshoot estimates (Table 4) to excluding router flow.  The same specifications
(three windows; log σ + hour FE; + log L + log volume; + linear trend; RD jump with separate slopes), pool fixed effects,
day-clustered SE, on the hourly panels of the strict overshoot of (a) all flow — must reproduce Table 4 — and (b) bot flow
(public routers excluded), built by arb_component_panel.py from the per-arb tables.  Also the fake-fork placebos of
Table 14 (pre-period split at its midpoint) for the overshoot, and the latency-floor fit on the bot-flow estimates.
Outputs: tables_v41/table15b_bots_core_pooled.md, tables_v41/table16_latency_floor_botsets.md, robust_bots.json"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os, json, glob
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy import optimize, stats

CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
FORKS = ["Lorentz", "Maxwell", "Fermi"]
DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
LAW = {f: 0.5 * np.log(d1 / d0) for f, (d0, d1) in DT.items()}
FORK_TS = {"Lorentz": "2025-04-29 05:05:00", "Maxwell": "2025-06-30 02:30:00", "Fermi": "2026-01-14 02:30:00"}
SPECS = [("log σ + hour FE", "", ""), ("+ log L + log volume", " + np.log(liq_mean) + np.log(volume)", ""),
         ("+ linear trend", " + np.log(liq_mean) + np.log(volume) + t_days", ""),
         ("RD jump (separate slopes)", " + np.log(liq_mean) + np.log(volume)", " + t_days + post:t_days")]
OUT = ROOT + "/paper/tables_v41"
um = lambda s: str(s).replace("-", "−")


def load(kind, fork):
    base = {"all": ROOT + f"/arb_resp/comp/{fork}/arb_response/component_panels", "bots": ROOT + f"/arb_resp/comp_bots/{fork}/arb_response_bots/component_panels"}[kind]
    frames = []
    for p in CORE:
        d = pd.read_csv(f"{base}/{p}.csv"); d["pool"] = p; frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["hour"] = pd.to_datetime(d["hour_ms"], unit="ms", utc=True)
    d["y"] = d["overshoot_all"]
    return d


def clean(d, extra):
    d = d[(d["y"] > 0) & (d["sigma_ps"] > 0)].replace([np.inf, -np.inf], np.nan).dropna(subset=["sigma_ps", "y"])
    if "liq_mean" in extra:
        d = d[d["liq_mean"] > 0]
    if "volume" in extra:
        d = d[d["volume"] > 0]
    return d


def fit(d, extra, rhs_extra="", var="post"):
    d = clean(d, extra + rhs_extra)
    f = f"np.log(y) ~ {var} + np.log(sigma_ps) + C(hod) + C(pool)" + extra + rhs_extra
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return m.params[var], m.bse[var], m.pvalues[var], len(d)


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def window(d, days):
    return d[(d.t_days >= -days) & (d.t_days < days)]


def estimates(kind):
    """{(window, spec): {fork: (b, se, p, n)}} and placebo {(window, spec): {fork: (b, se, p, fake)}}"""
    E, P = {}, {}
    for f in FORKS:
        d30 = load(kind, f); d30 = window(d30, 30); d14 = window(d30, 14); d7 = window(d30, 7)
        for wname, d in (("±30 d", d30), ("±14 d", d14), ("±7 d", d7)):
            for sname, extra, rhs in SPECS:
                if wname == "±7 d" and sname.startswith("RD"):
                    continue
                E.setdefault((wname, sname), {})[f] = fit(d, extra, rhs)
        # fake-fork placebos: pre-period split at its midpoint (Table 14)
        fork_ts = pd.Timestamp(FORK_TS[f], tz="UTC")
        for wname, d in (("±30 d", d30), ("±14 d", d14)):
            pre = d[d.post == 0].copy()
            mid = pre["hour"].min() + (fork_ts - pre["hour"].min()) / 2
            pre["fake"] = (pre["hour"] >= mid).astype(int)
            for sname, extra, rhs in SPECS[:3]:
                b, se, p, n = fit(pre, extra, "", var="fake")
                P.setdefault((wname, sname), {})[f] = (b, se, p, f"{mid:%Y-%m-%d %H:%M}")
    return E, P


def table(E, kind_label):
    rows = []
    for (wname, sname), est in E.items():
        r = {"Window": wname, "Specification": sname}
        el, w = [], []
        for f in FORKS:
            b, se, p, n = est[f]
            r[f"{f} β [share]"] = um(f"{b:+.3f}{star(p)} ({se:.3f}) [{b / LAW[f]:.0%}]")
            e, es = b / np.log(DT[f][1] / DT[f][0]), se / abs(np.log(DT[f][1] / DT[f][0])); el.append(e); w.append(1 / es ** 2)
        el, w = np.array(el), np.array(w); pooled = (w * el).sum() / w.sum(); se_p = np.sqrt(1 / w.sum())
        chi2 = ((el - pooled) ** 2 * w).sum(); p_eq = 1 - stats.chi2.cdf(chi2, 2)
        r["Elasticity L / M / F"] = um(" / ".join(f"{e:.2f}" for e in el)); r["Pooled elasticity"] = um(f"{pooled:.3f} ({se_p:.3f})")
        r["t vs 0.5"] = um(f"{(pooled - 0.5) / se_p:.1f}"); r["Equal (p)"] = f"{p_eq:.2f}"
        rows.append(r)
    return pd.DataFrame(rows)


E_all, P_all = estimates("all")
E_bots, P_bots = estimates("bots")
T4_rep = table(E_all, "all"); T15b = table(E_bots, "bots")
print("### replication of Table 4 (all flow)\n"); print(T4_rep.to_markdown(index=False, disable_numparse=True))
print("\n### bot flow\n"); print(T15b.to_markdown(index=False, disable_numparse=True))

# placebo rows for the bots table (overshoot only), plus the all-flow replication for checking
prow = []
for (wname, sname), est in P_bots.items():
    r = {"Window": wname, "Specification": f"placebo (fake fork at the pre-period midpoint): {sname}"}
    for f in FORKS:
        b, se, p, mid = est[f]; ba, sea, pa, _ = P_all[(wname, sname)][f]
        r[f"{f} β [share]"] = um(f"{b:+.3f}{star(p)} ({se:.3f}) [all flow {ba:+.3f}]")
    r["Elasticity L / M / F"] = ""; r["Pooled elasticity"] = ""; r["t vs 0.5"] = ""; r["Equal (p)"] = ""
    prow.append(r)
T15b_full = pd.concat([T15b, pd.DataFrame(prow)], ignore_index=True)
open(f"{OUT}/table15b_bots_core_pooled.md", "w").write(T15b_full.to_markdown(index=False, disable_numparse=True))
print("\n### placebos (bot flow, all flow in brackets)\n"); print(pd.DataFrame(prow).to_markdown(index=False, disable_numparse=True))

# ---------------- latency-floor fit on bot-flow estimates (sets A and B of Table 16)
def pred(l, f):
    d0, d1 = DT[f]; return 0.5 * np.log((d1 + l) / (d0 + l))


def fit_floor(est):
    chi2 = lambda l: sum(((est[f][0] - pred(l, f)) / est[f][1]) ** 2 for f in FORKS)
    r = optimize.minimize_scalar(chi2, bounds=(0, 10), method="bounded"); l, c = r.x, r.fun
    grid = np.linspace(0, 10, 10001); vals = np.array([chi2(g) for g in grid]); ci = grid[vals <= c + 3.84]
    c0 = chi2(0.0)
    return {"ell": float(l), "ci": [float(ci.min()), float(ci.max())], "chi2": float(c), "p": float(1 - stats.chi2.cdf(c, 2)), "chi2_ell0": float(c0),
            "p_ell0": float(1 - stats.chi2.cdf(c0, 3)), "model": {f: float(pred(l, f)) for f in FORKS},
            "next_halving": float(0.5 * np.log((0.225 + l) / (0.45 + l))), "floor_rel_0.45s": float(np.sqrt(l / (0.45 + l)))}


sets = {}
for kind, E in (("all", E_all), ("bots", E_bots)):
    g = lambda f, w, s: E[(w, s)][f][:2]
    sets[f"A_{kind}"] = {"Lorentz": g("Lorentz", "±30 d", "+ linear trend"), "Maxwell": g("Maxwell", "±14 d", "+ log L + log volume"), "Fermi": g("Fermi", "±14 d", "+ log L + log volume")}
    sets[f"B_{kind}"] = {"Lorentz": g("Lorentz", "±30 d", "RD jump (separate slopes)"), "Maxwell": g("Maxwell", "±14 d", "RD jump (separate slopes)"), "Fermi": g("Fermi", "±30 d", "RD jump (separate slopes)")}
    pref = {"Lorentz": [g("Lorentz", "±30 d", "+ linear trend"), g("Lorentz", "±30 d", "RD jump (separate slopes)")],
            "Maxwell": [g("Maxwell", "±14 d", "log σ + hour FE"), g("Maxwell", "±14 d", "+ log L + log volume"), g("Maxwell", "±14 d", "+ linear trend"), g("Maxwell", "±14 d", "RD jump (separate slopes)")],
            "Fermi": [g("Fermi", "±14 d", "+ log L + log volume"), g("Fermi", "±30 d", "+ linear trend"), g("Fermi", "±30 d", "RD jump (separate slopes)")]}
    pooled = {}
    for f, l in pref.items():
        w = np.array([1 / s ** 2 for b, s in l]); b = np.array([b for b, s in l]); pooled[f] = (float((w * b).sum() / w.sum()), float(np.sqrt(1 / w.sum())))
    sets[f"C_{kind}"] = pooled
res = {k: fit_floor(v) for k, v in sets.items()}
rows = []
labels = {"A_bots": "D (bot flow, specifications of A)", "B_bots": "E (bot flow, specifications of B)", "C_bots": "F (bot flow, specifications of C)",
          "A_all": "A (all flow, replication)", "B_all": "B (all flow, replication)", "C_all": "C (all flow, replication)"}
for k in ["A_all", "B_all", "C_all", "A_bots", "B_bots", "C_bots"]:
    r = res[k]; est = sets[k]
    rows.append({"Estimate set": labels[k], "ℓ (s)": f"{r['ell']:.2f}", "95% CI": f"{r['ci'][0]:.2f}–{r['ci'][1]:.2f}", "χ²(2), p": f"{r['chi2']:.2f}, {r['p']:.2f}",
                 "χ² at ℓ = 0 (3 df), p": f"{r['chi2_ell0']:.1f}, {r['p_ell0']:.3f}",
                 **{f"{f}: est. / model / √law": um(f"{est[f][0]:.3f} ({est[f][1]:.3f}) / {r['model'][f]:.3f} / {LAW[f]:.3f}") for f in FORKS},
                 "Next halving 0.45 → 0.225 s": um(f"{r['next_halving']:.3f}"), "Floor relative to 0.45 s": f"{r['floor_rel_0.45s']:.2f}"})
T16 = pd.DataFrame(rows)
open(f"{OUT}/table16_latency_floor_botsets.md", "w").write(T16.to_markdown(index=False, disable_numparse=True))
print("\n### latency floor\n"); print(T16.to_markdown(index=False, disable_numparse=True))
json.dump({"estimates_all": {f"{w}|{s}": {f: list(v) for f, v in est.items()} for (w, s), est in E_all.items()},
           "estimates_bots": {f"{w}|{s}": {f: list(v) for f, v in est.items()} for (w, s), est in E_bots.items()},
           "placebo_all": {f"{w}|{s}": {f: list(v) for f, v in est.items()} for (w, s), est in P_all.items()},
           "placebo_bots": {f"{w}|{s}": {f: list(v) for f, v in est.items()} for (w, s), est in P_bots.items()},
           "floor": res, "sets": {k: {f: list(v) for f, v in est.items()} for k, est in sets.items()}},
          open(ROOT + "/paper/robust_bots.json", "w"), indent=1, default=float)
