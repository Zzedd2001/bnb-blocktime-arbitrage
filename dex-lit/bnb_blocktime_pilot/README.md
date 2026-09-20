# Data pipeline: BNB Chain block intervals × PancakeSwap v3 arbitrage and LP economics

All inputs are public and free: BNB Smart Chain JSON-RPC nodes (block headers, contract calls), Envio HyperSync or
`eth_getLogs` (Swap event logs) and Binance's public market-data archive, data.binance.vision (1-second klines and
aggregate trades). No credentials are stored in the code; the HyperSync token is read from `ENVIO_API_TOKEN`
and an `eth_getLogs` endpoint from `--logs-rpc` / `BSC_LOGS_RPC`. Every stage is streaming and resumable and runs
on a laptop with 16 GB of memory.

## Stages

1. **Blocks and timestamps** (`find_blocks.py`, `rpc.py`). The fork block and the window's block range are located
   from the fork's announced timestamp. Block timestamps are reconstructed from sparse anchors: BNB Chain's consensus
   sets each block's timestamp to its parent's plus the nominal interval (3 s / 1.5 s / 0.75 s / 0.45 s) unless the
   chain lags wall-clock time (never earlier), so headers are fetched every ten minutes, each span whose elapsed time
   equals the nominal one is filled in exactly, and the others are bisected until the irregular blocks are found.
   Millisecond timestamps exist since Lorentz (`milliTimestamp`); before Lorentz whole seconds are exact.
   The reconstruction is cross-checked, swap by swap, against the timestamps returned by the log providers.
2. **Swap events** (`fetch_swaps.py`, `fetch_hypersync.py`, `hypersync_probe.py`). `Swap` logs of the seven pools
   (PancakeSwap v3 layout, with `protocolFeesToken0/1` appended to the Uniswap v3 layout) for 720 hours before and
   after the fork, decoded to post-trade √price, signed amounts, active liquidity and transaction hash.
   `hypersync_probe.py` checks that HyperSync and `eth_getLogs` return identical events on a reference slice.
3. **Reference prices** (`fetch_binance.py`). 1-second klines (BNBUSDT, ETHUSDT, BTCUSDT, CAKEUSDT) and aggregate
   trades, compressed to a "last price per millisecond" table per day (`binance_agg/<SYMBOL>/<day>.parquet`).
4. **Swap-level enrichment** (`analyze_pilot.py`, driven by `run_pilot.py`). For every swap: pool price before and
   after, the candle reference (close of the last completed 1-second candle before the block timestamp) and the
   trade reference (last aggregate trade at or before the block timestamp, `--reference aggtrades`; at least N ms
   before it with `--ref-lag-ms N`), the pre- and post-trade deviations, the arbitrage classification (identified /
   strict), the LP's mark-to-market gain, fee income, adverse-selection loss, and mark-outs at +5 s and +30 s.
   Output: `results_agg/<pool>/swaps_enriched.parquet` (candle-reference runs write `results/`).
5. **Hourly panels and regime tables** (`full_analysis.py`, `core_analysis.py`, `dose_response.py`). Pool-hour
   aggregates (`analysis_agg/hourly_panel.parquet`, ±30 d; `analysis_agg_14d/`, ±14 d), regime tables, the price-
   efficiency statistics on the 1-second grid, regressions, matched pairs and placebos per pool; core-pool pooled
   estimates, RD jumps, heterogeneity and σ paths (`extra_agg/`).
6. **Opening times and response times** (`arb_response.py`). For every identified arbitrage: when the opportunity
   opened (last crossing of the reference price out of the no-arbitrage band since the previous swap, or the previous
   block's swap that pushed the pool price out of the band), the trigger type (CEX-triggered, on-chain-triggered,
   continuation, same-block), the response time τ, the number of blocks sealed in between, the jump J and movement
   M components, the interval-censored latency and its Turnbull estimate, the quantile intercepts, sender tables.
   `--exclude-senders public_contracts_<Fork>.csv` restricts to bot flow (public routers excluded).
7. **Component panels** (`arb_component_panel.py`). Hourly means of the overshoot by trigger type, of J and M, and
   the hourly response-time statistics (`component_panels/<pool>.csv`).
8. **Senders, gas and operators** (`fetch_tx_from.py`, `arb_operators.py`). The signing account, gas price and
   position in the block of every swap of the contracts with at least twenty strict arbitrages in the window;
   classification of contracts as public (many one-off callers) or private; the bipartite contract–wallet graph whose
   connected components are the operators; entry, exit, wallet pools and latency by operator.
9. **Validation on synthetic data** (`simulate_test.py`, `simulate_response_test.py`, `mock_server.py`). The whole
   pipeline runs on simulated chains with known latencies and no network; the response-time stage must recover the
   simulated latency distribution and a zero "latency-change" component at the synthetic fork.

## Commands (one fork; repeat for Lorentz, Maxwell, Fermi)

```
pip install -r ../../requirements.txt
export ENVIO_API_TOKEN=<token>                       # free account at envio.dev; or use --logs-rpc <eth_getLogs endpoint>

python run_pilot.py --fork Fermi --hours 720 --pools all --out full_fermi --include-swaps --hypersync --workers 4 --reference aggtrades
python full_analysis.py --results full_fermi --subdir results_agg
python full_analysis.py --results full_fermi --subdir results_agg --days 14 --out full_fermi/analysis_agg_14d
python core_analysis.py --bundle full_fermi --label Fermi --out full_fermi/extra_agg --analysis-dir analysis_agg --analysis14-dir analysis_agg_14d --summary summary_agg.json

python arb_response.py --out full_fermi --fork Fermi
python arb_component_panel.py --out full_fermi --fork Fermi
python fetch_tx_from.py --out full_fermi --fork Fermi
python arb_operators.py --dir full_fermi/arb_response/operators --fork Fermi --out full_fermi/arb_response/operators/out
python arb_response.py --out full_fermi --fork Fermi --reuse --exclude-senders public_contracts_Fermi.csv
python arb_component_panel.py --out full_fermi --fork Fermi --tag bots

# reference aligned 250 ms before the block (Appendix C)
python run_pilot.py --fork Fermi --hours 720 --pools all --out full_fermi --include-swaps --hypersync --workers 4 --reference aggtrades --ref-lag-ms 250
python full_analysis.py --results full_fermi --subdir results_agg_lag250
python full_analysis.py --results full_fermi --subdir results_agg_lag250 --days 14 --out full_fermi/analysis_agg_lag250_14d
python core_analysis.py --bundle full_fermi --label Fermi-lag250 --out full_fermi/extra_agg_lag250 --analysis-dir analysis_agg_lag250 --analysis14-dir analysis_agg_lag250_14d --summary summary_agg_lag250.json

# candle reference (the convention of the earlier literature; Appendix C)
python run_pilot.py --fork Fermi --hours 720 --pools all --out full_fermi --include-swaps --hypersync --workers 4
python full_analysis.py --results full_fermi

# synthetic validation, no network
python simulate_test.py --hours 6 --out results/sim
python simulate_response_test.py --out sim_response
```

Run times on a laptop: swap-event retrieval minutes to an hour per fork with HyperSync; aggregate-trade download
6–8 GB and one to two hours per fork; enrichment about an hour per fork; response times a few minutes per pool.
The processed outputs of these commands for the three forks are the `<fork>_tick/bundle/`, `<fork>/`,
`<fork>_lag250/` and `arb_resp/` directories of the replication package (`full_<fork>` renamed).

## Definitions (Section 4 of the paper)

* pre-trade deviation `dev_pre = p_pre / P − 1`; identified arbitrage: `|dev_pre| > γ` and the trade moves the pool
  price toward `P`; strict arbitrage: in addition `|dev_post| ≤ γ`; overshoot `|dev_pre| − γ`.
* `lp_gain = ΔQ + ΔB · P`; `fee_income = γ × input value`; `arb_loss = fee_income − lp_gain` (gross adverse-selection
  loss); `markout_30s = ΔQ + ΔB · P(t + 30 s)`; `arb_profit = Σ_arbs (arb_loss − fee_income)`.
* realised volatility σ: hourly, from 1-minute log returns of the Binance reference, per √second.
* response time τ: block timestamp minus the opening time; quantile intercepts `Q_q(τ) − q·Δt`; Turnbull NPMLE on
  the interval `(t_{b−1} − t_open, t_b − t_open]`.
