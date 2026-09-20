"""Core-pool (5 bp) pooled analysis of one fork's hourly panels, identical code for Maxwell and Fermi.

    python core_analysis.py --bundle <dir with analysis/hourly_panel.parquet and analysis_14d/hourly_panel.parquet> \
                            --label Fermi --out <outdir>

Outputs (all in --out):
  core_pooled.md/.csv     windows ±30/±14/±7 d × 4 control sets × 5 outcomes, 3 core pools pooled (pool FE)
  rd_jump.md/.csv         RD-style jump at the fork with separate pre/post slopes (+ pre-trend test), both windows
  placebo_core.md         fake fork inside the pre period, pooled core, all control sets, both windows
  heterogeneity.md        post × log σ, post × high-σ hour, post × Asia hours (±14 d, preferred controls)
  sigma_path.md/.csv      daily σ / volume / liquidity of the core pools relative to the fork; post/pre ratios
  fig_event_study_core.png  daily means of residualised outcomes around the fork (±30 d)
  onebp.md                the 1 bp WBNB-USDT-100 pool on its own (same specs), for the dose-response discussion
"""
from __future__ import annotations
import argparse, os, json
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

C_PRE, C_POST, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e6e3"
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
OUTCOMES = [("log 越界幅度（严格）", "overshoot_strict_bps"), ("log 套利者利润", "arb_profit"),
            ("log 单笔 LP 损失", "loss_per_arb"), ("log LP 损失（总）", "arb_loss"), ("log 套利笔数", "n_arb")]
CONTROLS = [("σ", ""), ("σ+L+vol", " + np.log(liq_mean) + np.log(volume)"),
            ("σ+L+vol+趋势", " + np.log(liq_mean) + np.log(volume) + t_days"),
            ("σ+L+vol+池别趋势", " + np.log(liq_mean) + np.log(volume) + t_days:C(pool)")]
PREF = CONTROLS[2][1]


def setup_fonts():
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK" in f or "NotoSerifCJK" in f:
            font_manager.fontManager.addfont(f)
    for name in ("Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans SC", "WenQuanYi Zen Hei", "DejaVu Sans"):
        if any(name == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def clean(d: pd.DataFrame, y: str, extra: str) -> pd.DataFrame:
    d = d[(d[y] > 0) & (d["sigma_ps"] > 0)].replace([np.inf, -np.inf], np.nan).dropna(subset=["sigma_ps", y])
    if "liq_mean" in extra or "liq_mean" in d:
        d = d[d["liq_mean"] > 0]
    if "volume" in extra:
        d = d[d["volume"] > 0]
    return d


def fit(d: pd.DataFrame, y: str, extra: str, var: str = "post", rhs_extra: str = ""):
    d = clean(d, y, extra)
    f = f"np.log({y}) ~ {var} + np.log(sigma_ps) + C(hod) + C(pool)" + extra + rhs_extra
    m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    return m, len(d)


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def cell(m, var):
    return f"{m.params[var]:+.3f}{star(m.pvalues[var])} ({m.bse[var]:.3f})"


def window(p: pd.DataFrame, days: float) -> pd.DataFrame:
    return p[(p.t_days >= -days) & (p.t_days < days)]


def core_pooled(p30, p14, out):
    rows = []
    for wname, d in (("±30 d", p30), ("±14 d", p14), ("±7 d", window(p14, 7))):
        d = d[d.pool.isin(CORE)]
        for cname, extra in CONTROLS:
            r = {"窗口": wname, "控制": cname}
            n = None
            for lab, y in OUTCOMES:
                m, n_ = fit(d, y, extra)
                r[lab] = cell(m, "post")
                if y == "overshoot_strict_bps":
                    n = n_
                    r["_b_over"], r["_se_over"] = m.params["post"], m.bse["post"]
                if y == "arb_profit":
                    r["_b_prof"], r["_se_prof"] = m.params["post"], m.bse["post"]
                if y == "arb_loss":
                    r["_b_loss"], r["_se_loss"] = m.params["post"], m.bse["post"]
            r["n"] = n
            rows.append(r)
    t = pd.DataFrame(rows)
    show = t[[c for c in t.columns if not c.startswith("_")]]
    show.to_csv(os.path.join(out, "core_pooled.csv"), index=False)
    open(os.path.join(out, "core_pooled.md"), "w").write(show.to_markdown(index=False))
    t.to_csv(os.path.join(out, "core_pooled_raw.csv"), index=False)
    return t


def rd_jump(p30, p14, out):
    """log y ~ post + t + post:t + controls (σ, L, vol, hod, pool): jump at t=0 with separate slopes;
    pre-trend = slope of t before the fork (per day)."""
    rows = []
    for wname, d in (("±30 d", p30), ("±14 d", p14)):
        d = d[d.pool.isin(CORE)]
        for lab, y in OUTCOMES[:4]:
            m, n = fit(d, y, CONTROLS[1][1], rhs_extra=" + t_days + post:t_days")
            rows.append({"窗口": wname, "被解释变量": lab, "跳跃（post）": cell(m, "post"),
                         "分叉前斜率（/天）": cell(m, "t_days"), "斜率变化": cell(m, "post:t_days"), "n": n,
                         "_b": m.params["post"], "_se": m.bse["post"]})
    t = pd.DataFrame(rows)
    t[[c for c in t.columns if not c.startswith("_")]].to_csv(os.path.join(out, "rd_jump.csv"), index=False)
    open(os.path.join(out, "rd_jump.md"), "w").write(t[[c for c in t.columns if not c.startswith("_")]].to_markdown(index=False))
    return t


def placebo_core(p30, p14, fork_ts, out):
    txt = ""
    rows = []
    for wname, d in (("±30 d", p30), ("±14 d", p14)):
        pre = d[(d.post == 0) & d.pool.isin(CORE)].copy()
        mid = pre["hour"].min() + (fork_ts - pre["hour"].min()) / 2
        pre["fake"] = (pre["hour"] >= mid).astype(int)
        for cname, extra in CONTROLS[:3]:
            extra_ = extra.replace("t_days", "t_days")
            r = {"窗口": wname, "假分叉": f"{mid:%Y-%m-%d %H:%M}", "控制": cname}
            for lab, y in OUTCOMES[:4]:
                m, n = fit(pre, y, extra_, var="fake")
                r[lab] = cell(m, "fake")
            rows.append(r)
    t = pd.DataFrame(rows)
    open(os.path.join(out, "placebo_core.md"), "w").write(t.to_markdown(index=False))
    return t


def heterogeneity(p14, out):
    d = p14[p14.pool.isin(CORE)].copy()
    d = clean(d, "overshoot_strict_bps", PREF)
    d["lsig"] = np.log(d["sigma_ps"]) - np.log(d["sigma_ps"]).mean()
    d["hi_sig"] = (d["sigma_ps"] > d.groupby("pool")["sigma_ps"].transform("median")).astype(int)
    d["asia"] = d["hod"].between(1, 8).astype(int)
    rows = []
    for lab, rhs in (("post × log σ（去均值）", "post + post:lsig + lsig"),
                     ("post × 高波动小时", "post + post:hi_sig + hi_sig"),
                     ("post × 亚洲时段(01–08 UTC)", "post + post:asia")):
        f = f"np.log(overshoot_strict_bps) ~ {rhs} + np.log(sigma_ps) + C(hod) + C(pool)" + PREF
        m = smf.ols(f, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
        inter = [k for k in m.params.index if k.startswith("post:")][0]
        rows.append({"交互项": lab, "post": cell(m, "post"), "交互系数": cell(m, inter), "p": f"{m.pvalues[inter]:.2f}", "n": int(m.nobs)})
    t = pd.DataFrame(rows)
    open(os.path.join(out, "heterogeneity.md"), "w").write(t.to_markdown(index=False))
    return t


def sigma_path(p30, out):
    d = p30[p30.pool.isin(CORE)].copy()
    d["dayrel"] = np.floor(d["t_days"]).astype(int)
    g = d.groupby(["pool", "dayrel"]).agg(rv=("rv", "sum"), hours=("rv", "size"), volume=("volume", "sum"),
                                          liq=("liq_mean", "mean"), n_arb=("n_arb", "sum"),
                                          over=("overshoot_strict_bps", "mean"), profit=("arb_profit", "sum"),
                                          loss=("arb_loss", "sum")).reset_index()
    g["sigma_bps"] = 1e4 * np.sqrt(g["rv"] / (g["hours"] * 3600))
    g.to_csv(os.path.join(out, "sigma_path_daily.csv"), index=False)
    rows = []
    for w in (7, 14, 30):
        for pool in CORE:
            s = d[d.pool == pool]
            pre, post = s[(s.t_days >= -w) & (s.t_days < 0)], s[(s.t_days >= 0) & (s.t_days < w)]
            sp = np.sqrt(pre["rv"].sum() / (len(pre) * 3600)); sq = np.sqrt(post["rv"].sum() / (len(post) * 3600))
            rows.append({"窗口": f"±{w} d", "池": pool, "σ_pre(bp/√s)": 1e4 * sp, "σ_post(bp/√s)": 1e4 * sq, "σ 比": sq / sp,
                         "成交额比": post["volume"].sum() / pre["volume"].sum(),
                         "流动性比": post["liq_mean"].mean() / pre["liq_mean"].mean(),
                         "套利笔数比": post["n_arb"].sum() / pre["n_arb"].sum(),
                         "严格越界均值比": post["overshoot_strict_bps"].mean() / pre["overshoot_strict_bps"].mean(),
                         "利润比": post["arb_profit"].sum() / pre["arb_profit"].sum(),
                         "LP 损失比": post["arb_loss"].sum() / pre["arb_loss"].sum()})
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(out, "sigma_path.csv"), index=False)
    open(os.path.join(out, "sigma_path.md"), "w").write(t.to_markdown(index=False, floatfmt=".3f"))
    return t, g


def event_study_fig(p30, label, theory, out):
    d = p30[p30.pool.isin(CORE)].copy()
    panels = [("套利者出手时的越界幅度（严格）", "overshoot_strict_bps"), ("套利者利润", "arb_profit"), ("LP 逆向选择损失（总）", "arb_loss")]
    fig, axes = plt.subplots(3, 1, figsize=(8.5, 9), sharex=True)
    res_stats = {}
    for ax, (title, y) in zip(axes, panels):
        dd = clean(d, y, CONTROLS[1][1])
        f = f"np.log({y}) ~ np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + C(hod) + C(pool)"
        m = smf.ols(f, data=dd).fit()
        dd = dd.assign(res=m.resid, dayrel=np.floor(dd["t_days"]).astype(int))
        daily = dd.groupby("dayrel")["res"].mean()
        pre, post = daily[daily.index < 0], daily[daily.index >= 0]
        ax.axhline(0, color=GRID, lw=1)
        ax.plot(pre.index + 0.5, pre.values, "o-", color=C_PRE, ms=3.5, lw=1)
        ax.plot(post.index + 0.5, post.values, "o-", color=C_POST, ms=3.5, lw=1)
        ax.axhline(pre.mean(), xmin=0, xmax=0.5, color=C_PRE, lw=1, ls="--")
        ax.axhline(post.mean(), xmin=0.5, xmax=1, color=C_POST, lw=1, ls="--")
        ax.axvline(0, color=INK2, lw=1, ls=":")
        diff = post.mean() - pre.mean()
        res_stats[y] = {"pre_mean": pre.mean(), "post_mean": post.mean(), "diff": diff}
        note = f"前后均值差 {diff:+.2f}"
        if y in ("overshoot_strict_bps", "arb_profit"):
            note += f"（理论 {theory:+.3f}）"
        ax.set_title(f"{title}：残差的日均值 — {note}", fontsize=10, color=INK, loc="left")
        ax.tick_params(colors=INK2, labelsize=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.spines["left"].set_color(GRID); ax.spines["bottom"].set_color(GRID)
    axes[-1].set_xlabel("相对分叉的天数", color=INK2, fontsize=9)
    fig.suptitle(f"{label}：三个 5 bp 核心池，对 log σ、log L、log 成交额、时段与池效应回归后的残差", fontsize=10, color=INK, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_event_study_core.png"), dpi=160)
    plt.close(fig)
    return res_stats


def onebp(p30, p14, out):
    rows = []
    for wname, d in (("±30 d", p30), ("±14 d", p14), ("±7 d", window(p14, 7))):
        d = d[d.pool == "WBNB-USDT-100"]
        for cname, extra in CONTROLS[:3]:
            r = {"窗口": wname, "控制": cname}
            for lab, y in OUTCOMES:
                dd = clean(d, y, extra)
                f = f"np.log({y}) ~ post + np.log(sigma_ps) + C(hod)" + extra
                m = smf.ols(f, data=dd).fit(cov_type="cluster", cov_kwds={"groups": dd["day"].astype(str)})
                r[lab] = cell(m, "post")
            rows.append(r)
    t = pd.DataFrame(rows)
    open(os.path.join(out, "onebp.md"), "w").write(t.to_markdown(index=False))
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--analysis-dir", default="analysis", help="±30 d panel directory under --bundle (analysis_agg for tick-level runs)")
    ap.add_argument("--analysis14-dir", default="analysis_14d", help="±14 d panel directory under --bundle (analysis_agg_14d for tick-level runs)")
    ap.add_argument("--summary", default="summary.json", help="summary file under --bundle (summary_agg.json for tick-level runs)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    p30 = pd.read_parquet(os.path.join(a.bundle, a.analysis_dir, "hourly_panel.parquet"))
    p14 = pd.read_parquet(os.path.join(a.bundle, a.analysis14_dir, "hourly_panel.parquet"))
    summ = json.load(open(os.path.join(a.bundle, a.summary)))
    fork_ts = pd.Timestamp(summ["fork_time_utc"])
    theory = 0.5 * np.log(summ["block_interval_after"] / summ["block_interval_before"])
    print(f"{a.label}: fork {fork_ts}, Δt {summ['block_interval_before']} → {summ['block_interval_after']} s, theory {theory:+.4f}")
    setup_fonts()
    t = core_pooled(p30, p14, a.out); print(t[[c for c in t.columns if not c.startswith('_')]].to_string())
    r = rd_jump(p30, p14, a.out); print(r[[c for c in r.columns if not c.startswith('_')]].to_string())
    print(placebo_core(p30, p14, fork_ts, a.out).to_string())
    print(heterogeneity(p14, a.out).to_string())
    s, _ = sigma_path(p30, a.out); print(s.to_string())
    print(event_study_fig(p30, a.label, theory, a.out))
    print(onebp(p30, p14, a.out).to_string())
    json.dump({"theory": theory, "fork": str(fork_ts)}, open(os.path.join(a.out, "meta.json"), "w"))


if __name__ == "__main__":
    main()
