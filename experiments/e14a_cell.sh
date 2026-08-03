#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 7 ]]; then
  echo "usage: e14a_cell.sh CONTRACT EVIDENCE_DIR SERVER MODEL INDEX CONFIG REPETITION" >&2
  exit 2
fi

contract_path="$1"
evidence_dir="$2"
server="$3"
model="$4"
index="$5"
configuration="$6"
repetition="$7"
cell_dir="$evidence_dir/cells/$(printf '%02d' "$index")-${configuration}-r${repetition}"
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
exclusion_regex="$(jq -r --arg name "$configuration" '.execution.configurations[$name].exclusion_regex // ""' "$contract_path")"
weight_repack="$(jq -r --arg name "$configuration" '.execution.configurations[$name].weight_repack' "$contract_path")"
if [[ -n "$exclusion_regex" ]]; then
  export GGML_CPU_REPACK_EXCLUDE="$exclusion_regex"
else
  unset GGML_CPU_REPACK_EXCLUDE || true
fi
jq -n \
  --arg variable "GGML_CPU_REPACK_EXCLUDE" \
  --arg value "$exclusion_regex" \
  --argjson weight_repack "$weight_repack" \
  '{variable: $variable, value: $value, weight_repack: $weight_repack}' \
  > "$cell_dir/environment.json"

CONTRACT_PATH="$contract_path" SERVER_PATH="$server" MODEL_PATH="$model" \
  CONFIGURATION="$configuration" REPETITION="$repetition" \
  python3 - <<'PY' > "$cell_dir/recipe.json"
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
configuration = os.environ["CONFIGURATION"]
config = contract["execution"]["configurations"][configuration]
server = str(Path(os.environ["SERVER_PATH"]).resolve())
model = str(Path(os.environ["MODEL_PATH"]).resolve())
argv = expected_server_argv(
    server,
    model,
    candidate=contract["selected"]["candidate"],
    profile_name="e7c_final",
)
if not config["weight_repack"]:
    argv.append("--no-repack")
recipe = {
    "schema_version": 1,
    "experiment_id": "E14a",
    "configuration": configuration,
    "repetition": int(os.environ["REPETITION"]),
    "source": contract["source"],
    "build": contract["build"],
    "service": config,
    "server_path": server,
    "server_version": capture_server_version(server),
    "model": {
        "path": model,
        "sha256": contract["selected"]["model_sha256"],
        "size_bytes": contract["selected"]["model_size_bytes"],
    },
    "runtime_environment": {
        "GGML_CPU_REPACK_EXCLUDE": config["exclusion_regex"],
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
  --timeout 45 \
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
  --experiment-id E14a \
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
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell_dir/runner-state-after.txt"
trap - EXIT
