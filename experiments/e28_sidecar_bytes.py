#!/usr/bin/env python3
"""Measure the exact E25 decoded-metadata allocation from a GGUF tensor table."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import BinaryIO


Q4_K_TYPE = 12
QK_K = 256
Q4_K_BLOCK_BYTES = 144
Q4_K_INTERLEAVED_ROWS = 8
DECODED_METADATA_BYTES_PER_INTERLEAVED_BLOCK = 128
FIXED_VALUE_BYTES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
STRING_TYPE = 8
ARRAY_TYPE = 9


def read_exact(handle: BinaryIO, size: int) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise ValueError("truncated GGUF header")
    return value


def unpack(handle: BinaryIO, code: str) -> int:
    return int(struct.unpack("<" + code, read_exact(handle, struct.calcsize(code)))[0])


def skip_string(handle: BinaryIO) -> str:
    size = unpack(handle, "Q")
    return read_exact(handle, size).decode("utf-8")


def skip_value(handle: BinaryIO, value_type: int) -> None:
    if value_type in FIXED_VALUE_BYTES:
        handle.seek(FIXED_VALUE_BYTES[value_type], 1)
    elif value_type == STRING_TYPE:
        size = unpack(handle, "Q")
        handle.seek(size, 1)
    elif value_type == ARRAY_TYPE:
        element_type = unpack(handle, "I")
        count = unpack(handle, "Q")
        if element_type in FIXED_VALUE_BYTES:
            handle.seek(FIXED_VALUE_BYTES[element_type] * count, 1)
        else:
            for _ in range(count):
                skip_value(handle, element_type)
    else:
        raise ValueError(f"unsupported GGUF metadata value type {value_type}")


def measure(path: Path, model_sha256: str) -> dict[str, object]:
    rows = []
    with path.open("rb") as handle:
        if read_exact(handle, 4) != b"GGUF":
            raise ValueError("input is not a little-endian GGUF file")
        version = unpack(handle, "I")
        if version not in (2, 3):
            raise ValueError(f"unsupported GGUF version {version}")
        tensor_count = unpack(handle, "Q")
        metadata_count = unpack(handle, "Q")
        for _ in range(metadata_count):
            skip_string(handle)
            skip_value(handle, unpack(handle, "I"))
        for _ in range(tensor_count):
            name = skip_string(handle)
            dimension_count = unpack(handle, "I")
            shape = [unpack(handle, "Q") for _ in range(dimension_count)]
            tensor_type = unpack(handle, "I")
            unpack(handle, "Q")  # tensor data offset
            if tensor_type != Q4_K_TYPE or dimension_count != 2 or shape[1] % 8:
                continue
            elements = shape[0] * shape[1]
            if elements % (QK_K * Q4_K_INTERLEAVED_ROWS):
                raise ValueError(f"eligible tensor {name} cannot form complete 8-row Q4_K blocks")
            packed_bytes = elements // QK_K * Q4_K_BLOCK_BYTES
            interleaved_blocks = elements // (QK_K * Q4_K_INTERLEAVED_ROWS)
            rows.append(
                {
                    "name": name,
                    "shape": shape,
                    "packed_bytes": packed_bytes,
                    "decoded_metadata_bytes": interleaved_blocks
                    * DECODED_METADATA_BYTES_PER_INTERLEAVED_BLOCK,
                }
            )
    return {
        "schema_version": 1,
        "model_path": str(path),
        "model_size_bytes": path.stat().st_size,
        "model_sha256": model_sha256,
        "gguf_version": version,
        "gguf_tensor_count": tensor_count,
        "selection": "Q4_K tensors with exactly two dimensions and ne[1] divisible by 8",
        "allocation_formula": "ggml_nbytes(tensor) / 1152 * 128",
        "selected_tensor_count": len(rows),
        "packed_q4_k_bytes": sum(int(row["packed_bytes"]) for row in rows),
        "decoded_sidecar_bytes": sum(int(row["decoded_metadata_bytes"]) for row in rows),
        "tensors": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model-sha256", required=True)
    args = parser.parse_args()
    result = measure(args.model, args.model_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("selected_tensor_count", "packed_q4_k_bytes", "decoded_sidecar_bytes")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
