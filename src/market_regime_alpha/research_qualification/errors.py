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


class BacktestReportIntegrityError(ResearchValidityError):
    code = "BACKTEST_REPORT_INTEGRITY_ERROR"


class BacktestExecutionIntegrityError(ResearchValidityError):
    code = "BACKTEST_EXECUTION_INTEGRITY_ERROR"


class IncompatibleBacktestComparisonError(ResearchValidityError):
    code = "BACKTEST_COMPARISON_INCOMPATIBLE"


class ResearchRetryableTransactionError(RuntimeError):
    """Infrastructure-classified whole-transaction retry signal."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class ResearchUnknownCommitResultError(RuntimeError):
    """Commit acknowledgement was lost; only exact receipt replay is safe."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


__all__ = [
    "BacktestExecutionIntegrityError",
    "EvaluationAcquisitionError",
    "EvaluationProtocolError",
    "EvaluationReconciliationError",
    "BacktestReportIntegrityError",
    "ExperimentBindingError",
    "IncompatibleBacktestComparisonError",
    "PartitionInputError",
    "ResearchRetryableTransactionError",
    "ResearchUnknownCommitResultError",
    "ResearchValidityError",
]
