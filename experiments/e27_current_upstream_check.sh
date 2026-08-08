#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 OUTPUT_DIR" >&2
    exit 2
fi
if [[ "$(uname -m)" != "aarch64" || "$(nproc)" -lt 4 ]]; then
    echo "current-upstream E27 validation requires at least four aarch64 CPUs" >&2
    exit 2
fi
for command in cmake c++ git jq ninja nm objdump python3 sha256sum taskset; do
    command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 2; }
done

output_dir=$(realpath -m "$1")
if [[ -e "$output_dir" ]]; then
    echo "output path already exists: $output_dir" >&2
    exit 2
fi
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
contract="$repo_root/experiments/e27_contract.json"
patch="$repo_root/patches/llama.cpp/e27/0001-arm-sve-flash-attention-neon-gemm.patch"
harness_source="$repo_root/experiments/e27_flash_attn_harness.cpp"
repository=$(jq -r '.source.repository' "$contract")
commit=$(jq -r '.source.audited_current_commit' "$contract")
work_dir=${E27_CURRENT_WORK_DIR:-$(mktemp -d /var/tmp/e27-current.XXXXXX)}
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"
variant_dir="$work_dir/variants"

mkdir -p "$output_dir"/{host,source,correctness,direct,results} \
    "$variant_dir"/{baseline,candidate}
cp "$contract" "$output_dir/contract.json"
date --utc --iso-8601=seconds > "$output_dir/captured-at.txt"
uname -a > "$output_dir/host/uname.txt"
lscpu > "$output_dir/host/lscpu.txt"
c++ --version > "$output_dir/host/cxx-version.txt"
sha256sum "$contract" "$patch" "$harness_source" > "$output_dir/source/input-sha256.txt"

git clone --filter=blob:none "$repository" "$source_dir"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
git -C "$source_dir" apply --check "$patch"

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CPU_KLEIDIAI=OFF -DGGML_LTO=OFF -DGGML_NATIVE=ON \
    -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF \
    -DLLAMA_BUILD_TESTS=OFF -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
    2>&1 | tee "$output_dir/source/configure.log"
cmake --build "$build_dir" --target ggml-cpu --parallel "$(nproc)" \
    2>&1 | tee "$output_dir/source/baseline-build.log"
cp -a "$build_dir/bin/." "$variant_dir/baseline/"

git -C "$source_dir" apply "$patch"
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index > "$output_dir/source/candidate.patch"
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
        --query-heads 24 --kv-heads 8 --threads 4 --repetitions 1 \
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
        --query-heads 24 --kv-heads 8 --threads 4 --repetitions 5 \
        --seed 42 --kv-type f16 > "$output_dir/direct/$tag-$run-$variant.json" \
        2> "$output_dir/direct/$tag-$run-$variant.stderr"
}
for case_spec in d128-q512-kv2048:2048 d128-q512-kv4096:4096; do
    IFS=: read -r tag kv_tokens <<< "$case_spec"
    for round in 1 2 3; do
        run_direct baseline "$tag" "$kv_tokens" "$round-a"
        run_direct candidate "$tag" "$kv_tokens" "$round-a"
        run_direct candidate "$tag" "$kv_tokens" "$round-b"
        run_direct baseline "$tag" "$kv_tokens" "$round-b"
    done
done

nm -C "$variant_dir/baseline/libggml-cpu.so" > "$output_dir/source/baseline-symbols.txt"
nm -C "$variant_dir/candidate/libggml-cpu.so" > "$output_dir/source/candidate-symbols.txt"
objdump -d -C "$variant_dir/baseline/libggml-cpu.so" \
    > "$output_dir/source/baseline-assembly.txt"
objdump -d -C "$variant_dir/candidate/libggml-cpu.so" \
    > "$output_dir/source/candidate-assembly.txt"

python3 - "$output_dir" <<'PY'
import json
import pathlib
import statistics
import sys

root = pathlib.Path(sys.argv[1])
correctness = [json.loads(line) for line in (root / "correctness/d128-q64-kv512.jsonl").read_text().splitlines()]
direct = {}
for case in ("d128-q512-kv2048", "d128-q512-kv4096"):
    direct[case] = {}
    for variant in ("baseline", "candidate"):
        values = [
            float(json.loads(path.read_text())["median_us"])
            for path in sorted((root / "direct").glob(f"{case}-*-{variant}.json"))
        ]
        if len(values) != 6:
            raise ValueError(f"expected six {case} {variant} samples")
        direct[case][variant] = {"samples_us": values, "median_us": statistics.median(values)}
    direct[case]["speedup"] = direct[case]["baseline"]["median_us"] / direct[case]["candidate"]["median_us"]
gates = {
    "correctness": len(correctness) == 3 and all(row["pass"] for row in correctness),
    "direct_all_at_least_1_20x": all(value["speedup"] >= 1.20 for value in direct.values()),
}
gates["accepted"] = all(gates.values())
result = {
    "schema_version": 1,
    "experiment_id": "E27-current-upstream",
    "correctness": {"maximum_nmse": max(row["nmse"] for row in correctness)},
    "direct": direct,
    "gates": gates,
}
(root / "results/summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(gates, sort_keys=True))
if not gates["accepted"]:
    raise SystemExit(1)
PY

find "$output_dir" -type f ! -name file-inventory-sha256.txt -print0 \
    | sort -z | xargs -0 sha256sum > "$output_dir/file-inventory-sha256.txt"
jq . "$output_dir/results/summary.json"
