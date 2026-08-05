"""Controlled single-day DecisionTime operation boundary."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .journal import (
    CONTROLLED_OPERATION_STAGE_ORDER,
    ChildRunReferenceKind,
    ClaimedDecisionTimeOperationStage,
    ControlledOperationCommand,
    DecisionTimeOperationReceipt,
    DecisionTimeOperationRunSnapshot,
    DecisionTimeOperationRunStatus,
    DecisionTimeOperationStageName,
    DecisionTimeOperationStageStatus,
    OperationArtifactReference,
    OperationChildRunReference,
)
from .policy import (
    DecisionTimeOperationPolicy,
    DecisionWindowAssessment,
    DecisionWindowState,
    default_decision_time_operation_policy,
)
from .sqlite_journal import (
    ControlledOperationClaimRejected,
    ControlledOperationConflict,
    SQLiteDecisionTimeOperationJournal,
)
from .postgres_journal import PostgresDecisionTimeOperationJournal
from .postgres_longitudinal_index import PostgresLongitudinalOperationalIndex
if TYPE_CHECKING:
    from .replay import (
        ControlledOperationReplayReport,
        replay_controlled_operation,
    )
    from .runner import (
        ControlledDecisionTimeOperationRunner,
        ControlledOperationDataBlocked,
        ControlledOperationDecisionResult,
        ControlledOperationInputPaths,
        ControlledOperationPreparation,
        ControlledOperationSettlementInputPaths,
        ControlledOperationSettlementResult,
    )


_LAZY_EXPORTS = {
    "ControlledDecisionTimeOperationRunner": (".runner", "ControlledDecisionTimeOperationRunner"),
    "ControlledOperationDataBlocked": (".runner", "ControlledOperationDataBlocked"),
    "ControlledOperationDecisionResult": (".runner", "ControlledOperationDecisionResult"),
    "ControlledOperationInputPaths": (".runner", "ControlledOperationInputPaths"),
    "ControlledOperationPreparation": (".runner", "ControlledOperationPreparation"),
    "ControlledOperationSettlementInputPaths": (".runner", "ControlledOperationSettlementInputPaths"),
    "ControlledOperationSettlementResult": (".runner", "ControlledOperationSettlementResult"),
    "ControlledOperationReplayReport": (".replay", "ControlledOperationReplayReport"),
    "replay_controlled_operation": (".replay", "replay_controlled_operation"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "CONTROLLED_OPERATION_STAGE_ORDER",
    "ChildRunReferenceKind",
    "ClaimedDecisionTimeOperationStage",
    "ControlledOperationClaimRejected",
    "ControlledOperationCommand",
    "ControlledOperationConflict",
    "ControlledOperationDataBlocked",
    "ControlledOperationDecisionResult",
    "ControlledOperationInputPaths",
    "ControlledOperationPreparation",
    "ControlledOperationReplayReport",
    "ControlledOperationSettlementInputPaths",
    "ControlledOperationSettlementResult",
    "ControlledDecisionTimeOperationRunner",
    "DecisionTimeOperationReceipt",
    "DecisionTimeOperationRunSnapshot",
    "DecisionTimeOperationRunStatus",
    "DecisionTimeOperationStageName",
    "DecisionTimeOperationStageStatus",
    "DecisionTimeOperationPolicy",
    "DecisionWindowAssessment",
    "DecisionWindowState",
    "OperationArtifactReference",
    "OperationChildRunReference",
    "PostgresDecisionTimeOperationJournal",
    "PostgresLongitudinalOperationalIndex",
    "SQLiteDecisionTimeOperationJournal",
    "default_decision_time_operation_policy",
    "replay_controlled_operation",
]
