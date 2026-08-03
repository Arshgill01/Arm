#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 6 ]]; then
  echo "usage: e16b_construct.sh CONTRACT EVIDENCE_DIR SERVER MODEL IDENTITY SIDECAR" >&2
  exit 2
fi

contract_path="$1"
evidence_dir="$2"
server="$3"
model="$4"
identity="$5"
sidecar="$6"
construction_dir="$evidence_dir/construction"
dump_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/pareto64-e16b-dump-XXXXXX")"
active_timer_pid=""
active_server_pid=""

cleanup_process() {
  if [[ -n "$active_server_pid" ]] && kill -0 "$active_server_pid" 2>/dev/null; then
    kill -INT "$active_server_pid" 2>/dev/null || true
  fi
  if [[ -n "$active_timer_pid" ]]; then
    wait "$active_timer_pid" 2>/dev/null || true
  fi
}
trap cleanup_process EXIT

mkdir -p "$construction_dir"
export GGML_CPU_REPACK_DUMP_DIR="$dump_dir"
unset GGML_CPU_REPACK_SIDECAR || true

CONTRACT_PATH="$contract_path" SERVER_PATH="$server" MODEL_PATH="$model" \
  python3 - <<'PY' > "$construction_dir/recipe.json"
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
server = str(Path(os.environ["SERVER_PATH"]).resolve())
model = str(Path(os.environ["MODEL_PATH"]).resolve())
argv = expected_server_argv(
    server,
    model,
    candidate=contract["selected"]["candidate"],
    profile_name="e7c_final",
)
argv.extend(["--log-verbosity", str(contract["mechanism"]["proof_log_verbosity"])])
print(json.dumps({
    "schema_version": 1,
    "experiment_id": "E16b",
    "phase": "one_time_sidecar_construction",
    "server_path": server,
    "server_version": capture_server_version(server),
    "model_path": model,
    "runtime_environment": {
        "GGML_CPU_REPACK_DUMP_DIR": "fresh generated scratch directory",
        "GGML_CPU_REPACK_SIDECAR": None,
    },
    "argv": argv,
}, indent=2, sort_keys=True))
PY
mapfile -t launch < <(jq -r '.argv[]' "$construction_dir/recipe.json")
/usr/bin/time --verbose --output "$construction_dir/server-time.log" \
  "${launch[@]}" > "$construction_dir/server.stdout.log" 2> "$construction_dir/server.stderr.log" &
active_timer_pid=$!
python3 experiments/e3d_http_quality.py wait \
  --url http://127.0.0.1:18081 \
  --timeout 120 \
  --output "$construction_dir/readiness.json"
for _ in $(seq 1 50); do
  active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
  if [[ -n "$active_server_pid" ]]; then
    break
  fi
  sleep 0.1
done
test -n "$active_server_pid"
echo "$active_server_pid" > "$construction_dir/server-pid.txt"
kill -INT "$active_server_pid"
set +e
wait "$active_timer_pid"
server_status=$?
set -e
echo "$server_status" > "$construction_dir/server-shell-exit.txt"
[[ "$server_status" -eq 0 || "$server_status" -eq 130 ]]
active_timer_pid=""
active_server_pid=""

cp "$dump_dir/inventory.tsv" "$construction_dir/inventory.tsv"
cp "$dump_dir/runtime.tsv" "$construction_dir/runtime.tsv"
/usr/bin/time --verbose --output "$construction_dir/sidecar-build-time.log" \
  python3 experiments/e16a_sidecar.py build \
    --dump-dir "$dump_dir" \
    --identity "$identity" \
    --output "$sidecar" \
    --index "$construction_dir/sidecar-index.json" \
    > "$construction_dir/build-sidecar-result.json"
python3 experiments/e16a_sidecar.py verify \
  --sidecar "$sidecar" \
  --index "$construction_dir/sidecar-index.json" \
  > "$construction_dir/verification.json"

DUMP_DIR="$dump_dir" INDEX_PATH="$construction_dir/sidecar-index.json" \
  python3 - <<'PY' > "$construction_dir/raw-dump-cleanup.json"
import csv
import json
import os
from pathlib import Path

dump = Path(os.environ["DUMP_DIR"])
index = json.loads(Path(os.environ["INDEX_PATH"]).read_text())
with (dump / "inventory.tsv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
raw_bytes = 0
for row in rows:
    path = dump / row["file"]
    if not path.is_file() or path.stat().st_size != int(row["bytes"]):
        raise ValueError(f"generated tensor differs before cleanup: {path}")
    raw_bytes += path.stat().st_size
    path.unlink()
if any(dump.glob("*.bin")):
    raise ValueError("generated tensor cleanup is incomplete")
print(json.dumps({
    "deleted_raw_tensor_bytes": raw_bytes,
    "deleted_raw_tensor_count": len(rows),
    "raw_tensor_cleanup_complete": True,
    "sidecar_retained_for_measured_cells": True,
    "sidecar_sha256": index["sidecar_sha256"],
    "sidecar_size_bytes": index["sidecar_size_bytes"],
}, indent=2, sort_keys=True))
PY
test -z "$(find "$dump_dir" -maxdepth 1 -type f -name '*.bin' -print -quit)"
trap - EXIT
