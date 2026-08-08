#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 OUTPUT_DIR" >&2
    exit 2
fi
if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "E27 requires an aarch64 host" >&2
    exit 2
fi
if (( $(nproc) < 4 )); then
    echo "E27 requires at least four logical CPUs" >&2
    exit 2
fi
for command in cmake c++ curl git jq ldd ninja nm objdump perf python3 realpath sha256sum taskset /usr/bin/time; do
    command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 2; }
done

output_dir=$(realpath -m "$1")
if [[ -d "$output_dir" && -n "$(find "$output_dir" -mindepth 1 -print -quit)" ]]; then
    echo "output directory is not empty: $output_dir" >&2
    exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
contract="$repo_root/experiments/e27_contract.json"
candidate_patch="$repo_root/patches/llama.cpp/e27/0001-arm-sve-flash-attention-neon-gemm.patch"
harness_source="$repo_root/experiments/e27_flash_attn_harness.cpp"
llama_commit=$(jq -r '.source.baseline_commit' "$contract")
llama_repo=$(jq -r '.source.repository' "$contract")
work_dir=${E27_WORK_DIR:-$(mktemp -d /var/tmp/e27-arm-flash.XXXXXX)}
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"
variant_dir="$work_dir/variants"
model_dir="$work_dir/model"

mkdir -p "$output_dir"/{host,source,profile,correctness,direct,inference,demo,results} \
    "$variant_dir"/{baseline,candidate} "$model_dir"
cp "$contract" "$output_dir/contract.json"
cp "$candidate_patch" "$output_dir/source/candidate.patch"
date --utc --iso-8601=seconds > "$output_dir/captured-at.txt"

uname -a > "$output_dir/host/uname.txt"
lscpu > "$output_dir/host/lscpu.txt"
lscpu --extended > "$output_dir/host/lscpu-extended.txt"
cat /proc/cpuinfo > "$output_dir/host/cpuinfo.txt"
cat /proc/meminfo > "$output_dir/host/meminfo.txt"
cat /proc/sys/kernel/perf_event_paranoid > "$output_dir/host/perf-event-paranoid.txt"
cmake --version > "$output_dir/host/cmake-version.txt"
c++ --version > "$output_dir/host/cxx-version.txt"
perf --version > "$output_dir/host/perf-version.txt"
printf '%s\n' "$work_dir" > "$output_dir/host/work-dir.txt"
if [[ -r /proc/sys/abi/sve_default_vector_length ]]; then
    cat /proc/sys/abi/sve_default_vector_length > "$output_dir/host/sve-default-vector-length.txt"
fi
metadata=http://metadata.google.internal/computeMetadata/v1/instance
header='Metadata-Flavor: Google'
for field in id machine-type zone preempted maintenance-event; do
    curl --fail --silent --header "$header" "$metadata/$field" \
        > "$output_dir/host/metadata-$field.txt"
done
test "$(cat "$output_dir/host/metadata-preempted.txt")" = FALSE
test "$(cat "$output_dir/host/metadata-maintenance-event.txt")" = NONE
grep -q 'Neoverse-V2' "$output_dir/host/lscpu.txt"
grep -q '^armv8_pmuv3' < <(find /sys/bus/event_source/devices -maxdepth 1 -mindepth 1 -printf '%f\n')

git clone --filter=blob:none "$llama_repo" "$source_dir" \
    > "$output_dir/source/clone.stdout" 2> "$output_dir/source/clone.stderr"
git -C "$source_dir" checkout --detach "$llama_commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$llama_commit"
git -C "$source_dir" ls-remote origin refs/heads/master \
    > "$output_dir/source/current-upstream-master.txt"

mapfile -t baseline_patches < <(jq -r '.source.cumulative_baseline_patches[]' "$contract")
sha256sum "$contract" "$candidate_patch" "$harness_source" \
    "${baseline_patches[@]/#/$repo_root/}" > "$output_dir/source/input-sha256.txt"
for relative_patch in "${baseline_patches[@]}"; do
    patch="$repo_root/$relative_patch"
    git -C "$source_dir" apply --check "$patch"
    git -C "$source_dir" apply "$patch"
done
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index > "$output_dir/source/cumulative-baseline.patch"
git -C "$source_dir" diff --name-only > "$output_dir/source/cumulative-baseline-files.txt"

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
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_CURL=OFF \
    -DLLAMA_OPENSSL=OFF \
    2>&1 | tee "$output_dir/source/configure.log"
cmake --build "$build_dir" --target llama-bench llama-completion --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/baseline-build.log"
ninja -C "$build_dir" -t commands > "$output_dir/source/baseline-build-commands.txt"
cp -a "$build_dir/bin/." "$variant_dir/baseline/"

model_repository=$(jq -r '.primary_model.repository' "$contract")
model_revision=$(jq -r '.primary_model.revision' "$contract")
model_filename=$(jq -r '.primary_model.filename' "$contract")
model="$model_dir/$model_filename"
if [[ -n "${MODEL_PATH:-}" ]]; then
    cp --reflink=auto "$MODEL_PATH" "$model"
else
    curl --fail --location --retry 5 --retry-all-errors --output "$model" \
        "https://huggingface.co/$model_repository/resolve/$model_revision/$model_filename?download=true"
fi
test "$(stat --format='%s' "$model")" = "$(jq -r '.primary_model.size_bytes' "$contract")"
echo "$(jq -r '.primary_model.sha256' "$contract")  $model" | sha256sum --check --strict
sha256sum "$model" > "$output_dir/source/model-sha256.txt"

common_bench=(
    --model "$model"
    --threads 4
    --n-gpu-layers 0
    --flash-attn on
    --batch-size 1024
    --ubatch-size 512
    --no-warmup
    --output jsonl
)

profile_case() {
    local prompt_tokens=$1
    local tag=$2
    local case_dir="$output_dir/profile/$tag"
    mkdir -p "$case_dir"
    local -a command=(taskset -c 0-3 "$variant_dir/baseline/llama-bench" "${common_bench[@]}" --repetitions 1 --n-prompt "$prompt_tokens" --n-gen 0)
    printf '%q ' "${command[@]}" > "$case_dir/command.txt"
    printf '\n' >> "$case_dir/command.txt"
    LD_LIBRARY_PATH="$variant_dir/baseline" "${command[@]}" > "$case_dir/control.jsonl" 2> "$case_dir/control.stderr"
    LD_LIBRARY_PATH="$variant_dir/baseline" perf stat --no-big-num -x, \
        -e cpu_cycles,inst_retired,l1d_cache,l1d_cache_refill,l2d_cache \
        --output "$case_dir/perf-stat.csv" -- "${command[@]}" \
        > "$case_dir/perf-stat.jsonl" 2> "$case_dir/perf-stat.stderr"
    LD_LIBRARY_PATH="$variant_dir/baseline" perf record -e cpu_cycles:u -c 100000 \
        --output "$case_dir/perf.data" -- "${command[@]}" \
        > "$case_dir/perf-record.jsonl" 2> "$case_dir/perf-record.stderr"
    perf report --stdio --no-children --input "$case_dir/perf.data" --sort symbol \
        --percent-limit 0.01 > "$case_dir/perf-report-symbol.txt"
    perf annotate --stdio --input "$case_dir/perf.data" \
        'ggml_compute_forward_flash_attn_ext_tiled(ggml_compute_params const*, ggml_tensor*, int, int)' \
        > "$case_dir/annotate-flash-attn-tiled.txt" 2>&1 || true
}

profile_case 512 pp512
profile_case 2048 pp2048
profile_case 4096 pp4096

git -C "$source_dir" apply --check "$candidate_patch"
git -C "$source_dir" apply "$candidate_patch"
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index > "$output_dir/source/cumulative-candidate.patch"
git -C "$source_dir" diff --name-only > "$output_dir/source/cumulative-candidate-files.txt"
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
        --mode compare --head-size 128 --query-tokens 64 --kv-tokens 128 \
        --query-heads 24 --kv-heads 8 --threads 4 --repetitions 1 --seed "$seed" --kv-type f16 \
        >> "$output_dir/correctness/d128-q64-kv128.jsonl"
    taskset -c 0-3 "$variant_dir/candidate/e27-flash-harness" \
        --mode compare --head-size 128 --query-tokens 64 --kv-tokens 512 \
        --query-heads 24 --kv-heads 8 --threads 4 --repetitions 1 --seed "$seed" --kv-type f16 \
        >> "$output_dir/correctness/d128-q64-kv512.jsonl"
    taskset -c 0-3 "$variant_dir/candidate/e27-flash-harness" \
        --mode compare --head-size 64 --query-tokens 64 --kv-tokens 512 \
        --query-heads 12 --kv-heads 4 --threads 4 --repetitions 1 --seed "$seed" --kv-type f32 \
        >> "$output_dir/correctness/d64-q64-kv512-f32.jsonl"
done
jq -e -s 'all(.[]; .pass == true and .nmse <= .tolerance_nmse)' "$output_dir/correctness"/*.jsonl >/dev/null

run_direct() {
    local variant=$1
    local tag=$2
    local head_size=$3
    local query_tokens=$4
    local kv_tokens=$5
    local query_heads=$6
    local kv_heads=$7
    local run=$8
    LD_LIBRARY_PATH="$variant_dir/$variant" taskset -c 0-3 "$variant_dir/$variant/e27-flash-harness" \
        --mode tiled --head-size "$head_size" --query-tokens "$query_tokens" --kv-tokens "$kv_tokens" \
        --query-heads "$query_heads" --kv-heads "$kv_heads" --threads 4 --repetitions 7 --seed 42 --kv-type f16 \
        > "$output_dir/direct/$tag-$run-$variant.json"
}

for case_spec in d128-q512-kv512:128:512:512:24:8 d128-q512-kv2048:128:512:2048:24:8 d128-q512-kv4096:128:512:4096:24:8; do
    IFS=: read -r tag head_size query_tokens kv_tokens query_heads kv_heads <<< "$case_spec"
    for round in 1 2 3; do
        run_direct baseline "$tag" "$head_size" "$query_tokens" "$kv_tokens" "$query_heads" "$kv_heads" "$round-a"
        run_direct candidate "$tag" "$head_size" "$query_tokens" "$kv_tokens" "$query_heads" "$kv_heads" "$round-a"
        run_direct candidate "$tag" "$head_size" "$query_tokens" "$kv_tokens" "$query_heads" "$kv_heads" "$round-b"
        run_direct baseline "$tag" "$head_size" "$query_tokens" "$kv_tokens" "$query_heads" "$kv_heads" "$round-b"
    done
done

run_inference() {
    local variant=$1
    local tag=$2
    local prompt_tokens=$3
    local generated_tokens=$4
    local run=$5
    LD_LIBRARY_PATH="$variant_dir/$variant" taskset -c 0-3 "$variant_dir/$variant/llama-bench" \
        "${common_bench[@]}" --repetitions 3 --n-prompt "$prompt_tokens" --n-gen "$generated_tokens" \
        > "$output_dir/inference/$tag-$run-$variant.jsonl" \
        2> "$output_dir/inference/$tag-$run-$variant.stderr"
}

for case_spec in pp512:512:0 pp2048:2048:0 pp4096:4096:0 tg128:0:128; do
    IFS=: read -r tag prompt_tokens generated_tokens <<< "$case_spec"
    for round in 1 2 3; do
        run_inference baseline "$tag" "$prompt_tokens" "$generated_tokens" "$round-a"
        run_inference candidate "$tag" "$prompt_tokens" "$generated_tokens" "$round-a"
        run_inference candidate "$tag" "$prompt_tokens" "$generated_tokens" "$round-b"
        run_inference baseline "$tag" "$prompt_tokens" "$generated_tokens" "$round-b"
    done
done

candidate_profile="$output_dir/profile/candidate-pp2048"
mkdir -p "$candidate_profile"
candidate_command=(taskset -c 0-3 "$variant_dir/candidate/llama-bench" "${common_bench[@]}" --repetitions 1 --n-prompt 2048 --n-gen 0)
LD_LIBRARY_PATH="$variant_dir/candidate" perf record -e cpu_cycles:u -c 100000 \
    --output "$candidate_profile/perf.data" -- "${candidate_command[@]}" \
    > "$candidate_profile/perf-record.jsonl" 2> "$candidate_profile/perf-record.stderr"
perf report --stdio --no-children --input "$candidate_profile/perf.data" --sort symbol \
    --percent-limit 0.01 > "$candidate_profile/perf-report-symbol.txt"
perf annotate --stdio --input "$candidate_profile/perf.data" \
    'ggml_compute_forward_flash_attn_ext_tiled(ggml_compute_params const*, ggml_tensor*, int, int)' \
    > "$candidate_profile/annotate-flash-attn-tiled.txt" 2>&1 || true

python3 - "$output_dir/demo/prompt.txt" <<'PY'
import pathlib
import sys

paragraph = (
    "Arm CPU inference benefits from careful data movement, predictable tiling, and measured vector kernels. "
    "This fixed paragraph forms one deterministic long request for a time-to-first-token comparison. "
)
pathlib.Path(sys.argv[1]).write_text((paragraph * 220) + "\nSummarize the engineering priorities in one sentence.\n")
PY

run_demo() {
    local variant=$1
    /usr/bin/time --verbose --output "$output_dir/demo/$variant.time" \
        env LD_LIBRARY_PATH="$variant_dir/$variant" taskset -c 0-3 "$variant_dir/$variant/llama-completion" \
        -m "$model" -f "$output_dir/demo/prompt.txt" -n 1 --seed 42 --temp 0 \
        -t 4 -c 8192 -b 1024 -ub 512 --no-warmup --no-display-prompt --no-conversation \
        > "$output_dir/demo/$variant.stdout" 2> "$output_dir/demo/$variant.stderr"
}
run_demo baseline
run_demo candidate
diff -u "$output_dir/demo/baseline.stdout" "$output_dir/demo/candidate.stdout" \
    > "$output_dir/demo/output.diff" || true
sha256sum "$output_dir/demo"/*.stdout > "$output_dir/demo/output-sha256.txt"

sha256sum "$variant_dir"/baseline/libggml-cpu.so* "$variant_dir"/candidate/libggml-cpu.so* \
    > "$output_dir/source/library-sha256.txt"
nm -C "$variant_dir/baseline/libggml-cpu.so" > "$output_dir/source/baseline-symbols.txt"
nm -C "$variant_dir/candidate/libggml-cpu.so" > "$output_dir/source/candidate-symbols.txt"
objdump -d -C "$variant_dir/baseline/libggml-cpu.so" > "$output_dir/source/baseline-assembly.txt"
objdump -d -C "$variant_dir/candidate/libggml-cpu.so" > "$output_dir/source/candidate-assembly.txt"
ldd "$variant_dir/baseline/llama-bench" > "$output_dir/source/baseline-loader.txt"
ldd "$variant_dir/candidate/llama-bench" > "$output_dir/source/candidate-loader.txt"

python3 "$repo_root/experiments/e27_ingest.py" "$output_dir" "$output_dir/results/summary.json"
find "$output_dir" -type f ! -name file-inventory-sha256.txt ! -name perf.data -print0 \
    | sort -z | xargs -0 sha256sum > "$output_dir/file-inventory-sha256.txt"
jq . "$output_dir/results/summary.json"
