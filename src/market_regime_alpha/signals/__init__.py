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
from market_regime_alpha.signals.input_assembly import (
    SIGNAL_INPUT_MAPPING_CONFIGURATION_SCHEMA,
    SIGNAL_OBSERVATION_V2_SCHEMA,
    SignalFactorMapping,
    SignalFactorName,
    SignalFactorObservation,
    SignalInputAssembler,
    SignalInputMappingConfiguration,
    SignalObservationV2,
    canonical_signal_input_mapping,
)
from market_regime_alpha.signals.model_contracts import (
    SignalMeaning,
    SignalModel,
    SignalModelRequest,
    SignalModelResult,
)
from market_regime_alpha.signals.v2 import (
    SIGNAL_RUN_V2_SCHEMA,
    SignalRunArtifactV2,
    VerifiedSignalRunArtifactV2,
    load_verified_signal_run_v2,
    publish_signal_run_v2,
    replay_signal_run_v2,
    run_signal_model_v2,
)

__all__ = [
    "SIGNAL_MODEL_CONFIG_SCHEMA",
    "SIGNAL_INPUT_MAPPING_CONFIGURATION_SCHEMA",
    "SIGNAL_OBSERVATION_SCHEMA",
    "SIGNAL_OBSERVATION_V2_SCHEMA",
    "SIGNAL_RUN_V2_SCHEMA",
    "ConfirmationState",
    "SignalFamily",
    "SignalFactorMapping",
    "SignalFactorName",
    "SignalFactorObservation",
    "SignalInputAssembler",
    "SignalInputMappingConfiguration",
    "SignalMeaning",
    "SignalModel",
    "SignalModelConfig",
    "SignalModelRequest",
    "SignalModelResult",
    "SignalObservation",
    "SignalObservationV2",
    "SignalRunArtifact",
    "SignalRunArtifactV2",
    "SignalSnapshot",
    "SignalState",
    "VerifiedSignalRunArtifactV2",
    "canonical_signal_input_mapping",
    "load_verified_signal_run",
    "load_verified_signal_run_v2",
    "publish_signal_run",
    "publish_signal_run_v2",
    "replay_signal_run",
    "replay_signal_run_v2",
    "run_signal_model",
    "run_signal_model_v2",
]
