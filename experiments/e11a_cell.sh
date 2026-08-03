#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$EVIDENCE_DIR/build" "$EVIDENCE_DIR/harness" \
  "$EVIDENCE_DIR/patches" "$EVIDENCE_DIR/raw" \
  "$EVIDENCE_DIR/preflight-raw" "$EVIDENCE_DIR/adapter/tasks" \
  "$EVIDENCE_DIR/adapter/patches" "$MODEL_ROOT"
test "$(uname -m)" = "aarch64"
echo "$E11A_CONTRACT_SHA256  $E11A_CONTRACT_PATH" | sha256sum --check --strict
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

for contract_path in (os.environ["E11A_CONTRACT_PATH"], "experiments/e10d_contract.json"):
    contract = json.loads(Path(contract_path).read_text())
    for key, path_value in contract["inputs"].items():
        if key.endswith("_path"):
            expected = contract["inputs"][f"{key[:-5]}_sha256"]
            observed = hashlib.sha256(Path(path_value).read_bytes()).hexdigest()
            if observed != expected:
                raise ValueError(f"frozen input differs: {path_value}")
PY
python3 -m unittest tests.test_e10d tests.test_e11a

cp "$E11A_CONTRACT_PATH" "$EVIDENCE_DIR/contract.json"
cp experiments/e11a_plan.json "$EVIDENCE_DIR/plan.json"
cp experiments/e11a_models.json "$EVIDENCE_DIR/models.json"
cp experiments/e11a_cell.sh "$EVIDENCE_DIR/cell-runner.sh"
cp experiments/e9a_contract.json "$EVIDENCE_DIR/e9a-contract.json"
cp experiments/e10d_sample_map.json "$EVIDENCE_DIR/sample-map.json"
cp experiments/e10d_contract.json "$EVIDENCE_DIR/adapter/contract.json"
cp experiments/e9a_contract.json "$EVIDENCE_DIR/adapter/e9a-contract.json"
cp experiments/e9b_preflight_plan.json "$EVIDENCE_DIR/adapter/e9b-plan.json"
cp experiments/e3f_models.json "$EVIDENCE_DIR/adapter/models-manifest.json"
cp results/manifests/e10b-30797568757.json "$EVIDENCE_DIR/adapter/e10b-manifest.json"
cp results/manifests/e10c-30812791972.json "$EVIDENCE_DIR/adapter/e10c-negative-manifest.json"
cp experiments/e10d_sample_map.json "$EVIDENCE_DIR/adapter/sample-map.json"
cp experiments/e9b_samples.py "$EVIDENCE_DIR/adapter/e9b-samples.py"
cp experiments/e9b_tasks/e9b_arc_easy.yaml "$EVIDENCE_DIR/adapter/tasks/e9b_arc_easy.yaml"
cp experiments/e9b_tasks/e9b_hellaswag.yaml "$EVIDENCE_DIR/adapter/tasks/e9b_hellaswag.yaml"
cp experiments/e9b_tasks/e9b_winogrande.yaml "$EVIDENCE_DIR/adapter/tasks/e9b_winogrande.yaml"
cp experiments/e9b_tasks/e9b_utils.py "$EVIDENCE_DIR/adapter/tasks/e9b_utils.py"
cp experiments/e10d_requirements.txt "$EVIDENCE_DIR/adapter/requirements.txt"
cp patches/llama.cpp/b10216/0004-server-select-exact-token-probabilities.patch \
  "$EVIDENCE_DIR/adapter/patches/0004-server-select-exact-token-probabilities.patch"
uname -a | tee "$EVIDENCE_DIR/uname.txt"
lscpu | tee "$EVIDENCE_DIR/lscpu.txt"
free -h | tee "$EVIDENCE_DIR/memory-before.txt"
df -h | tee "$EVIDENCE_DIR/disk-before.txt"
python3 --version | tee "$EVIDENCE_DIR/python-version.txt"
git rev-parse HEAD | tee "$EVIDENCE_DIR/repository-commit.txt"
jq -n \
  --arg run_id "$GITHUB_RUN_ID" \
  --argjson run_attempt "$GITHUB_RUN_ATTEMPT" \
  --arg sha "$GITHUB_SHA" \
  --arg ref "$GITHUB_REF" \
  --arg runner_os "$RUNNER_OS" \
  --arg runner_arch "$RUNNER_ARCH" \
  '{run_id: $run_id, run_attempt: $run_attempt, sha: $sha, ref: $ref, runner_os: $runner_os, runner_arch: $runner_arch}' \
  > "$EVIDENCE_DIR/github.json"
python3 experiments/e9b_samples.py --output "$EVIDENCE_DIR/generated-sample-map.json"
echo 'c92200f74c83666ee9e381e5edcb5d10bc66d8051ec07e9daa6805eab7632e49  '"$EVIDENCE_DIR"'/generated-sample-map.json' \
  | sha256sum --check --strict
python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["EVIDENCE_DIR"])
generated = json.loads((root / "generated-sample-map.json").read_text())
retained = json.loads((root / "sample-map.json").read_text())
if generated != retained:
    raise ValueError("generated sample map differs from retained sample map")
PY

git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$LLAMA_SOURCE"
git -C "$LLAMA_SOURCE" checkout --detach "$LLAMA_COMMIT"
test "$(git -C "$LLAMA_SOURCE" rev-parse HEAD)" = "$LLAMA_COMMIT"
test "$(git -C "$LLAMA_SOURCE" describe --tags --exact-match)" = b10216
for patch in \
  patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch \
  patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch \
  patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch \
  patches/llama.cpp/b10216/0004-server-select-exact-token-probabilities.patch; do
  cp "$patch" "$EVIDENCE_DIR/patches/$(basename "$patch")"
  git -C "$LLAMA_SOURCE" apply --check "$GITHUB_WORKSPACE/$patch"
  git -C "$LLAMA_SOURCE" apply "$GITHUB_WORKSPACE/$patch"
done
git -C "$LLAMA_SOURCE" diff --check
git -C "$LLAMA_SOURCE" diff --binary --full-index HEAD -- > "$EVIDENCE_DIR/source-diff.patch"
test "$(sha256sum "$EVIDENCE_DIR/source-diff.patch" | cut -d' ' -f1)" = \
  8ab4ea8e4a7412ec24f0fa4ebf49a23745c58cf66b8cfb2e99ac0ca53c69be12
git -C "$LLAMA_SOURCE" diff --name-only | sort > "$EVIDENCE_DIR/patched-files.txt"
python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["EVIDENCE_DIR"])
patches = sorted(path.name for path in (root / "patches").iterdir())
value = {"commit": os.environ["LLAMA_COMMIT"], "tag": "b10216", "patches_applied": patches}
(root / "source.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY

git clone --filter=blob:none \
  https://github.com/EleutherAI/lm-evaluation-harness.git "$HARNESS_SOURCE"
git -C "$HARNESS_SOURCE" checkout --detach "$HARNESS_COMMIT"
test "$(git -C "$HARNESS_SOURCE" rev-parse HEAD)" = "$HARNESS_COMMIT"
test -z "$(git -C "$HARNESS_SOURCE" status --short)"
git -C "$HARNESS_SOURCE" show -s --format=fuller HEAD | tee "$EVIDENCE_DIR/harness/commit.txt"
python3 -m venv "$E11A_VENV"
"$E11A_VENV/bin/python" -m pip install --disable-pip-version-check \
  --requirement experiments/e10d_requirements.txt \
  2>&1 | tee "$EVIDENCE_DIR/harness/pip-requirements.log"
"$E11A_VENV/bin/python" -m pip install --disable-pip-version-check \
  --no-deps "$HARNESS_SOURCE" \
  2>&1 | tee "$EVIDENCE_DIR/harness/pip-harness.log"
"$E11A_VENV/bin/python" -m pip freeze | sort > "$EVIDENCE_DIR/harness/pip-freeze.txt"
"$E11A_VENV/bin/python" - <<'PY' | tee "$EVIDENCE_DIR/harness/version.txt"
from importlib.metadata import version
print(version("lm_eval"))
PY

repository="$(jq -r '.model_repository.repository' "$E11A_CONTRACT_PATH")"
revision="$(jq -r '.model_repository.revision' "$E11A_CONTRACT_PATH")"
entrypoint="$(jq -r --arg candidate "$CANDIDATE" '.models[] | select(.candidate == $candidate) | .path' "$E11A_CONTRACT_PATH")"
model_sha="$(jq -r --arg candidate "$CANDIDATE" '.models[] | select(.candidate == $candidate) | .sha256' "$E11A_CONTRACT_PATH")"
model_size="$(jq -r --arg candidate "$CANDIDATE" '.models[] | select(.candidate == $candidate) | .size_bytes' "$E11A_CONTRACT_PATH")"
model="$MODEL_ROOT/$CANDIDATE/$entrypoint"
mkdir -p "$(dirname "$model")"
curl --fail --location --retry 5 --retry-all-errors \
  --output "$model" \
  "https://huggingface.co/$repository/resolve/$revision/$entrypoint?download=true"
test "$(stat --format='%s' "$model")" = "$model_size"
echo "$model_sha  $model" | sha256sum --check --strict
sha256sum "$model" | tee "$EVIDENCE_DIR/model-sha256.txt"

mapfile -t cmake_args < <(jq -r '.profiles.e7c_final.build.cmake_arguments[]' experiments/e9a_contract.json)
python3 - "${cmake_args[@]}" <<'PY' > "$EVIDENCE_DIR/build/configure-command.json"
import json
import sys
print(json.dumps({"cmake_arguments": sys.argv[1:]}, indent=2, sort_keys=True))
PY
printf '%s\n' "${cmake_args[@]}" > "$EVIDENCE_DIR/build/cmake-arguments.txt"
cmake -S "$LLAMA_SOURCE" -B "$LLAMA_BUILD" -G Ninja \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "${cmake_args[@]}" \
  2>&1 | tee "$EVIDENCE_DIR/build/configure.log"
grep -q 'Using KleidiAI optimized kernels if applicable' "$EVIDENCE_DIR/build/configure.log"
grep -q 'ARM detected' "$EVIDENCE_DIR/build/configure.log"
grep -q '^LLAMA_OPENSSL:BOOL=OFF$' "$LLAMA_BUILD/CMakeCache.txt"
cp "$LLAMA_BUILD/CMakeCache.txt" "$EVIDENCE_DIR/build/CMakeCache.txt"
/usr/bin/time --verbose --output "$EVIDENCE_DIR/build/build-time.log" \
  cmake --build "$LLAMA_BUILD" --target llama-server --parallel "$(nproc)" \
  2>&1 | tee "$EVIDENCE_DIR/build/build.log"
ninja -C "$LLAMA_BUILD" -t commands > "$EVIDENCE_DIR/build/build-commands.txt"
"$LLAMA_BUILD/bin/llama-server" --version 2>&1 | tee "$EVIDENCE_DIR/build/server-version.txt"
c++ --version > "$EVIDENCE_DIR/build/compiler-full.txt"
head -1 "$EVIDENCE_DIR/build/compiler-full.txt" | tee "$EVIDENCE_DIR/build/compiler.txt"
python3 experiments/e7a_runtime_closure.py \
  --server "$LLAMA_BUILD/bin/llama-server" \
  --build-root "$LLAMA_BUILD" \
  --copy-dir "$EVIDENCE_DIR/build/runtime-files" \
  --output "$EVIDENCE_DIR/build/runtime-closure.json"
jq -e '(.dynamic_dependency_basenames | index("libssl.so.3") == null) and (.dynamic_dependency_basenames | index("libcrypto.so.3") == null)' \
  "$EVIDENCE_DIR/build/runtime-closure.json"

active_timer_pid=""
active_server_pid=""
cleanup() {
  if [ -n "$active_server_pid" ] && kill -0 "$active_server_pid" 2>/dev/null; then
    kill -INT "$active_server_pid" 2>/dev/null || true
  fi
  if [ -n "$active_timer_pid" ]; then
    wait "$active_timer_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
server="$LLAMA_BUILD/bin/llama-server"
SERVER="$server" MODEL="$model" MODEL_SHA="$model_sha" MODEL_SIZE="$model_size" python3 - <<'PY'
import json
import os
from pathlib import Path
from experiments.e6f_ingest import capture_server_version
from experiments.e9a_ingest import expected_server_argv

adapter = json.loads(Path("experiments/e10d_contract.json").read_text())
contract = json.loads(Path(os.environ["E11A_CONTRACT_PATH"]).read_text())
model = next(item for item in contract["models"] if item["candidate"] == os.environ["CANDIDATE"])
recipe = {
    "schema_version": 1,
    "experiment_id": "E10d",
    "profile_name": "e7c_final_plus_probability_ids",
    "service": adapter["service"],
    "server_path": os.environ["SERVER"],
    "server_version": capture_server_version(os.environ["SERVER"]).strip(),
    "model": {
        "candidate": model["candidate"],
        "path": os.environ["MODEL"],
        "sha256": os.environ["MODEL_SHA"],
        "size_bytes": int(os.environ["MODEL_SIZE"]),
    },
    "argv": expected_server_argv(
        os.environ["SERVER"], os.environ["MODEL"],
        candidate=model["candidate"], profile_name="e7c_final",
    ),
}
(Path(os.environ["EVIDENCE_DIR"]) / "recipe.json").write_text(json.dumps(recipe, indent=2, sort_keys=True) + "\n")
PY
mapfile -t server_argv < <(jq -r '.argv[]' "$EVIDENCE_DIR/recipe.json")
/usr/bin/time --verbose --output "$EVIDENCE_DIR/server-time.log" \
  "${server_argv[@]}" \
  > "$EVIDENCE_DIR/server.stdout.log" \
  2> "$EVIDENCE_DIR/server.stderr.log" &
active_timer_pid=$!
python3 experiments/e3d_http_quality.py wait \
  --url http://127.0.0.1:18081 --timeout 45 --output "$EVIDENCE_DIR/readiness.json"
for _ in $(seq 1 50); do
  active_server_pid="$(pgrep -P "$active_timer_pid" -x llama-server || true)"
  if [ -n "$active_server_pid" ]; then break; fi
  sleep 0.1
done
test -n "$active_server_pid"
echo "$active_server_pid" > "$EVIDENCE_DIR/server-pid.txt"
"$E11A_VENV/bin/python" experiments/e10d_preflight.py \
  --base-url http://127.0.0.1:18081 \
  --seed 424242 \
  --raw-dir "$EVIDENCE_DIR/preflight-raw" \
  --output "$EVIDENCE_DIR/preflight.json"
PYTHONPATH="$HARNESS_SOURCE:$GITHUB_WORKSPACE" \
  "$E11A_VENV/bin/python" experiments/e10d_prepare.py \
    --base-url http://127.0.0.1:18081 \
    --plan experiments/e9b_preflight_plan.json \
    --include-path experiments/e9b_tasks \
    --max-length 256 \
    --seed 424242 \
    --output "$EVIDENCE_DIR/prepared.json"
"$E11A_VENV/bin/python" experiments/e10d_probe.py \
  --base-url http://127.0.0.1:18081 \
  --prepared "$EVIDENCE_DIR/prepared.json" \
  --model "$CANDIDATE" \
  --model-sha256 "$model_sha" \
  --server-pid "$active_server_pid" \
  --seed 424242 \
  --raw-dir "$EVIDENCE_DIR/raw" \
  --output "$EVIDENCE_DIR/probe.json"
curl --fail --silent http://127.0.0.1:18081/metrics > "$EVIDENCE_DIR/metrics.txt"
curl --fail --silent http://127.0.0.1:18081/slots > "$EVIDENCE_DIR/slots.json"
curl --fail --silent http://127.0.0.1:18081/health > "$EVIDENCE_DIR/health.json"
kill -INT "$active_server_pid"
set +e
wait "$active_timer_pid"
server_status=$?
set -e
echo "$server_status" > "$EVIDENCE_DIR/server-shell-exit.txt"
[[ "$server_status" -eq 0 || "$server_status" -eq 130 ]]
active_server_pid=""
active_timer_pid=""
trap - EXIT

python3 experiments/e11a_ingest.py cell \
  --evidence-dir "$EVIDENCE_DIR" \
  --contract "$E11A_CONTRACT_PATH" \
  --root "$GITHUB_WORKSPACE" \
  --model "$CANDIDATE" \
  --output "$EVIDENCE_DIR/summary.json"
find "$EVIDENCE_DIR" -type f ! -name file-inventory-sha256.txt -print0 \
  | sort -z | xargs -0 sha256sum > "$EVIDENCE_DIR/file-inventory-sha256.txt"
df -h | tee "$EVIDENCE_DIR/disk-after.txt"
