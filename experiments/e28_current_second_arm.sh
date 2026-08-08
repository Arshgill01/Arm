#!/usr/bin/env bash
# shellcheck disable=SC2034,SC2154 # Globals and functions come from the sourced campaign library.
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 OUTPUT_DIR" >&2
    exit 2
fi

requested_output=$1
set -- "$requested_output" prepare
# shellcheck source=e28_current_campaign.sh disable=SC1091
E28_CURRENT_LIBRARY_ONLY=1 source "$(dirname "${BASH_SOURCE[0]}")/e28_current_campaign.sh"

model_key=portability
model="$model_dir/$(jq -r '.models.portability.filename' "$contract")"

run_portability_benchmarks() {
    test -f "$marker_dir/prepare.complete"
    test ! -e "$output_dir/inference"
    mkdir -p "$output_dir/inference"
    for spec in pp512:512:0 pp2048:2048:0 pp4096:4096:0 tg128:0:128; do
        IFS=: read -r case_name prompt_tokens generated_tokens <<< "$spec"
        for round in 1 2 3; do
            run_current_bench_cell A stock "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p1"
            run_current_bench_cell D combined "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p2"
            run_current_bench_cell D combined "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p3"
            run_current_bench_cell A stock "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p4"
        done
    done
}

test ! -e "$marker_dir/second-arm.complete"
record_host
verify_inputs
prepare_current_sources_and_builds
prepare_model
E28_CURRENT_Q8_LAYOUT=1 compile_harnesses
run_correctness
touch "$marker_dir/prepare.complete"
run_portability_benchmarks
python3 "$repo_root/experiments/e28_current_second_ingest.py" "$output_dir" \
    "$output_dir/results/summary.json"
touch "$marker_dir/second-arm.complete"
finish_inventory
