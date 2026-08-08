from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    ContinuousTickStatus,
    ProviderAttemptStatus,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousRunState,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
    ProviderAcquisitionRequest,
    ProviderAcquisitionResult,
    ValidatedEvidencePayload,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.runner import (
    ContinuousResearchTickRunner,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


NOW = datetime(2026, 8, 6, 6, 50, tzinfo=timezone.utc)
HASHES = tuple("sha256:" + character * 64 for character in "123456789abcdef")


def _command() -> ContinuousResearchCommand:
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key="continuous-runner",
        trading_date=date(2026, 8, 6),
        requested_symbols=("600000.SH",),
        trading_calendar_id=ArtifactId("calendar-runner"),
        trading_calendar_hash=HASHES[0],
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("provider-config-runner"),
        provider_configuration_hash=HASHES[1],
        research_configuration_id=ArtifactId("research-config-runner"),
        research_configuration_hash=HASHES[2],
        code_revision="baseline-head",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def _tick(command: ContinuousResearchCommand, index: int) -> RuntimeTickCommand:
    return RuntimeTickCommand.create(
        idempotency_key=f"runner-tick-{index}",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=NOW + timedelta(minutes=index),
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
    )


def _provider_result(material_hash: str) -> ProviderAcquisitionResult:
    return ProviderAcquisitionResult.succeeded(
        completed_at=NOW,
        raw_response_hash=HASHES[3],
        source_manifest_id=ArtifactId("manifest-runner"),
        source_manifest_hash=HASHES[4],
        reason_codes=("VALIDATED_RESPONSE",),
        evidence=ValidatedEvidencePayload(
            evidence_scope="A_SHARE_MINUTE_SCOPE",
            raw_artifact_id=ArtifactId("raw-runner"),
            raw_artifact_hash=HASHES[3],
            evidence_artifact_id=ArtifactId("evidence-runner"),
            evidence_artifact_hash=HASHES[5],
            material_identity_hash=material_hash,
            effective_at=NOW,
            retrieved_at=NOW,
            available_at=NOW,
            as_of_time=NOW,
            evidence_qualification="FREE_DATA_EXPLORATORY",
            limitations=("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"),
            downstream_contract_satisfied=True,
        ),
    )


class ScriptedProvider:
    def __init__(self, results: list[ProviderAcquisitionResult]) -> None:
        self.results = results
        self.call_count = 0

    def acquire(self, request: ProviderAcquisitionRequest) -> ProviderAcquisitionResult:
        self.call_count += 1
        return self.results.pop(0)


class CountingChildren:
    def __init__(self) -> None:
        self.calls: Counter[ContinuousChildKind] = Counter()
        self._durable: dict[str, tuple[ChildExecutionResult, ...]] = {}

    def lookup_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...] | None:
        return self._durable.get(request.idempotency_key)

    def execute_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...]:
        results = tuple(
            ChildExecutionResult(
                child_kind=kind,
                child_run_id=ArtifactId(f"{kind.value.lower()}-run"),
                child_receipt_id=ArtifactId(f"{kind.value.lower()}-receipt"),
                child_receipt_hash=HASHES[6],
                child_artifact_id=ArtifactId(f"{kind.value.lower()}-artifact"),
                child_artifact_hash=HASHES[7],
                input_references=request.input_references,
                configuration_references=request.configuration_references,
            )
            for kind in ContinuousChildKind
        )
        for result in results:
            self.calls[result.child_kind] += 1
        self._durable[request.idempotency_key] = results
        return results


def _request() -> ProviderAcquisitionRequest:
    return ProviderAcquisitionRequest(
        provider_id="tencent-public",
        product="a-share-minute",
        request_hash=HASHES[0],
        provider_revision="fixture-v1",
    )


def test_first_evidence_runs_each_existing_child_once_and_completes(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    journal.create_or_get(command)
    provider = ScriptedProvider([_provider_result(HASHES[8])])
    children = CountingChildren()
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=children,
        policy=default_continuous_decision_window_policy(),
        clock=lambda: NOW,
    )

    result = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    assert result.tick.status is ContinuousTickStatus.COMPLETED
    assert result.run_state is ContinuousRunState.DECISION_WINDOW_OPEN
    assert provider.call_count == 1
    assert children.calls == Counter({kind: 1 for kind in ContinuousChildKind})
    assert result.entry_authority_granted is False


def test_no_material_change_reuses_children_without_calling_them(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    journal.create_or_get(command)
    provider = ScriptedProvider(
        [_provider_result(HASHES[8]), _provider_result(HASHES[8])]
    )
    children = CountingChildren()
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=children,
        policy=default_continuous_decision_window_policy(),
        clock=lambda: NOW,
    )
    runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )
    baseline_calls = children.calls.copy()

    result = runner.execute(
        run_command=command,
        tick_command=_tick(command, 1),
        provider_request=_request(),
    )

    assert children.calls == baseline_calls
    assert len(result.child_references) == len(ContinuousChildKind)
    assert all(
        reference.reference_disposition.value == "REUSED"
        for reference in result.child_references
    )


def test_provider_failure_records_attempt_and_preserves_current_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    journal.create_or_get(command)
    provider = ScriptedProvider(
        [
            _provider_result(HASHES[8]),
            ProviderAcquisitionResult.failed(
                status=ProviderAttemptStatus.TIMED_OUT,
                completed_at=NOW,
                error_code="PROVIDER_TIMEOUT",
                error_message="provider timed out",
                reason_codes=("PROVIDER_TIMEOUT",),
                retry_at=None,
            ),
        ]
    )
    children = CountingChildren()
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=children,
        policy=default_continuous_decision_window_policy(),
        clock=lambda: NOW,
    )
    first = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )
    assert first.evidence is not None
    baseline = journal.get_current_evidence(command.run_id, "A_SHARE_MINUTE_SCOPE")

    failed = runner.execute(
        run_command=command,
        tick_command=_tick(command, 1),
        provider_request=_request(),
    )

    assert failed.tick.status is ContinuousTickStatus.FAILED
    assert failed.evidence is None
    assert journal.get_current_evidence(
        command.run_id, "A_SHARE_MINUTE_SCOPE"
    ) == baseline
    assert children.calls == Counter({kind: 1 for kind in ContinuousChildKind})


def test_data_insufficient_first_evidence_completes_without_children(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    journal.create_or_get(command)
    acquired = _provider_result(HASHES[8])
    assert acquired.evidence is not None
    provider = ScriptedProvider(
        [
            replace(
                acquired,
                evidence=replace(
                    acquired.evidence, downstream_contract_satisfied=False
                ),
            )
        ]
    )
    children = CountingChildren()
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=children,
        policy=default_continuous_decision_window_policy(),
        clock=lambda: NOW,
    )

    result = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    assert result.tick.status is ContinuousTickStatus.COMPLETED
    assert result.decision is not None
    assert result.decision.decision_type.value == "DATA_INSUFFICIENT"
    assert result.child_references == ()
    assert children.calls == Counter()


def test_future_evidence_is_recorded_as_invalid_attempt_and_not_consumed(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    acquired = _provider_result(HASHES[8])
    assert acquired.evidence is not None
    future = NOW + timedelta(minutes=1)
    provider = ScriptedProvider(
        [
            replace(
                acquired,
                completed_at=future,
                evidence=replace(
                    acquired.evidence,
                    effective_at=future,
                    retrieved_at=future,
                    available_at=future,
                    as_of_time=future,
                ),
            )
        ]
    )
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=CountingChildren(),
        policy=default_continuous_decision_window_policy(),
        clock=lambda: NOW,
    )

    result = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    assert result.tick.status is ContinuousTickStatus.FAILED
    assert result.evidence is None
    attempt = journal.get_provider_attempt(result.tick.provider_attempt_id or 0)
    assert attempt.status is ProviderAttemptStatus.INVALID_RESPONSE
    assert journal.get_current_evidence(command.run_id, "A_SHARE_MINUTE_SCOPE") is None


def test_provider_exception_is_recorded_as_failed_attempt(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    class RaisingProvider:
        def acquire(self, request: ProviderAcquisitionRequest) -> ProviderAcquisitionResult:
            raise TimeoutError("secret provider detail")

    command = _command()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=RaisingProvider(),
        children=CountingChildren(),
        policy=default_continuous_decision_window_policy(),
        clock=lambda: NOW,
    )

    result = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    attempt = journal.get_provider_attempt(result.tick.provider_attempt_id or 0)
    assert attempt.status is ProviderAttemptStatus.FAILED
    assert attempt.error_message == "TimeoutError"
    assert result.evidence is None
