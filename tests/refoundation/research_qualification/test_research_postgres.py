from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories import (
    PostgresAuditRepository,
)
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.research_uow import (
    PostgresResearchUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.target_uow import (
    PostgresTargetUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.selection_uow import (
    PostgresSelectionUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.research_qualification.application import (
    ResearchQualificationApplication,
)
from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    DatasetSourceRole,
    DecisionInputDatasetDefinition,
    FeatureAvailabilityRule,
    FeatureCellStatus,
    FeatureDefinition,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
)
from market_regime_alpha.market.application import MarketApplication
from market_regime_alpha.market.domain import (
    BarTimeframe,
    ClassificationMembershipRevision,
    ClassificationRevision,
    EvidenceScope,
    Instrument,
    InstrumentFactKind,
    InstrumentType,
    MarketBarRevision,
    MarketFactKind,
    MembershipStatus,
    NormalizationBatch,
    PriceBasis,
    Provider,
    ProviderKind,
    ProviderProduct,
    SecurityStatus,
    SecurityStatusFactRevision,
    SourceAvailabilityStatus,
    TradingSession,
)
from market_regime_alpha.market.ports import (
    CaptureRequest,
    NormalizerContract,
    ProviderResponse,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    RuntimeApplication,
)
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepSpec,
)
from market_regime_alpha.runtime.errors import (
    ArtifactByteStoreError,
    ArtifactIntegrityError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.selection.application import SelectionApplication
from market_regime_alpha.selection.domain import (
    CriterionOperator,
    CriterionValueKind,
    EligibilityPolicy,
    EligibilityRule,
    EligibilityRuleKind,
    UniverseDefinition,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.time import DecisionTime


UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _context(key: str, reason: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="research-definition-test",
        reason_code=reason,
    )


def _binding(artifact) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        size_bytes=artifact.size_bytes,
    )


class _BytesProvider:
    def capture(self, request: CaptureRequest) -> ProviderResponse:
        return ProviderResponse(
            content=b'{"research_definition":"canonical_market_fixture"}\n',
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code="HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
        )


class _Normalizer:
    contract = NormalizerContract(
        implementation="tests.research_definition_normalizer",
        version="1",
        implementation_sha256="7" * 64,
    )

    def __init__(self, factory) -> None:
        self._factory = factory

    def normalize(self, capture, content: bytes) -> NormalizationBatch:
        assert content
        return self._factory(capture)


@dataclass(frozen=True)
class _DatasetStack:
    research: ResearchQualificationApplication
    artifacts: ArtifactApplication
    store: LocalArtifactStore
    market: MarketApplication
    selection: SelectionApplication
    pool: TargetPostgresPool
    database_url: str
    product: ProviderProduct
    instrument_id: InstrumentId
    decision_time: DecisionTime
    universe_revision_id: UUID
    universe_member_id: UUID
    eligibility_policy_id: UUID
    eligibility_assessment_id: UUID
    market_capture_id: UUID
    market_fact_revision_id: UUID
    market_bar_revision_id: UUID
    market_session_id: UUID


@pytest.fixture
def dataset_stack(target_database_url: str, tmp_path, request) -> _DatasetStack:
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    request.addfinalizer(pool.close)
    store = LocalArtifactStore(tmp_path / "research-dataset-artifacts")
    runtime_uow = PostgresUnitOfWorkProvider(pool)
    artifacts = ArtifactApplication(store, runtime_uow)
    market = MarketApplication(
        store,
        PostgresMarketUnitOfWorkProvider(pool),
        PostgresMarketDatabaseClock(pool),
    )
    selection = SelectionApplication(PostgresSelectionUnitOfWorkProvider(pool))
    research = ResearchQualificationApplication(
        store,
        PostgresResearchUnitOfWorkProvider(pool),
        PostgresTargetUnitOfWorkProvider(pool),
    )
    provider = Provider(
        provider_id=uuid4(),
        provider_code="research_definition_fixture",
        display_name="Research Definition fixture",
        provider_kind=ProviderKind.PUBLIC_ENDPOINT,
    )
    product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="research_definition_facts",
        revision=1,
        payload_family="RESEARCH_DEFINITION_FACTS",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.UNKNOWN,
        fact_kinds=tuple(MarketFactKind),
        instrument_fact_kinds=tuple(InstrumentFactKind),
        bar_timeframes=tuple(BarTimeframe),
        price_bases=tuple(PriceBasis),
    )
    market.register_provider(
        provider,
        _context("dataset-provider", "REGISTER_PROVIDER"),
    )
    market.register_provider_product(
        product,
        _context("dataset-product", "REGISTER_PROVIDER_PRODUCT"),
    )
    captured = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="research-definition-source",
            resource="fixture://research-definition-source",
            request_headers_hash="6" * 64,
        ),
        _BytesProvider(),
        _context("dataset-capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    instrument_id = InstrumentId(uuid4())
    classification_id = uuid4()
    membership_revision_id = uuid4()
    fact_revision_id = uuid4()
    bar_revision_id = uuid4()
    session_id = uuid4()
    # Keep all synthetic session observations strictly in the past so this
    # reusable Authority fixture is deterministic across local clock rollovers.
    today = datetime.now(SHANGHAI).date() - timedelta(days=1)

    def instant(hour: int, minute: int) -> datetime:
        return datetime.combine(
            today,
            time(hour, minute),
            tzinfo=SHANGHAI,
        ).astimezone(UTC)

    session = TradingSession(
        session_id=session_id,
        exchange="XSHG",
        session_date=today,
        timezone_name="Asia/Shanghai",
        open_at=instant(9, 30),
        break_start_at=instant(11, 30),
        break_end_at=instant(13, 0),
        close_at=instant(15, 0),
        decision_reference_at=instant(14, 55),
        source_capture_id=captured.capture.capture_id,
    )

    def batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="600000.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(session,),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_id,
                    classification_scheme="INDEX",
                    classification_code="RESEARCH_SCOPE",
                    display_name="Research Scope",
                    revision=1,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    supersedes_classification_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=membership_revision_id,
                    classification_id=classification_id,
                    instrument_id=instrument_id,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.MEMBER,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_membership_revision_id=None,
                ),
            ),
            bars=(
                MarketBarRevision(
                    bar_revision_id=bar_revision_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session.session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=instant(14, 50),
                    event_end=instant(14, 55),
                    revision=1,
                    supersedes_revision_id=None,
                    open=Money(Decimal("10.00"), "CNY"),
                    high=Money(Decimal("10.20"), "CNY"),
                    low=Money(Decimal("9.90"), "CNY"),
                    close=Money(Decimal("10.10"), "CNY"),
                    volume=Quantity(Decimal("1000"), QuantityUnit.SHARES),
                    turnover=Money(Decimal("10100"), "CNY"),
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=fact_revision_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session.session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.ACTIVE,
                    event_start=session.open_at,
                    event_end=session.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    normalized = market.normalize(
        captured.capture.capture_id,
        _Normalizer(batch),
        _context("dataset-normalize", "NORMALIZE_MARKET_PIT"),
    )
    assert normalized.decision_visible_at.value >= instant(15, 0)
    historical_decision_time = DecisionTime(instant(15, 1))
    # The reusable integration fixture models a completed historical session.
    # PostgreSQL's production clock remains authoritative in application code;
    # only these freshly-created synthetic source rows are rebound before any
    # downstream Authority observes them. All temporal CHECKs remain enabled.
    with psycopg.connect(target_database_url) as connection:
        append_only_triggers = (
            ("data_capture", "data_capture_append_only"),
            ("instrument", "instrument_append_only"),
            ("trading_session", "trading_session_append_only"),
            ("classification", "classification_append_only"),
            (
                "classification_membership_revision",
                "classification_membership_revision_append_only",
            ),
            ("market_bar_revision", "market_bar_revision_append_only"),
            ("instrument_fact_revision", "instrument_fact_revision_append_only"),
        )
        for table_name, trigger_name in append_only_triggers:
            connection.execute(
                f"ALTER TABLE mra.{table_name} DISABLE TRIGGER {trigger_name}"
            )
        connection.execute(
            """
            UPDATE mra.data_capture
            SET capture_started_at = %s,
                capture_completed_at = %s,
                recorded_at = %s,
                known_at = %s,
                decision_visible_at = %s
            WHERE capture_id = %s
            """,
            (
                instant(14, 59),
                instant(15, 0),
                instant(15, 1),
                instant(15, 1),
                instant(15, 1),
                captured.capture.capture_id,
            ),
        )
        for table_name, capture_column in (
            ("instrument", "source_capture_id"),
            ("trading_session", "source_capture_id"),
            ("classification", "source_capture_id"),
            ("classification_membership_revision", "source_capture_id"),
            ("market_bar_revision", "capture_id"),
            ("instrument_fact_revision", "capture_id"),
        ):
            connection.execute(
                f"""
                UPDATE mra.{table_name}
                SET recorded_at = %s,
                    known_at = %s,
                    decision_visible_at = %s
                WHERE {capture_column} = %s
                """,
                (
                    historical_decision_time.value,
                    historical_decision_time.value,
                    historical_decision_time.value,
                    captured.capture.capture_id,
                ),
            )
        for table_name, trigger_name in append_only_triggers:
            connection.execute(
                f"ALTER TABLE mra.{table_name} ENABLE TRIGGER {trigger_name}"
            )
    scope_payload = {
        "classification_code": "RESEARCH_SCOPE",
        "classification_scheme": "INDEX",
        "instrument_ids": [str(instrument_id)],
        "market_provider_product_id": str(product.provider_product_id),
        "schema": "selection-universe-scope-v1",
    }
    scope_bytes = json.dumps(
        scope_payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    scope_artifact = artifacts.publish(
        scope_bytes,
        media_type="application/json",
        context=_context("dataset-scope-artifact", "REGISTER_UNIVERSE_SCOPE"),
    )
    scope = UniverseScopeSpecification(
        artifact_id=scope_artifact.artifact_id,
        content_sha256=scope_artifact.content_sha256,
        size_bytes=scope_artifact.size_bytes,
        market_provider_product_id=product.provider_product_id,
        classification_scheme="INDEX",
        classification_code="RESEARCH_SCOPE",
        instrument_ids=(instrument_id,),
    )
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="research-dataset-scope",
        purpose="Decision-input Dataset exact population",
    )
    rule = EligibilityRule(
        eligibility_rule_id=uuid4(),
        rule_code="NOT_SUSPENDED",
        ordinal=1,
        rule_kind=EligibilityRuleKind.NOT_SUSPENDED,
        measure_code="SECURITY_STATUS",
        aggregation="POINT",
        window_value=1,
        window_unit="SESSION",
        value_kind=CriterionValueKind.STATUS,
        operator=CriterionOperator.EQ,
        value_unit="STATUS",
        threshold_status="ACTIVE",
    )
    policy = EligibilityPolicy(
        eligibility_policy_id=uuid4(),
        market_provider_product_id=product.provider_product_id,
        policy_code="research-dataset-eligibility",
        version=1,
        rules=(rule,),
    )
    selection.register_universe(
        universe,
        _context("dataset-universe", "REGISTER_UNIVERSE"),
    )
    selection.register_eligibility_policy(
        policy,
        _context("dataset-policy", "REGISTER_ELIGIBILITY_POLICY"),
    )
    frozen = selection.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=historical_decision_time,
        context=_context("dataset-freeze", "FREEZE_UNIVERSE"),
    )
    assessed = selection.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=historical_decision_time,
        context=_context("dataset-assess", "ASSESS_ELIGIBILITY"),
    )
    assert frozen.included_count == 1
    assert assessed.eligible_count == 1
    return _DatasetStack(
        research=research,
        artifacts=artifacts,
        store=store,
        market=market,
        selection=selection,
        pool=pool,
        database_url=target_database_url,
        product=product,
        instrument_id=instrument_id,
        decision_time=historical_decision_time,
        universe_revision_id=frozen.universe_revision_id,
        universe_member_id=frozen.members[0].universe_member_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        eligibility_assessment_id=assessed.assessments[0].eligibility_assessment_id,
        market_capture_id=captured.capture.capture_id,
        market_fact_revision_id=fact_revision_id,
        market_bar_revision_id=bar_revision_id,
        market_session_id=session_id,
    )


@pytest.fixture
def research_stack(target_database_url: str, tmp_path, request):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    request.addfinalizer(pool.close)
    store = LocalArtifactStore(tmp_path / "research-definition-artifacts")
    artifacts = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    application = ResearchQualificationApplication(
        store,
        PostgresResearchUnitOfWorkProvider(pool),
        PostgresTargetUnitOfWorkProvider(pool),
    )
    return application, artifacts, store, pool, target_database_url


def _feature(artifacts: ArtifactApplication, *, key_prefix: str = "feature") -> FeatureDefinition:
    code = artifacts.publish(
        b"def mean_turnover(values): return sum(values) / len(values)\n",
        media_type="text/plain",
        context=_context(f"{key_prefix}-code", "REGISTER_FEATURE_CODE"),
    )
    config = artifacts.publish(
        b'{"window":20,"unit":"TRADING_SESSION"}\n',
        media_type="application/json",
        context=_context(f"{key_prefix}-config", "REGISTER_FEATURE_CONFIG"),
    )
    return FeatureDefinition(
        feature_definition_id=uuid4(),
        feature_code="mean_turnover_20s",
        version=1,
        value_type=FeatureValueType.DECIMAL,
        value_unit="CNY",
        frequency_value=1,
        frequency_unit=FeatureIntervalUnit.TRADING_SESSION,
        window_value=20,
        window_unit=FeatureIntervalUnit.TRADING_SESSION,
        lookback_value=20,
        lookback_unit=FeatureIntervalUnit.TRADING_SESSION,
        source_requirements=(
            FeatureSourceRequirement.MARKET_BAR_REVISION,
            FeatureSourceRequirement.TRADING_SESSION,
        ),
        availability_rule=FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE,
        missingness_policy=FeatureMissingnessPolicy.EXPLICIT_STATUS,
        algorithm_code="mean_turnover",
        algorithm_version="1",
        algorithm_sha256="9" * 64,
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )


def _dataset_feature(stack: _DatasetStack) -> FeatureDefinition:
    code = stack.artifacts.publish(
        b"def is_active(status): return status == 'ACTIVE'\n",
        media_type="text/plain",
        context=_context("dataset-feature-code", "REGISTER_FEATURE_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"fact_kind":"SECURITY_STATUS"}\n',
        media_type="application/json",
        context=_context("dataset-feature-config", "REGISTER_FEATURE_CONFIG"),
    )
    return FeatureDefinition(
        feature_definition_id=uuid4(),
        feature_code="is_active_at_decision",
        version=1,
        value_type=FeatureValueType.BOOLEAN,
        value_unit="BOOLEAN",
        frequency_value=1,
        frequency_unit=FeatureIntervalUnit.TRADING_SESSION,
        window_value=1,
        window_unit=FeatureIntervalUnit.TRADING_SESSION,
        lookback_value=0,
        lookback_unit=FeatureIntervalUnit.TRADING_SESSION,
        source_requirements=(
            FeatureSourceRequirement.INSTRUMENT_FACT_REVISION,
        ),
        availability_rule=FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE,
        missingness_policy=FeatureMissingnessPolicy.EXPLICIT_STATUS,
        algorithm_code="is_active",
        algorithm_version="1",
        algorithm_sha256="5" * 64,
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )


def _dataset_input(
    stack: _DatasetStack,
    feature: FeatureDefinition,
    *,
    key_prefix: str,
    status: FeatureCellStatus = FeatureCellStatus.AVAILABLE,
    include_expected_row: bool = True,
    extra_population: bool = False,
    market_source_role: DatasetSourceRole | None = None,
    market_source_identity: UUID | None = None,
    prohibited_manifest_field: str | None = None,
) -> tuple[DecisionInputDatasetDefinition, dict[str, object]]:
    code = stack.artifacts.publish(
        b"dataset-builder: decision-input-v1\n",
        media_type="text/plain",
        context=_context(f"{key_prefix}-code", "REGISTER_DATASET_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"population":"INCLUDED_AND_ELIGIBLE"}\n',
        media_type="application/json",
        context=_context(f"{key_prefix}-config", "REGISTER_DATASET_CONFIG"),
    )
    dataset_id = uuid4()
    population_source_id = uuid4()
    feature_source_id = uuid4()
    market_source_id = uuid4()
    if market_source_role is None:
        market_source_role = (
            DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION
            if status is FeatureCellStatus.AVAILABLE
            else DatasetSourceRole.MARKET_CAPTURE
        )
    if market_source_identity is None:
        market_source_identity = (
            stack.market_fact_revision_id
            if market_source_role
            is DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION
            else stack.market_capture_id
        )
    source_identity_field = {
        DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION: (
            "market_instrument_fact_revision_id"
        ),
        DatasetSourceRole.MARKET_CAPTURE: "market_capture_id",
    }[market_source_role]
    sources: list[dict[str, str]] = [
        {
            "dataset_source_id": str(feature_source_id),
            "role": DatasetSourceRole.FEATURE_DEFINITION.value,
            "feature_definition_id": str(feature.feature_definition_id),
        }
    ]
    rows: list[dict[str, object]] = []
    if include_expected_row or extra_population:
        instrument_id = (
            stack.instrument_id.value if include_expected_row else uuid4()
        )
        sources.extend(
            (
                {
                    "dataset_source_id": str(population_source_id),
                    "role": DatasetSourceRole.POPULATION.value,
                    "instrument_id": str(instrument_id),
                    "universe_member_id": str(
                        stack.universe_member_id if include_expected_row else uuid4()
                    ),
                    "eligibility_assessment_id": str(
                        stack.eligibility_assessment_id
                        if include_expected_row
                        else uuid4()
                    ),
                },
                {
                    "dataset_source_id": str(market_source_id),
                    "role": market_source_role.value,
                    source_identity_field: str(market_source_identity),
                },
            )
        )
        rows.append(
            {
                "instrument_id": str(instrument_id),
                "population_source_id": str(population_source_id),
                "cells": [
                    {
                        "feature_definition_id": str(
                            feature.feature_definition_id
                        ),
                        "status": status.value,
                        "value": (
                            True
                            if status is FeatureCellStatus.AVAILABLE
                            else None
                        ),
                        "reason_code": (
                            "OBSERVED"
                            if status is FeatureCellStatus.AVAILABLE
                            else "SOURCE_MISSING"
                        ),
                        "source_ids": sorted(
                            (str(feature_source_id), str(market_source_id))
                        ),
                    }
                ],
            }
        )
    sources.sort(key=lambda item: item["dataset_source_id"])
    rows.sort(key=lambda item: str(item["instrument_id"]))
    payload: dict[str, object] = {
        "schema": "mra-decision-input-dataset-v1",
        "dataset_id": str(dataset_id),
        "dataset_code": key_prefix,
        "dataset_version": 1,
        "decision_time": stack.decision_time.value.isoformat(),
        "universe_revision_id": str(stack.universe_revision_id),
        "eligibility_policy_id": str(stack.eligibility_policy_id),
        "feature_definition_ids": [str(feature.feature_definition_id)],
        "code_artifact": {
            "artifact_id": str(code.artifact_id),
            "content_sha256": code.content_sha256,
            "size_bytes": code.size_bytes,
        },
        "config_artifact": {
            "artifact_id": str(config.artifact_id),
            "content_sha256": config.content_sha256,
            "size_bytes": config.size_bytes,
        },
        "sources": sources,
        "rows": rows,
    }
    if prohibited_manifest_field is not None:
        payload[prohibited_manifest_field] = "physically-prohibited"
    manifest_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    manifest = stack.artifacts.publish(
        manifest_bytes,
        media_type="application/json",
        context=_context(f"{key_prefix}-manifest", "REGISTER_DATASET_MANIFEST"),
    )
    definition = DecisionInputDatasetDefinition(
        dataset_id=dataset_id,
        dataset_code=key_prefix,
        version=1,
        decision_time=stack.decision_time,
        universe_revision_id=stack.universe_revision_id,
        eligibility_policy_id=stack.eligibility_policy_id,
        feature_definition_ids=(feature.feature_definition_id,),
        manifest_artifact=_binding(manifest),
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    return definition, payload


def _claim_research_runtime_step(
    stack: _DatasetStack,
    *,
    config_artifact: ArtifactBinding,
) -> tuple[RuntimeApplication, AttemptClaim]:
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(stack.pool))
    schedule = ScheduleSpec(
        schedule_id=uuid4(),
        schedule_code="research-definition-command",
        revision=1,
        runtime_mode=RuntimeMode.OPERATIONAL,
        schedule_expression=None,
        timezone_name="Asia/Shanghai",
        step_catalog_hash="d" * 64,
        enabled=True,
    )
    runtime.create_schedule(
        schedule,
        _context("research-runtime-schedule", "CREATE_RUNTIME_SCHEDULE"),
    )
    step = StepSpec(
        step_key="register-research-definition",
        step_kind="ASSESS_RESEARCH",
        implementation="research_qualification.definition-command",
        implementation_version="1",
        ordinal=1,
        required=True,
        request_hash="e" * 64,
        input_evidence_hash=None,
        retry_policy=RetryPolicy(
            max_attempts=1,
            backoff=(),
            retryable_codes=frozenset(),
        ),
        external_effect_class=ExternalEffectClass.PURE_READ,
    )
    run_id = uuid4()
    runtime.schedule_run(
        RunSpec(
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            fire_key="research-definition-command-run",
            runtime_mode=RuntimeMode.OPERATIONAL,
            requested_at=datetime.now(UTC),
            decision_time=stack.decision_time.value,
            code_sha="2" * 40,
            config_artifact_id=config_artifact.artifact_id,
            config_hash=str(config_artifact.content_sha256),
        ),
        (step,),
        (),
        _context("research-runtime-plan", "SCHEDULE_RUNTIME_RUN"),
    )
    runtime.start_run(
        run_id,
        _context("research-runtime-start", "START_RUNTIME_RUN"),
    )
    claim = runtime.claim_next(
        worker_id="research-definition-worker",
        lease_duration=timedelta(seconds=60),
        context=_context("research-runtime-claim", "WORKER_CLAIM"),
    )
    assert claim is not None
    runtime.start_attempt(
        claim,
        _context("research-runtime-attempt", "WORKER_START"),
    )
    return runtime, claim


def test_feature_definition_registration_is_immutable_idempotent_and_audited(
    research_stack,
) -> None:
    application, artifacts, _, _, database_url = research_stack
    feature = _feature(artifacts)

    first = application.register_feature_definition(
        feature,
        _context("register-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    replay = application.register_feature_definition(
        feature,
        _context("register-feature", "REGISTER_FEATURE_DEFINITION"),
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.result_hash == first.result_hash
    assert replay.aggregate_id == str(feature.feature_definition_id)
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT definition.feature_code, definition.version,
                   definition.value_type, definition.value_unit,
                   definition.source_requirements,
                   definition.availability_rule,
                   definition.missingness_policy,
                   definition.content_sha256,
                   receipt.status, audit.action
            FROM mra.feature_definition AS definition
            JOIN mra.command_receipt AS receipt
              ON receipt.result_aggregate_id = definition.feature_definition_id::text
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            WHERE definition.feature_definition_id = %s
            """,
            (feature.feature_definition_id,),
        ).fetchone()
    assert row == (
        "mean_turnover_20s",
        1,
        "DECIMAL",
        "CNY",
        ["MARKET_BAR_REVISION", "TRADING_SESSION"],
        "DECISION_VISIBLE_AT_OR_BEFORE",
        "EXPLICIT_STATUS",
        str(feature.content_sha256),
        "SUCCEEDED",
        "REGISTER_FEATURE_DEFINITION",
    )


def test_feature_identity_conflict_rolls_back_and_records_deterministic_failure(
    research_stack,
) -> None:
    application, artifacts, _, _, database_url = research_stack
    feature = _feature(artifacts)
    application.register_feature_definition(
        feature,
        _context("feature-original", "REGISTER_FEATURE_DEFINITION"),
    )
    conflict = replace(
        feature,
        feature_definition_id=uuid4(),
        algorithm_sha256="8" * 64,
    )

    with pytest.raises(RuntimeStateConflictError):
        application.register_feature_definition(
            conflict,
            _context("feature-conflict", "REGISTER_FEATURE_DEFINITION"),
        )

    with psycopg.connect(database_url) as connection:
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.feature_definition),
                receipt.status, receipt.error_code,
                audit.action, audit.reason_code
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            WHERE receipt.idempotency_key = 'feature-conflict'
            """
        ).fetchone()
    assert facts == (
        1,
        "FAILED",
        "REGISTER_FEATURE_DEFINITION_REJECTED",
        "RESEARCH_COMMAND_FAILED",
        "REGISTER_FEATURE_DEFINITION_REJECTED",
    )


def test_feature_artifact_binding_fails_closed_without_definition_write(
    research_stack,
) -> None:
    application, artifacts, _, _, database_url = research_stack
    feature = _feature(artifacts)
    invalid = replace(
        feature,
        code_artifact=ArtifactBinding(
            artifact_id=feature.code_artifact.artifact_id,
            content_sha256="0" * 64,
            size_bytes=feature.code_artifact.size_bytes,
        ),
    )

    with pytest.raises(ArtifactIntegrityError):
        application.register_feature_definition(
            invalid,
            _context("feature-bad-artifact", "REGISTER_FEATURE_DEFINITION"),
        )

    with psycopg.connect(database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.feature_definition),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'feature-bad-artifact'
                   AND status = 'FAILED')
            """
        ).fetchone()
    assert counts == (0, 1)


def test_dataset_population_lineage_and_missing_cells_reconcile_exactly(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("dataset-register-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-missing",
        status=FeatureCellStatus.MISSING,
    )

    result = stack.research.register_dataset(
        definition,
        _context("register-dataset-missing", "REGISTER_DATASET"),
    )
    replay = stack.research.register_dataset(
        definition,
        _context("register-dataset-missing", "REGISTER_DATASET"),
    )

    assert result.replayed is False
    assert replay.replayed is True
    assert result.row_count == 1
    assert result.feature_count == 1
    assert result.cell_count == 1
    assert result.missing_cell_count == 1
    assert result.available_cell_count == 0
    with psycopg.connect(stack.database_url) as connection:
        root = connection.execute(
            """
            SELECT dataset_kind, decision_time, universe_revision_id,
                   eligibility_policy_id, row_count, feature_count,
                   source_count, cell_count, available_cell_count,
                   missing_cell_count
            FROM mra.dataset
            WHERE dataset_id = %s
            """,
            (definition.dataset_id,),
        ).fetchone()
        sources = connection.execute(
            """
            SELECT source_role, instrument_id, universe_member_id,
                   eligibility_assessment_id, feature_definition_id,
                   market_capture_id, membership_status, eligibility_result
            FROM mra.dataset_source
            WHERE dataset_id = %s
            ORDER BY source_role, dataset_source_id
            """,
            (definition.dataset_id,),
        ).fetchall()
        verification = connection.execute(
            """
            SELECT verification_policy, result
            FROM mra.artifact_verification
            WHERE artifact_id = %s
            ORDER BY verified_at DESC, verification_id DESC
            LIMIT 1
            """,
            (definition.manifest_artifact.artifact_id,),
        ).fetchone()
    assert root == (
        "DECISION_INPUT",
        stack.decision_time.value,
        stack.universe_revision_id,
        stack.eligibility_policy_id,
        1,
        1,
        3,
        1,
        0,
        1,
    )
    assert {row[0] for row in sources} == {
        "POPULATION",
        "FEATURE_DEFINITION",
        "MARKET_CAPTURE",
    }
    population = next(row for row in sources if row[0] == "POPULATION")
    assert population == (
        "POPULATION",
        stack.instrument_id.value,
        stack.universe_member_id,
        stack.eligibility_assessment_id,
        None,
        None,
        "INCLUDED",
        "ELIGIBLE",
    )
    assert verification == ("RESEARCH_DATASET_MANIFEST_READ", "VERIFIED")


@pytest.mark.parametrize("extra_population", (False, True))
def test_dataset_population_must_equal_included_and_eligible_intersection(
    dataset_stack: _DatasetStack,
    extra_population: bool,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("population-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix=("candidate-input-extra" if extra_population else "candidate-input-omitted"),
        include_expected_row=False,
        extra_population=extra_population,
    )

    with pytest.raises(RuntimeStateConflictError, match="population"):
        stack.research.register_dataset(
            definition,
            _context("population-mismatch", "REGISTER_DATASET"),
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.dataset),
                (SELECT count(*) FROM mra.dataset_source),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'population-mismatch'
                   AND status = 'FAILED')
            """
        ).fetchone()
    assert counts == (0, 0, 1)


def test_dataset_accepts_exact_empty_included_and_eligible_population(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    empty_scope_bytes = json.dumps(
        {
            "classification_code": "ABSENT_RESEARCH_SCOPE",
            "classification_scheme": "INDEX",
            "instrument_ids": [str(stack.instrument_id)],
            "market_provider_product_id": str(
                stack.product.provider_product_id
            ),
            "schema": "selection-universe-scope-v1",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    empty_scope_artifact = stack.artifacts.publish(
        empty_scope_bytes,
        media_type="application/json",
        context=_context("empty-scope-artifact", "REGISTER_UNIVERSE_SCOPE"),
    )
    empty_scope = UniverseScopeSpecification(
        artifact_id=empty_scope_artifact.artifact_id,
        content_sha256=empty_scope_artifact.content_sha256,
        size_bytes=empty_scope_artifact.size_bytes,
        market_provider_product_id=stack.product.provider_product_id,
        classification_scheme="INDEX",
        classification_code="ABSENT_RESEARCH_SCOPE",
        instrument_ids=(stack.instrument_id,),
    )
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="research-empty-dataset-scope",
        purpose="prove exact empty Decision-input population",
    )
    stack.selection.register_universe(
        universe,
        _context("empty-universe", "REGISTER_UNIVERSE"),
    )
    frozen = stack.selection.freeze_universe(
        universe_id=universe.universe_id,
        scope=empty_scope,
        decision_time=stack.decision_time,
        context=_context("empty-freeze", "FREEZE_UNIVERSE"),
    )
    assessed = stack.selection.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=stack.eligibility_policy_id,
        decision_time=stack.decision_time,
        context=_context("empty-assess", "ASSESS_ELIGIBILITY"),
    )
    assert frozen.included_count == 0
    assert assessed.eligible_count == 1
    empty_stack = replace(
        stack,
        universe_revision_id=frozen.universe_revision_id,
        universe_member_id=frozen.members[0].universe_member_id,
        eligibility_assessment_id=assessed.assessments[0].eligibility_assessment_id,
    )
    feature = _dataset_feature(empty_stack)
    stack.research.register_feature_definition(
        feature,
        _context("empty-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        empty_stack,
        feature,
        key_prefix="candidate-input-empty",
        include_expected_row=False,
    )

    result = stack.research.register_dataset(
        definition,
        _context("empty-dataset", "REGISTER_DATASET"),
    )

    assert (
        result.row_count,
        result.feature_count,
        result.source_count,
        result.cell_count,
    ) == (0, 1, 1, 0)
    with psycopg.connect(stack.database_url) as connection:
        roles = connection.execute(
            """
            SELECT source_role
            FROM mra.dataset_source
            WHERE dataset_id = %s
            """,
            (definition.dataset_id,),
        ).fetchall()
    assert roles == [("FEATURE_DEFINITION",)]


def test_dataset_available_cell_binds_exact_market_fact_and_decision_time(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("available-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-available",
    )

    result = stack.research.register_dataset(
        definition,
        _context("available-dataset", "REGISTER_DATASET"),
    )

    assert result.available_cell_count == 1
    assert result.missing_cell_count == 0
    with psycopg.connect(stack.database_url) as connection:
        source = connection.execute(
            """
            SELECT dataset_source.source_role,
                   dataset_source.market_instrument_fact_revision_id,
                   fact.instrument_id, fact.decision_visible_at,
                   dataset.decision_time
            FROM mra.dataset_source AS dataset_source
            JOIN mra.dataset AS dataset
              ON dataset.dataset_id = dataset_source.dataset_id
            JOIN mra.instrument_fact_revision AS fact
              ON fact.fact_revision_id =
                 dataset_source.market_instrument_fact_revision_id
            WHERE dataset_source.dataset_id = %s
              AND dataset_source.source_role =
                  'MARKET_INSTRUMENT_FACT_REVISION'
            """,
            (definition.dataset_id,),
        ).fetchone()
    assert source == (
        "MARKET_INSTRUMENT_FACT_REVISION",
        stack.market_fact_revision_id,
        stack.instrument_id.value,
        stack.decision_time.value,
        stack.decision_time.value,
    )


def test_dataset_rejects_market_lineage_not_visible_at_decision_time(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    with psycopg.connect(stack.database_url) as connection:
        session_times = connection.execute(
            """
            SELECT open_at, close_at
            FROM mra.trading_session
            WHERE session_id = %s
            """,
            (stack.market_session_id,),
        ).fetchone()
    assert session_times is not None
    later_capture = stack.market.capture(
        CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key="research-definition-later-source",
            resource="fixture://research-definition-later-source",
            request_headers_hash="4" * 64,
        ),
        _BytesProvider(),
        _context("later-capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    later_fact_id = uuid4()

    def later_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=later_fact_id,
                    provider_product_id=stack.product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=stack.instrument_id,
                    session_id=stack.market_session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.ACTIVE,
                    event_start=session_times[0],
                    event_end=session_times[1],
                    revision=2,
                    supersedes_revision_id=stack.market_fact_revision_id,
                ),
            ),
        )

    normalized = stack.market.normalize(
        later_capture.capture.capture_id,
        _Normalizer(later_batch),
        _context("later-normalize", "NORMALIZE_MARKET_PIT"),
    )
    assert normalized.decision_visible_at.value > stack.decision_time.value
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("pit-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-future-lineage",
        market_source_identity=later_fact_id,
    )

    with pytest.raises(RuntimeStateConflictError, match="DecisionTime"):
        stack.research.register_dataset(
            definition,
            _context("future-lineage-dataset", "REGISTER_DATASET"),
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.dataset),
                (SELECT count(*) FROM mra.dataset_source),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'future-lineage-dataset'
                   AND status = 'FAILED')
            """
        ).fetchone()
    assert counts == (0, 0, 1)


def test_dataset_parser_rejects_label_leakage_before_any_authority_write(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("leakage-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-leakage",
        prohibited_manifest_field="forward_return",
    )

    with pytest.raises(ValueError, match="label leakage"):
        stack.research.register_dataset(
            definition,
            _context("leakage-dataset", "REGISTER_DATASET"),
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.dataset),
                (SELECT count(*) FROM mra.dataset_source),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'leakage-dataset'
                   AND status = 'FAILED')
            """
        ).fetchone()
    assert counts == (0, 0, 1)


@pytest.mark.parametrize("failure_mode", ("missing", "corrupt"))
def test_dataset_manifest_artifact_failure_fails_closed_and_is_replayable(
    dataset_stack: _DatasetStack,
    failure_mode: str,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("artifact-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix=f"candidate-input-{failure_mode}",
    )
    object_path = stack.store.object_path(
        str(definition.manifest_artifact.content_sha256)
    )
    if failure_mode == "missing":
        object_path.unlink()
    else:
        object_path.write_bytes(b"x" * definition.manifest_artifact.size_bytes)

    command_context = _context(
        f"dataset-artifact-{failure_mode}",
        "REGISTER_DATASET",
    )
    with pytest.raises(ArtifactIntegrityError, match="manifest bytes"):
        stack.research.register_dataset(definition, command_context)
    with pytest.raises(CommandPreviouslyFailedError):
        stack.research.register_dataset(definition, command_context)

    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.dataset),
                (SELECT count(*) FROM mra.dataset_source),
                receipt.status, receipt.error_code,
                (SELECT count(*) FROM mra.audit_event AS audit
                 WHERE audit.command_receipt_id = receipt.receipt_id),
                artifact.integrity_state,
                verification.result,
                receipt.receipt_id,
                verification.command_receipt_id
            FROM mra.command_receipt AS receipt
            JOIN mra.artifact_verification AS verification
              ON verification.command_receipt_id = receipt.receipt_id
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = verification.artifact_id
            WHERE receipt.idempotency_key = %s
            """,
            (command_context.idempotency_key,),
        ).fetchone()
    expected_state = "MISSING" if failure_mode == "missing" else "CORRUPT"
    expected_result = "MISSING" if failure_mode == "missing" else "HASH_MISMATCH"
    assert facts[:-2] == (
        0,
        0,
        "FAILED",
        "REGISTER_DATASET_REJECTED",
        1,
        expected_state,
        expected_result,
    )
    assert facts[-2] == facts[-1]


def test_dataset_manifest_read_race_records_integrity_failure_atomically(
    dataset_stack: _DatasetStack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("read-race-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-read-race",
    )

    def fail_read(*_args, **_kwargs):
        raise ArtifactByteStoreError("injected verified-read race")

    monkeypatch.setattr(stack.store, "read_bytes", fail_read)
    with pytest.raises(ArtifactIntegrityError, match="changed during read"):
        stack.research.register_dataset(
            definition,
            _context("read-race-dataset", "REGISTER_DATASET"),
        )

    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT artifact.integrity_state, verification.result,
                   receipt.status, receipt.error_code,
                   (SELECT count(*) FROM mra.dataset)
            FROM mra.command_receipt AS receipt
            JOIN mra.artifact_verification AS verification
              ON verification.command_receipt_id = receipt.receipt_id
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = verification.artifact_id
            WHERE receipt.idempotency_key = 'read-race-dataset'
            """
        ).fetchone()
    assert facts == (
        "CORRUPT",
        "INTEGRITY_ERROR",
        "FAILED",
        "REGISTER_DATASET_REJECTED",
        0,
    )


def test_dataset_identity_conflict_rolls_back_new_lineage(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("identity-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    original, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-identity",
    )
    stack.research.register_dataset(
        original,
        _context("dataset-identity-first", "REGISTER_DATASET"),
    )
    conflicting, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-identity",
        status=FeatureCellStatus.MISSING,
    )

    with pytest.raises(RuntimeStateConflictError):
        stack.research.register_dataset(
            conflicting,
            _context("dataset-identity-conflict", "REGISTER_DATASET"),
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.dataset),
                (SELECT count(*) FROM mra.dataset_source),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'dataset-identity-conflict'
                   AND status = 'FAILED')
            """
        ).fetchone()
    assert counts == (1, 3, 1)


def test_dataset_source_roles_real_fks_uniqueness_and_append_only_are_enforced(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("constraint-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-constraints",
    )
    stack.research.register_dataset(
        definition,
        _context("constraint-dataset", "REGISTER_DATASET"),
    )

    with psycopg.connect(stack.database_url, autocommit=True) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO mra.dataset_source (
                    dataset_source_id, dataset_id, source_role,
                    feature_definition_id, market_capture_id
                )
                VALUES (%s, %s, 'MARKET_CAPTURE', %s, %s)
                """,
                (
                    uuid4(),
                    definition.dataset_id,
                    feature.feature_definition_id,
                    stack.market_capture_id,
                ),
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                """
                INSERT INTO mra.dataset_source (
                    dataset_source_id, dataset_id, source_role,
                    market_capture_id
                )
                VALUES (%s, %s, 'MARKET_CAPTURE', %s)
                """,
                (uuid4(), definition.dataset_id, uuid4()),
            )
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO mra.dataset_source (
                    dataset_source_id, dataset_id, source_role,
                    market_instrument_fact_revision_id
                )
                VALUES (%s, %s, 'MARKET_INSTRUMENT_FACT_REVISION', %s)
                """,
                (uuid4(), definition.dataset_id, stack.market_fact_revision_id),
            )
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                UPDATE mra.dataset
                SET dataset_code = 'mutated-dataset'
                WHERE dataset_id = %s
                """,
                (definition.dataset_id,),
            )
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                DELETE FROM mra.feature_definition
                WHERE feature_definition_id = %s
                """,
                (feature.feature_definition_id,),
            )


def test_research_bound_artifacts_are_protected_from_foundation_gc(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("gc-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-gc",
    )
    stack.research.register_dataset(
        definition,
        _context("gc-dataset", "REGISTER_DATASET"),
    )

    scan = stack.artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="research-artifact-scanner",
    )

    bound_hashes = {
        str(feature.code_artifact.content_sha256),
        str(feature.config_artifact.content_sha256),
        str(definition.manifest_artifact.content_sha256),
        str(definition.code_artifact.content_sha256),
        str(definition.config_artifact.content_sha256),
    }
    assert bound_hashes <= set(scan.protected)
    assert not bound_hashes & set(scan.observed)
    assert not bound_hashes & set(scan.quarantined)


def _index_names(node: dict) -> set[str]:
    names = {str(node["Index Name"])} if "Index Name" in node else set()
    for child in node.get("Plans", ()):
        names.update(_index_names(child))
    return names


def test_dataset_population_and_lineage_queries_have_bounded_index_plans(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("plan-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-plan",
    )
    stack.research.register_dataset(
        definition,
        _context("plan-dataset", "REGISTER_DATASET"),
    )

    with psycopg.connect(stack.database_url) as connection:
        connection.execute("SET LOCAL enable_seqscan = off")
        plans = (
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT instrument_id
                FROM mra.universe_member
                WHERE universe_revision_id = %s
                  AND membership_status = 'INCLUDED'
                ORDER BY instrument_id
                """,
                (stack.universe_revision_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT eligibility_assessment_id, instrument_id
                FROM mra.eligibility_assessment
                WHERE universe_revision_id = %s
                  AND eligibility_policy_id = %s
                  AND result = 'ELIGIBLE'
                ORDER BY instrument_id
                """,
                (
                    stack.universe_revision_id,
                    stack.eligibility_policy_id,
                ),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT dataset_source_id
                FROM mra.dataset_source
                WHERE dataset_id = %s AND source_role = 'POPULATION'
                ORDER BY dataset_source_id
                """,
                (definition.dataset_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT dataset_id
                FROM mra.dataset
                WHERE universe_revision_id = %s
                  AND eligibility_policy_id = %s
                  AND decision_time = %s
                """,
                (
                    stack.universe_revision_id,
                    stack.eligibility_policy_id,
                    stack.decision_time.value,
                ),
            ).fetchone()[0][0]["Plan"],
        )
    names = set().union(*(_index_names(plan) for plan in plans))
    assert {
        "universe_member_status_idx",
        "eligibility_assessment_result_idx",
        "dataset_source_dataset_role_idx",
    } <= names, names
    assert names & {
        "dataset_decision_scope_idx",
        "dataset_universe_decision_idx",
        "dataset_eligibility_policy_idx",
    }, names


def test_feature_idempotency_key_conflict_does_not_create_parallel_identity(
    research_stack,
) -> None:
    application, artifacts, _, _, database_url = research_stack
    feature = _feature(artifacts)
    context = _context("feature-idempotency", "REGISTER_FEATURE_DEFINITION")
    application.register_feature_definition(feature, context)
    conflict = replace(
        feature,
        feature_definition_id=uuid4(),
        algorithm_sha256="8" * 64,
    )

    with pytest.raises(IdempotencyKeyReusedError):
        application.register_feature_definition(conflict, context)

    with psycopg.connect(database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.feature_definition),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'feature-idempotency')
            """
        ).fetchone()
    assert counts == (1, 1)


def test_concurrent_exact_dataset_registration_commits_one_authority(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    stack.research.register_feature_definition(
        feature,
        _context("concurrent-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    definition, _ = _dataset_input(
        stack,
        feature,
        key_prefix="candidate-input-concurrent",
    )
    context = _context("concurrent-dataset", "REGISTER_DATASET")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(stack.research.register_dataset, definition, context)
            for _ in range(2)
        )
        results = tuple(future.result(timeout=10) for future in futures)

    assert sorted(item.replayed for item in results) == [False, True]
    assert len({item.result_hash for item in results}) == 1
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.dataset),
                (SELECT count(*) FROM mra.dataset_source),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'concurrent-dataset')
            """
        ).fetchone()
    assert counts == (1, 3, 1)


def test_research_success_atomically_terminalizes_runtime_claim(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    runtime, claim = _claim_research_runtime_step(
        stack,
        config_artifact=feature.config_artifact,
    )

    result = stack.research.register_feature_definition(
        feature,
        _context("runtime-feature-success", "REGISTER_FEATURE_DEFINITION"),
        runtime_claim=claim,
    )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "SUCCEEDED"
    assert trace.steps[0].state == "SUCCEEDED"
    assert trace.steps[0].attempt_states == ("SUCCEEDED",)
    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT receipt.status, audit.action, attempt.state,
                   attempt.result_receipt_id
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            WHERE receipt.receipt_id = %s
            """,
            (result.receipt_id,),
        ).fetchone()
    assert facts == (
        "SUCCEEDED",
        "REGISTER_FEATURE_DEFINITION",
        "SUCCEEDED",
        result.receipt_id,
    )


def test_research_deterministic_failure_atomically_terminalizes_runtime_claim(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    runtime, claim = _claim_research_runtime_step(
        stack,
        config_artifact=feature.config_artifact,
    )
    invalid = replace(
        feature,
        code_artifact=ArtifactBinding(
            artifact_id=feature.code_artifact.artifact_id,
            content_sha256="0" * 64,
            size_bytes=feature.code_artifact.size_bytes,
        ),
    )

    with pytest.raises(ArtifactIntegrityError):
        stack.research.register_feature_definition(
            invalid,
            _context("runtime-feature-failure", "REGISTER_FEATURE_DEFINITION"),
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT receipt.status, receipt.error_code,
                   audit.action, audit.reason_code,
                   attempt.state, attempt.error_class, attempt.error_code,
                   (SELECT count(*) FROM mra.feature_definition)
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            WHERE receipt.idempotency_key = 'runtime-feature-failure'
            """
        ).fetchone()
    assert facts == (
        "FAILED",
        "REGISTER_FEATURE_DEFINITION_REJECTED",
        "RESEARCH_COMMAND_FAILED",
        "REGISTER_FEATURE_DEFINITION_REJECTED",
        "FAILED_TERMINAL",
        "COMMAND",
        "REGISTER_FEATURE_DEFINITION_REJECTED",
        0,
    )


def test_research_idempotency_conflict_preserves_original_and_fails_attempt(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    original_context = _context(
        "runtime-idempotency-conflict",
        "REGISTER_FEATURE_DEFINITION",
    )
    original = stack.research.register_feature_definition(
        feature,
        original_context,
    )
    runtime, claim = _claim_research_runtime_step(
        stack,
        config_artifact=feature.config_artifact,
    )
    conflict = replace(
        feature,
        feature_definition_id=uuid4(),
        algorithm_sha256="8" * 64,
    )

    with pytest.raises(IdempotencyKeyReusedError):
        stack.research.register_feature_definition(
            conflict,
            original_context,
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT
                (SELECT status FROM mra.command_receipt
                 WHERE receipt_id = %s),
                rejection.status, rejection.error_code,
                audit.action, attempt.state,
                (SELECT count(*) FROM mra.feature_definition)
            FROM mra.command_receipt AS rejection
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = rejection.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = rejection.receipt_id
            WHERE rejection.command_kind = 'RESEARCH_COMMAND_REJECTION'
              AND rejection.runtime_attempt_id = %s
            """,
            (original.receipt_id, claim.attempt_id),
        ).fetchone()
    assert facts == (
        "SUCCEEDED",
        "FAILED",
        "IDEMPOTENCY_KEY_REUSED",
        "RESEARCH_COMMAND_REJECTED",
        "FAILED_TERMINAL",
        1,
    )


def test_research_stale_fence_rejects_before_receipt_or_audit(
    dataset_stack: _DatasetStack,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    runtime, claim = _claim_research_runtime_step(
        stack,
        config_artifact=feature.config_artifact,
    )
    stale = replace(claim, fence_token=claim.fence_token + 1)

    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        stack.research.register_feature_definition(
            feature,
            _context("stale-feature", "REGISTER_FEATURE_DEFINITION"),
            runtime_claim=stale,
        )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "RUNNING"
    assert trace.steps[0].state == "RUNNING"
    assert trace.steps[0].attempt_states == ("RUNNING",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.feature_definition),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'stale-feature'),
                (SELECT count(*) FROM mra.audit_event
                 WHERE aggregate_id LIKE 'REGISTER_FEATURE_DEFINITION:%')
            """
        ).fetchone()
    assert counts == (0, 0, 0)


def test_research_failure_receipt_audit_and_attempt_roll_back_together(
    dataset_stack: _DatasetStack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = dataset_stack
    feature = _dataset_feature(stack)
    runtime, claim = _claim_research_runtime_step(
        stack,
        config_artifact=feature.config_artifact,
    )
    invalid = replace(
        feature,
        code_artifact=ArtifactBinding(
            artifact_id=feature.code_artifact.artifact_id,
            content_sha256="0" * 64,
            size_bytes=feature.code_artifact.size_bytes,
        ),
    )

    def fail_audit(*_args, **_kwargs) -> None:
        raise RuntimeError("injected Research failure-audit error")

    monkeypatch.setattr(PostgresAuditRepository, "append", fail_audit)
    with pytest.raises(RuntimeError, match="injected Research failure-audit error"):
        stack.research.register_feature_definition(
            invalid,
            _context("rollback-feature", "REGISTER_FEATURE_DEFINITION"),
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "RUNNING"
    assert trace.steps[0].state == "RUNNING"
    assert trace.steps[0].attempt_states == ("RUNNING",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.feature_definition),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'rollback-feature'),
                (SELECT count(*) FROM mra.audit_event
                 WHERE aggregate_id LIKE 'REGISTER_FEATURE_DEFINITION:%')
            """
        ).fetchone()
    assert counts == (0, 0, 0)
