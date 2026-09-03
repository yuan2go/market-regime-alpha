"""Current generic Backtest specification contracts.

These immutable values are command/projection types.  PostgreSQL relations
remain Authority and :class:`FrozenBacktestRun` projections are never FK
targets or independent business identities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.decision_support.domain.context import (
    ContextKind,
    ContextState,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelExecutionEnvironment,
    ModelScalarParameter,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MONTH_SLICE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_QUARTER_SLICE = re.compile(r"^[0-9]{4}-Q[1-4]$")


class BacktestExecutionKind(StrEnum):
    RULE = "RULE"
    MODEL = "MODEL"


class BacktestComparisonRole(StrEnum):
    BASELINE = "BASELINE"
    CHALLENGER = "CHALLENGER"
    DIAGNOSTIC = "DIAGNOSTIC"


class BacktestContextMode(StrEnum):
    CURRENT_GATE = "CURRENT_GATE"
    OBSERVATIONAL = "OBSERVATIONAL"


class BacktestSessionRole(StrEnum):
    FIT_INPUT = "FIT_INPUT"
    PURGE = "PURGE"
    EVALUATION = "EVALUATION"
    EMBARGO = "EMBARGO"


class BacktestWalkForwardMode(StrEnum):
    FIXED = "FIXED"
    ROLLING = "ROLLING"
    EXPANDING = "EXPANDING"


class BacktestCostKind(StrEnum):
    COMMISSION_BPS = "COMMISSION_BPS"
    SLIPPAGE_BPS = "SLIPPAGE_BPS"
    STAMP_DUTY_BPS = "STAMP_DUTY_BPS"


class BacktestCostChargeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    BOTH = "BOTH"


class BacktestBindingSource(StrEnum):
    SHARED_DEFAULT = "SHARED_DEFAULT"
    ARM_OVERRIDE = "ARM_OVERRIDE"


class BacktestEvaluationScopeKind(StrEnum):
    FOLD = "FOLD"
    AGGREGATE = "AGGREGATE"
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    CONTEXT = "CONTEXT"


class FrozenBacktestSource(StrEnum):
    CURRENT_RELATIONAL = "CURRENT_RELATIONAL"
    HISTORICAL_EXACT = "HISTORICAL_EXACT"


class FrozenBacktestEvidence(StrEnum):
    CURRENT = "CURRENT"
    COMPLETED_ZERO_WRITE = "COMPLETED_ZERO_WRITE"
    DEFINITION_ONLY = "DEFINITION_ONLY"


@dataclass(frozen=True, slots=True)
class AuthorityBinding:
    authority_id: UUID
    content_sha256: ContentHash | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(str(self.content_sha256)),
        )


@dataclass(frozen=True, slots=True)
class VersionedAuthorityBinding:
    authority_id: UUID
    version: int
    content_sha256: ContentHash | str

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Authority version must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(str(self.content_sha256)),
        )


@dataclass(frozen=True, slots=True)
class BacktestPolicyDefaults:
    candidate: AuthorityBinding
    context: AuthorityBinding
    strategy: AuthorityBinding
    portfolio: AuthorityBinding
    risk: AuthorityBinding


@dataclass(frozen=True, slots=True)
class BacktestSampleMember:
    universe_revision_member_id: UUID
    instrument_id: UUID
    ordinal: int
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("sample member ordinal must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "instrument_id": self.instrument_id,
                        "ordinal": self.ordinal,
                        "universe_revision_member_id": self.universe_revision_member_id,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestFoldSession:
    exploratory_backtest_fold_session_id: UUID
    ordinal: int
    trading_session_id: UUID
    session_date: date
    role: BacktestSessionRole
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("fold session ordinal must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "exploratory_backtest_fold_session_id": self.exploratory_backtest_fold_session_id,
                        "ordinal": self.ordinal,
                        "role": self.role,
                        "session_date": self.session_date,
                        "trading_session_id": self.trading_session_id,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestFoldSpecification:
    exploratory_backtest_fold_id: UUID
    ordinal: int
    purpose: PartitionPurpose
    exchange_code: str
    purge_sessions: int
    embargo_sessions: int
    evaluation_protocol: AuthorityBinding
    sessions: tuple[BacktestFoldSession, ...]
    session_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("fold ordinal must be positive")
        if self.purpose not in {PartitionPurpose.FIT, PartitionPurpose.VALIDATION}:
            raise ValueError("current Backtest fold must be FIT or VALIDATION")
        if self.exchange_code not in {"XSHG", "XSHE"}:
            raise ValueError("fold exchange_code is invalid")
        if self.purge_sessions < 0 or self.embargo_sessions < 0:
            raise ValueError("purge and embargo must be non-negative")
        if not self.sessions:
            raise ValueError("fold session roster must be non-empty")
        if tuple(item.ordinal for item in self.sessions) != tuple(range(1, len(self.sessions) + 1)):
            raise ValueError("fold session ordinals must be contiguous")
        dates = tuple(item.session_date for item in self.sessions)
        if dates != tuple(sorted(dates)) or len({item.trading_session_id for item in self.sessions}) != len(self.sessions):
            raise ValueError("fold sessions must be chronological and unique")
        if sum(item.role is BacktestSessionRole.PURGE for item in self.sessions) != (self.purge_sessions):
            raise ValueError("fold purge roster does not match purge_sessions")
        if sum(item.role is BacktestSessionRole.EMBARGO for item in self.sessions) != (self.embargo_sessions):
            raise ValueError("fold embargo roster does not match embargo_sessions")
        required = BacktestSessionRole.FIT_INPUT if self.purpose is PartitionPurpose.FIT else BacktestSessionRole.EVALUATION
        if not any(item.role is required for item in self.sessions):
            raise ValueError(f"{self.purpose.value} fold requires {required.value}")
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "exploratory_backtest_fold_session_id": item.exploratory_backtest_fold_session_id,
                        "ordinal": item.ordinal,
                    }
                    for item in self.sessions
                )
            )
        )
        object.__setattr__(self, "session_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "embargo_sessions": self.embargo_sessions,
                        "evaluation_protocol": _authority_payload(self.evaluation_protocol),
                        "exchange_code": self.exchange_code,
                        "exploratory_backtest_fold_id": self.exploratory_backtest_fold_id,
                        "ordinal": self.ordinal,
                        "purge_sessions": self.purge_sessions,
                        "purpose": self.purpose,
                        "session_roster_sha256": str(roster_hash),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestFoldDependency:
    dependency_id: UUID
    ordinal: int
    fit_fold_id: UUID
    validation_fold_id: UUID
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("fold dependency ordinal must be positive")
        if self.fit_fold_id == self.validation_fold_id:
            raise ValueError("fold cannot depend on itself")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "dependency_id": self.dependency_id,
                        "fit_fold_id": self.fit_fold_id,
                        "ordinal": self.ordinal,
                        "validation_fold_id": self.validation_fold_id,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestArmFold:
    arm_fold_id: UUID
    ordinal: int
    arm_id: UUID
    fold_id: UUID
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("arm-fold ordinal must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "arm_fold_id": self.arm_fold_id,
                        "arm_id": self.arm_id,
                        "fold_id": self.fold_id,
                        "ordinal": self.ordinal,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestModelTrainingRecipe:
    """Current pre-FIT recipe; cutoff, sample and fitted bytes remain execution facts."""

    algorithm_code: str
    algorithm_version: str
    implementation_sha256: ContentHash | str
    environment: ModelExecutionEnvironment
    hyperparameters: tuple[ModelScalarParameter, ...]
    hyperparameter_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.algorithm_code):
            raise ValueError("Model recipe algorithm_code is invalid")
        if not _VERSION.fullmatch(self.algorithm_version):
            raise ValueError("Model recipe algorithm_version is invalid")
        if tuple(item.ordinal for item in self.hyperparameters) != tuple(range(1, len(self.hyperparameters) + 1)) or len(
            {item.parameter_code for item in self.hyperparameters}
        ) != len(self.hyperparameters):
            raise ValueError("Model recipe hyperparameter roster must be ordered and unique")
        implementation_hash = ContentHash(str(self.implementation_sha256))
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "ordinal": item.ordinal,
                        "parameter_code": item.parameter_code,
                    }
                    for item in self.hyperparameters
                )
            )
        )
        object.__setattr__(self, "implementation_sha256", implementation_hash)
        object.__setattr__(self, "hyperparameter_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "algorithm_code": self.algorithm_code,
                        "algorithm_version": self.algorithm_version,
                        "environment_sha256": str(self.environment.content_sha256),
                        "hyperparameter_roster_sha256": str(roster_hash),
                        "implementation_sha256": str(implementation_hash),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestModelTrainingRequirement:
    requirement_id: UUID
    ordinal: int
    model_arm_id: UUID
    fit_fold_id: UUID
    validation_fold_id: UUID
    model_definition: AuthorityBinding
    training_metric: AuthorityBinding | None = None
    planned_model_version: int | None = None
    recipe: BacktestModelTrainingRecipe | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Model training requirement ordinal must be positive")
        if self.planned_model_version is not None and (isinstance(self.planned_model_version, bool) or self.planned_model_version < 1):
            raise ValueError("planned Model version must be positive")
        content: dict[str, object] = {
            "fit_fold_id": self.fit_fold_id,
            "model_arm_id": self.model_arm_id,
            "model_definition": _authority_payload(self.model_definition),
            "ordinal": self.ordinal,
            "requirement_id": self.requirement_id,
            "validation_fold_id": self.validation_fold_id,
        }
        # Private historical projections predate these current-only fields.
        # Omitting absent values preserves every historical projection hash.
        if self.training_metric is not None:
            content["training_metric"] = _authority_payload(self.training_metric)
        if self.planned_model_version is not None:
            content["planned_model_version"] = self.planned_model_version
        if self.recipe is not None:
            content["recipe_sha256"] = str(self.recipe.content_sha256)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(canonical_json_sha256(content)),
        )


@dataclass(frozen=True, slots=True)
class BacktestWalkForwardPolicy:
    policy_code: str
    policy_version: int
    mode: BacktestWalkForwardMode
    minimum_fit_sessions: int
    validation_sessions: int
    step_sessions: int
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.policy_code):
            raise ValueError("walk-forward policy_code has an invalid format")
        for name in (
            "policy_version",
            "minimum_fit_sessions",
            "validation_sessions",
            "step_sessions",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "minimum_fit_sessions": self.minimum_fit_sessions,
                        "mode": self.mode,
                        "policy_code": self.policy_code,
                        "policy_version": self.policy_version,
                        "step_sessions": self.step_sessions,
                        "validation_sessions": self.validation_sessions,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestCostAssumption:
    assumption_id: UUID
    ordinal: int
    cost_kind: BacktestCostKind
    charge_side: BacktestCostChargeSide
    amount_bps: Decimal
    arm_id: UUID | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("cost ordinal must be positive")
        if self.amount_bps < 0:
            raise ValueError("cost amount_bps must be non-negative")
        amount = bounded_decimal(
            self.amount_bps,
            field="Backtest cost amount_bps",
            precision=24,
            scale=12,
        )
        object.__setattr__(self, "amount_bps", amount)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "amount_bps": amount,
                        "arm_id": self.arm_id,
                        "assumption_id": self.assumption_id,
                        "charge_side": self.charge_side,
                        "cost_kind": self.cost_kind,
                        "ordinal": self.ordinal,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestEvaluationRequirement:
    requirement_id: UUID
    ordinal: int
    fold_id: UUID | None
    evaluation_protocol: AuthorityBinding
    primary: bool
    scope_kind: BacktestEvaluationScopeKind = BacktestEvaluationScopeKind.FOLD
    arm_id: UUID | None = None
    slice_key: str | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Evaluation requirement ordinal must be positive")
        if self.arm_id is None:
            raise ValueError("current Evaluation requirement requires an exact arm")
        if self.scope_kind is BacktestEvaluationScopeKind.FOLD:
            if self.fold_id is None or self.slice_key is not None:
                raise ValueError("FOLD Evaluation requires a Fold and no slice_key")
        elif self.scope_kind is BacktestEvaluationScopeKind.AGGREGATE:
            if self.fold_id is not None or self.slice_key is not None:
                raise ValueError("AGGREGATE Evaluation forbids Fold and slice_key")
        elif self.fold_id is not None or self.slice_key is None or not self.slice_key:
            raise ValueError("time/Context Evaluation forbids Fold and requires slice_key")
        if self.scope_kind is BacktestEvaluationScopeKind.CONTEXT:
            parse_backtest_context_slice(self.slice_key)
        elif self.scope_kind is BacktestEvaluationScopeKind.MONTH and not (
            self.slice_key is not None and _MONTH_SLICE.fullmatch(self.slice_key)
        ):
            raise ValueError("MONTH slice_key must be YYYY-MM")
        elif self.scope_kind is BacktestEvaluationScopeKind.QUARTER and not (
            self.slice_key is not None and _QUARTER_SLICE.fullmatch(self.slice_key)
        ):
            raise ValueError("QUARTER slice_key must be YYYY-QN")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "arm_id": self.arm_id,
                        "evaluation_protocol": _authority_payload(self.evaluation_protocol),
                        "fold_id": self.fold_id,
                        "ordinal": self.ordinal,
                        "primary": self.primary,
                        "requirement_id": self.requirement_id,
                        "scope_kind": self.scope_kind,
                        "slice_key": self.slice_key,
                    }
                )
            ),
        )


def parse_backtest_context_slice(
    value: str | None,
) -> tuple[ContextKind, ContextState]:
    if value is None:
        raise ValueError("CONTEXT slice_key must be KIND:STATE")
    try:
        kind_text, state_text = value.split(":")
        return ContextKind(kind_text), ContextState(state_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("CONTEXT slice_key must be KIND:STATE") from exc


@dataclass(frozen=True, slots=True)
class BacktestArmSpecification:
    exploratory_backtest_arm_id: UUID
    ordinal: int
    arm_code: str
    execution_kind: BacktestExecutionKind
    comparison_role: BacktestComparisonRole
    context_mode: BacktestContextMode
    candidate: AuthorityBinding
    context: AuthorityBinding
    strategy: AuthorityBinding
    model: AuthorityBinding | None
    portfolio: AuthorityBinding
    risk: AuthorityBinding
    effective_cost_roster_sha256: ContentHash | str
    candidate_binding_source: BacktestBindingSource = BacktestBindingSource.SHARED_DEFAULT
    context_binding_source: BacktestBindingSource = BacktestBindingSource.SHARED_DEFAULT
    strategy_binding_source: BacktestBindingSource = BacktestBindingSource.SHARED_DEFAULT
    portfolio_binding_source: BacktestBindingSource = BacktestBindingSource.SHARED_DEFAULT
    risk_binding_source: BacktestBindingSource = BacktestBindingSource.SHARED_DEFAULT
    cost_binding_source: BacktestBindingSource = BacktestBindingSource.SHARED_DEFAULT
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("arm ordinal must be positive")
        if not _CODE.fullmatch(self.arm_code):
            raise ValueError("arm_code has an invalid format")
        if (self.execution_kind is BacktestExecutionKind.MODEL) != (self.model is not None):
            raise ValueError("MODEL arm requires Model; RULE arm forbids Model")
        cost_hash = ContentHash(str(self.effective_cost_roster_sha256))
        object.__setattr__(self, "effective_cost_roster_sha256", cost_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "arm_code": self.arm_code,
                        "candidate": _authority_payload(self.candidate),
                        "candidate_binding_source": self.candidate_binding_source,
                        "comparison_role": self.comparison_role,
                        "context": _authority_payload(self.context),
                        "context_binding_source": self.context_binding_source,
                        "context_mode": self.context_mode,
                        "cost_binding_source": self.cost_binding_source,
                        "effective_cost_roster_sha256": str(cost_hash),
                        "execution_kind": self.execution_kind,
                        "exploratory_backtest_arm_id": self.exploratory_backtest_arm_id,
                        "model": (None if self.model is None else _authority_payload(self.model)),
                        "ordinal": self.ordinal,
                        "portfolio": _authority_payload(self.portfolio),
                        "portfolio_binding_source": self.portfolio_binding_source,
                        "risk": _authority_payload(self.risk),
                        "risk_binding_source": self.risk_binding_source,
                        "strategy": _authority_payload(self.strategy),
                        "strategy_binding_source": self.strategy_binding_source,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class FrozenBacktestRun:
    """Immutable executor projection over one canonical Backtest identity."""

    exploratory_backtest_run_id: UUID
    run_code: str
    generation: int
    definition_sha256: ContentHash | str
    specification_sha256: ContentHash | str
    source: FrozenBacktestSource
    evidence: FrozenBacktestEvidence
    arms: tuple[BacktestArmSpecification, ...]
    folds: tuple[BacktestFoldSpecification, ...]
    fold_dependencies: tuple[BacktestFoldDependency, ...]
    arm_folds: tuple[BacktestArmFold, ...]
    model_training_requirements: tuple[BacktestModelTrainingRequirement, ...]
    distinct_trading_session_count: int
    fold_session_binding_count: int
    evaluation_requirements: tuple[BacktestEvaluationRequirement, ...] = ()
    projection_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        definition_hash = ContentHash(str(self.definition_sha256))
        specification_hash = ContentHash(str(self.specification_sha256))
        object.__setattr__(self, "definition_sha256", definition_hash)
        object.__setattr__(self, "specification_sha256", specification_hash)
        if not self.arms or not self.folds:
            raise ValueError("Frozen Backtest projection requires arms and folds")
        if self.distinct_trading_session_count < 1:
            raise ValueError("distinct trading Session count must be positive")
        if self.fold_session_binding_count < self.distinct_trading_session_count:
            raise ValueError("fold Session binding count cannot be smaller than distinct count")
        projection: dict[str, object] = {
            "arm_content_sha256": tuple(str(item.content_sha256) for item in self.arms),
            "definition_sha256": str(definition_hash),
            "distinct_trading_session_count": self.distinct_trading_session_count,
            "evidence": self.evidence,
            "exploratory_backtest_run_id": self.exploratory_backtest_run_id,
            "fold_content_sha256": tuple(str(item.content_sha256) for item in self.folds),
            "fold_dependency_content_sha256": tuple(str(item.content_sha256) for item in self.fold_dependencies),
            "fold_session_binding_count": self.fold_session_binding_count,
            "run_code": self.run_code,
            "source": self.source,
            "specification_sha256": str(specification_hash),
        }
        # Historical exact projections did not own the current relational
        # requirement closure.  Omitting this key for the private decoder keeps
        # every previously frozen projection byte/hash stable.
        if self.evaluation_requirements:
            projection["evaluation_requirement_content_sha256"] = tuple(str(item.content_sha256) for item in self.evaluation_requirements)
        object.__setattr__(
            self,
            "projection_sha256",
            ContentHash(canonical_json_sha256(projection)),
        )


@dataclass(frozen=True, slots=True)
class BacktestSpecification:
    """Complete application-level predeclaration for a current Backtest Run."""

    exploratory_backtest_run_id: UUID
    run_code: str
    generation: int
    hypothesis: str
    market_archive: AuthorityBinding
    market_archive_seal: AuthorityBinding
    universe_revision: AuthorityBinding
    eligibility_policy: AuthorityBinding
    sample_scope_code: str
    sample_members: tuple[BacktestSampleMember, ...]
    exchange_code: str
    first_trading_session_id: UUID
    last_trading_session_id: UUID
    feature_definitions: tuple[AuthorityBinding, ...]
    target: VersionedAuthorityBinding
    defaults: BacktestPolicyDefaults
    arms: tuple[BacktestArmSpecification, ...]
    folds: tuple[BacktestFoldSpecification, ...]
    fold_dependencies: tuple[BacktestFoldDependency, ...]
    arm_folds: tuple[BacktestArmFold, ...]
    model_training_requirements: tuple[BacktestModelTrainingRequirement, ...]
    walk_forward_policy: BacktestWalkForwardPolicy
    cost_assumptions: tuple[BacktestCostAssumption, ...]
    evaluation_requirements: tuple[BacktestEvaluationRequirement, ...]
    random_seed: int
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    sample_algorithm_version: int = 1
    sample_input_key: str = "ROOT_RANDOM_SEED"
    specification_schema_version: int = field(default=1, init=False)
    definition_version: int = field(default=1, init=False)
    evidence_lane: str = field(default="EXPLORATORY_RETROSPECTIVE", init=False)
    formal_provider_state: str = field(default="BLOCKED", init=False)
    formal_pit_state: str = field(default="BLOCKED", init=False)
    formal_oos_state: str = field(default="NOT_RUN", init=False)
    prospective_proven: bool = field(default=False, init=False)
    alpha_proven: bool = field(default=False, init=False)
    distinct_trading_session_count: int = field(init=False)
    fold_session_binding_count: int = field(init=False)
    sample_roster_sha256: ContentHash = field(init=False)
    feature_roster_sha256: ContentHash = field(init=False)
    arm_roster_sha256: ContentHash = field(init=False)
    fold_roster_sha256: ContentHash = field(init=False)
    dependency_roster_sha256: ContentHash = field(init=False)
    arm_fold_roster_sha256: ContentHash = field(init=False)
    model_training_requirement_roster_sha256: ContentHash = field(init=False)
    cost_roster_sha256: ContentHash = field(init=False)
    evaluation_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)
    definition_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.run_code):
            raise ValueError("run_code has an invalid format")
        if isinstance(self.generation, bool) or self.generation < 1:
            raise ValueError("generation must be positive")
        if not self.hypothesis.strip():
            raise ValueError("hypothesis is required")
        if self.exchange_code not in {"XSHG", "XSHE"}:
            raise ValueError("exchange_code is invalid")
        if isinstance(self.random_seed, bool) or self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        if not _CODE.fullmatch(self.sample_scope_code):
            raise ValueError("sample_scope_code has an invalid format")
        if isinstance(self.sample_algorithm_version, bool) or self.sample_algorithm_version < 1:
            raise ValueError("sample_algorithm_version must be positive")
        if not self.sample_input_key:
            raise ValueError("sample_input_key is required")
        _require_contiguous("sample member", self.sample_members)
        if len({item.instrument_id for item in self.sample_members}) != len(self.sample_members) or len(
            {item.universe_revision_member_id for item in self.sample_members}
        ) != len(self.sample_members):
            raise ValueError("sample member roster contains duplicates")
        if not self.feature_definitions or len({item.authority_id for item in self.feature_definitions}) != len(self.feature_definitions):
            raise ValueError("Feature roster must be non-empty and unique")
        _require_contiguous("arm", self.arms)
        if len({item.exploratory_backtest_arm_id for item in self.arms}) != len(self.arms):
            raise ValueError("arm identities must be unique")
        if len({item.arm_code for item in self.arms}) != len(self.arms):
            raise ValueError("arm codes must be unique")
        _require_contiguous("fold", self.folds)
        fold_by_id = {item.exploratory_backtest_fold_id: item for item in self.folds}
        if len(fold_by_id) != len(self.folds):
            raise ValueError("fold identities must be unique")
        if any(item.exchange_code != self.exchange_code for item in self.folds):
            raise ValueError("fold exchange does not match specification")
        fold_cutoffs = tuple(max(row.session_date for row in fold.sessions) for fold in self.folds)
        if fold_cutoffs != tuple(sorted(fold_cutoffs)):
            raise ValueError("fold cutoffs must be chronological")
        session_dates: dict[UUID, date] = {}
        for fold in self.folds:
            for session in fold.sessions:
                previous = session_dates.setdefault(session.trading_session_id, session.session_date)
                if previous != session.session_date:
                    raise ValueError("trading Session identity has conflicting dates")
        first = min(session_dates, key=session_dates.__getitem__)
        last = max(session_dates, key=session_dates.__getitem__)
        if first != self.first_trading_session_id or last != self.last_trading_session_id:
            raise ValueError("specification Session range does not match folds")
        _require_contiguous("fold dependency", self.fold_dependencies)
        dependency_ids = {item.dependency_id for item in self.fold_dependencies}
        if len(dependency_ids) != len(self.fold_dependencies):
            raise ValueError("fold dependency identities must be unique")
        validation_sources: set[UUID] = set()
        for dependency in self.fold_dependencies:
            fit = fold_by_id.get(dependency.fit_fold_id)
            validation = fold_by_id.get(dependency.validation_fold_id)
            if fit is None or validation is None:
                raise ValueError("fold dependency references an unknown fold")
            if fit.purpose is not PartitionPurpose.FIT or (validation.purpose is not PartitionPurpose.VALIDATION):
                raise ValueError("fold dependency must be FIT to VALIDATION")
            if fit.ordinal >= validation.ordinal:
                raise ValueError("FIT dependency must precede VALIDATION")
            if validation.exploratory_backtest_fold_id in validation_sources:
                raise ValueError("VALIDATION fold has multiple FIT dependencies")
            validation_sources.add(validation.exploratory_backtest_fold_id)
        expected_validations = {item.exploratory_backtest_fold_id for item in self.folds if item.purpose is PartitionPurpose.VALIDATION}
        if validation_sources != expected_validations:
            raise ValueError("every VALIDATION fold requires an exact FIT dependency")
        _require_contiguous("arm-fold", self.arm_folds)
        arm_by_id = {item.exploratory_backtest_arm_id: item for item in self.arms}
        actual_arm_folds = {(item.arm_id, item.fold_id) for item in self.arm_folds}
        if len(actual_arm_folds) != len(self.arm_folds) or any(
            arm_id not in arm_by_id or fold_id not in fold_by_id for arm_id, fold_id in actual_arm_folds
        ):
            raise ValueError("arm-fold roster contains a duplicate or unknown binding")
        if {arm_id for arm_id, _ in actual_arm_folds} != set(arm_by_id):
            raise ValueError("every arm must participate in at least one fold")
        if {fold_id for _, fold_id in actual_arm_folds} != set(fold_by_id):
            raise ValueError("every fold must contain at least one participating arm")
        if self.model_training_requirements:
            _require_contiguous("Model training requirement", self.model_training_requirements)
        dependency_pairs = {(item.fit_fold_id, item.validation_fold_id) for item in self.fold_dependencies}
        model_arm_ids = {arm_id for arm_id, arm in arm_by_id.items() if arm.execution_kind is BacktestExecutionKind.MODEL}
        actual_requirements: set[tuple[UUID, UUID, UUID]] = set()
        planned_versions: set[tuple[UUID, int]] = set()
        for requirement in self.model_training_requirements:
            arm = arm_by_id.get(requirement.model_arm_id)
            pair = (requirement.fit_fold_id, requirement.validation_fold_id)
            if arm is None or arm.execution_kind is not BacktestExecutionKind.MODEL or arm.model != requirement.model_definition:
                raise ValueError("Model training requirement does not match a Model arm")
            if pair not in dependency_pairs:
                raise ValueError("Model training requirement lacks exact FoldDependency")
            if requirement.training_metric is None:
                raise ValueError("current Model training requirement requires an exact training metric")
            if requirement.planned_model_version is None:
                raise ValueError("current Model training requirement requires a planned Model version")
            if requirement.recipe is None:
                raise ValueError("current Model training requirement requires a training recipe")
            version_key = (
                requirement.model_definition.authority_id,
                requirement.planned_model_version,
            )
            if version_key in planned_versions:
                raise ValueError("planned Model version is duplicated")
            planned_versions.add(version_key)
            key = (requirement.model_arm_id, *pair)
            if key in actual_requirements:
                raise ValueError("Model training requirement is duplicated")
            actual_requirements.add(key)
        fit_by_validation = {dependency.validation_fold_id: dependency.fit_fold_id for dependency in self.fold_dependencies}
        expected_requirements = {
            (arm_id, fit_by_validation[validation_id], validation_id)
            for arm_id, validation_id in actual_arm_folds
            if arm_id in model_arm_ids and fold_by_id[validation_id].purpose is PartitionPurpose.VALIDATION
        }
        if actual_requirements != expected_requirements:
            raise ValueError("every Model validation requires one exact training requirement")
        if any((arm_id, fit_id) not in actual_arm_folds for arm_id, fit_id, _ in expected_requirements):
            raise ValueError("every Model training requirement requires FIT arm participation")
        _require_contiguous("cost", self.cost_assumptions)
        if len({(item.arm_id, item.cost_kind) for item in self.cost_assumptions}) != len(self.cost_assumptions):
            raise ValueError("cost kinds must be unique within each effective scope")
        shared_costs = tuple(item for item in self.cost_assumptions if item.arm_id is None)
        if not shared_costs:
            raise ValueError("root shared cost roster must be non-empty")
        unknown_cost_arms = {item.arm_id for item in self.cost_assumptions if item.arm_id is not None and item.arm_id not in arm_by_id}
        if unknown_cost_arms:
            raise ValueError("cost override references an unknown arm")
        shared_cost_hash = _roster_hash(
            shared_costs,
            identity_name="assumption_id",
        )
        all_cost_hash = _roster_hash(
            self.cost_assumptions,
            identity_name="assumption_id",
        )
        for arm in self.arms:
            shared_bindings = (
                (
                    "Candidate",
                    arm.candidate_binding_source,
                    arm.candidate,
                    self.defaults.candidate,
                ),
                (
                    "Context",
                    arm.context_binding_source,
                    arm.context,
                    self.defaults.context,
                ),
                (
                    "Strategy",
                    arm.strategy_binding_source,
                    arm.strategy,
                    self.defaults.strategy,
                ),
                (
                    "Portfolio",
                    arm.portfolio_binding_source,
                    arm.portfolio,
                    self.defaults.portfolio,
                ),
                (
                    "Risk",
                    arm.risk_binding_source,
                    arm.risk,
                    self.defaults.risk,
                ),
            )
            for name, source, effective, default in shared_bindings:
                if source is BacktestBindingSource.SHARED_DEFAULT and effective != default:
                    raise ValueError(f"{name} shared binding differs from root default")
            if arm.cost_binding_source is BacktestBindingSource.SHARED_DEFAULT and arm.effective_cost_roster_sha256 != shared_cost_hash:
                raise ValueError("Cost shared binding differs from root default")
            override_costs = tuple(item for item in self.cost_assumptions if item.arm_id == arm.exploratory_backtest_arm_id)
            if arm.cost_binding_source is BacktestBindingSource.SHARED_DEFAULT:
                if override_costs:
                    raise ValueError("shared Cost arm cannot own override rows")
            elif not override_costs or arm.effective_cost_roster_sha256 != _roster_hash(
                override_costs,
                identity_name="assumption_id",
            ):
                raise ValueError("Cost override differs from exact arm roster")
        _require_contiguous("Evaluation requirement", self.evaluation_requirements)
        requirement_scopes = {
            (
                item.scope_kind,
                item.arm_id,
                item.fold_id,
                item.slice_key,
            )
            for item in self.evaluation_requirements
        }
        if len(requirement_scopes) != len(self.evaluation_requirements):
            raise ValueError("Evaluation requirement scope is duplicated")
        known_arms = set(arm_by_id)
        for evaluation_requirement in self.evaluation_requirements:
            if evaluation_requirement.arm_id not in known_arms:
                raise ValueError("Evaluation requirement references an unknown arm")
            if evaluation_requirement.scope_kind is BacktestEvaluationScopeKind.FOLD:
                assert evaluation_requirement.fold_id is not None
                if (
                    evaluation_requirement.arm_id,
                    evaluation_requirement.fold_id,
                ) not in actual_arm_folds:
                    raise ValueError("FOLD Evaluation requires exact arm-fold participation")
                if evaluation_requirement.evaluation_protocol != fold_by_id[evaluation_requirement.fold_id].evaluation_protocol:
                    raise ValueError("Evaluation requirement Protocol does not match fold")
        fold_evaluation_scopes = {
            (item.arm_id, item.fold_id) for item in self.evaluation_requirements if item.scope_kind is BacktestEvaluationScopeKind.FOLD
        }
        if fold_evaluation_scopes != actual_arm_folds:
            raise ValueError("FOLD Evaluation requirements must cover every arm-fold exactly once")
        aggregate_evaluation_arms = {
            item.arm_id for item in self.evaluation_requirements if item.scope_kind is BacktestEvaluationScopeKind.AGGREGATE
        }
        if aggregate_evaluation_arms != known_arms:
            raise ValueError("AGGREGATE Evaluation requirements must cover every arm exactly once")

        distinct_count = len(session_dates)
        binding_count = sum(len(item.sessions) for item in self.folds)
        roster_hashes = {
            "sample_roster_sha256": _roster_hash(
                self.sample_members,
                identity_name="universe_revision_member_id",
            ),
            "feature_roster_sha256": ContentHash(
                canonical_json_sha256(
                    tuple(
                        {
                            "content_sha256": str(binding.content_sha256),
                            "feature_definition_id": binding.authority_id,
                            "ordinal": ordinal,
                        }
                        for ordinal, binding in enumerate(self.feature_definitions, start=1)
                    )
                )
            ),
            "arm_roster_sha256": _roster_hash(
                self.arms,
                identity_name="exploratory_backtest_arm_id",
            ),
            "fold_roster_sha256": _roster_hash(
                self.folds,
                identity_name="exploratory_backtest_fold_id",
            ),
            "dependency_roster_sha256": _roster_hash(
                self.fold_dependencies,
                identity_name="dependency_id",
            ),
            "arm_fold_roster_sha256": _roster_hash(
                self.arm_folds,
                identity_name="arm_fold_id",
            ),
            "model_training_requirement_roster_sha256": _roster_hash(
                self.model_training_requirements,
                identity_name="requirement_id",
            ),
            "cost_roster_sha256": all_cost_hash,
            "evaluation_roster_sha256": _roster_hash(
                self.evaluation_requirements,
                identity_name="requirement_id",
            ),
        }
        provenance_hash = ContentHash(str(self.provenance_sha256))
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "distinct_trading_session_count", distinct_count)
        object.__setattr__(self, "fold_session_binding_count", binding_count)
        for name, value in roster_hashes.items():
            object.__setattr__(self, name, value)
        specification_hash = ContentHash(
            canonical_json_sha256(
                {
                    **{name: str(value) for name, value in roster_hashes.items()},
                    "code_artifact": _artifact_payload(self.code_artifact),
                    "config_artifact": _artifact_payload(self.config_artifact),
                    "defaults": {
                        "candidate": _authority_payload(self.defaults.candidate),
                        "context": _authority_payload(self.defaults.context),
                        "portfolio": _authority_payload(self.defaults.portfolio),
                        "risk": _authority_payload(self.defaults.risk),
                        "strategy": _authority_payload(self.defaults.strategy),
                    },
                    "definition_version": self.definition_version,
                    "distinct_trading_session_count": distinct_count,
                    "evidence_lane": self.evidence_lane,
                    "exchange_code": self.exchange_code,
                    "exploratory_backtest_run_id": self.exploratory_backtest_run_id,
                    "first_trading_session_id": self.first_trading_session_id,
                    "fold_session_binding_count": binding_count,
                    "generation": self.generation,
                    "hypothesis": self.hypothesis,
                    "last_trading_session_id": self.last_trading_session_id,
                    "market_archive": _authority_payload(self.market_archive),
                    "market_archive_seal": _authority_payload(self.market_archive_seal),
                    "eligibility_policy": _authority_payload(self.eligibility_policy),
                    "provenance_sha256": str(provenance_hash),
                    "random_seed": self.random_seed,
                    "run_code": self.run_code,
                    "sample_algorithm_version": (self.sample_algorithm_version),
                    "sample_input_key": self.sample_input_key,
                    "sample_scope_code": self.sample_scope_code,
                    "specification_schema_version": self.specification_schema_version,
                    "target": _versioned_authority_payload(self.target),
                    "universe_revision": _authority_payload(self.universe_revision),
                    "walk_forward_policy": {
                        "content_sha256": str(self.walk_forward_policy.content_sha256),
                        "minimum_fit_sessions": (self.walk_forward_policy.minimum_fit_sessions),
                        "mode": self.walk_forward_policy.mode,
                        "policy_code": self.walk_forward_policy.policy_code,
                        "policy_version": (self.walk_forward_policy.policy_version),
                        "step_sessions": (self.walk_forward_policy.step_sessions),
                        "validation_sessions": (self.walk_forward_policy.validation_sessions),
                    },
                    "evidence_ceiling": {
                        "alpha_proven": self.alpha_proven,
                        "formal_oos_state": self.formal_oos_state,
                        "formal_pit_state": self.formal_pit_state,
                        "formal_provider_state": self.formal_provider_state,
                        "prospective_proven": self.prospective_proven,
                        "retrospective": self.evidence_lane,
                    },
                }
            )
        )
        object.__setattr__(self, "content_sha256", specification_hash)
        object.__setattr__(
            self,
            "definition_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "current_specification_sha256": str(specification_hash),
                        "exploratory_backtest_run_id": (self.exploratory_backtest_run_id),
                        "specification_schema_version": (self.specification_schema_version),
                    }
                )
            ),
        )


def _require_contiguous(name: str, rows: tuple[object, ...]) -> None:
    if not rows:
        raise ValueError(f"{name} roster must be non-empty")
    ordinals = tuple(getattr(item, "ordinal") for item in rows)
    if ordinals != tuple(range(1, len(rows) + 1)):
        raise ValueError(f"{name} ordinals must be contiguous")


def _authority_payload(binding: AuthorityBinding) -> dict[str, object]:
    return {
        "authority_id": binding.authority_id,
        "content_sha256": str(binding.content_sha256),
    }


def _versioned_authority_payload(
    binding: VersionedAuthorityBinding,
) -> dict[str, object]:
    return {
        "authority_id": binding.authority_id,
        "content_sha256": str(binding.content_sha256),
        "version": binding.version,
    }


def _artifact_payload(binding: ArtifactBinding) -> dict[str, object]:
    return {
        "artifact_id": binding.artifact_id,
        "content_sha256": str(binding.content_sha256),
        "size_bytes": binding.size_bytes,
    }


def freeze_backtest_specification(
    specification: BacktestSpecification,
) -> FrozenBacktestRun:
    """Project a validated current specification without creating Authority."""

    return FrozenBacktestRun(
        exploratory_backtest_run_id=specification.exploratory_backtest_run_id,
        run_code=specification.run_code,
        generation=specification.generation,
        definition_sha256=specification.definition_sha256,
        specification_sha256=specification.content_sha256,
        source=FrozenBacktestSource.CURRENT_RELATIONAL,
        evidence=FrozenBacktestEvidence.CURRENT,
        arms=specification.arms,
        folds=specification.folds,
        fold_dependencies=specification.fold_dependencies,
        arm_folds=specification.arm_folds,
        model_training_requirements=specification.model_training_requirements,
        distinct_trading_session_count=(specification.distinct_trading_session_count),
        fold_session_binding_count=specification.fold_session_binding_count,
        evaluation_requirements=specification.evaluation_requirements,
    )


def _roster_hash(rows: tuple[object, ...], *, identity_name: str) -> ContentHash:
    return ContentHash(
        canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(getattr(item, "content_sha256")),
                    identity_name: getattr(item, identity_name),
                    "ordinal": getattr(item, "ordinal"),
                }
                for item in rows
            )
        )
    )


__all__ = [
    "AuthorityBinding",
    "BacktestArmFold",
    "BacktestArmSpecification",
    "BacktestBindingSource",
    "BacktestComparisonRole",
    "BacktestContextMode",
    "BacktestCostAssumption",
    "BacktestCostChargeSide",
    "BacktestCostKind",
    "BacktestEvaluationRequirement",
    "BacktestEvaluationScopeKind",
    "BacktestExecutionKind",
    "BacktestFoldDependency",
    "BacktestFoldSession",
    "BacktestFoldSpecification",
    "BacktestModelTrainingRequirement",
    "BacktestModelTrainingRecipe",
    "BacktestPolicyDefaults",
    "BacktestSampleMember",
    "BacktestSessionRole",
    "BacktestSpecification",
    "BacktestWalkForwardMode",
    "BacktestWalkForwardPolicy",
    "FrozenBacktestEvidence",
    "FrozenBacktestRun",
    "FrozenBacktestSource",
    "VersionedAuthorityBinding",
    "freeze_backtest_specification",
    "parse_backtest_context_slice",
]
