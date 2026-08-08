#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "${MODEL_PATH:-}" ]]; then
    echo "usage: MODEL_PATH=/path/to/q4_k_m.gguf $0 OUTPUT_DIR" >&2
    exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
expected_sha256=fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4
expected_size=2146497824
test "$(stat --format='%s' "$MODEL_PATH")" = "$expected_size"
echo "$expected_sha256  $MODEL_PATH" | sha256sum --check --strict
exec "$repo_root/experiments/e24c_second_arm_ab.sh" "$1"
