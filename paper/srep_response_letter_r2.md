# Response to the referee, round 2 — Scientific Reports

**Manuscript:** Faster blocks fall short of the square-root law: arbitrage rents and latency across three block-interval reductions on BNB Chain

**Author:** Zhengdong Zhu

Dear Editor, dear Referee,

Thank you for the second report and for recommending acceptance. The three changes it asks for are made; we also took up the suggestion that was not required, because it turned out to sharpen the argument. Nothing else in the manuscript has changed apart from the p-values affected by the change of reference distribution described under III.1. The main text is 4,300 words, the abstract 199 words, and the display items remain three figures and four tables; the Supplementary Information is 38 pages.

## II. The argument for Supplementary Table S5

**(a) Pooled elasticities per panel, with a test against the full-sample value.** Supplementary Table S5 now has a Panel D that reports, for each sample, the inverse-variance-weighted mean of the six regime elasticities of log τ to log σ with controls, its standard error, its t-statistic against zero, the t-statistic of its difference from the full-sample pooled value (difference divided by the standard error of the difference; the on-chain sample is disjoint from the full sample and the sharp-opening sample is a 1% subset of it) and the heterogeneity statistic Q across regimes. The values are: all CEX-triggered arbitrages −0.111 (0.016); sharp openings +0.016 (0.065), 1.9 standard errors from the full-sample value; on-chain-triggered arbitrages +0.048 (0.024), 5.5 standard errors above the full-sample value (the referee's t ≈ 6 treats the full-sample value as known; ours divides by the standard error of the difference).

**(b) Panel B is under-powered; Panel C carries the test.** The Results now say exactly this: "Sharp openings … are too few to decide it: their pooled elasticity is +0.02 (0.07), consistent with zero but only 1.9 standard errors from the full-sample value. On-chain-triggered arbitrages, whose response time is a difference of two block timestamps, carry the test: their pooled elasticity is +0.05 (0.02), 5.5 standard errors above the full-sample value, and their first-block share rises with σ in none of the six regimes (p ≥ 0.11)." The count of "ten of twelve estimates" is gone, and the caption of S5 states that Panel B's pooled standard error of 0.065 could not distinguish an elasticity of −0.11 from zero at conventional levels.

**(c) "is what" → "is consistent with what".** Changed as suggested: "The residual fall is consistent with what the opening convention would produce when the reference price crosses the band edge by a hair and the arbitrageur acts only once the deviation reaches its own threshold, a distance that volatile hours cover faster".

**The suggestion that was not required.** We estimated the full-sample elasticity by size of the crossing jump J — the excess, in basis points, by which the crossing trade carried the reference price beyond the band edge — in bins at the quartiles of J up to 0.4 bp, then 0.4–1 bp, 1–2.5 bp and the sharp openings above ½γ = 2.5 bp (Supplementary Table S5, Panel E). The elasticity of log τ to log σ, with controls and pooled across regimes, is −0.134 (0.022) for crossings of less than 0.05 bp, −0.120 (0.022) at 0.05–0.15 bp, −0.102 (0.024) at 0.15–0.4 bp, −0.048 (0.022) at 0.4–1 bp, +0.050 (0.036) at 1–2.5 bp and +0.016 (0.065) above 2.5 bp: it declines monotonically in magnitude with the size of the crossing and is zero once the crossing exceeds about one basis point. This is where the mechanism puts it, so the sentence quoted under (c) now continues: "and it sits where that mechanism puts it, since the elasticity is −0.13 (0.02) for crossings of less than 0.05 bp beyond the edge, −0.10 (0.02) at 0.15–0.4 bp, −0.05 (0.02) at 0.4–1 bp and +0.05 (0.04) at 1–2.5 bp". (A split into terciles of J, the first thing we tried, gives −0.13, −0.10 and −0.09: the top tercile begins at 0.36 bp and mixes crossings that do and do not clear the arbitrageurs' thresholds, which is why the finer bins are the informative ones.)

## III. Minor points

**1. p-values from t(G − 1).** All exactly reported p-values — Table 1, Table 2 Panel B, the elasticity tests in the text, Supplementary Tables S5 and S7 — now refer the cluster-robust t-statistic to a t distribution with G − 1 degrees of freedom, G being the number of clusters (61 in the ±30-day windows, 31 in the pre-period placebos, 30–31 in the within-regime regressions). The Methods (Statistics and software) and the captions say so. No conclusion changes; the largest movements are in the placebo rows (for instance the Maxwell placebo on the strict overshoot, p = 0.026 → 0.033) and in the borderline cells of S5 (p = 0.050 → 0.060 for sharp openings after Lorentz). The significance stars of the appendix tables of the Supplementary Information were assigned under the normal approximation; with 31 or more clusters the two conventions differ by at most about 0.01 in p at the 10%, 5% and 1% thresholds, and the Methods now state this.

**2. The 110-word sentence.** Split. The passage from "Holding volume and liquidity fixed removes …" now runs in five sentences: the residual response at given volume and liquidity; the question it raises; what the sharp-opening subsample can and cannot say; what the on-chain-triggered subsample shows; and the reading of the residual with its evidence from Panel E.

We are grateful for both reports.

Sincerely,

Zhengdong Zhu
School of Business, Macau University of Science and Technology, Macau, China
2250030525@student.must.edu.mo
