"""Parser/dispatch contract only; PostgreSQL execution is verified separately."""

from uuid import uuid4

import pytest

from market_regime_alpha.interfaces.cli.main import _parser, _dispatch
from market_regime_alpha.interfaces.cli import research


@pytest.mark.parametrize('command', ['provider-recording-normalize','source-compare','prepare-recorded-archive'])
def test_new_research_commands_reach_existing_research_dispatch(command,monkeypatch):
    identity=str(uuid4())
    options=(["--capture-id",identity,"--idempotency-key","normalize-unit","--actor-id","operator"]
        if command=='provider-recording-normalize' else ["--left-run-id",identity,"--right-run-id",identity,
            "--left-arm","zero","--right-arm","ridge_v2","--start-date","2025-01-02","--end-date","2025-01-03","--mode","FIXED_DATA_MODELS"])
    if command=='prepare-recorded-archive':
        options=['--recording-capture-id',identity,'--reference-capture-id',str(uuid4()),'--archive-code','recorded_test',
            '--wheel','fixture.whl','--lockfile','uv.lock','--source-checkout','source','--output','scope','--code-sha','a'*40,'--actor-id','operator']
    args=_parser().parse_args(['research',command,*options,'--expected-database-name','research_scope','--expected-database-oid','123'])
    settings=object()
    def execute(actual,arguments):
        assert actual is settings and arguments is args
        return 'EXACT_RESEARCH_DISPATCH'
    monkeypatch.setattr(research,'execute_research',execute)
    assert _dispatch(args,settings)=='EXACT_RESEARCH_DISPATCH'


def test_recorded_archive_parser_requires_exact_capture_slice_and_database_identity():
    args=_parser().parse_args(['archive','observe-recorded','--manifest','frozen.json','--slice-id',str(uuid4()),
        '--capture-id',str(uuid4()),'--expected-database-name','research_scope','--expected-database-oid','123',
        '--actor-id','operator','--operation-key','observed-unit'])
    assert args.archive_command=='observe-recorded' and args.expected_database_oid==123
