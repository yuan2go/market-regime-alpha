"""Research-only Signal Layer contracts, model and immutable replay boundary."""

from market_regime_alpha.signals.artifact import (
    load_verified_signal_run,
    publish_signal_run,
    replay_signal_run,
)
from market_regime_alpha.signals.contracts import (
    ConfirmationState,
    SignalFamily,
    SignalSnapshot,
    SignalState,
)
from market_regime_alpha.signals.engine import (
    SIGNAL_MODEL_CONFIG_SCHEMA,
    SIGNAL_OBSERVATION_SCHEMA,
    SignalModelConfig,
    SignalObservation,
    SignalRunArtifact,
    run_signal_model,
)

__all__ = [
    "SIGNAL_MODEL_CONFIG_SCHEMA",
    "SIGNAL_OBSERVATION_SCHEMA",
    "ConfirmationState",
    "SignalFamily",
    "SignalModelConfig",
    "SignalObservation",
    "SignalRunArtifact",
    "SignalSnapshot",
    "SignalState",
    "load_verified_signal_run",
    "publish_signal_run",
    "replay_signal_run",
    "run_signal_model",
]
