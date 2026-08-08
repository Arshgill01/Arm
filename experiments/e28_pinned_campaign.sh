#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 OUTPUT_DIR [prepare|benchmark|demo-profile|all]" >&2
    exit 2
fi

output_dir=$(realpath -m "$1")
stage=${2:-all}
case "$stage" in
    prepare|benchmark|demo-profile|all) ;;
    *) echo "invalid stage: $stage" >&2; exit 2 ;;
esac

if [[ "$(uname -m)" != "aarch64" || "$(nproc)" -lt 4 ]]; then
    echo "E28 requires an aarch64 host with at least four logical CPUs" >&2
    exit 2
fi
for command in cmake c++ curl gdb git jq ninja nm objdump perf python3 realpath sha256sum taskset /usr/bin/time; do
    command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 2; }
done

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
contract="$repo_root/experiments/e28_contract.json"
work_dir=${E28_WORK_DIR:-/var/tmp/e28-pinned-work}
source_repo="$work_dir/llama.cpp"
source_root="$work_dir/sources"
build_root="$work_dir/builds"
model_dir="$work_dir/model"
tool_dir="$work_dir/tools"
model_key=${E28_MODEL_KEY:-primary}
case "$model_key" in
    primary|portability) ;;
    *) echo "invalid E28_MODEL_KEY: $model_key" >&2; exit 2 ;;
esac
model="$model_dir/$(jq -r ".models.$model_key.filename" "$contract")"
commit=$(jq -r '.source.pinned_baseline_commit' "$contract")
repository=$(jq -r '.source.repository' "$contract")
marker_dir="$output_dir/stages"

mkdir -p "$output_dir" "$marker_dir" "$work_dir" "$source_root" "$build_root" "$model_dir" "$tool_dir"

record_host() {
    mkdir -p "$output_dir/host" "$output_dir/source" "$output_dir/experiments"
    cp "$contract" "$output_dir/contract.json"
    cp "$repo_root/experiments/e3_tasks.json" "$output_dir/experiments/e3_tasks.json"
    date --utc --iso-8601=seconds > "$output_dir/captured-at.txt"
    uname -a > "$output_dir/host/uname.txt"
    lscpu > "$output_dir/host/lscpu.txt"
    lscpu --extended > "$output_dir/host/lscpu-extended.txt"
    cat /proc/cpuinfo > "$output_dir/host/cpuinfo.txt"
    cat /proc/meminfo > "$output_dir/host/meminfo.txt"
    c++ --version > "$output_dir/host/cxx-version.txt"
    cmake --version > "$output_dir/host/cmake-version.txt"
    perf --version > "$output_dir/host/perf-version.txt"
    cat /proc/sys/kernel/perf_event_paranoid > "$output_dir/host/perf-event-paranoid.txt"
    if [[ -r /proc/sys/abi/sve_default_vector_length ]]; then
        cat /proc/sys/abi/sve_default_vector_length > "$output_dir/host/sve-default-vector-length.txt"
    fi
    if curl --fail --silent --connect-timeout 2 \
        --header "Metadata-Flavor: Google" \
        http://metadata.google.internal/computeMetadata/v1/instance/id \
        > "$output_dir/host/metadata-id.txt"; then
        for field in machine-type zone preempted maintenance-event image; do
            curl --fail --silent --header "Metadata-Flavor: Google" \
                "http://metadata.google.internal/computeMetadata/v1/instance/$field" \
                > "$output_dir/host/metadata-$field.txt"
        done
        test "$(cat "$output_dir/host/metadata-preempted.txt")" = "FALSE"
        test "$(cat "$output_dir/host/metadata-maintenance-event.txt")" = "NONE"
    fi
    if [[ "$model_key" = portability ]]; then
        grep -q "Neoverse-N2" "$output_dir/host/lscpu.txt"
    else
        grep -q "Neoverse-V2" "$output_dir/host/lscpu.txt"
    fi
    grep -q "13.3.0" "$output_dir/host/cxx-version.txt"
    for flag in asimd asimddp i8mm sve sve2 svei8mm; do
        grep '^Flags:' "$output_dir/host/lscpu.txt" | grep -qw "$flag"
    done
}

verify_inputs() {
    python3 - "$repo_root" "$contract" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
contract = json.loads(pathlib.Path(sys.argv[2]).read_text())
items = contract["source"]["pinned_baseline_series"]
items += list(contract["source"]["mechanism_patches"].values())
for item in items:
    path = root / item["path"]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != item["sha256"]:
        raise SystemExit(f"SHA-256 mismatch for {path}: {actual}")
PY
    jq -e '.performance.processes_per_variant_per_case == 6' "$contract" >/dev/null
}

prepare_sources_and_builds() {
    mkdir -p "$output_dir/source"
    if [[ ! -d "$source_repo/.git" ]]; then
        git clone --filter=blob:none "$repository" "$source_repo" \
            > "$output_dir/source/clone.stdout" 2> "$output_dir/source/clone.stderr"
    fi
    git -C "$source_repo" fetch origin "$commit"
    test "$(git -C "$source_repo" rev-parse "$commit")" = "$commit"
    git -C "$source_repo" ls-remote origin refs/heads/master \
        > "$output_dir/source/upstream-master-at-run.txt"

    mapfile -t baseline_patches < <(jq -r '.source.pinned_baseline_series[].path' "$contract")
    e25_patch=$(jq -r '.source.mechanism_patches.e25.path' "$contract")
    e27_patch=$(jq -r '.source.mechanism_patches.e27.path' "$contract")

    for variant in A B C D; do
        source_dir="$source_root/$variant"
        build_dir="$build_root/$variant"
        if [[ ! -e "$source_dir/.git" ]]; then
            git -C "$source_repo" worktree add --detach "$source_dir" "$commit"
        fi
        test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
        test -z "$(git -C "$source_dir" status --porcelain)"

        patch_list=("${baseline_patches[@]}")
        if [[ "$variant" = B || "$variant" = D ]]; then patch_list+=("$e25_patch"); fi
        if [[ "$variant" = C || "$variant" = D ]]; then patch_list+=("$e27_patch"); fi
        : > "$output_dir/source/$variant-patches.txt"
        for relative_patch in "${patch_list[@]}"; do
            patch="$repo_root/$relative_patch"
            git -C "$source_dir" apply --check "$patch"
            git -C "$source_dir" apply "$patch"
            sha256sum "$patch" >> "$output_dir/source/$variant-patches.txt"
        done
        git -C "$source_dir" diff --check
        git -C "$source_dir" diff --binary --full-index > "$output_dir/source/$variant.patch"
        git -C "$source_dir" diff --name-only > "$output_dir/source/$variant-files.txt"

        cmake -S "$source_dir" -B "$build_dir" -G Ninja \
            -DBUILD_SHARED_LIBS=ON \
            -DCMAKE_BUILD_TYPE=Release \
            '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
            '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
            -DGGML_CPU_KLEIDIAI=ON \
            -DGGML_OPENMP=ON \
            -DGGML_LTO=OFF \
            -DGGML_NATIVE=ON \
            -DLLAMA_BUILD_EXAMPLES=ON \
            -DLLAMA_BUILD_SERVER=ON \
            -DLLAMA_BUILD_TESTS=OFF \
            -DLLAMA_CURL=OFF \
            -DLLAMA_OPENSSL=OFF \
            2>&1 | tee "$output_dir/source/$variant-configure.log"
        cmake --build "$build_dir" --parallel "$(nproc)" \
            --target llama-bench llama-completion llama-server llama-perplexity \
            2>&1 | tee "$output_dir/source/$variant-build.log"
        ninja -C "$build_dir" -t commands > "$output_dir/source/$variant-build-commands.txt"
        sha256sum "$build_dir/bin/llama-bench" "$build_dir/bin/llama-completion" \
            "$build_dir/bin/llama-server" "$build_dir/bin/llama-perplexity" \
            "$build_dir/bin/libggml-cpu.so"* > "$output_dir/source/$variant-binary-sha256.txt"
        nm -C "$build_dir/bin/libggml-cpu.so" > "$output_dir/source/$variant-symbols.txt"
    done
}

prepare_model() {
    if [[ ! -f "$model" ]]; then
        if [[ -n "${MODEL_PATH:-}" ]]; then
            cp --reflink=auto "$MODEL_PATH" "$model"
        else
            model_repo=$(jq -r ".models.$model_key.repository" "$contract")
            model_revision=$(jq -r ".models.$model_key.revision" "$contract")
            model_filename=$(jq -r ".models.$model_key.filename" "$contract")
            curl --fail --location --retry 5 --retry-all-errors \
                --output "$model" \
                "https://huggingface.co/$model_repo/resolve/$model_revision/$model_filename?download=true"
        fi
    fi
    test "$(stat --format='%s' "$model")" = "$(jq -r ".models.$model_key.size_bytes" "$contract")"
    echo "$(jq -r ".models.$model_key.sha256" "$contract")  $model" | sha256sum --check --strict
    sha256sum "$model" > "$output_dir/source/model-sha256.txt"
    python3 "$repo_root/experiments/e28_sidecar_bytes.py" "$model" \
        "$output_dir/source/e25-decoded-sidecar-bytes.json" \
        --model-sha256 "$(jq -r ".models.$model_key.sha256" "$contract")"
}

compile_harnesses() {
    source_dir="$source_root/D"
    build_dir="$build_root/D"
    compile=(
        c++ -O3 -std=c++17 -march=native
        -I"$source_dir/ggml/include"
        -I"$source_dir/ggml/src"
        -I"$source_dir/ggml/src/ggml-cpu"
        -L"$build_dir/bin" "-Wl,-rpath,$build_dir/bin"
    )
    if [[ "${E28_CURRENT_Q8_LAYOUT:-0}" = 1 ]]; then
        compile+=(-DE28_Q4_GEMM_Q8_4X4)
    fi
    libraries=(-lggml-cpu -lggml-base -lggml -fopenmp)
    "${compile[@]}" "$repo_root/experiments/e24_gemv_correctness.cpp" \
        -o "$tool_dir/e28-q4-gemv-correctness" "${libraries[@]}"
    "${compile[@]}" "$repo_root/experiments/e25_q4_gemm_correctness.cpp" \
        -o "$tool_dir/e28-q4-gemm-correctness" "${libraries[@]}"
    "${compile[@]}" "$repo_root/experiments/e24_q6_gemv_correctness.cpp" \
        -o "$tool_dir/e28-q6-gemv-correctness" "${libraries[@]}"
    "${compile[@]}" "$repo_root/experiments/e25_q4_layout_bench.cpp" \
        -o "$tool_dir/e28-q4-decoded-correctness" "${libraries[@]}"
    "${compile[@]}" "$repo_root/experiments/e27_flash_attn_harness.cpp" \
        -o "$tool_dir/e28-flash-attn" "${libraries[@]}"
}

run_correctness() {
    test ! -e "$output_dir/correctness"
    mkdir -p "$output_dir/correctness"
    LD_LIBRARY_PATH="$build_root/D/bin" taskset -c 0 \
        "$tool_dir/e28-q4-gemv-correctness" > "$output_dir/correctness/q4-gemv.txt"
    LD_LIBRARY_PATH="$build_root/D/bin" taskset -c 0 \
        "$tool_dir/e28-q4-gemm-correctness" > "$output_dir/correctness/q4-gemm.txt"
    LD_LIBRARY_PATH="$build_root/D/bin" taskset -c 0 \
        "$tool_dir/e28-q6-gemv-correctness" > "$output_dir/correctness/q6-gemv.txt"
    LD_LIBRARY_PATH="$build_root/D/bin" taskset -c 0 \
        "$tool_dir/e28-q4-decoded-correctness" 3072 2304 3 \
        > "$output_dir/correctness/q4-decoded-3072x2304.txt"
    LD_LIBRARY_PATH="$build_root/D/bin" taskset -c 0 \
        "$tool_dir/e28-q4-decoded-correctness" 9216 768 3 \
        > "$output_dir/correctness/q4-decoded-9216x768.txt"

    for spec in q512-kv512:512 q512-kv2048:2048 q512-kv4096:4096; do
        IFS=: read -r tag kv_tokens <<< "$spec"
        for seed in 1 17 42; do
            LD_LIBRARY_PATH="$build_root/D/bin" taskset -c 0-3 \
                "$tool_dir/e28-flash-attn" --mode compare \
                --head-size 128 --query-tokens 512 --kv-tokens "$kv_tokens" \
                --query-heads 24 --kv-heads 8 --threads 4 --repetitions 1 \
                --seed "$seed" --kv-type f16 \
                >> "$output_dir/correctness/flash-$tag.jsonl"
        done
    done
    jq -e -s 'length == 9 and all(.[]; .pass == true and .nmse <= 0.0005)' \
        "$output_dir/correctness"/flash-*.jsonl >/dev/null
}

make_long_prompt() {
    mkdir -p "$output_dir/semantic"
    python3 - "$output_dir/semantic/prompt.txt" <<'PY'
import pathlib
import sys
paragraph = (
    "Arm CPU inference benefits from careful data movement, predictable tiling, and measured vector kernels. "
    "This fixed paragraph forms one deterministic long request for a time-to-first-token comparison. "
)
pathlib.Path(sys.argv[1]).write_text(
    paragraph * 220 + "\nSummarize the engineering priorities in one sentence.\n"
)
PY
}

run_semantic_pairs() {
    test ! -e "$output_dir/semantic/complete"
    make_long_prompt
    for variant in A B C D; do
        bin_dir="$build_root/$variant/bin"
        command=(
            env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3
            "$bin_dir/llama-completion" -m "$model"
            -f "$output_dir/semantic/prompt.txt" -n 8 --seed 42 --temp 0
            -t 4 -c 8192 -b 1024 -ub 512 --no-warmup
            --no-display-prompt --no-conversation
        )
        printf '%q ' "${command[@]}" > "$output_dir/semantic/$variant-command.txt"
        printf '\n' >> "$output_dir/semantic/$variant-command.txt"
        "${command[@]}" > "$output_dir/semantic/$variant.stdout" \
            2> "$output_dir/semantic/$variant.stderr"
    done
    cmp "$output_dir/semantic/A.stdout" "$output_dir/semantic/C.stdout"
    cmp "$output_dir/semantic/B.stdout" "$output_dir/semantic/D.stdout"
    diff -u "$output_dir/semantic/A.stdout" "$output_dir/semantic/C.stdout" \
        > "$output_dir/semantic/A-C.diff"
    diff -u "$output_dir/semantic/B.stdout" "$output_dir/semantic/D.stdout" \
        > "$output_dir/semantic/B-D.diff"
    sha256sum "$output_dir/semantic"/*.stdout > "$output_dir/semantic/output-sha256.txt"
    touch "$output_dir/semantic/complete"
}

run_dispatch_proof() {
    test ! -e "$output_dir/dispatch"
    mkdir -p "$output_dir/dispatch"
    bin_dir="$build_root/D/bin"
    common_args=(
        --model "$model" --threads 4 --n-gpu-layers 0 --flash-attn on
        --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl
        --repetitions 1 --n-prompt 0 --n-gen 8
    )
    for item in \
        "e24:ggml_gemv_q6_K_8x8_q8_K" \
        "e25:ggml_gemv_q4_K_8x4_q8_K_decoded"; do
        IFS=: read -r tag symbol <<< "$item"
        cat > "$output_dir/dispatch/$tag.gdb" <<EOF
set pagination off
set breakpoint pending on
break $symbol
commands
silent
printf "E28_DISPATCH $tag symbol=$symbol n=%d nc=%d\\n", n, nc
bt 4
quit
end
run
EOF
        env LD_LIBRARY_PATH="$bin_dir" taskset -c 0-3 \
            gdb --batch --command "$output_dir/dispatch/$tag.gdb" \
            --args "$bin_dir/llama-bench" "${common_args[@]}" \
            > "$output_dir/dispatch/$tag.txt" 2>&1
        grep -q "E28_DISPATCH $tag" "$output_dir/dispatch/$tag.txt"
    done

    perf record -e cpu_cycles:u -c 100000 \
        --output "$output_dir/dispatch/e27-perf.data" -- \
        env LD_LIBRARY_PATH="$bin_dir" taskset -c 0-3 "$bin_dir/llama-bench" \
        --model "$model" --threads 4 --n-gpu-layers 0 --flash-attn on \
        --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl \
        --repetitions 1 --n-prompt 512 --n-gen 0 \
        > "$output_dir/dispatch/e27-perf.jsonl" \
        2> "$output_dir/dispatch/e27-perf.stderr"
    perf report --stdio --no-children --input "$output_dir/dispatch/e27-perf.data" \
        --sort symbol --percent-limit 0.01 > "$output_dir/dispatch/e27-symbols.txt"
    perf annotate --stdio --input "$output_dir/dispatch/e27-perf.data" \
        'ggml_compute_forward_flash_attn_ext_tiled(ggml_compute_params const*, ggml_tensor*, int, int)' \
        > "$output_dir/dispatch/e27-annotate.txt"
    objdump -d -C "$bin_dir/libggml-cpu.so" > "$output_dir/dispatch/D-assembly.txt"
    grep -E 'fmla[[:space:]].*v[0-9]+\.4s' "$output_dir/dispatch/e27-annotate.txt" \
        > "$output_dir/dispatch/e27-neon-fmla.txt"
    test -s "$output_dir/dispatch/e27-neon-fmla.txt"
}

stop_server() {
    local timer_pid=$1
    local server_pid
    server_pid=$(pgrep -P "$timer_pid" -x llama-server || true)
    if [[ -n "$server_pid" ]]; then
        kill -INT "$server_pid" 2>/dev/null || true
    fi
    set +e
    wait "$timer_pid"
    local status=$?
    set -e
    [[ "$status" -eq 0 || "$status" -eq 130 || "$status" -eq 143 ]]
}

run_quality_cell() {
    local variant=$1 repetition=$2
    local cell="$output_dir/quality/$variant/repeat-$repetition"
    local bin_dir="$build_root/$variant/bin"
    local port=$((18080 + repetition))
    mkdir -p "$cell"
    server_argv=(
        "$bin_dir/llama-server" --model "$model" --alias e28-ministral
        --threads 4 --threads-batch 4 --ctx-size 2048
        --cache-type-k f16 --cache-type-v f16 --flash-attn on
        --parallel 1 --cont-batching --host 127.0.0.1 --port "$port"
        --no-webui --metrics --slots --jinja --temp 0.0 --seed 424242
        --log-colors off --batch-size 1024 --ubatch-size 512
    )
    printf '%q ' "${server_argv[@]}" > "$cell/command.txt"
    printf '\n' >> "$cell/command.txt"
    /usr/bin/time --verbose --output "$cell/server.time" \
        env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3 "${server_argv[@]}" \
        > "$cell/server.stdout" 2> "$cell/server.stderr" &
    timer_pid=$!
    trap 'stop_server "$timer_pid" || true' ERR INT TERM
    python3 "$repo_root/experiments/e3d_http_quality.py" wait \
        --url "http://127.0.0.1:$port" --timeout 180 \
        --output "$cell/readiness.json"
    python3 "$repo_root/experiments/e3d_http_quality.py" run \
        --url "http://127.0.0.1:$port" \
        --tasks "$repo_root/experiments/e3_tasks.json" \
        --model e28-ministral --model-path "$model" \
        --load-ms "$(jq -r '.ready_ms' "$cell/readiness.json")" \
        --threads 4 --context 2048 --max-output-tokens 8 \
        --seed 424242 --timeout 180 --instruction-role user_prefix \
        --output "$cell/quality.json"
    stop_server "$timer_pid"
    trap - ERR INT TERM
}

run_quality_and_perplexity() {
    test ! -e "$output_dir/quality"
    mkdir -p "$output_dir/quality" "$output_dir/perplexity"
    for variant in A B C D; do run_quality_cell "$variant" 1; done
    for variant in D C B A; do run_quality_cell "$variant" 2; done

    for repetition in 1 2; do
        order=(A B C D)
        if [[ "$repetition" -eq 2 ]]; then order=(D C B A); fi
        for variant in "${order[@]}"; do
            bin_dir="$build_root/$variant/bin"
            /usr/bin/time --verbose \
                --output "$output_dir/perplexity/$variant-$repetition.time" \
                env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3 \
                "$bin_dir/llama-perplexity" -m "$model" \
                -f "$repo_root/experiments/e3_tasks.json" \
                -t 4 -c 2048 -b 512 -ub 512 --flash-attn on \
                > "$output_dir/perplexity/$variant-$repetition.stdout" \
                2> "$output_dir/perplexity/$variant-$repetition.stderr"
        done
    done
}

run_bench_cell() {
    local variant=$1 case_name=$2 prompt_tokens=$3 generated_tokens=$4 run=$5
    local bin_dir="$build_root/$variant/bin"
    local cell="$output_dir/inference/$case_name/$run-$variant"
    mkdir -p "$(dirname "$cell")"
    command=(
        env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3 "$bin_dir/llama-bench"
        --model "$model" --threads 4 --n-gpu-layers 0 --flash-attn on
        --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl
        --repetitions 3 --n-prompt "$prompt_tokens" --n-gen "$generated_tokens"
    )
    printf '%q ' "${command[@]}" > "$cell.command.txt"
    printf '\n' >> "$cell.command.txt"
    /usr/bin/time --verbose --output "$cell.time" "${command[@]}" \
        > "$cell.jsonl" 2> "$cell.stderr"
}

run_benchmarks() {
    test -f "$marker_dir/prepare.complete"
    test ! -e "$output_dir/inference"
    mkdir -p "$output_dir/inference"
    for spec in pp512:512:0 pp2048:2048:0 pp4096:4096:0 tg128:0:128; do
        IFS=: read -r case_name prompt_tokens generated_tokens <<< "$spec"
        for round in 1 2 3; do
            position=0
            for variant in A B C D D C B A; do
                position=$((position + 1))
                run_bench_cell "$variant" "$case_name" "$prompt_tokens" \
                    "$generated_tokens" "r$round-p$position"
            done
        done
    done
}

run_demo() {
    test -f "$marker_dir/prepare.complete"
    test ! -e "$output_dir/demo"
    mkdir -p "$output_dir/demo"
    cp "$output_dir/semantic/prompt.txt" "$output_dir/demo/prompt.txt"
    for variant in A B C D; do
        bin_dir="$build_root/$variant/bin"
        command=(
            env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3
            "$bin_dir/llama-completion" -m "$model"
            -f "$output_dir/demo/prompt.txt" -n 1 --seed 42 --temp 0
            -t 4 -c 8192 -b 1024 -ub 512 --no-warmup
            --no-display-prompt --no-conversation
        )
        printf '%q ' "${command[@]}" > "$output_dir/demo/$variant-command.txt"
        printf '\n' >> "$output_dir/demo/$variant-command.txt"
        /usr/bin/time --verbose --output "$output_dir/demo/$variant.time" \
            "${command[@]}" > "$output_dir/demo/$variant.stdout" \
            2> "$output_dir/demo/$variant.stderr"
    done
    cmp "$output_dir/demo/A.stdout" "$output_dir/demo/C.stdout"
    cmp "$output_dir/demo/B.stdout" "$output_dir/demo/D.stdout"
    sha256sum "$output_dir/demo"/*.stdout > "$output_dir/demo/output-sha256.txt"
}

run_profiles() {
    test ! -e "$output_dir/profile"
    bin_dir="$build_root/D/bin"
    mkdir -p "$output_dir/profile"
    for spec in pp2048:2048:0 tg128:0:128; do
        IFS=: read -r case_name prompt_tokens generated_tokens <<< "$spec"
        cell="$output_dir/profile/$case_name"
        mkdir -p "$cell"
        command=(
            env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3 "$bin_dir/llama-bench"
            --model "$model" --threads 4 --n-gpu-layers 0 --flash-attn on
            --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl
            --repetitions 1 --n-prompt "$prompt_tokens" --n-gen "$generated_tokens"
        )
        printf '%q ' "${command[@]}" > "$cell/command.txt"
        printf '\n' >> "$cell/command.txt"
        perf stat --no-big-num -x, \
            -e cpu_cycles,inst_retired,l1d_cache,l1d_cache_refill,l2d_cache \
            --output "$cell/perf-stat.csv" -- "${command[@]}" \
            > "$cell/perf-stat.jsonl" 2> "$cell/perf-stat.stderr"
        perf record -e cpu_cycles:u -c 100000 --output "$cell/perf.data" -- \
            "${command[@]}" > "$cell/perf-record.jsonl" \
            2> "$cell/perf-record.stderr"
        perf report --stdio --no-children --input "$cell/perf.data" \
            --sort symbol --percent-limit 0.01 > "$cell/perf-report-symbol.txt"
    done
}

finish_inventory() {
    find "$output_dir" -type f \
        ! -name file-inventory-sha256.txt ! -name perf.data -print0 \
        | sort -z | xargs -0 sha256sum > "$output_dir/file-inventory-sha256.txt"
}

if [[ "${E28_LIBRARY_ONLY:-0}" = 1 ]]; then
    return 0
fi

if [[ "$stage" = prepare || "$stage" = all ]]; then
    test ! -e "$marker_dir/prepare.complete"
    record_host
    verify_inputs
    prepare_sources_and_builds
    prepare_model
    compile_harnesses
    run_correctness
    run_semantic_pairs
    run_dispatch_proof
    run_quality_and_perplexity
    touch "$marker_dir/prepare.complete"
    finish_inventory
fi

if [[ "$stage" = benchmark || "$stage" = all ]]; then
    test ! -e "$marker_dir/benchmark.complete"
    prepare_model
    run_benchmarks
    touch "$marker_dir/benchmark.complete"
    finish_inventory
fi

if [[ "$stage" = demo-profile || "$stage" = all ]]; then
    test ! -e "$marker_dir/demo-profile.complete"
    prepare_model
    run_demo
    run_profiles
    python3 "$repo_root/experiments/e28_ingest.py" "$output_dir" \
        "$output_dir/results/summary.json"
    touch "$marker_dir/demo-profile.complete"
    finish_inventory
fi
