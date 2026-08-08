#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
    echo "usage: $0 BUILD_BIN MODEL BASELINE_LIB_DIR CANDIDATE_LIB_DIR OUTPUT_DIR" >&2
    exit 2
fi

build_bin=$1
model=$2
baseline_lib=$3
candidate_lib=$4
output_dir=$5
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
prompt_file="$repo_root/experiments/e23_demo_prompt.txt"

for path in "$build_bin/llama-completion" "$model" "$prompt_file" \
    "$baseline_lib/libggml-cpu.so" "$candidate_lib/libggml-cpu.so"; do
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
    local library_dir=$2
    LD_LIBRARY_PATH="$library_dir:$build_bin" \
        /usr/bin/time --format='elapsed_seconds=%e' \
        --output="$output_dir/$variant.time" \
        taskset --cpu-list 0-3 "$build_bin/llama-completion" \
        -m "$model" -f "$prompt_file" -n 16 --seed 42 --temp 0 \
        -t 4 -c 2048 -b 512 -ub 512 --no-warmup --no-display-prompt \
        --no-conversation \
        > "$output_dir/$variant.stdout" 2> "$output_dir/$variant.stderr"
}

run_variant baseline "$baseline_lib"
run_variant candidate "$candidate_lib"
diff -u "$output_dir/baseline.stdout" "$output_dir/candidate.stdout" \
    > "$output_dir/output.diff"
sha256sum "$output_dir/baseline.stdout" "$output_dir/candidate.stdout" \
    | tee "$output_dir/output-sha256.txt"
grep -E 'prompt eval time|eval time' "$output_dir/baseline.stderr" \
    | tee "$output_dir/baseline-timings.txt"
grep -E 'prompt eval time|eval time' "$output_dir/candidate.stderr" \
    | tee "$output_dir/candidate-timings.txt"
cat "$output_dir/baseline.time" "$output_dir/candidate.time"
