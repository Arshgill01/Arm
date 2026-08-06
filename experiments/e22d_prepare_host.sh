#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "usage: e22d_prepare_host.sh EVIDENCE WORK_ROOT" >&2
  exit 2
fi
evidence="$1"
work_root="$2"
contract=experiments/e22d_contract.json
source_dir="$work_root/llama.cpp"
build_dir="$work_root/build"
model_root="$work_root/models"
scratch_root="$work_root/tmp"
sidecar="$work_root/weights.sidecar"
index="$work_root/weights.index.json"
receipt="$evidence/product/sidecar-receipt.json"

test "$(uname -m)" = aarch64
test "$(jq -r '.experiment_id' "$contract")" = \
  E22d-independent-host-density-replication
test ! -e "$evidence"
test ! -e "$work_root"

sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential cmake curl git jq linux-tools-common linux-tools-generic ninja-build \
  time

mkdir -p "$evidence/build" "$evidence/model" "$evidence/product" \
  "$model_root" "$scratch_root"
cp "$contract" "$evidence/contract.json"
git rev-parse HEAD > "$evidence/repository-commit.txt"
cat /proc/sys/kernel/perf_event_paranoid \
  > "$evidence/perf-event-paranoid-before-configuration.txt"
sudo sysctl -w kernel.perf_event_paranoid=1 \
  | tee "$evidence/perf-event-paranoid-configuration.txt" >/dev/null
dpkg-query -W > "$evidence/packages.tsv"
cmake --version > "$evidence/cmake-version.txt"
gcc --version > "$evidence/gcc-version.txt"
ninja --version > "$evidence/ninja-version.txt"
experiments/e22b_host_preflight.sh "$evidence/host-preflight"

repository="$(jq -r '.source.repository' "$contract")"
commit="$(jq -r '.source.commit' "$contract")"
tag="$(jq -r '.source.tag' "$contract")"
git clone --filter=blob:none "$repository" "$source_dir"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
test "$(git -C "$source_dir" describe --tags --exact-match)" = "$tag"
while IFS= read -r patch_file; do
  git -C "$source_dir" apply --check "$PWD/$patch_file"
  git -C "$source_dir" apply "$PWD/$patch_file"
done < <(jq -r '.source.patches[].path' "$contract")
git -C "$source_dir" diff --check
git -C "$source_dir" diff --name-only HEAD | sort \
  > "$evidence/source-patched-files.txt"
diff -u \
  <(jq -r '.source.changed_files[]' "$contract") \
  "$evidence/source-patched-files.txt"
git -C "$source_dir" diff --binary --full-index HEAD -- \
  > "$evidence/source-diff.patch"
echo "$(jq -r '.source.aggregate_diff_sha256' "$contract")  $evidence/source-diff.patch" \
  | sha256sum --check --strict

mapfile -t cmake_args < <(jq -r '.build.cmake_arguments[]' "$contract")
cmake -S "$source_dir" -B "$build_dir" -G Ninja \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "${cmake_args[@]}" \
  2>&1 | tee "$evidence/build/configure.log"
grep -q 'Using KleidiAI optimized kernels if applicable' \
  "$evidence/build/configure.log"
grep -q 'ARM detected' "$evidence/build/configure.log"
cp "$build_dir/CMakeCache.txt" "$evidence/build/CMakeCache.txt"
/usr/bin/time --verbose --output "$evidence/build/build-time.log" \
  cmake --build "$build_dir" --target llama-server --parallel "$(nproc)" \
  2>&1 | tee "$evidence/build/build.log"
ninja -C "$build_dir" -t commands > "$evidence/build/build-commands.txt"
"$build_dir/bin/llama-server" --version \
  2>&1 | tee "$evidence/build/server-version.txt"
python3 experiments/e7a_runtime_closure.py \
  --server "$build_dir/bin/llama-server" \
  --build-root "$build_dir" \
  --copy-dir "$evidence/build/runtime-files" \
  --output "$evidence/build/runtime-closure.json"
if grep -Eq 'lib(ssl|crypto)\.so' "$evidence/build/runtime-closure.json"; then
  exit 1
fi

runtime_archive="$work_root/e22c-runtime-source.tar.gz"
runtime_url="$(jq -r '.source_result.raw_archive_url' "$contract")"
curl --fail --location --retry 5 --retry-all-errors \
  --output "$runtime_archive" "$runtime_url"
test "$(stat --format='%s' "$runtime_archive")" = \
  "$(jq -r '.source_result.raw_archive_size_bytes' "$contract")"
echo "$(jq -r '.source_result.raw_archive_sha256' "$contract")  $runtime_archive" \
  | sha256sum --check --strict
tar --extract --gzip --file "$runtime_archive" --directory "$evidence" \
  --strip-components=1 evidence-e22c/runtime
server="$evidence/runtime/bin/llama-server"
export LD_LIBRARY_PATH="$evidence/runtime/bin"
"$server" --version 2>&1 | tee "$evidence/runtime/server-version-e22d.txt"

candidate="$(jq -r '.selected.candidate' "$contract")"
repository="$(jq -r --arg candidate "$candidate" \
  '.variants[$candidate].repository' experiments/e3f_models.json)"
revision="$(jq -r --arg candidate "$candidate" \
  '.variants[$candidate].revision' experiments/e3f_models.json)"
entrypoint="$(jq -r --arg candidate "$candidate" \
  '.variants[$candidate].entrypoint' experiments/e3f_models.json)"
model="$model_root/$entrypoint"
curl --fail --location --retry 5 --retry-all-errors \
  --output "$model" \
  "https://huggingface.co/$repository/resolve/$revision/$entrypoint?download=true"
test "$(stat --format='%s' "$model")" = \
  "$(jq -r '.selected.model_size_bytes' "$contract")"
echo "$(jq -r '.selected.model_sha256' "$contract")  $model" \
  | sha256sum --check --strict
sha256sum "$model" > "$evidence/model/model-sha256.txt"

python3 -m pareto64 sidecar-prepack \
  --contract experiments/e16c_contract.json \
  --evidence results/manifests/e16c-30851609576.json \
  --model "$model" \
  --llama-server "$server" \
  --sidecar "$sidecar" \
  --index "$index" \
  --receipt "$receipt" \
  --lifecycle-dir "$evidence/product/prepack" \
  --scratch-root "$scratch_root" \
  --port 18081 \
  --readiness-timeout 180
python3 -m pareto64 sidecar-verify \
  --contract experiments/e16c_contract.json \
  --evidence results/manifests/e16c-30851609576.json \
  --model "$model" \
  --llama-server "$server" \
  --sidecar "$sidecar" \
  --index "$index" \
  --receipt "$receipt" \
  --output "$evidence/product/sidecar-verification.json"

jq -n \
  --arg server "$server" \
  --arg model "$model" \
  --arg sidecar "$sidecar" \
  --arg index "$index" \
  --arg receipt "$receipt" \
  '{
    schema_version: 1,
    status: "ready_for_e22d_campaign",
    server: $server,
    model: $model,
    sidecar: $sidecar,
    index: $index,
    sidecar_receipt: $receipt
  }' > "$evidence/preparation-status.json"
jq -c . "$evidence/preparation-status.json"
