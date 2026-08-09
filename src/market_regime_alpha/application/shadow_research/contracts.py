"""Immutable Shadow Session and frozen decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.research_summary import (
    ResearchDailySummary,
)
from market_regime_alpha.application.state_system.runtime import StateResearchStage
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


class ShadowSessionStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    FROZEN = "FROZEN"
    OUTCOME_PENDING = "OUTCOME_PENDING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"


class ShadowOutcomeStatus(str, Enum):
    NOT_EXPECTED = "NOT_EXPECTED"
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True, slots=True)
class ShadowSessionCommand:
    session_id: ArtifactId
    session_hash: str
    idempotency_key: str
    run_id: ArtifactId
    trading_date: date
    runtime_mode: RuntimeAuthorityMode
    scheduled_at: datetime
    operator_observation: str | None
    schema_version: str = "shadow-session-command/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "shadow-session-command/v1":
            raise ValueError("unsupported Shadow Session command schema")
        require_sha256("session_hash", self.session_hash)
        require_text("idempotency_key", self.idempotency_key)
        _aware("scheduled_at", self.scheduled_at)
        if self.runtime_mode is not RuntimeAuthorityMode.SHADOW:
            raise ValueError("Shadow Session requires SHADOW Runtime")
        if self.operator_observation is not None:
            require_text("operator_observation", self.operator_observation)
        if canonical_hash(self.semantic_payload()) != self.session_hash:
            raise ValueError("Shadow Session command hash mismatch")
        if self.session_id != _content_id("shadow-session", self.session_hash):
            raise ValueError("Shadow Session identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ShadowSessionCommand:
        digest = canonical_hash(_session_payload(**values))
        return cls(
            session_id=_content_id("shadow-session", digest),
            session_hash=digest,
            **values,
        )

    @property
    def initial_status(self) -> ShadowSessionStatus:
        return ShadowSessionStatus.SCHEDULED

    @property
    def no_order(self) -> bool:
        return True

    @property
    def no_fill(self) -> bool:
        return True

    @property
    def no_broker(self) -> bool:
        return True

    @property
    def no_position_mutation(self) -> bool:
        return True

    def semantic_payload(self) -> dict[str, Any]:
        return _session_payload(
            idempotency_key=self.idempotency_key,
            run_id=self.run_id,
            trading_date=self.trading_date,
            runtime_mode=self.runtime_mode,
            scheduled_at=self.scheduled_at,
            operator_observation=self.operator_observation,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "session_hash": self.session_hash,
            **self.semantic_payload(),
            "safety": _safety(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ShadowSessionCommand:
        if _mapping(payload.get("safety")) != _safety():
            raise ValueError("Shadow Session safety declaration mismatch")
        command = cls.create(
            idempotency_key=_text(payload["idempotency_key"]),
            run_id=ArtifactId(_text(payload["run_id"])),
            trading_date=date.fromisoformat(_text(payload["trading_date"])),
            runtime_mode=RuntimeAuthorityMode(_text(payload["runtime_mode"])),
            scheduled_at=_instant(payload["scheduled_at"]),
            operator_observation=_optional_text(payload.get("operator_observation")),
        )
        if (
            str(command.session_id) != payload.get("session_id")
            or command.session_hash != payload.get("session_hash")
            or payload.get("schema_version") != command.schema_version
        ):
            raise ValueError("Shadow Session command identity mismatch")
        return command


@dataclass(frozen=True, slots=True)
class ShadowDecision:
    decision_id: ArtifactId
    decision_hash: str
    session_id: ArtifactId
    run_id: ArtifactId
    tick_id: ArtifactId
    summary: RuntimeArtifactReference
    trading_date: date
    decision_time: datetime
    decision_frozen_at: datetime
    source_manifest: RuntimeArtifactReference
    dataset: RuntimeArtifactReference
    feature_bundle: RuntimeArtifactReference
    state_system_receipt: RuntimeArtifactReference
    controlled_operation: RuntimeArtifactReference
    market_state: RuntimeArtifactReference
    etf_state: RuntimeArtifactReference
    theme_state: RuntimeArtifactReference
    capital_state: RuntimeArtifactReference
    dynamic_pool: RuntimeArtifactReference | None
    candidate_set: RuntimeArtifactReference | None
    signal: RuntimeArtifactReference | None
    forecast: RuntimeArtifactReference | None
    model_selection_receipts: tuple[RuntimeArtifactReference, ...]
    configuration_references: tuple[RuntimeArtifactReference, ...]
    provider_source_references: tuple[RuntimeArtifactReference, ...]
    summary_outcome: str
    data_eligibility: DataEligibility
    evidence_ceiling: PITSourceEvidenceLevel
    reason_codes: tuple[str, ...]
    schema_version: str = "shadow-decision/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "shadow-decision/v1":
            raise ValueError("unsupported Shadow Decision schema")
        require_sha256("decision_hash", self.decision_hash)
        _aware("decision_time", self.decision_time)
        _aware("decision_frozen_at", self.decision_frozen_at)
        if self.decision_frozen_at < self.decision_time:
            raise ValueError("Shadow Decision cannot freeze before DecisionTime")
        for references in (
            self.model_selection_receipts,
            self.configuration_references,
            self.provider_source_references,
        ):
            if references != _sorted_references(references):
                raise ValueError("Shadow Decision references must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Shadow Decision reasons must be unique and sorted")
        if canonical_hash(self.semantic_payload()) != self.decision_hash:
            raise ValueError("Shadow Decision hash mismatch")
        if self.decision_id != _content_id("shadow-decision", self.decision_hash):
            raise ValueError("Shadow Decision identity mismatch")

    @classmethod
    def from_summary(
        cls,
        *,
        session: ShadowSessionCommand,
        summary: ResearchDailySummary,
        controlled_operation: RuntimeArtifactReference,
        decision_frozen_at: datetime,
    ) -> ShadowDecision:
        if summary.runtime_mode is not RuntimeAuthorityMode.SHADOW:
            raise ValueError("Shadow Decision requires a SHADOW Summary")
        if (
            session.run_id != summary.run_id
            or session.trading_date != summary.trading_date
        ):
            raise ValueError("Shadow Session and Summary lineage mismatch")
        if decision_frozen_at < summary.created_at:
            raise ValueError("Shadow Decision cannot freeze before Summary creation")
        stages = {item.stage: item for item in summary.stages}
        state_receipt = summary.state_system_receipt
        if state_receipt is None:
            raise ValueError("Shadow Decision requires State owner Receipt")
        required_state_outputs = {
            stage: stages[stage].output_reference
            for stage in (
                StateResearchStage.MARKET_REGIME,
                StateResearchStage.ETF_ROTATION,
                StateResearchStage.THEME_ROTATION,
                StateResearchStage.CAPITAL_STATE,
            )
        }
        if any(item is None for item in required_state_outputs.values()):
            raise ValueError("Shadow Decision requires every State owner Artifact")
        market_state = required_state_outputs[StateResearchStage.MARKET_REGIME]
        etf_state = required_state_outputs[StateResearchStage.ETF_ROTATION]
        theme_state = required_state_outputs[StateResearchStage.THEME_ROTATION]
        capital_state = required_state_outputs[StateResearchStage.CAPITAL_STATE]
        assert market_state is not None
        assert etf_state is not None
        assert theme_state is not None
        assert capital_state is not None
        values: dict[str, Any] = {
            "session_id": session.session_id,
            "run_id": summary.run_id,
            "tick_id": summary.tick_id,
            "summary": RuntimeArtifactReference(
                "RESEARCH_DAILY_SUMMARY",
                summary.summary_id,
                summary.content_hash,
            ),
            "trading_date": summary.trading_date,
            "decision_time": summary.decision_time,
            "decision_frozen_at": decision_frozen_at,
            "source_manifest": summary.source_manifest,
            "dataset": summary.dataset,
            "feature_bundle": summary.feature_bundle,
            "state_system_receipt": state_receipt,
            "controlled_operation": controlled_operation,
            "market_state": market_state,
            "etf_state": etf_state,
            "theme_state": theme_state,
            "capital_state": capital_state,
            "dynamic_pool": stages[StateResearchStage.DYNAMIC_POOL].output_reference,
            "candidate_set": summary.candidate_set,
            "signal": stages[StateResearchStage.SIGNAL].output_reference,
            "forecast": stages[StateResearchStage.FORECAST].output_reference,
            "model_selection_receipts": _sorted_references(
                summary.model_selection_receipts
            ),
            "configuration_references": _sorted_references(
                summary.configuration_references
            ),
            "provider_source_references": _sorted_references(
                summary.provider_source_references
            ),
            "summary_outcome": summary.outcome.value,
            "data_eligibility": summary.data_eligibility,
            "evidence_ceiling": summary.evidence_ceiling,
            "reason_codes": tuple(
                sorted({*summary.reason_codes, "SHADOW_ENGINEERING_ONLY"})
            ),
        }
        digest = canonical_hash(_decision_payload(**values))
        return cls(
            decision_id=_content_id("shadow-decision", digest),
            decision_hash=digest,
            **values,
        )

    @property
    def no_order(self) -> bool:
        return True

    @property
    def no_fill(self) -> bool:
        return True

    @property
    def no_broker(self) -> bool:
        return True

    @property
    def no_position_mutation(self) -> bool:
        return True

    def semantic_payload(self) -> dict[str, Any]:
        return _decision_payload(
            session_id=self.session_id,
            run_id=self.run_id,
            tick_id=self.tick_id,
            summary=self.summary,
            trading_date=self.trading_date,
            decision_time=self.decision_time,
            decision_frozen_at=self.decision_frozen_at,
            source_manifest=self.source_manifest,
            dataset=self.dataset,
            feature_bundle=self.feature_bundle,
            state_system_receipt=self.state_system_receipt,
            controlled_operation=self.controlled_operation,
            market_state=self.market_state,
            etf_state=self.etf_state,
            theme_state=self.theme_state,
            capital_state=self.capital_state,
            dynamic_pool=self.dynamic_pool,
            candidate_set=self.candidate_set,
            signal=self.signal,
            forecast=self.forecast,
            model_selection_receipts=self.model_selection_receipts,
            configuration_references=self.configuration_references,
            provider_source_references=self.provider_source_references,
            summary_outcome=self.summary_outcome,
            data_eligibility=self.data_eligibility,
            evidence_ceiling=self.evidence_ceiling,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.semantic_payload(),
            "safety": _safety(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ShadowDecision:
        if _mapping(payload.get("safety")) != _safety():
            raise ValueError("Shadow Decision safety declaration mismatch")
        values: dict[str, Any] = {
            "session_id": ArtifactId(_text(payload["session_id"])),
            "run_id": ArtifactId(_text(payload["run_id"])),
            "tick_id": ArtifactId(_text(payload["tick_id"])),
            "summary": _reference(payload["summary"]),
            "trading_date": date.fromisoformat(_text(payload["trading_date"])),
            "decision_time": _instant(payload["decision_time"]),
            "decision_frozen_at": _instant(payload["decision_frozen_at"]),
            "source_manifest": _reference(payload["source_manifest"]),
            "dataset": _reference(payload["dataset"]),
            "feature_bundle": _reference(payload["feature_bundle"]),
            "state_system_receipt": _reference(payload["state_system_receipt"]),
            "controlled_operation": _reference(payload["controlled_operation"]),
            "market_state": _reference(payload["market_state"]),
            "etf_state": _reference(payload["etf_state"]),
            "theme_state": _reference(payload["theme_state"]),
            "capital_state": _reference(payload["capital_state"]),
            "dynamic_pool": _optional_reference(payload.get("dynamic_pool")),
            "candidate_set": _optional_reference(payload.get("candidate_set")),
            "signal": _optional_reference(payload.get("signal")),
            "forecast": _optional_reference(payload.get("forecast")),
            "model_selection_receipts": _references(
                payload["model_selection_receipts"]
            ),
            "configuration_references": _references(
                payload["configuration_references"]
            ),
            "provider_source_references": _references(
                payload["provider_source_references"]
            ),
            "summary_outcome": _text(payload["summary_outcome"]),
            "data_eligibility": DataEligibility(_text(payload["data_eligibility"])),
            "evidence_ceiling": PITSourceEvidenceLevel(
                _text(payload["evidence_ceiling"])
            ),
            "reason_codes": _strings(payload["reason_codes"]),
        }
        decision = cls(
            decision_id=ArtifactId(_text(payload["decision_id"])),
            decision_hash=_text(payload["decision_hash"]),
            **values,
        )
        if payload.get("schema_version") != decision.schema_version:
            raise ValueError("Shadow Decision schema mismatch")
        return decision


@dataclass(frozen=True, slots=True)
class ShadowSessionSnapshot:
    command: ShadowSessionCommand
    status: ShadowSessionStatus
    outcome_status: ShadowOutcomeStatus
    decision_id: ArtifactId | None
    version: int
    reason_codes: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


def _session_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "shadow-session-command/v1",
        "idempotency_key": values["idempotency_key"],
        "run_id": str(values["run_id"]),
        "trading_date": values["trading_date"].isoformat(),
        "runtime_mode": values["runtime_mode"].value,
        "scheduled_at": canonical_datetime(values["scheduled_at"]),
        "operator_observation": values["operator_observation"],
    }


def _decision_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "shadow-decision/v1",
        "session_id": str(values["session_id"]),
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "summary": values["summary"].to_canonical_dict(),
        "trading_date": values["trading_date"].isoformat(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "decision_frozen_at": canonical_datetime(values["decision_frozen_at"]),
        "source_manifest": values["source_manifest"].to_canonical_dict(),
        "dataset": values["dataset"].to_canonical_dict(),
        "feature_bundle": values["feature_bundle"].to_canonical_dict(),
        "state_system_receipt": values["state_system_receipt"].to_canonical_dict(),
        "controlled_operation": values["controlled_operation"].to_canonical_dict(),
        "market_state": values["market_state"].to_canonical_dict(),
        "etf_state": values["etf_state"].to_canonical_dict(),
        "theme_state": values["theme_state"].to_canonical_dict(),
        "capital_state": values["capital_state"].to_canonical_dict(),
        "dynamic_pool": _optional_reference_dict(values["dynamic_pool"]),
        "candidate_set": _optional_reference_dict(values["candidate_set"]),
        "signal": _optional_reference_dict(values["signal"]),
        "forecast": _optional_reference_dict(values["forecast"]),
        "model_selection_receipts": [
            item.to_canonical_dict() for item in values["model_selection_receipts"]
        ],
        "configuration_references": [
            item.to_canonical_dict() for item in values["configuration_references"]
        ],
        "provider_source_references": [
            item.to_canonical_dict() for item in values["provider_source_references"]
        ],
        "summary_outcome": values["summary_outcome"],
        "data_eligibility": values["data_eligibility"].value,
        "evidence_ceiling": values["evidence_ceiling"].value,
        "reason_codes": list(values["reason_codes"]),
    }


def _safety() -> dict[str, bool]:
    return {
        "no_order": True,
        "no_fill": True,
        "no_broker": True,
        "no_position_mutation": True,
        "engineering_evidence_only": True,
    }


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _sorted_references(
    references: tuple[RuntimeArtifactReference, ...]
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


def _optional_reference_dict(
    reference: RuntimeArtifactReference | None,
) -> dict[str, str] | None:
    return None if reference is None else reference.to_canonical_dict()


def _reference(value: object) -> RuntimeArtifactReference:
    return RuntimeArtifactReference.from_canonical_dict(_mapping(value))


def _optional_reference(value: object) -> RuntimeArtifactReference | None:
    return None if value is None else _reference(value)


def _references(value: object) -> tuple[RuntimeArtifactReference, ...]:
    if not isinstance(value, list):
        raise ValueError("references must be an array")
    return tuple(_reference(item) for item in value)


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _aware("timestamp", parsed)
    return parsed


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("value must be non-empty text")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("value must be an object")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("value must be a string array")
    return tuple(value)


__all__ = [
    "ShadowDecision",
    "ShadowOutcomeStatus",
    "ShadowSessionCommand",
    "ShadowSessionSnapshot",
    "ShadowSessionStatus",
]
