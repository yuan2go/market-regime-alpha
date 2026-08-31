"""Research validity and evaluation fail-closed errors."""

from market_regime_alpha.shared.errors import MraError


class ResearchValidityError(MraError):
    code = "RESEARCH_VALIDITY_ERROR"


class PartitionInputError(ResearchValidityError):
    code = "PARTITION_INPUT_INVALID"


class ExperimentBindingError(ResearchValidityError):
    code = "EXPERIMENT_BINDING_INVALID"


class EvaluationProtocolError(ResearchValidityError):
    code = "EVALUATION_PROTOCOL_INVALID"


class EvaluationAcquisitionError(ResearchValidityError):
    code = "EVALUATION_ACQUISITION_FAILED"


class EvaluationReconciliationError(ResearchValidityError):
    code = "EVALUATION_RECONCILIATION_FAILED"


__all__ = [
    "EvaluationAcquisitionError",
    "EvaluationProtocolError",
    "EvaluationReconciliationError",
    "ExperimentBindingError",
    "PartitionInputError",
    "ResearchValidityError",
]
