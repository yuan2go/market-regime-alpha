from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest

from market_regime_alpha.application.continuous_research.composition import (
    CONTINUOUS_CHILD_ORDER,
    ExistingResearchServiceComposition,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.core.identity import ArtifactId


HASH = "sha256:" + "1" * 64


def _request() -> ChildExecutionRequest:
    return ChildExecutionRequest(
        trading_date=date(2026, 8, 6),
        as_of_time=datetime(2026, 8, 6, 6, 42, tzinfo=timezone.utc),
        run_id=ArtifactId("composition-run"),
        tick_id=ArtifactId("composition-tick"),
        tick_sequence=1,
        claim_id="composition-claim",
        fencing_token=1,
        tick_version=2,
        lease_expires_at=datetime(2026, 8, 6, 7, 0, tzinfo=timezone.utc),
        provider_attempt_id=1,
        source_manifest_id=ArtifactId("composition-manifest"),
        source_manifest_hash=HASH,
        evidence_commit_id=ArtifactId("composition-evidence"),
        evidence_commit_hash=HASH,
        decision_id=ArtifactId("composition-decision"),
        decision_hash=HASH,
        input_references=(
            RuntimeArtifactReference("EVIDENCE", ArtifactId("input"), HASH),
        ),
        configuration_references=(
            RuntimeArtifactReference(
                "CONFIGURATION", ArtifactId("configuration"), HASH
            ),
        ),
    )


@dataclass
class Delegate:
    child_kind: ContinuousChildKind
    call_count: int = 0
    durable: ChildExecutionResult | None = None
    seen_input_kinds: tuple[str, ...] = ()

    def lookup(self, request: ChildExecutionRequest) -> ChildExecutionResult | None:
        return self.durable

    def execute(self, request: ChildExecutionRequest) -> ChildExecutionResult:
        self.call_count += 1
        self.seen_input_kinds = tuple(
            reference.reference_kind for reference in request.input_references
        )
        self.durable = ChildExecutionResult(
            child_kind=self.child_kind,
            child_run_id=ArtifactId(f"{self.child_kind.value}-run"),
            child_receipt_id=ArtifactId(f"{self.child_kind.value}-receipt"),
            child_receipt_hash=HASH,
            child_artifact_id=ArtifactId(f"{self.child_kind.value}-artifact"),
            child_artifact_hash=HASH,
            input_references=request.input_references,
            configuration_references=request.configuration_references,
        )
        return self.durable


def test_composition_delegates_to_each_existing_service_and_reuses_receipts() -> None:
    delegates = {kind: Delegate(kind) for kind in ContinuousChildKind}
    composition = ExistingResearchServiceComposition(delegates=delegates)

    first = composition.execute_children(_request())
    second = composition.execute_children(_request())

    assert first == second
    assert all(delegate.call_count == 1 for delegate in delegates.values())
    assert composition.lookup_children(_request()) == first
    assert tuple(result.child_kind for result in first) == CONTINUOUS_CHILD_ORDER
    assert "FEATURE_MATERIALIZATION_OUTPUT" in delegates[
        ContinuousChildKind.STATE_SYSTEM
    ].seen_input_kinds
    assert "STATE_SYSTEM_OUTPUT" in delegates[
        ContinuousChildKind.CONTROLLED_OPERATION
    ].seen_input_kinds


def test_composition_rejects_a_parallel_partial_chain() -> None:
    with pytest.raises(ValueError, match="every existing child service"):
        ExistingResearchServiceComposition(
            delegates={
                ContinuousChildKind.DAILY_DATASET: Delegate(
                    ContinuousChildKind.DAILY_DATASET
                )
            }
        )
