#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
    echo "usage: $0 STOCK_BIN_DIR COMBINED_BIN_DIR MODEL PROMPT OUTPUT_DIR" >&2
    exit 2
fi
stock_dir=$(realpath "$1")
combined_dir=$(realpath "$2")
model=$(realpath "$3")
prompt=$(realpath "$4")
output_dir=$(realpath -m "$5")
for directory in "$stock_dir" "$combined_dir"; do
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

run_variant stock "$stock_dir"
run_variant combined "$combined_dir"
diff -u "$output_dir/stock.stdout" "$output_dir/combined.stdout" \
    > "$output_dir/output.diff" || true
sha256sum "$output_dir"/*.stdout > "$output_dir/output-sha256.txt"
if [[ -s "$output_dir/output.diff" ]]; then
    echo "stock and combined output differ; inspect the retained diff and quality evidence"
else
    echo "byte-identical output"
fi
echo "timing retained in $output_dir"
