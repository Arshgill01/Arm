#!/usr/bin/env python3
"""Build and verify a deterministic provenance-bound Arm repack sidecar."""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import platform
import re
import struct
from pathlib import Path
from typing import Any, BinaryIO


MAGIC = b"P64ARMPACKV1\0\0\0\0"
DATA_OFFSET = 1024 * 1024
INVENTORY_FIELDS = [
    "tensor",
    "file",
    "type",
    "parameter_type",
    "ne0",
    "ne1",
    "ne2",
    "ne3",
    "bytes",
    "buffer_offset",
    "columns",
    "interleave",
]
SAFE_FILE = re.compile(r"[A-Za-z0-9._-]+\.bin")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_region(handle: BinaryIO, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    handle.seek(offset)
    remaining = size
    while remaining:
        chunk = handle.read(min(1024 * 1024, remaining))
        if not chunk:
            raise ValueError("sidecar tensor region is truncated")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def parse_runtime(path: Path) -> dict[str, Any]:
    rows = list(
        csv.DictReader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t")
    )
    if (
        len(rows) != 1
        or set(rows[0]) != {"buffer_base", "buffer_size_bytes"}
        or not re.fullmatch(r"0x[0-9a-f]+", rows[0]["buffer_base"])
    ):
        raise ValueError("repack runtime record is invalid")
    size = int(rows[0]["buffer_size_bytes"])
    if size <= 0:
        raise ValueError("repack buffer size must be positive")
    return {"buffer_base": rows[0]["buffer_base"], "buffer_size_bytes": size}


def parse_inventory(dump_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime = parse_runtime(dump_dir / "runtime.tsv")
    with (dump_dir / "inventory.tsv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != INVENTORY_FIELDS:
            raise ValueError("repack inventory header differs")
        raw_rows = list(reader)
    if not raw_rows:
        raise ValueError("repack inventory is empty")

    tensors: list[dict[str, Any]] = []
    names: set[str] = set()
    files: set[str] = set()
    for row in raw_rows:
        filename = row["file"]
        if (
            row["tensor"] in names
            or filename in files
            or not SAFE_FILE.fullmatch(filename)
            or Path(filename).name != filename
        ):
            raise ValueError("repack inventory has duplicate or unsafe identity")
        names.add(row["tensor"])
        files.add(filename)
        numeric = {
            key: int(row[key])
            for key in (
                "ne0",
                "ne1",
                "ne2",
                "ne3",
                "bytes",
                "buffer_offset",
                "columns",
                "interleave",
            )
        }
        if (
            any(numeric[key] <= 0 for key in ("ne0", "ne1", "ne2", "ne3"))
            or numeric["bytes"] <= 0
            or numeric["buffer_offset"] < 0
            or numeric["columns"] <= 0
            or numeric["interleave"] <= 0
        ):
            raise ValueError("repack inventory has invalid numeric metadata")
        source = dump_dir / filename
        if not source.is_file() or source.stat().st_size != numeric["bytes"]:
            raise ValueError(f"repack tensor bytes differ: {filename}")
        tensors.append(
            {
                "tensor": row["tensor"],
                "file": filename,
                "type": row["type"],
                "parameter_type": row["parameter_type"],
                **numeric,
                "sha256": sha256_file(source),
            }
        )

    tensors.sort(key=lambda item: (item["buffer_offset"], item["tensor"]))
    previous_end = 0
    for tensor in tensors:
        if tensor["buffer_offset"] < previous_end:
            raise ValueError("repack tensor regions overlap")
        previous_end = tensor["buffer_offset"] + tensor["bytes"]
    if previous_end > runtime["buffer_size_bytes"]:
        raise ValueError("repack tensor exceeds its buffer")
    return tensors, runtime


def cpu_features(path: Path = Path("/proc/cpuinfo")) -> dict[str, Any]:
    records = [
        record
        for record in path.read_text(encoding="utf-8").split("\n\n")
        if record.strip()
    ]
    parsed: list[dict[str, str]] = []
    for record in records:
        values: dict[str, str] = {}
        for line in record.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key.strip().lower()] = value.strip()
        if values:
            parsed.append(values)
    feature_sets = [
        set(record.get("features", "").split())
        for record in parsed
        if "features" in record
    ]
    shared = sorted(set.intersection(*feature_sets)) if feature_sets else []
    sve_vector_length = 0
    if "sve" in shared:
        result = ctypes.CDLL(None, use_errno=True).prctl(51, 0, 0, 0, 0)
        if result >= 0:
            sve_vector_length = result & 0xFFFF
    return {
        "architecture": platform.machine(),
        "cpu_implementers": sorted(
            {record.get("cpu implementer", "") for record in parsed} - {""}
        ),
        "cpu_parts": sorted({record.get("cpu part", "") for record in parsed} - {""}),
        "common_features": shared,
        "common_features_sha256": hashlib.sha256(
            "\n".join(shared).encode()
        ).hexdigest(),
        "sve_vector_length_bytes": sve_vector_length,
    }


def create_identity(contract_path: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    return {
        "schema_version": 1,
        "experiment_id": contract["experiment_id"],
        "source_model_sha256": contract["selected"]["model_sha256"],
        "llama_cpp_commit": contract["source"]["commit"],
        "source_diff_sha256": contract["source"]["aggregate_diff_sha256"],
        "repack_dump_format_version": contract["mechanism"]["dump_format_version"],
        "sidecar_format_version": contract["mechanism"]["sidecar_format_version"],
        "cpu": cpu_features(),
    }


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def build_sidecar(
    dump_dir: Path, identity: dict[str, Any], output: Path
) -> dict[str, Any]:
    tensors, runtime = parse_inventory(dump_dir)
    packed_bytes = sum(tensor["bytes"] for tensor in tensors)
    header = {
        "schema_version": 1,
        "format": "pareto64-arm-repack-sidecar",
        "data_offset": DATA_OFFSET,
        "arena_size_bytes": runtime["buffer_size_bytes"],
        "packed_tensor_bytes": packed_bytes,
        "coverage_fraction": packed_bytes / runtime["buffer_size_bytes"],
        "tensor_count": len(tensors),
        "binding": identity,
        "tensors": tensors,
    }
    encoded = canonical_json(header)
    prefix_size = len(MAGIC) + 8 + len(encoded)
    if prefix_size > DATA_OFFSET:
        raise ValueError("sidecar header exceeds fixed reservation")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w+b") as sidecar:
        sidecar.write(MAGIC)
        sidecar.write(struct.pack("<Q", len(encoded)))
        sidecar.write(encoded)
        sidecar.seek(DATA_OFFSET - 1)
        sidecar.write(b"\0")
        for tensor in tensors:
            sidecar.seek(DATA_OFFSET + tensor["buffer_offset"])
            with (dump_dir / tensor["file"]).open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    sidecar.write(chunk)
        sidecar.truncate(DATA_OFFSET + runtime["buffer_size_bytes"])
    return {
        "schema_version": 1,
        "header": header,
        "header_sha256": hashlib.sha256(encoded).hexdigest(),
        "sidecar_sha256": sha256_file(output),
        "sidecar_size_bytes": output.stat().st_size,
        "runtime_capture": runtime,
    }


def read_header(sidecar: BinaryIO) -> tuple[dict[str, Any], bytes]:
    if sidecar.read(len(MAGIC)) != MAGIC:
        raise ValueError("sidecar magic differs")
    length_bytes = sidecar.read(8)
    if len(length_bytes) != 8:
        raise ValueError("sidecar header length is truncated")
    length = struct.unpack("<Q", length_bytes)[0]
    if length <= 0 or length > DATA_OFFSET - len(MAGIC) - 8:
        raise ValueError("sidecar header length is invalid")
    encoded = sidecar.read(length)
    header = json.loads(encoded)
    if not isinstance(header, dict) or canonical_json(header) != encoded:
        raise ValueError("sidecar header is not canonical")
    return header, encoded


def verify_sidecar(sidecar_path: Path, index_path: Path) -> dict[str, Any]:
    index = load_object(index_path)
    with sidecar_path.open("rb") as sidecar:
        header, encoded = read_header(sidecar)
        if (
            header != index.get("header")
            or hashlib.sha256(encoded).hexdigest() != index.get("header_sha256")
            or sidecar_path.stat().st_size != index.get("sidecar_size_bytes")
            or sha256_file(sidecar_path) != index.get("sidecar_sha256")
        ):
            raise ValueError("sidecar container differs from its index")
        for tensor in header["tensors"]:
            observed = sha256_region(
                sidecar,
                header["data_offset"] + tensor["buffer_offset"],
                tensor["bytes"],
            )
            if observed != tensor["sha256"]:
                raise ValueError(f"sidecar tensor differs: {tensor['tensor']}")
    return {
        "status": "valid_sidecar",
        "sidecar_sha256": index["sidecar_sha256"],
        "tensor_count": header["tensor_count"],
    }


def write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    identity_parser = commands.add_parser("identity")
    identity_parser.add_argument("--contract", type=Path, required=True)
    identity_parser.add_argument("--output", type=Path, required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--dump-dir", type=Path, required=True)
    build_parser.add_argument("--identity", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--index", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--sidecar", type=Path, required=True)
    verify_parser.add_argument("--index", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "identity":
        write_object(args.output, create_identity(args.contract))
        print(json.dumps({"status": "identity_created"}, sort_keys=True))
    elif args.command == "build":
        index = build_sidecar(args.dump_dir, load_object(args.identity), args.output)
        write_object(args.index, index)
        print(
            json.dumps(
                {
                    "status": "sidecar_built",
                    "sidecar_sha256": index["sidecar_sha256"],
                    "tensor_count": index["header"]["tensor_count"],
                },
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(verify_sidecar(args.sidecar, args.index), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
