"""Manual execution and Fill-derived position lifecycle adapters.

The first three handlers are deliberately observation-only.  A lifecycle run
may see an H4.5 confirmation and a human-recorded Fill, but it cannot create
either one.  Later H7 assessment stages stay fail closed until durable,
independently verifiable assessment Readers exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.risk_reduction import (
    load_symbol_trading_session_status_set,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    ordered_references,
    reference_path,
    require_single_reference,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import ArtifactId, PositionBookId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.repositories import (
    RiskReductionManualIntentRepository,
)
from market_regime_alpha.execution.risk_reduction import (
    RiskReductionConfirmationResult,
    RiskReductionConfirmationState,
)
from market_regime_alpha.position.authority import (
    PositionSnapshot,
    PositionState,
)


class ManualConfirmationStageHandler:
    """Observe an external H4.5 confirmation; never perform confirmation."""

    stage_name = LifecycleStageName.MANUAL_CONFIRMATION
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, repository: RiskReductionManualIntentRepository) -> None:
        self._repository = repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        risk_reference = require_single_reference(
            context, LifecycleObjectType.RISK_REDUCING_DECISION
        )
        result = self._repository.get_confirmed_risk_reduction(
            ArtifactId(str(risk_reference.object_id))
        )
        if result is None:
            return StageExecutionResult(
                stage_status=LifecycleStageStatus.WAITING,
                run_status=LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
                input_references=(risk_reference,),
                output_references=(),
                model_versions=(),
                configuration_hashes=(),
                reason_codes=(
                    "BROKER_NOT_INVOKED",
                    "MANUAL_CONFIRMATION_REQUIRED",
                    "NO_FILL_CREATED",
                    "NO_ORDER_CREATED",
                ),
                blocker_reason=(
                    "No durable external H4.5 confirmed intent exists for the "
                    "risk-reducing decision"
                ),
            )
        _verify_confirmation_result(
            context=context,
            repository=self._repository,
            risk_reference=risk_reference,
            result=result,
        )
        output = _repository_reference(
            object_type=LifecycleObjectType.RISK_REDUCTION_CONFIRMATION,
            object_id=result.attempt.attempt_id,
            payload=result.attempt.to_canonical_dict(),
            reader_kind=LifecycleReaderKind.RISK_REDUCTION_REPOSITORY,
            available_at=result.attempt.confirmed_at,
        )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=(risk_reference,),
            output_references=(output,),
            model_versions=(),
            configuration_hashes=(result.attempt.confirmation_policy_hash,),
            reason_codes=(
                "BROKER_NOT_INVOKED",
                "EXTERNAL_MANUAL_CONFIRMATION_VERIFIED",
                "NO_FILL_CREATED",
                "NO_ORDER_CREATED",
            ),
            blocker_reason=None,
        )


class ManualTradeStageHandler:
    """Load the existing ManualTrade created by H4.5 and wait for a Fill."""

    stage_name = LifecycleStageName.MANUAL_TRADE
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, repository: RiskReductionManualIntentRepository) -> None:
        self._repository = repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        risk_reference = require_single_reference(
            context, LifecycleObjectType.RISK_REDUCING_DECISION
        )
        confirmation_reference = require_single_reference(
            context, LifecycleObjectType.RISK_REDUCTION_CONFIRMATION
        )
        result = self._repository.get_confirmed_risk_reduction(
            ArtifactId(str(risk_reference.object_id))
        )
        if result is None:
            raise ValueError(
                "confirmation receipt exists without durable H4.5 confirmation"
            )
        _verify_confirmation_result(
            context=context,
            repository=self._repository,
            risk_reference=risk_reference,
            result=result,
        )
        _verify_reference(
            confirmation_reference,
            object_id=result.attempt.attempt_id,
            payload=result.attempt.to_canonical_dict(),
        )
        trade = _required_trade(result)
        output = _repository_reference(
            object_type=LifecycleObjectType.MANUAL_TRADE,
            object_id=ArtifactId(str(trade.manual_trade_id)),
            payload=trade.to_canonical_dict(),
            reader_kind=LifecycleReaderKind.MANUAL_TRADE_REPOSITORY,
            available_at=trade.updated_at,
        )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.WAITING_FOR_FILL,
            input_references=ordered_references(
                (risk_reference, confirmation_reference)
            ),
            output_references=(output,),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=(
                "BROKER_NOT_INVOKED",
                "EXISTING_MANUAL_TRADE_VERIFIED",
                "NO_FILL_CREATED",
                "NO_ORDER_CREATED",
            ),
            blocker_reason=(
                "The verified ManualTrade is an intent record; an external "
                "human-recorded Fill is required"
            ),
        )


class FillPositionStageHandler:
    """Observe external Fill authority and rebuild Position deterministically."""

    stage_name = LifecycleStageName.FILL_POSITION
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, repository: RiskReductionManualIntentRepository) -> None:
        self._repository = repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        risk_reference = require_single_reference(
            context, LifecycleObjectType.RISK_REDUCING_DECISION
        )
        confirmation_reference = require_single_reference(
            context, LifecycleObjectType.RISK_REDUCTION_CONFIRMATION
        )
        trade_reference = require_single_reference(
            context, LifecycleObjectType.MANUAL_TRADE
        )
        book_reference = require_single_reference(
            context, LifecycleObjectType.POSITION_BOOK
        )
        calendar_reference = require_single_reference(
            context, LifecycleObjectType.TRADING_CALENDAR_ARTIFACT
        )
        statuses_reference = require_single_reference(
            context, LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET
        )
        result = self._repository.get_confirmed_risk_reduction(
            ArtifactId(str(risk_reference.object_id))
        )
        if result is None:
            raise ValueError("ManualTrade stage lost its durable H4.5 authority")
        _verify_confirmation_result(
            context=context,
            repository=self._repository,
            risk_reference=risk_reference,
            result=result,
        )
        _verify_reference(
            confirmation_reference,
            object_id=result.attempt.attempt_id,
            payload=result.attempt.to_canonical_dict(),
        )
        trade = _required_trade(result)
        if str(trade_reference.object_id) != str(trade.manual_trade_id):
            raise ValueError("ManualTrade identity changed after stage settlement")
        reducing_fills = self._repository.fills_for_trade(trade.manual_trade_id)
        inputs = ordered_references(
            (
                confirmation_reference,
                trade_reference,
                book_reference,
                calendar_reference,
                statuses_reference,
            )
        )
        if not reducing_fills:
            return StageExecutionResult(
                stage_status=LifecycleStageStatus.WAITING,
                run_status=LifecycleRunStatus.WAITING_FOR_FILL,
                input_references=inputs,
                output_references=(),
                model_versions=(),
                configuration_hashes=(),
                reason_codes=(
                    "BROKER_NOT_INVOKED",
                    "NO_EXTERNAL_FILL_OBSERVED",
                    "NO_FILL_CREATED",
                    "NO_ORDER_CREATED",
                ),
                blocker_reason=(
                    "No external Fill is recorded for the verified ManualTrade"
                ),
            )
        book = self._repository.get_position_book(
            PositionBookId(str(book_reference.object_id))
        )
        _verify_reference(
            book_reference,
            object_id=ArtifactId(str(book.position_book_id)),
            payload=book.to_canonical_dict(),
        )
        calendar = _load_calendar(calendar_reference)
        statuses = load_symbol_trading_session_status_set(statuses_reference)
        fills = self._repository.fills_for_book(book.position_book_id)
        if not {item.fill_id for item in reducing_fills}.issubset(
            {item.fill_id for item in fills}
        ):
            raise ValueError("ManualTrade Fill is absent from PositionBook authority")
        position = self._repository.get_fill_derived_position(
            ArtifactId(str(risk_reference.object_id))
        )
        if position is None:
            raise ValueError("external Fill disappeared during Position projection")
        if tuple(item.fill_id for item in fills) != position.source_fill_ids:
            raise ValueError(
                "Fill ledger changed while the Position reference was being built"
            )
        status_ids = tuple(sorted((item.status_id for item in statuses), key=str))
        if (
            position.calendar_artifact_id != calendar.artifact_id
            or position.calendar_content_hash != calendar.content_hash
            or position.source_trading_status_ids != status_ids
        ):
            raise ValueError("Fill-derived Position Reader evidence mismatch")
        outputs = ordered_references(
            (
                *(
                    _repository_reference(
                        object_type=LifecycleObjectType.FILL,
                        object_id=ArtifactId(str(fill.fill_id)),
                        payload=fill.to_canonical_dict(),
                        reader_kind=LifecycleReaderKind.MANUAL_FILL_LEDGER,
                        available_at=fill.recorded_at,
                    )
                    for fill in fills
                ),
                _repository_reference(
                    object_type=LifecycleObjectType.POSITION_SNAPSHOT,
                    object_id=ArtifactId(str(position.snapshot_id)),
                    payload=position.to_canonical_dict(),
                    reader_kind=LifecycleReaderKind.POSITION_SNAPSHOT_REPOSITORY,
                    available_at=position.as_of,
                ),
            )
        )
        return _position_result(
            position=position,
            inputs=inputs,
            outputs=outputs,
        )


def _verify_confirmation_result(
    *,
    context: LifecycleStageContext,
    repository: RiskReductionManualIntentRepository,
    risk_reference: LifecycleObjectReference,
    result: RiskReductionConfirmationResult,
) -> None:
    attempt = result.attempt
    trade = _required_trade(result)
    book_reference = require_single_reference(
        context, LifecycleObjectType.POSITION_BOOK
    )
    book = repository.get_position_book(
        PositionBookId(str(book_reference.object_id))
    )
    _verify_reference(
        book_reference,
        object_id=ArtifactId(str(book.position_book_id)),
        payload=book.to_canonical_dict(),
    )
    current_hash = canonical_hash(result.current_position.to_canonical_dict())
    if (
        attempt.state is not RiskReductionConfirmationState.CONFIRMED_INTENT
        or str(attempt.risk_reducing_decision_id) != str(risk_reference.object_id)
        or attempt.risk_reducing_decision_hash != risk_reference.content_hash
        or attempt.current_position_snapshot_id != result.current_position.snapshot_id
        or attempt.current_position_snapshot_hash != current_hash
        or trade.authority_route is not ManualTradeAuthorityRoute.REDUCING
        or trade.side is not TradeSide.SELL
        or trade.risk_reducing_decision_id != attempt.risk_reducing_decision_id
        or trade.risk_reducing_decision_hash
        != attempt.risk_reducing_decision_hash
        or trade.risk_reduction_confirmation_id != attempt.attempt_id
        or trade.risk_reduction_confirmation_hash != attempt.content_hash
        or trade.source_position_snapshot_id
        != attempt.source_position_snapshot_id
        or trade.source_position_snapshot_hash
        != attempt.source_position_snapshot_hash
        or trade.position_book_id != book.position_book_id
        or trade.thesis_id != book.thesis_id
        or trade.opportunity_id != book.opportunity_id
        or trade.symbol != book.symbol
        or result.current_position.position_book_id != book.position_book_id
        or result.current_position.thesis_id != book.thesis_id
        or result.current_position.opportunity_id != book.opportunity_id
        or result.current_position.symbol != book.symbol
        or result.fill_boundary != "NO_FILL_CREATED"
        or result.broker_boundary != "NO_BROKER_ORDER_CREATED"
    ):
        raise ValueError("H4.5 confirmation scope or lineage mismatch")


def _required_trade(result: RiskReductionConfirmationResult) -> ManualTradeRecord:
    trade = result.manual_trade
    if trade is None:
        raise ValueError("confirmed H4.5 result has no ManualTrade")
    return trade


def _position_result(
    *,
    position: PositionSnapshot,
    inputs: tuple[LifecycleObjectReference, ...],
    outputs: tuple[LifecycleObjectReference, ...],
) -> StageExecutionResult:
    reasons = {
        "BROKER_NOT_INVOKED",
        "EXTERNAL_FILL_AUTHORITY_OBSERVED",
        "FILL_DERIVED_POSITION_REBUILT",
        "NO_FILL_CREATED",
        "NO_ORDER_CREATED",
        f"POSITION_STATE_{position.state.value}",
        *position.reason_codes,
    }
    if position.state is PositionState.RECONCILIATION_REQUIRED:
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.WAITING,
            run_status=LifecycleRunStatus.WAITING_FOR_FILL,
            input_references=inputs,
            output_references=outputs,
            model_versions=(),
            configuration_hashes=(),
            reason_codes=tuple(sorted((*reasons, "POSITION_RECONCILIATION_REQUIRED"))),
            blocker_reason="A correcting external Fill is required for reconciliation",
        )
    if position.state is PositionState.OPEN and position.available_quantity == 0:
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.WAITING,
            run_status=LifecycleRunStatus.WAITING_FOR_T1,
            input_references=inputs,
            output_references=outputs,
            model_versions=(),
            configuration_hashes=(),
            reason_codes=tuple(sorted((*reasons, "A_SHARE_T1_NOT_SELLABLE"))),
            blocker_reason="The Fill-derived A-share Position is waiting for T+1",
        )
    run_status = (
        LifecycleRunStatus.POSITION_OPEN
        if position.state is PositionState.OPEN
        else LifecycleRunStatus.READY_FOR_EXIT_REVIEW
    )
    return StageExecutionResult(
        stage_status=LifecycleStageStatus.COMPLETED,
        run_status=run_status,
        input_references=inputs,
        output_references=outputs,
        model_versions=(),
        configuration_hashes=(),
        reason_codes=tuple(sorted(reasons)),
        blocker_reason=None,
    )


def _load_calendar(reference: LifecycleObjectReference) -> TradingCalendarArtifact:
    payload = _read_json(reference_path(reference))
    calendar = TradingCalendarArtifact.from_canonical_dict(payload)
    _verify_reference(
        reference,
        object_id=calendar.artifact_id,
        payload=calendar.to_canonical_dict(),
        expected_content_hash=calendar.content_hash,
    )
    return calendar


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid lifecycle Reader JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _verify_reference(
    reference: LifecycleObjectReference,
    *,
    object_id: ArtifactId,
    payload: Mapping[str, Any],
    expected_content_hash: str | None = None,
) -> None:
    content_hash = (
        canonical_hash(payload)
        if expected_content_hash is None
        else expected_content_hash
    )
    if (
        str(reference.object_id) != str(object_id)
        or reference.content_hash != content_hash
    ):
        raise ValueError(f"{reference.object_type.value} reference mismatch")


def _repository_reference(
    *,
    object_type: LifecycleObjectType,
    object_id: ArtifactId,
    payload: Mapping[str, Any],
    reader_kind: LifecycleReaderKind,
    available_at: datetime,
) -> LifecycleObjectReference:
    canonical_available_at = available_at.astimezone(timezone.utc)
    if canonical_available_at.microsecond:
        raise ValueError("repository output available_at must have second precision")
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(str(object_id)),
        content_hash=canonical_hash(payload),
        reader_kind=reader_kind,
        locator=None,
        available_at=canonical_available_at,
    )
