from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleAttemptResult,
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRetryState,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    configuration_manifest_hash,
    model_version_manifest_hash,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.decision_risk import (
    OpportunityStageHandler,
    PortfolioRiskStageHandler,
    ThesisStageHandler,
    repository_output_reference,
)
from market_regime_alpha.application.canonical_lifecycle.stages.risk_reduction import (
    RiskReductionStageHandler,
    build_symbol_trading_session_status_set,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    ordered_references,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.application.trading_lifecycle.complete_account_risk import (
    CompleteAccountPortfolioRiskApplicationService,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.risk_reduction import (
    OperatorAuthenticationRequirement,
    RiskReductionConfirmationPolicy,
)
from market_regime_alpha.portfolio.risk_routes import RiskChangeKind
from market_regime_alpha.portfolio import (
    AccountPortfolioCompleteness,
    AccountReconciliationState,
    AuthoritativeAccountPortfolioSnapshot,
    PortfolioOutputMode,
    ThesisAllocationRequest,
)
from market_regime_alpha.portfolio.sqlite_account_authority import (
    SQLiteCompleteAccountPortfolioRiskRepository,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)
from tests.daily_decision.conftest import daily_decision_fixture
from tests.execution.risk_reduction_confirmation_support import (
    ConfirmationFixture,
    build_confirmation_fixture,
)
from tests.portfolio.test_complete_account_risk import (
    NOW as PORTFOLIO_NOW,
    _risk_configuration,
    _thesis,
)
from zoneinfo import ZoneInfo


UTC = timezone.utc


def _reference(
    *,
    object_type: LifecycleObjectType,
    object_id: object,
    content_hash: str,
    reader_kind: LifecycleReaderKind,
    available_at: datetime,
    locator: Path | None = None,
) -> LifecycleObjectReference:
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(str(object_id)),
        content_hash=content_hash,
        reader_kind=reader_kind,
        locator=str(locator.resolve()) if locator is not None else None,
        available_at=available_at.astimezone(UTC),
    )


def _context(
    *,
    stage_name: LifecycleStageName,
    as_of: datetime,
    initial_references: tuple[LifecycleObjectReference, ...],
    run_type: LifecycleRunType = LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
) -> LifecycleStageContext:
    as_of = as_of.astimezone(UTC)
    index = LIFECYCLE_STAGE_ORDER.index(stage_name)
    started = as_of - timedelta(seconds=64)
    run = LifecycleRun(
        run_id=LifecycleRunId(f"decision-risk-{stage_name.value.lower()}"),
        idempotency_key=f"decision-risk-{stage_name.value.lower()}",
        command_hash=canonical_hash(
            {"stage": stage_name.value, "run_type": run_type.value}
        ),
        run_type=run_type,
        decision_date=as_of.date(),
        as_of_time=as_of,
        status=LifecycleRunStatus.RUNNING,
        current_stage=stage_name,
        input_manifest_id=(
            None
            if run_type is LifecycleRunType.RISK_REDUCTION_CONTINUATION
            else ArtifactId("decision-risk-input")
        ),
        input_content_hash=(
            None
            if run_type is LifecycleRunType.RISK_REDUCTION_CONTINUATION
            else canonical_hash({"input": "decision-risk"})
        ),
        completed_stages=tuple(LIFECYCLE_STAGE_ORDER[:index]),
        configuration_references=(),
        configuration_manifest_hash=configuration_manifest_hash(()),
        model_references=(),
        model_version_manifest_hash=model_version_manifest_hash(()),
        retry_state=LifecycleRetryState.NOT_REQUIRED,
        failure_reason=None,
        blocker_reason=None,
        created_at=started,
        updated_at=as_of,
        completed_at=None,
        version=index + 1,
        claim_token=1,
    )
    prior_stages = tuple(
        LifecycleStage(
            run_id=run.run_id,
            stage_name=prior_name,
            stage_status=(
                LifecycleStageStatus.SKIPPED_NOT_APPLICABLE
                if run_type is LifecycleRunType.RISK_REDUCTION_CONTINUATION
                else LifecycleStageStatus.COMPLETED
            ),
            attempt_count=1,
            input_references=(),
            output_references=(),
            started_at=started + timedelta(seconds=prior_index),
            completed_at=started + timedelta(seconds=prior_index + 1),
            failure_reason=None,
            blocker_reason=(
                "risk continuation starts from existing H4 authority"
                if run_type is LifecycleRunType.RISK_REDUCTION_CONTINUATION
                else None
            ),
            version=2,
        )
        for prior_index, prior_name in enumerate(LIFECYCLE_STAGE_ORDER[:index])
    )
    stage = LifecycleStage(
        run_id=run.run_id,
        stage_name=stage_name,
        stage_status=LifecycleStageStatus.RUNNING,
        attempt_count=1,
        input_references=(),
        output_references=(),
        started_at=as_of,
        completed_at=None,
        failure_reason=None,
        blocker_reason=None,
        version=2,
    )
    attempt = LifecycleAttempt(
        attempt_id=LifecycleAttemptId(f"attempt-{stage_name.value.lower()}"),
        run_id=run.run_id,
        stage_name=stage_name,
        attempt_number=1,
        started_at=as_of,
        completed_at=None,
        result=LifecycleAttemptResult.RUNNING,
        exception_type=None,
        exception_message=None,
        claim_token=1,
    )
    return LifecycleStageContext(
        run=run,
        stage=stage,
        attempt=attempt,
        prior_stages=prior_stages,
        initial_references=ordered_references(initial_references),
    )


@pytest.fixture
def confirmation_fixture(tmp_path: Path) -> ConfirmationFixture:
    return build_confirmation_fixture(
        tmp_path,
        daily_decision_fixture.__wrapped__(),
        action=RiskChangeKind.REDUCE,
    )


def _decision_references(
    fixture: ConfirmationFixture,
) -> tuple[LifecycleObjectReference, LifecycleObjectReference]:
    database = fixture.repository.path
    decisions = SQLiteDecisionLifecycleRepository(database)
    thesis = decisions.get_thesis(fixture.book.thesis_id)
    opportunity = decisions.get_opportunity(thesis.opportunity_id)
    opportunity_reference = repository_output_reference(
        object_type=LifecycleObjectType.OPPORTUNITY,
        object_id=opportunity.opportunity_id,
        payload=opportunity.to_canonical_dict(),
        reader_kind=LifecycleReaderKind.DECISION_LIFECYCLE_REPOSITORY,
        available_at=opportunity.updated_at,
    )
    thesis_reference = repository_output_reference(
        object_type=LifecycleObjectType.THESIS,
        object_id=thesis.thesis_id,
        payload=thesis.to_canonical_dict(),
        reader_kind=LifecycleReaderKind.DECISION_LIFECYCLE_REPOSITORY,
        available_at=thesis.updated_at,
    )
    return opportunity_reference, thesis_reference


def test_decision_stages_wait_without_persisted_creation_or_approval_authority(
    confirmation_fixture: ConfirmationFixture,
) -> None:
    as_of = confirmation_fixture.command.confirmed_at.astimezone(UTC)
    database = confirmation_fixture.repository.path
    repository = SQLiteDecisionLifecycleRepository(database)
    opportunity_handler = OpportunityStageHandler(repository=repository)

    opportunity_result = opportunity_handler.execute(
        _context(
            stage_name=LifecycleStageName.OPPORTUNITY,
            as_of=as_of,
            initial_references=(),
        )
    )

    assert opportunity_result.stage_status is LifecycleStageStatus.WAITING
    assert "OPPORTUNITY_CREATION_AUTHORITY_REQUIRED" in opportunity_result.reason_codes
    opportunity_reference, _ = _decision_references(confirmation_fixture)
    thesis_result = ThesisStageHandler(repository=repository).execute(
        _context(
            stage_name=LifecycleStageName.THESIS,
            as_of=as_of,
            initial_references=(opportunity_reference,),
        )
    )
    assert thesis_result.stage_status is LifecycleStageStatus.WAITING
    assert thesis_result.output_references == ()
    assert "THESIS_APPROVAL_AUTHORITY_REQUIRED" in thesis_result.reason_codes


def test_existing_opportunity_and_human_approved_thesis_are_loaded_exactly(
    confirmation_fixture: ConfirmationFixture,
) -> None:
    as_of = confirmation_fixture.command.confirmed_at.astimezone(UTC)
    database = confirmation_fixture.repository.path
    repository = SQLiteDecisionLifecycleRepository(database)
    opportunity_reference, thesis_reference = _decision_references(
        confirmation_fixture
    )
    opportunity_context = _context(
        stage_name=LifecycleStageName.OPPORTUNITY,
        as_of=as_of,
        initial_references=(opportunity_reference, thesis_reference),
    )
    opportunity_handler = OpportunityStageHandler(repository=repository)

    opportunity_result = opportunity_handler.execute(opportunity_context)
    recovered_opportunity = opportunity_handler.recover(opportunity_context)
    thesis_result = ThesisStageHandler(repository=repository).execute(
        _context(
            stage_name=LifecycleStageName.THESIS,
            as_of=as_of,
            initial_references=(opportunity_reference, thesis_reference),
        )
    )

    assert recovered_opportunity == opportunity_result
    assert opportunity_result.output_references == (opportunity_reference,)
    assert thesis_result.output_references == (thesis_reference,)
    assert "DURABLE_THESIS_APPROVAL_AUTHORITY_VERIFIED" in thesis_result.reason_codes


def test_portfolio_risk_fails_closed_without_complete_account_authority(
    confirmation_fixture: ConfirmationFixture,
) -> None:
    _, thesis_reference = _decision_references(confirmation_fixture)
    handler = PortfolioRiskStageHandler(
        repository=SQLiteCompleteAccountPortfolioRiskRepository(
            confirmation_fixture.repository.path
        )
    )

    result = handler.execute(
        _context(
            stage_name=LifecycleStageName.PORTFOLIO_RISK,
            as_of=confirmation_fixture.command.confirmed_at,
            initial_references=(thesis_reference,),
        )
    )

    assert result.stage_status is LifecycleStageStatus.WAITING
    assert "PORTFOLIO_RISK_DATA_INSUFFICIENT" in result.reason_codes
    assert "POSITION_AUTHORITATIVE_COMPLETE_ACCOUNT_INPUTS_REQUIRED" in (
        result.reason_codes
    )
    assert result.output_references == ()


def test_portfolio_risk_loads_actual_complete_account_service_authority(
    tmp_path: Path,
) -> None:
    repository = SQLiteCompleteAccountPortfolioRiskRepository(
        tmp_path / "complete-account.sqlite3"
    )
    thesis = _thesis("000001.SZ")
    account = AuthoritativeAccountPortfolioSnapshot.create(
        account_id="canonical-stage-account",
        as_of=PORTFOLIO_NOW - timedelta(seconds=1),
        source_reference="canonical-stage-complete-account",
        net_asset_value=100_000.0,
        available_cash=100_000.0,
        all_positions=(),
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=0,
    )
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-canonical",
        target_quantity=100,
        reference_price=10.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=1.0,
    )
    portfolio, risk = CompleteAccountPortfolioRiskApplicationService(repository).run(
        theses=(thesis,),
        allocations=(allocation,),
        account_snapshot=account,
        configuration=_risk_configuration(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="canonical-risk-operator",
        reason="command-bound complete-account authority",
        portfolio_created_at=PORTFOLIO_NOW,
        risk_started_at=PORTFOLIO_NOW,
        risk_completed_at=PORTFOLIO_NOW + timedelta(seconds=1),
        idempotency_key="canonical-complete-account",
    )
    thesis_reference = repository_output_reference(
        object_type=LifecycleObjectType.THESIS,
        object_id=thesis.thesis_id,
        payload=thesis.to_canonical_dict(),
        reader_kind=LifecycleReaderKind.DECISION_LIFECYCLE_REPOSITORY,
        available_at=thesis.updated_at,
    )
    portfolio_reference = repository_output_reference(
        object_type=LifecycleObjectType.PORTFOLIO_DECISION,
        object_id=portfolio.decision_id,
        payload=portfolio.to_canonical_dict(),
        reader_kind=LifecycleReaderKind.PORTFOLIO_RISK_REPOSITORY,
        available_at=portfolio.created_at,
    )
    risk_reference = repository_output_reference(
        object_type=LifecycleObjectType.RISK_DECISION,
        object_id=risk.risk_decision_id,
        payload=risk.to_canonical_dict(),
        reader_kind=LifecycleReaderKind.PORTFOLIO_RISK_REPOSITORY,
        available_at=risk.completed_at,
    )
    context = _context(
        stage_name=LifecycleStageName.PORTFOLIO_RISK,
        as_of=risk.completed_at,
        initial_references=(
            thesis_reference,
            portfolio_reference,
            risk_reference,
        ),
    )
    handler = PortfolioRiskStageHandler(repository=repository)

    result = handler.execute(context)

    assert handler.recover(context) == result
    assert result.stage_status is LifecycleStageStatus.COMPLETED
    assert result.run_status is LifecycleRunStatus.RUNNING
    assert result.output_references == (portfolio_reference, risk_reference)
    assert "COMPLETE_ACCOUNT_PORTFOLIO_RISK_AUTHORITY_VERIFIED" in (
        result.reason_codes
    )


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return path


def _risk_references(
    fixture: ConfirmationFixture, root: Path
) -> tuple[LifecycleObjectReference, ...]:
    command = fixture.command
    database = fixture.repository.path
    risk_bundle = SQLiteRiskRouteRepository(
        database
    ).get_verified_reducing_decision_bundle(fixture.decision_id)
    health = SQLiteThesisHealthRepository(
        database
    ).get_verified_thesis_health_bundle(command.thesis_health_observation_id)
    composite = SQLiteCompositeOperationalRepository(database).get_manifest(
        command.composite_manifest_id
    )
    as_of = max(command.confirmed_at, composite.manifest.created_at)
    policy = RiskReductionConfirmationPolicy.create(
        profile_id="canonical-continuation-test-v1",
        builder_revision="canonical-lifecycle-test",
        maximum_decision_age_seconds=600,
        maximum_position_age_seconds=600,
        maximum_execution_observation_age_seconds=600,
        maximum_reference_price_deviation=(
            command.confirmation_policy.maximum_reference_price_deviation
        ),
        operator_authentication_requirement=(
            OperatorAuthenticationRequirement.RECORDED_ACTOR_ONLY
        ),
    )
    calendar_path = _write_json(
        root / "calendar.json", command.trading_calendar.to_canonical_dict()
    )
    observation_path = _write_json(
        root / "execution-observation.json",
        command.execution_observation.to_canonical_dict(),
    )
    statuses_payload = build_symbol_trading_session_status_set(
        command.symbol_trading_statuses
    )
    statuses_path = _write_json(root / "statuses.json", statuses_payload)
    policy_path = _write_json(
        root / "confirmation-policy.json",
        policy.to_canonical_dict(),
    )
    return ordered_references(
        (
            _reference(
                object_type=LifecycleObjectType.RISK_REDUCING_DECISION,
                object_id=risk_bundle.decision.decision_id,
                content_hash=risk_bundle.decision.content_hash,
                reader_kind=LifecycleReaderKind.RISK_REDUCTION_REPOSITORY,
                available_at=risk_bundle.decision.assessed_at,
            ),
            _reference(
                object_type=LifecycleObjectType.POSITION_BOOK,
                object_id=fixture.book.position_book_id,
                content_hash=canonical_hash(fixture.book.to_canonical_dict()),
                reader_kind=LifecycleReaderKind.POSITION_BOOK_REPOSITORY,
                available_at=fixture.book.opened_at,
            ),
            _reference(
                object_type=LifecycleObjectType.OPERATIONAL_EXIT_DIRECTIVE,
                object_id=fixture.directive.directive_id,
                content_hash=fixture.directive.content_hash,
                reader_kind=(
                    LifecycleReaderKind.OPERATIONAL_EXIT_DIRECTIVE_REPOSITORY
                ),
                available_at=fixture.directive.created_at,
            ),
            _reference(
                object_type=LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
                object_id=command.trading_calendar.artifact_id,
                content_hash=command.trading_calendar.content_hash,
                reader_kind=LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER,
                available_at=as_of,
                locator=calendar_path,
            ),
            _reference(
                object_type=LifecycleObjectType.THESIS_HEALTH_OBSERVATION,
                object_id=health.observation.observation_id,
                content_hash=health.observation.content_hash,
                reader_kind=LifecycleReaderKind.THESIS_HEALTH_REPOSITORY,
                available_at=health.observation.assessed_at,
            ),
            _reference(
                object_type=LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
                object_id=composite.manifest.manifest_id,
                content_hash=composite.manifest.content_hash,
                reader_kind=(
                    LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER
                ),
                available_at=composite.manifest.created_at,
                locator=composite.root,
            ),
            _reference(
                object_type=LifecycleObjectType.REDUCING_EXECUTION_OBSERVATION,
                object_id=command.execution_observation.observation_id,
                content_hash=command.execution_observation.content_hash,
                reader_kind=(
                    LifecycleReaderKind.REDUCING_EXECUTION_OBSERVATION_READER
                ),
                available_at=command.execution_observation.availability_time,
                locator=observation_path,
            ),
            _reference(
                object_type=(
                    LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET
                ),
                object_id=statuses_payload["status_set_id"],
                content_hash=str(statuses_payload["content_hash"]),
                reader_kind=(
                    LifecycleReaderKind.SYMBOL_TRADING_SESSION_STATUS_READER
                ),
                available_at=max(
                    item.availability_time
                    for item in command.symbol_trading_statuses
                ),
                locator=statuses_path,
            ),
            _reference(
                object_type=(
                    LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY
                ),
                object_id=policy.policy_id,
                content_hash=policy.policy_hash,
                reader_kind=(
                    LifecycleReaderKind.RISK_REDUCTION_CONFIRMATION_POLICY_READER
                ),
                available_at=as_of,
                locator=policy_path,
            ),
        )
    )


def _risk_handler(fixture: ConfirmationFixture) -> RiskReductionStageHandler:
    database = fixture.repository.path
    return RiskReductionStageHandler(
        risk_repository=SQLiteRiskRouteRepository(database),
        execution_repository=SQLiteRiskReductionManualIntentRepository(database),
        decision_repository=SQLiteDecisionLifecycleRepository(database),
        thesis_health_repository=SQLiteThesisHealthRepository(database),
        composite_repository=SQLiteCompositeOperationalRepository(database),
    )


def _risk_continuation_as_of(fixture: ConfirmationFixture) -> datetime:
    composite = SQLiteCompositeOperationalRepository(
        fixture.repository.path
    ).get_manifest(fixture.command.composite_manifest_id)
    return max(fixture.command.confirmed_at, composite.manifest.created_at)


def _authority_counts(database: Path) -> tuple[int, int]:
    with sqlite3.connect(database) as connection:
        trades = int(
            connection.execute("SELECT COUNT(*) FROM manual_trade_records").fetchone()[0]
        )
        confirmations = int(
            connection.execute(
                "SELECT COUNT(*) FROM risk_reduction_confirmation_attempts"
            ).fetchone()[0]
        )
    return trades, confirmations


def test_risk_continuation_replays_exact_h4_authority_and_stops_before_trade(
    confirmation_fixture: ConfirmationFixture,
    tmp_path: Path,
) -> None:
    references = _risk_references(confirmation_fixture, tmp_path)
    context = _context(
        stage_name=LifecycleStageName.RISK_REDUCTION,
        as_of=_risk_continuation_as_of(confirmation_fixture),
        initial_references=references,
        run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
    )
    handler = _risk_handler(confirmation_fixture)
    before = _authority_counts(confirmation_fixture.repository.path)

    result = handler.execute(context)
    recovered = handler.recover(context)

    assert recovered == result
    assert result.stage_status is LifecycleStageStatus.COMPLETED
    assert result.run_status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
    assert result.input_references == references
    assert result.output_references == tuple(
        item
        for item in references
        if item.object_type is LifecycleObjectType.RISK_REDUCING_DECISION
    )
    assert "H4_RISK_REDUCTION_AUTHORITY_VERIFIED" in result.reason_codes
    assert "MANUAL_CONFIRMATION_REQUIRED" in result.reason_codes
    assert "NO_ORDER_CREATED" in result.reason_codes
    assert "BROKER_NOT_INVOKED" in result.reason_codes
    assert "NO_FILL_CREATED" in result.reason_codes
    assert _authority_counts(confirmation_fixture.repository.path) == before


def test_risk_continuation_rejects_tampered_repository_reference(
    confirmation_fixture: ConfirmationFixture,
    tmp_path: Path,
) -> None:
    references = _risk_references(confirmation_fixture, tmp_path)
    decision_reference = next(
        item
        for item in references
        if item.object_type is LifecycleObjectType.RISK_REDUCING_DECISION
    )
    tampered = ordered_references(
        tuple(
            replace(item, content_hash="sha256:" + "f" * 64)
            if item is decision_reference
            else item
            for item in references
        )
    )

    with pytest.raises(ValueError, match="RISK_REDUCING_DECISION reference mismatch"):
        _risk_handler(confirmation_fixture).execute(
            _context(
                stage_name=LifecycleStageName.RISK_REDUCTION,
                as_of=_risk_continuation_as_of(confirmation_fixture),
                initial_references=tampered,
                run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
            )
        )


class _NeverCalledHandler:
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, stage_name: LifecycleStageName) -> None:
        self.stage_name = stage_name

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        raise AssertionError(f"unexpected recover: {context.stage_name.value}")

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        raise AssertionError(f"unexpected execute: {context.stage_name.value}")


class _IncreasingClock:
    def __init__(self, start: datetime) -> None:
        self._current = start.astimezone(UTC)

    def __call__(self) -> datetime:
        value = self._current
        self._current += timedelta(seconds=1)
        return value


def test_runner_journals_risk_continuation_receipt_and_exact_inputs(
    confirmation_fixture: ConfirmationFixture,
    tmp_path: Path,
) -> None:
    references = _risk_references(confirmation_fixture, tmp_path)
    as_of = _risk_continuation_as_of(confirmation_fixture).astimezone(UTC)
    command = CanonicalLifecycleCommand(
        run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
        decision_date=as_of.astimezone(ZoneInfo("Asia/Shanghai")).date(),
        as_of_time=as_of,
        idempotency_key="canonical-risk-continuation-receipt",
        input_manifest_id=None,
        input_content_hash=None,
        input_manifest_locator=None,
        input_references=references,
        configuration_references=_risk_configuration_references(
            confirmation_fixture, references, tmp_path
        ),
        model_references=(),
        stop_after_stage=None,
        output_directory=tmp_path / "outputs",
    )
    risk_handler = _risk_handler(confirmation_fixture)
    handlers = tuple(
        risk_handler
        if stage_name is LifecycleStageName.RISK_REDUCTION
        else _NeverCalledHandler(stage_name)
        for stage_name in LIFECYCLE_STAGE_ORDER
    )
    runner = CanonicalDecisionLifecycleRunner(
        repository=SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3"),
        handlers=handlers,
        clock=_IncreasingClock(as_of + timedelta(minutes=1)),
    )
    before = _authority_counts(confirmation_fixture.repository.path)

    result = runner.run(command)

    assert result.run.status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
    assert result.run.current_stage is LifecycleStageName.RISK_REDUCTION
    risk_stage = next(
        item
        for item in result.stages
        if item.stage_name is LifecycleStageName.RISK_REDUCTION
    )
    receipt = next(
        item
        for item in result.receipts
        if item.stage_name is LifecycleStageName.RISK_REDUCTION
    )
    assert risk_stage.input_references == references
    assert receipt.stage_result is LifecycleStageStatus.COMPLETED
    assert receipt.input_hashes == tuple(
        sorted(item.content_hash for item in references)
    )
    assert "MANUAL_CONFIRMATION_REQUIRED" in receipt.reason_codes
    assert _authority_counts(confirmation_fixture.repository.path) == before


def _risk_configuration_references(
    fixture: ConfirmationFixture,
    references: tuple[LifecycleObjectReference, ...],
    root: Path,
) -> tuple[LifecycleConfigurationReference, ...]:
    bundle = SQLiteRiskRouteRepository(
        fixture.repository.path
    ).get_verified_reducing_decision_bundle(fixture.decision_id)
    gate_path = _write_json(
        root / "risk-gate-configuration.json",
        bundle.configuration.to_canonical_dict(),
    )
    policy_reference = next(
        item
        for item in references
        if item.object_type
        is LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY
    )
    assert policy_reference.locator is not None
    policy = RiskReductionConfirmationPolicy.from_canonical_dict(
        json.loads(Path(policy_reference.locator).read_text(encoding="utf-8"))
    )
    return tuple(
        sorted(
            (
                LifecycleConfigurationReference(
                    configuration_kind=LifecycleConfigurationKind.GENERIC,
                    configuration_id=bundle.configuration.configuration_id,
                    configuration_version=bundle.configuration.schema_version,
                    content_hash=bundle.configuration.configuration_hash,
                    locator=str(gate_path.resolve()),
                ),
                LifecycleConfigurationReference(
                    configuration_kind=LifecycleConfigurationKind.GENERIC,
                    configuration_id=policy.policy_id,
                    configuration_version=policy.schema_version,
                    content_hash=policy.policy_hash,
                    locator=policy_reference.locator,
                ),
            ),
            key=lambda item: item.sort_key,
        )
    )
