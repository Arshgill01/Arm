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
llama_commit=876a4321163249c43ca4e986818fab5ab081f282
work_dir=${E24C_WORK_DIR:-$(mktemp -d /var/tmp/e24c-second-arm.XXXXXX)}
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"
variant_dir="$work_dir/variants"
common_patches=(
    "$repo_root/patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch"
    "$repo_root/patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch"
    "$repo_root/patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch"
)
e23_patch="$repo_root/patches/llama.cpp/b10216/0013-arm-q4-k-neon-vector-scale-kernel.patch"
decode_patches=(
    "$repo_root/patches/llama.cpp/b10216/0016-arm-q6-k-gemv-fused-scales.patch"
    "$repo_root/patches/llama.cpp/b10216/0020-arm-q6-k-gemv-just-in-time-loads.patch"
)

mkdir -p "$output_dir"/{host,source,correctness,direct,inference,live} \
    "$variant_dir"/{baseline,candidate}
uname -a > "$output_dir/host/uname.txt"
lscpu > "$output_dir/host/lscpu.txt"
cc --version > "$output_dir/host/cc-version.txt"
c++ --version > "$output_dir/host/cxx-version.txt"
cmake --version > "$output_dir/host/cmake-version.txt"
sha256sum "$MODEL_PATH" > "$output_dir/source/model-sha256.txt"
stat --format='%n %s bytes' "$MODEL_PATH" > "$output_dir/source/model-size.txt"
sha256sum "${common_patches[@]}" "$e23_patch" "${decode_patches[@]}" \
    > "$output_dir/source/patch-sha256.txt"

git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$source_dir" \
    > "$output_dir/source/clone.stdout" 2> "$output_dir/source/clone.stderr"
git -C "$source_dir" checkout --detach "$llama_commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$llama_commit"
for patch in "${common_patches[@]}" "$e23_patch"; do
    git -C "$source_dir" apply --check "$patch"
    git -C "$source_dir" apply "$patch"
done
git -C "$source_dir" diff --check
git -C "$source_dir" diff > "$output_dir/source/e23-baseline.patch"

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
    2>&1 | tee "$output_dir/source/baseline-build.log"
cp -a "$build_dir/bin/." "$variant_dir/baseline/"

for patch in "${decode_patches[@]}"; do
    git -C "$source_dir" apply --check "$patch"
    git -C "$source_dir" apply "$patch"
done
git -C "$source_dir" diff --check
git -C "$source_dir" diff > "$output_dir/source/combined.patch"
cmake --build "$build_dir" --target ggml-cpu --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/candidate-build.log"
cp -a "$build_dir/bin/." "$variant_dir/candidate/"

compile=(
    c++ -O3 -std=c++17 -march=native
    -I"$source_dir/ggml/include"
    -I"$source_dir/ggml/src"
    -I"$source_dir/ggml/src/ggml-cpu"
    -L"$build_dir/bin" "-Wl,-rpath,$build_dir/bin"
)
libraries=(-lggml-cpu -lggml-base -lggml -fopenmp)
"${compile[@]}" "$repo_root/experiments/e24_q6_gemv_correctness.cpp" \
    -o "$work_dir/q6-correctness" "${libraries[@]}"
"${compile[@]}" "$repo_root/experiments/e24_q6_gemv_bench.cpp" \
    -o "$work_dir/q6-bench" "${libraries[@]}"

run_direct() {
    local variant=$1
    local binary=$2
    shift 2
    LD_LIBRARY_PATH="$variant_dir/$variant" taskset --cpu-list 0-3 "$binary" "$@"
}
run_direct baseline "$work_dir/q6-correctness" > "$output_dir/correctness/baseline.txt"
run_direct candidate "$work_dir/q6-correctness" > "$output_dir/correctness/candidate.txt"
diff -u "$output_dir/correctness/baseline.txt" "$output_dir/correctness/candidate.txt" \
    > "$output_dir/correctness/baseline-vs-candidate.diff"

for shape in 3072:2304 9216:768; do
    IFS=: read -r n nc <<< "$shape"
    for round in 1 2 3; do
        for variant in baseline candidate candidate baseline; do
            run_direct "$variant" "$work_dir/q6-bench" "$n" "$nc" 31 \
                > "$output_dir/direct/n${n}-nc${nc}-${round}-${variant}-$(date +%s%N).txt"
        done
    done
done

run_inference() {
    local variant=$1
    local round=$2
    taskset --cpu-list 0-3 "$variant_dir/$variant/llama-bench" \
        -m "$MODEL_PATH" -p 0 -n 128 -t 4 -fa 1 -b 1024 -ub 512 \
        --no-warmup -r 3 -o jsonl \
        > "$output_dir/inference/tg128-${round}-${variant}.jsonl" \
        2> "$output_dir/inference/tg128-${round}-${variant}.stderr"
}
for round in 1 2 3; do
    run_inference baseline "$round-a"
    run_inference candidate "$round-a"
    run_inference candidate "$round-b"
    run_inference baseline "$round-b"
done
for variant in baseline candidate; do
    jq -s '[.[].avg_ts] | sort | {samples: ., median: ((.[2] + .[3]) / 2), mean: (add / length), min: .[0], max: .[-1]}' \
        "$output_dir/inference"/tg128-*-$variant.jsonl \
        > "$output_dir/inference/tg128-$variant-summary.json"
done

prompt='Explain why measurement order must be balanced in one sentence.'
for variant in baseline candidate; do
    taskset --cpu-list 0-3 "$variant_dir/$variant/llama-completion" \
        -m "$MODEL_PATH" -p "$prompt" -n 24 --seed 42 --temp 0 \
        -t 4 -c 2048 -b 512 -ub 512 --no-warmup --no-display-prompt \
        --no-conversation > "$output_dir/live/$variant.stdout" \
        2> "$output_dir/live/$variant.stderr"
done
diff -u "$output_dir/live/baseline.stdout" "$output_dir/live/candidate.stdout" \
    > "$output_dir/live/output.diff"
sha256sum "$output_dir/live"/*.stdout > "$output_dir/live/output-sha256.txt"

LD_DEBUG=libs taskset --cpu-list 0-3 "$variant_dir/baseline/llama-bench" \
    -m "$MODEL_PATH" -p 1 -n 1 -t 4 -r 1 -o jsonl \
    > /dev/null 2> "$output_dir/source/baseline-loader.txt"
LD_DEBUG=libs taskset --cpu-list 0-3 "$variant_dir/candidate/llama-bench" \
    -m "$MODEL_PATH" -p 1 -n 1 -t 4 -r 1 -o jsonl \
    > /dev/null 2> "$output_dir/source/candidate-loader.txt"
sha256sum "$variant_dir"/*/libggml-cpu.so* > "$output_dir/source/library-sha256.txt"
