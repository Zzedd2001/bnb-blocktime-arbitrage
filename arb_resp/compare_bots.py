"""Compare the address-level response-time results (arb_response.py, three forks) with the paper's latency-floor
fit and tick-reference estimates.  Outputs $REPL_ROOT/arb_resp/cmp/ (tables R1–R7 .md, key_numbers.json, figures).

R1  six-regime latency: quantile intercepts (bootstrap SE), Turnbull median, P(k=1), on-chain CDF points
R2  fork effects implied by τ vs tick estimates (per pool ±14 d σ+L+vol, and the core-pooled placebo-clean set) and √Δt law
R3  σ-normalised decomposition of the strict-arb overshoot by trigger type (jump / move / continuation / same-block)
R4  12-point test: τ-implied and composite predictions against the per-pool tick estimates
R5  concentration and adaptation of arbitrageur addresses
R6  the dominant sender contracts across pools and forks
R7  sensitivity: wider band, sharp openings
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os, json, re
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = ROOT + "/arb_resp/bots"; OUT = ROOT + "/arb_resp/cmp_bots"; os.makedirs(OUT, exist_ok=True)
FORKS = ["Lorentz", "Maxwell", "Fermi"]
DT = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
CORE = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-100"]
LABEL = {"WBNB-USDT-500": "WBNB/USDT 5 bp", "ETH-USDT-500": "ETH/USDT 5 bp", "BTCB-USDT-500": "BTCB/USDT 5 bp", "WBNB-USDT-100": "WBNB/USDT 1 bp"}
PANEL = {f: ROOT + f"/{f.lower()}_tick/bundle/analysis_agg/hourly_panel.parquet" for f in FORKS}
COL = {"Lorentz": "#2a9d8f", "Maxwell": "#2a78d6", "Fermi": "#eb6834"}
rng = np.random.default_rng(0)
KEY = {}


def load(fork):
    S = json.load(open(os.path.join(ROOT, fork, "arb_response_bots", "summary.json")))["pools"]
    samples = {}
    for p in S:
        f = os.path.join(ROOT, fork, "arb_response_bots", p, "arbs_sample.parquet")
        if os.path.exists(f):
            samples[p] = pd.read_parquet(f)
    return S, samples


DATA = {f: load(f) for f in FORKS}

# paper per-pool tick estimates (±14 d, σ+L+vol), from tables_v3/table5a
t5 = open(ROOT + "/paper/tables_v3/table5a_per_pool_overshoot_profit.md").read().splitlines()
PLAB = {"WBNB/USDT 0.01%": "WBNB-USDT-100", "WBNB/USDT 0.05%": "WBNB-USDT-500", "ETH/USDT 0.05%": "ETH-USDT-500", "BTCB/USDT 0.05%": "BTCB-USDT-500"}
TICK = {}
hdr = [c.strip() for c in t5[0].split("|")[1:-1]]
for line in t5[2:]:
    cells = [c.strip() for c in line.split("|")[1:-1]]
    if cells[0] in PLAB:
        for f in FORKS:
            v = cells[hdr.index(f"{f}: overshoot")].replace("−", "-")
            m = re.match(r"([-+]?[\d.]+)\**\s*\(([\d.]+)\)", v)
            if m:
                TICK[(f, PLAB[cells[0]])] = (float(m.group(1)), float(m.group(2)))
# core-pooled placebo-clean tick estimates (paper Table 4 / key_numbers of tick_cmp)
POOLED = {}
for f in FORKS:
    k = json.load(open(ROOT + f"/tick_cmp/{f}/key_numbers.json"))
    pref = {"Lorentz": [("±30 d", "σ+L+vol+趋势"), ("±30 d", "RD")], "Maxwell": [("±14 d", "σ"), ("±14 d", "σ+L+vol"), ("±14 d", "σ+L+vol+趋势"), ("±14 d", "RD")],
            "Fermi": [("±14 d", "σ+L+vol"), ("±30 d", "σ+L+vol+趋势"), ("±30 d", "RD")]}[f]
    ests = [(k[f"tick|{w}|{c}|overshoot_strict_bps"]["b"], k[f"tick|{w}|{c}|overshoot_strict_bps"]["se"]) for w, c in pref]
    POOLED[f] = (min(b for b, s in ests), max(b for b, s in ests), ests)
LF = json.load(open(ROOT + "/paper/three_forks_tick/latency_floor.json"))
ELL_B = [r for n, r in LF.items() if n.startswith("B")][0]


def q_int(tau, q, dt_ms):
    return np.quantile(tau, q) - q * dt_ms


def boot_int(tau, q, dt_ms, B=300):
    v = np.array([q_int(rng.choice(tau, len(tau), replace=True), q, dt_ms) for _ in range(B)])
    return v.std()


# ------------------------------------------------------------------ R1 six-regime latency
rows = []; R1 = {}
for f in FORKS:
    S, SM = DATA[f]
    for p in CORE:
        for reg in ("pre", "post"):
            R = S[p]["windows"]["30d"][reg]
            d = SM[p]; d = d[(d["regime"] == reg) & (d["trigger"] == "cex") & (d["tau_ms"] <= 60_000) & (d["tau_ms"] >= 0)]
            tau = d["tau_ms"].to_numpy(np.float64); dt = R["dt_ms"]
            q10, q50 = q_int(tau, .1, dt), q_int(tau, .5, dt)
            s10, s50 = boot_int(tau, .1, dt), boot_int(tau, .5, dt)
            oc = R.get("onchain", {}).get("cdf_ell_at_j_dt", {})
            R1[(f, p, reg)] = {"dt": dt / 1000, "n": R["n_cex"], "q10": R["ell_quantile_ms"]["q10"], "q25": R["ell_quantile_ms"]["q25"], "q50": R["ell_quantile_ms"]["q50"],
                               "se10": s10, "se50": s50, "tb_med": R["turnbull_ms"]["median"], "tb_p25": R["turnbull_ms"]["p25"], "tb_p75": R["turnbull_ms"]["p75"],
                               "pk1": R["k_blocks"]["p_k1"], "mean_k": R["k_blocks"]["mean"], "share_lt_dt": R["tau_ms"]["share_lt_dt"],
                               "oc1": oc.get("1"), "oc2": oc.get("2"), "n_on": R.get("n_onchain", 0), "esqrt": R["tau_ms"]["mean_sqrt_s"],
                               "p50_tau": R["tau_ms"]["p50"], "p10_tau": R["tau_ms"]["p10"], "share_lt_100": R["tau_ms"]["share_lt_100ms"]}
            r = R1[(f, p, reg)]
            rows.append({"fork": f, "pool": LABEL[p], "regime": reg, "Δt (s)": f"{r['dt']:.2f}", "n (CEX-triggered)": f"{r['n']:,}",
                         "ℓ̂ q10 (ms)": f"{r['q10']:.0f} ({s10:.0f})", "ℓ̂ q25": f"{r['q25']:.0f}", "ℓ̂ q50": f"{r['q50']:.0f} ({s50:.0f})",
                         "Turnbull p25 / median / p75": f"{r['tb_p25']:.0f} / {r['tb_med']:.0f} / {r['tb_p75']:.0f}",
                         "P(k=1)": f"{r['pk1']:.2f}", "mean k": f"{r['mean_k']:.2f}", "on-chain P(ℓ≤Δt) / P(ℓ≤2Δt)": (f"{r['oc1']:.2f} / {r['oc2']:.2f}" if r['oc1'] is not None else ""),
                         "n on-chain": f"{r['n_on']:,}", "share τ<100 ms": f"{r['share_lt_100']:.3f}"})
T1 = pd.DataFrame(rows)
open(os.path.join(OUT, "R1_six_regime_latency.md"), "w").write(T1.to_markdown(index=False))

# pooled-across-core-pools summary per regime (arb-weighted mean of the intercepts)
summ = []
for f in FORKS:
    for reg in ("pre", "post"):
        w = np.array([R1[(f, p, reg)]["n"] for p in CORE[:3]]); q10 = np.array([R1[(f, p, reg)]["q10"] for p in CORE[:3]]); q50 = np.array([R1[(f, p, reg)]["q50"] for p in CORE[:3]])
        tb = np.array([R1[(f, p, reg)]["tb_med"] for p in CORE[:3]]); pk = np.array([R1[(f, p, reg)]["pk1"] for p in CORE[:3]])
        summ.append({"fork": f, "regime": reg, "Δt (s)": R1[(f, CORE[0], reg)]["dt"], "ℓ̂ q10 (ms, 3 pools, range)": f"{q10.min():.0f}–{q10.max():.0f}",
                     "ℓ̂ q50 (range)": f"{q50.min():.0f}–{q50.max():.0f}", "Turnbull median (range)": f"{tb.min():.0f}–{tb.max():.0f}", "P(k=1) (range)": f"{pk.min():.2f}–{pk.max():.2f}",
                     "weighted ℓ̂ q50": f"{np.average(q50, weights=w):.0f}"})
        KEY[f"regime|{f}|{reg}"] = {"q10_range": [float(q10.min()), float(q10.max())], "q50_range": [float(q50.min()), float(q50.max())], "tb_range": [float(tb.min()), float(tb.max())],
                                     "pk1_range": [float(pk.min()), float(pk.max())], "w_q50": float(np.average(q50, weights=w))}
open(os.path.join(OUT, "R1b_regime_summary.md"), "w").write(pd.DataFrame(summ).to_markdown(index=False))

# ------------------------------------------------------------------ R2 implied effects vs tick estimates
rows = []; R2 = {}
for f in FORKS:
    S, SM = DATA[f]
    for p in CORE:
        e = S[p]["windows"]["30d"]["effects"]
        tk = TICK.get((f, p), (np.nan, np.nan))
        R2[(f, p)] = {"law": e["sqrt_law"], "impl": e["implied_from_tau"], "cf": e["counterfactual_fixed_latency"], "lat": e["latency_change_component"],
                      "ellp": e["ell_paper_equiv_s"], "tick": tk[0], "tick_se": tk[1], "on": e.get("implied_from_tau_onchain", np.nan),
                      "dmed": e["d_median_tau_ms"], "mmed": e["mechanical_d_median_ms"], "dp10": e["d_p10_tau_ms"], "mp10": e["mechanical_d_p10_ms"],
                      "pk1_act": e["p_k1_post_actual"], "pk1_cf": e["p_k1_post_counterfactual"]}
        r = R2[(f, p)]
        rows.append({"fork": f, "pool": LABEL[p], "√Δt law": f"{r['law']:+.3f}", "implied by τ: log(E√τ₁/E√τ₀)": f"{r['impl']:+.3f}",
                     "fixed-latency counterfactual": f"{r['cf']:+.3f}", "latency-change component": f"{r['lat']:+.3f}", "ℓ (paper convention, s)": f"{r['ellp']:.2f}",
                     "on-chain triggers": f"{r['on']:+.3f}" if np.isfinite(r["on"]) else "", "tick estimate (±14 d, σ+L+vol)": f"{r['tick']:+.3f} ({r['tick_se']:.3f})",
                     "implied − tick": f"{r['impl'] - r['tick']:+.3f}", "Δ median τ / mechanical (ms)": f"{r['dmed']:+.0f} / {r['mmed']:+.0f}",
                     "Δ p10 τ / mechanical": f"{r['dp10']:+.0f} / {r['mp10']:+.0f}", "P(k=1) post: actual / fixed-latency": f"{r['pk1_act']:.2f} / {r['pk1_cf']:.2f}"})
    lo, hi, ests = POOLED[f]
    rows.append({"fork": f, "pool": "core pooled (paper, placebo-clean)", "√Δt law": f"{0.5 * np.log(DT[f][1] / DT[f][0]):+.3f}", "tick estimate (±14 d, σ+L+vol)": f"{lo:+.3f} to {hi:+.3f}"})
T2 = pd.DataFrame(rows)
open(os.path.join(OUT, "R2_implied_vs_tick.md"), "w").write(T2.to_markdown(index=False))

# ------------------------------------------------------------------ R3 σ-normalised decomposition (strict arbs)
def sigma_join(f, p, d):
    h = pd.read_parquet(PANEL[f], columns=["hour", "pool", "sigma_ps"])
    h = h[h["pool"] == p].copy()
    h["hour_ms"] = (h["hour"].astype("int64") // 10 ** 6).astype("int64")
    d = d.copy(); d["hour_ms"] = (d["ts_ms"] // 3_600_000) * 3_600_000
    d = d.merge(h[["hour_ms", "sigma_ps"]], on="hour_ms", how="left")
    return d


rows = []; R3 = {}
for f in FORKS:
    S, SM = DATA[f]
    for p in CORE:
        d = sigma_join(f, p, SM[p])
        d = d[d["is_arb_strict"] & d["sigma_ps"].notna() & (d["sigma_ps"] > 0)].copy()
        d["ov_n"] = d["overshoot_bps"] / (d["sigma_ps"] * 1e4)               # overshoot / σ_ps  (units √s)
        d["jump_n"] = d["jump_bps"] / (d["sigma_ps"] * 1e4); d["move_n"] = d["move_bps"] / (d["sigma_ps"] * 1e4)
        comp = {}
        for reg in ("pre", "post"):
            x = d[d["regime"] == reg]
            n = len(x); sh = x["trigger"].value_counts(normalize=True)
            m = x.groupby("trigger", observed=True)["ov_n"].mean()
            cex = x[x["trigger"] == "cex"]
            comp[reg] = {"n": n, "share": {t: float(sh.get(t, 0)) for t in ("cex", "continuation", "same_block", "onchain", "long")},
                         "mean": {t: float(m.get(t, np.nan)) for t in ("cex", "continuation", "same_block", "onchain", "long")},
                         "jump": float(cex["jump_n"].mean()), "move": float(cex["move_n"].mean()), "total": float(x["ov_n"].mean()),
                         "esqrt": R1[(f, p, reg)]["esqrt"]}
        pre, post = comp["pre"], comp["post"]
        actual = np.log(post["total"] / pre["total"])
        x_tau = R2[(f, p)]["impl"]; x_law = R2[(f, p)]["law"]
        # counterfactual totals: only the CEX-move part changes (composition and other parts at pre-fork values)
        T_pre = pre["total"]
        cf_tau = T_pre - pre["share"]["cex"] * pre["move"] * (1 - np.exp(x_tau))
        cf_law = T_pre - pre["share"]["cex"] * pre["move"] * (1 - np.exp(x_law))
        # ... and if continuation / same-block arbs shrink with τ as well (their overshoot also accumulates over the block wait)
        cf_tau_all = T_pre - (pre["share"]["cex"] * pre["move"] + pre["share"]["continuation"] * pre["mean"]["continuation"]) * (1 - np.exp(x_tau))
        # contributions (Δ of share×mean per part, relative to the mean total)
        Tbar = 0.5 * (pre["total"] + post["total"])
        contrib = {}
        for t in ("cex_jump", "cex_move", "continuation", "same_block", "onchain"):
            if t.startswith("cex_"):
                a0 = pre["share"]["cex"] * pre[t[4:]]; a1 = post["share"]["cex"] * post[t[4:]]
            else:
                a0 = pre["share"][t] * (pre["mean"][t] if np.isfinite(pre["mean"][t]) else 0); a1 = post["share"][t] * (post["mean"][t] if np.isfinite(post["mean"][t]) else 0)
            contrib[t] = (a1 - a0) / Tbar
        R3[(f, p)] = {"pre": pre, "post": post, "actual": actual, "cf_tau": np.log(cf_tau / T_pre), "cf_law": np.log(cf_law / T_pre), "cf_tau_all": np.log(cf_tau_all / T_pre), "contrib": contrib,
                      "move_over_esqrt": {reg: comp[reg]["move"] / comp[reg]["esqrt"] for reg in ("pre", "post")}}
        for reg in ("pre", "post"):
            c = comp[reg]
            rows.append({"fork": f, "pool": LABEL[p], "regime": reg, "n strict (sample)": f"{c['n']:,}",
                         "share: cex / cont. / same-block / on-chain": f"{c['share']['cex']:.2f} / {c['share']['continuation']:.2f} / {c['share']['same_block']:.2f} / {c['share']['onchain']:.2f}",
                         "overshoot/σ (√s): total": f"{c['total']:.3f}", "cex: jump + move": f"{c['jump']:.3f} + {c['move']:.3f}", "jump share of cex": f"{c['jump'] / (c['jump'] + c['move']):.2f}",
                         "continuation": f"{c['mean']['continuation']:.3f}", "same-block": f"{c['mean']['same_block']:.3f}", "E[√τ] (√s)": f"{c['esqrt']:.3f}", "move / E√τ": f"{c['move'] / c['esqrt']:.2f}"})
        rows.append({"fork": f, "pool": LABEL[p], "regime": "Δlog", "n strict (sample)": "", "share: cex / cont. / same-block / on-chain": "",
                     "overshoot/σ (√s): total": f"{actual:+.3f} (tick est. {R2[(f, p)]['tick']:+.3f})",
                     "cex: jump + move": f"{np.log(post['jump'] / pre['jump']):+.3f} / {np.log(post['move'] / pre['move']):+.3f}",
                     "jump share of cex": f"pred. move-only: τ {R3[(f, p)]['cf_tau']:+.3f}, √law {R3[(f, p)]['cf_law']:+.3f}; τ on cex+cont.: {R3[(f, p)]['cf_tau_all']:+.3f}",
                     "continuation": f"{np.log(post['mean']['continuation'] / pre['mean']['continuation']):+.3f}", "same-block": f"{np.log(post['mean']['same_block'] / pre['mean']['same_block']):+.3f}",
                     "E[√τ] (√s)": f"{x_tau:+.3f}", "move / E√τ": ""})
T3 = pd.DataFrame(rows)
open(os.path.join(OUT, "R3_decomposition.md"), "w").write(T3.to_markdown(index=False))
rows = []
for (f, p), r in R3.items():
    c = r["contrib"]
    rows.append({"fork": f, "pool": LABEL[p], "actual Δlog(overshoot/σ)": f"{r['actual']:+.3f}", "tick estimate": f"{R2[(f, p)]['tick']:+.3f}",
                 **{f"contribution: {t}": f"{v:+.3f}" for t, v in c.items()}, "sum": f"{sum(c.values()):+.3f}"})
open(os.path.join(OUT, "R3b_contributions.md"), "w").write(pd.DataFrame(rows).to_markdown(index=False))

# ------------------------------------------------------------------ R4 12-point test
pts = []
for f in FORKS:
    for p in CORE:
        pts.append({"fork": f, "pool": p, "tick": R2[(f, p)]["tick"], "se": R2[(f, p)]["tick_se"], "impl": R2[(f, p)]["impl"], "law": R2[(f, p)]["law"],
                    "comp": R3[(f, p)]["cf_tau"], "comp_all": R3[(f, p)]["cf_tau_all"], "actual_norm": R3[(f, p)]["actual"]})
P = pd.DataFrame(pts)
import statsmodels.api as sm
def fit(x, y, w=None):
    X = sm.add_constant(x); m = sm.WLS(y, X, weights=w if w is not None else 1.0).fit()
    return float(m.params[0]), float(m.params[1]), float(m.bse[1]), float(m.rsquared), float(np.corrcoef(x, y)[0, 1])
res4 = {}
for name, col in (("τ-implied", "impl"), ("composite (move-only)", "comp"), ("composite (cex + continuation)", "comp_all"), ("√Δt law", "law")):
    a, b, s, r2, rho = fit(P[col].to_numpy(), P["tick"].to_numpy(), 1 / P["se"].to_numpy() ** 2)
    mae = np.abs(P[col] - P["tick"]).mean()
    res4[name] = {"intercept": a, "slope": b, "slope_se": s, "r2": r2, "corr": rho, "mae": mae, "mean_pred": P[col].mean(), "mean_tick": P["tick"].mean()}
T4 = pd.DataFrame([{"prediction": k, "mean prediction": f"{v['mean_pred']:+.3f}", "mean tick estimate": f"{v['mean_tick']:+.3f}", "MAE": f"{v['mae']:.3f}", "corr": f"{v['corr']:.2f}",
                    "WLS slope (se)": f"{v['slope']:.2f} ({v['slope_se']:.2f})", "intercept": f"{v['intercept']:+.3f}", "R²": f"{v['r2']:.2f}"} for k, v in res4.items()])
open(os.path.join(OUT, "R4_twelve_point_test.md"), "w").write(T4.to_markdown(index=False))
P.to_csv(os.path.join(OUT, "R4_points.csv"), index=False)
KEY["R4"] = res4

# ------------------------------------------------------------------ R5 concentration and adaptation
rows = []
for f in FORKS:
    S, SM = DATA[f]
    for p in CORE:
        W = S[p]["windows"]["30d"]; A0, A1 = W["pre"]["addresses"], W["post"]["addresses"]; e = W["effects"]
        pr = pd.read_csv(os.path.join(ROOT, f, "arb_response_bots", p, "paired_senders.csv"))
        pr = pr[(pr["n_pre"] >= 200) & (pr["n_post"] >= 200)]
        rows.append({"fork": f, "pool": LABEL[p], "senders pre → post": f"{A0['n_senders']} → {A1['n_senders']}", "active (≥20 arbs)": f"{A0['n_active_ge_min']} → {A1['n_active_ge_min']}",
                     "HHI": f"{A0['hhi_count']:.2f} → {A1['hhi_count']:.2f}", "top-3 share": f"{A0['top3_share']:.2f} → {A1['top3_share']:.2f}",
                     "senders for 90%": f"{A0['n_senders_90pct']} → {A1['n_senders_90pct']}", "stayers / entrants / exits": f"{e['entrants']['n_stayers']} / {e['entrants']['n_entrants']} / {e['entrants']['n_exits']}",
                     "entrants' share of post arbs": f"{e['entrants']['entrants_share_of_post_arbs']:.2f}",
                     "paired senders (≥200 arbs each side)": len(pr), "median Δ ℓ̂q10 (ms)": f"{(pr['ell_q10_post_ms'] - pr['ell_q10_pre_ms']).median():+.0f}" if len(pr) else "",
                     "median Δ ℓ̂q50 (ms)": f"{(pr['ell_q50_post_ms'] - pr['ell_q50_pre_ms']).median():+.0f}" if len(pr) else "",
                     "share with lower ℓ̂q10 post": f"{((pr['ell_q10_post_ms'] < pr['ell_q10_pre_ms'] - 20).mean()):.2f}" if len(pr) else "",
                     "P(k=1) of paired: pre → post": f"{pr['p_k1_pre'].mean():.2f} → {pr['p_k1_post'].mean():.2f}" if len(pr) else ""})
T5 = pd.DataFrame(rows)
open(os.path.join(OUT, "R5_addresses.md"), "w").write(T5.to_markdown(index=False))

# ------------------------------------------------------------------ R6 dominant senders across pools and forks
top = []
for f in FORKS:
    for p in CORE:
        for reg in ("pre", "post"):
            t = pd.read_csv(os.path.join(ROOT, f, "arb_response_bots", p, f"top_senders_{reg}.csv")).head(5)
            for _, x in t.iterrows():
                top.append({"fork": f, "pool": p, "regime": reg, "sender": x["sender"], "share": x["share"], "n": x["n_arb_strict"], "arb_share_own": x["arb_share_of_own_swaps"],
                            "tau_p10": x["tau_p10_ms"], "tau_p50": x["tau_p50_ms"], "p_k1": x["p_k1"], "same_block": x["share_same_block"], "dt": R1[(f, p, reg)]["dt"] * 1000})
TP = pd.DataFrame(top)
TP["ell_q10"] = TP["tau_p10"] - 0.1 * TP["dt"]; TP["ell_q50"] = TP["tau_p50"] - 0.5 * TP["dt"]
agg = TP.groupby("sender").agg(appearances=("share", "size"), pools=("pool", lambda s: len(set(s))), forks=("fork", lambda s: len(set(s))), mean_share=("share", "mean"),
                              max_share=("share", "max"), arbs=("n", "sum"), arb_share_own=("arb_share_own", "mean"), same_block=("same_block", "mean"),
                              ell_q10_med=("ell_q10", "median"), ell_q50_med=("ell_q50", "median")).sort_values("arbs", ascending=False)
agg.to_csv(os.path.join(OUT, "R6_senders.csv"))
open(os.path.join(OUT, "R6_senders.md"), "w").write(agg.head(15).reset_index().to_markdown(index=False, floatfmt=".2f"))
# per-sender trajectory of ℓ̂q10 across the six regimes (senders present in ≥4 regimes in a given pool)
traj = []
ORDER = [("Lorentz", "pre"), ("Lorentz", "post"), ("Maxwell", "pre"), ("Maxwell", "post"), ("Fermi", "pre"), ("Fermi", "post")]
for p in CORE[:3]:
    sub = TP[TP["pool"] == p]
    for s, g in sub.groupby("sender"):
        if len(g) >= 4:
            row = {"pool": LABEL[p], "sender": s[:10] + "…" + s[-4:]}
            for f, reg in ORDER:
                x = g[(g["fork"] == f) & (g["regime"] == reg)]
                row[f"{f} {reg}"] = f"{x['ell_q10'].iloc[0]:.0f} / {x['ell_q50'].iloc[0]:.0f}" if len(x) and np.isfinite(x['ell_q10'].iloc[0]) else ""
            traj.append(row)
open(os.path.join(OUT, "R6b_sender_trajectories.md"), "w").write(pd.DataFrame(traj).to_markdown(index=False))

# ------------------------------------------------------------------ R7 sensitivity
rows = []
for f in FORKS:
    S, SM = DATA[f]
    for p in CORE:
        for reg in ("pre", "post"):
            R = S[p]["windows"]["30d"][reg]; dt = R["dt_ms"]
            b15, b2, sh = R.get("tau_ms_band1.5", {}), R.get("tau_ms_band2.0", {}), R.get("tau_ms_sharp", {})
            rows.append({"fork": f, "pool": LABEL[p], "regime": reg, "γ band: ℓ̂ q10 / q50": f"{R['ell_quantile_ms']['q10']:.0f} / {R['ell_quantile_ms']['q50']:.0f}",
                         "1.5γ: ℓ̂ q10 / q50 (n)": f"{b15.get('ell_q10_ms', np.nan):.0f} / {b15.get('ell_q50_ms', np.nan):.0f} ({b15.get('n', 0):,})",
                         "2γ: ℓ̂ q10 / q50 (n)": f"{b2.get('ell_q10_ms', np.nan):.0f} / {b2.get('ell_q50_ms', np.nan):.0f} ({b2.get('n', 0):,})",
                         "sharp openings: ℓ̂ q10 / q50 (n)": f"{sh.get('ell_q10_ms', np.nan):.0f} / {sh.get('ell_q50_ms', np.nan):.0f} ({sh.get('n', 0):,})",
                         "sharp: P(k=1)": f"{sh.get('p_k1', np.nan):.2f}"})
open(os.path.join(OUT, "R7_sensitivity.md"), "w").write(pd.DataFrame(rows).to_markdown(index=False))

# ------------------------------------------------------------------ figures
# F1: intercepts across the six regimes with the paper-implied band
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
xs = np.arange(6); lab = [f"{f[:3]} {r}\n{DT[f][0 if r == 'pre' else 1]:.2f} s" for f, r in ORDER]
mk = {"WBNB-USDT-500": "o", "ETH-USDT-500": "s", "BTCB-USDT-500": "^", "WBNB-USDT-100": "x"}
for i, key in enumerate(("q10", "q50")):
    for p in CORE:
        y = [R1[(f, p, r)][key] for f, r in ORDER]; se = [R1[(f, p, r)]["se10" if key == "q10" else "se50"] for f, r in ORDER]
        ax[i].errorbar(xs + (CORE.index(p) - 1.5) * 0.12, y, yerr=1.96 * np.array(se), fmt=mk[p], ms=5, lw=1, capsize=2, label=LABEL[p], color=["#0b0b0b", "#2a78d6", "#eb6834", "#7a7a7a"][CORE.index(p)])
    lo, hi = 110, 520
    ax[i].axhspan(lo, hi, color="#2a9d8f", alpha=0.12, lw=0, label="paper ℓ = 0.59 s (CI 0.27–1.13) ⇔ ℓ_t ≈ 0.25 s (0.11–0.52)")
    ax[i].axhline(250, color="#2a9d8f", lw=0.8, ls="--")
    ax[i].set_xticks(xs); ax[i].set_xticklabels(lab, fontsize=8); ax[i].set_ylabel(f"ℓ̂ = Q_{{{key[1:]}}}(τ) − {int(key[1:]) / 100:.2f}·Δt  (ms)", fontsize=9)
    ax[i].set_title(f"latency intercept from the {key[1:]}th percentile of the response time", fontsize=9, loc="left")
    ax[i].grid(color="#e6e6e3", lw=0.6); ax[i].set_ylim(-50, 1500 if key == "q50" else 1100)
    for s_ in ("top", "right"):
        ax[i].spines[s_].set_visible(False)
ax[0].legend(fontsize=7, frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F1_intercepts_six_regimes.png"), dpi=170); plt.close(fig)

# F2: P(k=1) against Δt, with the fixed-latency model curves for ℓ_t = 0.1, 0.25, 0.5 s
fig, ax = plt.subplots(figsize=(6.2, 4.2))
dts = np.linspace(0.3, 3.2, 200)
for lt, ls in ((0.1, ":"), (0.25, "-"), (0.5, "--")):
    ax.plot(dts, np.maximum(0, 1 - lt / dts), color="#2a9d8f", ls=ls, lw=1, label=f"point latency ℓ_t = {lt} s: 1 − ℓ_t/Δt")
for p in CORE:
    x = [R1[(f, p, r)]["dt"] for f, r in ORDER]; y = [R1[(f, p, r)]["pk1"] for f, r in ORDER]
    ax.plot(x, y, mk[p], ms=6, color=["#0b0b0b", "#2a78d6", "#eb6834", "#7a7a7a"][CORE.index(p)], label=LABEL[p] + " (CEX-triggered)")
    yo = [R1[(f, p, r)]["oc1"] for f, r in ORDER]
    ax.plot(x, yo, mk[p], ms=6, mfc="none", color=["#0b0b0b", "#2a78d6", "#eb6834", "#7a7a7a"][CORE.index(p)], alpha=0.6)
ax.plot([], [], "o", mfc="none", color="#555", label="open markers: on-chain triggers, P(ℓ ≤ Δt)")
ax.set_xscale("log"); ax.set_xticks([0.45, 0.75, 1.5, 3.0]); ax.set_xticklabels(["0.45", "0.75", "1.5", "3.0"]); ax.set_xlabel("block interval Δt (s)"); ax.set_ylabel("share of arbs landing in the first block after the opening")
ax.set_ylim(0.3, 1.02); ax.grid(color="#e6e6e3", lw=0.6); ax.legend(fontsize=6.5, frameon=False, ncol=1)
for s_ in ("top", "right"):
    ax.spines[s_].set_visible(False)
ax.set_title("Arbs that miss the first block: rising as blocks get faster, as a fixed latency implies", fontsize=9, loc="left")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F2_first_block_share.png"), dpi=170); plt.close(fig)

# F3: 12-point test
fig, ax = plt.subplots(1, 2, figsize=(10, 4.2))
for i, (col, ttl) in enumerate((("impl", "τ-implied effect log(E√τ₁/E√τ₀)"), ("comp", "composite prediction (only the CEX-move part shrinks with τ)"))):
    for f in FORKS:
        s = P[P["fork"] == f]
        ax[i].errorbar(s[col], s["tick"], yerr=1.96 * s["se"], fmt="o", color=COL[f], ms=5, capsize=2, lw=1, label=f)
        for _, r in s.iterrows():
            ax[i].annotate(LABEL[r["pool"]].split("/")[0] + ("1" if r["pool"].endswith("100") else ""), (r[col], r["tick"]), fontsize=6, xytext=(3, 3), textcoords="offset points", color="#52514e")
    lim = [-0.45, 0.05]; ax[i].plot(lim, lim, color="#999", lw=0.8, ls="--"); ax[i].set_xlim(lim); ax[i].set_ylim(lim)
    v = res4["τ-implied" if col == "impl" else "composite (move-only)"]
    ax[i].set_xlabel(ttl, fontsize=8.5); ax[i].set_ylabel("tick-reference estimate (±14 d, σ+L+vol), log points", fontsize=8.5)
    ax[i].set_title(f"corr {v['corr']:.2f}, WLS slope {v['slope']:.2f} ({v['slope_se']:.2f}), MAE {v['mae']:.3f}", fontsize=9, loc="left")
    ax[i].grid(color="#e6e6e3", lw=0.6); ax[i].legend(fontsize=7, frameon=False)
    for s_ in ("top", "right"):
        ax[i].spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F3_twelve_point_test.png"), dpi=170); plt.close(fig)

# F4: decomposition bars (σ-normalised strict overshoot, share×mean by part), pre and post, 3 forks × 4 pools
fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
parts = [("cex_jump", "#0b0b0b", "CEX-triggered: jump at crossing"), ("cex_move", "#2a78d6", "CEX-triggered: move during τ"), ("continuation", "#eb6834", "continuation (partial arb)"),
         ("same_block", "#b0b0b0", "same block (back-run)"), ("onchain", "#2a9d8f", "on-chain trigger")]
for ax, f in zip(axes, FORKS):
    xt = []; xl = []
    for j, p in enumerate(CORE):
        r = R3[(f, p)]
        for k, reg in enumerate(("pre", "post")):
            c = r[reg]; base = 0; x = j * 3 + k
            for t, col, lab_ in parts:
                v = c["share"]["cex"] * c[t[4:]] if t.startswith("cex_") else c["share"][t] * (c["mean"][t] if np.isfinite(c["mean"][t]) else 0)
                ax.bar(x, v, bottom=base, color=col, width=0.8, label=lab_ if (j == 0 and k == 0) else None); base += v
            xt.append(x); xl.append(f"{LABEL[p].split('/')[0]}{'1' if p.endswith('100') else ''}\n{reg}")
    ax.set_xticks(xt); ax.set_xticklabels(xl, fontsize=6.5); ax.set_title(f"{f}: {DT[f][0]} → {DT[f][1]} s", fontsize=9, loc="left"); ax.grid(color="#e6e6e3", lw=0.6, axis="y")
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
axes[0].set_ylabel("mean overshoot / σ_ps over strict arbs (√s), by opening type", fontsize=8.5); axes[0].legend(fontsize=6.5, frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F4_decomposition.png"), dpi=170); plt.close(fig)

KEY["R2"] = {f"{f}|{p}": R2[(f, p)] for f in FORKS for p in CORE}
KEY["R3"] = {f"{f}|{p}": {"actual": R3[(f, p)]["actual"], "cf_tau": R3[(f, p)]["cf_tau"], "cf_law": R3[(f, p)]["cf_law"], "cf_tau_all": R3[(f, p)]["cf_tau_all"], "contrib": R3[(f, p)]["contrib"],
                          "pre": R3[(f, p)]["pre"], "post": R3[(f, p)]["post"], "move_over_esqrt": R3[(f, p)]["move_over_esqrt"]} for f in FORKS for p in CORE}
KEY["R1"] = {f"{f}|{p}|{r}": R1[(f, p, r)] for f in FORKS for p in CORE for r in ("pre", "post")}
KEY["paper_ell_B"] = ELL_B; KEY["pooled_tick"] = {f: POOLED[f][:2] for f in FORKS}
json.dump(KEY, open(os.path.join(OUT, "key_numbers.json"), "w"), indent=1, default=float)
for name in ("R1b_regime_summary", "R2_implied_vs_tick", "R3b_contributions", "R4_twelve_point_test", "R5_addresses"):
    print(f"\n### {name}\n"); print(open(os.path.join(OUT, name + ".md")).read())

# ------------------------------------------------------------------ R3c component regressions (paper specification on the sample-based hourly panel)
import statsmodels.formula.api as smf
def comp_panel(f, p):
    d = DATA[f][1][p]; d = d[d["is_arb_strict"]].copy()
    d["hour_ms"] = (d["ts_ms"] // 3_600_000) * 3_600_000
    g = d.groupby("hour_ms")
    out = pd.DataFrame({"n": g.size(), "overshoot_all": g["overshoot_bps"].mean(),
                        "share_cex": g["trigger"].apply(lambda s: (s == "cex").mean()), "share_same": g["trigger"].apply(lambda s: (s == "same_block").mean()),
                        "share_cont": g["trigger"].apply(lambda s: (s == "continuation").mean())})
    for t, col, name in (("cex", "overshoot_bps", "cex_overshoot"), ("cex", "jump_bps", "cex_jump"), ("cex", "move_bps", "cex_move"),
                         ("continuation", "overshoot_bps", "continuation"), ("same_block", "overshoot_bps", "same_block")):
        x = d[d["trigger"] == t]
        out[name] = x.groupby("hour_ms")[col].mean()
        out[name + "_n"] = x.groupby("hour_ms").size()
    h = pd.read_parquet(PANEL[f]); h = h[h["pool"] == p].copy()
    h["hour_ms"] = (h["hour"].astype("int64") // 10 ** 6).astype("int64")
    out = out.reset_index().merge(h[["hour_ms", "sigma_ps", "liq_mean", "volume", "hod", "day", "post", "t_days"]], on="hour_ms", how="inner")
    return out


def beta(panel, y, days=14, min_n=5, controls="np.log(sigma_ps) + np.log(liq_mean) + np.log(volume)"):
    d = panel[(panel["t_days"].abs() <= days) & (panel[y] > 0) & panel[y].notna() & (panel["sigma_ps"] > 0) & (panel["volume"] > 0) & (panel["liq_mean"] > 0)]
    if y + "_n" in d:
        d = d[d[y + "_n"] >= min_n]
    if len(d) < 60 or d["post"].nunique() < 2:
        return np.nan, np.nan, len(d)
    m = smf.ols(f"np.log({y}) ~ post + {controls} + C(hod)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"]})
    return float(m.params["post"]), float(m.bse["post"]), len(d)


rows = []; R3c = {}
for f in FORKS:
    for p in CORE:
        pan = comp_panel(f, p)
        r = {"fork": f, "pool": LABEL[p]}
        R3c[(f, p)] = {}
        for y, lab_ in (("overshoot_all", "all strict arbs"), ("cex_overshoot", "CEX-triggered"), ("cex_jump", "CEX: jump at crossing"), ("cex_move", "CEX: move during τ"),
                        ("continuation", "continuation"), ("same_block", "same block")):
            b, s, n = beta(pan, y)
            R3c[(f, p)][y] = (b, s, n)
            r[lab_] = f"{b:+.3f} ({s:.3f})" if np.isfinite(b) else ""
        # shares: linear
        for y, lab_ in (("share_cex", "Δ share CEX"), ("share_same", "Δ share same-block")):
            d = pan[(pan["t_days"].abs() <= 14) & (pan["n"] >= 5)]
            m = smf.ols(f"{y} ~ post + np.log(sigma_ps) + C(hod)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"]})
            r[lab_] = f"{m.params['post']:+.3f} ({m.bse['post']:.3f})"; R3c[(f, p)][y] = (float(m.params["post"]), float(m.bse["post"]), len(d))
        r["paper per-pool (±14 d)"] = f"{R2[(f, p)]['tick']:+.3f} ({R2[(f, p)]['tick_se']:.3f})"; r["τ-implied"] = f"{R2[(f, p)]['impl']:+.3f}"; r["√Δt law"] = f"{R2[(f, p)]['law']:+.3f}"
        rows.append(r)
T3c = pd.DataFrame(rows)
open(os.path.join(OUT, "R3c_component_regressions.md"), "w").write(T3c.to_markdown(index=False))
KEY["R3c"] = {f"{f}|{p}": {k: list(v) for k, v in R3c[(f, p)].items()} for f in FORKS for p in CORE}
json.dump(KEY, open(os.path.join(OUT, "key_numbers.json"), "w"), indent=1, default=float)
print("\n### R3c_component_regressions\n"); print(T3c.to_markdown(index=False))

# F5: component effects vs τ-implied
fig, ax = plt.subplots(figsize=(7.2, 4.4))
xs = np.arange(12); labs = []
for i, (f, p) in enumerate([(f, p) for f in FORKS for p in CORE]):
    r = R3c[(f, p)]
    for y, col, off, mk_ in (("cex_move", "#2a78d6", -0.2, "o"), ("cex_jump", "#0b0b0b", 0.0, "s"), ("same_block", "#b0b0b0", 0.2, "^")):
        b, s, n = r[y]
        if np.isfinite(b):
            ax.errorbar(i + off, b, yerr=1.96 * s, fmt=mk_, color=col, ms=4.5, capsize=2, lw=1, label={"cex_move": "CEX move during τ", "cex_jump": "jump at crossing", "same_block": "same-block (back-run)"}[y] if i == 0 else None)
    ax.plot(i - 0.2, R2[(f, p)]["impl"], "_", color="#eb6834", ms=12, mew=2, label="τ-implied (prediction for the move part)" if i == 0 else None)
    labs.append(f"{f[:3]}\n{LABEL[p].split('/')[0]}{'1' if p.endswith('100') else ''}")
ax.axhline(0, color="#999", lw=0.8); ax.set_xticks(xs); ax.set_xticklabels(labs, fontsize=7)
ax.set_ylabel("fork effect, log points (±14 d, σ+L+vol, hour FE)", fontsize=8.5); ax.legend(fontsize=7, frameon=False); ax.grid(color="#e6e6e3", lw=0.6)
ax.set_title("Fork effect by component: the CEX move during τ falls; the crossing jump and back-run overshoots do not", fontsize=8.5, loc="left")
for s_ in ("top", "right"):
    ax.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F5_component_effects.png"), dpi=170); plt.close(fig)
