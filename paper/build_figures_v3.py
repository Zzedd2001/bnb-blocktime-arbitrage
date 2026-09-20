"""Paper figures (English) for v3, built from the tick-reference source files (same as build_tables_v3.py)."""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os, json
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

C_PRE, C_POST, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e6e3"
FORKS = {
    "Lorentz": {"bundle": ROOT + "/lorentz_tick/bundle", "extra": ROOT + "/lorentz_tick/bundle/extra_agg", "dt": (3.0, 1.5), "fork": "2025-04-29T05:05:00Z",
                "title": "Lorentz: 3 s → 1.5 s (29 April 2025)"},
    "Maxwell": {"bundle": ROOT + "/maxwell_tick/bundle", "extra": ROOT + "/maxwell_tick/bundle/extra_agg", "dt": (1.5, 0.75), "fork": "2025-06-30T02:30:01Z",
                "title": "Maxwell: 1.5 s → 0.75 s (30 June 2025)"},
    "Fermi": {"bundle": ROOT + "/fermi_tick/bundle", "extra": ROOT + "/fermi_tick/bundle/extra_agg", "dt": (0.75, 0.45), "fork": "2026-01-14T02:30:00Z",
              "title": "Fermi: 0.75 s → 0.45 s (14 January 2026)"},
}
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
OUT = ROOT + "/paper/figures_v3"
A30, RES = "analysis_agg", "results_agg"
TF = ROOT + "/paper/three_forks_tick"
TICK_CMP = ROOT + "/tick_cmp"
os.makedirs(OUT, exist_ok=True)
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID); ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)


def theory(dt):
    return 0.5 * np.log(dt[1] / dt[0])


# ------------------------------------------------------------------ Figure 1: block interval and gas limit
fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.4))
for ax, (fork, cfg) in zip(axes, FORKS.items()):
    b = pd.read_csv(os.path.join(cfg["bundle"], RES, "blocks_hourly.csv"), parse_dates=["hour"])
    f = pd.Timestamp(cfg["fork"])
    b["t"] = (b["hour"] - f).dt.total_seconds() / 86400
    ax.plot(b["t"], b["interval_ms"], color=INK, lw=0.9)
    ax.set_ylabel("mean block interval (ms)", color=INK2, fontsize=8)
    ax.set_ylim(0, 3300)
    ax2 = ax.twinx()
    ax2.plot(b["t"], b["gas_limit"] / 1e6, color=C_PRE, lw=0.9, alpha=0.8)
    ax2.plot(b["t"], b["gas_used"] / 1e6, color=C_POST, lw=0.6, alpha=0.6)
    ax2.set_ylabel("gas limit / gas used per block (M)", color=INK2, fontsize=8)
    ax2.set_ylim(0, 150)
    ax2.tick_params(colors=INK2, labelsize=8)
    for s in ("top",):
        ax2.spines[s].set_visible(False)
    ax.axvline(0, color=INK2, ls=":", lw=1)
    ax.set_title(cfg["title"], fontsize=9, color=INK, loc="left")
    ax.set_xlabel("days relative to the fork", fontsize=8, color=INK2)
    style(ax)
fig.legend(handles=[Line2D([], [], color=INK, label="block interval (hourly mean)"), Line2D([], [], color=C_PRE, label="gas limit"),
                    Line2D([], [], color=C_POST, label="gas used")], loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.03))
fig.tight_layout(rect=(0, 0.06, 1, 1))
fig.savefig(os.path.join(OUT, "fig1_block_interval.png"), dpi=200)
plt.close(fig)

# ------------------------------------------------------------------ Figure 2: event study, both forks
PANELS = [("Overshoot at arbitrage (strict)", "overshoot_strict_bps", True), ("Arbitrageur profit", "arb_profit", True),
          ("LP adverse-selection loss (all swaps)", "arb_loss", False)]
fig, axes = plt.subplots(3, 3, figsize=(14, 8.2), sharex=True)
stats_out = {}
for j, (fork, cfg) in enumerate(FORKS.items()):
    p = pd.read_parquet(os.path.join(cfg["bundle"], A30, "hourly_panel.parquet"))
    d = p[p.pool.isin(CORE)].copy()
    th = theory(cfg["dt"])
    for i, (title, y, show_th) in enumerate(PANELS):
        ax = axes[i, j]
        dd = d[(d[y] > 0) & (d.sigma_ps > 0) & (d.liq_mean > 0) & (d.volume > 0)].replace([np.inf, -np.inf], np.nan).dropna(subset=[y, "sigma_ps"])
        m = smf.ols(f"np.log({y}) ~ np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + C(hod) + C(pool)", data=dd).fit()
        dd = dd.assign(res=m.resid, dayrel=np.floor(dd["t_days"]).astype(int))
        daily = dd.groupby("dayrel")["res"].mean()
        pre, post = daily[daily.index < 0], daily[daily.index >= 0]
        ax.axhline(0, color=GRID, lw=1)
        ax.plot(pre.index + 0.5, pre.values, "o-", color=C_PRE, ms=3, lw=0.9)
        ax.plot(post.index + 0.5, post.values, "o-", color=C_POST, ms=3, lw=0.9)
        ax.hlines(pre.mean(), -30, 0, color=C_PRE, lw=1, ls="--"); ax.hlines(post.mean(), 0, 30, color=C_POST, lw=1, ls="--")
        ax.axvline(0, color=INK2, lw=1, ls=":")
        diff = post.mean() - pre.mean()
        stats_out[(fork, y)] = diff
        note = f"post − pre = {diff:+.2f}" + (f" (pred. {th:+.3f})" if show_th else "")
        ax.set_title(f"{title}: {note}", fontsize=8.5, color=INK, loc="left")
        style(ax)
        if j == 0:
            ax.set_ylabel("daily mean residual (log)", fontsize=8, color=INK2)
    axes[0, j].text(0.0, 1.22, cfg["title"], transform=axes[0, j].transAxes, fontsize=9.5, color=INK, ha="left")
for ax in axes[-1]:
    ax.set_xlabel("days relative to the fork", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(os.path.join(OUT, "fig2_event_study.png"), dpi=200)
plt.close(fig)
json.dump({f"{k[0]}|{k[1]}": v for k, v in stats_out.items()}, open(os.path.join(OUT, "fig2_stats.json"), "w"), indent=1)

# ------------------------------------------------------------------ Figure 4: volatility and raw overshoot (core pools)
fig, axes = plt.subplots(2, 3, figsize=(14, 5.6), sharex=True)
for j, (fork, cfg) in enumerate(FORKS.items()):
    p = pd.read_parquet(os.path.join(cfg["bundle"], A30, "hourly_panel.parquet"))
    d = p[p.pool.isin(CORE)].copy(); d["dayrel"] = np.floor(d["t_days"]).astype(int)
    g = d.groupby(["dayrel", "pool"]).agg(rv=("rv", "sum"), h=("rv", "size"), ov=("overshoot_strict_bps", "mean")).reset_index()
    g["sig"] = 1e4 * np.sqrt(g["rv"] / (g["h"] * 3600))
    ax = axes[0, j]
    for pool, mk in zip(CORE, ("o", "s", "^")):
        s = g[g.pool == pool]
        ax.plot(s["dayrel"] + 0.5, s["sig"], marker=mk, ms=2.5, lw=0.8, label=pool.replace("-USDT-500", "/USDT 0.05%"), color=[C_PRE, "#7a5195", C_POST][CORE.index(pool)])
    ax.axvline(0, color=INK2, ls=":", lw=1); ax.set_ylabel("Binance realised σ (bp/√s), daily", fontsize=8, color=INK2)
    ax.set_title(cfg["title"], fontsize=9.5, color=INK, loc="left"); style(ax)
    if j == 0:
        ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    ax = axes[1, j]
    for pool, mk in zip(CORE, ("o", "s", "^")):
        s = g[g.pool == pool]
        ax.plot(s["dayrel"] + 0.5, s["ov"], marker=mk, ms=2.5, lw=0.8, color=[C_PRE, "#7a5195", C_POST][CORE.index(pool)])
    ax.axvline(0, color=INK2, ls=":", lw=1); ax.set_ylabel("overshoot at strict arbitrage (bp), daily mean", fontsize=8, color=INK2)
    ax.set_xlabel("days relative to the fork", fontsize=8, color=INK2); style(ax)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig4_sigma_overshoot.png"), dpi=200)
plt.close(fig)
# ------------------------------------------------------------------ Figure 3 (three forks) and Figure 5 (latency floor): copied from three_forks_tick
import shutil
shutil.copy(os.path.join(TF, "fig_three_forks.png"), os.path.join(OUT, "fig3_three_forks.png"))
shutil.copy(os.path.join(TF, "fig_latency_floor.png"), os.path.join(OUT, "fig5_latency_floor.png"))

# ------------------------------------------------------------------ Figure 6: kline-vs-tick wedge, daily, three forks
fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.6), sharey=True)
for ax, (fork, cfg) in zip(axes, FORKS.items()):
    kdir = {"Lorentz": ROOT + "/lorentz/bundle/analysis", "Maxwell": ROOT + "/maxwell/analysis", "Fermi": ROOT + "/fermi/bundle/analysis"}[fork]
    k = pd.read_parquet(os.path.join(kdir, "hourly_panel.parquet")); t = pd.read_parquet(os.path.join(cfg["bundle"], A30, "hourly_panel.parquet"))
    k["hour"] = pd.to_datetime(k["hour"], utc=True); t["hour"] = pd.to_datetime(t["hour"], utc=True)
    m = k[k.pool.isin(CORE)][["pool", "hour", "overshoot_strict_bps", "t_days"]].merge(t[["pool", "hour", "overshoot_strict_bps", "ref_gap_bps"]], on=["pool", "hour"], suffixes=("_k", "_t"))
    m["w"] = np.log(m["overshoot_strict_bps_t"]) - np.log(m["overshoot_strict_bps_k"]); m = m.replace([np.inf, -np.inf], np.nan)
    m["dayrel"] = np.floor(m["t_days"]).astype(int)
    g = m.groupby("dayrel").agg(w=("w", "mean"), gap=("ref_gap_bps", "mean")).reset_index()
    ax.plot(g["dayrel"] + 0.5, g["w"], "o-", color=INK, ms=2.5, lw=0.9, label="log(overshoot, tick / overshoot, 1-s kline)")
    ax2 = ax.twinx(); ax2.plot(g["dayrel"] + 0.5, g["gap"], color=C_PRE, lw=0.9, alpha=0.8, label="mean |kline / tick − 1| (bp)")
    ax2.set_ylim(0, 2.0); ax2.tick_params(colors=INK2, labelsize=8); ax2.spines["top"].set_visible(False)
    if fork == "Fermi":
        ax2.set_ylabel("reference gap, mean |kline/tick − 1| (bp)", fontsize=8, color=C_PRE)
    ax.axvline(0, color=INK2, ls=":", lw=1); ax.axhline(0, color=GRID, lw=1)
    ax.set_title(cfg["title"], fontsize=9, color=INK, loc="left"); ax.set_xlabel("days relative to the fork", fontsize=8, color=INK2)
    ax.set_ylim(-0.05, 0.55); style(ax)
axes[0].set_ylabel("daily mean of log(overshoot tick / kline), core pools", fontsize=8, color=INK2)
fig.legend(handles=[Line2D([], [], color=INK, marker="o", ms=3, label="log(strict overshoot with tick reference / with 1-s kline reference), daily mean"),
                    Line2D([], [], color=C_PRE, label="mean |kline reference / tick reference − 1| (bp, right axis)")],
           loc="lower center", ncol=2, fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.03))
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(os.path.join(OUT, "fig6_wedge.png"), dpi=200)
plt.close(fig)
print("figures written", sorted(os.listdir(OUT)), stats_out)
