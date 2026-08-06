#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 7 ]]; then
  echo "usage: e22c_campaign.sh EVIDENCE CONTRACT SERVER MODEL SIDECAR INDEX SIDECAR_RECEIPT" >&2
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

while read -r encoded; do
  cell_spec="$(printf '%s' "$encoded" | base64 --decode)"
  position="$(jq -r '.position' <<< "$cell_spec")"
  mode="$(jq -r '.mode' <<< "$cell_spec")"
  workers="$(jq -r '.workers' <<< "$cell_spec")"
  if ! experiments/e22b_cell.sh \
    "$evidence" "$server" "$model" "$sidecar" "$index" \
    "$sidecar_receipt" "$mode" "$workers" "$position"; then
    failed_cells=$((failed_cells + 1))
  fi
  if pgrep --exact llama-server >/dev/null; then
    echo "llama-server remained after E22c cell $position" >&2
    exit 1
  fi
  sleep "$(jq -r '.matrix.inter_cell_idle_seconds' "$contract")"
done < <(jq -r '.matrix.order[] | @base64' "$contract")

jq -n \
  --argjson failed_cells "$failed_cells" \
  '{
    schema_version: 1,
    status: "completed_clean_maximum_density_campaign",
    failed_cells: $failed_cells
  }' > "$evidence/campaign-status.json"
jq -c . "$evidence/campaign-status.json"
