#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "${MODEL_PATH:-}" ]]; then
    echo "usage: MODEL_PATH=/path/to/model.gguf $0 OUTPUT_DIR" >&2
    exit 2
fi

output_dir=$1
if [[ -d "$output_dir" && -n "$(find "$output_dir" -mindepth 1 -print -quit)" ]]; then
    echo "output directory is not empty: $output_dir" >&2
    exit 2
fi
if [[ "$(uname -m)" != aarch64 || $(nproc) -lt 4 ]]; then
    echo "this experiment requires an aarch64 host with at least four CPUs" >&2
    exit 2
fi
test -f "$MODEL_PATH"

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
contract="$repo_root/experiments/e26_contract.json"
work_dir=${E26_WORK_DIR:-$(mktemp -d /var/tmp/e26-tiled-ffn.XXXXXX)}
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"

mkdir -p "$output_dir"/{host,source,correctness,layer,inference,graph,live}
cp "$contract" "$output_dir/source/contract.json"
uname -a > "$output_dir/host/uname.txt"
lscpu > "$output_dir/host/lscpu.txt"
lscpu --extended > "$output_dir/host/lscpu-extended.txt"
cc --version > "$output_dir/host/cc-version.txt"
c++ --version > "$output_dir/host/cxx-version.txt"
cmake --version > "$output_dir/host/cmake-version.txt"
sha256sum "$MODEL_PATH" > "$output_dir/source/model-sha256.txt"
stat --format='%n %s bytes' "$MODEL_PATH" > "$output_dir/source/model-size.txt"

repository=$(jq -r '.source.repository' "$contract")
commit=$(jq -r '.source.commit' "$contract")
git clone --filter=blob:none "$repository" "$source_dir" \
    > "$output_dir/source/clone.stdout" 2> "$output_dir/source/clone.stderr"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"

mapfile -t baseline_patches < <(jq -r '.source.baseline_patches[]' "$contract")
candidate_patch=$(jq -r '.source.candidate_patch' "$contract")
for patch in "${baseline_patches[@]}" "$candidate_patch"; do
    git -C "$source_dir" apply --check "$repo_root/$patch"
    git -C "$source_dir" apply "$repo_root/$patch"
done
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index > "$output_dir/source/combined.patch"
sha256sum "${baseline_patches[@]/#/$repo_root/}" "$repo_root/$candidate_patch" \
    > "$output_dir/source/patch-sha256.txt"

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CPU_KLEIDIAI=ON \
    -DGGML_LTO=OFF \
    -DGGML_NATIVE=ON \
    -DLLAMA_BUILD_EXAMPLES=ON \
    -DLLAMA_BUILD_SERVER=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_CURL=OFF \
    2>&1 | tee "$output_dir/source/configure.log"
cmake --build "$build_dir" --target llama-bench llama-completion --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/build.log"

c++ -O3 -std=c++17 -march=native \
    -I"$source_dir/ggml/include" \
    -I"$source_dir/ggml/src" \
    -I"$source_dir/ggml/src/ggml-cpu" \
    "$repo_root/experiments/e26_tiled_ffn.cpp" -o "$work_dir/e26-tiled-ffn" \
    -L"$build_dir/bin" -Wl,-rpath,"$build_dir/bin" \
    -lggml-cpu -lggml-base -lggml -fopenmp

run_layer() {
    local profile=$1
    local tokens=$2
    local output=$3
    local enabled=0
    [[ "$profile" == candidate ]] && enabled=1
    GGML_CPU_TILED_FFN=$enabled taskset --cpu-list 0-3 "$work_dir/e26-tiled-ffn" \
        --n-embd 3072 --n-ff 9216 --n-tokens "$tokens" --threads 4 --repetitions 5 \
        --output "$output_dir/correctness/$output.bin" > "$output_dir/layer/$output.txt"
}

run_layer baseline 1 correctness-t1-baseline
run_layer candidate 1 correctness-t1-candidate
cmp "$output_dir/correctness/correctness-t1-baseline.bin" "$output_dir/correctness/correctness-t1-candidate.bin"
GGML_CPU_TILED_FFN=1 taskset --cpu-list 0-3 "$work_dir/e26-tiled-ffn" \
    --n-embd 3072 --n-ff 9216 --n-tokens 1 --threads 4 --repetitions 1 \
    --unsupported-names --output "$output_dir/correctness/fallback.bin" \
    > "$output_dir/correctness/fallback.txt"
cmp "$output_dir/correctness/correctness-t1-baseline.bin" "$output_dir/correctness/fallback.bin"

for tokens in 1 32; do
    for round in 1 2 3; do
        run_layer baseline "$tokens" "t${tokens}-${round}a-baseline"
        run_layer candidate "$tokens" "t${tokens}-${round}a-candidate"
        run_layer candidate "$tokens" "t${tokens}-${round}b-candidate"
        run_layer baseline "$tokens" "t${tokens}-${round}b-baseline"
    done
done

bench="$build_dir/bin/llama-bench"
run_inference() {
    local profile=$1
    local prompt_tokens=$2
    local generated_tokens=$3
    local case_name=$4
    local round=$5
    local enabled=0
    [[ "$profile" == candidate ]] && enabled=1
    GGML_CPU_TILED_FFN=$enabled taskset --cpu-list 0-3 "$bench" \
        -m "$MODEL_PATH" -p "$prompt_tokens" -n "$generated_tokens" \
        -t 4 -fa 1 -b 1024 -ub 512 --no-warmup -r 3 -o jsonl \
        > "$output_dir/inference/$case_name-$round-$profile.jsonl" \
        2> "$output_dir/inference/$case_name-$round-$profile.stderr"
}
for case_spec in pp128:128:0 pp512:512:0 tg128:0:128; do
    IFS=: read -r case_name prompt_tokens generated_tokens <<< "$case_spec"
    for round in 1 2; do
        run_inference baseline "$prompt_tokens" "$generated_tokens" "$case_name" "${round}a"
        run_inference candidate "$prompt_tokens" "$generated_tokens" "$case_name" "${round}a"
        run_inference candidate "$prompt_tokens" "$generated_tokens" "$case_name" "${round}b"
        run_inference baseline "$prompt_tokens" "$generated_tokens" "$case_name" "${round}b"
    done
done

GGML_CPU_TILED_FFN=1 GGML_CPU_TILED_FFN_DEBUG=1 taskset --cpu-list 0-3 "$bench" \
    -m "$MODEL_PATH" -p 1 -n 0 -t 4 -fa 1 --no-warmup -r 1 -o jsonl \
    > "$output_dir/graph/candidate.jsonl" 2> "$output_dir/graph/candidate.stderr"

prompt='Explain why a tiled feed-forward network can reduce memory traffic in one sentence.'
for profile in baseline candidate; do
    enabled=0
    [[ "$profile" == candidate ]] && enabled=1
    GGML_CPU_TILED_FFN=$enabled taskset --cpu-list 0-3 "$build_dir/bin/llama-completion" \
        -m "$MODEL_PATH" -p "$prompt" -n 32 --seed 42 --temp 0 \
        -t 4 -c 2048 -b 512 -ub 512 --no-warmup --no-display-prompt --no-conversation \
        > "$output_dir/live/$profile.stdout" 2> "$output_dir/live/$profile.stderr"
done
diff -u "$output_dir/live/baseline.stdout" "$output_dir/live/candidate.stdout" \
    > "$output_dir/live/output.diff"

python3 "$repo_root/experiments/e26_ingest.py" "$output_dir" "$output_dir/summary.json"
find "$output_dir" -type f ! -name file-inventory-sha256.txt -print0 \
    | sort -z | xargs -0 sha256sum > "$output_dir/file-inventory-sha256.txt"
