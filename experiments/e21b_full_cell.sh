#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 7 ]]; then
  echo "usage: e21b_full_cell.sh CONTRACT EVIDENCE_DIR SERVER MODEL INDEX POLICY REPETITION" >&2
  exit 2
fi

contract_path="$1"
evidence_dir="$2"
server="$3"
model="$4"
index="$5"
policy="$6"
repetition="$7"
cell_dir="$evidence_dir/cells/$(printf '%02d' "$index")-${policy}-r${repetition}"
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
export LD_LIBRARY_PATH="$(dirname "$server")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
SERVER="$server" MODEL="$model" OUTPUT="$cell_dir/recipe.json" \
  CONTRACT_PATH="$contract_path" POLICY="$policy" REPETITION="$repetition" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
server = os.environ["SERVER"]
model = os.environ["MODEL"]
selected = contract["selected"]
recipe = {
    "schema_version": 1,
    "experiment_id": "E21b",
    "policy": os.environ["POLICY"],
    "repetition": int(os.environ["REPETITION"]),
    "profile_name": "e7c_final",
    "service": contract["service"],
    "client": contract["client"],
    "server_path": server,
    "server_version": capture_server_version(server).strip(),
    "model": {
        "candidate": selected["candidate"],
        "path": model,
        "sha256": selected["model_sha256"],
        "size_bytes": selected["model_size_bytes"],
    },
    "argv": expected_server_argv(
        server,
        model,
        candidate=selected["candidate"],
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
} > "$cell_dir/runner-state-before.txt"
mapfile -t server_argv < <(jq -r '.argv[]' "$cell_dir/recipe.json")
/usr/bin/time --verbose --output "$cell_dir/server-time.log" \
  "${server_argv[@]}" > "$cell_dir/server.stdout.log" 2> "$cell_dir/server.stderr.log" &
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
python3 experiments/e21b_full_probe.py \
  --url http://127.0.0.1:18081 \
  --contract "$contract_path" \
  --tasks experiments/e3_tasks.json \
  --policy "$policy" \
  --repetition "$repetition" \
  --server-pid "$active_server_pid" \
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
