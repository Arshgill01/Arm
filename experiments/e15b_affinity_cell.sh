#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 6 ]]; then
  echo "usage: e15b_affinity_cell.sh INDEX CONFIG REPETITION DECODE_THREADS BATCH_THREADS CPU_LIST" >&2
  exit 2
fi
index="$1"
configuration="$2"
repetition="$3"
threads_decode="$4"
threads_batch="$5"
affinity_cpu_list="$6"
cell_dir="$EVIDENCE_DIR/cells/${index}-${configuration}-r${repetition}"
mkdir -p "$cell_dir"

SERVER="$SERVER" MODEL="$MODEL" CONFIGURATION="$configuration" \
  REPETITION="$repetition" THREADS_DECODE="$threads_decode" \
  THREADS_BATCH="$threads_batch" AFFINITY_CPU_LIST="$affinity_cpu_list" \
  CELL_DIR="$cell_dir" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

contract = json.loads(Path(os.environ["CONTRACT_PATH"]).read_text())
config = contract["execution"]["configurations"][os.environ["CONFIGURATION"]]
server = os.environ["SERVER"]
model = os.environ["MODEL"]
affinity_ids = [int(value) for value in os.environ["AFFINITY_CPU_LIST"].split(",")]
argv = [
    server,
    "--model", model,
    "--alias", contract["selected"]["candidate"],
    "--threads", os.environ["THREADS_DECODE"],
    "--threads-batch", os.environ["THREADS_BATCH"],
    "--ctx-size", str(config["context_per_slot"]),
    "--cache-type-k", config["kv_cache_type_k"],
    "--cache-type-v", config["kv_cache_type_v"],
    "--flash-attn", config["flash_attention"],
    "--parallel", str(config["server_parallel_slots"]),
    "--cont-batching",
    "--cache-prompt",
    "--host", "127.0.0.1",
    "--port", "18081",
    "--no-webui",
    "--metrics",
    "--slots",
    "--jinja",
    "--temp", "0.0",
    "--seed", "424242",
    "--log-colors", "off",
    "--batch-size", str(config["batch_size"]),
    "--ubatch-size", str(config["micro_batch_size"]),
]
version = subprocess.run(
    [server, "--version"], check=True, capture_output=True, text=True
)
recipe = {
    "schema_version": 1,
    "experiment_id": "E15b",
    "configuration": os.environ["CONFIGURATION"],
    "repetition": int(os.environ["REPETITION"]),
    "affinity_cpu_list": os.environ["AFFINITY_CPU_LIST"],
    "affinity_cpu_ids": affinity_ids,
    "server_path": server,
    "server_version": (version.stdout + version.stderr).strip(),
    "model": {
        "candidate": contract["selected"]["candidate"],
        "path": model,
        "sha256": contract["selected"]["model_sha256"],
        "size_bytes": contract["selected"]["model_size_bytes"],
    },
    "service": config,
    "argv": argv,
    "server_launch_prefix": ["taskset", "--cpu-list", os.environ["AFFINITY_CPU_LIST"]],
    "client_launch_prefix": ["taskset", "--cpu-list", os.environ["AFFINITY_CPU_LIST"]],
}
(Path(os.environ["CELL_DIR"]) / "recipe.json").write_text(
    json.dumps(recipe, indent=2, sort_keys=True) + "\n"
)
PY

capture_affinity() {
  local pid="$1"
  local output="$2"
  TARGET_PID="$pid" python3 - <<'PY' > "$output"
import json
import os
from pathlib import Path

pid = int(os.environ["TARGET_PID"])
status = (Path("/proc") / str(pid) / "status").read_text()
allowed = next(
    line.split(":", 1)[1].strip()
    for line in status.splitlines()
    if line.startswith("Cpus_allowed_list:")
)
thread_affinities = []
for task in sorted((Path("/proc") / str(pid) / "task").iterdir(), key=lambda item: int(item.name)):
    task_status = (task / "status").read_text()
    task_allowed = next(
        line.split(":", 1)[1].strip()
        for line in task_status.splitlines()
        if line.startswith("Cpus_allowed_list:")
    )
    thread_affinities.append({
        "tid": int(task.name),
        "os_sched_getaffinity": sorted(os.sched_getaffinity(int(task.name))),
        "proc_status_cpus_allowed_list": task_allowed,
    })
print(json.dumps({
    "pid": pid,
    "os_sched_getaffinity": sorted(os.sched_getaffinity(pid)),
    "proc_status_cpus_allowed_list": allowed,
    "thread_affinities": thread_affinities,
}, indent=2, sort_keys=True))
PY
}

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
  taskset --cpu-list "$affinity_cpu_list" "${server_argv[@]}" \
  > "$cell_dir/server.stdout.log" 2> "$cell_dir/server.stderr.log" &
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
capture_affinity "$active_server_pid" "$cell_dir/server-affinity-before.json"
AFFINITY_CPU_LIST="$affinity_cpu_list" taskset --cpu-list "$affinity_cpu_list" \
  python3 - <<'PY' > "$cell_dir/client-affinity.json"
import json
import os

print(json.dumps({
    "pid": os.getpid(),
    "expected_cpu_list": os.environ["AFFINITY_CPU_LIST"],
    "os_sched_getaffinity": sorted(os.sched_getaffinity(0)),
}, indent=2, sort_keys=True))
PY
/usr/bin/time --verbose --output "$cell_dir/client-time.log" \
  taskset --cpu-list "$affinity_cpu_list" \
  python3 experiments/e5b_inference_probe.py \
    --url http://127.0.0.1:18081 \
    --tasks experiments/e3_tasks.json \
    --reference-manifest results/manifests/e3f-30656151957.json \
    --candidate ministral3_3b_q4_k_m \
    --configuration "$configuration" \
    --repetition "$repetition" \
    --warmup-task arithmetic-02 --warmup-task logic-01 \
    --warmup-slot 0 --warmup-slot 0 \
    --concurrency 1 --max-output-tokens 8 --seed 424242 --timeout 30 \
    --experiment-id E15b --server-pid "$active_server_pid" \
    --cache-prompt --output "$cell_dir/probe.json"
capture_affinity "$active_server_pid" "$cell_dir/server-affinity-after.json"
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
