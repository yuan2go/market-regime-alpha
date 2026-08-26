"""Owner-reloadable extraction of the frozen predecessor correctness failures."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time
from typing import Final
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.alpha_correctness import (
    AlphaCorrectnessStatus,
    HistoricalAlphaCorrectnessChecker,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalNormalizedBar,
)
from market_regime_alpha.application.historical_corpus.correctness_failures import (
    AlphaCorrectnessFailureDetail,
    AlphaCorrectnessFailureIndex,
    FailureSourceBinding,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
)
from market_regime_alpha.application.historical_corpus.historical_target_semantics import (
    apply_raw_corporate_action_conflict,
    evaluate_historical_target_semantics,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_correctness_failures import (
    PostgresAlphaCorrectnessFailureRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.selective_read import (
    HistoricalReadQuery,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunStatus,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
)
from market_regime_alpha.application.research_evaluation.target_semantics import (
    TargetSemanticResult,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.universe.postgres_historical_facts import (
    PostgresHistoricalSecurityFactsRepository,
)


_SHANGHAI: Final[ZoneInfo] = ZoneInfo("Asia/Shanghai")
_EXPECTED_FAILURE_CODE = "PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE"
_SEMANTIC_DISCREPANCY = (
    "PERSISTED_DECISION_REFERENCE_VIOLATES_EXACT_1455_PROTOCOL"
)
_MISSING_CLASSIFICATION = (
    "DECISION_EXACT_1455_BAR_MISSING_WITH_IGNORED_PREVIOUS_SUSPENDED_DAILY"
)
_PLACEHOLDER_CLASSIFICATION = (
    "DECISION_EXACT_1455_BAR_UNPRICED_PLACEHOLDER_WITH_IGNORED_PREVIOUS_"
    "SUSPENDED_DAILY"
)


class HistoricalCorrectnessFailureIndexer:
    """Extract and persist the exact eight immutable predecessor failures."""

    def __init__(
        self,
        *,
        journal: PostgresHistoricalResearchJournal,
        components: PostgresHistoricalMaterializationRepository,
        corpus: PostgresHistoricalCorpusRepository,
        evidence: PostgresHistoricalEvidenceRepository,
        historical_facts: PostgresHistoricalSecurityFactsRepository,
        failures: PostgresAlphaCorrectnessFailureRepository,
    ) -> None:
        self._journal = journal
        self._components = components
        self._corpus = corpus
        self._evidence = evidence
        self._historical_facts = historical_facts
        self._failures = failures

    def build_and_persist(
        self,
        *,
        predecessor_run_id: ArtifactId,
        predecessor_evidence_id: ArtifactId,
        corrected_target_protocol: OutcomeTargetProtocol,
        trading_calendar: TradingCalendarArtifact,
        analysis_code_sha: str,
        created_at: datetime,
    ) -> AlphaCorrectnessFailureIndex:
        return self._failures.put(
            self.build(
                predecessor_run_id=predecessor_run_id,
                predecessor_evidence_id=predecessor_evidence_id,
                corrected_target_protocol=corrected_target_protocol,
                trading_calendar=trading_calendar,
                analysis_code_sha=analysis_code_sha,
                created_at=created_at,
            )
        )

    def build(
        self,
        *,
        predecessor_run_id: ArtifactId,
        predecessor_evidence_id: ArtifactId,
        corrected_target_protocol: OutcomeTargetProtocol,
        trading_calendar: TradingCalendarArtifact,
        analysis_code_sha: str,
        created_at: datetime,
    ) -> AlphaCorrectnessFailureIndex:
        """Rebuild the frozen detail index without mutating PostgreSQL."""

        snapshot = self._journal.get_run(predecessor_run_id)
        if snapshot.status is not HistoricalRunStatus.COMPLETE:
            raise ValueError(
                "predecessor correctness failure extraction requires COMPLETE run"
            )
        command = snapshot.command
        source_evidence = self._evidence.get(predecessor_evidence_id)
        if (
            source_evidence.run_id != command.run_id
            or source_evidence.command_hash != command.command_hash
            or source_evidence.experiment_reference
            != command.experiment_definition_reference
            or source_evidence.evidence_kind
            is not HistoricalEvidenceKind.ALPHA_CORRECTNESS
        ):
            raise ValueError(
                "predecessor correctness Evidence does not bind the source run"
            )
        if (
            trading_calendar.artifact_id != command.trading_calendar_id
            or trading_calendar.content_hash != command.trading_calendar_hash
        ):
            raise ValueError("predecessor Calendar owner drifted")
        normalized_reference = _one_reference(
            command.configuration_references, "NORMALIZED_DATASET"
        )
        raw_reference = _one_reference(
            command.configuration_references, "RAW_PROVIDER_ARCHIVE"
        )
        facts_reference = _one_reference(
            command.configuration_references, "HISTORICAL_SECURITY_FACTS"
        )
        normalized_package = self._corpus.open_index(normalized_reference)
        if normalized_package.parent_reference != raw_reference:
            raise ValueError(
                "predecessor Normalized owner does not bind the Raw owner"
            )
        if normalized_package.normalization_version is None:
            raise ValueError("predecessor normalization revision is absent")
        target = next(
            item
            for item in corrected_target_protocol.targets
            if item.checkpoint is OutcomeCheckpoint.TIME_1030
        )
        specification = (
            corrected_target_protocol.target_semantic_specification
        )
        if specification is None:
            raise ValueError(
                "correctness failure extraction requires Target semantics"
            )
        reproduction = HistoricalAlphaCorrectnessChecker(
            components=self._components,
            corpus=self._corpus,
            historical_facts=self._historical_facts,
        ).reproduce_run(
            run_id=predecessor_run_id,
            trading_calendar=trading_calendar,
            physical_package_paths={
                normalized_reference: normalized_package.root
            },
        )
        failed = {
            (item.decision_time.astimezone(_SHANGHAI).date(), item.symbol): item
            for item in reproduction.target_results
            if item.status is AlphaCorrectnessStatus.CORRECTNESS_FAILED
        }
        if len(failed) != 8 or any(
            item.discrepancies != (_EXPECTED_FAILURE_CODE,)
            for item in failed.values()
        ):
            raise ValueError(
                "predecessor correctness failure population is not the frozen eight"
            )
        details: list[AlphaCorrectnessFailureDetail] = []
        for decision_session, symbol in sorted(failed):
            feature_component = _one_session_component(
                self._components,
                run_id=predecessor_run_id,
                trading_date=decision_session,
                component_kind=HistoricalComponentKind.FEATURE,
            )
            outcome_component = _one_outcome_component(
                self._components,
                run_id=predecessor_run_id,
                trading_date=decision_session,
            )
            label = _primary_label(outcome_component, symbol=symbol)
            decision_time = _decision_time(feature_component)
            target_session = date.fromisoformat(
                str(outcome_component.payload["next_session_date"])
            )
            previous_session = max(
                item
                for item in trading_calendar.trading_dates
                if item < decision_session
            )
            materializer_bars = self._read_source_bars(
                normalized_reference=normalized_reference,
                symbol=symbol,
                first_session=previous_session,
                target_session=target_session,
            )
            checker_bars = self._read_source_bars(
                normalized_reference=normalized_reference,
                symbol=symbol,
                first_session=previous_session,
                target_session=target_session,
            )
            corporate_action_reason = self._corporate_action_reason(
                facts_reference=facts_reference,
                symbol=symbol,
                decision_session=decision_session,
                target_session=target_session,
            )
            materializer_result = evaluate_historical_target_semantics(
                specification=specification,
                target=target,
                symbol=symbol,
                decision_time=decision_time,
                next_session_date=target_session,
                source_bars=materializer_bars,
            )
            checker_result = evaluate_historical_target_semantics(
                specification=specification,
                target=target,
                symbol=symbol,
                decision_time=decision_time,
                next_session_date=target_session,
                source_bars=checker_bars,
            )
            if corporate_action_reason is not None:
                materializer_result = apply_raw_corporate_action_conflict(
                    materializer_result,
                    target=target,
                    reason_code=corporate_action_reason,
                )
                checker_result = apply_raw_corporate_action_conflict(
                    checker_result,
                    target=target,
                    reason_code=corporate_action_reason,
                )
            if materializer_result != checker_result:
                raise ValueError(
                    "predecessor failure independent source reads disagree"
                )
            classification = _classification(materializer_result.reason_codes)
            details.append(
                AlphaCorrectnessFailureDetail.create(
                    decision_session=decision_session,
                    decision_time=decision_time,
                    target_session=target_session,
                    target_window_end=materializer_result.outcome_window_end,
                    symbol=symbol,
                    classification=classification,
                    discrepancy_code=_SEMANTIC_DISCREPANCY,
                    predecessor_label_reference=ValidationArtifactReference(
                        "TARGET_OUTCOME_LABEL",
                        label.label_id,
                        label.label_hash,
                    ),
                    predecessor_component_reference=(
                        outcome_component.reference
                    ),
                    predecessor_availability_status=(
                        label.availability_status.value
                    ),
                    predecessor_decision_reference_price=(
                        label.decision_reference_price
                    ),
                    predecessor_checkpoint_price=label.checkpoint_price,
                    predecessor_checkpoint_return=label.checkpoint_return,
                    predecessor_mfe=label.mfe,
                    predecessor_mae=label.mae,
                    materializer_result=materializer_result,
                    checker_result=checker_result,
                    source_bindings=_source_bindings(
                        raw_reference=raw_reference,
                        normalized_reference=normalized_reference,
                        feature_component=feature_component,
                        outcome_component=outcome_component,
                        label=label,
                        source_bars=checker_bars,
                        semantic_result=checker_result,
                    ),
                    normalization_revision=(
                        normalized_package.normalization_version
                    ),
                    semantic_revision=specification.semantic_revision,
                    analysis_code_sha=analysis_code_sha,
                )
            )
        classifications = Counter(item.classification for item in details)
        if classifications != Counter(
            {
                _MISSING_CLASSIFICATION: 3,
                _PLACEHOLDER_CLASSIFICATION: 5,
            }
        ):
            raise ValueError(
                "predecessor failure classifications diverged from the freeze"
            )
        index = AlphaCorrectnessFailureIndex.create(
            source_run_reference=ValidationArtifactReference(
                "HISTORICAL_RESEARCH_RUN",
                command.run_id,
                command.command_hash,
            ),
            source_evidence_reference=source_evidence.reference,
            experiment_reference=command.experiment_definition_reference,
            target_protocol_reference=command.target_protocol_reference,
            calendar_reference=ValidationArtifactReference(
                "TRADING_CALENDAR",
                trading_calendar.artifact_id,
                trading_calendar.content_hash,
            ),
            raw_owner_reference=raw_reference,
            normalized_owner_reference=normalized_reference,
            normalization_revision=normalized_package.normalization_version,
            analysis_code_sha=analysis_code_sha,
            semantic_revision=specification.semantic_revision,
            details=tuple(details),
            created_at=created_at,
        )
        return index

    def _read_source_bars(
        self,
        *,
        normalized_reference: ValidationArtifactReference,
        symbol: str,
        first_session: date,
        target_session: date,
    ) -> tuple[HistoricalNormalizedBar, ...]:
        source_slice = self._corpus.read(
            HistoricalReadQuery.create(
                reference=normalized_reference,
                timeframes=(Timeframe.DAILY, Timeframe.MINUTE_5),
                first_market_date=first_session,
                last_market_date=target_session,
                symbols=(symbol,),
                max_rows=2_000,
                batch_size=2_000,
            )
        )
        bars = tuple(
            item
            for item in source_slice.records
            if isinstance(item, HistoricalNormalizedBar)
        )
        if not bars:
            raise ValueError("predecessor failure source bars are absent")
        return bars

    def _corporate_action_reason(
        self,
        *,
        facts_reference: ValidationArtifactReference,
        symbol: str,
        decision_session: date,
        target_session: date,
    ) -> str | None:
        actions, gaps = (
            self._historical_facts.corporate_action_evidence_for_symbols(
                facts_reference,
                symbols=(symbol,),
                after=decision_session,
                through=target_session,
            )
        )
        if symbol in actions:
            return "RAW_UNADJUSTED_RETURN_CROSSES_CORPORATE_ACTION"
        if symbol in gaps:
            return "CORPORATE_ACTION_COVERAGE_GAP_RAW_RETURN_NOT_ESTIMABLE"
        return None


def _one_reference(
    references: tuple[ValidationArtifactReference, ...],
    kind: str,
) -> ValidationArtifactReference:
    matches = tuple(item for item in references if item.artifact_kind == kind)
    if len(matches) != 1:
        raise ValueError(f"predecessor command requires one {kind} owner")
    return matches[0]


def _one_outcome_component(
    components: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    trading_date: date,
) -> HistoricalSessionComponent:
    return _one_session_component(
        components,
        run_id=run_id,
        trading_date=trading_date,
        component_kind=HistoricalComponentKind.OUTCOME,
    )


def _one_session_component(
    components: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    trading_date: date,
    component_kind: HistoricalComponentKind,
) -> HistoricalSessionComponent:
    matches = components.get_for_run_date(
        run_id=run_id,
        trading_date=trading_date,
        component_kinds=(component_kind,),
    )
    if len(matches) != 1:
        raise ValueError(
            f"predecessor {component_kind.value} component is not unique"
        )
    return matches[0]


def _primary_label(
    component: HistoricalSessionComponent,
    *,
    symbol: str,
) -> TargetOutcomeLabel:
    raw_labels = component.payload.get("labels")
    if not isinstance(raw_labels, list):
        raise ValueError("predecessor Outcome labels are absent")
    matches = tuple(
        label
        for raw_label in raw_labels
        if isinstance(raw_label, dict)
        for label in (TargetOutcomeLabel.from_canonical_dict(raw_label),)
        if label.symbol == symbol
        and label.label_interval_end.astimezone(_SHANGHAI).time().replace(
            tzinfo=None
        )
        == time(10, 30)
    )
    if len(matches) != 1:
        raise ValueError("predecessor primary Target label is not unique")
    return matches[0]


def _decision_time(component: HistoricalSessionComponent) -> datetime:
    decision_time = component.source_max_event_time
    if decision_time.astimezone(_SHANGHAI).date() != component.trading_date:
        raise ValueError("predecessor Feature DecisionTime drifted")
    if decision_time.astimezone(_SHANGHAI).time().replace(tzinfo=None) != time(
        14, 55
    ):
        raise ValueError("predecessor Feature DecisionTime is not exact 14:55")
    return decision_time


def _classification(reason_codes: tuple[str, ...]) -> str:
    reasons = set(reason_codes)
    required = {
        "DIAGNOSTIC_PREVIOUS_SESSION_DAILY_CLOSE_IGNORED",
        "DERIVED_DECISION_REFERENCE_UNAVAILABLE",
    }
    if not required.issubset(reasons):
        raise ValueError("predecessor failure lacks ignored Daily diagnostics")
    if "DECISION_EXACT_1455_BAR_MISSING" in reasons:
        return _MISSING_CLASSIFICATION
    if "DECISION_EXACT_1455_BAR_UNPRICED_PLACEHOLDER" in reasons:
        return _PLACEHOLDER_CLASSIFICATION
    raise ValueError("predecessor failure has an unexpected Decision condition")


def _source_bindings(
    *,
    raw_reference: ValidationArtifactReference,
    normalized_reference: ValidationArtifactReference,
    feature_component: HistoricalSessionComponent,
    outcome_component: HistoricalSessionComponent,
    label: TargetOutcomeLabel,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    semantic_result: TargetSemanticResult,
) -> tuple[FailureSourceBinding, ...]:
    bindings: list[FailureSourceBinding] = [
        FailureSourceBinding("RAW_OWNER", raw_reference),
        FailureSourceBinding("NORMALIZED_OWNER", normalized_reference),
        FailureSourceBinding("PREDECESSOR_FEATURE", feature_component.reference),
        FailureSourceBinding("PREDECESSOR_OUTCOME", outcome_component.reference),
        FailureSourceBinding(
            "PREDECESSOR_LABEL",
            ValidationArtifactReference(
                "TARGET_OUTCOME_LABEL",
                label.label_id,
                label.label_hash,
            ),
        ),
    ]
    relevant_references = {
        *semantic_result.decision_source_references,
        *semantic_result.outcome_source_references,
        *semantic_result.diagnostic_source_references,
    }
    ordered_bars = tuple(
        sorted(
            (item for item in source_bars if item.reference in relevant_references),
            key=lambda item: (
                item.market_date,
                item.event_start,
                item.event_end,
                str(item.bar_id),
            ),
        )
    )
    if {item.reference for item in ordered_bars} != relevant_references:
        raise ValueError("semantic failure source binding cannot resolve every bar")
    for ordinal, bar in enumerate(ordered_bars, 1):
        bindings.append(
            FailureSourceBinding(f"NORMALIZED_BAR_{ordinal:03d}", bar.reference)
        )
    raw_requests = tuple(
        sorted(
            {item.raw_request_reference for item in ordered_bars},
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    for ordinal, reference in enumerate(raw_requests, 1):
        bindings.append(
            FailureSourceBinding(f"RAW_REQUEST_{ordinal:03d}", reference)
        )
    return tuple(bindings)


__all__ = ["HistoricalCorrectnessFailureIndexer"]
