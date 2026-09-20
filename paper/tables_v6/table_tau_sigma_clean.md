# Response time and volatility on the subsamples with an unambiguous opening time (arbitrage level)

Coefficient on log σ (the hour's Binance realised volatility) in a regression of the arbitrage-level outcome on log σ, hour-of-day and pool fixed effects within each block-interval regime, three core pools pooled, bot flow, ±30-day windows; standard errors clustered by day in parentheses, exact two-sided p-values; sample sizes in the last block. Rows with controls add the hour's log volume and log active liquidity.


**All CEX-triggered arbitrages**

| Sample / outcome | Lorentz pre (3.0 s) | Lorentz post (1.5 s) | Maxwell pre (1.5 s) | Maxwell post (0.75 s) | Fermi pre (0.75 s) | Fermi post (0.45 s) |
|:--|:--|:--|:--|:--|:--|:--|
| log τ, no further controls | -0.374 (0.016), p < 0.001 | -0.368 (0.043), p < 0.001 | -0.228 (0.018), p < 0.001 | -0.231 (0.022), p < 0.001 | -0.240 (0.016), p < 0.001 | -0.157 (0.016), p < 0.001 |
| log τ, with log volume and log liquidity | -0.190 (0.038), p < 0.001 | -0.069 (0.053), p = 0.20 | -0.091 (0.035), p = 0.009 | -0.095 (0.052), p = 0.068 | -0.135 (0.029), p < 0.001 | -0.038 (0.040), p = 0.33 |
| first-block indicator, no further controls | +0.148 (0.008), p < 0.001 | +0.121 (0.016), p < 0.001 | +0.091 (0.008), p < 0.001 | +0.079 (0.011), p < 0.001 | +0.086 (0.006), p < 0.001 | +0.025 (0.010), p = 0.014 |
| first-block indicator, with log volume and log liquidity | +0.040 (0.022), p = 0.071 | +0.025 (0.021), p = 0.23 | +0.045 (0.018), p = 0.010 | +0.028 (0.020), p = 0.16 | +0.072 (0.014), p < 0.001 | +0.031 (0.015), p = 0.038 |

**Sharp openings (crossing trade ≥ ½γ beyond the edge)**

| Sample / outcome | Lorentz pre (3.0 s) | Lorentz post (1.5 s) | Maxwell pre (1.5 s) | Maxwell post (0.75 s) | Fermi pre (0.75 s) | Fermi post (0.45 s) |
|:--|:--|:--|:--|:--|:--|:--|
| log τ, no further controls | -0.240 (0.079), p = 0.002 | -0.133 (0.068), p = 0.048 | -0.176 (0.065), p = 0.007 | +0.002 (0.043), p = 0.96 | -0.062 (0.045), p = 0.17 | -0.193 (0.058), p < 0.001 |
| log τ, with log volume and log liquidity | +0.128 (0.152), p = 0.40 | +0.292 (0.149), p = 0.050 | -0.661 (0.193), p < 0.001 | -0.032 (0.121), p = 0.79 | +0.027 (0.161), p = 0.87 | +0.227 (0.235), p = 0.33 |
| first-block indicator, no further controls | +0.062 (0.025), p = 0.012 | -0.009 (0.026), p = 0.74 | +0.026 (0.032), p = 0.42 | +0.027 (0.041), p = 0.52 | +0.060 (0.045), p = 0.18 | +0.034 (0.036), p = 0.34 |
| first-block indicator, with log volume and log liquidity | -0.128 (0.074), p = 0.085 | -0.064 (0.072), p = 0.37 | +0.080 (0.091), p = 0.38 | -0.016 (0.103), p = 0.88 | +0.131 (0.180), p = 0.47 | -0.062 (0.077), p = 0.42 |

**On-chain-triggered arbitrages (τ from block timestamps only)**

| Sample / outcome | Lorentz pre (3.0 s) | Lorentz post (1.5 s) | Maxwell pre (1.5 s) | Maxwell post (0.75 s) | Fermi pre (0.75 s) | Fermi post (0.45 s) |
|:--|:--|:--|:--|:--|:--|:--|
| log τ, no further controls | -0.242 (0.029), p < 0.001 | -0.118 (0.025), p < 0.001 | -0.081 (0.029), p = 0.005 | -0.165 (0.050), p < 0.001 | -0.171 (0.052), p < 0.001 | -0.102 (0.023), p < 0.001 |
| log τ, with log volume and log liquidity | -0.143 (0.116), p = 0.22 | +0.119 (0.051), p = 0.018 | +0.060 (0.067), p = 0.37 | +0.032 (0.048), p = 0.51 | +0.208 (0.108), p = 0.053 | +0.000 (0.045), p = 0.99 |
| first-block indicator, no further controls | +0.175 (0.021), p < 0.001 | +0.074 (0.019), p < 0.001 | +0.050 (0.023), p = 0.029 | +0.079 (0.026), p = 0.002 | +0.024 (0.032), p = 0.45 | +0.037 (0.017), p = 0.026 |
| first-block indicator, with log volume and log liquidity | +0.124 (0.075), p = 0.098 | -0.119 (0.040), p = 0.003 | -0.027 (0.063), p = 0.67 | -0.023 (0.029), p = 0.44 | -0.160 (0.065), p = 0.013 | -0.016 (0.036), p = 0.65 |

**Sample sizes per regime (three core pools pooled)**

| Regime | CEX-triggered | sharp openings (share) | on-chain-triggered |
|:--|--:|--:|--:|
| Lorentz pre | 61,524 | 484 (0.8%) | 908 |
| Lorentz post | 52,729 | 525 (1.0%) | 1,530 |
| Maxwell pre | 49,370 | 398 (0.8%) | 945 |
| Maxwell post | 79,353 | 736 (0.9%) | 1,311 |
| Fermi pre | 61,512 | 345 (0.6%) | 465 |
| Fermi post | 129,744 | 1,281 (1.0%) | 1,723 |
