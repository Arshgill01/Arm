#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: e20a_bench_cell.sh CASE" >&2
  exit 2
fi

case_name="$1"
cell_dir="$EVIDENCE_DIR/bench/$case_name"
mkdir -p "$cell_dir"

CASE_NAME="$case_name" CELL_DIR="$cell_dir" python3 - <<'PY'
import json
import os
from pathlib import Path

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
matches = [item for item in contract["benchmark"]["cases"] if item["name"] == os.environ["CASE_NAME"]]
if len(matches) != 1:
    raise ValueError("E20a benchmark case differs")
case = matches[0]
replacements = {
    "BENCH_PATH": str(Path(os.environ["BUILD_DIR"]) / "bin/llama-bench"),
    "MODEL_PATH": os.environ["MODEL"],
}
argv = [replacements.get(value, value) for value in case["argv"]]
(Path(os.environ["CELL_DIR"]) / "command.json").write_text(
    json.dumps({"argv": argv, "case": case}, indent=2, sort_keys=True) + "\n"
)
PY

mapfile -t command < <(jq -r '.argv[]' "$cell_dir/command.json")
timing="$(jq -r '.case.node_timing' "$cell_dir/command.json")"
if [[ "$timing" == true ]]; then
  /usr/bin/time --verbose --output "$cell_dir/process-time.log" \
    env GGML_CPU_NODE_TIMING=1 "${command[@]}" \
    > "$cell_dir/result.jsonl" 2> "$cell_dir/stderr.log"
else
  /usr/bin/time --verbose --output "$cell_dir/process-time.log" \
    env -u GGML_CPU_NODE_TIMING "${command[@]}" \
    > "$cell_dir/result.jsonl" 2> "$cell_dir/stderr.log"
fi
