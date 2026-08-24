"""Summary-scoped T+1 factual Outcome engineering contract.

The calculation consumes the existing verified factual Outcome and raw-source
archive authorities.  It does not create a label, an Alpha result, or evidence
that an engineering fixture was prospective.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaPredictionSnapshot,
)
from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    OutcomeCompleteness,
    TradeHorizonOutcomeEvidence,
    TradeHorizonOutcomeObservation,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    OutcomeSettlementSourceArchive,
)
from market_regime_alpha.application.shadow_research.contracts import ShadowDecision
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
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


class OutcomeAvailabilityStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class SettlementSessionStatus(str, Enum):
    TRADING_DAY = "TRADING_DAY"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    UNKNOWN = "UNKNOWN"


class OutcomeMarketCondition(str, Enum):
    TRADING = "TRADING"
    SUSPENDED = "SUSPENDED"
    LIMIT_UP = "LIMIT_UP"
    LIMIT_DOWN = "LIMIT_DOWN"
    MISSING_QUOTE = "MISSING_QUOTE"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ShadowOutcomeObservation:
    observation_id: ArtifactId
    content_hash: str
    symbol: str
    decision_reference_price: Decimal
    next_open: Decimal | None
    price_0930: Decimal | None
    price_1000: Decimal | None
    price_1030: Decimal | None
    open_return: Decimal | None
    return_0930: Decimal | None
    return_1000: Decimal | None
    return_1030: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    first_passage_plus_1: datetime | None
    first_passage_plus_2: datetime | None
    first_passage_minus_1: datetime | None
    market_conditions: tuple[OutcomeMarketCondition, ...]
    availability_status: OutcomeAvailabilityStatus
    outcome_available_at: datetime
    reason_codes: tuple[str, ...]
    schema_version: str = "shadow-outcome-observation/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "shadow-outcome-observation/v1":
            raise ValueError("unsupported Shadow Outcome observation schema")
        require_sha256("content_hash", self.content_hash)
        if self.decision_reference_price <= 0:
            raise ValueError("Outcome decision reference price must be positive")
        _aware("outcome_available_at", self.outcome_available_at)
        if self.market_conditions != tuple(
            sorted(set(self.market_conditions), key=lambda item: item.value)
        ):
            raise ValueError("Outcome market conditions must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Outcome reasons must be unique and sorted")
        expected_returns = tuple(
            _return(value, self.decision_reference_price)
            for value in (
                self.next_open,
                self.price_0930,
                self.price_1000,
                self.price_1030,
            )
        )
        if expected_returns != (
            self.open_return,
            self.return_0930,
            self.return_1000,
            self.return_1030,
        ):
            raise ValueError("Outcome checkpoint returns do not match prices")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Shadow Outcome observation hash mismatch")
        if self.observation_id != _content_id(
            "shadow-outcome-observation", self.content_hash
        ):
            raise ValueError("Shadow Outcome observation identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ShadowOutcomeObservation:
        normalized = dict(values)
        normalized["market_conditions"] = tuple(
            sorted(set(values["market_conditions"]), key=lambda item: item.value)
        )
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        normalized["open_return"] = _return(
            values["next_open"], values["decision_reference_price"]
        )
        normalized["return_0930"] = _return(
            values["price_0930"], values["decision_reference_price"]
        )
        normalized["return_1000"] = _return(
            values["price_1000"], values["decision_reference_price"]
        )
        normalized["return_1030"] = _return(
            values["price_1030"], values["decision_reference_price"]
        )
        digest = canonical_hash(_observation_payload(**normalized))
        return cls(
            observation_id=_content_id("shadow-outcome-observation", digest),
            content_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _observation_payload(
            symbol=self.symbol,
            decision_reference_price=self.decision_reference_price,
            next_open=self.next_open,
            price_0930=self.price_0930,
            price_1000=self.price_1000,
            price_1030=self.price_1030,
            open_return=self.open_return,
            return_0930=self.return_0930,
            return_1000=self.return_1000,
            return_1030=self.return_1030,
            mfe=self.mfe,
            mae=self.mae,
            first_passage_plus_1=self.first_passage_plus_1,
            first_passage_plus_2=self.first_passage_plus_2,
            first_passage_minus_1=self.first_passage_minus_1,
            market_conditions=self.market_conditions,
            availability_status=self.availability_status,
            outcome_available_at=self.outcome_available_at,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ShadowOutcomeObservation:
        return cls(
            observation_id=ArtifactId(_text(payload["observation_id"])),
            content_hash=_text(payload["content_hash"]),
            symbol=_text(payload["symbol"]),
            decision_reference_price=_decimal(payload["decision_reference_price"]),
            next_open=_optional_decimal(payload["next_open"]),
            price_0930=_optional_decimal(payload["price_0930"]),
            price_1000=_optional_decimal(payload["price_1000"]),
            price_1030=_optional_decimal(payload["price_1030"]),
            open_return=_optional_decimal(payload["open_return"]),
            return_0930=_optional_decimal(payload["return_0930"]),
            return_1000=_optional_decimal(payload["return_1000"]),
            return_1030=_optional_decimal(payload["return_1030"]),
            mfe=_optional_decimal(payload["mfe"]),
            mae=_optional_decimal(payload["mae"]),
            first_passage_plus_1=_optional_instant(payload["first_passage_plus_1"]),
            first_passage_plus_2=_optional_instant(payload["first_passage_plus_2"]),
            first_passage_minus_1=_optional_instant(payload["first_passage_minus_1"]),
            market_conditions=tuple(
                OutcomeMarketCondition(_text(item))
                for item in _array(payload["market_conditions"])
            ),
            availability_status=OutcomeAvailabilityStatus(
                _text(payload["availability_status"])
            ),
            outcome_available_at=_instant(payload["outcome_available_at"]),
            reason_codes=tuple(
                _text(item) for item in _array(payload["reason_codes"])
            ),
            schema_version=_text(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ProspectiveShadowOutcome:
    settlement_id: ArtifactId
    settlement_hash: str
    shadow_decision: RuntimeArtifactReference
    shadow_session_id: ArtifactId
    run_id: ArtifactId
    tick_id: ArtifactId
    summary: RuntimeArtifactReference
    candidate_set: RuntimeArtifactReference | None
    signal: RuntimeArtifactReference | None
    forecast: RuntimeArtifactReference | None
    prediction_snapshot: RuntimeArtifactReference | None
    strategy_diagnostic: RuntimeArtifactReference | None
    model_selection_receipts: tuple[RuntimeArtifactReference, ...]
    source_archive: RuntimeArtifactReference
    source_dataset: RuntimeArtifactReference
    factual_evidence: RuntimeArtifactReference
    next_session_date: date
    session_status: SettlementSessionStatus
    observations: tuple[ShadowOutcomeObservation, ...]
    availability_status: OutcomeAvailabilityStatus
    outcome_available_at: datetime
    created_at: datetime
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    schema_version: str = "prospective-shadow-outcome/v2"

    def __post_init__(self) -> None:
        if self.schema_version not in {
            "prospective-shadow-outcome/v1",
            "prospective-shadow-outcome/v2",
        }:
            raise ValueError("unsupported Prospective Shadow Outcome schema")
        if self.schema_version == "prospective-shadow-outcome/v1":
            if self.prediction_snapshot is not None or self.strategy_diagnostic is not None:
                raise ValueError("Outcome v1 cannot carry Daily prediction lineage")
        elif (
            self.prediction_snapshot is None
            or self.prediction_snapshot.reference_kind
            != "DAILY_ALPHA_PREDICTION_SNAPSHOT"
            or self.strategy_diagnostic is None
            or self.strategy_diagnostic.reference_kind != "MULTI_STRATEGY_CYCLE"
        ):
            raise ValueError("Outcome v2 requires exact Daily prediction lineage")
        require_sha256("settlement_hash", self.settlement_hash)
        _aware("outcome_available_at", self.outcome_available_at)
        _aware("created_at", self.created_at)
        if self.created_at < self.outcome_available_at:
            raise ValueError("Outcome cannot be created before it is available")
        symbols = tuple(item.symbol for item in self.observations)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Outcome observations must be symbol-sorted and unique")
        if self.model_selection_receipts != _sorted_references(
            self.model_selection_receipts
        ):
            raise ValueError("Outcome model receipts must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Outcome reasons must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Outcome limitations must be unique and sorted")
        required = {
            "ENGINEERING_RECORDED_ONLY",
            "FACTUAL_OBSERVATION_ONLY",
            "NOT_ALPHA_VALIDATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Outcome engineering authority ceiling is incomplete")
        if canonical_hash(self.semantic_payload()) != self.settlement_hash:
            raise ValueError("Prospective Shadow Outcome hash mismatch")
        if self.settlement_id != _content_id(
            "prospective-shadow-outcome", self.settlement_hash
        ):
            raise ValueError("Prospective Shadow Outcome identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ProspectiveShadowOutcome:
        normalized = dict(values)
        normalized.setdefault("schema_version", "prospective-shadow-outcome/v2")
        normalized["observations"] = tuple(
            sorted(values["observations"], key=lambda item: item.symbol)
        )
        normalized["model_selection_receipts"] = _sorted_references(
            values["model_selection_receipts"]
        )
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        normalized["limitations"] = tuple(sorted(set(values["limitations"])))
        digest = canonical_hash(_settlement_payload(**normalized))
        return cls(
            settlement_id=_content_id("prospective-shadow-outcome", digest),
            settlement_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _settlement_payload(
            shadow_decision=self.shadow_decision,
            shadow_session_id=self.shadow_session_id,
            run_id=self.run_id,
            tick_id=self.tick_id,
            summary=self.summary,
            candidate_set=self.candidate_set,
            signal=self.signal,
            forecast=self.forecast,
            prediction_snapshot=self.prediction_snapshot,
            strategy_diagnostic=self.strategy_diagnostic,
            model_selection_receipts=self.model_selection_receipts,
            source_archive=self.source_archive,
            source_dataset=self.source_dataset,
            factual_evidence=self.factual_evidence,
            next_session_date=self.next_session_date,
            session_status=self.session_status,
            observations=self.observations,
            availability_status=self.availability_status,
            outcome_available_at=self.outcome_available_at,
            created_at=self.created_at,
            reason_codes=self.reason_codes,
            limitations=self.limitations,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "settlement_id": str(self.settlement_id),
            "settlement_hash": self.settlement_hash,
            **self.semantic_payload(),
            "authority": {
                "engineering_recorded_only": True,
                "prospective_proven": False,
                "alpha_validated": False,
            },
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ProspectiveShadowOutcome:
        authority = _mapping(payload["authority"])
        if authority != {
            "engineering_recorded_only": True,
            "prospective_proven": False,
            "alpha_validated": False,
        }:
            raise ValueError("Outcome authority declaration mismatch")
        return cls(
            settlement_id=ArtifactId(_text(payload["settlement_id"])),
            settlement_hash=_text(payload["settlement_hash"]),
            shadow_decision=_reference(payload["shadow_decision"]),
            shadow_session_id=ArtifactId(_text(payload["shadow_session_id"])),
            run_id=ArtifactId(_text(payload["run_id"])),
            tick_id=ArtifactId(_text(payload["tick_id"])),
            summary=_reference(payload["summary"]),
            candidate_set=_optional_reference(payload["candidate_set"]),
            signal=_optional_reference(payload["signal"]),
            forecast=_optional_reference(payload["forecast"]),
            prediction_snapshot=_optional_reference(
                payload.get("prediction_snapshot")
            ),
            strategy_diagnostic=_optional_reference(
                payload.get("strategy_diagnostic")
            ),
            model_selection_receipts=tuple(
                _reference(item) for item in _array(payload["model_selection_receipts"])
            ),
            source_archive=_reference(payload["source_archive"]),
            source_dataset=_reference(payload["source_dataset"]),
            factual_evidence=_reference(payload["factual_evidence"]),
            next_session_date=date.fromisoformat(_text(payload["next_session_date"])),
            session_status=SettlementSessionStatus(_text(payload["session_status"])),
            observations=tuple(
                ShadowOutcomeObservation.from_canonical_dict(_mapping(item))
                for item in _array(payload["observations"])
            ),
            availability_status=OutcomeAvailabilityStatus(
                _text(payload["availability_status"])
            ),
            outcome_available_at=_instant(payload["outcome_available_at"]),
            created_at=_instant(payload["created_at"]),
            reason_codes=tuple(
                _text(item) for item in _array(payload["reason_codes"])
            ),
            limitations=tuple(
                _text(item) for item in _array(payload["limitations"])
            ),
            schema_version=_text(payload["schema_version"]),
        )


def build_prospective_shadow_outcome(
    *,
    decision: ShadowDecision,
    prediction_snapshot: DailyAlphaPredictionSnapshot | None,
    source_archive: OutcomeSettlementSourceArchive,
    settlement_dataset: VerifiedMarketDataDataset,
    factual_evidence: TradeHorizonOutcomeEvidence,
    next_session_date: date,
    session_status: SettlementSessionStatus,
    created_at: datetime,
    schema_version: str = "prospective-shadow-outcome/v2",
) -> ProspectiveShadowOutcome:
    """Derive checkpoint facts from verified artifacts, never caller metrics."""

    if schema_version == "prospective-shadow-outcome/v2":
        if prediction_snapshot is None:
            raise ValueError("Outcome v2 requires a Daily prediction owner")
        prediction_snapshot.verify_identity()
        if (
            prediction_snapshot.run_reference.artifact_id != decision.run_id
            or prediction_snapshot.tick_reference.artifact_id != decision.tick_id
            or prediction_snapshot.trading_date != decision.trading_date
            or prediction_snapshot.decision_time != decision.decision_time
            or prediction_snapshot.candidate_reference != decision.candidate_set
            or prediction_snapshot.signal_reference != decision.signal
            or decision.forecast not in prediction_snapshot.forecast_references
            or prediction_snapshot.target_session_date != next_session_date
        ):
            raise ValueError(
                "Outcome Daily prediction lineage differs from frozen Decision"
            )
        if prediction_snapshot.available_at > decision.decision_frozen_at:
            raise ValueError("Daily prediction was unavailable at Shadow Decision freeze")
    elif schema_version != "prospective-shadow-outcome/v1" or prediction_snapshot is not None:
        raise ValueError("legacy Outcome build requires v1 without Daily prediction")
    if factual_evidence.operation_package_id != decision.controlled_operation.artifact_id:
        raise ValueError("Outcome Controlled Operation identity mismatch")
    if factual_evidence.operation_package_hash != decision.controlled_operation.content_hash:
        raise ValueError("Outcome Controlled Operation hash mismatch")
    if (
        factual_evidence.source_dataset_id
        != ArtifactId(str(settlement_dataset.artifact.dataset_id))
        or factual_evidence.source_dataset_hash
        != settlement_dataset.artifact.content_hash
    ):
        raise ValueError("Outcome settlement Dataset lineage mismatch")
    if source_archive.next_session_date != next_session_date:
        raise ValueError("Outcome source archive session date mismatch")
    if (source_archive.source_manifest_id, source_archive.source_manifest_hash) not in (
        settlement_dataset.artifact.source_manifest_references
    ):
        raise ValueError("Outcome source archive is not bound to settlement Dataset")
    if next_session_date <= decision.trading_date:
        raise ValueError("Outcome session must follow Shadow Decision date")
    by_symbol = {item.symbol: item for item in factual_evidence.observations}
    bars = tuple(settlement_dataset.artifact.iter_bars())
    observations = tuple(
        _extend_observation(
            factual=item,
            bars=bars,
            session_status=session_status,
        )
        for item in sorted(by_symbol.values(), key=lambda item: item.symbol)
    )
    availability = max(
        (source_archive.created_at, *(item.outcome_available_at for item in observations))
    )
    if availability <= decision.decision_frozen_at:
        raise ValueError("Outcome must become available after frozen Shadow Decision")
    if (
        prediction_snapshot is not None
        and availability <= prediction_snapshot.available_at
    ):
        raise ValueError("Outcome must become available after Daily prediction")
    if created_at < availability:
        raise ValueError("Outcome creation predates evidence availability")
    if not observations:
        overall = (
            OutcomeAvailabilityStatus.UNAVAILABLE
            if session_status is not SettlementSessionStatus.TRADING_DAY
            else OutcomeAvailabilityStatus.COMPLETE
        )
    elif all(
        item.availability_status is OutcomeAvailabilityStatus.COMPLETE
        for item in observations
    ):
        overall = OutcomeAvailabilityStatus.COMPLETE
    elif all(
        item.availability_status is OutcomeAvailabilityStatus.UNAVAILABLE
        for item in observations
    ):
        overall = OutcomeAvailabilityStatus.UNAVAILABLE
    else:
        overall = OutcomeAvailabilityStatus.PARTIAL
    reasons = {
        f"OUTCOME_{overall.value}",
        "ENGINEERING_RECORDED_ONLY",
        *("NO_CANDIDATE_OUTCOME" for _ in ((),) if not observations),
    }
    return ProspectiveShadowOutcome.create(
        shadow_decision=RuntimeArtifactReference(
            "SHADOW_DECISION", decision.decision_id, decision.decision_hash
        ),
        shadow_session_id=decision.session_id,
        run_id=decision.run_id,
        tick_id=decision.tick_id,
        summary=decision.summary,
        candidate_set=decision.candidate_set,
        signal=decision.signal,
        forecast=decision.forecast,
        prediction_snapshot=(
            None if prediction_snapshot is None else prediction_snapshot.reference
        ),
        strategy_diagnostic=(
            None
            if prediction_snapshot is None
            else prediction_snapshot.strategy_diagnostic_reference
        ),
        model_selection_receipts=decision.model_selection_receipts,
        source_archive=RuntimeArtifactReference(
            "OUTCOME_SOURCE_ARCHIVE",
            source_archive.artifact_id,
            source_archive.content_hash,
        ),
        source_dataset=RuntimeArtifactReference(
            "OUTCOME_DATASET",
            ArtifactId(str(settlement_dataset.artifact.dataset_id)),
            settlement_dataset.artifact.content_hash,
        ),
        factual_evidence=RuntimeArtifactReference(
            "FACTUAL_OUTCOME_EVIDENCE",
            factual_evidence.artifact_id,
            factual_evidence.content_hash,
        ),
        next_session_date=next_session_date,
        session_status=session_status,
        observations=observations,
        availability_status=overall,
        outcome_available_at=availability,
        created_at=created_at,
        reason_codes=tuple(sorted(reasons)),
        limitations=(
            "ENGINEERING_RECORDED_ONLY",
            "FACTUAL_OBSERVATION_ONLY",
            "NOT_ALPHA_VALIDATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        ),
        schema_version=schema_version,
    )


def _extend_observation(
    *,
    factual: TradeHorizonOutcomeObservation,
    bars: tuple[CanonicalMarketBar, ...],
    session_status: SettlementSessionStatus,
) -> ShadowOutcomeObservation:
    zone = ZoneInfo(factual.horizon.timezone_name)
    selected = tuple(
        sorted(
            (
                item
                for item in bars
                if item.symbol == factual.symbol
                and item.market_date == factual.next_session_date
            ),
            key=lambda item: item.event_start,
        )
    )
    minutes = tuple(item for item in selected if item.timeframe is Timeframe.MINUTE_1)
    price_0930 = factual.next_open
    price_1000 = _complete_checkpoint(minutes, zone=zone, checkpoint=time(10, 0))
    price_1030 = factual.next_1030_price
    conditions: set[OutcomeMarketCondition] = set()
    reasons = set(factual.reason_codes)
    if session_status is SettlementSessionStatus.NON_TRADING_DAY:
        conditions.add(OutcomeMarketCondition.NON_TRADING_DAY)
    if not selected:
        conditions.add(OutcomeMarketCondition.UNAVAILABLE)
    if any(item.trading_status is TradingStatus.SUSPENDED for item in selected):
        conditions.add(OutcomeMarketCondition.SUSPENDED)
    if any(item.price_limit_state is PriceLimitState.LIMIT_UP for item in selected):
        conditions.add(OutcomeMarketCondition.LIMIT_UP)
    if any(item.price_limit_state is PriceLimitState.LIMIT_DOWN for item in selected):
        conditions.add(OutcomeMarketCondition.LIMIT_DOWN)
    if any(
        item.adjustment_mode is not AdjustmentMode.RAW
        or item.adjustment_factor != Decimal("1")
        for item in selected
    ):
        conditions.add(OutcomeMarketCondition.CORPORATE_ACTION)
        reasons.add("CORPORATE_ACTION_OBSERVED")
    if price_0930 is None or price_1000 is None or price_1030 is None:
        conditions.add(OutcomeMarketCondition.MISSING_QUOTE)
        reasons.add("CHECKPOINT_QUOTE_MISSING")
    if not conditions:
        conditions.add(OutcomeMarketCondition.TRADING)
    available = factual.availability_time or max(
        (item.available_at for item in selected),
        default=factual.decision_time,
    )
    if not selected and available <= factual.decision_time:
        # The explicitly archived attempt is the factual availability for an
        # unavailable result; callers still must ensure it follows the freeze.
        available = factual.decision_time
    status = (
        OutcomeAvailabilityStatus.COMPLETE
        if factual.completeness is OutcomeCompleteness.COMPLETE
        and price_1000 is not None
        else OutcomeAvailabilityStatus.UNAVAILABLE
        if not selected or session_status is SettlementSessionStatus.NON_TRADING_DAY
        else OutcomeAvailabilityStatus.PARTIAL
    )
    return ShadowOutcomeObservation.create(
        symbol=factual.symbol,
        decision_reference_price=factual.decision_reference_price,
        next_open=factual.next_open,
        price_0930=price_0930,
        price_1000=price_1000,
        price_1030=price_1030,
        mfe=factual.mfe,
        mae=factual.mae,
        first_passage_plus_1=_first_passage(
            minutes, factual.decision_reference_price, Decimal("0.01"), True
        ),
        first_passage_plus_2=_first_passage(
            minutes, factual.decision_reference_price, Decimal("0.02"), True
        ),
        first_passage_minus_1=_first_passage(
            minutes, factual.decision_reference_price, Decimal("0.01"), False
        ),
        market_conditions=tuple(conditions),
        availability_status=status,
        outcome_available_at=available,
        reason_codes=tuple(reasons),
    )


def _complete_checkpoint(
    bars: tuple[CanonicalMarketBar, ...],
    *,
    zone: ZoneInfo,
    checkpoint: time,
) -> Decimal | None:
    eligible = tuple(
        item
        for item in bars
        if time(9, 30)
        <= item.event_start.astimezone(zone).time().replace(tzinfo=None)
        and item.event_end.astimezone(zone).time().replace(tzinfo=None)
        <= checkpoint
    )
    expected = int(
        (
            datetime.combine(date.min, checkpoint)
            - datetime.combine(date.min, time(9, 30))
        ).total_seconds()
        // 60
    )
    if len(eligible) != expected or not eligible:
        return None
    if eligible[-1].event_end.astimezone(zone).time().replace(tzinfo=None) != checkpoint:
        return None
    if any(
        left.event_end != right.event_start
        for left, right in zip(eligible, eligible[1:], strict=False)
    ):
        return None
    return eligible[-1].close


def _first_passage(
    bars: tuple[CanonicalMarketBar, ...],
    reference: Decimal,
    threshold: Decimal,
    upward: bool,
) -> datetime | None:
    boundary = reference * (Decimal("1") + threshold if upward else Decimal("1") - threshold)
    for item in bars:
        if (upward and item.high >= boundary) or (not upward and item.low <= boundary):
            return item.event_end
    return None


def _return(value: Decimal | None, reference: Decimal) -> Decimal | None:
    return None if value is None else (value - reference) / reference


def _observation_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "shadow-outcome-observation/v1",
        "symbol": values["symbol"],
        "decision_reference_price": canonical_decimal(values["decision_reference_price"]),
        "next_open": _decimal_value(values["next_open"]),
        "price_0930": _decimal_value(values["price_0930"]),
        "price_1000": _decimal_value(values["price_1000"]),
        "price_1030": _decimal_value(values["price_1030"]),
        "open_return": _decimal_value(values["open_return"]),
        "return_0930": _decimal_value(values["return_0930"]),
        "return_1000": _decimal_value(values["return_1000"]),
        "return_1030": _decimal_value(values["return_1030"]),
        "mfe": _decimal_value(values["mfe"]),
        "mae": _decimal_value(values["mae"]),
        "first_passage_plus_1": _instant_value(values["first_passage_plus_1"]),
        "first_passage_plus_2": _instant_value(values["first_passage_plus_2"]),
        "first_passage_minus_1": _instant_value(values["first_passage_minus_1"]),
        "market_conditions": [item.value for item in values["market_conditions"]],
        "availability_status": values["availability_status"].value,
        "outcome_available_at": canonical_datetime(values["outcome_available_at"]),
        "reason_codes": list(values["reason_codes"]),
    }


def _settlement_payload(**values: Any) -> dict[str, Any]:
    schema_version = values["schema_version"]
    payload = {
        "schema_version": schema_version,
        "shadow_decision": values["shadow_decision"].to_canonical_dict(),
        "shadow_session_id": str(values["shadow_session_id"]),
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "summary": values["summary"].to_canonical_dict(),
        "candidate_set": _optional_reference_dict(values["candidate_set"]),
        "signal": _optional_reference_dict(values["signal"]),
        "forecast": _optional_reference_dict(values["forecast"]),
        "model_selection_receipts": [
            item.to_canonical_dict() for item in values["model_selection_receipts"]
        ],
        "source_archive": values["source_archive"].to_canonical_dict(),
        "source_dataset": values["source_dataset"].to_canonical_dict(),
        "factual_evidence": values["factual_evidence"].to_canonical_dict(),
        "next_session_date": values["next_session_date"].isoformat(),
        "session_status": values["session_status"].value,
        "observations": [item.to_canonical_dict() for item in values["observations"]],
        "availability_status": values["availability_status"].value,
        "outcome_available_at": canonical_datetime(values["outcome_available_at"]),
        "created_at": canonical_datetime(values["created_at"]),
        "reason_codes": list(values["reason_codes"]),
        "limitations": list(values["limitations"]),
    }
    if schema_version == "prospective-shadow-outcome/v2":
        payload["prediction_snapshot"] = _optional_reference_dict(
            values["prediction_snapshot"]
        )
        payload["strategy_diagnostic"] = _optional_reference_dict(
            values["strategy_diagnostic"]
        )
    return payload


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _sorted_references(
    values: tuple[RuntimeArtifactReference, ...]
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _optional_reference_dict(
    value: RuntimeArtifactReference | None,
) -> dict[str, str] | None:
    return None if value is None else value.to_canonical_dict()


def _reference(value: object) -> RuntimeArtifactReference:
    return RuntimeArtifactReference.from_canonical_dict(_mapping(value))


def _optional_reference(value: object) -> RuntimeArtifactReference | None:
    return None if value is None else _reference(value)


def _decimal_value(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("decimal must be canonical text")
    return parse_canonical_decimal("outcome decimal", value)


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _instant_value(value: datetime | None) -> str | None:
    return None if value is None else canonical_datetime(value)


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _aware("timestamp", result)
    return result


def _optional_instant(value: object) -> datetime | None:
    return None if value is None else _instant(value)


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("value must be non-empty text")
    return value


def _array(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("value must be an array")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("value must be an object")
    return value


__all__ = [
    "OutcomeAvailabilityStatus",
    "OutcomeMarketCondition",
    "ProspectiveShadowOutcome",
    "SettlementSessionStatus",
    "ShadowOutcomeObservation",
    "build_prospective_shadow_outcome",
]
