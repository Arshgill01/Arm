#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 9 ]]; then
  echo "usage: e22b_cell.sh EVIDENCE SERVER MODEL SIDECAR INDEX SIDECAR_RECEIPT MODE WORKERS POSITION" >&2
  exit 2
fi
evidence="$1"
server="$2"
model="$3"
sidecar="$4"
index="$5"
sidecar_receipt="$6"
mode="$7"
workers="$8"
position="$9"
cell="$evidence/cells/$(printf '%02d' "$position")-${mode}-w${workers}"
temp_root="${PARETO64_E22B_TEMP_ROOT:-/var/tmp/pareto64-e22/tmp}"
stop_file="$temp_root/e22b-stop-${position}-${mode}-w${workers}"
launcher_pid=""
started_at="$(date --utc --iso-8601=seconds)"

capture_state() {
  local destination="$1"
  {
    date --utc --iso-8601=seconds
    uptime
    cat /proc/loadavg
    cat /proc/meminfo
    cat /proc/pressure/cpu
    cat /proc/pressure/memory
    cat /proc/pressure/io
    cat /proc/stat
    cat /proc/vmstat
  } > "$destination"
}

cleanup() {
  if [[ -n "$launcher_pid" ]] && kill -0 "$launcher_pid" 2>/dev/null; then
    touch "$stop_file"
    wait "$launcher_pid" 2>/dev/null || true
  fi
  rm -f -- "$stop_file"
}

finalize() {
  local exit_status="$?"
  trap - EXIT
  set +e
  cleanup
  capture_state "$cell/host-state-after.txt"
  if [[ ! -f "$cell/cell-status.json" ]]; then
    local deployment_status="missing"
    if [[ -f "$cell/deployment-receipt.json" ]]; then
      deployment_status="$(jq -r '.status // "missing"' \
        "$cell/deployment-receipt.json")"
    fi
    sudo journalctl --kernel --since "$started_at" --no-pager 2>&1 \
      | tee "$cell/kernel-since-start.txt" >/dev/null || true
    jq -n \
      --arg mode "$mode" \
      --argjson workers "$workers" \
      --argjson position "$position" \
      --argjson exit_status "$exit_status" \
      --arg deployment_status "$deployment_status" \
      '{
        schema_version: 1,
        status: "failed_fixed_memory_admission_cell",
        mode: $mode,
        workers: $workers,
        position: $position,
        exit_status: $exit_status,
        deployment_status: $deployment_status
      }' > "$cell/cell-status.json"
  fi
  exit "$exit_status"
}

test "$mode" = normal || test "$mode" = shared
test ! -e "$cell"
test ! -e "$stop_file"
mkdir -p "$cell/logs" "$temp_root"
capture_state "$cell/host-state-before.txt"
trap finalize EXIT

command=(
  python3 -m pareto64 deploy
  --mode "$mode"
  --contract experiments/e16c_contract.json
  --evidence results/manifests/e16c-30851609576.json
  --model "$model"
  --llama-server "$server"
  --workers "$workers"
  --threads 1
  --worker-base-port 18081
  --gateway-port 18080
  --registry "$cell/certificates.json"
  --minimum-cached-tokens 8
  --revalidate-every 16
  --plan-output "$cell/deployment-plan.json"
  --deployment-receipt "$cell/deployment-receipt.json"
  --ready-output "$cell/ready.json"
  --log-dir "$cell/logs"
  --stop-file "$stop_file"
  --readiness-timeout 300
  --upstream-timeout 90
)
if [[ "$mode" = shared ]]; then
  command+=(
    --sidecar "$sidecar"
    --index "$index"
    --sidecar-receipt "$sidecar_receipt"
  )
fi
printf '%q ' "${command[@]}" > "$cell/command.txt"
printf '\n' >> "$cell/command.txt"
"${command[@]}" > "$cell/deploy.stdout.log" 2> "$cell/deploy.stderr.log" &
launcher_pid=$!
for _ in $(seq 1 3600); do
  if [[ -f "$cell/ready.json" ]]; then
    break
  fi
  kill -0 "$launcher_pid"
  sleep 0.1
done
test -f "$cell/ready.json"
test "$(jq -r '.status' "$cell/ready.json")" = pareto64_deployment_ready
test "$(jq '.workers | length' "$cell/ready.json")" = "$workers"

python3 experiments/e22b_probe.py \
  --ready "$cell/ready.json" \
  --tasks experiments/e3_tasks.json \
  --reference-manifest results/manifests/e3f-30656151957.json \
  --candidate ministral3_3b_q4_k_m \
  --mode "$mode" \
  --workers "$workers" \
  --warmup-task arithmetic-02 \
  --warmup-task logic-01 \
  --max-output-tokens 8 \
  --seed 424242 \
  --timeout 90 \
  --perf-output "$cell/perf-stat.csv" \
  --output "$cell/probe.json"

for worker in $(seq 1 "$workers"); do
  pid="$(jq -r --argjson worker "$worker" \
    '.workers[] | select(.worker == $worker) | .pid' "$cell/ready.json")"
  port=$((18080 + worker))
  cat "/proc/$pid/maps" > "$cell/process-maps-worker-${worker}.txt"
  cat "/proc/$pid/smaps_rollup" > "$cell/smaps-rollup-worker-${worker}.txt"
  cat "/proc/$pid/stat" > "$cell/stat-worker-${worker}.txt"
  curl --fail --silent "http://127.0.0.1:$port/health" \
    > "$cell/health-worker-${worker}.json"
  curl --fail --silent "http://127.0.0.1:$port/metrics" \
    > "$cell/metrics-worker-${worker}.txt"
done
curl --fail --silent http://127.0.0.1:18080/healthz \
  > "$cell/gateway-health.json"
curl --fail --silent http://127.0.0.1:18080/metrics \
  > "$cell/gateway-metrics.json"
touch "$stop_file"
wait "$launcher_pid"
launcher_pid=""
test "$(jq -r '.status' "$cell/deployment-receipt.json")" = \
  valid_pareto64_deployment_lifecycle
jq -n \
  --arg mode "$mode" \
  --argjson workers "$workers" \
  --argjson position "$position" \
  '{
    schema_version: 1,
    status: "valid_fixed_memory_curve_cell",
    mode: $mode,
    workers: $workers,
    position: $position,
    exit_status: 0
  }' > "$cell/cell-status.json"
