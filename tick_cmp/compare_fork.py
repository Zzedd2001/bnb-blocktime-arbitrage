"""One fork: 1-s kline reference vs tick-level (aggTrades) reference — same panels, same specifications.

    python compare_fork.py --fork Fermi|Maxwell|Lorentz

Outputs (tick_cmp/<fork>/)
  tableA_core_kline_vs_tick.md/csv   pooled core (3×5 bp) post coefficients, both references, implied Δt-elasticity
  tableB_sigma_elasticity.md         σ-elasticity of the overshoot (σ-only spec), per pool and pooled
  tableC_wedge.md                    log(overshoot_tick / overshoot_kline) on post (+ controls)
  tableD_levels.md, levels_kline_vs_tick.csv   regime-table levels
  tableE_onebp.md                    1 bp pool, both references
  tableF_wedge_rd.md                 RD jump of the wedge at the fork (separate slopes), σ-only controls
  fig_wedge.png, fig_event_study_kline_vs_tick.png, key_numbers.json
"""
from __future__ import annotations
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os, json, argparse
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = ROOT + ""
CFG = {
    "Fermi": {"k30": f"{ROOT}/fermi/bundle/analysis", "k14": f"{ROOT}/fermi/bundle/analysis_14d",
              "t30": f"{ROOT}/fermi_tick/bundle/analysis_agg", "t14": f"{ROOT}/fermi_tick/bundle/analysis_agg_14d",
              "kres": f"{ROOT}/fermi/bundle/results", "tres": f"{ROOT}/fermi_tick/bundle/results_agg",
              "fork": "2026-01-14 02:30", "dt": (0.75, 0.45)},
    "Maxwell": {"k30": f"{ROOT}/maxwell/analysis", "k14": f"{ROOT}/maxwell/analysis_14d",
                "t30": f"{ROOT}/maxwell_tick/bundle/analysis_agg", "t14": f"{ROOT}/maxwell_tick/bundle/analysis_agg_14d",
                "kres": f"{ROOT}/maxwell/results", "tres": f"{ROOT}/maxwell_tick/bundle/results_agg",
                "fork": "2025-06-30 02:30:01", "dt": (1.5, 0.75)},
    "Lorentz": {"k30": f"{ROOT}/lorentz/bundle/analysis", "k14": f"{ROOT}/lorentz/bundle/analysis_14d",
                "t30": f"{ROOT}/lorentz_tick/bundle/analysis_agg", "t14": f"{ROOT}/lorentz_tick/bundle/analysis_agg_14d",
                "kres": f"{ROOT}/lorentz/bundle/results", "tres": f"{ROOT}/lorentz_tick/bundle/results_agg",
                "fork": "2025-04-29 05:05", "dt": (3.0, 1.5)},
}
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
POOLS = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-100", "USDC-USDT-100", "CAKE-WBNB-2500", "WBNB-USDT-10000"]
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


def load(cfg):
    P = {("kline", 30): pd.read_parquet(os.path.join(cfg["k30"], "hourly_panel.parquet")),
         ("kline", 14): pd.read_parquet(os.path.join(cfg["k14"], "hourly_panel.parquet")),
         ("tick", 30): pd.read_parquet(os.path.join(cfg["t30"], "hourly_panel.parquet")),
         ("tick", 14): pd.read_parquet(os.path.join(cfg["t14"], "hourly_panel.parquet"))}
    for k, d in P.items():
        d["hour"] = pd.to_datetime(d["hour"], utc=True)
    return P


def rd_fit(d, y, extra, pool_fe=True):
    """log y ~ post + t + post:t + σ (+ extra) — jump at the fork with separate slopes."""
    return fit(d, y, extra, rhs_extra=" + t_days + post:t_days", pool_fe=pool_fe)


def table_a(P, key, out, LNDT):
    rows = []
    for w in (30, 14, 7):
        for cname, extra in CONTROLS + [("RD", CONTROLS[1][1])]:
            if cname == "RD" and w == 7:
                continue
            for lab, y in OUTCOMES:
                r = {"窗口": f"±{w} d", "控制": cname, "被解释变量": lab}
                for ref in ("kline", "tick"):
                    d = P[(ref, 30 if w == 30 else 14)]
                    d = window(d, 7) if w == 7 else d
                    d = d[d.pool.isin(CORE)]
                    m, n = (rd_fit(d, y, extra) if cname == "RD" else fit(d, y, extra))
                    r[f"{ref}"] = cell(m); r[f"_b_{ref}"] = m.params["post"]; r[f"_se_{ref}"] = m.bse["post"]; r[f"_n_{ref}"] = n
                    if cname == "RD":
                        r[f"_preslope_{ref}"] = m.params["t_days"]; r[f"_preslope_se_{ref}"] = m.bse["t_days"]
                r["差（tick−kline）"] = f"{r['_b_tick'] - r['_b_kline']:+.3f}"
                if y in ("overshoot_strict_bps", "overshoot_bps", "arb_profit"):
                    r["Δt 弹性 kline"] = f"{r['_b_kline'] / LNDT:.2f}"; r["Δt 弹性 tick"] = f"{r['_b_tick'] / LNDT:.2f}"
                else:
                    r["Δt 弹性 kline"] = r["Δt 弹性 tick"] = ""
                rows.append(r)
    t = pd.DataFrame(rows)
    show = t[[c for c in t.columns if not c.startswith("_")]]
    show.to_csv(os.path.join(out, "tableA_core_kline_vs_tick.csv"), index=False)
    t.to_csv(os.path.join(out, "tableA_core_kline_vs_tick_raw.csv"), index=False)
    open(os.path.join(out, "tableA_core_kline_vs_tick.md"), "w").write(show.to_markdown(index=False))
    for _, r in t.iterrows():
        for ref in ("kline", "tick"):
            y = [yy for ll, yy in OUTCOMES if ll == r["被解释变量"]][0]
            key[f"{ref}|{r['窗口']}|{r['控制']}|{y}"] = {"b": float(r[f"_b_{ref}"]), "se": float(r[f"_se_{ref}"]), "n": int(r[f"_n_{ref}"])}
            if r["控制"] == "RD":
                key[f"{ref}|{r['窗口']}|RD|{y}|preslope"] = {"b": float(r[f"_preslope_{ref}"]), "se": float(r[f"_preslope_se_{ref}"])}
    return t


def table_b(P, key, out):
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
                    key[f"sigma_elasticity|{ref}|{w}|{pool}|{y}"] = {"b": float(m.params["np.log(sigma_ps)"]), "se": float(m.bse["np.log(sigma_ps)"])}
            rows.append(r)
    t = pd.DataFrame(rows)
    open(os.path.join(out, "tableB_sigma_elasticity.md"), "w").write(t.to_markdown(index=False))
    return t


def merged(P, w):
    k = P[("kline", w)]; t = P[("tick", w)]
    cols = ["pool", "hour", "overshoot_strict_bps", "overshoot_bps", "arb_profit", "arb_loss", "loss_per_arb", "n_arb", "n_arb_strict"]
    m = k[cols + ["sigma_ps", "liq_mean", "volume", "post", "hod", "day", "t_days"]].merge(
        t[cols + ["ref_gap_bps"]], on=["pool", "hour"], suffixes=("_k", "_t"))
    for y in ("overshoot_strict_bps", "overshoot_bps", "arb_profit", "arb_loss", "loss_per_arb", "n_arb"):
        m[f"w_{y}"] = np.log(m[f"{y}_t"]) - np.log(m[f"{y}_k"])
    return m.replace([np.inf, -np.inf], np.nan)


def table_c(P, key, out):
    rows, rd_rows = [], []
    for w in (30, 14):
        m = merged(P, w); m = m[m.pool.isin(CORE)]
        for cname, extra in CONTROLS:
            r = {"窗口": f"±{w} d", "控制": cname}
            for lab, y in (("越界幅度（严格）", "overshoot_strict_bps"), ("越界幅度（全部）", "overshoot_bps"),
                           ("套利者利润", "arb_profit"), ("LP 损失（总）", "arb_loss"), ("套利笔数", "n_arb")):
                d = m.dropna(subset=[f"w_{y}", "sigma_ps"]); d = d[(d.sigma_ps > 0) & (d.liq_mean > 0) & (d.volume > 0)]
                mod = smf.ols(f"w_{y} ~ post + np.log(sigma_ps) + C(hod) + C(pool)" + extra, data=d).fit(
                    cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
                r[f"楔子：{lab}"] = cell(mod)
                key[f"wedge|{w}|{cname}|{y}"] = {"b": float(mod.params["post"]), "se": float(mod.bse["post"]), "n": int(mod.nobs)}
                if y == "overshoot_strict_bps":
                    r["σ 系数（严格越界楔子）"] = cell(mod, "np.log(sigma_ps)"); r["n（严格越界楔子）"] = int(mod.nobs)
            rows.append(r)
        # RD jump of the wedge (σ-only), with and without log ref_gap
        r = {"窗口": f"±{w} d"}
        for lab, y in (("越界幅度（严格）", "overshoot_strict_bps"), ("越界幅度（全部）", "overshoot_bps"), ("套利者利润", "arb_profit"), ("套利笔数", "n_arb"), ("LP 损失（总）", "arb_loss")):
            d = m.dropna(subset=[f"w_{y}", "sigma_ps"]); d = d[(d.sigma_ps > 0)]
            mod = smf.ols(f"w_{y} ~ post + t_days + post:t_days + np.log(sigma_ps) + C(hod) + C(pool)", data=d).fit(
                cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
            r[f"跳变：{lab}"] = cell(mod)
            key[f"wedge_rd|{w}|{y}"] = {"b": float(mod.params["post"]), "se": float(mod.bse["post"]), "preslope": float(mod.params["t_days"]),
                                        "preslope_se": float(mod.bse["t_days"]), "n": int(mod.nobs)}
            if y == "overshoot_strict_bps":
                r["分叉前斜率（严格）"] = cell(mod, "t_days")
                d2 = d[d.ref_gap_bps > 0]
                mod2 = smf.ols("w_overshoot_strict_bps ~ post + t_days + post:t_days + np.log(sigma_ps) + np.log(ref_gap_bps) + C(hod) + C(pool)", data=d2).fit(
                    cov_type="cluster", cov_kwds={"groups": d2["day"].astype(str)})
                r["跳变（严格，加 log 参考价差）"] = cell(mod2); r["log 参考价差系数"] = cell(mod2, "np.log(ref_gap_bps)")
                key[f"wedge_rd_refgap|{w}"] = {"b": float(mod2.params["post"]), "se": float(mod2.bse["post"]),
                                               "b_refgap": float(mod2.params["np.log(ref_gap_bps)"]), "se_refgap": float(mod2.bse["np.log(ref_gap_bps)"])}
        rd_rows.append(r)
        for p in (0, 1):
            s = m[(m.post == p)]
            key[f"wedge_mean|{w}|post{p}"] = float(np.nanmean(s["w_overshoot_strict_bps"]))
            key[f"refgap_mean|{w}|post{p}"] = float(np.nanmean(s["ref_gap_bps"]))
    t = pd.DataFrame(rows)
    open(os.path.join(out, "tableC_wedge.md"), "w").write(t.to_markdown(index=False))
    tf = pd.DataFrame(rd_rows)
    open(os.path.join(out, "tableF_wedge_rd.md"), "w").write(tf.to_markdown(index=False))
    return t, tf


def table_d(cfg, key, out):
    rows_all = ["swaps", "arb_swaps_share", "arb_strict_share", "arb_volume_share", "arb_swaps_per_hour", "median_arb_size_quote",
                "arb_loss_bps_of_volume", "lp_net_bps_of_volume", "arb_loss_over_fee", "arb_loss_per_hour_quote", "arb_loss_per_arb_quote",
                "markout_30s_bps_of_volume", "ref_kline_vs_tick_mean_abs_bps", "ref_kline_vs_tick_rms_bps", "cex_vol_1s_bps"]
    recs = []
    for p in POOLS:
        k = pd.read_csv(os.path.join(cfg["kres"], p, "regime_table.csv"), index_col=0)
        t = pd.read_csv(os.path.join(cfg["tres"], p, "regime_table.csv"), index_col=0)
        for r in rows_all:
            recs.append(dict(pool=p, metric=r, kline_pre=k.loc[r, "pre"] if r in k.index else np.nan, tick_pre=t.loc[r, "pre"],
                             kline_post=k.loc[r, "post"] if r in k.index else np.nan, tick_post=t.loc[r, "post"]))
            if p in CORE + ["WBNB-USDT-100"]:
                key[f"level|{p}|{r}"] = {"kline_pre": None if r not in k.index else float(k.loc[r, "pre"]), "tick_pre": float(t.loc[r, "pre"]),
                                         "kline_post": None if r not in k.index else float(k.loc[r, "post"]), "tick_post": float(t.loc[r, "post"])}
    d = pd.DataFrame(recs); d.to_csv(os.path.join(out, "levels_kline_vs_tick.csv"), index=False)
    keep = ["arb_swaps_share", "arb_swaps_per_hour", "median_arb_size_quote", "arb_loss_bps_of_volume", "lp_net_bps_of_volume",
            "arb_loss_over_fee", "arb_loss_per_hour_quote", "ref_kline_vs_tick_mean_abs_bps", "ref_kline_vs_tick_rms_bps", "cex_vol_1s_bps"]
    names = {"arb_swaps_share": "套利 swap 占比", "arb_swaps_per_hour": "套利笔数/小时", "median_arb_size_quote": "套利中位规模 (USDT)",
             "arb_loss_bps_of_volume": "LP 损失 (bp of volume)", "lp_net_bps_of_volume": "LP 净收益 (bp of volume)",
             "arb_loss_over_fee": "LP 损失 / 手续费", "arb_loss_per_hour_quote": "LP 损失/小时 (USDT)",
             "ref_kline_vs_tick_mean_abs_bps": "参考价差 K线 vs tick，均值|gap| (bp)", "ref_kline_vs_tick_rms_bps": "参考价差 RMS (bp)",
             "cex_vol_1s_bps": "σ（1 s，bp）"}
    s = d[d.metric.isin(keep) & d.pool.isin(CORE + ["WBNB-USDT-100"])].copy(); s["指标"] = s.metric.map(names)
    s = s[["pool", "指标", "kline_pre", "tick_pre", "kline_post", "tick_post"]].rename(columns={"pool": "池", "kline_pre": "K线 pre", "tick_pre": "tick pre", "kline_post": "K线 post", "tick_post": "tick post"})
    open(os.path.join(out, "tableD_levels.md"), "w").write(s.to_markdown(index=False, floatfmt=".3g"))
    return d


def table_e(P, key, out):
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
    open(os.path.join(out, "tableE_onebp.md"), "w").write(t.to_markdown(index=False))
    return t


def fig_wedge(P, cfg, out, fork):
    m = merged(P, 30); m = m[m.pool.isin(CORE)]
    m["date"] = m["hour"].dt.floor("D")
    g = m.groupby("date").agg(w=("w_overshoot_strict_bps", "mean"), gap=("ref_gap_bps", "mean"), sig=("sigma_ps", "mean")).reset_index()
    fk = pd.Timestamp(cfg["fork"], tz="UTC")
    g["t"] = (g["date"] - fk).dt.total_seconds() / 86400
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    for a, col, ttl, c in ((ax[0], "w", f"{fork}：log(越界幅度 tick / K线)，核心 3 池日均", C_T),
                           (ax[1], "gap", "参考价差 |K线/tick − 1|（bp），日均", C_K),
                           (ax[2], "sig", "σ（分钟实现波动率，日均）", INK)):
        a.plot(g["t"], g[col], color=c, lw=1.4); a.axvline(0, color="#999", lw=1, ls="--")
        a.set_title(ttl, fontsize=10); a.set_xlabel("距分叉天数"); a.grid(color=GRID, lw=0.6)
        for s in ("top", "right"): a.spines[s].set_visible(False)
    ax[0].axhline(0, color="#bbb", lw=0.8)
    fig.tight_layout(); fig.savefig(os.path.join(out, "fig_wedge.png"), dpi=160); plt.close(fig)


def fig_event(P, cfg, out, fork):
    fk = pd.Timestamp(cfg["fork"], tz="UTC")
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    for j, (lab, y) in enumerate((("log 越界幅度（严格）", "overshoot_strict_bps"), ("log 套利者利润", "arb_profit"), ("log LP 损失（总）", "arb_loss"))):
        for ref, c in (("kline", C_K), ("tick", C_T)):
            d = P[(ref, 30)]; d = d[d.pool.isin(CORE)]
            d = clean(d, y, CONTROLS[1][1]); d = d[d.volume > 0]
            pre = d[d.post == 0]
            mod = smf.ols(f"np.log({y}) ~ np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + C(hod) + C(pool)", data=pre).fit()
            d = d.copy(); d["res"] = np.log(d[y]) - mod.predict(d); d["date"] = d["hour"].dt.floor("D")
            g = d.groupby("date")["res"].mean().reset_index(); g["t"] = (g["date"] - fk).dt.total_seconds() / 86400
            ax[j].plot(g["t"], g["res"], color=c, lw=1.3, label=f"{'1 s K 线' if ref == 'kline' else 'tick'} 参考价")
            ax[j].hlines(g[g.t >= 0]["res"].mean(), 0, 30, color=c, lw=1, ls=":")
        ax[j].axvline(0, color="#999", lw=1, ls="--"); ax[j].axhline(0, color="#bbb", lw=0.8)
        ax[j].set_title(f"{fork}：{lab}（分叉前拟合的残差，日均）", fontsize=10); ax[j].set_xlabel("距分叉天数"); ax[j].grid(color=GRID, lw=0.6)
        for s in ("top", "right"): ax[j].spines[s].set_visible(False)
    ax[0].legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(out, "fig_event_study_kline_vs_tick.png"), dpi=160); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fork", required=True, choices=list(CFG)); a = ap.parse_args()
    cfg = CFG[a.fork]; out = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.fork); os.makedirs(out, exist_ok=True)
    LNDT = np.log(cfg["dt"][1] / cfg["dt"][0])
    setup_fonts(); P = load(cfg); key = {"fork": a.fork, "dt": cfg["dt"], "theory": 0.5 * LNDT, "lndt": LNDT}
    tA = table_a(P, key, out, LNDT); table_b(P, key, out); tC, tF = table_c(P, key, out); table_d(cfg, key, out); table_e(P, key, out)
    fig_wedge(P, cfg, out, a.fork); fig_event(P, cfg, out, a.fork)
    json.dump(key, open(os.path.join(out, "key_numbers.json"), "w"), indent=1, ensure_ascii=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 300)
    show = tA[[c for c in tA.columns if not c.startswith("_")]]
    print(show[show["被解释变量"].isin(["log 越界幅度（严格）", "log 套利者利润", "log LP 损失（总）", "log 套利笔数"])].to_string())
    print(); print(tC.to_string()); print(); print(tF.to_string())


if __name__ == "__main__":
    main()
