"""Deterministic, research-only Signal model with explicit versioned inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.contracts import (
    ConfirmationState,
    SignalFamily,
    SignalSnapshot,
    SignalState,
)


SIGNAL_MODEL_CONFIG_SCHEMA = "signal-model-config-v1"
SIGNAL_OBSERVATION_SCHEMA = "signal-observation-v1"
SIGNAL_RUN_SCHEMA = "signal-run-artifact-v1"


def _require_text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_finite(label: str, value: float) -> None:
    if isinstance(value, bool) or not isfinite(value):
        raise ValueError(f"{label} must be finite and non-boolean")


@dataclass(frozen=True, slots=True)
class SignalModelConfig:
    """All V1 Signal choices; no implicit operating or production defaults."""

    profile_id: str
    model_id: ModelId
    model_version: str
    decision_profile_id: str
    decision_time_local: str
    timezone_name: str
    market_scope: str
    allowed_side: str
    signal_family: SignalFamily
    price_action_min_return: float
    volume_confirmation_min_ratio: float
    trend_confirmation_min_return: float
    vwap_min_relative_return: float
    overheat_max_return: float
    minimum_confirmations: int
    scoring_method: str
    schema_version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("profile_id", self.profile_id),
            ("model_version", self.model_version),
            ("decision_profile_id", self.decision_profile_id),
            ("decision_time_local", self.decision_time_local),
            ("timezone_name", self.timezone_name),
            ("market_scope", self.market_scope),
            ("allowed_side", self.allowed_side),
            ("scoring_method", self.scoring_method),
            ("schema_version", self.schema_version),
        ):
            _require_text(label, value)
        if self.schema_version != SIGNAL_MODEL_CONFIG_SCHEMA:
            raise ValueError("unsupported Signal model configuration schema")
        if self.market_scope != "A_SHARE" or self.allowed_side != "LONG_ONLY":
            raise ValueError("Signal V1 is restricted to A_SHARE LONG_ONLY")
        try:
            datetime.strptime(self.decision_time_local, "%H:%M")
            ZoneInfo(self.timezone_name)
        except (ValueError, KeyError) as exc:
            raise ValueError("invalid versioned Signal decision profile") from exc
        for label, numeric_value in (
            ("price_action_min_return", self.price_action_min_return),
            ("volume_confirmation_min_ratio", self.volume_confirmation_min_ratio),
            ("trend_confirmation_min_return", self.trend_confirmation_min_return),
            ("vwap_min_relative_return", self.vwap_min_relative_return),
            ("overheat_max_return", self.overheat_max_return),
        ):
            _require_finite(label, numeric_value)
        if self.volume_confirmation_min_ratio < 0.0:
            raise ValueError("volume confirmation ratio cannot be negative")
        if self.overheat_max_return <= 0.0:
            raise ValueError("overheat threshold must be positive")
        if not 1 <= self.minimum_confirmations <= 4:
            raise ValueError("minimum_confirmations must be within [1, 4]")
        if self.scoring_method != "EQUAL_CONFIRMATION_MEAN_V1":
            raise ValueError("unsupported Signal scoring method")

    @property
    def configuration_hash(self) -> str:
        return canonical_hash(self.to_canonical_dict())

    @property
    def configuration_id(self) -> ArtifactId:
        digest = self.configuration_hash.split(":", 1)[1]
        return ArtifactId(f"signal-config-{digest[:24]}")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "decision_profile_id": self.decision_profile_id,
            "decision_time_local": self.decision_time_local,
            "timezone_name": self.timezone_name,
            "market_scope": self.market_scope,
            "allowed_side": self.allowed_side,
            "signal_family": self.signal_family.value,
            "price_action_min_return": self.price_action_min_return,
            "volume_confirmation_min_ratio": self.volume_confirmation_min_ratio,
            "trend_confirmation_min_return": self.trend_confirmation_min_return,
            "vwap_min_relative_return": self.vwap_min_relative_return,
            "overheat_max_return": self.overheat_max_return,
            "minimum_confirmations": self.minimum_confirmations,
            "scoring_method": self.scoring_method,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> SignalModelConfig:
        expected = {
            "schema_version",
            "profile_id",
            "model_id",
            "model_version",
            "decision_profile_id",
            "decision_time_local",
            "timezone_name",
            "market_scope",
            "allowed_side",
            "signal_family",
            "price_action_min_return",
            "volume_confirmation_min_ratio",
            "trend_confirmation_min_return",
            "vwap_min_relative_return",
            "overheat_max_return",
            "minimum_confirmations",
            "scoring_method",
        }
        if set(payload) != expected:
            raise ValueError("SignalModelConfig fields mismatch")
        return cls(
            profile_id=str(payload["profile_id"]),
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            decision_profile_id=str(payload["decision_profile_id"]),
            decision_time_local=str(payload["decision_time_local"]),
            timezone_name=str(payload["timezone_name"]),
            market_scope=str(payload["market_scope"]),
            allowed_side=str(payload["allowed_side"]),
            signal_family=SignalFamily(str(payload["signal_family"])),
            price_action_min_return=float(payload["price_action_min_return"]),
            volume_confirmation_min_ratio=float(
                payload["volume_confirmation_min_ratio"]
            ),
            trend_confirmation_min_return=float(
                payload["trend_confirmation_min_return"]
            ),
            vwap_min_relative_return=float(payload["vwap_min_relative_return"]),
            overheat_max_return=float(payload["overheat_max_return"]),
            minimum_confirmations=int(payload["minimum_confirmations"]),
            scoring_method=str(payload["scoring_method"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class SignalObservation:
    symbol: str
    source_artifact_id: ArtifactId
    source_content_hash: str
    availability_time: AvailabilityTime
    price_action_return: float | None
    volume_ratio: float | None
    trend_return: float | None
    price_vs_vwap_return: float | None
    overheat_return: float | None
    reason_codes: tuple[str, ...]
    schema_version: str

    def __post_init__(self) -> None:
        _require_text("symbol", self.symbol)
        require_sha256("source_content_hash", self.source_content_hash)
        if self.schema_version != SIGNAL_OBSERVATION_SCHEMA:
            raise ValueError("unsupported Signal observation schema")
        values = (
            self.price_action_return,
            self.volume_ratio,
            self.trend_return,
            self.price_vs_vwap_return,
            self.overheat_return,
        )
        for value in values:
            if value is not None:
                _require_finite("Signal observation metric", value)
        if self.volume_ratio is not None and self.volume_ratio < 0.0:
            raise ValueError("volume_ratio cannot be negative")
        if any(value is None for value in values) and not self.reason_codes:
            raise ValueError("missing Signal metrics require reason_codes")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("Signal observation reason_codes must be unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "source_artifact_id": str(self.source_artifact_id),
            "source_content_hash": self.source_content_hash,
            "availability_time": self.availability_time.isoformat(),
            "price_action_return": self.price_action_return,
            "volume_ratio": self.volume_ratio,
            "trend_return": self.trend_return,
            "price_vs_vwap_return": self.price_vs_vwap_return,
            "overheat_return": self.overheat_return,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> SignalObservation:
        expected = {
            "schema_version",
            "symbol",
            "source_artifact_id",
            "source_content_hash",
            "availability_time",
            "price_action_return",
            "volume_ratio",
            "trend_return",
            "price_vs_vwap_return",
            "overheat_return",
            "reason_codes",
        }
        if set(payload) != expected or not isinstance(payload["reason_codes"], list):
            raise ValueError("SignalObservation fields mismatch")
        optional_values = {
            name: (
                float(payload[name]) if payload[name] is not None else None
            )
            for name in (
                "price_action_return",
                "volume_ratio",
                "trend_return",
                "price_vs_vwap_return",
                "overheat_return",
            )
        }
        return cls(
            symbol=str(payload["symbol"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_content_hash=str(payload["source_content_hash"]),
            availability_time=AvailabilityTime(
                datetime.fromisoformat(str(payload["availability_time"]))
            ),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
            schema_version=str(payload["schema_version"]),
            **optional_values,
        )


@dataclass(frozen=True, slots=True)
class SignalRunArtifact:
    envelope: ArtifactEnvelope
    candidate_set: CandidateSet
    configuration: SignalModelConfig
    observations: tuple[SignalObservation, ...]
    snapshots: tuple[SignalSnapshot, ...]

    def __post_init__(self) -> None:
        if self.envelope.artifact_type != "SIGNAL_RUN":
            raise ValueError("Signal run requires SIGNAL_RUN Envelope")
        if self.envelope.configuration_id != self.configuration.configuration_id:
            raise ValueError("Signal configuration identity mismatch")
        symbols = tuple(item.symbol for item in self.snapshots)
        if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
            raise ValueError("Signal snapshots must be sorted and unique")
        self.envelope.verify_payload(self.artifact_payload())

    @property
    def artifact_id(self) -> ArtifactId:
        return self.envelope.artifact_id

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SIGNAL_RUN_SCHEMA,
            "candidate_set": {
                "artifact_id": str(self.candidate_set.envelope.artifact_id),
                "content_hash": self.candidate_set.envelope.content_hash,
            },
            "configuration": self.configuration.to_canonical_dict(),
            "observations": [item.to_canonical_dict() for item in self.observations],
            "snapshots": [item.to_canonical_dict() for item in self.snapshots],
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            "candidate_set": self.candidate_set.to_canonical_dict(),
            "configuration": self.configuration.to_canonical_dict(),
            "observations": [item.to_canonical_dict() for item in self.observations],
            "snapshots": [item.to_canonical_dict() for item in self.snapshots],
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> SignalRunArtifact:
        expected = {
            "envelope",
            "candidate_set",
            "configuration",
            "observations",
            "snapshots",
        }
        if set(payload) != expected:
            raise ValueError("SignalRunArtifact fields mismatch")
        envelope = payload["envelope"]
        candidate_set = payload["candidate_set"]
        configuration = payload["configuration"]
        observations = payload["observations"]
        snapshots = payload["snapshots"]
        if not all(
            isinstance(item, dict)
            for item in (envelope, candidate_set, configuration)
        ) or not isinstance(observations, list) or not isinstance(snapshots, list):
            raise ValueError("SignalRunArtifact canonical value type mismatch")
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(envelope),
            candidate_set=CandidateSet.from_canonical_dict(candidate_set),
            configuration=SignalModelConfig.from_canonical_dict(configuration),
            observations=tuple(
                SignalObservation.from_canonical_dict(_object(item))
                for item in observations
            ),
            snapshots=tuple(
                SignalSnapshot.from_canonical_dict(_object(item))
                for item in snapshots
            ),
        )


def run_signal_model(
    *,
    candidate_set: CandidateSet,
    configuration: SignalModelConfig,
    observations: tuple[SignalObservation, ...],
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
) -> SignalRunArtifact:
    """Run the five-factor research confirmation model for selected Candidates."""

    local = decision_time.value.astimezone(ZoneInfo(configuration.timezone_name))
    if local.strftime("%H:%M") != configuration.decision_time_local:
        raise ValueError("DecisionTime does not match versioned Signal profile")
    if candidate_set.envelope.decision_time != decision_time:
        raise ValueError("Signal DecisionTime must match CandidateSet")
    observation_by_symbol = {item.symbol: item for item in observations}
    if len(observation_by_symbol) != len(observations):
        raise ValueError("Signal observations must have unique symbols")
    selected_symbols = tuple(sorted(item.symbol for item in candidate_set.selected))
    if tuple(sorted(observation_by_symbol)) != selected_symbols:
        raise ValueError("Signal observations must exactly cover selected Candidates")
    if any(item.availability_time.value > decision_time.value for item in observations):
        raise ValueError("Signal observation AvailabilityTime exceeds DecisionTime")
    source_hashes: dict[ArtifactId, str] = {}
    for observation in observations:
        existing_hash = source_hashes.get(observation.source_artifact_id)
        if existing_hash is not None and existing_hash != observation.source_content_hash:
            raise ValueError("Signal source Artifact hash conflict")
        source_hashes[observation.source_artifact_id] = observation.source_content_hash
    ordered_observations = tuple(
        observation_by_symbol[symbol] for symbol in selected_symbols
    )
    snapshots = tuple(
        _build_snapshot(
            candidate_set=candidate_set,
            configuration=configuration,
            observation=observation_by_symbol[symbol],
            decision_time=decision_time,
            created_at=created_at,
            code_revision=code_revision,
        )
        for symbol in selected_symbols
    )
    input_pairs = {
        candidate_set.envelope.artifact_id: candidate_set.envelope.content_hash,
        **{
            item.source_artifact_id: item.source_content_hash
            for item in ordered_observations
        },
        **{
            item.envelope.artifact_id: item.envelope.content_hash for item in snapshots
        },
    }
    payload = {
        "schema_version": SIGNAL_RUN_SCHEMA,
        "candidate_set": {
            "artifact_id": str(candidate_set.envelope.artifact_id),
            "content_hash": candidate_set.envelope.content_hash,
        },
        "configuration": configuration.to_canonical_dict(),
        "observations": [
            item.to_canonical_dict() for item in ordered_observations
        ],
        "snapshots": [item.to_canonical_dict() for item in snapshots],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="SIGNAL_RUN",
        artifact_payload=payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
        configuration_id=configuration.configuration_id,
        configuration_hash=configuration.configuration_hash,
        source_manifest_id=candidate_set.envelope.source_manifest_id,
        source_manifest_hash=candidate_set.envelope.source_manifest_hash,
        input_artifact_ids=tuple(input_pairs),
        input_content_hashes=tuple(input_pairs.values()),
        model_id=configuration.model_id,
        model_version=configuration.model_version,
        data_eligibility=candidate_set.envelope.data_eligibility,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_ONLY",
        reason_codes=("SIGNAL_RESEARCH_ONLY",),
        limitations=(
            "NO_ENTRY_ACTION",
            "NO_CALIBRATED_PROBABILITY",
            "NO_TRADING_AUTHORITY",
        ),
    )
    return SignalRunArtifact(
        envelope=envelope,
        candidate_set=candidate_set,
        configuration=configuration,
        observations=ordered_observations,
        snapshots=snapshots,
    )


def _build_snapshot(
    *,
    candidate_set: CandidateSet,
    configuration: SignalModelConfig,
    observation: SignalObservation,
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
) -> SignalSnapshot:
    metrics = (
        _confirm_min(observation.price_action_return, configuration.price_action_min_return),
        _confirm_min(observation.volume_ratio, configuration.volume_confirmation_min_ratio),
        _confirm_min(observation.trend_return, configuration.trend_confirmation_min_return),
        _confirm_min(observation.price_vs_vwap_return, configuration.vwap_min_relative_return),
    )
    overheat = (
        ConfirmationState.UNKNOWN
        if observation.overheat_return is None
        else (
            ConfirmationState.CONTRADICTED
            if observation.overheat_return >= configuration.overheat_max_return
            else ConfirmationState.CONFIRMED
        )
    )
    all_states = (*metrics, overheat)
    known = tuple(item for item in all_states if item is not ConfirmationState.UNKNOWN)
    confirmed = sum(item is ConfirmationState.CONFIRMED for item in metrics)
    if len(known) != len(all_states):
        signal_state = SignalState.DATA_INSUFFICIENT
        score = None
        reasons = tuple(sorted({*observation.reason_codes, "SIGNAL_METRIC_MISSING"}))
    elif overheat is ConfirmationState.CONTRADICTED:
        signal_state = SignalState.INACTIVE
        score = _score(all_states)
        reasons = ("OVERHEAT_CONTRADICTED",)
    elif confirmed >= configuration.minimum_confirmations:
        signal_state = SignalState.CONFIRMED_FOR_RESEARCH
        score = _score(all_states)
        reasons = ("SIGNAL_CONFIRMED_FOR_RESEARCH_ONLY",)
    else:
        signal_state = SignalState.WATCH
        score = _score(all_states)
        reasons = ("MINIMUM_CONFIRMATIONS_NOT_MET",)
    payload = {
        "symbol": observation.symbol,
        "signal_family": configuration.signal_family.value,
        "signal_state": signal_state.value,
        "price_action_state": metrics[0].value,
        "volume_confirmation_state": metrics[1].value,
        "trend_confirmation_state": metrics[2].value,
        "vwap_state": metrics[3].value,
        "overheat_state": overheat.value,
        "signal_score": score,
        "confidence": len(known) / len(all_states),
        "reason_codes": list(reasons),
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="SIGNAL_SNAPSHOT",
        artifact_payload=payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
        configuration_id=configuration.configuration_id,
        configuration_hash=configuration.configuration_hash,
        source_manifest_id=candidate_set.envelope.source_manifest_id,
        source_manifest_hash=candidate_set.envelope.source_manifest_hash,
        input_artifact_ids=(
            candidate_set.envelope.artifact_id,
            observation.source_artifact_id,
        ),
        input_content_hashes=(
            candidate_set.envelope.content_hash,
            observation.source_content_hash,
        ),
        model_id=configuration.model_id,
        model_version=configuration.model_version,
        data_eligibility=candidate_set.envelope.data_eligibility,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=signal_state.value,
        reason_codes=reasons,
        limitations=("RESEARCH_SIGNAL_NOT_ENTRY", "NO_TRADING_AUTHORITY"),
    )
    return SignalSnapshot(
        envelope=envelope,
        symbol=observation.symbol,
        signal_family=configuration.signal_family,
        signal_state=signal_state,
        price_action_state=metrics[0],
        volume_confirmation_state=metrics[1],
        trend_confirmation_state=metrics[2],
        vwap_state=metrics[3],
        overheat_state=overheat,
        signal_score=score,
        confidence=len(known) / len(all_states),
        reason_codes=reasons,
    )


def _confirm_min(value: float | None, threshold: float) -> ConfirmationState:
    if value is None:
        return ConfirmationState.UNKNOWN
    if value >= threshold:
        return ConfirmationState.CONFIRMED
    return ConfirmationState.UNCONFIRMED


def _score(states: tuple[ConfirmationState, ...]) -> float:
    values = {
        ConfirmationState.CONFIRMED: 1.0,
        ConfirmationState.UNCONFIRMED: 0.0,
        ConfirmationState.CONTRADICTED: -1.0,
        ConfirmationState.UNKNOWN: 0.0,
    }
    return sum(values[item] for item in states) / len(states)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Signal artifact value must be an object")
    return value
