#!/usr/bin/env python3
"""Render and execute E12b with E10f's safe-sampled scoring transport."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

OLD_PROBE = '''"$E12B_VENV/bin/python" experiments/e10d_probe.py \\
  --base-url http://127.0.0.1:18081 \\
  --prepared "$EVIDENCE_DIR/prepared.json" \\
  --model "$CANDIDATE" \\
  --model-sha256 "$model_sha" \\
  --server-pid "$active_server_pid" \\
  --seed 424242 \\
  --raw-dir "$EVIDENCE_DIR/raw" \\
  --output "$EVIDENCE_DIR/probe.json"'''

SAFE_PROBE = '''"$E12B_VENV/bin/python" experiments/e10f_probe.py \\
  --base-url http://127.0.0.1:18081 \\
  --prepared "$EVIDENCE_DIR/prepared.json" \\
  --model "$CANDIDATE" \\
  --model-sha256 "$model_sha" \\
  --server-pid "$active_server_pid" \\
  --seed "$(jq -r '.scoring.probe_parameters.seed' "$E12B_CONTRACT_PATH")" \\
  --timeout "$(jq -r '.scoring.request_timeout_seconds' "$E12B_CONTRACT_PATH")" \\
  --safe-token-id "$(jq -r '.safe_sampling.token_id' "$E12B_CONTRACT_PATH")" \\
  --safe-logit-bias "$(jq -r '.safe_sampling.logit_bias' "$E12B_CONTRACT_PATH")" \\
  --safe-token-text "$(jq -r '.safe_sampling.token_text' "$E12B_CONTRACT_PATH")" \\
  --raw-dir "$EVIDENCE_DIR/raw" \\
  --output "$EVIDENCE_DIR/probe.json"'''


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def render(source: str) -> str:
    replacements = (
        (
            "python3 -m unittest tests.test_e10d tests.test_e11a tests.test_e12b",
            (
                "python3 -m unittest tests.test_e10d tests.test_e10f "
                "tests.test_e11a tests.test_e12b tests.test_e12b_successor"
            ),
        ),
        (OLD_PROBE, SAFE_PROBE),
        (
            "python3 experiments/e12b_ingest.py cell \\",
            "python3 experiments/e12b_successor_ingest.py cell \\",
        ),
    )
    rendered = source
    for old, new in replacements:
        if rendered.count(old) != 1:
            raise ValueError("E12b successor source replacement boundary differs")
        rendered = rendered.replace(old, new)
    return rendered


def retain_successor_inputs(evidence: Path, root: Path, resolved: str) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    files = {
        "successor-wrapper.py": root / "experiments/e12b_successor_cell.py",
        "successor-ingest.py": root / "experiments/e12b_successor_ingest.py",
        "successor-freeze.py": root / "experiments/e12b_successor_freeze.py",
        "successor-test.py": root / "tests/test_e12b_successor.py",
        "e10f-contract.json": root / "experiments/e10f_contract.json",
        "e10f-probe.py": root / "experiments/e10f_probe.py",
        "e10f-ingest.py": root / "experiments/e10f_ingest.py",
        "base-ingest.py": root / "experiments/e12b_ingest.py",
        "base-freeze.py": root / "experiments/e12b_freeze.py",
        "base-test.py": root / "tests/test_e12b.py",
        "e10f-retained-manifest.json": (
            root / "results/manifests/e10f-30829237582.json"
        ),
        "e12a-resume-contract.json": (root / "experiments/e12a_resume_contract.json"),
        "e11a-successor-contract.json": (
            root / "experiments/e11a_successor_contract.json"
        ),
    }
    for name, source in files.items():
        shutil.copy2(source, evidence / name)
    resolved_path = evidence / "resolved-cell-runner.sh"
    resolved_path.write_text(resolved)
    resolved_path.chmod(0o700)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--source", type=Path, default=Path("experiments/e12b_cell.sh"))
    parser.add_argument("--print-sha256", action="store_true")
    args = parser.parse_args()
    source = (args.root / args.source).read_text()
    resolved = render(source)
    digest = sha256_bytes(resolved.encode())
    if args.print_sha256:
        print(digest)
        return 0
    contract_path = Path(os.environ["E12B_CONTRACT_PATH"])
    contract = json.loads(contract_path.read_text())
    if digest != contract["execution"]["resolved_cell_runner_sha256"]:
        raise ValueError("E12b resolved safe-sampled cell runner differs")
    evidence = Path(os.environ["EVIDENCE_DIR"])
    retain_successor_inputs(evidence, args.root, resolved)
    completed = subprocess.run(
        ["bash", str(evidence / "resolved-cell-runner.sh")],
        cwd=args.root,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
