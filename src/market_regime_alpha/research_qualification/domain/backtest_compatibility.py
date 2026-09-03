"""Private exact decoder for immutable historical Backtest evidence.

The allowlist below is a compatibility oracle, not business Authority.  It
permits generic read/replay only when every historical root and roster hash is
the exact value qualified by its original implementation.  Absence of a
current specification never selects this decoder.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestArmFold,
    BacktestArmSpecification,
    BacktestBindingSource,
    BacktestComparisonRole,
    BacktestContextMode,
    BacktestExecutionKind,
    BacktestFoldDependency,
    BacktestFoldSession,
    BacktestFoldSpecification,
    BacktestModelTrainingRequirement,
    BacktestSessionRole,
    FrozenBacktestEvidence,
    FrozenBacktestRun,
    FrozenBacktestSource,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind as HistoricalArmKind,
    ExploratoryBacktestRunPlan as HistoricalBacktestPlan,
)
from market_regime_alpha.shared.identity import ContentHash


class HistoricalBacktestCompatibilityError(ValueError):
    pass


class _HistoricalContractCode(StrEnum):
    WP17P_COMPLETED_EXACT_SHA = "WP17P_COMPLETED_EXACT_SHA"
    WP18_DEFINITION_FIXTURE = "WP18_DEFINITION_FIXTURE"


@dataclass(frozen=True, slots=True)
class _HistoricalCompatibilityManifest:
    contract_code: _HistoricalContractCode
    exploratory_backtest_run_id: UUID
    run_code: str
    generation: int
    definition_sha256: ContentHash | str
    feature_roster_sha256: ContentHash | str
    arm_roster_sha256: ContentHash | str
    fold_roster_sha256: ContentHash | str
    cost_roster_sha256: ContentHash | str
    session_count: int
    arm_kinds: tuple[HistoricalArmKind, ...]
    fold_ids: tuple[UUID, ...]
    dependency_pairs: tuple[tuple[UUID, UUID], ...]
    evidence: FrozenBacktestEvidence

    def __post_init__(self) -> None:
        for name in (
            "definition_sha256",
            "feature_roster_sha256",
            "arm_roster_sha256",
            "fold_roster_sha256",
            "cost_roster_sha256",
        ):
            object.__setattr__(self, name, ContentHash(str(getattr(self, name))))


_WP17P_FIT = UUID("949ed24c-5ad1-59cd-a047-1302bb1daa0e")
_WP17P_VALIDATION = UUID("e5b041cb-4e04-5aaf-a05f-dbc43dc982da")
_WP18_FOLDS = (
    UUID("61c244d6-56ea-5aac-b8f5-6d06c8be8f6b"),
    UUID("17a03bf8-b010-5a9b-be3f-f4086e6a9b7e"),
    UUID("3d91207e-cb75-578b-ae1e-61d2ddb703ca"),
    UUID("b7ca679f-d14b-53e4-9443-b910b6760440"),
    UUID("95d3ae18-ffff-533c-96e3-2cbfa430c389"),
    UUID("1fb6e0ea-0094-5b06-82f0-073898870450"),
    UUID("5a9f1d08-60a4-554d-ab93-407fe27efef0"),
    UUID("386362c5-7d84-5f8f-ae00-7c1a772cc122"),
    UUID("612fcc2c-e2b8-5b56-a16c-3aaa528ac76a"),
    UUID("98f836fc-11df-55af-b95b-c28f45dbb93c"),
)

_HISTORICAL_MANIFESTS = MappingProxyType(
    {
        UUID("8f7b6def-9c63-533e-9777-a5a6c57866e0"): (
            _HistoricalCompatibilityManifest(
                _HistoricalContractCode.WP17P_COMPLETED_EXACT_SHA,
                UUID("8f7b6def-9c63-533e-9777-a5a6c57866e0"),
                "wp17p_pilot",
                1,
                "ac2686e2ef3105e8a5ca5a2a2ece6cfd7821ea84d56ae7611eb1e9b0e7305d78",
                "da275246148c871e03ec69377ec4762260e0c35e8365eed330551977eabf3e20",
                "9b23355c734a084c308b37bce8f33472f4d02f258016e8047fb138ab8c3995ad",
                "b11b30c0c55555c92dd5a4fd2dfc1a6e2c96624aa6b6a6798bfd0de9407eaa5c",
                "60d170aff1bba1176a14a3b6ae765dfd49ac2450ce856f5ed6480feda8cd4185",
                8,
                (
                    HistoricalArmKind.RULE_BASELINE,
                    HistoricalArmKind.MODEL_CHALLENGER,
                ),
                (_WP17P_FIT, _WP17P_VALIDATION),
                ((_WP17P_FIT, _WP17P_VALIDATION),),
                FrozenBacktestEvidence.COMPLETED_ZERO_WRITE,
            )
        ),
        UUID("d835dfe2-1eee-5c23-a7c4-8b3a5b6ab5ee"): (
            _HistoricalCompatibilityManifest(
                _HistoricalContractCode.WP18_DEFINITION_FIXTURE,
                UUID("d835dfe2-1eee-5c23-a7c4-8b3a5b6ab5ee"),
                "wp18_walk_forward",
                2,
                "4d6202206687660f1cd025ee4e3dadeaee5e40c7fa0c2320327254ec2f390213",
                "6ff46757008f8befd0f1d1815c5e73cde3fe69a9501c90db1e6ec8567b299eb2",
                "9739b8f4376a1db0462b4a3abb8d9b51f019ee9bfdd53bc20349d06deb800dbd",
                "0933b70f9b81093435a0fb32b2eef60a19a108cb3960c2fd3ce05580887b7d80",
                "46a2d22f059f04adcfab48757f9d3bec0c1015dcad7eb5fa0e37f7f03067e26d",
                40,
                (
                    HistoricalArmKind.RULE_CURRENT_CONTEXT,
                    HistoricalArmKind.RIDGE_CURRENT_CONTEXT,
                    HistoricalArmKind.RULE_CONTEXT_OBSERVATIONAL,
                    HistoricalArmKind.RIDGE_CONTEXT_OBSERVATIONAL,
                ),
                _WP18_FOLDS,
                tuple(
                    (_WP18_FOLDS[index], _WP18_FOLDS[index + 1])
                    for index in range(0, len(_WP18_FOLDS), 2)
                ),
                FrozenBacktestEvidence.DEFINITION_ONLY,
            )
        ),
    }
)


def is_exact_historical_backtest_identity(
    exploratory_backtest_run_id: UUID,
) -> bool:
    """Return allowlist membership without inspecting mutable database shape."""

    return exploratory_backtest_run_id in _HISTORICAL_MANIFESTS


_ARM_SEMANTICS = MappingProxyType(
    {
        HistoricalArmKind.RULE_BASELINE: (
            BacktestExecutionKind.RULE,
            BacktestComparisonRole.BASELINE,
        ),
        HistoricalArmKind.MODEL_CHALLENGER: (
            BacktestExecutionKind.MODEL,
            BacktestComparisonRole.CHALLENGER,
        ),
        HistoricalArmKind.RULE_CURRENT_CONTEXT: (
            BacktestExecutionKind.RULE,
            BacktestComparisonRole.BASELINE,
        ),
        HistoricalArmKind.RIDGE_CURRENT_CONTEXT: (
            BacktestExecutionKind.MODEL,
            BacktestComparisonRole.CHALLENGER,
        ),
        HistoricalArmKind.RULE_CONTEXT_OBSERVATIONAL: (
            BacktestExecutionKind.RULE,
            BacktestComparisonRole.DIAGNOSTIC,
        ),
        HistoricalArmKind.RIDGE_CONTEXT_OBSERVATIONAL: (
            BacktestExecutionKind.MODEL,
            BacktestComparisonRole.DIAGNOSTIC,
        ),
    }
)


def decode_exact_historical_backtest(
    plan: HistoricalBacktestPlan,
    *,
    model_definitions: Mapping[UUID, AuthorityBinding],
) -> FrozenBacktestRun:
    """Normalize one allowlisted immutable plan; never accepts shape alone."""

    manifest = _HISTORICAL_MANIFESTS.get(plan.exploratory_backtest_run_id)
    if manifest is None or not _matches_manifest(plan, manifest):
        raise HistoricalBacktestCompatibilityError(
            "Backtest is not in the exact historical allowlist; "
            "a missing current specification is not legacy eligibility"
        )

    model_arm_ids = {
        arm.exploratory_backtest_arm_id for arm in plan.arms if arm.uses_model
    }
    if set(model_definitions) != model_arm_ids:
        raise HistoricalBacktestCompatibilityError(
            "historical Model bindings do not match the exact Model arm roster"
        )

    candidate = AuthorityBinding(
        plan.candidate_policy_id, plan.candidate_policy_sha256
    )
    context = AuthorityBinding(plan.context_policy_id, plan.context_policy_sha256)
    root_strategy = AuthorityBinding(
        plan.strategy_version_id, plan.strategy_version_sha256
    )
    portfolio = AuthorityBinding(
        plan.portfolio_policy_id, plan.portfolio_policy_sha256
    )
    risk = AuthorityBinding(plan.risk_policy_id, plan.risk_policy_sha256)
    arms = tuple(
        BacktestArmSpecification(
            exploratory_backtest_arm_id=arm.exploratory_backtest_arm_id,
            ordinal=arm.ordinal,
            arm_code=arm.kind.value.lower().replace("_", "-"),
            execution_kind=_ARM_SEMANTICS[arm.kind][0],
            comparison_role=_ARM_SEMANTICS[arm.kind][1],
            context_mode=BacktestContextMode(arm.context_mode.value),
            candidate=candidate,
            context=context,
            strategy=(
                AuthorityBinding(
                    arm.strategy_version_id,
                    arm.strategy_version_sha256,
                )
                if arm.strategy_version_id is not None
                and arm.strategy_version_sha256 is not None
                else root_strategy
            ),
            model=model_definitions.get(arm.exploratory_backtest_arm_id),
            portfolio=portfolio,
            risk=risk,
            effective_cost_roster_sha256=plan.cost_roster_sha256,
            strategy_binding_source=(
                BacktestBindingSource.ARM_OVERRIDE
                if arm.strategy_version_id is not None
                and arm.strategy_version_sha256 is not None
                and AuthorityBinding(
                    arm.strategy_version_id,
                    arm.strategy_version_sha256,
                )
                != root_strategy
                else BacktestBindingSource.SHARED_DEFAULT
            ),
        )
        for arm in plan.arms
    )
    folds = tuple(
        BacktestFoldSpecification(
            exploratory_backtest_fold_id=fold.exploratory_backtest_fold_id,
            ordinal=fold.ordinal,
            purpose=fold.purpose,
            exchange_code=fold.exchange_code,
            purge_sessions=fold.purge_sessions,
            embargo_sessions=fold.embargo_sessions,
            evaluation_protocol=AuthorityBinding(
                fold.evaluation_protocol_id,
                fold.evaluation_protocol_sha256,
            ),
            sessions=tuple(
                BacktestFoldSession(
                    exploratory_backtest_fold_session_id=(
                        session.exploratory_backtest_fold_session_id
                    ),
                    ordinal=session.ordinal,
                    trading_session_id=session.trading_session_id,
                    session_date=session.session_date,
                    role=BacktestSessionRole(session.role.value),
                )
                for session in fold.sessions
            ),
        )
        for fold in plan.folds
    )
    dependencies = tuple(
        BacktestFoldDependency(
            dependency_id=_projection_id(
                plan.exploratory_backtest_run_id,
                f"dependency:{ordinal}:{fit_id}:{validation_id}",
            ),
            ordinal=ordinal,
            fit_fold_id=fit_id,
            validation_fold_id=validation_id,
        )
        for ordinal, (fit_id, validation_id) in enumerate(
            manifest.dependency_pairs, start=1
        )
    )
    arm_folds = tuple(
        BacktestArmFold(
            arm_fold_id=_projection_id(
                plan.exploratory_backtest_run_id,
                f"arm-fold:{arm.ordinal}:{fold.ordinal}",
            ),
            ordinal=ordinal,
            arm_id=arm.exploratory_backtest_arm_id,
            fold_id=fold.exploratory_backtest_fold_id,
        )
        for ordinal, (fold, arm) in enumerate(
            ((fold, arm) for fold in folds for arm in arms), start=1
        )
    )
    requirements = tuple(
        BacktestModelTrainingRequirement(
            requirement_id=_projection_id(
                plan.exploratory_backtest_run_id,
                f"model:{arm.ordinal}:{dependency.ordinal}",
            ),
            ordinal=ordinal,
            model_arm_id=arm.exploratory_backtest_arm_id,
            fit_fold_id=dependency.fit_fold_id,
            validation_fold_id=dependency.validation_fold_id,
            model_definition=model_definitions[arm.exploratory_backtest_arm_id],
        )
        for ordinal, (dependency, arm) in enumerate(
            (
                (dependency, arm)
                for dependency in dependencies
                for arm in arms
                if arm.execution_kind is BacktestExecutionKind.MODEL
            ),
            start=1,
        )
    )
    distinct_sessions = {
        session.trading_session_id for fold in folds for session in fold.sessions
    }
    return FrozenBacktestRun(
        exploratory_backtest_run_id=plan.exploratory_backtest_run_id,
        run_code=plan.run_code,
        generation=plan.generation,
        definition_sha256=plan.content_sha256,
        specification_sha256=plan.content_sha256,
        source=FrozenBacktestSource.HISTORICAL_EXACT,
        evidence=manifest.evidence,
        arms=arms,
        folds=folds,
        fold_dependencies=dependencies,
        arm_folds=arm_folds,
        model_training_requirements=requirements,
        distinct_trading_session_count=len(distinct_sessions),
        fold_session_binding_count=sum(len(fold.sessions) for fold in folds),
    )


def _matches_manifest(
    plan: HistoricalBacktestPlan,
    manifest: _HistoricalCompatibilityManifest,
) -> bool:
    return (
        plan.exploratory_backtest_run_id,
        plan.run_code,
        plan.generation,
        plan.content_sha256,
        plan.feature_roster_sha256,
        plan.arm_roster_sha256,
        plan.fold_roster_sha256,
        plan.cost_roster_sha256,
        plan.session_count,
        tuple(arm.kind for arm in plan.arms),
        tuple(fold.exploratory_backtest_fold_id for fold in plan.folds),
    ) == (
        manifest.exploratory_backtest_run_id,
        manifest.run_code,
        manifest.generation,
        manifest.definition_sha256,
        manifest.feature_roster_sha256,
        manifest.arm_roster_sha256,
        manifest.fold_roster_sha256,
        manifest.cost_roster_sha256,
        manifest.session_count,
        manifest.arm_kinds,
        manifest.fold_ids,
    )


def _projection_id(backtest_id: UUID, suffix: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"mra:historical-backtest-projection:{backtest_id}:{suffix}")


__all__ = [
    "HistoricalBacktestCompatibilityError",
    "decode_exact_historical_backtest",
    "is_exact_historical_backtest_identity",
]
