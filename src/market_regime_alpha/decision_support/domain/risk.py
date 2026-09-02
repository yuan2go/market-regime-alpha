"""Decision-support-only Risk policy and terminal decision Authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.decision_support.domain.context import DecisionArtifactBinding
from market_regime_alpha.decision_support.domain.portfolio import (
    PortfolioLineStatus,
    PortfolioProposalStatus,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


class RiskAuthorityScope(StrEnum):
    DECISION_SUPPORT_ONLY = "DECISION_SUPPORT_ONLY"


class RiskRuleScope(StrEnum):
    GLOBAL = "GLOBAL"
    LINE = "LINE"


class RiskSubject(StrEnum):
    PROPOSAL_STATUS = "PROPOSAL_STATUS"
    LINE_COUNT = "LINE_COUNT"
    GROSS_WEIGHT = "GROSS_WEIGHT"
    NET_WEIGHT = "NET_WEIGHT"
    SINGLE_LINE_WEIGHT = "SINGLE_LINE_WEIGHT"
    CASH_WEIGHT = "CASH_WEIGHT"
    ESTIMABILITY = "ESTIMABILITY"
    QUALIFICATION_PRESENCE = "QUALIFICATION_PRESENCE"


class RiskOperator(StrEnum):
    EQUALS = "EQUALS"
    AT_MOST = "AT_MOST"
    AT_LEAST = "AT_LEAST"


class RiskSeverity(StrEnum):
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"


class RiskMissingAction(StrEnum):
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RiskRuleResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RiskDecisionStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    NO_ACTION = "NO_ACTION"


def _sha(value: str, label: str) -> str:
    try:
        return str(ContentHash(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be a lowercase SHA-256") from exc


@dataclass(frozen=True, slots=True)
class RiskRulePlan:
    risk_rule_id: UUID
    risk_policy_id: UUID
    ordinal: int
    rule_code: str
    scope: RiskRuleScope
    subject: RiskSubject
    operator: RiskOperator
    decimal_threshold: Decimal | None
    integer_threshold: int | None
    text_threshold: str | None
    boolean_threshold: bool | None
    value_unit: str
    severity: RiskSeverity
    missing_action: RiskMissingAction
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.rule_code) or self.ordinal < 1:
            raise ValueError("RiskRule identity is invalid")
        thresholds = (
            self.decimal_threshold, self.integer_threshold,
            self.text_threshold, self.boolean_threshold,
        )
        if sum(value is not None for value in thresholds) != 1:
            raise ValueError("RiskRule requires exactly one typed threshold")
        if self.decimal_threshold is not None and not self.decimal_threshold.is_finite():
            raise ValueError("RiskRule Decimal threshold must be finite")
        if self.scope is RiskRuleScope.LINE and self.subject is not RiskSubject.SINGLE_LINE_WEIGHT:
            raise ValueError("V1 line RiskRule must inspect single-line weight")
        if self.scope is RiskRuleScope.GLOBAL and self.subject is RiskSubject.SINGLE_LINE_WEIGHT:
            raise ValueError("single-line RiskRule must be line scoped")
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "boolean_threshold": self.boolean_threshold,
            "decimal_threshold": self.decimal_threshold,
            "integer_threshold": self.integer_threshold,
            "missing_action": self.missing_action,
            "operator": self.operator,
            "ordinal": self.ordinal,
            "risk_policy_id": self.risk_policy_id,
            "risk_rule_id": self.risk_rule_id,
            "rule_code": self.rule_code,
            "scope": self.scope,
            "severity": self.severity,
            "subject": self.subject,
            "text_threshold": self.text_threshold,
            "value_unit": self.value_unit,
        }))


@dataclass(frozen=True, slots=True)
class RiskPolicyPlan:
    risk_policy_id: UUID
    policy_code: str
    version: int
    supersedes_policy_id: UUID | None
    authority_scope: RiskAuthorityScope
    rules: tuple[RiskRulePlan, ...]
    code_artifact: DecisionArtifactBinding
    config_artifact: DecisionArtifactBinding
    provenance_sha256: str
    rule_roster_sha256: str = field(init=False)
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.policy_code) or self.version < 1:
            raise ValueError("RiskPolicy identity is invalid")
        if (self.version == 1) != (self.supersedes_policy_id is None):
            raise ValueError("RiskPolicy supersession shape is invalid")
        if not self.rules or tuple(item.ordinal for item in self.rules) != tuple(range(1, len(self.rules) + 1)):
            raise ValueError("Risk rule roster must be non-empty and contiguous")
        if any(item.risk_policy_id != self.risk_policy_id for item in self.rules):
            raise ValueError("RiskRule belongs to a different policy")
        if len({item.rule_code for item in self.rules}) != len(self.rules):
            raise ValueError("Risk rule roster contains a duplicate")
        object.__setattr__(self, "provenance_sha256", _sha(self.provenance_sha256, "Risk provenance"))
        roster_hash = canonical_json_sha256(tuple({
            "content_sha256": item.content_sha256,
            "ordinal": item.ordinal,
            "risk_rule_id": item.risk_rule_id,
        } for item in self.rules))
        object.__setattr__(self, "rule_roster_sha256", roster_hash)
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "authority_scope": self.authority_scope,
            "code_artifact": self.code_artifact,
            "config_artifact": self.config_artifact,
            "policy_code": self.policy_code,
            "provenance_sha256": self.provenance_sha256,
            "risk_policy_id": self.risk_policy_id,
            "rule_count": len(self.rules),
            "rule_roster_sha256": roster_hash,
            "supersedes_policy_id": self.supersedes_policy_id,
            "version": self.version,
        }))


@dataclass(frozen=True, slots=True)
class PreparedRiskLine:
    portfolio_line_id: UUID
    ordinal: int
    status: PortfolioLineStatus
    proposed_weight: Decimal
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", _sha(self.content_sha256, "PortfolioLine hash"))


@dataclass(frozen=True, slots=True)
class PreparedRiskInputs:
    portfolio_proposal_id: UUID
    proposal_content_sha256: str
    proposal_status: PortfolioProposalStatus
    line_count: int
    included_count: int
    not_estimable_count: int
    gross_weight: Decimal
    net_weight: Decimal
    cash_weight: Decimal
    qualification_count: int
    lines: tuple[PreparedRiskLine, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_content_sha256", _sha(self.proposal_content_sha256, "PortfolioProposal hash"))
        if self.line_count != len(self.lines) or tuple(item.ordinal for item in self.lines) != tuple(range(1, len(self.lines) + 1)):
            raise ValueError("Risk requires the complete PortfolioLine roster")


@dataclass(frozen=True, slots=True)
class RiskReasonPlan:
    risk_reason_id: UUID
    ordinal: int
    rule: RiskRulePlan
    portfolio_line_id: UUID | None
    result: RiskRuleResult
    observed_decimal: Decimal | None
    observed_integer: int | None
    observed_text: str | None
    observed_boolean: bool | None
    reason_code: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "observed_boolean": self.observed_boolean,
            "observed_decimal": self.observed_decimal,
            "observed_integer": self.observed_integer,
            "observed_text": self.observed_text,
            "ordinal": self.ordinal,
            "portfolio_line_id": self.portfolio_line_id,
            "reason_code": self.reason_code,
            "result": self.result,
            "risk_reason_id": self.risk_reason_id,
            "risk_rule_id": self.rule.risk_rule_id,
        }))


@dataclass(frozen=True, slots=True)
class RiskDecisionAuthority:
    risk_decision_id: UUID
    prepared: PreparedRiskInputs
    policy: RiskPolicyPlan
    status: RiskDecisionStatus
    reasons: tuple[RiskReasonPlan, ...]
    reason_roster_sha256: str
    request_identity: str
    request_sha256: str
    command_receipt_id: UUID
    decided_at: datetime
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_roster_sha256", _sha(self.reason_roster_sha256, "Risk reason roster hash"))
        object.__setattr__(self, "decided_at", require_utc(self.decided_at, field="Risk decided_at"))
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "authority_scope": self.policy.authority_scope,
            "portfolio_proposal_id": self.prepared.portfolio_proposal_id,
            "reason_count": len(self.reasons),
            "reason_roster_sha256": self.reason_roster_sha256,
            "request_identity": self.request_identity,
            "request_sha256": self.request_sha256,
            "risk_decision_id": self.risk_decision_id,
            "risk_policy_id": self.policy.risk_policy_id,
            "status": self.status,
        }))


def build_risk_decision(
    *,
    risk_decision_id: UUID,
    prepared: PreparedRiskInputs,
    policy: RiskPolicyPlan,
    request_identity: str,
    request_sha256: str,
    command_receipt_id: UUID,
    decided_at: datetime,
    reason_id_factory: Callable[[RiskRulePlan, PreparedRiskLine | None], UUID],
) -> RiskDecisionAuthority:
    request_sha256 = _sha(request_sha256, "Risk request hash")
    reasons: list[RiskReasonPlan] = []
    for rule in policy.rules:
        subjects: tuple[PreparedRiskLine | None, ...] = prepared.lines if rule.scope is RiskRuleScope.LINE else (None,)
        for line in subjects:
            observed = _observed(prepared, rule, line)
            result = _compare(rule, observed)
            reasons.append(RiskReasonPlan(
                risk_reason_id=reason_id_factory(rule, line),
                ordinal=len(reasons) + 1,
                rule=rule,
                portfolio_line_id=line.portfolio_line_id if line else None,
                result=result,
                observed_decimal=observed if isinstance(observed, Decimal) else None,
                observed_integer=observed if isinstance(observed, int) and not isinstance(observed, bool) else None,
                observed_text=observed if isinstance(observed, str) else None,
                observed_boolean=observed if isinstance(observed, bool) else None,
                reason_code=f"RULE_{result.value}",
            ))
    reason_tuple = tuple(reasons)
    if any(item.result is RiskRuleResult.FAIL and item.rule.severity is RiskSeverity.REJECT for item in reason_tuple):
        status = RiskDecisionStatus.REJECTED
    elif any(item.result in {RiskRuleResult.UNKNOWN, RiskRuleResult.FAIL} for item in reason_tuple):
        status = RiskDecisionStatus.UNKNOWN
    elif prepared.proposal_status is PortfolioProposalStatus.NO_ACTION:
        status = RiskDecisionStatus.NO_ACTION
    elif prepared.proposal_status is PortfolioProposalStatus.NOT_ESTIMABLE:
        status = RiskDecisionStatus.UNKNOWN
    else:
        status = RiskDecisionStatus.AUTHORIZED
    roster_hash = canonical_json_sha256(tuple({
        "content_sha256": item.content_sha256,
        "ordinal": item.ordinal,
        "risk_reason_id": item.risk_reason_id,
    } for item in reason_tuple))
    return RiskDecisionAuthority(
        risk_decision_id=risk_decision_id, prepared=prepared, policy=policy,
        status=status, reasons=reason_tuple, reason_roster_sha256=roster_hash,
        request_identity=request_identity, request_sha256=request_sha256,
        command_receipt_id=command_receipt_id, decided_at=decided_at,
    )


def _observed(prepared: PreparedRiskInputs, rule: RiskRulePlan, line: PreparedRiskLine | None):
    if rule.subject is RiskSubject.PROPOSAL_STATUS:
        return prepared.proposal_status.value
    if rule.subject is RiskSubject.LINE_COUNT:
        return prepared.included_count
    if rule.subject is RiskSubject.GROSS_WEIGHT:
        return prepared.gross_weight
    if rule.subject is RiskSubject.NET_WEIGHT:
        return prepared.net_weight
    if rule.subject is RiskSubject.CASH_WEIGHT:
        return prepared.cash_weight
    if rule.subject is RiskSubject.ESTIMABILITY:
        return prepared.not_estimable_count == 0
    if rule.subject is RiskSubject.QUALIFICATION_PRESENCE:
        return prepared.qualification_count > 0
    if rule.subject is RiskSubject.SINGLE_LINE_WEIGHT and line is not None:
        return line.proposed_weight
    return None


def _compare(rule: RiskRulePlan, observed) -> RiskRuleResult:
    if observed is None:
        return RiskRuleResult.FAIL if rule.missing_action is RiskMissingAction.FAIL else RiskRuleResult.UNKNOWN
    threshold = next(value for value in (
        rule.decimal_threshold, rule.integer_threshold,
        rule.text_threshold, rule.boolean_threshold,
    ) if value is not None)
    if rule.operator is RiskOperator.EQUALS:
        passed = observed == threshold
    elif rule.operator is RiskOperator.AT_MOST:
        passed = observed <= threshold
    else:
        passed = observed >= threshold
    return RiskRuleResult.PASS if passed else RiskRuleResult.FAIL


__all__ = [
    "PreparedRiskInputs", "PreparedRiskLine", "RiskAuthorityScope",
    "RiskDecisionAuthority", "RiskDecisionStatus", "RiskMissingAction",
    "RiskOperator", "RiskPolicyPlan", "RiskReasonPlan", "RiskRulePlan",
    "RiskRuleResult", "RiskRuleScope", "RiskSeverity", "RiskSubject",
    "build_risk_decision",
]
