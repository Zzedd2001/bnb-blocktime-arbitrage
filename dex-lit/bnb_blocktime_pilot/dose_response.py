"""Maxwell vs Fermi: the same specifications side by side, a proportionality test (β_F = r·β_M with
r = ln(0.6)/ln(0.5) = 0.737), and a dot plot of estimates against the √Δt predictions.

    python dose_response.py --maxwell full_maxwell/extra --fermi full_fermi/extra --out full_fermi/extra

(the two input directories are outputs of core_analysis.py)."""
import os, json, argparse
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

C_PRE, C_POST, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e6e3"
ap = argparse.ArgumentParser()
ap.add_argument("--maxwell", default="full_maxwell/extra"); ap.add_argument("--fermi", default="full_fermi/extra")
ap.add_argument("--out", default=None)
_a = ap.parse_args()
M, F = _a.maxwell, _a.fermi
OUT = _a.out or F
TH_M, TH_F = 0.5 * np.log(0.75 / 1.5), 0.5 * np.log(0.45 / 0.75)
R = TH_F / TH_M


def setup_fonts():
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK" in f:
            font_manager.fontManager.addfont(f)
    for name in ("Noto Sans CJK SC", "Noto Sans CJK JP", "DejaVu Sans"):
        if any(name == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def load(d):
    cp = pd.read_csv(os.path.join(d, "core_pooled_raw.csv"))
    rd = pd.read_csv(os.path.join(d, "rd_jump.csv"))
    rows = []
    for _, r in cp.iterrows():
        if r["控制"] == "σ+L+vol+池别趋势":
            continue
        rows.append({"设定": f"{r['窗口']}，{r['控制']}", "b_over": r["_b_over"], "se_over": r["_se_over"],
                     "b_prof": r["_b_prof"], "se_prof": r["_se_prof"], "b_loss": r["_b_loss"], "se_loss": r["_se_loss"]})
    # RD jumps (overshoot / profit / loss) from rd_jump.csv text cells
    def parse(cell):
        b = float(cell.split(" ")[0].replace("*", "")); se = float(cell.split("(")[1].rstrip(")"))
        return b, se
    for w in ("±30 d", "±14 d"):
        sub = rd[rd["窗口"] == w].set_index("被解释变量")
        bo, so = parse(sub.loc["log 越界幅度（严格）", "跳跃（post）"])
        bp, sp = parse(sub.loc["log 套利者利润", "跳跃（post）"])
        bl, sl = parse(sub.loc["log LP 损失（总）", "跳跃（post）"])
        rows.append({"设定": f"{w}，RD 跳跃（两侧斜率）", "b_over": bo, "se_over": so, "b_prof": bp, "se_prof": sp, "b_loss": bl, "se_loss": sl})
    return pd.DataFrame(rows)


def star(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def main():
    from scipy import stats
    setup_fonts()
    m, f = load(M), load(F)
    t = m.merge(f, on="设定", suffixes=("_M", "_F"))
    rows = []
    for _, r in t.iterrows():
        d = r["b_over_F"] - R * r["b_over_M"]
        se = np.sqrt(r["se_over_F"] ** 2 + (R * r["se_over_M"]) ** 2)
        p = 2 * (1 - stats.norm.cdf(abs(d / se)))
        rows.append({"设定": r["设定"],
                     "Maxwell 越界幅度": f"{r['b_over_M']:+.3f} ({r['se_over_M']:.3f})", "占理论 −0.347": f"{r['b_over_M'] / TH_M:.0%}",
                     "Fermi 越界幅度": f"{r['b_over_F']:+.3f} ({r['se_over_F']:.3f})", "占理论 −0.255": f"{r['b_over_F'] / TH_F:.0%}",
                     "Fermi/Maxwell 比（预测 0.74）": f"{r['b_over_F'] / r['b_over_M']:.2f}",
                     "β_F − 0.74·β_M": f"{d:+.3f}{star(p)} ({se:.3f})",
                     "Maxwell 利润": f"{r['b_prof_M']:+.3f} ({r['se_prof_M']:.3f})", "Fermi 利润": f"{r['b_prof_F']:+.3f} ({r['se_prof_F']:.3f})",
                     "Maxwell LP 损失": f"{r['b_loss_M']:+.3f} ({r['se_loss_M']:.3f})", "Fermi LP 损失": f"{r['b_loss_F']:+.3f} ({r['se_loss_F']:.3f})"})
    tab = pd.DataFrame(rows)
    open(os.path.join(OUT, "dose_response.md"), "w").write(tab.to_markdown(index=False))
    tab.to_csv(os.path.join(OUT, "dose_response.csv"), index=False)
    print(tab.to_string())

    # figure: estimates vs theory
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [3, 2]})
    ax = axes[0]
    n = len(t)
    ys = np.arange(n)[::-1]
    for i, (_, r) in enumerate(t.iterrows()):
        y = ys[i]
        ax.errorbar(r["b_over_M"], y + 0.15, xerr=1.96 * r["se_over_M"], fmt="o", color=C_PRE, ms=5, capsize=2, lw=1)
        ax.errorbar(r["b_over_F"], y - 0.15, xerr=1.96 * r["se_over_F"], fmt="s", color=C_POST, ms=5, capsize=2, lw=1)
    ax.axvline(TH_M, color=C_PRE, ls="--", lw=1); ax.axvline(TH_F, color=C_POST, ls="--", lw=1)
    ax.axvline(0, color=GRID, lw=1)
    ax.set_yticks(ys); ax.set_yticklabels(t["设定"], fontsize=8, color=INK)
    ax.set_xlabel("log 越界幅度（严格套利）的 post 系数，95% 置信区间", fontsize=9, color=INK2)
    ax.text(TH_M - 0.01, -0.9, "Maxwell 理论\n−0.347", color=C_PRE, fontsize=8, ha="right", va="bottom")
    ax.text(TH_F + 0.01, -0.9, "Fermi 理论\n−0.255", color=C_POST, fontsize=8, ha="left", va="bottom")
    ax.set_ylim(-1.2, n - 0.3)
    ax.set_title("两次分叉、同一套设定：越界幅度的估计值与 √Δt 预测", fontsize=10, color=INK, loc="left")
    ax.set_xlim(-0.55, 0.1)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)
    # right: ratio to theory
    ax = axes[1]
    for i, (_, r) in enumerate(t.iterrows()):
        y = ys[i]
        ax.plot(r["b_over_M"] / TH_M, y + 0.15, "o", color=C_PRE, ms=5)
        ax.plot(r["b_over_F"] / TH_F, y - 0.15, "s", color=C_POST, ms=5)
    ax.axvline(1, color=INK2, ls=":", lw=1)
    ax.set_yticks(ys); ax.set_yticklabels([""] * n)
    ax.set_xlabel("估计值 / 理论值（1 = 与 √Δt 预测吻合）", fontsize=9, color=INK2)
    ax.set_title("占理论值的比例", fontsize=10, color=INK, loc="left")
    ax.set_xlim(0, 1.4)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([], [], marker="o", color=C_PRE, ls="", label="Maxwell（1.5 → 0.75 s）"),
                        Line2D([], [], marker="s", color=C_POST, ls="", label="Fermi（0.75 → 0.45 s）")],
               loc="lower center", ncol=2, fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(OUT, "fig_dose_response.png"), dpi=160)
    print("figure written")


if __name__ == "__main__":
    main()
