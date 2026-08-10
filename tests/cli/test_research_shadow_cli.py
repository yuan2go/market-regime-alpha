from __future__ import annotations

import pytest

from market_regime_alpha.cli.research_shadow import build_parser


@pytest.mark.parametrize(
    ("operation", "arguments"),
    (
        (
            "schedule",
            (
                "--run-id",
                "run-1",
                "--trading-date",
                "2026-08-10",
                "--scheduled-at",
                "2026-08-10T06:30:00Z",
                "--idempotency-key",
                "shadow-2026-08-10",
            ),
        ),
        ("run", ("--session-id", "session-1", "--expected-version", "1")),
        (
            "freeze",
            (
                "--session-id",
                "session-1",
                "--summary-id",
                "summary-1",
                "--frozen-at",
                "2026-08-10T06:55:01Z",
                "--expected-version",
                "2",
            ),
        ),
        (
            "outcome-pending",
            ("--session-id", "session-1", "--expected-version", "3"),
        ),
        (
            "settle",
            (
                "--decision-id",
                "decision-1",
                "--source-archive",
                "source.json",
                "--settlement-dataset",
                "dataset.json",
                "--factual-evidence",
                "factual.json",
                "--next-session-date",
                "2026-08-11",
                "--session-status",
                "TRADING_DAY",
                "--expected-version",
                "4",
                "--created-at",
                "2026-08-11T08:01:00Z",
                "--code-revision",
                "abc123",
                "--clock-mode",
                "SIMULATED",
                "--runtime-origin",
                "FIXTURE",
            ),
        ),
        (
            "build-evaluation",
            (
                "--decision-id",
                "decision-1",
                "--targeted-outcome-id",
                "targeted-1",
                "--target-protocol-id",
                "protocol-1",
                "--dynamic-pool",
                "pool.json",
                "--candidate-set",
                "candidates.json",
                "--state-policy-references",
                "policies.json",
                "--artifact-root",
                "artifacts",
                "--created-at",
                "2026-08-11T08:02:00Z",
            ),
        ),
        (
            "build-enriched-evaluation",
            (
                "--decision-id",
                "decision-1",
                "--targeted-outcome-id",
                "targeted-1",
                "--target-protocol-id",
                "protocol-1",
                "--dynamic-pool",
                "pool.json",
                "--candidate-set",
                "candidates.json",
                "--state-policy-references",
                "policies.json",
                "--artifact-root",
                "artifacts",
                "--created-at",
                "2026-08-11T08:02:00Z",
                "--dataset",
                "dataset",
                "--feature-bundle",
                "feature-bundle",
                "--feature-artifact-root",
                "feature-artifacts",
                "--forecasts",
                "forecasts.json",
                "--state-sources",
                "state-sources.json",
            ),
        ),
        ("report", ("--session-id", "session-1")),
        ("replay", ("--decision-id", "decision-1")),
        ("resume", ("--session-id", "session-1", "--expected-version", "5")),
        (
            "invalidate",
            (
                "--session-id",
                "session-1",
                "--expected-version",
                "5",
                "--reason-code",
                "OPERATOR_INVALIDATED",
            ),
        ),
    ),
)
def test_research_shadow_cli_exposes_the_operating_loop(
    operation: str,
    arguments: tuple[str, ...],
) -> None:
    parsed = build_parser().parse_args(
        ["--database-url", "postgresql://shadow-authority", operation, *arguments]
    )

    assert parsed.operation == operation
