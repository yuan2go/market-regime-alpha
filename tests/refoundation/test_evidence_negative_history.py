from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain.backtest_execution import BacktestExecutionState
from market_regime_alpha.research_qualification.ports.backtest_queries import BacktestReplayVerification
from market_regime_alpha.runtime.application.evidence import EvidenceApplication


@pytest.mark.parametrize('state,codes,integrity', [
    (BacktestExecutionState.FAILED, ('EXECUTION:FAILED',), True),
    (BacktestExecutionState.PLANNED, ('EXECUTION:PLANNED',), True),
    (BacktestExecutionState.RUNNING, ('EXECUTION:RUNNING',), True),
    (BacktestExecutionState.FAILED, ('EXECUTION:FAILED', 'ARTIFACT_BYTES:broken'), False),
    (BacktestExecutionState.INTEGRITY_ERROR, ('EXECUTION:INTEGRITY_ERROR', 'ACTION_INTEGRITY:broken'), False),
])
def test_inventory_integrity_preserves_negative_execution_without_promoting_replay(state, codes, integrity):
    run_id = uuid4()
    snapshot = {'artifacts': [], 'archives': [], 'backtests': [{'exploratory_backtest_run_id': str(run_id)}],
                'database': {}, 'observed_at': '2026-09-05T18:00:00Z'}
    replay = BacktestReplayVerification(run_id, False, codes, 'CURRENT_RELATIONAL', '1' * 64, state)
    application = EvidenceApplication(
        SimpleNamespace(snapshot=lambda: snapshot),
        SimpleNamespace(verify=lambda _rows: {'matched': True, 'mismatch_count': 0}),
        Path('local-artifacts'), object(), lambda _id: None, lambda _id: replay,
    )
    result = application.verify()
    assert result['matched'] is integrity
    assert (result['mismatch_count'] == 0) is integrity
    observation = result['reconciliations'][0]
    assert observation['completion_replay_matched'] is False
    assert observation['completion_replay_mismatch_codes'] == codes
    assert observation['execution_state'] == state.value
    assert replay.matched is False and replay.mismatch_count == len(codes)
