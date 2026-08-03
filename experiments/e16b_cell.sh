#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 8 ]]; then
  echo "usage: e16b_cell.sh CONTRACT EVIDENCE_DIR SERVER MODEL SIDECAR INDEX CONFIG REPETITION" >&2
  exit 2
fi

contract_path="$1"
evidence_dir="$2"
server="$3"
model="$4"
sidecar="$5"
index="$6"
configuration="$7"
repetition="$8"
cell_index="$(jq -r --arg name "$configuration" --argjson repetition "$repetition" \
  '.execution.order | to_entries[] | select(.value.configuration == $name and .value.repetition == $repetition) | .key + 1' \
  "$contract_path")"
cell_dir="$evidence_dir/cells/$(printf '%02d' "$cell_index")-${configuration}-r${repetition}"
active_timer_pid=""
active_server_pid=""

cleanup() {
  if [[ -n "$active_server_pid" ]] && kill -0 "$active_server_pid" 2>/dev/null; then
    kill -INT "$active_server_pid" 2>/dev/null || true
  fi
  if [[ -n "$active_timer_pid" ]]; then
    wait "$active_timer_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p "$cell_dir"
unset GGML_CPU_REPACK_DUMP_DIR || true
if [[ "$configuration" == "sidecar_loader" ]]; then
  python3 experiments/e16a_sidecar.py verify \
    --sidecar "$sidecar" --index "$index" > "$cell_dir/prelaunch-verification.json"
  GGML_CPU_REPACK_SIDECAR="$sidecar"
  GGML_CPU_REPACK_SIDECAR_EXPERIMENT_ID="$(jq -r '.header.binding.experiment_id' "$index")"
  GGML_CPU_REPACK_SIDECAR_MODEL_SHA256="$(jq -r '.header.binding.source_model_sha256' "$index")"
  GGML_CPU_REPACK_SIDECAR_SOURCE_COMMIT="$(jq -r '.header.binding.llama_cpp_commit' "$index")"
  GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256="$(jq -r '.header.binding.source_diff_sha256' "$index")"
  GGML_CPU_REPACK_SIDECAR_ARCHITECTURE="$(jq -r '.header.binding.cpu.architecture' "$index")"
  GGML_CPU_REPACK_SIDECAR_CPU_FEATURES_SHA256="$(jq -r '.header.binding.cpu.common_features_sha256' "$index")"
  GGML_CPU_REPACK_SIDECAR_SVE_BYTES="$(jq -r '.header.binding.cpu.sve_vector_length_bytes' "$index")"
  export GGML_CPU_REPACK_SIDECAR GGML_CPU_REPACK_SIDECAR_EXPERIMENT_ID \
    GGML_CPU_REPACK_SIDECAR_MODEL_SHA256 GGML_CPU_REPACK_SIDECAR_SOURCE_COMMIT \
    GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256 GGML_CPU_REPACK_SIDECAR_ARCHITECTURE \
    GGML_CPU_REPACK_SIDECAR_CPU_FEATURES_SHA256 GGML_CPU_REPACK_SIDECAR_SVE_BYTES
else
  unset GGML_CPU_REPACK_SIDECAR GGML_CPU_REPACK_SIDECAR_EXPERIMENT_ID \
    GGML_CPU_REPACK_SIDECAR_MODEL_SHA256 GGML_CPU_REPACK_SIDECAR_SOURCE_COMMIT \
    GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256 GGML_CPU_REPACK_SIDECAR_ARCHITECTURE \
    GGML_CPU_REPACK_SIDECAR_CPU_FEATURES_SHA256 GGML_CPU_REPACK_SIDECAR_SVE_BYTES || true
fi

CONTRACT_PATH="$contract_path" SERVER_PATH="$server" MODEL_PATH="$model" \
  CONFIGURATION="$configuration" REPETITION="$repetition" INDEX_PATH="$index" \
  python3 - <<'PY' > "$cell_dir/recipe.json"
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
server = str(Path(os.environ["SERVER_PATH"]).resolve())
model = str(Path(os.environ["MODEL_PATH"]).resolve())
configuration = os.environ["CONFIGURATION"]
index = json.loads(Path(os.environ["INDEX_PATH"]).read_text())
binding = index["header"]["binding"]
argv = expected_server_argv(
    server,
    model,
    candidate=contract["selected"]["candidate"],
    profile_name="e7c_final",
)
argv.extend(["--log-verbosity", str(contract["mechanism"]["proof_log_verbosity"])])
runtime_environment = {"GGML_CPU_REPACK_SIDECAR": None}
if configuration == "sidecar_loader":
    runtime_environment = {
        "GGML_CPU_REPACK_SIDECAR": "one-time generated and independently verified sidecar",
        "GGML_CPU_REPACK_SIDECAR_EXPERIMENT_ID": binding["experiment_id"],
        "GGML_CPU_REPACK_SIDECAR_MODEL_SHA256": binding["source_model_sha256"],
        "GGML_CPU_REPACK_SIDECAR_SOURCE_COMMIT": binding["llama_cpp_commit"],
        "GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256": binding["source_diff_sha256"],
        "GGML_CPU_REPACK_SIDECAR_ARCHITECTURE": binding["cpu"]["architecture"],
        "GGML_CPU_REPACK_SIDECAR_CPU_FEATURES_SHA256": binding["cpu"]["common_features_sha256"],
        "GGML_CPU_REPACK_SIDECAR_SVE_BYTES": str(binding["cpu"]["sve_vector_length_bytes"]),
    }
print(json.dumps({
    "schema_version": 1,
    "experiment_id": "E16b",
    "configuration": configuration,
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
    "runtime_environment": runtime_environment,
    "argv": argv,
}, indent=2, sort_keys=True))
PY
mapfile -t launch < <(jq -r '.argv[]' "$cell_dir/recipe.json")
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell_dir/runner-state-before.txt"
ulimit -c 0
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
  --configuration "$configuration" \
  --repetition "$repetition" \
  --warmup-task arithmetic-02 \
  --warmup-task logic-01 \
  --warmup-slot 0 \
  --warmup-slot 0 \
  --concurrency 1 \
  --max-output-tokens 8 \
  --seed 424242 \
  --timeout 30 \
  --experiment-id E16b \
  --server-pid "$active_server_pid" \
  --cache-prompt \
  --output "$cell_dir/probe.json"
cat "/proc/$active_server_pid/smaps_rollup" > "$cell_dir/smaps-rollup-after-workload.txt"
cat "/proc/$active_server_pid/maps" > "$cell_dir/process-maps-after-workload.txt"
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
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell_dir/runner-state-after.txt"
trap - EXIT
