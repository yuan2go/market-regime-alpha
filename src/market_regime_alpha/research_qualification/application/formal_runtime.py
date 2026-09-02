"""Pure plans for the two controlled WP-14 Runtime profiles."""

from __future__ import annotations

from datetime import timedelta

from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    StepDependency,
    StepSpec,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


_DECISION_KINDS = (
    "CAPTURE",
    "NORMALIZE_PIT",
    "FREEZE_UNIVERSE",
    "ASSESS_ELIGIBILITY",
    "REGISTER_DATASET",
    "BUILD_CANDIDATE_SET",
    "OPEN_DECISION_RUN",
    "ASSESS_CONTEXT",
    "SIGNAL_AND_FORECAST",
    "DECIDE_AND_RISK",
)
_DUE_KINDS = (
    "SETTLE_OUTCOME",
    "ACQUIRE_OUTCOME_INPUTS",
    "EVALUATE",
    "RECORD_EVIDENCE",
    "ASSESS_RESEARCH",
    "QUALIFY",
)


def build_decision_proof_runtime_profile(
    *, request_seed: str
) -> tuple[tuple[StepSpec, ...], tuple[StepDependency, ...]]:
    return _build_profile("decision", _DECISION_KINDS, request_seed=request_seed)


def build_due_proof_runtime_profile(
    *, request_seed: str
) -> tuple[tuple[StepSpec, ...], tuple[StepDependency, ...]]:
    return _build_profile("due", _DUE_KINDS, request_seed=request_seed)


def _build_profile(
    profile: str,
    kinds: tuple[str, ...],
    *,
    request_seed: str,
) -> tuple[tuple[StepSpec, ...], tuple[StepDependency, ...]]:
    if not request_seed:
        raise ValueError("request_seed is required")
    retry = RetryPolicy(
        max_attempts=3,
        backoff=(timedelta(0), timedelta(seconds=1)),
        retryable_codes=frozenset(
            {"DEADLOCK_DETECTED", "SERIALIZATION_FAILURE", "TRANSIENT_CONNECTION"}
        ),
    )
    steps = tuple(
        StepSpec(
            step_key=f"formal-{profile}-{ordinal:02d}-{kind.lower().replace('_', '-')}",
            step_kind=kind,
            implementation=f"market_regime_alpha.formal_research.{kind.lower()}",
            implementation_version="1",
            ordinal=ordinal,
            required=True,
            request_hash=canonical_json_sha256(
                {"kind": kind, "ordinal": ordinal, "request_seed": request_seed}
            ),
            input_evidence_hash=None,
            retry_policy=retry,
            external_effect_class=(
                ExternalEffectClass.CONTENT_PUT
                if kind == "CAPTURE"
                else ExternalEffectClass.NONE
            ),
        )
        for ordinal, kind in enumerate(kinds, start=1)
    )
    dependencies = tuple(
        StepDependency(predecessor.step_key, successor.step_key)
        for predecessor, successor in zip(steps, steps[1:])
    )
    return steps, dependencies


__all__ = [
    "build_decision_proof_runtime_profile",
    "build_due_proof_runtime_profile",
]
