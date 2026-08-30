from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.application.service import ActorType
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    ArtifactVerificationRecord,
    AttemptClaim,
    ByteVerification,
    ReceiptRecord,
)
from market_regime_alpha.selection.application.candidates import (
    CandidateApplication,
    replay_concurrent_success,
)
from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateArtifactBinding as PolicyArtifactBinding,
    CandidateCellStatus,
    CandidateDatasetPopulation,
    CandidatePopulationCell,
    CandidatePopulationRow,
)
from market_regime_alpha.selection.domain.candidate_policy import (
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    DesirabilityDirection,
)
from market_regime_alpha.selection.domain.candidate_ranking import (
    build_candidate_set as build_ranking_plan,
)
from market_regime_alpha.selection.domain.candidate_results import (
    CandidateRankingPlan,
    candidate_result_content_sha256 as compute_candidate_result_content_sha256,
)
from market_regime_alpha.selection.ports.candidate_artifacts import (
    CandidateArtifactBinding,
)
from market_regime_alpha.selection.ports.candidate_repository import (
    CandidatePersistenceReconciliation,
    CandidateSetBinding,
)
from market_regime_alpha.selection.ports.research_inputs import (
    CandidateDatasetDependency,
    CandidateFeatureDependency,
    CandidatePopulationDependency,
    CandidatePreparedResearchInput,
    CandidateResearchDependencySnapshot,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import DecisionTime


_H1 = "1" * 64
_H2 = "2" * 64
_H3 = "3" * 64
_H4 = "4" * 64
_H5 = "5" * 64
_H6 = "6" * 64


def _uuid(number: int) -> UUID:
    return UUID(int=number)


def _policy() -> CandidatePolicy:
    policy_id = _uuid(100)
    return CandidatePolicy(
        candidate_policy_id=policy_id,
        policy_code="candidate_v1",
        version=1,
        code_artifact=PolicyArtifactBinding(_uuid(101), _H1, 10),
        config_artifact=PolicyArtifactBinding(_uuid(102), _H2, 20),
        requested_top_k=1,
        components=(
            CandidatePolicyComponent(
                candidate_policy_component_id=_uuid(103),
                candidate_policy_id=policy_id,
                component_code="quality",
                ordinal=1,
                feature_definition_id=_uuid(104),
                feature_content_sha256=_H3,
                feature_value_type=CandidateFeatureValueType.DECIMAL,
                direction=DesirabilityDirection.HIGHER_IS_BETTER,
                declared_weight=Decimal("1"),
            ),
        ),
    )


def _prepared() -> CandidatePreparedResearchInput:
    dataset_id = _uuid(200)
    dataset = CandidateDatasetDependency(
        dataset_id=dataset_id,
        content_sha256=_H4,
        decision_time=DecisionTime(datetime(2026, 8, 28, 6, 30, tzinfo=UTC)),
        universe_revision_id=_uuid(201),
        eligibility_policy_id=_uuid(202),
        row_count=1,
        feature_count=1,
        source_count=3,
        cell_count=1,
        available_cell_count=1,
        missing_cell_count=0,
        unknown_cell_count=0,
        stale_cell_count=0,
        conflict_cell_count=0,
        dataset_source_lineage_sha256=_H6,
        manifest_artifact=CandidateArtifactBinding(_uuid(203), _H5, 30),
        code_artifact=CandidateArtifactBinding(_uuid(204), _H1, 10),
        config_artifact=CandidateArtifactBinding(_uuid(205), _H2, 20),
    )
    features = (
        CandidateFeatureDependency(
            feature_definition_id=_uuid(104),
            content_sha256=_H3,
            value_type="DECIMAL",
        ),
    )
    population = (
        CandidatePopulationDependency(
            population_dataset_source_id=_uuid(206),
            instrument_id=_uuid(207),
        ),
    )
    return CandidatePreparedResearchInput(
        dataset=dataset,
        features=features,
        population=population,
        rows=(
            CandidatePopulationRow(
                instrument_id=_uuid(207),
                dataset_population_source_id=_uuid(206),
                cells=(
                    CandidatePopulationCell(
                        feature_definition_id=_uuid(104),
                        status=CandidateCellStatus.AVAILABLE,
                        value=Decimal("12.5"),
                        reason_code="OBSERVED",
                        cell_source_lineage_hash=_H6,
                    ),
                ),
            ),
        ),
        manifest_verification=ByteVerification(
            result="VERIFIED",
            observed_exists=True,
            observed_size_bytes=30,
            observed_sha256=_H5,
        ),
        dependency_sha256=_H6,
    )


def _snapshot(
    prepared: CandidatePreparedResearchInput,
) -> CandidateResearchDependencySnapshot:
    return CandidateResearchDependencySnapshot(
        dataset=prepared.dataset,
        features=prepared.features,
        population=prepared.population,
        dependency_sha256=prepared.dependency_sha256,
    )


def _ranking_plan(
    policy: CandidatePolicy,
    prepared: CandidatePreparedResearchInput,
) -> CandidateRankingPlan:
    return build_ranking_plan(
        policy=policy,
        dataset=CandidateDatasetPopulation(
            dataset_id=prepared.dataset.dataset_id,
            dataset_content_sha256=prepared.dataset.content_sha256,
            decision_time=prepared.dataset.decision_time,
            universe_revision_id=prepared.dataset.universe_revision_id,
            eligibility_policy_id=prepared.dataset.eligibility_policy_id,
            rows=prepared.rows,
            dependency_sha256=prepared.dependency_sha256,
        ),
    )


def _claim(number: int = 300) -> AttemptClaim:
    now = datetime(2026, 8, 28, 7, tzinfo=UTC)
    return AttemptClaim(
        attempt_id=_uuid(number),
        run_id=_uuid(number + 1),
        step_id=_uuid(number + 2),
        step_key="BUILD_CANDIDATE_SET",
        attempt_no=1,
        fence_token=7,
        lease_owner="candidate-test",
        lease_until=now + timedelta(minutes=5),
    )


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="candidate-test",
        reason_code="WP07_TEST",
    )


def _new_receipt(receipt_id: UUID) -> ReceiptRecord:
    return ReceiptRecord(
        receipt_id=receipt_id,
        status="STARTED",
        request_hash=_H1,
        result_aggregate_kind=None,
        result_aggregate_id=None,
        result_aggregate_version=None,
        result_hash=None,
        error_code=None,
        is_new=True,
    )


@dataclass
class _ReceiptPlan:
    receipt: ReceiptRecord


class _SpyReceipts:
    def __init__(
        self,
        events: list[str],
        plan: _ReceiptPlan,
        starts: list[dict[str, Any]],
    ) -> None:
        self._events = events
        self._plan = plan
        self._starts = starts

    def start(self, **kwargs: Any) -> ReceiptRecord:
        self._events.append("receipts.start")
        self._starts.append(kwargs)
        return self._plan.receipt

    def succeed(self, **kwargs: Any) -> None:
        self._events.append("receipts.succeed")

    def fail(self, **kwargs: Any) -> None:
        self._events.append("receipts.fail")


class _SpyAudit:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def append(self, **kwargs: Any) -> None:
        self._events.append("audit.append")


class _SpyRuntimeFinalization:
    def __init__(
        self,
        events: list[str],
        *,
        stale: bool = False,
    ) -> None:
        self._events = events
        self._stale = stale

    def lock_live(self, claim: AttemptClaim) -> None:
        self._events.append("runtime.lock_live")
        if self._stale:
            raise StaleFenceError("stale Candidate fence")

    def succeed(self, claim: AttemptClaim, **kwargs: Any) -> tuple[int, int]:
        self._events.append("runtime.succeed")
        return 1, 1

    def fail(self, claim: AttemptClaim, **kwargs: Any) -> tuple[str, int, int]:
        self._events.append("runtime.fail")
        return "FAILED", 1, 1


class _SpyArtifacts:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def lock_exact_identity(self, binding: Any) -> ArtifactRecord:
        self._events.append("artifacts.lock_exact_identity")
        return self._record(binding)

    def require_exact(self, binding: Any, *, lock: bool) -> ArtifactRecord:
        self._events.append(f"artifacts.require_exact:{lock}")
        return self._record(binding)

    def record_verification(self, **kwargs: Any) -> ArtifactVerificationRecord:
        self._events.append("artifacts.record_verification")
        artifact = kwargs["artifact"]
        verification = kwargs["verification"]
        return ArtifactVerificationRecord(
            verification_id=kwargs["verification_id"],
            artifact_id=artifact.artifact_id,
            result=verification.result,
            observed_exists=verification.observed_exists,
            observed_size_bytes=verification.observed_size_bytes,
            observed_sha256=verification.observed_sha256,
        )

    @staticmethod
    def _record(binding: Any) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=binding.artifact_id,
            content_sha256=str(binding.content_sha256),
            size_bytes=binding.size_bytes,
            media_type="application/octet-stream",
            locator=f"artifact://{binding.artifact_id}",
            integrity_state="VERIFIED",
            retention_until=None,
            pin_reason_code=None,
        )


class _SpyDependencies:
    def __init__(
        self,
        events: list[str],
        prepared: CandidatePreparedResearchInput,
        *,
        snapshot_override: CandidateResearchDependencySnapshot | None = None,
    ) -> None:
        self._events = events
        self._prepared = prepared
        self._snapshot_override = snapshot_override

    def feature_dependencies(
        self,
        required_features: tuple[CandidateFeatureDependency, ...],
        *,
        lock: bool,
    ) -> tuple[CandidateFeatureDependency, ...]:
        self._events.append(f"dependencies.features:{lock}")
        return self._prepared.features

    def snapshot(
        self,
        *,
        dataset_id: UUID,
        required_features: tuple[CandidateFeatureDependency, ...],
        lock: bool,
    ) -> CandidateResearchDependencySnapshot:
        self._events.append(f"dependencies.snapshot:{lock}")
        return self._snapshot_override or _snapshot(self._prepared)


class _SpyCandidates:
    def __init__(
        self,
        events: list[str],
        policy: CandidatePolicy,
        *,
        reconciliation_override: CandidatePersistenceReconciliation | None = None,
    ) -> None:
        self._events = events
        self._policy = policy
        self._plan: Any | None = None
        self._persisted_override: Any | None = None
        self._reconciliation_override = reconciliation_override

    def insert_policy(self, policy: CandidatePolicy) -> None:
        self._events.append("candidates.insert_policy")
        self._policy = policy

    def policy(self, candidate_policy_id: UUID, *, lock: bool) -> CandidatePolicy:
        self._events.append(f"candidates.policy:{lock}")
        return self._policy

    def insert_candidate_set(self, plan: Any) -> None:
        self._events.append("candidates.insert_candidate_set")
        self._plan = plan

    def lock_candidate_set_identity(self, candidate_set_id: UUID) -> None:
        self._events.append("candidates.lock_candidate_set_identity")

    def persisted_candidate_set(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        lock: bool,
    ) -> Any | None:
        self._events.append(f"candidates.persisted_candidate_set:{lock}")
        return self._persisted_override or self._plan

    def candidate_set_binding(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        lock: bool,
    ) -> CandidateSetBinding | None:
        self._events.append(f"candidates.candidate_set_binding:{lock}")
        if self._plan is None:
            return None
        candidate_set = self._plan.candidate_set
        return CandidateSetBinding(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_policy_id=candidate_set.candidate_policy_id,
            candidate_policy_content_sha256=str(
                candidate_set.candidate_policy_content_sha256
            ),
            dataset_id=candidate_set.dataset_id,
            dataset_content_sha256=str(candidate_set.dataset_content_sha256),
            dependency_sha256=str(candidate_set.dependency_sha256),
            result_sha256=str(candidate_set.result_sha256),
        )

    def reconciliation(
        self,
        candidate_set_id: UUID,
    ) -> CandidatePersistenceReconciliation:
        self._events.append("candidates.reconciliation")
        if self._reconciliation_override is not None:
            return self._reconciliation_override
        assert self._plan is not None
        candidate_set = self._plan.candidate_set
        return CandidatePersistenceReconciliation(
            population_count=candidate_set.population_count,
            selected_count=candidate_set.selected_count,
            ranked_not_selected_count=(
                candidate_set.ranked_not_selected_count
            ),
            unrankable_count=candidate_set.unrankable_count,
            score_component_count=candidate_set.score_component_count,
            population_reconciled=True,
            rankable_reconciled=True,
            component_matrix_reconciled=True,
            ranking_reconciled=True,
        )


class _SpyUow:
    def __init__(
        self,
        *,
        name: str,
        events: list[str],
        starts: list[dict[str, Any]],
        receipt: ReceiptRecord,
        policy: CandidatePolicy,
        prepared: CandidatePreparedResearchInput,
        stale: bool = False,
        snapshot_override: CandidateResearchDependencySnapshot | None = None,
    ) -> None:
        self._name = name
        self._events = events
        self.receipts = _SpyReceipts(
            events,
            _ReceiptPlan(receipt),
            starts,
        )
        self.audit = _SpyAudit(events)
        self.runtime_finalization = _SpyRuntimeFinalization(events, stale=stale)
        self.candidate_artifacts = _SpyArtifacts(events)
        self.research_dependencies = _SpyDependencies(
            events,
            prepared,
            snapshot_override=snapshot_override,
        )
        self.candidates = _SpyCandidates(events, policy)
        self.committed = False
        self.active = False

    def __enter__(self) -> _SpyUow:
        self._events.append(f"{self._name}.enter")
        self.active = True
        return self

    def __exit__(self, *args: Any) -> None:
        self.active = False
        self._events.append(f"{self._name}.exit")

    def commit(self) -> None:
        self._events.append(f"{self._name}.commit")
        self.committed = True


class _QueuedProvider:
    def __init__(self, uows: list[_SpyUow]) -> None:
        self._uows = uows
        self.calls = 0
        self.read_only_calls: list[bool] = []

    def __call__(self, *, read_only: bool = False) -> _SpyUow:
        if self.calls >= len(self._uows):
            raise AssertionError("Candidate application opened an unexpected UoW")
        uow = self._uows[self.calls]
        self.calls += 1
        self.read_only_calls.append(read_only)
        return uow


class _SpyLoader:
    def __init__(
        self,
        events: list[str],
        prepared: CandidatePreparedResearchInput,
    ) -> None:
        self._events = events
        self._prepared = prepared
        self.calls = 0

    def prepare(
        self,
        *,
        dataset_id: UUID,
        required_features: tuple[CandidateFeatureDependency, ...],
    ) -> CandidatePreparedResearchInput:
        self.calls += 1
        self._events.append("loader.prepare")
        return self._prepared


def _id_factory() -> Callable[[], UUID]:
    values = iter(_uuid(number) for number in range(1_000, 1_100))
    return lambda: next(values)


def test_register_candidate_policy_is_one_fenced_atomic_command() -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    uow = _SpyUow(
        name="register",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(400)),
        policy=policy,
        prepared=prepared,
    )
    app = CandidateApplication(
        _SpyLoader(events, prepared),
        _QueuedProvider([uow]),
        id_factory=_id_factory(),
    )

    result = app.register_candidate_policy(
        policy,
        _context("register-policy"),
        runtime_claim=_claim(),
    )

    assert result.aggregate_kind == "CANDIDATE_POLICY"
    assert result.aggregate_id == str(policy.candidate_policy_id)
    assert result.aggregate_version == 1
    assert result.replayed is False
    assert starts[0]["request_hash"] == canonical_json_sha256(policy)
    assert events == [
        "register.enter",
        "runtime.lock_live",
        "receipts.start",
        "artifacts.require_exact:True",
        "artifacts.require_exact:True",
        "dependencies.features:True",
        "candidates.insert_policy",
        "candidates.policy:False",
        "receipts.succeed",
        "audit.append",
        "runtime.succeed",
        "register.commit",
        "register.exit",
    ]


def test_register_candidate_policy_replay_does_not_rewrite_dependencies() -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    result_hash = canonical_json_sha256(
        {
            "candidate_policy_id": policy.candidate_policy_id,
            "content_sha256": policy.content_sha256,
            "version": policy.version,
        }
    )
    replay = _SpyUow(
        name="replay",
        events=events,
        starts=starts,
        receipt=ReceiptRecord(
            receipt_id=_uuid(405),
            status="SUCCEEDED",
            request_hash=canonical_json_sha256(policy),
            result_aggregate_kind="CANDIDATE_POLICY",
            result_aggregate_id=str(policy.candidate_policy_id),
            result_aggregate_version=policy.version,
            result_hash=result_hash,
            error_code=None,
            is_new=False,
        ),
        policy=policy,
        prepared=prepared,
    )
    loader = _SpyLoader(events, prepared)
    app = CandidateApplication(
        loader,
        _QueuedProvider([replay]),
        id_factory=_id_factory(),
    )

    result = app.register_candidate_policy(
        policy,
        _context("register-policy-replay"),
        runtime_claim=_claim(),
    )

    assert result.replayed is True
    assert result.result_hash == result_hash
    assert loader.calls == 0
    assert events == [
        "replay.enter",
        "runtime.lock_live",
        "receipts.start",
        "candidates.policy:False",
        "runtime.succeed",
        "replay.commit",
        "replay.exit",
    ]


def test_build_prepares_and_ranks_between_preflight_and_final_uows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    preflight = _SpyUow(
        name="preflight",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(410)),
        policy=policy,
        prepared=prepared,
    )
    final = _SpyUow(
        name="final",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(411)),
        policy=policy,
        prepared=prepared,
    )
    loader = _SpyLoader(events, prepared)
    def rank_outside_uow(**kwargs: Any) -> Any:
        assert preflight.active is False
        assert final.active is False
        events.append("ranking.compute")
        return build_ranking_plan(**kwargs)

    monkeypatch.setattr(
        "market_regime_alpha.selection.application.candidates.rank_candidate_set",
        rank_outside_uow,
    )
    app = CandidateApplication(
        loader,
        _QueuedProvider([preflight, final]),
        id_factory=_id_factory(),
    )

    result = app.build_candidate_set(
        policy.candidate_policy_id,
        prepared.dataset.dataset_id,
        _context("build-candidate-set"),
        runtime_claim=_claim(),
    )

    assert result.aggregate_kind == "CANDIDATE_SET"
    assert result.replayed is False
    assert preflight.committed is False
    assert final.committed is True
    assert loader.calls == 1
    assert starts[0]["request_hash"] == starts[1]["request_hash"]
    assert starts[0]["request_hash"] == canonical_json_sha256(
        {
            "algorithm_contract": {
                "missing_policy": policy.missing_policy,
                "normalization_method": policy.normalization_method,
                "projection_method": policy.projection_method,
                "projection_version": policy.projection_version,
                "rank_method": policy.rank_method,
                "score_semantics": policy.score_semantics,
                "selection_method": policy.selection_method,
                "tie_policy": policy.tie_policy,
            },
            "candidate_policy_content_sha256": policy.content_sha256,
            "candidate_policy_id": policy.candidate_policy_id,
            "dataset_dependency_sha256": prepared.dependency_sha256,
            "dataset_id": prepared.dataset.dataset_id,
        }
    )
    assert events == [
        "preflight.enter",
        "runtime.lock_live",
        "candidates.policy:False",
        "dependencies.snapshot:False",
        "receipts.start",
        "preflight.exit",
        "loader.prepare",
        "ranking.compute",
        "final.enter",
        "runtime.lock_live",
        "candidates.lock_candidate_set_identity",
        "candidates.policy:True",
        "artifacts.require_exact:True",
        "artifacts.require_exact:True",
        "dependencies.snapshot:True",
        "artifacts.require_exact:True",
        "artifacts.require_exact:True",
        "artifacts.require_exact:True",
        "candidates.insert_candidate_set",
        "candidates.persisted_candidate_set:False",
        "candidates.reconciliation",
        "receipts.start",
        "artifacts.record_verification",
        "receipts.succeed",
        "audit.append",
        "runtime.succeed",
        "final.commit",
        "final.exit",
    ]


def test_build_requires_runtime_claim_before_opening_any_uow_or_reading_artifacts() -> None:
    events: list[str] = []
    prepared = _prepared()
    provider = _QueuedProvider([])
    loader = _SpyLoader(events, prepared)
    app = CandidateApplication(loader, provider, id_factory=_id_factory())

    with pytest.raises(TypeError, match="runtime_claim"):
        app.build_candidate_set(
            _policy().candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("candidate-build-without-runtime-claim"),
        )
    invalid_claim: Any = None
    with pytest.raises(TypeError, match="runtime_claim"):
        app.build_candidate_set(
            _policy().candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("candidate-build-with-null-runtime-claim"),
            runtime_claim=invalid_claim,
        )

    assert provider.calls == 0
    assert loader.calls == 0
    assert events == []


def test_unrepresentable_projection_fails_before_final_business_uow() -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy_id = _uuid(150)
    policy = CandidatePolicy(
        candidate_policy_id=policy_id,
        policy_code="candidate_projection_boundary",
        version=1,
        code_artifact=PolicyArtifactBinding(_uuid(151), _H1, 10),
        config_artifact=PolicyArtifactBinding(_uuid(152), _H2, 20),
        requested_top_k=1,
        components=(
            CandidatePolicyComponent(
                candidate_policy_component_id=_uuid(153),
                candidate_policy_id=policy_id,
                component_code="dominant",
                ordinal=1,
                feature_definition_id=_uuid(104),
                feature_content_sha256=_H3,
                feature_value_type=CandidateFeatureValueType.DECIMAL,
                direction=DesirabilityDirection.HIGHER_IS_BETTER,
                declared_weight=Decimal("1E+131071"),
            ),
            CandidatePolicyComponent(
                candidate_policy_component_id=_uuid(154),
                candidate_policy_id=policy_id,
                component_code="tiny",
                ordinal=2,
                feature_definition_id=_uuid(105),
                feature_content_sha256=_H4,
                feature_value_type=CandidateFeatureValueType.DECIMAL,
                direction=DesirabilityDirection.HIGHER_IS_BETTER,
                declared_weight=Decimal("1E-16383"),
            ),
        ),
    )
    base = _prepared()
    prepared = replace(
        base,
        dataset=replace(
            base.dataset,
            feature_count=2,
            cell_count=2,
            available_cell_count=2,
        ),
        features=(
            *base.features,
            CandidateFeatureDependency(
                feature_definition_id=_uuid(105),
                content_sha256=_H4,
                value_type="DECIMAL",
            ),
        ),
        rows=(
            replace(
                base.rows[0],
                cells=(
                    *base.rows[0].cells,
                    CandidatePopulationCell(
                        feature_definition_id=_uuid(105),
                        status=CandidateCellStatus.AVAILABLE,
                        value=Decimal("11"),
                        reason_code="OBSERVED",
                        cell_source_lineage_hash=_H6,
                    ),
                ),
            ),
        ),
    )
    preflight = _SpyUow(
        name="projection-preflight",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(155)),
        policy=policy,
        prepared=prepared,
    )
    failure = _SpyUow(
        name="projection-failure",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(156)),
        policy=policy,
        prepared=prepared,
    )
    provider = _QueuedProvider([preflight, failure])
    app = CandidateApplication(
        _SpyLoader(events, prepared),
        provider,
        id_factory=_id_factory(),
    )

    with pytest.raises(
        ValueError,
        match="Candidate Decimal projection exceeds PostgreSQL numeric physical limits",
    ):
        app.build_candidate_set(
            policy.candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("candidate-projection-boundary"),
            runtime_claim=_claim(),
        )

    assert provider.calls == 2
    assert preflight.committed is False
    assert failure.committed is True
    assert not any("candidates.insert_candidate_set" in item for item in events)
    assert events == [
        "projection-preflight.enter",
        "runtime.lock_live",
        "candidates.policy:False",
        "dependencies.snapshot:False",
        "receipts.start",
        "projection-preflight.exit",
        "loader.prepare",
        "projection-failure.enter",
        "runtime.lock_live",
        "receipts.start",
        "receipts.fail",
        "audit.append",
        "runtime.fail",
        "projection-failure.commit",
        "projection-failure.exit",
    ]


def test_fresh_build_and_replay_share_the_exact_persisted_result_hash_payload() -> None:
    policy = _policy()
    prepared = _prepared()
    plan = _ranking_plan(policy, prepared)

    recomputed = compute_candidate_result_content_sha256(
        policy=policy,
        candidate_set_id=plan.candidate_set_id,
        dataset_id=plan.candidate_set.dataset_id,
        dataset_content_sha256=plan.candidate_set.dataset_content_sha256,
        dependency_sha256=plan.candidate_set.dependency_sha256,
        projection_precision=plan.candidate_set.decimal_projection_precision,
        candidates=plan.candidates,
        score_components=plan.score_components,
        component_diagnostics=plan.component_diagnostics,
    )
    drifted_scores = tuple(
        replace(score, contribution=Decimal("0.4"))
        for score in plan.score_components
    )
    drifted = compute_candidate_result_content_sha256(
        policy=policy,
        candidate_set_id=plan.candidate_set_id,
        dataset_id=plan.candidate_set.dataset_id,
        dataset_content_sha256=plan.candidate_set.dataset_content_sha256,
        dependency_sha256=plan.candidate_set.dependency_sha256,
        projection_precision=plan.candidate_set.decimal_projection_precision,
        candidates=plan.candidates,
        score_components=drifted_scores,
        component_diagnostics=plan.component_diagnostics,
    )

    assert recomputed == plan.result_sha256
    assert drifted != plan.result_sha256


def test_build_rejects_legal_persisted_contribution_drift_before_receipt() -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    canonical_plan = _ranking_plan(policy, prepared)
    drifted_plan = replace(
        canonical_plan,
        score_components=tuple(
            replace(score, contribution=Decimal("0.4"))
            for score in canonical_plan.score_components
        ),
    )
    preflight = _SpyUow(
        name="preflight",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(415)),
        policy=policy,
        prepared=prepared,
    )
    final = _SpyUow(
        name="final-drift",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(416)),
        policy=policy,
        prepared=prepared,
    )
    final.candidates._persisted_override = drifted_plan
    failure = _SpyUow(
        name="failure",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(417)),
        policy=policy,
        prepared=prepared,
    )
    app = CandidateApplication(
        _SpyLoader(events, prepared),
        _QueuedProvider([preflight, final, failure]),
        id_factory=_id_factory(),
    )

    with pytest.raises(ArtifactIntegrityError, match="does not reconcile"):
        app.build_candidate_set(
            policy.candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("build-final-contribution-drift"),
            runtime_claim=_claim(),
        )

    assert preflight.committed is False
    assert final.committed is False
    assert failure.committed is True
    assert len(starts) == 2
    assert events.index("candidates.insert_candidate_set") < events.index(
        "candidates.persisted_candidate_set:False"
    )
    assert events.index("final-drift.exit") < events.index("failure.enter")


def test_build_replay_verifies_hash_outside_read_uow_without_ranking_then_finalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    persisted_plan = _ranking_plan(policy, prepared)
    existing_set_id = persisted_plan.candidate_set_id
    result_hash = str(persisted_plan.result_sha256)
    receipt = ReceiptRecord(
        receipt_id=_uuid(421),
        status="SUCCEEDED",
        request_hash=_H1,
        result_aggregate_kind="CANDIDATE_SET",
        result_aggregate_id=str(existing_set_id),
        result_aggregate_version=1,
        result_hash=result_hash,
        error_code=None,
        is_new=False,
    )
    replay_uow = _SpyUow(
        name="replay",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_uow.candidates._plan = persisted_plan
    replay_read = _SpyUow(
        name="replay-read",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_read.candidates._plan = persisted_plan
    replay_final = _SpyUow(
        name="replay-final",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_final.candidates._plan = persisted_plan

    def replay_must_not_rank(**kwargs: Any) -> Any:
        raise AssertionError("exact Candidate replay must not invoke ranking")

    def hash_outside_every_uow(**kwargs: Any) -> Any:
        assert replay_uow.active is False
        assert replay_read.active is False
        assert replay_final.active is False
        events.append("result-hash.compute")
        return compute_candidate_result_content_sha256(**kwargs)

    monkeypatch.setattr(
        "market_regime_alpha.selection.application.candidates.rank_candidate_set",
        replay_must_not_rank,
    )
    monkeypatch.setattr(
        "market_regime_alpha.selection.application.candidates.candidate_result_content_sha256",
        hash_outside_every_uow,
    )
    loader = _SpyLoader(events, prepared)
    provider = _QueuedProvider([replay_uow, replay_read, replay_final])
    app = CandidateApplication(
        loader,
        provider,
        id_factory=_id_factory(),
    )

    result = app.build_candidate_set(
        policy.candidate_policy_id,
        prepared.dataset.dataset_id,
        _context("build-replay"),
        runtime_claim=_claim(),
    )

    assert result.aggregate_id == str(existing_set_id)
    assert result.result_hash == result_hash
    assert result.replayed is True
    assert loader.calls == 0
    assert replay_uow.committed is False
    assert replay_read.committed is False
    assert replay_final.committed is True
    assert provider.read_only_calls == [False, True, False]
    assert events == [
        "replay.enter",
        "runtime.lock_live",
        "candidates.policy:False",
        "dependencies.snapshot:False",
        "receipts.start",
        "candidates.candidate_set_binding:False",
        "replay.exit",
        "replay-read.enter",
        "candidates.persisted_candidate_set:False",
        "candidates.reconciliation",
        "replay-read.exit",
        "result-hash.compute",
        "replay-final.enter",
        "runtime.lock_live",
        "candidates.policy:True",
        "artifacts.require_exact:True",
        "artifacts.require_exact:True",
        "dependencies.snapshot:True",
        "artifacts.require_exact:True",
        "artifacts.require_exact:True",
        "artifacts.require_exact:True",
        "receipts.start",
        "candidates.candidate_set_binding:True",
        "candidates.persisted_candidate_set:True",
        "candidates.reconciliation",
        "runtime.succeed",
        "replay-final.commit",
        "replay-final.exit",
    ]


def test_build_replay_rejects_legal_contribution_drift_after_read_uow_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    canonical_plan = _ranking_plan(policy, prepared)
    drifted_plan = replace(
        canonical_plan,
        score_components=tuple(
            replace(score, contribution=Decimal("0.4"))
            for score in canonical_plan.score_components
        ),
    )
    receipt = ReceiptRecord(
        receipt_id=_uuid(425),
        status="SUCCEEDED",
        request_hash=_H1,
        result_aggregate_kind="CANDIDATE_SET",
        result_aggregate_id=str(canonical_plan.candidate_set_id),
        result_aggregate_version=1,
        result_hash=str(canonical_plan.result_sha256),
        error_code=None,
        is_new=False,
    )
    replay_uow = _SpyUow(
        name="replay-drift",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_uow.candidates._plan = canonical_plan
    replay_read = _SpyUow(
        name="replay-drift-read",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_read.candidates._plan = canonical_plan
    replay_read.candidates._persisted_override = drifted_plan
    failure_uow = _SpyUow(
        name="replay-drift-failure",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(426)),
        policy=policy,
        prepared=prepared,
    )

    def replay_must_not_rank(**kwargs: Any) -> Any:
        raise AssertionError("exact Candidate replay must not invoke ranking")

    def hash_after_read_rollback(**kwargs: Any) -> Any:
        assert replay_uow.active is False
        assert replay_read.active is False
        events.append("result-hash.compute")
        return compute_candidate_result_content_sha256(**kwargs)

    monkeypatch.setattr(
        "market_regime_alpha.selection.application.candidates.rank_candidate_set",
        replay_must_not_rank,
    )
    monkeypatch.setattr(
        "market_regime_alpha.selection.application.candidates.candidate_result_content_sha256",
        hash_after_read_rollback,
    )
    loader = _SpyLoader(events, prepared)
    provider = _QueuedProvider([replay_uow, replay_read, failure_uow])
    app = CandidateApplication(
        loader,
        provider,
        id_factory=_id_factory(),
    )

    with pytest.raises(ArtifactIntegrityError, match="does not reconcile"):
        app.build_candidate_set(
            policy.candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("build-replay-drift"),
            runtime_claim=_claim(),
        )

    assert loader.calls == 0
    assert replay_uow.committed is False
    assert replay_read.committed is False
    assert failure_uow.committed is True
    assert provider.read_only_calls == [False, True, False]
    assert events == [
        "replay-drift.enter",
        "runtime.lock_live",
        "candidates.policy:False",
        "dependencies.snapshot:False",
        "receipts.start",
        "candidates.candidate_set_binding:False",
        "replay-drift.exit",
        "replay-drift-read.enter",
        "candidates.persisted_candidate_set:False",
        "candidates.reconciliation",
        "replay-drift-read.exit",
        "result-hash.compute",
        "replay-drift-failure.enter",
        "runtime.lock_live",
        "receipts.start",
        "receipts.fail",
        "audit.append",
        "runtime.fail",
        "replay-drift-failure.commit",
        "replay-drift-failure.exit",
    ]


def test_build_replay_rejects_sql_legal_boundary_summary_drift() -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    canonical_plan = _ranking_plan(policy, prepared)
    drifted_plan = replace(
        canonical_plan,
        candidate_set=replace(
            canonical_plan.candidate_set,
            boundary_score=Decimal("0.4"),
        ),
    )
    receipt = ReceiptRecord(
        receipt_id=_uuid(429),
        status="SUCCEEDED",
        request_hash=_H1,
        result_aggregate_kind="CANDIDATE_SET",
        result_aggregate_id=str(canonical_plan.candidate_set_id),
        result_aggregate_version=1,
        result_hash=str(canonical_plan.result_sha256),
        error_code=None,
        is_new=False,
    )
    replay_probe = _SpyUow(
        name="replay-boundary",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_probe.candidates._plan = canonical_plan
    replay_read = _SpyUow(
        name="replay-boundary-read",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_read.candidates._plan = canonical_plan
    replay_read.candidates._persisted_override = drifted_plan
    failure = _SpyUow(
        name="replay-boundary-failure",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(430)),
        policy=policy,
        prepared=prepared,
    )
    provider = _QueuedProvider([replay_probe, replay_read, failure])
    app = CandidateApplication(
        _SpyLoader(events, prepared),
        provider,
        id_factory=_id_factory(),
    )

    with pytest.raises(ArtifactIntegrityError, match="summary"):
        app.build_candidate_set(
            policy.candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("build-replay-boundary-drift"),
            runtime_claim=_claim(),
        )

    assert provider.read_only_calls == [False, True, False]
    assert replay_probe.committed is False
    assert replay_read.committed is False
    assert failure.committed is True
    assert "candidates.candidate_set_binding:False" in events
    assert "candidates.persisted_candidate_set:False" in events


def test_build_replay_revalidates_preflight_dependencies_before_finalizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    persisted_plan = _ranking_plan(policy, prepared)
    receipt = ReceiptRecord(
        receipt_id=_uuid(427),
        status="SUCCEEDED",
        request_hash=_H1,
        result_aggregate_kind="CANDIDATE_SET",
        result_aggregate_id=str(persisted_plan.candidate_set_id),
        result_aggregate_version=1,
        result_hash=str(persisted_plan.result_sha256),
        error_code=None,
        is_new=False,
    )
    replay_uow = _SpyUow(
        name="replay-preflight",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_uow.candidates._plan = persisted_plan
    replay_read = _SpyUow(
        name="replay-preflight-read",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
    )
    replay_read.candidates._plan = persisted_plan
    changed_snapshot = replace(_snapshot(prepared), dependency_sha256=_H5)
    replay_final = _SpyUow(
        name="replay-final-drift",
        events=events,
        starts=starts,
        receipt=receipt,
        policy=policy,
        prepared=prepared,
        snapshot_override=changed_snapshot,
    )
    replay_final.candidates._plan = persisted_plan
    failure_uow = _SpyUow(
        name="replay-final-failure",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(428)),
        policy=policy,
        prepared=prepared,
    )

    def replay_must_not_rank(**kwargs: Any) -> Any:
        raise AssertionError("exact Candidate replay must not invoke ranking")

    monkeypatch.setattr(
        "market_regime_alpha.selection.application.candidates.rank_candidate_set",
        replay_must_not_rank,
    )
    provider = _QueuedProvider(
        [replay_uow, replay_read, replay_final, failure_uow]
    )
    app = CandidateApplication(
        _SpyLoader(events, prepared),
        provider,
        id_factory=_id_factory(),
    )

    with pytest.raises(RuntimeStateConflictError, match="during Candidate replay"):
        app.build_candidate_set(
            policy.candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("build-replay-dependency-drift"),
            runtime_claim=_claim(),
        )

    assert replay_uow.committed is False
    assert replay_read.committed is False
    assert replay_final.committed is False
    assert failure_uow.committed is True
    assert provider.read_only_calls == [False, True, False, False]
    assert events.index("replay-final-drift.exit") < events.index(
        "replay-final-failure.enter"
    )
    assert "artifacts.record_verification" not in events
    assert events[-7:] == [
        "runtime.lock_live",
        "receipts.start",
        "receipts.fail",
        "audit.append",
        "runtime.fail",
        "replay-final-failure.commit",
        "replay-final-failure.exit",
    ]


def test_stale_fence_does_not_open_a_failure_uow() -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    stale = _SpyUow(
        name="stale",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(430)),
        policy=policy,
        prepared=prepared,
        stale=True,
    )
    provider = _QueuedProvider([stale])
    app = CandidateApplication(
        _SpyLoader(events, prepared),
        provider,
        id_factory=_id_factory(),
    )

    with pytest.raises(StaleFenceError):
        app.register_candidate_policy(
            policy,
            _context("stale-register"),
            runtime_claim=_claim(),
        )

    assert provider.calls == 1
    assert stale.committed is False
    assert events == [
        "stale.enter",
        "runtime.lock_live",
        "stale.exit",
    ]


def test_revalidation_failure_rolls_back_then_records_shared_failure() -> None:
    events: list[str] = []
    starts: list[dict[str, Any]] = []
    policy = _policy()
    prepared = _prepared()
    preflight = _SpyUow(
        name="preflight",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(440)),
        policy=policy,
        prepared=prepared,
    )
    changed_snapshot = CandidateResearchDependencySnapshot(
        dataset=prepared.dataset,
        features=prepared.features,
        population=prepared.population,
        dependency_sha256=_H5,
    )
    final = _SpyUow(
        name="final",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(441)),
        policy=policy,
        prepared=prepared,
        snapshot_override=changed_snapshot,
    )
    failure = _SpyUow(
        name="failure",
        events=events,
        starts=starts,
        receipt=_new_receipt(_uuid(442)),
        policy=policy,
        prepared=prepared,
    )
    provider = _QueuedProvider([preflight, final, failure])
    app = CandidateApplication(
        _SpyLoader(events, prepared),
        provider,
        id_factory=_id_factory(),
    )

    with pytest.raises(RuntimeStateConflictError):
        app.build_candidate_set(
            policy.candidate_policy_id,
            prepared.dataset.dataset_id,
            _context("dependency-drift"),
            runtime_claim=_claim(),
        )

    assert preflight.committed is False
    assert final.committed is False
    assert failure.committed is True
    assert starts[0]["request_hash"] == starts[1]["request_hash"]
    assert len(starts) == 2
    assert events.index("final.exit") < events.index("failure.enter")
    assert events[-7:] == [
        "runtime.lock_live",
        "receipts.start",
        "receipts.fail",
        "audit.append",
        "runtime.fail",
        "failure.commit",
        "failure.exit",
    ]


def test_concurrent_success_decorator_retries_through_replay_path() -> None:
    calls = 0

    @replay_concurrent_success
    def command() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            from market_regime_alpha.runtime.application import (
                ConcurrentCommandSucceeded,
            )

            raise ConcurrentCommandSucceeded()
        return "replayed"

    assert command() == "replayed"
    assert calls == 2
