#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
    echo "usage: $0 CONTRACT EVIDENCE WORK_ROOT" >&2
    exit 2
fi

contract=$(realpath "$1")
evidence=$(realpath -m "$2")
work_root=$(realpath -m "$3")
repo_root=$(dirname "$(dirname "$contract")")
source_dir="$work_root/llama.cpp"
build_dir="$work_root/build"
model_dir="$work_root/models"

test "$(uname -m)" = aarch64
test "$(jq -r '.experiment_id' "$contract")" = E24a
test ! -e "$evidence"
test ! -e "$work_root"

sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential cmake curl git jq linux-tools-common linux-tools-generic \
    ninja-build ripgrep time
sudo sysctl -w kernel.perf_event_paranoid=1

mkdir -p "$evidence/build" "$evidence/host" "$evidence/model" \
    "$evidence/profile/tg128" "$evidence/profile/live" \
    "$evidence/results" "$evidence/source" "$model_dir"
cp "$contract" "$evidence/contract.json"
cp "$repo_root/experiments/e24_decode_prompt.txt" "$evidence/source/live-prompt.txt"
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
        > "$evidence/host/metadata-$field.txt"
done
test "$(nproc)" = "$(jq -r '.host.logical_cpus' "$contract")"
test "$(cat "$evidence/host/metadata-preempted.txt")" = FALSE
test "$(cat "$evidence/host/metadata-maintenance-event.txt")" = NONE
grep -q 'Neoverse-V2' "$evidence/host/lscpu.txt"
grep -q '^armv8_pmuv3' < <(find /sys/bus/event_source/devices -maxdepth 1 -mindepth 1 -printf '%f\n')

repository=$(jq -r '.source.repository' "$contract")
commit=$(jq -r '.source.commit' "$contract")
tag=$(jq -r '.source.tag' "$contract")
git clone --filter=blob:none "$repository" "$source_dir"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
test "$(git -C "$source_dir" describe --tags --exact-match)" = "$tag"
git -C "$source_dir" ls-remote origin refs/heads/master \
    > "$evidence/source/current-upstream-master.txt"

while IFS= read -r patch_file; do
    git -C "$source_dir" apply --check "$repo_root/$patch_file"
    git -C "$source_dir" apply "$repo_root/$patch_file"
done < <(jq -r '.source.patches[]' "$contract")
git -C "$source_dir" diff --check
git -C "$source_dir" diff --binary --full-index HEAD -- \
    > "$evidence/source/e23-baseline.patch"
git -C "$source_dir" diff --name-only HEAD | sort \
    > "$evidence/source/e23-patched-files.txt"
rg -n 'ggml_gemv_q[456]_K_8x8_q8_K|gemv<block_q[456]_K' \
    "$source_dir/ggml/src/ggml-cpu/arch/arm/repack.cpp" \
    "$source_dir/ggml/src/ggml-cpu/repack.cpp" \
    > "$evidence/source/decode-dispatch-lines.txt"
rg -n 'KAI.*Q4_K|Q4_K|q4_K' "$source_dir/ggml/src/ggml-cpu/kleidiai" \
    > "$evidence/source/kleidiai-q4-k-audit.txt" || true

mapfile -t cmake_args < <(jq -r '.build.cmake_arguments[]' "$contract")
cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "${cmake_args[@]}" \
    2>&1 | tee "$evidence/build/configure.log"
grep -q 'Using KleidiAI optimized kernels if applicable' "$evidence/build/configure.log"
grep -q 'ARM detected' "$evidence/build/configure.log"
cp "$build_dir/CMakeCache.txt" "$evidence/build/CMakeCache.txt"
/usr/bin/time --verbose --output "$evidence/build/build-time.log" \
    cmake --build "$build_dir" --target llama-bench llama-completion --parallel "$(nproc)" \
    2>&1 | tee "$evidence/build/build.log"
ninja -C "$build_dir" -t commands > "$evidence/build/build-commands.txt"
cp "$build_dir/compile_commands.json" "$evidence/build/compile-commands.json"

bench="$build_dir/bin/llama-bench"
completion="$build_dir/bin/llama-completion"
cpu_lib="$build_dir/bin/libggml-cpu.so"
"$bench" --help > "$evidence/build/bench-help.txt" 2>&1
"$completion" --help > "$evidence/build/completion-help.txt" 2>&1
sha256sum "$bench" "$completion" "$cpu_lib" > "$evidence/build/binary-sha256.txt"
file "$bench" "$completion" "$cpu_lib" > "$evidence/build/binary-file.txt"
nm -S --defined-only --demangle "$cpu_lib" > "$evidence/build/cpu-library-symbols.txt"
while IFS= read -r symbol; do
    objdump --disassemble="$symbol" "$cpu_lib" \
        > "$evidence/build/$symbol.asm.txt" 2>&1 || true
done < <(jq -r '.profile.tracked_symbols[]' "$contract")

model_repository=$(jq -r '.model.repository' "$contract")
model_revision=$(jq -r '.model.revision' "$contract")
model_entrypoint=$(jq -r '.model.entrypoint' "$contract")
model="$model_dir/$model_entrypoint"
curl --fail --location --retry 5 --retry-all-errors \
    --output "$model" \
    "https://huggingface.co/$model_repository/resolve/$model_revision/$model_entrypoint?download=true"
test "$(stat --format='%s' "$model")" = "$(jq -r '.model.size_bytes' "$contract")"
echo "$(jq -r '.model.sha256' "$contract")  $model" | sha256sum --check --strict
sha256sum "$model" > "$evidence/model/model-sha256.txt"

core_set=$(jq -r '.host.benchmark_core_set' "$contract")
sample_period=$(jq -r '.profile.perf_sample_period' "$contract")
mapfile -t common_args < <(jq -r '.profile.common_benchmark_arguments[]' "$contract")
tg_repetitions=$(jq -r '.profile.tg128.repetitions' "$contract")
tg_prompt=$(jq -r '.profile.tg128.prompt_tokens' "$contract")
tg_generation=$(jq -r '.profile.tg128.generation_tokens' "$contract")
stat_events=$(jq -r '.profile.perf_stat_events | join(",")' "$contract")

tg_argv=("$bench" --model "$model" "${common_args[@]}" \
    --repetitions "$tg_repetitions" --n-prompt "$tg_prompt" --n-gen "$tg_generation")
printf '%q ' taskset -c "$core_set" "${tg_argv[@]}" > "$evidence/profile/tg128/command.txt"
printf '\n' >> "$evidence/profile/tg128/command.txt"
/usr/bin/time --verbose --output "$evidence/profile/tg128/control-time.txt" \
    taskset -c "$core_set" "${tg_argv[@]}" \
    > "$evidence/profile/tg128/control.jsonl" 2> "$evidence/profile/tg128/control.stderr.txt"
perf stat --no-big-num -x, -e "$stat_events" \
    --output "$evidence/profile/tg128/perf-stat.csv" -- \
    taskset -c "$core_set" "${tg_argv[@]}" \
    > "$evidence/profile/tg128/perf-stat.jsonl" 2> "$evidence/profile/tg128/perf-stat.stderr.txt"
perf record -e cpu_cycles:u -c "$sample_period" \
    --output "$evidence/profile/tg128/perf.data" -- \
    taskset -c "$core_set" "${tg_argv[@]}" \
    > "$evidence/profile/tg128/perf-record.jsonl" 2> "$evidence/profile/tg128/perf-record.stderr.txt"

live_generation=$(jq -r '.profile.live.generation_tokens' "$contract")
live_seed=$(jq -r '.profile.live.seed' "$contract")
live_temperature=$(jq -r '.profile.live.temperature' "$contract")
live_context=$(jq -r '.profile.live.context_tokens' "$contract")
live_prompt="$repo_root/experiments/e24_decode_prompt.txt"
live_argv=("$completion" -m "$model" -f "$live_prompt" -n "$live_generation" \
    --seed "$live_seed" --temp "$live_temperature" -t 4 -c "$live_context" \
    -b 512 -ub 512 --no-warmup --no-display-prompt --no-conversation)
printf '%q ' taskset -c "$core_set" "${live_argv[@]}" > "$evidence/profile/live/command.txt"
printf '\n' >> "$evidence/profile/live/command.txt"
/usr/bin/time --verbose --output "$evidence/profile/live/control-time.txt" \
    taskset -c "$core_set" "${live_argv[@]}" \
    > "$evidence/profile/live/control.stdout" 2> "$evidence/profile/live/control.stderr.txt"
perf stat --no-big-num -x, -e "$stat_events" \
    --output "$evidence/profile/live/perf-stat.csv" -- \
    taskset -c "$core_set" "${live_argv[@]}" \
    > "$evidence/profile/live/perf-stat.stdout" 2> "$evidence/profile/live/perf-stat.stderr.txt"
perf record -e cpu_cycles:u -c "$sample_period" \
    --output "$evidence/profile/live/perf.data" -- \
    taskset -c "$core_set" "${live_argv[@]}" \
    > "$evidence/profile/live/perf-record.stdout" 2> "$evidence/profile/live/perf-record.stderr.txt"

for case_name in tg128 live; do
    case_dir="$evidence/profile/$case_name"
    perf report --stdio --no-children --input "$case_dir/perf.data" --sort symbol \
        --percent-limit 0.01 > "$case_dir/perf-report-symbol.txt"
    perf report --stdio --no-children --input "$case_dir/perf.data" --sort dso,symbol \
        --percent-limit 0.01 > "$case_dir/perf-report-dso-symbol.txt"
    while IFS= read -r symbol; do
        perf annotate --stdio --input "$case_dir/perf.data" "$symbol" \
            > "$case_dir/annotate-$symbol.txt" 2>&1 || true
    done < <(jq -r '.profile.tracked_symbols[]' "$contract")
done

python3 - "$contract" "$evidence" <<'PY'
import json
import pathlib
import re
import sys

contract = json.loads(pathlib.Path(sys.argv[1]).read_text())
root = pathlib.Path(sys.argv[2])
symbols = contract["profile"]["tracked_symbols"]
summary = {"schema_version": 1, "experiment_id": "E24a", "cases": {}}
for case_name in ("tg128", "live"):
    case_dir = root / "profile" / case_name
    report = (case_dir / "perf-report-symbol.txt").read_text()
    shares = {}
    for symbol in symbols:
        pattern = r"^\s*([0-9.]+)%.*(?:\b|\.)" + re.escape(symbol) + r"(?:\b|$)"
        shares[symbol] = sum(float(value) for value in re.findall(pattern, report, re.MULTILINE)) / 100.0
    summary["cases"][case_name] = {
        "exclusive_cpu_cycle_sample_share": shares,
        "real_inference_execution": {symbol: share > 0 for symbol, share in shares.items()},
        "perfect_kernel_whole_model_speedup_ceiling": {
            symbol: (1.0 / (1.0 - share) if share < 1.0 else None)
            for symbol, share in shares.items()
        },
    }
(root / "results" / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY

find "$evidence" -type f ! -name file-inventory-sha256.txt -print0 \
    | sort -z | xargs -0 sha256sum > "$evidence/file-inventory-sha256.txt"
jq . "$evidence/results/summary.json"
