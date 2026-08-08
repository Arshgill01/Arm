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
if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "this experiment requires an aarch64 host" >&2
    exit 2
fi
if (( $(nproc) < 4 )); then
    echo "this experiment requires at least four logical CPUs" >&2
    exit 2
fi
if [[ ! -f "$MODEL_PATH" ]]; then
    echo "model not found: $MODEL_PATH" >&2
    exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
patch_path="$repo_root/patches/llama.cpp/b10216/0013-arm-q4-k-neon-vector-scale-kernel.patch"
correctness_src="$repo_root/experiments/e23_kernel_correctness.cpp"
bench_src="$repo_root/experiments/e23_kernel_bench.cpp"
llama_repo=${LLAMA_REPO:-https://github.com/ggml-org/llama.cpp.git}
llama_commit=876a4321163249c43ca4e986818fab5ab081f282
work_dir=${E23_WORK_DIR:-$(mktemp -d /var/tmp/e23-arm-kernel.XXXXXX)}
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"
variant_dir="$work_dir/variants"

mkdir -p "$output_dir/host" "$output_dir/source" "$output_dir/correctness" \
    "$output_dir/micro" "$output_dir/inference" "$variant_dir/baseline" "$variant_dir/candidate"

uname -a > "$output_dir/host/uname.txt"
lscpu > "$output_dir/host/lscpu.txt"
cc --version > "$output_dir/host/cc-version.txt"
c++ --version > "$output_dir/host/cxx-version.txt"
cmake --version > "$output_dir/host/cmake-version.txt"
printf '%s\n' "$work_dir" > "$output_dir/host/work-dir.txt"
sha256sum "$MODEL_PATH" > "$output_dir/source/model-sha256.txt"
stat --format='%n %s bytes' "$MODEL_PATH" > "$output_dir/source/model-size.txt"
cp "$patch_path" "$output_dir/source/candidate.patch"
sha256sum "$patch_path" > "$output_dir/source/patch-sha256.txt"
echo 'c4794e8e0087fd32691778c23b1ee559fde0e37ee69f281973ec2b02d02c33f2' \
    | diff - <(sha256sum "$patch_path" | cut -d' ' -f1)

git clone --filter=blob:none "$llama_repo" "$source_dir" \
    > "$output_dir/source/clone.stdout" 2> "$output_dir/source/clone.stderr"
git -C "$source_dir" checkout --detach "$llama_commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$llama_commit"
git -C "$source_dir" status --short > "$output_dir/source/baseline-status.txt"
test ! -s "$output_dir/source/baseline-status.txt"

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_BUILD_TYPE=Release \
    '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
    '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
    -DGGML_CPU_KLEIDIAI=ON \
    -DGGML_LTO=OFF \
    -DGGML_NATIVE=ON \
    -DLLAMA_BUILD_EXAMPLES=ON \
    -DLLAMA_BUILD_SERVER=OFF \
    -DLLAMA_BUILD_TESTS=ON \
    -DLLAMA_CURL=OFF \
    2>&1 | tee "$output_dir/source/configure.log"
cmake --build "$build_dir" --target llama-bench --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/baseline-build.log"
cp -a "$build_dir"/bin/libggml-cpu.so* "$variant_dir/baseline/"

git -C "$source_dir" apply --check "$patch_path"
git -C "$source_dir" apply "$patch_path"
git -C "$source_dir" diff --check
git -C "$source_dir" diff > "$output_dir/source/applied.patch"
git -C "$source_dir" diff --name-only > "$output_dir/source/changed-files.txt"
test "$(cat "$output_dir/source/changed-files.txt")" = 'ggml/src/ggml-cpu/arch/arm/repack.cpp'
cmake --build "$build_dir" --target ggml-cpu --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/candidate-build.log"
cp -a "$build_dir"/bin/libggml-cpu.so* "$variant_dir/candidate/"

common_compile=(
    c++ -O3 -std=c++17 -march=native
    -I"$source_dir/ggml/include"
    -I"$source_dir/ggml/src"
    -I"$source_dir/ggml/src/ggml-cpu"
    -L"$build_dir/bin"
    "-Wl,-rpath,$build_dir/bin"
)
common_libraries=(-lggml-cpu -lggml-base -lggml -fopenmp)
"${common_compile[@]}" "$correctness_src" -o "$work_dir/kernel-correctness" "${common_libraries[@]}"
"${common_compile[@]}" "$bench_src" -o "$work_dir/kernel-bench" "${common_libraries[@]}"

run_correctness() {
    local variant=$1
    LD_LIBRARY_PATH="$variant_dir/$variant:$build_dir/bin" \
        taskset --cpu-list 0-3 "$work_dir/kernel-correctness" \
        > "$output_dir/correctness/$variant.txt"
}
run_correctness baseline
run_correctness candidate
diff -u "$output_dir/correctness/baseline.txt" "$output_dir/correctness/candidate.txt" \
    > "$output_dir/correctness/baseline-vs-candidate.diff"

run_micro() {
    local variant=$1
    local round=$2
    LD_LIBRARY_PATH="$variant_dir/$variant:$build_dir/bin" \
        taskset --cpu-list 0-3 "$work_dir/kernel-bench" 3072 128 3072 8 \
        > "$output_dir/micro/${round}-${variant}.txt"
}
run_micro baseline 1
run_micro candidate 1
run_micro candidate 2
run_micro baseline 2

run_inference() {
    local prompt_tokens=$1
    local generated_tokens=$2
    local tag=$3
    local variant=$4
    local round=$5
    LD_LIBRARY_PATH="$variant_dir/$variant:$build_dir/bin" \
        taskset --cpu-list 0-3 "$build_dir/bin/llama-bench" \
        -m "$MODEL_PATH" -p "$prompt_tokens" -n "$generated_tokens" \
        -t 4 -fa 1 -r 3 -o jsonl \
        > "$output_dir/inference/${tag}-${round}-${variant}.jsonl" \
        2> "$output_dir/inference/${tag}-${round}-${variant}.stderr"
}
for test_case in 128:0:pp128 512:0:pp512 0:128:tg128; do
    IFS=: read -r prompt_tokens generated_tokens tag <<< "$test_case"
    run_inference "$prompt_tokens" "$generated_tokens" "$tag" baseline 1
    run_inference "$prompt_tokens" "$generated_tokens" "$tag" candidate 1
    run_inference "$prompt_tokens" "$generated_tokens" "$tag" candidate 2
    run_inference "$prompt_tokens" "$generated_tokens" "$tag" baseline 2
done

sha256sum "$variant_dir"/*/libggml-cpu.so* > "$output_dir/source/library-sha256.txt"
nm -S --size-sort --radix=x "$variant_dir/baseline/libggml-cpu.so" \
    > "$output_dir/source/baseline-symbols.txt"
nm -S --size-sort --radix=x "$variant_dir/candidate/libggml-cpu.so" \
    > "$output_dir/source/candidate-symbols.txt"
