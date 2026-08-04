"""Context-isolated Decimal authority for future Canonical Signal production."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.market_data.contracts import (
    canonical_decimal,
    parse_canonical_decimal,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.contracts import (
    ConfirmationState,
    SignalFamily,
    SignalState,
)
from market_regime_alpha.signals.input_assembly import SignalFactorName
from market_regime_alpha.signals.input_v3 import SignalObservationV3


SIGNAL_MODEL_CONFIGURATION_V2_SCHEMA = "signal-model-configuration-v2"
CANONICAL_SIGNAL_SNAPSHOT_V3_SCHEMA = "canonical-signal-snapshot-v3"
CANONICAL_SIGNAL_MODEL_ID = ModelId("canonical-five-factor-signal-v2")
CANONICAL_SIGNAL_MODEL_VERSION = "2.0.0"

_CONTEXT_PRECISION = 34
_ROUNDING = ROUND_HALF_EVEN


@dataclass(frozen=True, slots=True)
class SignalModelConfigurationV2:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    configuration_version: str
    model_id: ModelId
    model_version: str
    signal_family: SignalFamily
    price_action_min_return: Decimal
    volume_confirmation_min_ratio: Decimal
    trend_confirmation_min_return: Decimal
    vwap_min_relative_return: Decimal
    overheat_max_return: Decimal
    minimum_confirmations: int
    score_denominator: int
    contradicted_score: Decimal
    output_scale: int
    decimal_precision: int
    rounding: str
    scoring_method: str

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_MODEL_CONFIGURATION_V2_SCHEMA:
            raise ValueError("unsupported Signal Model Configuration V2 schema")
        require_sha256("configuration_hash", self.configuration_hash)
        require_text("configuration_version", self.configuration_version)
        require_text("model_version", self.model_version)
        if self.model_id != CANONICAL_SIGNAL_MODEL_ID or self.model_version != CANONICAL_SIGNAL_MODEL_VERSION:
            raise ValueError("Signal Model Configuration V2 model identity mismatch")
        for label, value in (
            ("price_action_min_return", self.price_action_min_return),
            ("volume_confirmation_min_ratio", self.volume_confirmation_min_ratio),
            ("trend_confirmation_min_return", self.trend_confirmation_min_return),
            ("vwap_min_relative_return", self.vwap_min_relative_return),
            ("overheat_max_return", self.overheat_max_return),
            ("contradicted_score", self.contradicted_score),
        ):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{label} must be finite Decimal")
        if self.volume_confirmation_min_ratio < 0 or self.overheat_max_return <= 0:
            raise ValueError("Signal Model Configuration V2 thresholds are invalid")
        if not 1 <= self.minimum_confirmations <= 4:
            raise ValueError("minimum_confirmations must be within [1, 4]")
        if self.score_denominator != 5:
            raise ValueError("canonical five-factor score denominator must equal five")
        if self.contradicted_score != Decimal("-1"):
            raise ValueError("canonical contradicted score must equal negative one")
        if not 0 <= self.output_scale <= 18:
            raise ValueError("Signal output scale must be within [0, 18]")
        if self.decimal_precision != _CONTEXT_PRECISION or self.rounding != _ROUNDING:
            raise ValueError("unsupported fixed Decimal context")
        if self.scoring_method != "FIXED_FIVE_FACTOR_MEAN_OVERHEAT_GATE_V2":
            raise ValueError("unsupported Canonical Signal scoring method")

    @classmethod
    def create(
        cls,
        *,
        configuration_version: str,
        price_action_min_return: Decimal,
        volume_confirmation_min_ratio: Decimal,
        trend_confirmation_min_return: Decimal,
        vwap_min_relative_return: Decimal,
        overheat_max_return: Decimal,
        minimum_confirmations: int,
        output_scale: int = 12,
    ) -> SignalModelConfigurationV2:
        semantic = _configuration_payload(
            configuration_version=configuration_version,
            price_action_min_return=price_action_min_return,
            volume_confirmation_min_ratio=volume_confirmation_min_ratio,
            trend_confirmation_min_return=trend_confirmation_min_return,
            vwap_min_relative_return=vwap_min_relative_return,
            overheat_max_return=overheat_max_return,
            minimum_confirmations=minimum_confirmations,
            output_scale=output_scale,
        )
        configuration_hash = canonical_hash(semantic)
        result = cls(
            schema_version=SIGNAL_MODEL_CONFIGURATION_V2_SCHEMA,
            configuration_id=ArtifactId(
                f"signal-model-configuration-v2-{configuration_hash.split(':', 1)[1][:24]}"
            ),
            configuration_hash=configuration_hash,
            configuration_version=configuration_version,
            model_id=CANONICAL_SIGNAL_MODEL_ID,
            model_version=CANONICAL_SIGNAL_MODEL_VERSION,
            signal_family=SignalFamily.TREND_CONTINUATION,
            price_action_min_return=price_action_min_return,
            volume_confirmation_min_ratio=volume_confirmation_min_ratio,
            trend_confirmation_min_return=trend_confirmation_min_return,
            vwap_min_relative_return=vwap_min_relative_return,
            overheat_max_return=overheat_max_return,
            minimum_confirmations=minimum_confirmations,
            score_denominator=5,
            contradicted_score=Decimal("-1"),
            output_scale=output_scale,
            decimal_precision=_CONTEXT_PRECISION,
            rounding=_ROUNDING,
            scoring_method="FIXED_FIVE_FACTOR_MEAN_OVERHEAT_GATE_V2",
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _configuration_payload(
            configuration_version=self.configuration_version,
            price_action_min_return=self.price_action_min_return,
            volume_confirmation_min_ratio=self.volume_confirmation_min_ratio,
            trend_confirmation_min_return=self.trend_confirmation_min_return,
            vwap_min_relative_return=self.vwap_min_relative_return,
            overheat_max_return=self.overheat_max_return,
            minimum_confirmations=self.minimum_confirmations,
            output_scale=self.output_scale,
        )

    def verify_identity(self) -> None:
        expected = canonical_hash(self.semantic_payload())
        if self.configuration_hash != expected:
            raise ValueError("Signal Model Configuration V2 hash mismatch")
        if str(self.configuration_id) != (
            f"signal-model-configuration-v2-{expected.split(':', 1)[1][:24]}"
        ):
            raise ValueError("Signal Model Configuration V2 identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> SignalModelConfigurationV2:
        expected = {
            "schema_version",
            "configuration_id",
            "configuration_hash",
            "configuration_version",
            "model_id",
            "model_version",
            "signal_family",
            "price_action_min_return",
            "volume_confirmation_min_ratio",
            "trend_confirmation_min_return",
            "vwap_min_relative_return",
            "overheat_max_return",
            "minimum_confirmations",
            "score_denominator",
            "contradicted_score",
            "output_scale",
            "decimal_precision",
            "rounding",
            "scoring_method",
        }
        if set(payload) != expected:
            raise ValueError("Signal Model Configuration V2 fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            configuration_version=str(payload["configuration_version"]),
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            signal_family=SignalFamily(str(payload["signal_family"])),
            price_action_min_return=parse_canonical_decimal(
                "price_action_min_return", payload["price_action_min_return"]
            ),
            volume_confirmation_min_ratio=parse_canonical_decimal(
                "volume_confirmation_min_ratio", payload["volume_confirmation_min_ratio"]
            ),
            trend_confirmation_min_return=parse_canonical_decimal(
                "trend_confirmation_min_return", payload["trend_confirmation_min_return"]
            ),
            vwap_min_relative_return=parse_canonical_decimal(
                "vwap_min_relative_return", payload["vwap_min_relative_return"]
            ),
            overheat_max_return=parse_canonical_decimal(
                "overheat_max_return", payload["overheat_max_return"]
            ),
            minimum_confirmations=_integer(payload["minimum_confirmations"], "minimum_confirmations"),
            score_denominator=_integer(payload["score_denominator"], "score_denominator"),
            contradicted_score=parse_canonical_decimal(
                "contradicted_score", payload["contradicted_score"]
            ),
            output_scale=_integer(payload["output_scale"], "output_scale"),
            decimal_precision=_integer(payload["decimal_precision"], "decimal_precision"),
            rounding=str(payload["rounding"]),
            scoring_method=str(payload["scoring_method"]),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class CanonicalSignalSnapshotV3:
    schema_version: str
    envelope: ArtifactEnvelope
    symbol: str
    signal_family: SignalFamily
    signal_state: SignalState
    price_action_state: ConfirmationState
    volume_confirmation_state: ConfirmationState
    trend_confirmation_state: ConfirmationState
    vwap_state: ConfirmationState
    overheat_state: ConfirmationState
    confirmation_count: int
    score_denominator: int
    signal_score: Decimal | None
    confidence: Decimal
    output_scale: int
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CANONICAL_SIGNAL_SNAPSHOT_V3_SCHEMA:
            raise ValueError("unsupported Canonical Signal Snapshot V3 schema")
        if self.envelope.artifact_type != "CANONICAL_SIGNAL_SNAPSHOT_V3":
            raise ValueError("Canonical Signal Snapshot V3 Envelope type mismatch")
        if not 0 <= self.confirmation_count <= 4 or self.score_denominator != 5:
            raise ValueError("Canonical Signal confirmation projection is invalid")
        if self.signal_score is not None and not Decimal("-1") <= self.signal_score <= Decimal("1"):
            raise ValueError("Canonical Signal score must be within [-1, 1]")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("Canonical Signal confidence must be within [0, 1]")
        self.envelope.verify_payload(self.artifact_payload())

    @property
    def artifact_id(self) -> ArtifactId:
        return self.envelope.artifact_id

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "signal_family": self.signal_family.value,
            "signal_state": self.signal_state.value,
            "price_action_state": self.price_action_state.value,
            "volume_confirmation_state": self.volume_confirmation_state.value,
            "trend_confirmation_state": self.trend_confirmation_state.value,
            "vwap_state": self.vwap_state.value,
            "overheat_state": self.overheat_state.value,
            "confirmation_count": self.confirmation_count,
            "score_denominator": self.score_denominator,
            "signal_score": (
                canonical_decimal(self.signal_score, label="signal_score")
                if self.signal_score is not None
                else None
            ),
            "confidence": canonical_decimal(self.confidence, label="confidence"),
            "output_scale": self.output_scale,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"envelope": self.envelope.to_canonical_dict(), **self.artifact_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> CanonicalSignalSnapshotV3:
        expected = {
            "envelope",
            "schema_version",
            "symbol",
            "signal_family",
            "signal_state",
            "price_action_state",
            "volume_confirmation_state",
            "trend_confirmation_state",
            "vwap_state",
            "overheat_state",
            "confirmation_count",
            "score_denominator",
            "signal_score",
            "confidence",
            "output_scale",
            "reason_codes",
        }
        if set(payload) != expected or not isinstance(payload["envelope"], dict):
            raise ValueError("Canonical Signal Snapshot V3 fields mismatch")
        raw_score = payload["signal_score"]
        raw_reasons = payload["reason_codes"]
        if not isinstance(raw_reasons, list):
            raise ValueError("Canonical Signal reasons must be an array")
        return cls(
            schema_version=str(payload["schema_version"]),
            envelope=ArtifactEnvelope.from_canonical_dict(payload["envelope"]),
            symbol=str(payload["symbol"]),
            signal_family=SignalFamily(str(payload["signal_family"])),
            signal_state=SignalState(str(payload["signal_state"])),
            price_action_state=ConfirmationState(str(payload["price_action_state"])),
            volume_confirmation_state=ConfirmationState(str(payload["volume_confirmation_state"])),
            trend_confirmation_state=ConfirmationState(str(payload["trend_confirmation_state"])),
            vwap_state=ConfirmationState(str(payload["vwap_state"])),
            overheat_state=ConfirmationState(str(payload["overheat_state"])),
            confirmation_count=_integer(payload["confirmation_count"], "confirmation_count"),
            score_denominator=_integer(payload["score_denominator"], "score_denominator"),
            signal_score=(
                parse_canonical_decimal("signal_score", raw_score)
                if raw_score is not None
                else None
            ),
            confidence=parse_canonical_decimal("confidence", payload["confidence"]),
            output_scale=_integer(payload["output_scale"], "output_scale"),
            reason_codes=tuple(str(item) for item in raw_reasons),
        )


class CanonicalSignalModelV2:
    model_id = CANONICAL_SIGNAL_MODEL_ID
    model_version = CANONICAL_SIGNAL_MODEL_VERSION

    def run(
        self,
        *,
        candidate_set: CandidateSet,
        observation: SignalObservationV3,
        configuration: SignalModelConfigurationV2,
        decision_time: DecisionTime,
        created_at: datetime,
        code_revision: str,
    ) -> CanonicalSignalSnapshotV3:
        configuration.verify_identity()
        observation.verify_identity()
        if observation.decision_time != decision_time.value:
            raise ValueError("Canonical Signal observation DecisionTime mismatch")
        factors = {item.factor_name: item.value for item in observation.factors}
        with localcontext(Context(prec=_CONTEXT_PRECISION, rounding=_ROUNDING)):
            states = (
                _confirm_min(
                    factors[SignalFactorName.PRICE_ACTION_RETURN],
                    configuration.price_action_min_return,
                ),
                _confirm_min(
                    factors[SignalFactorName.VOLUME_RATIO],
                    configuration.volume_confirmation_min_ratio,
                ),
                _confirm_min(
                    factors[SignalFactorName.TREND_RETURN],
                    configuration.trend_confirmation_min_return,
                ),
                _confirm_min(
                    factors[SignalFactorName.PRICE_VS_VWAP_RETURN],
                    configuration.vwap_min_relative_return,
                ),
            )
            overheat_value = factors[SignalFactorName.OVERHEAT_RETURN]
            overheat = (
                ConfirmationState.UNKNOWN
                if overheat_value is None
                else ConfirmationState.CONTRADICTED
                if overheat_value >= configuration.overheat_max_return
                else ConfirmationState.CONFIRMED
            )
            all_states = (*states, overheat)
            known_count = sum(item is not ConfirmationState.UNKNOWN for item in all_states)
            confirmation_count = sum(item is ConfirmationState.CONFIRMED for item in states)
            confidence = _quantize(
                Decimal(known_count) / Decimal(configuration.score_denominator),
                configuration.output_scale,
            )
            if not observation.factor_requirements_satisfied or known_count != 5:
                signal_state = SignalState.DATA_INSUFFICIENT
                score = None
                reasons = tuple(
                    sorted({*observation.reason_codes, "SIGNAL_FACTOR_REQUIREMENTS_NOT_MET"})
                )
            elif overheat is ConfirmationState.CONTRADICTED:
                signal_state = SignalState.INACTIVE
                score = _score(all_states, configuration)
                reasons = ("OVERHEAT_CONTRADICTED",)
            elif confirmation_count >= configuration.minimum_confirmations:
                signal_state = SignalState.CONFIRMED_FOR_RESEARCH
                score = _score(all_states, configuration)
                reasons = ("SIGNAL_CONFIRMED_FOR_RESEARCH_ONLY",)
            else:
                signal_state = SignalState.WATCH
                score = _score(all_states, configuration)
                reasons = ("MINIMUM_CONFIRMATIONS_NOT_MET",)
            payload = _snapshot_payload(
                symbol=observation.symbol,
                signal_family=configuration.signal_family,
                signal_state=signal_state,
                states=states,
                overheat=overheat,
                confirmation_count=confirmation_count,
                score_denominator=configuration.score_denominator,
                signal_score=score,
                confidence=confidence,
                output_scale=configuration.output_scale,
                reason_codes=reasons,
            )
        input_pairs = {
            candidate_set.envelope.artifact_id: candidate_set.envelope.content_hash,
            observation.observation_id: observation.content_hash,
        }
        envelope = ArtifactEnvelope.create(
            artifact_type="CANONICAL_SIGNAL_SNAPSHOT_V3",
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
            status=signal_state.value,
            reason_codes=reasons,
            limitations=(
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                "NO_CALIBRATED_PROBABILITY",
                "NO_ENTRY_ACTION",
                "NO_TRADING_AUTHORITY",
            ),
        )
        return CanonicalSignalSnapshotV3(
            schema_version=CANONICAL_SIGNAL_SNAPSHOT_V3_SCHEMA,
            envelope=envelope,
            symbol=observation.symbol,
            signal_family=configuration.signal_family,
            signal_state=signal_state,
            price_action_state=states[0],
            volume_confirmation_state=states[1],
            trend_confirmation_state=states[2],
            vwap_state=states[3],
            overheat_state=overheat,
            confirmation_count=confirmation_count,
            score_denominator=configuration.score_denominator,
            signal_score=score,
            confidence=confidence,
            output_scale=configuration.output_scale,
            reason_codes=reasons,
        )


def canonical_signal_model_configuration_v2() -> SignalModelConfigurationV2:
    return SignalModelConfigurationV2.create(
        configuration_version="canonical-five-factor-decimal-v2",
        price_action_min_return=Decimal("0"),
        volume_confirmation_min_ratio=Decimal("1"),
        trend_confirmation_min_return=Decimal("0"),
        vwap_min_relative_return=Decimal("0"),
        overheat_max_return=Decimal("0.08"),
        minimum_confirmations=3,
        output_scale=12,
    )


def _confirm_min(value: Decimal | None, threshold: Decimal) -> ConfirmationState:
    if value is None:
        return ConfirmationState.UNKNOWN
    return (
        ConfirmationState.CONFIRMED
        if value >= threshold
        else ConfirmationState.UNCONFIRMED
    )


def _score(
    states: tuple[ConfirmationState, ...],
    configuration: SignalModelConfigurationV2,
) -> Decimal:
    values = {
        ConfirmationState.CONFIRMED: Decimal("1"),
        ConfirmationState.UNCONFIRMED: Decimal("0"),
        ConfirmationState.CONTRADICTED: configuration.contradicted_score,
    }
    if any(item is ConfirmationState.UNKNOWN for item in states):
        raise ValueError("unknown factors cannot be scored")
    return _quantize(
        sum((values[item] for item in states), Decimal("0"))
        / Decimal(configuration.score_denominator),
        configuration.output_scale,
    )


def _quantize(value: Decimal, scale: int) -> Decimal:
    quantum = Decimal(1).scaleb(-scale)
    quantized = value.quantize(quantum, rounding=_ROUNDING)
    return quantized.normalize() if quantized != 0 else Decimal("0")


def _configuration_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_MODEL_CONFIGURATION_V2_SCHEMA,
        "configuration_version": values["configuration_version"],
        "model_id": str(CANONICAL_SIGNAL_MODEL_ID),
        "model_version": CANONICAL_SIGNAL_MODEL_VERSION,
        "signal_family": SignalFamily.TREND_CONTINUATION.value,
        "price_action_min_return": canonical_decimal(values["price_action_min_return"]),
        "volume_confirmation_min_ratio": canonical_decimal(values["volume_confirmation_min_ratio"]),
        "trend_confirmation_min_return": canonical_decimal(values["trend_confirmation_min_return"]),
        "vwap_min_relative_return": canonical_decimal(values["vwap_min_relative_return"]),
        "overheat_max_return": canonical_decimal(values["overheat_max_return"]),
        "minimum_confirmations": values["minimum_confirmations"],
        "score_denominator": 5,
        "contradicted_score": "-1",
        "output_scale": values["output_scale"],
        "decimal_precision": _CONTEXT_PRECISION,
        "rounding": _ROUNDING,
        "scoring_method": "FIXED_FIVE_FACTOR_MEAN_OVERHEAT_GATE_V2",
    }


def _snapshot_payload(
    *,
    symbol: str,
    signal_family: SignalFamily,
    signal_state: SignalState,
    states: tuple[ConfirmationState, ...],
    overheat: ConfirmationState,
    confirmation_count: int,
    score_denominator: int,
    signal_score: Decimal | None,
    confidence: Decimal,
    output_scale: int,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": CANONICAL_SIGNAL_SNAPSHOT_V3_SCHEMA,
        "symbol": symbol,
        "signal_family": signal_family.value,
        "signal_state": signal_state.value,
        "price_action_state": states[0].value,
        "volume_confirmation_state": states[1].value,
        "trend_confirmation_state": states[2].value,
        "vwap_state": states[3].value,
        "overheat_state": overheat.value,
        "confirmation_count": confirmation_count,
        "score_denominator": score_denominator,
        "signal_score": (
            canonical_decimal(signal_score, label="signal_score")
            if signal_score is not None
            else None
        ),
        "confidence": canonical_decimal(confidence, label="confidence"),
        "output_scale": output_scale,
        "reason_codes": list(reason_codes),
    }


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


__all__ = [
    "CANONICAL_SIGNAL_MODEL_ID",
    "CANONICAL_SIGNAL_MODEL_VERSION",
    "CanonicalSignalModelV2",
    "CanonicalSignalSnapshotV3",
    "SignalModelConfigurationV2",
    "canonical_signal_model_configuration_v2",
]
