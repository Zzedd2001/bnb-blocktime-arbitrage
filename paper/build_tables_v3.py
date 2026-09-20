"""Build the paper's tables (English markdown) and a key-numbers JSON from the three forks' TICK-REFERENCE analysis outputs
(run_pilot --reference aggtrades: summary_agg.json, analysis_agg/, analysis_agg_14d/, extra_agg/), so that every number in the
v3 manuscript is generated from the same source files.  Adds the reference-resolution tables (12–15) and copies the three-fork
tables from paper/three_forks_tick."""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json, os, re
import numpy as np, pandas as pd

FORKS = {
    "Lorentz": {"bundle": ROOT + "/lorentz_tick/bundle", "extra": ROOT + "/lorentz_tick/bundle/extra_agg", "dt": (3.0, 1.5)},
    "Maxwell": {"bundle": ROOT + "/maxwell_tick/bundle", "extra": ROOT + "/maxwell_tick/bundle/extra_agg", "dt": (1.5, 0.75)},
    "Fermi": {"bundle": ROOT + "/fermi_tick/bundle", "extra": ROOT + "/fermi_tick/bundle/extra_agg", "dt": (0.75, 0.45)},
}
SUMMARY, A30, A14, RES = "summary_agg.json", "analysis_agg", "analysis_agg_14d", "results_agg"
TICK_CMP = ROOT + "/tick_cmp"
TF = ROOT + "/paper/three_forks_tick"
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
ORDER = ["WBNB-USDT-100", "WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500", "USDC-USDT-100", "CAKE-WBNB-2500", "WBNB-USDT-10000"]
LABEL = {"WBNB-USDT-100": "WBNB/USDT 0.01%", "WBNB-USDT-500": "WBNB/USDT 0.05%", "ETH-USDT-500": "ETH/USDT 0.05%",
         "BTCB-USDT-500": "BTCB/USDT 0.05%", "USDC-USDT-100": "USDC/USDT 0.01%", "CAKE-WBNB-2500": "CAKE/WBNB 0.25%",
         "WBNB-USDT-10000": "WBNB/USDT 1%"}
OUT = ROOT + "/paper/tables_v3"
os.makedirs(OUT, exist_ok=True)
KEY = {}


def theory(dt):
    return 0.5 * np.log(dt[1] / dt[0])


def md_cells(path, section_idx, rowlabel):
    """Cells of one row of one '###' section of a full_analysis table (Chinese labels)."""
    secs = open(path).read().split("### ")[1:]
    for line in secs[section_idx].splitlines():
        if line.startswith("| " + rowlabel):
            return [c.strip() for c in line.split("|")[1:-1]]
    raise KeyError(rowlabel)


def strip_sigma(cell):
    return re.sub(r"\s*\[σ[^\]]*\]", "", cell).replace("-", "−").replace("−0", "−0")


def parse_cell(cell):
    m = re.match(r"([+-]?\d+\.\d+)(\**)\s*\((\d+\.\d+)\)", cell.strip())
    return float(m.group(1)), m.group(2), float(m.group(3))


# ----------------------------------------------------------------- Table 1: sample
rows = []
for pool in ORDER:
    r = {"Pool": LABEL[pool], "Fee": f"{int(pool.split('-')[-1]) / 100:g} bp"}
    for fork, cfg in FORKS.items():
        s = json.load(open(os.path.join(cfg["bundle"], SUMMARY)))
        r[f"Swaps ({fork})"] = f"{s['pools'][pool]['n_swaps']:,}"
        ex = pd.read_csv(os.path.join(cfg["bundle"], A14, "table_exposure.md"), sep="|", skipinitialspace=True)
        ex.columns = [c.strip() for c in ex.columns]
        ex = ex[ex["池"].notna()]
        ex["池"] = ex["池"].astype(str).str.strip()
        e = ex[ex["池"] == pool]
        r[f"Exposure σ√Δt/γ pre ({fork})"] = f"{float(e['暴露度 σ√Δt/γ'].iloc[0]):.2f}" if len(e) else "—"
    rows.append(r)
t1 = pd.DataFrame(rows)
open(os.path.join(OUT, "table1_sample.md"), "w").write(t1.to_markdown(index=False))

# ----------------------------------------------------------------- Table 2: descriptives (core pools, ±14 d)
rows = []
for fork, cfg in FORKS.items():
    p = pd.read_parquet(os.path.join(cfg["bundle"], A14, "hourly_panel.parquet"))
    s = json.load(open(os.path.join(cfg["bundle"], SUMMARY)))
    for pool in CORE:
        d = p[p.pool == pool]
        for post in (0, 1):
            x = d[d.post == post]
            hrs = len(x)
            rows.append({
                "Fork": fork, "Pool": LABEL[pool], "Regime": "post" if post else "pre",
                "Δt (s)": cfg["dt"][post],
                "σ (bp/√s)": 1e4 * np.sqrt(x.rv.sum() / (hrs * 3600)),
                "Swaps/h": x.swaps.mean(), "Volume/h (kUSDT)": x.volume.mean() / 1e3,
                "Arbs/h": x.n_arb.mean(), "Strict arbs/h": x.n_arb_strict.mean(),
                "Overshoot, strict (bp)": np.average(x.overshoot_strict_bps.fillna(0), weights=x.n_arb_strict),
                "Arb profit/h (USDT)": x.arb_profit.sum() / hrs,
                "LP loss/h (USDT)": x.arb_loss.sum() / hrs,
                "LP loss (bp of vol.)": 1e4 * x.arb_loss.sum() / x.volume.sum(),
                "LP net (bp of vol.)": 1e4 * x.lp_gain.sum() / x.volume.sum(),
                "Arb profit / LP loss": x.arb_profit.sum() / x.arb_loss.sum(),
            })
t2 = pd.DataFrame(rows)
t2.to_csv(os.path.join(OUT, "table2_descriptives.csv"), index=False)
open(os.path.join(OUT, "table2_descriptives.md"), "w").write(t2.to_markdown(index=False, floatfmt=".3g"))

# ----------------------------------------------------------------- Table 3: pooled core estimates, both forks
def load_core(cfg):
    cp = pd.read_csv(os.path.join(cfg["extra"], "core_pooled_raw.csv"))
    rd = pd.read_csv(os.path.join(cfg["extra"], "rd_jump.csv"))
    out = {}
    for _, r in cp.iterrows():
        key = (r["窗口"], r["控制"])
        out[key] = {"over": (r["_b_over"], r["_se_over"]), "prof": (r["_b_prof"], r["_se_prof"]), "loss": (r["_b_loss"], r["_se_loss"]),
                    "n": int(r["n"]), "per_arb": r["log 单笔 LP 损失"], "n_arb": r["log 套利笔数"]}
    for w in ("±30 d", "±14 d"):
        sub = rd[rd["窗口"] == w].set_index("被解释变量")
        out[(w, "RD")] = {"over": parse_cell(sub.loc["log 越界幅度（严格）", "跳跃（post）"])[::2],
                          "prof": parse_cell(sub.loc["log 套利者利润", "跳跃（post）"])[::2],
                          "loss": parse_cell(sub.loc["log LP 损失（总）", "跳跃（post）"])[::2],
                          "n": int(sub.loc["log 越界幅度（严格）", "n"]),
                          "pre_slope": sub.loc["log 越界幅度（严格）", "分叉前斜率（/天）"]}
    return out


def fmt(b, se):
    p = 2 * (1 - __import__("scipy").stats.norm.cdf(abs(b / se)))
    st = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
    return f"{b:+.3f}{st} ({se:.3f})".replace("+", "").replace("-", "−")


core = {f: load_core(c) for f, c in FORKS.items()}
SPEC_NAMES = {"σ": "log σ + hour FE", "σ+L+vol": "+ log L + log volume", "σ+L+vol+趋势": "+ linear trend",
              "σ+L+vol+池别趋势": "+ pool-specific trends", "RD": "RD jump (separate slopes)"}
rows = []
for w in ("±14 d", "±30 d", "±7 d"):
    for c in ("σ", "σ+L+vol", "σ+L+vol+趋势", "RD"):
        if (w, c) not in core["Maxwell"]:
            continue
        r = {"Window": w, "Specification": SPEC_NAMES[c]}
        for fork in FORKS:
            e = core[fork][(w, c)]
            r[f"{fork}: overshoot"] = fmt(*e["over"])
            r[f"{fork}: arb profit"] = fmt(*e["prof"])
            r[f"{fork}: LP loss"] = fmt(*e["loss"])
        r["N (M/F)"] = f"{core['Maxwell'][(w, c)]['n']:,} / {core['Fermi'][(w, c)]['n']:,}"
        rows.append(r)
t3 = pd.DataFrame(rows)
open(os.path.join(OUT, "table3_core_pooled.md"), "w").write(t3.to_markdown(index=False))

# ----------------------------------------------------------------- Table 4: dose response
th = {f: theory(c["dt"]) for f, c in FORKS.items()}
R = th["Fermi"] / th["Maxwell"]
SKIP_T4 = True
from scipy import stats
rows = []
for w in ("±30 d", "±14 d", "±7 d"):
    for c in ("σ", "σ+L+vol", "σ+L+vol+趋势", "RD"):
        if (w, c) not in core["Maxwell"] or SKIP_T4:
            continue
        bm, sm = core["Maxwell"][(w, c)]["over"]; bf, sf = core["Fermi"][(w, c)]["over"]
        d = bf - R * bm; se = np.sqrt(sf ** 2 + (R * sm) ** 2); p = 2 * (1 - stats.norm.cdf(abs(d / se)))
        rows.append({"Window": w, "Specification": SPEC_NAMES[c],
                     "Maxwell β (theory −0.347)": fmt(bm, sm), "share of theory": f"{bm / th['Maxwell']:.0%}",
                     "Fermi β (theory −0.255)": fmt(bf, sf), "share of theory ": f"{bf / th['Fermi']:.0%}",
                     "β_F/β_M (pred. 0.74)": f"{bf / bm:.2f}", "β_F − 0.74·β_M": fmt(d, se), "p": f"{p:.2f}"})
for f, c in FORKS.items():
    KEY[f"elasticity_{f}"] = [core[f][k]["over"][0] / np.log(c["dt"][1] / c["dt"][0]) for k in core[f] if k[1] != "σ+L+vol+池别趋势"]

# ----------------------------------------------------------------- Table 5: per-pool, ±14 d, σ+L+vol
rows = []
for pool in ORDER:
    r = {"Pool": LABEL[pool]}
    for fork, cfg in FORKS.items():
        path = os.path.join(cfg["bundle"], A14, "table_regressions.md")
        hdr = [c.strip() for c in open(path).read().split("### ")[2].splitlines()[2].split("|")[1:-1]]
        idx = hdr.index(pool)
        for lab, col in (("log 越界幅度（严格套利）", "overshoot"), ("log 套利者利润", "arb profit"),
                         ("log LP 逆向选择损失（总）", "LP loss"), ("LP 净收益 / 成交额", "LP net (bp)")):
            r[f"{fork}: {col}"] = strip_sigma(md_cells(path, 1, lab)[idx])
    rows.append(r)
t5 = pd.DataFrame(rows)
open(os.path.join(OUT, "table5_per_pool.md"), "w").write(t5.to_markdown(index=False))
t5a = t5[["Pool"] + [c for c in t5.columns if c.endswith(": overshoot") or c.endswith(": arb profit")]]
t5b = t5[["Pool"] + [c for c in t5.columns if c.endswith(": LP loss") or c.endswith(": LP net (bp)")]]
open(os.path.join(OUT, "table5a_per_pool_overshoot_profit.md"), "w").write(t5a.to_markdown(index=False))
open(os.path.join(OUT, "table5b_per_pool_lp.md"), "w").write(t5b.to_markdown(index=False))

# ----------------------------------------------------------------- Table 6: LP decomposition (core pooled)
import statsmodels.formula.api as smf
def fitlog(d, y, ex):
    d = d[(d[y] > 0) & (d.sigma_ps > 0) & (d.liq_mean > 0) & (d.volume > 0)]
    m = smf.ols(f"np.log({y}) ~ post + np.log(sigma_ps) + C(hod) + C(pool)" + ex, data=d).fit(cov_type="cluster", cov_kwds={"groups": d.day.astype(str)})
    return fmt(m.params["post"], m.bse["post"])
rows = []
for fork, cfg in FORKS.items():
    for w, sub in (("±14 d", A14), ("±30 d", A30)):
        p = pd.read_parquet(os.path.join(cfg["bundle"], sub, "hourly_panel.parquet")); p = p[p.pool.isin(CORE)]
        for ex, lab in ((" + np.log(liq_mean) + np.log(volume)", "+ log L + log volume"), (" + np.log(liq_mean) + np.log(volume) + t_days", "+ linear trend")):
            rows.append({"Fork": fork, "Window": w, "Specification": lab,
                         "Total LP loss (all swaps)": fitlog(p, "arb_loss", ex),
                         "LP loss to identified arbs": fitlog(p, "arb_loss_arbs", ex),
                         "Loss per arb": fitlog(p, "loss_per_arb", ex),
                         "Arbs per hour": fitlog(p, "n_arb", ex),
                         "Strict arbs per hour": fitlog(p, "n_arb_strict", ex),
                         "Arb profit": fitlog(p, "arb_profit", ex)})
t6 = pd.DataFrame(rows)
open(os.path.join(OUT, "table6_lp_decomposition.md"), "w").write(t6.to_markdown(index=False))

# ----------------------------------------------------------------- Table 7: price efficiency (summary.json, ±30 d; IS ±14 d)
rows = []
for pool in ORDER:
    r = {"Pool": LABEL[pool]}
    for fork, cfg in FORKS.items():
        s = json.load(open(os.path.join(cfg["bundle"], SUMMARY)))["pools"][pool]["regime"]
        a, b = s["pre"], s["post"]
        r[f"{fork}: episode length (s)"] = f"{a['outside_band_episode_mean_s']:.2f} → {b['outside_band_episode_mean_s']:.2f}"
        r[f"{fork}: half-life (s)"] = f"{a['dev_half_life_s']:.1f} → {b['dev_half_life_s']:.1f}"
        r[f"{fork}: seconds outside band"] = f"{100 * a['share_sec_outside_band']:.1f}% → {100 * b['share_sec_outside_band']:.1f}%"
        pass
    rows.append(r)
t7 = pd.DataFrame(rows)
open(os.path.join(OUT, "table7_efficiency.md"), "w").write(t7.to_markdown(index=False))

# ----------------------------------------------------------------- Table 8: placebo + heterogeneity + matched
rows = []
for fork, cfg in FORKS.items():
    pl = pd.read_csv(os.path.join(cfg["extra"], "placebo_core.md"), sep="|", skipinitialspace=True)
    pl.columns = [c.strip() for c in pl.columns]; pl = pl.dropna(axis=1, how="all"); pl = pl[pl["窗口"].astype(str).str.contains("d")]
    for _, r in pl.iterrows():
        rows.append({"Fork": fork, "Window": r["窗口"].strip(), "Fake fork (UTC)": r["假分叉"].strip(), "Specification": SPEC_NAMES[r["控制"].strip()],
                     "Overshoot": r["log 越界幅度（严格）"].strip().replace("-", "−"), "Arb profit": r["log 套利者利润"].strip().replace("-", "−"),
                     "LP loss": r["log LP 损失（总）"].strip().replace("-", "−")})
t8 = pd.DataFrame(rows)
open(os.path.join(OUT, "table8_placebo.md"), "w").write(t8.to_markdown(index=False))
rows = []
for fork, cfg in FORKS.items():
    h = pd.read_csv(os.path.join(cfg["extra"], "heterogeneity.md"), sep="|", skipinitialspace=True)
    h.columns = [c.strip() for c in h.columns]; h = h.dropna(axis=1, how="all"); h = h[h["交互项"].astype(str).str.contains("post")]
    names = {"post × log σ（去均值）": "post × log σ (demeaned)", "post × 高波动小时": "post × high-σ hour", "post × 亚洲时段(01–08 UTC)": "post × Asian hours (01–08 UTC)"}
    for _, r in h.iterrows():
        rows.append({"Fork": fork, "Interaction": names[r["交互项"].strip()], "post": r["post"].strip().replace("-", "−"),
                     "interaction": r["交互系数"].strip().replace("-", "−"), "p": r["p"].strip()})
t9 = pd.DataFrame(rows)
open(os.path.join(OUT, "table9_heterogeneity.md"), "w").write(t9.to_markdown(index=False))

# matched pairs ±14 d (from bundle table_matched.md)
rows = []
for fork, cfg in FORKS.items():
    m = pd.read_csv(os.path.join(cfg["bundle"], A14, "table_matched.md"), sep="|", skipinitialspace=True)
    m.columns = [c.strip() for c in m.columns]; m = m.dropna(axis=1, how="all")
    m = m[m["池"].astype(str).str.contains("USDT|WBNB")]
    for pool in CORE + ["WBNB-USDT-100"]:
        r = {"Fork": fork, "Pool": LABEL[pool]}
        for metric, lab in (("越界幅度（严格）", "overshoot (theory √(Δt₁/Δt₀))"), ("套利者利润", "arb profit"), ("LP 损失", "LP loss"), ("σ", "σ")):
            x = m[(m["池"].str.strip() == pool) & (m["指标"].str.strip() == metric)]
            r[lab] = f"{float(x['中位数比（post/pre）'].iloc[0]):.3f}" if len(x) else "—"
        rows.append(r)
t10 = pd.DataFrame(rows)
open(os.path.join(OUT, "table10_matched.md"), "w").write(t10.to_markdown(index=False))

# ----------------------------------------------------------------- sigma path
rows = []
for fork, cfg in FORKS.items():
    sp = pd.read_csv(os.path.join(cfg["extra"], "sigma_path.csv"))
    for _, r in sp.iterrows():
        rows.append({"Fork": fork, "Window": r["窗口"], "Pool": LABEL[r["池"]], "σ post/pre": f"{r['σ 比']:.2f}", "volume post/pre": f"{r['成交额比']:.2f}",
                     "liquidity post/pre": f"{r['流动性比']:.2f}"})
t11 = pd.DataFrame(rows)
open(os.path.join(OUT, "table11_sigma_path.md"), "w").write(t11.to_markdown(index=False))

# ----------------------------------------------------------------- key numbers
for fork, cfg in FORKS.items():
    s = json.load(open(os.path.join(cfg["bundle"], SUMMARY)))
    KEY[fork] = {"fork_block": s["fork_block"], "fork_time": s["fork_time_utc"], "blocks": s["blocks"], "n_swaps": sum(d["n_swaps"] for d in s["pools"].values()),
                 "headers": s["n_headers_fetched"], "timestamped": s["n_blocks_timestamped"],
                 "interval_pre_ms": s["pools"]["WBNB-USDT-500"]["regime"]["pre"]["block_interval_ms"],
                 "interval_post_ms": s["pools"]["WBNB-USDT-500"]["regime"]["post"]["block_interval_ms"],
                 "theory": th[fork]}
    KEY[fork]["core"] = {f"{k[0]}|{k[1]}": {"over": v["over"], "prof": v["prof"], "loss": v["loss"], "n": v["n"]} for k, v in core[fork].items()}
json.dump(KEY, open(os.path.join(OUT, "key_numbers.json"), "w"), indent=1, default=float)
# ----------------------------------------------------------------- Tables 3/4 (three forks) copied from three_forks_tick
import shutil
shutil.copy(os.path.join(TF, "tableA_three_forks.md"), os.path.join(OUT, "table3_three_forks_overshoot.md"))
shutil.copy(os.path.join(TF, "tableB_profit_loss.md"), os.path.join(OUT, "table4_three_forks_profit_loss.md"))
shutil.copy(os.path.join(TF, "tableC_stacked.md"), os.path.join(OUT, "table4b_stacked.md"))

# ----------------------------------------------------------------- Table 12: kline vs tick wedge, three forks
rows = []
for fork in FORKS:
    k = json.load(open(os.path.join(TICK_CMP, fork, "key_numbers.json")))
    r = {"Fork": fork,
         "Mean wedge pre → post (±30 d)": f"{k['wedge_mean|30|post0']:.3f} → {k['wedge_mean|30|post1']:.3f}",
         "RD jump of wedge, ±30 d": fmt(k["wedge_rd|30|overshoot_strict_bps"]["b"], k["wedge_rd|30|overshoot_strict_bps"]["se"]),
         "RD jump of wedge, ±14 d": fmt(k["wedge_rd|14|overshoot_strict_bps"]["b"], k["wedge_rd|14|overshoot_strict_bps"]["se"]),
         "Pre-fork slope of wedge (/day, ±30 d)": f"{k['wedge_rd|30|overshoot_strict_bps']['preslope']:+.4f} ({k['wedge_rd|30|overshoot_strict_bps']['preslope_se']:.4f})",
         "RD jump with log ref-gap control, ±30 d": fmt(k["wedge_rd_refgap|30"]["b"], k["wedge_rd_refgap|30"]["se"]),
         "Mean |kline/tick − 1| pre → post (bp)": f"{k['refgap_mean|30|post0']:.2f} → {k['refgap_mean|30|post1']:.2f}",
         "RD jump, profit wedge": fmt(k["wedge_rd|30|arb_profit"]["b"], k["wedge_rd|30|arb_profit"]["se"]),
         "RD jump, arb-count wedge": fmt(k["wedge_rd|30|n_arb"]["b"], k["wedge_rd|30|n_arb"]["se"]),
         "Kline − tick effect, preferred specs": ""}
    rows.append(r)
    KEY[f"wedge_{fork}"] = {kk: v for kk, v in k.items() if kk.startswith("wedge") or kk.startswith("refgap")}
t12 = pd.DataFrame(rows).drop(columns=["Kline − tick effect, preferred specs"])
open(os.path.join(OUT, "table12_wedge.md"), "w").write(t12.to_markdown(index=False))

# ----------------------------------------------------------------- Table 13: kline vs tick estimates, preferred specs
PREF = {"Lorentz": [("±30 d", "σ+L+vol+趋势"), ("±30 d", "RD")],
        "Maxwell": [("±14 d", "σ"), ("±14 d", "σ+L+vol"), ("±14 d", "σ+L+vol+趋势"), ("±14 d", "RD"), ("±30 d", "σ"), ("±30 d", "σ+L+vol")],
        "Fermi": [("±14 d", "σ+L+vol"), ("±30 d", "σ+L+vol+趋势"), ("±30 d", "RD")]}
rows = []
for fork in FORKS:
    k = json.load(open(os.path.join(TICK_CMP, fork, "key_numbers.json")))
    lndt = np.log(FORKS[fork]["dt"][1] / FORKS[fork]["dt"][0])
    for w, c in PREF[fork]:
        kk, tt = k[f"kline|{w}|{c}|overshoot_strict_bps"], k[f"tick|{w}|{c}|overshoot_strict_bps"]
        kp, tp = k[f"kline|{w}|{c}|arb_profit"], k[f"tick|{w}|{c}|arb_profit"]
        kl, tl = k[f"kline|{w}|{c}|arb_loss"], k[f"tick|{w}|{c}|arb_loss"]
        kn, tn = k[f"kline|{w}|{c}|n_arb"], k[f"tick|{w}|{c}|n_arb"]
        rows.append({"Fork": fork, "Window": w, "Specification": SPEC_NAMES[c],
                     "Overshoot, 1-s kline": fmt(kk["b"], kk["se"]), "Overshoot, tick": fmt(tt["b"], tt["se"]),
                     "share of prediction (tick)": f"{tt['b'] / th[fork]:.0%}", "elasticity (tick)": f"{tt['b'] / lndt:.2f} ({tt['se'] / abs(lndt):.2f})",
                     "Arb profit, kline": fmt(kp["b"], kp["se"]), "Arb profit, tick": fmt(tp["b"], tp["se"]),
                     "LP loss, kline": fmt(kl["b"], kl["se"]), "LP loss, tick": fmt(tl["b"], tl["se"]),
                     "Arbs/h, kline": fmt(kn["b"], kn["se"]), "Arbs/h, tick": fmt(tn["b"], tn["se"])})
        KEY.setdefault("pref", {})[f"{fork}|{w}|{c}"] = {"over_k": kk, "over_t": tt, "prof_k": kp, "prof_t": tp, "loss_k": kl, "loss_t": tl, "n_k": kn, "n_t": tn}
t13 = pd.DataFrame(rows)
open(os.path.join(OUT, "table13_kline_vs_tick_preferred.md"), "w").write(t13.to_markdown(index=False))

# ----------------------------------------------------------------- Table 14: latency floor (copied) + Table 15: LP loss / fee, six regimes; reference noise
shutil.copy(os.path.join(TF, "latency_floor.md"), os.path.join(OUT, "table14_latency_floor.md"))
KEY["latency_floor"] = json.load(open(os.path.join(TF, "latency_floor.json")))
lv = pd.read_csv(os.path.join(TICK_CMP, "levels_three_forks.csv"))
REG = [("Lorentz", "pre", "3 s"), ("Lorentz", "post", "1.5 s (Apr–May 2025)"), ("Maxwell", "pre", "1.5 s (Jun 2025)"), ("Maxwell", "post", "0.75 s (Jul 2025)"),
       ("Fermi", "pre", "0.75 s (Dec 2025–Jan 2026)"), ("Fermi", "post", "0.45 s")]
rows = []
for metric, lab in (("lossfee_t", "LP loss / fee income"), ("arbshare_t", "arbitrage share of swaps"), ("gap_t", "mean |kline − tick| reference gap (bp)"), ("rms_t", "RMS reference gap (bp)"), ("sig", "σ (bp per 1 s)")):
    for pool in ["ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-500", "WBNB-USDT-100"]:
        r = {"Statistic": lab, "Pool": LABEL[pool]}
        for fork, reg, name in REG:
            v = lv[(lv.fork == fork) & (lv.pool == pool)][metric].iloc[0].split("/")[0 if reg == "pre" else 1]
            r[name] = v
        rows.append(r)
t15 = pd.DataFrame(rows)
open(os.path.join(OUT, "table15_levels_six_regimes.md"), "w").write(t15.to_markdown(index=False))
KEY["levels_six_regimes"] = lv.to_dict(orient="records")
print("tables written:", sorted(os.listdir(OUT)))
print(t3.to_string()); print(t6.to_string())
