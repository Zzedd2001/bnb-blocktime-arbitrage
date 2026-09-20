"""Three forks (Lorentz 3→1.5 s, Maxwell 1.5→0.75 s, Fermi 0.75→0.45 s): same specifications side by side,
elasticity of the strict overshoot with respect to Δt per fork and pooled, equality tests, a stacked hourly-panel
regression with log Δt as a continuous treatment, and figures."""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os, json, argparse
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib import font_manager

C_L, C_M, C_F = "#2a9d8f", "#2a78d6", "#eb6834"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e6e3"
FORKS = {
    "Lorentz": {"bundle": ROOT + "/lorentz/bundle", "extra": ROOT + "/lorentz/bundle/extra", "dt": (3.0, 1.5), "color": C_L, "marker": "^",
                "label": "Lorentz (3 → 1.5 s)"},
    "Maxwell": {"bundle": ROOT + "/maxwell", "extra": ROOT + "/maxwell/extra2", "dt": (1.5, 0.75), "color": C_M, "marker": "o",
                "label": "Maxwell (1.5 → 0.75 s)"},
    "Fermi": {"bundle": ROOT + "/fermi/bundle", "extra": ROOT + "/fermi/extra", "dt": (0.75, 0.45), "color": C_F, "marker": "s",
              "label": "Fermi (0.75 → 0.45 s)"},
}
CORE = ["BTCB-USDT-500", "ETH-USDT-500", "WBNB-USDT-500"]
SPEC_NAMES = {"σ": "log σ + hour FE", "σ+L+vol": "+ log L + log volume", "σ+L+vol+趋势": "+ linear trend", "RD": "RD jump (separate slopes)"}
OUT = ROOT + "/paper/three_forks"
SUBS = {"±30 d": "analysis", "±14 d": "analysis_14d"}
_ap = argparse.ArgumentParser(); _ap.add_argument("--variant", choices=["kline", "tick"], default="kline")
VARIANT = _ap.parse_args().variant
if VARIANT == "tick":                       # tick-level (aggTrades) reference: run_pilot --reference aggtrades outputs
    FORKS["Lorentz"].update({"bundle": ROOT + "/lorentz_tick/bundle", "extra": ROOT + "/lorentz_tick/bundle/extra_agg"})
    FORKS["Maxwell"].update({"bundle": ROOT + "/maxwell_tick/bundle", "extra": ROOT + "/maxwell_tick/bundle/extra_agg"})
    FORKS["Fermi"].update({"bundle": ROOT + "/fermi_tick/bundle", "extra": ROOT + "/fermi_tick/bundle/extra_agg"})
    SUBS = {"±30 d": "analysis_agg", "±14 d": "analysis_agg_14d"}
    OUT = ROOT + "/paper/three_forks_tick"
os.makedirs(OUT, exist_ok=True)


def setup_fonts():
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK" in f:
            font_manager.fontManager.addfont(f)
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False


def theory(dt):
    return 0.5 * np.log(dt[1] / dt[0])


def parse_cell(cell):
    b = float(cell.split(" ")[0].replace("*", "")); se = float(cell.split("(")[1].rstrip(")"))
    return b, se


def load_core(cfg):
    cp = pd.read_csv(os.path.join(cfg["extra"], "core_pooled_raw.csv"))
    rd = pd.read_csv(os.path.join(cfg["extra"], "rd_jump.csv"))
    out = {}
    for _, r in cp.iterrows():
        if r["控制"] == "σ+L+vol+池别趋势":
            continue
        out[(r["窗口"], r["控制"])] = {"over": (r["_b_over"], r["_se_over"]), "prof": (r["_b_prof"], r["_se_prof"]),
                                     "loss": (r["_b_loss"], r["_se_loss"]), "n": int(r["n"])}
    for w in ("±30 d", "±14 d"):
        sub = rd[rd["窗口"] == w].set_index("被解释变量")
        out[(w, "RD")] = {"over": parse_cell(sub.loc["log 越界幅度（严格）", "跳跃（post）"]), "prof": parse_cell(sub.loc["log 套利者利润", "跳跃（post）"]),
                          "loss": parse_cell(sub.loc["log LP 损失（总）", "跳跃（post）"]), "n": int(sub.loc["log 越界幅度（严格）", "n"])}
    return out


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def fmt(b, se):
    p = 2 * (1 - stats.norm.cdf(abs(b / se)))
    return f"{b:+.3f}{star(p)} ({se:.3f})".replace("+", "").replace("-", "−")


def main():
    setup_fonts()
    core = {f: load_core(c) for f, c in FORKS.items()}
    th = {f: theory(c["dt"]) for f, c in FORKS.items()}
    dlog = {f: np.log(c["dt"][1] / c["dt"][0]) for f, c in FORKS.items()}
    specs = [(w, c) for w in ("±30 d", "±14 d", "±7 d") for c in ("σ", "σ+L+vol", "σ+L+vol+趋势", "RD") if (w, c) in core["Maxwell"]]

    # ------------------------------------------------ Table A: coefficients, shares, elasticities, equality test
    rows, el_rows = [], []
    for w, c in specs:
        r = {"Window": w, "Specification": SPEC_NAMES[c]}
        es, ws = [], []
        for f in FORKS:
            b, se = core[f][(w, c)]["over"]
            r[f"{f} β (pred. {th[f]:+.3f})"] = fmt(b, se)
            r[f"{f} share"] = f"{b / th[f]:.0%}"
            e, se_e = b / dlog[f], se / abs(dlog[f])          # elasticity wrt Δt (prediction 0.5)
            es.append(e); ws.append(1 / se_e ** 2)
            r[f"{f} elasticity"] = f"{e:.2f} ({se_e:.2f})"
        es, ws = np.array(es), np.array(ws)
        ebar = (ws * es).sum() / ws.sum(); se_bar = np.sqrt(1 / ws.sum())
        Q = (ws * (es - ebar) ** 2).sum(); p_eq = 1 - stats.chi2.cdf(Q, df=2)
        r["pooled elasticity"] = fmt(ebar, se_bar).replace("−", "-")
        r["t vs 0.5"] = f"{(ebar - 0.5) / se_bar:+.1f}"
        r["equality across forks (p)"] = f"{p_eq:.2f}"
        rows.append(r)
        el_rows.append({"window": w, "spec": c, "e_L": es[0], "e_M": es[1], "e_F": es[2], "se_L": 1 / np.sqrt(ws[0]), "se_M": 1 / np.sqrt(ws[1]),
                        "se_F": 1 / np.sqrt(ws[2]), "pooled": ebar, "se_pooled": se_bar, "p_eq": p_eq})
    tA = pd.DataFrame(rows)
    open(os.path.join(OUT, "tableA_three_forks.md"), "w").write(tA.to_markdown(index=False))
    tA.to_csv(os.path.join(OUT, "tableA_three_forks.csv"), index=False)
    tE = pd.DataFrame(el_rows); tE.to_csv(os.path.join(OUT, "elasticities.csv"), index=False)
    print(tA.to_string())

    # ------------------------------------------------ Table B: profit and LP loss, three forks
    rows = []
    for w, c in specs:
        r = {"Window": w, "Specification": SPEC_NAMES[c]}
        for f in FORKS:
            r[f"{f}: arb profit"] = fmt(*core[f][(w, c)]["prof"])
            r[f"{f}: LP loss"] = fmt(*core[f][(w, c)]["loss"])
        rows.append(r)
    tB = pd.DataFrame(rows)
    open(os.path.join(OUT, "tableB_profit_loss.md"), "w").write(tB.to_markdown(index=False))

    # ------------------------------------------------ stacked panel: log Δt continuous, fork-specific controls
    stacked = {}
    for w, sub in SUBS.items():
        parts = []
        for f, cfg in FORKS.items():
            p = pd.read_parquet(os.path.join(cfg["bundle"], sub, "hourly_panel.parquet"))
            p = p[p.pool.isin(CORE)].copy(); p["fork"] = f
            p["log_dt"] = np.log(np.where(p["post"] == 1, cfg["dt"][1], cfg["dt"][0]))
            parts.append(p)
        d = pd.concat(parts, ignore_index=True)
        d = d[(d.overshoot_strict_bps > 0) & (d.sigma_ps > 0) & (d.liq_mean > 0) & (d.volume > 0)].replace([np.inf, -np.inf], np.nan).dropna(subset=["overshoot_strict_bps", "sigma_ps"])
        d["fp"] = d["fork"] + ":" + d["pool"]; d["cl"] = d["fork"] + ":" + d["day"].astype(str)
        res = {}
        for name, extra in (("σ", ""), ("σ+L+vol", " + np.log(liq_mean) + np.log(volume)"),
                            ("σ+L+vol+趋势", " + np.log(liq_mean) + np.log(volume) + t_days:C(fork)")):
            f1 = "np.log(overshoot_strict_bps) ~ log_dt + np.log(sigma_ps):C(fork) + C(hod) + C(fp)" + extra
            m = smf.ols(f1, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["cl"]})
            f2 = "np.log(overshoot_strict_bps) ~ log_dt:C(fork) + np.log(sigma_ps):C(fork) + C(hod) + C(fp)" + extra
            m2 = smf.ols(f2, data=d).fit(cov_type="cluster", cov_kwds={"groups": d["cl"]})
            names = [k for k in m2.params.index if k.startswith("log_dt:C(fork)")]
            # Wald test of equal elasticities across forks
            R = np.zeros((2, len(m2.params))); idx = [list(m2.params.index).index(k) for k in names]
            R[0, idx[0]] = 1; R[0, idx[1]] = -1; R[1, idx[1]] = 1; R[1, idx[2]] = -1
            wt = m2.wald_test(R, scalar=True)
            res[name] = {"elasticity": m.params["log_dt"], "se": m.bse["log_dt"], "n": int(m.nobs),
                         "by_fork": {k.split("[T.")[1].rstrip("]") if "[T." in k else k.split("[")[1].rstrip("]"): (m2.params[k], m2.bse[k]) for k in names},
                         "p_equal": float(wt.pvalue)}
            print(w, name, f"elasticity {m.params['log_dt']:.3f} ({m.bse['log_dt']:.3f}) n={int(m.nobs)}",
                  {k: f"{v[0]:.2f} ({v[1]:.2f})" for k, v in res[name]["by_fork"].items()}, f"p_equal={wt.pvalue:.2f}")
        stacked[w] = res
    rows = []
    for w, res in stacked.items():
        for name, r in res.items():
            rows.append({"Window": w, "Specification": SPEC_NAMES[name], "elasticity to Δt (pred. 0.5)": fmt(r["elasticity"], r["se"]).replace("−", "-"),
                         "t vs 0.5": f"{(r['elasticity'] - 0.5) / r['se']:+.1f}",
                         **{f"{k}": f"{v[0]:.2f} ({v[1]:.2f})" for k, v in r["by_fork"].items()},
                         "equal elasticities (p)": f"{r['p_equal']:.2f}", "N": f"{r['n']:,}"})
    tC = pd.DataFrame(rows)
    open(os.path.join(OUT, "tableC_stacked.md"), "w").write(tC.to_markdown(index=False))
    json.dump({w: {k: {"elasticity": v["elasticity"], "se": v["se"], "n": v["n"], "p_equal": v["p_equal"],
                       "by_fork": {a: list(b) for a, b in v["by_fork"].items()}} for k, v in res.items()} for w, res in stacked.items()},
              open(os.path.join(OUT, "stacked.json"), "w"), indent=1)

    # ------------------------------------------------ Figure: three forks, estimates vs prediction + elasticities
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), gridspec_kw={"width_ratios": [3, 2]})
    ax = axes[0]; n = len(specs); ys = np.arange(n)[::-1]
    offs = {"Lorentz": 0.22, "Maxwell": 0.0, "Fermi": -0.22}
    for i, (w, c) in enumerate(specs):
        for f, cfg in FORKS.items():
            b, se = core[f][(w, c)]["over"]
            ax.errorbar(b, ys[i] + offs[f], xerr=1.96 * se, fmt=cfg["marker"], color=cfg["color"], ms=4.5, capsize=2, lw=1)
    for f, cfg in FORKS.items():
        ax.axvline(th[f], color=cfg["color"], ls="--", lw=1)
    ax.axvline(0, color=GRID, lw=1)
    ax.set_yticks(ys); ax.set_yticklabels([f"{w}, {SPEC_NAMES[c]}" for w, c in specs], fontsize=8, color=INK)
    ax.set_xlabel("post coefficient, log overshoot at arbitrage (strict); 95% CI", fontsize=8.5, color=INK2)
    ax.text(th["Lorentz"] - 0.012, -1.9, "Lorentz/Maxwell\nprediction −0.347", color=INK2, fontsize=7.5, ha="right", va="bottom")
    ax.text(th["Fermi"] + 0.012, -1.9, "Fermi\nprediction −0.255", color=C_F, fontsize=7.5, ha="left", va="bottom")
    ax.set_ylim(-2.0, n - 0.3); ax.set_xlim(-0.75, 0.15)
    ax.set_title("Three forks, identical specifications", fontsize=9.5, color=INK, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)
    ax = axes[1]
    for i, (w, c) in enumerate(specs):
        for f, cfg in FORKS.items():
            b, se = core[f][(w, c)]["over"]
            ax.errorbar(b / dlog[f], ys[i] + offs[f], xerr=1.96 * se / abs(dlog[f]), fmt=cfg["marker"], color=cfg["color"], ms=4.5, capsize=2, lw=1)
    ax.axvline(0.5, color=INK2, ls=":", lw=1)
    ax.set_yticks(ys); ax.set_yticklabels([""] * n); ax.set_xlim(0, 1.1); ax.set_ylim(-2.0, n - 0.3)
    ax.set_xlabel("elasticity of overshoot to Δt (√Δt law = 0.5); 95% CI", fontsize=8.5, color=INK2)
    ax.set_title("Same estimates as elasticities", fontsize=9.5, color=INK, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)
    fig.legend(handles=[Line2D([], [], marker=c["marker"], color=c["color"], ls="", label=c["label"]) for c in FORKS.values()],
               loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(OUT, "fig_three_forks.png"), dpi=200)
    plt.close(fig)

    # ------------------------------------------------ Figure: dose-response curve (levels): log overshoot/σ^0.5 vs log Δt by pool & regime
    rows = []
    for f, cfg in FORKS.items():
        p = pd.read_parquet(os.path.join(cfg["bundle"], SUBS["±14 d"], "hourly_panel.parquet"))
        for pool in CORE:
            d = p[p.pool == pool]
            for post in (0, 1):
                s = d[d.post == post]
                sig = np.sqrt(s.rv.sum() / (len(s) * 3600))
                ov = np.average(s.overshoot_strict_bps.fillna(0), weights=s.n_arb_strict)
                rows.append({"fork": f, "pool": pool, "post": post, "dt": cfg["dt"][post], "sigma": 1e4 * sig, "over": ov, "over_adj": ov / (1e4 * sig)})
    lv = pd.DataFrame(rows); lv.to_csv(os.path.join(OUT, "levels_14d.csv"), index=False)
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    mk = {"BTCB-USDT-500": "o", "ETH-USDT-500": "s", "WBNB-USDT-500": "^"}
    for pool in CORE:
        s = lv[lv.pool == pool].sort_values("dt")
        for f, cfg in FORKS.items():
            ss = s[s.fork == f]
            ax.plot(ss["dt"], ss["over_adj"], marker=mk[pool], color=cfg["color"], ms=5, lw=1, ls="-")
    # reference slope 0.5 through the geometric centre
    x = np.array([0.4, 3.5]); ref = np.exp(np.mean(np.log(lv["over_adj"]))) * (x / np.exp(np.mean(np.log(lv["dt"])))) ** 0.5
    ax.plot(x, ref, color=INK2, ls=":", lw=1)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([0.45, 0.75, 1.5, 3.0]); ax.set_xticklabels(["0.45", "0.75", "1.5", "3.0"])
    ax.set_xlabel("block interval Δt (s), log scale", fontsize=9, color=INK2)
    ax.set_ylabel("strict overshoot / σ  (bp per bp/√s), log scale", fontsize=9, color=INK2)
    ax.set_title("Overshoot per unit volatility across the four block-interval regimes (±14-day windows)", fontsize=9, color=INK, loc="left")
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.legend(handles=[Line2D([], [], marker=mk[p], color=INK2, ls="", label=p.replace("-USDT-500", "/USDT 0.05%")) for p in CORE] +
                      [Line2D([], [], color=c["color"], lw=2, label=c["label"]) for c in FORKS.values()] +
                      [Line2D([], [], color=INK2, ls=":", label="slope 0.5 (√Δt)")], fontsize=7.5, frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_levels_dose_response.png"), dpi=200)
    plt.close(fig)
    print("written", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
