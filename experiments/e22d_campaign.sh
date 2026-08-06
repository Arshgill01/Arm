#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 7 ]]; then
  echo "usage: e22d_campaign.sh EVIDENCE CONTRACT SERVER MODEL SIDECAR INDEX SIDECAR_RECEIPT" >&2
  exit 2
fi
evidence="$1"
contract="$2"
server="$3"
model="$4"
sidecar="$5"
index="$6"
sidecar_receipt="$7"

test "$(jq -r '.experiment_id' "$contract")" = \
  E22d-independent-host-density-replication
test ! -e "$evidence/cells"

repeated_exit=0
if experiments/e22c_campaign.sh \
  "$evidence" "$contract" "$server" "$model" "$sidecar" "$index" \
  "$sidecar_receipt"; then
  repeated_exit=0
else
  repeated_exit=$?
fi
mv "$evidence/campaign-status.json" "$evidence/repeated-campaign-status.json"

reserve="$(jq -r '.fixed_memory.minimum_mem_available_bytes' "$contract")"
boundary_status=eligible
for position in 1 4 6 7; do
  cell="$evidence/cells/$(printf '%02d' "$position")-normal-w6"
  status="$(jq -r '.status' "$cell/cell-status.json")"
  available=0
  oom_kills=1
  if [[ "$status" = valid_fixed_memory_curve_cell ]]; then
    available="$(jq -r '.memory_after_measurement.memavailable_bytes' "$cell/probe.json")"
    oom_kills="$(jq -r '.vmstat_delta.oom_kill' "$cell/probe.json")"
  fi
  if [[ "$status" != valid_fixed_memory_curve_cell \
    || "$available" -lt "$reserve" || "$oom_kills" -ne 0 ]]; then
    boundary_status=ineligible
  fi
done

boundary_exit=0
if [[ "$boundary_status" = eligible ]]; then
  if experiments/e22b_cell.sh \
    "$evidence" "$server" "$model" "$sidecar" "$index" \
    "$sidecar_receipt" normal 8 9; then
    boundary_exit=0
  else
    boundary_exit=$?
  fi
else
  boundary="$evidence/cells/09-normal-w8"
  mkdir -p "$boundary"
  jq -n \
    '{schema_version: 1, status: "skipped_by_frozen_normal_six_stop_rule", mode: "normal", workers: 8, position: 9}' \
    > "$boundary/cell-status.json"
  boundary_exit=125
fi

if pgrep --exact llama-server >/dev/null; then
  echo "llama-server remained after E22d campaign" >&2
  exit 1
fi

jq -n \
  --argjson repeated_exit "$repeated_exit" \
  --arg boundary_status "$boundary_status" \
  --argjson boundary_exit "$boundary_exit" \
  '{
    schema_version: 1,
    status: "completed_independent_host_density_replication",
    repeated_campaign_exit_status: $repeated_exit,
    normal_eight_boundary_status: $boundary_status,
    normal_eight_exit_status: $boundary_exit
  }' > "$evidence/campaign-status.json"
jq -c . "$evidence/campaign-status.json"
