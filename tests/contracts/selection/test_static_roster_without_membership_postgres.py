"""A real owner flow over synthetic captures with no classification capability."""

from datetime import date
import json
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_database, bootstrap_application
from market_regime_alpha.market.domain import (
    Provider, ProviderKind, ProviderProduct, SourceAvailabilityStatus, MarketFactKind,
    BarTimeframe, PriceBasis, Instrument, InstrumentType, NormalizationBatch, ArchiveLane, ArchiveSealDisposition,
)
from market_regime_alpha.market.application import ArchiveSlicePlan, StartMarketArchiveRequest, RecordArchiveCaptureObservationRequest
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.selection.domain import UniverseDefinition, UniverseScopeSpecification, ExploratoryRetrospectiveSelectionScope
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime
from tests.contracts.research_qualification.archive_campaign_fixture import _context, _session
from tests.contracts.research_qualification.test_research_postgres import _BytesProvider, _Normalizer


def test_static_roster_needs_archived_instrument_and_retains_missing_membership(target_database_url,tmp_path):
    settings=TargetSettings(target_database_url,tmp_path/"artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        provider=Provider(uuid4(),"static_source","Synthetic static source",ProviderKind.PUBLIC_ENDPOINT)
        app.market.register_provider(provider,_context("provider"))
        product=ProviderProduct(uuid4(),provider.provider_id,"static_facts",1,"TEST","application/json","UTF-8",
            SourceAvailabilityStatus.UNKNOWN,(MarketFactKind.INSTRUMENT,MarketFactKind.TRADING_SESSION,MarketFactKind.MARKET_BAR),
            (),(BarTimeframe.DAILY,),(PriceBasis.RAW_UNADJUSTED,))
        app.market.register_provider_product(product,_context("product"))
        capture=app.market.capture(CaptureRequest(product.provider_product_id,"static","fixture://static","a"*64),_BytesProvider(),_context("capture"))
        cid=capture.capture.capture_id
        session=_session(date(2024,1,8),cid,"XSHG")
        instrument=Instrument(InstrumentId(uuid4()),"600001.XSHG","XSHG",InstrumentType.EQUITY,"CNY",cid)
        app.market.normalize(cid,_Normalizer(lambda _:NormalizationBatch(cid,product.provider_product_id,
            instruments=(instrument,),trading_sessions=(session,))),_context("normalize"))
        config=app.artifacts.publish(b"static fixture",media_type="text/plain",context=_context("config"))
        archive=uuid4()
        part=ArchiveSlicePlan(uuid4(),1,"static",session.open_at,session.close_at,capture.capture.request_hash.value,"INSTRUMENT")
        app.market_archives.start(StartMarketArchiveRequest(archive,"static_archive",ArchiveLane.RETROSPECTIVE_BACKFILL,
            product.provider_product_id,"XSHG",BarTimeframe.DAILY,PriceBasis.RAW_UNADJUSTED,"STATIC_TEST","b"*64,
            session.open_at,session.close_at,1,1000000,1000000,config.artifact_id,config.artifact_id,"d"*64,(part,)),_context("start"))
        app.market_archives.record_capture_observation(RecordArchiveCaptureObservationRequest(archive,part.market_archive_slice_id,cid,
            "RETROSPECTIVE_BATCH",capture.capture.temporal.capture_started_at),_context("observe"))
        seal=app.market_archives.seal_retrospective(market_archive_id=archive,disposition=ArchiveSealDisposition.COMPLETE,context=_context("seal"))
        universe=UniverseDefinition(uuid4(),"static_universe","STATIC_UNIVERSE/SURVIVORSHIP_LIMITED")
        app.selection.register_universe(universe,_context("universe"))
        def scope(scheme,code):
            content=json.dumps(dict(schema="selection-universe-scope-v1",classification_scheme=scheme,classification_code=code,
                market_provider_product_id=str(product.provider_product_id),instrument_ids=[str(instrument.instrument_id)]),sort_keys=True,separators=(",",":")).encode()
            artifact=app.artifacts.publish(content,media_type="application/json",context=_context("scope:"+scheme))
            return UniverseScopeSpecification(artifact.artifact_id,artifact.content_sha256,artifact.size_bytes,product.provider_product_id,
                scheme,code,(instrument.instrument_id,))
        declared=scope("STATIC_RESEARCH_ROSTER","SURVIVORSHIP_LIMITED_V1")
        retrospective=ExploratoryRetrospectiveSelectionScope(archive,seal.market_archive_seal_id,seal.knowledge_cutoff,session.close_at)
        result=app.selection.freeze_exploratory_retrospective_universe(universe_id=universe.universe_id,scope=declared,
            retrospective_scope=retrospective,context=_context("freeze"))
        assert len(result.members)==1 and result.members[0].evidence_status.value=="MISSING"
        assert result.members[0].membership_revision_id is None
        with pytest.raises(ValueError,match="cannot enter prospective"):
            app.selection.freeze_universe(universe_id=universe.universe_id,scope=declared,
                decision_time=DecisionTime(seal.knowledge_cutoff),context=_context("prospective-refuse"))
        with pytest.raises(RuntimeStateConflictError,match="classification capabilities"):
            app.selection.freeze_exploratory_retrospective_universe(universe_id=universe.universe_id,scope=scope("INDEX_MEMBERSHIP","CSI300"),
                retrospective_scope=retrospective,context=_context("classification-refuse"))
