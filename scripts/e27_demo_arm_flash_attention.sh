#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
    echo "usage: $0 BASELINE_BIN_DIR CANDIDATE_BIN_DIR MODEL PROMPT OUTPUT_DIR" >&2
    exit 2
fi
baseline_dir=$(realpath "$1")
candidate_dir=$(realpath "$2")
model=$(realpath "$3")
prompt=$(realpath "$4")
output_dir=$(realpath -m "$5")
for directory in "$baseline_dir" "$candidate_dir"; do
    test -x "$directory/llama-completion"
done
test -f "$model"
test -f "$prompt"
if [[ -e "$output_dir" ]]; then
    echo "output path already exists: $output_dir" >&2
    exit 2
fi
mkdir -p "$output_dir"

run_variant() {
    local variant=$1 directory=$2
    local -a command=(
        env LD_LIBRARY_PATH="$directory"
        taskset -c 0-3 "$directory/llama-completion"
        -m "$model" -f "$prompt" -n 1 --seed 42 --temp 0
        -t 4 -c 8192 -b 1024 -ub 512 --no-warmup
        --no-display-prompt --no-conversation
    )
    printf '%q ' "${command[@]}" > "$output_dir/$variant.command.txt"
    printf '\n' >> "$output_dir/$variant.command.txt"
    /usr/bin/time --verbose --output "$output_dir/$variant.time.txt" \
        "${command[@]}" > "$output_dir/$variant.stdout" \
        2> "$output_dir/$variant.stderr"
}

run_variant baseline "$baseline_dir"
run_variant candidate "$candidate_dir"
diff -u "$output_dir/baseline.stdout" "$output_dir/candidate.stdout" \
    > "$output_dir/output.diff" || true
sha256sum "$output_dir"/*.stdout > "$output_dir/output-sha256.txt"
if [[ -s "$output_dir/output.diff" ]]; then
    echo "baseline and candidate output differ" >&2
    exit 1
fi
echo "byte-identical output; timing retained in $output_dir"
