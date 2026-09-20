"""Reference-alignment robustness: aggTrades reference at the block timestamp (lag 0) vs 250 ms before it (lag 250),
Fermi and Maxwell.  Same panels, same specifications.

Outputs (lag_cmp/):
  tableL1_core.md          core pooled post coefficients, lag 0 vs lag 250, all windows/specs, 5 outcomes
  tableL2_sigma.md         σ-elasticity of strict overshoot (σ-only spec), pooled core, lag 0 vs lag 250
  tableL3_levels.md        regime levels (arb share, LP loss bp, strict overshoot bp, kline-vs-ref gap), lag 0 vs lag 250
  tableL4_three_forks.md   three-fork elasticities with lag-250 estimates for Maxwell/Fermi (Lorentz lag 0), pooled + equality test
  tableL5_latency.md       latency-floor refit with lag-250 estimates
  tableL6_wedge.md         hour-level wedge log(overshoot lag250 / lag0): RD jump at the fork
  key_numbers.json
"""
from __future__ import annotations
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os, json
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy import stats, optimize

ROOT = ROOT + ""; OUT = os.path.join(ROOT, "lag_cmp"); os.makedirs(OUT, exist_ok=True)
CFG = {
    "Fermi": {"lag0": (f"{ROOT}/fermi_tick/bundle/analysis_agg", f"{ROOT}/fermi_tick/bundle/analysis_agg_14d", f"{ROOT}/fermi_tick/bundle/results_agg"),
              "lag250": (f"{ROOT}/fermi_lag250/bundle/analysis_agg_lag250", f"{ROOT}/fermi_lag250/bundle/analysis_agg_lag250_14d", f"{ROOT}/fermi_lag250/bundle/results_agg_lag250"),
              "dt": (0.75, 0.45)},
    "Maxwell": {"lag0": (f"{ROOT}/maxwell_tick/bundle/analysis_agg", f"{ROOT}/maxwell_tick/bundle/analysis_agg_14d", f"{ROOT}/maxwell_tick/bundle/results_agg"),
                "lag250": (f"{ROOT}/maxwell_lag250/bundle/analysis_agg_lag250", f"{ROOT}/maxwell_lag250/bundle/analysis_agg_lag250_14d", f"{ROOT}/maxwell_lag250/bundle/results_agg_lag250"),
                "dt": (1.5, 0.75)},
}
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
OUTCOMES = [("overshoot (strict)", "overshoot_strict_bps"), ("overshoot (all)", "overshoot_bps"), ("arb profit", "arb_profit"),
            ("LP loss (total)", "arb_loss"), ("loss per arb", "loss_per_arb"), ("arbs/h", "n_arb")]
CONTROLS = [("σ", ""), ("σ+L+vol", " + np.log(liq_mean) + np.log(volume)"), ("σ+L+vol+trend", " + np.log(liq_mean) + np.log(volume) + t_days")]
FORKS3 = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}


def clean(d, y, extra):
    d = d[(d[y] > 0) & (d["sigma_ps"] > 0)].replace([np.inf, -np.inf], np.nan).dropna(subset=["sigma_ps", y])
    d = d[d["liq_mean"] > 0]
    if "volume" in extra:
        d = d[d["volume"] > 0]
    return d


def fit(d, y, extra, rhs_extra="", pool_fe=True):
    d = clean(d, y, extra)
    f = f"np.log({y}) ~ post + np.log(sigma_ps) + C(hod)" + (" + C(pool)" if pool_fe else "") + extra + rhs_extra
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return m, len(d)


def star(p): return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
def cell(m, v="post"): return f"{m.params[v]:+.3f}{star(m.pvalues[v])} ({m.bse[v]:.3f})"
def window(p, days): return p[(p.t_days >= -days) & (p.t_days < days)]


def load(cfg):
    P = {}
    for lag in ("lag0", "lag250"):
        a30, a14, _ = cfg[lag]
        for w, path in ((30, a30), (14, a14)):
            d = pd.read_parquet(os.path.join(path, "hourly_panel.parquet")); d["hour"] = pd.to_datetime(d["hour"], utc=True)
            P[(lag, w)] = d
    return P


def main():
    key = {}; L1 = []; L2 = []; L3 = []; L6 = []; est = {}
    for fork, cfg in CFG.items():
        P = load(cfg); lndt = np.log(cfg["dt"][1] / cfg["dt"][0]); th = 0.5 * lndt
        for w in (30, 14, 7):
            for cname, extra in CONTROLS + [("RD", CONTROLS[1][1])]:
                if cname == "RD" and w == 7:
                    continue
                for lab, y in OUTCOMES:
                    r = {"fork": fork, "window": f"±{w} d", "spec": cname, "outcome": lab}
                    for lag in ("lag0", "lag250"):
                        d = P[(lag, 30 if w == 30 else 14)]; d = window(d, 7) if w == 7 else d; d = d[d.pool.isin(CORE)]
                        m, n = fit(d, y, extra, rhs_extra=(" + t_days + post:t_days" if cname == "RD" else ""))
                        r[lag] = cell(m); r[f"_b_{lag}"] = m.params["post"]; r[f"_se_{lag}"] = m.bse["post"]
                        key[f"{fork}|{lag}|±{w} d|{cname}|{y}"] = {"b": float(m.params["post"]), "se": float(m.bse["post"]), "n": n}
                    r["Δ (lag250 − lag0)"] = f"{r['_b_lag250'] - r['_b_lag0']:+.3f}"
                    if y == "overshoot_strict_bps":
                        r["share of prediction lag0 / lag250"] = f"{r['_b_lag0'] / th:.0%} / {r['_b_lag250'] / th:.0%}"
                        r["elasticity lag0 / lag250"] = f"{r['_b_lag0'] / lndt:.2f} / {r['_b_lag250'] / lndt:.2f}"
                        est[(fork, f"±{w} d", cname)] = {lag: (r[f"_b_{lag}"], r[f"_se_{lag}"]) for lag in ("lag0", "lag250")}
                    L1.append(r)
        # σ elasticity (σ-only spec), pooled core
        for w in (30, 14):
            r = {"fork": fork, "window": f"±{w} d"}
            for lag in ("lag0", "lag250"):
                d = P[(lag, w)]; d = d[d.pool.isin(CORE)]
                m, n = fit(d, "overshoot_strict_bps", "")
                r[f"σ-elasticity {lag}"] = cell(m, "np.log(sigma_ps)")
                key[f"sigma|{fork}|{lag}|{w}"] = {"b": float(m.params["np.log(sigma_ps)"]), "se": float(m.bse["np.log(sigma_ps)"])}
            L2.append(r)
        # levels
        for pool in CORE + ["WBNB-USDT-100"]:
            r = {"fork": fork, "pool": pool}
            for lag in ("lag0", "lag250"):
                reg = pd.read_csv(os.path.join(cfg[lag][2], pool, "regime_table.csv"), index_col=0)
                for metric, lab in (("arb_swaps_share", "arb share"), ("arb_loss_bps_of_volume", "LP loss (bp)"), ("lp_net_bps_of_volume", "LP net (bp)"),
                                    ("ref_kline_vs_tick_mean_abs_bps", "|kline/ref − 1| (bp)")):
                    r[f"{lab} {lag}"] = f"{reg.loc[metric, 'pre']:.2f} / {reg.loc[metric, 'post']:.2f}"
                # strict overshoot level from the ±14 d panel
                d = P[(lag, 14)]; d = d[d.pool == pool]
                ov = [np.average(d[d.post == p].overshoot_strict_bps.fillna(0), weights=d[d.post == p].n_arb_strict) for p in (0, 1)]
                r[f"strict overshoot (bp, ±14 d) {lag}"] = f"{ov[0]:.2f} / {ov[1]:.2f}"
                key[f"level|{fork}|{pool}|{lag}"] = {"ov_pre": ov[0], "ov_post": ov[1], "arb_loss_bp": [float(reg.loc["arb_loss_bps_of_volume", "pre"]), float(reg.loc["arb_loss_bps_of_volume", "post"])],
                                                    "arb_share": [float(reg.loc["arb_swaps_share", "pre"]), float(reg.loc["arb_swaps_share", "post"])]}
            L3.append(r)
        # hour-level wedge lag250 vs lag0
        for w in (30, 14):
            k = P[("lag0", w)]; t = P[("lag250", w)]
            cols = ["pool", "hour", "overshoot_strict_bps", "arb_profit", "n_arb"]
            m = k[cols + ["sigma_ps", "post", "hod", "day", "t_days"]].merge(t[cols], on=["pool", "hour"], suffixes=("_0", "_250"))
            m = m[m.pool.isin(CORE)]
            r = {"fork": fork, "window": f"±{w} d"}
            for lab, y in (("overshoot (strict)", "overshoot_strict_bps"), ("arb profit", "arb_profit"), ("arbs/h", "n_arb")):
                m[f"w_{y}"] = np.log(m[f"{y}_250"]) - np.log(m[f"{y}_0"])
                d = m.replace([np.inf, -np.inf], np.nan).dropna(subset=[f"w_{y}", "sigma_ps"]); d = d[d.sigma_ps > 0]
                mod = smf.ols(f"w_{y} ~ post + t_days + post:t_days + np.log(sigma_ps) + C(hod) + C(pool)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
                r[f"wedge mean pre/post: {lab}"] = f"{np.nanmean(d[d.post == 0][f'w_{y}']):+.3f} / {np.nanmean(d[d.post == 1][f'w_{y}']):+.3f}"
                r[f"RD jump: {lab}"] = cell(mod)
                key[f"wedge|{fork}|{w}|{y}"] = {"jump": float(mod.params["post"]), "se": float(mod.bse["post"]), "mean_pre": float(np.nanmean(d[d.post == 0][f'w_{y}'])), "mean_post": float(np.nanmean(d[d.post == 1][f'w_{y}']))}
            L6.append(r)
    t1 = pd.DataFrame(L1); show = t1[[c for c in t1.columns if not c.startswith("_")]]
    open(os.path.join(OUT, "tableL1_core.md"), "w").write(show.to_markdown(index=False)); t1.to_csv(os.path.join(OUT, "tableL1_core_raw.csv"), index=False)
    open(os.path.join(OUT, "tableL2_sigma.md"), "w").write(pd.DataFrame(L2).to_markdown(index=False))
    open(os.path.join(OUT, "tableL3_levels.md"), "w").write(pd.DataFrame(L3).to_markdown(index=False))
    open(os.path.join(OUT, "tableL6_wedge.md"), "w").write(pd.DataFrame(L6).to_markdown(index=False))

    # ---------------- three forks with lag-250 estimates for Maxwell / Fermi (Lorentz: lag 0)
    lor = pd.read_csv(f"{ROOT}/paper/three_forks_tick/tableA_three_forks.csv")
    def parse(cellv):
        b = float(cellv.split(" ")[0].replace("*", "").replace("−", "-")); se = float(cellv.split("(")[1].rstrip(")")); return b, se
    SPEC = {"σ": "log σ + hour FE", "σ+L+vol": "+ log L + log volume", "σ+L+vol+trend": "+ linear trend", "RD": "RD jump (separate slopes)"}
    rows = []
    for _, lr in lor.iterrows():
        w = lr["Window"]; spec_en = lr["Specification"]; cname = [k for k, v in SPEC.items() if v == spec_en][0]
        bL, sL = parse(lr["Lorentz β (pred. -0.347)"])
        r = {"Window": w, "Specification": spec_en, "Lorentz (lag 0)": f"{bL:+.3f} ({sL:.3f})"}
        es, ws = [bL / np.log(0.5)], [1 / (sL / abs(np.log(0.5))) ** 2]
        for fork in ("Maxwell", "Fermi"):
            e = est[(fork, w, cname)]; lndt = np.log(FORKS3[fork][1] / FORKS3[fork][0])
            for lag in ("lag0", "lag250"):
                b, se = e[lag]; r[f"{fork} {lag}"] = f"{b:+.3f} ({se:.3f}) [{b / (0.5 * lndt):.0%}]"
            b, se = e["lag250"]; es.append(b / lndt); ws.append(1 / (se / abs(lndt)) ** 2)
        es, ws = np.array(es), np.array(ws); ebar = (ws * es).sum() / ws.sum(); se_bar = np.sqrt(1 / ws.sum())
        Q = (ws * (es - ebar) ** 2).sum(); p_eq = 1 - stats.chi2.cdf(Q, df=2)
        r["elasticities L / M / F (lag 250)"] = " / ".join(f"{e:.2f}" for e in es)
        r["pooled elasticity (lag 250)"] = f"{ebar:.3f} ({se_bar:.3f})"; r["t vs 0.5"] = f"{(ebar - 0.5) / se_bar:+.1f}"; r["equal (p)"] = f"{p_eq:.2f}"
        r["pooled elasticity (lag 0)"] = lr["pooled elasticity"].replace("*", ""); r["equal (p), lag 0"] = f"{lr['equality across forks (p)']:.2f}"
        rows.append(r)
        key[f"three|{w}|{cname}"] = {"pooled_lag250": float(ebar), "se": float(se_bar), "p_eq": float(p_eq), "es": [float(x) for x in es]}
    open(os.path.join(OUT, "tableL4_three_forks.md"), "w").write(pd.DataFrame(rows).to_markdown(index=False))

    # ---------------- latency floor refit (sets A/B as in latency_floor.py) with lag 250 for Maxwell/Fermi
    def pred(l, f): d0, d1 = FORKS3[f]; return 0.5 * np.log((d1 + l) / (d0 + l))
    L = json.load(open(f"{ROOT}/tick_cmp/Lorentz/key_numbers.json"))
    sets = {"A (levels-type)": {"Lorentz": (L["tick|±30 d|σ+L+vol+趋势|overshoot_strict_bps"]["b"], L["tick|±30 d|σ+L+vol+趋势|overshoot_strict_bps"]["se"]),
                                "Maxwell": est[("Maxwell", "±14 d", "σ+L+vol")]["lag250"], "Fermi": est[("Fermi", "±14 d", "σ+L+vol")]["lag250"]},
            "B (RD-type)": {"Lorentz": (L["tick|±30 d|RD|overshoot_strict_bps"]["b"], L["tick|±30 d|RD|overshoot_strict_bps"]["se"]),
                            "Maxwell": est[("Maxwell", "±14 d", "RD")]["lag250"], "Fermi": est[("Fermi", "±30 d", "RD")]["lag250"]}}
    rows = []
    for name, e in sets.items():
        chi2 = lambda l: sum(((e[f][0] - pred(l, f)) / e[f][1]) ** 2 for f in FORKS3)
        r = optimize.minimize_scalar(chi2, bounds=(0, 10), method="bounded"); l, c = r.x, r.fun
        grid = np.linspace(0, 10, 10001); vals = np.array([chi2(g) for g in grid]); ci = grid[vals <= c + 3.84]; c0 = chi2(0.0)
        rows.append({"estimate set": name + " — Maxwell/Fermi at lag 250", "ℓ (s)": f"{l:.2f}", "95% CI": f"{ci.min():.2f}–{ci.max():.2f}", "χ²(2), p": f"{c:.2f}, {1 - stats.chi2.cdf(c, 2):.2f}",
                     "χ² at ℓ=0 (3 df), p": f"{c0:.1f}, {1 - stats.chi2.cdf(c0, 3):.3f}",
                     **{f"{f}: est / model": f"{e[f][0]:+.3f} ({e[f][1]:.3f}) / {pred(l, f):+.3f}" for f in FORKS3},
                     "next halving 0.45→0.225": f"{0.5 * np.log((0.225 + l) / (0.45 + l)):+.3f}", "floor rel. 0.45 s": f"{np.sqrt(l / (0.45 + l)):.2f}"})
        key[f"latency|{name}"] = {"ell": float(l), "ci": [float(ci.min()), float(ci.max())], "chi2": float(c), "p": float(1 - stats.chi2.cdf(c, 2)), "chi2_0": float(c0),
                                  "next": float(0.5 * np.log((0.225 + l) / (0.45 + l))), "floor": float(np.sqrt(l / (0.45 + l)))}
    open(os.path.join(OUT, "tableL5_latency.md"), "w").write(pd.DataFrame(rows).to_markdown(index=False))
    json.dump(key, open(os.path.join(OUT, "key_numbers.json"), "w"), indent=1, ensure_ascii=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 300)
    print(show[show.outcome.isin(["overshoot (strict)", "arb profit", "LP loss (total)", "arbs/h"])].to_string()); print()
    print(pd.DataFrame(L2).to_string()); print(); print(pd.DataFrame(L6).to_string()); print(); print(open(os.path.join(OUT, "tableL4_three_forks.md")).read()); print(); print(open(os.path.join(OUT, "tableL5_latency.md")).read())


if __name__ == "__main__":
    main()
