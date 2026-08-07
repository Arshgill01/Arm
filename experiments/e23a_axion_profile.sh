#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: e23a_axion_profile.sh CONTRACT EVIDENCE WORK_ROOT" >&2
  exit 2
fi

contract="$(realpath "$1")"
evidence="$(realpath -m "$2")"
work_root="$(realpath -m "$3")"
package_root="$(dirname "$(dirname "$contract")")"
source_dir="$work_root/llama.cpp"
build_dir="$work_root/build"
model_dir="$work_root/models"

test "$(uname -m)" = aarch64
test "$(jq -r '.experiment_id' "$contract")" = E23a
test ! -e "$evidence"
test ! -e "$work_root"

sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential cmake curl git jq linux-tools-common linux-tools-generic \
  ninja-build time
sudo sysctl -w kernel.perf_event_paranoid=1

mkdir -p "$evidence/build" "$evidence/host" "$evidence/model" \
  "$evidence/profile" "$evidence/results" "$model_dir"
cp "$contract" "$evidence/contract.json"
date --utc --iso-8601=seconds > "$evidence/captured-at.txt"
uname -a > "$evidence/host/uname.txt"
lscpu > "$evidence/host/lscpu.txt"
lscpu --extended > "$evidence/host/lscpu-extended.txt"
cat /proc/cpuinfo > "$evidence/host/cpuinfo.txt"
cat /proc/meminfo > "$evidence/host/meminfo.txt"
cat /proc/sys/kernel/perf_event_paranoid > "$evidence/host/perf-event-paranoid.txt"
perf --version > "$evidence/host/perf-version.txt"
perf list > "$evidence/host/perf-list.txt" 2>&1
gcc --version > "$evidence/build/gcc-version.txt"
cmake --version > "$evidence/build/cmake-version.txt"
ninja --version > "$evidence/build/ninja-version.txt"

metadata=http://metadata.google.internal/computeMetadata/v1/instance
header='Metadata-Flavor: Google'
for field in id machine-type zone preempted maintenance-event; do
  curl --fail --silent --header "$header" "$metadata/$field" \
    > "$evidence/host/metadata-${field}.txt"
done
test "$(nproc)" = "$(jq -r '.host.logical_cpus' "$contract")"
test "$(cat "$evidence/host/metadata-preempted.txt")" = FALSE
test "$(cat "$evidence/host/metadata-maintenance-event.txt")" = NONE
grep -q 'Neoverse-V2' "$evidence/host/lscpu.txt"
grep -q '^armv8_pmuv3' < <(find /sys/bus/event_source/devices -maxdepth 1 -mindepth 1 -printf '%f\n')

repository="$(jq -r '.source.repository' "$contract")"
commit="$(jq -r '.source.commit' "$contract")"
tag="$(jq -r '.source.tag' "$contract")"
git clone --filter=blob:none "$repository" "$source_dir"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
test "$(git -C "$source_dir" describe --tags --exact-match)" = "$tag"

while IFS= read -r patch_file; do
  git -C "$source_dir" apply --check "$package_root/$patch_file"
  git -C "$source_dir" apply "$package_root/$patch_file"
done < <(jq -r '.source.patches[]' "$contract")
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index HEAD -- \
  > "$evidence/build/source-diff.patch"
git -C "$source_dir" diff --name-only HEAD | sort \
  > "$evidence/build/source-patched-files.txt"

mapfile -t cmake_args < <(jq -r '.build.cmake_arguments[]' "$contract")
cmake -S "$source_dir" -B "$build_dir" -G Ninja \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "${cmake_args[@]}" \
  2>&1 | tee "$evidence/build/configure.log"
grep -q 'Using KleidiAI optimized kernels if applicable' \
  "$evidence/build/configure.log"
grep -q 'ARM detected' "$evidence/build/configure.log"
cp "$build_dir/CMakeCache.txt" "$evidence/build/CMakeCache.txt"
/usr/bin/time --verbose --output "$evidence/build/build-time.log" \
  cmake --build "$build_dir" --target llama-bench --parallel "$(nproc)" \
  2>&1 | tee "$evidence/build/build.log"
ninja -C "$build_dir" -t commands > "$evidence/build/build-commands.txt"
cp "$build_dir/compile_commands.json" "$evidence/build/compile_commands.json"
bench="$build_dir/bin/llama-bench"
"$bench" --version 2>&1 | tee "$evidence/build/bench-version.txt"
sha256sum "$bench" > "$evidence/build/bench-sha256.txt"
file "$bench" > "$evidence/build/bench-file.txt"
nm --defined-only --demangle "$bench" > "$evidence/build/bench-symbols.txt"
for symbol in \
  ggml_gemm_q4_K_8x8_q8_K \
  ggml_gemv_q4_K_8x8_q8_K \
  ggml_quantize_mat_q8_K_4x8_generic \
  quantize_row_q8_K_ref; do
  objdump --disassemble="$symbol" "$bench" \
    > "$evidence/build/${symbol}.asm.txt" 2>&1 || true
done

model_repository="$(jq -r '.model.repository' "$contract")"
model_revision="$(jq -r '.model.revision' "$contract")"
model_entrypoint="$(jq -r '.model.entrypoint' "$contract")"
model="$model_dir/$model_entrypoint"
curl --fail --location --retry 5 --retry-all-errors \
  --output "$model" \
  "https://huggingface.co/$model_repository/resolve/$model_revision/$model_entrypoint?download=true"
test "$(stat --format='%s' "$model")" = "$(jq -r '.model.size_bytes' "$contract")"
echo "$(jq -r '.model.sha256' "$contract")  $model" | sha256sum --check --strict
sha256sum "$model" > "$evidence/model/model-sha256.txt"

core_set="$(jq -r '.host.benchmark_core_set' "$contract")"
sample_period="$(jq -r '.benchmark.perf_sample_period' "$contract")"
mapfile -t common_args < <(jq -r '.benchmark.common_arguments[]' "$contract")

while IFS=$'\t' read -r name prompt generation; do
  case_dir="$evidence/profile/$name"
  mkdir -p "$case_dir"
  argv=("$bench" --model "$model" "${common_args[@]}" \
    --repetitions 3 --n-prompt "$prompt" --n-gen "$generation")
  printf '%q ' taskset -c "$core_set" "${argv[@]}" > "$case_dir/control-command.txt"
  printf '\n' >> "$case_dir/control-command.txt"
  /usr/bin/time --verbose --output "$case_dir/control-time.txt" \
    taskset -c "$core_set" "${argv[@]}" \
    > "$case_dir/control.jsonl" 2> "$case_dir/control.stderr.txt"

  sampled_argv=("$bench" --model "$model" "${common_args[@]}" \
    --repetitions 1 --n-prompt "$prompt" --n-gen "$generation")
  perf stat --no-big-num -x, \
    -e cpu_cycles,inst_retired,l1d_cache,l1d_cache_refill,l2d_cache \
    --output "$case_dir/perf-stat.csv" -- \
    taskset -c "$core_set" "${sampled_argv[@]}" \
    > "$case_dir/perf-stat.jsonl" 2> "$case_dir/perf-stat.stderr.txt"
  perf record -e cpu_cycles:u -c "$sample_period" \
    --output "$case_dir/perf.data" -- \
    taskset -c "$core_set" "${sampled_argv[@]}" \
    > "$case_dir/perf-record.jsonl" 2> "$case_dir/perf-record.stderr.txt"
  perf report --stdio --input "$case_dir/perf.data" --sort symbol \
    --percent-limit 0.01 > "$case_dir/perf-report-symbol.txt"
  perf report --stdio --input "$case_dir/perf.data" --sort dso,symbol \
    --percent-limit 0.01 > "$case_dir/perf-report-dso-symbol.txt"
  perf annotate --stdio --input "$case_dir/perf.data" \
    ggml_gemm_q4_K_8x8_q8_K > "$case_dir/annotate-gemm-q4_K-8x8.txt" 2>&1 || true
  perf annotate --stdio --input "$case_dir/perf.data" \
    ggml_gemv_q4_K_8x8_q8_K > "$case_dir/annotate-gemv-q4_K-8x8.txt" 2>&1 || true
  perf annotate --stdio --input "$case_dir/perf.data" \
    ggml_quantize_mat_q8_K_4x8_generic > "$case_dir/annotate-quantize-mat-q8_K-4x8.txt" 2>&1 || true
done < <(jq -r '.benchmark.cases[] | [.name, .prompt_tokens, .generation_tokens] | @tsv' "$contract")

python3 - "$contract" "$evidence" <<'PY'
import json
import pathlib
import re
import sys

contract = json.loads(pathlib.Path(sys.argv[1]).read_text())
root = pathlib.Path(sys.argv[2])
symbols = [
    "ggml_gemm_q4_K_8x8_q8_K",
    "ggml_gemv_q4_K_8x8_q8_K",
    "ggml_quantize_mat_q8_K_4x8_generic",
    "quantize_row_q8_K_ref",
]
summary = {"schema_version": 1, "experiment_id": "E23a", "cases": {}}
for case in contract["benchmark"]["cases"]:
    name = case["name"]
    case_dir = root / "profile" / name
    control = [json.loads(line) for line in (case_dir / "control.jsonl").read_text().splitlines() if line.strip()]
    report = (case_dir / "perf-report-symbol.txt").read_text()
    shares = {}
    for symbol in symbols:
        matches = re.findall(r"^\s*([0-9.]+)%.*\b" + re.escape(symbol) + r"(?:\b|$)", report, re.MULTILINE)
        shares[symbol] = sum(float(value) for value in matches) / 100.0
    summary["cases"][name] = {
        "control": control,
        "sample_share": shares,
        "real_inference_execution": {symbol: shares[symbol] > 0 for symbol in symbols},
    }
(root / "results" / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY

find "$evidence" -type f ! -name file-inventory-sha256.txt -print0 \
  | sort -z | xargs -0 sha256sum > "$evidence/file-inventory-sha256.txt"
jq . "$evidence/results/summary.json"
