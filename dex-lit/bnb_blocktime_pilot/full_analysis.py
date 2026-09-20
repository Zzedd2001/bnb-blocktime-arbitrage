"""Event analysis of a block-interval change from run_pilot.py output (any fork, any set of pools).

    python full_analysis.py --results full_maxwell --out full_maxwell/analysis
    python full_analysis.py --results full_fermi   --out full_fermi/analysis

`--results` is the run_pilot output directory (needs summary.json and results/<pool>/swaps_enriched.parquet,
i.e. run with --include-swaps).  Produces:
  hourly_panel.parquet, table_regimes.md, table_regressions.md, table_matched.md, table_placebo.md,
  table_exposure.md (dose-response across fee tiers / volatilities), and figures fig_*.png.

Method (see 试点报告): hourly panel per pool; post-fork dummy with hour-of-day fixed effects and the hour's
Binance realised volatility as control; SEs clustered by day.  Key outcomes are the block-time-dependent
quantities of the LVR-with-fees model — arbitrageurs' profit (∝ σ³√Δt/γ) and the overshoot beyond the fee
band at arbitrage time (∝ σ√Δt) — alongside LPs' gross adverse-selection loss and net return.
"""
from __future__ import annotations
import argparse, glob, json, os
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C_PRE, C_POST, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e6e3"


# ------------------------------------------------------------------ data
PANEL_COLS = ["block", "ts_ms", "p_cex", "dev_pre", "is_arb", "is_arb_strict", "volume_q", "fee_income", "lp_gain",
              "arb_loss", "markout_30s", "fee_rate", "liquidity", "p_cex_1s"]


def load_pool(path: str, fork_block: int) -> pd.DataFrame:
    """Whole-frame loader (small pools / tests).  hourly_panel_from_parquet streams instead."""
    import pyarrow.parquet as pq
    have = pq.read_schema(path).names
    df = pd.read_parquet(path, columns=[c for c in PANEL_COLS if c in have])
    if "liquidity" in df:
        df["liquidity"] = df["liquidity"].astype(float)
    df["t"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df["post"] = (df["block"] >= fork_block).astype(int)
    df["pool"] = os.path.basename(os.path.dirname(path))
    return df


def realised_vol(df: pd.DataFrame) -> pd.DataFrame:
    m = df.set_index("t")["p_cex"].resample("1min").last().ffill()
    return _rv_from_minutes(m)


def _rv_from_minutes(m: pd.Series) -> pd.DataFrame:
    """Hourly realised variance from a 1-minute price series (already forward-filled)."""
    r = np.log(m).diff().dropna()
    rv = (r ** 2).resample("1h").sum().rename("rv")
    out = rv.to_frame()
    out["sigma_ps"] = np.sqrt(out["rv"] / 3600.0)
    return out


def hourly_panel(df: pd.DataFrame, fork_ts: pd.Timestamp, dt_pre: float, dt_post: float) -> pd.DataFrame:
    """Whole-frame hourly panel (reference implementation; see hourly_panel_from_parquet for the streaming one)."""
    fee = float(df["fee_rate"].iloc[0])
    g = df.groupby(pd.Grouper(key="t", freq="1h"))
    arb = df[df["is_arb"]]
    ga = arb.groupby(pd.Grouper(key="t", freq="1h"))
    strict = df[df["is_arb_strict"]]
    gs = strict.groupby(pd.Grouper(key="t", freq="1h"))
    h = pd.DataFrame({
        "swaps": g.size(), "volume": g["volume_q"].sum(), "fee_income": g["fee_income"].sum(),
        "lp_gain": g["lp_gain"].sum(), "arb_loss": g["arb_loss"].sum(), "markout_30s": g["markout_30s"].sum(),
        "n_arb": ga.size(), "n_arb_strict": gs.size(), "arb_volume": ga["volume_q"].sum(),
        "arb_loss_arbs": ga["arb_loss"].sum(),
        "arb_profit": (arb["arb_loss"] - arb["fee_income"]).groupby(arb["t"].dt.floor("h")).sum()
        if len(arb) else pd.Series(dtype=float),
        "overshoot_bps": (1e4 * (arb["dev_pre"].abs() - fee)).groupby(arb["t"].dt.floor("h")).mean() if len(arb) else pd.Series(dtype=float),
        "overshoot_strict_bps": (1e4 * (strict["dev_pre"].abs() - fee)).groupby(strict["t"].dt.floor("h")).mean() if len(strict) else pd.Series(dtype=float),
        "median_arb_size": ga["volume_q"].median(),
        "mean_abs_dev_pre": g["dev_pre"].apply(lambda x: x.abs().mean()),
        "share_swaps_outside": g["dev_pre"].apply(lambda x: (x.abs() > fee).mean()),
    })
    if "liquidity" in df:
        h["liq_mean"] = g["liquidity"].mean()
    h = h.join(realised_vol(df), how="left")
    return _finish_panel(h, fee, df["pool"].iloc[0], fork_ts, dt_pre, dt_post)


def _finish_panel(h: pd.DataFrame, fee: float, pool: str, fork_ts: pd.Timestamp, dt_pre: float, dt_post: float) -> pd.DataFrame:
    for c in ("n_arb", "n_arb_strict", "arb_volume", "arb_loss_arbs", "arb_profit"):
        h[c] = h[c].fillna(0)
    h["post"] = (h.index >= fork_ts).astype(int)
    h["hod"] = h.index.hour; h["dow"] = h.index.dayofweek; h["day"] = h.index.floor("D")
    h["arb_loss_bps"] = 1e4 * h["arb_loss"] / h["volume"]
    h["lp_net_bps"] = 1e4 * h["lp_gain"] / h["volume"]
    h["loss_per_arb"] = h["arb_loss_arbs"] / h["n_arb"].replace(0, np.nan)
    h["dt"] = np.where(h["post"] == 1, dt_post, dt_pre)
    h["fee"] = fee
    h["pool"] = pool
    h["t_days"] = (h.index - fork_ts).total_seconds() / 86400.0        # days since the fork (linear trend control)
    return h.reset_index().rename(columns={"t": "hour", "index": "hour"})


def hourly_panel_from_parquet(path: str, fork_block: int, fork_ts: pd.Timestamp, dt_pre: float, dt_post: float,
                              batch_rows: int = 1_000_000) -> pd.DataFrame:
    """Streaming hourly panel: reads swaps_enriched.parquet in batches and keeps only per-hour sums/counts,
    per-hour arbitrage sizes (for medians) and the last Binance price of every minute (for realised volatility).
    Produces the same panel as hourly_panel(load_pool(...)) with memory bounded by one batch."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    cols = [c for c in PANEL_COLS if c in pf.schema_arrow.names and c != "block"]
    sums = {}                      # hour -> dict of sums
    sizes = {}                     # hour -> list of arrays of arb sizes
    minute_last = []               # Series per batch: minute -> last p_cex
    fee = None
    t_min = t_max = None
    for batch in pf.iter_batches(batch_size=batch_rows, columns=cols):
        d = batch.to_pandas()
        if len(d) == 0:
            continue
        if fee is None:
            fee = float(d["fee_rate"].iloc[0])
        ts = d["ts_ms"].to_numpy(dtype=np.int64)
        t_min = ts.min() if t_min is None else min(t_min, ts.min()); t_max = ts.max() if t_max is None else max(t_max, ts.max())
        hour = ts // 3_600_000 * 3_600_000            # hour start in ms (integer keys: fast, tz-unambiguous)
        absdev = d["dev_pre"].abs()
        arb, strict = d["is_arb"].to_numpy(), d["is_arb_strict"].to_numpy()
        liq = d["liquidity"].astype(float).to_numpy() if "liquidity" in d else np.zeros(len(d))
        base = pd.DataFrame({
            "swaps": 1.0, "volume": d["volume_q"], "fee_income": d["fee_income"], "lp_gain": d["lp_gain"], "liq_sum": liq,
            "arb_loss": d["arb_loss"], "markout_30s": d["markout_30s"],
            "n_arb": arb.astype(float), "n_arb_strict": strict.astype(float),
            "arb_volume": np.where(arb, d["volume_q"], 0.0), "arb_loss_arbs": np.where(arb, d["arb_loss"], 0.0),
            "arb_profit": np.where(arb, d["arb_loss"] - d["fee_income"], 0.0),
            "overshoot_sum": np.where(arb, 1e4 * (absdev - fee), 0.0),
            "overshoot_strict_sum": np.where(strict, 1e4 * (absdev - fee), 0.0),
            "absdev_sum": absdev, "outside": (absdev > fee).astype(float),
            "refgap_sum": (np.abs(d["p_cex_1s"].to_numpy() / d["p_cex"].to_numpy() - 1.0) if "p_cex_1s" in d else np.zeros(len(d))),
        })
        s = base.groupby(hour).sum()
        for hr, row in zip(s.index, s.to_numpy()):
            acc = sums.get(int(hr))
            sums[int(hr)] = row if acc is None else acc + row
        cols_order = list(s.columns)
        if arb.any():
            for hr, grp in pd.Series(d["volume_q"].to_numpy()[arb]).groupby(hour[arb]):
                sizes.setdefault(int(hr), []).append(grp.to_numpy())
        minute_last.append(d["p_cex"].groupby(ts // 60_000 * 60_000).last())
        del d, base, s
    if not sums:
        raise ValueError(f"no swaps in {path}")
    S = pd.DataFrame.from_dict(sums, orient="index", columns=cols_order).sort_index()
    S.index = pd.to_datetime(S.index, unit="ms", utc=True)
    idx = pd.date_range(pd.Timestamp(int(t_min), unit="ms", tz="UTC").floor("h"), pd.Timestamp(int(t_max), unit="ms", tz="UTC").floor("h"),
                        freq="1h", tz="UTC")
    S = S.reindex(idx, fill_value=0.0)
    med = pd.Series({pd.Timestamp(hr, unit="ms", tz="UTC"): float(np.median(np.concatenate(v))) for hr, v in sizes.items()}, dtype=float)
    h = pd.DataFrame(index=idx)
    for c in ("volume", "fee_income", "lp_gain", "arb_loss", "markout_30s", "n_arb", "n_arb_strict", "arb_volume", "arb_loss_arbs", "arb_profit"):
        h[c] = S[c]
    h["swaps"] = S["swaps"].astype(int)
    h["n_arb"] = S["n_arb"].astype(int); h["n_arb_strict"] = S["n_arb_strict"].astype(int)
    h["overshoot_bps"] = S["overshoot_sum"] / S["n_arb"].replace(0, np.nan)
    h["overshoot_strict_bps"] = S["overshoot_strict_sum"] / S["n_arb_strict"].replace(0, np.nan)
    h["median_arb_size"] = med.reindex(idx)
    h["mean_abs_dev_pre"] = S["absdev_sum"] / S["swaps"].replace(0, np.nan)
    h["share_swaps_outside"] = S["outside"] / S["swaps"].replace(0, np.nan)
    keep = ["swaps", "volume", "fee_income", "lp_gain", "arb_loss", "markout_30s", "n_arb", "n_arb_strict", "arb_volume",
            "arb_loss_arbs", "arb_profit", "overshoot_bps", "overshoot_strict_bps", "median_arb_size", "mean_abs_dev_pre",
            "share_swaps_outside"]
    if "liquidity" in cols:
        h["liq_mean"] = S["liq_sum"] / S["swaps"].replace(0, np.nan)
        keep.append("liq_mean")
    if "p_cex_1s" in cols:                       # tick-level reference run: mean |1s-kline ref / tick ref − 1| per hour
        h["ref_gap_bps"] = 1e4 * S["refgap_sum"] / S["swaps"].replace(0, np.nan)
        keep.append("ref_gap_bps")
    h = h[keep]
    m = pd.concat(minute_last).groupby(level=0).last()
    m.index = pd.to_datetime(m.index, unit="ms", utc=True)
    m = m.resample("1min").last().ffill()
    h = h.join(_rv_from_minutes(m), how="left")
    return _finish_panel(h, fee, os.path.basename(os.path.dirname(path)), fork_ts, dt_pre, dt_post)


# ------------------------------------------------------------------ tables
def regime_table(h: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    fee = float(h["fee"].iloc[0])
    for name, sub in (("pre", h[h.post == 0]), ("post", h[h.post == 1])):
        hrs, vol, loss = len(sub), sub["volume"].sum(), sub["arb_loss"].sum()
        sig = np.sqrt(sub["rv"].sum() / max(hrs * 3600, 1))
        n_arb = sub["n_arb"].sum()
        rows[name] = {
            "hours": hrs, "swaps": int(sub["swaps"].sum()), "volume_per_hour": vol / max(hrs, 1),
            "arbs_per_hour": n_arb / max(hrs, 1), "median_arb_size": np.nanmedian(sub["median_arb_size"]) if sub["median_arb_size"].notna().any() else np.nan,
            "arb_loss_per_hour": loss / max(hrs, 1), "arb_loss_bps": 1e4 * loss / vol if vol else np.nan,
            "arb_loss_over_fee": loss / sub["fee_income"].sum() if sub["fee_income"].sum() else np.nan,
            "lp_net_bps": 1e4 * sub["lp_gain"].sum() / vol if vol else np.nan,
            "arb_profit_per_hour": sub["arb_profit"].sum() / max(hrs, 1),
            "overshoot_bps": np.average(sub["overshoot_bps"].fillna(0), weights=sub["n_arb"]) if n_arb else np.nan,
            "overshoot_strict_bps": np.average(sub["overshoot_strict_bps"].fillna(0), weights=sub["n_arb_strict"]) if sub["n_arb_strict"].sum() else np.nan,
            "sigma_ps_bps": 1e4 * sig, "exposure_sigma_sqrt_dt_over_gamma": sig * np.sqrt(sub["dt"].iloc[0]) / fee if len(sub) else np.nan,
            "share_swaps_outside_band": np.average(sub["share_swaps_outside"], weights=sub["swaps"]) if sub["swaps"].sum() else np.nan,
            "arb_profit_rate_over_sigma3": (sub["arb_profit"].sum() / max(hrs, 1)) / sig ** 3 if sig else np.nan,
            "loss_rate_over_sigma2": (loss / max(hrs, 1)) / sig ** 2 if sig else np.nan,
        }
    t = pd.DataFrame(rows); t["post/pre"] = t["post"] / t["pre"]
    return t


THEORY = {"label": "[理论 −0.35]"}          # replaced by set_theory() once the fork's block intervals are known


def set_theory(dt_pre: float, dt_post: float) -> float:
    """Predicted log change of overshoot / arbitrageur profit (both ∝ √Δt): ½·ln(Δt_post/Δt_pre).
    Halving (Maxwell, Lorentz) → −0.347; Fermi 0.75 → 0.45 s → −0.255."""
    th = 0.5 * np.log(dt_post / dt_pre)
    THEORY["label"] = f"[理论 {th:+.3f}]".replace("+", "+").replace("-", "−")
    return th


def _lab(label: str) -> str:
    return label.replace("[理论 −0.35]", THEORY["label"])


SPECS = [
    ("log 越界幅度（严格套利）[理论 −0.35]", "np.log(overshoot_strict_bps) ~ post + np.log(sigma_ps) + C(hod)", "overshoot_strict_bps > 0"),
    ("log 越界幅度（全部套利）[理论 −0.35]", "np.log(overshoot_bps) ~ post + np.log(sigma_ps) + C(hod)", "overshoot_bps > 0"),
    ("log 套利者利润 [理论 −0.35]", "np.log(arb_profit) ~ post + np.log(sigma_ps) + C(hod)", "arb_profit > 0"),
    ("log 每小时套利笔数", "np.log(n_arb) ~ post + np.log(sigma_ps) + C(hod)", "n_arb > 0"),
    ("log 单笔套利 LP 损失", "np.log(loss_per_arb) ~ post + np.log(sigma_ps) + C(hod)", "loss_per_arb > 0"),
    ("log LP 逆向选择损失（总）", "np.log(arb_loss) ~ post + np.log(sigma_ps) + C(hod)", "arb_loss > 0"),
    ("log LP 逆向选择损失（总，不控制 σ）", "np.log(arb_loss) ~ post + C(hod)", "arb_loss > 0"),
    ("LP 逆向选择损失 / 成交额（bps）", "arb_loss_bps ~ post + np.log(sigma_ps) + C(hod)", "volume > 0"),
    ("LP 净收益 / 成交额（bps）", "lp_net_bps ~ post + np.log(sigma_ps) + C(hod)", "volume > 0"),
    ("log 成交额", "np.log(volume) ~ post + np.log(sigma_ps) + C(hod)", "volume > 0"),
    ("交易时平均 |偏离|（bps）", "I(1e4*mean_abs_dev_pre) ~ post + np.log(sigma_ps) + C(hod)", "swaps > 0"),
    ("偏离超出费率带的交易占比", "share_swaps_outside ~ post + np.log(sigma_ps) + C(hod)", "swaps > 0"),
]


def fit_post(d: pd.DataFrame, f: str, cond: str, var: str = "post", pooled: bool = False, extra: str = ""):
    d = d.query(cond).replace([np.inf, -np.inf], np.nan).dropna(subset=["sigma_ps"])
    d = d[d["sigma_ps"] > 0]
    if "liq_mean" in extra:
        d = d[d["liq_mean"] > 0] if "liq_mean" in d else d.iloc[0:0]
    if "volume" in extra:
        d = d[d["volume"] > 0]
    if len(d) < 30 or d[var].nunique() < 2:
        return None
    ff = f + extra + (" + C(pool)" if pooled else "")
    m = smf.ols(ff, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"].astype(str)})
    b, se, p = m.params[var], m.bse[var], m.pvalues[var]
    star = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
    el = m.params.get("np.log(sigma_ps)", np.nan)
    return f"{b:+.3f}{star} ({se:.3f})" + ("" if np.isnan(el) else f" [σ {el:.2f}]"), len(d)


CONTROL_SETS = [
    ("基准：控制 log σ + 时段 FE", ""),
    ("加流动性与成交额：+ log L + log 成交额", " + np.log(liq_mean) + np.log(volume)"),
    ("再加线性时间趋势：+ t（天）", " + np.log(liq_mean) + np.log(volume) + t_days"),
]


def regressions(panel: pd.DataFrame, pools: list[str], var: str = "post", extra: str = "") -> str:
    head = "| 被解释变量 | " + " | ".join(pools) + " | 合并（池 FE） |\n|---|" + "---|" * (len(pools) + 1) + "\n"
    out = head
    for label, f, cond in SPECS:
        lhs = f.split("~")[0].strip()
        if extra and lhs in extra:                 # the outcome is itself a control in this specification
            continue
        cells = []
        for pool in pools + ["POOLED"]:
            d = panel if pool == "POOLED" else panel[panel.pool == pool]
            r = fit_post(d, f.replace("post", var), cond, var, pooled=(pool == "POOLED"), extra=extra)
            cells.append("—" if r is None else r[0])
        out += f"| {_lab(label)} | " + " | ".join(cells) + " |\n"
    out += "\n系数为 " + var + "（括号内按天聚类标准误；对数被解释变量的系数≈比例变化；[σ x] 为 log 实现波动率的系数）。* p<0.1, ** p<0.05, *** p<0.01。\n"
    return out


def matched(panel: pd.DataFrame, pools: list[str], days: int) -> str:
    out = "| 池 | 指标 | 配对数 | 中位数比（post/pre） | 均值 log 比 | p 值 |\n|---|---|---|---|---|---|\n"
    lag = pd.Timedelta(days=7 * max(1, round(days / 7)))
    for pool in pools:
        d = panel[panel.pool == pool].set_index("hour")
        pre, post = d[d.post == 0], d[d.post == 1].copy()
        post.index = post.index - lag
        j = pre.join(post, lsuffix="_pre", rsuffix="_post", how="inner")
        for metric, lab in (("arb_profit", "套利者利润"), ("overshoot_strict_bps", "越界幅度（严格）"), ("arb_loss", "LP 损失"),
                            ("n_arb", "套利笔数"), ("sigma_ps", "σ")):
            a, b = j[f"{metric}_pre"], j[f"{metric}_post"]
            ok = (a > 0) & (b > 0)
            if ok.sum() < 20:
                continue
            lr = np.log(b[ok] / a[ok])
            out += f"| {pool} | {lab} | {ok.sum()} | {np.exp(lr.median()):.3f} | {lr.mean():+.3f} | {stats.ttest_1samp(lr, 0).pvalue:.3f} |\n"
        a, b, sa, sb = j["arb_loss_pre"], j["arb_loss_post"], j["sigma_ps_pre"], j["sigma_ps_post"]
        ok = (a > 0) & (b > 0) & (sa > 0) & (sb > 0)
        if ok.sum() >= 20:
            adj = (np.log(b / a) - 2 * np.log(sb / sa))[ok]
            out += f"| {pool} | LP 损失，扣除 2·log(σ 比) | {ok.sum()} | {np.exp(adj.median()):.3f} | {adj.mean():+.3f} | {stats.ttest_1samp(adj, 0).pvalue:.3f} |\n"
    out += f"\n配对：同一星期几、同一小时，相隔 {lag.days} 天（分叉前 vs 分叉后）。\n"
    return out


def placebo(panel: pd.DataFrame, pools: list[str], fork_ts: pd.Timestamp) -> str:
    pre = panel[panel.post == 0].copy()
    mid = pre["hour"].min() + (fork_ts - pre["hour"].min()) / 2
    pre["fake"] = (pre["hour"] >= mid).astype(int)
    out = f"| 被解释变量（仅分叉前，假分叉 {mid:%Y-%m-%d %H:%M} UTC） | " + " | ".join(pools) + " | 合并 |\n|---|" + "---|" * (len(pools) + 1) + "\n"
    for label, f, cond in SPECS[:3] + [SPECS[5]]:
        cells = []
        for pool in pools + ["POOLED"]:
            d = pre if pool == "POOLED" else pre[pre.pool == pool]
            r = fit_post(d, f.replace("post", "fake"), cond, "fake", pooled=(pool == "POOLED"))
            cells.append("—" if r is None else r[0])
        out += f"| {_lab(label)} | " + " | ".join(cells) + " |\n"
    return out


def exposure_table(panel: pd.DataFrame, pools: list[str]) -> str:
    """Dose-response: per-pool post effects on the key outcomes against pre-fork exposure sigma*sqrt(dt)/gamma."""
    rows = []
    for pool in pools:
        d = panel[panel.pool == pool]
        pre = d[d.post == 0]
        sig = np.sqrt(pre["rv"].sum() / max(len(pre) * 3600, 1))
        fee = float(d["fee"].iloc[0])
        e = sig * np.sqrt(pre["dt"].iloc[0]) / fee if len(pre) else np.nan
        cells = {"池": pool, "费率(bps)": 1e4 * fee, "σ_pre(bps/√s)": 1e4 * sig, "暴露度 σ√Δt/γ": e,
                 "套利占交易比": d["n_arb"].sum() / max(d["swaps"].sum(), 1)}
        for label, f, cond in SPECS[:3] + [SPECS[5], SPECS[8]]:
            r = fit_post(d, f, cond)
            cells[_lab(label)] = "—" if r is None else r[0]
        rows.append(cells)
    t = pd.DataFrame(rows).sort_values("暴露度 σ√Δt/γ", ascending=False)
    return t.to_markdown(index=False, floatfmt=".3g")


# ------------------------------------------------------------------ figures
def setup_fonts():
    from matplotlib import font_manager
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK" in f or "PingFang" in f or "Hiragino" in f:
            try:
                font_manager.fontManager.addfont(f)
            except Exception:  # noqa
                pass
    fams = [f.name for f in font_manager.fontManager.ttflist]
    pref = [n for n in ("Noto Sans CJK JP", "Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB", "Arial Unicode MS") if n in fams]
    plt.rcParams.update({"font.family": pref + ["DejaVu Sans"], "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                         "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                         "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "white"})


def scatter_fig(panel, pools, ycol, ylabel, fname, out):
    n = len(pools)
    fig, axes = plt.subplots(1, n, figsize=(4.3 * n, 4), squeeze=False)
    for ax, pool in zip(axes[0], pools):
        d = panel[(panel.pool == pool) & (panel[ycol] > 0) & (panel.sigma_ps > 0)]
        for p, c, lab in ((0, C_PRE, "分叉前"), (1, C_POST, "分叉后")):
            s_ = d[d.post == p]
            if len(s_) < 5:
                continue
            ax.scatter(1e4 * s_.sigma_ps, s_[ycol], s=10, alpha=0.5, color=c, label=lab, edgecolors="none")
            b = np.polyfit(np.log(s_.sigma_ps), np.log(s_[ycol]), 1)
            xs = np.linspace(np.log(s_.sigma_ps.min()), np.log(s_.sigma_ps.max()), 50)
            ax.plot(1e4 * np.exp(xs), np.exp(b[1] + b[0] * xs), color=c, lw=2)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("小时实现波动率 σ (bps/√s)"); ax.set_ylabel(ylabel)
        ax.set_title(pool, loc="left", fontsize=10, color=INK)
    axes[0][0].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(out, fname), dpi=150); plt.close(fig)


def daily_fig(panel, pools, fork_ts, out):
    fig, axes = plt.subplots(len(pools), 2, figsize=(11, 2.6 * len(pools)), sharex=True, squeeze=False)
    for i, pool in enumerate(pools):
        d = panel[panel.pool == pool].groupby("day").agg(profit=("arb_profit", "sum"), loss=("arb_loss", "sum"), vol=("volume", "sum"),
                                                          rv=("rv", "sum"), n=("hour", "size"))
        d = d[d.n >= 20]
        d["profit_over_sigma3"] = d.profit / np.sqrt(d.rv / 86400) ** 3 / 1e12
        d["sigma"] = 1e4 * np.sqrt(d.rv / 86400)
        for j, (col, lab) in enumerate((("profit_over_sigma3", "套利者利润 / σ³（波动率归一化，任意单位）"), ("sigma", "Binance 实现波动率 σ (bps/√s)"))):
            ax = axes[i, j]
            pre, post = d[d.index < fork_ts.floor("D")], d[d.index >= fork_ts.floor("D")]
            ax.plot(pre.index, pre[col], marker="o", ms=3, lw=1.5, color=C_PRE, label="分叉前")
            ax.plot(post.index, post[col], marker="o", ms=3, lw=1.5, color=C_POST, label="分叉后")
            ax.axvline(fork_ts, color=INK2, lw=1, ls="--"); ax.set_title(f"{pool}: {lab}", fontsize=9, color=INK, loc="left")
            if i == 0 and j == 0:
                ax.legend(frameon=False, fontsize=8)
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(os.path.join(out, "fig_daily.png"), dpi=150); plt.close(fig)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="run_pilot output dir (with summary.json and results/)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--fork-block", type=int); ap.add_argument("--fork-time"); ap.add_argument("--dt-pre", type=float); ap.add_argument("--dt-post", type=float)
    ap.add_argument("--days", type=float, default=None, help="restrict the panel to +/- this many days around the fork")
    ap.add_argument("--subdir", default="results", help="results subdirectory: results (1s-kline reference, default) or "
                                                        "results_agg (run_pilot --reference aggtrades)")
    a = ap.parse_args()
    agg = a.subdir != "results"
    out = a.out or os.path.join(a.results, "analysis" if not agg else "analysis_" + a.subdir.replace("results_", ""))
    os.makedirs(out, exist_ok=True)
    summ = {}
    sp = os.path.join(a.results, "summary.json" if not agg else "summary_" + a.subdir.replace("results_", "") + ".json")
    if agg and not os.path.exists(sp):
        sp = os.path.join(a.results, "summary.json")
    if os.path.exists(sp):
        summ = json.load(open(sp))
    fork_block = a.fork_block or summ.get("fork_block")
    fork_time = a.fork_time or summ.get("fork_time_utc")
    dt_pre = a.dt_pre or summ.get("block_interval_before")
    dt_post = a.dt_post or summ.get("block_interval_after")
    if not (fork_block and fork_time and dt_pre and dt_post):
        raise SystemExit("need fork block/time and block intervals: pass --fork-block/--fork-time/--dt-pre/--dt-post or provide summary.json")
    fork_ts = pd.Timestamp(fork_time)
    if fork_ts.tzinfo is None:
        fork_ts = fork_ts.tz_localize("UTC")
    print(f"theory: overshoot / arbitrageur profit ∝ √Δt → predicted log change {set_theory(dt_pre, dt_post):+.3f}")
    paths = sorted(glob.glob(os.path.join(a.results, a.subdir, "*", "swaps_enriched.parquet")))
    if not paths:
        raise SystemExit(f"no {a.subdir}/<pool>/swaps_enriched.parquet found (run run_pilot.py with --include-swaps)")
    pools = [os.path.basename(os.path.dirname(p)) for p in paths]
    panel = pd.concat([hourly_panel_from_parquet(p, fork_block, fork_ts, dt_pre, dt_post) for p in paths], ignore_index=True)
    if a.days:
        panel = panel[(panel["t_days"] >= -a.days) & (panel["t_days"] < a.days)].reset_index(drop=True)
    panel.to_parquet(os.path.join(out, "hourly_panel.parquet"), index=False)
    hours = int(panel[panel.pool == pools[0]]["post"].eq(0).sum())
    with open(os.path.join(out, "table_regimes.md"), "w") as f:
        for p in pools:
            f.write(f"\n### {p}\n\n" + regime_table(panel[panel.pool == p]).to_markdown(floatfmt=".4g") + "\n")
    with open(os.path.join(out, "table_regressions.md"), "w") as f:
        f.write(f"窗口：分叉前后各 {hours / 24:.0f} 天（{len(panel):,} 池·小时）。\n")
        for label, extra in CONTROL_SETS:
            if "liq_mean" in extra and ("liq_mean" not in panel or panel["liq_mean"].isna().all()):
                continue
            f.write(f"\n### {label}\n\n" + regressions(panel, pools, extra=extra))
    with open(os.path.join(out, "table_matched.md"), "w") as f:
        f.write(matched(panel, pools, hours / 24))
    with open(os.path.join(out, "table_placebo.md"), "w") as f:
        f.write(placebo(panel, pools, fork_ts))
    with open(os.path.join(out, "table_exposure.md"), "w") as f:
        f.write(exposure_table(panel, pools))
    setup_fonts()
    scatter_fig(panel, pools, "overshoot_strict_bps", "套利时超出费率带的幅度 (bps, 严格)", "fig_overshoot.png", out)
    scatter_fig(panel, pools, "arb_profit", "小时套利者利润 (quote)", "fig_arb_profit_vs_vol.png", out)
    scatter_fig(panel, pools, "arb_loss", "小时 LP 逆向选择损失 (quote)", "fig_loss_vs_vol.png", out)
    daily_fig(panel, pools, fork_ts, out)
    print(open(os.path.join(out, "table_regressions.md")).read())
    print(open(os.path.join(out, "table_exposure.md")).read())
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
