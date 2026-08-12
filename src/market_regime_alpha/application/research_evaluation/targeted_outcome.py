"""Target-scoped factual labels derived without mutating a frozen Decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, Mapping
from enum import Enum
from zoneinfo import ZoneInfo

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)


class BarrierOrderingOutcome(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_TOUCH = "NO_TOUCH"
    UP_FIRST = "UP_FIRST"
    DOWN_FIRST = "DOWN_FIRST"
    AMBIGUOUS_NOT_OBSERVABLE = "AMBIGUOUS_NOT_OBSERVABLE"
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
    ProspectiveShadowOutcome,
)
from market_regime_alpha.application.research_evaluation.targets import (
    BarrierDefinition,
    CorporateActionPolicy,
    OutcomeCheckpoint,
    OutcomeTargetProtocol,
    SuspensionPolicy,
    TargetDefinition,
)
from market_regime_alpha.application.shadow_research.contracts import ShadowDecision
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.artifacts import VerifiedMarketDataDataset
from market_regime_alpha.market_data.contracts import (
    AdjustmentMode,
    CanonicalMarketBar,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    canonical_decimal,
    parse_canonical_decimal,
)


@dataclass(frozen=True, slots=True)
class TargetOutcomeLabel:
    label_id: ArtifactId
    label_hash: str
    symbol: str
    target: RuntimeArtifactReference
    label_interval_start: datetime
    label_interval_end: datetime
    decision_reference_price: Decimal
    checkpoint_price: Decimal | None
    checkpoint_return: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    barrier_passages: tuple[tuple[str, datetime | None], ...]
    barrier_ordering: BarrierOrderingOutcome
    market_conditions: tuple[OutcomeMarketCondition, ...]
    availability_status: OutcomeAvailabilityStatus
    outcome_available_at: datetime
    reason_codes: tuple[str, ...]
    schema_version: str = "target-outcome-label/v2"

    def __post_init__(self) -> None:
        if self.schema_version not in {
            "target-outcome-label/v1",
            "target-outcome-label/v2",
        }:
            raise ValueError("unsupported Target Outcome label schema")
        require_sha256("label_hash", self.label_hash)
        require_text("symbol", self.symbol)
        if self.label_interval_start.tzinfo is None or self.label_interval_end.tzinfo is None:
            raise ValueError("Target label interval must be timezone-aware")
        if self.label_interval_end <= self.label_interval_start:
            raise ValueError("Target label interval must advance beyond Decision")
        if self.outcome_available_at < self.label_interval_end:
            raise ValueError("Target label cannot be available before interval end")
        expected = (
            None
            if self.checkpoint_price is None
            else (self.checkpoint_price - self.decision_reference_price) / self.decision_reference_price
        )
        if self.checkpoint_return != expected:
            raise ValueError("Target checkpoint return does not match price")
        if self.barrier_passages != tuple(sorted(self.barrier_passages, key=lambda item: item[0])):
            raise ValueError("Target barrier passages must be sorted")
        if (
            self.barrier_ordering
            is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
            and "BARRIER_ORDERING_NOT_OBSERVABLE" not in self.reason_codes
        ):
            raise ValueError("ambiguous barrier ordering requires an explicit reason")
        if self.market_conditions != tuple(sorted(set(self.market_conditions), key=lambda item: item.value)):
            raise ValueError("Target market conditions must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Target label reasons must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.label_hash:
            raise ValueError("Target label hash does not match content")
        if str(self.label_id) != f"target-outcome-label:{self.label_hash[7:]}":
            raise ValueError("Target label id does not match content")

    @classmethod
    def create(cls, **values: Any) -> TargetOutcomeLabel:
        normalized = dict(values)
        normalized.setdefault("schema_version", "target-outcome-label/v2")
        if (
            normalized["schema_version"] == "target-outcome-label/v2"
            and "barrier_ordering" not in normalized
        ):
            raise ValueError("Target Outcome label v2 requires barrier_ordering")
        normalized["barrier_passages"] = tuple(sorted(values["barrier_passages"], key=lambda item: item[0]))
        normalized["market_conditions"] = tuple(sorted(set(values["market_conditions"]), key=lambda item: item.value))
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        normalized["checkpoint_return"] = (
            None
            if values["checkpoint_price"] is None
            else (values["checkpoint_price"] - values["decision_reference_price"]) / values["decision_reference_price"]
        )
        digest = canonical_hash(_label_payload(**normalized))
        return cls(
            label_id=ArtifactId(f"target-outcome-label:{digest[7:]}"),
            label_hash=digest,
            **normalized,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _label_payload(**{name: getattr(self, name) for name in _label_value_names()})

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "label_id": str(self.label_id),
            "label_hash": self.label_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TargetOutcomeLabel:
        return cls(
            label_id=ArtifactId(str(payload["label_id"])),
            label_hash=str(payload["label_hash"]),
            symbol=str(payload["symbol"]),
            target=_reference(payload["target"]),
            label_interval_start=_instant(payload["label_interval_start"]),
            label_interval_end=_instant(payload["label_interval_end"]),
            decision_reference_price=_decimal(payload["decision_reference_price"]),
            checkpoint_price=_optional_decimal(payload["checkpoint_price"]),
            checkpoint_return=_optional_decimal(payload["checkpoint_return"]),
            mfe=_optional_decimal(payload["mfe"]),
            mae=_optional_decimal(payload["mae"]),
            barrier_passages=tuple(
                (str(item["barrier_id"]), _optional_instant(item["first_passage_at"])) for item in _objects(payload["barrier_passages"])
            ),
            barrier_ordering=BarrierOrderingOutcome(
                str(payload.get("barrier_ordering", "NOT_APPLICABLE"))
            ),
            market_conditions=tuple(OutcomeMarketCondition(str(item)) for item in _array(payload["market_conditions"])),
            availability_status=OutcomeAvailabilityStatus(str(payload["availability_status"])),
            outcome_available_at=_instant(payload["outcome_available_at"]),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class TargetedShadowOutcome:
    settlement_id: ArtifactId
    settlement_hash: str
    shadow_decision: RuntimeArtifactReference
    factual_outcome_v1: RuntimeArtifactReference
    source_dataset: RuntimeArtifactReference
    target_protocol_id: ArtifactId
    target_protocol_hash: str
    next_session_date: date
    labels: tuple[TargetOutcomeLabel, ...]
    availability_status: OutcomeAvailabilityStatus
    outcome_available_at: datetime
    created_at: datetime
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    schema_version: str = "targeted-shadow-outcome/v2"

    def __post_init__(self) -> None:
        if self.schema_version != "targeted-shadow-outcome/v2":
            raise ValueError("unsupported targeted Shadow Outcome schema")
        require_sha256("settlement_hash", self.settlement_hash)
        require_sha256("target_protocol_hash", self.target_protocol_hash)
        if self.created_at < self.outcome_available_at:
            raise ValueError("Targeted Outcome cannot be created before availability")
        ordering = tuple((item.symbol, str(item.target.artifact_id)) for item in self.labels)
        if ordering != tuple(sorted(set(ordering))):
            raise ValueError("Targeted Outcome labels must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Targeted Outcome reasons must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Targeted Outcome limitations must be unique and sorted")
        required = {
            "FACTUAL_LABELS_ONLY",
            "NOT_ALPHA_VALIDATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Targeted Outcome authority ceiling is incomplete")
        if canonical_hash(self.identity_payload()) != self.settlement_hash:
            raise ValueError("Targeted Outcome hash does not match content")
        if str(self.settlement_id) != f"targeted-shadow-outcome:{self.settlement_hash[7:]}":
            raise ValueError("Targeted Outcome id does not match content")

    @classmethod
    def create(cls, **values: Any) -> TargetedShadowOutcome:
        normalized = dict(values)
        normalized["labels"] = tuple(sorted(values["labels"], key=lambda item: (item.symbol, str(item.target.artifact_id))))
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        normalized["limitations"] = tuple(sorted(set(values["limitations"])))
        digest = canonical_hash(_settlement_payload(**normalized))
        return cls(
            settlement_id=ArtifactId(f"targeted-shadow-outcome:{digest[7:]}"),
            settlement_hash=digest,
            **normalized,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _settlement_payload(**{name: getattr(self, name) for name in _settlement_value_names()})

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "settlement_id": str(self.settlement_id),
            "settlement_hash": self.settlement_hash,
            **self.identity_payload(),
            "authority": {
                "engineering_recorded_only": True,
                "prospective_proven": False,
                "alpha_validated": False,
            },
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TargetedShadowOutcome:
        if payload.get("authority") != {
            "engineering_recorded_only": True,
            "prospective_proven": False,
            "alpha_validated": False,
        }:
            raise ValueError("Targeted Outcome authority declaration mismatch")
        return cls(
            settlement_id=ArtifactId(str(payload["settlement_id"])),
            settlement_hash=str(payload["settlement_hash"]),
            shadow_decision=_reference(payload["shadow_decision"]),
            factual_outcome_v1=_reference(payload["factual_outcome_v1"]),
            source_dataset=_reference(payload["source_dataset"]),
            target_protocol_id=ArtifactId(str(payload["target_protocol_id"])),
            target_protocol_hash=str(payload["target_protocol_hash"]),
            next_session_date=date.fromisoformat(str(payload["next_session_date"])),
            labels=tuple(TargetOutcomeLabel.from_canonical_dict(item) for item in _objects(payload["labels"])),
            availability_status=OutcomeAvailabilityStatus(str(payload["availability_status"])),
            outcome_available_at=_instant(payload["outcome_available_at"]),
            created_at=_instant(payload["created_at"]),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
            limitations=tuple(str(item) for item in _array(payload["limitations"])),
            schema_version=str(payload["schema_version"]),
        )


def build_targeted_shadow_outcome(
    *,
    decision: ShadowDecision,
    factual_outcome_v1: ProspectiveShadowOutcome,
    settlement_dataset: VerifiedMarketDataDataset,
    protocol: OutcomeTargetProtocol,
    created_at: datetime,
) -> TargetedShadowOutcome:
    if factual_outcome_v1.shadow_decision.artifact_id != decision.decision_id:
        raise ValueError("Targeted Outcome Decision identity mismatch")
    if factual_outcome_v1.shadow_decision.content_hash != decision.decision_hash:
        raise ValueError("Targeted Outcome Decision hash mismatch")
    if (
        factual_outcome_v1.source_dataset.artifact_id != ArtifactId(str(settlement_dataset.artifact.dataset_id))
        or factual_outcome_v1.source_dataset.content_hash != settlement_dataset.artifact.content_hash
    ):
        raise ValueError("Targeted Outcome Dataset lineage mismatch")
    bars = tuple(settlement_dataset.artifact.iter_bars())
    labels = tuple(
        _build_label(
            decision=decision,
            target=target,
            protocol=protocol,
            symbol_observation=observation,
            bars=bars,
            fallback_available_at=factual_outcome_v1.outcome_available_at,
            next_session_date=factual_outcome_v1.next_session_date,
        )
        for observation in factual_outcome_v1.observations
        for target in protocol.targets
    )
    availability = max((factual_outcome_v1.outcome_available_at, *(item.outcome_available_at for item in labels)))
    if created_at < availability:
        raise ValueError("Targeted Outcome creation predates source availability")
    if not labels or all(item.availability_status is OutcomeAvailabilityStatus.UNAVAILABLE for item in labels):
        overall = OutcomeAvailabilityStatus.UNAVAILABLE if labels else OutcomeAvailabilityStatus.COMPLETE
    elif all(item.availability_status is OutcomeAvailabilityStatus.COMPLETE for item in labels):
        overall = OutcomeAvailabilityStatus.COMPLETE
    else:
        overall = OutcomeAvailabilityStatus.PARTIAL
    return TargetedShadowOutcome.create(
        shadow_decision=RuntimeArtifactReference("SHADOW_DECISION", decision.decision_id, decision.decision_hash),
        factual_outcome_v1=RuntimeArtifactReference(
            "FACTUAL_OUTCOME_V1",
            factual_outcome_v1.settlement_id,
            factual_outcome_v1.settlement_hash,
        ),
        source_dataset=factual_outcome_v1.source_dataset,
        target_protocol_id=protocol.protocol_id,
        target_protocol_hash=protocol.protocol_hash,
        next_session_date=factual_outcome_v1.next_session_date,
        labels=labels,
        availability_status=overall,
        outcome_available_at=availability,
        created_at=created_at,
        reason_codes=tuple(
            sorted(
                {
                    f"TARGETED_OUTCOME_{overall.value}",
                    *({"NO_CANDIDATE_LABELS"} if not labels else set()),
                }
            )
        ),
        limitations=(
            "ENGINEERING_RECORDED_ONLY",
            "FACTUAL_LABELS_ONLY",
            "NOT_ALPHA_VALIDATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        ),
    )


def _build_label(
    *,
    decision: ShadowDecision,
    target: TargetDefinition,
    protocol: OutcomeTargetProtocol,
    symbol_observation: Any,
    bars: tuple[CanonicalMarketBar, ...],
    fallback_available_at: datetime,
    next_session_date: date,
) -> TargetOutcomeLabel:
    return build_target_outcome_label_from_bars(
        symbol=symbol_observation.symbol,
        decision_frozen_at=decision.decision_frozen_at,
        decision_reference_price=symbol_observation.decision_reference_price,
        target=target,
        protocol=protocol,
        bars=bars,
        fallback_available_at=fallback_available_at,
        next_session_date=next_session_date,
        initial_market_conditions=symbol_observation.market_conditions,
        fallback_open=symbol_observation.next_open,
    )


def build_target_outcome_label_from_bars(
    *,
    symbol: str,
    decision_frozen_at: datetime,
    decision_reference_price: Decimal,
    target: TargetDefinition,
    protocol: OutcomeTargetProtocol,
    bars: tuple[CanonicalMarketBar, ...],
    fallback_available_at: datetime,
    next_session_date: date,
    initial_market_conditions: tuple[OutcomeMarketCondition, ...] = (),
    fallback_open: Decimal | None = None,
) -> TargetOutcomeLabel:
    """Build one canonical Target label from owner-resolved market bars.

    The Shadow settlement and Historical corpus adapters deliberately share
    this numerical/tradability kernel.  Callers own only subject resolution and
    lineage; checkpoint, excursion, barrier and missingness semantics stay
    canonical here.
    """

    zone = ZoneInfo(protocol.timezone_name)
    end_time = _checkpoint_time(target.checkpoint)
    interval_end = datetime.combine(next_session_date, end_time, zone).astimezone(UTC)
    selected = tuple(
        sorted(
            (
                item
                for item in bars
                if item.symbol == symbol
                and item.market_date == next_session_date
                and item.event_end <= interval_end
            ),
            key=lambda item: item.event_start,
        )
    )
    intraday = tuple(item for item in selected if item.timeframe.duration is not None)
    daily = tuple(item for item in selected if item.timeframe is Timeframe.DAILY)
    checkpoint_price = _checkpoint_price(
        target.checkpoint,
        minutes=intraday,
        daily=daily,
        zone=zone,
        fallback_open=fallback_open,
    )
    conditions = set(initial_market_conditions)
    reasons: set[str] = set()
    missing_required = {
        data_kind
        for data_kind in target.required_market_data
        if (
            (
                data_kind in {item.value for item in Timeframe}
                and not any(item.timeframe.value == data_kind for item in selected)
            )
            or (
                data_kind == "FACTUAL_OUTCOME_V1"
                and fallback_open is None
            )
            or (
                data_kind == "NORMALIZED_DAILY_OPEN"
                and fallback_open is None
            )
        )
    }
    if missing_required:
        checkpoint_price = None
        reasons.update(f"REQUIRED_MARKET_DATA_MISSING_{item}" for item in missing_required)
    suspended = any(
        item.trading_status is TradingStatus.SUSPENDED for item in selected
    )
    unknown_status = any(
        item.trading_status is TradingStatus.UNKNOWN for item in selected
    )
    if suspended:
        conditions.add(OutcomeMarketCondition.SUSPENDED)
    if (
        suspended or unknown_status
    ) and target.canonical_horizon.suspension_policy is SuspensionPolicy.NOT_ESTIMABLE_AND_ANNOTATE:
        checkpoint_price = None
        reasons.add(
            "TARGET_SUSPENDED_NOT_ESTIMABLE"
            if suspended
            else "TARGET_TRADING_STATUS_UNKNOWN"
        )
    if any(item.price_limit_state is PriceLimitState.LIMIT_UP for item in selected):
        conditions.add(OutcomeMarketCondition.LIMIT_UP)
    if any(item.price_limit_state is PriceLimitState.LIMIT_DOWN for item in selected):
        conditions.add(OutcomeMarketCondition.LIMIT_DOWN)
    corporate_action = any(item.adjustment_mode is not AdjustmentMode.RAW or item.adjustment_factor != Decimal("1") for item in selected)
    if corporate_action:
        conditions.add(OutcomeMarketCondition.CORPORATE_ACTION)
        reasons.add("CORPORATE_ACTION_POLICY_FAILED_CLOSED")
        if target.corporate_action_policy is CorporateActionPolicy.RAW_ONLY_FAIL_CLOSED:
            checkpoint_price = None
    if checkpoint_price is None:
        conditions.add(OutcomeMarketCondition.MISSING_QUOTE)
        reasons.add("TARGET_CHECKPOINT_UNAVAILABLE")
    relevant = tuple(item for item in intraday if item.event_end <= interval_end)
    mfe = (
        None
        if not target.compute_mfe_mae or not relevant
        else (max(item.high for item in relevant) - decision_reference_price)
        / decision_reference_price
    )
    mae = (
        None
        if not target.compute_mfe_mae or not relevant
        else (min(item.low for item in relevant) - decision_reference_price)
        / decision_reference_price
    )
    available = max((fallback_available_at, *(item.available_at for item in selected)))
    # Missing/unavailable is a factual result available when the archived
    # settlement attempt completed, never a synthetic zero.
    available = max(available, interval_end)
    status = (
        OutcomeAvailabilityStatus.COMPLETE
        if checkpoint_price is not None and not corporate_action
        else OutcomeAvailabilityStatus.UNAVAILABLE
        if not selected
        else OutcomeAvailabilityStatus.PARTIAL
    )
    barrier_ordering = _barrier_ordering(
        relevant,
        decision_reference_price,
        target.barriers,
    )
    if barrier_ordering is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE:
        reasons.add("BARRIER_ORDERING_NOT_OBSERVABLE")
        if status is OutcomeAvailabilityStatus.COMPLETE:
            status = OutcomeAvailabilityStatus.PARTIAL
    reasons.add(f"TARGET_{status.value}")
    return TargetOutcomeLabel.create(
        symbol=symbol,
        target=RuntimeArtifactReference(
            "OUTCOME_TARGET_DEFINITION", target.target_id, target.target_hash
        ),
        label_interval_start=decision_frozen_at,
        label_interval_end=interval_end,
        decision_reference_price=decision_reference_price,
        checkpoint_price=checkpoint_price,
        mfe=mfe,
        mae=mae,
        barrier_passages=tuple(
            (
                barrier.barrier_id,
                _first_passage(relevant, decision_reference_price, barrier),
            )
            for barrier in target.barriers
        ),
        barrier_ordering=barrier_ordering,
        market_conditions=tuple(conditions),
        availability_status=status,
        outcome_available_at=available,
        reason_codes=tuple(reasons),
    )


def _checkpoint_price(
    checkpoint: OutcomeCheckpoint,
    *,
    minutes: tuple[CanonicalMarketBar, ...],
    daily: tuple[CanonicalMarketBar, ...],
    zone: ZoneInfo,
    fallback_open: Decimal | None,
) -> Decimal | None:
    if checkpoint is OutcomeCheckpoint.OPEN:
        return minutes[0].open if minutes else fallback_open
    if checkpoint is OutcomeCheckpoint.CLOSE:
        return daily[-1].close if daily else _complete_checkpoint(minutes, zone, time(15, 0))
    return _complete_checkpoint(minutes, zone, _checkpoint_time(checkpoint))


def _complete_checkpoint(bars: tuple[CanonicalMarketBar, ...], zone: ZoneInfo, checkpoint: time) -> Decimal | None:
    eligible = tuple(
        item
        for item in bars
        if time(9, 30) <= item.event_start.astimezone(zone).time().replace(tzinfo=None)
        and item.event_end.astimezone(zone).time().replace(tzinfo=None) <= checkpoint
    )
    if not eligible or eligible[-1].event_end.astimezone(zone).time().replace(tzinfo=None) != checkpoint:
        return None
    if any(
        left.event_end != right.event_start
        and not (
            left.event_end.astimezone(zone).time().replace(tzinfo=None) == time(11, 30)
            and right.event_start.astimezone(zone).time().replace(tzinfo=None) == time(13, 0)
        )
        for left, right in zip(eligible, eligible[1:], strict=False)
    ):
        return None
    return eligible[-1].close


def _first_passage(bars: tuple[CanonicalMarketBar, ...], reference: Decimal, barrier: BarrierDefinition) -> datetime | None:
    passage = _first_passage_bar(bars, reference, barrier)
    return None if passage is None else passage.event_end


def _first_passage_bar(
    bars: tuple[CanonicalMarketBar, ...],
    reference: Decimal,
    barrier: BarrierDefinition,
) -> CanonicalMarketBar | None:
    boundary = reference * (
        Decimal("1") + barrier.return_threshold if barrier.direction == "UP" else Decimal("1") - barrier.return_threshold
    )
    for item in bars:
        if (barrier.direction == "UP" and item.high >= boundary) or (barrier.direction == "DOWN" and item.low <= boundary):
            return item
    return None


def _barrier_ordering(
    bars: tuple[CanonicalMarketBar, ...],
    reference: Decimal,
    barriers: tuple[BarrierDefinition, ...],
) -> BarrierOrderingOutcome:
    up = tuple(item for item in barriers if item.direction == "UP")
    down = tuple(item for item in barriers if item.direction == "DOWN")
    if not up or not down:
        return BarrierOrderingOutcome.NOT_APPLICABLE
    up_bars = tuple(
        item
        for barrier in up
        if (item := _first_passage_bar(bars, reference, barrier)) is not None
    )
    down_bars = tuple(
        item
        for barrier in down
        if (item := _first_passage_bar(bars, reference, barrier)) is not None
    )
    first_up = min(up_bars, key=lambda item: item.event_end, default=None)
    first_down = min(down_bars, key=lambda item: item.event_end, default=None)
    if first_up is None and first_down is None:
        return BarrierOrderingOutcome.NO_TOUCH
    if first_down is None:
        return BarrierOrderingOutcome.UP_FIRST
    if first_up is None:
        return BarrierOrderingOutcome.DOWN_FIRST
    if (
        first_up.event_start == first_down.event_start
        and first_up.event_end == first_down.event_end
    ):
        return BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
    return (
        BarrierOrderingOutcome.UP_FIRST
        if first_up.event_end < first_down.event_end
        else BarrierOrderingOutcome.DOWN_FIRST
    )


def _checkpoint_time(value: OutcomeCheckpoint) -> time:
    return {
        OutcomeCheckpoint.OPEN: time(9, 30),
        OutcomeCheckpoint.TIME_0945: time(9, 45),
        OutcomeCheckpoint.TIME_1000: time(10, 0),
        OutcomeCheckpoint.TIME_1030: time(10, 30),
        OutcomeCheckpoint.TIME_1130: time(11, 30),
        OutcomeCheckpoint.CLOSE: time(15, 0),
    }[value]


def _label_value_names() -> tuple[str, ...]:
    return (
        "symbol",
        "target",
        "label_interval_start",
        "label_interval_end",
        "decision_reference_price",
        "checkpoint_price",
        "checkpoint_return",
        "mfe",
        "mae",
        "barrier_passages",
        "barrier_ordering",
        "market_conditions",
        "availability_status",
        "outcome_available_at",
        "reason_codes",
        "schema_version",
    )


def _label_payload(**values: Any) -> dict[str, Any]:
    payload = {
        "schema_version": values["schema_version"],
        "symbol": values["symbol"],
        "target": values["target"].to_canonical_dict(),
        "label_interval_start": canonical_datetime(values["label_interval_start"]),
        "label_interval_end": canonical_datetime(values["label_interval_end"]),
        "decision_reference_price": canonical_decimal(values["decision_reference_price"]),
        "checkpoint_price": _decimal_value(values["checkpoint_price"]),
        "checkpoint_return": _decimal_value(values["checkpoint_return"]),
        "mfe": _decimal_value(values["mfe"]),
        "mae": _decimal_value(values["mae"]),
        "barrier_passages": [
            {
                "barrier_id": barrier_id,
                "first_passage_at": None if at is None else canonical_datetime(at),
            }
            for barrier_id, at in values["barrier_passages"]
        ],
        "market_conditions": [item.value for item in values["market_conditions"]],
        "availability_status": values["availability_status"].value,
        "outcome_available_at": canonical_datetime(values["outcome_available_at"]),
        "reason_codes": list(values["reason_codes"]),
    }
    if values["schema_version"] == "target-outcome-label/v2":
        payload["barrier_ordering"] = values["barrier_ordering"].value
    return payload


def _settlement_value_names() -> tuple[str, ...]:
    return (
        "shadow_decision",
        "factual_outcome_v1",
        "source_dataset",
        "target_protocol_id",
        "target_protocol_hash",
        "next_session_date",
        "labels",
        "availability_status",
        "outcome_available_at",
        "created_at",
        "reason_codes",
        "limitations",
    )


def _settlement_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "targeted-shadow-outcome/v2",
        "shadow_decision": values["shadow_decision"].to_canonical_dict(),
        "factual_outcome_v1": values["factual_outcome_v1"].to_canonical_dict(),
        "source_dataset": values["source_dataset"].to_canonical_dict(),
        "target_protocol_id": str(values["target_protocol_id"]),
        "target_protocol_hash": values["target_protocol_hash"],
        "next_session_date": values["next_session_date"].isoformat(),
        "labels": [item.to_canonical_dict() for item in values["labels"]],
        "availability_status": values["availability_status"].value,
        "outcome_available_at": canonical_datetime(values["outcome_available_at"]),
        "created_at": canonical_datetime(values["created_at"]),
        "reason_codes": list(values["reason_codes"]),
        "limitations": list(values["limitations"]),
    }


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("reference must be an object")
    return RuntimeArtifactReference(
        reference_kind=str(value["reference_kind"]),
        artifact_id=ArtifactId(str(value["artifact_id"])),
        content_hash=str(value["content_hash"]),
    )


def _objects(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("expected object array")
    return tuple(value)


def _array(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return tuple(value)


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_instant(value: object) -> datetime | None:
    return None if value is None else _instant(value)


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("expected decimal")
    return parse_canonical_decimal("decimal", value)


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _decimal_value(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


__all__ = [
    "BarrierOrderingOutcome",
    "TargetOutcomeLabel",
    "TargetedShadowOutcome",
    "build_targeted_shadow_outcome",
]
