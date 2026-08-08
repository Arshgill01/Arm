#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "${MODEL_PATH:-}" ]]; then
    echo "usage: MODEL_PATH=/path/to/Ministral-Q4_K_M.gguf $0 OUTPUT_DIR" >&2
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

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
llama_commit=876a4321163249c43ca4e986818fab5ab081f282
model_sha256=fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4
model_size=2146497824
work_dir=${E25_WORK_DIR:-$(mktemp -d /var/tmp/e25-q4-layout.XXXXXX)}
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"
variant_dir="$work_dir/variants"
baseline_patches=(
    "$repo_root/patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch"
    "$repo_root/patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch"
    "$repo_root/patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch"
    "$repo_root/patches/llama.cpp/b10216/0013-arm-q4-k-neon-vector-scale-kernel.patch"
    "$repo_root/patches/llama.cpp/b10216/0016-arm-q6-k-gemv-fused-scales.patch"
    "$repo_root/patches/llama.cpp/b10216/0020-arm-q6-k-gemv-just-in-time-loads.patch"
)
candidate_patch="$repo_root/patches/llama.cpp/e25/0003-q4-k-decoded-metadata-layout.patch"

test "$(stat --format='%s' "$MODEL_PATH")" = "$model_size"
echo "$model_sha256  $MODEL_PATH" | sha256sum --check --strict
mkdir -p "$output_dir"/{host,source,correctness,direct,pp512,tg128,demo} \
    "$variant_dir"/{e24,e25}
date --utc --iso-8601=seconds > "$output_dir/captured-at.txt"
uname -a > "$output_dir/host/uname.txt"
lscpu > "$output_dir/host/lscpu.txt"
cc --version > "$output_dir/host/cc-version.txt"
cmake --version > "$output_dir/host/cmake-version.txt"
sha256sum "$MODEL_PATH" > "$output_dir/source/model-sha256.txt"
sha256sum "${baseline_patches[@]}" "$candidate_patch" \
    > "$output_dir/source/patch-sha256.txt"

git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$source_dir" \
    > "$output_dir/source/clone.stdout" 2> "$output_dir/source/clone.stderr"
git -C "$source_dir" checkout --detach "$llama_commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$llama_commit"
for patch in "${baseline_patches[@]}"; do
    git -C "$source_dir" apply --check "$patch"
    git -C "$source_dir" apply "$patch"
done
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index HEAD \
    > "$output_dir/source/e24-cumulative.patch"

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_NATIVE=ON \
    -DGGML_OPENMP=ON \
    -DLLAMA_BUILD_SERVER=OFF \
    2>&1 | tee "$output_dir/source/configure.log"
cmake --build "$build_dir" --parallel "$(nproc)" \
    --target llama-bench llama-completion \
    2>&1 | tee "$output_dir/source/e24-build.log"
cp -a "$build_dir/bin/." "$variant_dir/e24/"

git -C "$source_dir" apply --check "$candidate_patch"
git -C "$source_dir" apply "$candidate_patch"
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index HEAD \
    > "$output_dir/source/e25-cumulative.patch"
cmake --build "$build_dir" --parallel "$(nproc)" \
    --target llama-bench llama-completion \
    2>&1 | tee "$output_dir/source/e25-build.log"
cp -a "$build_dir/bin/." "$variant_dir/e25/"

compile=(
    c++ -O3 -std=c++17 -march=native
    -I"$source_dir/ggml/include"
    -I"$source_dir/ggml/src"
    -I"$source_dir/ggml/src/ggml-cpu"
    -L"$build_dir/bin" "-Wl,-rpath,$build_dir/bin"
)
libraries=(-lggml-cpu -lggml-base -lggml -fopenmp)
"${compile[@]}" "$repo_root/experiments/e25_q4_layout_bench.cpp" \
    -o "$work_dir/q4-layout-bench" "${libraries[@]}"
"${compile[@]}" "$repo_root/experiments/e25_q4_gemm_correctness.cpp" \
    -o "$work_dir/q4-gemm-correctness" "${libraries[@]}"

taskset --cpu-list 0 "$work_dir/q4-gemm-correctness" \
    > "$output_dir/correctness/gemm.txt"
for shape in 3072:2304 9216:768; do
    IFS=: read -r n nc <<< "$shape"
    for round in 1 2 3; do
        taskset --cpu-list 0 "$work_dir/q4-layout-bench" "$n" "$nc" 51 \
            > "$output_dir/direct/n${n}-nc${nc}-r${round}.txt"
    done
done

run_bench() {
    local case_name=$1
    local prompt_tokens=$2
    local generation_tokens=$3
    local round=$4
    local order=$5
    local variant=$6
    local bin_dir="$variant_dir/$variant"
    /usr/bin/time --verbose --output "$output_dir/$case_name/r${round}-${order}-${variant}.time.txt" \
        env LD_LIBRARY_PATH="$bin_dir" taskset --cpu-list 0-3 "$bin_dir/llama-bench" \
        --model "$MODEL_PATH" --threads 4 --n-gpu-layers 0 --flash-attn on \
        --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl \
        --repetitions 3 --n-prompt "$prompt_tokens" --n-gen "$generation_tokens" \
        > "$output_dir/$case_name/r${round}-${order}-${variant}.jsonl" \
        2> "$output_dir/$case_name/r${round}-${order}-${variant}.stderr.txt"
}
for case_name in pp512 tg128; do
    if [[ "$case_name" = pp512 ]]; then
        prompt_tokens=512
        generation_tokens=0
        rounds=2
    else
        prompt_tokens=0
        generation_tokens=128
        rounds=2
    fi
    for round in $(seq 1 "$rounds"); do
        run_bench "$case_name" "$prompt_tokens" "$generation_tokens" "$round" 01 e24
        run_bench "$case_name" "$prompt_tokens" "$generation_tokens" "$round" 02 e25
        run_bench "$case_name" "$prompt_tokens" "$generation_tokens" "$round" 03 e25
        run_bench "$case_name" "$prompt_tokens" "$generation_tokens" "$round" 04 e24
    done
    for variant in e24 e25; do
        jq -s '[.[].avg_ts] | sort | {samples: ., median: (if length % 2 == 1 then .[length/2|floor] else ((.[length/2-1] + .[length/2]) / 2) end)}' \
            "$output_dir/$case_name"/*-"$variant".jsonl \
            > "$output_dir/$case_name/$variant-summary.json"
    done
done

"$repo_root/scripts/demo_e25_q4_k_decode_layout.sh" \
    "$variant_dir/e24" "$variant_dir/e25" "$MODEL_PATH" "$output_dir/demo"
find "$output_dir" -type f ! -name file-inventory-sha256.txt -print0 \
    | sort -z | xargs -0 sha256sum > "$output_dir/file-inventory-sha256.txt"
