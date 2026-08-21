"""Immutable daily Alpha projection inside the sole Continuous control plane.

The projection does not replace Dataset, Feature, Candidate, Signal, Forecast or
Strategy owners.  It freezes their exact identities plus a human-readable
per-symbol view before any future Outcome can exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.universe.operational import OperationalUniverseArtifact


DAILY_ALPHA_PREDICTION_KIND = "DAILY_ALPHA_PREDICTION_SNAPSHOT"
DAILY_ALPHA_PREDICTION_SCHEMA = "daily-alpha-prediction-snapshot/v1"
EVIDENCE_DEPENDENCY_NOT_SATISFIED = "EVIDENCE_DEPENDENCY_NOT_SATISFIED"


class DailyAlphaActivationStatus(str, Enum):
    VALIDATED_CHALLENGER_ACTIVE = "VALIDATED_CHALLENGER_ACTIVE"
    VALIDATED_CHALLENGER_INACTIVE = "VALIDATED_CHALLENGER_INACTIVE"


@dataclass(frozen=True, slots=True)
class DailyAlphaEvidenceGate:
    status: DailyAlphaActivationStatus
    correctness_reference: ValidationArtifactReference | None
    external_validation_reference: ValidationArtifactReference | None
    candidate_policy_reference: ValidationArtifactReference | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _ordered_text("gate reason_codes", self.reason_codes, required=True)
        references = (
            self.correctness_reference,
            self.external_validation_reference,
            self.candidate_policy_reference,
        )
        if self.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE:
            if any(item is None for item in references):
                raise ValueError("active daily Alpha gate requires every Evidence owner")
            if EVIDENCE_DEPENDENCY_NOT_SATISFIED in self.reason_codes:
                raise ValueError("active daily Alpha gate cannot report unmet Evidence")
        elif EVIDENCE_DEPENDENCY_NOT_SATISFIED not in self.reason_codes:
            raise ValueError("inactive daily Alpha gate requires explicit dependency reason")

    @classmethod
    def inactive(
        cls,
        *,
        correctness_reference: ValidationArtifactReference | None = None,
        external_validation_reference: ValidationArtifactReference | None = None,
        candidate_policy_reference: ValidationArtifactReference | None = None,
        reason_codes: tuple[str, ...] = (),
    ) -> DailyAlphaEvidenceGate:
        return cls(
            DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE,
            correctness_reference,
            external_validation_reference,
            candidate_policy_reference,
            tuple(sorted({EVIDENCE_DEPENDENCY_NOT_SATISFIED, *reason_codes})),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "correctness_reference": _optional_validation_reference(
                self.correctness_reference
            ),
            "external_validation_reference": _optional_validation_reference(
                self.external_validation_reference
            ),
            "candidate_policy_reference": _optional_validation_reference(
                self.candidate_policy_reference
            ),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DailyAlphaEvidenceGate:
        _fields(
            payload,
            {
                "status",
                "correctness_reference",
                "external_validation_reference",
                "candidate_policy_reference",
                "reason_codes",
            },
            "Daily Alpha Evidence gate",
        )
        return cls(
            DailyAlphaActivationStatus(str(payload["status"])),
            _validation_reference(payload["correctness_reference"]),
            _validation_reference(payload["external_validation_reference"]),
            _validation_reference(payload["candidate_policy_reference"]),
            _strings(payload["reason_codes"]),
        )


class HistoricalEvidenceReader(Protocol):
    def list_for_run(
        self, run_id: ArtifactId
    ) -> tuple[HistoricalResearchEvidence, ...]: ...


def assess_daily_alpha_evidence_gate(
    evidence: tuple[HistoricalResearchEvidence, ...],
) -> DailyAlphaEvidenceGate:
    """Admit only an explicitly supported dependency chain.

    Evidence is selected by immutable creation time and identity.  Missing,
    negative, inconclusive, or merely engineering-ready facts all remain
    inactive.  Candidate activation is deliberately explicit rather than
    inferred from one favourable comparison metric.
    """

    latest: dict[HistoricalEvidenceKind, HistoricalResearchEvidence] = {}
    for item in sorted(evidence, key=lambda value: (value.created_at, str(value.evidence_id))):
        latest[item.evidence_kind] = item
    correctness = latest.get(HistoricalEvidenceKind.ALPHA_CORRECTNESS)
    external = latest.get(HistoricalEvidenceKind.EXTERNAL_VALIDATION)
    candidate = latest.get(HistoricalEvidenceKind.CANDIDATE_POLICY)
    correctness_supported = (
        correctness is not None
        and correctness.payload.get("status") == "CORRECTNESS_SUPPORTED"
    )
    external_supported = (
        external is not None
        and external.payload.get("qualification_status") == "SUPPORTED"
    )
    candidate_active = (
        candidate is not None
        and candidate.payload.get("activation_status") == "CHALLENGER_ACTIVE"
        and candidate.payload.get("stability") == "STABLE"
    )
    references = (
        None if correctness is None else correctness.reference,
        None if external is None else external.reference,
        None if candidate is None else candidate.reference,
    )
    if correctness_supported and external_supported and candidate_active:
        return DailyAlphaEvidenceGate(
            DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE,
            *references,
            reason_codes=("EVIDENCE_DEPENDENCIES_SUPPORTED",),
        )
    reasons = []
    if not correctness_supported:
        reasons.append("CORRECTNESS_NOT_SUPPORTED")
    if not external_supported:
        reasons.append("EXTERNAL_VALIDATION_NOT_SUPPORTED")
    if not candidate_active:
        reasons.append("CANDIDATE_CHALLENGER_NOT_ACTIVE")
    return DailyAlphaEvidenceGate.inactive(
        correctness_reference=references[0],
        external_validation_reference=references[1],
        candidate_policy_reference=references[2],
        reason_codes=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class DailyAlphaSymbolProjection:
    symbol: str
    selection_status: str
    candidate_rank: int | None
    factor_score: str | None
    factor_values: tuple[tuple[str, str | None], ...]
    factor_contributions: tuple[tuple[str, str | None], ...]
    context: tuple[tuple[str, str | None], ...]
    signal_reference: RuntimeArtifactReference | None
    signal_state: str | None
    signal_score: str | None
    forecast_reference: RuntimeArtifactReference | None
    forecast_expected_return: str | None
    forecast_uncertainty: str | None
    calibration_status: str
    strategy_diagnostic_reference: RuntimeArtifactReference
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("selection_status", self.selection_status)
        require_text("calibration_status", self.calibration_status)
        if self.candidate_rank is not None and self.candidate_rank < 1:
            raise ValueError("daily Alpha Candidate rank must be positive")
        for label, values in (
            ("factor_values", self.factor_values),
            ("factor_contributions", self.factor_contributions),
            ("context", self.context),
        ):
            keys = tuple(item[0] for item in values)
            if keys != tuple(sorted(set(keys))) or any(not key.strip() for key in keys):
                raise ValueError(f"daily Alpha {label} keys must be unique and sorted")
        _ordered_text("symbol reason_codes", self.reason_codes, required=True)
        if (self.signal_reference is None) != (self.signal_state is None):
            raise ValueError("Signal reference/state must be paired")
        if self.forecast_reference is None and any(
            value is not None
            for value in (
                self.forecast_expected_return,
                self.forecast_uncertainty,
            )
        ):
            raise ValueError("Forecast values require a Forecast owner")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "selection_status": self.selection_status,
            "candidate_rank": self.candidate_rank,
            "factor_score": self.factor_score,
            "factor_values": _pairs_payload(self.factor_values),
            "factor_contributions": _pairs_payload(self.factor_contributions),
            "context": _pairs_payload(self.context),
            "signal_reference": _optional_runtime_reference(self.signal_reference),
            "signal_state": self.signal_state,
            "signal_score": self.signal_score,
            "forecast_reference": _optional_runtime_reference(self.forecast_reference),
            "forecast_expected_return": self.forecast_expected_return,
            "forecast_uncertainty": self.forecast_uncertainty,
            "calibration_status": self.calibration_status,
            "strategy_diagnostic_reference": self.strategy_diagnostic_reference.to_canonical_dict(),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DailyAlphaSymbolProjection:
        _fields(
            payload,
            {
                "symbol",
                "selection_status",
                "candidate_rank",
                "factor_score",
                "factor_values",
                "factor_contributions",
                "context",
                "signal_reference",
                "signal_state",
                "signal_score",
                "forecast_reference",
                "forecast_expected_return",
                "forecast_uncertainty",
                "calibration_status",
                "strategy_diagnostic_reference",
                "reason_codes",
            },
            "Daily Alpha symbol projection",
        )
        rank = payload["candidate_rank"]
        return cls(
            symbol=str(payload["symbol"]),
            selection_status=str(payload["selection_status"]),
            candidate_rank=None if rank is None else int(rank),
            factor_score=_optional_text(payload["factor_score"]),
            factor_values=_pairs(payload["factor_values"]),
            factor_contributions=_pairs(payload["factor_contributions"]),
            context=_pairs(payload["context"]),
            signal_reference=_runtime_reference(payload["signal_reference"]),
            signal_state=_optional_text(payload["signal_state"]),
            signal_score=_optional_text(payload["signal_score"]),
            forecast_reference=_runtime_reference(payload["forecast_reference"]),
            forecast_expected_return=_optional_text(
                payload["forecast_expected_return"]
            ),
            forecast_uncertainty=_optional_text(payload["forecast_uncertainty"]),
            calibration_status=str(payload["calibration_status"]),
            strategy_diagnostic_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["strategy_diagnostic_reference"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class DailyAlphaPredictionSnapshot:
    snapshot_id: ArtifactId
    snapshot_hash: str
    run_reference: RuntimeArtifactReference
    tick_reference: RuntimeArtifactReference
    code_reference: RuntimeArtifactReference
    configuration_references: tuple[RuntimeArtifactReference, ...]
    provider_evidence_reference: RuntimeArtifactReference
    dataset_reference: RuntimeArtifactReference
    universe_reference: RuntimeArtifactReference
    feature_references: tuple[RuntimeArtifactReference, ...]
    context_references: tuple[RuntimeArtifactReference, ...]
    candidate_reference: RuntimeArtifactReference
    signal_reference: RuntimeArtifactReference | None
    forecast_references: tuple[RuntimeArtifactReference, ...]
    strategy_diagnostic_reference: RuntimeArtifactReference
    evidence_gate: DailyAlphaEvidenceGate
    trading_date: date
    decision_time: datetime
    available_at: datetime
    symbols: tuple[DailyAlphaSymbolProjection, ...]
    reason_codes: tuple[str, ...]
    schema_version: str = DAILY_ALPHA_PREDICTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_ALPHA_PREDICTION_SCHEMA:
            raise ValueError("unsupported Daily Alpha prediction schema")
        require_sha256("snapshot_hash", self.snapshot_hash)
        require_utc_second("decision_time", self.decision_time)
        require_utc_second("available_at", self.available_at)
        if self.available_at < self.decision_time:
            raise ValueError("Daily Alpha snapshot cannot predate DecisionTime")
        for label, references in (
            ("configuration", self.configuration_references),
            ("feature", self.feature_references),
            ("context", self.context_references),
            ("forecast", self.forecast_references),
        ):
            _ordered_runtime_references(
                label,
                references,
                # A fail-closed DATA_INSUFFICIENT or MODEL_NOT_QUALIFIED tick
                # has no Forecast owner.  The immutable snapshot must still
                # expose that absence instead of fabricating a projection.
                required=label != "forecast",
            )
        symbol_keys = tuple(item.symbol for item in self.symbols)
        if symbol_keys != tuple(sorted(set(symbol_keys))):
            raise ValueError("Daily Alpha symbols must be unique and sorted")
        _ordered_text("snapshot reason_codes", self.reason_codes, required=True)
        if (
            self.evidence_gate.status
            is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE
            and EVIDENCE_DEPENDENCY_NOT_SATISFIED not in self.reason_codes
        ):
            raise ValueError("inactive Daily Alpha snapshot must expose Evidence gate")
        self.verify_identity()

    @classmethod
    def create(cls, **values: Any) -> DailyAlphaPredictionSnapshot:
        normalized = dict(values)
        normalized["configuration_references"] = _sort_runtime_references(
            values["configuration_references"]
        )
        normalized["feature_references"] = _sort_runtime_references(
            values["feature_references"]
        )
        normalized["context_references"] = _sort_runtime_references(
            values["context_references"]
        )
        normalized["forecast_references"] = _sort_runtime_references(
            values["forecast_references"]
        )
        normalized["symbols"] = tuple(
            sorted(values["symbols"], key=lambda item: item.symbol)
        )
        normalized["reason_codes"] = tuple(
            sorted(
                {
                    "FREE_DATA_RESEARCH_ONLY",
                    "FORMAL_OOS_FALSE",
                    "NO_TRADING_AUTHORITY",
                    "PRODUCTION_QUALIFIED_FALSE",
                    *values["reason_codes"],
                    *values["evidence_gate"].reason_codes,
                }
            )
        )
        normalized.setdefault("schema_version", DAILY_ALPHA_PREDICTION_SCHEMA)
        digest = canonical_hash(_snapshot_payload(**normalized))
        return cls(
            snapshot_id=ArtifactId(f"daily-alpha-prediction:{digest[7:]}"),
            snapshot_hash=digest,
            **normalized,
        )

    @property
    def reference(self) -> RuntimeArtifactReference:
        return RuntimeArtifactReference(
            DAILY_ALPHA_PREDICTION_KIND, self.snapshot_id, self.snapshot_hash
        )

    def verify_identity(self) -> None:
        if canonical_hash(self.identity_payload()) != self.snapshot_hash:
            raise ValueError("Daily Alpha snapshot hash mismatch")
        if self.snapshot_id != ArtifactId(
            f"daily-alpha-prediction:{self.snapshot_hash[7:]}"
        ):
            raise ValueError("Daily Alpha snapshot identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _snapshot_payload(
            run_reference=self.run_reference,
            tick_reference=self.tick_reference,
            code_reference=self.code_reference,
            configuration_references=self.configuration_references,
            provider_evidence_reference=self.provider_evidence_reference,
            dataset_reference=self.dataset_reference,
            universe_reference=self.universe_reference,
            feature_references=self.feature_references,
            context_references=self.context_references,
            candidate_reference=self.candidate_reference,
            signal_reference=self.signal_reference,
            forecast_references=self.forecast_references,
            strategy_diagnostic_reference=self.strategy_diagnostic_reference,
            evidence_gate=self.evidence_gate,
            trading_date=self.trading_date,
            decision_time=self.decision_time,
            available_at=self.available_at,
            symbols=self.symbols,
            reason_codes=self.reason_codes,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": str(self.snapshot_id),
            "snapshot_hash": self.snapshot_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DailyAlphaPredictionSnapshot:
        expected = {
            "snapshot_id",
            "snapshot_hash",
            "schema_version",
            "run_reference",
            "tick_reference",
            "code_reference",
            "configuration_references",
            "provider_evidence_reference",
            "dataset_reference",
            "universe_reference",
            "feature_references",
            "context_references",
            "candidate_reference",
            "signal_reference",
            "forecast_references",
            "strategy_diagnostic_reference",
            "evidence_gate",
            "trading_date",
            "decision_time",
            "available_at",
            "symbols",
            "reason_codes",
        }
        _fields(payload, expected, "Daily Alpha prediction snapshot")
        return cls(
            snapshot_id=ArtifactId(str(payload["snapshot_id"])),
            snapshot_hash=str(payload["snapshot_hash"]),
            run_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["run_reference"])
            ),
            tick_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["tick_reference"])
            ),
            code_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["code_reference"])
            ),
            configuration_references=_runtime_references(
                payload["configuration_references"]
            ),
            provider_evidence_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["provider_evidence_reference"])
            ),
            dataset_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["dataset_reference"])
            ),
            universe_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["universe_reference"])
            ),
            feature_references=_runtime_references(payload["feature_references"]),
            context_references=_runtime_references(payload["context_references"]),
            candidate_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["candidate_reference"])
            ),
            signal_reference=_runtime_reference(payload["signal_reference"]),
            forecast_references=_runtime_references(payload["forecast_references"]),
            strategy_diagnostic_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["strategy_diagnostic_reference"])
            ),
            evidence_gate=DailyAlphaEvidenceGate.from_canonical_dict(
                _mapping(payload["evidence_gate"])
            ),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            symbols=tuple(
                DailyAlphaSymbolProjection.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["symbols"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
            schema_version=str(payload["schema_version"]),
        )


class DailyAlphaOwnerResolver(Protocol):
    def verify_snapshot_sources(self, snapshot: DailyAlphaPredictionSnapshot) -> None: ...


class DailyAlphaPredictionAuthority(Protocol):
    def put(
        self,
        snapshot: DailyAlphaPredictionSnapshot,
        *,
        universe: OperationalUniverseArtifact | None = None,
    ) -> DailyAlphaPredictionSnapshot: ...


class PostgresDailyAlphaPredictionAuthority:
    """Typed facade over the existing PostgreSQL Research Evidence authority."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        resolver: DailyAlphaOwnerResolver,
    ) -> None:
        self._factory = factory
        self._repository = PostgresResearchValidationRepository(factory)
        self._resolver = resolver

    def put(
        self,
        snapshot: DailyAlphaPredictionSnapshot,
        *,
        universe: OperationalUniverseArtifact | None = None,
    ) -> DailyAlphaPredictionSnapshot:
        snapshot.verify_identity()
        if universe is not None:
            universe.verify_identity()
            if (
                str(universe.universe_id)
                != str(snapshot.universe_reference.artifact_id)
                or universe.content_hash
                != snapshot.universe_reference.content_hash
            ):
                raise ValueError("Daily Alpha snapshot does not bind supplied Universe")
            self._repository.record(
                artifact_id=ArtifactId(str(universe.universe_id)),
                artifact_hash=universe.content_hash,
                artifact_kind="OPERATIONAL_UNIVERSE",
                evidence_authority="ENGINEERING_ONLY",
                payload=universe.semantic_payload(),
                created_at=universe.available_at,
            )
        self._resolver.verify_snapshot_sources(snapshot)
        self._repository.record(
            artifact_id=snapshot.snapshot_id,
            artifact_hash=snapshot.snapshot_hash,
            artifact_kind=DAILY_ALPHA_PREDICTION_KIND,
            evidence_authority="ENGINEERING_ONLY",
            payload=snapshot.identity_payload(),
            created_at=snapshot.available_at,
        )
        return self.get(snapshot.snapshot_id)

    def get(self, snapshot_id: ArtifactId) -> DailyAlphaPredictionSnapshot:
        reference = self._reference(snapshot_id)
        payload = self._repository.get_artifact_payload(reference)
        snapshot = DailyAlphaPredictionSnapshot.from_canonical_dict(
            {
                "snapshot_id": str(snapshot_id),
                "snapshot_hash": reference.content_hash,
                **payload,
            }
        )
        self._resolver.verify_snapshot_sources(snapshot)
        return snapshot

    def _reference(self, snapshot_id: ArtifactId) -> ValidationArtifactReference:
        # Resolve the hash from the immutable generic owner without trusting a
        # caller-supplied value.  The repository then verifies kind and payload.
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT artifact_hash, artifact_kind FROM research_validation_artifact "
                "WHERE artifact_id = %s",
                (str(snapshot_id),),
            ).fetchone()
        if row is None or str(row[1]) != DAILY_ALPHA_PREDICTION_KIND:
            raise KeyError(str(snapshot_id))
        return ValidationArtifactReference(
            DAILY_ALPHA_PREDICTION_KIND, snapshot_id, str(row[0])
        )


class PostgresDailyAlphaEvidenceGateResolver:
    """Resolve the latest immutable Phase-II dependency chain from PostgreSQL."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._evidence = PostgresHistoricalEvidenceRepository(factory)

    def assess(self) -> DailyAlphaEvidenceGate:
        kinds = (
            HistoricalEvidenceKind.ALPHA_CORRECTNESS,
            HistoricalEvidenceKind.EXTERNAL_VALIDATION,
            HistoricalEvidenceKind.CANDIDATE_POLICY,
        )
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (evidence_kind) evidence_id
                FROM historical_research_evidence
                WHERE evidence_kind = ANY(%s)
                ORDER BY evidence_kind, created_at DESC, evidence_id DESC
                """,
                ([item.value for item in kinds],),
            ).fetchall()
        return assess_daily_alpha_evidence_gate(
            tuple(self._evidence.get(ArtifactId(str(row[0]))) for row in rows)
        )


def _snapshot_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "run_reference": values["run_reference"].to_canonical_dict(),
        "tick_reference": values["tick_reference"].to_canonical_dict(),
        "code_reference": values["code_reference"].to_canonical_dict(),
        "configuration_references": [
            item.to_canonical_dict() for item in values["configuration_references"]
        ],
        "provider_evidence_reference": values[
            "provider_evidence_reference"
        ].to_canonical_dict(),
        "dataset_reference": values["dataset_reference"].to_canonical_dict(),
        "universe_reference": values["universe_reference"].to_canonical_dict(),
        "feature_references": [
            item.to_canonical_dict() for item in values["feature_references"]
        ],
        "context_references": [
            item.to_canonical_dict() for item in values["context_references"]
        ],
        "candidate_reference": values["candidate_reference"].to_canonical_dict(),
        "signal_reference": _optional_runtime_reference(values["signal_reference"]),
        "forecast_references": [
            item.to_canonical_dict() for item in values["forecast_references"]
        ],
        "strategy_diagnostic_reference": values[
            "strategy_diagnostic_reference"
        ].to_canonical_dict(),
        "evidence_gate": values["evidence_gate"].to_canonical_dict(),
        "trading_date": values["trading_date"].isoformat(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "available_at": canonical_datetime(values["available_at"]),
        "symbols": [item.to_canonical_dict() for item in values["symbols"]],
        "reason_codes": list(values["reason_codes"]),
    }


def _sort_runtime_references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _ordered_runtime_references(
    label: str,
    references: tuple[RuntimeArtifactReference, ...],
    *,
    required: bool,
) -> None:
    if required and not references:
        raise ValueError(f"Daily Alpha {label} references are required")
    if references != _sort_runtime_references(references):
        raise ValueError(f"Daily Alpha {label} references must be unique and sorted")


def _ordered_text(label: str, values: tuple[str, ...], *, required: bool) -> None:
    if required and not values:
        raise ValueError(f"{label} are required")
    if values != tuple(sorted(set(values))) or any(not item.strip() for item in values):
        raise ValueError(f"{label} must be unique, non-empty, and sorted")


def _optional_validation_reference(
    value: ValidationArtifactReference | None,
) -> dict[str, str] | None:
    return None if value is None else value.to_canonical_dict()


def _validation_reference(value: object) -> ValidationArtifactReference | None:
    if value is None:
        return None
    return ValidationArtifactReference.from_canonical_dict(_mapping(value))


def _optional_runtime_reference(
    value: RuntimeArtifactReference | None,
) -> dict[str, str] | None:
    return None if value is None else value.to_canonical_dict()


def _runtime_reference(value: object) -> RuntimeArtifactReference | None:
    if value is None:
        return None
    return RuntimeArtifactReference.from_canonical_dict(_mapping(value))


def _runtime_references(value: object) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        RuntimeArtifactReference.from_canonical_dict(_mapping(item))
        for item in _sequence(value)
    )


def _pairs_payload(values: tuple[tuple[str, str | None], ...]) -> list[dict[str, str | None]]:
    return [{"name": key, "value": value} for key, value in values]


def _pairs(value: object) -> tuple[tuple[str, str | None], ...]:
    pairs = []
    for item in _sequence(value):
        payload = _mapping(item)
        _fields(payload, {"name", "value"}, "Daily Alpha named value")
        pairs.append((str(payload["name"]), _optional_text(payload["value"])))
    return tuple(pairs)


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Daily Alpha value must be an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Daily Alpha value must be an array")
    return tuple(value)


def _strings(value: object) -> tuple[str, ...]:
    values = _sequence(value)
    if any(not isinstance(item, str) for item in values):
        raise ValueError("Daily Alpha value must be a string array")
    return tuple(str(item) for item in values)


def _fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


__all__ = [
    "DAILY_ALPHA_PREDICTION_KIND",
    "DailyAlphaActivationStatus",
    "DailyAlphaEvidenceGate",
    "DailyAlphaOwnerResolver",
    "DailyAlphaPredictionAuthority",
    "DailyAlphaPredictionSnapshot",
    "DailyAlphaSymbolProjection",
    "EVIDENCE_DEPENDENCY_NOT_SATISFIED",
    "PostgresDailyAlphaPredictionAuthority",
    "assess_daily_alpha_evidence_gate",
]
