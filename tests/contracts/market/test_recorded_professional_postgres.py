"""Local substitute bytes only; this is not real professional Provider evidence."""

from hashlib import sha256
from dataclasses import replace
import json
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings,bootstrap_application,bootstrap_database
from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.queries.professional_recording import replay_recorded_capture
from market_regime_alpha.infrastructure.recorded_professional_provider import RecordedProfessionalMarketProvider
from market_regime_alpha.market.domain import Provider,ProviderKind,ProviderProduct,SourceAvailabilityStatus,MarketFactKind,InstrumentFactKind,BarTimeframe,PriceBasis
from market_regime_alpha.market.ports.provider import CaptureRequest
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from tests.contracts.market.test_professional_daily_recording import contract,payload
from tests.contracts.research_qualification.archive_campaign_fixture import _context


def test_recorded_capture_recovers_contract_and_exact_original_bytes_without_sidecar(target_database_url,tmp_path):
    settings=TargetSettings(target_database_url,tmp_path/"artifacts")
    bootstrap_database(settings)
    raw=json.dumps(payload()).encode()
    digest=sha256(raw).hexdigest()
    provider=RecordedProfessionalMarketProvider(contract(),raw,expected_sha256=digest)
    with bootstrap_application(settings) as app:
        source=Provider(uuid4(),"recorded_protocol_fixture","Explicit local protocol substitute",ProviderKind.PUBLIC_ENDPOINT)
        product=ProviderProduct(uuid4(),source.provider_id,"recorded_daily_fixture",1,"LOCAL_PROTOCOL_SUBSTITUTE",
            "application/json","UTF-8",SourceAvailabilityStatus.UNKNOWN,tuple(MarketFactKind),tuple(InstrumentFactKind),tuple(BarTimeframe),tuple(PriceBasis))
        app.market.register_provider(source,_context("recorded-source"))
        app.market.register_provider_product(product,_context("recorded-product"))
        request=CaptureRequest(product.provider_product_id,"recorded-capture",provider.resource,"a"*64)
        captured=app.market.capture(request,provider,_context("recorded-capture"))
        repeated=app.market.capture(request,provider,_context("recorded-capture"))
        assert repeated.capture.capture_id==captured.capture.capture_id
        store=LocalArtifactStore(settings.artifact_root)
        with app._pool.connection(read_only=True) as c:
            before=c.execute("SELECT (SELECT count(*) FROM mra.command_receipt),(SELECT count(*) FROM mra.audit_event)").fetchone()
        checked=replay_recorded_capture(app._pool,store,captured.capture.capture_id)
        assert checked==replay_recorded_capture(app._pool,store,captured.capture.capture_id)
        assert checked["recording_sha256"]==digest and checked["contract"]["dividend_type"]=="none"
        assert checked["contract"]["volume_unit"]=="SHARES" and checked["source_available_at"] is None
        assert checked["verification"]["evidence_kind"]=="LOCAL_PROTOCOL_SUBSTITUTE" and checked["business_writes"]==0
        assert checked["verification"]["capture_request_identity"]=="MATCHED_ORIGINAL_CAPTURE_OWNER"
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT (SELECT count(*) FROM mra.command_receipt),(SELECT count(*) FROM mra.audit_event)").fetchone()==before
        path=store.object_path(checked["capture_content_sha256"])
        original=path.read_bytes()
        try:
            path.write_bytes(b"broken capture")
            with pytest.raises(ArtifactIntegrityError,match="physical bytes"):
                replay_recorded_capture(app._pool,store,captured.capture.capture_id)
        finally:
            path.write_bytes(original)
        class WrongRequestProvider:
            def capture(self, ignored):
                return RecordedProfessionalMarketProvider(contract(),raw,expected_sha256=digest).capture(request)
        foreign=app.market.capture(replace(request,capture_key="wrong-request",resource="another-resource"),
            WrongRequestProvider(),_context("wrong-request"))
        with pytest.raises(ArtifactIntegrityError,match="original request identity differs"):
            replay_recorded_capture(app._pool,store,foreign.capture.capture_id)
