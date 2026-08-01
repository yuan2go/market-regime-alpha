#!/usr/bin/env python3
"""Run and publish a lifecycle review from an explicit canonical input file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.trading_lifecycle import (
    publish_lifecycle_review,
    run_lifecycle_review_input,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a versioned manual lifecycle review; no live execution"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    payload = _object(json.loads(args.input.read_text(encoding="utf-8")))
    review = run_lifecycle_review_input(payload)
    path = publish_lifecycle_review(root=args.artifact_root, review=review)
    print(
        json.dumps(
            {
                "artifact_id": str(review.artifact_id),
                "artifact_path": str(path),
                "content_hash": review.content_hash,
                "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("lifecycle review input must contain an object")
    return value


if __name__ == "__main__":
    main()
