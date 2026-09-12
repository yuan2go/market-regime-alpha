"""Actual immutable v3 declaration, with explicitly synthetic read projections."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta
from hashlib import sha256
from importlib.resources import files
from io import StringIO
import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.application.validity import validity_report
from market_regime_alpha.research_qualification.domain import validity_protocol
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from tests.contracts.research_qualification.test_validity_report import canonical_fixture


HASHES = {
    1: '1414d39ab1082fffb1e45499c1ba2d93b1e54a442f58fe7a3cc68509d69c6944',
    2: 'efb4b9683ccf6201b9c1e3cbe0eb32338559fc430756155b06374794ffdb52de',
    3: '39106ff7c6d1742761f73ceba937b99b21092a76ab136f0e2fe7ec2aa16fc53f',
}


@pytest.mark.parametrize('version', (1, 2, 3))
def test_published_versions_keep_exact_bytes_and_append_only_predecessors(version):
    protocol = validity_protocol.load_validity_protocol(version)
    content = files('market_regime_alpha').joinpath(f'research_qualification/protocols/validity_v{version}.json').read_bytes()
    assert sha256(content).hexdigest() == protocol['protocol_sha256'] == HASHES[version]
    assert protocol['predecessor'] == (HASHES[version-1] if version > 1 else None)
    assert protocol['cohort_end_exclusive'] == {1: '2026-09-14', 2: '2026-09-15', 3: None}[version]


@pytest.mark.parametrize('version', (1, 2, 3))
def test_even_whitespace_changes_to_published_resource_fail_closed(version, monkeypatch, tmp_path):
    relative = f'research_qualification/protocols/validity_v{version}.json'
    original = files('market_regime_alpha').joinpath(relative).read_bytes()
    tampered = tmp_path / relative
    tampered.parent.mkdir(parents=True)
    tampered.write_bytes(original + b'\n')
    monkeypatch.setattr(validity_protocol, 'files', lambda package: tmp_path)
    with pytest.raises(ArtifactIntegrityError, match='FROZEN_VALIDITY_PROTOCOL_BYTES_CHANGED'):
        validity_protocol.load_validity_protocol(version)


def test_actual_v3_declaration_follows_owner_and_restoration_before_future_cohort():
    protocol = validity_protocol.load_validity_protocol()
    assert validity_protocol.CURRENT_PROTOCOL_VERSION == protocol['protocol_version'] == 3
    provenance = protocol['declaration_provenance']
    instant = validity_protocol.instant
    assert (instant(provenance['successor_registered_at']) < instant(provenance['hba_restored_at'])
            <= instant(protocol['declared_at']) < instant(provenance['successor_valid_from'])
            <= instant(protocol['first_eligible_target_start']) < instant(provenance['successor_expires_at']))
    assert instant(provenance['calendar_known_at']) < instant(protocol['declared_at'])
    assert protocol['declared_at'] == '2026-09-11T14:14:48.484434+00:00'
    assert protocol['first_eligible_future_session'] == '2026-09-15'
    assert protocol['first_eligible_target_session_id'] == 'e6162056-17f7-59bb-9ab7-10c0b24e536a'
    assert provenance['hba_restoration_state'] == 'PASS' and provenance['original_owner_login_denied'] is True
    assert protocol['identities']['experimental_model_use'] == {
        'id': '3a426d5f-702f-56fb-9563-0bc6256b558c',
        'content_sha256': '0a943331bfd04b58a61eb4f156da01da44027b05db83d2786988a23f4851c67c',
    }
    assert protocol['frozen_population_semantics']['experimental_model_use_id'] == protocol['identities']['experimental_model_use']['id']
    assert provenance['declaration_mode'] == 'PACKAGED_IMMUTABLE_SOURCE_PROTOCOL; NOT_DB_ARTIFACT_REGISTRATION'


def test_actual_v3_keeps_semantics_floors_and_population_from_v2():
    previous, protocol = (validity_protocol.load_validity_protocol(version) for version in (2, 3))
    validity_protocol.validate_protocol_revision(protocol, previous)
    for key in ('baseline_strategy_version_id', 'formula_contract', 'metric_roster', 'minimum_sessions', 'minimum_observations',
                'minimum_rank_pairs', 'rolling_sessions', 'ranking_k', 'ranking_quantiles', 'missingness_policy', 'population',
                'slices', 'unavailable_slices', 'target_metric_code', 'economic_assumptions', 'economic_policy', 'walk_forward'):
        assert protocol[key] == previous[key]
    for key in ('model_version', 'feature_definition', 'target_definition'):
        assert protocol['identities'][key] == previous['identities'][key]
    for key, value in previous['frozen_population_semantics'].items():
        if key != 'experimental_model_use_id':
            assert protocol['frozen_population_semantics'][key] == value
    assert (protocol['minimum_sessions'], protocol['minimum_observations']) == (20, 500)
    assert len(protocol['frozen_population_semantics']['instrument_ids']) == 32
    assert protocol['capacity_policy'] == {
        'downtime_buffer_sessions': 10, 'missing_observation_buffer_fraction': '0.20', 'expected_members_per_session': 32,
    }
    assert protocol['population_anchor'] == previous['population_anchor']


def test_actual_v2_capacity_ends_before_successor_even_with_later_calendar_facts():
    from tests.contracts.research_qualification.test_validity_capacity import NOW, _calendar, _use, _witness

    protocol = validity_protocol.load_validity_protocol(2)
    calendar = _calendar((date(2026, 9, 14), date(2026, 9, 24), date(2026, 10, 29), date(2026, 12, 31)))
    result = validity_protocol.cohort_capacity(protocol, calendar, _use(protocol), observed_at=NOW,
                                               calendar_coverage_witness=_witness(calendar))
    assert result['initial_theoretical_capacity']['session_roster'] == [date(2026, 9, 14)]
    assert result['initial_theoretical_capacity']['known_sessions'] == 1
    assert result['remaining_attainable']['known_observation_upper_bound'] == 32


@pytest.mark.parametrize('change', ('floor', 'use_hash', 'declaration', 'cohort', 'buffer', 'provenance'))
def test_v3_report_refuses_post_declaration_changes(change):
    protocol = validity_protocol.load_validity_protocol(3)
    if change == 'floor':
        protocol['minimum_observations'] = 31
    elif change == 'use_hash':
        protocol['identities']['experimental_model_use']['content_sha256'] = '0' * 64
    elif change == 'declaration':
        protocol['declared_at'] = '2026-09-10T00:00:00+00:00'
    elif change == 'cohort':
        protocol['first_eligible_future_session'] = '2026-09-14'
    elif change == 'buffer':
        protocol['capacity_policy']['downtime_buffer_sessions'] = 0
    else:
        protocol['declaration_provenance']['hba_restoration_state'] = 'FAIL'
    with pytest.raises(ArtifactIntegrityError, match='FROZEN_VALIDITY_PROTOCOL_CONTENT_MISMATCH'):
        validity_report({'cycles': [], 'unavailable': []}, protocol, [])


def _rollover_projection():
    # Synthetic canonical-shaped fixtures: never represented as live results.
    previous, protocol = (validity_protocol.load_validity_protocol(version) for version in (2, 3))
    observations, _, calendar = canonical_fixture(date(2026, 9, 15), protocol_version=3)
    cycles = []
    for day in (date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14)):
        historical, _, _ = canonical_fixture(day)
        cycle = historical['cycles'][0]
        cycle['prediction_id'] = UUID(int=day.day)
        cycles.append(cycle)
    v1 = validity_protocol.load_validity_protocol(1)
    for item in (v1, previous):
        start = datetime.fromisoformat(item['first_eligible_target_start'])
        calendar.append({'session_date': date.fromisoformat(item['first_eligible_future_session']),
                         'session_id': UUID(item['first_eligible_target_session_id']), 'open_at': start,
                         'close_at': start + timedelta(hours=5, minutes=30)})
    calendar.sort(key=lambda row: row['session_date'])
    by_day = {row['session_date']: row for row in calendar}
    for cycle in cycles:
        cycle['publication']['target_session_id'] = by_day[cycle['target_session']]['session_id']
    pending = cycles.pop()
    observations['unavailable'] = [{key: pending[key] for key in (
        'prediction_id', 'target_session', 'experimental_model_use_id', 'frozen_plan', 'publication')} | {'sampled': 32, 'state': 'OUTCOME_PENDING'}]
    observations['cycles'] = [*cycles, *observations['cycles']]
    uses = {UUID(previous['identities']['experimental_model_use']['id']): cycles[0]['frozen_identities']['experimental_model_use'],
            UUID(protocol['identities']['experimental_model_use']['id']): observations['cycles'][-1]['frozen_identities']['experimental_model_use']}
    return observations, calendar, uses


@pytest.mark.parametrize('version', (1, 2, None))
def test_cli_default_v3_and_explicit_predecessors_keep_use_cohorts_separate(version, monkeypatch):
    import market_regime_alpha.interfaces.cli.daily as cli
    import market_regime_alpha.interfaces.daily_observations as surface
    from market_regime_alpha.interfaces.cli.main import main

    observations, calendar, uses = _rollover_projection()
    before = deepcopy(observations)
    requests, owner_reads = [], []

    def owner(identity):
        owner_reads.append(identity)
        return uses[identity]

    @contextmanager
    def bootstrap(settings):
        yield SimpleNamespace(daily_prediction_reads=SimpleNamespace(
            validity_calendar=lambda: calendar, experimental_model_use_record=owner),
            calendar_continuity_reads=SimpleNamespace(calendar_coverage=lambda provider, observed_at: None))

    def read(app, **filters):
        requests.append(filters)
        return observations

    monkeypatch.setattr(cli, 'bootstrap_application', bootstrap)
    monkeypatch.setattr(surface, 'daily_observations', read)
    arguments = ['research', 'validity', 'daily']
    if version is not None:
        arguments.extend(('--protocol-version', str(version)))
    output, error = StringIO(), StringIO()
    assert main(arguments, environ={'MRA_DATABASE_URL': 'postgresql:///unused_test', 'MRA_ARTIFACT_ROOT': '/tmp/unused-validity-test'},
                stdout=output, stderr=error) == 0
    result = json.loads(output.getvalue())
    selected = version or 3
    expected = validity_protocol.load_validity_protocol(selected)
    assert result['protocol']['protocol_version'] == selected
    assert owner_reads == [UUID(expected['identities']['experimental_model_use']['id'])]
    assert set(requests[0]) == {'model_version_id', 'target_definition_id'}
    assert result['operational_session_count'] == 3
    assert result['predeclared_session_count'] == (1 if selected == 3 else 0)
    assert result['common_observation_count'] == (3 if selected == 3 else 0)
    assert result['session_cohort'] == (['2026-09-15'] if selected == 3 else ['2026-09-10', '2026-09-11'])
    assert [row['target_session'] for row in result['unavailable_sessions']] == ([] if selected == 3 else ['2026-09-14'])
    if selected == 2:
        assert result['cohort_population']['declared_daily_requests'] == 1
        assert result['cohort_data_quality']['evaluation_completion']['denominator'] == 1
    if selected == 3:
        assert result['cohort_population']['all_sampled'] == 32
        assert result['predeclared']['per_session'][0]['model']['mae']['denominator'] == 3
    assert result['MODEL_VALUE'] == 'NOT_ESTIMABLE' and result['ALPHA_PROVEN'] == 'NO'
    assert result['business_writes'] == 0 and result['reconciliation']['matched'] is True
    assert not error.getvalue() and observations == before


def test_old_use_cannot_be_relabelled_as_v3_even_with_identical_financial_semantics():
    observations, _, calendar = canonical_fixture(date(2026, 9, 14))
    with pytest.raises(ArtifactIntegrityError, match='MISMATCH'):
        validity_report(observations, validity_protocol.load_validity_protocol(3), calendar)
