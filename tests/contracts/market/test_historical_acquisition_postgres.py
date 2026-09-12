"""Disposable PostgreSQL recovery; recorded local protocol is not research data."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.interfaces.archive import resume_archive
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.market.application import ArchiveManifestSlice, ArchiveOperatorManifest, ArchiveSlicePlan, StartMarketArchiveRequest
from market_regime_alpha.market.domain import ArchiveLane, BarTimeframe
from market_regime_alpha.market.domain.archive import ArchiveSupplementalPriceBasis
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.contracts.market.test_baostock_archive_provider import _Sdk, _SdkResult
from tests.contracts.research_qualification.archive_campaign_fixture import seed_complete_archive, _context


@pytest.mark.parametrize("interrupted_after", ["capture", "normalize"])
def test_real_owner_resume_after_committed_capture_or_normalization(target_database_url, tmp_path, monkeypatch, interrupted_after):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        product, _, _, code, config, _, _ = seed_complete_archive(app, daily_bars=True)
        query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.TRADE_DATES, date(2026,1,20),date(2026,1,20))
        capture = CaptureRequest(product.provider_product_id,"historical-recovery-calendar",query.resource,"a"*64)
        start, end = datetime(2026,1,20,tzinfo=UTC), datetime(2026,1,20,23,59,tzinfo=UTC)
        item = ArchiveSlicePlan(uuid4(),1,"EXACT_CALENDAR",start,end,canonical_json_sha256(capture),"TRADING_SESSION")
        request = StartMarketArchiveRequest(uuid4(),"historical_recovery",ArchiveLane.RETROSPECTIVE_BACKFILL,
            product.provider_product_id,"XSHG",BarTimeframe.DAILY,ArchiveSupplementalPriceBasis.MIXED_EXPLICIT,
            "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED:CONTRACT_TEST", "b"*64,start,end,1048576,33554432,1048576,
            code.artifact_id,config.artifact_id,"c"*64,(item,))
        manifest = ArchiveOperatorManifest(request,(ArchiveManifestSlice(item,capture,"HISTORICAL_CAPTURE"),))
        app.market_archives.start(request,_context("historical-recovery-start"))
        assert app.archive_inspection.inspect(request.market_archive_id).slices[0].status == "OVERDUE"
        sdk = _Sdk(_SdkResult(["calendar_date","is_trading_day"],[["2026-01-20","1"]]))
        original = getattr(app.market, interrupted_after)
        failure = RuntimeError("injected process exit after committed owner operation")
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise failure
        monkeypatch.setattr(app.market,interrupted_after,interrupted)
        with pytest.raises(RuntimeError) as error:
            # No budget flags: the new mixed inventory must apply its defaults.
            resume_archive(app,manifest,sdk=sdk,actor_id="contract-test",operation_key="stable")
        assert error.value is failure
        assert len([call for call in sdk.calls if call[0] == "calendar"]) == 1
    # Fresh composition, original request identity and recorded owner facts.
    with bootstrap_application(settings) as restored:
        resumed = _Sdk(_SdkResult(["calendar_date","is_trading_day"],[]))
        result = resume_archive(restored,manifest,sdk=resumed,actor_id="contract-test",operation_key="stable")
        assert len(result) == 1 and result[0].status.value == "CAPTURED"
        assert resumed.calls == []
        assert restored.archive_inspection.inspect(request.market_archive_id).captured_slice_count == 1
        with restored._pool.connection(read_only=True) as connection:
            row = connection.execute("""SELECT observation.requested_at, observation.capture_started_at,
                count(*) OVER () FROM mra.market_archive_capture_observation observation
                WHERE market_archive_id=%s""",(request.market_archive_id,)).fetchone()
        assert row[0] == row[1] and row[2] == 1
        assert resume_archive(restored,manifest,sdk=resumed,actor_id="contract-test",operation_key="stable") == ()
        assert resumed.calls == []
