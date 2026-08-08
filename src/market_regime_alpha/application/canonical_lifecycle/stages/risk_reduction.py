"""Read-only H4 risk-reduction continuation for the canonical lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectReference,
    LifecycleObjectType,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
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
from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
    load_verified_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionStatus,
)
from market_regime_alpha.application.operational_research.composite_repository import (
    CompositeOperationalRepository,
)
from market_regime_alpha.core.identity import ArtifactId, PositionBookId, StableId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.decision.opportunity import (
    OpportunityState,
    TradingOpportunity,
)
from market_regime_alpha.decision.repositories import DecisionLifecycleRepository
from market_regime_alpha.decision.thesis import ThesisState, TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.position_book import PositionBook, PositionBookState
from market_regime_alpha.execution.repositories import (
    RiskReductionManualIntentRepository,
)
from market_regime_alpha.execution.risk_reduction import (
    OperationalExitDirectiveV2,
    RiskReductionConfirmationPolicy,
)
from market_regime_alpha.portfolio.repositories import RiskRouteRepository
from market_regime_alpha.portfolio.risk_routes import (
    ReducingExecutionObservation,
    RiskReducingDecisionState,
    VerifiedRiskReducingDecisionBundle,
)
from market_regime_alpha.position.authority import SymbolTradingSessionStatus
from market_regime_alpha.position.thesis_health import (
    ThesisHealthRepository,
    VerifiedThesisHealthBundle,
)


_STATUS_SET_SCHEMA = "symbol-trading-session-status-set-v1"
_MANUAL_CONFIRMATION_BLOCKER = (
    "A separate authenticated manual confirmation is required; no trade, order, "
    "or fill was created"
)


class RiskReductionStageHandler:
    """Verify an existing H4/H4.5 authority chain without confirming intent."""

    stage_name = LifecycleStageName.RISK_REDUCTION
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(
        self,
        *,
        risk_repository: RiskRouteRepository,
        execution_repository: RiskReductionManualIntentRepository,
        decision_repository: DecisionLifecycleRepository,
        thesis_health_repository: ThesisHealthRepository,
        composite_repository: CompositeOperationalRepository,
    ) -> None:
        self._risk_repository = risk_repository
        self._execution_repository = execution_repository
        self._decision_repository = decision_repository
        self._thesis_health_repository = thesis_health_repository
        self._composite_repository = composite_repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        references = _RiskContinuationReferences.from_context(context)
        risk_bundle = self._load_risk_bundle(references)
        decision = risk_bundle.decision
        book = self._execution_repository.get_position_book(
            PositionBookId(str(references.position_book.object_id))
        )
        _verify_reference(
            references.position_book,
            object_id=book.position_book_id,
            content_hash=canonical_hash(book.to_canonical_dict()),
        )
        directive = self._execution_repository.get_operational_exit_directive(
            ArtifactId(str(references.exit_directive.object_id))
        )
        _verify_reference(
            references.exit_directive,
            object_id=directive.directive_id,
            content_hash=directive.content_hash,
        )
        thesis = self._decision_repository.get_thesis(decision.thesis_id)
        opportunity = self._decision_repository.get_opportunity(thesis.opportunity_id)
        health = self._thesis_health_repository.get_verified_thesis_health_bundle(
            ArtifactId(str(references.thesis_health.object_id))
        )
        _verify_reference(
            references.thesis_health,
            object_id=health.observation.observation_id,
            content_hash=health.observation.content_hash,
        )
        composite_file = load_verified_composite_operational_manifest(
            reference_path(references.composite)
        )
        composite_stored = self._composite_repository.get_manifest(
            ArtifactId(str(references.composite.object_id))
        )
        if composite_file != composite_stored:
            raise ValueError("Composite Reader and PostgreSQL authority disagree")
        _verify_reference(
            references.composite,
            object_id=composite_file.manifest.manifest_id,
            content_hash=composite_file.manifest.content_hash,
        )
        calendar = _load_calendar(references.trading_calendar)
        observation = _load_execution_observation(references.execution_observation)
        statuses = load_symbol_trading_session_status_set(references.session_statuses)
        policy = _load_confirmation_policy(references.confirmation_policy)
        _verify_scope(
            context=context,
            risk_bundle=risk_bundle,
            directive=directive,
            book=book,
            thesis=thesis,
            opportunity=opportunity,
            health=health,
            composite=composite_file,
            calendar=calendar,
            observation=observation,
            statuses=statuses,
            policy=policy,
        )
        reasons = tuple(
            sorted(
                {
                    "BROKER_NOT_INVOKED",
                    "H4_RISK_REDUCTION_AUTHORITY_VERIFIED",
                    "MANUAL_CONFIRMATION_REQUIRED",
                    "NO_FILL_CREATED",
                    "NO_ORDER_CREATED",
                    *decision.reason_codes,
                }
            )
        )
        if decision.state is not RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION:
            return _waiting(
                inputs=references.all,
                reasons=tuple(
                    sorted({*reasons, f"H4_STATE_{decision.state.value}"})
                ),
                blocker="H4 did not permit this decision for manual confirmation",
            )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
            input_references=references.all,
            output_references=(references.risk_decision,),
            model_versions=(),
            configuration_hashes=tuple(
                sorted(
                    {
                        risk_bundle.configuration.configuration_hash,
                        policy.policy_hash,
                    }
                )
            ),
            reason_codes=reasons,
            blocker_reason=_MANUAL_CONFIRMATION_BLOCKER,
        )

    def _load_risk_bundle(
        self, references: _RiskContinuationReferences
    ) -> VerifiedRiskReducingDecisionBundle:
        bundle = self._risk_repository.get_verified_reducing_decision_bundle(
            ArtifactId(str(references.risk_decision.object_id))
        )
        _verify_reference(
            references.risk_decision,
            object_id=bundle.decision.decision_id,
            content_hash=bundle.decision.content_hash,
        )
        return bundle


@dataclass(frozen=True, slots=True)
class _RiskContinuationReferences:
    risk_decision: LifecycleObjectReference
    position_book: LifecycleObjectReference
    exit_directive: LifecycleObjectReference
    trading_calendar: LifecycleObjectReference
    thesis_health: LifecycleObjectReference
    composite: LifecycleObjectReference
    execution_observation: LifecycleObjectReference
    session_statuses: LifecycleObjectReference
    confirmation_policy: LifecycleObjectReference

    @classmethod
    def from_context(
        cls, context: LifecycleStageContext
    ) -> _RiskContinuationReferences:
        return cls(
            risk_decision=require_single_reference(
                context, LifecycleObjectType.RISK_REDUCING_DECISION
            ),
            position_book=require_single_reference(
                context, LifecycleObjectType.POSITION_BOOK
            ),
            exit_directive=require_single_reference(
                context, LifecycleObjectType.OPERATIONAL_EXIT_DIRECTIVE
            ),
            trading_calendar=require_single_reference(
                context, LifecycleObjectType.TRADING_CALENDAR_ARTIFACT
            ),
            thesis_health=require_single_reference(
                context, LifecycleObjectType.THESIS_HEALTH_OBSERVATION
            ),
            composite=require_single_reference(
                context, LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST
            ),
            execution_observation=require_single_reference(
                context, LifecycleObjectType.REDUCING_EXECUTION_OBSERVATION
            ),
            session_statuses=require_single_reference(
                context, LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET
            ),
            confirmation_policy=require_single_reference(
                context, LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY
            ),
        )

    @property
    def all(self) -> tuple[LifecycleObjectReference, ...]:
        return ordered_references(
            (
                self.risk_decision,
                self.position_book,
                self.exit_directive,
                self.trading_calendar,
                self.thesis_health,
                self.composite,
                self.execution_observation,
                self.session_statuses,
                self.confirmation_policy,
            )
        )


def _verify_scope(
    *,
    context: LifecycleStageContext,
    risk_bundle: VerifiedRiskReducingDecisionBundle,
    directive: OperationalExitDirectiveV2,
    book: PositionBook,
    thesis: TradingThesis,
    opportunity: TradingOpportunity,
    health: VerifiedThesisHealthBundle,
    composite: VerifiedCompositeOperationalManifest,
    calendar: TradingCalendarArtifact,
    observation: ReducingExecutionObservation,
    statuses: tuple[SymbolTradingSessionStatus, ...],
    policy: RiskReductionConfirmationPolicy,
) -> None:
    decision = risk_bundle.decision
    position = risk_bundle.position
    health_observation = health.observation
    manifest = composite.manifest
    position_hash = canonical_hash(position.to_canonical_dict())
    status_ids = tuple(sorted((item.status_id for item in statuses), key=str))
    if (
        decision.position_snapshot_id != position.snapshot_id
        or decision.position_snapshot_hash != position_hash
        or decision.position_snapshot_version != position.version
        or decision.position_book_id != book.position_book_id
        or decision.position_book_id != position.position_book_id
        or decision.thesis_id != thesis.thesis_id
        or decision.thesis_id != book.thesis_id
        or decision.thesis_id != position.thesis_id
        or decision.symbol != thesis.symbol
        or decision.symbol != book.symbol
        or decision.symbol != position.symbol
        or opportunity.opportunity_id != thesis.opportunity_id
        or opportunity.opportunity_id != book.opportunity_id
        or opportunity.opportunity_id != position.opportunity_id
        or directive.action.value != decision.action.value
        or directive.position_book_id != decision.position_book_id
        or directive.thesis_id != decision.thesis_id
        or directive.opportunity_id != opportunity.opportunity_id
        or directive.symbol != decision.symbol
        or directive.position_snapshot_id != position.snapshot_id
        or directive.position_snapshot_hash != position_hash
        or directive.thesis_health_observation_id
        != health_observation.observation_id
        or directive.thesis_health_observation_hash
        != health_observation.content_hash
        or directive.composite_manifest_id != manifest.manifest_id
        or directive.composite_manifest_hash != manifest.content_hash
        or health_observation.thesis_id != thesis.thesis_id
        or health_observation.opportunity_id != opportunity.opportunity_id
        or health_observation.symbol != decision.symbol
        or observation.symbol != decision.symbol
    ):
        raise ValueError("H4 continuation scope or lineage mismatch")
    if (
        book.state is not PositionBookState.OPEN
        or opportunity.state is not OpportunityState.CONFIRMED_TO_THESIS
        or thesis.state not in {ThesisState.APPROVED, ThesisState.INVALIDATED}
        or not health.is_latest
        or manifest.status is not CompositeOperationalCompositionStatus.VERIFIED
    ):
        raise ValueError("H4 continuation authority is no longer current")
    if (
        position.calendar_artifact_id != calendar.artifact_id
        or position.calendar_content_hash != calendar.content_hash
        or position.source_trading_status_ids != status_ids
        or any(item.symbol != decision.symbol for item in statuses)
    ):
        raise ValueError("H4 continuation position/calendar authority mismatch")
    as_of = context.run.as_of_time
    timestamps = (
        decision.assessed_at,
        directive.created_at,
        position.as_of,
        health_observation.assessed_at,
        manifest.created_at,
        observation.availability_time,
        *(item.availability_time for item in statuses),
    )
    if any(item > as_of for item in timestamps):
        raise ValueError("H4 continuation input was unavailable at lifecycle as-of")
    decision_age = (as_of - decision.assessed_at).total_seconds()
    position_age = (as_of - position.as_of).total_seconds()
    observation_age = (as_of - observation.availability_time).total_seconds()
    if (
        decision_age < 0
        or decision_age > policy.maximum_decision_age_seconds
        or position_age < 0
        or position_age > policy.maximum_position_age_seconds
        or observation_age < 0
        or observation_age > policy.maximum_execution_observation_age_seconds
    ):
        raise ValueError("H4 continuation input expired before lifecycle as-of")


def build_symbol_trading_session_status_set(
    statuses: tuple[SymbolTradingSessionStatus, ...],
) -> dict[str, Any]:
    """Build the strict content-addressed wrapper used by the controlled Reader."""

    ordered = tuple(sorted(statuses, key=lambda item: str(item.status_id)))
    if not ordered or len({item.status_id for item in ordered}) != len(ordered):
        raise ValueError("symbol status set must be non-empty and unique")
    semantic = {
        "schema_version": _STATUS_SET_SCHEMA,
        "statuses": [item.to_canonical_dict() for item in ordered],
    }
    content_hash = canonical_hash(semantic)
    return {
        "status_set_id": (
            f"symbol-trading-session-status-set-"
            f"{content_hash.split(':', 1)[1][:24]}"
        ),
        **semantic,
        "content_hash": content_hash,
    }


def load_symbol_trading_session_status_set(
    reference: LifecycleObjectReference,
) -> tuple[SymbolTradingSessionStatus, ...]:
    payload = _read_json_object(reference_path(reference))
    expected = {"status_set_id", "schema_version", "statuses", "content_hash"}
    if set(payload) != expected or payload["schema_version"] != _STATUS_SET_SCHEMA:
        raise ValueError("symbol trading status set fields mismatch")
    values = payload["statuses"]
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError("symbol trading status set statuses must be objects")
    statuses = tuple(
        SymbolTradingSessionStatus.from_canonical_dict(item) for item in values
    )
    expected_payload = build_symbol_trading_session_status_set(statuses)
    if payload != expected_payload:
        raise ValueError("symbol trading status set is not reconstructible")
    _verify_reference(
        reference,
        object_id=ArtifactId(str(payload["status_set_id"])),
        content_hash=str(payload["content_hash"]),
    )
    return statuses


def _waiting(
    *,
    inputs: tuple[LifecycleObjectReference, ...],
    reasons: tuple[str, ...],
    blocker: str,
) -> StageExecutionResult:
    return StageExecutionResult(
        stage_status=LifecycleStageStatus.WAITING,
        run_status=LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
        input_references=ordered_references(inputs),
        output_references=(),
        model_versions=(),
        configuration_hashes=(),
        reason_codes=tuple(sorted(set(reasons))),
        blocker_reason=blocker,
    )


def _verify_reference(
    reference: LifecycleObjectReference,
    *,
    object_id: StableId,
    content_hash: str,
) -> None:
    if (
        str(reference.object_id) != str(object_id)
        or reference.content_hash != content_hash
    ):
        raise ValueError(f"{reference.object_type.value} reference mismatch")


def _load_calendar(reference: LifecycleObjectReference) -> TradingCalendarArtifact:
    calendar = TradingCalendarArtifact.from_canonical_dict(
        _read_json_object(reference_path(reference))
    )
    _verify_reference(
        reference,
        object_id=calendar.artifact_id,
        content_hash=calendar.content_hash,
    )
    return calendar


def _load_execution_observation(
    reference: LifecycleObjectReference,
) -> ReducingExecutionObservation:
    observation = ReducingExecutionObservation.from_canonical_dict(
        _read_json_object(reference_path(reference))
    )
    _verify_reference(
        reference,
        object_id=observation.observation_id,
        content_hash=observation.content_hash,
    )
    return observation


def _load_confirmation_policy(
    reference: LifecycleObjectReference,
) -> RiskReductionConfirmationPolicy:
    policy = RiskReductionConfirmationPolicy.from_canonical_dict(
        _read_json_object(reference_path(reference))
    )
    _verify_reference(
        reference,
        object_id=policy.policy_id,
        content_hash=policy.policy_hash,
    )
    return policy


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid lifecycle Reader JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value
