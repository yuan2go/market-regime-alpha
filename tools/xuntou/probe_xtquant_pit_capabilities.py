#!/usr/bin/env python3
"""Probe XtQuant availability without inferring undocumented PIT semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_regime_alpha.research.xuntou_pit_v4_runtime import probe_xtquant_pit_capabilities


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe_xtquant_pit_capabilities()
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        if args.output.exists():
            raise FileExistsError("capability probe output is non-overwriting")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
