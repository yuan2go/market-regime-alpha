"""Closed source protocols cannot absorb a successor's gaps or invalidity."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.research_qualification.application.validity import validity_report
from market_regime_alpha.research_qualification.domain import validity_protocol
from tests.contracts.research_qualification.test_validity_report import canonical_fixture


UTC = timezone.utc


def test_closed_published_v1_reports_only_its_own_missing_sessions():
    observations, _, calendar = canonical_fixture(date(2026, 9, 14))
    protocol = validity_protocol.load_validity_protocol(1)
    calendar.extend((
        {'session_date': date(2026, 9, 11), 'session_id': UUID(protocol['first_eligible_target_session_id']),
         'open_at': datetime.fromisoformat(protocol['first_eligible_target_start']),
         'close_at': datetime(2026, 9, 11, 7, tzinfo=UTC)},
        {'session_date': date(2026, 9, 15), 'session_id': UUID(int=998),
         'open_at': datetime(2026, 9, 15, 1, 30, tzinfo=UTC),
         'close_at': datetime(2026, 9, 15, 7, tzinfo=UTC)},
    ))
    calendar.sort(key=lambda row: row['session_date'])
    observations['observed_at'] = datetime(2026, 9, 15, 8, tzinfo=UTC)
    before = deepcopy(observations)
    report = validity_report(observations, protocol, calendar)
    assert report['planning_gaps'] == [date(2026, 9, 11)]
    assert report['per_session'][0]['classification'] == 'OUTSIDE_PROTOCOL_COHORT'
    assert report['predeclared_session_count'] == 0
    assert report['operational_session_count'] == 1
    assert report['canonical_observations'] == before['cycles']
    assert observations == before and report['business_writes'] == 0


def _synthetic_closed_v2(monkeypatch, boundary):
    # Only the successor-resource discovery seam is synthetic. v1/v2 contents,
    # minimum samples, identities and production require_frozen_protocol remain.
    # No v3 source file or real future protocol is created by this test.
    original_resource = validity_protocol._resource
    monkeypatch.setitem(validity_protocol._PROTOCOL_HASHES, 3, 'f' * 64)
    monkeypatch.setattr(validity_protocol, '_resource', lambda version:
        ({'first_eligible_future_session': boundary.isoformat()}, 'f' * 64)
        if version == 3 else original_resource(version))
    return validity_protocol.load_validity_protocol(2)


def _full_synthetic_session(day, ordinal):
    observations, _, _ = canonical_fixture(day)
    cycle = observations['cycles'][0]
    for key in ('predictions', 'population'):
        rows = cycle['publication'][key]
        if key == 'population':
            for row in rows:
                row['eligibility_result'] = 'ELIGIBLE'
            continue
        template = deepcopy(rows[0])
        cycle['publication'][key] = [dict(template, commitment_id=UUID(int=ordinal*100+index),
            instrument_id=UUID(cycle['frozen_plan']['plan']['instrument_ids'][index-1]),
            point_estimate=Decimal(index), baseline_point_estimate=Decimal(0)) for index in range(1, 33)]
    label, outcome = (deepcopy(cycle[key][0]) for key in ('labels', 'observations'))
    source = deepcopy(cycle['temporal_facts']['outcome_observations'][0])
    cycle['labels'] = [dict(label, commitment_id=row['commitment_id'], decimal_value=Decimal(index))
        for index, row in enumerate(cycle['publication']['predictions'], 1)]
    cycle['observations'] = [dict(outcome, commitment_id=row['commitment_id'], market_target_outcome_revision_id=UUID(int=10000+ordinal*100+index))
        for index, row in enumerate(cycle['publication']['predictions'], 1)]
    cycle['temporal_facts']['outcome_observations'] = [dict(source, commitment_id=row['commitment_id'])
        for row in cycle['publication']['predictions']]
    cycle['publication']['denominators'] = {key: 32 for key in cycle['publication']['denominators']}
    if ordinal:
        cycle['publication']['target_session_id'] = UUID(int=1000+ordinal)
    return cycle


def test_invalid_observations_after_closed_cohort_do_not_change_its_sample_gate(monkeypatch):
    boundary = date(2026, 10, 4)
    protocol = _synthetic_closed_v2(monkeypatch, boundary)
    # Explicit synthetic calendar: these are not assertions that civil dates
    # are real trading Sessions and cannot establish operational or Alpha proof.
    days = tuple(date(2026, 9, 14) + timedelta(days=offset) for offset in range(21))
    cycles = [_full_synthetic_session(day, index) for index, day in enumerate(days)]
    calendar = [{'session_date': cycle['target_session'], 'session_id': cycle['publication']['target_session_id'],
                 'open_at': cycle['temporal_facts']['target_start'], 'close_at': cycle['temporal_facts']['target_end']}
                for cycle in cycles]
    cycles[-1]['temporal_facts']['feature_known_at'] = cycles[-1]['publication']['input_cutoff'] + timedelta(seconds=1)
    observations = {'cycles': cycles, 'unavailable': [], 'observed_at': calendar[-1]['close_at']+timedelta(minutes=1), 'business_writes': 0}
    before = deepcopy(observations)
    report = validity_report(observations, protocol, calendar)
    assert report['predeclared_session_count'] == 20 and report['common_observation_count'] == 640
    assert report['RESEARCH_VALIDITY_STATUS'] == 'VALIDITY_BASELINE_ESTABLISHED'
    assert report['per_session'][-1]['classification'] == 'OUTSIDE_PROTOCOL_COHORT'
    assert report['per_session'][-1]['temporal_integrity']['invalid_count'] == 32
    assert report['planning_gaps'] == []
    assert report['operational_session_count'] == 21
    assert report['ALPHA_PROVEN'] == 'NO'
    assert observations == before and report['business_writes'] == 0
