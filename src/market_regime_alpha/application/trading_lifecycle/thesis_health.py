"""Application orchestration for one H5 artifact-derived health command."""

from __future__ import annotations

from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.position.thesis_health import (
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    ThesisHealthObservationV2,
    ThesisHealthRepository,
)


class ThesisHealthApplicationService:
    """Build and atomically persist a V2 Observation; create no trade action."""

    def __init__(self, repository: ThesisHealthRepository) -> None:
        self._repository = repository

    def assess(
        self,
        *,
        input_bundle: ThesisHealthInputBundle,
        idempotency_key: str,
    ) -> ThesisHealthObservationV2:
        if not isinstance(input_bundle, ThesisHealthInputBundle):
            raise TypeError("input_bundle must be a ThesisHealthInputBundle")
        bundle = ThesisHealthInputBundle.from_canonical_dict(
            input_bundle.to_canonical_dict()
        )
        try:
            bundle.rule_set.validate_for(bundle.thesis)
        except ValueError as error:
            raise ValueError(
                "THESIS_INVALIDATION_RULESET_NOT_ESTABLISHED"
            ) from error
        command_hash = canonical_hash(
            {
                "command_schema": "build-thesis-health-v2-command-v1",
                "input_bundle_id": str(bundle.input_bundle_id),
                "input_bundle_hash": bundle.content_hash,
                "thesis_id": str(bundle.thesis.thesis_id),
                "thesis_version": bundle.thesis.version,
                "assessed_at": bundle.assessed_at.isoformat(),
                "configuration_id": str(bundle.configuration.configuration_id),
                "configuration_hash": bundle.configuration.configuration_hash,
                "rule_set_id": str(bundle.rule_set.rule_set_id),
                "rule_set_hash": bundle.rule_set.rule_set_hash,
                "builder_revision": bundle.configuration.builder_revision,
                "prior_observation_id": (
                    str(bundle.prior_observation.observation_id)
                    if bundle.prior_observation is not None
                    else None
                ),
                "prior_observation_hash": (
                    bundle.prior_observation.content_hash
                    if bundle.prior_observation is not None
                    else None
                ),
            }
        )
        replay = self._repository.resolve_command(
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        if replay is not None:
            return replay
        observation = ThesisHealthObservationBuilder().build(bundle)
        return self._repository.save_observation(
            observation,
            input_bundle=bundle,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
