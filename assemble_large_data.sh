#!/usr/bin/env bash
# Restores the arbitrage-level tables (the "large-data" part of the package, ~750 MB) into this directory from the
# nine archives written by the pipeline (arb_response.py and fetch_tx_from.py write them next to each fork's output):
#   arb_response_<Fork>.zip        -> arb_resp/<Fork>/arb_response/<pool>/arbs_sample.parquet, ...
#   arb_response_bots_<Fork>.zip   -> arb_resp/bots/<Fork>/arb_response_bots/<pool>/arbs_sample.parquet, ...
#   arb_txfrom_<Fork>.zip          -> arb_resp/ops/<Fork>/arb_response/operators/<pool>_arbs_tx.parquet, ...
# Usage:  bash assemble_large_data.sh <directory under which the nine zip files can be found (searched recursively,
#         e.g. the pipeline folder holding full_lorentz/, full_maxwell/, full_fermi/)>
set -euo pipefail
SRC="${1:?directory under which the arb_response_*.zip, arb_response_bots_*.zip and arb_txfrom_*.zip files live}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
locate() { local f; f="$(find "$SRC" -name "$1" -type f | head -n 1)"; [ -n "$f" ] || { echo "missing: $1" >&2; exit 1; }; echo "$f"; }
for F in Lorentz Maxwell Fermi; do
  mkdir -p "$ROOT/arb_resp/$F" "$ROOT/arb_resp/bots/$F" "$ROOT/arb_resp/ops/$F"
  unzip -oq "$(locate arb_response_$F.zip)"      -d "$ROOT/arb_resp/$F"
  unzip -oq "$(locate arb_response_bots_$F.zip)" -d "$ROOT/arb_resp/bots/$F"
  unzip -oq "$(locate arb_txfrom_$F.zip)"        -d "$ROOT/arb_resp/ops/$F"
done
echo "done: $(find "$ROOT/arb_resp" -name '*.parquet' | wc -l) parquet files under arb_resp/"
