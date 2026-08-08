#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 OUTPUT_DIR [prepare|benchmark|profile|all]" >&2
    exit 2
fi
requested_output=$1
requested_stage=${2:-all}
case "$requested_stage" in
    prepare|benchmark|profile|all) ;;
    *) echo "invalid stage: $requested_stage" >&2; exit 2 ;;
esac

set -- "$requested_output" prepare
# shellcheck source=e28_pinned_campaign.sh disable=SC1091
E28_LIBRARY_ONLY=1 source "$(dirname "${BASH_SOURCE[0]}")/e28_pinned_campaign.sh"
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
contract="$repo_root/experiments/e28_contract.json"
output_dir=$(realpath -m "$requested_output")
stage=$requested_stage
work_dir=${E28_CURRENT_WORK_DIR:-/var/tmp/e28-current-work}
source_repo="$work_dir/llama.cpp"
source_root="$work_dir/sources"
build_root="$work_dir/builds"
model_dir="$work_dir/model"
tool_dir="$work_dir/tools"
model="$model_dir/$(jq -r '.models.primary.filename' "$contract")"
commit=$(jq -r '.source.current_upstream_commit' "$contract")
repository=$(jq -r '.source.repository' "$contract")
marker_dir="$output_dir/stages"
mkdir -p "$output_dir" "$marker_dir" "$work_dir" "$source_root" "$build_root" "$model_dir" "$tool_dir"

prepare_current_sources_and_builds() {
    mkdir -p "$output_dir/source"
    if [[ ! -d "$source_repo/.git" ]]; then
        git clone --filter=blob:none "$repository" "$source_repo" \
            > "$output_dir/source/clone.stdout" 2> "$output_dir/source/clone.stderr"
    fi
    git -C "$source_repo" fetch origin master
    observed=$(git -C "$source_repo" ls-remote origin refs/heads/master | awk '{print $1}')
    printf '%s\n' "$observed" > "$output_dir/source/upstream-master-at-run.txt"
    test "$observed" = "$commit"

    current_e24=$(jq -r '.source.mechanism_patches.current_e24.path' "$contract")
    current_e25=$(jq -r '.source.mechanism_patches.current_e25.path' "$contract")
    e27=$(jq -r '.source.mechanism_patches.e27.path' "$contract")
    for variant in A D; do
        source_dir="$source_root/$variant"
        build_dir="$build_root/$variant"
        if [[ ! -e "$source_dir/.git" ]]; then
            git -C "$source_repo" worktree add --detach "$source_dir" "$commit"
        fi
        test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
        test -z "$(git -C "$source_dir" status --porcelain)"
        : > "$output_dir/source/$variant-patches.txt"
        if [[ "$variant" = D ]]; then
            for relative_patch in "$current_e24" "$current_e25" "$e27"; do
                patch="$repo_root/$relative_patch"
                git -C "$source_dir" apply --check "$patch"
                git -C "$source_dir" apply "$patch"
                sha256sum "$patch" >> "$output_dir/source/$variant-patches.txt"
            done
        fi
        git -C "$source_dir" diff --check
        git -C "$source_dir" diff --binary --full-index > "$output_dir/source/$variant.patch"
        git -C "$source_dir" diff --name-only > "$output_dir/source/$variant-files.txt"
        cmake -S "$source_dir" -B "$build_dir" -G Ninja \
            -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
            '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
            '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
            -DGGML_CPU_KLEIDIAI=ON -DGGML_OPENMP=ON -DGGML_LTO=OFF \
            -DGGML_NATIVE=ON -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_SERVER=ON \
            -DLLAMA_BUILD_TESTS=OFF -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
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

    old_e23="$repo_root/patches/llama.cpp/b10216/0013-arm-q4-k-neon-vector-scale-kernel.patch"
    git -C "$source_root/A" apply --check "$old_e23"
    {
        echo "The old E23 patch still applies, so its exact source change is not already upstream."
        echo "It modifies ggml_gemm_q4_K_8x8_q8_K, while E25 selects the current"
        echo "ggml_gemm_q4_K_8x4_q8_K path for aligned two-dimensional Q4_K tensors."
        echo "E23 is therefore omitted as superseded in the measured E25 combined path."
    } > "$output_dir/source/e23-audit.txt"
    rg -n 'ggml_gemm_q4_K_8x4_q8_K_decoded|tensor_traits.*q4_K' \
        "$source_root/D/ggml/src/ggml-cpu/repack.cpp" \
        "$source_root/D/ggml/src/ggml-cpu/arch/arm/repack.cpp" \
        >> "$output_dir/source/e23-audit.txt"
}

run_current_e23_dispatch_audit() {
    bin_dir="$build_root/D/bin"
    cat > "$output_dir/dispatch/e23-superseding-prefill.gdb" <<'EOF'
set pagination off
set breakpoint pending on
break ggml_gemm_q4_K_8x4_q8_K
commands
silent
printf "E28_DISPATCH e23-superseded symbol=ggml_gemm_q4_K_8x4_q8_K n=%d nr=%d nc=%d\n", n, nr, nc
bt 4
quit
end
run
EOF
    env LD_LIBRARY_PATH="$bin_dir" taskset -c 0-3 \
        gdb --batch --command "$output_dir/dispatch/e23-superseding-prefill.gdb" \
        --args "$bin_dir/llama-bench" \
        --model "$model" --threads 4 --n-gpu-layers 0 --flash-attn on \
        --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl \
        --repetitions 1 --n-prompt 512 --n-gen 0 \
        > "$output_dir/dispatch/e23-superseding-prefill.txt" 2>&1
    grep -q 'E28_DISPATCH e23-superseded' \
        "$output_dir/dispatch/e23-superseding-prefill.txt"
}

run_current_quality_and_perplexity() {
    test ! -e "$output_dir/quality"
    mkdir -p "$output_dir/quality" "$output_dir/perplexity"
    run_quality_cell A 1
    run_quality_cell D 1
    run_quality_cell D 2
    run_quality_cell A 2
    mv "$output_dir/quality/A" "$output_dir/quality/stock"
    mv "$output_dir/quality/D" "$output_dir/quality/combined"
    for repetition in 1 2; do
        order=(stock combined)
        if [[ "$repetition" -eq 2 ]]; then order=(combined stock); fi
        for label in "${order[@]}"; do
            variant=A
            if [[ "$label" = combined ]]; then variant=D; fi
            bin_dir="$build_root/$variant/bin"
            /usr/bin/time --verbose \
                --output "$output_dir/perplexity/$label-$repetition.time" \
                env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3 \
                "$bin_dir/llama-perplexity" -m "$model" \
                -f "$repo_root/experiments/e3_tasks.json" \
                -t 4 -c 2048 -b 512 -ub 512 --flash-attn on \
                > "$output_dir/perplexity/$label-$repetition.stdout" \
                2> "$output_dir/perplexity/$label-$repetition.stderr"
        done
    done
}

run_current_bench_cell() {
    local variant=$1 label=$2 case_name=$3 prompt_tokens=$4 generated_tokens=$5 run=$6
    local bin_dir="$build_root/$variant/bin"
    local cell="$output_dir/inference/$case_name/$run-$label"
    mkdir -p "$(dirname "$cell")"
    command=(
        env "LD_LIBRARY_PATH=$bin_dir" taskset -c 0-3 "$bin_dir/llama-bench"
        --model "$model" --threads 4 --n-gpu-layers 0 --flash-attn on
        --batch-size 1024 --ubatch-size 512 --no-warmup --output jsonl
        --repetitions 1 --n-prompt "$prompt_tokens" --n-gen "$generated_tokens"
    )
    printf '%q ' "${command[@]}" > "$cell.command.txt"
    printf '\n' >> "$cell.command.txt"
    /usr/bin/time --verbose --output "$cell.time" "${command[@]}" \
        > "$cell.jsonl" 2> "$cell.stderr"
}

run_current_benchmarks() {
    test -f "$marker_dir/prepare.complete"
    test ! -e "$output_dir/inference"
    mkdir -p "$output_dir/inference"
    for spec in pp2048:2048:0 tg128:0:128; do
        IFS=: read -r case_name prompt_tokens generated_tokens <<< "$spec"
        for round in 1 2 3; do
            run_current_bench_cell A stock "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p1"
            run_current_bench_cell D combined "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p2"
            run_current_bench_cell D combined "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p3"
            run_current_bench_cell A stock "$case_name" "$prompt_tokens" "$generated_tokens" "r$round-p4"
        done
    done
}

if [[ "${E28_CURRENT_LIBRARY_ONLY:-0}" = 1 ]]; then
    return 0
fi

if [[ "$stage" = prepare || "$stage" = all ]]; then
    test ! -e "$marker_dir/prepare.complete"
    record_host
    verify_inputs
    prepare_current_sources_and_builds
    prepare_model
    E28_CURRENT_Q8_LAYOUT=1 compile_harnesses
    run_correctness
    run_dispatch_proof
    run_current_e23_dispatch_audit
    run_current_quality_and_perplexity
    touch "$marker_dir/prepare.complete"
    finish_inventory
fi

if [[ "$stage" = benchmark || "$stage" = all ]]; then
    test ! -e "$marker_dir/benchmark.complete"
    prepare_model
    run_current_benchmarks
    touch "$marker_dir/benchmark.complete"
    finish_inventory
fi

if [[ "$stage" = profile || "$stage" = all ]]; then
    test ! -e "$marker_dir/profile.complete"
    prepare_model
    run_profiles
    python3 "$repo_root/experiments/e28_current_ingest.py" "$output_dir" \
        "$output_dir/results/summary.json"
    touch "$marker_dir/profile.complete"
    finish_inventory
fi
