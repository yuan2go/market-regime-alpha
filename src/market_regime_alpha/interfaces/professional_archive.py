"""Freeze existing recorded inputs through the original Archive commands.

No downloads, normalization runner or alternate inventory are introduced. The
scope declares RAW-only coverage and retains actual Capture knowledge times.
"""

from dataclasses import asdict
from hashlib import sha256
import re
import shutil
from uuid import NAMESPACE_URL, uuid5

from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.queries.professional_normalization import PostgresProfessionalNormalizationReferences
from market_regime_alpha.infrastructure.postgres.queries.professional_recording import replay_recorded_capture
from market_regime_alpha.infrastructure.postgres.repositories.market import PostgresMarketRepository
from market_regime_alpha.infrastructure.providers.recorded_professional_normalizer import RecordedProfessionalDailyNormalizer
from market_regime_alpha.interfaces import historical_study
from market_regime_alpha.market.application import ArchiveSlicePlan, RecordArchiveCaptureObservationRequest, StartMarketArchiveRequest
from market_regime_alpha.market.domain import ArchiveLane, BarTimeframe, CaptureStatus, PriceBasis
from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract
from market_regime_alpha.market.domain.professional_normalization import verify_recorded_archive_scope
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256


def prepare_recorded_archive(app, settings, arguments) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}",arguments.archive_code) or not arguments.output.is_dir():
        raise ValueError("recorded Archive needs a bounded code and existing persistent output directory")
    reference_ids = tuple(sorted(arguments.reference_capture_id,key=str))
    if not 1 <= len(reference_ids) <= 8 or len(set(reference_ids)) != len(reference_ids) or arguments.recording_capture_id in reference_ids:
        raise ValueError("recorded Archive requires one to eight distinct original reference Captures")
    budgets = (arguments.reserved_free_bytes,arguments.maximum_slice_bytes,arguments.maximum_archive_bytes)
    if any(type(v) is not int for v in budgets) or budgets[0] < 0 or not 1 <= budgets[1] <= budgets[2]:
        raise ValueError("recorded Archive byte budgets are invalid")
    build=historical_study.verify_historical_build(wheel=arguments.wheel,lockfile=arguments.lockfile,
        source_checkout=arguments.source_checkout,code_sha=arguments.code_sha)
    store=LocalArtifactStore(settings.artifact_root)
    recorded=replay_recorded_capture(app._pool,store,arguments.recording_capture_id)
    if "normalization_evidence" not in recorded["verification"]:
        raise ValueError("recorded Archive requires the evidenced v3 daily mapping")
    contract=ProfessionalDailyContract(**recorded["contract"])
    identities=(*reference_ids,arguments.recording_capture_id)
    with app._pool.connection(read_only=True) as connection:
        sources=tuple(PostgresMarketRepository(connection).capture_source(identity) for identity in identities)
        normalized=connection.execute("""SELECT 1 FROM mra.command_receipt WHERE command_kind='NORMALIZE_MARKET_PIT'
            AND scope_id=%s AND request_hash=%s AND status='SUCCEEDED' AND result_aggregate_kind='MARKET_NORMALIZATION'
            AND result_aggregate_id=%s LIMIT 1""",(str(arguments.recording_capture_id),canonical_json_sha256({
                "capture_id":arguments.recording_capture_id,"normalizer_contract":RecordedProfessionalDailyNormalizer.contract}),
                str(arguments.recording_capture_id))).fetchone()
        selected_sessions={r[0] for r in connection.execute("""SELECT DISTINCT binding.session_id
            FROM mra.market_capture_trading_session_normalization binding
            JOIN mra.market_capture_reference_normalization normalized USING(capture_id)
            WHERE binding.capture_id=ANY(%s) AND normalized.recorded_at<=%s""",(list(reference_ids),sources[-1].capture.temporal.known_at.value)).fetchall()}
        selected_instruments={r[0] for r in connection.execute("""SELECT DISTINCT binding.instrument_id
            FROM mra.market_capture_instrument_normalization binding
            JOIN mra.market_capture_reference_normalization normalized USING(capture_id)
            WHERE binding.capture_id=ANY(%s) AND normalized.recorded_at<=%s""",(list(reference_ids),sources[-1].capture.temporal.known_at.value)).fetchall()}
    if normalized is None:
        raise ArtifactIntegrityError("recorded Archive lacks its exact successful Market normalizer receipt")
    references=PostgresProfessionalNormalizationReferences(app._pool,store).references(contract,sources[-1].capture)
    if (not {r.instrument_id.value for r in references}.issubset(selected_instruments)
            or not {s.session_id.value for r in references for s in r.sessions}.issubset(selected_sessions)):
        raise ArtifactIntegrityError("selected reference Captures do not cover the recording's exact Calendar and instruments")
    for source in sources:
        if (source.capture.status is not CaptureStatus.CAPTURED or source.capture.provider_product_id!=recorded["provider_product_id"]
                or source.artifact is None or source.artifact.integrity_state!="AVAILABLE"
                or source.artifact.size_bytes>arguments.maximum_slice_bytes
                or source.capture.temporal.known_at.value>sources[-1].capture.temporal.known_at.value):
            raise ArtifactIntegrityError("recorded Archive Capture identity, knowledge, integrity or size differs")
        store.read_bytes(str(source.artifact.content_sha256),expected_size=source.artifact.size_bytes)
    if (sum(s.artifact.size_bytes for s in sources if s.artifact is not None)>arguments.maximum_archive_bytes
            or shutil.disk_usage(settings.artifact_root).free<arguments.reserved_free_bytes+arguments.maximum_slice_bytes):
        raise ValueError("recorded Archive exceeds the explicit storage budget")
    securities=tuple((r.stock_code,str(r.instrument_id.value)) for r in references)
    scope={"schema":"mra-recorded-archive-scope-v1","securities":securities,
        "price_inventory":{"target":"RAW_UNADJUSTED","cross_day_features":"NOT_SUPPORTED"},
        "universe":"STATIC_UNIVERSE/SURVIVORSHIP_LIMITED","source_contract":asdict(contract),
        "recording_capture_id":arguments.recording_capture_id,"reference_capture_ids":reference_ids,
        "captures":tuple({"capture_id":s.capture.capture_id,"request_sha256":str(s.capture.request_hash),
            "known_at":s.capture.temporal.known_at.value,"artifact_sha256":str(s.artifact.content_sha256),
            "artifact_size_bytes":s.artifact.size_bytes} for s in sources if s.artifact is not None),
        "code_sha":arguments.code_sha,"wheel_sha256":build.wheel_sha256,"lockfile_sha256":build.lockfile_sha256,
        "budgets":{"reserved_free_bytes":budgets[0],"maximum_slice_bytes":budgets[1],"maximum_archive_bytes":budgets[2]},
        "qualification":"RECORDED_SOURCE_NOT_PIT_OR_PROVIDER_QUALIFICATION"}
    content=historical_study._json(scope)
    verify_recorded_archive_scope(content)
    historical_study._exact(arguments.output/'recorded-archive-scope.json',content)
    def context(step):
        return CommandContext(arguments.archive_code+':'+step,ActorType.OPERATOR,arguments.actor_id,'RECORDED_ARCHIVE')
    code=app.artifacts.publish(build.content,media_type='application/zip',context=context('code'))
    config=app.artifacts.publish(content,media_type='application/json',context=context('config'))
    archive_id=uuid5(NAMESPACE_URL,'mra:recorded-archive:'+arguments.archive_code)
    sessions=tuple(s for r in references for s in r.sessions)
    start,end=min(s.open_at for s in sessions),max(s.close_at for s in sessions)
    slices=tuple(ArchiveSlicePlan(uuid5(archive_id,str(s.capture.capture_id)),ordinal,'recorded:'+str(s.capture.capture_id),
        start,end,str(s.capture.request_hash),'MARKET_BAR') for ordinal,s in enumerate(sources,1))
    primary_exchange='XSHG' if any(s.exchange=='XSHG' for s in sessions) else 'XSHE'
    request=StartMarketArchiveRequest(archive_id,arguments.archive_code,ArchiveLane.RETROSPECTIVE_BACKFILL,
        recorded['provider_product_id'],primary_exchange,BarTimeframe.DAILY,PriceBasis.RAW_UNADJUSTED,
        'STATIC_RECORDED_RAW_SCOPE',canonical_json_sha256({'securities':securities,'price_inventory':scope['price_inventory'],
            'limitation':scope['universe']}),start,end,budgets[0],budgets[2],budgets[1],code.artifact_id,config.artifact_id,sha256(content).hexdigest(),slices)
    started=app.market_archives.start(request,context('start'))
    observed=tuple(app.market_archives.record_capture_observation(RecordArchiveCaptureObservationRequest(archive_id,
        slice_.market_archive_slice_id,source.capture.capture_id,'LOCAL_RECORDED_INPUT',source.capture.temporal.capture_started_at),
        context('observe:'+str(source.capture.capture_id))) for slice_,source in zip(slices,sources,strict=True))
    return {'archive_id':archive_id,'archive_sha256':started.content_sha256,'scope_sha256':sha256(content).hexdigest(),
        'observations':observed,'state':'CAPTURES_ARCHIVED_SEAL_AND_QUALITY_REQUIRED','price_basis':'RAW_UNADJUSTED',
        'professional_provider_validation':'NOT_RUN','source_gap_semantics':'NORMALIZED_QUALITY_GAPS_ARE_DISTINCT_FROM_REQUEST_FAILURES'}
