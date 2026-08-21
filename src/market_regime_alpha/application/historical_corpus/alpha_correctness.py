"""Independent correctness checks over Historical normalized source bars.

This module is a checker, not a Feature, Target, Runtime or Evidence authority.
It deliberately recomputes the three WP-ALPHA-RESEARCH-01 intraday values and
the T+1 10:30 target without reading their persisted numerical outputs.
"""

from __future__ import annotations

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
from market_regime_alpha.application.historical_corpus.artifacts import (
    VerifiedHistoricalPackage,
    load_verified_historical_package,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
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
    normalized_bar_bindings: tuple[tuple[str, str], ...]

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
        if not self.normalized_bar_bindings:
            raise ValueError("physical verification requires normalized bars")
        if self.normalized_bar_bindings != tuple(
            sorted(set(self.normalized_bar_bindings))
        ):
            raise ValueError("physical normalized-bar bindings must be unique and sorted")
        for bar_id, content_hash in self.normalized_bar_bindings:
            if not bar_id:
                raise ValueError("physical normalized-bar binding requires bar identity")
            require_sha256("normalized bar hash", content_hash)

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "normalized_owner_reference": self.normalized_owner_reference.to_canonical_dict(),
            "physical_hash": self.physical_hash,
            "checksums": [list(item) for item in self.checksums],
            "checksums_hash": self.checksums_hash,
            "normalized_bar_bindings": [list(item) for item in self.normalized_bar_bindings],
        }

def establish_physical_reproduction(
    *,
    package_path: Path,
    corpus_repository: PostgresHistoricalCorpusRepository,
) -> PhysicalSourceVerification:
    """Open physical bytes independently, then compare with the PG owner reload."""

    physical = load_verified_historical_package(package_path)
    postgres_owner = corpus_repository.load(physical.owner.reference)
    return _physical_verification_from_reloaded_packages(
        physical_package=physical,
        postgres_owner_package=postgres_owner,
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
    return PhysicalSourceVerification(
        normalized_owner_reference=physical_package.owner.reference,
        physical_hash=physical_package.physical_hash,
        checksums=physical_package.checksums,
        checksums_hash=canonical_hash(
            {"checksums": [list(item) for item in physical_package.checksums]}
        ),
        normalized_bar_bindings=tuple(
            sorted(
                (str(record.bar_id), record.content_hash)
                for partition in physical_package.owner.partitions
                for record in partition.records
                if isinstance(record, HistoricalNormalizedBar)
            )
        ),
    )


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
    ) -> None:
        self._components = components
        self._corpus = corpus

    def reproduce_run(
        self,
        *,
        run_id: ArtifactId,
        trading_calendar: TradingCalendarArtifact,
        physical_package_paths: Mapping[ValidationArtifactReference, Path] | None = None,
    ) -> HistoricalCorrectnessReproduction:
        components = self._components.list_for_run(run_id=run_id)
        features = {
            item.trading_date: item
            for item in components
            if item.component_kind is HistoricalComponentKind.FEATURE
        }
        outcomes = {
            item.trading_date: item
            for item in components
            if item.component_kind is HistoricalComponentKind.OUTCOME
        }
        if not features or set(features) != set(outcomes):
            raise ValueError("Historical correctness requires aligned Feature/Outcome owners")
        feature_results: list[FeatureReproductionResult] = []
        target_results: list[TargetReproductionResult] = []
        normalized_by_session = {
            session: _shared_normalized_owner(features[session], outcomes[session])
            for session in sorted(features)
        }
        bars_by_owner: dict[
            ValidationArtifactReference, tuple[HistoricalNormalizedBar, ...]
        ] = {}
        physical_by_owner: dict[
            ValidationArtifactReference, PhysicalSourceVerification
        ] = {}
        for normalized_reference in sorted(
            set(normalized_by_session.values()),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        ):
            package = self._corpus.load(normalized_reference)
            package.owner.verify_identity()
            bars_by_owner[normalized_reference] = tuple(
                record
                for partition in package.owner.partitions
                for record in partition.records
                if isinstance(record, HistoricalNormalizedBar)
            )
            if physical_package_paths is not None:
                path = physical_package_paths.get(normalized_reference)
                if path is not None:
                    physical_by_owner[normalized_reference] = (
                        establish_physical_reproduction(
                            package_path=path,
                            corpus_repository=self._corpus,
                        )
                    )
        for session in sorted(features):
            feature_component = features[session]
            outcome_component = outcomes[session]
            normalized_reference = normalized_by_session[session]
            bars = bars_by_owner[normalized_reference]
            active_verification = physical_by_owner.get(normalized_reference)
            decision_time = _component_decision_time(feature_component)
            persisted_by_symbol = _persisted_feature_projection(
                feature_component, bars
            )
            labels = _target_labels(outcome_component)
            if set(persisted_by_symbol) != set(labels):
                raise ValueError("Historical correctness Feature/Target symbols drifted")
            next_session = date.fromisoformat(
                str(outcome_component.payload["next_session_date"])
            )
            for symbol in sorted(persisted_by_symbol):
                feature_results.append(
                    reproduce_intraday_features(
                        session=session,
                        symbol=symbol,
                        decision_time=decision_time,
                        source_bars=bars,
                        persisted=persisted_by_symbol[symbol],
                        physical_verification=active_verification,
                    )
                )
                label = labels[symbol]
                decision_bars = _ordered_bars(
                    tuple(
                        item
                        for item in bars
                        if item.symbol == symbol
                        and item.market_date == session
                        and item.timeframe is Timeframe.MINUTE_5
                        and item.event_end <= decision_time
                    )
                )
                target_bars = _ordered_bars(
                    tuple(
                        item
                        for item in bars
                        if item.symbol == symbol
                        and item.market_date == next_session
                        and item.timeframe is Timeframe.MINUTE_5
                        and item.event_start >= label.label_interval_start
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
                            source_bars=bars,
                            persisted=None,
                            physical_verification=active_verification,
                        )
                    )
                    continue
                persisted_target = PersistedTargetObservation.create(
                    decision_reference_price=label.decision_reference_price,
                    target_price=label.checkpoint_price,
                    target_return=label.checkpoint_return,
                    decision_source_bars=(decision_bars[-1],),
                    target_source_bars=target_bars,
                    target_session=next_session,
                )
                target_results.append(
                    reproduce_t_plus_one_1030_target(
                        symbol=symbol,
                        decision_time=decision_time,
                        next_session=next_session,
                        trading_calendar=trading_calendar,
                        source_bars=bars,
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
    source_bar_ids: tuple[str, ...]
    source_bar_hashes: tuple[str, ...]
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
            source_bar_ids=ids,
            source_bar_hashes=hashes,
            source_lineage_hash=lineage,
            event_start=ordered[0].event_start,
            event_end=ordered[-1].event_end,
        )


@dataclass(frozen=True, slots=True)
class FeatureCorrectnessComparison:
    factor_id: str
    persisted_value: Decimal
    recomputed_value: Decimal
    persisted_source_bar_ids: tuple[str, ...]
    persisted_source_bar_hashes: tuple[str, ...]
    persisted_source_lineage_hash: str
    persisted_event_start: datetime
    persisted_event_end: datetime
    source_bar_ids: tuple[str, ...]
    source_bar_hashes: tuple[str, ...]
    source_lineage_hash: str
    event_start: datetime
    event_end: datetime
    decision_time: datetime
    discrepancies: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.factor_id not in _SUPPORTED_FACTORS:
            raise ValueError("Feature comparison Factor is unsupported")
        for ids, hashes, lineage in (
            (
                self.persisted_source_bar_ids,
                self.persisted_source_bar_hashes,
                self.persisted_source_lineage_hash,
            ),
            (self.source_bar_ids, self.source_bar_hashes, self.source_lineage_hash),
        ):
            if not ids or len(ids) != len(hashes):
                raise ValueError("Feature comparison lineage is incomplete")
            if lineage != _lineage_hash(ids, hashes):
                raise ValueError("Feature comparison lineage hash drifted")
        if self.event_end > self.decision_time or self.persisted_event_end > self.decision_time:
            raise ValueError("Feature comparison uses information after DecisionTime")
        expected: list[str] = []
        if self.persisted_value != self.recomputed_value:
            expected.append(f"VALUE_MISMATCH:{self.factor_id}")
        if (
            self.persisted_source_bar_ids != self.source_bar_ids
            or self.persisted_source_bar_hashes != self.source_bar_hashes
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
            "persisted_source_bar_ids": list(self.persisted_source_bar_ids),
            "persisted_source_bar_hashes": list(self.persisted_source_bar_hashes),
            "persisted_source_lineage_hash": self.persisted_source_lineage_hash,
            "persisted_event_start": self.persisted_event_start.isoformat(),
            "persisted_event_end": self.persisted_event_end.isoformat(),
            "source_bar_ids": list(self.source_bar_ids),
            "source_bar_hashes": list(self.source_bar_hashes),
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

    def __post_init__(self) -> None:
        _require_aware("Feature result DecisionTime", self.decision_time)
        if self.session != self.decision_time.astimezone(_SHANGHAI).date():
            raise ValueError("Feature result session/DecisionTime drifted")
        factor_ids = tuple(item.factor_id for item in self.comparisons)
        if factor_ids != tuple(sorted(set(factor_ids))):
            raise ValueError("Feature result comparisons must be unique and sorted")
        if any(item.decision_time != self.decision_time for item in self.comparisons):
            raise ValueError("Feature comparison DecisionTime drifted")
        derived = _correctness_status(
            discrepancies=self.discrepancies,
            physical_source_available=self.physical_source_reference is not None,
            complete=set(factor_ids) == _SUPPORTED_FACTORS,
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
    decision_reference_price: Decimal
    target_price: Decimal
    target_return: Decimal
    decision_source_ids: tuple[str, ...]
    decision_source_hashes: tuple[str, ...]
    target_source_ids: tuple[str, ...]
    target_source_hashes: tuple[str, ...]
    persisted_observation: PersistedTargetObservation | None
    status: AlphaCorrectnessStatus
    physical_source_reference: ValidationArtifactReference | None
    trading_calendar_reference: ValidationArtifactReference
    discrepancies: tuple[str, ...]

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
        if (
            len(self.decision_source_ids) != len(self.decision_source_hashes)
            or len(self.target_source_ids) != len(self.target_source_hashes)
            or not self.decision_source_ids
            or not self.target_source_ids
        ):
            raise ValueError("Target result source bindings are incomplete")
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
        if expected_discrepancies != self.discrepancies:
            raise ValueError("Target result discrepancies are not derived")
        derived = _correctness_status(
            discrepancies=expected_discrepancies,
            physical_source_available=self.physical_source_reference is not None,
            complete=self.persisted_observation is not None,
        )
        if self.status is not derived:
            raise ValueError("Target result status is not derived")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "decision_time": self.decision_time.isoformat(),
            "target_session": self.target_session.isoformat(),
            "target_event_end": self.target_event_end.isoformat(),
            "decision_reference_price": str(self.decision_reference_price),
            "target_price": str(self.target_price),
            "target_return": str(self.target_return),
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
        }


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
        feature_source_ids = {
            source_id
            for comparison in feature.comparisons
            for source_id in comparison.source_bar_ids
        }
        if feature_source_ids.intersection(target.target_source_ids):
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
            discrepancies=("DECISION_TIME_SOURCE_BARS_MISSING",),
        )
    if physical_verification is not None:
        physical_bindings = set(physical_verification.normalized_bar_bindings)
        selected_bindings = {
            (str(item.bar_id), item.content_hash) for item in selected
        }
        if not selected_bindings.issubset(physical_bindings):
            raise ValueError("Feature source bars are outside verified physical package")
    if any(item.event_end > decision_time for item in selected):
        raise ValueError("Feature source event_end exceeds DecisionTime")
    recomputed = _intraday_values(selected)
    comparisons: list[FeatureCorrectnessComparison] = []
    all_discrepancies: list[str] = []
    for observation in persisted:
        value, factor_bars = recomputed[observation.factor_id]
        ids, hashes, lineage = _source_lineage(factor_bars)
        discrepancies: list[str] = []
        if observation.value != value:
            discrepancies.append(f"VALUE_MISMATCH:{observation.factor_id}")
        if (
            observation.source_bar_ids != ids
            or observation.source_bar_hashes != hashes
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
            persisted_source_bar_ids=observation.source_bar_ids,
            persisted_source_bar_hashes=observation.source_bar_hashes,
            persisted_source_lineage_hash=observation.source_lineage_hash,
            persisted_event_start=observation.event_start,
            persisted_event_end=observation.event_end,
            source_bar_ids=ids,
            source_bar_hashes=hashes,
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
        complete={item.factor_id for item in persisted} == _SUPPORTED_FACTORS,
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
    if not decision_bars:
        raise ValueError("Decision reference bar is unavailable")
    if decision_bars[-1].event_end != decision_time:
        raise ValueError("Decision reference checkpoint is incomplete")
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
    if (
        not target_bars
        or target_bars[0].event_start != target_start
        or target_bars[-1].event_end != checkpoint
    ):
        raise ValueError("T+1 10:30 checkpoint is incomplete")
    if physical_verification is not None:
        physical_bindings = set(physical_verification.normalized_bar_bindings)
        required_bindings = {
            (str(item.bar_id), item.content_hash)
            for item in (*decision_bars, *target_bars)
        }
        if not required_bindings.issubset(physical_bindings):
            raise ValueError("Target source bars are outside verified physical package")
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
    status = _correctness_status(
        discrepancies=tuple(discrepancies),
        physical_source_available=physical_verification is not None,
        complete=persisted is not None,
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
    )


def _intraday_values(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> dict[str, tuple[Decimal, tuple[HistoricalNormalizedBar, ...]]]:
    if any(item.close is None or item.open is None for item in bars):
        raise ValueError("intraday correctness bars require complete prices")
    first, latest = bars[0], bars[-1]
    assert first.open is not None and latest.close is not None
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


def _persisted_feature_projection(
    component: HistoricalSessionComponent,
    bars: tuple[HistoricalNormalizedBar, ...],
) -> dict[str, tuple[PersistedFeatureObservation, ...]]:
    raw_features = component.payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("Historical Feature owner payload is missing")
    bars_by_id = {str(item.bar_id): item for item in bars}
    projected: dict[str, list[PersistedFeatureObservation]] = {}
    for raw_feature in raw_features:
        feature = _mapping(raw_feature, "Historical Feature computation")
        symbol = str(feature["symbol"])
        values = feature.get("values")
        if not isinstance(values, list):
            raise ValueError("Historical Feature values are missing")
        for raw_value in values:
            value = _mapping(raw_value, "Historical Feature value")
            factor_id = str(value["output_id"])
            if factor_id not in _SUPPORTED_FACTORS:
                continue
            if value.get("state") != "AVAILABLE" or value.get("value") is None:
                raise ValueError(
                    "frozen intraday Factor is unavailable in Feature owner: "
                    f"{symbol}:{factor_id}:{value.get('missing_reason_codes')}"
                )
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
        {item.factor_id for item in values} != _SUPPORTED_FACTORS
        for values in result.values()
    ):
        raise ValueError("Historical Feature owner lacks the frozen intraday family")
    return result


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


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_SCALE, rounding=ROUND_HALF_EVEN)


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
    "establish_physical_reproduction",
]
