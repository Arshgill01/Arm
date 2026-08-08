#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 OUTPUT_DIR" >&2
    exit 2
fi

output_dir=$1
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
contract="$repo_root/experiments/e26_contract.json"
work_dir=$(mktemp -d /var/tmp/e26-rejected-smoke.XXXXXX)
trap 'rm -rf -- "$work_dir"' EXIT
source_dir="$work_dir/llama.cpp"
build_dir="$work_dir/build"
mkdir -p "$output_dir"

repository=$(jq -r '.source.repository' "$contract")
commit=$(jq -r '.source.commit' "$contract")
current_commit=$(jq -r '.source.current_upstream_commit_at_freeze' "$contract")
candidate_patch=$(jq -r '.source.candidate_patch' "$contract")
mapfile -t baseline_patches < <(jq -r '.source.baseline_patches[]' "$contract")

git clone --filter=blob:none "$repository" "$source_dir"
git -C "$source_dir" checkout --detach "$commit"
for patch in "${baseline_patches[@]}" "$candidate_patch"; do
    git -C "$source_dir" apply --check "$repo_root/$patch"
    git -C "$source_dir" apply "$repo_root/$patch"
done
git -C "$source_dir" diff --check

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
    -DGGML_LTO=OFF -DGGML_NATIVE=ON \
    -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF \
    -DLLAMA_BUILD_TESTS=OFF -DLLAMA_CURL=OFF
cmake --build "$build_dir" --target ggml --parallel "$(nproc)"
c++ -O3 -std=c++17 -march=native \
    -I"$source_dir/ggml/include" -I"$source_dir/ggml/src" -I"$source_dir/ggml/src/ggml-cpu" \
    "$repo_root/experiments/e26_tiled_ffn.cpp" -o "$work_dir/e26-tiled-ffn" \
    -L"$build_dir/bin" -Wl,-rpath,"$build_dir/bin" \
    -lggml-cpu -lggml-base -lggml -fopenmp

GGML_CPU_TILED_FFN=0 "$work_dir/e26-tiled-ffn" --n-embd 512 --n-ff 1024 \
    --threads 4 --repetitions 1 --output "$output_dir/reference.bin" > "$output_dir/reference.txt"
GGML_CPU_TILED_FFN=1 "$work_dir/e26-tiled-ffn" --n-embd 512 --n-ff 1024 \
    --threads 4 --repetitions 1 --output "$output_dir/candidate.bin" > "$output_dir/candidate.txt"
python3 "$repo_root/experiments/e26_compare.py" \
    "$output_dir/reference.bin" "$output_dir/candidate.bin" "$output_dir/numerics.json"
GGML_CPU_TILED_FFN=1 "$work_dir/e26-tiled-ffn" --n-embd 512 --n-ff 1024 \
    --threads 4 --repetitions 1 --unsupported-names --output "$output_dir/fallback.bin" \
    > "$output_dir/fallback.txt"
cmp "$output_dir/reference.bin" "$output_dir/fallback.bin"

git -C "$source_dir" reset --hard
git -C "$source_dir" clean -fd
git -C "$source_dir" checkout --detach "$current_commit"
git -C "$source_dir" apply --check "$repo_root/$candidate_patch"
