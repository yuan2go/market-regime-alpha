from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import sqlite3

import pytest

from market_regime_alpha.application.trading_lifecycle.manual_execution import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.application.trading_lifecycle.traceable_execution import (
    TraceableManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import FillId
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.decision.thesis import ThesisState, transition_thesis
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    ManualOrderState,
    ManualTradeAuthorityRoute,
)
from market_regime_alpha.execution.risk_reduction import (
    RiskReductionConfirmationState,
    validate_h5_h6_operational_lineage,
)
from market_regime_alpha.portfolio.risk_routes import (
    ExecutionConstraintState,
    ReducingExecutionObservation,
    RiskChangeKind,
)
from market_regime_alpha.execution.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.position.authority import PositionProjector, PositionState
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)
from market_regime_alpha.position.thesis_health import (
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    VerifiedThesisHealthBundle,
    thesis_health_command_hash,
)
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import make_h5_fixture
from tests.execution.risk_reduction_confirmation_support import (
    build_confirmation_fixture,
)


pytest_plugins = ("tests.daily_decision.conftest",)


def test_atomic_exit_confirmation_creates_only_route_authorized_manual_intent(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert result.attempt.state is RiskReductionConfirmationState.CONFIRMED_INTENT
    assert result.outcome == "MANUAL_INTENT_CREATED"
    assert result.fill_boundary == "NO_FILL_CREATED"
    assert result.broker_boundary == "NO_BROKER_ORDER_CREATED"
    assert result.manual_trade is not None
    assert result.manual_trade.authority_route is ManualTradeAuthorityRoute.REDUCING
    assert result.manual_trade.side.value == "SELL"
    assert result.manual_trade.intended_quantity == fixture.quantity
    assert result.manual_trade.position_book_id == fixture.book.position_book_id
    assert fixture.repository.get_position_book(
        fixture.book.position_book_id
    ) == fixture.book
    assert fixture.repository.fills_for_trade(
        result.manual_trade.manual_trade_id
    ) == ()

    replay = fixture.repository.confirm_risk_reduction(fixture.command)
    assert replay == result
    restarted = SQLiteRiskReductionManualIntentRepository(
        fixture.repository.path
    )
    assert restarted.confirm_risk_reduction(fixture.command) == result


def test_legal_reduce_creates_sell_intent_with_positive_remainder(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(
        tmp_path,
        daily_decision_fixture,
        action=RiskChangeKind.REDUCE,
    )

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert result.manual_trade is not None
    assert result.manual_trade.target_quantity == fixture.quantity - 40
    assert result.manual_trade.order_quantity == 40
    assert result.manual_trade.intended_quantity == 40
    assert result.manual_trade.side.value == "SELL"


def test_h4_v1_reduce_to_zero_requires_new_exit_decision_without_trade(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(
        tmp_path,
        daily_decision_fixture,
        action=RiskChangeKind.REDUCE,
        reduce_target_zero=True,
    )

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert (
        result.attempt.state
        is RiskReductionConfirmationState.ACTION_SEMANTICS_CONFLICT
    )
    assert result.attempt.reason_codes == (
        "H4_V2_REDUCE_REQUIRES_POSITIVE_REMAINDER",
        "REQUIRES_NEW_EXIT_DECISION",
    )
    assert result.manual_trade is None


def test_current_invalidated_thesis_can_confirm_exit_intent(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(
        tmp_path,
        daily_decision_fixture,
        invalidated_thesis=True,
    )

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert result.manual_trade is not None
    assert result.attempt.state is RiskReductionConfirmationState.CONFIRMED_INTENT


def test_confirmation_rejects_manual_trade_projection_tamper(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    with sqlite3.connect(fixture.repository.path) as connection:
        connection.execute(
            """
            UPDATE manual_trade_records
            SET version = version + 1
            WHERE manual_trade_id = 'manual-trade-h4-5-entry'
            """
        )

    with pytest.raises(ValueError, match="history is not contiguous"):
        fixture.repository.confirm_risk_reduction(fixture.command)


def test_new_append_only_fill_before_confirmation_yields_position_changed(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    ManualExecutionApplicationService(fixture.repository).record_fill(
        fixture.repository.trades_for_book(fixture.book.position_book_id)[0].manual_trade_id,
        external_fill_id="h4-5-entry-correction-before-confirmation",
        quantity=90,
        price=10.0,
        fees=0.0,
        occurred_at=fixture.command.confirmed_at - timedelta(days=1),
        recorded_at=fixture.command.confirmed_at - timedelta(seconds=1),
        actor="manual-operator",
        reason="late-arriving correction changes authoritative Position",
        idempotency_key="h4-5-entry-correction-before-confirmation",
        correction_of_fill_id=FillId("fill-h4-5-entry"),
    )

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert result.attempt.state is RiskReductionConfirmationState.POSITION_CHANGED
    assert result.attempt.source_position_snapshot_id != (
        result.attempt.current_position_snapshot_id
    )
    assert result.attempt.source_position_snapshot_hash != (
        result.attempt.current_position_snapshot_hash
    )
    assert result.manual_trade is None


def test_closed_position_book_blocks_confirmation_without_new_book(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    closed = fixture.book.close(
        closed_at=fixture.command.confirmed_at,
        actor="manual-operator",
        reason="explicit close before confirmation",
    )
    fixture.repository.close_position_book(
        closed,
        expected_version=fixture.book.version,
        idempotency_key="h4-5-close-before-confirm",
    )

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert result.attempt.state is RiskReductionConfirmationState.BLOCKED_ON_RECHECK
    assert result.attempt.reason_codes == ("POSITION_BOOK_OR_THESIS_CLOSED",)
    assert result.manual_trade is None
    assert fixture.repository.open_position_books(fixture.book.account_id) == ()


def test_closed_thesis_blocks_confirmation(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    repository = SQLiteDecisionLifecycleRepository(fixture.repository.path)
    current = repository.get_thesis(fixture.book.thesis_id)
    closed = transition_thesis(
        current,
        to_state=ThesisState.CLOSED,
        actor="thesis-reviewer",
        reason="closed before H4.5 confirmation",
        changed_at=fixture.command.confirmed_at,
    )
    repository.transition_thesis(
        closed,
        expected_version=current.version,
        idempotency_key="h4-5-close-thesis",
        command_hash=canonical_hash(closed.to_canonical_dict()),
    )

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert result.attempt.state is RiskReductionConfirmationState.BLOCKED_ON_RECHECK
    assert result.attempt.reason_codes == ("POSITION_BOOK_OR_THESIS_CLOSED",)
    assert result.manual_trade is None


def test_second_command_cannot_create_another_intent_for_confirmed_decision(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    fixture.repository.confirm_risk_reduction(fixture.command)

    with pytest.raises(ValueError, match="already created a confirmed intent"):
        fixture.repository.confirm_risk_reduction(
            replace(
                fixture.command,
                idempotency_key="h4-5-same-evidence-new-command",
            )
        )


def test_expired_decision_persists_failed_attempt_without_trade(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    result = fixture.repository.confirm_risk_reduction(
        replace(
            fixture.command,
            confirmed_at=(
                fixture.command.confirmed_at
                + timedelta(
                    seconds=fixture.command.confirmation_policy.maximum_decision_age_seconds
                    + 1
                )
            ),
            idempotency_key="h4-5-expired",
        )
    )

    assert result.attempt.state is RiskReductionConfirmationState.EXPIRED
    assert result.manual_trade is None
    assert fixture.repository.get_confirmation_attempt(
        result.attempt.attempt_id
    ) == result.attempt


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            ExecutionConstraintState.SUSPENDED,
            RiskReductionConfirmationState.BLOCKED_ON_RECHECK,
        ),
        (
            ExecutionConstraintState.PRICE_LIMIT_BLOCKED,
            RiskReductionConfirmationState.BLOCKED_ON_RECHECK,
        ),
        (
            ExecutionConstraintState.UNKNOWN,
            RiskReductionConfirmationState.DATA_INSUFFICIENT,
        ),
    ],
)
def test_market_gate_is_replayed_from_fresh_canonical_observation(
    tmp_path, daily_decision_fixture, state, expected
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    source = fixture.command.execution_observation
    observation = ReducingExecutionObservation.create(
        symbol=source.symbol,
        session_date=source.session_date,
        state=state,
        reference_price=source.reference_price,
        average_daily_volume=source.average_daily_volume,
        source_artifact_id=source.source_artifact_id,
        source_artifact_hash=source.source_artifact_hash,
        availability_time=source.availability_time,
        reason_code=f"H4_5_RECHECK_{state.value}",
    )

    result = fixture.repository.confirm_risk_reduction(
        replace(
            fixture.command,
            execution_observation=observation,
            idempotency_key=f"h4-5-{state.value.lower()}",
        )
    )

    assert result.attempt.state is expected
    assert result.attempt.recheck_observation_id == observation.observation_id
    assert result.attempt.recheck_observation_hash == observation.content_hash
    assert result.manual_trade is None


def test_stale_execution_observation_is_data_insufficient(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    source = fixture.command.execution_observation
    stale = ReducingExecutionObservation.create(
        symbol=source.symbol,
        session_date=source.session_date,
        state=source.state,
        reference_price=source.reference_price,
        average_daily_volume=source.average_daily_volume,
        source_artifact_id=source.source_artifact_id,
        source_artifact_hash=source.source_artifact_hash,
        availability_time=(
            fixture.command.confirmed_at
            - timedelta(
                seconds=fixture.command.confirmation_policy.maximum_execution_observation_age_seconds
                + 1
            )
        ),
        reason_code="H4_5_STALE_RECHECK",
    )

    result = fixture.repository.confirm_risk_reduction(
        replace(
            fixture.command,
            execution_observation=stale,
            idempotency_key="h4-5-stale-recheck",
        )
    )

    assert result.attempt.state is RiskReductionConfirmationState.DATA_INSUFFICIENT
    assert result.manual_trade is None


def test_expected_price_range_must_contain_fresh_reference_within_policy(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)

    result = fixture.repository.confirm_risk_reduction(
        replace(
            fixture.command,
            expected_price_lower=9.7,
            expected_price_upper=9.9,
            idempotency_key="h4-5-price-range-blocked",
        )
    )

    assert result.attempt.state is RiskReductionConfirmationState.BLOCKED_ON_RECHECK
    assert result.attempt.reason_codes == (
        "EXPECTED_PRICE_RANGE_OUTSIDE_POLICY",
    )
    assert result.manual_trade is None


def test_command_idempotency_semantic_conflict_is_rejected(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    fixture.repository.confirm_risk_reduction(fixture.command)

    with pytest.raises(ValueError, match="idempotency key reused"):
        fixture.repository.confirm_risk_reduction(
            replace(fixture.command, reason="different confirmation semantics")
        )


def test_reducing_binding_tamper_blocks_trade_and_fill_reads(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    result = fixture.repository.confirm_risk_reduction(fixture.command)
    assert result.manual_trade is not None
    with sqlite3.connect(fixture.repository.path) as connection:
        connection.execute(
            "DROP TRIGGER risk_reducing_manual_trade_bindings_no_update"
        )
        connection.execute(
            """
            UPDATE risk_reducing_manual_trade_bindings
            SET thesis_id = 'forged-thesis'
            """
        )

    with pytest.raises(ValueError, match="reducing trace index mismatch"):
        fixture.repository.get_trade(result.manual_trade.manual_trade_id)
    with pytest.raises(ValueError, match="reducing trace index mismatch"):
        ManualExecutionApplicationService(fixture.repository).record_fill(
            result.manual_trade.manual_trade_id,
            external_fill_id="blocked-tampered-binding",
            quantity=1,
            price=10.0,
            fees=0.0,
            occurred_at=fixture.command.confirmed_at,
            recorded_at=fixture.command.confirmed_at + timedelta(seconds=1),
            actor="manual-operator",
            reason="must fail before Fill insert",
            idempotency_key="blocked-tampered-binding",
        )


def test_non_latest_h5_observation_is_persisted_as_data_insufficient_attempt(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    repository = SQLiteThesisHealthRepository(fixture.repository.path)
    current = repository.get_verified_thesis_health_bundle(
        fixture.command.thesis_health_observation_id
    )
    source = current.input_bundle
    successor_bundle = ThesisHealthInputBundle.create(
        thesis=source.thesis,
        opportunity=source.opportunity,
        market_regime=source.market_regime,
        theme_rotation=source.theme_rotation,
        capital_evolution=source.capital_evolution,
        candidate_set=source.candidate_set,
        signal_snapshot=source.signal_snapshot,
        path_forecast=source.path_forecast,
        price_snapshot=source.price_snapshot,
        configuration=source.configuration,
        rule_set=source.rule_set,
        manual_evidence=source.manual_evidence,
        prior_observation=current.observation,
        assessed_at=source.assessed_at + timedelta(seconds=1),
        actor=source.actor,
        reason="newer operational H5 observation",
    )
    successor = ThesisHealthObservationBuilder().build(successor_bundle)
    repository.save_observation(
        successor,
        input_bundle=successor_bundle,
        idempotency_key="h4-5-newer-health",
        command_hash=thesis_health_command_hash(successor_bundle),
    )

    result = fixture.repository.confirm_risk_reduction(fixture.command)

    assert result.attempt.state is RiskReductionConfirmationState.DATA_INSUFFICIENT
    assert result.attempt.reason_codes == (
        "H5_H6_OPERATIONAL_LINEAGE_NOT_VERIFIED",
    )
    assert result.manual_trade is None


def test_h6_manifest_hash_mismatch_is_persisted_as_data_insufficient_attempt(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)

    result = fixture.repository.confirm_risk_reduction(
        replace(
            fixture.command,
            composite_manifest_hash="sha256:" + "9" * 64,
            idempotency_key="h4-5-wrong-h6-hash",
        )
    )

    assert result.attempt.state is RiskReductionConfirmationState.DATA_INSUFFICIENT
    assert result.attempt.reason_codes == ("H5_H6_CURRENT_LINEAGE_MISMATCH",)
    assert result.manual_trade is None


def test_synthetic_h5_chain_cannot_claim_operational_h6_lineage(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    synthetic_bundle = _bundle(make_h5_fixture())
    synthetic_observation = ThesisHealthObservationBuilder().build(
        synthetic_bundle
    )
    synthetic = VerifiedThesisHealthBundle(
        observation=synthetic_observation,
        input_bundle=synthetic_bundle,
        is_latest=True,
    )
    composite = SQLiteCompositeOperationalRepository(
        fixture.repository.path
    ).get_manifest(fixture.command.composite_manifest_id)

    with pytest.raises(ValueError, match="exact H6 lineage"):
        validate_h5_h6_operational_lineage(
            health_bundle=synthetic,
            composite=composite,
        )


def test_confirmed_reducing_trade_accepts_manual_fill_and_reprojects_position(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    result = fixture.repository.confirm_risk_reduction(fixture.command)
    assert result.manual_trade is not None

    filled_trade, fill = ManualExecutionApplicationService(
        fixture.repository
    ).record_fill(
        result.manual_trade.manual_trade_id,
        external_fill_id="external-h4-5-exit",
        quantity=40,
        price=10.0,
        fees=0.0,
        occurred_at=fixture.command.confirmed_at,
        recorded_at=fixture.command.confirmed_at + timedelta(seconds=1),
        actor="manual-operator",
        reason="partial manual risk reduction Fill",
        idempotency_key="h4-5-partial-fill",
    )

    assert filled_trade.state is ManualOrderState.PARTIALLY_FILLED
    assert fill in fixture.repository.fills_for_book(fixture.book.position_book_id)
    projected = PositionProjector().project_book_t_plus_one(
        book=fixture.book,
        trades=fixture.repository.trades_for_book(fixture.book.position_book_id),
        fills=fixture.repository.fills_for_book(fixture.book.position_book_id),
        calendar=fixture.command.trading_calendar,
        symbol_session_statuses=fixture.command.symbol_trading_statuses,
        as_of=fixture.command.confirmed_at + timedelta(seconds=1),
    )
    assert projected.total_quantity == fixture.quantity - 40
    assert projected.available_quantity == fixture.quantity - 40

    second = fixture.repository.confirm_risk_reduction(
        replace(
            fixture.command,
            confirmed_at=fixture.command.confirmed_at + timedelta(seconds=1),
            idempotency_key="h4-5-second-confirmation",
        )
    )
    assert second.attempt.state is RiskReductionConfirmationState.POSITION_CHANGED
    assert second.manual_trade is None


def test_full_exit_fill_supports_later_explicit_position_book_close(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    result = fixture.repository.confirm_risk_reduction(fixture.command)
    assert result.manual_trade is not None
    service = TraceableManualExecutionApplicationService(fixture.repository)

    filled_trade, _ = service.record_fill(
        result.manual_trade.manual_trade_id,
        external_fill_id="external-h4-5-full-exit",
        quantity=fixture.quantity,
        price=10.0,
        fees=0.0,
        occurred_at=fixture.command.confirmed_at,
        recorded_at=fixture.command.confirmed_at + timedelta(seconds=1),
        actor="manual-operator",
        reason="full manual EXIT Fill",
        idempotency_key="h4-5-full-exit-fill",
    )
    final_position = service.rebuild_a_share_position(
        fixture.book.position_book_id,
        calendar=fixture.command.trading_calendar,
        symbol_session_statuses=fixture.command.symbol_trading_statuses,
        as_of=fixture.command.confirmed_at + timedelta(seconds=1),
    )

    assert filled_trade.state is ManualOrderState.FILLED
    assert final_position.state is PositionState.CLOSED
    assert final_position.total_quantity == 0
    closed = service.close_position_book(
        fixture.book.position_book_id,
        expected_version=fixture.book.version,
        final_position=final_position,
        trading_calendar=fixture.command.trading_calendar,
        symbol_trading_statuses=fixture.command.symbol_trading_statuses,
        actor="manual-operator",
        reason="explicit close after authoritative full EXIT Fill",
        closed_at=fixture.command.confirmed_at + timedelta(seconds=2),
        idempotency_key="h4-5-close-after-full-exit",
    )

    assert closed.state.value == "CLOSED"


def test_atomic_rollback_removes_attempt_and_trade_on_binding_failure(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    with sqlite3.connect(fixture.repository.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_h4_5_binding
            BEFORE INSERT ON risk_reducing_manual_trade_bindings
            BEGIN
                SELECT RAISE(ABORT, 'injected H4.5 binding failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected H4.5"):
        fixture.repository.confirm_risk_reduction(fixture.command)

    with sqlite3.connect(fixture.repository.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM risk_reduction_confirmation_attempts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM manual_trade_records WHERE authority_route = 'REDUCING'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM risk_reduction_confirmation_commands"
        ).fetchone()[0] == 0
