"""Ports owned by Market Target Outcome."""

from market_regime_alpha.outcome.ports.preparation import (
    OutcomeDependencyRepository,
    OutcomeInputPreparationProvider,
    OutcomeSettlementRequest,
)
from market_regime_alpha.outcome.ports.queries import OutcomeReadPort, OutcomeSnapshot
from market_regime_alpha.outcome.ports.repository import (
    OutcomeHead,
    OutcomeReconciliation,
    OutcomeRepository,
)
from market_regime_alpha.outcome.ports.uow import (
    OutcomeRuntimeFinalization,
    OutcomeUnitOfWork,
    OutcomeUnitOfWorkProvider,
)
from market_regime_alpha.outcome.ports.verification import OutcomeVerificationProvider

__all__ = [
    "OutcomeDependencyRepository",
    "OutcomeHead",
    "OutcomeInputPreparationProvider",
    "OutcomeSettlementRequest",
    "OutcomeReadPort",
    "OutcomeReconciliation",
    "OutcomeRepository",
    "OutcomeRuntimeFinalization",
    "OutcomeSnapshot",
    "OutcomeUnitOfWork",
    "OutcomeUnitOfWorkProvider",
    "OutcomeVerificationProvider",
]
