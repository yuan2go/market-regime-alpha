"""Failed requests explain missingness, never event facts or numeric values."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from market_regime_alpha.infrastructure.historical_request_failure import historical_request_failure
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.interfaces.historical_feature_definitions import historical_feature_definitions
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.application._dataset_validation import validate_market_lineage
from market_regime_alpha.research_qualification.domain import ArtifactBinding, DatasetSourceRole, FeatureCellStatus, parse_decision_input_dataset_manifest
from market_regime_alpha.research_qualification.domain.backtest_dataset import BacktestDatasetFeatureCell, BacktestDatasetMember, BacktestFeatureDependency, BacktestFeatureLineageKind as Kind, materialize_backtest_dataset
from market_regime_alpha.research_qualification.ports.sources import DatasetMarketSourceObservation
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeStateConflictError


def _failure():
    start,end = datetime(2022,1,1,tzinfo=UTC),datetime(2022,1,31,23,59,59,999999,tzinfo=UTC)
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.HISTORY_DAILY_RAW,start.date(),end.date(),"sh.600000")
    product = uuid4()
    request = CaptureRequest(product,"exact-history:1",query.resource,canonical_json_sha256({"headers":"NONE","query":query.resource}))
    digest = canonical_json_sha256(request)
    args = dict(slice_id=uuid4(),slice_sha256="b"*64,scope_key="HISTORY_DAILY_RAW:sh.600000",window_start=start,window_end=end,
        product_id=product,capture_id=uuid4(),capture_key=request.capture_key,slice_request_sha256=digest,capture_request_sha256=digest,
        instrument_id=UUID(int=1),identifier="sh.600000")
    return historical_request_failure(**args),args


def _manifest(status=FeatureCellStatus.UNKNOWN):
    failure,_ = _failure()
    code,config = ArtifactBinding(uuid4(),"a"*64,1),ArtifactBinding(uuid4(),"b"*64,1)
    feature = next(f for f in historical_feature_definitions(uuid4(),code,config) if f.algorithm_code=="historical_intraday_v1")
    session,gap,bar = uuid4(),uuid4(),uuid4()
    dependencies = (BacktestFeatureDependency(Kind.TRADING_SESSION,session),BacktestFeatureDependency(Kind.SOURCE_GAP,gap))
    cell = BacktestDatasetFeatureCell(feature.feature_definition_id,status,"FEATURE_PROVIDER_UNKNOWN",
        Kind.BAR_REVISION if status is FeatureCellStatus.AVAILABLE else Kind.TRADING_SESSION,
        bar if status is FeatureCellStatus.AVAILABLE else session,Decimal(0) if status is FeatureCellStatus.AVAILABLE else None,dependencies)
    decision = datetime(2022,1,10,7,tzinfo=UTC)
    failure = replace(failure,closed_sessions=((session,decision),))
    materialized = materialize_backtest_dataset(dataset_id=uuid4(),dataset_code="failed_request_context",
        simulated_decision_time=decision,universe_revision_id=uuid4(),eligibility_policy_id=uuid4(),feature_definition_ids=(feature.feature_definition_id,),
        code_artifact=code,config_artifact=config,members=(BacktestDatasetMember(failure.instrument_id,uuid4(),uuid4(),(cell,)),))
    binding = ArtifactBinding(uuid4(),sha256_bytes(materialized.manifest_content),len(materialized.manifest_content))
    manifest = parse_decision_input_dataset_manifest(materialized.manifest_content,dataset=materialized.definition(binding),feature_definitions=(feature,))
    known = datetime(2026,9,12,tzinfo=UTC)
    observations = tuple(DatasetMarketSourceObservation(s.dataset_source_id,s.role,
        s.market_source_gap_id or s.market_trading_session_id or s.market_bar_revision_id,
        failure.instrument_id if s.role is DatasetSourceRole.MARKET_BAR_REVISION else None,known,True,
        None if s.role is DatasetSourceRole.MARKET_SOURCE_GAP else decision,
        failure if s.role is DatasetSourceRole.MARKET_SOURCE_GAP else None)
        for s in manifest.sources if s.role in {DatasetSourceRole.MARKET_SOURCE_GAP,DatasetSourceRole.MARKET_TRADING_SESSION,DatasetSourceRole.MARKET_BAR_REVISION})
    return manifest,feature,observations,known


def test_exact_capture_and_slice_request_hashes_are_both_required():
    failure,args = _failure()
    assert failure.price_basis=="RAW_UNADJUSTED"
    for changes in ({"identifier":"sh.600001"},{"capture_request_sha256":"f"*64},{"slice_request_sha256":"f"*64},{"scope_key":"HISTORY_DAILY_BACK_ADJUSTED:sh.600000"}):
        with pytest.raises(ArtifactIntegrityError,match="request"):
            historical_request_failure(**(args|changes))


def test_failure_context_preserves_unknown_and_real_knowledge_without_inventing_event_time():
    manifest,feature,observations,known = _manifest()
    validate_market_lineage(manifest,features=(feature,),observations=observations,knowledge_cutoff=known,simulated_event_cutoff=manifest.decision_time.value)
    failure = next(o for o in observations if o.request_failure is not None)
    assert failure.instrument_id is None and failure.event_cutoff_at is None and failure.decision_visible_at==known
    for context_change in ({"instrument_id":uuid4()},{"price_basis":"BACKWARD_ADJUSTED"},{"window_start":datetime(2023,1,1,tzinfo=UTC),"window_end":datetime(2023,2,1,tzinfo=UTC)}):
        altered = tuple(replace(o,request_failure=replace(o.request_failure,**context_change)) if o.request_failure else o for o in observations)
        with pytest.raises(RuntimeStateConflictError,match="exact unavailable"):
            validate_market_lineage(manifest,features=(feature,),observations=altered,knowledge_cutoff=known,simulated_event_cutoff=manifest.decision_time.value)
    late = tuple(replace(o,decision_visible_at=known+timedelta(seconds=1)) if o.request_failure else o for o in observations)
    with pytest.raises(RuntimeStateConflictError,match="knowledge cutoff"):
        validate_market_lineage(manifest,features=(feature,),observations=late,knowledge_cutoff=known,simulated_event_cutoff=manifest.decision_time.value)
    old_date = datetime(2022,1,3,7,tzinfo=UTC)
    old_calendar = tuple(replace(o,event_cutoff_at=old_date) if o.role is DatasetSourceRole.MARKET_TRADING_SESSION else
        replace(o,request_failure=replace(o.request_failure,window_start=old_date-timedelta(hours=1),window_end=old_date+timedelta(hours=1))) if o.request_failure else o
        for o in observations)
    with pytest.raises(RuntimeStateConflictError,match="exact unavailable"):
        validate_market_lineage(manifest,features=(feature,),observations=old_calendar,knowledge_cutoff=known,simulated_event_cutoff=manifest.decision_time.value)


def test_failure_context_cannot_support_available_feature():
    manifest,feature,observations,known = _manifest(FeatureCellStatus.AVAILABLE)
    with pytest.raises(RuntimeStateConflictError,match="exact unavailable"):
        validate_market_lineage(manifest,features=(feature,),observations=observations,knowledge_cutoff=known,simulated_event_cutoff=manifest.decision_time.value)
