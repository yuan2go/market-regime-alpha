"""Executable Strategy feedback closure over PostgreSQL-owned evidence."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.strategies.feedback import (
    StrategyFeedbackArtifact,
    attribute_path_outcomes,
    decide_strategy_qualification,
    evaluate_strategy_challenger,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)


def close_strategy_feedback_loop(
    *,
    repository: PostgresMultiStrategyRepository,
    incumbent_version_reference: RuntimeArtifactReference,
    challenger_version_reference: RuntimeArtifactReference,
    formal_pit: bool,
    formal_oos: bool,
    calibrated: bool,
    net_economics_established: bool,
    prospective_evidence: bool,
    created_at: datetime,
) -> tuple[StrategyFeedbackArtifact, ...]:
    """Persist Attribution, Challenger Evaluation, and fail-closed Qualification."""

    if any(
        (
            formal_pit,
            formal_oos,
            calibrated,
            net_economics_established,
            prospective_evidence,
        )
    ):
        raise ValueError(
            "positive qualification evidence must be owner-resolved, not caller asserted"
        )

    registry = repository.load_registry()
    versions = {(item.version_id, item.version_hash): item for item in registry.versions}
    incumbent_version = versions.get(
        (
            incumbent_version_reference.artifact_id,
            incumbent_version_reference.content_hash,
        )
    )
    challenger_version = versions.get(
        (
            challenger_version_reference.artifact_id,
            challenger_version_reference.content_hash,
        )
    )
    if incumbent_version is None or challenger_version is None:
        raise ValueError("Feedback loop requires registered Strategy Versions")
    if incumbent_version.family is not challenger_version.family:
        raise ValueError("Challenger comparison cannot cross Strategy Family")
    if incumbent_version.version_id == challenger_version.version_id:
        raise ValueError("Challenger comparison requires distinct Strategy Versions")

    incumbent = repository.save_feedback(
        attribute_path_outcomes(
            strategy_version_reference=incumbent_version_reference,
            outcomes=repository.list_path_outcomes(
                strategy_version_id=incumbent_version_reference.artifact_id,
            ),
            created_at=created_at,
        )
    )
    challenger = repository.save_feedback(
        attribute_path_outcomes(
            strategy_version_reference=challenger_version_reference,
            outcomes=repository.list_path_outcomes(
                strategy_version_id=challenger_version_reference.artifact_id,
            ),
            created_at=created_at,
        )
    )
    comparison = repository.save_feedback(
        evaluate_strategy_challenger(
            incumbent=incumbent,
            challenger=challenger,
            created_at=created_at,
        )
    )
    qualification = repository.save_feedback(
        decide_strategy_qualification(
            strategy_version_reference=challenger_version_reference,
            attribution=challenger,
            challenger_evaluation=comparison,
            formal_pit=False,
            formal_oos=False,
            calibrated=False,
            net_economics_established=False,
            prospective_evidence=False,
            created_at=created_at,
        )
    )
    return incumbent, challenger, comparison, qualification


__all__ = ["close_strategy_feedback_loop"]
