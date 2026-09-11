"""Protocol/cohort and temporal exclusions over immutable canonical projections."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.application.validity import validity_report
from market_regime_alpha.research_qualification.domain.validity_protocol import load_validity_protocol, validate_protocol_revision
from market_regime_alpha.research_qualification.domain.validity_readiness import walk_forward_readiness
from market_regime_alpha.research_qualification.domain.validity_temporal import temporal_integrity
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def canonical_fixture(day=date(2026, 9, 14), *, protocol_version=2):
    protocol = load_validity_protocol(protocol_version)
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=1, minutes=30)
    end = start + timedelta(hours=5, minutes=30)
    cutoff = start - timedelta(hours=2)
    identities = {}
    for name, alias in (("model_version", "model"), ("experimental_model_use", "experimental_model_use"),
                        ("feature_definition", "feature"), ("target_definition", "target")):
        value = protocol['identities'][name]
        identities[alias] = {name + '_id': UUID(value['id']), 'content_sha256': value['content_sha256']}
    identities['experimental_model_use'].update(valid_from=cutoff-timedelta(days=30), expires_at=cutoff+timedelta(days=30),
                                                registered_at=cutoff-timedelta(days=30), revoked_at=None,
                                                model_version_id=UUID(protocol['identities']['model_version']['id']))
    predictions = [{"commitment_id": UUID(int=i), "instrument_id": UUID(protocol["frozen_population_semantics"]["instrument_ids"][i-1]),
                    "point_estimate": model, "baseline_point_estimate": baseline,
                    "forecast_status": "AVAILABLE", "baseline_status": "AVAILABLE"}
                   for i, model, baseline in ((1, Decimal(1), Decimal(0)), (2, Decimal(-1), Decimal(1)), (3, Decimal(0), Decimal(-1)))]
    labels = [{"commitment_id": UUID(int=i), "metric_code": "next_session_intraday_return", "decimal_value": value,
               "value_status": "COMPLETE", "availability_status": "AVAILABLE", "finality_status": "UNKNOWN"}
              for i, value in ((1, Decimal(2)), (2, Decimal(-2)), (3, Decimal(0)))]
    population = [{"instrument_id": UUID(protocol["frozen_population_semantics"]["instrument_ids"][i-1]), "membership_status": "INCLUDED", "membership_reason": "KNOWN",
                   "eligibility_result": "ELIGIBLE" if i <= 3 else "INELIGIBLE", "eligibility_reason": "FROZEN_FIXTURE_DISPOSITION"} for i in range(1,33)]
    counts = {key: 3 for key in ('sampled','eligible','feature_ready','model_prediction','baseline_prediction','common_prediction')}
    counts['sampled'] = 32
    cycle = {'prediction_id': UUID(int=50), 'target_session': day, 'plan_sha256': 'a'*64,
             'experimental_model_use_id': UUID(protocol['identities']['experimental_model_use']['id']),
             'frozen_identities': identities, 'frozen_plan': {'plan':deepcopy(protocol['frozen_population_semantics'])},
             'publication': {'input_cutoff': cutoff, 'decision_time': cutoff, 'published_at': start-timedelta(hours=1),
                             'target_session_id': UUID(protocol['first_eligible_target_session_id']),
                             'baseline_strategy_version_id': protocol['baseline_strategy_version_id'], 'predictions': predictions,
                             'population': population, 'denominators': counts, 'dataset_id': UUID(int=60),
                             'decision_run_id': UUID(int=61), 'forecast_group_id': UUID(int=62)},
             'evaluation': {'metrics': [{'metric_code':'frozen_old_mae','decimal_value':Decimal('0.5')}]},
             'observations': [{'commitment_id': UUID(int=i), 'market_target_outcome_revision_id': UUID(int=200+i)} for i in range(1,4)],
             'labels': labels, 'replay': {'matched': True,'mismatch_count':0,'business_writes':0,'evaluation_id':UUID(int=63)},
             'temporal_facts': {'feature_known_at':cutoff-timedelta(seconds=1), 'model_recorded_at':cutoff-timedelta(days=2),
                                'model_training_knowledge_cutoff':cutoff-timedelta(days=3), 'dataset_frozen_at':cutoff+timedelta(seconds=1),
                                'target_start':start,'target_end':end,
                                'outcome_observations':[{'commitment_id': UUID(int=i), 'source_role':'OUTCOME_OBSERVATION',
                                    'capture_requested_at':end+timedelta(seconds=1),'capture_response_at':end+timedelta(seconds=2),
                                    'capture_recorded_at':end+timedelta(seconds=3),'capture_known_at':end+timedelta(seconds=3),
                                    'known_at':end+timedelta(seconds=4),'source_gap_id':None} for i in range(1,4)]}}
    calendar = [{'session_date':date(2026,9,10),'session_id':UUID(int=70),'open_at':datetime(2026,9,10,1,30,tzinfo=timezone.utc),'close_at':datetime(2026,9,10,7,tzinfo=timezone.utc)},
                {'session_date':date.fromisoformat(protocol['first_eligible_future_session']),'session_id':UUID(protocol['first_eligible_target_session_id']),
                 'open_at':datetime.fromisoformat(protocol['first_eligible_target_start']),
                 'close_at':datetime.combine(date.fromisoformat(protocol['first_eligible_future_session']), datetime.min.time(), tzinfo=timezone.utc)+timedelta(hours=7)}]
    observations = {'cycles':[cycle], 'unavailable':[], 'observed_at':end+timedelta(minutes=1), 'business_writes':0}
    return observations, protocol, calendar


def test_protocol_immutable_resource_hash_and_future_boundary():
    protocol = load_validity_protocol(2)
    assert protocol['protocol_sha256'] == 'efb4b9683ccf6201b9c1e3cbe0eb32338559fc430756155b06374794ffdb52de'
    assert protocol['minimum_sessions'] == 20 and protocol['minimum_observations'] == 500
    with pytest.raises(ValueError, match='UNDECLARED'):
        load_validity_protocol(99)
    revision = {**protocol,'protocol_version':3,'predecessor':protocol['protocol_sha256']}
    with pytest.raises(ValueError, match='CANNOT_RELABEL'):
        validate_protocol_revision(revision, protocol)
    revision['declared_at'] = revision['first_eligible_target_start']
    with pytest.raises(ValueError, match='NOT_BEFORE'):
        validate_protocol_revision(revision, protocol)


def test_report_preserves_canonical_metrics_and_common_population():
    observations, protocol, calendar = canonical_fixture()
    before = deepcopy(observations)
    report = validity_report(observations, protocol, calendar)
    assert observations == before
    assert report['business_writes'] == 0 and report['reconciliation']['matched'] is True
    assert report['RESEARCH_VALIDITY_STATUS'] == 'VALIDITY_EVIDENCE_ACCUMULATING'
    assert report['MODEL_VALUE'] == 'NOT_ESTIMABLE' and report['ALPHA_PROVEN'] == 'NO'
    row = report['per_session'][0]
    assert row['population']['common_estimable'] == 3
    assert row['canonical_evaluation'] == before['cycles'][0]['evaluation']
    assert row['data_quality']['unknown_finality']['numerator'] == 3
    assert row['temporal_integrity']['state'] == 'PASS'
    assert report['post_hoc_descriptive']['common_observation_count'] == 0
    assert report['walk_forward']['WALK_FORWARD_READY'] == 'NO'


def test_missing_baseline_excludes_same_member_from_both_metrics():
    observations, protocol, calendar = canonical_fixture()
    observations['cycles'][0]['publication']['predictions'][0]['baseline_point_estimate'] = None
    report = validity_report(observations, protocol, calendar)
    row = report['per_session'][0]
    assert (row['population']['model_estimable'],row['population']['baseline_estimable'],row['population']['common_estimable']) == (3,2,2)
    metrics = report['predeclared']['per_session'][0]
    assert metrics['model']['mae']['denominator'] == metrics['baseline']['mae']['denominator'] == 2
    assert row['exclusions'][0]['reason_codes'] == ['BASELINE_FORECAST_UNAVAILABLE']


@pytest.mark.parametrize('field', ['feature_known_at','model_recorded_at','model_training_knowledge_cutoff','dataset_frozen_at'])
def test_temporal_invalid_session_is_excluded_without_relabeling(field):
    observations, protocol, calendar = canonical_fixture()
    cycle = observations['cycles'][0]
    cycle['temporal_facts'][field] = cycle['temporal_facts']['target_end']
    report = validity_report(observations, protocol, calendar)
    assert report['per_session'][0]['temporal_integrity']['state'] == 'INVALID_FOR_VALIDITY'
    assert report['common_observation_count'] == 0
    assert len(report['per_session'][0]['exclusions']) == 3
    assert report['canonical_observations'][0]['labels'] == cycle['labels']


@pytest.mark.parametrize('field', ['capture_requested_at','capture_response_at','capture_recorded_at','capture_known_at','known_at'])
def test_outcome_cannot_reuse_input_capture_or_backdate(field):
    observations, _, _ = canonical_fixture()
    cycle = observations['cycles'][0]
    cycle['temporal_facts']['outcome_observations'][0][field] = cycle['publication']['input_cutoff']
    result = temporal_integrity(cycle)
    assert result['invalid_count'] == 1 and result['valid_count'] == 2


def test_historical_statistics_cannot_enter_future_protocol():
    observations, protocol, calendar = canonical_fixture(date(2026,9,10))
    report = validity_report(observations, protocol, calendar)
    assert report['predeclared_session_count'] == 0
    assert report['post_hoc_descriptive']['common_observation_count'] == 3
    assert report['per_session'][0]['classification'] == 'POST_HOC_DESCRIPTIVE'
    assert report['RESEARCH_VALIDITY_STATUS'] == 'INSUFFICIENT_OBSERVATIONS'


@pytest.mark.parametrize('change', ['replay','identity','duplicate','calendar'])
def test_replay_identity_and_roster_mismatch_refuse_even_filtered_report(change):
    observations, protocol, calendar = canonical_fixture()
    if change == 'replay':
        observations['cycles'][0]['replay']['mismatch_count'] = 1
    if change == 'identity':
        observations['cycles'][0]['frozen_identities']['model']['content_sha256'] = '0'*64
    if change == 'duplicate':
        observations['cycles'].append(deepcopy(observations['cycles'][0]))
    if change == 'calendar':
        calendar[-1]['open_at'] += timedelta(seconds=1)
    with pytest.raises(ArtifactIntegrityError):
        validity_report(observations, protocol, calendar, target_session_from=date(2026,9,12))


def test_views_do_not_select_qualifying_cohort_and_unknown_is_not_zero():
    observations, protocol, calendar = canonical_fixture()
    observations['cycles'][0]['labels'][0]['value_status'] = 'UNKNOWN'
    result = validity_report(observations, protocol, calendar, target_session_to=date(2026,9,10))
    assert result['RESEARCH_VALIDITY_STATUS'] == 'DESCRIPTIVE'
    assert result['selected_view_sessions'] == []
    assert result['common_observation_count'] == 2
    assert result['predeclared']['per_session'][0]['model']['mae']['denominator'] == 2


def test_walk_forward_rejects_duplicate_calendar_and_missing_data():
    observations, protocol, calendar = canonical_fixture()
    result = walk_forward_readiness(protocol, calendar, observations['cycles'])
    assert result['WALK_FORWARD_READY'] == 'NO'
    assert 'INSUFFICIENT_CAPTURED_TRADING_SESSION_HISTORY' in result['blockers']
    with pytest.raises(ValueError,match='CALENDAR_ROSTER'):
        walk_forward_readiness(protocol,[calendar[0],calendar[0]],observations['cycles'])


def test_cli_readonly_report_dispatch_and_protocol_refusal(monkeypatch):
    from contextlib import contextmanager
    from io import StringIO
    import json
    from types import SimpleNamespace
    import market_regime_alpha.interfaces.cli.daily as cli
    import market_regime_alpha.interfaces.daily_observations as surface
    from market_regime_alpha.interfaces.cli.main import main

    observations, _, calendar = canonical_fixture()
    calls = []

    @contextmanager
    def bootstrap(settings):
        yield SimpleNamespace(daily_prediction_reads=SimpleNamespace(
            validity_calendar=lambda: calendar,
            experimental_model_use_record=lambda identity: observations['cycles'][0]['frozen_identities']['experimental_model_use']),
            calendar_continuity_reads=SimpleNamespace(calendar_coverage=lambda provider, observed_at: None))

    def read(app, **filters):
        calls.append(filters)
        return observations

    monkeypatch.setattr(cli, 'bootstrap_application', bootstrap)
    monkeypatch.setattr(surface, 'daily_observations', read)
    env = {'MRA_DATABASE_URL':'postgresql:///unused_test', 'MRA_ARTIFACT_ROOT':'/tmp/unused-validity-test'}
    output, error = StringIO(), StringIO()
    assert main(['research','validity','daily','--protocol-version','2'],environ=env,stdout=output,stderr=error) == 0
    result = json.loads(output.getvalue())
    assert result['business_writes'] == 0
    assert result['ALPHA_PROVEN'] == 'NO'
    assert set(calls[0]) == {'model_version_id','target_definition_id'}
    assert not error.getvalue()
    assert main(['research','validity','daily','--protocol-version','99'],environ=env,stdout=StringIO(),stderr=error) == 2
    assert 'UNDECLARED_VALIDITY_PROTOCOL' in error.getvalue()


def test_operational_days_cross_use_without_joining_formal_population():
    observations, protocol, calendar = canonical_fixture()
    operational = deepcopy(observations)
    old = deepcopy(operational['cycles'][0])
    old['target_session'] = date(2026, 9, 10)
    old['experimental_model_use_id'] = UUID(int=999)
    operational['cycles'].append(old)
    result = validity_report(observations, protocol, calendar, operational_observations=operational)
    assert result['operational_session_count'] == 2
    assert result['predeclared_session_count'] == 1
    assert result['common_observation_count'] == 3
    assert result['session_cohort'] == [date(2026, 9, 14)]
    assert result['sustained_consecutive_sessions'] == 2
    operational['cycles'][-1]['replay']['matched'] = False
    with pytest.raises(ArtifactIntegrityError, match='OPERATIONAL_REPLAY_MISMATCH'):
        validity_report(observations, protocol, calendar, operational_observations=operational)
    operational['business_writes'] = 1
    with pytest.raises(ArtifactIntegrityError, match='OPERATIONAL_OBSERVATION_WRITES_REFUSED'):
        validity_report(observations, protocol, calendar, operational_observations=operational)


def test_daily_health_reads_backup_receipts_without_classifying_manual_as_scheduled(monkeypatch, tmp_path):
    from contextlib import contextmanager
    from io import StringIO
    import json
    from types import SimpleNamespace
    import market_regime_alpha.interfaces.cli.daily as cli
    import market_regime_alpha.interfaces.daily_health as health
    from market_regime_alpha.interfaces.cli.main import main

    @contextmanager
    def bootstrap(settings):
        yield SimpleNamespace(prospective_health=SimpleNamespace(inspect=lambda *args, **kwargs: {'business_writes':0}))

    monkeypatch.setattr(cli, 'bootstrap_application', bootstrap)
    monkeypatch.setattr(health, 'daily_health', lambda *args, **kwargs: {'business_writes':0})
    directory = tmp_path / 'refresh-manual'
    directory.mkdir()
    (directory / 'events.json').write_text(json.dumps([
        {'phase':'invocation', 'invocation_kind':'MANUAL_CONTROLLED_RECOVERY', 'observed_at':'2026-09-11T01:00:00+00:00'},
        {'phase':'failed', 'reason':'EXPIRED_ATTEMPT', 'observed_at':'2026-09-11T01:00:01+00:00'},
    ]))
    out, error = StringIO(), StringIO()
    env = {'MRA_DATABASE_URL':'postgresql:///unused_test', 'MRA_ARTIFACT_ROOT':str(tmp_path)}
    assert main(['research','daily','health','--series-code','fixture','--backup-receipts-directory',str(tmp_path)],
                environ=env, stdout=out, stderr=error) == 0
    result = json.loads(out.getvalue())['scheduled_backup']
    assert result['business_writes'] == 0
    assert result['SCHEDULED_BACKUP_RELIABILITY']['scheduled_fires'] == 0
    assert result['SCHEDULED_BACKUP_RELIABILITY']['state'] == 'NOT_ESTIMABLE'
    assert result['manual_receipt_count'] == 1
    assert result['receipts'][0]['reason_code'] == 'EXPIRED_ATTEMPT'


@pytest.mark.parametrize('change', ['threshold','candidate','population','session_date'])
def test_review_regressions_prevent_protocol_population_or_session_relabeling(change):
    observations, protocol, calendar = canonical_fixture()
    cycle = observations['cycles'][0]
    if change == 'threshold':
        protocol['minimum_sessions'] = protocol['minimum_observations'] = 1
    if change == 'candidate':
        cycle['frozen_plan']['plan']['candidate_policy_id'] = str(UUID(int=999))
    if change == 'population':
        cycle['frozen_plan']['plan']['instrument_ids'].pop()
    if change == 'session_date':
        cycle['target_session'] = date(2026,9,10)
        report = validity_report(observations, protocol, calendar)
        assert report['per_session'][0]['temporal_integrity']['state'] == 'INVALID_FOR_VALIDITY'
        assert report['post_hoc_descriptive']['common_observation_count'] == 0
        return
    with pytest.raises(ArtifactIntegrityError):
        validity_report(observations, protocol, calendar)


def test_predecessor_protocol_cannot_accumulate_into_successor():
    observations, protocol, calendar = canonical_fixture(date(2026,9,11))
    report = validity_report(observations, protocol, calendar)
    assert report['per_session'][0]['classification'] == 'PREDECESSOR_PROTOCOL_DESCRIPTIVE'
    assert report['predeclared_session_count'] == 0
    assert report['predecessor_protocol_descriptive']['session_count'] == 1
    assert report['post_hoc_descriptive']['session_count'] == 0
    assert load_validity_protocol(1)['population_binding_state'] == 'PROTOCOL_POPULATION_BINDING_INCOMPLETE'
    assert load_validity_protocol(1)['cohort_end_exclusive'] == '2026-09-14'


def test_walk_forward_actual_roster_accumulates_and_rejects_late_model_and_feature():
    protocol = load_validity_protocol(2)
    calendar, cycles = [], []
    first = date(2026,1,1)
    for offset in range(337):
        # Explicit disposable fixture calendar identities; never operational days.
        day = first + timedelta(days=offset)
        observation, _, _ = canonical_fixture(day)
        cycle = observation['cycles'][0]
        cycle['temporal_facts']['model_recorded_at'] = datetime(2025,1,1,tzinfo=timezone.utc)
        cycle['temporal_facts']['model_training_knowledge_cutoff'] = datetime(2024,12,31,tzinfo=timezone.utc)
        cycles.append(cycle)
        calendar.append({'session_date':day, 'session_id':UUID(int=1000+offset),
                         'open_at':cycle['temporal_facts']['target_start'], 'close_at':cycle['temporal_facts']['target_end']})
    short = walk_forward_readiness(protocol, calendar, cycles[:-1])
    assert short['WALK_FORWARD_READY'] == 'NO'
    assert short['captured_history_sessions'] == 336
    complete = walk_forward_readiness(protocol, calendar, cycles)
    assert complete['WALK_FORWARD_READY'] == 'YES'
    fold = complete['folds'][0]
    assert {key:len(rows) for key,rows in fold['sessions'].items()} == {'training':252,'validation':63,'embargo':1,'oos':21}
    assert fold['sessions']['training'][-1] < fold['sessions']['validation'][0] < fold['sessions']['embargo'][0] < fold['sessions']['oos'][0]
    cycles[0]['temporal_facts']['model_recorded_at'] = calendar[-1]['close_at']
    late_model = walk_forward_readiness(protocol, calendar, cycles)
    assert late_model['WALK_FORWARD_READY'] == 'NO'
    assert late_model['folds'][0]['invalid_model_binding_sessions'] == [str(first)]
    cycles[0]['temporal_facts']['model_recorded_at'] = datetime(2025,1,1,tzinfo=timezone.utc)
    cycles[0]['temporal_facts']['feature_known_at'] = calendar[-1]['close_at']
    assert walk_forward_readiness(protocol, calendar, cycles)['folds'][0]['invalid_pit_sessions'] == [str(first)]


def test_walk_forward_unknown_labels_never_ready_and_old_gap_is_retained():
    protocol = load_validity_protocol(2)
    calendar, cycles = [], []
    first = date(2026,1,1)
    for offset in range(337):
        observation, _, _ = canonical_fixture(first+timedelta(days=offset))
        cycle = observation['cycles'][0]
        cycle['temporal_facts']['model_recorded_at'] = datetime(2025,1,1,tzinfo=timezone.utc)
        cycle['temporal_facts']['model_training_knowledge_cutoff'] = datetime(2024,12,31,tzinfo=timezone.utc)
        cycles.append(cycle)
        calendar.append({'session_date':cycle['target_session'],'session_id':UUID(int=1000+offset),
                         'open_at':cycle['temporal_facts']['target_start'],'close_at':cycle['temporal_facts']['target_end']})
    old = {'session_date':first-timedelta(days=1),'session_id':UUID(int=999),
           'open_at':calendar[0]['open_at']-timedelta(days=1),'close_at':calendar[0]['close_at']-timedelta(days=1)}
    result = walk_forward_readiness(protocol,[old,*calendar],cycles)
    assert result['WALK_FORWARD_READY'] == 'YES'
    assert result['folds'][0]['missing_canonical_sessions'] == [str(old['session_date'])]
    assert result['folds'][-1]['state'] == 'READY'
    assert result['folds'][-1]['sessions']['training'][0] == first
    for cycle in cycles:
        for label in cycle['labels']:
            label.update(decimal_value=None,value_status='UNKNOWN',availability_status='UNKNOWN')
    unknown = walk_forward_readiness(protocol,calendar,cycles)
    assert unknown['WALK_FORWARD_READY'] == 'NO'
    assert unknown['usable_canonical_history_sessions'] == 0
    assert len(unknown['folds'][0]['unavailable_canonical_input_sessions']) == 337
