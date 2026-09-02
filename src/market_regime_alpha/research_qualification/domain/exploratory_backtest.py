"""Frozen lineage root for a two-arm exploratory retrospective backtest."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


class BacktestArmKind(StrEnum):
    RULE_BASELINE = "RULE_BASELINE"
    MODEL_CHALLENGER = "MODEL_CHALLENGER"


class BacktestSessionRole(StrEnum):
    FIT_INPUT = "FIT_INPUT"
    PURGE = "PURGE"
    EVALUATION = "EVALUATION"
    EMBARGO = "EMBARGO"


class BacktestCostKind(StrEnum):
    COMMISSION_BPS = "COMMISSION_BPS"
    SLIPPAGE_BPS = "SLIPPAGE_BPS"
    STAMP_DUTY_BPS = "STAMP_DUTY_BPS"


@dataclass(frozen=True, slots=True)
class BacktestArmPlan:
    exploratory_backtest_arm_id: UUID
    ordinal: int
    kind: BacktestArmKind
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("arm ordinal must be positive")
        object.__setattr__(self, "content_sha256", ContentHash(canonical_json_sha256({
            "exploratory_backtest_arm_id": self.exploratory_backtest_arm_id,
            "kind": self.kind,
            "ordinal": self.ordinal,
        })))


@dataclass(frozen=True, slots=True)
class BacktestFoldSessionPlan:
    exploratory_backtest_fold_session_id: UUID
    ordinal: int
    trading_session_id: UUID
    session_date: date
    role: BacktestSessionRole
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("fold session ordinal must be positive")
        object.__setattr__(self, "content_sha256", ContentHash(canonical_json_sha256({
            "exploratory_backtest_fold_session_id": self.exploratory_backtest_fold_session_id,
            "ordinal": self.ordinal,
            "role": self.role,
            "session_date": self.session_date,
            "trading_session_id": self.trading_session_id,
        })))


@dataclass(frozen=True, slots=True)
class BacktestFoldPlan:
    exploratory_backtest_fold_id: UUID
    ordinal: int
    purpose: PartitionPurpose
    exchange_code: str
    purge_sessions: int
    embargo_sessions: int
    evaluation_protocol_id: UUID
    evaluation_protocol_sha256: ContentHash | str
    sessions: tuple[BacktestFoldSessionPlan, ...]
    session_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("fold ordinal must be positive")
        if self.purpose not in {
            PartitionPurpose.DISCOVERY,
            PartitionPurpose.FIT,
            PartitionPurpose.VALIDATION,
        }:
            raise ValueError("exploratory fold purpose cannot be protected or prospective")
        if self.exchange_code not in {"XSHG", "XSHE"}:
            raise ValueError("fold exchange_code is invalid")
        if self.purge_sessions < 0 or self.embargo_sessions < 0:
            raise ValueError("purge and embargo must be non-negative")
        if not self.sessions:
            raise ValueError("fold session roster must be non-empty")
        if tuple(item.ordinal for item in self.sessions) != tuple(range(1, len(self.sessions) + 1)):
            raise ValueError("fold session ordinals must be contiguous")
        dates = tuple(item.session_date for item in self.sessions)
        if dates != tuple(sorted(dates)) or len(set(dates)) != len(dates):
            raise ValueError("fold sessions must be strictly chronological")
        role_order = {
            BacktestSessionRole.FIT_INPUT: 1,
            BacktestSessionRole.PURGE: 2,
            BacktestSessionRole.EVALUATION: 3,
            BacktestSessionRole.EMBARGO: 4,
        }
        orders = tuple(role_order[item.role] for item in self.sessions)
        if orders != tuple(sorted(orders)):
            raise ValueError("fold role roster must be chronological")
        if sum(item.role is BacktestSessionRole.PURGE for item in self.sessions) != self.purge_sessions:
            raise ValueError("fold purge roster does not match purge_sessions")
        if sum(item.role is BacktestSessionRole.EMBARGO for item in self.sessions) != self.embargo_sessions:
            raise ValueError("fold embargo roster does not match embargo_sessions")
        if not any(item.role is BacktestSessionRole.EVALUATION for item in self.sessions):
            raise ValueError("fold requires at least one Evaluation session")
        protocol_hash = ContentHash(str(self.evaluation_protocol_sha256))
        roster_hash = ContentHash(canonical_json_sha256(tuple(
            {
                "content_sha256": str(item.content_sha256),
                "exploratory_backtest_fold_session_id": (
                    item.exploratory_backtest_fold_session_id
                ),
                "ordinal": item.ordinal,
            }
            for item in self.sessions
        )))
        object.__setattr__(self, "evaluation_protocol_sha256", protocol_hash)
        object.__setattr__(self, "session_roster_sha256", roster_hash)
        object.__setattr__(self, "content_sha256", ContentHash(canonical_json_sha256({
            "embargo_sessions": self.embargo_sessions,
            "evaluation_protocol_id": self.evaluation_protocol_id,
            "evaluation_protocol_sha256": str(protocol_hash),
            "exchange_code": self.exchange_code,
            "exploratory_backtest_fold_id": self.exploratory_backtest_fold_id,
            "ordinal": self.ordinal,
            "purge_sessions": self.purge_sessions,
            "purpose": self.purpose,
            "session_roster_sha256": str(roster_hash),
        })))


@dataclass(frozen=True, slots=True)
class BacktestCostAssumption:
    exploratory_backtest_cost_assumption_id: UUID
    ordinal: int
    cost_kind: BacktestCostKind
    amount_bps: Decimal
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("cost ordinal must be positive")
        if self.amount_bps < 0:
            raise ValueError("cost amount_bps must be non-negative")
        object.__setattr__(self, "content_sha256", ContentHash(canonical_json_sha256({
            "amount_bps": self.amount_bps,
            "cost_kind": self.cost_kind,
            "exploratory_backtest_cost_assumption_id": self.exploratory_backtest_cost_assumption_id,
            "ordinal": self.ordinal,
        })))


@dataclass(frozen=True, slots=True)
class ExploratoryBacktestRunPlan:
    exploratory_backtest_run_id: UUID
    run_code: str
    generation: int
    market_archive_id: UUID
    market_archive_seal_id: UUID
    hypothesis: str
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    feature_definitions: tuple[tuple[UUID, ContentHash | str], ...]
    candidate_policy_id: UUID
    candidate_policy_sha256: ContentHash | str
    context_policy_id: UUID
    context_policy_sha256: ContentHash | str
    strategy_version_id: UUID
    strategy_version_sha256: ContentHash | str
    portfolio_policy_id: UUID
    portfolio_policy_sha256: ContentHash | str
    risk_policy_id: UUID
    risk_policy_sha256: ContentHash | str
    arms: tuple[BacktestArmPlan, ...]
    folds: tuple[BacktestFoldPlan, ...]
    cost_assumptions: tuple[BacktestCostAssumption, ...]
    random_seed: int
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    evidence_lane: str = field(default="EXPLORATORY_RETROSPECTIVE", init=False)
    feature_roster_sha256: ContentHash = field(init=False)
    arm_roster_sha256: ContentHash = field(init=False)
    fold_roster_sha256: ContentHash = field(init=False)
    cost_roster_sha256: ContentHash = field(init=False)
    session_count: int = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.run_code):
            raise ValueError("run_code has an invalid format")
        if isinstance(self.generation, bool) or self.generation < 1:
            raise ValueError("generation must be positive")
        if not self.hypothesis.strip():
            raise ValueError("hypothesis is required")
        if isinstance(self.random_seed, bool) or self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        if not self.feature_definitions:
            raise ValueError("feature roster must be non-empty")
        if len({item[0] for item in self.feature_definitions}) != len(self.feature_definitions):
            raise ValueError("feature roster contains duplicates")
        expected_arms = (
            BacktestArmKind.RULE_BASELINE,
            BacktestArmKind.MODEL_CHALLENGER,
        )
        if len(self.arms) != 2:
            raise ValueError("first exploratory generation requires exactly two arms")
        if tuple(item.ordinal for item in self.arms) != (1, 2) or tuple(item.kind for item in self.arms) != expected_arms:
            raise ValueError("exploratory arm roster must be baseline then challenger")
        if not self.folds or tuple(item.ordinal for item in self.folds) != tuple(range(1, len(self.folds) + 1)):
            raise ValueError("backtest fold ordinals must be contiguous")
        if tuple(fold.sessions[0].session_date for fold in self.folds) != tuple(
            sorted(fold.sessions[0].session_date for fold in self.folds)
        ):
            raise ValueError("backtest folds must be chronological")
        if len({session.trading_session_id for fold in self.folds for session in fold.sessions}) != sum(
            len(fold.sessions) for fold in self.folds
        ):
            raise ValueError("backtest fold sessions cannot overlap")
        if not self.cost_assumptions:
            raise ValueError("cost assumption roster must be non-empty")
        if tuple(item.ordinal for item in self.cost_assumptions) != tuple(range(1, len(self.cost_assumptions) + 1)):
            raise ValueError("cost assumption ordinals must be contiguous")
        if len({item.cost_kind for item in self.cost_assumptions}) != len(self.cost_assumptions):
            raise ValueError("cost assumption kinds must be unique")
        for name in (
            "target_definition_sha256", "candidate_policy_sha256",
            "context_policy_sha256", "strategy_version_sha256",
            "portfolio_policy_sha256", "risk_policy_sha256", "provenance_sha256",
        ):
            object.__setattr__(self, name, ContentHash(str(getattr(self, name))))
        normalized_features = tuple(
            (identity, ContentHash(str(content_hash)))
            for identity, content_hash in self.feature_definitions
        )
        object.__setattr__(self, "feature_definitions", normalized_features)
        feature_hash = ContentHash(canonical_json_sha256(tuple(
            {"content_sha256": str(content_hash), "feature_definition_id": identity}
            for identity, content_hash in normalized_features
        )))
        arm_hash = ContentHash(canonical_json_sha256(tuple(
            {
                "content_sha256": str(item.content_sha256),
                "exploratory_backtest_arm_id": item.exploratory_backtest_arm_id,
                "ordinal": item.ordinal,
            }
            for item in self.arms
        )))
        fold_hash = ContentHash(canonical_json_sha256(tuple(
            {
                "content_sha256": str(item.content_sha256),
                "exploratory_backtest_fold_id": item.exploratory_backtest_fold_id,
                "ordinal": item.ordinal,
            }
            for item in self.folds
        )))
        cost_hash = ContentHash(canonical_json_sha256(tuple(
            {
                "content_sha256": str(item.content_sha256),
                "exploratory_backtest_cost_assumption_id": (
                    item.exploratory_backtest_cost_assumption_id
                ),
                "ordinal": item.ordinal,
            }
            for item in self.cost_assumptions
        )))
        session_count = sum(len(fold.sessions) for fold in self.folds)
        object.__setattr__(self, "feature_roster_sha256", feature_hash)
        object.__setattr__(self, "arm_roster_sha256", arm_hash)
        object.__setattr__(self, "fold_roster_sha256", fold_hash)
        object.__setattr__(self, "cost_roster_sha256", cost_hash)
        object.__setattr__(self, "session_count", session_count)
        object.__setattr__(self, "content_sha256", ContentHash(canonical_json_sha256({
            "arm_roster_sha256": str(arm_hash),
            "candidate_policy_id": self.candidate_policy_id,
            "candidate_policy_sha256": str(self.candidate_policy_sha256),
            "code_artifact": {
                "artifact_id": self.code_artifact.artifact_id,
                "content_sha256": str(self.code_artifact.content_sha256),
                "size_bytes": self.code_artifact.size_bytes,
            },
            "config_artifact": {
                "artifact_id": self.config_artifact.artifact_id,
                "content_sha256": str(self.config_artifact.content_sha256),
                "size_bytes": self.config_artifact.size_bytes,
            },
            "context_policy_id": self.context_policy_id,
            "context_policy_sha256": str(self.context_policy_sha256),
            "cost_roster_sha256": str(cost_hash),
            "evidence_lane": self.evidence_lane,
            "exploratory_backtest_run_id": self.exploratory_backtest_run_id,
            "feature_roster_sha256": str(feature_hash),
            "fold_roster_sha256": str(fold_hash),
            "generation": self.generation,
            "hypothesis": self.hypothesis,
            "market_archive_id": self.market_archive_id,
            "market_archive_seal_id": self.market_archive_seal_id,
            "portfolio_policy_id": self.portfolio_policy_id,
            "portfolio_policy_sha256": str(self.portfolio_policy_sha256),
            "provenance_sha256": str(self.provenance_sha256),
            "random_seed": self.random_seed,
            "risk_policy_id": self.risk_policy_id,
            "risk_policy_sha256": str(self.risk_policy_sha256),
            "session_count": session_count,
            "strategy_version_id": self.strategy_version_id,
            "strategy_version_sha256": str(self.strategy_version_sha256),
            "target_definition_id": self.target_definition_id,
            "target_definition_sha256": str(self.target_definition_sha256),
            "target_version": self.target_version,
        })))


@dataclass(frozen=True, slots=True)
class ExploratoryBacktestDatasetScope:
    retrospective: ExploratoryRetrospectiveDatasetScope
    exploratory_backtest_run_id: UUID
    exploratory_backtest_arm_id: UUID
    exploratory_backtest_fold_id: UUID
    exploratory_backtest_fold_session_id: UUID
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", ContentHash(canonical_json_sha256({
            "exploratory_backtest_arm_id": self.exploratory_backtest_arm_id,
            "exploratory_backtest_fold_id": self.exploratory_backtest_fold_id,
            "exploratory_backtest_fold_session_id": (
                self.exploratory_backtest_fold_session_id
            ),
            "exploratory_backtest_run_id": self.exploratory_backtest_run_id,
            "retrospective_scope_sha256": str(self.retrospective.content_sha256),
        })))


__all__ = [
    "BacktestArmKind", "BacktestArmPlan", "BacktestCostAssumption",
    "BacktestCostKind", "BacktestFoldPlan", "BacktestFoldSessionPlan",
    "BacktestSessionRole", "ExploratoryBacktestDatasetScope",
    "ExploratoryBacktestRunPlan",
]
