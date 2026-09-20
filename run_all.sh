#!/usr/bin/env bash
# Regenerates every v6 table and figure of the paper from the processed data, then reassembles paper_v6.md.
# Run from the package root:  bash run_all.sh      (about 2 minutes; sim_sigma_elasticity.py is optional, ~10 minutes)
set -euo pipefail
export REPL_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPL_ROOT/paper"
for s in main_spec.py lp_levels.py latency_floor_v6.py grid_v6.py vol_competition.py classification_table.py build_figures_v6.py make_v6.py; do
  if [ "$s" = vol_competition.py ] && [ ! -f "$REPL_ROOT/arb_resp/ops/Fermi/arb_response/operators/ETH-USDT-500_arbs_tx.parquet" ]; then
    echo "=== $s skipped: needs the arbitrage-level operator tables of the large-data archive (Table 5, Tables D2-D3); shipped outputs kept"
    continue
  fi
  echo "=== $s"
  python3 "$s"
done
echo "Outputs: paper/tables_v6/, paper/figures_v6/, paper/paper_v6.md"
echo "Optional: python3 paper/sim_sigma_elasticity.py --out \"$REPL_ROOT/sim_sigma\"   (Table D1)"
