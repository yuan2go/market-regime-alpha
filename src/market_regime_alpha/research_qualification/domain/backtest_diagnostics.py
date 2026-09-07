"""Typed read-only member accounting, never financial or qualification Authority."""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FunnelCell:
    arm_id: str
    fold_id: str
    session_id: str
    session_date: date
    role: str
    dataset_id: str | None
    decision_run_id: str | None
    available_features: int
    missing_features: int
    unknown_features: int
    stale_features: int
    conflict_features: int


@dataclass(frozen=True, slots=True)
class FunnelMember:
    arm_id: str
    session_id: str
    instrument_id: str
    membership: str | None
    eligibility: str | None
    eligibility_reasons: tuple[str, ...]
    candidate_id: str | None
    candidate_disposition: str | None
    candidate_reason: str | None
    feature_states: tuple[str, ...]
    context_states: tuple[str, ...]
    signal_states: tuple[str, ...]
    forecast_states: tuple[str, ...]
    opportunity_states: tuple[str, ...]
    portfolio_states: tuple[str, ...]
    risk_states: tuple[str, ...]
    outcome_states: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FunnelMetricInput:
    metric_id: str
    expected_roster_size: int | None
    minimum_observations: int | None
    observation_count: int
    included_observation_count: int
    parent_member_count: int
    parent_observation_count: int
    input_states: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class FunnelTraining:
    training_run_id: str
    model_version_id: str | None
    sample_rows: int
    estimable_rows: int
    independent_session_count: int
    distinct_decision_count: int


@dataclass(frozen=True, slots=True)
class FunnelSnapshot:
    run_id: UUID
    specification_sha256: str
    database_name: str
    database_oid: int
    cluster_identity: str
    sample_instrument_ids: tuple[str, ...]
    cells: tuple[FunnelCell, ...]
    members: tuple[FunnelMember, ...]
    metric_inputs: tuple[FunnelMetricInput, ...]
    training: tuple[FunnelTraining, ...]
    arms: tuple["FunnelArm", ...] = ()
    outcome_gaps: tuple["FunnelOutcomeGap", ...] = ()


def summarize_funnel(source: FunnelSnapshot) -> dict[str, object]:
    cell_keys = {(c.arm_id, c.session_id) for c in source.cells}
    if len(cell_keys) != len(source.cells):
        raise ValueError('duplicate funnel cells')
    if len(set(source.sample_instrument_ids)) != len(source.sample_instrument_ids):
        raise ValueError('duplicate frozen sample instruments')
    keys = {(m.arm_id, m.session_id, m.instrument_id) for m in source.members}
    if len(keys) != len(source.members):
        raise ValueError('duplicate funnel member')
    expected = {(arm, session, instrument) for arm, session in cell_keys for instrument in source.sample_instrument_ids}
    if not expected or keys != expected:
        raise ValueError('funnel requires complete frozen member/cell roster')
    legal = [m for m in source.members if m.candidate_id is None and m.eligibility == 'INELIGIBLE' and m.eligibility_reasons]
    unexplained = [m for m in source.members if m.candidate_id is None and m not in legal]
    roles = {(c.arm_id, c.session_id): c.role for c in source.cells}
    downstream = {'signal_states', 'forecast_states', 'opportunity_states', 'portfolio_states', 'risk_states'}
    def counts(field: str) -> dict[str, int]:
        values: Counter[str] = Counter()
        for member in source.members:
            state = getattr(member, field)
            if isinstance(state, tuple):
                values.update(state or (('NOT_PLANNED_FIT' if field in downstream and roles[(member.arm_id, member.session_id)] == 'FIT_INPUT' else 'ABSENT'),))
            else:
                values.update((state or 'ABSENT',))
        return dict(sorted(values.items()))
    return {
        'declared_member_cell_count': len(expected),
        'candidate_member_cell_count': sum(m.candidate_id is not None for m in source.members),
        'eligible_denominator_count': sum(m.eligibility == 'ELIGIBLE' for m in source.members),
        'legal_eligibility_exclusion_count': len(legal),
        'unexplained_member_loss_count': len(unexplained),
        'feature_source_gap_reason_member_count': sum(any('SOURCE_GAP' in value for value in m.feature_states) for m in source.members),
        'independent_trading_session_count': len({c.session_date for c in source.cells}),
        'fold_session_cell_count': len(source.cells),
        'decision_count': len({c.decision_run_id for c in source.cells if c.decision_run_id}),
        'dataset_count': len({c.dataset_id for c in source.cells if c.dataset_id}),
        'economic_episode_count': 'NOT_INFERRED_FROM_MEMBER_ROWS; USE_CANONICAL_V2_EVALUATION_SCOPE',
        'model_training_count': len(source.training),
        'model_version_count': len({t.model_version_id for t in source.training if t.model_version_id}),
        'stages': {name: counts(field) for name, field in (
            ('Universe', 'membership'), ('Eligibility', 'eligibility'), ('Feature', 'feature_states'),
            ('Candidate', 'candidate_disposition'), ('Context', 'context_states'), ('Signal', 'signal_states'),
            ('Forecast', 'forecast_states'), ('Opportunity', 'opportunity_states'),
            ('Portfolio', 'portfolio_states'), ('Risk', 'risk_states'), ('Outcome', 'outcome_states'),
        )},
        'count_units': 'member × arm × fold-session; Context and Risk repeat on members; not independent observations',
    }


@dataclass(frozen=True, slots=True)
class FunnelArm:
    arm_id: str
    candidate_policy_sha256: str
    portfolio_policy_sha256: str
    risk_policy_sha256: str
    cost_roster_sha256: str


@dataclass(frozen=True, slots=True)
class FunnelOutcomeGap:
    decision_run_id: str
    commitment_id: str
    revision_id: str
    instrument_id: str
    outcome_status: str
    availability_status: str
    reason_codes: tuple[str, ...]
