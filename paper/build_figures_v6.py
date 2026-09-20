#!/usr/bin/env python3
"""build_figures_v6.py — journal-legible figures for the revised manuscript (referee minor 5).

Every figure is drawn at 5.4 inches wide (the Springer text width is 5.2 in), with 7.5–8.5 pt type, so that nothing is
scaled down at print.  Multi-fork panels are stacked vertically instead of side by side.
Outputs: figures_v6/fig1_block_interval.png, fig2_roadmap.png, fig3_event_study.png, fig4_wedge.png, fig5_first_block.png,
         fig6_latency_intercepts.png, fig7_component_effects.png, figA1_sigma_overshoot.png, figD1_twelve_point.png
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.optimize import brentq
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

C_PRE, C_POST, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#dcdcd8"
COL = {"Lorentz": "#2a9d8f", "Maxwell": "#2a78d6", "Fermi": "#eb6834"}
FORKS = {
    "Lorentz": {"bundle": ROOT + "/lorentz_tick/bundle", "dt": (3.0, 1.5), "fork": "2025-04-29T05:05:00Z", "title": "Lorentz: 3 s → 1.5 s (29 April 2025)"},
    "Maxwell": {"bundle": ROOT + "/maxwell_tick/bundle", "dt": (1.5, 0.75), "fork": "2025-06-30T02:30:01Z", "title": "Maxwell: 1.5 s → 0.75 s (30 June 2025)"},
    "Fermi": {"bundle": ROOT + "/fermi_tick/bundle", "dt": (0.75, 0.45), "fork": "2026-01-14T02:30:00Z", "title": "Fermi: 0.75 s → 0.45 s (14 January 2026)"},
}
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
LIQ = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-100"]
LABEL = {"WBNB-USDT-500": "WBNB/USDT 5 bp", "ETH-USDT-500": "ETH/USDT 5 bp", "BTCB-USDT-500": "BTCB/USDT 5 bp", "WBNB-USDT-100": "WBNB/USDT 1 bp"}
PCOL = {"WBNB-USDT-500": "#0b0b0b", "ETH-USDT-500": "#2a78d6", "BTCB-USDT-500": "#eb6834", "WBNB-USDT-100": "#8a8a8a"}
PMK = {"WBNB-USDT-500": "o", "ETH-USDT-500": "s", "BTCB-USDT-500": "^", "WBNB-USDT-100": "D"}
ORDER = [("Lorentz", "pre"), ("Lorentz", "post"), ("Maxwell", "pre"), ("Maxwell", "post"), ("Fermi", "pre"), ("Fermi", "post")]
OUT = ROOT + "/paper/figures_v6"
T6 = ROOT + "/paper/tables_v6"
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False, "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
                     "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5})
W = 5.4
K = json.load(open(ROOT + "/arb_resp/cmp_bots/key_numbers.json"))
MS = json.load(open(f"{T6}/main_spec.json"))["main"]
LF = json.load(open(f"{T6}/latency_floor_v6.json"))


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2)
    ax.grid(color=GRID, lw=0.5)


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=250)
    plt.close(fig)


# ------------------------------------------------------------------ Figure 1: block interval and gas (three stacked panels)
fig, axes = plt.subplots(3, 1, figsize=(W, 6.6), sharex=True)
for ax, (fork, cfg) in zip(axes, FORKS.items()):
    b = pd.read_csv(os.path.join(cfg["bundle"], "results_agg", "blocks_hourly.csv"), parse_dates=["hour"])
    b["t"] = (b["hour"] - pd.Timestamp(cfg["fork"])).dt.total_seconds() / 86400
    ax.plot(b["t"], b["interval_ms"], color=INK, lw=0.9)
    ax.set_ylabel("block interval (ms)", color=INK2)
    ax.set_ylim(0, 3300)
    ax2 = ax.twinx()
    ax2.plot(b["t"], b["gas_limit"] / 1e6, color=C_PRE, lw=0.9, alpha=0.85)
    ax2.plot(b["t"], b["gas_used"] / 1e6, color=C_POST, lw=0.6, alpha=0.7)
    ax2.set_ylabel("gas per block (M)", color=INK2)
    ax2.set_ylim(0, 150)
    ax2.tick_params(colors=INK2)
    ax2.spines["top"].set_visible(False)
    ax.axvline(0, color=INK2, ls=":", lw=1)
    ax.set_title(cfg["title"], color=INK, loc="left")
    style(ax)
axes[-1].set_xlabel("days relative to the fork", color=INK2)
fig.legend(handles=[Line2D([], [], color=INK, label="block interval (hourly mean)"), Line2D([], [], color=C_PRE, label="gas limit"),
                    Line2D([], [], color=C_POST, label="gas used")], loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.005))
fig.tight_layout(rect=(0, 0.035, 1, 1))
save(fig, "fig1_block_interval.png")

# ------------------------------------------------------------------ Figure 2: roadmap — chained main-specification estimates vs the law and the latency floor
SETS = [("Overshoot at strict arbitrage (headline)", "Strict overshoot, all flow (headline)", "strict overshoot, all flow", INK, "o"),
        ("Strict overshoot, bot flow (public routers excluded)", "Strict overshoot, bot flow", "strict overshoot, bot flow", "#2a78d6", "s"),
        ("Overshoot of CEX-triggered bot arbitrages", "CEX-triggered bot arbitrages", "CEX-triggered bot arbitrages", "#eb6834", "^")]
fig, ax = plt.subplots(figsize=(W, 3.9))
dts = np.array([3.0, 1.5, 0.75, 0.45])
x = np.linspace(0.05, 3.3, 500)
ax.plot(x, np.sqrt(x / 3), color="#b0322f", lw=1.1, ls="-.", label="√Δt law (ℓ = 0)")
for key, lfkey, lab, col, mk in SETS:
    l = LF[lfkey]["ell"]
    ax.plot(x, np.sqrt((x + l) / (3 + l)), color=col, lw=1.0, ls="--", alpha=0.8, label=f"latency-floor fit, {lab}: ℓ = {l:.2f} s")
for i, (key, lfkey, lab, col, mk) in enumerate(SETS):
    lv, se2 = [1.0], [0.0]
    for f in FORKS:
        b, s = MS[f"{key}|{f}"]["b"], MS[f"{key}|{f}"]["se"]
        lv.append(lv[-1] * np.exp(b))
        se2.append(se2[-1] + s ** 2)
    lv, se = np.array(lv), np.sqrt(np.array(se2))
    off = dts * (1 + 0.04 * (i - 1))
    ax.errorbar(off, lv, yerr=[lv - lv * np.exp(-1.96 * se), lv * np.exp(1.96 * se) - lv], fmt=mk, color=col, ms=5, capsize=2.5, lw=1,
                label=f"chained estimates, {lab} (95% CI)")
ax.set_xscale("log")
ax.set_xticks(dts)
ax.set_xticklabels(["3.0", "1.5", "0.75", "0.45"])
ax.set_xlabel("block interval Δt (s), log scale", color=INK2)
ax.set_ylabel("overshoot at arbitrage relative to 3-second blocks", color=INK2)
ax.set_ylim(0.3, 1.1)
style(ax)
ax.legend(frameon=False, loc="lower right", fontsize=7)
fig.tight_layout()
save(fig, "fig2_roadmap.png")

# ------------------------------------------------------------------ Figure 3: event study, 3 outcomes × 3 forks
PANELS = [("Strict overshoot", "overshoot_strict_bps", True), ("Arbitrageur profit", "arb_profit", True), ("LPs' gross loss", "arb_loss", False)]
fig, axes = plt.subplots(3, 3, figsize=(W, 6.4), sharex=True)
for j, (fork, cfg) in enumerate(FORKS.items()):
    p = pd.read_parquet(os.path.join(cfg["bundle"], "analysis_agg", "hourly_panel.parquet"))
    d = p[p.pool.isin(CORE)].copy()
    th = 0.5 * np.log(cfg["dt"][1] / cfg["dt"][0])
    for i, (title, y, show_th) in enumerate(PANELS):
        ax = axes[i, j]
        dd = d[(d[y] > 0) & (d.sigma_ps > 0) & (d.liq_mean > 0) & (d.volume > 0)].replace([np.inf, -np.inf], np.nan).dropna(subset=[y, "sigma_ps"])
        m = smf.ols(f"np.log({y}) ~ np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + C(hod) + C(pool)", data=dd).fit()
        dd = dd.assign(res=m.resid, dayrel=np.floor(dd["t_days"]).astype(int))
        daily = dd.groupby("dayrel")["res"].mean()
        pre, post = daily[daily.index < 0], daily[daily.index >= 0]
        ax.axhline(0, color=GRID, lw=1)
        ax.plot(pre.index + 0.5, pre.values, "o-", color=C_PRE, ms=2, lw=0.7)
        ax.plot(post.index + 0.5, post.values, "o-", color=C_POST, ms=2, lw=0.7)
        ax.hlines(pre.mean(), -30, 0, color=C_PRE, lw=1, ls="--")
        ax.hlines(post.mean(), 0, 30, color=C_POST, lw=1, ls="--")
        ax.axvline(0, color=INK2, lw=0.8, ls=":")
        diff = post.mean() - pre.mean()
        note = f"post − pre {diff:+.2f}" + (f"; law {th:+.2f}" if show_th else "")
        style(ax)
        ax.tick_params(labelsize=6.8)
        ax.set_title((f"{fork}\n" if i == 0 else "") + note, color=INK, loc="left", fontsize=7.2)
        if j == 0:
            ax.set_ylabel(f"{title}\n(daily mean residual, log)", color=INK2, fontsize=7.2)
for ax in axes[-1]:
    ax.set_xlabel("days relative to the fork", color=INK2, fontsize=7.5)
fig.tight_layout()
save(fig, "fig3_event_study.png")

# ------------------------------------------------------------------ Figure 4: the wedge between the two references, three stacked panels
fig, axes = plt.subplots(3, 1, figsize=(W, 6.6), sharex=True)
for ax, (fork, cfg) in zip(axes, FORKS.items()):
    kdir = {"Lorentz": ROOT + "/lorentz/bundle/analysis", "Maxwell": ROOT + "/maxwell/analysis", "Fermi": ROOT + "/fermi/bundle/analysis"}[fork]
    k = pd.read_parquet(os.path.join(kdir, "hourly_panel.parquet"))
    t = pd.read_parquet(os.path.join(cfg["bundle"], "analysis_agg", "hourly_panel.parquet"))
    k["hour"] = pd.to_datetime(k["hour"], utc=True)
    t["hour"] = pd.to_datetime(t["hour"], utc=True)
    m = k[k.pool.isin(CORE)][["pool", "hour", "overshoot_strict_bps", "t_days"]].merge(t[["pool", "hour", "overshoot_strict_bps", "ref_gap_bps"]], on=["pool", "hour"], suffixes=("_k", "_t"))
    m["w"] = np.log(m["overshoot_strict_bps_t"]) - np.log(m["overshoot_strict_bps_k"])
    m = m.replace([np.inf, -np.inf], np.nan)
    m["dayrel"] = np.floor(m["t_days"]).astype(int)
    g = m.groupby("dayrel").agg(w=("w", "mean"), gap=("ref_gap_bps", "mean")).reset_index()
    ax.plot(g["dayrel"] + 0.5, g["w"], "o-", color=INK, ms=2.2, lw=0.8)
    ax2 = ax.twinx()
    ax2.plot(g["dayrel"] + 0.5, g["gap"], color=C_PRE, lw=0.9, alpha=0.85)
    ax2.set_ylim(0, 2.0)
    ax2.tick_params(colors=INK2)
    ax2.spines["top"].set_visible(False)
    ax2.set_ylabel("reference gap (bp)", color=C_PRE)
    ax.axvline(0, color=INK2, ls=":", lw=1)
    ax.axhline(0, color=GRID, lw=1)
    ax.set_title(cfg["title"], color=INK, loc="left")
    ax.set_ylim(-0.05, 0.55)
    ax.set_ylabel("wedge (log)", color=INK2)
    style(ax)
axes[-1].set_xlabel("days relative to the fork", color=INK2)
fig.legend(handles=[Line2D([], [], color=INK, marker="o", ms=3, label="wedge: log(strict overshoot, trade reference / candle reference), daily mean"),
                    Line2D([], [], color=C_PRE, label="reference gap: mean |candle / trade − 1| (bp, right axis)")],
           loc="lower center", ncol=1, frameon=False, bbox_to_anchor=(0.5, -0.005))
fig.tight_layout(rect=(0, 0.05, 1, 1))
save(fig, "fig4_wedge.png")

# ------------------------------------------------------------------ Figure 5: share of CEX-triggered arbitrages landing in the first block (former Fig. D1)
R1 = K["R1"]
fig, ax = plt.subplots(figsize=(W, 4.3))
xx = np.linspace(0.3, 3.3, 300)
for lt, ls in ((0.1, ":"), (0.25, "-"), (0.5, "--")):
    ax.plot(xx, np.maximum(0, 1 - lt / xx), color="#2a9d8f", ls=ls, lw=1.1, label=f"point latency ℓ = {lt} s: 1 − ℓ/Δt")
for p in LIQ:
    xs = [R1[f"{f}|{p}|{r}"]["dt"] for f, r in ORDER]
    ys = [R1[f"{f}|{p}|{r}"]["pk1"] for f, r in ORDER]
    ax.plot(xs, ys, PMK[p], ms=6, color=PCOL[p], label=LABEL[p] + ", CEX-triggered")
    yo = [R1[f"{f}|{p}|{r}"]["oc1"] for f, r in ORDER]
    ax.plot(xs, yo, PMK[p], ms=6, mfc="none", color=PCOL[p], alpha=0.7)
ax.plot([], [], "o", mfc="none", color="#555", label="open markers: on-chain triggers, P(ℓ ≤ Δt)")
ax.set_xscale("log")
ax.set_xticks([0.45, 0.75, 1.5, 3.0])
ax.set_xticklabels(["0.45", "0.75", "1.5", "3.0"])
ax.set_xlabel("block interval Δt (s), log scale", color=INK2)
ax.set_ylabel("share landing in the first block after the opening", color=INK2)
ax.set_ylim(0.3, 1.02)
style(ax)
ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.16))
fig.tight_layout()
save(fig, "fig5_first_block.png")

# ------------------------------------------------------------------ Figure 6: latency intercepts across the six regimes (two stacked panels)
def esqrt(lt, dt, n=20001):
    u = np.linspace(0, dt, n)
    return np.sqrt(lt + u).mean()


def paper_l(lt, dt0, dt1):
    target = np.log(esqrt(lt, dt1) / esqrt(lt, dt0))
    return brentq(lambda l: 0.5 * np.log((dt1 + l) / (dt0 + l)) - target, 1e-6, 50)


def lt_from_l(L):
    return [brentq(lambda lt: paper_l(lt, *v) - L, 1e-4, 5) for v in FORKS_DT.values()]


FORKS_DT = {f: c["dt"] for f, c in FORKS.items()}
ell = LF["Strict overshoot, all flow (headline)"]
lt_mid = lt_from_l(ell["ell"])
lt_lo = lt_from_l(ell["ci"][0])
lt_hi = lt_from_l(ell["ci"][1])
BAND = {"mid": float(np.mean(lt_mid)), "lo": float(min(lt_lo)), "hi": float(max(lt_hi)), "ell": ell["ell"], "ci": ell["ci"]}
json.dump(BAND, open(f"{T6}/latency_band.json", "w"), indent=1)
fig, axes = plt.subplots(2, 1, figsize=(W, 6.6), sharex=True)
xs = np.arange(6)
lab = [f"{f[:3]} {r}\n{FORKS[f]['dt'][0 if r == 'pre' else 1]:.2f} s" for f, r in ORDER]
for ax, key, sek, ttl, ylim in ((axes[0], "q10", "se10", "tenth percentile: ℓ̂ = Q₀.₁(τ) − 0.1·Δt", 1100), (axes[1], "q50", "se50", "median: ℓ̂ = Q₀.₅(τ) − 0.5·Δt", 1500)):
    for p in LIQ:
        y = [R1[f"{f}|{p}|{r}"][key] for f, r in ORDER]
        se = [R1[f"{f}|{p}|{r}"][sek] for f, r in ORDER]
        ax.errorbar(xs + (LIQ.index(p) - 1.5) * 0.14, y, yerr=1.96 * np.array(se), fmt=PMK[p], ms=5, lw=1, capsize=2, label=LABEL[p], color=PCOL[p])
    ax.axhspan(1000 * BAND["lo"], 1000 * BAND["hi"], color="#2a9d8f", alpha=0.12, lw=0)
    ax.axhline(1000 * BAND["mid"], color="#2a9d8f", lw=0.9, ls="--")
    ax.set_xticks(xs)
    ax.set_xticklabels(lab)
    ax.set_ylabel("latency intercept (ms)", color=INK2)
    ax.set_title(ttl, color=INK, loc="left")
    ax.set_ylim(-50, ylim)
    style(ax)
axes[0].legend(frameon=False, ncol=2, fontsize=7)
axes[1].plot([], [], color="#2a9d8f", ls="--", label=f"latency implied by the fitted floor: ℓ = {ell['ell']:.2f} s ⇔ ℓ_t ≈ {BAND['mid']:.2f} s (band: 95% CI)")
axes[1].legend(frameon=False, fontsize=7, loc="upper right")
fig.tight_layout()
save(fig, "fig6_latency_intercepts.png")

# ------------------------------------------------------------------ Figure 7: fork effect by component, pool by pool, main specification (RD jump, ±30 d)
def comp_fit(fork, pool, y, days=30):
    d = pd.read_csv(ROOT + f"/arb_resp/comp_bots/{fork}/arb_response_bots/component_panels/{pool}.csv")
    d = d[(d.t_days >= -days) & (d.t_days < days) & (d[y] > 0) & d[y].notna() & (d["sigma_ps"] > 0) & (d["liq_mean"] > 0) & (d["volume"] > 0)].copy()
    if y + "_n" in d:
        d = d[d[y + "_n"] >= 5]
    d["yy"] = np.log(d[y])
    m = smf.ols("yy ~ post + np.log(sigma_ps) + np.log(liq_mean) + np.log(volume) + t_days + post:t_days + C(hod)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"]})
    return float(m.params["post"]), float(m.bse["post"]), int(m.nobs)


COMP = {}
fig, ax = plt.subplots(figsize=(W, 3.9))
labs = []
i = 0
for f in FORKS:
    for p in LIQ:
        for y, col, off, mk in (("cex_move", "#2a78d6", -0.22, "o"), ("cex_jump", "#0b0b0b", 0.0, "s"), ("same_block", "#9a9a9a", 0.22, "^")):
            b, s, n = comp_fit(f, p, y)
            COMP[f"{f}|{p}|{y}"] = [b, s, n]
            ax.errorbar(i + off, b, yerr=1.96 * s, fmt=mk, color=col, ms=4.2, capsize=2, lw=0.9,
                        label={"cex_move": "movement during τ (M)", "cex_jump": "jump at the crossing (J)", "same_block": "same-block back-run"}[y] if i == 0 else None)
        law = 0.5 * np.log(FORKS[f]["dt"][1] / FORKS[f]["dt"][0])
        ax.plot([i - 0.4, i + 0.4], [law, law], color="#b0322f", lw=1.3, label="√Δt law" if i == 0 else None)
        labs.append({"WBNB-USDT-500": "WBNB", "ETH-USDT-500": "ETH", "BTCB-USDT-500": "BTCB", "WBNB-USDT-100": "WBNB\n1 bp"}[p])
        i += 1
json.dump(COMP, open(f"{T6}/components_pool_main.json", "w"), indent=1)
ax.axhline(0, color="#999", lw=0.8)
ax.set_xticks(np.arange(12))
ax.set_xticklabels(labs, fontsize=6.8)
for k, f in enumerate(FORKS):
    ax.text(4 * k + 1.5, 0.62, f"{f}: {FORKS[f]['dt'][0]} → {FORKS[f]['dt'][1]} s", ha="center", va="bottom", fontsize=7.5, color=INK)
    if k:
        ax.axvline(4 * k - 0.5, color=GRID, lw=0.8)
ax.set_ylabel("fork effect, log points (RD jump, ±30 d)", color=INK2)
ax.set_ylim(-1.0, 0.7)
style(ax)
ax.legend(frameon=False, fontsize=7, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.13))
fig.tight_layout()
save(fig, "fig7_component_effects.png")

# ------------------------------------------------------------------ Figure A1: volatility and raw overshoot, three forks (rows) × two statistics (columns)
fig, axes = plt.subplots(3, 2, figsize=(W, 7.0), sharex=True)
for i, (fork, cfg) in enumerate(FORKS.items()):
    p = pd.read_parquet(os.path.join(cfg["bundle"], "analysis_agg", "hourly_panel.parquet"))
    d = p[p.pool.isin(CORE)].copy()
    d["dayrel"] = np.floor(d["t_days"]).astype(int)
    g = d.groupby(["dayrel", "pool"]).agg(rv=("rv", "sum"), h=("rv", "size"), ov=("overshoot_strict_bps", "mean")).reset_index()
    g["sig"] = 1e4 * np.sqrt(g["rv"] / (g["h"] * 3600))
    for j, (col, ylab) in enumerate((("sig", "Binance σ (bp/√s), daily"), ("ov", "strict overshoot (bp), daily mean"))):
        ax = axes[i, j]
        for pool, mk in zip(CORE, ("o", "s", "^")):
            s = g[g.pool == pool]
            ax.plot(s["dayrel"] + 0.5, s[col], marker=mk, ms=2, lw=0.7, color=[C_PRE, "#7a5195", C_POST][CORE.index(pool)], label=pool.replace("-USDT-500", "/USDT 5 bp"))
        ax.axvline(0, color=INK2, ls=":", lw=1)
        ax.set_ylabel(ylab, color=INK2, fontsize=7.2)
        style(ax)
        ax.tick_params(labelsize=6.8)
        if j == 0:
            ax.set_title(cfg["title"], color=INK, loc="left", fontsize=8)
axes[0, 0].legend(frameon=False, fontsize=6.5)
for ax in axes[-1]:
    ax.set_xlabel("days relative to the fork", color=INK2, fontsize=7.5)
fig.tight_layout()
save(fig, "figA1_sigma_overshoot.png")

# ------------------------------------------------------------------ Figure D1 (former D2): twelve-point test, two stacked panels
P4 = pd.read_csv(ROOT + "/arb_resp/cmp_bots/R4_points.csv")
res4 = K["R4"]
fig, axes = plt.subplots(2, 1, figsize=(W, 7.6))
for ax, col, ttl, rk in ((axes[0], "impl", "τ-implied effect log(E√τ₁ / E√τ₀)", "τ-implied"), (axes[1], "comp", "composite prediction: only the movement component shrinks", "composite (move-only)")):
    for f in FORKS:
        s = P4[P4["fork"] == f]
        ax.errorbar(s[col], s["tick"], yerr=1.96 * s["se"], fmt="o", color=COL[f], ms=5, capsize=2, lw=1, label=f)
        for _, r in s.iterrows():
            ax.annotate(LABEL[r["pool"]].split("/")[0] + (" 1bp" if r["pool"].endswith("100") else ""), (r[col], r["tick"]), fontsize=6.5, xytext=(3, 3), textcoords="offset points", color=INK2)
    lim = [-0.45, 0.05]
    ax.plot(lim, lim, color="#999", lw=0.8, ls="--")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    v = res4[rk]
    ax.set_xlabel(ttl, color=INK2)
    ax.set_ylabel("pool-level estimate (±14 d, σ + L + volume), log points", color=INK2, fontsize=7.5)
    ax.set_title(f"corr. {v['corr']:.2f}; WLS slope {v['slope']:.2f} ({v['slope_se']:.2f}); MAE {v['mae']:.3f}", color=INK, loc="left")
    style(ax)
    ax.legend(frameon=False, fontsize=7)
fig.tight_layout()
save(fig, "figD1_twelve_point.png")
print("figures written:", sorted(os.listdir(OUT)))
print("band", BAND)
