#!/usr/bin/env python3
"""build_srep_si.py — Supplementary Information for the Scientific Reports version:
Supplementary Tables S1–S7 (the full main-specification table, the fork effects on the components, the
latency-floor fits, the predictions–tests–verdicts table, the response time and volatility on the subsamples with
an unambiguous opening time, the three forks and the events in their windows, the exact p-values of Table 3)
followed by Appendices A–E of the article version, with cross-references remapped to the Scientific Reports
structure.  Writes srep_SI.md and srep_SI.docx.

Revision (Scientific Reports referee, T1/T2/P5): Table D5 of the article version is no longer duplicated (it is
Supplementary Table S2 and Appendix D points to it); the misplaced copy of Table D6 is gone; the cross-references
of Supplementary Table S4 use the Scientific Reports numbering; the caption of Figure D2 says top/bottom.
"""
import json
import os
import re
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "paper_v6.md"), encoding="utf-8").read()


def block(caption_start, next_marker):
    i = src.index(caption_start)
    j = src.index(next_marker, i + 1)
    return src[i:j].strip()


s1 = block("**Table 3. Main specification", "**Figure 1.")
s2 = block("**Table D5.", "**Table D6.")                      # the components table only (T1)
s3 = block("**Table 7. The latency-floor model", "\nThe two routes")
s4 = block("**Table 6. Predictions, tests and verdicts", "\n## 7. Discussion")
s6 = block("**Table 1. The three block-interval reductions.**", "\n### 2.2")
appendices = src[src.index("## Appendix A."):]
# Appendix D: replace the components table by a pointer to Supplementary Table S2 (T1)
d5 = block("**Table D5.", "**Table D6.")
assert d5 in appendices
appendices = appendices.replace(d5, "[[D5STUB]]")

# ---- cross-references of the predictions table (T2): fix before the generic remap
s4 = (s4.replace("| Tables 3, 4 |", "| Tables 3 and 4 |")                 # article numbering here; remap() converts it
        .replace("| Tables B8, A3, 5 |", "| Tables B8 and A3, Table 5 |")
        .replace("Table 3 Panel B, Table 7, Figure 1", "Supplementary Table S1 Panel B, Supplementary Table S3, Figure 1"))
appendices = appendices.replace("**Figure D2. Fork effects implied by the response times against the pool-level estimates, twelve pool-forks.** Left: log(E[√τ]_post / E[√τ]_pre); right: the composite prediction",
                                "**Figure D2. Fork effects implied by the response times against the pool-level estimates, twelve pool-forks.** Top: log(E[√τ]_post / E[√τ]_pre); bottom: the composite prediction")
assert "Top: log(E[√τ]_post" in appendices

# ---- remap article cross-references to the Scientific Reports structure
TAB = {"1": "Supplementary Table S6", "2": "Table 4", "3": "Table 1", "4": "Table 2", "5": "Table 3",
       "6": "Supplementary Table S4", "7": "Supplementary Table S3"}
SEC = {"2": "Methods (Setting)", "2.1": "Methods (Setting)", "2.2": "Methods (Setting)",
       "3": "Methods (Model and predictions)", "3.1": "Methods (Model and predictions)", "3.2": "Methods (Model and predictions)", "3.3": "Methods (Model and predictions)",
       "4": "Methods", "4.1": "Methods (On-chain data and block timestamps)", "4.2": "Methods (Reference prices)",
       "4.3": "Methods (Arbitrage identification and LP economics)", "4.4": "Methods (Hourly panel and estimation)",
       "4.5": "Methods (Opening times, response times and components)",
       "5": "Methods (Hourly panel and estimation)", "5.1": "Methods (Hourly panel and estimation)", "5.2": "Methods (Hourly panel and estimation)", "5.3": "Methods (Hourly panel and estimation)",
       "6": "Results", "6.1": "Results (the overshoot falls at every fork)", "6.2": "Results (what the reference price does)",
       "6.3": "Results (arbitrageurs' profits fall; the liquidity providers' cost does not)", "6.4": "Methods (Arbitrage identification and LP economics)",
       "6.5": "Supplementary Appendix B", "6.6": "Results (volatility and competition within the hour)",
       "6.7": "Results (arbitrageurs' latency; the anatomy of the overshoot)", "6.8": "Supplementary Table S4",
       "7": "Discussion", "7.1": "Discussion", "7.2": "Discussion", "7.3": "Discussion", "7.4": "Discussion",
       "8": "Introduction", "9": "Discussion"}
RD = [("RD jump at the fork", "jump at the fork"), ("RD jumps", "jumps at the fork"), ("RD jump", "jump at the fork"), ("RD designs", "jump-at-the-fork designs"), ("RD-style", "jump-at-the-fork"), ("RD rows", "jump-at-the-fork rows"),
      ("regression-discontinuity", "jump-at-the-fork"), ("Table D5", "Supplementary Table S2")]


def remap(t):
    t = re.sub(r"Sections (\d(?:\.\d)?) and (\d(?:\.\d)?)", lambda m: f"{SEC.get(m.group(1), 'the article')} and {SEC.get(m.group(2), 'the article')}", t)
    t = re.sub(r"Section (\d(?:\.\d)?)(?!\d)(?!\.\d)", lambda m: SEC.get(m.group(1), "the article"), t)
    def tab(m):   # one pass, so that a remapped number is never remapped again
        if m.group(1):
            a, c = TAB[m.group(1)], TAB[m.group(2)]
            return f"Tables {a[6:]} and {c[6:]}" if a.startswith("Table ") and c.startswith("Table ") else f"{a} and {c}"
        return TAB[m.group(3)]
    t = re.sub(r"Tables (\d) and (\d)(?![\dA-Z])|Table (\d)(?![\dA-Z])", tab, t)
    for a, b in RD:
        t = t.replace(a, b)
    return t


s1 = remap(s1.replace("**Table 3. Main specification", "**Supplementary Table S1. Main specification", 1))
s1 = s1.replace("core pools.** jump at the fork in the ±30-day window", "core pools.** Jump at the fork in the ±30-day window")
s1 = s1.replace("| 0.289 (0.035) | −6.1 | 0.00 |", "| 0.289 (0.035) | −6.1 | 0.002 |").replace("| 0.307 (0.027) | −7.2 | 0.00 |", "| 0.307 (0.027) | −7.2 | 0.002 |")
assert s1.count("| 0.002 |") == 2
s2 = remap(s2.replace("**Table D5.", "**Supplementary Table S2.", 1))
s3 = remap(s3.replace("**Table 7. The latency-floor model", "**Supplementary Table S3. The latency-floor model", 1))
s4 = remap(s4.replace("**Table 6. Predictions, tests and verdicts", "**Supplementary Table S4. Predictions, tests and verdicts", 1))
assert s4.count("significantly under two of four") == 1
s4 = s4.replace("significantly under two of four", "with the equality of the three elasticities rejected under two of four (p = 0.002 for strict and for CEX-triggered arbitrages, 0.20 and 0.21 for bot flow and all identified arbitrages)")
s6 = remap(s6.replace("**Table 1. The three block-interval reductions.**", "**Supplementary Table S6. The three block-interval reductions, the changes bundled with them and the events in their ±30-day windows.**", 1))
appendices = remap(appendices)
appendices = appendices.replace("[[D5STUB]]", "**Table D5. Fork effects on the components of the strict overshoot.** Reported as Supplementary Table S2 above; the table is not repeated here.")

# ---- Supplementary Table S5: response time and volatility on the clean subsamples (arbitrage level)
clean = open(os.path.join(HERE, "tables_v6", "table_tau_sigma_clean.md"), encoding="utf-8").read()
cj = json.load(open(os.path.join(HERE, "tables_v6", "tau_sigma_clean.json")))
n = {k.split("|")[1]: v for k, v in cj.items() if k.startswith("n|")}
s5_cap = ("**Supplementary Table S5. Response time and volatility on the subsamples whose opening time is unambiguous, and by size of the crossing jump (arbitrage level).** "
          "Coefficient on log σ (the hour's Binance realised volatility) in an ordinary-least-squares regression of the arbitrage-level outcome — the log response time τ, "
          "or the indicator of landing in the first block sealed after the opening — on log σ with hour-of-day and pool fixed effects within each block-interval regime, "
          "three core 0.05% pools pooled, bot flow, ±30-day windows; rows \"with controls\" add the hour's log volume and log active liquidity. Standard errors clustered by "
          "calendar day (31 clusters per regime) in parentheses, followed by the exact two-sided p-value from t(30). Panel A: all CEX-triggered arbitrages, the sample of Table 3, for comparison. "
          "Panel B: sharp openings, CEX-triggered arbitrages whose crossing trade carried the reference price at least ½γ beyond the band edge, so that t_open is unambiguous. "
          "Panel C: on-chain-triggered arbitrages, whose τ is the difference between two block timestamps and involves no reference price. "
          "Panel D: for each sample, the inverse-variance-weighted mean of the six regime elasticities of log τ with controls, its standard error, its t-statistic against zero with the p-value under the normal approximation, "
          "the t-statistic of its difference from the full-sample pooled value (difference divided by the standard error of the difference, the samples of Panels B and C being disjoint from, or a 1% subset of, that of Panel A) "
          "and the heterogeneity statistic Q across regimes (χ² on five degrees of freedom). Panel B is under-powered — its pooled standard error of 0.065 could not distinguish an elasticity of −0.11 from zero at conventional levels — whereas Panel C, with a standard error of 0.024, carries the test. "
          "Panel E: the full-sample (Panel A) elasticity with controls by size of the crossing jump J, the excess in basis points by which the crossing trade carried the reference price beyond the band edge "
          "(bins at the quartiles of J up to 0.4 bp, then 0.4–1 bp, 1–2.5 bp and the sharp openings above ½γ = 2.5 bp), as coefficient (standard error) per regime, with the pooled elasticity and its p-value under the normal approximation, Q and the number of arbitrages per bin: "
          "if the residual negative elasticity is what the opening convention produces on marginal crossings, it should be largest for the smallest J and vanish once the crossing clears the arbitrageurs' own thresholds. "
          "Panel F: sample sizes, which are the n of the corresponding regressions, and the number of day-clusters.")
panels = clean.split("\n**")[1:]     # blocks start with the bold sample label
labels = ["Panel A. All CEX-triggered arbitrages (the sample of Table 3)", "Panel B. Sharp openings (crossing trade at least ½γ beyond the band edge)",
          "Panel C. On-chain-triggered arbitrages (τ from block timestamps only)",
          "Panel D. Pooled elasticity of log τ to log σ with controls: inverse-variance-weighted mean of the six regime estimates",
          "Panel E. All CEX-triggered arbitrages by size of the crossing jump J (bp beyond the band edge): elasticity of log τ to log σ with controls",
          "Panel F. Sample sizes per regime, three core pools pooled"]
assert len(panels) == len(labels), (len(panels), len(labels))
s5_parts = [s5_cap]
for lab, blk in zip(labels, panels):
    body = blk.split("**\n", 1)[1].strip()
    body = body.replace("| Sample / outcome |", "| Outcome |").replace(", with log volume and log liquidity", ", with controls")
    body = "\n".join(ln if re.match(r"^\|[:\-| ]+\|$", ln) else re.sub(r"-(?=\d)", "−", ln) for ln in body.split("\n"))
    s5_parts.append(("<<<pagebreak>>>\n\n" if lab.startswith("Panel E.") else "") + f"*{lab}*\n\n{body}")   # keep the ten-column panel on one page
s5 = "\n\n".join(s5_parts)

# ---- Supplementary Table S7: exact p-values of Table 3
from scipy import stats  # noqa: E402

vc = json.load(open(os.path.join(HERE, "vol_competition.json")))["elasticities"]
REG = ["Lorentz pre", "Lorentz post", "Maxwell pre", "Maxwell post", "Fermi pre", "Fermi post"]
ROWS = [("log_tau_med", "Median τ (log)"), ("log_sqrt_tau", "E[√τ] (log)"), ("first_block", "First-block share (level)"),
        ("log_n_senders", "Active contracts (log)"), ("log_M", "Movement M (log)"), ("log_J", "Crossing jump J (log)"), ("log_overshoot_cex", "CEX-triggered overshoot (log)")]


def fp(p):
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}" if p < 0.1 else f"{p:.2f}"


import pandas as pd  # noqa: E402

_H = pd.read_parquet(os.path.join(HERE, "vol_competition_panel.parquet"))
G = {f"{f} {r}": int(_H[(_H["fork"] == f) & (_H["regime"] == r)]["day"].nunique()) for f in ("Lorentz", "Maxwell", "Fermi") for r in ("pre", "post")}
s7 = ["**Supplementary Table S7. Exact two-sided p-values for every cell of Table 3.** Same regressions as Table 3 (coefficient on log σ within each block-interval regime, "
      "hour-of-day and pool fixed effects, day-clustered standard errors; n = 1,086, 880, 875, 1,288, 1,104 and 1,557 pool-hours in the six regimes); p-values refer the cluster-robust "
      "t-statistic to t(G − 1), G being the number of day-clusters (" + ", ".join(str(G[r]) for r in REG) + "), \"<0.001\" below that level.",
      "| Outcome | " + " | ".join(REG) + " |", "|:--|" + ":--|" * len(REG)]
for tag, suffix in [("*No further controls*", ""), ("*With log volume and log active liquidity*", " +controls")]:
    s7.append(f"| {tag} |" + " |" * len(REG))
    for key, lab in ROWS:
        cells = []
        for r in REG:
            x = vc[key][r + suffix]
            cells.append(fp(2 * stats.t.sf(abs(x["beta"] / x["se"]), G[r] - 1)))
        s7.append(f"| {lab} | " + " | ".join(cells) + " |")
s7 = "\n".join(s7)

head = ("# Supplementary Information for \"Faster blocks fall short of the square-root law: arbitrage rents and latency across three block-interval reductions on BNB Chain\"\n\n"
        "*Zhengdong Zhu — School of Business, Macau University of Science and Technology, Macau, China — 2250030525@student.must.edu.mo*\n\n"
        "This Supplementary Information contains Supplementary Tables S1–S7 and Appendices A–E. Tables and figures with a letter prefix (A1, B1, …) belong to the appendices; unprefixed table and figure numbers refer to the main text.\n\n"
        "## Supplementary Tables\n\n")
si = head + "\n\n".join([s1, s2, s3, s4, s5, s6, s7]) + "\n\n" + appendices
# typographic subscripts (md2docx renders ~x~ as a Word subscript); the code-font API name keeps its underscore
for a, c in [("t_{b−1}", "t~b−1~"), ("t_b − t_open", "t~b~ − t_open"), ("t_open", "t~open~"), ("t_block", "t~block~"), ("Q_q", "Q~q~"),
             ("E[√τ]_post", "E[√τ]~post~"), ("E[√τ]_pre", "E[√τ]~pre~"), ("dev_pre", "dev~pre~"), ("p_pre", "p~pre~"), ("P_open", "P~open~"),
             ("Post_t", "Post~t~"), ("t_prev", "t~prev~"), ("λ'", "λ′")]:
    si = si.replace(a, c)
open(os.path.join(HERE, "srep_SI.md"), "w", encoding="utf-8").write(si)
left = [x for x in re.findall(r"Section \d|\bRD\b|Table D5\b|regression-discontinuity", si) if x != "Table D5"] + (["Table D5 cited"] if si.count("Table D5") > 1 else [])
print("remaining old refs:", left, "| Table D6 count:", si.count("**Table D6."), "| words:", len(si.split()))
subprocess.run(["node", os.path.join(HERE, "md2docx.js"), os.path.join(HERE, "srep_SI.md"), os.path.join(HERE, "srep_SI.docx")], check=True, cwd=HERE)
