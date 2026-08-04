#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: e20c_cell.sh INDEX PROFILE REPETITION" >&2
  exit 2
fi

cell_index="$1"
profile="$2"
repetition="$3"
cell_dir="$EVIDENCE_DIR/cells/${cell_index}-${profile}-r${repetition}"
mkdir -p "$cell_dir"

case "$profile" in
  reuse_off) pair_fusion=0 ;;
  reuse_on) pair_fusion=1 ;;
  *)
    echo "unknown E20c profile: $profile" >&2
    exit 2
    ;;
esac

PROFILE="$profile" PAIR_FUSION="$pair_fusion" CELL_DIR="$cell_dir" python3 - <<'PY'
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version, expected_server_argv

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
profile = os.environ["PROFILE"]
server = os.environ["SERVER"]
model = os.environ["MODEL"]
environment = {
    "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION": os.environ["PAIR_FUSION"],
    "GGML_CPU_NODE_TIMING": "0",
}
recipe = {
    "schema_version": 1,
    "experiment_id": "E20c",
    "profile_name": profile,
    "build_profile": contract["build"]["profiles"][profile],
    "runtime": contract["runtime"],
    "server_path": server,
    "server_version": capture_server_version(server),
    "model": {
        "path": model,
        "sha256": contract["selected"]["model_sha256"],
        "size_bytes": contract["selected"]["model_size_bytes"],
    },
    "service": contract["service"],
    "environment": environment,
    "argv": expected_server_argv(
        server,
        model,
        candidate=contract["selected"]["candidate"],
        service=contract["service"],
    ),
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
  env \
    "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION=$pair_fusion" \
    GGML_CPU_NODE_TIMING=0 \
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
python3 experiments/e5b_inference_probe.py \
  --url http://127.0.0.1:18081 \
  --tasks experiments/e3_tasks.json \
  --reference-manifest results/manifests/e3f-30656151957.json \
  --candidate ministral3_3b_q4_k_m \
  --configuration "$profile" \
  --repetition "$repetition" \
  --warmup-task arithmetic-02 \
  --warmup-task logic-01 \
  --warmup-slot 0 \
  --warmup-slot 0 \
  --concurrency 1 \
  --max-output-tokens 8 \
  --seed 424242 \
  --timeout 30 \
  --experiment-id E20c \
  --server-pid "$active_server_pid" \
  --cache-prompt \
  --output "$cell_dir/probe.json"
curl --fail --silent http://127.0.0.1:18081/metrics > "$cell_dir/metrics.txt"
curl --fail --silent http://127.0.0.1:18081/slots > "$cell_dir/slots.json"
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
