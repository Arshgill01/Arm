#!/usr/bin/env python3
"""CLI entry point for the shared E3c quality-frontier evidence ingester."""

try:
    from experiments.e3b_ingest import main
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e3b_ingest import main


if __name__ == "__main__":
    raise SystemExit(main())
