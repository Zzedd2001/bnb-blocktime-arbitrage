# Arbitrage competition and volatility within the hour (three core pools, bot flow, CEX-triggered arbitrages)

Elasticity (or level response for shares) of each hourly statistic to log σ within each block-interval regime; hour-of-day and pool fixed effects; day-clustered standard errors in parentheses. Hours with at least 20 CEX-triggered bot arbitrages.

| Outcome | Lorentz pre | Lorentz post | Maxwell pre | Maxwell post | Fermi pre | Fermi post |
|---|---|---|---|---|---|---|
| median response time τ (log) | -0.21 (0.02) | -0.15 (0.04) | -0.09 (0.01) | -0.12 (0.02) | -0.09 (0.01) | -0.03 (0.02) |
| 10th-percentile τ (log) | -0.35 (0.04) | -0.29 (0.07) | -0.18 (0.05) | -0.15 (0.03) | -0.27 (0.04) | -0.12 (0.03) |
| E[√τ] (log) | -0.20 (0.01) | -0.17 (0.02) | -0.14 (0.01) | -0.17 (0.02) | -0.15 (0.01) | -0.11 (0.01) |
| share landing in the first block (level) | +0.14 (0.01) | +0.09 (0.02) | +0.09 (0.01) | +0.08 (0.01) | +0.08 (0.01) | +0.02 (0.01) |
| active contracts in the hour (log) | +0.53 (0.03) | +0.61 (0.03) | +0.48 (0.03) | +0.41 (0.02) | +0.45 (0.03) | +0.48 (0.04) |
| bot arbitrages in the hour (log) | +1.08 (0.02) | +1.04 (0.04) | +1.04 (0.05) | +1.27 (0.03) | +1.21 (0.04) | +1.33 (0.03) |
| share of the largest contract (level) | -0.05 (0.01) | -0.16 (0.03) | -0.08 (0.01) | +0.01 (0.02) | -0.04 (0.01) | -0.06 (0.01) |
| movement component M (log) | +0.52 (0.06) | +0.54 (0.18) | +0.55 (0.06) | +0.81 (0.33) | +0.80 (0.21) | +0.97 (0.12) |
| crossing jump J (log) | +0.22 (0.03) | +0.35 (0.04) | +0.39 (0.03) | +0.37 (0.05) | +0.23 (0.04) | +0.39 (0.03) |
| overshoot of CEX-triggered arbs (log) | +0.43 (0.03) | +0.47 (0.05) | +0.45 (0.03) | +0.44 (0.03) | +0.32 (0.03) | +0.56 (0.03) |

Within each regime with log volume and log liquidity added (same hours, hour-of-day and pool FE):

| Outcome | Lorentz pre | Lorentz post | Maxwell pre | Maxwell post | Fermi pre | Fermi post |
|---|---|---|---|---|---|---|
| median response time τ (log) | -0.08 (0.03) | -0.08 (0.05) | -0.08 (0.03) | -0.01 (0.03) | -0.04 (0.03) | -0.05 (0.02) |
| 10th-percentile τ (log) | -0.13 (0.10) | -0.25 (0.09) | -0.08 (0.11) | -0.05 (0.07) | -0.09 (0.08) | +0.06 (0.07) |
| E[√τ] (log) | -0.08 (0.02) | -0.06 (0.03) | -0.11 (0.03) | -0.03 (0.03) | -0.09 (0.02) | -0.07 (0.02) |
| share landing in the first block (level) | +0.04 (0.02) | +0.06 (0.03) | +0.08 (0.02) | -0.01 (0.03) | +0.07 (0.02) | +0.04 (0.02) |
| active contracts in the hour (log) | +0.05 (0.07) | +0.25 (0.10) | +0.08 (0.09) | +0.08 (0.05) | +0.27 (0.06) | +0.08 (0.05) |
| bot arbitrages in the hour (log) | +0.42 (0.08) | +0.21 (0.09) | +0.44 (0.08) | +0.50 (0.05) | +0.70 (0.10) | +0.67 (0.08) |
| share of the largest contract (level) | -0.03 (0.02) | -0.12 (0.04) | -0.03 (0.03) | +0.02 (0.03) | -0.04 (0.02) | +0.00 (0.02) |
| movement component M (log) | +0.58 (0.31) | -0.03 (0.55) | +0.48 (0.14) | +0.58 (0.59) | +1.78 (0.55) | +0.64 (0.26) |
| crossing jump J (log) | -0.03 (0.08) | +0.27 (0.09) | +0.13 (0.08) | -0.07 (0.09) | +0.07 (0.07) | -0.02 (0.09) |
| overshoot of CEX-triggered arbs (log) | +0.24 (0.05) | +0.31 (0.07) | +0.27 (0.07) | +0.16 (0.04) | +0.21 (0.04) | +0.18 (0.06) |

With log volume and log liquidity added, pooled across the two regimes of each fork (regime fixed effect):

| Outcome | Lorentz | Maxwell | Fermi |
|---|---|---|---|
| median response time τ (log) | -0.08 (0.03) | -0.04 (0.02) | -0.04 (0.02) |
| 10th-percentile τ (log) | -0.19 (0.07) | -0.08 (0.06) | +0.02 (0.06) |
| E[√τ] (log) | -0.06 (0.02) | -0.07 (0.02) | -0.08 (0.01) |
| share landing in the first block (level) | +0.02 (0.02) | +0.03 (0.02) | +0.05 (0.01) |
| active contracts in the hour (log) | +0.20 (0.05) | +0.06 (0.04) | +0.16 (0.05) |
| bot arbitrages in the hour (log) | +0.32 (0.06) | +0.48 (0.05) | +0.69 (0.06) |
| share of the largest contract (level) | -0.09 (0.02) | +0.02 (0.02) | -0.02 (0.01) |
| movement component M (log) | +0.73 (0.22) | +0.36 (0.32) | +1.12 (0.27) |
| crossing jump J (log) | +0.09 (0.06) | -0.03 (0.06) | +0.02 (0.05) |
| overshoot of CEX-triggered arbs (log) | +0.28 (0.04) | +0.19 (0.04) | +0.20 (0.04) |

Median response time (ms) and first-block share by within-regime tercile of σ (hours pooled over the three pools):

| Regime | Δt (s) | τ median, low σ | mid | high | first block, low σ | mid | high | contracts/h, low | mid | high |
|---|---|---|---|---|---|---|---|---|---|---|
| Lorentz pre | 3.00 | 2644 | 2544 | 2255 | 0.60 | 0.64 | 0.74 | 5.5 | 6.4 | 8.9 |
| Lorentz post | 1.50 | 1432 | 1415 | 1380 | 0.54 | 0.57 | 0.61 | 6.0 | 7.3 | 9.6 |
| Maxwell pre | 1.50 | 1258 | 1258 | 1190 | 0.64 | 0.65 | 0.71 | 6.2 | 6.8 | 8.8 |
| Maxwell post | 0.75 | 761 | 736 | 712 | 0.50 | 0.52 | 0.56 | 7.4 | 8.5 | 10.2 |
| Fermi pre | 0.75 | 634 | 623 | 585 | 0.64 | 0.67 | 0.71 | 7.0 | 8.1 | 10.0 |
| Fermi post | 0.45 | 443 | 428 | 416 | 0.52 | 0.55 | 0.56 | 8.0 | 9.4 | 12.9 |
