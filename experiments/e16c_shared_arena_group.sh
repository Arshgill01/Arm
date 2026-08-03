#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 8 ]]; then
  echo "usage: e16c_shared_arena_group.sh CONTRACT EVIDENCE SERVER MODEL SIDECAR INDEX CONFIG REPETITION" >&2
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
timer_pids=("" "")
server_pids=("" "")

cleanup() {
  for pid in "${server_pids[@]}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -INT "$pid" 2>/dev/null || true
    fi
  done
  for pid in "${timer_pids[@]}"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT
mkdir -p "$cell_dir"
unset GGML_CPU_REPACK_DUMP_DIR || true
if [[ "$configuration" == "shared_sidecar_workers" ]]; then
  for worker in 1 2; do
    python3 experiments/e16a_sidecar.py verify \
      --sidecar "$sidecar" --index "$index" \
      > "$cell_dir/prelaunch-verification-worker-${worker}.json"
  done
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

for worker in 1 2; do
  port=$((18080 + worker))
  CONTRACT_PATH="$contract_path" SERVER_PATH="$server" MODEL_PATH="$model" \
    CONFIGURATION="$configuration" REPETITION="$repetition" \
    INDEX_PATH="$index" WORKER="$worker" PORT="$port" python3 - <<'PY' \
      > "$cell_dir/recipe-worker-${worker}.json"
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
    server, model, candidate=contract["selected"]["candidate"],
    profile_name="e7c_final",
)
argv[argv.index("--port") + 1] = os.environ["PORT"]
argv.extend(["--log-verbosity", str(contract["mechanism"]["proof_log_verbosity"])])
runtime_environment = {"GGML_CPU_REPACK_SIDECAR": None}
if configuration == "shared_sidecar_workers":
    runtime_environment = {
        "GGML_CPU_REPACK_SIDECAR": "one shared verified sidecar",
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
    "experiment_id": "E16c",
    "configuration": configuration,
    "repetition": int(os.environ["REPETITION"]),
    "worker": int(os.environ["WORKER"]),
    "port": int(os.environ["PORT"]),
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
done

{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell_dir/runner-state-before.txt"
ulimit -c 0
for worker_index in 0 1; do
  worker=$((worker_index + 1))
  mapfile -t launch < <(jq -r '.argv[]' "$cell_dir/recipe-worker-${worker}.json")
  /usr/bin/time --verbose \
    --output "$cell_dir/server-time-worker-${worker}.log" \
    "${launch[@]}" > "$cell_dir/server-worker-${worker}.stdout.log" \
    2> "$cell_dir/server-worker-${worker}.stderr.log" &
  timer_pids[worker_index]=$!
done
for worker_index in 0 1; do
  worker=$((worker_index + 1))
  port=$((18080 + worker))
  python3 experiments/e3d_http_quality.py wait \
    --url "http://127.0.0.1:$port" --timeout 120 \
    --output "$cell_dir/readiness-worker-${worker}.json"
  for _ in $(seq 1 50); do
    server_pids[worker_index]="$(pgrep -P "${timer_pids[worker_index]}" -x llama-server || true)"
    if [[ -n "${server_pids[$worker_index]}" ]]; then break; fi
    sleep 0.1
  done
  test -n "${server_pids[$worker_index]}"
  echo "${server_pids[$worker_index]}" > "$cell_dir/server-pid-worker-${worker}.txt"
done

python3 experiments/e16c_dual_probe.py \
  --url http://127.0.0.1:18081 --url http://127.0.0.1:18082 \
  --server-pid "${server_pids[0]}" --server-pid "${server_pids[1]}" \
  --tasks experiments/e3_tasks.json \
  --reference-manifest results/manifests/e3f-30656151957.json \
  --candidate ministral3_3b_q4_k_m \
  --configuration "$configuration" --repetition "$repetition" \
  --warmup-task arithmetic-02 --warmup-task logic-01 \
  --max-output-tokens 8 --seed 424242 --timeout 30 \
  --output "$cell_dir/probe.json"

for worker_index in 0 1; do
  worker=$((worker_index + 1))
  port=$((18080 + worker))
  pid="${server_pids[$worker_index]}"
  cat "/proc/$pid/smaps_rollup" > "$cell_dir/smaps-rollup-worker-${worker}.txt"
  cat "/proc/$pid/maps" > "$cell_dir/process-maps-worker-${worker}.txt"
  cat "/proc/$pid/smaps" > "$cell_dir/smaps-worker-${worker}.txt"
  curl --fail --silent "http://127.0.0.1:$port/metrics" \
    > "$cell_dir/metrics-worker-${worker}.txt"
  curl --fail --silent "http://127.0.0.1:$port/slots" \
    > "$cell_dir/slots-worker-${worker}.json"
  curl --fail --silent "http://127.0.0.1:$port/health" \
    > "$cell_dir/health-worker-${worker}.json"
done
for pid in "${server_pids[@]}"; do kill -INT "$pid"; done
for worker_index in 0 1; do
  worker=$((worker_index + 1))
  set +e
  wait "${timer_pids[$worker_index]}"
  status=$?
  set -e
  echo "$status" > "$cell_dir/server-shell-exit-worker-${worker}.txt"
  [[ "$status" -eq 0 || "$status" -eq 130 ]]
  timer_pids[worker_index]=""
  server_pids[worker_index]=""
done
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell_dir/runner-state-after.txt"
trap - EXIT
