"""Label-blind Locked OOS scope and Outcome-access gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
)
from market_regime_alpha.universe.research import HistoricalConstituentTimeline


WP_ALPHA_PROOF_02_EXTERNAL_FINAL_TARGET = date(2026, 1, 19)
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_LIMITATIONS = (
    "FORMAL_PIT_REQUIRED_BEFORE_OUTCOME_ACCESS",
    "LOCKED_OOS_OUTCOME_NOT_CONSUMED",
    "NO_PRODUCTION_AUTHORITY",
)


@dataclass(frozen=True, slots=True)
class FrozenLockedOOSScope:
    scope_id: ArtifactId
    scope_hash: str
    protocol_reference: ValidationArtifactReference
    calendar_reference: ValidationArtifactReference
    universe_timeline_reference: ValidationArtifactReference
    external_final_target_session: date
    data_cutoff: datetime
    decision_sessions: tuple[date, ...]
    target_session_bindings: tuple[tuple[date, date], ...]
    session_universe_references: tuple[
        tuple[date, ValidationArtifactReference], ...
    ]
    outcome_values_read: bool
    limitations: tuple[str, ...]
    schema_version: str = "frozen-locked-oos-scope/v1"

    def __post_init__(self) -> None:
        require_sha256("scope_hash", self.scope_hash)
        if self.schema_version != "frozen-locked-oos-scope/v1":
            raise ValueError("unsupported Frozen Locked OOS scope schema")
        if (
            self.protocol_reference.artifact_kind
            != "RESEARCH_EXPERIMENT_DEFINITION"
        ):
            raise ValueError("Locked OOS scope requires frozen Experiment owner")
        if self.calendar_reference.artifact_kind != "TRADING_CALENDAR":
            raise ValueError("Locked OOS scope requires Trading Calendar owner")
        if (
            self.universe_timeline_reference.artifact_kind
            != "HISTORICAL_CONSTITUENT_TIMELINE"
        ):
            raise ValueError("Locked OOS scope requires constituent Timeline owner")
        if (
            self.external_final_target_session
            != WP_ALPHA_PROOF_02_EXTERNAL_FINAL_TARGET
        ):
            raise ValueError("Locked OOS scope changed frozen External final Target")
        normalize_canonical_datetime(self.data_cutoff)
        if (
            not self.decision_sessions
            or self.decision_sessions
            != tuple(sorted(set(self.decision_sessions)))
            or self.decision_sessions[0] <= self.external_final_target_session
        ):
            raise ValueError("Locked OOS Decision sessions overlap prior partitions")
        expected_decisions = tuple(item[0] for item in self.target_session_bindings)
        if expected_decisions != self.decision_sessions or any(
            target <= decision
            for decision, target in self.target_session_bindings
        ):
            raise ValueError("Locked OOS Target-session bindings are invalid")
        if tuple(item[0] for item in self.session_universe_references) != (
            self.decision_sessions
        ) or any(
            reference.artifact_kind != "FREE_RESEARCH_UNIVERSE"
            for _session, reference in self.session_universe_references
        ):
            raise ValueError("Locked OOS session Universe roster is invalid")
        if self.outcome_values_read:
            raise ValueError("Frozen Locked OOS scope cannot contain Outcome values")
        if self.limitations != _LIMITATIONS:
            raise ValueError("Locked OOS scope Evidence ceiling drifted")
        if (
            canonical_hash(self.identity_payload()) != self.scope_hash
            or self.scope_id
            != ArtifactId(f"frozen-locked-oos-scope:{self.scope_hash[7:]}")
        ):
            raise ValueError("Frozen Locked OOS scope identity mismatch")

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "FROZEN_LOCKED_OOS_SCOPE",
            self.scope_id,
            self.scope_hash,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_reference": self.protocol_reference.to_canonical_dict(),
            "calendar_reference": self.calendar_reference.to_canonical_dict(),
            "universe_timeline_reference": (
                self.universe_timeline_reference.to_canonical_dict()
            ),
            "external_final_target_session": (
                self.external_final_target_session.isoformat()
            ),
            "data_cutoff": timestamp(self.data_cutoff),
            "decision_sessions": [
                item.isoformat() for item in self.decision_sessions
            ],
            "target_session_bindings": [
                [decision.isoformat(), target.isoformat()]
                for decision, target in self.target_session_bindings
            ],
            "session_universe_references": [
                {
                    "decision_session": session.isoformat(),
                    "universe_reference": reference.to_canonical_dict(),
                }
                for session, reference in self.session_universe_references
            ],
            "outcome_values_read": self.outcome_values_read,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "scope_id": str(self.scope_id),
            "scope_hash": self.scope_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> FrozenLockedOOSScope:
        bindings = _array(payload["target_session_bindings"])
        rosters = _array(payload["session_universe_references"])
        return cls(
            scope_id=ArtifactId(str(payload["scope_id"])),
            scope_hash=str(payload["scope_hash"]),
            protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["protocol_reference"])
            ),
            calendar_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["calendar_reference"])
            ),
            universe_timeline_reference=(
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(payload["universe_timeline_reference"])
                )
            ),
            external_final_target_session=date.fromisoformat(
                str(payload["external_final_target_session"])
            ),
            data_cutoff=datetime.fromisoformat(str(payload["data_cutoff"])),
            decision_sessions=tuple(
                date.fromisoformat(str(item))
                for item in _array(payload["decision_sessions"])
            ),
            target_session_bindings=tuple(
                (
                    date.fromisoformat(str(_array(item)[0])),
                    date.fromisoformat(str(_array(item)[1])),
                )
                for item in bindings
            ),
            session_universe_references=tuple(
                (
                    date.fromisoformat(str(_mapping(item)["decision_session"])),
                    ValidationArtifactReference.from_canonical_dict(
                        _mapping(_mapping(item)["universe_reference"])
                    ),
                )
                for item in rosters
            ),
            outcome_values_read=bool(payload["outcome_values_read"]),
            limitations=tuple(str(item) for item in _array(payload["limitations"])),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class LockedOOSAccessDecision:
    decision_id: ArtifactId
    decision_hash: str
    scope_reference: ValidationArtifactReference
    outcome_access_allowed: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("decision_hash", self.decision_hash)
        if self.scope_reference.artifact_kind != "FROZEN_LOCKED_OOS_SCOPE":
            raise ValueError("Locked OOS access decision scope kind is invalid")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Locked OOS access reasons must be sorted and unique")
        if self.outcome_access_allowed != (
            self.reason_codes == ("LOCKED_OOS_OUTCOME_ACCESS_ELIGIBLE",)
        ):
            raise ValueError("Locked OOS access status/reasons disagree")
        if (
            canonical_hash(self.identity_payload()) != self.decision_hash
            or self.decision_id
            != ArtifactId(f"locked-oos-access-decision:{self.decision_hash[7:]}")
        ):
            raise ValueError("Locked OOS access decision identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "locked-oos-access-decision/v1",
            "scope_reference": self.scope_reference.to_canonical_dict(),
            "outcome_access_allowed": self.outcome_access_allowed,
            "reason_codes": list(self.reason_codes),
        }


def freeze_locked_oos_scope(
    *,
    protocol_reference: ValidationArtifactReference,
    calendar: TradingCalendarArtifact,
    universe_timeline: HistoricalConstituentTimeline,
    external_final_target_session: date,
    data_cutoff: datetime,
) -> FrozenLockedOOSScope:
    if protocol_reference.artifact_kind != "RESEARCH_EXPERIMENT_DEFINITION":
        raise ValueError("Locked OOS scope requires frozen Experiment owner")
    if (
        external_final_target_session
        != WP_ALPHA_PROOF_02_EXTERNAL_FINAL_TARGET
    ):
        raise ValueError("Locked OOS scope changed frozen External final Target")
    if calendar.market not in {"A_SHARE", "CN_A_SHARE"} or (
        calendar.timezone_name != "Asia/Shanghai"
    ):
        raise ValueError("Locked OOS scope requires canonical A-share Calendar")
    cutoff = normalize_canonical_datetime(data_cutoff)
    try:
        external_index = calendar.trading_dates.index(
            external_final_target_session
        )
    except ValueError as exc:
        raise ValueError(
            "frozen External final Target is absent from Calendar owner"
        ) from exc
    bindings: list[tuple[date, date]] = []
    for index in range(external_index + 1, len(calendar.trading_dates) - 1):
        decision = calendar.trading_dates[index]
        target = calendar.trading_dates[index + 1]
        target_available_at = datetime.combine(target, time(10, 30), _SHANGHAI)
        if target_available_at > cutoff:
            break
        bindings.append((decision, target))
    if not bindings:
        raise ValueError("Calendar has no complete Locked OOS Target before cutoff")
    effective_by_query = dict(universe_timeline.query_effective_dates)
    cohort_by_effective = {
        item.effective_date: item.snapshot_reference
        for item in universe_timeline.cohorts
    }
    rosters: list[tuple[date, ValidationArtifactReference]] = []
    for decision, _target in bindings:
        effective = effective_by_query.get(decision)
        reference = (
            None if effective is None else cohort_by_effective.get(effective)
        )
        if reference is None:
            raise ValueError(
                "Locked OOS Decision session lacks exact PIT Universe cohort"
            )
        rosters.append((decision, reference))
    values = {
        "schema_version": "frozen-locked-oos-scope/v1",
        "protocol_reference": protocol_reference.to_canonical_dict(),
        "calendar_reference": ValidationArtifactReference(
            "TRADING_CALENDAR",
            calendar.artifact_id,
            calendar.content_hash,
        ).to_canonical_dict(),
        "universe_timeline_reference": (
            universe_timeline.reference.to_canonical_dict()
        ),
        "external_final_target_session": external_final_target_session.isoformat(),
        "data_cutoff": timestamp(cutoff),
        "decision_sessions": [item[0].isoformat() for item in bindings],
        "target_session_bindings": [
            [decision.isoformat(), target.isoformat()]
            for decision, target in bindings
        ],
        "session_universe_references": [
            {
                "decision_session": session.isoformat(),
                "universe_reference": reference.to_canonical_dict(),
            }
            for session, reference in rosters
        ],
        "outcome_values_read": False,
        "limitations": list(_LIMITATIONS),
    }
    digest = canonical_hash(values)
    return FrozenLockedOOSScope(
        scope_id=ArtifactId(f"frozen-locked-oos-scope:{digest[7:]}"),
        scope_hash=digest,
        protocol_reference=protocol_reference,
        calendar_reference=ValidationArtifactReference(
            "TRADING_CALENDAR",
            calendar.artifact_id,
            calendar.content_hash,
        ),
        universe_timeline_reference=universe_timeline.reference,
        external_final_target_session=external_final_target_session,
        data_cutoff=cutoff,
        decision_sessions=tuple(item[0] for item in bindings),
        target_session_bindings=tuple(bindings),
        session_universe_references=tuple(rosters),
        outcome_values_read=False,
        limitations=_LIMITATIONS,
    )


def assess_locked_oos_access(
    *,
    scope: FrozenLockedOOSScope,
    formal_pit_supported: bool,
    physical_correctness_supported: bool,
) -> LockedOOSAccessDecision:
    reasons: set[str] = set()
    if not formal_pit_supported:
        reasons.add("FORMAL_PIT_NOT_SUPPORTED")
    if not physical_correctness_supported:
        reasons.add("PHYSICAL_CORRECTNESS_NOT_SUPPORTED")
    ordered = tuple(sorted(reasons)) or (
        "LOCKED_OOS_OUTCOME_ACCESS_ELIGIBLE",
    )
    values = {
        "schema_version": "locked-oos-access-decision/v1",
        "scope_reference": scope.reference.to_canonical_dict(),
        "outcome_access_allowed": not reasons,
        "reason_codes": list(ordered),
    }
    digest = canonical_hash(values)
    return LockedOOSAccessDecision(
        decision_id=ArtifactId(f"locked-oos-access-decision:{digest[7:]}"),
        decision_hash=digest,
        scope_reference=scope.reference,
        outcome_access_allowed=not reasons,
        reason_codes=ordered,
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Locked OOS payload value is not an object")
    return value


def _array(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Locked OOS payload value is not an array")
    return value


__all__ = [
    "FrozenLockedOOSScope",
    "LockedOOSAccessDecision",
    "WP_ALPHA_PROOF_02_EXTERNAL_FINAL_TARGET",
    "assess_locked_oos_access",
    "freeze_locked_oos_scope",
]
