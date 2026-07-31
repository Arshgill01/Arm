#!/usr/bin/env python3
"""Validate E3f evidence with the shared current-runtime frontier ingester."""

try:
    from experiments.e3d_ingest import main
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e3d_ingest import main


if __name__ == "__main__":
    raise SystemExit(main())
