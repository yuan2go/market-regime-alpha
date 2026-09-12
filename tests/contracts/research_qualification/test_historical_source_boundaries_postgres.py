"""Real owner/query regressions on disposable synthetic source facts only."""

from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.queries.historical_inventory import PostgresHistoricalInventory
from market_regime_alpha.infrastructure.postgres.queries.historical_study import read_study_dependencies
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.interfaces import historical_study as study
from market_regime_alpha.interfaces.historical_study_build import HistoricalBuild
from market_regime_alpha.market.application import ArchiveSlicePlan, RecordArchiveCaptureObservationRequest, StartMarketArchiveRequest
from market_regime_alpha.market.domain import ArchiveLane, ArchiveSealDisposition, BarTimeframe, InstrumentIdentifier, NormalizationBatch
from market_regime_alpha.market.domain.archive import ArchiveSupplementalPriceBasis
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import InstrumentId
from tests.contracts.market.test_archive_postgres import _FailingProvider
from tests.contracts.research_qualification.archive_campaign_fixture import _context, _session, seed_complete_archive
from tests.contracts.research_qualification.daily_campaign_fixture import daily_baseline
from tests.contracts.research_qualification.test_research_postgres import _BytesProvider, _Normalizer


def _start(app, product, code, config, slices, scope_hash="b" * 64):
    archive = uuid4()
    app.market_archives.start(StartMarketArchiveRequest(
        archive, "source_boundary_" + archive.hex, ArchiveLane.RETROSPECTIVE_BACKFILL,
        product, "XSHG", BarTimeframe.DAILY, ArchiveSupplementalPriceBasis.MIXED_EXPLICIT,
        "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED:CONTRACT_TEST", scope_hash,
        min(s.event_window_start for s in slices), max(s.event_window_end for s in slices),
        1, 10000000, 10000000, code, config, "d" * 64, tuple(slices)), _context("start-" + archive.hex))
    return archive


def _observe(app, archive, item, capture):
    app.market_archives.record_capture_observation(RecordArchiveCaptureObservationRequest(
        archive, item.market_archive_slice_id, capture.capture_id, "RETROSPECTIVE_BATCH",
        capture.temporal.capture_started_at), _context("observe-" + item.market_archive_slice_id.hex))


def test_inventory_maps_failed_requests_across_full_window_without_scope_spread(target_database_url, tmp_path):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        product, instruments, sessions, code, _, original_archive, _ = seed_complete_archive(app, daily_bars=True)
        captured = app.market.capture(CaptureRequest(product.provider_product_id, "inventory-identifiers", "fixture://identifiers", "a" * 64),
            _BytesProvider(), _context("inventory-identifiers"))
        extra_sessions = tuple(_session(date(2026, 2, 1) + timedelta(days=n), captured.capture.capture_id, "XSHG") for n in range(25))
        codes = tuple("sh." + str(600000 + n) for n in range(len(instruments)))
        identifiers = tuple(InstrumentIdentifier(uuid4(), instrument, "BAOSTOCK", codes[n], datetime(2020, 1, 1, tzinfo=UTC), None, 1, None,
            captured.capture.capture_id) for n, instrument in enumerate(instruments))
        app.market.normalize(captured.capture.capture_id, _Normalizer(lambda c: NormalizationBatch(c.capture_id, c.provider_product_id,
            instrument_identifiers=identifiers, trading_sessions=extra_sessions)), _context("inventory-identifiers-normalize"))
        all_sessions = (*sessions, *extra_sessions)
        start, end = datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 2, 26, tzinfo=UTC)
        frozen = {"schema": "mra-historical-acquisition-freeze-v1", "securities": list(zip(codes, map(str, instruments))),
            "price_inventory": ["RAW_UNADJUSTED", "BACKWARD_ADJUSTED"], "universe": "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED"}
        config = app.artifacts.publish(json.dumps(frozen).encode(), media_type="application/json", context=_context("inventory-config"))
        with app._pool.connection(read_only=True) as c:
            original = c.execute("SELECT capture_id FROM mra.market_archive_capture_observation WHERE market_archive_id=%s", (original_archive,)).fetchone()[0]
        with app._pool.connection(read_only=True) as c:
            from market_regime_alpha.infrastructure.postgres.repositories.market import PostgresMarketRepository
            original_capture = PostgresMarketRepository(c).capture_source(original).capture
        slices = [ArchiveSlicePlan(uuid4(), n, "EXACT_CAPTURE_" + str(n), start, end, capture.request_hash.value, "MARKET_BAR")
            for n, capture in enumerate((original_capture, captured.capture), 1)]
        failures = []
        for n, (instrument_index, kind, lo, hi) in enumerate((
            (0, BaoStockArchiveQueryKind.HISTORY_DAILY_BACK_ADJUSTED, start, end),
            (0, BaoStockArchiveQueryKind.HISTORY_DAILY_RAW, datetime(2026, 1, 5, tzinfo=UTC), datetime(2026, 1, 8, tzinfo=UTC)),
            (1, BaoStockArchiveQueryKind.HISTORY_DAILY_BACK_ADJUSTED, datetime(2026, 2, 3, tzinfo=UTC), datetime(2026, 2, 5, tzinfo=UTC)),
        ), 3):
            query = BaoStockArchiveQuery(kind, lo.date(), hi.date(), codes[instrument_index])
            failed = app.market.capture(CaptureRequest(product.provider_product_id, "inventory-failure-" + str(n), query.resource,
                canonical_json_sha256({"headers": "NONE", "query": query.resource})), _FailingProvider(), _context("failure-" + str(n)))
            with app._pool.connection(read_only=True) as c:
                gap = c.execute("SELECT gap_id FROM mra.source_gap WHERE capture_id=%s", (failed.capture.capture_id,)).fetchone()[0]
            item = ArchiveSlicePlan(uuid4(), n, kind.value + ":" + codes[instrument_index], lo, hi, failed.capture.request_hash.value, "MARKET_BAR")
            slices.append(item)
            failures.append((item, gap, instrument_index, lo.date(), hi.date()))
        archive = _start(app, product.provider_product_id, code.artifact_id, config.artifact_id, slices,
            canonical_json_sha256({k: frozen[k] for k in ("securities", "price_inventory")} | {"limitation": frozen["universe"]}))
        for item, capture in zip(slices, (original_capture, captured.capture)):
            _observe(app, archive, item, capture)
        for item, gap, *_ in failures:
            app.market_archives.record_slice_gap(market_archive_id=archive, market_archive_slice_id=item.market_archive_slice_id,
                gap_id=gap, terminal_status="GAP_RECORDED", context=_context("gap-" + str(gap)))
        seal = app.market_archives.seal_retrospective(market_archive_id=archive, disposition=ArchiveSealDisposition.PARTIAL_WITH_GAPS,
            context=_context("inventory-seal"))
        result = PostgresHistoricalInventory(app._pool, LocalArtifactStore(settings.artifact_root)).inspect(archive, seal.market_archive_seal_id)
        assert len(result["calendar"]) == len(all_sessions) > 21
        assert {g["gap_id"] for g in result["source_gaps"]} == {g for _, g, *_ in failures}
        cells = {(c["instrument_id"], c["session_date"], c["price_basis"]): c for c in result["exclusions"]}
        for item, gap, instrument_index, lo, hi in failures:
            basis = "RAW_UNADJUSTED" if item.scope_key.startswith("HISTORY_DAILY_RAW:") else "BACKWARD_ADJUSTED"
            expected_days = {s.session_date for s in all_sessions if lo <= s.session_date <= hi}
            attributed = {key for key, cell in cells.items() if any(g["gap_id"] == gap for g in cell["gaps"])}
            assert attributed == {(instruments[instrument_index].value, day, basis) for day in expected_days}
        # Successful original bars remain visible alongside the failed raw request.
        raw = cells[(instruments[0].value, date(2026, 1, 5), "RAW_UNADJUSTED")]
        assert raw["state"] == "CONFLICT" and raw["bar_revision_ids"] and raw["gaps"]


@pytest.mark.parametrize("calendar_binding", ["FOREIGN_ONLY", "SHARED", "MISSING_FINAL", "MISSING_PARTITION_EMBARGO"])
def test_study_requires_selected_archive_calendar_before_declarations(target_database_url, tmp_path, monkeypatch, calendar_binding):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    raw = b"synthetic build; source-bound wheel checked separately"
    monkeypatch.setattr(study, "verify_historical_build", lambda **_: HistoricalBuild(raw, sha256(raw).hexdigest(), "1"*64, "2"*64, "3"*64, "0.1.0", "0.8.15"))
    with bootstrap_application(settings) as app:
        template, _ = daily_baseline(app, archive_exchange="XSHG")
        app.backtests.predeclare(template, _context("calendar-template"))
        with app._pool.connection(read_only=True) as c:
            product = c.execute("SELECT provider_product_id FROM mra.market_archive WHERE market_archive_id=%s", (template.market_archive.authority_id,)).fetchone()[0]
            rows = c.execute("SELECT session_date FROM mra.trading_session ORDER BY session_date").fetchall()
        capture = app.market.capture(CaptureRequest(product, "selected-calendar", "fixture://selected-calendar", "a"*64), _BytesProvider(), _context("selected-calendar"))
        dates = [r[0] for r in rows]
        included = [] if calendar_binding == "FOREIGN_ONLY" else (dates if calendar_binding == "SHARED" else dates[:4])
        if calendar_binding == "MISSING_PARTITION_EMBARGO":
            included = dates[:5]
        if included:
            app.market.normalize(capture.capture.capture_id, _Normalizer(lambda c: NormalizationBatch(c.capture_id, c.provider_product_id,
                trading_sessions=tuple(_session(day, c.capture_id, "XSHG") for day in included))), _context("selected-calendar-normalize"))
        else:
            app.market.normalize(capture.capture.capture_id, _Normalizer(lambda c: NormalizationBatch(c.capture_id, c.provider_product_id,
                instrument_identifiers=(InstrumentIdentifier(uuid4(), InstrumentId(template.sample_members[0].instrument_id),
                    "BOUNDARY_TEST", "source-only", datetime(2020, 1, 1, tzinfo=UTC), None, 1, None, c.capture_id),))),
                _context("selected-reference-normalize"))
        item = ArchiveSlicePlan(uuid4(), 1, "EXACT_CALENDAR", datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 20, tzinfo=UTC),
            capture.capture.request_hash.value, "TRADING_SESSION")
        archive = _start(app, product, template.code_artifact.artifact_id, template.config_artifact.artifact_id, (item,))
        _observe(app, archive, item, capture.capture)
        seal = app.market_archives.seal_retrospective(market_archive_id=archive, disposition=ArchiveSealDisposition.COMPLETE, context=_context("calendar-seal"))
        with app._pool.connection(read_only=True) as c:
            digest = c.execute("SELECT content_sha256 FROM mra.market_archive WHERE market_archive_id=%s", (archive,)).fetchone()[0]
        plan = HistoricalStudyPlan("calendar_boundary", template.exploratory_backtest_run_id, str(template.definition_sha256), archive, digest,
            seal.market_archive_seal_id, seal.content_sha256, (dates[0],), (dates[1],), (dates[2],), (dates[3],), (uuid4(),))
        if calendar_binding == "SHARED":
            result = read_study_dependencies(app._pool, plan)
            assert [r["session_date"] for r in result["sessions"]] == dates[:4]
            assert result["target_coverage"]["session_date"] == dates[4]
            return
        with app._pool.connection(read_only=True) as c:
            before = c.execute("SELECT (SELECT count(*) FROM mra.artifact),(SELECT count(*) FROM mra.exploratory_backtest_run)").fetchone()
        output = tmp_path / "refused-study"
        output.mkdir()
        with pytest.raises(ValueError, match="Calendar"):
            read_study_dependencies(app._pool, plan)
        with pytest.raises(ValueError, match="Calendar"):
            study.prepare_study(app, plan, wheel=Path("fixture.whl"), lockfile=Path("fixture.lock"), source_checkout=tmp_path,
                code_sha="a"*40, output=output, actor_id="fixture")
        assert not list(output.iterdir())
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT (SELECT count(*) FROM mra.artifact),(SELECT count(*) FROM mra.exploratory_backtest_run)").fetchone() == before
