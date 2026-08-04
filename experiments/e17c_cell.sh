#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 4 ]]; then
  echo "usage: e17c_cell.sh INDEX CONFIGURATION SLOTS REPETITION" >&2
  exit 2
fi

cell_index="$1"
configuration="$2"
slots="$3"
repetition="$4"
cell_dir="$EVIDENCE_DIR/cells/${cell_index}-${configuration}-s${slots}-r${repetition}"
mkdir -p "$cell_dir"

SERVER="$SERVER" MODEL="$MODEL" CONFIGURATION="$configuration" SLOTS="$slots" \
  REPETITION="$repetition" CELL_DIR="$cell_dir" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
configuration = os.environ["CONFIGURATION"]
slots = int(os.environ["SLOTS"])
repetition = int(os.environ["REPETITION"])
config = contract["execution"]["configurations"][configuration]
server = os.environ["SERVER"]
context = slots * contract["workload"]["context_tokens_per_slot"]
argv = [
    server,
    "--model", os.environ["MODEL"],
    "--alias", contract["selected"]["candidate"],
    "--threads", "4",
    "--threads-batch", "4",
    "--ctx-size", str(context),
    "--cache-type-k", config["kv_cache_type_k"],
    "--cache-type-v", config["kv_cache_type_v"],
    "--flash-attn", "on",
    "--parallel", str(slots),
    "--cont-batching",
    "--host", "127.0.0.1",
    "--port", "18083",
    "--no-webui",
    "--metrics",
    "--slots",
    "--jinja",
    "--temp", "0.0",
    "--seed", "424242",
    "--log-colors", "off",
    "--log-verbosity", "4",
    "--batch-size", "1024",
    "--ubatch-size", "512",
]
version = subprocess.run(
    [server, "--version"], check=True, capture_output=True, text=True
)
recipe = {
    "schema_version": 1,
    "experiment_id": "E17c",
    "configuration": configuration,
    "slots": slots,
    "repetition": repetition,
    "server_path": server,
    "server_version": (version.stdout + version.stderr).strip(),
    "model": {
        "candidate": contract["selected"]["candidate"],
        "path": os.environ["MODEL"],
        "sha256": contract["selected"]["model_sha256"],
        "size_bytes": contract["selected"]["model_size_bytes"],
    },
    "service": {
        **config,
        "context_tokens_per_slot": contract["workload"]["context_tokens_per_slot"],
        "total_context_tokens": context,
        "parallel_slots": slots,
        "flash_attention": "on",
        "prompt_cache": False,
    },
    "process_address_space_limit_bytes": contract["execution"][
        "process_address_space_limit_bytes"
    ],
    "argv": argv,
}
(Path(os.environ["CELL_DIR"]) / "recipe.json").write_text(
    json.dumps(recipe, indent=2, sort_keys=True) + "\n"
)
PY

mapfile -t server_argv < <(jq -r '.argv[]' "$cell_dir/recipe.json")
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

free -b > "$cell_dir/memory-before.txt"
/usr/bin/time --verbose --output "$cell_dir/server-time.log" \
  /usr/bin/prlimit --as=16106127360 -- "${server_argv[@]}" \
  > "$cell_dir/server.stdout.log" 2> "$cell_dir/server.stderr.log" &
active_timer_pid=$!
python3 experiments/e3d_http_quality.py wait \
  --url http://127.0.0.1:18083 --timeout 120 \
  --output "$cell_dir/readiness.json"
for _ in $(seq 1 100); do
  active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
  if [[ -n "$active_server_pid" ]]; then break; fi
  sleep 0.1
done
test -n "$active_server_pid"
echo "$active_server_pid" > "$cell_dir/server-pid.txt"
cp "/proc/$active_server_pid/status" "$cell_dir/process-status-ready.txt"
cp "/proc/$active_server_pid/smaps_rollup" "$cell_dir/process-smaps-ready.txt"
cp "/proc/$active_server_pid/limits" "$cell_dir/process-limits-ready.txt"

python3 experiments/e17c_probe.py \
  --url http://127.0.0.1:18083 \
  --contract "$CONTRACT_PATH" \
  --tasks experiments/e17c_tasks.json \
  --configuration "$configuration" \
  --slots "$slots" \
  --repetition "$repetition" \
  --server-pid "$active_server_pid" \
  --output "$cell_dir/probe.json"
cp "/proc/$active_server_pid/status" "$cell_dir/process-status-after.txt"
cp "/proc/$active_server_pid/smaps_rollup" "$cell_dir/process-smaps-after.txt"
curl --fail --silent http://127.0.0.1:18083/metrics > "$cell_dir/metrics.txt"
curl --fail --silent http://127.0.0.1:18083/slots > "$cell_dir/slots.json"
free -b > "$cell_dir/memory-after.txt"
kill -INT "$active_server_pid"
set +e
wait "$active_timer_pid"
server_status=$?
set -e
echo "$server_status" > "$cell_dir/server-shell-exit.txt"
[[ "$server_status" -eq 0 || "$server_status" -eq 130 ]]
active_server_pid=""
active_timer_pid=""
trap - EXIT
