"""Independent source-difference and pre-access guard contracts."""

from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from dataclasses import replace

import pytest

from market_regime_alpha.research_qualification.application.source_comparison import raw_differences, source_comparison, replay_model_batch
from market_regime_alpha.research_qualification.domain.backtest import BacktestSessionRole
from market_regime_alpha.research_qualification.domain.manifest import DecisionInputDatasetManifest, DecisionInputDatasetRow, FeatureCell
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.vocabulary import FeatureCellStatus
from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError
from market_regime_alpha.research_qualification.ports.model_execution import FrozenModelVersionPayload, ModelPrediction
from market_regime_alpha.research_qualification.ports.source_comparison import SourceComparisonModel
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


def bar(**changes):
    value = dict(instrument_id=1,timeframe='DAILY',price_basis='RAW_UNADJUSTED',event_start=datetime(2025,1,2,tzinfo=UTC),
        event_end=datetime(2025,1,2,7,tzinfo=UTC),bar_revision_id=uuid4(),open_value=Decimal(10),high_value=Decimal(11),
        low_value=Decimal(9),close_value=Decimal('10.2'),volume_value=Decimal('12345678901234567890123456.0000000001'),turnover_value=None)
    return value | changes


def test_raw_differences_preserve_price_basis_missing_revision_and_decimal_scale():
    original=bar()
    changed=bar(close_value=Decimal('10.21'),volume_value=Decimal('12345678901234567890123456.0000000002'))
    result=raw_differences((original,),(changed,))
    assert result[0]['right_minus_left']['close_value']==Decimal('.01')
    assert result[0]['right_minus_left']['volume_value']==Decimal('.0000000001')
    assert result[0]['right_minus_left']['turnover_value'] is None
    missing=raw_differences((original,),(bar(price_basis='BACKWARD_ADJUSTED'),))
    assert len(missing)==2 and all(r['state']=='MISSING_SIDE' and r['right_minus_left'] is None for r in missing)
    ambiguous=raw_differences((original,bar()),(changed,))
    assert ambiguous[0]['state']=='AMBIGUOUS_REVISION_ROSTER' and ambiguous[0]['right_minus_left'] is None


@pytest.mark.parametrize('fault', ['target','members','dates','duplicate','budget','mode'])
def test_comparison_refuses_changed_scope_before_loading_any_results(fault):
    start=date(2025,1,2)
    sessions=[SimpleNamespace(session_date=start,role=BacktestSessionRole.EVALUATION)]
    common=dict(target='target',sample_members=(SimpleNamespace(instrument_id=1),),
        folds=(SimpleNamespace(sessions=sessions),),market_archive='source',market_archive_seal='seal')
    left,right=SimpleNamespace(**common),SimpleNamespace(**common)
    if fault=='target':
        right.target='other'
    elif fault=='members':
        right.sample_members=()
    elif fault=='dates':
        right.folds=(SimpleNamespace(sessions=()),)
    elif fault=='duplicate':
        sessions.append(sessions[0])
    elif fault=='budget':
        sessions.extend(SimpleNamespace(session_date=start+timedelta(days=d),role=BacktestSessionRole.EVALUATION) for d in range(1,21))
    def forbidden(*_):
        pytest.fail('results must not be accessed before source scope validation')
    comparison=SimpleNamespace(_specifications=SimpleNamespace(load_specification=lambda r:left if r==1 else right),project=forbidden)
    with pytest.raises(ValueError):
        source_comparison(comparison._specifications,None,forbidden,None,None,left_run_id=1,right_run_id=2,left_arm='zero',right_arm='zero',
            start_date=start,end_date=start+timedelta(days=22),mode='FIXED_MODEL_REPLAY' if fault=='mode' else 'FIXED_DATA_MODELS')


def batch_inputs():
    first,second=uuid4(),uuid4()
    now=datetime(2025,1,10,7,tzinfo=UTC)
    binding=ArtifactBinding(uuid4(),'1'*64,1)
    rows=tuple(DecisionInputDatasetRow(uuid4(),uuid4(),(
        FeatureCell(first,FeatureCellStatus.AVAILABLE,Decimal(value),'COMPLETE',()),
        FeatureCell(second,FeatureCellStatus.MISSING if value==3 else FeatureCellStatus.AVAILABLE,
            None if value==3 else Decimal(value+10),'MISSING' if value==3 else 'COMPLETE',()))) for value in (1,2,3))
    manifest=DecisionInputDatasetManifest(uuid4(),'unit',1,DecisionTime(now),uuid4(),uuid4(),(first,second),binding,binding,(),rows,ContentHash('2'*64))
    payload=FrozenModelVersionPayload('fixture','1','3'*64,b'fixture','4'*64,(second,first),(),18,3)
    model=SourceComparisonModel(uuid4(),'5'*64,uuid4(),now-timedelta(days=2),now-timedelta(days=1),payload)
    return model,manifest


def test_fixed_replay_preserves_feature_order_missingness_and_uses_one_complete_batch():
    model,manifest=batch_inputs()
    class Predictor:
        calls=0
        def predict(self,payload,batch):
            self.calls+=1
            assert payload is model.payload
            assert tuple(row.features for row in batch.rows)==((Decimal(11),Decimal(1)),(Decimal(12),Decimal(2)))
            return tuple(ModelPrediction(row.row_id,row.features[0]*3+row.features[1]*2) for row in batch.rows)
    predictor=Predictor()
    result=replay_model_batch(model,manifest,predictor)
    assert predictor.calls==1
    assert result=={manifest.rows[0].instrument_id:Decimal(35),manifest.rows[1].instrument_id:Decimal(40)}


@pytest.mark.parametrize('field',['last_fit_decision','last_fit_label_cutoff'])
def test_fixed_replay_refuses_future_training_or_unmatured_labels_before_inference(field):
    model,manifest=batch_inputs()
    with pytest.raises(BacktestReportIntegrityError,match='future FIT decision or unmatured label'):
        replay_model_batch(replace(model,**{field:manifest.decision_time.value}),manifest,None)


@pytest.mark.parametrize('fault',['duplicate','nonfinite'])
def test_fixed_replay_refuses_invalid_prediction_roster(fault):
    model,manifest=batch_inputs()
    class Predictor:
        def predict(self,payload,batch):
            return tuple(ModelPrediction(batch.rows[0].row_id if fault=='duplicate' else row.row_id,
                Decimal('NaN') if fault=='nonfinite' else Decimal(1)) for row in batch.rows)
    with pytest.raises(BacktestReportIntegrityError,match='unexpected or nonfinite prediction roster'):
        replay_model_batch(model,manifest,Predictor())
