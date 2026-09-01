"""Closed vocabulary for Research Partition, Experiment, and Evaluation."""

from enum import StrEnum


class PartitionPurpose(StrEnum):
    DISCOVERY = "DISCOVERY"
    FIT = "FIT"
    VALIDATION = "VALIDATION"
    LOCKED_OOS = "LOCKED_OOS"
    PROSPECTIVE = "PROSPECTIVE"


class PartitionPopulationScope(StrEnum):
    ALL_COMMITMENTS = "ALL_COMMITMENTS"
    SELECTED = "SELECTED"
    RANKED_NOT_SELECTED = "RANKED_NOT_SELECTED"
    UNRANKABLE = "UNRANKABLE"


class PartitionOverlapPolicy(StrEnum):
    DIAGNOSTIC_REUSE = "DIAGNOSTIC_REUSE"
    PURGED_WALK_FORWARD = "PURGED_WALK_FORWARD"
    ISOLATED_PROTECTED = "ISOLATED_PROTECTED"


class PartitionStatus(StrEnum):
    FROZEN = "FROZEN"


class ExperimentStatus(StrEnum):
    REGISTERED = "REGISTERED"


class ExperimentRunStatus(StrEnum):
    OPENED = "OPENED"


class EvaluationProtocolStatus(StrEnum):
    FROZEN = "FROZEN"


class EvaluationRunStatus(StrEnum):
    OPEN = "OPEN"
    INPUTS_ACQUIRED = "INPUTS_ACQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvaluationReducer(StrEnum):
    MEAN_DECIMAL = "MEAN_DECIMAL"
    MEDIAN_DECIMAL = "MEDIAN_DECIMAL"
    TRUE_RATE = "TRUE_RATE"
    ESTIMABLE_RATE = "ESTIMABLE_RATE"


class SourceMetricValueType(StrEnum):
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"


class EvaluationSliceKind(StrEnum):
    ALL_MEMBERS = "ALL_MEMBERS"
    CANDIDATE_DISPOSITION = "CANDIDATE_DISPOSITION"


class CandidateDisposition(StrEnum):
    SELECTED = "SELECTED"
    RANKED_NOT_SELECTED = "RANKED_NOT_SELECTED"
    UNRANKABLE = "UNRANKABLE"


class MetricDirection(StrEnum):
    HIGHER = "HIGHER"
    LOWER = "LOWER"
    DESCRIPTIVE = "DESCRIPTIVE"


class EvaluationMissingnessPolicy(StrEnum):
    RETAIN_AND_ESTIMATE = "RETAIN_AND_ESTIMATE"
    REQUIRE_COMPLETE_ROSTER = "REQUIRE_COMPLETE_ROSTER"


class EvaluationInclusionPolicy(StrEnum):
    COMPLETE_ONLY = "COMPLETE_ONLY"
    AVAILABLE_VALUE = "AVAILABLE_VALUE"


class AcceptanceOperator(StrEnum):
    NONE = "NONE"
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"


class AcceptanceState(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class EvaluationMetricState(StrEnum):
    ESTIMATED = "ESTIMATED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class EvaluationInputState(StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


__all__ = [
    "AcceptanceOperator",
    "AcceptanceState",
    "CandidateDisposition",
    "EvaluationInclusionPolicy",
    "EvaluationInputState",
    "EvaluationMetricState",
    "EvaluationMissingnessPolicy",
    "EvaluationProtocolStatus",
    "EvaluationReducer",
    "EvaluationRunStatus",
    "EvaluationSliceKind",
    "ExperimentRunStatus",
    "ExperimentStatus",
    "MetricDirection",
    "PartitionOverlapPolicy",
    "PartitionPopulationScope",
    "PartitionPurpose",
    "PartitionStatus",
    "SourceMetricValueType",
]
