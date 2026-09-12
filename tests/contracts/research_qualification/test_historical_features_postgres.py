"""Disposable PostgreSQL/Artifact contracts, never historical performance evidence."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.infrastructure.artifacts.local import ArtifactStoreError, LocalArtifactStore
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.infrastructure.historical_features import HistoricalBacktestFeatureAdapter
from market_regime_alpha.infrastructure.postgres.queries.historical_features import PostgresHistoricalFeatureInputReadPort
from market_regime_alpha.interfaces.historical_feature_definitions import historical_feature_definitions
from market_regime_alpha.market.application import ArchiveSlicePlan, RecordArchiveCaptureObservationRequest, StartMarketArchiveRequest
from market_regime_alpha.market.domain import ArchiveLane, ArchiveSealDisposition, BarTimeframe, Instrument, InstrumentType, NormalizationBatch, PriceBasis
from market_regime_alpha.market.domain.archive import ArchiveSupplementalPriceBasis
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
from market_regime_alpha.research_qualification.domain.backtest_dataset import BacktestDatasetMember, materialize_backtest_dataset
from market_regime_alpha.research_qualification.domain.manifest import parse_decision_input_dataset_manifest
from market_regime_alpha.research_qualification.ports.backtest_actions import BacktestFeatureExecutionDefinition, BacktestFeatureRequest
from market_regime_alpha.shared.hashing import sha256_bytes
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from tests.contracts.research_qualification.archive_campaign_fixture import seed_complete_archive, _bar, _binding, _context, _session
from market_regime_alpha.shared.identity import InstrumentId
from tests.contracts.research_qualification.test_research_postgres import _BytesProvider, _Normalizer


def test_batch_factors_reload_exact_archive_and_reject_future_scope_and_physical_tampering(target_database_url,tmp_path):
    settings = TargetSettings(target_database_url,tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        product,instruments,sessions,code,config,archive,_seal = seed_complete_archive(app,daily_bars=True)
        with app._pool.connection(read_only=True) as connection:
            original = connection.execute("SELECT capture_id,capture.capture_started_at,capture.request_hash FROM mra.market_archive_capture_observation observation JOIN mra.data_capture capture USING(capture_id) WHERE market_archive_id=%s",(archive,)).fetchone()
        adjusted = app.market.capture(CaptureRequest(product.provider_product_id,"adjusted-test","fixture://adjusted","a"*64),_BytesProvider(),_context("adjusted-test"))
        adjusted_bars = tuple(replace(_bar(product.provider_product_id,adjusted.capture.capture_id,i,s,"REFERENCE",n),
            bar_revision_id=uuid4(),timeframe=BarTimeframe.DAILY,price_basis=PriceBasis.BACKWARD_ADJUSTED,event_start=s.open_at,event_end=s.close_at)
            for n,i in enumerate(instruments) for s in sessions)
        shenzhen = Instrument(InstrumentId(uuid4()),"000001.SZ","XSHE",InstrumentType.EQUITY,"CNY",adjusted.capture.capture_id)
        sz_sessions = tuple(_session(s.session_date,adjusted.capture.capture_id,"XSHE") for s in sessions)
        sz_bars = tuple(replace(_bar(product.provider_product_id,adjusted.capture.capture_id,shenzhen.instrument_id,s,"REFERENCE",0),
            bar_revision_id=uuid4(),timeframe=BarTimeframe.DAILY,price_basis=basis,event_start=s.open_at,event_end=s.close_at)
            for s in sz_sessions for basis in (PriceBasis.RAW_UNADJUSTED,PriceBasis.BACKWARD_ADJUSTED))
        app.market.normalize(adjusted.capture.capture_id,_Normalizer(lambda capture:NormalizationBatch(capture.capture_id,capture.provider_product_id,
            instruments=(shenzhen,),trading_sessions=sz_sessions,bars=(*adjusted_bars,*sz_bars))),_context("adjusted-normalize"))
        mixed = uuid4()
        slices = tuple(ArchiveSlicePlan(uuid4(),n,"EXACT_TEST_CAPTURE_"+str(n),sessions[0].open_at,sessions[-1].close_at,digest,"MARKET_BAR")
            for n,digest in enumerate((original[2],adjusted.capture.request_hash.value),1))
        app.market_archives.start(StartMarketArchiveRequest(mixed,"historical_feature_test",ArchiveLane.RETROSPECTIVE_BACKFILL,
            product.provider_product_id,"XSHG",BarTimeframe.DAILY,ArchiveSupplementalPriceBasis.MIXED_EXPLICIT,
            "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED:TEST","b"*64,sessions[0].open_at,sessions[-1].close_at,1,10000000,10000000,
            code.artifact_id,config.artifact_id,"d"*64,slices),_context("mixed-start"))
        for item,capture_id,started in ((slices[0],original[0],original[1]),(slices[1],adjusted.capture.capture_id,adjusted.capture.temporal.capture_started_at)):
            app.market_archives.record_capture_observation(RecordArchiveCaptureObservationRequest(mixed,item.market_archive_slice_id,capture_id,"RETROSPECTIVE_BATCH",started),_context("mixed-observe-"+str(item.ordinal)))
        seal = app.market_archives.seal_retrospective(market_archive_id=mixed,disposition=ArchiveSealDisposition.COMPLETE,context=_context("mixed-seal"))
        scope = ExploratoryRetrospectiveDatasetScope(mixed,seal.market_archive_seal_id,seal.knowledge_cutoff,sessions[-1].close_at)
        store = LocalArtifactStore(settings.artifact_root)
        reader = PostgresHistoricalFeatureInputReadPort(app._pool,store)
        snapshot = reader.snapshot(scope=scope,instruments=tuple(i.value for i in instruments),session_date=sessions[-1].session_date)
        assert len(snapshot.sessions)==12 and len(snapshot.population)==32
        mixed_snapshot = reader.snapshot(scope=scope,instruments=tuple(i.value for i in instruments)+(shenzhen.instrument_id.value,),session_date=sessions[-1].session_date)
        assert len(mixed_snapshot.population)==33
        assert any(d.identity==sz_sessions[-1].session_id.value for d in mixed_snapshot.dependencies[(shenzhen.instrument_id.value,sessions[-1].session_date,"RAW_UNADJUSTED")])
        definitions = historical_feature_definitions(uuid4(),_binding(code),_binding(config))
        requests = tuple(BacktestFeatureRequest(BacktestFeatureExecutionDefinition(f.feature_definition_id,f.content_sha256,f.feature_code,f.algorithm_code,f.algorithm_version,f.algorithm_sha256),scope,i,sessions[-1].session_date,sessions[-1].close_at) for i in instruments for f in definitions)
        adapter = HistoricalBacktestFeatureAdapter(reader)
        cells = adapter.materialize_batch(requests)
        assert len(cells)==320
        for n,request in enumerate(requests):
            factor = request.definition.algorithm_code
            if factor in {"historical_return_1_v1","historical_return_5_v1","historical_peer_relative_5_v1"}:
                assert cells[n].value==0
            if factor.endswith("20_v1"):
                assert cells[n].value is None and cells[n].reason_code=="FEATURE_WARMUP_INSUFFICIENT"
        members = tuple(BacktestDatasetMember(i.value,uuid4(),uuid4(),cells[n*10:(n+1)*10]) for n,i in enumerate(instruments))
        materialized = materialize_backtest_dataset(dataset_id=uuid4(),dataset_code="historical_feature_manifest",
            simulated_decision_time=scope.simulated_event_cutoff,universe_revision_id=uuid4(),eligibility_policy_id=uuid4(),
            feature_definition_ids=tuple(f.feature_definition_id for f in definitions),code_artifact=_binding(code),config_artifact=_binding(config),members=members)
        manifest_artifact = ArtifactBinding(uuid4(),sha256_bytes(materialized.manifest_content),len(materialized.manifest_content))
        parsed = parse_decision_input_dataset_manifest(materialized.manifest_content,dataset=materialized.definition(manifest_artifact),feature_definitions=definitions)
        assert len(parsed.rows)==32 and len(parsed.sources)>700
        with pytest.raises(RuntimeStateConflictError,match="cutoff"):
            reader.snapshot(scope=replace(scope,simulated_event_cutoff=sessions[-1].close_at-timedelta(seconds=1)),instruments=tuple(i.value for i in instruments),session_date=sessions[-1].session_date)
        assert adapter.materialize_batch(requests)==cells
        path = store.object_path(adjusted.artifact.content_sha256)
        prior = path.read_bytes()
        path.write_bytes(b"corrupt")
        try:
            with pytest.raises(ArtifactStoreError,match="cannot be read"):
                reader.snapshot(scope=scope,instruments=tuple(i.value for i in instruments),session_date=sessions[-1].session_date)
        finally:
            path.write_bytes(prior)
        _verify_failed_capture_context(app,product,instruments,sessions,code,config,original,reader,definitions)


def _verify_failed_capture_context(app,product,instruments,sessions,code,config,original,reader,definitions):
    from datetime import UTC, datetime
    from market_regime_alpha.market.domain import InstrumentIdentifier
    from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
    from market_regime_alpha.infrastructure.postgres.queries.research_sources import PostgresResearchSourceQueries
    from market_regime_alpha.research_qualification.application._dataset_validation import validate_market_lineage
    from market_regime_alpha.shared.hashing import canonical_json_sha256
    from tests.contracts.market.test_archive_postgres import _FailingProvider
    identified = app.market.capture(CaptureRequest(product.provider_product_id,"identifier-test","fixture://identifier","a"*64),_BytesProvider(),_context("identifier-test"))
    identifier = InstrumentIdentifier(uuid4(),instruments[0],"BAOSTOCK","sh.600000",datetime(2020,1,1,tzinfo=UTC),None,1,None,identified.capture.capture_id)
    app.market.normalize(identified.capture.capture_id,_Normalizer(lambda capture:NormalizationBatch(capture.capture_id,capture.provider_product_id,instrument_identifiers=(identifier,))),_context("identifier-normalize"))
    start = datetime.combine(sessions[0].session_date,datetime.min.time(),UTC)
    end = datetime.combine(sessions[-1].session_date,datetime.max.time(),UTC)
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.HISTORY_DAILY_BACK_ADJUSTED,start.date(),end.date(),"sh.600000")
    request = CaptureRequest(product.provider_product_id,"failed-adjusted-test",query.resource,canonical_json_sha256({"headers":"NONE","query":query.resource}))
    failed = app.market.capture(request,_FailingProvider(),_context("failed-adjusted"))
    with app._pool.connection(read_only=True) as connection:
        gap = connection.execute("SELECT gap_id FROM mra.source_gap WHERE capture_id=%s",(failed.capture.capture_id,)).fetchone()[0]
    archive = uuid4()
    slices = tuple(ArchiveSlicePlan(uuid4(),n,"HISTORY_DAILY_BACK_ADJUSTED:sh.600000" if n==3 else "EXACT_TEST_CAPTURE_"+str(n),
        start,end,digest,"MARKET_BAR") for n,digest in enumerate((original[2],identified.capture.request_hash.value,failed.capture.request_hash.value),1))
    app.market_archives.start(StartMarketArchiveRequest(archive,"historical_failed_feature",ArchiveLane.RETROSPECTIVE_BACKFILL,
        product.provider_product_id,"XSHG",BarTimeframe.DAILY,ArchiveSupplementalPriceBasis.MIXED_EXPLICIT,
        "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED:TEST","b"*64,start,end,1,10000000,10000000,code.artifact_id,config.artifact_id,"d"*64,slices),_context("failed-archive-start"))
    for item,capture_id,started in ((slices[0],original[0],original[1]),(slices[1],identified.capture.capture_id,identified.capture.temporal.capture_started_at)):
        app.market_archives.record_capture_observation(RecordArchiveCaptureObservationRequest(archive,item.market_archive_slice_id,capture_id,"RETROSPECTIVE_BATCH",started),_context("failed-archive-observe-"+str(item.ordinal)))
    app.market_archives.record_slice_gap(market_archive_id=archive,market_archive_slice_id=slices[2].market_archive_slice_id,gap_id=gap,terminal_status="GAP_RECORDED",context=_context("failed-archive-gap"))
    seal = app.market_archives.seal_retrospective(market_archive_id=archive,disposition=ArchiveSealDisposition.PARTIAL_WITH_GAPS,context=_context("failed-archive-seal"))
    scope = ExploratoryRetrospectiveDatasetScope(archive,seal.market_archive_seal_id,seal.knowledge_cutoff,sessions[-1].close_at)
    requests = tuple(BacktestFeatureRequest(BacktestFeatureExecutionDefinition(f.feature_definition_id,f.content_sha256,f.feature_code,f.algorithm_code,f.algorithm_version,f.algorithm_sha256),scope,instruments[0],sessions[-1].session_date,sessions[-1].close_at) for f in definitions)
    cells = HistoricalBacktestFeatureAdapter(reader).materialize_batch(requests)
    for request,cell in zip(requests,cells):
        if request.definition.algorithm_code=="historical_return_5_v1":
            assert cell.status.value=="UNKNOWN" and any(d.identity==gap for d in cell.additional_dependencies)
    materialized = materialize_backtest_dataset(dataset_id=uuid4(),dataset_code="historical_failed_manifest",simulated_decision_time=scope.simulated_event_cutoff,
        universe_revision_id=uuid4(),eligibility_policy_id=uuid4(),feature_definition_ids=tuple(f.feature_definition_id for f in definitions),
        code_artifact=_binding(code),config_artifact=_binding(config),members=(BacktestDatasetMember(instruments[0].value,uuid4(),uuid4(),cells),))
    binding = ArtifactBinding(uuid4(),sha256_bytes(materialized.manifest_content),len(materialized.manifest_content))
    manifest = parse_decision_input_dataset_manifest(materialized.manifest_content,dataset=materialized.definition(binding),feature_definitions=definitions)
    with app._pool.connection(read_only=True) as connection:
        observations = PostgresResearchSourceQueries(connection).exploratory_market_source_observations(manifest.sources,
            market_archive_id=archive,market_archive_seal_id=seal.market_archive_seal_id,knowledge_cutoff=seal.knowledge_cutoff,
            simulated_event_cutoff=scope.simulated_event_cutoff,lock=False)
    validate_market_lineage(manifest,features=definitions,observations=observations,knowledge_cutoff=seal.knowledge_cutoff,simulated_event_cutoff=scope.simulated_event_cutoff)
    context = next(o for o in observations if o.request_failure is not None)
    assert context.source_identity==gap and context.event_cutoff_at is None and context.instrument_id is None
