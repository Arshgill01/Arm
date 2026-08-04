#!/usr/bin/env bash
set -euo pipefail

pair_candidate="$1"
cell_index="$2"
role="$3"
repetition="$4"

anchor="$(jq -r '.anchor' "$CONTRACT_PATH")"
candidate="$pair_candidate"
if [[ "$role" == anchor ]]; then
  candidate="$anchor"
elif [[ "$role" != candidate ]]; then
  echo "unknown E11b role: $role" >&2
  exit 1
fi

entrypoint="$(jq -r --arg candidate "$candidate" '.models[$candidate].path' "$CONTRACT_PATH")"
model="$MODEL_ROOT/$candidate/$entrypoint"
output="$EVIDENCE_DIR/pairs/$pair_candidate/${cell_index}-${role}-r${repetition}"
mkdir -p "$output"
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$output/runner-state-before.txt"

SERVER="$SERVER" MODEL="$model" CANDIDATE="$candidate" ROLE="$role" \
  OUTPUT="$output/recipe.json" python3 - <<'PY'
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
candidate = os.environ["CANDIDATE"]
model = contract["models"][candidate]
server = os.environ["SERVER"]
recipe = {
    "schema_version": 1,
    "experiment_id": "E11b",
    "candidate": candidate,
    "role": os.environ["ROLE"],
    "source": contract["runtime"]["source"],
    "build": contract["runtime"]["build"],
    "service": contract["runtime"]["service"],
    "server_path": server,
    "server_version": capture_server_version(server),
    "model": {
        "path": os.environ["MODEL"],
        "sha256": model["sha256"],
        "size_bytes": model["size_bytes"],
    },
    "argv": expected_server_argv(
        server,
        os.environ["MODEL"],
        candidate=candidate,
        profile_name=contract["runtime"]["profile_name"],
    ),
}
Path(os.environ["OUTPUT"]).write_text(
    json.dumps(recipe, indent=2, sort_keys=True) + "\n"
)
PY

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

mapfile -t server_argv < <(jq -r '.argv[]' "$output/recipe.json")
/usr/bin/time --verbose --output "$output/server-time.log" \
  "${server_argv[@]}" > "$output/server.stdout.log" \
  2> "$output/server.stderr.log" &
active_timer_pid=$!
python3 experiments/e3d_http_quality.py wait \
  --url http://127.0.0.1:18081 \
  --timeout 45 \
  --output "$output/readiness.json"
for _ in $(seq 1 50); do
  active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
  if [[ -n "$active_server_pid" ]]; then break; fi
  sleep 0.1
done
test -n "$active_server_pid"
echo "$active_server_pid" > "$output/server-pid.txt"

mapfile -t warmup_tasks < <(jq -r '.request.warmup_task_ids[]' "$CONTRACT_PATH")
probe_args=(
  --url http://127.0.0.1:18081
  --tasks "$(jq -r '.inputs.tasks_path' "$CONTRACT_PATH")"
  --reference-manifest "$(jq -r '.inputs.reference_manifest_path' "$CONTRACT_PATH")"
  --reference-candidate "$anchor"
  --candidate "$candidate"
  --role "$role"
  --repetition "$repetition"
  --concurrency "$(jq -r '.request.client_concurrency' "$CONTRACT_PATH")"
  --max-output-tokens "$(jq -r '.request.max_output_tokens' "$CONTRACT_PATH")"
  --seed "$(jq -r '.request.seed' "$CONTRACT_PATH")"
  --timeout "$(jq -r '.request.timeout_seconds' "$CONTRACT_PATH")"
  --server-pid "$active_server_pid"
  --cache-prompt
  --warmup-slot 0
  --warmup-slot 0
  --output "$output/probe.json"
)
for task in "${warmup_tasks[@]}"; do
  probe_args+=(--warmup-task "$task")
done
python3 experiments/e11b_probe.py "${probe_args[@]}"
curl --fail --silent http://127.0.0.1:18081/metrics > "$output/metrics.txt"
curl --fail --silent http://127.0.0.1:18081/slots > "$output/slots.json"
curl --fail --silent http://127.0.0.1:18081/health > "$output/health.json"
kill -INT "$active_server_pid"
set +e
wait "$active_timer_pid"
server_status=$?
set -e
echo "$server_status" > "$output/server-shell-exit.txt"
[[ "$server_status" -eq 0 || "$server_status" -eq 130 ]]
active_server_pid=""
active_timer_pid=""
trap - EXIT

{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$output/runner-state-after.txt"
