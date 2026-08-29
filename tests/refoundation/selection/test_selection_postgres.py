from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.selection_uow import (
    PostgresSelectionUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import MarketApplication
from market_regime_alpha.market.domain import (
    BarTimeframe,
    ClassificationMembershipRevision,
    ClassificationRevision,
    EvidenceScope,
    Instrument,
    InstrumentFactKind,
    InstrumentFactRevision,
    InstrumentLifecycleFactRevision,
    InstrumentType,
    ListingStatus,
    MarketBarRevision,
    MarketFactKind,
    MembershipStatus,
    NormalizationBatch,
    NumericInstrumentFactKind,
    PriceBasis,
    Provider,
    ProviderKind,
    ProviderProduct,
    SecurityStatus,
    SecurityStatusFactRevision,
    SourceAvailabilityStatus,
    SpecialTreatmentStatus,
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
    StepDependency,
    StepSpec,
)
from market_regime_alpha.runtime.errors import StaleFenceError
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.selection.application import SelectionApplication
from market_regime_alpha.selection.domain import (
    CriterionOperator,
    CriterionResult,
    CriterionValueKind,
    EligibilityPolicy,
    EligibilityRule,
    EligibilityRuleKind,
    EligibilityStatus,
    UniverseDefinition,
    UniverseMembershipStatus,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime


UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _context(key: str, reason: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="selection-core-test",
        reason_code=reason,
    )


def _money(value: str) -> Money:
    return Money(Decimal(value), "CNY")


def _shares(value: str) -> Quantity:
    return Quantity(Decimal(value), QuantityUnit.SHARES)


class _BytesProvider:
    def capture(self, request: CaptureRequest) -> ProviderResponse:
        return ProviderResponse(
            content=b'{"selection":"canonical-market-fixture"}\n',
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code="HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
        )


class _Normalizer:
    contract = NormalizerContract(
        implementation="tests.selection_core_normalizer",
        version="1",
        implementation_sha256="7" * 64,
    )

    def __init__(self, factory) -> None:
        self._factory = factory

    def normalize(self, capture, content: bytes) -> NormalizationBatch:
        assert content
        return self._factory(capture)


def _session(session_date: date, capture_id: UUID) -> TradingSession:
    def instant(hour: int, minute: int) -> datetime:
        return datetime.combine(
            session_date,
            time(hour, minute),
            tzinfo=SHANGHAI,
        ).astimezone(UTC)

    return TradingSession(
        session_id=uuid4(),
        exchange="XSHG",
        session_date=session_date,
        timezone_name="Asia/Shanghai",
        open_at=instant(9, 30),
        break_start_at=instant(11, 30),
        break_end_at=instant(13, 0),
        close_at=instant(15, 0),
        decision_reference_at=instant(14, 55),
        source_capture_id=capture_id,
    )


def _bar(
    *,
    product_id: UUID,
    capture_id: UUID,
    instrument_id: InstrumentId,
    session: TradingSession,
    turnover: str,
) -> MarketBarRevision:
    return MarketBarRevision(
        bar_revision_id=uuid4(),
        provider_product_id=product_id,
        capture_id=capture_id,
        instrument_id=instrument_id,
        session_id=session.session_id,
        timeframe=BarTimeframe.DAILY,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=session.open_at,
        event_end=session.close_at,
        revision=1,
        supersedes_revision_id=None,
        open=_money("10"),
        high=_money("11"),
        low=_money("9"),
        close=_money("10.5"),
        volume=_shares("1000"),
        turnover=_money(turnover),
    )


def _limit_facts(
    *,
    product_id: UUID,
    capture_id: UUID,
    instrument_id: InstrumentId,
    session: TradingSession,
) -> tuple[InstrumentFactRevision, ...]:
    values = (
        (NumericInstrumentFactKind.LIMIT_UP_PRICE, "11"),
        (NumericInstrumentFactKind.LIMIT_DOWN_PRICE, "9"),
        (NumericInstrumentFactKind.REFERENCE_PRICE, "10"),
    )
    return tuple(
        InstrumentFactRevision(
            fact_revision_id=uuid4(),
            provider_product_id=product_id,
            capture_id=capture_id,
            instrument_id=instrument_id,
            session_id=session.session_id,
            fact_kind=kind,
            evidence_scope=EvidenceScope.DECISION_SESSION,
            event_start=session.open_at,
            event_end=session.close_at,
            value=_money(value),
            revision=1,
            supersedes_revision_id=None,
        )
        for kind, value in values
    )


@dataclass(frozen=True)
class _SelectionStack:
    application: SelectionApplication
    artifacts: ArtifactApplication
    market: MarketApplication
    pool: TargetPostgresPool
    product: ProviderProduct
    instrument_ids: tuple[InstrumentId, ...]
    classification_id: UUID
    first_membership_id: UUID
    decision_time: DecisionTime
    database_url: str


@pytest.fixture
def selection_stack(target_database_url: str, tmp_path) -> _SelectionStack:
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    store = LocalArtifactStore(tmp_path / "selection-artifacts")
    runtime_uow = PostgresUnitOfWorkProvider(pool)
    artifacts = ArtifactApplication(store, runtime_uow)
    market = MarketApplication(
        store,
        PostgresMarketUnitOfWorkProvider(pool),
        PostgresMarketDatabaseClock(pool),
    )
    selection = SelectionApplication(PostgresSelectionUnitOfWorkProvider(pool))
    provider = Provider(
        provider_id=uuid4(),
        provider_code="selection_fixture",
        display_name="Selection fixture",
        provider_kind=ProviderKind.PUBLIC_ENDPOINT,
    )
    product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="selection_canonical_facts",
        revision=1,
        payload_family="SELECTION_CANONICAL_FACTS",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.UNKNOWN,
        fact_kinds=tuple(MarketFactKind),
        instrument_fact_kinds=tuple(InstrumentFactKind),
        bar_timeframes=tuple(BarTimeframe),
        price_bases=tuple(PriceBasis),
    )
    market.register_provider(provider, _context("provider", "REGISTER_PROVIDER"))
    market.register_provider_product(
        product,
        _context("product", "REGISTER_PROVIDER_PRODUCT"),
    )
    captured = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="selection-core-fixture",
            resource="fixture://selection-core",
            request_headers_hash="8" * 64,
        ),
        _BytesProvider(),
        _context("capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    instrument_ids = tuple(sorted((InstrumentId(uuid4()), InstrumentId(uuid4()), InstrumentId(uuid4())), key=str))
    today = datetime.now(SHANGHAI).date()
    classification_id = uuid4()
    first_membership_id = uuid4()

    def batch(capture) -> NormalizationBatch:
        current = _session(today, capture.capture_id)
        history = (
            _session(today - timedelta(days=1), capture.capture_id),
            _session(today - timedelta(days=2), capture.capture_id),
        )
        first, second, third = instrument_ids
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=tuple(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code=f"{600000 + index}.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                )
                for index, instrument_id in enumerate(instrument_ids)
            ),
            trading_sessions=(*history, current),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_id,
                    classification_scheme="INDEX",
                    classification_code="SELECTION_SCOPE",
                    display_name="Selection Scope",
                    revision=1,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    supersedes_classification_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=first_membership_id,
                    classification_id=classification_id,
                    instrument_id=first,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.MEMBER,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_membership_revision_id=None,
                ),
                ClassificationMembershipRevision(
                    membership_revision_id=uuid4(),
                    classification_id=classification_id,
                    instrument_id=second,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.NOT_MEMBER,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_membership_revision_id=None,
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=first,
                    session_id=current.session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.ACTIVE,
                    event_start=current.open_at,
                    event_end=current.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=second,
                    session_id=current.session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.SUSPENDED,
                    event_start=current.open_at,
                    event_end=current.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            lifecycle_status_facts=(
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=first,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.LISTED,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=first,
                    fact_kind=InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
                    status=SpecialTreatmentStatus.NORMAL,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=second,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.LISTED,
                    effective_from=datetime(2026, 8, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=second,
                    fact_kind=InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
                    status=SpecialTreatmentStatus.ST,
                    effective_from=datetime(2026, 8, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            instrument_facts=(
                *_limit_facts(
                    product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=first,
                    session=current,
                ),
                *_limit_facts(
                    product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=second,
                    session=current,
                ),
            ),
            bars=tuple(
                _bar(
                    product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session=session,
                    turnover=turnover,
                )
                for instrument_id, turnover in ((first, "3000"), (second, "1000"))
                for session in history
            ),
        )

    normalized = market.normalize(
        captured.capture.capture_id,
        _Normalizer(batch),
        _context("normalize", "NORMALIZE_MARKET_PIT"),
    )
    try:
        yield _SelectionStack(
            application=selection,
            artifacts=artifacts,
            market=market,
            pool=pool,
            product=product,
            instrument_ids=instrument_ids,
            classification_id=classification_id,
            first_membership_id=first_membership_id,
            decision_time=normalized.decision_visible_at,
            database_url=target_database_url,
        )
    finally:
        pool.close()


def _scope(stack: _SelectionStack) -> UniverseScopeSpecification:
    payload = {
        "classification_code": "SELECTION_SCOPE",
        "classification_scheme": "INDEX",
        "instrument_ids": [str(item) for item in stack.instrument_ids],
        "market_provider_product_id": str(stack.product.provider_product_id),
        "schema": "selection-universe-scope-v1",
    }
    content = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    artifact = stack.artifacts.publish(
        content,
        media_type="application/json",
        context=_context("scope-artifact", "REGISTER_UNIVERSE_SCOPE"),
        pin_reason_code="UNIVERSE_SCOPE",
    )
    return UniverseScopeSpecification(
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        size_bytes=artifact.size_bytes,
        market_provider_product_id=stack.product.provider_product_id,
        classification_scheme="INDEX",
        classification_code="SELECTION_SCOPE",
        instrument_ids=stack.instrument_ids,
    )


def _policy(product_id: UUID) -> EligibilityPolicy:
    shapes = (
        (
            EligibilityRuleKind.NOT_SUSPENDED,
            "NOT_SUSPENDED",
            "SECURITY_STATUS",
            "POINT",
            1,
            "SESSION",
            CriterionValueKind.STATUS,
            CriterionOperator.EQ,
            "STATUS",
            None,
            "ACTIVE",
            None,
        ),
        (
            EligibilityRuleKind.NOT_SPECIAL_TREATMENT,
            "NOT_SPECIAL_TREATMENT",
            "SPECIAL_TREATMENT_STATUS",
            "POINT",
            0,
            "NONE",
            CriterionValueKind.STATUS,
            CriterionOperator.EQ,
            "STATUS",
            None,
            "NORMAL",
            None,
        ),
        (
            EligibilityRuleKind.MIN_LISTING_AGE,
            "MIN_LISTING_AGE",
            "LISTING_AGE",
            "ELAPSED",
            0,
            "NONE",
            CriterionValueKind.DECIMAL,
            CriterionOperator.GTE,
            "CALENDAR_DAYS",
            Decimal("365"),
            None,
            None,
        ),
        (
            EligibilityRuleKind.MIN_LIQUIDITY,
            "MIN_LIQUIDITY",
            "TURNOVER_VALUE",
            "MEAN",
            2,
            "SESSION",
            CriterionValueKind.DECIMAL,
            CriterionOperator.GTE,
            "CNY",
            Decimal("2000"),
            None,
            None,
        ),
        (
            EligibilityRuleKind.LIMIT_METADATA_PRESENT,
            "LIMIT_METADATA_PRESENT",
            "LIMIT_PRICE_FACT_COUNT",
            "COUNT",
            1,
            "SESSION",
            CriterionValueKind.COUNT,
            CriterionOperator.GTE,
            "FACT_COUNT",
            None,
            None,
            3,
        ),
    )
    rules = tuple(
        EligibilityRule(
            eligibility_rule_id=uuid4(),
            rule_code=shape[1],
            ordinal=ordinal,
            rule_kind=shape[0],
            measure_code=shape[2],
            aggregation=shape[3],
            window_value=shape[4],
            window_unit=shape[5],
            value_kind=shape[6],
            operator=shape[7],
            value_unit=shape[8],
            threshold_decimal=shape[9],
            threshold_status=shape[10],
            threshold_count=shape[11],
        )
        for ordinal, shape in enumerate(shapes, start=1)
    )
    return EligibilityPolicy(
        eligibility_policy_id=uuid4(),
        market_provider_product_id=product_id,
        policy_code="selection-core-v1",
        version=1,
        rules=rules,
    )


def test_freeze_and_assess_cover_complete_scope_all_rules_and_exact_lineage(
    selection_stack: _SelectionStack,
) -> None:
    stack = selection_stack
    scope = _scope(stack)
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="selection-core",
        purpose="explicit research scope only",
    )
    policy = _policy(stack.product.provider_product_id)
    stack.application.register_universe(
        universe,
        _context("register-universe", "REGISTER_UNIVERSE"),
    )
    stack.application.register_eligibility_policy(
        policy,
        _context("register-policy", "REGISTER_ELIGIBILITY_POLICY"),
    )
    frozen = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=stack.decision_time,
        context=_context("freeze", "FREEZE_UNIVERSE"),
    )
    replayed_frozen = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=stack.decision_time,
        context=_context("freeze", "FREEZE_UNIVERSE"),
    )
    assert (
        frozen.total_count,
        frozen.included_count,
        frozen.excluded_count,
        frozen.unknown_count,
    ) == (3, 1, 1, 1)
    assert tuple(item.membership_status for item in frozen.members) == (
        UniverseMembershipStatus.INCLUDED,
        UniverseMembershipStatus.EXCLUDED,
        UniverseMembershipStatus.UNKNOWN,
    )
    assert replayed_frozen.replayed is True
    assert replayed_frozen.result_hash == frozen.result_hash

    batch = stack.application.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=stack.decision_time,
        context=_context("assess", "ASSESS_ELIGIBILITY"),
    )
    replayed_batch = stack.application.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=stack.decision_time,
        context=_context("assess", "ASSESS_ELIGIBILITY"),
    )
    assert (
        batch.total_count,
        batch.eligible_count,
        batch.ineligible_count,
        batch.unknown_count,
    ) == (3, 1, 1, 1)
    assert tuple(item.result for item in batch.assessments) == (
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.INELIGIBLE,
        EligibilityStatus.UNKNOWN,
    )
    assert all(len(item.reasons) == len(policy.rules) for item in batch.assessments)
    assert all(reason.criterion_result is CriterionResult.PASS for reason in batch.assessments[0].reasons)
    assert any(reason.criterion_result is CriterionResult.FAIL for reason in batch.assessments[1].reasons)
    assert all(reason.criterion_result is CriterionResult.UNKNOWN for reason in batch.assessments[2].reasons)
    assert replayed_batch.replayed is True
    assert replayed_batch.result_hash == batch.result_hash

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.universe_revision),
                (SELECT count(*) FROM mra.universe_member),
                (SELECT count(*) FROM mra.eligibility_assessment),
                (SELECT count(*) FROM mra.eligibility_reason),
                (SELECT count(*) FROM mra.eligibility_reason
                 WHERE cardinality(market_fact_revision_ids) > 0),
                (SELECT count(*) FROM mra.eligibility_reason
                 WHERE cardinality(market_bar_revision_ids) > 0)
            """
        ).fetchone()
    assert counts == (1, 3, 3, 15, 8, 2)


def test_empty_explicit_scope_is_valid_and_never_expands_to_current_instruments(
    selection_stack: _SelectionStack,
) -> None:
    stack = selection_stack
    empty_payload = {
        "classification_code": "SELECTION_SCOPE",
        "classification_scheme": "INDEX",
        "instrument_ids": [],
        "market_provider_product_id": str(stack.product.provider_product_id),
        "schema": "selection-universe-scope-v1",
    }
    content = json.dumps(
        empty_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    artifact = stack.artifacts.publish(
        content,
        media_type="application/json",
        context=_context("empty-scope-artifact", "REGISTER_UNIVERSE_SCOPE"),
    )
    scope = UniverseScopeSpecification(
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        size_bytes=artifact.size_bytes,
        market_provider_product_id=stack.product.provider_product_id,
        classification_scheme="INDEX",
        classification_code="SELECTION_SCOPE",
        instrument_ids=(),
    )
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="empty-scope",
        purpose="prove empty scope remains empty",
    )
    policy = _policy(stack.product.provider_product_id)
    stack.application.register_universe(
        universe,
        _context("register-empty", "REGISTER_UNIVERSE"),
    )
    stack.application.register_eligibility_policy(
        policy,
        _context("register-empty-policy", "REGISTER_ELIGIBILITY_POLICY"),
    )
    frozen = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=stack.decision_time,
        context=_context("freeze-empty", "FREEZE_UNIVERSE"),
    )
    batch = stack.application.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=stack.decision_time,
        context=_context("assess-empty", "ASSESS_ELIGIBILITY"),
    )
    assert frozen.total_count == 0
    assert frozen.members == ()
    assert batch.total_count == 0
    assert batch.assessments == ()


def test_freeze_same_idempotency_key_is_concurrency_safe(
    selection_stack: _SelectionStack,
) -> None:
    stack = selection_stack
    scope = _scope(stack)
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="concurrent-scope",
        purpose="serialize one immutable scope result",
    )
    stack.application.register_universe(
        universe,
        _context("register-concurrent", "REGISTER_UNIVERSE"),
    )

    def freeze():
        return stack.application.freeze_universe(
            universe_id=universe.universe_id,
            scope=scope,
            decision_time=stack.decision_time,
            context=_context("same-concurrent-freeze", "FREEZE_UNIVERSE"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(future.result() for future in (executor.submit(freeze), executor.submit(freeze)))
    assert {item.replayed for item in results} == {False, True}
    assert len({item.universe_revision_id for item in results}) == 1
    assert len({item.result_hash for item in results}) == 1
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.universe_revision WHERE universe_id = %s",
            (universe.universe_id,),
        ).fetchone() == (1,)


def test_decision_time_mismatch_and_stale_fence_leave_no_selection_write(
    selection_stack: _SelectionStack,
) -> None:
    stack = selection_stack
    scope = _scope(stack)
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="fenced-scope",
        purpose="prove stale workers cannot write Selection",
    )
    policy = _policy(stack.product.provider_product_id)
    stack.application.register_universe(
        universe,
        _context("register-fenced", "REGISTER_UNIVERSE"),
    )
    stack.application.register_eligibility_policy(
        policy,
        _context("register-fenced-policy", "REGISTER_ELIGIBILITY_POLICY"),
    )
    stale = AttemptClaim(
        attempt_id=uuid4(),
        run_id=uuid4(),
        step_id=uuid4(),
        step_key="freeze-universe",
        attempt_no=1,
        fence_token=1,
        lease_owner="stale-selection-worker",
        lease_until=datetime.now(UTC) + timedelta(minutes=1),
    )
    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        stack.application.freeze_universe(
            universe_id=universe.universe_id,
            scope=scope,
            decision_time=stack.decision_time,
            context=_context("stale-freeze", "FREEZE_UNIVERSE"),
            runtime_claim=stale,
        )
    frozen = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=stack.decision_time,
        context=_context("live-freeze", "FREEZE_UNIVERSE"),
    )
    mismatched = DecisionTime(stack.decision_time.value - timedelta(seconds=1))
    with pytest.raises(
        ValueError,
        match="Eligibility DecisionTime must equal Universe DecisionTime",
    ):
        stack.application.assess_eligibility(
            universe_revision_id=frozen.universe_revision_id,
            eligibility_policy_id=policy.eligibility_policy_id,
            decision_time=mismatched,
            context=_context("mismatched-assess", "ASSESS_ELIGIBILITY"),
        )
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'stale-freeze'),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'mismatched-assess'),
                (SELECT count(*) FROM mra.eligibility_assessment)
            """
        ).fetchone()
    assert counts == (0, 0, 0)


def test_freeze_uses_decision_time_membership_and_never_backfills_current_state(
    selection_stack: _SelectionStack,
) -> None:
    stack = selection_stack
    scope = _scope(stack)
    first = stack.instrument_ids[0]
    correction = stack.market.capture(
        CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key="membership-correction",
            resource="fixture://membership-correction",
            request_headers_hash="9" * 64,
        ),
        _BytesProvider(),
        _context("capture-membership-correction", "CAPTURE_PROVIDER_RESPONSE"),
    )

    def corrected_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=uuid4(),
                    classification_id=stack.classification_id,
                    instrument_id=first,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.NOT_MEMBER,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=2,
                    supersedes_membership_revision_id=stack.first_membership_id,
                ),
            ),
        )

    corrected = stack.market.normalize(
        correction.capture.capture_id,
        _Normalizer(corrected_batch),
        _context("normalize-membership-correction", "NORMALIZE_MARKET_PIT"),
    )
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="pit-membership",
        purpose="prove exact DecisionTime membership",
    )
    stack.application.register_universe(
        universe,
        _context("register-pit-membership", "REGISTER_UNIVERSE"),
    )
    historical = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=stack.decision_time,
        context=_context("freeze-before-correction", "FREEZE_UNIVERSE"),
    )
    current = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=corrected.decision_visible_at,
        context=_context("freeze-after-correction", "FREEZE_UNIVERSE"),
    )
    assert historical.members[0].membership_status is UniverseMembershipStatus.INCLUDED
    assert current.members[0].membership_status is UniverseMembershipStatus.EXCLUDED
    assert historical.members[0].membership_revision_id != current.members[0].membership_revision_id


def test_market_freshness_expiry_becomes_unknown_without_lowering_integrity(
    selection_stack: _SelectionStack,
) -> None:
    stack = selection_stack
    scope = _scope(stack)
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="stale-market-evidence",
        purpose="prove consumer freshness is tri-state",
    )
    policy = _policy(stack.product.provider_product_id)
    stack.application.register_universe(
        universe,
        _context("register-stale-universe", "REGISTER_UNIVERSE"),
    )
    stack.application.register_eligibility_policy(
        policy,
        _context("register-stale-policy", "REGISTER_ELIGIBILITY_POLICY"),
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            UPDATE mra.artifact AS artifact
            SET last_verified_at = clock_timestamp() - interval '25 hours'
            FROM mra.data_capture AS capture
            WHERE capture.artifact_id = artifact.artifact_id
              AND capture.provider_product_id = %s
            """,
            (stack.product.provider_product_id,),
        )
    frozen = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=stack.decision_time,
        context=_context("freeze-stale-market", "FREEZE_UNIVERSE"),
    )
    batch = stack.application.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=stack.decision_time,
        context=_context("assess-stale-market", "ASSESS_ELIGIBILITY"),
    )
    assert frozen.included_count == frozen.excluded_count == 0
    assert frozen.unknown_count == frozen.total_count == 3
    assert batch.eligible_count == batch.ineligible_count == 0
    assert batch.unknown_count == batch.total_count == 3
    assert all(reason.criterion_result is CriterionResult.UNKNOWN for assessment in batch.assessments for reason in assessment.reasons)
    with psycopg.connect(stack.database_url) as connection:
        states = connection.execute(
            """
            SELECT DISTINCT artifact.integrity_state
            FROM mra.artifact AS artifact
            JOIN mra.data_capture AS capture
              ON capture.artifact_id = artifact.artifact_id
            WHERE capture.provider_product_id = %s
            """,
            (stack.product.provider_product_id,),
        ).fetchall()
    assert states == [("AVAILABLE",)]


def _index_names(node: dict) -> set[str]:
    names = {str(node["Index Name"])} if "Index Name" in node else set()
    for child in node.get("Plans", ()):
        names.update(_index_names(child))
    return names


def test_selection_market_and_result_queries_have_bounded_index_plans(
    selection_stack: _SelectionStack,
) -> None:
    stack = selection_stack
    scope = _scope(stack)
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="query-plan-scope",
        purpose="representative Selection query plan proof",
    )
    policy = _policy(stack.product.provider_product_id)
    stack.application.register_universe(
        universe,
        _context("register-query-plan", "REGISTER_UNIVERSE"),
    )
    stack.application.register_eligibility_policy(
        policy,
        _context("register-query-policy", "REGISTER_ELIGIBILITY_POLICY"),
    )
    frozen = stack.application.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=stack.decision_time,
        context=_context("freeze-query-plan", "FREEZE_UNIVERSE"),
    )
    stack.application.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=stack.decision_time,
        context=_context("assess-query-plan", "ASSESS_ELIGIBILITY"),
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute("SET LOCAL enable_seqscan = off")
        session_row = connection.execute(
            """
            SELECT session_id, open_at, close_at FROM mra.trading_session
            WHERE session_date < %s ORDER BY session_date DESC LIMIT 1
            """,
            (datetime.now(SHANGHAI).date(),),
        ).fetchone()
        assert session_row is not None
        session_id, session_open, session_close = session_row
        plans = (
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT membership_revision_id
                FROM mra.classification_membership_revision
                WHERE classification_id = %s
                  AND instrument_id = %s
                  AND effective_from <= %s
                  AND (effective_to IS NULL OR effective_to > %s)
                  AND decision_visible_at <= %s
                ORDER BY effective_from DESC, decision_visible_at DESC,
                         revision DESC, membership_revision_id DESC
                LIMIT 1
                """,
                (
                    stack.classification_id,
                    stack.instrument_ids[0].value,
                    stack.decision_time.value,
                    stack.decision_time.value,
                    stack.decision_time.value,
                ),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT fact_revision_id
                FROM mra.instrument_fact_revision
                WHERE provider_product_id = %s
                  AND instrument_id = %s
                  AND fact_kind = 'LISTING_STATUS'
                  AND evidence_scope = 'EFFECTIVE_INTERVAL'
                  AND session_id IS NULL
                  AND decision_visible_at <= %s
                  AND event_start <= %s
                  AND (event_end IS NULL OR event_end > %s)
                ORDER BY event_start DESC, decision_visible_at DESC,
                         revision DESC, fact_revision_id DESC
                LIMIT 1
                """,
                (
                    stack.product.provider_product_id,
                    stack.instrument_ids[0].value,
                    stack.decision_time.value,
                    stack.decision_time.value,
                    stack.decision_time.value,
                ),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT bar_revision_id
                FROM mra.market_bar_revision
                WHERE provider_product_id = %s
                  AND instrument_id = %s
                  AND session_id = %s
                  AND timeframe = 'DAILY'
                  AND price_basis = 'RAW_UNADJUSTED'
                  AND event_start = %s
                  AND event_end = %s
                  AND decision_visible_at <= %s
                ORDER BY decision_visible_at DESC, revision DESC,
                         bar_revision_id DESC
                LIMIT 1
                """,
                (
                    stack.product.provider_product_id,
                    stack.instrument_ids[0].value,
                    session_id,
                    session_open,
                    session_close,
                    stack.decision_time.value,
                ),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT instrument_id
                FROM mra.universe_member
                WHERE universe_revision_id = %s
                  AND membership_status = 'INCLUDED'
                ORDER BY instrument_id
                """,
                (frozen.universe_revision_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT instrument_id
                FROM mra.eligibility_assessment
                WHERE universe_revision_id = %s
                  AND eligibility_policy_id = %s
                  AND result = 'ELIGIBLE'
                ORDER BY instrument_id
                """,
                (frozen.universe_revision_id, policy.eligibility_policy_id),
            ).fetchone()[0][0]["Plan"],
        )
    names = set().union(*(_index_names(plan) for plan in plans))
    expected_indexes = {
        "classification_membership_classification_idx",
        "instrument_fact_current_asof_idx",
        "market_bar_exact_asof_idx",
        "universe_member_status_idx",
        "eligibility_assessment_result_idx",
    }
    assert expected_indexes <= names, names


def test_target_runtime_executes_capture_normalize_freeze_assess_in_four_atomic_steps(
    target_database_url: str,
    tmp_path,
    request: pytest.FixtureRequest,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    request.addfinalizer(pool.close)
    store = LocalArtifactStore(tmp_path / "selection-runtime-artifacts")
    runtime_uow = PostgresUnitOfWorkProvider(pool)
    runtime = RuntimeApplication(runtime_uow)
    artifacts = ArtifactApplication(store, runtime_uow)
    market = MarketApplication(
        store,
        PostgresMarketUnitOfWorkProvider(pool),
        PostgresMarketDatabaseClock(pool),
    )
    selection = SelectionApplication(PostgresSelectionUnitOfWorkProvider(pool))
    provider = Provider(
        provider_id=uuid4(),
        provider_code="selection_runtime",
        display_name="Selection Runtime",
        provider_kind=ProviderKind.PUBLIC_ENDPOINT,
    )
    product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="selection_runtime_facts",
        revision=1,
        payload_family="SELECTION_RUNTIME_FACTS",
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
        _context("runtime-provider", "REGISTER_PROVIDER"),
    )
    market.register_provider_product(
        product,
        _context("runtime-product", "REGISTER_PROVIDER_PRODUCT"),
    )
    instrument_id = InstrumentId(uuid4())
    scope_payload = {
        "classification_code": "RUNTIME_SCOPE",
        "classification_scheme": "INDEX",
        "instrument_ids": [str(instrument_id)],
        "market_provider_product_id": str(product.provider_product_id),
        "schema": "selection-universe-scope-v1",
    }
    scope_content = json.dumps(
        scope_payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    scope_artifact = artifacts.publish(
        scope_content,
        media_type="application/json",
        context=_context("runtime-scope", "REGISTER_UNIVERSE_SCOPE"),
        pin_reason_code="UNIVERSE_SCOPE",
    )
    scope = UniverseScopeSpecification(
        artifact_id=scope_artifact.artifact_id,
        content_sha256=scope_artifact.content_sha256,
        size_bytes=scope_artifact.size_bytes,
        market_provider_product_id=product.provider_product_id,
        classification_scheme="INDEX",
        classification_code="RUNTIME_SCOPE",
        instrument_ids=(instrument_id,),
    )
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code="runtime-scope",
        purpose="test-only four-step target Runtime slice",
    )
    complete_policy = _policy(product.provider_product_id)
    policy = EligibilityPolicy(
        eligibility_policy_id=uuid4(),
        market_provider_product_id=product.provider_product_id,
        policy_code="runtime-effective-facts",
        version=1,
        rules=(
            replace(
                complete_policy.rules[1],
                eligibility_rule_id=uuid4(),
                ordinal=1,
            ),
            replace(
                complete_policy.rules[2],
                eligibility_rule_id=uuid4(),
                ordinal=2,
            ),
        ),
    )
    selection.register_universe(
        universe,
        _context("runtime-universe", "REGISTER_UNIVERSE"),
    )
    selection.register_eligibility_policy(
        policy,
        _context("runtime-policy", "REGISTER_ELIGIBILITY_POLICY"),
    )
    schedule = ScheduleSpec(
        schedule_id=uuid4(),
        schedule_code="selection-four-step",
        revision=1,
        runtime_mode=RuntimeMode.OPERATIONAL,
        schedule_expression=None,
        timezone_name="Asia/Shanghai",
        step_catalog_hash="a" * 64,
        enabled=True,
    )
    runtime.create_schedule(
        schedule,
        _context("runtime-schedule", "CREATE_RUNTIME_SCHEDULE"),
    )
    step_kinds = (
        ("capture", "CAPTURE", ExternalEffectClass.CONTENT_PUT),
        ("normalize-pit", "NORMALIZE_PIT", ExternalEffectClass.PURE_READ),
        ("freeze-universe", "FREEZE_UNIVERSE", ExternalEffectClass.PURE_READ),
        (
            "assess-eligibility",
            "ASSESS_ELIGIBILITY",
            ExternalEffectClass.PURE_READ,
        ),
    )
    steps = tuple(
        StepSpec(
            step_key=key,
            step_kind=kind,
            implementation=f"selection.runtime.{key}",
            implementation_version="1",
            ordinal=ordinal,
            required=True,
            request_hash=f"{ordinal + 1:x}" * 64,
            input_evidence_hash=None,
            retry_policy=RetryPolicy(
                max_attempts=1,
                backoff=(),
                retryable_codes=frozenset(),
            ),
            external_effect_class=effect,
        )
        for ordinal, (key, kind, effect) in enumerate(step_kinds, start=1)
    )
    dependencies = tuple(
        StepDependency(predecessor_key=left[0], successor_key=right[0]) for left, right in zip(step_kinds, step_kinds[1:], strict=False)
    )
    run_id = uuid4()
    runtime.schedule_run(
        RunSpec(
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            fire_key="selection-four-step-run",
            runtime_mode=RuntimeMode.OPERATIONAL,
            requested_at=datetime.now(UTC),
            decision_time=None,
            code_sha="1" * 40,
            config_artifact_id=scope_artifact.artifact_id,
            config_hash=scope_artifact.content_sha256,
        ),
        steps,
        dependencies,
        _context("runtime-plan", "SCHEDULE_RUNTIME_RUN"),
    )
    runtime.start_run(run_id, _context("runtime-start", "START_RUNTIME_RUN"))

    capture_claim = runtime.claim_next(
        worker_id="selection-capture-worker",
        lease_duration=timedelta(seconds=10),
        context=_context("claim-runtime-capture", "WORKER_CLAIM"),
    )
    assert capture_claim is not None
    runtime.start_attempt(
        capture_claim,
        _context("start-runtime-capture", "WORKER_START"),
    )
    captured = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="runtime-selection-capture",
            resource="fixture://runtime-selection",
            request_headers_hash="b" * 64,
        ),
        _BytesProvider(),
        _context("runtime-market-capture", "CAPTURE_PROVIDER_RESPONSE"),
        runtime_claim=capture_claim,
    )

    normalize_claim = runtime.claim_next(
        worker_id="selection-normalize-worker",
        lease_duration=timedelta(seconds=10),
        context=_context("claim-runtime-normalize", "WORKER_CLAIM"),
    )
    assert normalize_claim is not None
    runtime.start_attempt(
        normalize_claim,
        _context("start-runtime-normalize", "WORKER_START"),
    )
    classification_id = uuid4()

    def runtime_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="688001.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_id,
                    classification_scheme="INDEX",
                    classification_code="RUNTIME_SCOPE",
                    display_name="Runtime Scope",
                    revision=1,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    supersedes_classification_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=uuid4(),
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
            lifecycle_status_facts=(
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.LISTED,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
                    status=SpecialTreatmentStatus.NORMAL,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    normalized = market.normalize(
        captured.capture.capture_id,
        _Normalizer(runtime_batch),
        _context("runtime-market-normalize", "NORMALIZE_MARKET_PIT"),
        runtime_claim=normalize_claim,
    )

    freeze_claim = runtime.claim_next(
        worker_id="selection-freeze-worker",
        lease_duration=timedelta(seconds=10),
        context=_context("claim-runtime-freeze", "WORKER_CLAIM"),
    )
    assert freeze_claim is not None
    runtime.start_attempt(
        freeze_claim,
        _context("start-runtime-freeze", "WORKER_START"),
    )
    frozen = selection.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=normalized.decision_visible_at,
        context=_context("runtime-selection-freeze", "FREEZE_UNIVERSE"),
        runtime_claim=freeze_claim,
    )

    assess_claim = runtime.claim_next(
        worker_id="selection-assess-worker",
        lease_duration=timedelta(seconds=10),
        context=_context("claim-runtime-assess", "WORKER_CLAIM"),
    )
    assert assess_claim is not None
    runtime.start_attempt(
        assess_claim,
        _context("start-runtime-assess", "WORKER_START"),
    )
    assessed = selection.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=normalized.decision_visible_at,
        context=_context("runtime-selection-assess", "ASSESS_ELIGIBILITY"),
        runtime_claim=assess_claim,
    )
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "SUCCEEDED"
    assert tuple(step.state for step in trace.steps) == ("SUCCEEDED",) * 4
    assert frozen.included_count == 1
    assert assessed.eligible_count == 1
    with psycopg.connect(target_database_url) as connection:
        atomic_rows = connection.execute(
            """
            SELECT receipt.command_kind, receipt.fence_token,
                   audit.fence_token, attempt.state, step.state
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            JOIN mra.runtime_step AS step ON step.step_id = attempt.step_id
            WHERE receipt.command_kind IN (
                'CAPTURE_MARKET_DATA', 'NORMALIZE_MARKET_PIT',
                'FREEZE_UNIVERSE', 'ASSESS_ELIGIBILITY'
            )
            ORDER BY step.ordinal
            """
        ).fetchall()
    assert atomic_rows == [
        ("CAPTURE_MARKET_DATA", 1, 1, "SUCCEEDED", "SUCCEEDED"),
        ("NORMALIZE_MARKET_PIT", 1, 1, "SUCCEEDED", "SUCCEEDED"),
        ("FREEZE_UNIVERSE", 1, 1, "SUCCEEDED", "SUCCEEDED"),
        ("ASSESS_ELIGIBILITY", 1, 1, "SUCCEEDED", "SUCCEEDED"),
    ]
