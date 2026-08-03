#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 5 ]]; then
  echo "usage: e10f_cell.sh PLAN ADAPTER_CONTRACT EVIDENCE_DIR SERVER MODEL" >&2
  exit 2
fi

plan_path="$1"
adapter_contract_path="$2"
evidence_dir="$3"
server="$4"
model="$5"
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

export LD_LIBRARY_PATH="$(dirname "$server")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
SERVER="$server" MODEL="$model" OUTPUT="$evidence_dir/recipe.json" \
  PLAN_PATH="$plan_path" ADAPTER_CONTRACT_PATH="$adapter_contract_path" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

plan = json.loads(Path(os.environ["PLAN_PATH"]).read_text())
adapter = json.loads(Path(os.environ["ADAPTER_CONTRACT_PATH"]).read_text())
server = os.environ["SERVER"]
model_path = os.environ["MODEL"]
model = next(
    item for item in plan["models"] if item["candidate"] == os.environ["CANDIDATE"]
)
recipe = {
    "schema_version": 1,
    "experiment_id": "E10d",
    "profile_name": "e7c_final_plus_probability_ids",
    "service": adapter["service"],
    "server_path": server,
    "server_version": capture_server_version(server).strip(),
    "model": {
        "candidate": model["candidate"],
        "path": model_path,
        "sha256": model["sha256"],
        "size_bytes": model["size_bytes"],
    },
    "argv": expected_server_argv(
        server,
        model_path,
        candidate=model["candidate"],
        profile_name="e7c_final",
    ),
}
Path(os.environ["OUTPUT"]).write_text(
    json.dumps(recipe, indent=2, sort_keys=True) + "\n"
)
PY

{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$evidence_dir/runner-state-before.txt"
mapfile -t server_argv < <(jq -r '.argv[]' "$evidence_dir/recipe.json")
/usr/bin/time --verbose --output "$evidence_dir/server-time.log" \
  "${server_argv[@]}" \
  > "$evidence_dir/server.stdout.log" \
  2> "$evidence_dir/server.stderr.log" &
active_timer_pid=$!
python3 experiments/e3d_http_quality.py wait \
  --url http://127.0.0.1:18081 \
  --timeout 45 \
  --output "$evidence_dir/readiness.json"
for _ in $(seq 1 50); do
  active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
  if [[ -n "$active_server_pid" ]]; then
    break
  fi
  sleep 0.1
done
test -n "$active_server_pid"
echo "$active_server_pid" > "$evidence_dir/server-pid.txt"
python3 experiments/e10d_preflight.py \
  --base-url http://127.0.0.1:18081 \
  --seed "$(jq -r '.scoring.probe_parameters.seed' "$plan_path")" \
  --raw-dir "$evidence_dir/preflight-raw" \
  --output "$evidence_dir/preflight.json"
python3 experiments/e10f_probe.py \
  --base-url http://127.0.0.1:18081 \
  --prepared "$evidence_dir/prepared.json" \
  --model "$CANDIDATE" \
  --model-sha256 "$(jq -r --arg candidate "$CANDIDATE" '.models[] | select(.candidate == $candidate) | .sha256' "$plan_path")" \
  --server-pid "$active_server_pid" \
  --seed "$(jq -r '.scoring.probe_parameters.seed' "$plan_path")" \
  --timeout "$(jq -r '.scoring.request_timeout_seconds' "$plan_path")" \
  --safe-token-id "$(jq -r '.safe_sampling.token_id' "$plan_path")" \
  --safe-logit-bias "$(jq -r '.safe_sampling.logit_bias' "$plan_path")" \
  --safe-token-text "$(jq -r '.safe_sampling.token_text' "$plan_path")" \
  --raw-dir "$evidence_dir/raw" \
  --output "$evidence_dir/probe.json"
curl --fail --silent http://127.0.0.1:18081/metrics > "$evidence_dir/metrics.txt"
curl --fail --silent http://127.0.0.1:18081/slots > "$evidence_dir/slots.json"
curl --fail --silent http://127.0.0.1:18081/health > "$evidence_dir/health.json"
kill -INT "$active_server_pid"
set +e
wait "$active_timer_pid"
server_status=$?
set -e
echo "$server_status" > "$evidence_dir/server-shell-exit.txt"
[[ "$server_status" -eq 0 || "$server_status" -eq 130 ]]
active_server_pid=""
active_timer_pid=""
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$evidence_dir/runner-state-after.txt"
trap - EXIT
