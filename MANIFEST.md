# Manifest: tables and figures of the revised manuscript, the scripts and the inputs that generate them

Paths are relative to the package root. "Hourly panels" means `<fork>_tick/bundle/analysis_agg/hourly_panel.parquet`
for the three forks (trade reference, ±30 days; `analysis_agg_14d/` for ±14 days); "component panels" means
`arb_resp/comp_bots/<Fork>/arb_response_bots/component_panels/<pool>.csv` (hourly means of the strict overshoot of
bot flow by trigger type, with J and M for CEX-triggered arbitrages, and the hourly response-time statistics).
The pipeline scripts that produce these inputs from the raw data are listed at the end.

## Main text

| Item | Content | Script | Inputs |
|---|---|---|---|
| Table 1 | The three block-interval reductions | compiled in `paper/v6/02_setting.md` from BNB Chain release notes (BEP-524, BEP-563, BEP-590, BEP-126) | block counts and hourly mean intervals: `<fork>_tick/bundle/results_agg/blocks_hourly.csv`; swap counts: `<fork>_tick/bundle/summary_agg.json` |
| Table 2 | Pools, sample sizes, pre-fork exposure | compiled in `paper/v6/02_setting.md` | `<fork>_tick/bundle/summary_agg.json`, `<fork>_tick/bundle/analysis_agg/table_exposure.md` (pipeline `full_analysis.py`) |
| Table 3 | Main specification, all outcomes and classifications, with placebos and elasticities | `paper/main_spec.py` → `paper/tables_v6/table_main.md`, `main_spec.json` | hourly panels; component panels |
| Figure 1 | Overshoot along the roadmap vs the √Δt law and the latency-floor model | `paper/build_figures_v6.py` → `paper/figures_v6/fig2_roadmap.png` | `paper/tables_v6/main_spec.json`, `latency_floor_v6.json` |
| Table 4 | LPs' loss / fee income at two mark-out horizons; fee-tier margin | `paper/lp_levels.py` → `table_lp_levels.md`, `table_fee_tier.md`, `lp_levels.json` | hourly panels (`fee_income`, `lp_gain`, `arb_loss`, `markout_30s`, `volume`, `liquidity`) |
| Table 5 | Elasticities to σ within regimes: response times, competition, components | `paper/vol_competition.py` → `paper/vol_competition.md`, `vol_competition.json` | component panels; hourly panels (σ, volume, liquidity) |
| Table 6 | Predictions, tests and verdicts | compiled in `paper/v6/06b_results.md` from Tables 3–5, 7 and Figures 2–3 | — |
| Table 7 | Latency-floor model fitted to the main-specification estimates | `paper/latency_floor_v6.py` → `table_latency_floor.md`, `latency_floor_v6.json` | `paper/tables_v6/main_spec.json` |
| Figure 2 | Share of arbitrages landing in the first block vs Δt | `paper/build_figures_v6.py` → `fig5_first_block.png` | `arb_resp/cmp_bots/key_numbers.json` (from `arb_resp/compare_bots.py`) |
| Figure 3 | Fork effect by component, four pools, main specification | `paper/build_figures_v6.py` → `fig7_component_effects.png`, `paper/tables_v6/components_pool_main.json` | component panels; hourly panels |
| §6.7 text table (Table D4 in the appendix) | Response times across six regimes | `arb_resp/compare_bots.py` → `arb_resp/cmp_bots/R1_six_regime_latency.md`, `R1b_regime_summary.md` | `arb_resp/bots/<Fork>/arb_response_bots/<pool>/{regime_stats.json, turnbull.csv}` |

## Appendix A — descriptive statistics, data validation, reference prices

| Item | Script | Inputs / outputs |
|---|---|---|
| Table A1 (descriptives, ±14 d) | pipeline `full_analysis.py --days 14` | `<fork>_tick/bundle/analysis_agg_14d/table_regimes.md`, `hourly_panel.parquet` |
| Figure A1 (block intervals) | `paper/build_figures_v6.py` → `fig1_block_interval.png` | `<fork>_tick/bundle/results_agg/blocks_hourly.csv` |
| Table A2 (post/pre ratios of σ, volume, L) | pipeline `core_analysis.py` | `<fork>_tick/bundle/extra_agg/sigma_path.md` |
| Table A3 (σ elasticity of the overshoot) | pipeline `full_analysis.py`, `core_analysis.py` | `<fork>_tick/bundle/analysis_agg*/table_regressions.md`, `extra_agg/core_pooled.md` |
| Figure A2 (σ and activity around the forks) | `paper/build_figures_v6.py` → `figA1_sigma_overshoot.png` | hourly panels |
| Timestamp validation, reference construction | pipeline `find_blocks.py`, `rpc.py`, `fetch_binance.py`, `analyze_pilot.py` | `<fork>_tick/bundle/summary_agg.json` (cross-check counts) |

## Appendix B — the full grid and additional estimates

| Item | Script | Inputs / outputs |
|---|---|---|
| Tables B1–B3 (grid: overshoot, profit and loss, placebos incl. RD placebos) | `paper/grid_v6.py` → `paper/tables_v6/table_grid_{overshoot,profit_loss,placebo}.md`, `grid_v6.json` | hourly panels (±30 d and ±14 d) |
| Figure B1 (event study, daily residuals) | `paper/build_figures_v6.py` → `fig3_event_study.png` | hourly panels |
| Table B4 (stacked three-fork panel) | `paper/three_forks.py` → `paper/three_forks_tick/tableC_stacked.md`, `stacked.json` | hourly panels |
| Table B5 (four classifications × four specifications) | `paper/classification_table.py` → `paper/tables_v6/table_classification_full.md`, `classification.json` | hourly panels; component panels |
| Table B6 (pool by pool, ±14 d) | pipeline `full_analysis.py --days 14` | `<fork>_tick/bundle/analysis_agg_14d/table_regressions.md` |
| Table B7 (decomposition of the LPs' loss) | pipeline `core_analysis.py` | `<fork>_tick/bundle/extra_agg/core_pooled.md` |
| Table B8 (heterogeneity) | pipeline `core_analysis.py` | `<fork>_tick/bundle/extra_agg/heterogeneity.md` |
| Table B9 (matched pairs) | pipeline `full_analysis.py --days 14` | `<fork>_tick/bundle/analysis_agg_14d/table_matched.md` |
| Table B10 (grid on bot flow) | `paper/robust_bots.py` → `paper/tables_v41/table15b_bots_core_pooled.md`, `paper/robust_bots.json` | component panels |
| Table B11 (price efficiency) | pipeline `full_analysis.py` | `<fork>_tick/bundle/results_agg/*/regime tables`, `analysis_agg/table_regimes.md` |

## Appendix C — candle versus trade reference; the reference lag

| Item | Script | Inputs / outputs |
|---|---|---|
| Table C1 (candle vs trade, selected specifications) | `paper/three_forks.py` run on the candle bundles (`lorentz/`, `maxwell/`, `fermi/`) and on the trade bundles | `paper/three_forks/tableA_three_forks.md`, `paper/three_forks_tick/tableA_three_forks.md` |
| Table C2, Figure C1 (the wedge at the fork) | `tick_cmp/compare_fork.py`, tables assembled by `paper/build_tables_v3.py` | `tick_cmp/<Fork>/*.md`, `tick_cmp/levels_three_forks.csv`; figure `paper/build_figures_v6.py` → `fig4_wedge.png` |
| Table C3 (reference gap by regime) | pipeline `full_analysis.py` (`ref_gap_bps`, `ref_kline_vs_tick_rms_bps`) | `<fork>_tick/bundle/results_agg/`, `analysis_agg/table_regimes.md` |
| Table C4 (full grid, candle reference) | `paper/three_forks.py` (candle bundles) | `paper/three_forks/tableA_three_forks.md` |
| Tables C5–C7 (reference lagged 250 ms) | `lag_cmp/lag_cmp.py` | `maxwell_lag250/`, `fermi_lag250/` (pipeline run with `--ref-lag-ms 250`), outputs `lag_cmp/tableL*.md`; the lag-250 latency-floor refit: `paper/latency_floor_v6.py` (`--lag250` block) |

## Appendix D — opening times, operators, simulations

| Item | Script | Inputs / outputs |
|---|---|---|
| Table D1 (simulated σ elasticities) | `paper/sim_sigma_elasticity.py` (uses pipeline `simulate_response_test.py` and `arb_response.py`) | `paper/sim_sigma_elasticity.md`, `.json` |
| Tables D2–D3 (σ elasticities with controls; terciles) | `paper/vol_competition.py` | `paper/vol_competition.md`, `.json` |
| Table D4 (response times, six regimes, core pools) and D6 (four pools) | `arb_resp/compare_bots.py` | `arb_resp/cmp_bots/R1_six_regime_latency.md`, `R1b_regime_summary.md`; `arb_resp/bots/<Fork>/arb_response_bots/<pool>/regime_stats.json`, `turnbull.csv` |
| Table D5 (fork effects on the components, main specification) | `paper/main_spec.py` → `paper/tables_v6/table_main_components.md` | component panels |
| Figure D1 (latency intercepts) | `paper/build_figures_v6.py` → `fig6_latency_intercepts.png`, `paper/tables_v6/latency_band.json` | `arb_resp/cmp_bots/key_numbers.json` |
| Table D7, Figure D2 (fork effects implied by response times; twelve-point test) | `arb_resp/compare_bots.py` → `R2_implied_vs_tick.md`, `R4_twelve_point_test.md`, `R4_points.csv`; figure `paper/build_figures_v6.py` → `figD1_twelve_point.png` | `arb_resp/bots/…/regime_stats.json`; `paper/tables_v6/grid_v6.json` |
| Table D8 (components: pooled fork effects and σ elasticities, per pool) | `paper/build_tables_v41_bots.py` → `paper/tables_v41/table20_components_pooled.md`, `table21_components_per_pool.md`, `table21b_sigma_elasticity_components.md` | component panels; `arb_resp/cmp_bots/R3c_component_regressions.md` |
| Tables D9–D10 (contracts; sender trajectories) | `arb_resp/compare_bots.py` → `R5_addresses.md`, `R6_senders.md`, `R6b_sender_trajectories.md`; `paper/build_tables_v41_bots.py` → `tableF3_addresses.md`, `tableE3_sender_trajectories.md` | `arb_resp/bots/…/{top_senders_pre,top_senders_post,paired_senders}.csv` |
| Tables D11–D16 (operators, entry/exit, gas, top operators, wallet pools, router flow) | `arb_resp/ops/ops_analysis.py` → `arb_resp/ops/out/R1…R7.md`, `out2/`; `paper/build_tables_v41.py` → `paper/tables_v41/E4…E7.md` | `arb_resp/ops/<Fork>/arb_response/operators/<pool>_contracts.csv` and `<pool>_arbs_tx.parquet` (large-data archive); `arb_resp/ops/public_lists/` |
| Validation on simulated data (latency recovery, selection) | pipeline `simulate_response_test.py` | writes `sim_response/` and runs `arb_response.py` on it |

## Appendix E and the manuscript

`paper/make_v6.py` assembles `paper/paper_v6.md` from `paper/v6/*.md` (body), `paper/tables_v6/*.md` (grid and classification tables) and `paper/paper_df.md` (the appendices of the first submission, edited in place by the script); `paper/sn/md2sn.py` typesets it in the Springer `sn-jnl` class; `paper/md2docx.js` exports Word.

## Pipeline scripts (raw data → processed data), `dex-lit/bnb_blocktime_pilot/`

| Script | Stage |
|---|---|
| `config.py` | Fork dates and blocks, pool and token registry, event signatures |
| `rpc.py`, `find_blocks.py` | JSON-RPC client; block-timestamp reconstruction from sparse anchors with bisection (Section 4.1, Appendix A) |
| `fetch_swaps.py`, `fetch_hypersync.py`, `hypersync_probe.py` | Swap-event retrieval (`eth_getLogs` / HyperSync) and their cross-check |
| `fetch_binance.py` | Binance 1-second klines and aggregate trades (data.binance.vision) |
| `analyze_pilot.py` | Swap-level enrichment: pool prices, both reference prices (candle; trade at lag 0 or lag N ms), deviations, arbitrage classification, LP gain, fee income, adverse-selection loss, mark-outs at +5 s and +30 s |
| `run_pilot.py` | End-to-end driver for one fork (streaming, resumable) → `results_agg/`, `summary_agg.json` |
| `full_analysis.py` | Hourly pool panels (±30 d, ±14 d), regime tables, regressions, matched pairs, placebos, price-efficiency statistics |
| `core_analysis.py`, `dose_response.py` | Core-pool pooled estimates, RD jumps, placebos, heterogeneity, σ paths; cross-fork comparisons |
| `arb_response.py` | Opening times, trigger types, response times, block counts, J and M components; Turnbull estimator; sender tables |
| `arb_component_panel.py` | Hourly component panels from the arbitrage-level tables |
| `fetch_tx_from.py`, `arb_operators.py` | Signing accounts and gas of the active contracts; public/private classification; bipartite contract–wallet graph → operators |
| `simulate_test.py`, `simulate_response_test.py`, `mock_server.py` | Synthetic data with known latencies for end-to-end validation |
