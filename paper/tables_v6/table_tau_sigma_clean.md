# Response time and volatility on the subsamples with an unambiguous opening time (arbitrage level)

Coefficient on log σ (the hour's Binance realised volatility) in a regression of the arbitrage-level outcome on log σ, hour-of-day and pool fixed effects within each block-interval regime, three core pools pooled, bot flow, ±30-day windows; standard errors clustered by day in parentheses, exact two-sided p-values from t(G−1); sample sizes in the last block. Rows with controls add the hour's log volume and log active liquidity.


**All CEX-triggered arbitrages**

| Sample / outcome | Lorentz pre (3.0 s) | Lorentz post (1.5 s) | Maxwell pre (1.5 s) | Maxwell post (0.75 s) | Fermi pre (0.75 s) | Fermi post (0.45 s) |
|:--|:--|:--|:--|:--|:--|:--|
| log τ, no further controls | -0.374 (0.016), p < 0.001 | -0.368 (0.043), p < 0.001 | -0.228 (0.018), p < 0.001 | -0.231 (0.022), p < 0.001 | -0.240 (0.016), p < 0.001 | -0.157 (0.016), p < 0.001 |
| log τ, with log volume and log liquidity | -0.190 (0.038), p < 0.001 | -0.069 (0.053), p = 0.21 | -0.091 (0.035), p = 0.014 | -0.095 (0.052), p = 0.078 | -0.135 (0.029), p < 0.001 | -0.038 (0.040), p = 0.34 |
| first-block indicator, no further controls | +0.148 (0.008), p < 0.001 | +0.121 (0.016), p < 0.001 | +0.091 (0.008), p < 0.001 | +0.079 (0.011), p < 0.001 | +0.086 (0.006), p < 0.001 | +0.025 (0.010), p = 0.020 |
| first-block indicator, with log volume and log liquidity | +0.040 (0.022), p = 0.081 | +0.025 (0.021), p = 0.24 | +0.045 (0.018), p = 0.015 | +0.028 (0.020), p = 0.17 | +0.072 (0.014), p < 0.001 | +0.031 (0.015), p = 0.047 |

**Sharp openings (crossing trade ≥ ½γ beyond the edge)**

| Sample / outcome | Lorentz pre (3.0 s) | Lorentz post (1.5 s) | Maxwell pre (1.5 s) | Maxwell post (0.75 s) | Fermi pre (0.75 s) | Fermi post (0.45 s) |
|:--|:--|:--|:--|:--|:--|:--|
| log τ, no further controls | -0.240 (0.079), p = 0.005 | -0.133 (0.068), p = 0.058 | -0.176 (0.065), p = 0.011 | +0.002 (0.043), p = 0.96 | -0.062 (0.045), p = 0.18 | -0.193 (0.058), p = 0.002 |
| log τ, with log volume and log liquidity | +0.128 (0.152), p = 0.41 | +0.292 (0.149), p = 0.060 | -0.661 (0.193), p = 0.002 | -0.032 (0.121), p = 0.79 | +0.027 (0.161), p = 0.87 | +0.227 (0.235), p = 0.34 |
| first-block indicator, no further controls | +0.062 (0.025), p = 0.018 | -0.009 (0.026), p = 0.74 | +0.026 (0.032), p = 0.43 | +0.027 (0.041), p = 0.52 | +0.060 (0.045), p = 0.19 | +0.034 (0.036), p = 0.35 |
| first-block indicator, with log volume and log liquidity | -0.128 (0.074), p = 0.095 | -0.064 (0.072), p = 0.38 | +0.080 (0.091), p = 0.39 | -0.016 (0.103), p = 0.88 | +0.131 (0.180), p = 0.47 | -0.062 (0.077), p = 0.43 |

**On-chain-triggered arbitrages (τ from block timestamps only)**

| Sample / outcome | Lorentz pre (3.0 s) | Lorentz post (1.5 s) | Maxwell pre (1.5 s) | Maxwell post (0.75 s) | Fermi pre (0.75 s) | Fermi post (0.45 s) |
|:--|:--|:--|:--|:--|:--|:--|
| log τ, no further controls | -0.242 (0.029), p < 0.001 | -0.118 (0.025), p < 0.001 | -0.081 (0.029), p = 0.009 | -0.165 (0.050), p = 0.002 | -0.171 (0.052), p = 0.002 | -0.102 (0.023), p < 0.001 |
| log τ, with log volume and log liquidity | -0.143 (0.116), p = 0.23 | +0.119 (0.051), p = 0.025 | +0.060 (0.067), p = 0.38 | +0.032 (0.048), p = 0.51 | +0.208 (0.108), p = 0.063 | +0.000 (0.045), p = 0.99 |
| first-block indicator, no further controls | +0.175 (0.021), p < 0.001 | +0.074 (0.019), p < 0.001 | +0.050 (0.023), p = 0.037 | +0.079 (0.026), p = 0.005 | +0.024 (0.032), p = 0.46 | +0.037 (0.017), p = 0.034 |
| first-block indicator, with log volume and log liquidity | +0.124 (0.075), p = 0.11 | -0.119 (0.040), p = 0.005 | -0.027 (0.063), p = 0.67 | -0.023 (0.029), p = 0.44 | -0.160 (0.065), p = 0.019 | -0.016 (0.036), p = 0.66 |

**Pooled elasticity of log τ to log σ with controls: inverse-variance-weighted mean of the six regime estimates**

| Sample | Pooled elasticity (s.e.) | t against zero | t against the full-sample value (difference / its s.e.) | Heterogeneity Q (5 d.f.), p |
|:--|:--|:--|:--|:--|
| All CEX-triggered arbitrages | -0.111 (0.016) | -7.07, p < 0.001 | — | 9.4, p = 0.093 |
| Sharp openings (crossing trade ≥ ½γ beyond the edge) | +0.016 (0.065) | +0.25, p = 0.80 | +1.91, p = 0.056 | 17.2, p = 0.004 |
| On-chain-triggered arbitrages (τ from block timestamps only) | +0.048 (0.024) | +1.97, p = 0.048 | +5.49, p < 0.001 | 8.2, p = 0.15 |

**All CEX-triggered arbitrages by size of the crossing jump J (bp beyond the band edge): elasticity of log τ to log σ with controls**

| J (bp) | Lorentz pre | Lorentz post | Maxwell pre | Maxwell post | Fermi pre | Fermi post | Pooled (s.e.), p | Q (5 d.f.), p | n |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| [0, 0.05) | -0.136 (0.066) | -0.051 (0.073) | -0.110 (0.045) | -0.135 (0.065) | -0.210 (0.054) | -0.135 (0.041) | -0.134 (0.022), p < 0.001 | 3.6, p = 0.61 | 102,383 |
| [0.05, 0.15) | -0.209 (0.060) | -0.037 (0.061) | -0.111 (0.061) | -0.107 (0.056) | -0.172 (0.048) | -0.085 (0.044) | -0.120 (0.022), p < 0.001 | 5.9, p = 0.32 | 115,329 |
| [0.15, 0.4) | -0.251 (0.058) | -0.034 (0.073) | -0.041 (0.047) | -0.141 (0.081) | -0.100 (0.062) | -0.077 (0.053) | -0.102 (0.024), p < 0.001 | 9.6, p = 0.087 | 119,727 |
| [0.4, 1) | -0.239 (0.063) | -0.133 (0.070) | -0.098 (0.058) | +0.017 (0.038) | -0.029 (0.047) | +0.082 (0.069) | -0.048 (0.022), p = 0.027 | 18.1, p = 0.003 | 72,396 |
| [1, 2.5) | +0.122 (0.089) | -0.215 (0.113) | -0.019 (0.085) | +0.095 (0.066) | +0.092 (0.086) | +0.145 (0.138) | +0.050 (0.036), p = 0.17 | 8.0, p = 0.16 | 20,628 |
| ≥ 2.5 (sharp openings) | +0.128 (0.152) | +0.292 (0.149) | -0.661 (0.193) | -0.032 (0.121) | +0.027 (0.161) | +0.227 (0.235) | +0.016 (0.065), p = 0.80 | 17.2, p = 0.004 | 3,769 |

Quartiles of J (bp): 0.05, 0.15, 0.36; 90th, 95th and 99th percentiles: 0.72, 1.06, 2.35.

**Sample sizes per regime (three core pools pooled)**

| Regime | CEX-triggered | sharp openings (share) | on-chain-triggered | day-clusters |
|:--|--:|--:|--:|--:|
| Lorentz pre | 61,524 | 484 (0.8%) | 908 | 31 |
| Lorentz post | 52,729 | 525 (1.0%) | 1,530 | 31 |
| Maxwell pre | 49,370 | 398 (0.8%) | 945 | 31 |
| Maxwell post | 79,353 | 736 (0.9%) | 1,311 | 31 |
| Fermi pre | 61,512 | 345 (0.6%) | 465 | 31 |
| Fermi post | 129,744 | 1,281 (1.0%) | 1,723 | 31 |
