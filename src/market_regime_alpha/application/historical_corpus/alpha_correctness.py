"""Independent correctness checks over Historical normalized source bars.

This module is a checker, not a Feature, Target, Runtime or Evidence authority.
It deliberately recomputes the three WP-ALPHA-RESEARCH-01 intraday values and
the T+1 10:30 target without reading their persisted numerical outputs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalNormalizedBar,
)
from market_regime_alpha.application.historical_corpus.historical_target_semantics import (
    apply_raw_corporate_action_conflict,
    evaluate_historical_target_semantics,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    HistoricalPackageIndex,
    VerifiedHistoricalPackage,
    load_historical_package_index,
    verify_historical_package_files,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.selective_read import (
    HistoricalReadQuery,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.raw_normalization_correctness import (
    IndependentNormalizationStatus,
    IndependentNormalizationVerification,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
)
from market_regime_alpha.application.research_evaluation.target_semantics import (
    TargetSemanticResult,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.historical_corpus.alpha_diagnostics import (
    ExecutionPriceInputs,
    ExecutionPriceProxy,
    ExecutionTimingDiagnostic,
    FactorRedundancyResult,
    PlaceboKind,
    PlaceboResult,
    RobustInferenceResult,
    TimedPriceObservation,
    diagnose_execution_price,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.universe.postgres_historical_facts import (
    PostgresHistoricalSecurityFactsRepository,
)


_SHANGHAI: Final[ZoneInfo] = ZoneInfo("Asia/Shanghai")
_SCALE: Final[Decimal] = Decimal("0.000000000001")
_SUPPORTED_FACTORS: Final[frozenset[str]] = frozenset(
    {
        "intraday_return_to_decision_time",
        "price_vs_vwap_return",
        "vwap_slope",
    }
)


class AlphaCorrectnessStatus(str, Enum):
    CORRECTNESS_SUPPORTED = "CORRECTNESS_SUPPORTED"
    CORRECTNESS_FAILED = "CORRECTNESS_FAILED"
    PARTIALLY_REPRODUCED = "PARTIALLY_REPRODUCED"
    PHYSICAL_REPRODUCTION_NOT_ESTABLISHED = (
        "PHYSICAL_REPRODUCTION_NOT_ESTABLISHED"
    )


class AlphaCorrectnessConclusion(str, Enum):
    CORRECTNESS_SUPPORTED = "CORRECTNESS_SUPPORTED"
    CORRECTNESS_FAILED = "CORRECTNESS_FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class PhysicalSourceVerification:
    """Proof that an independently opened physical package matches its PG owner."""

    normalized_owner_reference: ValidationArtifactReference
    physical_hash: str
    checksums: tuple[tuple[str, str], ...]
    checksums_hash: str
    normalized_bar_count: int
    normalized_bar_manifest_hash: str

    def __post_init__(self) -> None:
        if self.normalized_owner_reference.artifact_kind != "NORMALIZED_DATASET":
            raise ValueError("physical verification requires normalized-data owner")
        require_sha256("physical_hash", self.physical_hash)
        require_sha256("checksums_hash", self.checksums_hash)
        if (
            not self.checksums
            or self.checksums != tuple(sorted(set(self.checksums)))
            or canonical_hash({"checksums": [list(item) for item in self.checksums]})
            != self.checksums_hash
        ):
            raise ValueError("physical checksum manifest is invalid")
        if self.normalized_bar_count <= 0:
            raise ValueError("physical verification requires normalized bars")
        require_sha256(
            "normalized_bar_manifest_hash", self.normalized_bar_manifest_hash
        )
        expected_manifest_hash = canonical_hash(
            {
                "normalized_owner_reference": (
                    self.normalized_owner_reference.to_canonical_dict()
                ),
                "physical_hash": self.physical_hash,
                "normalized_bar_count": self.normalized_bar_count,
            }
        )
        if self.normalized_bar_manifest_hash != expected_manifest_hash:
            raise ValueError("physical normalized-bar manifest is invalid")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "normalized_owner_reference": self.normalized_owner_reference.to_canonical_dict(),
            "physical_hash": self.physical_hash,
            "checksums": [list(item) for item in self.checksums],
            "checksums_hash": self.checksums_hash,
            "normalized_bar_count": self.normalized_bar_count,
            "normalized_bar_manifest_hash": self.normalized_bar_manifest_hash,
        }

def establish_physical_reproduction(
    *,
    package_path: Path,
    corpus_repository: PostgresHistoricalCorpusRepository,
) -> PhysicalSourceVerification:
    """Open physical bytes independently, then compare with the PG owner reload."""

    _package, verification = _open_physical_reproduction(
        package_path=package_path,
        corpus_repository=corpus_repository,
    )
    return verification


def _open_physical_reproduction(
    *,
    package_path: Path,
    corpus_repository: PostgresHistoricalCorpusRepository,
) -> tuple[HistoricalPackageIndex, PhysicalSourceVerification]:
    """Verify PostgreSQL metadata and every physical byte without bulk decoding."""

    physical_index = load_historical_package_index(package_path)
    postgres_index = corpus_repository.open_index(physical_index.reference)
    if physical_index != postgres_index:
        raise ValueError("physical package index does not match PostgreSQL owner")
    verify_historical_package_files(physical_index)
    return physical_index, _physical_verification_from_index(physical_index)


def _physical_verification_from_index(
    package: HistoricalPackageIndex,
) -> PhysicalSourceVerification:
    normalized_bar_count = package.coverage.normalized_row_count
    normalized_bar_manifest_hash = canonical_hash(
        {
            "normalized_owner_reference": package.reference.to_canonical_dict(),
            "physical_hash": package.physical_hash,
            "normalized_bar_count": normalized_bar_count,
        }
    )
    return PhysicalSourceVerification(
        normalized_owner_reference=package.reference,
        physical_hash=package.physical_hash,
        checksums=package.checksums,
        checksums_hash=canonical_hash(
            {"checksums": [list(item) for item in package.checksums]}
        ),
        normalized_bar_count=normalized_bar_count,
        normalized_bar_manifest_hash=normalized_bar_manifest_hash,
    )


def _physical_verification_from_package(
    package: VerifiedHistoricalPackage,
) -> PhysicalSourceVerification:
    package.owner.verify_identity()
    normalized_bar_count = package.owner.coverage.normalized_row_count
    normalized_bar_manifest_hash = canonical_hash(
        {
            "normalized_owner_reference": package.owner.reference.to_canonical_dict(),
            "physical_hash": package.physical_hash,
            "normalized_bar_count": normalized_bar_count,
        }
    )
    return PhysicalSourceVerification(
        normalized_owner_reference=package.owner.reference,
        physical_hash=package.physical_hash,
        checksums=package.checksums,
        checksums_hash=canonical_hash(
            {"checksums": [list(item) for item in package.checksums]}
        ),
        normalized_bar_count=normalized_bar_count,
        normalized_bar_manifest_hash=normalized_bar_manifest_hash,
    )


def _physical_verification_from_reloaded_packages(
    *,
    physical_package: VerifiedHistoricalPackage,
    postgres_owner_package: VerifiedHistoricalPackage,
) -> PhysicalSourceVerification:
    physical_package.owner.verify_identity()
    postgres_owner_package.owner.verify_identity()
    if physical_package.owner != postgres_owner_package.owner:
        raise ValueError("physical package does not match PostgreSQL owner identity")
    if (
        physical_package.physical_hash != postgres_owner_package.physical_hash
        or physical_package.checksums != postgres_owner_package.checksums
    ):
        raise ValueError("physical package checksum projection disagrees with owner")
    return _physical_verification_from_package(physical_package)


@dataclass(frozen=True, slots=True)
class HistoricalCorrectnessReproduction:
    feature_results: tuple[FeatureReproductionResult, ...]
    target_results: tuple[TargetReproductionResult, ...]
    physical_verifications: tuple[PhysicalSourceVerification, ...]


class HistoricalAlphaCorrectnessChecker:
    """Reload canonical Historical owners and run the independent checker kernel."""

    def __init__(
        self,
        *,
        components: PostgresHistoricalMaterializationRepository,
        corpus: PostgresHistoricalCorpusRepository,
        historical_facts: PostgresHistoricalSecurityFactsRepository | None = None,
    ) -> None:
        self._components = components
        self._corpus = corpus
        self._historical_facts = historical_facts

    def reproduce_run(
        self,
        *,
        run_id: ArtifactId,
        trading_calendar: TradingCalendarArtifact,
        physical_package_paths: Mapping[ValidationArtifactReference, Path] | None = None,
    ) -> HistoricalCorrectnessReproduction:
        feature_sessions = tuple(
            item.trading_date
            for batch in self._components.iter_for_run(
                run_id=run_id,
                component_kind=HistoricalComponentKind.FEATURE,
                batch_size=1,
            )
            for item in batch
        )
        outcome_sessions = tuple(
            item.trading_date
            for batch in self._components.iter_for_run(
                run_id=run_id,
                component_kind=HistoricalComponentKind.OUTCOME,
                batch_size=1,
            )
            for item in batch
        )
        if (
            not feature_sessions
            or feature_sessions != tuple(sorted(set(feature_sessions)))
            or feature_sessions != outcome_sessions
        ):
            raise ValueError("Historical correctness requires aligned Feature/Outcome owners")
        feature_results: list[FeatureReproductionResult] = []
        target_results: list[TargetReproductionResult] = []
        monthly_sessions: defaultdict[tuple[int, int], list[date]] = defaultdict(
            list
        )
        for session in feature_sessions:
            monthly_sessions[(session.year, session.month)].append(session)
        monthly_query_ranges = {
            key: (
                max(
                    (
                        item
                        for item in trading_calendar.trading_dates
                        if item < values[0]
                    ),
                    default=values[0],
                ),
                trading_calendar.resolve_next_session_date(
                    DecisionTime(
                        datetime.combine(
                            values[-1], time(14, 55), _SHANGHAI
                        )
                    )
                ),
            )
            for key, values in monthly_sessions.items()
        }
        physical_by_owner: dict[
            ValidationArtifactReference, PhysicalSourceVerification
        ] = {}
        verified_owner_references: set[ValidationArtifactReference] = set()
        loaded_month_key: tuple[ValidationArtifactReference, int, int] | None = (
            None
        )
        minute_bars: dict[
            tuple[date, str], tuple[HistoricalNormalizedBar, ...]
        ] = {}
        monthly_bars_by_symbol: dict[
            str, tuple[HistoricalNormalizedBar, ...]
        ] = {}
        for batch in self._components.iter_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.FEATURE,
            batch_size=1,
        ):
            if len(batch) != 1:
                raise ValueError("Historical Feature stream is not session-bounded")
            feature_component = batch[0]
            session = feature_component.trading_date
            outcome_components = self._components.get_for_run_date(
                run_id=run_id,
                trading_date=session,
                component_kinds=(HistoricalComponentKind.OUTCOME,),
            )
            if len(outcome_components) != 1:
                raise ValueError("Historical Outcome owner is not unique")
            outcome_component = outcome_components[0]
            normalized_reference = _shared_normalized_owner(
                feature_component, outcome_component
            )
            if normalized_reference not in verified_owner_references:
                package_index: HistoricalPackageIndex
                path = (
                    None
                    if physical_package_paths is None
                    else physical_package_paths.get(normalized_reference)
                )
                if path is None:
                    package_index = self._corpus.open_index(normalized_reference)
                else:
                    package_index, physical_by_owner[normalized_reference] = (
                        _open_physical_reproduction(
                            package_path=path,
                            corpus_repository=self._corpus,
                        )
                    )
                if package_index.reference != normalized_reference:
                    raise ValueError("Historical normalized package identity drifted")
                verified_owner_references.add(normalized_reference)
            active_verification = physical_by_owner.get(normalized_reference)
            decision_time = _component_decision_time(feature_component)
            labels = _target_labels(outcome_component)
            target_protocol = OutcomeTargetProtocol.from_canonical_dict(
                _mapping(
                    outcome_component.payload.get("target_protocol"),
                    "Historical Outcome target protocol",
                )
            )
            declared_target_omissions = _declared_target_omissions(
                outcome_component
            )
            next_session = date.fromisoformat(
                str(outcome_component.payload["next_session_date"])
            )
            month_key = (normalized_reference, session.year, session.month)
            if month_key != loaded_month_key:
                first_read_date, last_read_date = monthly_query_ranges[
                    (session.year, session.month)
                ]
                source_slice = self._corpus.read(
                    HistoricalReadQuery.create(
                        reference=normalized_reference,
                        timeframes=(Timeframe.DAILY, Timeframe.MINUTE_5),
                        first_market_date=first_read_date,
                        last_market_date=last_read_date,
                        symbols=None,
                        max_rows=500_000,
                        batch_size=8_192,
                    )
                )
                grouped: defaultdict[
                    tuple[date, str], list[HistoricalNormalizedBar]
                ] = defaultdict(list)
                for item in source_slice.records:
                    if isinstance(item, HistoricalNormalizedBar):
                        grouped[(item.market_date, item.symbol)].append(item)
                minute_bars = {
                    key: _ordered_bars(tuple(values))
                    for key, values in grouped.items()
                }
                by_symbol: defaultdict[
                    str, list[HistoricalNormalizedBar]
                ] = defaultdict(list)
                for values in grouped.values():
                    for item in values:
                        by_symbol[item.symbol].append(item)
                monthly_bars_by_symbol = {
                    symbol: _ordered_bars(tuple(values))
                    for symbol, values in by_symbol.items()
                }
                loaded_month_key = month_key
            feature_symbols = _feature_symbols(feature_component)
            source_symbols = feature_symbols | set(labels)
            corporate_action_reasons: dict[str, str] = {}
            if target_protocol.target_semantic_specification is not None:
                fact_references = tuple(
                    item
                    for item in outcome_component.source_references
                    if item.artifact_kind == "HISTORICAL_SECURITY_FACTS"
                )
                if len(fact_references) > 1:
                    raise ValueError(
                        "Historical Outcome binds multiple Security Facts owners"
                    )
                if fact_references:
                    if self._historical_facts is None:
                        raise ValueError(
                            "v3 Target reproduction requires Security Facts owner reload"
                        )
                    actions, gaps = (
                        self._historical_facts.corporate_action_evidence_for_symbols(
                            fact_references[0],
                            symbols=tuple(sorted(source_symbols)),
                            after=session,
                            through=next_session,
                        )
                    )
                    corporate_action_reasons.update(
                        {
                            symbol: "RAW_UNADJUSTED_RETURN_CROSSES_CORPORATE_ACTION"
                            for symbol in actions
                        }
                    )
                    corporate_action_reasons.update(
                        {
                            symbol: (
                                "CORPORATE_ACTION_COVERAGE_GAP_RAW_RETURN_NOT_ESTIMABLE"
                            )
                            for symbol in gaps
                        }
                    )
            decision_bars = {
                symbol: minute_bars.get((session, symbol), ())
                for symbol in source_symbols
            }
            next_session_bars = {
                symbol: minute_bars.get((next_session, symbol), ())
                for symbol in source_symbols
            }
            bars_by_id = {
                str(item.bar_id): item
                for symbol in source_symbols
                for item in (*decision_bars[symbol], *next_session_bars[symbol])
            }
            persisted_by_symbol, feature_unavailable = _persisted_feature_projection(
                feature_component, bars_by_id
            )
            target_omissions = _resolve_target_symbol_omissions(
                feature_symbols=set(persisted_by_symbol),
                label_symbols=set(labels),
                declared_omissions=declared_target_omissions,
            )
            for symbol in sorted(persisted_by_symbol):
                symbol_decision_bars = decision_bars[symbol]
                symbol_next_session_bars = next_session_bars[symbol]
                decision_source_bars = tuple(
                    item
                    for item in symbol_decision_bars
                    if item.timeframe is Timeframe.MINUTE_5
                    and item.event_end <= decision_time
                )
                feature_results.append(
                    reproduce_intraday_features(
                        session=session,
                        symbol=symbol,
                        decision_time=decision_time,
                        source_bars=symbol_decision_bars,
                        persisted=persisted_by_symbol[symbol],
                        physical_verification=active_verification,
                        incomplete_reason_codes=feature_unavailable.get(symbol, ()),
                    )
                )
                label = labels.get(symbol)
                if label is None:
                    target_results.append(
                        reproduce_t_plus_one_1030_target(
                            symbol=symbol,
                            decision_time=decision_time,
                            next_session=next_session,
                            trading_calendar=trading_calendar,
                            source_bars=(
                                *symbol_decision_bars,
                                *symbol_next_session_bars,
                            ),
                            persisted=None,
                            physical_verification=active_verification,
                            unavailable_reason_codes=target_omissions[symbol],
                        )
                    )
                    continue
                if label.schema_version == "target-outcome-label/v3":
                    target_results.append(
                        reproduce_t_plus_one_1030_target_v2(
                            label=label,
                            protocol=target_protocol,
                            trading_calendar=trading_calendar,
                            source_bars=monthly_bars_by_symbol.get(symbol, ()),
                            physical_verification=active_verification,
                            corporate_action_reason_code=(
                                corporate_action_reasons.get(symbol)
                            ),
                        )
                    )
                    continue
                target_bars = _ordered_bars(
                    tuple(
                        item
                        for item in symbol_next_session_bars
                        if item.event_start >= label.label_interval_start
                        and item.event_end <= label.label_interval_end
                    )
                )
                if label.checkpoint_price is None or label.checkpoint_return is None:
                    target_results.append(
                        reproduce_t_plus_one_1030_target(
                            symbol=symbol,
                            decision_time=decision_time,
                            next_session=next_session,
                            trading_calendar=trading_calendar,
                            source_bars=(
                                *symbol_decision_bars,
                                *symbol_next_session_bars,
                            ),
                            persisted=None,
                            physical_verification=active_verification,
                            unavailable_reason_codes=(
                                label.reason_codes
                                or ("PERSISTED_TARGET_NOT_ESTIMABLE",)
                            ),
                        )
                    )
                    continue
                persisted_sources_complete = bool(
                    decision_source_bars
                    and decision_source_bars[-1].event_end == decision_time
                    and decision_source_bars[-1].close is not None
                    and decision_source_bars[-1].close > 0
                    and target_bars
                    and target_bars[0].event_start
                    == datetime.combine(
                        next_session, time(9, 30), _SHANGHAI
                    ).astimezone(decision_time.tzinfo)
                    and target_bars[-1].event_end == label.label_interval_end
                    and target_bars[-1].close is not None
                )
                if not persisted_sources_complete:
                    target_results.append(
                        reproduce_t_plus_one_1030_target(
                            symbol=symbol,
                            decision_time=decision_time,
                            next_session=next_session,
                            trading_calendar=trading_calendar,
                            source_bars=(
                                *symbol_decision_bars,
                                *symbol_next_session_bars,
                            ),
                            persisted=None,
                            physical_verification=active_verification,
                            unavailable_reason_codes=(
                                "PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE",
                            ),
                        )
                    )
                    continue
                if label.decision_reference_price is None:
                    raise ValueError(
                        "legacy Target label lost its required Decision reference"
                    )
                persisted_target = PersistedTargetObservation.create(
                    decision_reference_price=label.decision_reference_price,
                    target_price=label.checkpoint_price,
                    target_return=label.checkpoint_return,
                    decision_source_bars=(decision_source_bars[-1],),
                    target_source_bars=target_bars,
                    target_session=next_session,
                )
                target_results.append(
                    reproduce_t_plus_one_1030_target(
                        symbol=symbol,
                        decision_time=decision_time,
                        next_session=next_session,
                        trading_calendar=trading_calendar,
                        source_bars=(
                            *symbol_decision_bars,
                            *symbol_next_session_bars,
                        ),
                        persisted=persisted_target,
                        physical_verification=active_verification,
                    )
                )
        return HistoricalCorrectnessReproduction(
            tuple(feature_results),
            tuple(target_results),
            tuple(
                physical_by_owner[key]
                for key in sorted(
                    physical_by_owner,
                    key=lambda item: (item.artifact_kind, str(item.artifact_id)),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class PersistedFeatureObservation:
    factor_id: str
    value: Decimal
    source_bar_count: int
    source_lineage_hash: str
    event_start: datetime
    event_end: datetime

    @classmethod
    def create(
        cls,
        *,
        factor_id: str,
        value: Decimal,
        source_bars: tuple[HistoricalNormalizedBar, ...],
    ) -> PersistedFeatureObservation:
        ordered = _ordered_bars(source_bars)
        if factor_id not in _SUPPORTED_FACTORS:
            raise ValueError("unsupported independent intraday factor")
        if not ordered:
            raise ValueError("persisted Feature observation requires source bars")
        ids, hashes, lineage = _source_lineage(ordered)
        return cls(
            factor_id=factor_id,
            value=value,
            source_bar_count=len(ids),
            source_lineage_hash=lineage,
            event_start=ordered[0].event_start,
            event_end=ordered[-1].event_end,
        )


@dataclass(frozen=True, slots=True)
class FeatureCorrectnessComparison:
    factor_id: str
    persisted_value: Decimal
    recomputed_value: Decimal
    persisted_source_bar_count: int
    persisted_source_lineage_hash: str
    persisted_event_start: datetime
    persisted_event_end: datetime
    source_bar_count: int
    source_lineage_hash: str
    event_start: datetime
    event_end: datetime
    decision_time: datetime
    discrepancies: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.factor_id not in _SUPPORTED_FACTORS:
            raise ValueError("Feature comparison Factor is unsupported")
        for count, lineage in (
            (
                self.persisted_source_bar_count,
                self.persisted_source_lineage_hash,
            ),
            (self.source_bar_count, self.source_lineage_hash),
        ):
            if count <= 0:
                raise ValueError("Feature comparison lineage is incomplete")
            require_sha256("Feature comparison lineage hash", lineage)
        if self.event_end > self.decision_time or self.persisted_event_end > self.decision_time:
            raise ValueError("Feature comparison uses information after DecisionTime")
        expected: list[str] = []
        if self.persisted_value != self.recomputed_value:
            expected.append(f"VALUE_MISMATCH:{self.factor_id}")
        if (
            self.persisted_source_bar_count != self.source_bar_count
            or self.persisted_source_lineage_hash != self.source_lineage_hash
        ):
            expected.append(f"SOURCE_LINEAGE_MISMATCH:{self.factor_id}")
        if (
            self.persisted_event_start != self.event_start
            or self.persisted_event_end != self.event_end
        ):
            expected.append(f"EVENT_INTERVAL_MISMATCH:{self.factor_id}")
        if tuple(expected) != self.discrepancies:
            raise ValueError("Feature comparison discrepancies are not derived")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "factor_id": self.factor_id,
            "persisted_value": str(self.persisted_value),
            "recomputed_value": str(self.recomputed_value),
            "persisted_source_bar_count": self.persisted_source_bar_count,
            "persisted_source_lineage_hash": self.persisted_source_lineage_hash,
            "persisted_event_start": self.persisted_event_start.isoformat(),
            "persisted_event_end": self.persisted_event_end.isoformat(),
            "source_bar_count": self.source_bar_count,
            "source_lineage_hash": self.source_lineage_hash,
            "event_start": self.event_start.isoformat(),
            "event_end": self.event_end.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "discrepancies": list(self.discrepancies),
        }


@dataclass(frozen=True, slots=True)
class FeatureReproductionResult:
    session: date
    symbol: str
    decision_time: datetime
    status: AlphaCorrectnessStatus
    physical_source_reference: ValidationArtifactReference | None
    comparisons: tuple[FeatureCorrectnessComparison, ...]
    discrepancies: tuple[str, ...]
    incomplete_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware("Feature result DecisionTime", self.decision_time)
        if self.session != self.decision_time.astimezone(_SHANGHAI).date():
            raise ValueError("Feature result session/DecisionTime drifted")
        factor_ids = tuple(item.factor_id for item in self.comparisons)
        if factor_ids != tuple(sorted(set(factor_ids))):
            raise ValueError("Feature result comparisons must be unique and sorted")
        if any(item.decision_time != self.decision_time for item in self.comparisons):
            raise ValueError("Feature comparison DecisionTime drifted")
        if self.incomplete_reason_codes != tuple(
            sorted(set(self.incomplete_reason_codes))
        ):
            raise ValueError("Feature incomplete reasons must be unique and sorted")
        derived = _correctness_status(
            discrepancies=self.discrepancies,
            physical_source_available=self.physical_source_reference is not None,
            complete=(
                set(factor_ids) == _SUPPORTED_FACTORS
                and not self.incomplete_reason_codes
            ),
        )
        if self.status is not derived:
            raise ValueError("Feature result status is not derived")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "session": self.session.isoformat(),
            "symbol": self.symbol,
            "decision_time": self.decision_time.isoformat(),
            "status": self.status.value,
            "physical_source_reference": (
                None
                if self.physical_source_reference is None
                else self.physical_source_reference.to_canonical_dict()
            ),
            "comparisons": [item.to_canonical_dict() for item in self.comparisons],
            "discrepancies": list(self.discrepancies),
            "incomplete_reason_codes": list(self.incomplete_reason_codes),
        }


@dataclass(frozen=True, slots=True)
class PersistedTargetObservation:
    decision_reference_price: Decimal
    target_price: Decimal
    target_return: Decimal
    decision_source_ids: tuple[str, ...]
    decision_source_hashes: tuple[str, ...]
    target_source_ids: tuple[str, ...]
    target_source_hashes: tuple[str, ...]
    target_session: date
    target_event_end: datetime

    def __post_init__(self) -> None:
        if self.decision_reference_price <= 0 or self.target_price <= 0:
            raise ValueError("persisted Target prices must be positive")
        if (
            self.target_return
            != (self.target_price - self.decision_reference_price)
            / self.decision_reference_price
        ):
            raise ValueError("persisted Target return disagrees with its prices")
        if (
            not self.decision_source_ids
            or not self.target_source_ids
            or len(self.decision_source_ids) != len(self.decision_source_hashes)
            or len(self.target_source_ids) != len(self.target_source_hashes)
            or set(self.decision_source_ids).intersection(self.target_source_ids)
        ):
            raise ValueError("persisted Target source lineage is invalid")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "decision_reference_price": str(self.decision_reference_price),
            "target_price": str(self.target_price),
            "target_return": str(self.target_return),
            "decision_source_ids": list(self.decision_source_ids),
            "decision_source_hashes": list(self.decision_source_hashes),
            "target_source_ids": list(self.target_source_ids),
            "target_source_hashes": list(self.target_source_hashes),
            "target_session": self.target_session.isoformat(),
            "target_event_end": self.target_event_end.isoformat(),
        }

    @classmethod
    def create(
        cls,
        *,
        decision_reference_price: Decimal,
        target_price: Decimal,
        target_return: Decimal,
        decision_source_bars: tuple[HistoricalNormalizedBar, ...],
        target_source_bars: tuple[HistoricalNormalizedBar, ...],
        target_session: date,
    ) -> PersistedTargetObservation:
        decision = _ordered_bars(decision_source_bars)
        target = _ordered_bars(target_source_bars)
        if not decision or not target:
            raise ValueError("persisted Target observation requires source bars")
        expected = (target_price - decision_reference_price) / decision_reference_price
        if target_return != expected:
            raise ValueError("persisted Target return disagrees with its prices")
        decision_ids, decision_hashes, _ = _source_lineage(decision)
        target_ids, target_hashes, _ = _source_lineage(target)
        if set(decision_ids).intersection(target_ids):
            raise ValueError("Feature/Decision and Target lineage must be disjoint")
        return cls(
            decision_reference_price=decision_reference_price,
            target_price=target_price,
            target_return=target_return,
            decision_source_ids=decision_ids,
            decision_source_hashes=decision_hashes,
            target_source_ids=target_ids,
            target_source_hashes=target_hashes,
            target_session=target_session,
            target_event_end=target[-1].event_end,
        )


@dataclass(frozen=True, slots=True)
class TargetReproductionResult:
    symbol: str
    decision_time: datetime
    target_session: date
    target_event_end: datetime
    decision_reference_price: Decimal | None
    target_price: Decimal | None
    target_return: Decimal | None
    decision_source_ids: tuple[str, ...]
    decision_source_hashes: tuple[str, ...]
    target_source_ids: tuple[str, ...]
    target_source_hashes: tuple[str, ...]
    persisted_observation: PersistedTargetObservation | None
    status: AlphaCorrectnessStatus
    physical_source_reference: ValidationArtifactReference | None
    trading_calendar_reference: ValidationArtifactReference
    discrepancies: tuple[str, ...]
    unavailable_reason_codes: tuple[str, ...] = ()
    semantic_result: TargetSemanticResult | None = None
    persisted_semantic_result: TargetSemanticResult | None = None

    def __post_init__(self) -> None:
        _require_aware("Target result DecisionTime", self.decision_time)
        _require_aware("Target result event end", self.target_event_end)
        if (
            self.target_session <= self.decision_time.astimezone(_SHANGHAI).date()
            or self.target_event_end.astimezone(_SHANGHAI).date()
            != self.target_session
            or set(self.decision_source_ids).intersection(self.target_source_ids)
        ):
            raise ValueError("Target result temporal/source lineage is invalid")
        if self.unavailable_reason_codes != tuple(
            sorted(set(self.unavailable_reason_codes))
        ):
            raise ValueError("Target unavailable reasons must be unique and sorted")
        if (
            self.semantic_result is not None
            or self.persisted_semantic_result is not None
        ):
            self._verify_semantic_reproduction()
            return
        values = (
            self.decision_reference_price,
            self.target_price,
            self.target_return,
        )
        values_available = all(item is not None for item in values)
        expected_discrepancies: tuple[str, ...]
        if not values_available:
            if any(item is not None for item in values) or any(
                (
                    self.decision_source_ids,
                    self.decision_source_hashes,
                    self.target_source_ids,
                    self.target_source_hashes,
                )
            ):
                raise ValueError("unavailable Target result must not invent values")
            if not self.unavailable_reason_codes:
                raise ValueError("unavailable Target result requires reasons")
            expected_discrepancies = _unavailable_target_discrepancies(
                set(self.unavailable_reason_codes)
            )
        else:
            if (
                len(self.decision_source_ids) != len(self.decision_source_hashes)
                or len(self.target_source_ids) != len(self.target_source_hashes)
                or not self.decision_source_ids
                or not self.target_source_ids
            ):
                raise ValueError("Target result source bindings are incomplete")
            assert self.decision_reference_price is not None
            assert self.target_price is not None
            assert self.target_return is not None
            expected_discrepancies = _target_discrepancies(
                self.persisted_observation,
                decision_price=self.decision_reference_price,
                target_price=self.target_price,
                target_return=self.target_return,
                decision_ids=self.decision_source_ids,
                decision_hashes=self.decision_source_hashes,
                target_ids=self.target_source_ids,
                target_hashes=self.target_source_hashes,
                target_session=self.target_session,
                target_event_end=self.target_event_end,
            )
            if (
                "PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE"
                in self.unavailable_reason_codes
            ):
                expected_discrepancies = (
                    *expected_discrepancies,
                    "PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE",
                )
        if expected_discrepancies != self.discrepancies:
            raise ValueError("Target result discrepancies are not derived")
        derived = _correctness_status(
            discrepancies=expected_discrepancies,
            physical_source_available=self.physical_source_reference is not None,
            complete=(
                values_available
                and self.persisted_observation is not None
                and not self.unavailable_reason_codes
            ),
        )
        if self.status is not derived:
            raise ValueError("Target result status is not derived")

    def _verify_semantic_reproduction(self) -> None:
        result = self.semantic_result
        persisted = self.persisted_semantic_result
        if result is None or persisted is None:
            raise ValueError("v3 Target reproduction requires both semantic results")
        if self.persisted_observation is not None:
            raise ValueError("v3 Target reproduction cannot use a legacy observation")
        decision_ids = tuple(
            str(item.artifact_id) for item in result.decision_source_references
        )
        decision_hashes = tuple(
            item.content_hash for item in result.decision_source_references
        )
        target_ids = tuple(
            str(item.artifact_id) for item in result.outcome_source_references
        )
        target_hashes = tuple(
            item.content_hash for item in result.outcome_source_references
        )
        expected_projection = (
            result.symbol,
            result.decision_time,
            result.target_session,
            result.outcome_window_end,
            result.decision_reference_price,
            result.checkpoint_price,
            result.checkpoint_return,
            decision_ids,
            decision_hashes,
            target_ids,
            target_hashes,
            tuple(sorted(result.reason_codes)),
        )
        actual_projection = (
            self.symbol,
            self.decision_time,
            self.target_session,
            self.target_event_end,
            self.decision_reference_price,
            self.target_price,
            self.target_return,
            self.decision_source_ids,
            self.decision_source_hashes,
            self.target_source_ids,
            self.target_source_hashes,
            self.unavailable_reason_codes,
        )
        if actual_projection != expected_projection:
            raise ValueError("v3 Target reproduction projection drifted")
        expected_discrepancies = _semantic_target_discrepancies(
            persisted, result
        )
        if self.discrepancies != expected_discrepancies:
            raise ValueError("v3 Target discrepancies are not derived")
        derived = _correctness_status(
            discrepancies=expected_discrepancies,
            physical_source_available=self.physical_source_reference is not None,
            complete=True,
        )
        if self.status is not derived:
            raise ValueError("v3 Target correctness status is not derived")

    def to_canonical_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "symbol": self.symbol,
            "decision_time": self.decision_time.isoformat(),
            "target_session": self.target_session.isoformat(),
            "target_event_end": self.target_event_end.isoformat(),
            "decision_reference_price": _optional_decimal_text(
                self.decision_reference_price
            ),
            "target_price": _optional_decimal_text(self.target_price),
            "target_return": _optional_decimal_text(self.target_return),
            "decision_source_ids": list(self.decision_source_ids),
            "decision_source_hashes": list(self.decision_source_hashes),
            "target_source_ids": list(self.target_source_ids),
            "target_source_hashes": list(self.target_source_hashes),
            "persisted_observation": (
                None
                if self.persisted_observation is None
                else self.persisted_observation.to_canonical_dict()
            ),
            "status": self.status.value,
            "physical_source_reference": (
                None
                if self.physical_source_reference is None
                else self.physical_source_reference.to_canonical_dict()
            ),
            "trading_calendar_reference": self.trading_calendar_reference.to_canonical_dict(),
            "discrepancies": list(self.discrepancies),
            "unavailable_reason_codes": list(self.unavailable_reason_codes),
        }
        if self.semantic_result is not None:
            assert self.persisted_semantic_result is not None
            payload["schema_version"] = "target-reproduction-result/v2"
            payload["semantic_result"] = self.semantic_result.to_canonical_dict()
            payload["persisted_semantic_result"] = (
                self.persisted_semantic_result.to_canonical_dict()
            )
        return payload


@dataclass(frozen=True, slots=True)
class AlphaCorrectnessProof:
    proof_id: ArtifactId
    proof_hash: str
    status: AlphaCorrectnessStatus
    feature_results: tuple[FeatureReproductionResult, ...]
    target_results: tuple[TargetReproductionResult, ...]
    physical_verifications: tuple[PhysicalSourceVerification, ...]
    normalization_verifications: tuple[IndependentNormalizationVerification, ...]
    placebo_results: tuple[PlaceboResult, ...]
    execution_diagnostics: tuple[ExecutionTimingDiagnostic, ...]
    factor_redundancy: FactorRedundancyResult
    robust_inference: tuple[tuple[str, RobustInferenceResult], ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("proof_hash", self.proof_hash)
        _validate_proof_population(
            self.feature_results,
            self.target_results,
            self.physical_verifications,
            self.normalization_verifications,
            self.placebo_results,
            self.execution_diagnostics,
            self.robust_inference,
        )
        derived = _derive_proof_status(
            feature_results=self.feature_results,
            target_results=self.target_results,
            physical_verifications=self.physical_verifications,
            normalization_verifications=self.normalization_verifications,
            placebo_results=self.placebo_results,
            execution_diagnostics=self.execution_diagnostics,
            factor_redundancy=self.factor_redundancy,
            robust_inference=self.robust_inference,
        )
        if self.status is not derived:
            raise ValueError("Alpha Correctness proof status is not derived from its suite")
        digest = canonical_hash(self.identity_payload())
        if digest != self.proof_hash or self.proof_id != ArtifactId(
            f"alpha-correctness-proof:{digest[7:]}"
        ):
            raise ValueError("Alpha Correctness proof identity mismatch")

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "ALPHA_CORRECTNESS_PROOF", self.proof_id, self.proof_hash
        )

    @property
    def conclusion(self) -> AlphaCorrectnessConclusion:
        if self.status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED:
            return AlphaCorrectnessConclusion.CORRECTNESS_SUPPORTED
        if self.status is AlphaCorrectnessStatus.CORRECTNESS_FAILED:
            return AlphaCorrectnessConclusion.CORRECTNESS_FAILED
        return AlphaCorrectnessConclusion.INCONCLUSIVE

    def identity_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "conclusion": self.conclusion.value,
            "feature_results": [
                item.to_canonical_dict() for item in self.feature_results
            ],
            "target_results": [item.to_canonical_dict() for item in self.target_results],
            "physical_verifications": [
                item.to_canonical_dict() for item in self.physical_verifications
            ],
            "normalization_verifications": [
                item.to_canonical_dict()
                for item in self.normalization_verifications
            ],
            "placebo_results": [
                item.to_canonical_dict() for item in self.placebo_results
            ],
            "execution_diagnostics": [
                item.to_canonical_dict() for item in self.execution_diagnostics
            ],
            "factor_redundancy": self.factor_redundancy.to_canonical_dict(),
            "robust_inference": [
                {"factor_id": factor_id, "result": result.to_canonical_dict()}
                for factor_id, result in self.robust_inference
            ],
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "proof_id": str(self.proof_id),
            "proof_hash": self.proof_hash,
            **self.identity_payload(),
        }

    def to_evidence_dict(
        self,
        *,
        predecessor_failure_index_reference: (
            ValidationArtifactReference | None
        ) = None,
    ) -> dict[str, object]:
        """Return a bounded projection while retaining the full proof Merkle root.

        The in-memory proof is owner-rebuilt before admission. PostgreSQL Evidence
        stores its exact root and diagnostic summaries instead of duplicating
        millions of source-bar bindings and placebo observations in one JSONB
        value. The immutable source owners make the full proof reproducible.
        """

        factor_ids = tuple(
            sorted(
                {
                    comparison.factor_id
                    for result in self.feature_results
                    for comparison in result.comparisons
                }
            )
        )
        projection: dict[str, object] = {
            "schema_version": (
                "alpha-correctness-evidence-projection/v2"
                if predecessor_failure_index_reference is not None
                else "alpha-correctness-evidence-projection/v1"
            ),
            "status": self.status.value,
            "conclusion": self.conclusion.value,
            "factor_ids": list(factor_ids),
            "feature_results": _result_population_summary(self.feature_results),
            "target_results": _result_population_summary(self.target_results),
            "physical_verifications": [
                {
                    "normalized_owner_reference": (
                        item.normalized_owner_reference.to_canonical_dict()
                    ),
                    "physical_hash": item.physical_hash,
                    "checksums_hash": item.checksums_hash,
                    "checksum_count": len(item.checksums),
                    "normalized_bar_count": item.normalized_bar_count,
                    "normalized_bar_manifest_hash": (
                        item.normalized_bar_manifest_hash
                    ),
                }
                for item in self.physical_verifications
            ],
            "normalization_verifications": [
                {
                    "verification_id": str(item.verification_id),
                    "verification_hash": item.verification_hash,
                    "provenance": item.provenance.value,
                    "raw_owner_reference": item.raw_owner_reference.to_canonical_dict(),
                    "normalized_owner_reference": (
                        item.normalized_owner_reference.to_canonical_dict()
                    ),
                    "comparison_count": item.comparison_count,
                    "independent_value_hash": item.independent_value_hash,
                    "canonical_value_hash": item.canonical_value_hash,
                    "status": item.status.value,
                    "discrepancy_count": len(item.discrepancies),
                    "reason_codes": list(item.reason_codes),
                }
                for item in self.normalization_verifications
            ],
            "placebo_results": [
                {
                    "protocol_reference": item.protocol_reference.to_canonical_dict(),
                    "factor_id": item.factor_id,
                    "target_id": item.target_id,
                    "kind": item.kind.value,
                    "observation_count": len(item.observations),
                    "rank_ic_diagnostic": (
                        item.to_canonical_dict()["rank_ic_diagnostic"]
                    ),
                    "result_hash": item.result_hash,
                }
                for item in self.placebo_results
            ],
            "execution_diagnostics": [
                item.to_canonical_dict() for item in self.execution_diagnostics
            ],
            "factor_redundancy": self.factor_redundancy.to_canonical_dict(),
            "robust_inference": [
                {"factor_id": factor_id, "result": result.to_canonical_dict()}
                for factor_id, result in self.robust_inference
            ],
            "limitations": list(self.limitations),
            "full_proof_owner_reload_required": True,
        }
        if predecessor_failure_index_reference is not None:
            if (
                predecessor_failure_index_reference.artifact_kind
                != "ALPHA_CORRECTNESS_FAILURE_INDEX"
            ):
                raise ValueError(
                    "Correctness Evidence v2 requires a failure-index owner"
                )
            projection["predecessor_failure_index_reference"] = (
                predecessor_failure_index_reference.to_canonical_dict()
            )
            projection["target_semantic_statuses"] = (
                _target_semantic_status_summary(self.target_results)
            )
        projection_hash = canonical_hash(projection)
        return {
            "proof_id": str(self.proof_id),
            "proof_hash": self.proof_hash,
            "projection_hash": projection_hash,
            **projection,
        }


def build_alpha_correctness_proof(
    *,
    feature_results: tuple[FeatureReproductionResult, ...],
    target_results: tuple[TargetReproductionResult, ...],
    physical_verifications: tuple[PhysicalSourceVerification, ...],
    placebo_results: tuple[PlaceboResult, ...],
    execution_diagnostics: tuple[ExecutionTimingDiagnostic, ...],
    factor_redundancy: FactorRedundancyResult,
    robust_inference: tuple[tuple[str, RobustInferenceResult], ...],
    normalization_verifications: tuple[IndependentNormalizationVerification, ...] = (),
) -> AlphaCorrectnessProof:
    features = tuple(
        sorted(feature_results, key=lambda item: (item.session, item.symbol))
    )
    targets = tuple(
        sorted(target_results, key=lambda item: (item.decision_time, item.symbol))
    )
    physical = tuple(
        sorted(
            physical_verifications,
            key=lambda item: str(item.normalized_owner_reference.artifact_id),
        )
    )
    normalization = tuple(
        sorted(
            normalization_verifications,
            key=lambda item: str(item.normalized_owner_reference.artifact_id),
        )
    )
    placebos = tuple(
        sorted(placebo_results, key=lambda item: (item.factor_id, item.kind.value))
    )
    execution = tuple(sorted(execution_diagnostics, key=lambda item: item.proxy.value))
    inference = tuple(sorted(robust_inference, key=lambda item: item[0]))
    _validate_proof_population(
        features,
        targets,
        physical,
        normalization,
        placebos,
        execution,
        inference,
    )
    status = _derive_proof_status(
        feature_results=features,
        target_results=targets,
        physical_verifications=physical,
        normalization_verifications=normalization,
        placebo_results=placebos,
        execution_diagnostics=execution,
        factor_redundancy=factor_redundancy,
        robust_inference=inference,
    )
    conclusion = (
        AlphaCorrectnessConclusion.CORRECTNESS_SUPPORTED
        if status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
        else AlphaCorrectnessConclusion.CORRECTNESS_FAILED
        if status is AlphaCorrectnessStatus.CORRECTNESS_FAILED
        else AlphaCorrectnessConclusion.INCONCLUSIVE
    )
    limitations = tuple(
        sorted(
            {
                "ALPHA_PROVEN_FALSE",
                "FORMAL_OOS_FALSE",
                "NO_TRADING_AUTHORITY",
                *(
                    ("INCONCLUSIVE",)
                    if conclusion is AlphaCorrectnessConclusion.INCONCLUSIVE
                    else ()
                ),
                *(
                    ("PHYSICAL_REPRODUCTION_NOT_ESTABLISHED",)
                    if status
                    is AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
                    else ()
                ),
            }
        )
    )
    payload: dict[str, object] = {
        "status": status.value,
        "conclusion": conclusion.value,
        "feature_results": [item.to_canonical_dict() for item in features],
        "target_results": [item.to_canonical_dict() for item in targets],
        "physical_verifications": [item.to_canonical_dict() for item in physical],
        "normalization_verifications": [
            item.to_canonical_dict() for item in normalization
        ],
        "placebo_results": [item.to_canonical_dict() for item in placebos],
        "execution_diagnostics": [item.to_canonical_dict() for item in execution],
        "factor_redundancy": factor_redundancy.to_canonical_dict(),
        "robust_inference": [
            {"factor_id": factor_id, "result": result.to_canonical_dict()}
            for factor_id, result in inference
        ],
        "limitations": list(limitations),
    }
    digest = canonical_hash(payload)
    return AlphaCorrectnessProof(
        ArtifactId(f"alpha-correctness-proof:{digest[7:]}"),
        digest,
        status,
        features,
        targets,
        physical,
        normalization,
        placebos,
        execution,
        factor_redundancy,
        inference,
        limitations,
    )


def _result_population_summary(
    results: tuple[FeatureReproductionResult, ...]
    | tuple[TargetReproductionResult, ...],
) -> dict[str, object]:
    statuses = Counter(item.status.value for item in results)
    discrepancies = Counter(
        discrepancy for item in results for discrepancy in item.discrepancies
    )
    availability_reasons: Counter[str] = Counter()
    for item in results:
        if isinstance(item, FeatureReproductionResult):
            availability_reasons.update(item.incomplete_reason_codes)
        else:
            availability_reasons.update(item.unavailable_reason_codes)
    return {
        "count": len(results),
        "status_counts": dict(sorted(statuses.items())),
        "discrepancy_counts": dict(sorted(discrepancies.items())),
        "availability_reason_counts": dict(sorted(availability_reasons.items())),
    }


def _target_semantic_status_summary(
    results: tuple[TargetReproductionResult, ...],
) -> dict[str, object]:
    semantic_results = tuple(item.semantic_result for item in results)
    if not semantic_results or any(item is None for item in semantic_results):
        raise ValueError(
            "Correctness Evidence v2 requires semantic Target results"
        )
    resolved = tuple(item for item in semantic_results if item is not None)
    specifications = tuple(
        sorted(
            {item.semantic_specification for item in resolved},
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    fields = (
        "decision_reference_status",
        "outcome_window_status",
        "checkpoint_observation_status",
        "checkpoint_return_status",
        "mfe_status",
        "mae_status",
        "barrier_status",
    )
    return {
        "count": len(resolved),
        "semantic_specification_references": [
            item.to_canonical_dict() for item in specifications
        ],
        "status_counts": {
            field_name: dict(
                sorted(
                    Counter(
                        getattr(item, field_name).value for item in resolved
                    ).items()
                )
            )
            for field_name in fields
        },
    }


def _derive_proof_status(
    *,
    feature_results: tuple[FeatureReproductionResult, ...],
    target_results: tuple[TargetReproductionResult, ...],
    physical_verifications: tuple[PhysicalSourceVerification, ...],
    normalization_verifications: tuple[IndependentNormalizationVerification, ...],
    placebo_results: tuple[PlaceboResult, ...],
    execution_diagnostics: tuple[ExecutionTimingDiagnostic, ...],
    factor_redundancy: FactorRedundancyResult,
    robust_inference: tuple[tuple[str, RobustInferenceResult], ...],
) -> AlphaCorrectnessStatus:
    statuses = tuple(item.status for item in feature_results) + tuple(
        item.status for item in target_results
    )
    if AlphaCorrectnessStatus.CORRECTNESS_FAILED in statuses:
        return AlphaCorrectnessStatus.CORRECTNESS_FAILED
    if any(
        item.status is IndependentNormalizationStatus.MISMATCH
        for item in normalization_verifications
    ):
        return AlphaCorrectnessStatus.CORRECTNESS_FAILED
    factor_complete = bool(feature_results) and all(
        {item.factor_id for item in result.comparisons} == _SUPPORTED_FACTORS
        for result in feature_results
    )
    physical_by_reference = {
        item.normalized_owner_reference: item for item in physical_verifications
    }
    bound_physical = (
        bool(physical_by_reference)
        and all(
            item.physical_source_reference in physical_by_reference
            for item in feature_results
        )
        and all(
            item.physical_source_reference in physical_by_reference
            for item in target_results
        )
    )
    normalization_by_reference = {
        item.normalized_owner_reference: item
        for item in normalization_verifications
    }
    normalization_complete = (
        bool(normalization_by_reference)
        and set(normalization_by_reference) == set(physical_by_reference)
        and len(normalization_by_reference) == len(normalization_verifications)
        and all(
            item.status is IndependentNormalizationStatus.MATCHED
            and item.comparison_count > 0
            for item in normalization_verifications
        )
    )
    expected_placebos = {
        (factor_id, kind)
        for factor_id in _SUPPORTED_FACTORS
        for kind in PlaceboKind
    }
    actual_placebos = {(item.factor_id, item.kind) for item in placebo_results}
    placebo_targets = {item.target_id for item in placebo_results}
    placebo_protocols = {
        (item.factor_id, item.protocol.protocol_id, item.protocol.protocol_hash)
        for item in placebo_results
    }
    placebo_complete = (
        actual_placebos == expected_placebos
        and len(placebo_results) == len(expected_placebos)
        and all(item.observations for item in placebo_results)
        and len(placebo_targets) == 1
        and len(placebo_protocols) == len(_SUPPORTED_FACTORS)
    )
    execution_populations = {
        (
            item.information_cutoff,
            item.information_cutoff_price,
            item.information_cutoff_reference,
            item.target_reference_price,
            item.target_observed_at,
            item.target_available_at,
            item.target_source_reference,
        )
        for item in execution_diagnostics
    }
    execution_complete = (
        {item.proxy for item in execution_diagnostics} == set(ExecutionPriceProxy)
        and len(execution_diagnostics) == len(ExecutionPriceProxy)
        and len(execution_populations) == 1
    )
    inference_by_factor = dict(robust_inference)
    inference_complete = (
        set(inference_by_factor) == _SUPPORTED_FACTORS
        and len(inference_by_factor) == len(robust_inference)
        and len(
            {item.protocol.reference for item in inference_by_factor.values()}
        )
        == 1
        and all(
            item.sensitivity and item.observation_count > 0
            for item in inference_by_factor.values()
        )
    )
    redundancy_complete = (
        factor_redundancy.factor_ids == tuple(sorted(_SUPPORTED_FACTORS))
        and factor_redundancy.status != "NOT_ESTIMABLE"
    )
    if not bound_physical or any(
        item is AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
        for item in statuses
    ):
        return AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
    if (
        not factor_complete
        or not normalization_complete
        or not placebo_complete
        or not execution_complete
        or not redundancy_complete
        or not inference_complete
        or any(item is AlphaCorrectnessStatus.PARTIALLY_REPRODUCED for item in statuses)
    ):
        return AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    if statuses and all(
        item is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED for item in statuses
    ):
        return AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    return AlphaCorrectnessStatus.PARTIALLY_REPRODUCED


def reproduce_execution_timing_diagnostics(
    *,
    target: TargetReproductionResult,
    source_bars: tuple[HistoricalNormalizedBar, ...],
) -> tuple[ExecutionTimingDiagnostic, ...]:
    """Rebuild the four frozen entry proxies from the exact normalized owner.

    Close observations become available at ``event_end``.  A bar-open proxy is
    admitted only from a bar whose ``event_start`` is strictly after the
    Information Cutoff; this deliberately excludes treating the 14:55 close
    and a same-timestamp 14:55 open as simultaneously executable.
    """

    owner_reference = target.physical_source_reference
    if owner_reference is None:
        raise ValueError("execution reproduction requires physical owner binding")
    if (
        target.decision_reference_price is None
        or target.target_price is None
        or not target.decision_source_ids
        or not target.target_source_ids
    ):
        raise ValueError("execution proxy is not estimable from frozen source bars")
    bound = tuple(
        item
        for item in _ordered_bars(source_bars)
        if item.symbol == target.symbol
        and item.timeframe is Timeframe.MINUTE_5
        and item.open is not None
        and item.close is not None
    )
    by_id = {str(item.bar_id): item for item in bound}
    expected_ids = set(target.decision_source_ids) | set(target.target_source_ids)
    if not expected_ids.issubset(by_id):
        raise ValueError("execution reproduction is missing Target source bars")
    for source_id, source_hash in zip(
        (*target.decision_source_ids, *target.target_source_ids),
        (*target.decision_source_hashes, *target.target_source_hashes),
        strict=True,
    ):
        if by_id[source_id].content_hash != source_hash:
            raise ValueError("execution reproduction source hash drifted")

    decision_bars = tuple(by_id[item] for item in target.decision_source_ids)
    target_bars = tuple(by_id[item] for item in target.target_source_ids)
    decision_bar = max(decision_bars, key=_bar_time_key)
    target_bar = max(target_bars, key=_bar_time_key)
    if (
        decision_bar.event_end != target.decision_time
        or decision_bar.close != target.decision_reference_price
        or target_bar.event_end != target.target_event_end
        or target_bar.close != target.target_price
    ):
        raise ValueError("execution reproduction disagrees with Target prices/times")

    after_cutoff = tuple(
        item
        for item in bound
        if item.event_end > target.decision_time
        and item.event_end < target.target_event_end
    )
    next_close_bar = min(after_cutoff, key=_bar_time_key, default=None)
    next_open_bar = min(
        (
            item
            for item in after_cutoff
            if item.event_start > target.decision_time
        ),
        key=lambda item: (item.event_start, item.event_end, str(item.bar_id)),
        default=None,
    )
    decision_session = target.decision_time.astimezone(_SHANGHAI).date()
    session_close_bar = max(
        (
            item
            for item in after_cutoff
            if item.market_date == decision_session
        ),
        key=_bar_time_key,
        default=None,
    )
    if next_close_bar is None or next_open_bar is None or session_close_bar is None:
        raise ValueError("execution proxy is not estimable from frozen source bars")
    assert next_close_bar.close is not None
    assert next_open_bar.open is not None
    assert session_close_bar.close is not None

    inputs = ExecutionPriceInputs(
        information_cutoff=target.decision_time,
        decision_reference=TimedPriceObservation(
            target.decision_reference_price,
            decision_bar.event_end,
            decision_bar.event_end,
            owner_reference,
        ),
        next_observable_price=TimedPriceObservation(
            next_close_bar.close,
            next_close_bar.event_end,
            next_close_bar.event_end,
            owner_reference,
        ),
        next_bar_open=TimedPriceObservation(
            next_open_bar.open,
            next_open_bar.event_start,
            next_open_bar.event_start,
            owner_reference,
        ),
        session_close=TimedPriceObservation(
            session_close_bar.close,
            session_close_bar.event_end,
            session_close_bar.event_end,
            owner_reference,
        ),
        target_reference=TimedPriceObservation(
            target.target_price,
            target_bar.event_end,
            target_bar.event_end,
            owner_reference,
        ),
    )
    return tuple(
        sorted(
            (
                diagnose_execution_price(inputs, proxy)
                for proxy in ExecutionPriceProxy
            ),
            key=lambda item: item.proxy.value,
        )
    )


def _validate_proof_population(
    features: tuple[FeatureReproductionResult, ...],
    targets: tuple[TargetReproductionResult, ...],
    physical: tuple[PhysicalSourceVerification, ...],
    normalization: tuple[IndependentNormalizationVerification, ...],
    placebos: tuple[PlaceboResult, ...],
    execution: tuple[ExecutionTimingDiagnostic, ...],
    inference: tuple[tuple[str, RobustInferenceResult], ...],
) -> None:
    if features != tuple(sorted(features, key=lambda item: (item.session, item.symbol))):
        raise ValueError("Alpha Correctness Feature results must be sorted")
    if targets != tuple(
        sorted(targets, key=lambda item: (item.decision_time, item.symbol))
    ):
        raise ValueError("Alpha Correctness Target results must be sorted")
    feature_keys = tuple((item.session, item.symbol) for item in features)
    target_keys = tuple((item.decision_time, item.symbol) for item in targets)
    if (
        not features
        or not targets
        or len(feature_keys) != len(set(feature_keys))
        or len(target_keys) != len(set(target_keys))
    ):
        raise ValueError("Alpha Correctness proof inputs are incomplete or duplicated")
    feature_decision_keys = {(item.decision_time, item.symbol) for item in features}
    if feature_decision_keys != set(target_keys):
        raise ValueError(
            "Alpha Correctness Feature and Target populations must align exactly"
        )
    targets_by_key = {(item.decision_time, item.symbol): item for item in targets}
    for feature in features:
        target = targets_by_key[(feature.decision_time, feature.symbol)]
        if feature.physical_source_reference != target.physical_source_reference:
            raise ValueError(
                "Alpha Correctness Feature and Target physical owners must match"
            )
        if any(
            comparison.event_end.astimezone(_SHANGHAI).date()
            >= target.target_session
            for comparison in feature.comparisons
        ):
            raise ValueError(
                "Alpha Correctness Feature lineage references future Target bars"
            )
    if physical != tuple(
        sorted(
            physical,
            key=lambda item: str(item.normalized_owner_reference.artifact_id),
        )
    ) or len({item.normalized_owner_reference for item in physical}) != len(physical):
        raise ValueError("Alpha Correctness physical owners must be unique and sorted")
    if normalization != tuple(
        sorted(
            normalization,
            key=lambda item: str(item.normalized_owner_reference.artifact_id),
        )
    ) or len({item.normalized_owner_reference for item in normalization}) != len(
        normalization
    ):
        raise ValueError(
            "Alpha Correctness normalization verifications must be unique and sorted"
        )
    if placebos != tuple(
        sorted(placebos, key=lambda item: (item.factor_id, item.kind.value))
    ):
        raise ValueError("Alpha Correctness placebo results must be sorted")
    if execution != tuple(sorted(execution, key=lambda item: item.proxy.value)):
        raise ValueError("Alpha Correctness execution diagnostics must be sorted")
    if inference != tuple(sorted(inference, key=lambda item: item[0])) or len(
        {item[0] for item in inference}
    ) != len(inference):
        raise ValueError("Alpha Correctness inference results must be unique and sorted")


def reproduce_intraday_features(
    *,
    session: date,
    symbol: str,
    decision_time: datetime,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    persisted: tuple[PersistedFeatureObservation, ...],
    physical_verification: PhysicalSourceVerification | None,
    incomplete_reason_codes: tuple[str, ...] = (),
) -> FeatureReproductionResult:
    """Recompute frozen intraday factors directly from bounded normalized bars."""

    _require_aware("decision_time", decision_time)
    decision_session = decision_time.astimezone(_SHANGHAI).date()
    if session != decision_session:
        raise ValueError("Feature session must equal DecisionTime session")
    persisted_ids = tuple(item.factor_id for item in persisted)
    if persisted_ids != tuple(sorted(set(persisted_ids))):
        raise ValueError("persisted Feature observations must be unique and sorted")
    selected = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == session
            and item.timeframe is Timeframe.MINUTE_5
            and item.event_end <= decision_time
        )
    )
    if not selected:
        return FeatureReproductionResult(
            session=session,
            symbol=symbol,
            decision_time=decision_time,
            status=_correctness_status(
                discrepancies=(),
                physical_source_available=physical_verification is not None,
                complete=False,
            ),
            physical_source_reference=(
                None
                if physical_verification is None
                else physical_verification.normalized_owner_reference
            ),
            comparisons=(),
            discrepancies=(),
            incomplete_reason_codes=tuple(
                sorted(
                    set(incomplete_reason_codes)
                    | {"DECISION_TIME_SOURCE_BARS_MISSING"}
                )
            ),
        )
    if any(item.event_end > decision_time for item in selected):
        raise ValueError("Feature source event_end exceeds DecisionTime")
    try:
        recomputed = _intraday_values(selected)
    except ValueError:
        if not incomplete_reason_codes:
            raise
        source_discrepancies = (
            ("PERSISTED_FEATURE_SOURCE_NOT_REPRODUCIBLE",)
            if persisted
            else ()
        )
        return FeatureReproductionResult(
            session=session,
            symbol=symbol,
            decision_time=decision_time,
            status=_correctness_status(
                discrepancies=source_discrepancies,
                physical_source_available=physical_verification is not None,
                complete=False,
            ),
            physical_source_reference=(
                None
                if physical_verification is None
                else physical_verification.normalized_owner_reference
            ),
            comparisons=(),
            discrepancies=source_discrepancies,
            incomplete_reason_codes=tuple(
                sorted(
                    set(incomplete_reason_codes)
                    | {"FEATURE_SOURCE_NOT_ESTIMABLE"}
                )
            ),
        )
    comparisons: list[FeatureCorrectnessComparison] = []
    all_discrepancies: list[str] = []
    for observation in persisted:
        value, factor_bars = recomputed[observation.factor_id]
        ids, hashes, lineage = _source_lineage(factor_bars)
        discrepancies: list[str] = []
        if observation.value != value:
            discrepancies.append(f"VALUE_MISMATCH:{observation.factor_id}")
        if (
            observation.source_bar_count != len(ids)
            or observation.source_lineage_hash != lineage
        ):
            discrepancies.append(f"SOURCE_LINEAGE_MISMATCH:{observation.factor_id}")
        if (
            observation.event_start != factor_bars[0].event_start
            or observation.event_end != factor_bars[-1].event_end
        ):
            discrepancies.append(f"EVENT_INTERVAL_MISMATCH:{observation.factor_id}")
        comparison = FeatureCorrectnessComparison(
            factor_id=observation.factor_id,
            persisted_value=observation.value,
            recomputed_value=value,
            persisted_source_bar_count=observation.source_bar_count,
            persisted_source_lineage_hash=observation.source_lineage_hash,
            persisted_event_start=observation.event_start,
            persisted_event_end=observation.event_end,
            source_bar_count=len(ids),
            source_lineage_hash=lineage,
            event_start=factor_bars[0].event_start,
            event_end=factor_bars[-1].event_end,
            decision_time=decision_time,
            discrepancies=tuple(discrepancies),
        )
        comparisons.append(comparison)
        all_discrepancies.extend(discrepancies)
    status = _correctness_status(
        discrepancies=tuple(all_discrepancies),
        physical_source_available=physical_verification is not None,
        complete=(
            {item.factor_id for item in persisted} == _SUPPORTED_FACTORS
            and not incomplete_reason_codes
        ),
    )
    return FeatureReproductionResult(
        session=session,
        symbol=symbol,
        decision_time=decision_time,
        status=status,
        physical_source_reference=(
            None
            if physical_verification is None
            else physical_verification.normalized_owner_reference
        ),
        comparisons=tuple(comparisons),
        discrepancies=tuple(all_discrepancies),
        incomplete_reason_codes=tuple(sorted(set(incomplete_reason_codes))),
    )


def reproduce_t_plus_one_1030_target_v2(
    *,
    label: TargetOutcomeLabel,
    protocol: OutcomeTargetProtocol,
    trading_calendar: TradingCalendarArtifact,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    physical_verification: PhysicalSourceVerification | None,
    corporate_action_reason_code: str | None = None,
) -> TargetReproductionResult:
    """Independently select sources and reproduce one persisted v3 label."""

    persisted = label.semantic_result
    specification = protocol.target_semantic_specification
    if label.schema_version != "target-outcome-label/v3" or persisted is None:
        raise ValueError("v2 Target protocol requires a v3 persisted label")
    if specification is None:
        raise ValueError("v3 Target label requires protocol semantics")
    if persisted.semantic_specification != specification.reference:
        raise ValueError("v3 Target semantic specification owner drifted")
    target = next(
        (
            item
            for item in protocol.targets
            if item.target_id == label.target.artifact_id
            and item.target_hash == label.target.content_hash
        ),
        None,
    )
    if target is None:
        raise ValueError("v3 Target Definition owner is not bound to its protocol")
    resolved_next = trading_calendar.resolve_next_session_date(
        DecisionTime(persisted.decision_time)
    )
    if persisted.target_session != resolved_next:
        raise ValueError("v3 Target session is not Calendar-owner resolved")
    reproduced = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol=label.symbol,
        decision_time=persisted.decision_time,
        next_session_date=resolved_next,
        source_bars=source_bars,
    )
    if corporate_action_reason_code is not None:
        reproduced = apply_raw_corporate_action_conflict(
            reproduced,
            target=target,
            reason_code=corporate_action_reason_code,
        )
    discrepancies = _semantic_target_discrepancies(persisted, reproduced)
    physical_reference = (
        None
        if physical_verification is None
        else physical_verification.normalized_owner_reference
    )
    return TargetReproductionResult(
        symbol=reproduced.symbol,
        decision_time=reproduced.decision_time,
        target_session=reproduced.target_session,
        target_event_end=reproduced.outcome_window_end,
        decision_reference_price=reproduced.decision_reference_price,
        target_price=reproduced.checkpoint_price,
        target_return=reproduced.checkpoint_return,
        decision_source_ids=tuple(
            str(item.artifact_id)
            for item in reproduced.decision_source_references
        ),
        decision_source_hashes=tuple(
            item.content_hash for item in reproduced.decision_source_references
        ),
        target_source_ids=tuple(
            str(item.artifact_id) for item in reproduced.outcome_source_references
        ),
        target_source_hashes=tuple(
            item.content_hash for item in reproduced.outcome_source_references
        ),
        persisted_observation=None,
        status=_correctness_status(
            discrepancies=discrepancies,
            physical_source_available=physical_reference is not None,
            complete=True,
        ),
        physical_source_reference=physical_reference,
        trading_calendar_reference=ValidationArtifactReference(
            "PIT_TRADING_CALENDAR",
            trading_calendar.artifact_id,
            trading_calendar.content_hash,
        ),
        discrepancies=discrepancies,
        unavailable_reason_codes=tuple(sorted(reproduced.reason_codes)),
        semantic_result=reproduced,
        persisted_semantic_result=persisted,
    )


def reproduce_t_plus_one_1030_target(
    *,
    symbol: str,
    decision_time: datetime,
    next_session: date,
    trading_calendar: TradingCalendarArtifact,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    persisted: PersistedTargetObservation | None,
    physical_verification: PhysicalSourceVerification | None,
    unavailable_reason_codes: tuple[str, ...] = (),
) -> TargetReproductionResult:
    """Independently reconstruct the frozen Decision reference and T+1 10:30 return."""

    _require_aware("decision_time", decision_time)
    decision_session = decision_time.astimezone(_SHANGHAI).date()
    resolved_next = trading_calendar.resolve_next_session_date(
        DecisionTime(decision_time)
    )
    if next_session != resolved_next:
        raise ValueError("Target must use the immediate next owner-resolved session")
    decision_bars = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == decision_session
            and item.timeframe is Timeframe.MINUTE_5
            and item.event_end <= decision_time
        )
    )
    checkpoint = datetime.combine(next_session, time(10, 30), _SHANGHAI).astimezone(
        decision_time.tzinfo
    )
    target_bars = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == next_session
            and item.timeframe is Timeframe.MINUTE_5
            and time(9, 30)
            <= item.event_start.astimezone(_SHANGHAI).time().replace(tzinfo=None)
            and item.event_end <= checkpoint
        )
    )
    target_start = datetime.combine(
        next_session, time(9, 30), _SHANGHAI
    ).astimezone(decision_time.tzinfo)
    checkpoint_complete = not (
        not target_bars
        or target_bars[0].event_start != target_start
        or target_bars[-1].event_end != checkpoint
    )
    decision_complete = bool(
        decision_bars and decision_bars[-1].event_end == decision_time
    )
    if not decision_complete or not checkpoint_complete:
        if not unavailable_reason_codes:
            if not decision_complete:
                raise ValueError("Decision reference checkpoint is incomplete")
            raise ValueError("T+1 10:30 checkpoint is incomplete")
        reasons = set(unavailable_reason_codes)
        if not decision_complete:
            reasons.add("DECISION_REFERENCE_NOT_ESTIMABLE")
        if not checkpoint_complete:
            reasons.add("T_PLUS_ONE_1030_NOT_ESTIMABLE")
        unavailable_discrepancies = _unavailable_target_discrepancies(reasons)
        return TargetReproductionResult(
            symbol=symbol,
            decision_time=decision_time,
            target_session=next_session,
            target_event_end=checkpoint,
            decision_reference_price=None,
            target_price=None,
            target_return=None,
            decision_source_ids=(),
            decision_source_hashes=(),
            target_source_ids=(),
            target_source_hashes=(),
            persisted_observation=None,
            status=_correctness_status(
                discrepancies=unavailable_discrepancies,
                physical_source_available=physical_verification is not None,
                complete=False,
            ),
            physical_source_reference=(
                None
                if physical_verification is None
                else physical_verification.normalized_owner_reference
            ),
            trading_calendar_reference=ValidationArtifactReference(
                "PIT_TRADING_CALENDAR",
                trading_calendar.artifact_id,
                trading_calendar.content_hash,
            ),
            discrepancies=unavailable_discrepancies,
            unavailable_reason_codes=tuple(sorted(reasons)),
        )
    if any(left.event_end != right.event_start for left, right in zip(target_bars, target_bars[1:], strict=False)):
        raise ValueError("T+1 checkpoint bars are not contiguous")
    decision_source = (decision_bars[-1],)
    decision_ids, decision_hashes, _ = _source_lineage(decision_source)
    target_ids, target_hashes, _ = _source_lineage(target_bars)
    if set(decision_ids).intersection(target_ids):
        raise ValueError("Feature/Decision and Target lineage must be disjoint")
    decision_price = decision_bars[-1].close
    target_price = target_bars[-1].close
    if decision_price is None or target_price is None or decision_price <= 0:
        if unavailable_reason_codes:
            price_reasons = tuple(
                sorted(
                    set(unavailable_reason_codes)
                    | {"TARGET_SOURCE_PRICE_NOT_ESTIMABLE"}
                )
            )
            unavailable_discrepancies = _unavailable_target_discrepancies(
                set(price_reasons)
            )
            return TargetReproductionResult(
                symbol=symbol,
                decision_time=decision_time,
                target_session=next_session,
                target_event_end=checkpoint,
                decision_reference_price=None,
                target_price=None,
                target_return=None,
                decision_source_ids=(),
                decision_source_hashes=(),
                target_source_ids=(),
                target_source_hashes=(),
                persisted_observation=None,
                status=_correctness_status(
                    discrepancies=unavailable_discrepancies,
                    physical_source_available=physical_verification is not None,
                    complete=False,
                ),
                physical_source_reference=(
                    None
                    if physical_verification is None
                    else physical_verification.normalized_owner_reference
                ),
                trading_calendar_reference=ValidationArtifactReference(
                    "PIT_TRADING_CALENDAR",
                    trading_calendar.artifact_id,
                    trading_calendar.content_hash,
                ),
                discrepancies=unavailable_discrepancies,
                unavailable_reason_codes=price_reasons,
            )
        raise ValueError("Target reproduction requires positive source prices")
    target_return = (target_price - decision_price) / decision_price
    discrepancies = _target_discrepancies(
        persisted,
        decision_price=decision_price,
        target_price=target_price,
        target_return=target_return,
        decision_ids=decision_ids,
        decision_hashes=decision_hashes,
        target_ids=target_ids,
        target_hashes=target_hashes,
        target_session=next_session,
        target_event_end=checkpoint,
    )
    if (
        "PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE"
        in unavailable_reason_codes
    ):
        discrepancies = (
            *discrepancies,
            "PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE",
        )
    status = _correctness_status(
        discrepancies=tuple(discrepancies),
        physical_source_available=physical_verification is not None,
        complete=persisted is not None and not unavailable_reason_codes,
    )
    return TargetReproductionResult(
        symbol=symbol,
        decision_time=decision_time,
        target_session=next_session,
        target_event_end=checkpoint,
        decision_reference_price=decision_price,
        target_price=target_price,
        target_return=target_return,
        decision_source_ids=decision_ids,
        decision_source_hashes=decision_hashes,
        target_source_ids=target_ids,
        target_source_hashes=target_hashes,
        persisted_observation=persisted,
        status=status,
        physical_source_reference=(
            None
            if physical_verification is None
            else physical_verification.normalized_owner_reference
        ),
        trading_calendar_reference=ValidationArtifactReference(
            "PIT_TRADING_CALENDAR",
            trading_calendar.artifact_id,
            trading_calendar.content_hash,
        ),
        discrepancies=tuple(discrepancies),
        unavailable_reason_codes=tuple(sorted(set(unavailable_reason_codes))),
    )


def _intraday_values(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> dict[str, tuple[Decimal, tuple[HistoricalNormalizedBar, ...]]]:
    first, latest = bars[0], bars[-1]
    if first.open is None or latest.close is None:
        raise ValueError("intraday correctness bars require endpoint prices")
    if first.open <= 0:
        raise ValueError("intraday first open must be positive")
    total_volume = sum((item.volume for item in bars), Decimal("0"))
    if total_volume <= 0 or any(item.amount is None for item in bars):
        raise ValueError("VWAP correctness bars require positive volume and amount")
    total_amount = sum(
        (item.amount for item in bars if item.amount is not None), Decimal("0")
    )
    vwap = total_amount / total_volume
    split = max(1, len(bars) // 2)
    first_bars = bars[:split]
    first_volume = sum((item.volume for item in first_bars), Decimal("0"))
    first_amount = sum(
        (item.amount for item in first_bars if item.amount is not None), Decimal("0")
    )
    if first_volume <= 0 or first_amount <= 0:
        raise ValueError("VWAP slope correctness window is unavailable")
    first_vwap = first_amount / first_volume
    return {
        "intraday_return_to_decision_time": (
            _quantize(latest.close / first.open - Decimal("1")),
            (first, latest) if first is not latest else (first,),
        ),
        "price_vs_vwap_return": (
            _quantize(latest.close / vwap - Decimal("1")),
            bars,
        ),
        "vwap_slope": (
            _quantize(vwap / first_vwap - Decimal("1")),
            bars,
        ),
    }


def _target_discrepancies(
    persisted: PersistedTargetObservation | None,
    *,
    decision_price: Decimal,
    target_price: Decimal,
    target_return: Decimal,
    decision_ids: tuple[str, ...],
    decision_hashes: tuple[str, ...],
    target_ids: tuple[str, ...],
    target_hashes: tuple[str, ...],
    target_session: date,
    target_event_end: datetime,
) -> tuple[str, ...]:
    if persisted is None:
        return ()
    discrepancies: list[str] = []
    if persisted.decision_reference_price != decision_price:
        discrepancies.append("DECISION_REFERENCE_PRICE_MISMATCH")
    if persisted.target_price != target_price:
        discrepancies.append("TARGET_PRICE_MISMATCH")
    if persisted.target_return != target_return:
        discrepancies.append("TARGET_RETURN_MISMATCH")
    if (
        persisted.decision_source_ids != decision_ids
        or persisted.decision_source_hashes != decision_hashes
        or persisted.target_source_ids != target_ids
        or persisted.target_source_hashes != target_hashes
    ):
        discrepancies.append("TARGET_SOURCE_LINEAGE_MISMATCH")
    if (
        persisted.target_session != target_session
        or persisted.target_event_end != target_event_end
    ):
        discrepancies.append("TARGET_TEMPORAL_BOUNDARY_MISMATCH")
    return tuple(discrepancies)


def _semantic_target_discrepancies(
    persisted: TargetSemanticResult,
    reproduced: TargetSemanticResult,
) -> tuple[str, ...]:
    comparisons = (
        (
            "TARGET_SEMANTIC_SPECIFICATION_MISMATCH",
            persisted.semantic_specification,
            reproduced.semantic_specification,
        ),
        (
            "TARGET_SEMANTIC_BOUNDARY_MISMATCH",
            (
                persisted.symbol,
                persisted.decision_time,
                persisted.target_session,
                persisted.outcome_window_start,
                persisted.outcome_window_end,
                persisted.expected_outcome_bar_count,
                persisted.observed_outcome_bar_count,
            ),
            (
                reproduced.symbol,
                reproduced.decision_time,
                reproduced.target_session,
                reproduced.outcome_window_start,
                reproduced.outcome_window_end,
                reproduced.expected_outcome_bar_count,
                reproduced.observed_outcome_bar_count,
            ),
        ),
        (
            "TARGET_SEMANTIC_STATUS_MISMATCH",
            (
                persisted.decision_reference_status,
                persisted.outcome_window_status,
                persisted.checkpoint_observation_status,
                persisted.checkpoint_return_status,
                persisted.mfe_status,
                persisted.mae_status,
                persisted.barrier_status,
            ),
            (
                reproduced.decision_reference_status,
                reproduced.outcome_window_status,
                reproduced.checkpoint_observation_status,
                reproduced.checkpoint_return_status,
                reproduced.mfe_status,
                reproduced.mae_status,
                reproduced.barrier_status,
            ),
        ),
        (
            "TARGET_SEMANTIC_VALUE_MISMATCH",
            (
                persisted.decision_reference_price,
                persisted.checkpoint_price,
                persisted.checkpoint_return,
                persisted.mfe,
                persisted.mae,
                persisted.barrier_passages,
                persisted.barrier_ordering,
            ),
            (
                reproduced.decision_reference_price,
                reproduced.checkpoint_price,
                reproduced.checkpoint_return,
                reproduced.mfe,
                reproduced.mae,
                reproduced.barrier_passages,
                reproduced.barrier_ordering,
            ),
        ),
        (
            "TARGET_SEMANTIC_SOURCE_LINEAGE_MISMATCH",
            (
                persisted.decision_source_references,
                persisted.outcome_source_references,
                persisted.diagnostic_source_references,
            ),
            (
                reproduced.decision_source_references,
                reproduced.outcome_source_references,
                reproduced.diagnostic_source_references,
            ),
        ),
        (
            "TARGET_SEMANTIC_REASON_MISMATCH",
            persisted.reason_codes,
            reproduced.reason_codes,
        ),
    )
    return tuple(code for code, left, right in comparisons if left != right)


def _source_lineage(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    ids = tuple(str(item.bar_id) for item in bars)
    hashes = tuple(item.content_hash for item in bars)
    lineage = _lineage_hash(ids, hashes)
    return ids, hashes, lineage


def _lineage_hash(ids: tuple[str, ...], hashes: tuple[str, ...]) -> str:
    return canonical_hash(
        {
            "normalized_source_bars": [
                {"bar_id": bar_id, "bar_hash": bar_hash}
                for bar_id, bar_hash in zip(ids, hashes, strict=True)
            ]
        }
    )


def _shared_normalized_owner(
    feature: HistoricalSessionComponent,
    outcome: HistoricalSessionComponent,
) -> ValidationArtifactReference:
    feature_owners = {
        item for item in feature.source_references if item.artifact_kind == "NORMALIZED_DATASET"
    }
    outcome_owners = {
        item for item in outcome.source_references if item.artifact_kind == "NORMALIZED_DATASET"
    }
    shared = feature_owners.intersection(outcome_owners)
    if len(shared) != 1:
        raise ValueError("Historical correctness requires one shared normalized owner")
    return next(iter(shared))


def _component_decision_time(component: HistoricalSessionComponent) -> datetime:
    decision_time = component.source_max_event_time
    if decision_time.astimezone(_SHANGHAI).date() != component.trading_date:
        raise ValueError("Historical Feature owner DecisionTime projection is invalid")
    return decision_time


def _feature_symbols(component: HistoricalSessionComponent) -> set[str]:
    raw_features = component.payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("Historical Feature owner payload is missing")
    symbols = {
        str(_mapping(item, "Historical Feature computation")["symbol"])
        for item in raw_features
    }
    if not symbols:
        raise ValueError("Historical Feature symbols are incomplete")
    return symbols


def _declared_target_omissions(
    component: HistoricalSessionComponent,
) -> dict[str, tuple[str, ...]]:
    raw_omissions = component.payload.get("target_omissions", [])
    if not isinstance(raw_omissions, list):
        raise ValueError("Historical Outcome target omissions are malformed")
    result: dict[str, tuple[str, ...]] = {}
    for raw_omission in raw_omissions:
        omission = _mapping(raw_omission, "Historical Outcome target omission")
        if set(omission) != {
            "symbol",
            "target_count",
            "target_ids",
            "reason_codes",
        }:
            raise ValueError("Historical Outcome target omission fields drifted")
        symbol = str(omission["symbol"])
        target_ids = omission["target_ids"]
        reasons = omission["reason_codes"]
        target_count = omission["target_count"]
        if (
            symbol in result
            or not symbol
            or isinstance(target_count, bool)
            or not isinstance(target_count, int)
            or target_count <= 0
            or not isinstance(target_ids, list)
            or len(target_ids) != target_count
            or len({str(item) for item in target_ids}) != target_count
            or not isinstance(reasons, list)
            or not reasons
            or any(not isinstance(item, str) or not item for item in reasons)
        ):
            raise ValueError("Historical Outcome target omission is invalid")
        result[symbol] = tuple(sorted(set(reasons)))
    return result


def _resolve_target_symbol_omissions(
    *,
    feature_symbols: set[str],
    label_symbols: set[str],
    declared_omissions: Mapping[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    target_only = label_symbols - feature_symbols
    if target_only:
        raise ValueError("Target symbols absent from Feature owner")
    declared_symbols = set(declared_omissions)
    if declared_symbols - feature_symbols or declared_symbols & label_symbols:
        raise ValueError("Historical target omission owner projection drifted")
    omitted = feature_symbols - label_symbols
    return {
        symbol: declared_omissions.get(
            symbol,
            ("PERSISTED_TARGET_OMISSION_NOT_DECLARED",),
        )
        for symbol in sorted(omitted)
    }


def _persisted_feature_projection(
    component: HistoricalSessionComponent,
    bars_by_id: Mapping[str, HistoricalNormalizedBar],
) -> tuple[
    dict[str, tuple[PersistedFeatureObservation, ...]],
    dict[str, tuple[str, ...]],
]:
    raw_features = component.payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("Historical Feature owner payload is missing")
    projected: dict[str, list[PersistedFeatureObservation]] = {}
    unavailable: dict[str, list[str]] = {}
    for raw_feature in raw_features:
        feature = _mapping(raw_feature, "Historical Feature computation")
        symbol = str(feature["symbol"])
        projected.setdefault(symbol, [])
        values = feature.get("values")
        if not isinstance(values, list):
            raise ValueError("Historical Feature values are missing")
        for raw_value in values:
            value = _mapping(raw_value, "Historical Feature value")
            factor_id = str(value["output_id"])
            if factor_id not in _SUPPORTED_FACTORS:
                continue
            if value.get("state") != "AVAILABLE" or value.get("value") is None:
                raw_reasons = value.get("missing_reason_codes")
                reasons = (
                    tuple(str(item) for item in raw_reasons)
                    if isinstance(raw_reasons, list)
                    else ("OWNER_DECLARED_FACTOR_NOT_ESTIMABLE",)
                )
                unavailable.setdefault(symbol, []).extend(
                    f"{factor_id}:{reason}" for reason in reasons
                )
                continue
            raw_ids = value.get("normalized_source_bar_ids")
            raw_hashes = value.get("normalized_source_bar_hashes")
            if not isinstance(raw_ids, list) or not isinstance(raw_hashes, list):
                raise ValueError("Historical Feature normalized lineage is missing")
            ids = tuple(str(item) for item in raw_ids)
            hashes = tuple(str(item) for item in raw_hashes)
            if len(ids) != len(hashes) or not ids:
                raise ValueError("Historical Feature normalized lineage is incomplete")
            try:
                source_bars = tuple(bars_by_id[item] for item in ids)
            except KeyError as error:
                raise ValueError("Historical Feature source bar is absent from owner") from error
            if tuple(item.content_hash for item in source_bars) != hashes:
                raise ValueError("Historical Feature source hash disagrees with owner")
            observation = PersistedFeatureObservation.create(
                factor_id=factor_id,
                value=Decimal(str(value["value"])),
                source_bars=source_bars,
            )
            if (
                observation.event_start.isoformat() != str(value["source_event_start"])
                or observation.event_end.isoformat() != str(value["source_event_end"])
            ):
                raise ValueError("Historical Feature event-time projection drifted")
            projected.setdefault(symbol, []).append(observation)
    result = {
        symbol: tuple(sorted(values, key=lambda item: item.factor_id))
        for symbol, values in projected.items()
    }
    if not result or any(
        not {item.factor_id for item in values}.issubset(_SUPPORTED_FACTORS)
        for values in result.values()
    ):
        raise ValueError("Historical Feature owner projection is invalid")
    return result, {
        symbol: tuple(sorted(set(reasons)))
        for symbol, reasons in unavailable.items()
    }


def _target_labels(
    component: HistoricalSessionComponent,
) -> dict[str, TargetOutcomeLabel]:
    raw_labels = component.payload.get("labels")
    if not isinstance(raw_labels, list):
        raise ValueError("Historical Outcome labels are missing")
    labels = tuple(
        TargetOutcomeLabel.from_canonical_dict(
            _mapping(item, "Historical Outcome label")
        )
        for item in raw_labels
    )
    selected = tuple(
        item
        for item in labels
        if item.label_interval_end.astimezone(_SHANGHAI).time().replace(tzinfo=None)
        == time(10, 30)
    )
    by_symbol = {item.symbol: item for item in selected}
    if not by_symbol or len(by_symbol) != len(selected):
        raise ValueError("Historical T+1 10:30 Target labels are incomplete or duplicated")
    return by_symbol


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _ordered_bars(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> tuple[HistoricalNormalizedBar, ...]:
    ordered = tuple(
        sorted(bars, key=lambda item: (item.event_start, item.event_end, str(item.bar_id)))
    )
    ids = tuple(str(item.bar_id) for item in ordered)
    if len(ids) != len(set(ids)):
        raise ValueError("correctness source bars must be unique")
    return ordered


def _bar_time_key(
    bar: HistoricalNormalizedBar,
) -> tuple[datetime, datetime, str]:
    return bar.event_end, bar.event_start, str(bar.bar_id)


def _correctness_status(
    *,
    discrepancies: tuple[str, ...],
    physical_source_available: bool,
    complete: bool,
) -> AlphaCorrectnessStatus:
    if discrepancies:
        return AlphaCorrectnessStatus.CORRECTNESS_FAILED
    if not physical_source_available:
        return AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
    if not complete:
        return AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    return AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED


def _unavailable_target_discrepancies(
    reasons: set[str],
) -> tuple[str, ...]:
    discrepancies: set[str] = set()
    if "PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE" in reasons:
        discrepancies.add("PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE")
    if "PERSISTED_TARGET_OMISSION_NOT_DECLARED" in reasons:
        discrepancies.add("PERSISTED_TARGET_SYMBOL_MISSING")
    return tuple(sorted(discrepancies))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_SCALE, rounding=ROUND_HALF_EVEN)


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _require_aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


__all__ = [
    "AlphaCorrectnessConclusion",
    "AlphaCorrectnessProof",
    "AlphaCorrectnessStatus",
    "FeatureCorrectnessComparison",
    "FeatureReproductionResult",
    "HistoricalAlphaCorrectnessChecker",
    "HistoricalCorrectnessReproduction",
    "PersistedFeatureObservation",
    "PersistedTargetObservation",
    "PhysicalSourceVerification",
    "TargetReproductionResult",
    "build_alpha_correctness_proof",
    "reproduce_intraday_features",
    "reproduce_execution_timing_diagnostics",
    "reproduce_t_plus_one_1030_target",
    "reproduce_t_plus_one_1030_target_v2",
    "establish_physical_reproduction",
]
