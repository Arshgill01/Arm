#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 OUTPUT_DIR" >&2
    exit 2
fi
if [[ "$(uname -m)" != "aarch64" || "$(nproc)" -lt 4 ]]; then
    echo "E27 second-machine evidence requires at least four aarch64 CPUs" >&2
    exit 2
fi
for command in cmake c++ curl git jq ninja python3 sha256sum taskset; do
    command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 2; }
done
: "${MODEL_PATH:?MODEL_PATH must name the verified adjacent model}"

output_dir=$(realpath -m "$1")
if [[ -e "$output_dir" ]]; then
    echo "output path already exists: $output_dir" >&2
    exit 2
fi
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
contract="$repo_root/experiments/e27_contract.json"
candidate_patch="$repo_root/patches/llama.cpp/e27/0001-arm-sve-flash-attention-neon-gemm.patch"
harness_source="$repo_root/experiments/e27_flash_attn_harness.cpp"
work_dir=${E27_SECOND_WORK_DIR:-$(mktemp -d /tmp/e27-second-arm.XXXXXX)}
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"
variant_dir="$work_dir/variants"

mkdir -p "$output_dir"/{host,source,correctness,direct,inference,results} \
    "$variant_dir"/{baseline,candidate}
cp "$contract" "$output_dir/contract.json"
date --utc --iso-8601=seconds > "$output_dir/captured-at.txt"
uname -a > "$output_dir/host/uname.txt"
lscpu > "$output_dir/host/lscpu.txt"
lscpu --extended > "$output_dir/host/lscpu-extended.txt"
cat /proc/cpuinfo > "$output_dir/host/cpuinfo.txt"
c++ --version > "$output_dir/host/cxx-version.txt"
cmake --version > "$output_dir/host/cmake-version.txt"

model_size=$(jq -r '.adjacent_model.size_bytes' "$contract")
model_sha=$(jq -r '.adjacent_model.sha256' "$contract")
test "$(stat --format='%s' "$MODEL_PATH")" = "$model_size"
echo "$model_sha  $MODEL_PATH" | sha256sum --check --strict
sha256sum "$MODEL_PATH" > "$output_dir/source/model-sha256.txt"

repository=$(jq -r '.source.repository' "$contract")
commit=$(jq -r '.source.baseline_commit' "$contract")
git clone --filter=blob:none "$repository" "$source_dir"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
mapfile -t baseline_patches < <(jq -r '.source.cumulative_baseline_patches[]' "$contract")
sha256sum "$candidate_patch" "$harness_source" \
    "${baseline_patches[@]/#/$repo_root/}" > "$output_dir/source/input-sha256.txt"
for relative_patch in "${baseline_patches[@]}"; do
    git -C "$source_dir" apply --check "$repo_root/$relative_patch"
    git -C "$source_dir" apply "$repo_root/$relative_patch"
done
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index > "$output_dir/source/cumulative-baseline.patch"

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CPU_KLEIDIAI=ON -DGGML_LTO=OFF -DGGML_NATIVE=ON \
    -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_SERVER=OFF \
    -DLLAMA_BUILD_TESTS=OFF -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
    2>&1 | tee "$output_dir/source/configure.log"
cmake --build "$build_dir" --target llama-bench --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/baseline-build.log"
cp -a "$build_dir/bin/." "$variant_dir/baseline/"

git -C "$source_dir" apply --check "$candidate_patch"
git -C "$source_dir" apply "$candidate_patch"
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index > "$output_dir/source/cumulative-candidate.patch"
cmake --build "$build_dir" --target ggml-cpu --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/candidate-build.log"
cp -a "$build_dir/bin/." "$variant_dir/candidate/"

c++ -O3 -std=c++17 -march=native \
    -I"$source_dir/ggml/include" "$harness_source" \
    -L"$build_dir/bin" '-Wl,-rpath,$ORIGIN' \
    -lggml-cpu -lggml-base -fopenmp -o "$work_dir/e27-flash-harness"
cp "$work_dir/e27-flash-harness" "$variant_dir/baseline/"
cp "$work_dir/e27-flash-harness" "$variant_dir/candidate/"

for seed in 1 17 42; do
    taskset -c 0-3 "$variant_dir/candidate/e27-flash-harness" \
        --mode compare --head-size 128 --query-tokens 64 --kv-tokens 512 \
        --query-heads 12 --kv-heads 2 --threads 4 --repetitions 1 \
        --seed "$seed" --kv-type f16 \
        >> "$output_dir/correctness/d128-q64-kv512.jsonl" \
        2>> "$output_dir/correctness/harness.stderr"
done
jq -e -s 'length == 3 and all(.[]; .pass == true and .nmse <= .tolerance_nmse)' \
    "$output_dir/correctness/d128-q64-kv512.jsonl" >/dev/null

run_direct() {
    local variant=$1 tag=$2 kv_tokens=$3 run=$4
    LD_LIBRARY_PATH="$variant_dir/$variant" taskset -c 0-3 \
        "$variant_dir/$variant/e27-flash-harness" \
        --mode tiled --head-size 128 --query-tokens 512 --kv-tokens "$kv_tokens" \
        --query-heads 12 --kv-heads 2 --threads 4 --repetitions 5 \
        --seed 42 --kv-type f16 > "$output_dir/direct/$tag-$run-$variant.json" \
        2> "$output_dir/direct/$tag-$run-$variant.stderr"
}
for case_spec in d128-q512-kv512:512 d128-q512-kv2048:2048; do
    IFS=: read -r tag kv_tokens <<< "$case_spec"
    for round in 1 2 3; do
        run_direct baseline "$tag" "$kv_tokens" "$round-a"
        run_direct candidate "$tag" "$kv_tokens" "$round-a"
        run_direct candidate "$tag" "$kv_tokens" "$round-b"
        run_direct baseline "$tag" "$kv_tokens" "$round-b"
    done
done

common_bench=(
    --model "$MODEL_PATH" --threads 4 --n-gpu-layers 0 --flash-attn on
    --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl
)
run_inference() {
    local variant=$1 tag=$2 prompt=$3 generation=$4 run=$5
    LD_LIBRARY_PATH="$variant_dir/$variant" taskset -c 0-3 \
        "$variant_dir/$variant/llama-bench" "${common_bench[@]}" \
        --repetitions 1 --n-prompt "$prompt" --n-gen "$generation" \
        > "$output_dir/inference/$tag-$run-$variant.jsonl" \
        2> "$output_dir/inference/$tag-$run-$variant.stderr"
}
for case_spec in pp512:512:0 pp2048:2048:0 tg64:0:64; do
    IFS=: read -r tag prompt generation <<< "$case_spec"
    for round in 1 2 3; do
        run_inference baseline "$tag" "$prompt" "$generation" "$round-a"
        run_inference candidate "$tag" "$prompt" "$generation" "$round-a"
        run_inference candidate "$tag" "$prompt" "$generation" "$round-b"
        run_inference baseline "$tag" "$prompt" "$generation" "$round-b"
    done
done

python3 "$repo_root/experiments/e27_second_arm_ingest.py" \
    "$output_dir" "$output_dir/results/summary.json"
find "$output_dir" -type f ! -name file-inventory-sha256.txt -print0 \
    | sort -z | xargs -0 sha256sum > "$output_dir/file-inventory-sha256.txt"
jq . "$output_dir/results/summary.json"
