#!/usr/bin/env python3
"""make_v6.py — assemble the revised manuscript (v6, response to the Digital Finance referee report).

Body sections are written in v6/*.md with symbolic labels [[T:key]] / [[F:key]] (appendix items carry the appendix letter
in the key, e.g. [[T:B:grid]]); the appendices are taken from paper_df.md (v5) and edited here; tables computed for the
revision come from tables_v6/.  Labels are numbered in order of first caption appearance (Arabic in the body, letter +
counter in each appendix) and every reference is replaced.  Output: paper_v6.md
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import os
import re

P = ROOT + "/paper"
V6 = f"{P}/v6"
T6 = f"{P}/tables_v6"
old = open(f"{P}/paper_df.md", encoding="utf-8").read()


def rd(name):
    return open(os.path.join(V6, name), encoding="utf-8").read().strip() + "\n"


def block(text, start, end):
    """text between the line starting with `start` and the line starting with `end` (exclusive)."""
    i = text.index(start)
    j = text.index(end, i + 1)
    return text[i:j]


def table_only(text, caption_start):
    """caption line + following blank + table lines."""
    i = text.index(caption_start)
    lines = text[i:].split("\n")
    out = [lines[0], ""]
    k = 1
    while k < len(lines) and not lines[k].strip():
        k += 1
    while k < len(lines) and lines[k].startswith("|"):
        out.append(lines[k])
        k += 1
    return "\n".join(out) + "\n"


def rep(text, a, b, count=None):
    assert a in text, a[:80]
    return text.replace(a, b) if count is None else text.replace(a, b, count)


def md_table(path):
    return open(path, encoding="utf-8").read().strip() + "\n"


# ---------------------------------------------------------------- body
body = "".join(rd(f) for f in ["00_front.md", "01_intro.md", "02_setting.md", "03_model.md", "04_data.md", "05_strategy.md",
                               "06a_results.md", "06b_results.md", "07_discussion.md", "08_related_conclusion.md", "09_references.md"])

# ---------------------------------------------------------------- move two results tables to Appendix D (body length)
def cut_table(text, cap_start):
    i = text.index(cap_start)
    j = text.index("\n\n", text.index("\n|", i))          # end of the table block (first blank line after the table rows)
    # extend to the end of contiguous table rows
    lines = text[i:].split("\n")
    k = 1
    while k < len(lines) and not lines[k].strip():
        k += 1
    while k < len(lines) and lines[k].startswith("|"):
        k += 1
    blk = "\n".join(lines[:k]) + "\n"
    return text.replace(blk, ""), blk

body, tbl_resp = cut_table(body, "**Table [[T:resp]].")
body, tbl_comp = cut_table(body, "**Table [[T:comp]].")
tbl_resp = tbl_resp.replace("[[T:resp]]", "[[T:D:regimes]]")
tbl_comp = tbl_comp.replace("[[T:comp]]", "[[T:D:compmain]]")
body = body.replace("[[T:resp]]", "[[T:D:regimes]]").replace("[[T:comp]]", "[[T:D:compmain]]")

# ---------------------------------------------------------------- Appendix A
A = block(old, "## Appendix A.", "## Appendix B.")
A = rep(A, "## Appendix A. Data validation and the construction of the reference prices", "## Appendix A. Descriptive statistics, data validation and the reference prices")
desc = table_only(old, "**Table 3. Descriptive statistics, core pools, ±14 days around each fork (trade reference).**")
desc = desc.replace("**Table 3.", "**Table [[T:A:desc]].")
A = rep(A, "**Timestamps.**", "**Descriptive statistics.** Table [[T:A:desc]] reports the hourly means of the main variables for the three core pools in the ±14-day windows around each fork (Section 4.4).\n\n" + desc + "\n**Timestamps.**")
A = rep(A, "and the reference used for mark-outs at t + 5 s and t + 30 s is found in the same way", "and the reference used for the 30-second mark-out of Section 4.3 is found in the same way")
A = rep(A, "reported in Tables 7 and C2", "reported in Tables [[T:C:gap]] and [[T:C:wedge]]")
blocks_fig = ("**Figure [[F:A:blocks]]. Block interval and gas limits around the three forks.** Hourly mean block interval (black, left axis) with the per-block gas limit and gas used (right axis), ±30 days around each fork. "
              "Lorentz halved the gas limit with the interval and validators raised it back within a month; Maxwell was preceded by a gas-limit increase on 4 June 2025 and accompanied by a cut from 125 M to 75 M; Fermi cut the limit from 100 M to 55 M. "
              "Gas utilisation stays well below the limit throughout; the rise in gas used after Lorentz is the start of the Binance Alpha activity wave.\n\n![Figure [[F:A:blocks]]](figures_v6/fig1_block_interval.png)\n\n")
A = rep(A, "**Swap logs.**", blocks_fig + "**Swap logs.**")
A = rep(A, "Where the log provider returned block timestamps (the 2.33 million swaps of the WBNB/USDT 0.05% pool in the Maxwell sample, for which the log provider returned block timestamps; all swap blocks in the Lorentz and Fermi samples via HyperSync), they agree with the reconstruction without exception.",
        "Where the log provider returned block timestamps (the 2.33 million swaps of the WBNB/USDT 0.05% pool in the Maxwell sample; all swap blocks in the Lorentz and Fermi samples via HyperSync), they agree with the reconstruction without exception.")
A = rep(A, "**Table A1.", "**Table [[T:A:ratios]].")
A = rep(A, "**Table A2.", "**Table [[T:A:sigel]].")
A = rep(A, "Figure A1 plots", "Figure [[F:A:sig]] plots")
A = rep(A, "**Figure A1.", "**Figure [[F:A:sig]].")
A = rep(A, "![Figure A1](figures_v41/fig4_sigma_overshoot.png)", "![Figure [[F:A:sig]]](figures_v6/figA1_sigma_overshoot.png)")
A = rep(A, "the raw overshoot tracks volatility, which is why windows with stable volatility are preferred and why the ±30-day Fermi window is used only with a trend.",
        "the raw overshoot tracks volatility, which is why the main specification controls for volatility hour by hour and estimates the jump at the fork net of a trend.")
A = rep(A, "it documents the volatility regimes that motivate the choice of windows and controls in Section 5.", "it documents the volatility regimes discussed in Section 5.2.")

# ---------------------------------------------------------------- Appendix B
B = block(old, "## Appendix B.", "## Appendix C.")
B = rep(B, "## Appendix B. Additional estimates", "## Appendix B. The full grid of specifications and additional estimates")
intro_old = block(B, "This appendix collects", "**Table B1.")
intro_new = ("This appendix reports every window and specification for the three headline outcomes (Tables [[T:B:grid]] and [[T:B:profloss]]) and their fake-fork placebos (Table [[T:B:placebo]]), "
             "the stacked three-fork panel (Table [[T:B:stacked]]), the four arbitrage classifications under four windows and specifications (Table [[T:B:class]]), "
             "the pool-by-pool estimates (Table [[T:B:pool]]), the decomposition of the LPs' loss (Table [[T:B:decomp]]), the heterogeneity of the overshoot effect (Table [[T:B:het]]), "
             "the matched-pair estimates (Table [[T:B:matched]]), the grid on bot flow with public routers excluded (Table [[T:B:bots]]) and the price-efficiency statistics (Table [[T:B:eff]]). "
             "All estimates are for the three core 0.05% pools pooled with pool fixed effects, with day-clustered standard errors; the RD rows of Tables [[T:B:grid]] and [[T:B:profloss]] are the main specification of Table [[T:main]].\n\n")
grid_cap = ("**Table [[T:B:grid]]. Effect of the block-interval reduction on the log overshoot at strict arbitrage: all windows and specifications, three core 0.05% pools pooled, trade reference.** "
            "Cells are the coefficient on Post with day-clustered standard errors and, in brackets, the estimate as a share of the prediction (−0.347 for Lorentz and Maxwell, −0.255 for Fermi). "
            "Elasticity = β/ln(Δt₁/Δt₀), predicted 0.5; the pooled elasticity is the inverse-variance-weighted mean across forks and the last column the p-value of a χ² test that the three elasticities are equal. "
            "All specifications include log σ and hour-of-day fixed effects; \"+ log L + log volume\" adds active liquidity and volume; \"+ linear trend\" adds a trend in days; \"RD jump\" adds a trend with separate slopes before and after the fork, on top of the liquidity and volume controls (the main specification in the ±30-day window). "
            "Standard errors in parentheses; ∗, ∗∗ and ∗∗∗ denote significance at the 10%, 5% and 1% levels.\n\n")
pl_cap = ("**Table [[T:B:profloss]]. Effect of the block-interval reduction on log arbitrageur profit and log LP gross loss: all windows and specifications, core pools pooled (trade reference).** "
          "Same specifications as Table [[T:B:grid]]; predictions are θ for profit and −s·(1 − √(Δt₁/Δt₀)) for the loss. Standard errors in parentheses; ∗, ∗∗ and ∗∗∗ denote significance at the 10%, 5% and 1% levels.\n\n")
plc_cap = ("**Table [[T:B:placebo]]. Fake-fork placebos on the pre-period, core pools pooled (trade reference).** The pre-period of each window is split at its midpoint and the specification is re-estimated with a fictitious Post at the split; "
           "in the RD rows the trend is allowed to change slope at the fictitious fork. Standard errors in parentheses; ∗, ∗∗ and ∗∗∗ denote significance at the 10%, 5% and 1% levels.\n\n")
stacked = table_only(old, "**Table 5. Stacked panel:")
stacked = stacked.replace("**Table 5.", "**Table [[T:B:stacked]].")
cls_cap = ("**Table [[T:B:class]]. Sensitivity of the fork effect to the classification of arbitrages, four windows and specifications, core pools pooled.** "
           "Four definitions of the arbitrage overshoot estimated with the same specifications on the same pool-hours (Section 4.3): all identified arbitrages; strict arbitrages (the headline); "
           "strict arbitrages of arbitrage contracts, public routers excluded; and CEX-triggered bot arbitrages. Cells are the coefficient on Post with day-clustered standard errors and, in brackets, "
           "the estimate as a share of the prediction. Standard errors in parentheses; ∗, ∗∗ and ∗∗∗ denote significance at the 10%, 5% and 1% levels.\n\n")
event_fig = ("**Figure [[F:B:event]]. Event study: daily means of residualised outcomes around the three forks.** Hourly observations of the three core pools are regressed on log σ, log L, log volume, hour-of-day and pool fixed effects (no Post term); "
             "residuals are averaged by day relative to the fork. Dashed lines are the pre- and post-fork means; the law's prediction is shown for the overshoot and profit.\n\n![Figure [[F:B:event]]](figures_v6/fig3_event_study.png)\n\n")
new_tables = (grid_cap + md_table(f"{T6}/table_grid_overshoot.md") + "\n" + pl_cap + md_table(f"{T6}/table_grid_profit_loss.md") + "\n" + plc_cap + md_table(f"{T6}/table_grid_placebo.md") + "\n"
              + event_fig + stacked + "\n" + cls_cap + md_table(f"{T6}/table_classification_full.md") + "\n")
B = B.replace(intro_old, intro_new + new_tables)
for a, b in [("B1", "B:pool"), ("B2", "B:decomp"), ("B3", "B:het"), ("B4", "B:matched"), ("B5", "B:bots")]:
    B = rep(B, f"**Table {a}.", f"**Table [[T:{b}]].")
B = rep(B, "Specifications and columns as in Table 4; the panel is", "Specifications and columns as in Table [[T:B:grid]]; the panel is")
B = rep(B, "reproduces Table 4 to ±0.001", "reproduces Table [[T:B:grid]] to ±0.001")
B = rep(B, "the fake-fork placebos of Table 9 on bot flow", "the fake-fork placebos of Table [[T:B:placebo]] on bot flow")
B = rep(B, "it differs from Table 9 by at most 0.002", "it differs from Table [[T:B:placebo]] by at most 0.002")
eff_tab = ("\n**Table [[T:B:eff]]. Price-efficiency statistics on the 1-second grid, ±30-day windows (pre → post).** Episode length is the mean number of consecutive seconds with |dev| > γ; outside band is the share of seconds with |dev| > γ; half-life is from an AR(1) fit to the deviation.\n\n"
           + "\n".join(l for l in table_only(old, "**Table 8. Price-efficiency statistics").split("\n")[2:]) + "\n")
B = B.rstrip("\n") + "\n" + eff_tab
# the stacked table's markdown is a plain copy; fix its header wording for the appendix
B = rep(B, "The three columns in the middle report fork-specific elasticities", "The three columns in the middle report fork-specific elasticities")

# ---------------------------------------------------------------- Appendix C
C = block(old, "## Appendix C.", "## Appendix D.")
C = rep(C, "This appendix collects the estimates that compare the two reference prices (Section 6.2) and the two alignments of the trade reference (Section 6.8). Table C1 places the candle-reference estimates next to the trade-reference estimates for the placebo-clean specifications and Table C2 measures the wedge between the two references at each fork; Table C3 reproduces the full set of candle-reference estimates; Tables C4–C6 report the estimates with the reference taken 250 ms before the block timestamp.",
        "This appendix collects the estimates that compare the two reference prices (Section 6.2) and the two alignments of the trade reference (Section 6.5). Table [[T:C:cmp]] places the candle-reference estimates next to the trade-reference estimates for the main specification and selected ±14-day and ±30-day specifications, Table [[T:C:wedge]] measures the wedge between the two references at each fork and Table [[T:C:gap]] the reference gap regime by regime; Table [[T:C:candle]] reproduces the full grid with the candle reference; Tables [[T:C:lag]]–[[T:C:lagel]] report the estimates with the reference taken 250 ms before the block timestamp.")
C = rep(C, "**Table C1. The same estimates with the 1-second candle reference and the trade reference, placebo-clean specifications, core pools pooled.**",
        "**Table [[T:C:cmp]]. The same estimates with the 1-second candle reference and the trade reference, main specification and selected other specifications, core pools pooled.**")
C = rep(C, "the trade-reference overshoot estimates are those of Table 4.", "the trade-reference overshoot estimates are those of Table [[T:B:grid]].")
C = rep(C, "**Table C2.", "**Table [[T:C:wedge]].")
wedge_fig = ("**Figure [[F:C:wedge]]. The wedge between the two references, day by day.** Daily mean of log(strict overshoot with the trade reference / with the candle reference) in the three core pools (black, left axis) and the daily mean reference gap |candle/trade − 1| (blue, right axis), ±30 days around each fork.\n\n"
             "![Figure [[F:C:wedge]]](figures_v6/fig4_wedge.png)\n\n")
gap_rows = []
for l in table_only(old, "**Table 7. LPs' loss relative to fee income").split("\n"):
    if l.startswith("| Statistic") or l.startswith("|:--") or l.startswith("| Reference gap") or l.startswith("| σ (bp"):
        gap_rows.append(l)
gap_tab = ("**Table [[T:C:gap]]. The reference gap and volatility across the six block-interval regimes, core pools (±30-day half-windows).** The reference gap is |candle reference / trade reference − 1| per swap, averaged (mean) or root-mean-squared over swaps; σ is the mean hourly Binance realised volatility expressed per second.\n\n"
           + "\n".join(gap_rows) + "\n")
C = rep(C, "\n\nFor comparison with the earlier version of this paper and with studies", "\n\n" + wedge_fig + gap_tab + "\nFor comparison with studies")
C = rep(C, "Table C3 reproduces the pooled core-pool overshoot estimates of Table 4 with the 1-second candle reference.", "Table [[T:C:candle]] reproduces the pooled core-pool overshoot estimates of Table [[T:B:grid]] with the 1-second candle reference.")
C = rep(C, "the difference from Table 4 is the wedge of Section 6.2.", "the difference from Table [[T:B:grid]] is the wedge of Section 6.2.")
C = rep(C, "**Table C3.", "**Table [[T:C:candle]].")
C = rep(C, "Specifications and columns as in Table 4; the reference is the close", "Specifications and columns as in Table [[T:B:grid]]; the reference is the close")
C = rep(C, "**Table C4. Reference at the block timestamp (lag 0) and 250 ms before it (lag 250): placebo-clean specifications, core pools pooled.**",
        "**Table [[T:C:lag]]. Reference at the block timestamp (lag 0) and 250 ms before it (lag 250): main specification and the ±14-day specifications, core pools pooled.**")
C = rep(C, "the last block refits the latency-floor model of Table 12 with the lag-250 estimates for Maxwell and Fermi and the lag-0 estimate for Lorentz, whose pre-fork timestamps are whole seconds.",
        "the last block refits the latency-floor model of Table [[T:lf]] to the main-specification estimates with the lag-250 values for Maxwell and Fermi and the lag-0 value for Lorentz, whose pre-fork timestamps are whole seconds.")
C = rep(C, "| set A (levels-type) | | | 0.88 | 0.54–1.42 | 11.1, 0.00 | 77.4 | −0.092 | 0.81 | |\n| set B (RD-type) | | | 0.46 | 0.20–0.88 | 0.11, 0.95 | 18.5 | −0.142 | 0.71 | |",
        "| main specification (RD jump, ±30 d) | | | 0.81 | 0.44–1.42 | 4.81, 0.09 | 44.3 | −0.098 | 0.80 | |")
C = rep(C, "**Table C5.", "**Table [[T:C:lagall]].")
C = rep(C, "**Table C6.", "**Table [[T:C:lagel]].")
C = rep(C, "the last two columns repeat the lag-0 values of Table 4.", "the last two columns repeat the lag-0 values of Table [[T:B:grid]].")

# ---------------------------------------------------------------- Appendix D
D = block(old, "## Appendix D.", "## Appendix E.")
D = rep(D, "## Appendix D. Opening times: construction, validation and address-level statistics", "## Appendix D. Opening times, operators and simulations: construction, validation and address-level statistics")
D = rep(D, "The simulation also reproduces the component pattern of Section 6.9 with no behaviour beyond a fixed latency:", "The simulation also reproduces the component pattern of Section 6.7 with no behaviour beyond a fixed latency:")
sim_par = ("\n\n**Simulated elasticities to volatility.** The same simulation (fixed latencies of 250, 500 and 900 ms, no behavioural response) run with the reference volatility scaled by 0.5, 0.7, 1, 1.4 and 2 gives the mechanical elasticities of the components to σ discussed in Section 6.6 (Table [[T:D:sim]]): "
           "over the five runs the log-log slope is 0.90–0.91 for the movement component M, −0.01 to +0.03 for the crossing jump J, 0.77–0.80 for the number of arbitrages and 0.36–0.41 for the overshoot of the arbitrages that occur.\n\n"
           "**Table [[T:D:sim]]. Simulated overshoot and its components as the reference volatility is scaled, fixed latencies, no behavioural response.** Two days at 1.5-second blocks (pre) and two days at 0.75-second blocks (post); the number of arbitrages that occur, and the means of the overshoot and of its components over the CEX-triggered ones.\n\n"
           "| Regime | Δt (s) | σ scale | Arbitrages | Overshoot (bp) | J (bp) | M (bp) |\n|:--|--:|--:|--:|--:|--:|--:|\n"
           "| pre | 1.5 | ×0.5 | 14,936 | 3.08 | 2.18 | 0.90 |\n| pre | 1.5 | ×0.7 | 19,719 | 3.02 | 1.83 | 1.20 |\n| pre | 1.5 | ×1.0 | 26,484 | 3.33 | 1.66 | 1.67 |\n| pre | 1.5 | ×1.4 | 34,233 | 4.07 | 1.79 | 2.27 |\n| pre | 1.5 | ×2.0 | 43,377 | 5.36 | 2.17 | 3.19 |\n"
           "| post | 0.75 | ×0.5 | 19,695 | 2.61 | 1.98 | 0.63 |\n| post | 0.75 | ×0.7 | 26,152 | 2.47 | 1.67 | 0.81 |\n| post | 0.75 | ×1.0 | 34,965 | 2.71 | 1.55 | 1.16 |\n| post | 0.75 | ×1.4 | 45,823 | 3.25 | 1.69 | 1.55 |\n| post | 0.75 | ×2.0 | 59,349 | 4.26 | 2.08 | 2.18 |\n")
ops_par = ("\n**Operator identification.** A *public* contract is one called by at least 30 distinct signing accounts with a median of at most two strict arbitrages each (the PancakeSwap SmartRouter in the Fermi window: 501 accounts, median one); every other contract is *private*, "
           "including the arbitrage bots that rotate a fixed pool of hot wallets, each of which signs tens to thousands of arbitrages (one contract signs from exactly 41 wallets, another from 50, a third from up to 189). "
           "Private contracts and the wallets that sign for them form a bipartite graph whose connected components are the operators; an arbitrage through a public contract is attributed to the operator of the account that sent it if that account also uses a private contract, "
           "to the account itself as an operator if it sent at least twenty such arbitrages in the window, and to anonymous flow otherwise. Router flow of both kinds is 6–23% of strict arbitrages across the three windows (one-off accounts 3–13%, persistent accounts 4–11%) "
           "and matters only in the two WBNB pools, where it is 19–50% of strict arbitrages in the Lorentz and Maxwell windows (1–4% in the ETH and BTCB pools, 7–11% at Fermi); Table [[T:D:router]] reports its profile.\n\n"
           "**Concentration, entry and organisation.** In each core pool and regime the Herfindahl index of strict arbitrages by contract is 0.15–0.43 and changes in no systematic direction at the forks (Table [[T:D:contracts]]). "
           "Merging contracts into operators changes none of this (Table [[T:D:ops]]): in all eighteen pool-regimes of the core pools the share of the largest operator equals that of the largest contract to two decimals, the top-three share is at most 0.09 higher, "
           "the Herfindahl index at most 0.04 higher and the number covering 90% of arbitrages at most one lower, because multi-contract operators hold 3–42% of bot arbitrages, mostly the smaller ones. "
           "Contracts that first appear after a fork account for 1–12% of post-fork arbitrages and operators for 1–11% (Table [[T:D:entry]]). The largest operators sign from fixed pools of wallets — exactly 20 in every week of the Lorentz and Maxwell windows and exactly 41 in the Fermi window for the largest BTCB-pool arbitrageur, "
           "50 throughout for the largest ETH-pool arbitrageur, and exactly 100 in every week before Fermi and 58–156 a week after it (189 in all) for the fastest of the operators new since the Maxwell window (Tables [[T:D:top]] and [[T:D:wallets]]); "
           "contracts signing from at least 30 wallets executed 27% and 17% of bot arbitrages before and after Lorentz, 14% and 26% around Maxwell, and 52% and 53% around Fermi (Table [[T:D:wallets]]). "
           "Gas competition faded along the roadmap: the 90th percentile of the gas price paid by CEX-triggered bot arbitrages fell from 9.2 gwei before Lorentz to 0.7 gwei after Fermi, the share paying more than one and a half times the median fell within the Lorentz window from 0.34 to 0.14 and within the Maxwell window from 0.40 to 0.17, "
           "and the median arbitrage is the fourth or fifth transaction of its block around Lorentz and Maxwell and the tenth around Fermi (Table [[T:D:gas]]).\n")
volctrl = ("\n**Volatility and competition with volume and liquidity controls.** Table [[T:D:volctrl]] repeats the within-hour elasticities of Table [[T:volcomp]] with log volume and log liquidity added, pooling the two regimes of each fork with a regime fixed effect.\n\n"
           "**Table [[T:D:volctrl]]. Elasticities of the hourly competition statistics and overshoot components to realised volatility, with volume and liquidity controls.** Hourly panel of CEX-triggered bot arbitrages in the three core pools (hours with at least 20 such arbitrages); coefficient on log σ with log volume, log liquidity, hour-of-day, pool and regime fixed effects, the two regimes of each fork pooled; day-clustered standard errors in parentheses.\n\n"
           "| Outcome | Lorentz | Maxwell | Fermi |\n|:--|:--|:--|:--|\n"
           "| Median τ (log) | −0.08 (0.03) | −0.04 (0.02) | −0.04 (0.02) |\n| 10th percentile of τ (log) | −0.19 (0.07) | −0.08 (0.06) | +0.02 (0.06) |\n| E[√τ] (log) | −0.06 (0.02) | −0.07 (0.02) | −0.08 (0.01) |\n"
           "| First-block share (level) | +0.02 (0.02) | +0.03 (0.02) | +0.05 (0.01) |\n| Active contracts (log) | +0.20 (0.05) | +0.06 (0.04) | +0.16 (0.05) |\n| Bot arbitrages (log) | +0.32 (0.06) | +0.48 (0.05) | +0.69 (0.06) |\n"
           "| Top-1 contract share (level) | −0.09 (0.02) | +0.02 (0.02) | −0.02 (0.01) |\n| Movement M (log) | +0.73 (0.22) | +0.36 (0.32) | +1.12 (0.27) |\n| Crossing jump J (log) | +0.09 (0.06) | −0.03 (0.06) | +0.02 (0.05) |\n| CEX-triggered overshoot (log) | +0.28 (0.04) | +0.19 (0.04) | +0.20 (0.04) |\n")
terc = ("\n**Table [[T:D:terc]]. Response times, first-block share and active contracts by within-regime tercile of realised volatility.** Hours of the three core pools pooled; terciles of σ within pool and regime; median of the hourly median response time (ms), mean first-block share and mean number of active arbitrage contracts per hour, CEX-triggered bot arbitrages.\n\n"
        "| Regime | Δt (s) | τ median, low σ | mid | high | First block, low σ | mid | high | Contracts/h, low | mid | high |\n|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|\n"
        "| Lorentz pre | 3.00 | 2,644 | 2,544 | 2,255 | 0.60 | 0.64 | 0.74 | 5.5 | 6.4 | 8.9 |\n| Lorentz post | 1.50 | 1,432 | 1,415 | 1,380 | 0.54 | 0.57 | 0.61 | 6.0 | 7.3 | 9.6 |\n"
        "| Maxwell pre | 1.50 | 1,258 | 1,258 | 1,190 | 0.64 | 0.65 | 0.71 | 6.2 | 6.8 | 8.8 |\n| Maxwell post | 0.75 | 761 | 736 | 712 | 0.50 | 0.52 | 0.56 | 7.4 | 8.5 | 10.2 |\n"
        "| Fermi pre | 0.75 | 634 | 623 | 585 | 0.64 | 0.67 | 0.71 | 7.0 | 8.1 | 10.0 |\n| Fermi post | 0.45 | 443 | 428 | 416 | 0.52 | 0.55 | 0.56 | 8.0 | 9.4 | 12.9 |\n")
D = rep(D, "\n\n**Table D1.", sim_par + volctrl + terc + ops_par + "\n**Response times and components.** Table [[T:D:regimes]] summarises the response times of CEX-triggered bot arbitrages in the three core pools across the six regimes (Section 6.7), Table [[T:D:resp]] gives the four liquid pools regime by regime, and Table [[T:D:compmain]] reports the fork effects on the components of the strict overshoot under the main specification and in the ±14-day window.\n\n" + tbl_resp + "\n" + tbl_comp + "\n**Table D1.")
D = rep(D, "**Table D1. Response times and latency intercepts, four liquid pools, six regimes, bot flow.** Columns as in Table 10;",
        "**Table [[T:D:resp]]. Response times and latency intercepts, four liquid pools, six regimes, bot flow.** Columns as in Table [[T:D:regimes]], with the median response time and the intercepts for sharp openings (crossing trade at least ½γ beyond the band edge);")
figd1 = block(D, "**Figure D1.", "**Table D2.")
lat_fig = ("**Figure [[F:D:lat]]. The arbitrageurs' latency across the six block-interval regimes.** Quantile intercepts ℓ̂ = Q_q(τ) − q·Δt of the response time of CEX-triggered arbitrages, for the tenth percentile (top) and the median (bottom), four liquid pools, with bootstrap 95% intervals. "
           "The shaded band is the latency implied by the fit of Table [[T:lf]] to the headline estimates (ℓ = 0.94 s, 95% interval 0.51–1.65 s) translated into a response latency (ℓ_t ≈ 0.42 s, 0.21–0.78 s; Section 7.2).\n\n![Figure [[F:D:lat]]](figures_v6/fig6_latency_intercepts.png)\n\n")
D = D.replace(figd1, lat_fig)
D = rep(D, "**Table D2.", "**Table [[T:D:impl]].")
D = rep(D, "the last column repeats the pool-level overshoot estimate of Table B1 (all flow, ±14 d, with liquidity and volume).", "the last column repeats the pool-level overshoot estimate of Table [[T:B:pool]] (all flow, ±14 d, with liquidity and volume).")
D = rep(D, "**Figure D2.", "**Figure [[F:D:twelve]].")
D = rep(D, "![Figure D2](figures_v41/figE2_twelve_point.png)", "![Figure [[F:D:twelve]]](figures_v6/figD1_twelve_point.png)")
D = rep(D, "| Overshoot estimate (Table B1)   |", "| Overshoot estimate (Table [[T:B:pool]])   |")
D = rep(D, "| Table B1 (all flow)   |", "| Table [[T:B:pool]] (all flow)   |")
D = rep(D, "**Table D3.", "**Table [[T:D:comp]].")
D = rep(D, "the last column repeats the estimate of Table B1, which includes the router flow;", "the last column repeats the estimate of Table [[T:B:pool]], which includes the router flow;")
for a, b in [("D4", "D:contracts"), ("D5", "D:traj"), ("D6", "D:ops"), ("D7", "D:entry"), ("D8", "D:gas"), ("D9", "D:top"), ("D10", "D:wallets"), ("D11", "D:router")]:
    D = rep(D, f"**Table {a}.", f"**Table [[T:{b}]].")
D = rep(D, "the change of the intercept is for the tenth percentile; the contract-level columns are computed on the arbitrages with transaction data (99.6% of strict arbitrages) and can differ from Table D4 by a millisecond.",
        "the change of the intercept is for the tenth percentile; the contract-level columns are computed on the arbitrages with transaction data (99.6% of strict arbitrages) and can differ from Table [[T:D:contracts]] by a millisecond.")
D = rep(D, "(Table D11 and Section 4.5)", "(Table [[T:D:router]] and Section 4.5)")
D = rep(D, "the aggregate strict-overshoot effect of Lorentz is −0.36 with it and −0.29 without it (Table 11). Tables 10, 11 and D1–D5 therefore use bot flow.",
        "the aggregate strict-overshoot effect of Lorentz in the ±14-day window with liquidity and volume is −0.36 with it and −0.29 without it (Tables [[T:B:grid]] and [[T:B:bots]]). Tables [[T:D:regimes]]–[[T:D:traj]] therefore use bot flow.")
D = rep(D, "Columns as in Table D4, at the contract level", "Columns as in Table [[T:D:contracts]], at the contract level")
assert "Table D" not in re.sub(r"\[\[T:D:[a-z]+\]\]", "", D).replace("Table [[", ""), [m.group(0) for m in re.finditer(r"Table D\d+", D)]

# ---------------------------------------------------------------- Appendix E
E = ("## Appendix E. Replication package\n\n"
     "All data are public: BNB Chain JSON-RPC (block headers, contract calls), Envio HyperSync and `eth_getLogs` (swap events) and Binance's public data archive (1-second candles and aggregate trades). "
     "The anonymised replication package that accompanies this submission contains (i) the data pipeline — timestamp reconstruction from sparse headers, event retrieval, alignment to both references, arbitrage identification, LP economics at both mark-out horizons, hourly panels, "
     "the reconstruction of opening and response times, the component panels, the retrieval of transaction senders and gas, and the merging of contracts into operators; (ii) the processed data underlying every result — the reconstructed block-timestamp tables, the hourly pool panels of the seven pools for the three ±30-day windows, "
     "the component panels of bot flow, the arbitrage-level tables with opening times, response times, trigger types and components, and the operator tables; (iii) the estimation scripts that produce every table and figure of the paper from the processed data, including the main specification and its placebos, the full grid, the classification sensitivity, "
     "the volatility–competition panel, the latency-floor fits, the response-time statistics and the simulations; and (iv) a manifest listing, for each table and figure, the script and the input files that generate it. "
     "Each fork's full sample can be rebuilt from scratch from the public sources on a laptop in a few hours, the aggregate-trade alignment adding 6–8 GB of downloads per fork; the estimation scripts run on the processed data in minutes. The package is released under an open-source licence and will be deposited in a public repository with a DOI on acceptance.\n")

doc = body + "\n" + A + "\n" + B + "\n" + C + "\n" + D + "\n" + E

# ---------------------------------------------------------------- numbering
counters = {}
assigned = {}
context = ""
for line in doc.split("\n"):
    m = re.match(r"^## Appendix ([A-Z])\.", line)
    if m:
        context = m.group(1)
        continue
    m = re.match(r"^\*\*(Table|Figure) \[\[(T|F):([^\]]+)\]\]\.", line)
    if m:
        kind, key = m.group(2), m.group(3)
        k = (context, kind)
        counters[k] = counters.get(k, 0) + 1
        ident = f"{context}{counters[k]}"
        assert (kind, key) not in assigned, (kind, key)
        assigned[(kind, key)] = ident
missing = set(re.findall(r"\[\[(T|F):([^\]]+)\]\]", doc)) - set(assigned)
assert not missing, missing
doc = re.sub(r"\[\[(T|F):([^\]]+)\]\]", lambda m: assigned[(m.group(1), m.group(2))], doc)
open(f"{P}/paper_v6.md", "w", encoding="utf-8").write(doc)
print("labels:", {f"{k[0]}:{k[1]}": v for k, v in assigned.items()})
print("words (body prose):", len(re.sub(r"\|.*", "", doc[:doc.index("## Statements and Declarations")]).split()))
