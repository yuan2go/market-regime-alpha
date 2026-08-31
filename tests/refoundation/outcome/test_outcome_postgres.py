from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.decision_support.domain import (
    OpenDecisionRunRequest,
    RequestedDecisionTarget,
)
from market_regime_alpha.infrastructure.postgres.outcome_uow import (
    PostgresOutcomeUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.outcome_inputs import (
    PostgresOutcomeInputPreparationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.outcomes import (
    PostgresOutcomeQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.outcome_verification import (
    PostgresOutcomeVerificationProvider,
)
from market_regime_alpha.market.domain import (
    BarTimeframe,
    GapFactKind,
    GapKind,
    GapReasonCode,
    MarketBarRevision,
    NormalizationBatch,
    PriceBasis,
    SourceGap,
    TradingSession,
)
from market_regime_alpha.outcome.application import (
    OutcomeApplication,
    OutcomeNotDueResult,
    OutcomeVerifier,
    SettleMarketTargetOutcomeRequest,
)
from market_regime_alpha.outcome.errors import (
    OutcomeAuthorityIntegrityError,
    OutcomeInputResolutionError,
    OutcomeRevisionConflictError,
)
from market_regime_alpha.outcome.domain import OutcomeMismatchKind
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    StaleFenceError,
)
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from tests.refoundation.decision_support import test_decision_postgres as _decision
from tests.refoundation.research_qualification import (
    test_research_postgres as _research,
)
from tests.refoundation.research_qualification.test_target_domain import valid_target
from tests.refoundation.selection import (
    test_candidate_vertical_slice_postgres as _candidate,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def outcome_stack(target_database_url, tmp_path, request):
    return _research.dataset_stack.__wrapped__(
        target_database_url,
        tmp_path,
        request,
    )


def _binding(record: object) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=record.artifact_id,  # type: ignore[attr-defined]
        content_sha256=record.content_sha256,  # type: ignore[attr-defined]
        size_bytes=record.size_bytes,  # type: ignore[attr-defined]
    )


def _context(key: str, reason: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="wp10-outcome-worker",
        reason_code=reason,
    )


def _register_midnight_target(stack):
    code = stack.artifacts.publish(
        b"def simple_return(reference, observation): return observation / reference - 1\n",
        media_type="text/plain",
        context=_context("wp10-target-code", "REGISTER_TARGET_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"outcome":"T+1 00:05","reference":"14:55"}\n',
        media_type="application/json",
        context=_context("wp10-target-config", "REGISTER_TARGET_CONFIG"),
    )
    definition = valid_target()
    outcome_checkpoint = replace(
        definition.checkpoints[1],
        checkpoint_code="next_session_0005",
        local_time=time(0, 5),
    )
    algorithm = replace(
        definition.algorithm,
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    definition = replace(
        definition,
        algorithm=algorithm,
        checkpoints=(definition.checkpoints[0], outcome_checkpoint),
        metrics=tuple(
            replace(metric, algorithm=algorithm) for metric in definition.metrics
        ),
    )
    stack.research.register_target_definition(
        definition,
        _context("wp10-register-target", "REGISTER_TARGET_DEFINITION"),
    )
    return definition


def _open_decision(stack, target):
    runtime, _, built, claim = _decision._build_candidate_for_decision(
        stack,
        key_prefix="wp10-decision",
    )
    result = _decision._application(stack).open_decision_run(
        OpenDecisionRunRequest(
            candidate_set_id=UUID(built.aggregate_id),
            targets=(
                RequestedDecisionTarget(
                    target_definition_id=target.target_definition_id,
                    reference_provider_product_id=stack.product.provider_product_id,
                ),
            ),
        ),
        _context("wp10-open-decision", "OPEN_DECISION_RUN"),
        runtime_claim=claim,
    )
    assess_claim = _candidate._claim(runtime, step_key="assess-context")
    runtime.succeed_attempt(
        assess_claim,
        result_hash="e" * 64,
        context=_context("wp10-finish-assess", "WORKER_SUCCEED"),
    )
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT commitment_id
            FROM mra.decision_target_commitment
            WHERE decision_run_id = %s
            """,
            (result.decision_run_id,),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def _add_outcome_bar(stack) -> tuple[datetime, datetime, UUID]:
    with psycopg.connect(stack.database_url) as connection:
        reference = connection.execute(
            """
            SELECT session_date
            FROM mra.trading_session
            WHERE session_id = %s
            """,
            (stack.market_session_id,),
        ).fetchone()
    assert reference is not None
    session_date = reference[0] + timedelta(days=1)

    def instant(hour: int, minute: int) -> datetime:
        return datetime.combine(
            session_date,
            time(hour, minute),
            SHANGHAI,
        ).astimezone(UTC)

    captured = stack.market.capture(
        _research.CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key=f"wp10-outcome-source-{uuid4().hex}",
            resource="fixture://wp10-outcome-source",
            request_headers_hash="d" * 64,
        ),
        _research._BytesProvider(),
        _context("wp10-outcome-capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    session_id = uuid4()
    bar_id = uuid4()
    session = TradingSession(
        session_id=session_id,
        exchange="XSHG",
        session_date=session_date,
        timezone_name="Asia/Shanghai",
        open_at=instant(0, 0),
        break_start_at=None,
        break_end_at=None,
        close_at=instant(15, 0),
        decision_reference_at=instant(14, 55),
        source_capture_id=captured.capture.capture_id,
    )

    def batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            trading_sessions=(session,),
            bars=(
                MarketBarRevision(
                    bar_revision_id=bar_id,
                    provider_product_id=stack.product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=stack.instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=instant(0, 0),
                    event_end=instant(0, 5),
                    revision=1,
                    supersedes_revision_id=None,
                    open=Money(Decimal("10.10"), "CNY"),
                    high=Money(Decimal("10.80"), "CNY"),
                    low=Money(Decimal("10.00"), "CNY"),
                    close=Money(Decimal("10.60"), "CNY"),
                    volume=Quantity(Decimal("1200"), QuantityUnit.SHARES),
                    turnover=Money(Decimal("12600"), "CNY"),
                ),
            ),
        )

    normalized = stack.market.normalize(
        captured.capture.capture_id,
        _research._Normalizer(batch),
        _context("wp10-outcome-normalize", "NORMALIZE_MARKET_PIT"),
    )
    return instant(0, 5), normalized.decision_visible_at.value, bar_id


def _correct_outcome_bar(
    stack,
    supersedes_bar_revision_id: UUID,
    *,
    close_value: Decimal,
) -> tuple[datetime, UUID]:
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT instrument_id, session_id, timeframe, price_basis,
                   event_start, event_end, revision
            FROM mra.market_bar_revision
            WHERE bar_revision_id = %s
            """,
            (supersedes_bar_revision_id,),
        ).fetchone()
    assert row is not None
    suffix = uuid4().hex
    captured = stack.market.capture(
        _research.CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key=f"wp10-outcome-correction-{suffix}",
            resource=f"fixture://wp10-outcome-correction/{suffix}",
            request_headers_hash="e" * 64,
        ),
        _research._BytesProvider(),
        _context(
            f"wp10-outcome-correction-capture-{suffix}",
            "CAPTURE_PROVIDER_RESPONSE",
        ),
    )
    revised_bar_id = uuid4()

    def batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            bars=(
                MarketBarRevision(
                    bar_revision_id=revised_bar_id,
                    provider_product_id=stack.product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=UUID(str(row[0])),
                    session_id=UUID(str(row[1])),
                    timeframe=BarTimeframe(str(row[2])),
                    price_basis=PriceBasis(str(row[3])),
                    event_start=row[4],
                    event_end=row[5],
                    revision=int(row[6]) + 1,
                    supersedes_revision_id=supersedes_bar_revision_id,
                    open=Money(Decimal("10.20"), "CNY"),
                    high=Money(max(close_value, Decimal("10.90")), "CNY"),
                    low=Money(Decimal("10.00"), "CNY"),
                    close=Money(close_value, "CNY"),
                    volume=Quantity(Decimal("1300"), QuantityUnit.SHARES),
                    turnover=Money(Decimal("13910"), "CNY"),
                ),
            ),
        )

    normalized = stack.market.normalize(
        captured.capture.capture_id,
        _research._Normalizer(batch),
        _context(
            f"wp10-outcome-correction-normalize-{suffix}",
            "NORMALIZE_MARKET_PIT",
        ),
    )
    return normalized.decision_visible_at.value, revised_bar_id


def _add_outcome_gap(
    stack,
    *,
    include_gap: bool = True,
) -> tuple[datetime, datetime, UUID | None]:
    with psycopg.connect(stack.database_url) as connection:
        reference = connection.execute(
            """
            SELECT session_date
            FROM mra.trading_session
            WHERE session_id = %s
            """,
            (stack.market_session_id,),
        ).fetchone()
    assert reference is not None
    session_date = reference[0] + timedelta(days=1)

    def instant(hour: int, minute: int) -> datetime:
        return datetime.combine(
            session_date,
            time(hour, minute),
            SHANGHAI,
        ).astimezone(UTC)

    suffix = uuid4().hex
    captured = stack.market.capture(
        _research.CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key=f"wp10-outcome-gap-{suffix}",
            resource=f"fixture://wp10-outcome-gap/{suffix}",
            request_headers_hash="f" * 64,
        ),
        _research._BytesProvider(),
        _context(
            f"wp10-outcome-gap-capture-{suffix}",
            "CAPTURE_PROVIDER_RESPONSE",
        ),
    )
    session_id = uuid4()
    gap_id = uuid4()
    session = TradingSession(
        session_id=session_id,
        exchange="XSHG",
        session_date=session_date,
        timezone_name="Asia/Shanghai",
        open_at=instant(0, 0),
        break_start_at=None,
        break_end_at=None,
        close_at=instant(15, 0),
        decision_reference_at=instant(14, 55),
        source_capture_id=captured.capture.capture_id,
    )

    def batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            trading_sessions=(session,),
            gaps=(
                SourceGap(
                    gap_id=gap_id,
                    provider_product_id=stack.product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=stack.instrument_id,
                    session_id=session_id,
                    gap_kind=GapKind.MISSING,
                    reason_code=GapReasonCode.EXACT_BAR_MISSING,
                    fact_kind=GapFactKind.MARKET_BAR,
                    instrument_fact_kind=None,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=instant(0, 0),
                    event_end=instant(0, 5),
                    detail="exact Outcome checkpoint absent in source",
                ),
            )
            if include_gap
            else (),
        )

    normalized = stack.market.normalize(
        captured.capture.capture_id,
        _research._Normalizer(batch),
        _context(
            f"wp10-outcome-gap-normalize-{suffix}",
            "NORMALIZE_MARKET_PIT",
        ),
    )
    return (
        instant(0, 5),
        normalized.decision_visible_at.value,
        gap_id if include_gap else None,
    )


def _outcome_runtime_claim(stack):
    runtime, _ = _candidate._schedule_run(
        stack,
        steps=(
            _candidate._step(
                key="settle-outcome",
                kind="SETTLE_OUTCOME",
                ordinal=1,
                request_character="a",
            ),
        ),
        canonical_decision_time=stack.decision_time,
    )
    return runtime, _candidate._claim(runtime, step_key="settle-outcome")


def _outcome_claim(stack):
    return _outcome_runtime_claim(stack)[1]


def _application(stack) -> OutcomeApplication:
    queries = PostgresOutcomeQueryProvider(stack.pool)
    return OutcomeApplication(
        PostgresOutcomeInputPreparationProvider(stack.pool),
        PostgresOutcomeUnitOfWorkProvider(stack.pool),
        queries,
    )


class _BarrierPreparation:
    def __init__(self, delegate, barrier: Barrier) -> None:
        self._delegate = delegate
        self._barrier = barrier

    def prepare(self, request, runtime_claim):
        prepared = self._delegate.prepare(request, runtime_claim)
        self._barrier.wait(timeout=15)
        return prepared


def _concurrent_application(stack, barrier: Barrier) -> OutcomeApplication:
    queries = PostgresOutcomeQueryProvider(stack.pool)
    return OutcomeApplication(
        _BarrierPreparation(
            PostgresOutcomeInputPreparationProvider(stack.pool),
            barrier,
        ),
        PostgresOutcomeUnitOfWorkProvider(stack.pool),
        queries,
    )


def _settled_for_verification(stack, *, key: str, gap: bool = False):
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    if gap:
        event_end, known_at, gap_id = _add_outcome_gap(stack)
        assert gap_id is not None
    else:
        event_end, known_at, _ = _add_outcome_bar(stack)
    result = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        _context(key, "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome_claim(stack),
    )
    return result


def test_postgres_not_due_then_due_closes_exact_outcome_and_replays(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, bar_id = _add_outcome_bar(stack)
    claim = _outcome_claim(stack)
    application = _application(stack)

    not_due = application.settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end - timedelta(microseconds=1),
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        _context("wp10-not-due", "SETTLE_DUE_OUTCOME"),
        runtime_claim=claim,
    )
    assert isinstance(not_due, OutcomeNotDueResult)
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT count(*) FROM mra.market_target_outcome
            WHERE commitment_id = %s
            """,
            (commitment_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT count(*) FROM mra.command_receipt
            WHERE command_kind = 'SETTLE_MARKET_TARGET_OUTCOME'
            """
        ).fetchone() == (0,)

    request = SettleMarketTargetOutcomeRequest(
        commitment_id=commitment_id,
        observation_cutoff=event_end,
        knowledge_cutoff=known_at,
        expected_current_revision_id=None,
    )
    context = _context("wp10-settle-1", "SETTLE_DUE_OUTCOME")
    result = application.settle_market_target_outcome(
        request,
        context,
        runtime_claim=claim,
    )
    replay = application.settle_market_target_outcome(
        request,
        context,
        runtime_claim=claim,
    )

    assert result.replayed is False
    assert replay == result.as_replay()
    assert result.revision_ordinal == 1
    assert result.source_count == 2
    assert result.observation_count == 1
    assert result.metric_count == 1
    assert result.reference_dependency_count == 1
    assert result.observation_dependency_count == 1
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT observation.source_kind, source.bar_revision_id,
                   reference.decision_reference_observation_id,
                   metric.decimal_value, revision.finality_status,
                   receipt.status, attempt.state
            FROM mra.market_target_outcome_revision AS revision
            JOIN mra.market_target_outcome_observation AS observation
              ON observation.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
            JOIN mra.market_target_outcome_source AS source
              ON source.market_target_outcome_source_id =
                 observation.market_target_outcome_source_id
            JOIN mra.market_target_outcome_metric AS metric
              ON metric.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
            JOIN mra.market_target_outcome_metric_reference AS reference
              ON reference.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
            JOIN mra.command_receipt AS receipt
              ON receipt.receipt_id = revision.command_receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.attempt_id = revision.runtime_attempt_id
            WHERE revision.market_target_outcome_revision_id = %s
            """,
            (result.market_target_outcome_revision_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "BAR_REVISION"
    assert row[1] == bar_id
    assert row[2] is not None
    assert Decimal(row[3]) == Decimal("0.049504950495049505")
    assert row[4:] == ("UNKNOWN", "SUCCEEDED", "SUCCEEDED")

    verification = OutcomeVerifier(
        PostgresOutcomeQueryProvider(stack.pool),
        PostgresOutcomeVerificationProvider(stack.pool),
    ).verify(result.market_target_outcome_revision_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0
    assert verification.mismatches == ()


def test_market_correction_appends_revision_and_preserves_old_revision(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, first_known_at, first_bar_id = _add_outcome_bar(stack)
    correction_known_at, corrected_bar_id = _correct_outcome_bar(
        stack,
        first_bar_id,
        close_value=Decimal("10.70"),
    )
    assert correction_known_at > first_known_at
    first = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=first_known_at,
            expected_current_revision_id=None,
        ),
        _context("wp10-settle-correction-base", "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome_claim(stack),
    )
    second = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=correction_known_at,
            expected_current_revision_id=first.market_target_outcome_revision_id,
        ),
        _context("wp10-settle-correction-2", "CORRECT_MARKET_OUTCOME"),
        runtime_claim=_outcome_claim(stack),
    )

    assert second.market_target_outcome_id == first.market_target_outcome_id
    assert second.revision_ordinal == 2
    assert second.supersedes_revision_id == first.market_target_outcome_revision_id
    with psycopg.connect(stack.database_url) as connection:
        rows = connection.execute(
            """
            SELECT revision.revision_ordinal, source.bar_revision_id,
                   metric.decimal_value
            FROM mra.market_target_outcome_revision AS revision
            JOIN mra.market_target_outcome_source AS source
              ON source.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
             AND source.source_kind = 'BAR_REVISION'
            JOIN mra.market_target_outcome_metric AS metric
              ON metric.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
            WHERE revision.market_target_outcome_id = %s
            ORDER BY revision.revision_ordinal
            """,
            (first.market_target_outcome_id,),
        ).fetchall()
    assert rows[0][0:2] == (1, first_bar_id)
    assert Decimal(rows[0][2]) == Decimal("0.049504950495049505")
    assert rows[1][0:2] == (2, corrected_bar_id)
    assert Decimal(rows[1][2]) == Decimal("0.059405940594059406")
    verifier = OutcomeVerifier(
        PostgresOutcomeQueryProvider(stack.pool),
        PostgresOutcomeVerificationProvider(stack.pool),
    )
    assert verifier.verify(first.market_target_outcome_revision_id).matched
    assert verifier.verify(second.market_target_outcome_revision_id).matched


def test_exact_source_gap_closes_unavailable_without_value_fallback(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, gap_id = _add_outcome_gap(stack)
    assert gap_id is not None
    result = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        _context("wp10-settle-gap", "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome_claim(stack),
    )

    assert result.status.value == "UNAVAILABLE"
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT source.source_kind, source.source_gap_id,
                   observation.value_status,
                   observation.availability_status,
                   observation.finality_status,
                   observation.selected_value,
                   metric.value_status, metric.decimal_value,
                   reason.reason_code
            FROM mra.market_target_outcome_revision AS revision
            JOIN mra.market_target_outcome_source AS source
              ON source.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
             AND source.source_kind = 'SOURCE_GAP'
            JOIN mra.market_target_outcome_observation AS observation
              ON observation.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
            JOIN mra.market_target_outcome_metric AS metric
              ON metric.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
            JOIN mra.market_target_outcome_reason AS reason
              ON reason.market_target_outcome_revision_id =
                 revision.market_target_outcome_revision_id
             AND reason.reason_dimension = 'OBSERVATION'
            WHERE revision.market_target_outcome_revision_id = %s
            """,
            (result.market_target_outcome_revision_id,),
        ).fetchone()
    assert row == (
        "SOURCE_GAP",
        gap_id,
        "UNAVAILABLE",
        "UNAVAILABLE",
        "UNKNOWN",
        None,
        "UNAVAILABLE",
        None,
        "OBSERVATION_UNAVAILABLE",
    )


def test_concurrent_identical_settlement_has_one_writer_and_exact_replay(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, gap_id = _add_outcome_gap(stack)
    assert gap_id is not None
    claim = _outcome_claim(stack)
    request = SettleMarketTargetOutcomeRequest(
        commitment_id=commitment_id,
        observation_cutoff=event_end,
        knowledge_cutoff=known_at,
        expected_current_revision_id=None,
    )
    context = _context("wp10-concurrent-identical", "SETTLE_DUE_OUTCOME")
    barrier = Barrier(2)

    def settle():
        return _concurrent_application(stack, barrier).settle_market_target_outcome(
            request,
            context,
            runtime_claim=claim,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(executor.submit(settle) for _ in range(2))
        results = tuple(future.result() for future in futures)

    assert {item.replayed for item in results} == {False, True}
    assert len({item.market_target_outcome_revision_id for item in results}) == 1
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.market_target_outcome
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_revision
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'SETTLE_MARKET_TARGET_OUTCOME'
                 AND scope_id = %(scope_id)s),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'SETTLE_MARKET_TARGET_OUTCOME'
                 AND aggregate_id = %(outcome_id)s)
            """,
            {
                "commitment_id": commitment_id,
                "scope_id": str(commitment_id),
                "outcome_id": str(results[0].market_target_outcome_id),
            },
        ).fetchone()
    assert counts == (1, 1, 1, 1)


def test_same_idempotency_identity_with_changed_cutoff_fails_closed(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, _ = _add_outcome_bar(stack)
    claim = _outcome_claim(stack)
    context = _context("wp10-changed-request", "SETTLE_DUE_OUTCOME")
    request = SettleMarketTargetOutcomeRequest(
        commitment_id=commitment_id,
        observation_cutoff=event_end,
        knowledge_cutoff=known_at,
        expected_current_revision_id=None,
    )
    first = _application(stack).settle_market_target_outcome(
        request,
        context,
        runtime_claim=claim,
    )

    with pytest.raises(IdempotencyKeyReusedError):
        _application(stack).settle_market_target_outcome(
            replace(
                request,
                knowledge_cutoff=known_at + timedelta(microseconds=1),
            ),
            context,
            runtime_claim=claim,
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.market_target_outcome_revision
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'SETTLE_MARKET_TARGET_OUTCOME'
                 AND scope_id = %(scope_id)s),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'SETTLE_MARKET_TARGET_OUTCOME'
                 AND aggregate_id = %(outcome_id)s)
            """,
            {
                "commitment_id": commitment_id,
                "scope_id": str(commitment_id),
                "outcome_id": str(first.market_target_outcome_id),
            },
        ).fetchone()
    assert counts == (1, 1, 1)


def test_concurrent_corrections_cannot_fork_revision_leaf(outcome_stack) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, first_known_at, first_bar_id = _add_outcome_bar(stack)
    first = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=first_known_at,
            expected_current_revision_id=None,
        ),
        _context("wp10-concurrent-correction-base", "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome_claim(stack),
    )
    correction_known_at, _ = _correct_outcome_bar(
        stack,
        first_bar_id,
        close_value=Decimal("10.70"),
    )
    request = SettleMarketTargetOutcomeRequest(
        commitment_id=commitment_id,
        observation_cutoff=event_end,
        knowledge_cutoff=correction_known_at,
        expected_current_revision_id=first.market_target_outcome_revision_id,
    )
    claims = (_outcome_claim(stack), _outcome_claim(stack))
    contexts = (
        _context("wp10-concurrent-correction-a", "CORRECT_MARKET_OUTCOME"),
        _context("wp10-concurrent-correction-b", "CORRECT_MARKET_OUTCOME"),
    )
    barrier = Barrier(2)

    def settle(index: int):
        try:
            return _concurrent_application(
                stack,
                barrier,
            ).settle_market_target_outcome(
                request,
                contexts[index],
                runtime_claim=claims[index],
            )
        except OutcomeRevisionConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(executor.submit(settle, index) for index in range(2))
        results = tuple(future.result() for future in futures)

    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, OutcomeRevisionConflictError) for item in results) == 1
    with psycopg.connect(stack.database_url) as connection:
        chain = connection.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE supersedes_revision_id = %s),
                   count(*) FILTER (
                       WHERE NOT EXISTS (
                           SELECT 1
                           FROM mra.market_target_outcome_revision AS successor
                           WHERE successor.supersedes_revision_id =
                                 revision.market_target_outcome_revision_id
                       )
                   )
            FROM mra.market_target_outcome_revision AS revision
            WHERE market_target_outcome_id = %s
            """,
            (
                first.market_target_outcome_revision_id,
                first.market_target_outcome_id,
            ),
        ).fetchone()
    assert chain == (2, 1, 1)


def test_stale_outcome_fence_has_zero_business_and_failure_writes(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, _ = _add_outcome_bar(stack)
    claim = _outcome_claim(stack)
    stale_claim = replace(claim, fence_token=claim.fence_token + 1)

    with pytest.raises(StaleFenceError):
        _application(stack).settle_market_target_outcome(
            SettleMarketTargetOutcomeRequest(
                commitment_id=commitment_id,
                observation_cutoff=event_end,
                knowledge_cutoff=known_at,
                expected_current_revision_id=None,
            ),
            _context("wp10-stale-settle", "SETTLE_DUE_OUTCOME"),
            runtime_claim=stale_claim,
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.market_target_outcome
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_revision
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind LIKE 'SETTLE_MARKET_TARGET_OUTCOME%%'
                 AND scope_id IN (%(scope_id)s, %(attempt_id)s)),
              (SELECT count(*) FROM mra.audit_event
               WHERE action LIKE 'SETTLE_MARKET_TARGET_OUTCOME%%'
                 AND aggregate_id LIKE %(aggregate_pattern)s)
            """,
            {
                "commitment_id": commitment_id,
                "scope_id": str(commitment_id),
                "attempt_id": str(stale_claim.attempt_id),
                "aggregate_pattern": (
                    f"SETTLE_MARKET_TARGET_OUTCOME:{commitment_id}%"
                ),
            },
        ).fetchone()
    assert counts == (0, 0, 0, 0)


def test_missing_exact_source_rolls_back_and_records_fenced_failure(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, gap_id = _add_outcome_gap(stack, include_gap=False)
    assert gap_id is None
    runtime, claim = _outcome_runtime_claim(stack)

    with pytest.raises(
        OutcomeInputResolutionError,
        match="neither exact bar nor exact SourceGap",
    ):
        _application(stack).settle_market_target_outcome(
            SettleMarketTargetOutcomeRequest(
                commitment_id=commitment_id,
                observation_cutoff=event_end,
                knowledge_cutoff=known_at,
                expected_current_revision_id=None,
            ),
            _context("wp10-missing-source", "SETTLE_DUE_OUTCOME"),
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.market_target_outcome
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_revision
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'SETTLE_MARKET_TARGET_OUTCOME'
                 AND scope_id = %(scope_id)s AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'SETTLE_MARKET_TARGET_OUTCOME_FAILED'
                 AND aggregate_id = %(aggregate_id)s)
            """,
            {
                "commitment_id": commitment_id,
                "scope_id": str(commitment_id),
                "aggregate_id": (
                    f"SETTLE_MARKET_TARGET_OUTCOME:{commitment_id}"
                ),
            },
        ).fetchone()
    assert counts == (0, 0, 1, 1)


def test_mid_write_failure_leaves_no_partial_outcome_before_failure_record(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, _ = _add_outcome_bar(stack)
    runtime, claim = _outcome_runtime_claim(stack)
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.fail_wp10_metric_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'injected Outcome metric failure'
                  USING ERRCODE = '55000';
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER wp10_injected_metric_insert
            BEFORE INSERT ON mra.market_target_outcome_metric
            FOR EACH ROW EXECUTE FUNCTION mra.fail_wp10_metric_insert()
            """
        )
    try:
        with pytest.raises(OutcomeAuthorityIntegrityError):
            _application(stack).settle_market_target_outcome(
                SettleMarketTargetOutcomeRequest(
                    commitment_id=commitment_id,
                    observation_cutoff=event_end,
                    knowledge_cutoff=known_at,
                    expected_current_revision_id=None,
                ),
                _context("wp10-mid-write-failure", "SETTLE_DUE_OUTCOME"),
                runtime_claim=claim,
            )
    finally:
        with psycopg.connect(stack.database_url) as connection:
            connection.execute(
                "DROP TRIGGER wp10_injected_metric_insert "
                "ON mra.market_target_outcome_metric"
            )
            connection.execute("DROP FUNCTION mra.fail_wp10_metric_insert()")

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "FAILED"
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.market_target_outcome
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_revision
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_source),
              (SELECT count(*) FROM mra.market_target_outcome_observation),
              (SELECT count(*) FROM mra.market_target_outcome_metric),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'SETTLE_MARKET_TARGET_OUTCOME'
                 AND scope_id = %(scope_id)s AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'SETTLE_MARKET_TARGET_OUTCOME_FAILED')
            """,
            {
                "commitment_id": commitment_id,
                "scope_id": str(commitment_id),
            },
        ).fetchone()
    assert counts == (0, 0, 0, 0, 0, 1, 1)

    recovery_runtime, recovery_claim = _outcome_runtime_claim(stack)
    recovered = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        _context("wp10-mid-write-recovery", "RECOVER_SETTLEMENT"),
        runtime_claim=recovery_claim,
    )
    assert recovered.revision_ordinal == 1
    assert recovered.replayed is False
    assert recovery_runtime.inspect_run(recovery_claim.run_id).run_state == "SUCCEEDED"


def test_failure_recording_failure_rolls_back_incident_and_keeps_claim_live(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, _ = _add_outcome_gap(stack, include_gap=False)
    runtime, claim = _outcome_runtime_claim(stack)
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.fail_wp10_failure_audit()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.action = 'SETTLE_MARKET_TARGET_OUTCOME_FAILED' THEN
                    RAISE EXCEPTION 'injected Outcome failure-recording failure'
                      USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER wp10_injected_failure_audit
            BEFORE INSERT ON mra.audit_event
            FOR EACH ROW EXECUTE FUNCTION mra.fail_wp10_failure_audit()
            """
        )
    try:
        with pytest.raises(OutcomeAuthorityIntegrityError):
            _application(stack).settle_market_target_outcome(
                SettleMarketTargetOutcomeRequest(
                    commitment_id=commitment_id,
                    observation_cutoff=event_end,
                    knowledge_cutoff=known_at,
                    expected_current_revision_id=None,
                ),
                _context("wp10-failure-record-failure", "SETTLE_DUE_OUTCOME"),
                runtime_claim=claim,
            )
    finally:
        with psycopg.connect(stack.database_url) as connection:
            connection.execute(
                "DROP TRIGGER wp10_injected_failure_audit ON mra.audit_event"
            )
            connection.execute("DROP FUNCTION mra.fail_wp10_failure_audit()")

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "RUNNING"
    assert trace.steps[0].state == "RUNNING"
    assert trace.steps[0].attempt_states == ("RUNNING",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.market_target_outcome
               WHERE commitment_id = %(commitment_id)s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind LIKE 'SETTLE_MARKET_TARGET_OUTCOME%%'
                 AND scope_id IN (%(scope_id)s, %(attempt_id)s)),
              (SELECT count(*) FROM mra.audit_event
               WHERE action LIKE 'SETTLE_MARKET_TARGET_OUTCOME%%')
            """,
            {
                "commitment_id": commitment_id,
                "scope_id": str(commitment_id),
                "attempt_id": str(claim.attempt_id),
            },
        ).fetchone()
    assert counts == (0, 0, 0)


def test_closed_outcome_root_revision_and_children_are_append_only(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, gap_id = _add_outcome_gap(stack)
    assert gap_id is not None
    result = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        _context("wp10-append-only", "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome_claim(stack),
    )
    with psycopg.connect(stack.database_url) as connection:
        rows = connection.execute(
            """
            SELECT
              (SELECT market_target_outcome_source_id
               FROM mra.market_target_outcome_source
               WHERE market_target_outcome_revision_id = %(revision_id)s
               ORDER BY source_ordinal LIMIT 1),
              (SELECT market_target_outcome_observation_id
               FROM mra.market_target_outcome_observation
               WHERE market_target_outcome_revision_id = %(revision_id)s
               LIMIT 1),
              (SELECT market_target_outcome_metric_id
               FROM mra.market_target_outcome_metric
               WHERE market_target_outcome_revision_id = %(revision_id)s
               LIMIT 1),
              (SELECT market_target_outcome_metric_reference_id
               FROM mra.market_target_outcome_metric_reference
               WHERE market_target_outcome_revision_id = %(revision_id)s
               LIMIT 1),
              (SELECT market_target_outcome_metric_observation_id
               FROM mra.market_target_outcome_metric_observation
               WHERE market_target_outcome_revision_id = %(revision_id)s
               LIMIT 1),
              (SELECT market_target_outcome_reason_id
               FROM mra.market_target_outcome_reason
               WHERE market_target_outcome_revision_id = %(revision_id)s
               LIMIT 1)
            """,
            {"revision_id": result.market_target_outcome_revision_id},
        ).fetchone()
    assert rows is not None
    identities = (
        (
            "market_target_outcome",
            "market_target_outcome_id",
            result.market_target_outcome_id,
        ),
        (
            "market_target_outcome_revision",
            "market_target_outcome_revision_id",
            result.market_target_outcome_revision_id,
        ),
        ("market_target_outcome_source", "market_target_outcome_source_id", rows[0]),
        (
            "market_target_outcome_observation",
            "market_target_outcome_observation_id",
            rows[1],
        ),
        ("market_target_outcome_metric", "market_target_outcome_metric_id", rows[2]),
        (
            "market_target_outcome_metric_reference",
            "market_target_outcome_metric_reference_id",
            rows[3],
        ),
        (
            "market_target_outcome_metric_observation",
            "market_target_outcome_metric_observation_id",
            rows[4],
        ),
        ("market_target_outcome_reason", "market_target_outcome_reason_id", rows[5]),
    )
    with psycopg.connect(stack.database_url, autocommit=True) as connection:
        for table, primary_key, identity in identities:
            with pytest.raises(psycopg.Error) as update_error:
                connection.execute(
                    f"UPDATE mra.{table} SET created_at = created_at "
                    f"WHERE {primary_key} = %s",
                    (identity,),
                )
            assert update_error.value.sqlstate == "55000"
            with pytest.raises(psycopg.Error) as delete_error:
                connection.execute(
                    f"DELETE FROM mra.{table} WHERE {primary_key} = %s",
                    (identity,),
                )
            assert delete_error.value.sqlstate == "55000"


def test_replay_verifier_reports_hash_and_immutable_fact_mutation(
    outcome_stack,
) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, _ = _add_outcome_bar(stack)
    result = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        _context("wp10-replay-mutation", "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome_claim(stack),
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_metric
            DISABLE TRIGGER market_target_outcome_metric_append_only
            """
        )
        connection.execute(
            """
            UPDATE mra.market_target_outcome_metric
            SET decimal_value = decimal_value + 1,
                content_sha256 = %s
            WHERE market_target_outcome_revision_id = %s
            """,
            ("f" * 64, result.market_target_outcome_revision_id),
        )
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_metric
            ENABLE TRIGGER market_target_outcome_metric_append_only
            """
        )

    report = OutcomeVerifier(
        PostgresOutcomeQueryProvider(stack.pool),
        PostgresOutcomeVerificationProvider(stack.pool),
    ).verify(result.market_target_outcome_revision_id)
    assert report.matched is False
    assert report.mismatch_count >= 2
    assert OutcomeMismatchKind.HASH_MISMATCH in {
        item.kind for item in report.mismatches
    }
    assert OutcomeMismatchKind.IMMUTABLE_FACT_MUTATION in {
        item.kind for item in report.mismatches
    }
    with psycopg.connect(stack.database_url) as connection:
        persisted = connection.execute(
            """
            SELECT content_sha256
            FROM mra.market_target_outcome_metric
            WHERE market_target_outcome_revision_id = %s
            """,
            (result.market_target_outcome_revision_id,),
        ).fetchone()
    assert persisted == ("f" * 64,)


def test_replay_verifier_distinguishes_missing_roster_rows(outcome_stack) -> None:
    stack = outcome_stack
    result = _settled_for_verification(
        stack,
        key="wp10-replay-missing",
        gap=True,
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_reason
            DISABLE TRIGGER market_target_outcome_reason_append_only
            """
        )
        connection.execute(
            """
            DELETE FROM mra.market_target_outcome_reason
            WHERE market_target_outcome_revision_id = %s
              AND reason_ordinal = (
                  SELECT max(reason_ordinal)
                  FROM mra.market_target_outcome_reason
                  WHERE market_target_outcome_revision_id = %s
              )
            """,
            (
                result.market_target_outcome_revision_id,
                result.market_target_outcome_revision_id,
            ),
        )
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_reason
            ENABLE TRIGGER market_target_outcome_reason_append_only
            """
        )

    report = OutcomeVerifier(
        PostgresOutcomeQueryProvider(stack.pool),
        PostgresOutcomeVerificationProvider(stack.pool),
    ).verify(result.market_target_outcome_revision_id)
    kinds = {item.kind for item in report.mismatches}
    assert OutcomeMismatchKind.MISSING_ROW in kinds
    assert OutcomeMismatchKind.COUNT_MISMATCH in kinds
    assert OutcomeMismatchKind.HASH_MISMATCH in kinds


def test_replay_verifier_distinguishes_extra_and_order_mismatch(
    outcome_stack,
) -> None:
    stack = outcome_stack
    result = _settled_for_verification(
        stack,
        key="wp10-replay-extra-order",
    )
    with psycopg.connect(stack.database_url) as connection:
        revision = connection.execute(
            """
            SELECT market_target_outcome_id, revision_ordinal, settled_at
            FROM mra.market_target_outcome_revision
            WHERE market_target_outcome_revision_id = %s
            """,
            (result.market_target_outcome_revision_id,),
        ).fetchone()
        assert revision is not None
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_reason
            DISABLE TRIGGER outcome_reason_open_guard
            """
        )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            INSERT INTO mra.market_target_outcome_reason (
                market_target_outcome_reason_id,
                market_target_outcome_revision_id,
                market_target_outcome_id, revision_ordinal,
                reason_ordinal, reason_dimension, reason_code,
                market_target_outcome_source_id,
                market_target_outcome_observation_id,
                market_target_outcome_metric_id,
                content_sha256, created_at
            ) VALUES (%s, %s, %s, %s, 2, 'REVISION', 'INJECTED_EXTRA',
                      NULL, NULL, NULL, %s, %s)
            """,
            (
                uuid4(),
                result.market_target_outcome_revision_id,
                revision[0],
                revision[1],
                "e" * 64,
                revision[2],
            ),
        )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_reason
            ENABLE TRIGGER outcome_reason_open_guard
            """
        )

    report = OutcomeVerifier(
        PostgresOutcomeQueryProvider(stack.pool),
        PostgresOutcomeVerificationProvider(stack.pool),
    ).verify(result.market_target_outcome_revision_id)
    kinds = {item.kind for item in report.mismatches}
    assert OutcomeMismatchKind.EXTRA_ROW in kinds
    assert OutcomeMismatchKind.COUNT_MISMATCH in kinds
    assert OutcomeMismatchKind.ORDER_MISMATCH in kinds
    assert OutcomeMismatchKind.HASH_MISMATCH in kinds


def test_replay_verifier_distinguishes_reference_binding_mismatch(
    outcome_stack,
) -> None:
    stack = outcome_stack
    result = _settled_for_verification(
        stack,
        key="wp10-replay-reference",
    )
    injected_reference_id = uuid4()
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_metric_reference
            DROP CONSTRAINT outcome_metric_reference_root_fk
            """
        )
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_metric_reference
            DROP CONSTRAINT outcome_metric_reference_observation_fk
            """
        )
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_metric_reference
            DISABLE TRIGGER market_target_outcome_metric_reference_append_only
            """
        )
        connection.execute(
            """
            UPDATE mra.market_target_outcome_metric_reference
            SET decision_reference_observation_id = %s
            WHERE market_target_outcome_revision_id = %s
            """,
            (injected_reference_id, result.market_target_outcome_revision_id),
        )

    report = OutcomeVerifier(
        PostgresOutcomeQueryProvider(stack.pool),
        PostgresOutcomeVerificationProvider(stack.pool),
    ).verify(result.market_target_outcome_revision_id)
    assert OutcomeMismatchKind.REFERENCE_MISMATCH in {
        item.kind for item in report.mismatches
    }


def test_replay_verifier_distinguishes_runtime_identity_mismatch(
    outcome_stack,
) -> None:
    stack = outcome_stack
    result = _settled_for_verification(
        stack,
        key="wp10-replay-runtime",
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_revision
            DROP CONSTRAINT outcome_revision_runtime_attempt_fk
            """
        )
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_revision
            DROP CONSTRAINT outcome_revision_receipt_claim_fk
            """
        )
        connection.execute(
            """
            ALTER TABLE mra.market_target_outcome_revision
            DISABLE TRIGGER market_target_outcome_revision_append_only
            """
        )
        connection.execute(
            """
            UPDATE mra.market_target_outcome_revision
            SET runtime_attempt_id = %s
            WHERE market_target_outcome_revision_id = %s
            """,
            (uuid4(), result.market_target_outcome_revision_id),
        )

    report = OutcomeVerifier(
        PostgresOutcomeQueryProvider(stack.pool),
        PostgresOutcomeVerificationProvider(stack.pool),
    ).verify(result.market_target_outcome_revision_id)
    assert OutcomeMismatchKind.RUNTIME_IDENTITY_MISMATCH in {
        item.kind for item in report.mismatches
    }


def test_representative_outcome_queries_use_declared_indexes(outcome_stack) -> None:
    stack = outcome_stack
    target = _register_midnight_target(stack)
    commitment_id = _open_decision(stack, target)
    event_end, known_at, _ = _add_outcome_bar(stack)
    context = _context("wp10-query-plan", "SETTLE_DUE_OUTCOME")
    result = _application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        context,
        runtime_claim=_outcome_claim(stack),
    )
    statements = (
        (
            "SELECT market_target_outcome_id "
            "FROM mra.market_target_outcome WHERE commitment_id = %s",
            (commitment_id,),
            "market_target_outcome_commitment_idx",
        ),
        (
            "SELECT market_target_outcome_revision_id "
            "FROM mra.market_target_outcome_revision "
            "WHERE commitment_id = %s AND request_identity = %s",
            (commitment_id, context.idempotency_key),
            "outcome_revision_request_idx",
        ),
        (
            "SELECT market_target_outcome_source_id "
            "FROM mra.market_target_outcome_source "
            "WHERE market_target_outcome_revision_id = %s "
            "ORDER BY source_ordinal",
            (result.market_target_outcome_revision_id,),
            "outcome_source_revision_idx",
        ),
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute("SET LOCAL enable_seqscan = off")
        for statement, parameters, expected_index in statements:
            plan = "\n".join(
                str(row[0])
                for row in connection.execute(
                    f"EXPLAIN (ANALYZE, COSTS OFF, FORMAT TEXT) {statement}",
                    parameters,
                ).fetchall()
            )
            assert expected_index in plan, plan
