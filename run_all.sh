#!/usr/bin/env bash
# Regenerates every table and figure from the processed data (tables_v6/, figures_v6/).
# Run from the package root:  bash run_all.sh      (about 2 minutes; sim_sigma_elasticity.py is optional, ~10 minutes)
set -euo pipefail
export REPL_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPL_ROOT/paper"
for s in main_spec.py lp_levels.py latency_floor_v6.py grid_v6.py vol_competition.py tau_sigma_clean.py classification_table.py build_figures_v6.py table3_pvalues.py; do
  if { [ "$s" = vol_competition.py ] || [ "$s" = tau_sigma_clean.py ]; } && [ ! -f "$REPL_ROOT/arb_resp/ops/Fermi/arb_response/operators/ETH-USDT-500_arbs_tx.parquet" ]; then
    echo "=== $s skipped: needs the arbitrage-level operator tables of the large-data archive (Table 5, Tables D2-D3, Supplementary Table S5); shipped outputs kept"
    continue
  fi
  echo "=== $s"
  python3 "$s"
done
echo "Outputs: paper/tables_v6/, paper/figures_v6/"
echo "Optional: python3 paper/sim_sigma_elasticity.py --out \"$REPL_ROOT/sim_sigma\"   (Table D1)"
