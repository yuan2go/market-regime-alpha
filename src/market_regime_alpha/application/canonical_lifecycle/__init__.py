"""Recoverable, human-in-the-loop canonical lifecycle orchestration contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleAttemptResult,
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
    LifecycleEvent,
    LifecycleEventId,
    LifecycleEventType,
    LifecycleModelVersionReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRetryState,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    StageReceipt,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
    CanonicalLifecycleInputManifestReader,
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    LoadedRuntimeConfiguration,
    RuntimeConfigurationError,
    RuntimeConfigurationReader,
    RuntimeConfigurationSet,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayCheck,
    LifecycleReplayReport,
    LifecycleReplayStatus,
    ReplayCheckStatus,
    verify_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.durable_replay import (
    DurableLifecycleReplayResult,
    lifecycle_history_hash,
    run_durable_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    MANUAL_ACCOUNT_OBSERVATION_STAGE_ORDER,
    POSITION_REVIEW_CONTRACT_ONLY_STAGE_ORDER,
    POSTGRES_COMPOSED_STAGE_ORDER,
    RESEARCH_DECISION_SUPPORT_STAGE_ORDER,
    InvalidLifecycleTransition,
    LifecycleCapabilityBoundary,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
    lifecycle_stage_boundary,
    validate_lifecycle_run_transition,
    validate_lifecycle_stage_progression,
    validate_lifecycle_stage_transition,
)
from market_regime_alpha.application.canonical_lifecycle.postgres_repository import (
    PostgresLifecycleRunRepository,
)
if TYPE_CHECKING:
    from market_regime_alpha.application.canonical_lifecycle.postgres_composition import (
        build_postgres_lifecycle_runner,
        postgres_lifecycle_stage_handlers,
    )


def __getattr__(name: str) -> Any:
    """Load the PostgreSQL composition only when its public facade is requested."""

    if name in {
        "build_postgres_lifecycle_runner",
        "postgres_lifecycle_stage_handlers",
    }:
        from market_regime_alpha.application.canonical_lifecycle import (
            postgres_composition,
        )

        return getattr(postgres_composition, name)
    raise AttributeError(name)


__all__ = [
    "LIFECYCLE_STAGE_ORDER",
    "MANUAL_ACCOUNT_OBSERVATION_STAGE_ORDER",
    "POSITION_REVIEW_CONTRACT_ONLY_STAGE_ORDER",
    "POSTGRES_COMPOSED_STAGE_ORDER",
    "RESEARCH_DECISION_SUPPORT_STAGE_ORDER",
    "CanonicalLifecycleCommand",
    "CanonicalLifecycleInputManifest",
    "CanonicalLifecycleInputManifestReader",
    "DurableLifecycleReplayResult",
    "InvalidLifecycleTransition",
    "LifecycleCapabilityBoundary",
    "LifecycleAttempt",
    "LifecycleAttemptId",
    "LifecycleAttemptResult",
    "LifecycleAuthorityCeiling",
    "LifecycleConfigurationKind",
    "LifecycleConfigurationReference",
    "LifecycleEvent",
    "LifecycleEventId",
    "LifecycleEventType",
    "LifecycleModelVersionReference",
    "LifecycleObjectId",
    "LifecycleObjectReference",
    "LifecycleObjectType",
    "LifecycleReaderKind",
    "LifecycleRetryState",
    "LifecycleReplayCheck",
    "LifecycleReplayReport",
    "LifecycleReplayStatus",
    "LifecycleRun",
    "LifecycleRunId",
    "LifecycleRunStatus",
    "LifecycleRunType",
    "LifecycleStage",
    "LifecycleStageName",
    "LifecycleStageStatus",
    "PostgresLifecycleRunRepository",
    "build_postgres_lifecycle_runner",
    "postgres_lifecycle_stage_handlers",
    "LoadedRuntimeConfiguration",
    "RuntimeConfigurationError",
    "RuntimeConfigurationReader",
    "RuntimeConfigurationSet",
    "ReplayCheckStatus",
    "StageReceipt",
    "lifecycle_stage_boundary",
    "validate_lifecycle_run_transition",
    "validate_lifecycle_stage_progression",
    "validate_lifecycle_stage_transition",
    "verify_lifecycle_replay",
    "lifecycle_history_hash",
    "run_durable_lifecycle_replay",
]
