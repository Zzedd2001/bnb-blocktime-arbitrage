"""Fermi: 1-s kline reference vs tick-level (aggTrades) reference — same panels, same specifications.

Inputs
  fermi/bundle/analysis{,_14d}/hourly_panel.parquet            kline reference (run_pilot default)
  fermi_tick/bundle/analysis_agg{,_14d}/hourly_panel.parquet   tick reference (run_pilot --reference aggtrades)
Outputs (fermi_tick/cmp/)
  tableA_core_kline_vs_tick.md/csv   pooled core (3×5 bp) post coefficients, both references, implied Δt-elasticity
  tableB_sigma_elasticity.md         σ-elasticity of the overshoot (σ-only spec), per pool and pooled
  tableC_wedge.md                    log(overshoot_tick / overshoot_kline) regressed on post (+ controls)
  tableD_levels.md                   regime-table levels, core pools + 1 bp pool
  tableE_onebp.md                    1 bp pool, both references
  fig_wedge.png                      daily wedge and daily reference gap around the fork
  fig_event_study_kline_vs_tick.png  residualised daily overshoot / profit / LP loss, both references
  key_numbers.json
"""
from __future__ import annotations
import os, json
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "cmp"); os.makedirs(OUT, exist_ok=True)
K30 = os.path.join(ROOT, "fermi/bundle/analysis/hourly_panel.parquet")
K14 = os.path.join(ROOT, "fermi/bundle/analysis_14d/hourly_panel.parquet")
T30 = os.path.join(HERE, "bundle/analysis_agg/hourly_panel.parquet")
T14 = os.path.join(HERE, "bundle/analysis_agg_14d/hourly_panel.parquet")
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
THEORY = 0.5 * np.log(0.45 / 0.75)          # -0.2554
LNDT = np.log(0.45 / 0.75)                  # -0.5108
OUTCOMES = [("log 越界幅度（严格）", "overshoot_strict_bps"), ("log 越界幅度（全部）", "overshoot_bps"),
            ("log 套利者利润", "arb_profit"), ("log 单笔 LP 损失", "loss_per_arb"),
            ("log LP 损失（总）", "arb_loss"), ("log 套利笔数", "n_arb")]
CONTROLS = [("σ", ""), ("σ+L+vol", " + np.log(liq_mean) + np.log(volume)"),
            ("σ+L+vol+趋势", " + np.log(liq_mean) + np.log(volume) + t_days")]
C_K, C_T, INK, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#e6e6e3"


def setup_fonts():
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK" in f or "NotoSerifCJK" in f:
            font_manager.fontManager.addfont(f)
    for name in ("Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans SC", "DejaVu Sans"):
        if any(name == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name; break
    plt.rcParams["axes.unicode_minus"] = False


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


def load():
    P = {("kline", 30): pd.read_parquet(K30), ("kline", 14): pd.read_parquet(K14),
         ("tick", 30): pd.read_parquet(T30), ("tick", 14): pd.read_parquet(T14)}
    for k, d in P.items():
        d["hour"] = pd.to_datetime(d["hour"], utc=True)
    return P


def table_a(P, key):
    rows = []
    for w in (30, 14, 7):
        for cname, extra in CONTROLS:
            for lab, y in OUTCOMES:
                r = {"窗口": f"±{w} d", "控制": cname, "被解释变量": lab}
                for ref in ("kline", "tick"):
                    d = P[(ref, 30 if w == 30 else 14)]
                    d = window(d, 7) if w == 7 else d
                    d = d[d.pool.isin(CORE)]
                    m, n = fit(d, y, extra)
                    r[f"{ref}"] = cell(m); r[f"_b_{ref}"] = m.params["post"]; r[f"_se_{ref}"] = m.bse["post"]
                    r[f"_n_{ref}"] = n
                r["差（tick−kline）"] = f"{r['_b_tick'] - r['_b_kline']:+.3f}"
                if y in ("overshoot_strict_bps", "overshoot_bps", "arb_profit"):
                    r["Δt 弹性 kline"] = f"{r['_b_kline'] / LNDT:.2f}"
                    r["Δt 弹性 tick"] = f"{r['_b_tick'] / LNDT:.2f}"
                else:
                    r["Δt 弹性 kline"] = r["Δt 弹性 tick"] = ""
                rows.append(r)
    t = pd.DataFrame(rows)
    show = t[[c for c in t.columns if not c.startswith("_")]]
    show.to_csv(os.path.join(OUT, "tableA_core_kline_vs_tick.csv"), index=False)
    t.to_csv(os.path.join(OUT, "tableA_core_kline_vs_tick_raw.csv"), index=False)
    open(os.path.join(OUT, "tableA_core_kline_vs_tick.md"), "w").write(show.to_markdown(index=False))
    # key numbers: placebo-clean specs (Fermi: ±14 d σ+L+vol; ±30 d σ+L+vol+趋势)
    for ref in ("kline", "tick"):
        for (w, c) in ((14, "σ+L+vol"), (30, "σ+L+vol+趋势"), (30, "σ+L+vol"), (14, "σ+L+vol+趋势")):
            for lab, y in OUTCOMES:
                sub = t[(t["窗口"] == f"±{w} d") & (t["控制"] == c) & (t["被解释变量"] == lab)].iloc[0]
                key[f"{ref}|{w}|{c}|{y}"] = {"b": float(sub[f"_b_{ref}"]), "se": float(sub[f"_se_{ref}"]), "n": int(sub[f"_n_{ref}"])}
    return t


def table_b(P, key):
    rows = []
    for w in (30, 14):
        for pool in CORE + ["WBNB-USDT-100", "合并（核心 3 池）"]:
            r = {"窗口": f"±{w} d", "池": pool}
            for ref in ("kline", "tick"):
                d = P[(ref, w)]
                d = d[d.pool.isin(CORE)] if pool.startswith("合并") else d[d.pool == pool]
                for lab, y in (("严格", "overshoot_strict_bps"), ("全部", "overshoot_bps")):
                    m, n = fit(d, y, "", pool_fe=pool.startswith("合并"))
                    r[f"{ref} σ 弹性（{lab}）"] = cell(m, "np.log(sigma_ps)")
                    if pool.startswith("合并"):
                        key[f"sigma_elasticity|{ref}|{w}|{y}"] = {"b": float(m.params["np.log(sigma_ps)"]), "se": float(m.bse["np.log(sigma_ps)"])}
            rows.append(r)
    t = pd.DataFrame(rows)
    open(os.path.join(OUT, "tableB_sigma_elasticity.md"), "w").write(t.to_markdown(index=False))
    return t


def merged(P, w):
    k = P[("kline", w)]; t = P[("tick", w)]
    cols = ["pool", "hour", "overshoot_strict_bps", "overshoot_bps", "arb_profit", "arb_loss", "loss_per_arb", "n_arb", "n_arb_strict"]
    m = k[cols + ["sigma_ps", "liq_mean", "volume", "post", "hod", "day", "t_days"]].merge(
        t[cols + ["ref_gap_bps"]], on=["pool", "hour"], suffixes=("_k", "_t"))
    for y in ("overshoot_strict_bps", "overshoot_bps", "arb_profit", "arb_loss", "loss_per_arb", "n_arb"):
        m[f"w_{y}"] = np.log(m[f"{y}_t"]) - np.log(m[f"{y}_k"])
    return m.replace([np.inf, -np.inf], np.nan)


def table_c(P, key):
    rows = []
    for w in (30, 14):
        m = merged(P, w)
        m = m[m.pool.isin(CORE)]
        for cname, extra in CONTROLS:
            r = {"窗口": f"±{w} d", "控制": cname}
            for lab, y in (("越界幅度（严格）", "overshoot_strict_bps"), ("越界幅度（全部）", "overshoot_bps"),
                           ("套利者利润", "arb_profit"), ("LP 损失（总）", "arb_loss"), ("套利笔数", "n_arb")):
                d = m.dropna(subset=[f"w_{y}", "sigma_ps"])
                d = d[(d.sigma_ps > 0) & (d.liq_mean > 0) & (d.volume > 0)]
                f = f"w_{y} ~ post + np.log(sigma_ps) + C(hod) + C(pool)" + extra
                mod = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
                r[f"楔子：{lab}"] = cell(mod)
                if y == "overshoot_strict_bps":
                    r["_b"] = mod.params["post"]; r["_se"] = mod.bse["post"]
                    r["σ 系数（严格越界楔子）"] = cell(mod, "np.log(sigma_ps)")
                    r["n（严格越界楔子）"] = int(mod.nobs)
                    key[f"wedge|{w}|{cname}|overshoot_strict"] = {"b": float(mod.params["post"]), "se": float(mod.bse["post"]),
                                                                 "sigma": float(mod.params["np.log(sigma_ps)"]), "n": int(mod.nobs)}
            rows.append(r)
        # wedge vs reference gap (mechanism): wedge_overshoot ~ log ref_gap + post + ...
        d = m.dropna(subset=["w_overshoot_strict_bps", "ref_gap_bps"]); d = d[(d.ref_gap_bps > 0) & (d.sigma_ps > 0)]
        mod = smf.ols("w_overshoot_strict_bps ~ np.log(ref_gap_bps) + post + np.log(sigma_ps) + C(hod) + C(pool)", data=d).fit(
            cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
        key[f"wedge_refgap|{w}"] = {"b_refgap": float(mod.params["np.log(ref_gap_bps)"]), "se_refgap": float(mod.bse["np.log(ref_gap_bps)"]),
                                    "b_post": float(mod.params["post"]), "se_post": float(mod.bse["post"]), "n": int(mod.nobs)}
        # mean wedge pre/post, mean ref gap pre/post
        for p in (0, 1):
            s = m[(m.post == p)]
            key[f"wedge_mean|{w}|post{p}"] = float(np.nanmean(s["w_overshoot_strict_bps"]))
            key[f"refgap_mean|{w}|post{p}"] = float(np.nanmean(s["ref_gap_bps"]))
    t = pd.DataFrame(rows)
    show = t[[c for c in t.columns if not c.startswith("_")]]
    open(os.path.join(OUT, "tableC_wedge.md"), "w").write(show.to_markdown(index=False))
    return t


def table_d():
    d = pd.read_csv(os.path.join(OUT, "levels_kline_vs_tick.csv"))
    keep = ["arb_swaps_share", "arb_swaps_per_hour", "median_arb_size_quote", "arb_loss_bps_of_volume", "lp_net_bps_of_volume",
            "arb_loss_over_fee", "arb_loss_per_hour_quote", "ref_kline_vs_tick_mean_abs_bps", "ref_kline_vs_tick_rms_bps", "cex_vol_1s_bps"]
    names = {"arb_swaps_share": "套利 swap 占比", "arb_swaps_per_hour": "套利笔数/小时", "median_arb_size_quote": "套利中位规模 (USDT)",
             "arb_loss_bps_of_volume": "LP 损失 (bp of volume)", "lp_net_bps_of_volume": "LP 净收益 (bp of volume)",
             "arb_loss_over_fee": "LP 损失 / 手续费", "arb_loss_per_hour_quote": "LP 损失/小时 (USDT)",
             "ref_kline_vs_tick_mean_abs_bps": "参考价差 K线 vs tick，均值|gap| (bp)", "ref_kline_vs_tick_rms_bps": "参考价差 RMS (bp)",
             "cex_vol_1s_bps": "σ（1 s，bp）"}
    d = d[d.metric.isin(keep) & d.pool.isin(CORE + ["WBNB-USDT-100"])].copy()
    d["指标"] = d.metric.map(names)
    d = d[["pool", "指标", "kline_pre", "tick_pre", "kline_post", "tick_post"]].rename(columns={"pool": "池", "kline_pre": "K线 pre", "tick_pre": "tick pre", "kline_post": "K线 post", "tick_post": "tick post"})
    open(os.path.join(OUT, "tableD_levels.md"), "w").write(d.to_markdown(index=False, floatfmt=".3g"))
    return d


def table_e(P, key):
    rows = []
    for w in (30, 14):
        for cname, extra in CONTROLS:
            r = {"窗口": f"±{w} d", "控制": cname}
            for lab, y in OUTCOMES:
                for ref in ("kline", "tick"):
                    d = P[(ref, w)]; d = d[d.pool == "WBNB-USDT-100"]
                    m, n = fit(d, y, extra, pool_fe=False)
                    r[f"{lab} {ref}"] = cell(m)
                    key[f"onebp|{ref}|{w}|{cname}|{y}"] = {"b": float(m.params["post"]), "se": float(m.bse["post"])}
            rows.append(r)
    t = pd.DataFrame(rows)
    open(os.path.join(OUT, "tableE_onebp.md"), "w").write(t.to_markdown(index=False))
    return t


def fig_wedge(P):
    m = merged(P, 30); m = m[m.pool.isin(CORE)]
    m["date"] = m["hour"].dt.floor("D")
    g = m.groupby("date").agg(w=("w_overshoot_strict_bps", "mean"), gap=("ref_gap_bps", "mean"), sig=("sigma_ps", "mean")).reset_index()
    fork = pd.Timestamp("2026-01-14 02:30", tz="UTC")
    g["t"] = (g["date"] - fork).dt.total_seconds() / 86400
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    for a, col, ttl, c in ((ax[0], "w", "log(越界幅度 tick / K线)，核心 3 池日均", C_T),
                           (ax[1], "gap", "参考价差 |K线/tick − 1|（bp），日均", C_K),
                           (ax[2], "sig", "σ（分钟实现波动率，日均）", INK)):
        a.plot(g["t"], g[col], color=c, lw=1.4)
        a.axvline(0, color="#999", lw=1, ls="--")
        a.set_title(ttl, fontsize=10); a.set_xlabel("距分叉天数"); a.grid(color=GRID, lw=0.6)
        for s in ("top", "right"): a.spines[s].set_visible(False)
    ax[0].axhline(0, color="#bbb", lw=0.8)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_wedge.png"), dpi=160); plt.close(fig)


def fig_event(P):
    """Residualised daily means (hod + pool FE + log σ + log L + log vol, pre-period fit) for both references."""
    fork = pd.Timestamp("2026-01-14 02:30", tz="UTC")
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    for j, (lab, y) in enumerate((("log 越界幅度（严格）", "overshoot_strict_bps"), ("log 套利者利润", "arb_profit"), ("log LP 损失（总）", "arb_loss"))):
        for ref, c in (("kline", C_K), ("tick", C_T)):
            d = P[(ref, 30)]; d = d[d.pool.isin(CORE)]
            d = clean(d, y, CONTROLS[1][1]); d = d[d.volume > 0]
            pre = d[d.post == 0]
            mod = smf.ols(f"np.log({y}) ~ np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + C(hod) + C(pool)", data=pre).fit()
            d = d.copy(); d["res"] = np.log(d[y]) - mod.predict(d)
            d["date"] = d["hour"].dt.floor("D")
            g = d.groupby("date")["res"].mean().reset_index()
            g["t"] = (g["date"] - fork).dt.total_seconds() / 86400
            ax[j].plot(g["t"], g["res"], color=c, lw=1.3, label=f"{'1 s K 线' if ref == 'kline' else 'tick'} 参考价")
            post_mean = g[g.t >= 0]["res"].mean(); ax[j].hlines(post_mean, 0, 30, color=c, lw=1, ls=":")
        ax[j].axvline(0, color="#999", lw=1, ls="--"); ax[j].axhline(0, color="#bbb", lw=0.8)
        ax[j].set_title(f"{lab}（分叉前拟合的残差，日均）", fontsize=10); ax[j].set_xlabel("距分叉天数"); ax[j].grid(color=GRID, lw=0.6)
        for s in ("top", "right"): ax[j].spines[s].set_visible(False)
    ax[0].legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_event_study_kline_vs_tick.png"), dpi=160); plt.close(fig)


def main():
    setup_fonts()
    P = load(); key = {}
    tA = table_a(P, key); tB = table_b(P, key); tC = table_c(P, key); tD = table_d(); tE = table_e(P, key)
    fig_wedge(P); fig_event(P)
    json.dump(key, open(os.path.join(OUT, "key_numbers.json"), "w"), indent=1, ensure_ascii=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
    print(tA[[c for c in tA.columns if not c.startswith("_")]].to_string()); print(); print(tB.to_string()); print(); print(tC[[c for c in tC.columns if not c.startswith("_")]].to_string()); print(); print(tE.to_string())
    for k, v in key.items():
        if k.startswith("wedge_refgap") or k.startswith("wedge_mean") or k.startswith("refgap_mean"):
            print(k, v)


if __name__ == "__main__":
    main()
