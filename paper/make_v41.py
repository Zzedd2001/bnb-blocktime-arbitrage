"""Build paper_draft_v41.md from v4: bot-flow (public routers excluded) versions of Tables 18–21, E1–E3 and Figures 7, 8,
E1, E2; identification of arbitrageurs by contract + signing account (Section 4.5); operator-level evidence (Section 6.9,
Tables E4–E7); text updates in the abstract, introduction, 6.9, 7.2–7.4, 8, 9, Appendices E and F."""
import re

s = open("paper_draft_v4.md").read()
T = lambda name: open(f"tables_v41/{name}.md").read().strip()
D = open("v41_text_drafts.md").read()


def rep(old, new, count=1):
    global s
    assert s.count(old) >= 1, "NOT FOUND: " + old[:90]
    s = s.replace(old, new, count)


def rep_between(start, end, new, keep_end=True):
    """Replace the text from `start` (inclusive) up to `end` (exclusive) with `new`."""
    global s
    i = s.index(start); j = s.index(end, i)
    s = s[:i] + new + s[j:]


def draft(section_start, section_end=None):
    i = D.index(section_start) + len(section_start)
    j = D.index(section_end, i) if section_end else len(D)
    return D[i:j].strip()


# ---------------------------------------------------------------- header, figures
rep("*Anonymous submission — draft v4 (September 2026)*", "*Anonymous submission — draft v4.1 (September 2026)*")
s = s.replace("figures_v4/", "figures_v41/")

# ---------------------------------------------------------------- abstract
rep("Reconstructing, for 10.3 million arbitrage trades, the moment at which each opportunity opened",
    "Reconstructing, for 6.5 million trades by arbitrage contracts, the moment at which each opportunity opened")
rep("at 0.1–0.35 s at sub-second block times (0.4–1.4 s in April 2025)", "at 0.1–0.35 s at sub-second block times (0.3–1.4 s in April 2025)")
rep("rises from 14–46% at 3-second blocks to 37–51% at 0.45 s. But only the part of the overshoot that accumulates while the arbitrageur waits — 27% of it — responds to the block interval as the model says: it falls by −0.49, −0.19 and −0.32 log points",
    "rises from 14–47% at 3-second blocks to 37–51% at 0.45 s. But only the part of the overshoot that accumulates while the arbitrageur waits — 28% of it — responds to the block interval as the model says: it falls by −0.46, −0.19 and −0.32 log points")
rep("the jump of the reference price at the trade that opens the opportunity (18%) and the overshoot of same-block back-runs (19%) change little (by −0.07 to +0.03 and −0.14 to +0.07 at the two sub-second forks)",
    "the jump of the reference price at the trade that opens the opportunity (19%) and the overshoot of same-block back-runs (18%) change little (by −0.07 to +0.04 and −0.14 to +0.06 at the two sub-second forks)")

# ---------------------------------------------------------------- introduction
rep("For each of 10.3 million arbitrage trades we reconstruct", "For each of 6.5 million trades by arbitrage contracts we reconstruct")
rep("down from 0.4–1.4 s in April 2025, when the same arbitrageurs were much slower — and the share of arbitrages that miss the first block after the opportunity opens rises from 14–46% at 3-second blocks",
    "down from 0.3–1.4 s in April 2025, when the same arbitrageurs were much slower — and the share of arbitrages that miss the first block after the opportunity opens rises from 14–47% at 3-second blocks")
rep("in the 5 bp pools the fork effect they imply is −0.14 to −0.24 at Maxwell and Fermi against estimates of −0.04 to −0.18.",
    "in the 5 bp pools the fork effect they imply is −0.16 to −0.24 at Maxwell and Fermi against estimates of −0.04 to −0.18.")
rep("a part that accumulates while the arbitrageur waits — 27% of the strict overshoot in the four liquid pools, 32% in the three core pools — and parts that do not depend on the block interval at all: the jump of the reference price at the trade that opens the opportunity (18%),",
    "a part that accumulates while the arbitrageur waits — 28% of the strict overshoot in the four liquid pools, 32% in the three core pools — and parts that do not depend on the block interval at all: the jump of the reference price at the trade that opens the opportunity (19%),")
rep("The first part falls with the block interval at every fork — −0.49, −0.19 and −0.32 log points against the law's −0.35, −0.35 and −0.26, i.e. by the law or more at Lorentz and Fermi and by half of it at Maxwell; the jump component moves by −0.07 to +0.03 and the back-run component by −0.14 to +0.07 at the two sub-second forks.",
    "The first part falls with the block interval at every fork — −0.46, −0.19 and −0.32 log points against the law's −0.35, −0.35 and −0.26, i.e. by the law or more at Lorentz and Fermi and by half of it at Maxwell; the jump component moves by −0.07 to +0.04 and the back-run component by −0.14 to +0.06 at the two sub-second forks.")
rep("and it documents, at the address level, that a handful of contracts execute most CEX–DEX arbitrage and that their latency fell steadily between April 2025 and January 2026 — from about a second to a fifth of a second for the largest arbitrageur of the ETH pool, from 0.44 s to 0.06 s for the largest overall.",
    "and it documents, at the level of contracts and of the operators behind them, that a handful of operators execute most CEX–DEX arbitrage, that their latency fell steadily between April 2025 and January 2026 — from about a second to 0.15 s for the largest arbitrageur of the ETH pool, from 0.44 s to 0.06 s in the BTCB pool for the largest overall — and that at 0.45-second blocks the fastest of them sign from pools of dozens of wallets to keep several transactions in flight.")

rep("by a same-block trade (19%) or by an earlier partial correction (34%)", "by a same-block trade (18%) or by an earlier partial correction (34%)")

# ---------------------------------------------------------------- 4.5: identification of arbitrageurs, sample
rep("The arbitrageur is identified by the sender of the swap, the contract that called the pool.\n",
    draft("REPLACE that sentence with:", "## §6.9") + "\n")
rep("Across the three ±30-day windows the seven pools contain 10.3 million identified arbitrages (2.9 million around Lorentz, 4.3 million around Maxwell, 3.1 million around Fermi), almost all of them in the four liquid pools. Among strict arbitrages in the three core pools, CEX-triggered ones are 21–69% depending on pool and regime, continuations 20–41%, same-block back-runs 5–51% and on-chain-triggered ones 0.3–1.6%.",
    "Across the three ±30-day windows the seven pools contain 10.3 million identified arbitrages, of which 6.5 million were sent by arbitrage contracts (1.7 million around Lorentz, 2.3 million around Maxwell, 2.6 million around Fermi) and the rest through public routers; the statistics that follow use the former, almost all of them in the four liquid pools. Among their strict arbitrages in the three core pools, CEX-triggered ones are 29–70% depending on pool and regime, continuations 20–41%, same-block back-runs 4–43% and on-chain-triggered ones 0.4–1.6%.")
rep("the hourly mean over all strict arbitrages reproduces the overshoot series of Section 4.3 and the ±14-day estimates of Table 8 to the third decimal.",
    "the hourly mean over all strict arbitrages, bot flow and router flow together, reproduces the overshoot series of Section 4.3 and the ±14-day estimates of Table 8 to the third decimal, and the component estimates of Section 6.9 are computed on bot flow.")

# ---------------------------------------------------------------- 6.9: response times paragraph
rep_between("**Response times and latency.** Table 18 summarises", "**Table 18. Response times",
"""**Response times and latency.** Table 18 summarises the response times of CEX-triggered arbitrages by arbitrage contracts in the three core pools across the six block-interval regimes (Table E1 gives the four liquid pools regime by regime; Appendix E shows what including the flow that reaches the pools through public routers does to the estimates); Figure 7 plots the latency intercepts. At sub-second block times the picture is the one P6 describes. In the Fermi window the intercepts of the tenth percentile and of the median differ by less than a tenth of a second and move by less than 50 ms at the fork (WBNB 125/187 → 132/203 ms, ETH 206/271 → 162/237 ms, BTCB 133/192 → 109/160 ms), the Turnbull estimator places the median latency at 160–230 ms, and the median response time falls by 134, 184 and 182 ms in the three pools against the 150 ms by which the expected wait for a block fell (Table 19); at Maxwell the corresponding changes are −420, −504 and −505 ms against −375, and the intercepts are 0.20–0.47 s. Openings created by a sharp jump of the reference price, whose timing is unambiguous, give intercepts of 0.08–0.40 s in every one of the six regimes. On-chain-triggered arbitrages, which use only block timestamps, tell the same story from the other side: the share landing in the first block, which is the distribution function of the latency at Δt, is 0.80–0.91 whether Δt is 3 s or 0.45 s, so four fifths to nine tenths of the latency distribution lies below 0.45 s and the remainder is a tail that does not respond to the block interval at all (small deviations that arbitrageurs wait to grow). Wider bands give intercepts near zero or negative: arbitrageurs act at the band edge, not beyond it. At 3-second blocks, in April 2025, arbitrageurs were slower and more heterogeneous — median intercepts of 0.56 s (WBNB), 0.75 s (BTCB) and 1.4 s (ETH) — and they became faster within the Lorentz window itself (latency-change components of −0.06 to −0.11 in three pools in Table 19; +0.09 in BTCB, whose mean response time is held up by a long tail) and kept doing so through the year: the same operators appear in every pool and regime, and the tenth-percentile intercept of the contract that was the largest ETH-pool arbitrageur before Lorentz fell from 954 ms then to 151 ms after Fermi (Table E3). As a fixed latency implies, the share of CEX-triggered arbitrages that land in the first block after the opening falls at both sub-second forks in every pool — from 0.68–0.85 to 0.54–0.64 at Maxwell and from 0.62–0.73 to 0.49–0.63 at Fermi (Figure E1) — so that at 0.45-second blocks 37–51% of arbitrages miss the first block; at Lorentz it fell in two pools and rose in the WBNB pool, whose arbitrageurs became faster within the window.

""")
rep("**Table 18. Response times of CEX-triggered arbitrages and the arbitrageurs' latency across the six block-interval regimes, three core 0.05% pools (ranges over the three pools).**",
    "**Table 18. Response times of CEX-triggered arbitrages and the arbitrageurs' latency across the six block-interval regimes, three core 0.05% pools, bot flow (ranges over the three pools).**")
rep("(it is not identified at 1.5- and 3-second blocks, where almost every interval starts at zero)", "(it is not identified at 1.5- and 3-second blocks, where almost every interval starts at zero; the values are reported for completeness)")
rep_between("| Regime | Δt (s) | CEX-triggered arbitrages |", "**Figure 7.", T("table18_six_regimes") + "\n\n")

# 6.9: implied effects paragraph
rep_between("**What the response times imply for the fork effects.**", "**Table 19.",
"""**What the response times imply for the fork effects.** If the overshoot were σ√τ, the fork effect would be log(E[√τ]_post / E[√τ]_pre); Table 19 computes it from the response times alone and places it next to the estimated overshoot effect of each pool (Table 8). The response-time-implied effects track the estimates across the twelve pool-forks (correlation 0.67, weighted slope 1.06 with s.e. 0.38; Figure E2) and coincide with them at Lorentz — −0.35, −0.33, −0.17 and −0.37 against −0.39, −0.33, −0.24 and −0.36 — but at the two sub-second forks they are systematically larger than the estimates — −0.16 to −0.24 against −0.04 to −0.18 in the 5 bp pools, and −0.29 against +0.01 in the 1 bp pool at Maxwell: the latency accounts for part of the sub-second shortfall, not for all of it. Holding the pre-fork latency distribution fixed and changing only Δt reproduces the post-fork response-time distribution almost exactly at Maxwell and Fermi (latency-change components between −0.03 and +0.09), whereas at Lorentz the arbitrageurs also became faster. Expressed in the convention of Section 3.2 and Table 16, the latency that the response times measure is 0.12–0.36 s at Fermi and 0.22–0.89 s at Maxwell — consistent with the χ² fit at Maxwell, at the lower end of its confidence interval at Fermi.

""")
rep("**Table 19. Fork effects implied by the response times, four liquid pools.**", "**Table 19. Fork effects implied by the response times, four liquid pools, bot flow.**")
rep("the last column repeats the pool-level overshoot estimate of Table 8 (±14 d, with liquidity and volume).",
    "the last column repeats the pool-level overshoot estimate of Table 8 (all flow, ±14 d, with liquidity and volume).")
rep_between("| Fork    | Pool            | √Δt law   | Implied by τ", "**The components of the overshoot.**", T("table19_tau_implied") + "\n\n")

# 6.9: components paragraph
rep_between("**The components of the overshoot.**", "The composition itself changes at the forks",
"""**The components of the overshoot.** Table 20 estimates the fork effect on each component of the strict overshoot with the specification of Table 4 (core pools pooled, pool fixed effects), Table 21 does so pool by pool together with the pre-fork weight of each component, and Figure 8 plots the pool-level estimates. Three results. First, the accumulated-movement component M falls at every fork, by the √Δt law or more at Lorentz and Fermi and by about half of it at Maxwell: −0.46 (0.04), −0.19 (0.04) and −0.32 (0.04) in the ±14-day windows against −0.35, −0.35 and −0.26, with −0.46, −0.24 and −0.32 at ±7 days and −0.56, −0.17 and −0.32 at ±30 days; pool by pool the estimates are −0.28 to −0.78, −0.10 to −0.49 and −0.23 to −0.47, and the fake-fork placebos for this component are −0.07, +0.04 and −0.09. That M falls by more than the response times imply is what a fixed latency produces once the selection of the arbitrages that actually occur is taken into account — an opportunity is only closed if the price stays outside the band until the block, and that condition binds more at longer response times (Appendix E reproduces the pattern in a simulation with a fixed latency). Second, the components that the model says should not respond respond little. The crossing-jump component J changes by −0.02 (0.03), +0.04 (0.03) and −0.06 (0.02) at the three forks (−0.07 to +0.04 across windows), and the overshoot of same-block back-runs by +0.06 (0.04) at Maxwell and −0.11 (0.05) at Fermi (pool by pool, −0.30 to +0.27): J moves by a quarter of the law at most, the back-runs by nothing at Maxwell and by two fifths of the law at Fermi, where M moves by more than the law; continuations fall by −0.37, −0.21 and −0.18, by less than M at Lorentz and Fermi and by as much at Maxwell. The jump component also has among the lowest elasticities to volatility — 0.04–0.15, against 0.43–0.54 for M (Table 21, lower panel) — as a quantity set by the discreteness of the reference price rather than by its diffusion should. Third, the weighted sum of the components' effects, with each pool's pre-fork weights, reproduces the total: −0.30 against a total of −0.27 at Lorentz, −0.12 against −0.12 at Maxwell and −0.15 against −0.12 at Fermi (means over the four liquid pools). The weights are what makes the returns diminish. In the pre-fork fortnight the movement component M is 28% of the strict overshoot (8–54% across the twelve pool-forks), the jump 19%, continuations 34% and same-block back-runs 18%; the two components that do not respond together rise from 32% of the overshoot at Lorentz to 35% at Maxwell and 44% at Fermi, because each fork removes part of M and none of the rest. At Fermi, w_M times the √Δt law is −0.06, w_M times the estimated effect on M is −0.08, and the continuations add about −0.05 — the −0.11 to −0.14 that the aggregate estimates show (−0.14 on bot flow, −0.11 to −0.13 with all flow). Lorentz is the fork at which everything fell, including the jump in two of the four pools and the back-runs (−0.26) — most plausibly a selection effect, since at 3-second blocks only large jumps were corrected before the price returned into the band and at 1.5 s smaller ones were too — and it is the fork at which the aggregate effect was close to the law. On bot flow the aggregate effect on the strict overshoot is −0.29, −0.13 and −0.14 (±14 d, core pools pooled) against −0.36, −0.11 and −0.13 with the router flow included (the first column of Table 20 against the corresponding row of Table 4): at Lorentz the share of router flow, whose overshoot is a tenth of the bots', rose after the fork, and about 0.07 of that fork's aggregate estimate is composition.

""")
rep("the share of same-block back-runs falls at Maxwell (−0.03 to −0.21) and Fermi (−0.01 to −0.09) and the share of continuations rises (+0.09 to +0.18 in three pools at Maxwell, +0.01 to +0.07 at Fermi).",
    "the share of same-block back-runs falls at Maxwell (−0.03 to −0.17) and Fermi (−0.01 to −0.09) and the share of continuations rises (+0.09 to +0.16 in three pools at Maxwell, +0.01 to +0.07 at Fermi).")

# Tables 20, 21, 21b
rep("**Table 20. Fork effects on the components of the strict overshoot, three core 0.05% pools pooled with pool fixed effects (trade reference).** Each column is a separate regression",
    "**Table 20. Fork effects on the components of the strict overshoot, three core 0.05% pools pooled with pool fixed effects (trade reference, bot flow).** The first column is the aggregate strict overshoot of bot flow (the same specification on all flow gives the estimates of Table 4); each column is a separate regression")
rep_between("| Fork    | Window                                | All strict arbitrages   |", "**Table 21.", T("table20_components_pooled") + "\n\n")
rep("**Table 21. Fork effects on the components pool by pool (±14 d, log σ + log L + log volume + hour effects), pre-fork weights of the components and their weighted sum.** The first column is the estimate of Table 8, reproduced from the component panel; Δ share",
    "**Table 21. Fork effects on the components pool by pool (±14 d, log σ + log L + log volume + hour effects, bot flow), pre-fork weights of the components and their weighted sum.** The first column is the aggregate strict overshoot of bot flow and the last column repeats the estimate of Table 8, which includes the router flow; Δ share")
rep_between("| Fork    | Pool            | All strict arbitrages (= Table 8)   |", "*Elasticity to volatility, by component", T("table21_components_per_pool") + "\n\n")
rep_between("| Fork    | All strict arbitrages   | CEX-triggered, total   | J    |", "**Figure 8.", T("table21b_sigma_elasticity_components") + "\n\n")

# 6.9: arbitrageurs paragraphs
arb = draft("## §6.9 — \"Arbitrageurs\" paragraph (replace the existing one)", "## Appendix E — additions")
arb = arb.replace("[[N1–N2]]", "58–136").replace("[[N3–N4]]", "14–35").replace("[[H1–H2]]", "0.15–0.43")
rep_between("**Arbitrageurs.** CEX–DEX arbitrage on these pools is done by few contracts.", "## 7. Discussion", arb + "\n\n")

# ---------------------------------------------------------------- 7.2
rep("and the response times measure ℓ_t at 0.10–0.47 s at Maxwell and 0.11–0.27 s at Fermi.", "and the response times measure ℓ_t at 0.20–0.47 s at Maxwell and 0.11–0.27 s at Fermi.")
rep("In the 5 bp pools the response times alone would predict fork effects of −0.14 to −0.24 at the two sub-second forks; the estimates are −0.04 to −0.18 because",
    "In the 5 bp pools the response times alone would predict fork effects of −0.16 to −0.24 at the two sub-second forks; the estimates are −0.04 to −0.18 because")
rep("adding the partial response of continuations at the rate observed at Fermi gives about −0.13; the latency fit gives −0.08 to −0.12. For the limit, the components that respond little are 44% of the overshoot in the fortnight before Fermi in the four liquid pools (39–47% across pools; 38% on average over the twelve pool-forks, 17–54%) and 40% in the fortnight after it, when continuations are a further 37%. If a continuation's overshoot is a residual that does not respond plus a drift that scales with √Δt, its response at Fermi (−0.16) implies that about two fifths of it is residual, so the decomposition puts the overshoot at an infinitely fast chain at 0.40 + 0.37 × 0.4 ≈ 0.55 of its 0.45-second level — one half to three fifths (0.49–0.66 with the ±30-day and ±7-day continuation estimates; 0.40 if continuations vanished with the block interval, 0.78 if none of them responded) — against the three quarters to 85% of the latency fit.",
    "adding the partial response of continuations at the rate observed at Fermi gives about −0.15; the latency fit gives −0.08 to −0.12. For the limit, the components that respond little are 44% of the overshoot in the fortnight before Fermi in the four liquid pools (40–47% across pools; 37% on average over the twelve pool-forks, 17–54%) and 41% in the fortnight after it, when continuations are a further 36%. If a continuation's overshoot is a residual that does not respond plus a drift that scales with √Δt, its response at Fermi (−0.18) implies that about three tenths of it is residual, so the decomposition puts the overshoot at an infinitely fast chain at 0.41 + 0.36 × 0.3 ≈ 0.52 of its 0.45-second level — about one half (0.47–0.63 with the ±30-day and ±7-day continuation estimates; 0.41 if continuations vanished with the block interval, 0.77 if none of them responded) — against the three quarters to 85% of the latency fit.")
rep("and the jump component J is 0.23–0.38 bp in the 5 bp pools over the six regimes, a component of the price path rather than of our measurement",
    "and the mean jump component J of strict CEX-triggered arbitrages is 0.21–0.50 bp in the 5 bp pools across the forks, a component of the price path rather than of our measurement")
rep("A single-parameter latency floor fitted to aggregate effects is therefore an *effective* latency: it summarises, in one number, a delay of a quarter of a second and a floor of a different kind — the discreteness of the reference price and of the on-chain flow that creates arbitrage opportunities.",
    "A single-parameter latency floor fitted to aggregate effects is therefore an *effective* latency: it summarises, in one number, a delay of a quarter of a second and a floor of a different kind — the discreteness of the reference price and of the on-chain flow that creates arbitrage opportunities. " + draft("## §7.2 — one sentence to add (after the discussion of ℓ as an effective latency)", "## §7.4 Limitations — add"))

# ---------------------------------------------------------------- 7.3, 7.4
rep("0.43–0.70 for the accumulated movement, 0.11–0.40 for the crossing jump", "0.43–0.54 for the accumulated movement, 0.04–0.15 for the crossing jump")
rep("Sender contracts identify arbitrageurs only up to the contracts an operator uses.",
    "Arbitrageurs are identified by their contracts and by the accounts that sign for them; the flow that reaches the pools through public routers from one-off accounts — 6–23% of strict arbitrages, concentrated in the WBNB pools — cannot be attributed to an operator and is excluded from the response-time and component statistics as ordinary order flow, which it resembles in every observable respect; a bot that rotated a fresh account for every trade would be excluded with it, and the aggregate estimates of Sections 6.1–6.7, which include this flow, describe the mispricing that LPs face rather than the bots' rents alone.")

# ---------------------------------------------------------------- 8, 9
rep("Our address-level evidence is in the same spirit: a handful of contracts execute most CEX–DEX arbitrage on these pools, the main ones shortened their latency between April 2025 and January 2026 — from about a second to a fifth of a second in the ETH pool, from 0.44 s to 0.06 s for the largest contract overall — while the chain's clock was shortened nearly seven-fold, and each fork moved their response times by roughly the mechanical amount, with the arbitrageurs' own speed-up concentrated in the Lorentz and Maxwell windows.",
    "Our address-level evidence is in the same spirit: a handful of operators, the largest of them one contract signing from a fixed pool of wallets, execute most CEX–DEX arbitrage on these pools; the main ones shortened their latency between April 2025 and January 2026 — from about a second to 0.15 s in the ETH pool, from 0.44 s to 0.06 s in the BTCB pool for the largest contract overall — while the chain's clock was shortened nearly seven-fold, each fork moved their response times by roughly the mechanical amount, with the arbitrageurs' own speed-up concentrated in the Lorentz and Maxwell windows, and at 0.45-second blocks the fastest of them sign from pools of 41–189 wallets to keep several transactions in flight — the on-chain form of the co-location race.")
rep("Reconstructing when each of 10.3 million arbitrage opportunities opened shows why", "Reconstructing when each of 6.5 million arbitrage opportunities opened shows why")

# ---------------------------------------------------------------- Appendix E
rep("are 0.5–5.7% of CEX-triggered arbitrages in the core pools.", "are 0.4–5.4% of CEX-triggered arbitrages by arbitrage contracts in the core pools.")
rep("**Table E1. Response times and latency intercepts, four liquid pools, six regimes.** Columns as in Table 18;",
    "**Table E1. Response times and latency intercepts, four liquid pools, six regimes, bot flow.** Columns as in Table 18;")
rep_between("| Pool            | Regime       | Δt (s)   | CEX-triggered arbs   |", "**Figure E1.", T("tableF1_latency_per_pool") + "\n\n")
rep("**Table E2. Arbitrageur contracts: concentration, entry and exit, and the response times of contracts active on both sides of a fork, four liquid pools.** Senders are the contracts that called the pool;",
    "**Table E2. Arbitrageur contracts: concentration, entry and exit, and the response times of contracts active on both sides of a fork, four liquid pools, bot flow.** Senders are the arbitrage contracts that called the pool (public routers excluded);")
rep_between("| Fork | Pool | Sender contracts, pre → post |", "**Table E3.", T("tableF3_addresses") + "\n\n")
rep_between("| Pool | Sender contract | Lorentz, pre (3 s) |", "## Appendix F.", T("tableE3_sender_trajectories") + "\n\n" + """**Table E4. Contracts versus operators, bot flow, four liquid pools.** Operators are the connected components of the graph linking private contracts to the accounts that sign for them (Section 4.5); bot flow excludes arbitrages sent through public routers. Active: at least 20 strict arbitrages in the regime; the share of multi-contract operators is the share of bot arbitrages executed by operators using two or more contracts in the window.

""" + T("E4_contracts_vs_operators") + """

**Table E4b. Entry, exit and paired latency changes: contracts versus operators, bot flow.** Columns as in Table E2, at the contract level and at the operator level; the change of the intercept is for the tenth percentile; the contract-level columns are computed on the arbitrages with transaction data (99.6% of strict arbitrages) and can differ from Table E2 by a millisecond.

""" + T("E4b_entry_exit_operators") + """

**Table E5. Gas prices, position in the block and the cost of an arbitrage, CEX-triggered bot arbitrages in the three core pools.** BNB price: median reference price of the WBNB/USDT pool in the regime; position in block: zero-based index of the transaction, so a median of 3 is the fourth transaction; the gross gain is the arbitrage's loss to the LPs (Section 4.3); the last column is the ratio of total gas cost to total gross gain.

""" + T("E5_gas_position") + """

**Table E6. The largest operators across the six regimes: signing wallets / tenth-percentile latency intercept (ms) / share of the core pools' arbitrages attributed to operators.** Operators among the eight largest of the core pools in at least three regimes; the share is of bot flow plus the router flow attributed to operators (it differs from the bot-flow share by at most 0.02).

""" + T("E6_wallet_pools") + """

**Table E6b. Wallet pools and latency, three core pools pooled.** Share of bot arbitrages executed by contracts signing from at least 30 (5) distinct accounts in the regime; the correlation is across operators with at least 500 CEX-triggered arbitrages in the regime (Spearman, log of the number of wallets against the tenth-percentile intercept).

""" + T("E6b_wallet_rotation") + """

**Table E7. Bot flow and router flow, four liquid pools, ±30 days.** Public routers are contracts called by at least 30 distinct accounts with a median of at most two strict arbitrages each; one-off accounts sent fewer than 20 strict arbitrages in the window through public routers and use no private contract.

""" + T("E7_flow_profiles") + """

**Router flow.** The flow through public routers is concentrated in the two WBNB pools and in the Lorentz and Maxwell windows (Table E7 and Section 4.5). Including it in the response-time statistics lowers the tenth-percentile intercept of the WBNB/USDT 0.05% pool from 344 to 185 ms before Lorentz, from 246 to 60 ms after it and from 249 to 103 ms before Maxwell, and those of the 1 bp pool by 50–230 ms in the same regimes, while the intercepts of the ETH and BTCB pools change by at most 65 ms (and by less than 10 ms outside the Lorentz window); the aggregate strict-overshoot effect of Lorentz is −0.36 with it and −0.29 without it (Table 20). Tables 18–21 and E1–E3 therefore use bot flow. The router flow that comes from persistent accounts (4–11% of strict arbitrages) has the same profile as the one-off flow — median overshoot 0.04–0.27 bp, 37–64% same-block — and is excluded with it; the cost is a small number of bots that call the SmartRouter directly from a stable account (in the Fermi window three accounts sent 92% of the SmartRouter's strict arbitrages, about 2% of all strict arbitrages). Operators can be merged only through shared signing accounts; a bot that used a fresh account for every transaction would appear as anonymous flow, and none of the large ones does.

""")

# ---------------------------------------------------------------- Appendix F
rep("the reconstruction of opening and response times, the component panels and figures — is released",
    "the reconstruction of opening and response times, the component panels, the retrieval of transaction senders and gas and the merging of contracts into operators, and the figures — is released")

# ---------------------------------------------------------------- router-flow robustness of the main overshoot estimates (Table 15b, Table 16 D–F)
rep("After Lorentz the placebo-clean estimate is −0.291 (s.e. 0.041), 84% of the predicted −0.347; after Maxwell",
    "After Lorentz the placebo-clean estimate is −0.291 (s.e. 0.041), 84% of the predicted −0.347 (−0.21, 60%, once the order flow that reaches the pools through public routers is excluded; Section 6.7); after Maxwell")
rep("and the hypothesis that the three forks share one elasticity is rejected in ten of eleven specifications.",
    "and the hypothesis that the three forks share one elasticity is rejected in ten of eleven specifications (with router flow excluded, in the specifications without a trend).")
rep("fits the three estimates with ℓ between 0.6 and 1.1 seconds (the pure √Δt law, ℓ = 0, is rejected",
    "fits the three estimates with ℓ between 0.6 and 1.1 seconds — 1.0 s on the flow of arbitrage contracts alone — (the pure √Δt law, ℓ = 0, is rejected")
rep("against a predicted 0.5, and equality across forks is rejected. Reconstructing",
    "against a predicted 0.5 (0.30 at 3 → 1.5 s on the flow of arbitrage contracts alone), and equality across forks is rejected in most specifications. Reconstructing")
rep("The matched-pair medians (Table 15) are 0.72 and 0.69 for BTCB and ETH against a predicted 0.707, and 0.54 for the WBNB pool at the centre of the wave.",
    "The matched-pair medians (Table 15) are 0.72 and 0.69 for BTCB and ETH against a predicted 0.707, and 0.54 for the WBNB pool at the centre of the wave. The order flow that reaches the pools through public routers (Section 4.5) is part of what these estimates measure; excluding it (Table 15b in Section 6.7) lowers the Lorentz estimate to −0.21 (0.04), 60% of the prediction, and leaves those of Maxwell and Fermi within 0.03 of Table 4.")
rep("with volatility ratios of 0.96–1.11, 0.76–0.85 and 1.01–1.14 in the same pairs.",
    "with volatility ratios of 0.96–1.11, 0.76–0.85 and 1.01–1.14 in the same pairs. (vii) *Router flow.* Table 15b re-estimates every specification of Table 4 on the strict overshoot of bot flow — the arbitrages of arbitrage contracts, excluding those sent through public routers (Section 4.5), which are 22%, 23% and 6% of strict arbitrages in the three windows and up to half of them in the WBNB/USDT 0.05% pool after Lorentz. The Maxwell and Fermi estimates move by at most 0.03 (−0.13 to −0.21 and −0.13 to −0.14 in the placebo-clean specifications, against −0.11 to −0.21 and −0.11 to −0.13 in Table 4); the Lorentz estimates fall from −0.29 to −0.21 in the placebo-clean specifications — 60% of the prediction rather than 84%, an elasticity of 0.30 rather than 0.42 — because the share of router flow, whose overshoot is a tenth of the bots', rose after that fork, and its placebo (+0.05) stays clean (on bot flow's own placebos the Maxwell ±14-day trend specification detects −0.13 (0.06), while the ±30-day trend specification is clean, −0.02). With router flow excluded the three elasticities are closer — 0.30, 0.16 and 0.25 in the ±30-day trend and RD specifications — and their equality is no longer rejected in the trend and RD specifications (p = 0.10–0.96) or in the ±7-day liquidity-and-volume specification (0.29), while it still is in the specifications without a trend (p = 0.00); the pooled elasticity, 0.15–0.34, remains six to nine standard errors below 0.5 in every specification. About 0.08 of the Lorentz estimate is therefore composition, and the conclusion that survives on bot flow is the one the rest of the paper rests on: every fork delivers less than the law, the two sub-second forks two fifths to three fifths of it.")
rep("\n### 6.8 Aligning the reference to the arbitrageur's information: a 250 ms lag",
    "\n**Table 15b. Effect of the block-interval reduction on the log strict overshoot of bot flow (public routers excluded), core pools pooled, three forks, trade reference.** Specifications and columns as in Table 4; the panel is the hourly mean strict overshoot of arbitrages by arbitrage contracts (Section 4.5), and the all-flow version of the same panel reproduces Table 4 to ±0.001. The last six rows are the fake-fork placebos of Table 14 on bot flow (pre-period split at its midpoint), with the all-flow placebo re-estimated on the same panel in brackets (it differs from Table 14 by at most 0.002).\n\n" + T("table15b_bots_core_pooled") + "\n\n### 6.8 Aligning the reference to the arbitrageur's information: a 250 ms lag")
rep("The last two columns give the model's prediction for a further halving from 0.45 s to 0.225 s and the overshoot at Δt → 0 relative to its 0.45-second level.",
    "The last two columns give the model's prediction for a further halving from 0.45 s to 0.225 s and the overshoot at Δt → 0 relative to its 0.45-second level. Sets D–F repeat A–C on the bot-flow estimates of Table 15b (router flow excluded), fitted with the same procedure.")
rep_between("| Estimate set | ℓ (s) | 95% CI |", "**Figure 6.", T("table16_latency_floor_ABCDEF") + "\n\n")
rep("and that the overshoot at an infinitely fast chain would still be 75–85% of its level at 0.45 s.",
    "and that the overshoot at an infinitely fast chain would still be 75–85% of its level at 0.45 s. On bot flow (sets D–F, the same choices of specification with router flow excluded) the fitted latency is 1.0–1.05 s (95% intervals 0.5–1.9 s) whichever set is used, the RD-type set is again fitted well (χ² = 1.8, p = 0.40), the law is still rejected (χ² ≥ 37), and the forward prediction is the same: −0.08 for the next halving and a floor of 83–84% of the 0.45-second level.")
rep("0.59 s corresponds to ℓ_t ≈ 0.25 s (0.11–0.52 s), and the response times measure",
    "0.59 s corresponds to ℓ_t ≈ 0.25 s (0.11–0.52 s) and the 1.0 s of the bot-flow fit to ℓ_t ≈ 0.45 s, and the response times measure")
rep("but by a diminishing fraction of the √Δt law: 84% at the halving from 3 s, a third to a half at the two reductions below 1.5 s.",
    "but by a diminishing fraction of the √Δt law: 84% at the halving from 3 s (60% on the flow of arbitrage contracts alone), a third to a half at the two reductions below 1.5 s.")
rep("and the aggregate estimates of Sections 6.1–6.7, which include this flow, describe the mispricing that LPs face rather than the bots' rents alone.",
    "and the aggregate estimates of Sections 6.1–6.7, which include this flow, describe the mispricing that LPs face rather than the bots' rents alone (Table 15b gives the overshoot estimates without it).")

# ---------------------------------------------------------------- final wording: all-flow headline, one clean bot-flow clause per location
rep("against a predicted 0.5 (0.30 at 3 → 1.5 s on the flow of arbitrage contracts alone), and equality across forks is rejected in most specifications. Reconstructing",
    "against a predicted 0.5, and equality across forks is rejected in most specifications; on the trades of arbitrage contracts alone, excluding the order flow that reaches the pools through public routers, the first fork's elasticity is 0.30 and the other two are unchanged. Reconstructing")
rep("84% of the predicted −0.347 (−0.21, 60%, once the order flow that reaches the pools through public routers is excluded; Section 6.7); after Maxwell",
    "84% of the predicted −0.347 — 60% on the trades of arbitrage contracts alone, once the order flow that reaches the pools through public routers is excluded (Section 6.7); after Maxwell")
rep("is rejected in ten of eleven specifications (with router flow excluded, in the specifications without a trend).",
    "is rejected in ten of eleven specifications, and in the specifications without a trend once router flow is excluded.")
rep("fits the three estimates with ℓ between 0.6 and 1.1 seconds — 1.0 s on the flow of arbitrage contracts alone — (the pure √Δt law, ℓ = 0, is rejected",
    "fits the three estimates with ℓ between 0.6 and 1.1 seconds, 1.0 s on the trades of arbitrage contracts alone (the pure √Δt law, ℓ = 0, is rejected")
rep("84% at the halving from 3 s (60% on the flow of arbitrage contracts alone), a third to a half at the two reductions below 1.5 s. The elasticities differ across the forks.",
    "84% at the halving from 3 s — 60% on the trades of arbitrage contracts alone — and a third to a half at the two reductions below 1.5 s. The elasticities differ across the forks in most specifications.")

# ---------------------------------------------------------------- Appendix C: caption for Table C1 (missing since v3)
_i = s.index("## Appendix C.")
_j = s.index("| Window | Specification | Lorentz β [share]", _i)
s = s[:_j] + ("**Table C1. Effect of the block-interval reduction on the log overshoot at strict arbitrage with the 1-second candle reference: "
              "three core 0.05% pools pooled with pool fixed effects, three forks.** Specifications and columns as in Table 4; the reference is the close "
              "of the last completed 1-second Binance candle before the block timestamp (Section 4.2).\n\n") + s[_j:]

# ---------------------------------------------------------------- abstract: press-conference version (<= 300 words)
NEW_ABSTRACT = """## Abstract

Automated market makers quote stale prices between blocks, and the fee-band model of arbitrage predicts that the mispricing at which arbitrageurs trade — the source of liquidity providers' (LPs') adverse-selection cost — scales with the square root of the block interval. We test it on three pre-announced reductions of BNB Chain's block interval, from 3 s to 1.5, 0.75 and 0.45 s, on the same seven PancakeSwap v3 pools, using 49 million swaps aligned to the last Binance trade before each block at millisecond resolution. The mispricing falls at every fork, but by a diminishing fraction of the √Δt prediction: 84% at the first halving, 28–59% and 44–51% at the two sub-second reductions — an elasticity of 0.42 and then 0.14–0.30 against a predicted 0.5. Reconstructing when each of 6.5 million arbitrage opportunities opened shows why. Arbitrageurs respond with a fixed latency of 0.1–0.35 s at sub-second block times, and only the part of the mispricing that accumulates while they wait for a block — 28% of it — shrinks by the law; the jump of the reference price that opens an opportunity and the overshoot of same-block back-runs do not respond to the clock, and their share grows from 32% at 3-second blocks to 44% at 0.75 s. The diminishing returns are a composition effect, and a further halving would remove about a tenth of the remaining mispricing. Arbitrageurs' profits fall by 8–22% per fork and mispricing episodes become 20–35% shorter, but LPs' gross adverse-selection loss does not fall and, in the 5 bp ETH and BTCB pools, equals their fee income: the block interval is a lever over price efficiency and the distribution of arbitrage rents, not over the cost of providing liquidity. A 1-second candle reference would overstate the sub-second effects, because its staleness co-moves with the block interval.

**Keywords:** automated market makers, loss-versus-rebalancing, block time, arbitrage, latency, decentralized exchanges, natural experiment

"""
i = s.index("## Abstract"); j = s.index("## 1. Introduction")
s = s[:i] + NEW_ABSTRACT + s[j:]


# ================================================================ 回测修正（2026-09-15：数字核对与参考文献核对）
# --- 数字/措辞（核对表格后的修正）
rep("The strict overshoot is a fraction of a basis point at sub-second intervals — 0.36–1.32 bp before Maxwell, 0.47–0.73 bp before Fermi — and 0.6–2.8 bp at 3-second blocks, in every case far below the 5 bp band",
    "The strict overshoot is below one basis point at sub-second intervals — 0.30–0.97 bp after Maxwell and around Fermi — against 0.36–1.32 bp at 1.5-second blocks before Maxwell and 0.6–2.8 bp at 3-second blocks, in every case far below the 5 bp band")
rep("and are insignificant elsewhere, apart from the USDC/USDT placebo pool after Fermi, whose volume rose thirteen-fold in the February stablecoin rotation.",
    "and are insignificant elsewhere, apart from the CAKE/WBNB pool after Lorentz (−0.29) and the USDC/USDT placebo pool after Fermi, whose volume rose more than tenfold after the fork.")
rep("the LPs' loss was predicted to fall by 6–16% at Lorentz and by 2–7% at the later forks",
    "the LPs' loss was predicted to fall by 6–16% at Lorentz and by 2–8% at the later forks")
rep("with the candle reference the Maxwell and Fermi overshoot effects were 58–101% and 76–87% of the prediction, the profit effects 14–45%, and the count of arbitrages appeared to fall after Fermi.",
    "with the candle reference the Maxwell and Fermi overshoot effects were 58–101% and 76–87% of the prediction and the profit falls 14–45% (against 8–22% with the trade reference), and the count of arbitrages appeared to fall after Fermi.")
rep("The trade reference lowers it by only 0.00–0.15 relative to the candle, so reference noise explains little of the shortfall.",
    "The trade reference lowers it by at most 0.16 relative to the candle, and by nothing in most cells, so reference noise explains little of the shortfall.")
rep("After Fermi, the one specification whose profit placebo is clean, ±14 days with liquidity and volume, gives",
    "After Fermi, the one placebo-clean specification whose profit placebo is also clean, ±14 days with liquidity and volume, gives")
rep("attributes the recovery of profits in July to the fork. The ±30-day specifications without a trend, −0.31 and −0.22, are placebo-contaminated for this outcome (Table 14).",
    "attributes the recovery of profits in July to the fork. The profit placebos of this window are contaminated in both directions (+0.16 without a trend, −0.15 with it; Table 14), so the Maxwell profit effect is the least well identified of the three: its sign is robust across the trend and RD designs, its size is not. The ±30-day specifications without a trend, −0.31 and −0.22, are placebo-contaminated for this outcome as well (Table 14).")
rep("is rejected in ten of eleven specifications, and in the specifications without a trend once router flow is excluded.",
    "is rejected at the 10% level in ten of eleven specifications (at 5% in nine), and in five of the six specifications without a trend once router flow is excluded.")
rep("is rejected at the 6% level or better in ten of the eleven specifications (the exception is the ±7-day trend specification, in which nothing is precisely estimated).",
    "is rejected at the 10% level or better in ten of the eleven specifications, at 5% in nine (the exception is the ±7-day trend specification, in which nothing is precisely estimated).")
rep("equality across forks is rejected at the 6% level in eight of eleven specifications",
    "equality across forks is rejected at the 10% level in eight of eleven specifications (at 5% in seven)")
rep("two further reductions that deliver a third to a half of it", "two further reductions that deliver roughly a third to a half of it")
rep("and a third to a half at the two reductions below 1.5 s", "and roughly a third to a half at the two reductions below 1.5 s")
rep("but that part is only a quarter of the mispricing at which arbitrageurs trade",
    "but that part is only a quarter to a third of the mispricing at which arbitrageurs trade")
rep("There is no heterogeneity of the log effect by volatility or time of day at the two later forks",
    "There is little heterogeneity of the log effect by volatility or time of day at the two later forks")
rep("About 0.08 of the Lorentz estimate is therefore composition,", "About 0.08 of the Lorentz estimate in this specification is therefore composition,")
rep("against −0.11 to −0.21 and −0.11 to −0.13 in Table 4", "against −0.10 to −0.21 and −0.11 to −0.13 in Table 4")
rep("roughly the middle of the pre-fork interval at Fermi and a third of it at Maxwell",
    "roughly the middle of the post-fork interval at Fermi and a third of it at Maxwell")
rep("at Lorentz it fell in two pools and rose in the WBNB pool, whose arbitrageurs became faster within the window.",
    "at Lorentz it fell in the ETH and BTCB pools and rose in the two WBNB pools, whose arbitrageurs became faster within the window.")
rep("consistent with the χ² fit at Maxwell, at the lower end of its confidence interval at Fermi.",
    "consistent with the χ² fit at Maxwell, at or below the lower end of its confidence interval at Fermi.")
rep("The CAKE/WBNB and 1% pools give insignificant overshoot estimates at every fork.",
    "The CAKE/WBNB and 1% pools give overshoot estimates that do not differ from zero at the 5% level at any fork.")
rep("The CAKE/WBNB and 1% pools, where strict arbitrages are rare, give imprecise estimates centred near zero.",
    "The CAKE/WBNB and 1% pools, where strict arbitrages are rare, give imprecise estimates (standard errors of 0.09–0.33) that do not differ from zero at the 5% level.")
rep("and by the mechanical amount at Fermi except in the ETH pool", "and by roughly the mechanical amount at Fermi except in the ETH pool")
rep("reductions below 1.5 s delivered a third to a half of it.", "reductions below 1.5 s delivered roughly a third to a half of it (28–59% and 44–51%).")
# --- 未能从输出文件追溯的数字：重算后的精确表述（回测第二轮）
rep("(it differs from the bot-flow share by at most 0.02).",
    "(it differs from the bot-flow share by less than 0.02 in every regime except after Lorentz, where the difference reaches 0.034 for one operator).")
rep("gives an effective ℓ of about 2.2–2.3·ℓ_t in the convention of the fit)", "gives an effective ℓ of about 2.2–2.4·ℓ_t in the convention of the fit)")
rep("the σ elasticity (0.43–0.59 under either alignment) and the placebo results are unchanged.",
    "the σ elasticity (0.43–0.59 under either alignment) and the placebo results are unchanged in sign and, with one exception, in significance (the Fermi ±14-day trend overshoot placebo rises from +0.11 to +0.13 and becomes significant at 5%; that specification is not among the placebo-clean ones).")
# --- 参考文献（Crossref 核对：LNCS 卷的出版年；Capponi & Jia 统一用 RFS 2025 版）
rep("Adams et al., 2025", "Adams et al., 2026", count=3)
rep("Adams, A., Moallemi, C. C., Reynolds, S., & Robinson, D. (2025). am-AMM", "Adams, A., Moallemi, C. C., Reynolds, S., & Robinson, D. (2026). am-AMM")
rep("Milionis, Moallemi and Roughgarden, 2024", "Milionis, Moallemi and Roughgarden, 2025", count=2)
rep("Milionis, Moallemi and Roughgarden (2024)", "Milionis, Moallemi and Roughgarden (2025)")
rep("Milionis et al., 2022, 2024;", "Milionis et al., 2022, 2025;")
rep("Milionis, J., Moallemi, C. C., & Roughgarden, T. (2024). Automated market making and arbitrage profits",
    "Milionis, J., Moallemi, C. C., & Roughgarden, T. (2025). Automated market making and arbitrage profits")
rep("Capponi and Jia, 2021", "Capponi and Jia, 2025")
rep("Capponi and Jia (2021)", "Capponi and Jia (2025)")
rep("Capponi, A., & Jia, R. (2021). The adoption of blockchain-based decentralized exchanges. arXiv:2103.08842. Published in revised form as: Liquidity provision on blockchain-based decentralized exchanges. *Review of Financial Studies*, 38(10), 3040–3085 (2025). https://doi.org/10.1093/rfs/hhaf046",
    "Capponi, A., & Jia, R. (2025). Liquidity provision on blockchain-based decentralized exchanges. *Review of Financial Studies*, 38(10), 3040–3085. https://doi.org/10.1093/rfs/hhaf046 (Earlier version: The adoption of blockchain-based decentralized exchanges, arXiv:2103.08842, 2021.)")
rep("Lehar, A., Parlour, C. A., & Zoican, M. (2024). Fragmentation and optimal liquidity supply on decentralized exchanges. Working paper, SSRN 4267429 / arXiv:2307.13772.",
    "Lehar, A., Parlour, C. A., & Zoican, M. (2024). Fragmentation and optimal liquidity supply on decentralized exchanges. Working paper, SSRN 4267429 (revised May 2024); arXiv:2307.13772.")

open("paper_draft_v41.md", "w").write(s)
print("written", len(s.splitlines()), "lines")
