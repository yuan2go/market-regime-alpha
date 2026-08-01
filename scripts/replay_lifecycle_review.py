#!/usr/bin/env python3
"""Verify and deterministically replay one lifecycle review Artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_regime_alpha.application.trading_lifecycle import (
    replay_lifecycle_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify and replay a manual decision lifecycle review package"
    )
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    verified = replay_lifecycle_review(args.artifact)
    review = verified.review
    print(
        json.dumps(
            {
                "artifact_id": str(review.artifact_id),
                "content_hash": review.content_hash,
                "holding_action": review.holding_assessment.action.value,
                "exit_action": review.exit_assessment.action.value,
                "trade_outcome_id": str(review.trade_outcome.outcome_id),
                "scorecard_id": str(review.rolling_scorecard.scorecard_id),
                "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
