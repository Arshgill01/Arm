#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "usage: $0 BASELINE_BIN_DIR CANDIDATE_BIN_DIR MODEL OUTPUT_DIR" >&2
    exit 2
fi

baseline_bin=$1
candidate_bin=$2
model=$3
output_dir=$4
prompt='Explain why balanced measurement order matters in performance experiments. Answer in three concise sentences.'

for path in "$baseline_bin/llama-completion" "$candidate_bin/llama-completion" "$model"; do
    if [[ ! -e "$path" ]]; then
        echo "required input not found: $path" >&2
        exit 2
    fi
done
if [[ -d "$output_dir" && -n "$(find "$output_dir" -mindepth 1 -print -quit)" ]]; then
    echo "output directory is not empty: $output_dir" >&2
    exit 2
fi
mkdir -p "$output_dir"

run_variant() {
    local variant=$1
    local bin_dir=$2
    printf '\n===== %s stream (%s) =====\n' "$variant" "$(date -u +%FT%TZ)"
    /usr/bin/time --format='elapsed_seconds=%e' \
        --output="$output_dir/$variant.wall-time.txt" \
        stdbuf --output=0 taskset --cpu-list 0-3 "$bin_dir/llama-completion" \
        -m "$model" -p "$prompt" -n 128 --seed 42 --temp 0 \
        -t 4 -c 2048 -b 512 -ub 512 --no-warmup --no-display-prompt \
        --no-conversation --ignore-eos \
        2> "$output_dir/$variant.stderr" \
        | tee "$output_dir/$variant.stdout"
    printf '\n===== %s complete (%s) =====\n' "$variant" "$(date -u +%FT%TZ)"
}

run_variant baseline "$baseline_bin"
run_variant candidate "$candidate_bin"
diff -u "$output_dir/baseline.stdout" "$output_dir/candidate.stdout" \
    > "$output_dir/output.diff"
sha256sum "$output_dir/baseline.stdout" "$output_dir/candidate.stdout" \
    | tee "$output_dir/output-sha256.txt"
grep -E 'prompt eval time|eval time' "$output_dir/baseline.stderr" \
    > "$output_dir/baseline-timings.txt"
grep -E 'prompt eval time|eval time' "$output_dir/candidate.stderr" \
    > "$output_dir/candidate-timings.txt"
cat "$output_dir"/*-timings.txt "$output_dir"/*.wall-time.txt
