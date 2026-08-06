#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 9 ]]; then
  echo "usage: e22a_cell.sh EVIDENCE SERVER MODEL SIDECAR INDEX SIDECAR_RECEIPT MODE WORKERS POSITION" >&2
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
stop_file="$RUNNER_TEMP/e22a-stop-${position}-${mode}-w${workers}"
launcher_pid=""

cleanup() {
  if [[ -n "$launcher_pid" ]] && kill -0 "$launcher_pid" 2>/dev/null; then
    touch "$stop_file"
    wait "$launcher_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
test "$mode" = normal || test "$mode" = shared
test ! -e "$stop_file"
mkdir -p "$cell/logs"
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell/runner-state-before.txt"

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
  --readiness-timeout 180
  --upstream-timeout 60
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
for _ in $(seq 1 2400); do
  if [[ -f "$cell/ready.json" ]]; then break; fi
  kill -0 "$launcher_pid"
  sleep 0.1
done
test -f "$cell/ready.json"
test "$(jq -r '.status' "$cell/ready.json")" = pareto64_deployment_ready
test "$(jq '.workers | length' "$cell/ready.json")" = "$workers"

python3 experiments/e22a_probe.py \
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
  --timeout 60 \
  --output "$cell/probe.json"

for worker in $(seq 1 "$workers"); do
  pid="$(jq -r --argjson worker "$worker" '.workers[] | select(.worker == $worker) | .pid' "$cell/ready.json")"
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
trap - EXIT
test "$(jq -r '.status' "$cell/deployment-receipt.json")" = \
  valid_pareto64_deployment_lifecycle
{
  date --utc --iso-8601=seconds
  uptime
  cat /proc/loadavg
  free -h
} > "$cell/runner-state-after.txt"
