## 2. Institutional Setting

### 2.1 BNB Chain's block-interval roadmap

BNB Smart Chain runs a proof-of-staked-authority consensus (Parlia) in which a fixed set of validators produce blocks in turn at a fixed nominal interval. In 2025–26 the chain implemented a three-stage roadmap toward sub-second blocks (Table [[T:forks]]; BNB Chain, 2025a, 2025b, 2026). The Lorentz hard fork (BEP-520, 29 April 2025 05:05 UTC, block 48,773,576) halved the interval from 3 s to 1.5 s and introduced millisecond timestamps; the Maxwell hard fork (BEP-524, 30 June 2025 02:30 UTC, block 52,337,091) halved it again to 0.75 s; the Fermi hard fork (BEP-619, 14 January 2026 02:30 UTC, block 75,140,593) reduced it to 0.45 s. Each fork was announced weeks in advance with a fixed activation time; the timing followed client releases and validator upgrades, not market conditions.

Each fork bundled other changes (Table [[T:forks]]). Gas limits were cut with the interval so as to hold per-second throughput roughly constant, and daily gas utilisation stayed between 9% and 61% around the forks (Figure [[F:A:blocks]]), so none of the changes created congestion, and none touches how a swap is priced. Finality changed with the interval too: under BNB Chain's fast-finality rule (BEP-126) a block is final once its child has been justified by two thirds of the validators, so time to finality is a fixed number of block intervals — about 2.5 — and shortened in step with the interval at every fork, from roughly 7.5 s before Lorentz to about 1.9 s after Maxwell (BNB Chain, 2025b) and about 1.1 s after Fermi; Fermi's BEP-590 lets a proposer include votes for up to three ancestor blocks, which improves the resilience of finality without changing its latency. Because finality is defined in blocks, its change cannot be separated from the change of the interval; Section 7.3 discusses what this implies for the estimand. The forks were clean in the sense that matters for the design — the same validators, PancakeSwap contracts, LPs and arbitrageurs operated before and after — but they were not the only thing happening in their windows (Section 5).

**Table [[T:forks]]. The three block-interval reductions.**

| Fork | Activation (UTC) | Block | Δt before → after | Predicted log change of overshoot and arbitrage profit, ½·ln(Δt₁/Δt₀) | Bundled changes | Concurrent events in the ±30-day window |
|:--|:--|--:|:--|--:|:--|:--|
| Lorentz (BEP-520) | 2025-04-29 05:05 | 48,773,576 | 3 s → 1.5 s | −0.347 | gas limit 140 M → 70 M (throughput unchanged); millisecond timestamps | US tariff shock (2–9 April); CAKE tokenomics overhaul (23 April – 7 May); PancakeSwap Infinity launch; Binance Alpha trading-rewards ramp from early May |
| Maxwell (BEP-524) | 2025-06-30 02:30 | 52,337,091 | 1.5 s → 0.75 s | −0.347 | validator turn 8 → 16 blocks; finality ≈ 1.9 s; gas limit 125 M → 75 M | Binance Alpha volume cycle (peak early June, trough late June); gas-limit increase 100 M → 125 M on 4 June |
| Fermi (BEP-619) | 2026-01-14 02:30 | 75,140,593 | 0.75 s → 0.45 s | −0.255 | gas limit 100 M → 55 M; fast-finality voting rules (BEP-590) | crypto sell-off of 1–6 February 2026 (volatility ×1.7–1.8 over the 30 days after the fork) |

### 2.2 PancakeSwap v3 and the pools

PancakeSwap v3 is a concentrated-liquidity AMM with the Uniswap v3 design: LPs post liquidity on price ranges, trades move the price along a constant-product curve within the active range, and a fee tier (0.01%, 0.05%, 0.25% or 1%) is charged on the input amount. We study seven pools (Table [[T:pools]]). The three 0.05% pools for WBNB/USDT, ETH/USDT and BTCB/USDT are the *core sample*: liquid pools of volatile assets whose external price is observed on Binance with bid–ask noise of a few hundredths to a few tenths of a basis point, small relative to the 5 bp fee band. The 0.01% WBNB/USDT pool is the chain's main routing pool and is analysed separately because its band is of the order of the reference-price noise; the USDC/USDT 0.01% pool is a placebo (σ ≈ 0.09 bp/√s, so CEX–DEX arbitrage is economically irrelevant); and the CAKE/WBNB 0.25% and WBNB/USDT 1% pools have exposures σ√Δt/γ — how far the price drifts within one block relative to the fee band — too low to expect measurable effects.

**Table [[T:pools]]. Pools, sample sizes and pre-fork exposure.** Swaps in the ±30-day windows around Lorentz / Maxwell / Fermi; exposure is σ√Δt/γ from Binance realised volatility in the 14 days before each fork.

| Pool | Fee | Role | Swaps (millions), L / M / F | Exposure before the fork, L / M / F |
|:--|:--|:--|:--|:--|
| WBNB/USDT 0.01% | 1 bp | routing pool; band ≈ reference noise | 6.56 / 15.05 / 12.46 | 0.92 / 0.60 / 0.51 |
| WBNB/USDT 0.05% | 5 bp | core | 5.24 / 2.33 / 0.62 | 0.18 / 0.12 / 0.11 |
| ETH/USDT 0.05% | 5 bp | core | 0.50 / 0.52 / 0.60 | 0.42 / 0.34 / 0.16 |
| BTCB/USDT 0.05% | 5 bp | core | 0.25 / 0.25 / 0.63 | 0.26 / 0.17 / 0.12 |
| USDC/USDT 0.01% | 1 bp | placebo (σ ≈ 0.09 bp/√s) | 0.70 / 2.37 / 1.09 | 0.14 / 0.11 / 0.08 |
| CAKE/WBNB 0.25% | 25 bp | low exposure | 0.07 / 0.08 / 0.02 | 0.10 / 0.04 / 0.03 |
| WBNB/USDT 1% | 100 bp | near-inactive; placebo | 0.003 / 0.003 / 0.004 | 0.01 / 0.01 / 0.01 |
