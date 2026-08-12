"""Versioned Research Universe Policy and immutable Runtime Scope receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
    require_text,
)
from market_regime_alpha.universe.research import (
    FreeResearchUniverseSnapshot,
)


RUNTIME_SCOPE_POLICY_SCHEMA = "research-universe-policy/v1"
RUNTIME_SCOPE_RECEIPT_SCHEMA = "runtime-scope-receipt/v1"


class UniverseScopeKind(str, Enum):
    FULL_A = "FULL_A"
    INDEX = "INDEX"
    INDUSTRY = "INDUSTRY"
    THEME = "THEME"
    WATCHLIST = "WATCHLIST"
    ETF = "ETF"


class RuntimeScopeDecision(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class UniversePolicySelector:
    kind: UniverseScopeKind
    selector_id: str
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("selector_id", self.selector_id)
        if self.symbols != tuple(sorted(set(self.symbols))):
            raise ValueError("selector symbols must be sorted and unique")
        if self.kind is UniverseScopeKind.WATCHLIST and not self.symbols:
            raise ValueError("watchlist selector requires symbols")
        if self.kind is not UniverseScopeKind.WATCHLIST and self.symbols:
            raise ValueError("only watchlist selectors embed symbols")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "selector_id": self.selector_id,
            "symbols": list(self.symbols),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> UniversePolicySelector:
        return cls(
            kind=UniverseScopeKind(str(payload["kind"])),
            selector_id=str(payload["selector_id"]),
            symbols=tuple(str(item) for item in payload["symbols"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchUniversePolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    selectors: tuple[UniversePolicySelector, ...]
    minimum_history_sessions: int
    minimum_median_daily_amount: Decimal
    include_st: bool
    require_tradable: bool
    lot_size: int
    data_authority: str
    schema_version: str = RUNTIME_SCOPE_POLICY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SCOPE_POLICY_SCHEMA:
            raise ValueError("unsupported Research Universe Policy schema")
        require_text("policy_version", self.policy_version)
        require_text("data_authority", self.data_authority)
        require_sha256("policy_hash", self.policy_hash)
        keys = tuple((item.kind.value, item.selector_id) for item in self.selectors)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("policy selectors must be non-empty, unique, and sorted")
        if self.minimum_history_sessions <= 0:
            raise ValueError("minimum_history_sessions must be positive")
        if self.minimum_median_daily_amount <= 0:
            raise ValueError("minimum_median_daily_amount must be positive")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        digest = canonical_hash(self.identity_payload())
        if digest != self.policy_hash:
            raise ValueError("Research Universe Policy hash mismatch")
        if str(self.policy_id) != f"research-universe-policy-{digest[7:31]}":
            raise ValueError("Research Universe Policy identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "selectors": [item.to_canonical_dict() for item in self.selectors],
            "minimum_history_sessions": self.minimum_history_sessions,
            "minimum_median_daily_amount": str(
                self.minimum_median_daily_amount
            ),
            "include_st": self.include_st,
            "require_tradable": self.require_tradable,
            "lot_size": self.lot_size,
            "data_authority": self.data_authority,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchUniversePolicy:
        return cls(
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            policy_version=str(payload["policy_version"]),
            selectors=tuple(
                UniversePolicySelector.from_canonical_dict(item)
                for item in payload["selectors"]
            ),
            minimum_history_sessions=int(payload["minimum_history_sessions"]),
            minimum_median_daily_amount=Decimal(
                str(payload["minimum_median_daily_amount"])
            ),
            include_st=bool(payload["include_st"]),
            require_tradable=bool(payload["require_tradable"]),
            lot_size=int(payload["lot_size"]),
            data_authority=str(payload["data_authority"]),
            schema_version=str(payload["schema_version"]),
        )


def build_research_universe_policy(
    *,
    policy_version: str,
    selectors: tuple[UniversePolicySelector, ...],
    minimum_history_sessions: int,
    minimum_median_daily_amount: Decimal,
    include_st: bool,
    require_tradable: bool,
    lot_size: int,
    data_authority: str,
) -> ResearchUniversePolicy:
    ordered = tuple(sorted(selectors, key=lambda item: (item.kind.value, item.selector_id)))
    values = {
        "schema_version": RUNTIME_SCOPE_POLICY_SCHEMA,
        "policy_version": policy_version,
        "selectors": [item.to_canonical_dict() for item in ordered],
        "minimum_history_sessions": minimum_history_sessions,
        "minimum_median_daily_amount": str(minimum_median_daily_amount),
        "include_st": include_st,
        "require_tradable": require_tradable,
        "lot_size": lot_size,
        "data_authority": data_authority,
    }
    digest = canonical_hash(values)
    return ResearchUniversePolicy(
        policy_id=ArtifactId(f"research-universe-policy-{digest[7:31]}"),
        policy_hash=digest,
        policy_version=policy_version,
        selectors=ordered,
        minimum_history_sessions=minimum_history_sessions,
        minimum_median_daily_amount=minimum_median_daily_amount,
        include_st=include_st,
        require_tradable=require_tradable,
        lot_size=lot_size,
        data_authority=data_authority,
    )


@dataclass(frozen=True, slots=True)
class RuntimeEligibilityObservation:
    observation_id: ArtifactId
    observation_hash: str
    symbol: str
    observed_at: datetime
    known_at: datetime
    is_st: bool | None
    suspended: bool | None
    history_sessions: int | None
    median_daily_amount: Decimal | None
    source_references: tuple[ValidationArtifactReference, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_sha256("observation_hash", self.observation_hash)
        normalize_canonical_datetime(self.observed_at)
        normalize_canonical_datetime(self.known_at)
        if self.known_at < self.observed_at:
            raise ValueError("eligibility known_at cannot precede observed_at")
        if self.history_sessions is not None and self.history_sessions < 0:
            raise ValueError("history_sessions cannot be negative")
        if self.median_daily_amount is not None and self.median_daily_amount < 0:
            raise ValueError("median_daily_amount cannot be negative")
        if not self.source_references:
            raise ValueError("eligibility observation requires provenance")
        if self.source_references != _references(self.source_references):
            raise ValueError("eligibility references must be unique and sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.observation_hash:
            raise ValueError("eligibility observation hash mismatch")
        if str(self.observation_id) != f"runtime-eligibility-{digest[7:31]}":
            raise ValueError("eligibility observation identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        observed_at: datetime,
        known_at: datetime,
        is_st: bool | None,
        suspended: bool | None,
        history_sessions: int | None,
        median_daily_amount: Decimal | None,
        source_references: tuple[ValidationArtifactReference, ...],
    ) -> RuntimeEligibilityObservation:
        ordered = _references(source_references)
        payload = _eligibility_payload(
            symbol=symbol,
            observed_at=observed_at,
            known_at=known_at,
            is_st=is_st,
            suspended=suspended,
            history_sessions=history_sessions,
            median_daily_amount=median_daily_amount,
            source_references=ordered,
        )
        digest = canonical_hash(payload)
        return cls(
            ArtifactId(f"runtime-eligibility-{digest[7:31]}"),
            digest,
            symbol,
            normalize_canonical_datetime(observed_at),
            normalize_canonical_datetime(known_at),
            is_st,
            suspended,
            history_sessions,
            median_daily_amount,
            ordered,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _eligibility_payload(
            symbol=self.symbol,
            observed_at=self.observed_at,
            known_at=self.known_at,
            is_st=self.is_st,
            suspended=self.suspended,
            history_sessions=self.history_sessions,
            median_daily_amount=self.median_daily_amount,
            source_references=self.source_references,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "observation_hash": self.observation_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RuntimeEligibilityObservation:
        return cls(
            observation_id=ArtifactId(str(payload["observation_id"])),
            observation_hash=str(payload["observation_hash"]),
            symbol=str(payload["symbol"]),
            observed_at=_datetime(payload["observed_at"]),
            known_at=_datetime(payload["known_at"]),
            is_st=_optional_bool(payload["is_st"]),
            suspended=_optional_bool(payload["suspended"]),
            history_sessions=(
                None
                if payload["history_sessions"] is None
                else int(payload["history_sessions"])
            ),
            median_daily_amount=(
                None
                if payload["median_daily_amount"] is None
                else Decimal(str(payload["median_daily_amount"]))
            ),
            source_references=_references(
                tuple(
                    ValidationArtifactReference.from_canonical_dict(item)
                    for item in payload["source_references"]
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeScopeMembershipSnapshot:
    selector: UniversePolicySelector
    effective_at: datetime
    known_at: datetime
    decisions: tuple[tuple[str, RuntimeScopeDecision], ...]
    source_reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        if self.selector.kind in {UniverseScopeKind.FULL_A, UniverseScopeKind.WATCHLIST}:
            raise ValueError("FULL_A/WATCHLIST do not use membership snapshots")
        normalize_canonical_datetime(self.effective_at)
        normalize_canonical_datetime(self.known_at)
        symbols = tuple(symbol for symbol, _ in self.decisions)
        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("membership decisions must be non-empty and sorted")


@dataclass(frozen=True, slots=True)
class RuntimeScopeRecord:
    symbol: str
    decision: RuntimeScopeDecision
    reason_codes: tuple[str, ...]
    source_references: tuple[ValidationArtifactReference, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("Runtime Scope reasons must be non-empty, unique, sorted")
        if not self.source_references or self.source_references != _references(
            self.source_references
        ):
            raise ValueError("Runtime Scope references must be non-empty, unique, sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "decision": self.decision.value,
            "reason_codes": list(self.reason_codes),
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RuntimeScopeRecord:
        return cls(
            symbol=str(payload["symbol"]),
            decision=RuntimeScopeDecision(str(payload["decision"])),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
            source_references=_references(
                tuple(
                    ValidationArtifactReference.from_canonical_dict(item)
                    for item in payload["source_references"]
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeScopeReceipt:
    scope_id: ArtifactId
    scope_hash: str
    policy_id: ArtifactId
    policy_hash: str
    as_of: datetime
    built_at: datetime
    records: tuple[RuntimeScopeRecord, ...]
    input_references: tuple[ValidationArtifactReference, ...]
    code_revision: str
    data_eligibility: str
    evidence_ceiling: str
    formal_pit: bool
    limitations: tuple[str, ...]
    schema_version: str = RUNTIME_SCOPE_RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SCOPE_RECEIPT_SCHEMA:
            raise ValueError("unsupported Runtime Scope receipt schema")
        require_sha256("scope_hash", self.scope_hash)
        require_sha256("policy_hash", self.policy_hash)
        require_text("code_revision", self.code_revision)
        normalize_canonical_datetime(self.as_of)
        normalize_canonical_datetime(self.built_at)
        symbols = tuple(item.symbol for item in self.records)
        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Runtime Scope records must be non-empty, unique, sorted")
        if self.input_references != _references(self.input_references):
            raise ValueError("Runtime Scope input references must be unique and sorted")
        if self.formal_pit and self.evidence_ceiling != "FORMAL_PIT_PROVIDER":
            raise ValueError("Formal Runtime Scope requires Formal PIT evidence ceiling")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Runtime Scope limitations must be unique and sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.scope_hash:
            raise ValueError("Runtime Scope receipt hash mismatch")
        if str(self.scope_id) != f"runtime-scope-{digest[7:31]}":
            raise ValueError("Runtime Scope receipt identity mismatch")

    @property
    def requested_symbols(self) -> tuple[str, ...]:
        return tuple(
            item.symbol
            for item in self.records
            if item.decision is RuntimeScopeDecision.INCLUDED
        )

    def record_for(self, symbol: str) -> RuntimeScopeRecord:
        for item in self.records:
            if item.symbol == symbol:
                return item
        raise KeyError(symbol)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            "as_of": canonical_datetime(self.as_of),
            "built_at": canonical_datetime(self.built_at),
            "records": [item.to_canonical_dict() for item in self.records],
            "input_references": [
                item.to_canonical_dict() for item in self.input_references
            ],
            "code_revision": self.code_revision,
            "data_eligibility": self.data_eligibility,
            "evidence_ceiling": self.evidence_ceiling,
            "formal_pit": self.formal_pit,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "scope_id": str(self.scope_id),
            "scope_hash": self.scope_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RuntimeScopeReceipt:
        return cls(
            scope_id=ArtifactId(str(payload["scope_id"])),
            scope_hash=str(payload["scope_hash"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            as_of=_datetime(payload["as_of"]),
            built_at=_datetime(payload["built_at"]),
            records=tuple(
                RuntimeScopeRecord.from_canonical_dict(item)
                for item in payload["records"]
            ),
            input_references=_references(
                tuple(
                    ValidationArtifactReference.from_canonical_dict(item)
                    for item in payload["input_references"]
                )
            ),
            code_revision=str(payload["code_revision"]),
            data_eligibility=str(payload["data_eligibility"]),
            evidence_ceiling=str(payload["evidence_ceiling"]),
            formal_pit=bool(payload["formal_pit"]),
            limitations=tuple(str(item) for item in payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


def build_runtime_scope(
    *,
    policy: ResearchUniversePolicy,
    as_of: datetime,
    built_at: datetime,
    security_master: FreeResearchUniverseSnapshot,
    eligibility_observations: tuple[RuntimeEligibilityObservation, ...],
    membership_snapshots: tuple[RuntimeScopeMembershipSnapshot, ...],
    code_revision: str,
) -> RuntimeScopeReceipt:
    """Apply one policy without inflating the free-data evidence ceiling."""

    as_of = normalize_canonical_datetime(as_of)
    built_at = normalize_canonical_datetime(built_at)
    if security_master.known_at > built_at:
        raise ValueError("Security Master was not known at the requested build time")
    eligibility = _eligibility_by_symbol(eligibility_observations, as_of, built_at)
    membership = _membership_by_selector(policy, membership_snapshots, as_of, built_at)
    master = {item.symbol: item for item in security_master.records}
    selected_symbols = _selected_symbols(policy, master, membership)
    records: list[RuntimeScopeRecord] = []
    master_reference = ValidationArtifactReference(
        "RESEARCH_UNIVERSE", security_master.snapshot_id, security_master.snapshot_hash
    )
    for symbol in sorted(selected_symbols):
        master_record = master.get(symbol)
        reasons: set[str] = set()
        references: list[ValidationArtifactReference] = [master_reference]
        base_decision = _base_membership_decision(
            symbol, policy, master_record, membership, reasons, references
        )
        observation = eligibility.get(symbol)
        if base_decision is RuntimeScopeDecision.INCLUDED:
            decision = _apply_eligibility(
                observation=observation,
                policy=policy,
                reasons=reasons,
                references=references,
            )
        else:
            decision = base_decision
        records.append(
            RuntimeScopeRecord(
                symbol=symbol,
                decision=decision,
                reason_codes=tuple(sorted(reasons)),
                source_references=_references(tuple(references)),
            )
        )
    input_references = _references(
        tuple(reference for item in records for reference in item.source_references)
    )
    values = {
        "schema_version": RUNTIME_SCOPE_RECEIPT_SCHEMA,
        "policy_id": str(policy.policy_id),
        "policy_hash": policy.policy_hash,
        "as_of": canonical_datetime(as_of),
        "built_at": canonical_datetime(built_at),
        "records": [item.to_canonical_dict() for item in records],
        "input_references": [item.to_canonical_dict() for item in input_references],
        "code_revision": code_revision,
        "data_eligibility": security_master.data_eligibility.value,
        "evidence_ceiling": security_master.evidence_ceiling.value,
        "formal_pit": False,
        "limitations": [
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FREE_DATA_EXPLORATORY",
            "PIT_INCOMPLETE",
            "UNKNOWN_FAILS_CLOSED",
        ],
    }
    digest = canonical_hash(values)
    return RuntimeScopeReceipt(
        scope_id=ArtifactId(f"runtime-scope-{digest[7:31]}"),
        scope_hash=digest,
        policy_id=policy.policy_id,
        policy_hash=policy.policy_hash,
        as_of=as_of,
        built_at=built_at,
        records=tuple(records),
        input_references=input_references,
        code_revision=code_revision,
        data_eligibility=security_master.data_eligibility.value,
        evidence_ceiling=security_master.evidence_ceiling.value,
        formal_pit=False,
        limitations=(
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FREE_DATA_EXPLORATORY",
            "PIT_INCOMPLETE",
            "UNKNOWN_FAILS_CLOSED",
        ),
    )


def _selected_symbols(
    policy: ResearchUniversePolicy,
    master: Mapping[str, Any],
    membership: Mapping[tuple[str, str], RuntimeScopeMembershipSnapshot],
) -> set[str]:
    selected: set[str] = set()
    for selector in policy.selectors:
        if selector.kind is UniverseScopeKind.FULL_A:
            selected.update(master)
        elif selector.kind is UniverseScopeKind.WATCHLIST:
            selected.update(selector.symbols)
        else:
            snapshot = membership.get((selector.kind.value, selector.selector_id))
            if snapshot is not None:
                selected.update(symbol for symbol, _ in snapshot.decisions)
    if not selected:
        raise ValueError("Universe Policy resolved no population facts")
    return selected


def _base_membership_decision(
    symbol: str,
    policy: ResearchUniversePolicy,
    master_record: Any,
    membership: Mapping[tuple[str, str], RuntimeScopeMembershipSnapshot],
    reasons: set[str],
    references: list[ValidationArtifactReference],
) -> RuntimeScopeDecision:
    if master_record is None:
        reasons.add("SECURITY_MASTER_RECORD_MISSING")
        return RuntimeScopeDecision.UNKNOWN
    decisions: list[RuntimeScopeDecision] = []
    for selector in policy.selectors:
        if selector.kind is UniverseScopeKind.FULL_A:
            decisions.append(RuntimeScopeDecision(master_record.membership_status.value))
        elif selector.kind is UniverseScopeKind.WATCHLIST:
            if symbol in selector.symbols:
                decisions.append(RuntimeScopeDecision(master_record.membership_status.value))
        else:
            snapshot = membership.get((selector.kind.value, selector.selector_id))
            if snapshot is None:
                reasons.add(f"{selector.kind.value}_MEMBERSHIP_SNAPSHOT_MISSING")
                decisions.append(RuntimeScopeDecision.UNKNOWN)
            else:
                references.append(snapshot.source_reference)
                decision = dict(snapshot.decisions).get(symbol)
                if decision is not None:
                    decisions.append(decision)
    if not decisions:
        reasons.add("UNIVERSE_MEMBERSHIP_NOT_SELECTED")
        return RuntimeScopeDecision.EXCLUDED
    if RuntimeScopeDecision.INCLUDED in decisions:
        reasons.add("UNIVERSE_POLICY_INCLUDED")
        return RuntimeScopeDecision.INCLUDED
    if RuntimeScopeDecision.UNKNOWN in decisions:
        reasons.add("UNIVERSE_MEMBERSHIP_UNKNOWN")
        return RuntimeScopeDecision.UNKNOWN
    reasons.add("UNIVERSE_POLICY_EXCLUDED")
    return RuntimeScopeDecision.EXCLUDED


def _apply_eligibility(
    *,
    observation: RuntimeEligibilityObservation | None,
    policy: ResearchUniversePolicy,
    reasons: set[str],
    references: list[ValidationArtifactReference],
) -> RuntimeScopeDecision:
    if observation is None:
        reasons.add("ELIGIBILITY_FACT_MISSING")
        return RuntimeScopeDecision.UNKNOWN
    references.extend(observation.source_references)
    unknown = False
    excluded = False
    if observation.is_st is None:
        reasons.add("ST_STATUS_UNKNOWN")
        unknown = True
    elif observation.is_st and not policy.include_st:
        reasons.add("ST_NOT_ALLOWED")
        excluded = True
    if observation.suspended is None:
        reasons.add("TRADABILITY_UNKNOWN")
        unknown = True
    elif observation.suspended and policy.require_tradable:
        reasons.add("SUSPENDED")
        excluded = True
    if observation.history_sessions is None:
        reasons.add("HISTORY_LENGTH_UNKNOWN")
        unknown = True
    elif observation.history_sessions < policy.minimum_history_sessions:
        reasons.add("MINIMUM_HISTORY_NOT_MET")
        excluded = True
    if observation.median_daily_amount is None:
        reasons.add("LIQUIDITY_UNKNOWN")
        unknown = True
    elif observation.median_daily_amount < policy.minimum_median_daily_amount:
        reasons.add("MINIMUM_LIQUIDITY_NOT_MET")
        excluded = True
    if unknown:
        return RuntimeScopeDecision.UNKNOWN
    if excluded:
        return RuntimeScopeDecision.EXCLUDED
    reasons.add("TRADING_ELIGIBILITY_SATISFIED")
    return RuntimeScopeDecision.INCLUDED


def _eligibility_by_symbol(
    observations: tuple[RuntimeEligibilityObservation, ...],
    as_of: datetime,
    built_at: datetime,
) -> dict[str, RuntimeEligibilityObservation]:
    result: dict[str, RuntimeEligibilityObservation] = {}
    for item in observations:
        if item.observed_at > as_of:
            raise ValueError("eligibility observation is after Runtime Scope as_of")
        if item.known_at > built_at:
            raise ValueError("eligibility observation was not known when scope was built")
        if item.symbol in result:
            raise ValueError("duplicate eligibility observation symbol")
        result[item.symbol] = item
    return result


def _membership_by_selector(
    policy: ResearchUniversePolicy,
    snapshots: tuple[RuntimeScopeMembershipSnapshot, ...],
    as_of: datetime,
    built_at: datetime,
) -> dict[tuple[str, str], RuntimeScopeMembershipSnapshot]:
    result: dict[tuple[str, str], RuntimeScopeMembershipSnapshot] = {}
    allowed = {(item.kind.value, item.selector_id) for item in policy.selectors}
    for item in snapshots:
        key = (item.selector.kind.value, item.selector.selector_id)
        if key not in allowed:
            raise ValueError("membership snapshot is outside Universe Policy")
        if item.effective_at > as_of or item.known_at > built_at:
            raise ValueError("membership snapshot violates as-of semantics")
        if key in result:
            raise ValueError("duplicate membership snapshot selector")
        result[key] = item
    return result


def _references(
    references: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    keyed = {
        (item.artifact_kind, str(item.artifact_id), item.content_hash): item
        for item in references
    }
    return tuple(keyed[key] for key in sorted(keyed))


def _eligibility_payload(
    *,
    symbol: str,
    observed_at: datetime,
    known_at: datetime,
    is_st: bool | None,
    suspended: bool | None,
    history_sessions: int | None,
    median_daily_amount: Decimal | None,
    source_references: tuple[ValidationArtifactReference, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "runtime-eligibility-observation/v1",
        "symbol": symbol,
        "observed_at": canonical_datetime(observed_at),
        "known_at": canonical_datetime(known_at),
        "is_st": is_st,
        "suspended": suspended,
        "history_sessions": history_sessions,
        "median_daily_amount": (
            None if median_daily_amount is None else str(median_daily_amount)
        ),
        "source_references": [
            item.to_canonical_dict() for item in source_references
        ],
    }


def _datetime(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _optional_bool(value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError("optional boolean field is invalid")


__all__ = [
    "RUNTIME_SCOPE_POLICY_SCHEMA",
    "RUNTIME_SCOPE_RECEIPT_SCHEMA",
    "ResearchUniversePolicy",
    "RuntimeEligibilityObservation",
    "RuntimeScopeDecision",
    "RuntimeScopeMembershipSnapshot",
    "RuntimeScopeReceipt",
    "UniversePolicySelector",
    "UniverseScopeKind",
    "build_research_universe_policy",
    "build_runtime_scope",
]
