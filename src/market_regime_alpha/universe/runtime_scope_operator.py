"""Owner-backed Full-A Runtime Scope construction and deterministic replay."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.universe.operational import (
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.runtime_scope import (
    ResearchUniversePolicy,
    RuntimeEligibilityObservation,
    RuntimeScopeReceipt,
    build_runtime_scope,
)


class PostgresRuntimeScopeOperator:
    """Compose existing free owners into the one PostgreSQL Runtime Scope owner."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._universe = PostgresFreeResearchUniverseRepository(
            factory,
            apply_migrations=apply_migrations,
        )
        self._scope = PostgresRuntimeScopeRepository(
            factory,
            apply_migrations=False,
        )

    def build(
        self,
        *,
        policy: ResearchUniversePolicy,
        as_of: datetime,
        built_at: datetime,
        security_master_snapshot_id: ArtifactId,
        operational_universes: tuple[OperationalUniverseArtifact, ...],
        code_revision: str,
    ) -> RuntimeScopeReceipt:
        if not operational_universes:
            raise ValueError("Runtime Scope requires Operational Universe inputs")
        security_master = self._universe.get(security_master_snapshot_id)
        observations = _eligibility_observations(
            operational_universes,
            as_of=as_of,
            built_at=built_at,
        )
        receipt = build_runtime_scope(
            policy=policy,
            as_of=as_of,
            built_at=built_at,
            security_master=security_master,
            eligibility_observations=observations,
            membership_snapshots=(),
            code_revision=code_revision,
        )
        return self._scope.publish(
            policy=policy,
            receipt=receipt,
            operational_universes=operational_universes,
        )

    def report(self, scope_id: ArtifactId) -> RuntimeScopeReceipt:
        return self._scope.get(scope_id)

    def replay(self, scope_id: ArtifactId) -> RuntimeScopeReceipt:
        stored = self._scope.get(scope_id)
        policy = self._scope.get_policy(stored.policy_id)
        security_references = tuple(
            item
            for item in stored.input_references
            if item.artifact_kind == "RESEARCH_UNIVERSE"
        )
        if len(security_references) != 1:
            raise ValueError("Runtime Scope Security Master lineage is not unique")
        security = self._universe.get(security_references[0].artifact_id)
        if security.snapshot_hash != security_references[0].content_hash:
            raise ValueError("Runtime Scope Security Master projection diverged")
        inputs = self._scope.get_operational_inputs(scope_id)
        rebuilt = build_runtime_scope(
            policy=policy,
            as_of=stored.as_of,
            built_at=stored.built_at,
            security_master=security,
            eligibility_observations=_eligibility_observations(
                inputs,
                as_of=stored.as_of,
                built_at=stored.built_at,
            ),
            membership_snapshots=(),
            code_revision=stored.code_revision,
        )
        if rebuilt != stored:
            raise ValueError("Runtime Scope replay mismatch")
        return stored


def _eligibility_observations(
    universes: tuple[OperationalUniverseArtifact, ...],
    *,
    as_of: datetime,
    built_at: datetime,
) -> tuple[RuntimeEligibilityObservation, ...]:
    ordered = tuple(sorted(universes, key=lambda item: str(item.universe_id)))
    if len({str(item.universe_id) for item in ordered}) != len(ordered):
        raise ValueError("Operational Universe inputs must be unique")
    grouped: dict[
        str,
        list[
            tuple[
                OperationalUniverseArtifact,
                OperationalUniverseRecord,
                ValidationArtifactReference,
            ]
        ],
    ] = {}
    for universe in ordered:
        universe.verify_identity()
        if universe.decision_date != as_of.date() or universe.effective_at > as_of:
            raise ValueError("Operational Universe violates Runtime Scope as-of")
        if universe.available_at > built_at:
            raise ValueError("Operational Universe was not available at build time")
        reference = ValidationArtifactReference(
            "OPERATIONAL_UNIVERSE",
            ArtifactId(str(universe.universe_id)),
            universe.content_hash,
        )
        for record in universe.records:
            grouped.setdefault(record.symbol, []).append(
                (universe, record, reference)
            )
    return tuple(
        _combined_observation(symbol, tuple(grouped[symbol]))
        for symbol in sorted(grouped)
    )


def _combined_observation(
    symbol: str,
    inputs: tuple[
        tuple[
            OperationalUniverseArtifact,
            OperationalUniverseRecord,
            ValidationArtifactReference,
        ],
        ...,
    ],
) -> RuntimeEligibilityObservation:
    st_values = tuple(
        None
        if record.st_status is STStatus.UNKNOWN
        else record.st_status is STStatus.ST
        for _, record, _ in inputs
    )
    suspension_values = tuple(
        None
        if record.suspension_status is SuspensionStatus.UNKNOWN
        else record.suspension_status is SuspensionStatus.SUSPENDED
        for _, record, _ in inputs
    )
    amounts = tuple(
        record.liquidity_evidence.median_daily_amount for _, record, _ in inputs
    )
    included_values = tuple(record.included for _, record, _ in inputs)
    listing_values = tuple(record.listing_status.value for _, record, _ in inputs)
    known_amounts = tuple(item for item in amounts if item is not None)
    return RuntimeEligibilityObservation.create(
        symbol=symbol,
        observed_at=max(universe.effective_at for universe, _, _ in inputs),
        known_at=max(universe.available_at for universe, _, _ in inputs),
        included=_conservative_inclusion(included_values),
        listing_status=_conservative_listing(listing_values),
        is_st=_conservative_rejection(st_values),
        suspended=_conservative_rejection(suspension_values),
        history_sessions=min(
            record.history_sessions_observed for _, record, _ in inputs
        ),
        median_daily_amount=(
            min(known_amounts) if len(known_amounts) == len(amounts) else None
        ),
        source_references=tuple(reference for _, _, reference in inputs),
    )


def _conservative_rejection(values: tuple[bool | None, ...]) -> bool | None:
    if any(item is True for item in values):
        return True
    if all(item is False for item in values):
        return False
    return None


def _conservative_inclusion(values: tuple[bool, ...]) -> bool:
    return all(values)


def _conservative_listing(values: tuple[str, ...]) -> str:
    if "DELISTED" in values:
        return "DELISTED"
    if all(item == "LISTED" for item in values):
        return "LISTED"
    return "UNKNOWN"


__all__ = ["PostgresRuntimeScopeOperator"]
