#!/usr/bin/env python3
"""Render E12b for the actual recovered E11a and E12a prerequisites."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

try:
    from experiments.e12b_successor_cell import (
        render as render_successor,
        retain_successor_inputs,
        sha256_bytes,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e12b_successor_cell import (
        render as render_successor,
        retain_successor_inputs,
        sha256_bytes,
    )


def render(source: str) -> str:
    rendered = render_successor(source)
    replacements = (
        (
            "tests.test_e11a tests.test_e12b tests.test_e12b_successor",
            (
                "tests.test_e11a tests.test_e12b tests.test_e12b_successor "
                "tests.test_e12b_actual"
            ),
        ),
        (
            "python3 experiments/e12b_successor_ingest.py cell \\",
            "python3 experiments/e12b_actual_ingest.py cell \\",
        ),
    )
    for old, new in replacements:
        if rendered.count(old) != 1:
            raise ValueError("E12b actual source replacement boundary differs")
        rendered = rendered.replace(old, new)
    return rendered


def retain_actual_inputs(evidence: Path, root: Path, resolved: str) -> None:
    retain_successor_inputs(evidence, root, resolved)
    contract = json.loads(Path(os.environ["E12B_CONTRACT_PATH"]).read_text())
    files = {
        "actual-wrapper.py": root / "experiments/e12b_actual_cell.py",
        "actual-ingest.py": root / "experiments/e12b_actual_ingest.py",
        "actual-freeze.py": root / "experiments/e12b_actual_freeze.py",
        "actual-test.py": root / "tests/test_e12b_actual.py",
        "e12a-metadata-contract.json": (
            root / "experiments/e12a_metadata_recovery_contract.json"
        ),
        "e12a-metadata-manifest.json": (
            root / "results/manifests/e12a-metadata-recovery-30855550027.json"
        ),
        "e11a-recovery-contract.json": (
            root / contract["inputs"]["e11a_recovery_contract_path"]
        ),
        "e11a-recovery-summary.json": (
            root / contract["inputs"]["e11a_recovery_summary_path"]
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
    resolved = render((args.root / args.source).read_text())
    digest = sha256_bytes(resolved.encode())
    if args.print_sha256:
        print(digest)
        return 0
    contract = json.loads(Path(os.environ["E12B_CONTRACT_PATH"]).read_text())
    if digest != contract["execution"]["resolved_cell_runner_sha256"]:
        raise ValueError("E12b actual resolved cell runner differs")
    evidence = Path(os.environ["EVIDENCE_DIR"])
    retain_actual_inputs(evidence, args.root, resolved)
    completed = subprocess.run(
        ["bash", str(evidence / "resolved-cell-runner.sh")],
        cwd=args.root,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
