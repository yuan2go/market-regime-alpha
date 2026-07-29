"""EXPLORATORY daily Universe/Eligibility adapters over canonical contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from statistics import median
import re
from typing import Any, Mapping

from market_regime_alpha.candidates.contracts import (
    CandidatePopulation,
    build_candidate_population,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, RetrievedAt
from market_regime_alpha.data.contracts import (
    DataEligibility,
    DatasetContract,
    ProviderReference,
)
from market_regime_alpha.data.providers.public_composite import (
    AcquiredSourcePayload,
    PublicCompositeProviderResult,
    TradingStatus,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
)
from market_regime_alpha.universe.eligibility_artifacts import (
    HistoricalTradingEligibilityRecord,
    build_historical_trading_eligibility_artifact,
)


SMOKE_POOL_SYMBOLS = tuple(
    sorted(
        (
            "601919.SH",
            "601088.SH",
            "601225.SH",
            "600900.SH",
            "600886.SH",
            "601398.SH",
            "601939.SH",
            "601288.SH",
            "600036.SH",
            "600941.SH",
            "601728.SH",
            "600050.SH",
            "600018.SH",
            "001872.SZ",
            "600377.SH",
            "001965.SZ",
            "601006.SH",
            "600028.SH",
            "601857.SH",
            "002714.SZ",
        )
    )
)
_A_SHARE_SYMBOL = re.compile(r"^\d{6}\.(SH|SZ)$")


class DailyEligibilityReason(str, Enum):
    NOT_IN_FIXED_UNIVERSE = "NOT_IN_FIXED_UNIVERSE"
    SUSPENDED = "SUSPENDED"
    TRADING_STATUS_UNKNOWN = "TRADING_STATUS_UNKNOWN"
    ST_STATUS_UNKNOWN = "ST_STATUS_UNKNOWN"
    LISTING_STATUS_UNKNOWN = "LISTING_STATUS_UNKNOWN"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    QUOTE_STALE = "QUOTE_STALE"
    PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
    MAPPING_UNKNOWN = "MAPPING_UNKNOWN"


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DailyUniversePolicy:
    """Versioned configuration that materializes existing Universe contracts."""

    SCHEMA_VERSION = "daily-universe-policy-v1"

    name: str
    version: str
    symbols: tuple[str, ...]
    minimum_history_sessions: int
    minimum_median_daily_amount: float
    instrument_scope: str = field(init=False, default="A_SHARE_STOCK")
    data_eligibility: DataEligibility = field(
        init=False,
        default=DataEligibility.EXPLORATORY,
    )
    content_hash: str = field(init=False)
    policy_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        for label, value in (("name", self.name), ("version", self.version)):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        if not self.symbols or tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("symbols must be non-empty, unique, and ordered")
        if any(_A_SHARE_SYMBOL.fullmatch(symbol) is None for symbol in self.symbols):
            raise ValueError("daily Universe supports only normalized A-share stocks")
        if (
            isinstance(self.minimum_history_sessions, bool)
            or self.minimum_history_sessions < 1
        ):
            raise ValueError("minimum_history_sessions must be positive")
        if (
            isinstance(self.minimum_median_daily_amount, bool)
            or self.minimum_median_daily_amount <= 0
        ):
            raise ValueError("minimum_median_daily_amount must be positive")
        content_hash = _canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "policy_id",
            ArtifactId(f"universe-policy-{content_hash.split(':', 1)[1][:24]}"),
        )

    @property
    def policy_version(self) -> str:
        return f"{self.name}@{self.version}"

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "name": self.name,
            "version": self.version,
            "symbols": list(self.symbols),
            "minimum_history_sessions": self.minimum_history_sessions,
            "minimum_median_daily_amount": float(
                self.minimum_median_daily_amount
            ),
            "instrument_scope": self.instrument_scope,
            "data_eligibility": self.data_eligibility.value,
        }


def smoke_pool_policy_v1() -> DailyUniversePolicy:
    """Return the frozen 20-symbol exploratory pipeline-validation pool."""

    return DailyUniversePolicy(
        name="a-share-smoke-pool",
        version="v1",
        symbols=SMOKE_POOL_SYMBOLS,
        minimum_history_sessions=21,
        minimum_median_daily_amount=10_000_000.0,
    )


@dataclass(frozen=True, slots=True)
class DailyUniverseDecision:
    symbol: str
    member: bool
    status: TradingEligibilityStatus
    reasons: tuple[str, ...]


DAILY_ELIGIBILITY_POLICY_AUTHORITY_ID = ProviderId(
    "authority-daily-eligibility-policy"
)


@dataclass(frozen=True, slots=True)
class DailyEligibilitySourceEvidence:
    """Immutable policy decisions over explicit SourceManifest inputs."""

    raw_payloads: tuple[AcquiredSourcePayload, ...]
    fields: tuple[SourceManifestField, ...]


def build_daily_eligibility_source_evidence(
    *,
    policy: DailyUniversePolicy,
    source_manifest: SourceManifest,
    provider_result: PublicCompositeProviderResult,
    retrieved_time: RetrievedAt,
) -> DailyEligibilitySourceEvidence:
    """Materialize policy-owned eligibility without claiming Provider authority."""

    decisions = _evaluate_daily_policy_inputs(
        policy=policy,
        source_manifest=source_manifest,
        provider_result=provider_result,
    )
    payload = AcquiredSourcePayload(
        provider_id=DAILY_ELIGIBILITY_POLICY_AUTHORITY_ID,
        product="daily-eligibility-policy-evidence-v1",
        locator=f"policy://eligibility/{policy.policy_version}",
        raw_payload=json.dumps(
            {
                "schema_version": "daily-eligibility-policy-evidence-v1",
                "policy_id": str(policy.policy_id),
                "policy_hash": policy.content_hash,
                "policy_version": policy.policy_version,
                "source_manifest_id": str(source_manifest.source_manifest_id),
                "source_manifest_hash": source_manifest.content_hash,
                "decision_date": (
                    provider_result.decision_time.value.date().isoformat()
                ),
                "decisions": [
                    {
                        "symbol": item.symbol,
                        "member": item.member,
                        "status": item.status.value,
                        "reasons": list(item.reasons),
                    }
                    for item in decisions
                ],
                "data_eligibility": DataEligibility.EXPLORATORY.value,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        retrieved_time=retrieved_time,
        limitations=(
            "ELIGIBILITY_POLICY_DECISION_NOT_PROVIDER_MARKET_DATA",
            "PUBLIC_STATUS_METADATA_NOT_QUALIFIED",
            "FORMAL_PIT_NOT_ESTABLISHED",
        ),
    )
    fields = tuple(
        SourceManifestField(
            field_id="eligibility",
            symbol=item.symbol,
            critical_fact=CriticalSourceFact.ELIGIBILITY,
            provider_id=payload.provider_id,
            source_artifact_id=payload.source_artifact_id,
            event_time=provider_result.decision_time.value,
            available_time=AvailabilityTime(provider_result.decision_time.value),
            retrieved_time=retrieved_time,
            decision_time=provider_result.decision_time,
            unit="POLICY_DECISION",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.FINAL,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=(
                SourceFieldQualityStatus.COMPLETE
                if item.status is TradingEligibilityStatus.ELIGIBLE
                else (
                    SourceFieldQualityStatus.DEGRADED
                    if item.status is TradingEligibilityStatus.INELIGIBLE
                    else SourceFieldQualityStatus.INSUFFICIENT
                )
            ),
            reason_codes=(
                ()
                if item.status is TradingEligibilityStatus.ELIGIBLE
                else item.reasons or ("ELIGIBILITY_UNKNOWN",)
            ),
            schema_version=SourceManifestField.SCHEMA_V2,
            authority_kind=SourceAuthorityKind.ELIGIBILITY_POLICY,
            value=item.status.value,
        )
        for item in decisions
    )
    return DailyEligibilitySourceEvidence(
        raw_payloads=(payload,),
        fields=fields,
    )


@dataclass(frozen=True, slots=True)
class DailyUniverseReconciliation:
    policy: DailyUniversePolicy
    dataset_contract: DatasetContract
    universe_snapshot: PITUniverseSnapshot
    eligibility_snapshot: TradingEligibilitySnapshot
    population: CandidatePopulation
    decisions: tuple[DailyUniverseDecision, ...]


def reconcile_daily_universe(
    *,
    policy: DailyUniversePolicy,
    source_manifest: SourceManifest,
    provider_result: PublicCompositeProviderResult,
) -> DailyUniverseReconciliation:
    """Account for every observed/configured symbol using existing PIT contracts."""

    if source_manifest.decision_time != provider_result.decision_time:
        raise ValueError("SourceManifest and ProviderResult Decision Time mismatch")
    if source_manifest.provider_profile_id != provider_result.profile_id:
        raise ValueError("SourceManifest and ProviderResult profile mismatch")
    result_artifacts = {
        item.source_artifact_id for item in provider_result.raw_payloads
    }
    if not result_artifacts.issubset(
        {item.artifact_id for item in source_manifest.source_artifacts}
    ):
        raise ValueError("SourceManifest omits ProviderResult source evidence")
    if source_manifest.schema_version == SourceManifest.SCHEMA_V2:
        decisions = _decisions_from_policy_evidence(
            policy=policy,
            source_manifest=source_manifest,
            provider_result=provider_result,
        )
    else:
        decisions = _evaluate_daily_policy_inputs(
            policy=policy,
            source_manifest=source_manifest,
            provider_result=provider_result,
        )
    source_dataset_id = _source_dataset_id(source_manifest, policy)
    universe_artifact = build_historical_pit_universe_artifact(
        source_dataset_id=source_dataset_id,
        method_version=policy.policy_version,
        timezone_name="Asia/Shanghai",
        effective_time_convention=(
            "EXPLICIT_DAILY_FIXED_POLICY_AT_LOCAL_DATE_EXPLORATORY"
        ),
        records=tuple(
            HistoricalUniverseMembershipRecord(
                as_of_date=provider_result.decision_time.value.date(),
                symbol=item.symbol,
                is_member=item.member,
            )
            for item in decisions
        ),
    )
    universe_snapshot = universe_artifact.snapshot_for_decision_time(
        provider_result.decision_time
    )
    eligibility_artifact = build_historical_trading_eligibility_artifact(
        source_dataset_id=source_dataset_id,
        policy_version=policy.policy_version,
        policy_artifact_id=policy.policy_id,
        materializer_version="daily-exploratory-reconciliation-v1",
        raw_evidence_convention=(
            "EXACT_SOURCE_MANIFEST_FACTS_AT_DECISION_TIME"
        ),
        records=tuple(
            HistoricalTradingEligibilityRecord(
                as_of=AsOfTime(provider_result.decision_time.value),
                symbol=item.symbol,
                status=item.status,
                reasons=item.reasons,
            )
            for item in decisions
        ),
    )
    eligibility_snapshot = eligibility_artifact.snapshot_for_decision_time(
        provider_result.decision_time
    )
    population = build_candidate_population(
        universe_snapshot,
        eligibility_snapshot,
        decision_time=provider_result.decision_time,
    )
    provider_references = tuple(
        dict.fromkeys(
            ProviderReference(
                provider_id=item.provider_id,
                product=item.product,
                contract_version="public-composite-v1",
            )
            for item in provider_result.raw_payloads
        )
    )
    dataset_contract = DatasetContract(
        dataset_id=source_dataset_id,
        schema_version="daily-public-source-dataset-v1",
        eligibility=DataEligibility.EXPLORATORY,
        manifest_artifact_id=source_manifest.source_manifest_id,
        provider_references=provider_references,
        pit_correct_for_scope=False,
        scope="20-symbol A-share exploratory daily loop",
        limitations=(
            *source_manifest.limitations,
            "FORMAL_PIT_NOT_ESTABLISHED",
        ),
    )
    return DailyUniverseReconciliation(
        policy=policy,
        dataset_contract=dataset_contract,
        universe_snapshot=universe_snapshot,
        eligibility_snapshot=eligibility_snapshot,
        population=population,
        decisions=tuple(decisions),
    )


def _evaluate_daily_policy_inputs(
    *,
    policy: DailyUniversePolicy,
    source_manifest: SourceManifest,
    provider_result: PublicCompositeProviderResult,
) -> tuple[DailyUniverseDecision, ...]:
    """Evaluate explicit Provider/policy inputs before policy evidence is frozen."""

    observed_symbols = {
        *(item.symbol for item in provider_result.bars),
        *(item.symbol for item in provider_result.quotes),
    }
    all_symbols = tuple(sorted(set(policy.symbols) | observed_symbols))
    field_by_fact = {
        (item.symbol, item.critical_fact): item
        for item in source_manifest.fields
        if item.symbol is not None and item.critical_fact is not None
    }
    quote_by_symbol = {item.symbol: item for item in provider_result.quotes}
    bars_by_symbol = {
        symbol: tuple(
            sorted(
                (
                    item
                    for item in provider_result.bars
                    if item.symbol == symbol
                ),
                key=lambda item: item.event_time,
            )
        )
        for symbol in all_symbols
    }
    decisions: list[DailyUniverseDecision] = []
    for symbol in all_symbols:
        member = symbol in policy.symbols
        reasons: list[str] = []
        if _A_SHARE_SYMBOL.fullmatch(symbol) is None:
            reasons.append(DailyEligibilityReason.MAPPING_UNKNOWN.value)
        if not member:
            reasons.append(DailyEligibilityReason.NOT_IN_FIXED_UNIVERSE.value)
        if member:
            quote = quote_by_symbol.get(symbol)
            price_field = field_by_fact.get((symbol, CriticalSourceFact.PRICE))
            trading_field = field_by_fact.get(
                (symbol, CriticalSourceFact.TRADING_STATUS)
            )
            history_field = field_by_fact.get(
                (symbol, CriticalSourceFact.HISTORY_WINDOW)
            )
            if (
                quote is None
                or quote.price is None
                or price_field is None
                or price_field.quality_status
                is SourceFieldQualityStatus.INSUFFICIENT
                or not _fact_available_at_decision(
                    price_field,
                    source_manifest,
                )
            ):
                reasons.append(DailyEligibilityReason.PRICE_UNAVAILABLE.value)
            elif "QUOTE_STALE" in price_field.reason_codes:
                reasons.append(DailyEligibilityReason.QUOTE_STALE.value)
            if (
                (
                    source_manifest.schema_version
                    == SourceManifest.SCHEMA_V2
                    and trading_field is not None
                    and trading_field.value == TradingStatus.SUSPENDED.value
                )
                or (
                    source_manifest.schema_version
                    == SourceManifest.SCHEMA_V1
                    and quote is not None
                    and quote.trading_status is TradingStatus.SUSPENDED
                )
            ):
                reasons.append(DailyEligibilityReason.SUSPENDED.value)
            if (
                trading_field is None
                or trading_field.quality_status
                is SourceFieldQualityStatus.INSUFFICIENT
                or not _fact_available_at_decision(
                    trading_field,
                    source_manifest,
                )
                or (
                    source_manifest.schema_version
                    == SourceManifest.SCHEMA_V2
                    and trading_field.value
                    not in {
                        TradingStatus.TRADING.value,
                        TradingStatus.SUSPENDED.value,
                    }
                )
            ):
                reasons.append(
                    (
                        DailyEligibilityReason.TRADING_STATUS_UNKNOWN.value
                        if source_manifest.schema_version
                        == SourceManifest.SCHEMA_V2
                        else DailyEligibilityReason.ST_STATUS_UNKNOWN.value
                    )
                )
            if source_manifest.schema_version == SourceManifest.SCHEMA_V2:
                st_field = field_by_fact.get(
                    (symbol, CriticalSourceFact.ST_STATUS)
                )
                listing_field = field_by_fact.get(
                    (symbol, CriticalSourceFact.LISTING_STATUS)
                )
                if (
                    st_field is None
                    or st_field.quality_status
                    is SourceFieldQualityStatus.INSUFFICIENT
                    or not _fact_available_at_decision(
                        st_field,
                        source_manifest,
                    )
                    or st_field.value != "NOT_ST"
                ):
                    reasons.append(DailyEligibilityReason.ST_STATUS_UNKNOWN.value)
                if (
                    listing_field is None
                    or listing_field.quality_status
                    is SourceFieldQualityStatus.INSUFFICIENT
                    or not _fact_available_at_decision(
                        listing_field,
                        source_manifest,
                    )
                    or listing_field.value != "LISTED"
                ):
                    reasons.append(
                        DailyEligibilityReason.LISTING_STATUS_UNKNOWN.value
                    )
            if (
                history_field is None
                or history_field.quality_status
                is SourceFieldQualityStatus.INSUFFICIENT
                or (
                    history_field.event_time is not None
                    and history_field.event_time
                    > source_manifest.decision_time.value
                )
                or history_field.retrieved_time.as_utc()
                > source_manifest.decision_time.as_utc()
            ):
                reasons.append(DailyEligibilityReason.INSUFFICIENT_HISTORY.value)
            daily_amounts = _daily_amounts(bars_by_symbol[symbol])
            if (
                len(daily_amounts) >= policy.minimum_history_sessions
                and median(daily_amounts[-20:])
                < policy.minimum_median_daily_amount
            ):
                reasons.append(
                    DailyEligibilityReason.INSUFFICIENT_LIQUIDITY.value
                )
        unique_reasons = tuple(dict.fromkeys(reasons))
        decisions.append(
            DailyUniverseDecision(
                symbol=symbol,
                member=member,
                status=(
                    TradingEligibilityStatus.ELIGIBLE
                    if not unique_reasons
                    else TradingEligibilityStatus.INELIGIBLE
                ),
                reasons=unique_reasons,
            )
        )
    return tuple(decisions)


def _fact_available_at_decision(
    field: SourceManifestField,
    source_manifest: SourceManifest,
) -> bool:
    return (
        field.available_time is not None
        and field.available_time.as_utc()
        <= source_manifest.decision_time.as_utc()
        and field.retrieved_time.as_utc()
        <= source_manifest.decision_time.as_utc()
        and (
            field.event_time is None
            or field.event_time <= source_manifest.decision_time.value
        )
    )


def _decisions_from_policy_evidence(
    *,
    policy: DailyUniversePolicy,
    source_manifest: SourceManifest,
    provider_result: PublicCompositeProviderResult,
) -> tuple[DailyUniverseDecision, ...]:
    observed_symbols = {
        *(item.symbol for item in provider_result.bars),
        *(item.symbol for item in provider_result.quotes),
    }
    all_symbols = tuple(sorted(set(policy.symbols) | observed_symbols))
    field_by_fact = {
        (item.symbol, item.critical_fact): item
        for item in source_manifest.fields
        if item.symbol is not None and item.critical_fact is not None
    }
    decisions: list[DailyUniverseDecision] = []
    for symbol in all_symbols:
        membership = field_by_fact.get(
            (symbol, CriticalSourceFact.UNIVERSE_MEMBERSHIP)
        )
        eligibility = field_by_fact.get(
            (symbol, CriticalSourceFact.ELIGIBILITY)
        )
        member = bool(
            membership is not None
            and membership.authority_kind
            is SourceAuthorityKind.UNIVERSE_POLICY
            and membership.value is True
        )
        reasons: list[str] = []
        if _A_SHARE_SYMBOL.fullmatch(symbol) is None:
            reasons.append(DailyEligibilityReason.MAPPING_UNKNOWN.value)
        if not member:
            reasons.append(DailyEligibilityReason.NOT_IN_FIXED_UNIVERSE.value)
        if (
            eligibility is None
            or eligibility.authority_kind
            is not SourceAuthorityKind.ELIGIBILITY_POLICY
            or eligibility.value
            not in {item.value for item in TradingEligibilityStatus}
        ):
            status = TradingEligibilityStatus.UNKNOWN
            reasons.append("ELIGIBILITY_POLICY_EVIDENCE_INVALID")
        else:
            status = TradingEligibilityStatus(str(eligibility.value))
            reasons.extend(eligibility.reason_codes)
        if not member:
            status = TradingEligibilityStatus.INELIGIBLE
        decisions.append(
            DailyUniverseDecision(
                symbol=symbol,
                member=member,
                status=status,
                reasons=tuple(dict.fromkeys(reasons)),
            )
        )
    return tuple(decisions)


def _daily_amounts(bars: tuple[Any, ...]) -> list[float]:
    by_date: dict[Any, float] = {}
    for item in bars:
        session_date = item.event_time.date()
        by_date[session_date] = by_date.get(session_date, 0.0) + float(item.amount)
    return [by_date[key] for key in sorted(by_date)]


def _source_dataset_id(
    source_manifest: SourceManifest,
    policy: DailyUniversePolicy,
) -> DatasetId:
    content_hash = _canonical_hash(
        {
            "schema_version": "daily-public-source-dataset-identity-v1",
            "source_manifest_id": str(source_manifest.source_manifest_id),
            "source_manifest_hash": source_manifest.content_hash,
            "universe_policy_id": str(policy.policy_id),
            "universe_policy_hash": policy.content_hash,
        }
    )
    return DatasetId(f"daily-source-{content_hash.split(':', 1)[1][:24]}")
