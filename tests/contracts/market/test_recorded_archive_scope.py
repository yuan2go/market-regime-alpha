"""Closed RAW-only inventory contract; these are synthetic protocol tests."""

from dataclasses import asdict
from datetime import UTC, datetime
import json
from uuid import uuid4

import pytest

from market_regime_alpha.market.domain.professional_normalization import verify_recorded_archive_scope
from tests.contracts.market.test_professional_daily_recording import contract


def scope():
    references,recording=str(uuid4()),str(uuid4())
    return {'schema':'mra-recorded-archive-scope-v1','securities':[['600000.SH',str(uuid4())]],
        'price_inventory':{'target':'RAW_UNADJUSTED','cross_day_features':'NOT_SUPPORTED'},
        'universe':'STATIC_UNIVERSE/SURVIVORSHIP_LIMITED','source_contract':asdict(contract()),
        'recording_capture_id':recording,'reference_capture_ids':[references],
        'captures':[{'capture_id':i,'request_sha256':'a'*64,'known_at':datetime(2026,1,2,tzinfo=UTC),
            'artifact_sha256':'b'*64,'artifact_size_bytes':100} for i in (references,recording)],
        'code_sha':'a'*40,'wheel_sha256':'c'*64,'lockfile_sha256':'d'*64,
        'budgets':{'reserved_free_bytes':0,'maximum_slice_bytes':100,'maximum_archive_bytes':200},
        'qualification':'RECORDED_SOURCE_NOT_PIT_OR_PROVIDER_QUALIFICATION'}


def content(raw):
    return json.dumps(raw,default=lambda v:v.isoformat()).encode()


def test_recorded_archive_scope_preserves_real_knowledge_and_raw_only_population():
    result=verify_recorded_archive_scope(content(scope()))
    assert result['captures'][0]['known_at']=='2026-01-02T00:00:00+00:00'
    assert result['price_inventory']['cross_day_features']=='NOT_SUPPORTED'


@pytest.mark.parametrize('mutation',[
    lambda s:s['source_contract'].update(dividend_type='back'),
    lambda s:s['price_inventory'].update(cross_day_features='BACKWARD_ADJUSTED'),
    lambda s:s.update(qualification='FORMAL_PIT'),
    lambda s:s['securities'][0].__setitem__(0,'000001.SZ'),
    lambda s:s['captures'][0].update(extra='unknown'),
    lambda s:s['captures'][0].update(capture_id=str(uuid4())),
    lambda s:s['captures'][0].update(known_at='2026-01-03T00:00:00+00:00'),
    lambda s:s['captures'][0].update(known_at='2026-01-02T00:00:00'),
    lambda s:s['captures'][0].update(artifact_sha256='bad'),
    lambda s:s['captures'][0].update(artifact_size_bytes=True),
    lambda s:s['budgets'].update(maximum_archive_bytes=199),
    lambda s:s['budgets'].update(maximum_slice_bytes=99),
])
def test_unknown_mapping_roster_time_and_budget_are_rejected(mutation):
    raw=scope()
    mutation(raw)
    with pytest.raises(ValueError):
        verify_recorded_archive_scope(content(raw))
