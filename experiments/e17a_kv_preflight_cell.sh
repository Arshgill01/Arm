#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "usage: e17a_kv_preflight_cell.sh INDEX CONFIGURATION" >&2
  exit 2
fi

cell_index="$1"
configuration="$2"
cell_dir="$EVIDENCE_DIR/cells/${cell_index}-${configuration}"
mkdir -p "$cell_dir"

SERVER="$SERVER" MODEL="$MODEL" CONFIGURATION="$configuration" \
  CELL_DIR="$cell_dir" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
config = contract["execution"]["configurations"][os.environ["CONFIGURATION"]]
server = os.environ["SERVER"]
argv = [
    server,
    "--model", os.environ["MODEL"],
    "--alias", contract["selected"]["candidate"],
    "--threads", "4",
    "--threads-batch", "4",
    "--ctx-size", str(config["context_size"]),
    "--cache-type-k", config["kv_cache_type_k"],
    "--cache-type-v", config["kv_cache_type_v"],
    "--flash-attn", config["flash_attention"],
    "--parallel", "1",
    "--cont-batching",
    "--host", "127.0.0.1",
    "--port", "18081",
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
    "experiment_id": "E17a",
    "configuration": os.environ["CONFIGURATION"],
    "server_path": server,
    "server_version": (version.stdout + version.stderr).strip(),
    "model": {
        "candidate": contract["selected"]["candidate"],
        "path": os.environ["MODEL"],
        "sha256": contract["selected"]["model_sha256"],
        "size_bytes": contract["selected"]["model_size_bytes"],
    },
    "service": config,
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

/usr/bin/time --verbose --output "$cell_dir/server-time.log" \
  "${server_argv[@]}" > "$cell_dir/server.stdout.log" \
  2> "$cell_dir/server.stderr.log" &
active_timer_pid=$!
python3 experiments/e3d_http_quality.py wait \
  --url http://127.0.0.1:18081 --timeout 45 \
  --output "$cell_dir/readiness.json"
for _ in $(seq 1 50); do
  active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
  if [[ -n "$active_server_pid" ]]; then break; fi
  sleep 0.1
done
test -n "$active_server_pid"
echo "$active_server_pid" > "$cell_dir/server-pid.txt"

python3 experiments/e17a_subset_probe.py \
  --url http://127.0.0.1:18081 \
  --tasks experiments/e17a_tasks.json \
  --reference-manifest results/manifests/e3f-30656151957.json \
  --candidate ministral3_3b_q4_k_m \
  --configuration "$configuration" \
  --repetition 1 \
  --warmup-task arithmetic-02 \
  --concurrency 1 \
  --max-output-tokens 8 \
  --seed 424242 \
  --timeout 30 \
  --experiment-id E17a \
  --server-pid "$active_server_pid" \
  --no-cache-prompt \
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
trap - EXIT
