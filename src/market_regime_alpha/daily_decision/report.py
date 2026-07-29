"""Deterministic reconstruction of the Phase D daily report."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market_regime_alpha.daily_decision.artifact import (
        PhaseDDailyDecisionBundle,
    )


def render_phase_d_daily_report(bundle: PhaseDDailyDecisionBundle) -> str:
    lines = [
        "# Phase D Exploratory Daily Decision",
        "",
        f"- Artifact status: `{bundle.status.value}`",
        f"- RunRequestId: `{bundle.run_identity.run_request_id}`",
        f"- DailyRunId: `{bundle.run_identity.daily_run_id}`",
        f"- SourceManifest: `{bundle.source_manifest.source_manifest_id}`",
        f"- Data quality: `{bundle.data_quality_report.status.value}`",
        f"- Prediction runs: `{len(bundle.prediction_runs)}`",
        f"- Candidate recommendations: `{len(bundle.recommendations)}`",
        f"- Entry assessments: `{len(bundle.entry_assessments)}`",
        "",
    ]
    if bundle.data_quality_report.blocked_reason_codes:
        lines.extend(
            [
                "## Blocked reasons",
                "",
                *(
                    f"- `{reason}`"
                    for reason in bundle.data_quality_report.blocked_reason_codes
                ),
                "",
            ]
        )
    if bundle.recommendations:
        lines.extend(["## Recommendations", ""])
        for item in bundle.recommendations:
            lines.append(
                f"- `{item.model_id}` #{item.rank} `{item.symbol}` "
                f"score `{item.score:.12g}` — not a probability"
            )
        lines.append("")
    lines.extend(
        [
            "## Authority boundary",
            "",
            "- `EXPLORATORY_DAILY_LOOP_OPERATIONAL`",
            "- `FORMAL_OOS_ALPHA_NOT_ESTABLISHED`",
            "- `TRADING_AUTHORITY_NOT_GRANTED`",
            "",
        ]
    )
    return "\n".join(lines)
