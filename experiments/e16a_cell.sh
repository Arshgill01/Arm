#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 6 ]]; then
  echo "usage: e16a_cell.sh CONTRACT EVIDENCE_DIR SERVER MODEL IDENTITY REPETITION" >&2
  exit 2
fi

contract_path="$1"
evidence_dir="$2"
server="$3"
model="$4"
identity="$5"
repetition="$6"
cell_dir="$evidence_dir/cells/$(printf '%02d' "$repetition")-r${repetition}"
dump_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/pareto64-e16a-r${repetition}-XXXXXX")"
sidecar_path="${RUNNER_TEMP:-/tmp}/pareto64-e16a-sidecar-r${repetition}.bin"
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

mkdir -p "$cell_dir"
export GGML_CPU_REPACK_DUMP_DIR="$dump_dir"
jq -n \
  --arg variable "GGML_CPU_REPACK_DUMP_DIR" \
  --arg value "$dump_dir" \
  '{variable: $variable, value: $value, fresh_generated_scratch_directory: true}' \
  > "$cell_dir/environment.json"

CONTRACT_PATH="$contract_path" SERVER_PATH="$server" MODEL_PATH="$model" \
  REPETITION="$repetition" python3 - <<'PY' > "$cell_dir/recipe.json"
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
recipe = {
    "schema_version": 1,
    "experiment_id": "E16a",
    "repetition": int(os.environ["REPETITION"]),
    "source": contract["source"],
    "build": contract["build"],
    "service": contract["service"],
    "server_path": server,
    "server_version": capture_server_version(server),
    "model": {
        "path": model,
        "sha256": contract["selected"]["model_sha256"],
        "size_bytes": contract["selected"]["model_size_bytes"],
    },
    "runtime_environment": {
        "GGML_CPU_REPACK_DUMP_DIR": "fresh generated scratch directory",
    },
    "argv": argv,
}
print(json.dumps(recipe, indent=2, sort_keys=True))
PY
mapfile -t launch < <(jq -r '.argv[]' "$cell_dir/recipe.json")
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell_dir/runner-state-before.txt"
/usr/bin/time --verbose --output "$cell_dir/server-time.log" \
  "${launch[@]}" > "$cell_dir/server.stdout.log" 2> "$cell_dir/server.stderr.log" &
active_timer_pid=$!
python3 experiments/e3d_http_quality.py wait \
  --url http://127.0.0.1:18081 \
  --timeout 120 \
  --output "$cell_dir/readiness.json"
for _ in $(seq 1 50); do
  active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
  if [[ -n "$active_server_pid" ]]; then
    break
  fi
  sleep 0.1
done
test -n "$active_server_pid"
echo "$active_server_pid" > "$cell_dir/server-pid.txt"
python3 experiments/e5b_inference_probe.py \
  --url http://127.0.0.1:18081 \
  --tasks experiments/e3_tasks.json \
  --reference-manifest results/manifests/e3f-30656151957.json \
  --candidate ministral3_3b_q4_k_m \
  --configuration persistent_prepack_feasibility \
  --repetition "$repetition" \
  --warmup-task arithmetic-02 \
  --warmup-task logic-01 \
  --warmup-slot 0 \
  --warmup-slot 0 \
  --concurrency 1 \
  --max-output-tokens 8 \
  --seed 424242 \
  --timeout 30 \
  --experiment-id E16a \
  --server-pid "$active_server_pid" \
  --cache-prompt \
  --output "$cell_dir/probe.json"
curl --fail --silent http://127.0.0.1:18081/metrics > "$cell_dir/metrics.txt"
curl --fail --silent http://127.0.0.1:18081/slots > "$cell_dir/slots.json"
curl --fail --silent http://127.0.0.1:18081/health > "$cell_dir/health.json"
kill -INT "$active_server_pid"
set +e
wait "$active_timer_pid"
server_status=$?
set -e
echo "$server_status" > "$cell_dir/server-shell-exit.txt"
[[ "$server_status" -eq 0 || "$server_status" -eq 130 ]]
active_server_pid=""
active_timer_pid=""
cp "$dump_dir/inventory.tsv" "$cell_dir/inventory.tsv"
cp "$dump_dir/runtime.tsv" "$cell_dir/runtime.tsv"

python3 experiments/e16a_sidecar.py build \
  --dump-dir "$dump_dir" \
  --identity "$identity" \
  --output "$sidecar_path" \
  --index "$cell_dir/sidecar-index.json" \
  > "$cell_dir/build-sidecar-result.json"
python3 experiments/e16a_sidecar.py verify \
  --sidecar "$sidecar_path" \
  --index "$cell_dir/sidecar-index.json" \
  > "$cell_dir/verification.json"

DUMP_DIR="$dump_dir" SIDECAR_PATH="$sidecar_path" \
  INDEX_PATH="$cell_dir/sidecar-index.json" python3 - <<'PY' > "$cell_dir/cleanup.json"
import csv
import json
import os
from pathlib import Path

dump = Path(os.environ["DUMP_DIR"])
sidecar = Path(os.environ["SIDECAR_PATH"])
index = json.loads(Path(os.environ["INDEX_PATH"]).read_text())
with (dump / "inventory.tsv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
raw_bytes = 0
for row in rows:
    path = dump / row["file"]
    if not path.is_file() or path.stat().st_size != int(row["bytes"]):
        raise ValueError(f"generated repack tensor differs before cleanup: {path}")
    raw_bytes += path.stat().st_size
    path.unlink()
if any(dump.glob("*.bin")):
    raise ValueError("generated repack tensor cleanup is incomplete")
sidecar_bytes = sidecar.stat().st_size
if sidecar_bytes != index["sidecar_size_bytes"]:
    raise ValueError("generated sidecar size differs before cleanup")
sidecar.unlink()
print(json.dumps({
    "deleted_raw_tensor_bytes": raw_bytes,
    "deleted_raw_tensor_count": len(rows),
    "deleted_sidecar_bytes": sidecar_bytes,
    "generated_binary_bytes_deleted": raw_bytes + sidecar_bytes,
    "generated_binary_cleanup_complete": not sidecar.exists(),
}, indent=2, sort_keys=True))
PY
test ! -e "$sidecar_path"
test -z "$(find "$dump_dir" -maxdepth 1 -type f -name '*.bin' -print -quit)"
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell_dir/runner-state-after.txt"
trap - EXIT
