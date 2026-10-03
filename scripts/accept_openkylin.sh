#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
OUT="${OUT:-$ROOT/results/openkylin-$(date +%Y%m%d-%H%M%S)}"
cd "$ROOT"
mkdir -p "$OUT"
"$PYTHON" kmb doctor --require-openkylin --out "$OUT/platform.json"
"$PYTHON" -m unittest discover -s tests -v > "$OUT/tests.log" 2>&1
"$PYTHON" kmb generate --seed 20261003 --per-dimension 4 --out "$OUT/dataset.json"
"$PYTHON" kmb validate "$OUT/dataset.json"
"$PYTHON" kmb run --dataset "$OUT/dataset.json" --config configs/calibration.json --repeat 3 --out "$OUT/calibration"
RUNS=()
while IFS= read -r path; do RUNS+=("${path%/run.json}"); done < <(find "$OUT/calibration" -name run.json | sort)
"$PYTHON" kmb compare "${RUNS[@]}" --out "$OUT/calibration-report"
if [[ -n "${REAL_AGENT_CONFIG:-}" ]]; then
  "$PYTHON" kmb run --dataset "$OUT/dataset.json" --config "$REAL_AGENT_CONFIG" --repeat "${REPEATS:-3}" --out "$OUT/real-agents"
  REAL_RUNS=()
  while IFS= read -r path; do REAL_RUNS+=("${path%/run.json}"); done < <(find "$OUT/real-agents" -name run.json | sort)
  "$PYTHON" kmb compare "${REAL_RUNS[@]}" --out "$OUT/real-report"
fi
printf 'Evidence directory: %s\n' "$OUT"
