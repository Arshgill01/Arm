#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 6 ]]; then
  echo "usage: e10e_cell.sh PLAN E10D_CONTRACT CASES EVIDENCE_DIR SERVER MODEL" >&2
  exit 2
fi

plan_path="$1"
e10d_contract_path="$2"
cases_path="$3"
evidence_dir="$4"
server="$5"
model="$6"

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

mapfile -t case_args < <(
  jq -r '.cases[] | "--case\n\(.task):\(.sample_ordinal):\(.choice_index)"' "$plan_path"
)

run_variant() {
  local variant="$1"
  local output_dir="$evidence_dir/variants/$variant"
  local forced_token
  local forced_bias
  mkdir -p "$output_dir/raw"
  {
    date --utc --iso-8601=seconds
    uptime
    cat /proc/loadavg
    free -h
  } > "$output_dir/runner-state-before.txt"

  SERVER="$server" MODEL="$model" OUTPUT="$output_dir/recipe.json" \
    PLAN_PATH="$plan_path" E10D_CONTRACT_PATH="$e10d_contract_path" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

plan = json.loads(Path(os.environ["PLAN_PATH"]).read_text())
contract = json.loads(Path(os.environ["E10D_CONTRACT_PATH"]).read_text())
server = os.environ["SERVER"]
model_path = os.environ["MODEL"]
model = plan["model"]
recipe = {
    "schema_version": 1,
    "experiment_id": "E10d",
    "profile_name": "e7c_final_plus_probability_ids",
    "service": contract["service"],
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

  mapfile -t server_argv < <(jq -r '.argv[]' "$output_dir/recipe.json")
  /usr/bin/time --verbose --output "$output_dir/server-time.log" \
    "${server_argv[@]}" \
    > "$output_dir/server.stdout.log" \
    2> "$output_dir/server.stderr.log" &
  active_timer_pid=$!
  python3 experiments/e3d_http_quality.py wait \
    --url http://127.0.0.1:18081 \
    --timeout 45 \
    --output "$output_dir/readiness.json"
  active_server_pid=""
  for _ in $(seq 1 50); do
    active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
    if [[ -n "$active_server_pid" ]]; then
      break
    fi
    sleep 0.1
  done
  test -n "$active_server_pid"
  echo "$active_server_pid" > "$output_dir/server-pid.txt"

  probe_args=(
    --base-url http://127.0.0.1:18081
    --prepared "$cases_path"
    "${case_args[@]}"
    --variant "$variant"
    --seed "$(jq -r '.probe_parameters.seed' "$plan_path")"
    --timeout "$(jq -r '.probe_parameters.timeout' "$plan_path")"
    --server-pid "$active_server_pid"
    --model "$(jq -r '.model.candidate' "$plan_path")"
    --model-sha256 "$(jq -r '.model.sha256' "$plan_path")"
    --raw-dir "$output_dir/raw"
    --output "$output_dir/probe.json"
  )
  forced_token="$(jq -r --arg variant "$variant" '.variants[$variant].forced_safe_token_id // ""' "$plan_path")"
  forced_bias="$(jq -r --arg variant "$variant" '.variants[$variant].forced_safe_logit_bias // ""' "$plan_path")"
  if [[ -n "$forced_token" ]]; then
    probe_args+=(
      --forced-safe-token-id "$forced_token"
      --forced-safe-logit-bias "$forced_bias"
    )
  fi
  python3 experiments/e10e_probability_preflight.py "${probe_args[@]}"
  curl --fail --silent http://127.0.0.1:18081/metrics > "$output_dir/metrics.txt"
  curl --fail --silent http://127.0.0.1:18081/slots > "$output_dir/slots.json"
  curl --fail --silent http://127.0.0.1:18081/health > "$output_dir/health.json"

  kill -INT "$active_server_pid"
  set +e
  wait "$active_timer_pid"
  local server_status=$?
  set -e
  echo "$server_status" > "$output_dir/server-shell-exit.txt"
  [[ "$server_status" -eq 0 || "$server_status" -eq 130 ]]
  active_server_pid=""
  active_timer_pid=""
  {
    date --utc --iso-8601=seconds
    uptime
    cat /proc/loadavg
    free -h
  } > "$output_dir/runner-state-after.txt"
}

while IFS= read -r variant; do
  run_variant "$variant"
done < <(jq -r '.variant_order[]' "$plan_path")

trap - EXIT
