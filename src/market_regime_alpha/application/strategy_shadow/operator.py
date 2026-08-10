"""Thin PostgreSQL operator flow for one complete Strategy Shadow day.

Only factual operator observations are accepted as inputs.  Runtime, Research
Shadow, Panel, Candidate, Entry Research and Strategy Shadow identities are
resolved from their existing PostgreSQL owners.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
)
from market_regime_alpha.application.research_validation.entry_qualification import (
    EntryResearchDecision,
    EntryResearchModel,
    EntryResearchVariant,
    assess_entry,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    HoldingAssessment,
    HoldingRuleKind,
    ShadowEntry,
    ShadowFill,
    ShadowExitDecision,
    ShadowFillStatus,
    ShadowPosition,
    StrategyOutcome,
    StrategyShadowPolicy,
    assess_exit,
    assess_holding,
    make_shadow_entry,
    make_shadow_fill,
    make_shadow_position,
    reference,
    restore_strategy_shadow_artifact,
    settle_strategy_outcome,
    strategy_shadow_artifact_payload,
)
from market_regime_alpha.application.strategy_shadow.operations import (
    StrategyShadowArtifactKind,
    StrategyShadowArtifactRecord,
    StrategyShadowEventKind,
    StrategyShadowOperations,
    StrategyShadowSession,
    StrategyShadowSessionStatus,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


_RESULT_VALUE_FIELDS = frozenset(
    {
        "intended_quantity",
        "decision_reference_price",
        "observed_fill_price",
        "fillability",
        "slippage_bps",
        "impact_bps",
        "commission_bps",
        "sessions_held",
        "current_price",
        "signal_reversed",
        "market_deteriorated",
        "theme_deteriorated",
        "capital_deteriorated",
        "exit_cost",
        "mfe",
        "mae",
    }
)


@dataclass(frozen=True, slots=True)
class StrategyDayObservation:
    trading_date: date
    observed_at: datetime
    symbol: str | None
    intended_quantity: Decimal
    decision_reference_price: Decimal
    observed_fill_price: Decimal | None
    fillability: Decimal
    slippage_bps: Decimal
    impact_bps: Decimal
    commission_bps: Decimal
    sessions_held: int
    current_price: Decimal | None
    signal_reversed: bool
    market_deteriorated: bool
    theme_deteriorated: bool
    capital_deteriorated: bool
    exit_cost: Decimal
    mfe: Decimal | None
    mae: Decimal | None
    value_provenance: tuple[tuple[str, ShadowParameterProvenance], ...]

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Strategy day observation time must be timezone-aware")
        if self.intended_quantity <= 0 or self.decision_reference_price <= 0:
            raise ValueError("Strategy day quantity/reference price must be positive")
        if not Decimal("0") <= self.fillability <= Decimal("1"):
            raise ValueError("Strategy day fillability must be between zero and one")
        if self.sessions_held < 0 or self.exit_cost < 0:
            raise ValueError("Strategy day sessions/cost cannot be negative")
        if self.current_price is not None and self.current_price <= 0:
            raise ValueError("Strategy day current price must be positive")
        if self.value_provenance != tuple(sorted(set(self.value_provenance))):
            raise ValueError("Strategy day value provenance must be sorted and unique")
        if {name for name, _provenance in self.value_provenance} != _RESULT_VALUE_FIELDS:
            raise ValueError("Strategy day requires exact result-value provenance")

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> StrategyDayObservation:
        return cls(
            trading_date=date.fromisoformat(str(value["trading_date"])),
            observed_at=datetime.fromisoformat(str(value["observed_at"])),
            symbol=None if value["symbol"] is None else str(value["symbol"]),
            intended_quantity=Decimal(str(value["intended_quantity"])),
            decision_reference_price=Decimal(str(value["decision_reference_price"])),
            observed_fill_price=_optional_decimal(value["observed_fill_price"]),
            fillability=Decimal(str(value["fillability"])),
            slippage_bps=Decimal(str(value["slippage_bps"])),
            impact_bps=Decimal(str(value["impact_bps"])),
            commission_bps=Decimal(str(value["commission_bps"])),
            sessions_held=int(value["sessions_held"]),
            current_price=_optional_decimal(value["current_price"]),
            signal_reversed=_boolean(value["signal_reversed"]),
            market_deteriorated=_boolean(value["market_deteriorated"]),
            theme_deteriorated=_boolean(value["theme_deteriorated"]),
            capital_deteriorated=_boolean(value["capital_deteriorated"]),
            exit_cost=Decimal(str(value["exit_cost"])),
            mfe=_optional_decimal(value["mfe"]),
            mae=_optional_decimal(value["mae"]),
            value_provenance=tuple(
                sorted(
                    (
                        str(name),
                        ShadowParameterProvenance(str(provenance)),
                    )
                    for name, provenance in _mapping(
                        value["value_provenance"]
                    ).items()
                )
            ),
        )


class StrategyShadowDayOperator:
    """Resume-safe application facade over existing owner repositories."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._research_shadow = PostgresShadowResearchRepository(factory)
        self._continuous = PostgresContinuousResearchJournal(
            factory,
            apply_migrations=False,
        )
        self._state = PostgresStateSystemRepository(factory, apply_migrations=False)
        self._validation = PostgresResearchValidationRepository(
            factory,
            apply_migrations=False,
        )
        self._strategy_repository = PostgresStrategyShadowRepository(
            factory,
            apply_migrations=False,
        )
        self._strategy = StrategyShadowOperations(self._strategy_repository)

    def run(self, observation: StrategyDayObservation) -> dict[str, Any]:
        decision, panel_reference = self._resolve_research_lineage(
            observation.trading_date
        )
        candidate_set = self._state.get_runtime_candidate(
            run_id=decision.run_id,
            tick_id=decision.tick_id,
        )
        selected = candidate_set.selected
        if not selected:
            return _result(
                operation="STRATEGY_DAY",
                status="DATA_INSUFFICIENT",
                reason_codes=("NO_SELECTED_CANDIDATE",),
            )
        if observation.symbol is None:
            candidate = selected[0]
        else:
            matches = tuple(item for item in selected if item.symbol == observation.symbol)
            if len(matches) != 1:
                raise ValueError("Strategy day symbol is not one selected Candidate")
            candidate = matches[0]
        model = EntryResearchModel.create(
            model_version="free-data-selected-candidate-pass-through-v1",
            variant=EntryResearchVariant.SELECTED_CANDIDATE_PASS_THROUGH,
            score_threshold=None,
        )
        candidate_reference = ValidationArtifactReference(
            "CANDIDATE_SET",
            candidate_set.envelope.artifact_id,
            candidate_set.envelope.content_hash,
        )
        assessment = assess_entry(
            model=model,
            symbol=candidate.symbol,
            decision_time=decision.decision_time,
            inputs=((
                "candidate_score",
                None
                if candidate.candidate_discovery_score is None
                else Decimal(str(candidate.candidate_discovery_score)),
            ),),
            source_references=(candidate_reference, panel_reference),
        )
        self._validation.record(
            artifact_id=ArtifactId(str(model.model_id)),
            artifact_hash=model.model_hash,
            artifact_kind="ENTRY_RESEARCH_MODEL",
            evidence_authority="EXPLORATORY",
            payload=model.identity_payload(),
            created_at=observation.observed_at,
        )
        self._validation.record(
            artifact_id=assessment.assessment_id,
            artifact_hash=assessment.assessment_hash,
            artifact_kind="ENTRY_RESEARCH_ASSESSMENT",
            evidence_authority="EXPLORATORY",
            payload=assessment.identity_payload(),
            created_at=observation.observed_at,
        )
        if assessment.decision is not EntryResearchDecision.SHADOW_ENTER:
            return _result(
                operation="STRATEGY_DAY",
                status=assessment.decision.value,
                reason_codes=assessment.reason_codes,
                assessment_id=str(assessment.assessment_id),
            )

        policy = StrategyShadowPolicy.create(
            # The Strategy Shadow schema binds a Policy Artifact to one session.
            # Include the frozen decision identity so identical rules on another
            # day cannot collide with that session-local immutable Artifact.
            policy_version=f"free-data-t-plus-one-shadow-v1:{decision.decision_id}",
            rule_kinds=(HoldingRuleKind.FIXED_TIME,),
            fixed_horizon_sessions=1,
            trailing_drawdown=None,
            protection_return=None,
            participation_rate=None,
        )
        run = self._continuous.get_run(decision.run_id)
        tick = next(
            item
            for item in run.ticks
            if item.command.tick_id == decision.tick_id
        )
        session = self._strategy.schedule(
            trading_date=observation.trading_date,
            scheduled_for=decision.decision_frozen_at,
            research_shadow_reference=ValidationArtifactReference(
                "SHADOW_DECISION",
                decision.decision_id,
                decision.decision_hash,
            ),
            runtime_run_reference=ValidationArtifactReference(
                "RUNTIME_RUN",
                decision.run_id,
                run.command.command_hash,
            ),
            runtime_tick_reference=ValidationArtifactReference(
                "RUNTIME_TICK",
                decision.tick_id,
                tick.command.tick_hash,
            ),
            policy_reference=reference(
                "STRATEGY_SHADOW_POLICY",
                policy.policy_id,
                policy.policy_hash,
            ),
            created_at=decision.decision_frozen_at,
        )
        self._strategy_repository.save_artifact(
            _artifact_record(
                session=session,
                kind=StrategyShadowArtifactKind.POLICY,
                value=policy,
                artifact_id=policy.policy_id,
                artifact_hash=policy.policy_hash,
                created_at=decision.decision_frozen_at,
            )
        )
        if session.status is StrategyShadowSessionStatus.SETTLED:
            outcome = self._require_restored_artifact(
                session.session_id,
                StrategyShadowArtifactKind.STRATEGY_OUTCOME,
                StrategyOutcome,
            )
            return self._settled_result(
                session=session,
                assessment_id=assessment.assessment_id,
                outcome=outcome,
            )
        session = self._ensure_started(session, observation.observed_at)
        entry = self._optional_restored_artifact(
            session.session_id,
            StrategyShadowArtifactKind.ENTRY,
            ShadowEntry,
        )
        if entry is None:
            entry = make_shadow_entry(
                assessment_reference=ValidationArtifactReference(
                    "ENTRY_RESEARCH_ASSESSMENT",
                    assessment.assessment_id,
                    assessment.assessment_hash,
                ),
                policy=policy,
                symbol=candidate.symbol,
                decision_time=decision.decision_time,
                intended_quantity=observation.intended_quantity,
                intended_reference_price=observation.decision_reference_price,
                source_references=(candidate_reference, panel_reference),
            )
            session = self._ensure_artifact(
                session=session,
                event_kind=StrategyShadowEventKind.ENTRY_CREATED,
                artifact=_artifact_record(
                    session=session,
                    kind=StrategyShadowArtifactKind.ENTRY,
                    value=entry,
                    artifact_id=entry.entry_id,
                    artifact_hash=entry.entry_hash,
                    created_at=observation.observed_at,
                ),
                occurred_at=observation.observed_at,
            )
        fill = self._optional_restored_artifact(
            session.session_id,
            StrategyShadowArtifactKind.FILL,
            ShadowFill,
        )
        if fill is None:
            liquidity_payload = {
                "schema": "free-data-shadow-liquidity-observation/v1",
                "symbol": candidate.symbol,
                "observed_at": observation.observed_at.isoformat(),
                "fillability": str(observation.fillability),
                "observed_fill_price": (
                    None
                    if observation.observed_fill_price is None
                    else str(observation.observed_fill_price)
                ),
                "slippage_bps": str(observation.slippage_bps),
                "impact_bps": str(observation.impact_bps),
                "commission_bps": str(observation.commission_bps),
                "value_provenance": [
                    [name, provenance.value]
                    for name, provenance in observation.value_provenance
                ],
                "limitations": [
                    "FREE_DATA_EXPLORATORY",
                    "NOT_ORDER_BOOK_EVIDENCE",
                    "NOT_REAL_FILL",
                ],
            }
            liquidity_id, liquidity_hash = content_identity(
                "free-data-shadow-liquidity-observation",
                liquidity_payload,
            )
            liquidity_reference = ValidationArtifactReference(
                "FREE_DATA_SHADOW_LIQUIDITY_OBSERVATION",
                liquidity_id,
                liquidity_hash,
            )
            self._strategy_repository.save_artifact(
                StrategyShadowArtifactRecord(
                    artifact_reference=liquidity_reference,
                    artifact_kind=StrategyShadowArtifactKind.LIQUIDITY_OBSERVATION,
                    session_id=session.session_id,
                    payload=liquidity_payload,
                    created_at=observation.observed_at,
                )
            )
            fill = make_shadow_fill(
                entry=entry,
                observed_price=observation.observed_fill_price,
                fillability=observation.fillability,
                slippage_bps=observation.slippage_bps,
                impact_bps=observation.impact_bps,
                commission_bps=observation.commission_bps,
                observed_at=observation.observed_at,
                liquidity_reference=liquidity_reference,
            )
            session = self._ensure_artifact(
                session=session,
                event_kind=StrategyShadowEventKind.FILL_OBSERVED,
                artifact=_artifact_record(
                    session=session,
                    kind=StrategyShadowArtifactKind.FILL,
                    value=fill,
                    artifact_id=fill.fill_id,
                    artifact_hash=fill.fill_hash,
                    created_at=observation.observed_at,
                ),
                occurred_at=observation.observed_at,
            )
        if fill.status is ShadowFillStatus.UNFILLED:
            return _result(
                operation="STRATEGY_DAY",
                status="SHADOW_UNFILLED",
                reason_codes=("NO_SHADOW_POSITION_CREATED",),
                session_id=str(session.session_id),
                fill_id=str(fill.fill_id),
            )
        position = self._optional_restored_artifact(
            session.session_id,
            StrategyShadowArtifactKind.POSITION,
            ShadowPosition,
        )
        if position is None:
            position = make_shadow_position(entry=entry, fill=fill)
            session = self._ensure_artifact(
                session=session,
                event_kind=StrategyShadowEventKind.POSITION_OPENED,
                artifact=_artifact_record(
                    session=session,
                    kind=StrategyShadowArtifactKind.POSITION,
                    value=position,
                    artifact_id=position.position_id,
                    artifact_hash=position.position_hash,
                    created_at=observation.observed_at,
                ),
                occurred_at=observation.observed_at,
            )
        holding = assess_holding(
            position=position,
            policy=policy,
            assessed_at=observation.observed_at,
            sessions_held=observation.sessions_held,
            current_price=observation.current_price,
            signal_reversed=observation.signal_reversed,
            market_deteriorated=observation.market_deteriorated,
            theme_deteriorated=observation.theme_deteriorated,
            capital_deteriorated=observation.capital_deteriorated,
        )
        session = self._ensure_repeatable_artifact(
            session=session,
            event_kind=StrategyShadowEventKind.HOLDING_ASSESSED,
            artifact=_artifact_record(
                session=session,
                kind=StrategyShadowArtifactKind.HOLDING_ASSESSMENT,
                value=holding,
                artifact_id=holding.assessment_id,
                artifact_hash=holding.assessment_hash,
                created_at=observation.observed_at,
            ),
            occurred_at=observation.observed_at,
        )
        exit_assessment = assess_exit(
            holding=holding,
            position=position,
            assessed_at=observation.observed_at,
        )
        session = self._ensure_repeatable_artifact(
            session=session,
            event_kind=StrategyShadowEventKind.EXIT_ASSESSED,
            artifact=_artifact_record(
                session=session,
                kind=StrategyShadowArtifactKind.EXIT_ASSESSMENT,
                value=exit_assessment,
                artifact_id=exit_assessment.assessment_id,
                artifact_hash=exit_assessment.assessment_hash,
                created_at=observation.observed_at,
            ),
            occurred_at=observation.observed_at,
        )
        if exit_assessment.decision is not ShadowExitDecision.SHADOW_EXIT:
            return _result(
                operation="STRATEGY_DAY",
                status=exit_assessment.decision.value,
                reason_codes=exit_assessment.reason_codes,
                session_id=str(session.session_id),
                position_id=str(position.position_id),
            )
        outcome = settle_strategy_outcome(
            entry=entry,
            fill=fill,
            position=position,
            exit_assessment=exit_assessment,
            exit_cost=observation.exit_cost,
            mfe=observation.mfe,
            mae=observation.mae,
        )
        session = self._ensure_artifact(
            session=session,
            event_kind=StrategyShadowEventKind.OUTCOME_SETTLED,
            artifact=_artifact_record(
                session=session,
                kind=StrategyShadowArtifactKind.STRATEGY_OUTCOME,
                value=outcome,
                artifact_id=outcome.outcome_id,
                artifact_hash=outcome.outcome_hash,
                created_at=observation.observed_at,
            ),
            occurred_at=observation.observed_at,
        )
        return self._settled_result(
            session=session,
            assessment_id=assessment.assessment_id,
            outcome=outcome,
            holding=holding,
            exit_assessment=exit_assessment,
        )

    def replay(self, session_id: ArtifactId) -> dict[str, Any]:
        session = self._strategy.replay(session_id)
        artifacts = self._strategy_repository.list_artifacts(session_id=session_id)
        for artifact in artifacts:
            if artifact.artifact_kind is StrategyShadowArtifactKind.LIQUIDITY_OBSERVATION:
                continue
            restore_strategy_shadow_artifact(
                artifact_kind=artifact.artifact_kind.value,
                artifact_id=artifact.artifact_reference.artifact_id,
                artifact_hash=artifact.artifact_reference.content_hash,
                payload=artifact.payload,
            )
        by_reference = {
            (
                item.artifact_reference.artifact_kind,
                item.artifact_reference.artifact_id,
                item.artifact_reference.content_hash,
            )
            for item in artifacts
        }
        event_references = {
            (
                item.artifact_reference.artifact_kind,
                item.artifact_reference.artifact_id,
                item.artifact_reference.content_hash,
            )
            for item in session.events
            if item.artifact_reference is not None
        }
        if not event_references.issubset(by_reference):
            raise ValueError("Strategy Shadow replay cannot resolve an event Artifact owner row")
        fill = self._optional_restored_artifact(
            session_id,
            StrategyShadowArtifactKind.FILL,
            ShadowFill,
        )
        if fill is not None and (
            fill.liquidity_reference.artifact_kind,
            fill.liquidity_reference.artifact_id,
            fill.liquidity_reference.content_hash,
        ) not in by_reference:
            raise ValueError("Strategy Shadow replay cannot resolve liquidity evidence")
        return _result(
            operation="STRATEGY_REPLAY",
            status=session.status.value,
            reason_codes=("STRATEGY_SHADOW_REPLAY_VERIFIED",),
            session_id=str(session.session_id),
            revision=session.revision,
            event_count=len(session.events),
            artifact_count=len(artifacts),
        )

    def report_day(self, trading_date: date, *, generated_at: datetime) -> dict[str, Any]:
        sessions = self._strategy_repository.list_sessions(trading_date=trading_date)
        report = self._strategy.daily_report(
            trading_date=trading_date,
            sessions=sessions,
            generated_at=generated_at,
        )
        return _result(
            operation="STRATEGY_REPORT_DAY",
            status="REPORTED",
            reason_codes=("STRATEGY_SHADOW_REPORT_GENERATED",),
            report_id=str(report.report_id),
            scheduled_count=report.scheduled_count,
            settled_count=report.settled_count,
            failed_count=report.failed_count,
        )

    def list_sessions(self, trading_date: date) -> tuple[StrategyShadowSession, ...]:
        return self._strategy_repository.list_sessions(trading_date=trading_date)

    def _resolve_research_lineage(
        self,
        trading_date: date,
    ) -> tuple[Any, ValidationArtifactReference]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT decision.decision_id, panel.panel_id, panel.panel_hash
                FROM shadow_research_decision AS decision
                JOIN shadow_research_session AS shadow
                  ON shadow.session_id = decision.session_id
                JOIN research_evaluation_panel_slice_v2 AS slice
                  ON slice.shadow_decision_id = decision.decision_id
                JOIN research_evaluation_panel_v2 AS panel
                  ON panel.panel_id = slice.panel_id
                WHERE shadow.trading_date = %s
                  AND shadow.status = 'SETTLED'
                ORDER BY panel.created_at DESC, panel.panel_id DESC
                """,
                (trading_date,),
            ).fetchall()
        if len(rows) != 1:
            raise ValueError("Strategy day requires exactly one settled Research Shadow Panel")
        return (
            self._research_shadow.get_decision(ArtifactId(str(rows[0][0]))),
            ValidationArtifactReference(
                "RESEARCH_PANEL_V2",
                ArtifactId(str(rows[0][1])),
                str(rows[0][2]),
            ),
        )

    def _ensure_started(
        self,
        session: StrategyShadowSession,
        occurred_at: datetime,
    ) -> StrategyShadowSession:
        if any(item.event_kind is StrategyShadowEventKind.STARTED for item in session.events):
            return session
        return self._strategy.start(
            session.session_id,
            expected_revision=session.revision,
            occurred_at=occurred_at,
        )

    def _ensure_artifact(
        self,
        *,
        session: StrategyShadowSession,
        event_kind: StrategyShadowEventKind,
        artifact: StrategyShadowArtifactRecord,
        occurred_at: datetime,
    ) -> StrategyShadowSession:
        existing = next(
            (item for item in session.events if item.event_kind is event_kind),
            None,
        )
        if existing is not None:
            if existing.artifact_reference != artifact.artifact_reference:
                raise ValueError(f"Strategy Shadow recovered {event_kind.value} identity conflict")
            return session
        return self._strategy.record_artifact(
            session.session_id,
            expected_revision=session.revision,
            event_kind=event_kind,
            artifact=artifact,
            occurred_at=occurred_at,
        )

    def _ensure_repeatable_artifact(
        self,
        *,
        session: StrategyShadowSession,
        event_kind: StrategyShadowEventKind,
        artifact: StrategyShadowArtifactRecord,
        occurred_at: datetime,
    ) -> StrategyShadowSession:
        existing = next(
            (
                item
                for item in session.events
                if item.event_kind is event_kind
                and item.artifact_reference == artifact.artifact_reference
            ),
            None,
        )
        if existing is not None:
            return session
        return self._strategy.record_artifact(
            session.session_id,
            expected_revision=session.revision,
            event_kind=event_kind,
            artifact=artifact,
            occurred_at=occurred_at,
        )

    def _optional_restored_artifact(
        self,
        session_id: ArtifactId,
        artifact_kind: StrategyShadowArtifactKind,
        expected_type: type[Any],
    ) -> Any | None:
        record = self._strategy_repository.get_artifact(
            session_id=session_id,
            artifact_kind=artifact_kind,
        )
        if record is None:
            return None
        restored = restore_strategy_shadow_artifact(
            artifact_kind=record.artifact_kind.value,
            artifact_id=record.artifact_reference.artifact_id,
            artifact_hash=record.artifact_reference.content_hash,
            payload=record.payload,
        )
        if not isinstance(restored, expected_type):
            raise ValueError("Strategy Shadow owner restored an unexpected Artifact type")
        return restored

    def _require_restored_artifact(
        self,
        session_id: ArtifactId,
        artifact_kind: StrategyShadowArtifactKind,
        expected_type: type[Any],
    ) -> Any:
        restored = self._optional_restored_artifact(
            session_id,
            artifact_kind,
            expected_type,
        )
        if restored is None:
            raise ValueError(f"Strategy Shadow is missing {artifact_kind.value} owner row")
        return restored

    def _settled_result(
        self,
        *,
        session: StrategyShadowSession,
        assessment_id: ArtifactId,
        outcome: StrategyOutcome,
        holding: HoldingAssessment | None = None,
        exit_assessment: Any | None = None,
    ) -> dict[str, Any]:
        entry = self._require_restored_artifact(
            session.session_id,
            StrategyShadowArtifactKind.ENTRY,
            ShadowEntry,
        )
        fill = self._require_restored_artifact(
            session.session_id,
            StrategyShadowArtifactKind.FILL,
            ShadowFill,
        )
        position = self._require_restored_artifact(
            session.session_id,
            StrategyShadowArtifactKind.POSITION,
            ShadowPosition,
        )
        exit_assessment_id = (
            outcome.exit_reference.artifact_id
            if exit_assessment is None
            else exit_assessment.assessment_id
        )
        if holding is None:
            exit_record = next(
                (
                    item
                    for item in self._strategy_repository.list_artifacts(
                        session_id=session.session_id,
                        artifact_kind=StrategyShadowArtifactKind.EXIT_ASSESSMENT,
                    )
                    if item.artifact_reference.artifact_id == exit_assessment_id
                ),
                None,
            )
            if exit_record is None:
                raise ValueError("Strategy Shadow Outcome Exit owner row is missing")
            holding_assessment_id = ArtifactId(
                str(exit_record.payload["holding_reference"]["artifact_id"])
            )
        else:
            holding_assessment_id = holding.assessment_id
        return _result(
            operation="STRATEGY_DAY",
            status=session.status.value,
            reason_codes=("STRATEGY_SHADOW_OUTCOME_SETTLED",),
            session_id=str(session.session_id),
            assessment_id=str(assessment_id),
            entry_id=str(entry.entry_id),
            fill_id=str(fill.fill_id),
            position_id=str(position.position_id),
            holding_assessment_id=str(holding_assessment_id),
            exit_assessment_id=str(exit_assessment_id),
            strategy_outcome_id=str(outcome.outcome_id),
            revision=session.revision,
        )


def _artifact_record(
    *,
    session: StrategyShadowSession,
    kind: StrategyShadowArtifactKind,
    value: Any,
    artifact_id: ArtifactId,
    artifact_hash: str,
    created_at: datetime,
) -> StrategyShadowArtifactRecord:
    reference_kind = {
        StrategyShadowArtifactKind.POLICY: "STRATEGY_SHADOW_POLICY",
        StrategyShadowArtifactKind.LIQUIDITY_OBSERVATION: "FREE_DATA_SHADOW_LIQUIDITY_OBSERVATION",
        StrategyShadowArtifactKind.ENTRY: "SHADOW_ENTRY",
        StrategyShadowArtifactKind.FILL: "SHADOW_FILL",
        StrategyShadowArtifactKind.POSITION: "SHADOW_POSITION",
        StrategyShadowArtifactKind.HOLDING_ASSESSMENT: "HOLDING_ASSESSMENT",
        StrategyShadowArtifactKind.EXIT_ASSESSMENT: "EXIT_ASSESSMENT",
        StrategyShadowArtifactKind.STRATEGY_OUTCOME: "STRATEGY_OUTCOME",
        StrategyShadowArtifactKind.DAILY_REPORT: "STRATEGY_SHADOW_DAILY_REPORT",
    }[kind]
    return StrategyShadowArtifactRecord(
        artifact_reference=ValidationArtifactReference(
            reference_kind,
            artifact_id,
            artifact_hash,
        ),
        artifact_kind=kind,
        session_id=session.session_id,
        payload=strategy_shadow_artifact_payload(value),
        created_at=created_at,
    )


def _result(
    *,
    operation: str,
    status: str,
    reason_codes: tuple[str, ...],
    **details: Any,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "status": status,
        "reason_codes": list(reason_codes),
        **details,
        "shadow_fill_is_real_fill": False,
        "shadow_position_is_real_position": False,
        "broker_invoked": False,
        "order_authority_granted": False,
        "production_authorized": False,
        "entry_qualified": False,
        "alpha_validated": False,
    }


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Strategy day boolean field must be bool")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Strategy day value_provenance must be an object")
    return value


__all__ = [
    "StrategyDayObservation",
    "StrategyShadowDayOperator",
]
