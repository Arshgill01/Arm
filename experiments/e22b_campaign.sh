#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 7 ]]; then
  echo "usage: e22b_campaign.sh EVIDENCE CONTRACT SERVER MODEL SIDECAR INDEX SIDECAR_RECEIPT" >&2
  exit 2
fi
evidence="$1"
contract="$2"
server="$3"
model="$4"
sidecar="$5"
index="$6"
sidecar_receipt="$7"
test ! -e "$evidence/cells"
mkdir -p "$evidence/cells"
failed_cells=0
skipped_cells=0

while read -r encoded; do
  cell_spec="$(printf '%s' "$encoded" | base64 --decode)"
  position="$(jq -r '.position' <<< "$cell_spec")"
  mode="$(jq -r '.mode' <<< "$cell_spec")"
  workers="$(jq -r '.workers' <<< "$cell_spec")"
  if [[ "$mode" = normal && "$workers" = 8 ]]; then
    normal_six="$evidence/cells/09-normal-w6"
    reserve="$(jq -r '.fixed_memory.minimum_mem_available_bytes' "$contract")"
    status="$(jq -r '.status' "$normal_six/cell-status.json")"
    available=0
    oom_kills=1
    if [[ "$status" = valid_fixed_memory_curve_cell ]]; then
      available="$(jq -r \
        '.memory_after_measurement.memavailable_bytes' \
        "$normal_six/probe.json")"
      oom_kills="$(jq -r '.vmstat_delta.oom_kill' "$normal_six/probe.json")"
    fi
    if [[ "$status" != valid_fixed_memory_curve_cell \
      || "$available" -lt "$reserve" || "$oom_kills" -ne 0 ]]; then
      skipped="$evidence/cells/12-normal-w8"
      mkdir -p "$skipped"
      jq -n \
        --arg normal_six_status "$status" \
        --argjson normal_six_mem_available_bytes "$available" \
        --argjson minimum_mem_available_bytes "$reserve" \
        --argjson normal_six_oom_kills "$oom_kills" \
        '{
          schema_version: 1,
          status: "skipped_by_frozen_normal_six_stop_rule",
          mode: "normal",
          workers: 8,
          position: 12,
          normal_six_status: $normal_six_status,
          normal_six_mem_available_bytes: $normal_six_mem_available_bytes,
          minimum_mem_available_bytes: $minimum_mem_available_bytes,
          normal_six_oom_kills: $normal_six_oom_kills
        }' > "$skipped/cell-status.json"
      skipped_cells=$((skipped_cells + 1))
      continue
    fi
  fi
  if ! experiments/e22b_cell.sh \
    "$evidence" "$server" "$model" "$sidecar" "$index" \
    "$sidecar_receipt" "$mode" "$workers" "$position"; then
    failed_cells=$((failed_cells + 1))
  fi
  if pgrep --exact llama-server >/dev/null; then
    echo "llama-server remained after E22b cell $position" >&2
    exit 1
  fi
  sleep 2
done < <(jq -r '.matrix.order[] | @base64' "$contract")

jq -n \
  --argjson failed_cells "$failed_cells" \
  --argjson skipped_cells "$skipped_cells" \
  '{
    schema_version: 1,
    status: "completed_fixed_memory_curve_campaign",
    failed_cells: $failed_cells,
    skipped_cells: $skipped_cells
  }' > "$evidence/campaign-status.json"
jq -c . "$evidence/campaign-status.json"
