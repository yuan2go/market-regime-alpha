from __future__ import annotations

from datetime import UTC, datetime

from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
    ResearchStatement,
    ResearchStatementKind,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


def _ref(kind: str, value: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, ArtifactId(value), "sha256:" + value[-1] * 64)


def test_phase_ii_evidence_keeps_typed_claims_and_engineering_ceiling() -> None:
    evidence = HistoricalResearchEvidence.create(
        run_id=ArtifactId("run-a"),
        command_hash="sha256:" + "a" * 64,
        experiment_reference=_ref("RESEARCH_EXPERIMENT_DEFINITION", "experiment-a"),
        evidence_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        research_question="Can the intraday values be independently reproduced?",
        classification=ResearchFinding.INCONCLUSIVE,
        rationale="Physical package is unavailable.",
        source_references=(_ref("NORMALIZED_DATASET", "dataset-a"),),
        metrics=(),
        payload={"status": "INCONCLUSIVE"},
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        statements=(
            ResearchStatement(
                ResearchStatementKind.FACT,
                "PostgreSQL owner replay is deterministic.",
            ),
            ResearchStatement(
                ResearchStatementKind.INVALIDATION_CONDITION,
                "Any Feature mismatch invalidates the hypothesis.",
            ),
        ),
    )

    restored = HistoricalResearchEvidence.from_canonical_dict(
        evidence.to_canonical_dict()
    )

    assert restored == evidence
    assert {item.statement_kind for item in evidence.statements}.issuperset(
        {
            ResearchStatementKind.FACT,
            ResearchStatementKind.RESEARCH_RESULT,
            ResearchStatementKind.LIMITATION,
            ResearchStatementKind.INVALIDATION_CONDITION,
        }
    )
    assert "FORMAL_OOS_FALSE" in evidence.limitations
