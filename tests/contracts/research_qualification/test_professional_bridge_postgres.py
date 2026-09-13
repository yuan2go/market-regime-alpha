"""Synthetic recorded input through real Market, Dataset, Model and Evaluation.

The existing fixture supplies explicitly synthetic reference facts. Its DAILY
bars/status are replaced *before normalization*, then the production recorded
bridge owns those facts. No raw fixture result is model-validity evidence.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest

from market_regime_alpha.runtime.errors import ArtifactByteStoreError, ArtifactIntegrityError

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.queries.market_revision_lineage import PostgresMarketRevisionLineageReadPort
from market_regime_alpha.infrastructure.postgres.queries.professional_normalization import PostgresProfessionalNormalizationReferences
from market_regime_alpha.infrastructure.postgres.queries.professional_recording import replay_recorded_capture
from market_regime_alpha.infrastructure.providers.recorded_professional_normalizer import RecordedProfessionalDailyNormalizer
from market_regime_alpha.infrastructure.recorded_professional_provider import RecordedProfessionalMarketProvider
from market_regime_alpha.interfaces import historical_study as study
from market_regime_alpha.interfaces.historical_study_build import HistoricalBuild
from market_regime_alpha.market.domain import BarTimeframe, PriceBasis
from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract
from market_regime_alpha.market.ports.provider import CaptureRequest, NormalizerContract
from market_regime_alpha.research_qualification.domain.backtest import freeze_backtest_specification
from market_regime_alpha.research_qualification.domain.backtest_execution import BacktestExecutionBudget, BacktestExecutionState
from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalRidgeCandidate
from market_regime_alpha.research_qualification.domain.historical_rolling import HistoricalRollingPlan, RollingStudyPlan, ROBUSTNESS_CONTROLS
from tests.contracts.market.test_professional_normalization import mapping
from tests.contracts.research_qualification.archive_campaign_fixture import _context
from tests.contracts.research_qualification.daily_campaign_fixture import daily_baseline


def test_recorded_daily_bridge_reaches_canonical_model_outcome_evaluation_and_replay(target_database_url,tmp_path,monkeypatch):
    settings=TargetSettings(target_database_url,tmp_path/'artifacts')
    bootstrap_database(settings)
    build_bytes=b'LOCAL_PROTOCOL_SUBSTITUTE_ONLY_NOT_REAL_HISTORY'
    monkeypatch.setattr(study,'verify_historical_build',lambda **_: HistoricalBuild(build_bytes,sha256(build_bytes).hexdigest(),
        '1'*64,'2'*64,'3'*64,'0.1.0','0.8.15'))
    with bootstrap_application(settings) as app:
        captured_bridge=[]
        source_inputs=[]
        normalizing=app.market.normalize
        observing=app.market_archives.record_capture_observation
        starting=app.market_archives.start
        store=LocalArtifactStore(settings.artifact_root)
        bridge=RecordedProfessionalDailyNormalizer(PostgresProfessionalNormalizationReferences(app._pool,store),
            PostgresMarketRevisionLineageReadPort(app._pool))
        def normalize_references(capture_id,normalizer,context,**kwargs):
            batches=[]
            class ReferencesOnly:
                contract=NormalizerContract('fixture.professional_reference','1','4'*64)
                def normalize(self,capture,content):
                    batch=normalizer.normalize(capture,content)
                    batches.append(batch)
                    return replace(batch,bars=tuple(b for b in batch.bars if b.timeframe is not BarTimeframe.DAILY),security_status_facts=())
            result=normalizing(capture_id,ReferencesOnly(),context,**kwargs)
            batch=batches[0]
            codes={i.instrument_id:i.canonical_code[:6]+'.SH' for i in batch.instruments}
            bars=tuple(b for b in batch.bars if b.timeframe is BarTimeframe.DAILY and b.price_basis is PriceBasis.RAW_UNADJUSTED)
            days={s.session_id:s.session_date for s in batch.trading_sessions}
            c=ProfessionalDailyContract('fixture-1',tuple(sorted(codes.values())),min(days.values()),max(days.values()),'none',
                'SHARES','BAR_CLOSE','a'*64,len(bars),1_000_000)
            evidence=json.dumps(mapping(c),sort_keys=True).encode()
            c=replace(c,semantics_evidence_sha256=sha256(evidence).hexdigest())
            rows=[{'stock_code':codes[b.instrument_id],'session_date':str(days[b.session_id]),'time':int(b.event_end.timestamp()*1000),
                **{name:str(getattr(b,name).amount) for name in ('open','high','low','close','volume')},
                'amount':str(b.turnover.amount),'preClose':str(b.open.amount),'suspendFlag':0,'revision':'explicit-synthetic-1'} for b in bars]
            raw=json.dumps({'schema':'mra-xtquant-daily-recording-v1','evidence_kind':'LOCAL_PROTOCOL_SUBSTITUTE','sdk_version':'fixture-1','rows':rows}).encode()
            provider=RecordedProfessionalMarketProvider(c,raw,expected_sha256=sha256(raw).hexdigest(),normalization_evidence=evidence)
            request=CaptureRequest(batch.source_provider_product_id,'professional-bridge-capture',provider.resource,'a'*64)
            captured=app.market.capture(request,provider,_context('professional-bridge-capture'))
            first=normalizing(captured.capture.capture_id,bridge,_context('professional-bridge-normalize'))
            repeated=normalizing(captured.capture.capture_id,bridge,_context('professional-bridge-normalize'))
            assert repeated.replayed and repeated.receipt_id==first.receipt_id
            captured_bridge.append(captured.capture)
            source_inputs.append((batch,c,rows,evidence))
            return result
        def observe_both(request,context,**kwargs):
            result=observing(request,context,**kwargs)
            captured=captured_bridge[0]
            observing(replace(request,market_archive_slice_id=uuid5(request.market_archive_id,'professional-daily-slice'),
                capture_id=captured.capture_id,requested_at=captured.temporal.capture_started_at,
                schedule_slot='LOCAL_RECORDED_DAILY'),_context('professional-bridge-observe'))
            return result
        def start_two_slices(request,context,**kwargs):
            second=replace(request.slices[0],market_archive_slice_id=uuid5(request.market_archive_id,'professional-daily-slice'),
                ordinal=2,scope_key='local-recorded-daily',request_sha256=str(captured_bridge[0].request_hash))
            return starting(replace(request,slices=(*request.slices,second)),context,**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(app.market,'normalize',normalize_references)
            patch.setattr(app.market_archives,'record_capture_observation',observe_both)
            patch.setattr(app.market_archives,'start',start_two_slices)
            template,catalog=daily_baseline(app,archive_exchange='XSHG',mixed_daily_bars=True,all_session_facts=True)
        app.backtests.predeclare(template,_context('professional-bridge-template'))
        p=RollingStudyPlan('professional_bridge',template.exploratory_backtest_run_id,str(template.definition_sha256),
            template.market_archive.authority_id,str(template.market_archive.content_sha256),template.market_archive_seal.authority_id,
            str(template.market_archive_seal.content_sha256),(date(2026,1,5),date(2026,1,6)),(date(2026,1,7),),(date(2026,1,8),),
            (date(2026,1,9),),tuple(sorted((i.value for i in catalog['instruments']),key=str)),candidates=ROBUSTNESS_CONTROLS)
        plan=HistoricalRollingPlan(p,(),(HistoricalRidgeCandidate('ridge_intraday',('intraday',),Decimal(1)),),1)
        result=study.prepare_study(app,p,matrix=plan,wheel=Path('synthetic.whl'),lockfile=Path('synthetic.lock'),source_checkout=tmp_path,
            code_sha='a'*40,output=tmp_path,actor_id='local-protocol-substitute')
        run_id=UUID(str(result['run_id']))
        frozen=freeze_backtest_specification(app.backtest_specifications.load_specification(run_id))
        app.backtest_execution.run(frozen,budget=BacktestExecutionBudget(1,3600))
        assert app.backtest_execution.resume(frozen).execution_state is BacktestExecutionState.COMPLETED
        report=app.historical_comparison.project(run_id)
        assert report['full_funnel']['model_version_count']==5 and report['robustness']['all_arm_common_observations']==32
        assert len(report['input_roster'])==160 and all(point['model_version_id'] for point in report['input_roster'])
        captured=captured_bridge[0]
        checked=replay_recorded_capture(app._pool,store,captured.capture_id)
        assert checked['verification']['evidence_kind']=='LOCAL_PROTOCOL_SUBSTITUTE' and checked['source_available_at'] is None
        revisions=list({p['outcome_revision_id'] for p in report['input_roster']})
        with app._pool.connection(read_only=True) as connection:
            source_captures=connection.execute('''SELECT DISTINCT capture_id FROM mra.market_target_outcome_source
                WHERE market_target_outcome_revision_id=ANY(%s) AND source_kind='BAR_REVISION' ''',(revisions,)).fetchall()
        assert source_captures==[(captured.capture_id,)]
        replay=app.backtest_replay.verify(run_id)
        assert replay.matched
        path=store.object_path(checked['capture_content_sha256'])
        original=path.read_bytes()
        try:
            path.write_bytes(b'corrupt recorded source')
            with pytest.raises(ArtifactByteStoreError, match="content-addressed object cannot be read"):
                app.backtest_replay.verify(run_id)
        finally:
            path.write_bytes(original)
        assert app.backtest_replay.verify(run_id).matched
        _compare_second_recorded_source(app,settings,run_id,p,plan,catalog,source_inputs[0],bridge,tmp_path)


def _compare_second_recorded_source(app,settings,run_id,p,plan,catalog,source_input,bridge,tmp_path):
    """Two synthetic products, identical contracts, one explicit raw-price change."""
    from market_regime_alpha.market.application import ArchiveSlicePlan, ArchiveOperatorManifest, ArchiveManifestSlice, StartMarketArchiveRequest
    from market_regime_alpha.interfaces.archive import observe_recorded_archive_capture
    from market_regime_alpha.market.domain import ArchiveLane, ArchiveSealDisposition, NormalizationBatch
    from market_regime_alpha.shared.hashing import canonical_json_sha256
    from tests.contracts.research_qualification import test_research_postgres as fixtures
    same=app.historical_comparison.compare_sources(left_run_id=run_id,right_run_id=run_id,
        left_arm='zero',right_arm='ridge_v2',start_date=date(2026,1,9),end_date=date(2026,1,9),mode='FIXED_DATA_MODELS')
    assert same['paired_estimable']==32
    assert all(row['label_delta']==0 for row in same['rows'])
    assert all(all(delta==0 for delta in row['right_minus_left'].values() if delta is not None) for row in same['raw_differences'])
    batch,contract,rows,evidence=source_input
    product=replace(catalog['product'],provider_product_id=uuid4(),product_code='professional_synthetic_source_b')
    app.market.register_provider_product(product,_context('source-b-product'))
    refs=app.market.capture(CaptureRequest(product.provider_product_id,'source-b-references','fixture://source-b/references','a'*64),
        fixtures._BytesProvider(),_context('source-b-references'))
    # Independent synthetic activity evidence keeps the constant control's
    # mathematical price independence observable on the one missing-bar day.
    missing_instrument=next(i.instrument_id for i in batch.instruments if i.canonical_code=='600001.XSHG')
    missing_session=next(s.session_id for s in batch.trading_sessions if s.session_date==date(2026,1,9))
    independent_status=tuple(replace(f,fact_revision_id=uuid4(),provider_product_id=product.provider_product_id,
        capture_id=refs.capture.capture_id) for f in batch.security_status_facts
        if f.instrument_id==missing_instrument and f.session_id==missing_session)
    assert len(independent_status)==1
    reference_batch=NormalizationBatch(refs.capture.capture_id,product.provider_product_id,
        security_status_facts=independent_status,
        instruments=tuple(replace(i,source_capture_id=refs.capture.capture_id) for i in batch.instruments),
        trading_sessions=tuple(replace(s,source_capture_id=refs.capture.capture_id) for s in batch.trading_sessions),
        lifecycle_status_facts=tuple(replace(f,fact_revision_id=uuid4(),provider_product_id=product.provider_product_id,
            capture_id=refs.capture.capture_id) for f in batch.lifecycle_status_facts))
    changed=[dict(row) for row in rows if not (row['stock_code']=='600001.SH' and row['session_date']=='2026-01-09')]
    # One observed feature/label change; no adjustment equivalence claim.
    for row in changed:
        if row['stock_code']=='600000.SH':
            row['close']=str(Decimal(row['close'])+Decimal('.01'))
    raw=json.dumps({'schema':'mra-xtquant-daily-recording-v1','evidence_kind':'LOCAL_PROTOCOL_SUBSTITUTE',
        'sdk_version':'fixture-1','rows':changed}).encode()
    provider=RecordedProfessionalMarketProvider(contract,raw,expected_sha256=sha256(raw).hexdigest(),normalization_evidence=evidence)
    premature=app.market.capture(CaptureRequest(product.provider_product_id,'source-b-before-references',provider.resource,'a'*64),
        provider,_context('source-b-before-references'))
    with pytest.raises(ArtifactIntegrityError,match='reference lacks an exact readable product Capture binding'):
        app.market.normalize(premature.capture.capture_id,bridge,_context('source-b-refuse-foreign-calendar'))
    app.market.normalize(refs.capture.capture_id,fixtures._Normalizer(lambda _:reference_batch),_context('source-b-normalize-references'))
    # A later reference normalization cannot retroactively enter the first Capture's cutoff.
    with pytest.raises(ArtifactIntegrityError,match='reference lacks an exact readable product Capture binding'):
        PostgresProfessionalNormalizationReferences(app._pool,LocalArtifactStore(settings.artifact_root)).references(contract,premature.capture)
    provider=RecordedProfessionalMarketProvider(contract,raw,expected_sha256=sha256(raw).hexdigest(),normalization_evidence=evidence)
    capture=app.market.capture(CaptureRequest(product.provider_product_id,'source-b-daily',provider.resource,'a'*64),provider,_context('source-b-daily'))
    app.market.normalize(capture.capture.capture_id,bridge,_context('source-b-normalize-daily'))
    archive_id=uuid4()
    slices=tuple(ArchiveSlicePlan(uuid4(),ordinal,'source-b-'+str(ordinal),batch.trading_sessions[0].open_at,
        batch.trading_sessions[-1].close_at,str(c.request_hash),'MARKET_BAR') for ordinal,c in enumerate((refs.capture,capture.capture),1))
    start_request=StartMarketArchiveRequest(archive_id,'source_b_'+archive_id.hex[:12],ArchiveLane.RETROSPECTIVE_BACKFILL,
        product.provider_product_id,'XSHG',BarTimeframe.DAILY,PriceBasis.RAW_UNADJUSTED,'LOCAL_PROTOCOL_SUBSTITUTE',
        canonical_json_sha256(p.instrument_ids),batch.trading_sessions[0].open_at,batch.trading_sessions[-1].close_at,
        1,10_000_000,10_000_000,catalog['code'].artifact_id,catalog['config'].artifact_id,'d'*64,slices)
    app.market_archives.start(start_request,_context('source-b-archive'))
    requests=(CaptureRequest(product.provider_product_id,'source-b-references','fixture://source-b/references','a'*64),
        CaptureRequest(product.provider_product_id,'source-b-daily',provider.resource,'a'*64))
    manifest=ArchiveOperatorManifest(start_request,tuple(ArchiveManifestSlice(slice_,request,'LOCAL_PROTOCOL_SUBSTITUTE')
        for slice_,request in zip(slices,requests,strict=True)))
    for ordinal,(slice_,c) in enumerate(zip(slices,(refs.capture,capture.capture),strict=True)):
        observed=observe_recorded_archive_capture(app,manifest,capture_id=c.capture_id,slice_id=slice_.market_archive_slice_id,
            actor_id='local-protocol-substitute',operation_key='source-b-observe-'+str(ordinal),artifact_root=settings.artifact_root)
        repeated=observe_recorded_archive_capture(app,manifest,capture_id=c.capture_id,slice_id=slice_.market_archive_slice_id,
            actor_id='local-protocol-substitute',operation_key='source-b-observe-'+str(ordinal),artifact_root=settings.artifact_root)
        assert repeated.replayed and repeated.receipt_id==observed.receipt_id
    # Archive completeness counts captured requests. Market quality gaps remain
    # independent normalized facts and must still exclude unavailable features.
    sealed=app.market_archives.seal_retrospective(market_archive_id=archive_id,disposition=ArchiveSealDisposition.COMPLETE,context=_context('source-b-seal'))
    with app._pool.connection(read_only=True) as connection:
        quality_gaps=connection.execute("""SELECT gap.gap_id FROM mra.source_gap gap
            JOIN mra.market_archive_capture_observation observation USING(capture_id)
            WHERE observation.market_archive_id=%s AND gap.fact_kind='MARKET_BAR' AND gap.gap_kind='MISSING'""",(archive_id,)).fetchall()
    assert len(quality_gaps)==1 and sealed.gap_count==0
    # The production archive preparation freezes the recorded roster and uses
    # the same Archive owner. COMPLETE requests still contain one quality gap.
    from argparse import Namespace
    from market_regime_alpha.interfaces.professional_archive import prepare_recorded_archive
    from market_regime_alpha.infrastructure.postgres.queries.historical_inventory import PostgresHistoricalInventory
    archive_output=tmp_path/'recorded-source-scope'
    archive_output.mkdir()
    arguments=Namespace(archive_code='professional_source_scope',output=archive_output,
        recording_capture_id=capture.capture.capture_id,reference_capture_id=[refs.capture.capture_id],
        reserved_free_bytes=1,maximum_slice_bytes=10_000_000,maximum_archive_bytes=20_000_000,
        wheel=Path('synthetic.whl'),lockfile=Path('synthetic.lock'),source_checkout=tmp_path,code_sha='a'*40,
        actor_id='local-protocol-substitute')
    recorded=prepare_recorded_archive(app,settings,arguments)
    repeated=prepare_recorded_archive(app,settings,arguments)
    assert repeated['archive_id']==recorded['archive_id'] and all(o.replayed for o in repeated['observations'])
    archive_id=recorded['archive_id']
    sealed=app.market_archives.seal_retrospective(market_archive_id=archive_id,disposition=ArchiveSealDisposition.COMPLETE,context=_context('recorded-source-scope-seal'))
    inventory=PostgresHistoricalInventory(app._pool,LocalArtifactStore(settings.artifact_root)).inspect(archive_id,sealed.market_archive_seal_id)
    assert inventory['schema']=='mra-historical-inventory-v3'
    assert inventory['request_terminal_gap_count']==0 and inventory['normalized_quality_gap_count']==1
    assert inventory['declared_price_bases']==['RAW_UNADJUSTED']
    assert len(inventory['exclusions'])==1 and inventory['exclusions'][0]['state']=='SOURCE_GAP'
    assert inventory['physically_verified_capture_count']==2
    from market_regime_alpha.infrastructure.postgres.queries.historical_features import PostgresHistoricalFeatureInputReadPort
    from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
    from market_regime_alpha.research_qualification.domain.historical_features import calculate_historical_features
    selected_session=next(s for s in batch.trading_sessions if s.session_date==date(2026,1,9))
    snapshot=PostgresHistoricalFeatureInputReadPort(app._pool,LocalArtifactStore(settings.artifact_root)).snapshot(
        scope=ExploratoryRetrospectiveDatasetScope(archive_id,sealed.market_archive_seal_id,sealed.knowledge_cutoff,selected_session.close_at),
        instruments=p.instrument_ids,session_date=date(2026,1,9))
    assert all(point.adjusted_close is None for points in snapshot.population.values() for point in points)
    factors=calculate_historical_features(tuple(s[0] for s in snapshot.sessions),snapshot.population)
    assert sum(values['intraday'].value is not None for values in factors.values())==31
    assert all(values['return_1'].value is None for values in factors.values())
    with app._pool.connection(read_only=True) as connection:
        session_id=batch.trading_sessions[0].session_id.value
        selected=connection.execute("SELECT * FROM mra.exploratory_archive_calendar_capture(%s,%s,%s)",
            (session_id,archive_id,sealed.knowledge_cutoff)).fetchall()
        assert len(selected)==1 and selected[0][0]==refs.capture.capture_id and selected[0][2] is True
        assert connection.execute("SELECT * FROM mra.exploratory_archive_calendar_capture(%s,%s,%s)",
            (session_id,archive_id,premature.capture.temporal.known_at.value)).fetchall()==[]
        assert connection.execute("SELECT * FROM mra.exploratory_archive_calendar_capture(%s,%s,%s)",
            (session_id,uuid4(),sealed.knowledge_cutoff)).fetchall()==[]
    original=app.backtest_specifications.load_specification(run_id)
    second=replace(p,study_code='professional_source_b',template_backtest_id=run_id,template_definition_sha256=str(original.definition_sha256),
        market_archive_id=archive_id,market_archive_sha256=str(recorded['archive_sha256']),
        market_archive_seal_id=sealed.market_archive_seal_id,market_archive_seal_sha256=str(sealed.content_sha256))
    output=tmp_path/'second-source-study'
    output.mkdir()
    result=study.prepare_study(app,second,matrix=replace(plan,baseline=second),wheel=Path('synthetic.whl'),lockfile=Path('synthetic.lock'),
        source_checkout=tmp_path,code_sha='a'*40,output=output,actor_id='local-protocol-substitute',source_contracts_from=run_id)
    second_id=UUID(str(result['run_id']))
    frozen=freeze_backtest_specification(app.backtest_specifications.load_specification(second_id))
    try:
        execution=app.backtest_execution.run(frozen)
    except Exception:
        # Preserve the original exception while retaining narrow canonical
        # exclusion diagnostics before this disposable fixture is removed.
        from collections import Counter
        from psycopg.rows import dict_row
        from market_regime_alpha.infrastructure.postgres.queries.backtest_diagnostics import _CELLS_SQL, _MEMBERS_SQL, _MEMBER_FACTS_SQL
        with app._pool.connection(read_only=True) as connection,connection.cursor(row_factory=dict_row) as cursor:
            cells=cursor.execute(_CELLS_SQL,(second_id,)).fetchall()
            members=cursor.execute(_MEMBERS_SQL,(second_id,)).fetchall()
            datasets=list({c['dataset_id'] for c in cells if c['dataset_id'] is not None})
            decisions=list({c['decision_run_id'] for c in cells if c['decision_run_id'] is not None})
            facts=cursor.execute(_MEMBER_FACTS_SQL,(datasets,*(decisions for _ in range(5)))).fetchall()
            print('canonical_source_failure_members',Counter((r['membership_status'],r['result'],r['disposition'],r['reason_code']) for r in members))
            print('canonical_source_failure_facts',Counter((r['kind'],r['state'],r['reason']) for r in facts))
            print('canonical_source_failure_evaluations',cursor.execute("""SELECT e.expected_member_count,e.observation_count
                FROM mra.backtest_evaluation_execution x JOIN mra.evaluation_run e USING(evaluation_run_id)
                WHERE x.exploratory_backtest_run_id=%s""",(second_id,)).fetchall())
        raise
    assert execution.execution_state is BacktestExecutionState.COMPLETED
    from market_regime_alpha.infrastructure.postgres.schema import _historical_projection
    with app._pool.connection(read_only=True) as connection:
        before_comparison=_historical_projection(connection)
    missing=app.historical_comparison.compare_sources(left_run_id=second_id,right_run_id=second_id,left_arm='zero',right_arm='ridge_v2',
        start_date=date(2026,1,9),end_date=date(2026,1,9),mode='FIXED_DATA_MODELS')
    assert sum(row['left'].get('estimable',False) for row in missing['rows'])==32
    assert sum(row['right'].get('estimable',False) for row in missing['rows'])==31
    assert missing['paired_estimable']==31
    from market_regime_alpha.infrastructure.postgres.queries.outcome_inputs import _load_commitment, _load_retrospective_scope, _load_sessions, _load_target
    from market_regime_alpha.outcome.errors import OutcomeInputResolutionError
    with app._pool.connection(read_only=True) as connection:
        original_outcome=connection.execute("""SELECT r.commitment_id,r.observation_cutoff,r.knowledge_cutoff
            FROM mra.market_target_outcome_revision r JOIN mra.decision_target_commitment c USING(commitment_id)
            JOIN mra.exploratory_retrospective_decision_run d USING(decision_run_id)
            JOIN mra.exploratory_backtest_dataset b USING(dataset_id)
            WHERE b.exploratory_backtest_run_id=%s ORDER BY r.commitment_id LIMIT 1""",(second_id,)).fetchone()
        original_scope=_load_retrospective_scope(connection,original_outcome[0],observation_cutoff=original_outcome[1],knowledge_cutoff=original_outcome[2])
        commitment=_load_commitment(connection,original_outcome[0],retrospective_scope=original_scope)
        target=_load_target(connection,commitment.target_definition_id,version=commitment.target_version,content_sha256=commitment.target_definition_sha256)
        sessions=_load_sessions(connection,commitment=commitment,target=target,knowledge_cutoff=original_outcome[2])
        # Keep canonical first-Capture FK bytes, separately prove the selected
        # Archive's legitimate binding. A foreign Archive must not supply labels.
        assert all(connection.execute('SELECT source_capture_id FROM mra.trading_session WHERE session_id=%s',
            (s.session_id,)).fetchone()==(s.source_capture_id,) for s in sessions)
        wrong=replace(commitment,exploratory_retrospective_scope=replace(original_scope,market_archive_id=uuid4()))
        with pytest.raises(OutcomeInputResolutionError,match='selected Archive knowledge binding'):
            _load_sessions(connection,commitment=wrong,target=target,knowledge_cutoff=original_outcome[2])
    arguments=dict(left_run_id=run_id,right_run_id=second_id,left_arm='ridge_v2',right_arm='ridge_v2',
        start_date=date(2026,1,9),end_date=date(2026,1,9))
    for mode in ('FIXED_PROTOCOL_RETRAIN','FIXED_MODEL_REPLAY'):
        result=app.historical_comparison.compare_sources(**arguments,mode=mode)
        assert result['paired_estimable']==31
        assert sum(row['label_delta'] is not None and row['label_delta']!=0 for row in result['rows'])==1
        assert any(row['right_minus_left'] is not None and row['right_minus_left']['close_value']!=0 for row in result['raw_differences'])
        assert any(cell['value_delta'] is not None and cell['value_delta']!=0 for row in result['rows'] for cell in row['feature_deltas'])
    with pytest.raises(ValueError,match='cannot change algorithm'):
        app.historical_comparison.compare_sources(**{**arguments,'right_arm':'zero'},mode='FIXED_PROTOCOL_RETRAIN')
    with app._pool.connection(read_only=True) as connection:
        assert _historical_projection(connection,manifest=before_comparison.manifest).sha256==before_comparison.sha256

