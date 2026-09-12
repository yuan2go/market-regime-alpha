"""Freeze bounded historical requests through existing Market/Archive owners."""

from dataclasses import asdict
from datetime import UTC, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind as K
from market_regime_alpha.interfaces.historical_study import _exact, _json
from market_regime_alpha.interfaces.historical_study_build import verify_historical_build
from market_regime_alpha.market.application import ArchiveManifestSlice, ArchiveOperatorManifest, ArchiveSlicePlan, StartMarketArchiveRequest
from market_regime_alpha.market.domain import ArchiveLane, BarTimeframe, InstrumentFactKind, MarketFactKind, PriceBasis, ProviderProduct, SourceAvailabilityStatus
from market_regime_alpha.market.domain.archive import ArchiveSupplementalPriceBasis
from market_regime_alpha.market.domain.historical_acquisition import HistoricalAcquisitionPlan
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


def prepare_historical_archive(app, plan: HistoricalAcquisitionPlan, *, wheel: Path, lockfile: Path,
                               source_checkout: Path, code_sha: str, output: Path, actor_id: str) -> dict:
    if not output.is_dir():
        raise ValueError("archive output must be an existing persistent directory")
    build = verify_historical_build(wheel=wheel, lockfile=lockfile, source_checkout=source_checkout, code_sha=code_sha)
    source = app.historical_acquisition_sources.validate(plan)
    identities = source["securities"]
    frozen = {"schema": "mra-historical-acquisition-freeze-v1", "plan": asdict(plan), "code_sha": code_sha,
        "wheel_sha256": build.wheel_sha256, "lockfile_sha256": build.lockfile_sha256,
        "securities": identities, "provider_id": source["provider_id"], "request_count": 1 + 3 * len(plan.codes),
        "price_inventory": {"target": "RAW_UNADJUSTED", "cross_day_features": "BACKWARD_ADJUSTED"},
        "price_adjustment": "BAOSTOCK_PERCENT_CHANGE_ADJUSTMENT_NOT_DISTRIBUTION_REINVESTMENT",
        "universe": "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED", "pit": "NOT_ESTABLISHED",
        "source_availability_and_finality": "UNKNOWN", "known_at": "ACTUAL_CAPTURE_COMPLETION",
        "request_timeout_seconds": 30, "maximum_transport_attempts": 2,
        "minimum_interval_seconds": .25, "maximum_invocation_seconds": 7200}
    content = _json(frozen)
    _exact(output / "frozen-acquisition.json", content)
    namespace = uuid5(NAMESPACE_URL, "mra:historical-acquisition:" + plan.archive_code)
    def uid(name):
        return uuid5(namespace, name)
    def context(name):
        return CommandContext(plan.archive_code + ":" + name, ActorType.OPERATOR, actor_id, "HISTORICAL_ACQUISITION")
    code = app.artifacts.publish(build.content, media_type="application/zip", context=context("code"))
    config = app.artifacts.publish(content, media_type="application/json", context=context("config"))
    product = ProviderProduct(uid("product"), source["provider_id"], plan.archive_code + "_daily", 1,
        "BAOSTOCK_HISTORICAL_DAILY", "application/json", "UTF-8", SourceAvailabilityStatus.UNKNOWN,
        (MarketFactKind.INSTRUMENT, MarketFactKind.INSTRUMENT_IDENTIFIER, MarketFactKind.TRADING_SESSION,
         MarketFactKind.MARKET_BAR, MarketFactKind.INSTRUMENT_FACT),
        (InstrumentFactKind.LISTING_STATUS, InstrumentFactKind.SECURITY_STATUS, InstrumentFactKind.SPECIAL_TREATMENT_STATUS),
        (BarTimeframe.DAILY,), (PriceBasis.RAW_UNADJUSTED, PriceBasis.BACKWARD_ADJUSTED))
    app.market.register_provider_product(product, context("product"))
    queries: tuple[BaoStockArchiveQuery, ...] = (BaoStockArchiveQuery(K.TRADE_DATES, plan.start_date, plan.end_date),)
    queries += tuple(BaoStockArchiveQuery(K.STOCK_BASIC, code=security) for security in plan.codes)
    queries += tuple(BaoStockArchiveQuery(kind, plan.start_date, plan.end_date, security)
                     for security in plan.codes for kind in (K.HISTORY_DAILY_RAW, K.HISTORY_DAILY_BACK_ADJUSTED))
    start = datetime.combine(plan.start_date, time(), UTC)
    end = datetime.combine(plan.end_date + timedelta(days=1), time(), UTC) - timedelta(microseconds=1)
    slices = []
    for ordinal, query in enumerate(queries, 1):
        request = CaptureRequest(product.provider_product_id, plan.archive_code + ":" + str(ordinal),
            query.resource, ContentHash(canonical_json_sha256({"headers": "NONE", "query": query.resource})))
        fact = "TRADING_SESSION" if query.kind is K.TRADE_DATES else "INSTRUMENT" if query.kind is K.STOCK_BASIC else "MARKET_BAR"
        item = ArchiveSlicePlan(uid("slice:" + str(ordinal)), ordinal, query.kind.value + ":" + (query.code or "CALENDAR"),
            start, end, canonical_json_sha256(request), fact)
        slices.append(ArchiveManifestSlice(item, request, "HISTORICAL_CAPTURE"))
    scope = "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED:" + plan.archive_code
    roster_sha256 = canonical_json_sha256({"securities": identities, "price_inventory": frozen["price_inventory"], "limitation": frozen["universe"]})
    manifest = ArchiveOperatorManifest(StartMarketArchiveRequest(uid("archive"), plan.archive_code,
        ArchiveLane.RETROSPECTIVE_BACKFILL, product.provider_product_id, "XSHG", BarTimeframe.DAILY,
        ArchiveSupplementalPriceBasis.MIXED_EXPLICIT, scope, roster_sha256, start, end,
        plan.reserved_free_bytes, plan.maximum_archive_bytes, plan.maximum_slice_bytes,
        code.artifact_id, config.artifact_id, sha256(content).hexdigest(), tuple(item.plan for item in slices)), tuple(slices))
    _exact(output / "archive-manifest.json", manifest.to_bytes())
    result = app.market_archives.start(manifest.start_request, context("start"))
    return {"archive_id": result.market_archive_id, "archive_sha256": result.content_sha256,
            "request_count": len(slices), "state": "PREDECLARED_NOT_ACQUIRED", "manifest_sha256": sha256(manifest.to_bytes()).hexdigest()}
