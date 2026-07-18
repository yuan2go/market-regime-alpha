#!/usr/bin/env python3
"""Fail-closed boundary for an authorized Xuntou PIT validation export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_regime_alpha.research.xuntou_pit_v4_runtime import probe_xtquant_pit_capabilities


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--symbols-file", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--raw-output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.status_output.exists() or args.raw_output_root.exists():
        raise FileExistsError("Xuntou export outputs are immutable and non-overwriting")
    if not args.symbols_file.is_file():
        raise ValueError("an explicit symbols file is required")
    probe = probe_xtquant_pit_capabilities()
    status = (
        "EXTERNAL_XTQUANT_RUNTIME_REQUIRED"
        if probe["xtquant_import_status"] == "EXTERNAL_XTQUANT_RUNTIME_REQUIRED"
        else "INSUFFICIENT_PROVIDER_CAPABILITY"
    )
    payload = {
        "schema_version": "xuntou-pit-v4-export-status-v1",
        "status": status,
        "requested_start_date": args.start_date,
        "requested_end_date": args.end_date,
        "symbols_file": str(args.symbols_file),
        "raw_provider_files_written": [],
        "normalized_bundle_written": False,
        "mock_or_synthetic_data_used": False,
        "reason": (
            "XtQuant must run in the authorized Windows/MiniQMT environment"
            if status == "EXTERNAL_XTQUANT_RUNTIME_REQUIRED"
            else "documented method presence does not prove required PIT semantics or entitlement"
        ),
    }
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
