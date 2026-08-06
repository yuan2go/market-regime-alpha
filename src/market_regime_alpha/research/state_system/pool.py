"""Immutable versioned Dynamic Stock Pool authority for Candidate Discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash, require_text
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import DynamicPoolConfiguration


@dataclass(frozen=True, slots=True)
class DynamicPoolStateContext:
    market_regime_state_id: ArtifactId
    market_regime_state: str
    etf_rotation_states: tuple[tuple[ArtifactId, str, int], ...]
    theme_rotation_states: tuple[tuple[ArtifactId, str, int], ...]
    capital_state_id: ArtifactId
    capital_state: str
    data_coverage: Decimal
    available_at: datetime

    def __post_init__(self) -> None:
        require_text("market_regime_state", self.market_regime_state)
        require_text("capital_state", self.capital_state)
        if not Decimal("0") <= self.data_coverage <= Decimal("1"):
            raise ValueError("data_coverage must be within [0, 1]")
        for label, values in (
            ("etf_rotation_states", self.etf_rotation_states),
            ("theme_rotation_states", self.theme_rotation_states),
        ):
            if not values:
                raise ValueError(f"{label} must not be empty")
            ids = tuple(value[0] for value in values)
            if ids != tuple(sorted(set(ids), key=str)):
                raise ValueError(f"{label} must be unique and sorted by State ID")
            for _state_id, state, dwell in values:
                require_text(label, state)
                if dwell < 0:
                    raise ValueError(f"{label} dwell must be non-negative")
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("State context available_at must be timezone-aware")

    def material_payload(self, *, gate_open: bool) -> dict[str, Any]:
        return {
            "market_regime_state": self.market_regime_state,
            "etf_rotation_states": [value[1] for value in self.etf_rotation_states],
            "theme_rotation_states": [value[1] for value in self.theme_rotation_states],
            "capital_state": self.capital_state,
            "data_coverage": str(self.data_coverage),
            "gate_open": gate_open,
        }


@dataclass(frozen=True, slots=True)
class PoolEligibilityObservation:
    symbol: str
    eligible: bool
    eligibility_reason: str
    liquidity: Decimal
    board: str
    is_st: bool
    suspended: bool
    listing_age_days: int
    theme_overlap: tuple[str, ...]
    data_coverage: Decimal
    missing_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("eligibility_reason", self.eligibility_reason)
        require_text("board", self.board)
        if not isinstance(self.eligible, bool) or not isinstance(self.is_st, bool) or not isinstance(self.suspended, bool):
            raise TypeError("Eligibility boolean fields must be bool")
        if not Decimal("0") <= self.liquidity <= Decimal("1"):
            raise ValueError("liquidity must be within [0, 1]")
        if not Decimal("0") <= self.data_coverage <= Decimal("1"):
            raise ValueError("data_coverage must be within [0, 1]")
        if self.listing_age_days < 0:
            raise ValueError("listing_age_days must be non-negative")
        for label, values in (
            ("theme_overlap", self.theme_overlap),
            ("missing_evidence", self.missing_evidence),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{label} must be unique and sorted")


@dataclass(frozen=True, slots=True)
class DynamicPoolMember:
    symbol: str
    included: bool
    gate_result: str
    score: Decimal
    rank: int | None
    exclusion_reasons: tuple[str, ...]
    eligibility: bool
    liquidity: Decimal
    board: str
    is_st: bool
    suspended: bool
    listing_age_days: int
    theme_overlap: tuple[str, ...]
    data_coverage: Decimal
    missing_evidence: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "included": self.included,
            "gate_result": self.gate_result,
            "score": str(self.score),
            "rank": self.rank,
            "exclusion_reasons": list(self.exclusion_reasons),
            "eligibility": self.eligibility,
            "liquidity": str(self.liquidity),
            "board": self.board,
            "is_st": self.is_st,
            "suspended": self.suspended,
            "listing_age_days": self.listing_age_days,
            "theme_overlap": list(self.theme_overlap),
            "data_coverage": str(self.data_coverage),
            "missing_evidence": list(self.missing_evidence),
        }


class DynamicPoolEvaluationStatus(str, Enum):
    CREATED = "CREATED"
    NO_MATERIAL_POOL_CHANGE = "NO_MATERIAL_POOL_CHANGE"


@dataclass(frozen=True, slots=True)
class DynamicStockPoolVersion:
    pool_id: ArtifactId
    pool_hash: str
    previous_pool_id: ArtifactId | None
    pool_version: int
    effective_at: datetime
    available_at: datetime
    decision_time: datetime
    market_regime_state_id: ArtifactId
    etf_rotation_state_ids: tuple[ArtifactId, ...]
    theme_rotation_state_ids: tuple[ArtifactId, ...]
    capital_state_id: ArtifactId
    included_symbols: tuple[str, ...]
    excluded_symbols: tuple[str, ...]
    added_symbols: tuple[str, ...]
    removed_symbols: tuple[str, ...]
    members: tuple[DynamicPoolMember, ...]
    missing_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    configuration_version: str
    configuration_hash: str
    source_artifact_ids: tuple[ArtifactId, ...]
    runtime_tick_id: ArtifactId
    material_state_hash: str
    lineage: StateLineage

    @property
    def entry_authority_granted(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "dynamic_stock_pool/v1",
            "previous_pool_id": None if self.previous_pool_id is None else str(self.previous_pool_id),
            "pool_version": self.pool_version,
            "effective_at": canonical_datetime(self.effective_at),
            "available_at": canonical_datetime(self.available_at),
            "decision_time": canonical_datetime(self.decision_time),
            "market_regime_state_id": str(self.market_regime_state_id),
            "etf_rotation_state_ids": [str(value) for value in self.etf_rotation_state_ids],
            "theme_rotation_state_ids": [str(value) for value in self.theme_rotation_state_ids],
            "capital_state_id": str(self.capital_state_id),
            "included_symbols": list(self.included_symbols),
            "excluded_symbols": list(self.excluded_symbols),
            "added_symbols": list(self.added_symbols),
            "removed_symbols": list(self.removed_symbols),
            "members": [member.to_canonical_dict() for member in self.members],
            "missing_evidence": list(self.missing_evidence),
            "reason_codes": list(self.reason_codes),
            "configuration_version": self.configuration_version,
            "configuration_hash": self.configuration_hash,
            "source_artifact_ids": [str(value) for value in self.source_artifact_ids],
            "runtime_tick_id": str(self.runtime_tick_id),
            "material_state_hash": self.material_state_hash,
            "lineage": self.lineage.identity_payload(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "pool_id": str(self.pool_id),
            "pool_hash": self.pool_hash,
            **self.identity_payload(),
            "created_at": canonical_datetime(self.lineage.created_at),
        }


@dataclass(frozen=True, slots=True)
class DynamicPoolEvaluation:
    status: DynamicPoolEvaluationStatus
    pool: DynamicStockPoolVersion
    reason_codes: tuple[str, ...]

    @property
    def pool_id(self) -> ArtifactId:
        return self.pool.pool_id


def evaluate_dynamic_pool(
    *,
    state_context: DynamicPoolStateContext,
    eligibility: tuple[PoolEligibilityObservation, ...],
    previous: DynamicStockPoolVersion | None,
    configuration: DynamicPoolConfiguration,
    lineage: StateLineage,
) -> DynamicPoolEvaluation:
    if lineage.configuration_id != configuration.configuration_id or lineage.configuration_hash != configuration.configuration_hash:
        raise ValueError("Dynamic Pool configuration binding mismatch")
    if state_context.available_at > lineage.as_of_time:
        raise ValueError("future State cannot be consumed by Dynamic Pool")
    if previous is not None and lineage.as_of_time <= previous.decision_time:
        raise ValueError("Dynamic Pool decisions must advance As-of Time")
    symbols = tuple(item.symbol for item in eligibility)
    if not symbols or symbols != tuple(sorted(set(symbols))):
        raise ValueError("Eligibility cross section must be non-empty, unique and sorted")

    gate_open, gate_reasons = _rotation_gate(state_context, configuration)
    members = _members(eligibility, gate_open, configuration)
    included = tuple(member.symbol for member in members if member.included)
    excluded = tuple(member.symbol for member in members if not member.included)
    previous_included = () if previous is None else previous.included_symbols
    added = tuple(sorted(set(included) - set(previous_included)))
    removed = tuple(sorted(set(previous_included) - set(included)))
    material_state_hash = canonical_hash(state_context.material_payload(gate_open=gate_open))
    if previous is not None:
        universe = set(included) | set(previous.included_symbols)
        changed_fraction = Decimal(len(set(added) | set(removed))) / Decimal(max(1, len(universe)))
        state_changed = material_state_hash != previous.material_state_hash
        if not state_changed and changed_fraction < configuration.material_change_threshold:
            return DynamicPoolEvaluation(
                status=DynamicPoolEvaluationStatus.NO_MATERIAL_POOL_CHANGE,
                pool=previous,
                reason_codes=("NO_MATERIAL_POOL_CHANGE",),
            )

    reasons = tuple(sorted(set(gate_reasons) | {"DYNAMIC_POOL_EVALUATED"}))
    missing = tuple(sorted({reason for item in eligibility for reason in item.missing_evidence}))
    prototype = DynamicStockPoolVersion(
        pool_id=ArtifactId("pending"),
        pool_hash="pending",
        previous_pool_id=None if previous is None else previous.pool_id,
        pool_version=1 if previous is None else previous.pool_version + 1,
        effective_at=lineage.as_of_time,
        available_at=max(lineage.available_at, state_context.available_at),
        decision_time=lineage.as_of_time,
        market_regime_state_id=state_context.market_regime_state_id,
        etf_rotation_state_ids=tuple(value[0] for value in state_context.etf_rotation_states),
        theme_rotation_state_ids=tuple(value[0] for value in state_context.theme_rotation_states),
        capital_state_id=state_context.capital_state_id,
        included_symbols=included,
        excluded_symbols=excluded,
        added_symbols=added,
        removed_symbols=removed,
        members=members,
        missing_evidence=missing,
        reason_codes=reasons,
        configuration_version=configuration.configuration_version,
        configuration_hash=configuration.configuration_hash,
        source_artifact_ids=lineage.source_artifact_ids,
        runtime_tick_id=lineage.runtime_tick_id,
        material_state_hash=material_state_hash,
        lineage=lineage,
    )
    payload = prototype.identity_payload()
    digest = canonical_hash(payload)
    pool = DynamicStockPoolVersion(
        pool_id=ArtifactId(f"dynamic-pool:{digest[7:]}"),
        pool_hash=digest,
        **{
            field: getattr(prototype, field)
            for field in prototype.__dataclass_fields__
            if field not in {"pool_id", "pool_hash"}
        },
    )
    return DynamicPoolEvaluation(
        status=DynamicPoolEvaluationStatus.CREATED,
        pool=pool,
        reason_codes=reasons,
    )


def _rotation_gate(
    value: DynamicPoolStateContext,
    configuration: DynamicPoolConfiguration,
) -> tuple[bool, tuple[str, ...]]:
    reasons: set[str] = set()
    if value.data_coverage < configuration.minimum_evidence_coverage:
        reasons.add("POOL_EVIDENCE_COVERAGE_INSUFFICIENT")
    if value.market_regime_state in {"DATA_INSUFFICIENT", "RISK_OFF"}:
        reasons.add("MARKET_REGIME_GATE_CLOSED")
    if value.capital_state == "DATA_INSUFFICIENT":
        reasons.add("CAPITAL_STATE_GATE_CLOSED")
    rotation_states = (*value.etf_rotation_states, *value.theme_rotation_states)
    allowed = set(configuration.allowed_etf_states) | set(configuration.allowed_theme_states)
    if not any(state in allowed for _state_id, state, _dwell in rotation_states):
        reasons.add("ROTATION_STATE_GATE_CLOSED")
    if any(
        state in allowed and dwell < configuration.minimum_state_dwell_seconds
        for _state_id, state, dwell in rotation_states
    ):
        reasons.add("ROTATION_MINIMUM_DWELL_NOT_MET")
    return not reasons, tuple(sorted(reasons))


def _members(
    values: tuple[PoolEligibilityObservation, ...],
    gate_open: bool,
    configuration: DynamicPoolConfiguration,
) -> tuple[DynamicPoolMember, ...]:
    prepared: list[tuple[PoolEligibilityObservation, bool, tuple[str, ...], Decimal]] = []
    for value in values:
        exclusions: set[str] = set()
        if not gate_open:
            exclusions.add("ROTATION_STATE_GATE_REJECTED")
        if not value.eligible:
            exclusions.add(value.eligibility_reason)
        if value.is_st:
            exclusions.add("ST_EXCLUDED")
        if value.suspended:
            exclusions.add("SUSPENDED")
        if value.data_coverage < configuration.minimum_evidence_coverage:
            exclusions.add("ELIGIBILITY_COVERAGE_INSUFFICIENT")
        score = (value.liquidity + value.data_coverage) / Decimal("2")
        prepared.append((value, not exclusions, tuple(sorted(exclusions)), score))
    ranked = sorted(
        (item for item in prepared if item[1]),
        key=lambda item: (-item[3], item[0].symbol),
    )
    ranks = {item[0].symbol: index for index, item in enumerate(ranked, start=1)}
    return tuple(
        DynamicPoolMember(
            symbol=value.symbol,
            included=included,
            gate_result="INCLUDED" if included else "EXCLUDED",
            score=score,
            rank=ranks.get(value.symbol),
            exclusion_reasons=exclusions,
            eligibility=value.eligible,
            liquidity=value.liquidity,
            board=value.board,
            is_st=value.is_st,
            suspended=value.suspended,
            listing_age_days=value.listing_age_days,
            theme_overlap=value.theme_overlap,
            data_coverage=value.data_coverage,
            missing_evidence=value.missing_evidence,
        )
        for value, included, exclusions, score in prepared
    )
