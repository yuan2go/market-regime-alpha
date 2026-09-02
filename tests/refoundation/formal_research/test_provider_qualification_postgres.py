from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from threading import Lock
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.provider_qualification_uow import (
    PostgresProviderQualificationUnitOfWork,
    PostgresProviderQualificationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.provider_qualification import (
    PostgresProviderQualificationQueryPort,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import (
    MarketApplication,
    ProviderQualificationCommands,
)
from market_regime_alpha.market.errors import MarketCommitOutcomeUnknownError
from market_regime_alpha.market.domain import (
    BarTimeframe,
    InstrumentFactKind,
    MarketFactKind,
    PriceBasis,
    Provider,
    ProviderEvidenceClass,
    ProviderFinalityObservation,
    ProviderFinalityStatus,
    ProviderKind,
    ProviderProduct,
    ProviderQualificationArtifact,
    ProviderQualificationProtocol,
    ProviderQualificationPurpose,
    ProviderQualificationRequirement,
    ProviderRequirementKind,
    SourceAvailabilityStatus,
)
from market_regime_alpha.market.ports import CaptureRequest, ProviderResponse
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
)


class _UnknownCommitProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._lock = Lock()
        self._raised = False

    def __call__(self):
        provider = self

        class _UnknownCommitUow(PostgresProviderQualificationUnitOfWork):
            def commit(self) -> None:
                super().commit()
                with provider._lock:
                    if not provider._raised:
                        provider._raised = True
                        raise MarketCommitOutcomeUnknownError(
                            "injected lost Provider commit acknowledgement"
                        )

        return _UnknownCommitUow(self._pool, id_factory=uuid4)


class _RecordedBytesProvider:
    def __init__(self, available_at) -> None:
        self._available_at = available_at

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        return ProviderResponse(
            content=b'{"rows":[]}',
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=self._available_at,
            source_availability_status=SourceAvailabilityStatus.PROVIDER_REPORTED,
            source_available_at=self._available_at,
            limitation_code=None,
        )


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="wp14-provider-qualification-test",
        reason_code="WP14_ENGINEERING_REHEARSAL",
    )


def test_complete_provider_qualification_derives_full_rosters_and_caps_rehearsal(
    target_database_url: str,
    tmp_path,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=4)
    store = LocalArtifactStore(tmp_path / "wp14-provider-qualification")
    artifacts = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    market = MarketApplication(
        store,
        PostgresMarketUnitOfWorkProvider(pool),
        PostgresMarketDatabaseClock(pool),
    )
    commands = ProviderQualificationCommands(
        PostgresProviderQualificationUnitOfWorkProvider(pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    try:
        provider = Provider(
            provider_id=uuid4(),
            provider_code="wp14-fixture",
            display_name="WP-14 Fixture",
            provider_kind=ProviderKind.DATA_VENDOR,
        )
        product = ProviderProduct(
            provider_product_id=uuid4(),
            provider_id=provider.provider_id,
            product_code="minute_archive",
            revision=1,
            payload_family="HISTORICAL_BAR",
            media_type="application/json",
            payload_encoding="UTF-8",
            source_availability_policy=SourceAvailabilityStatus.PROVIDER_REPORTED,
            fact_kinds=tuple(MarketFactKind),
            instrument_fact_kinds=tuple(InstrumentFactKind),
            bar_timeframes=tuple(BarTimeframe),
            price_bases=tuple(PriceBasis),
        )
        market.register_provider(provider, _context("provider"))
        market.register_provider_product(product, _context("product"))
        available_at = PostgresMarketDatabaseClock(pool).now() - timedelta(days=1)
        capture = market.capture(
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="wp14-fixture-capture",
                resource="fixture://wp14-provider-qualification",
                request_headers_hash="1" * 64,
            ),
            _RecordedBytesProvider(available_at),
            _context("capture"),
        )
        code = artifacts.publish(
            b"provider qualification code",
            media_type="text/plain",
            context=_context("code"),
        )
        config = artifacts.publish(
            b'{"provider_qualification":"rehearsal"}',
            media_type="application/json",
            context=_context("config"),
        )
        protocol_id = uuid4()
        requirements = tuple(
            ProviderQualificationRequirement(
                provider_qualification_requirement_id=uuid4(),
                provider_qualification_protocol_id=protocol_id,
                ordinal=ordinal,
                requirement_kind=kind,
                minimum_observation_count=1,
                minimum_ratio=Decimal("1"),
            )
            for ordinal, kind in enumerate(ProviderRequirementKind, start=1)
        )
        capture_time = capture.capture.temporal.capture_started_at
        protocol = ProviderQualificationProtocol(
            provider_qualification_protocol_id=protocol_id,
            protocol_code="wp14-fixture-protocol",
            revision=1,
            supersedes_protocol_id=None,
            provider_product_id=product.provider_product_id,
            purpose=ProviderQualificationPurpose.HISTORICAL_PIT,
            evidence_class=ProviderEvidenceClass.ENGINEERING_REHEARSAL,
            market_scope="A_SHARE",
            instrument_scope="SSE_EQUITY",
            exchange_code="SSE",
            timeframe=BarTimeframe.MINUTE_1,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            decision_time_rule="SESSION_10_30_ASIA_SHANGHAI",
            capture_window_start=capture_time - timedelta(seconds=1),
            capture_window_end=capture_time + timedelta(seconds=1),
            evidence_cutoff=capture.capture.temporal.known_at.value + timedelta(seconds=2),
            outcome_path_sessions=5,
            requirements=requirements,
            code_artifact=ProviderQualificationArtifact(
                code.artifact_id, code.content_sha256, code.size_bytes
            ),
            config_artifact=ProviderQualificationArtifact(
                config.artifact_id, config.content_sha256, config.size_bytes
            ),
            provenance_sha256="2" * 64,
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            registrations = tuple(
                executor.map(
                    lambda _: commands.register_protocol(
                        protocol, _context("protocol")
                    ),
                    range(2),
                )
            )
        assert {item.requirement_count for item in registrations} == {10}
        assert {item.replayed for item in registrations} == {False, True}
        with pytest.raises(IdempotencyKeyReusedError):
            commands.register_protocol(
                replace(protocol, market_scope="CHANGED_SCOPE"),
                _context("protocol"),
            )

        finality = ProviderFinalityObservation(
            provider_finality_observation_id=uuid4(),
            capture_id=capture.capture.capture_id,
            observation_ordinal=1,
            supersedes_observation_id=None,
            finality_status=ProviderFinalityStatus.FINAL,
            publication_observed_at=available_at,
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="3" * 64,
        )
        observed = commands.record_finality_observation(
            finality,
            _context("finality"),
        )
        observed_replay = commands.record_finality_observation(
            finality,
            _context("finality"),
        )
        assert observed.replayed is False
        assert observed_replay.replayed is True
        assert observed_replay.result_hash == observed.result_hash

        decision_id = uuid4()
        with ThreadPoolExecutor(max_workers=2) as executor:
            completions = tuple(
                executor.map(
                    lambda _: commands.complete(
                        provider_qualification_decision_id=decision_id,
                        decision_code="wp14-fixture-decision",
                        provider_qualification_protocol_id=protocol_id,
                        context=_context("complete"),
                    ),
                    range(2),
                )
            )
        assert {item.replayed for item in completions} == {False, True}
        completed = completions[0]

        assert completed.decision_status == "REJECTED"
        assert completed.evidence_class == "ENGINEERING_REHEARSAL"
        assert completed.capture_count == 1
        assert completed.requirement_result_count == 10
        replay = commands.complete(
            provider_qualification_decision_id=completed.provider_qualification_decision_id,
            decision_code="wp14-fixture-decision",
            provider_qualification_protocol_id=protocol_id,
            context=_context("complete"),
        )
        assert replay.replayed is True
        assert replay.provider_qualification_decision_id == completed.provider_qualification_decision_id
        assert replay.result_hash == completed.result_hash
        verifier = PostgresProviderQualificationQueryPort(pool)
        protocol_verification = verifier.verify_protocol(protocol_id)
        decision_verification = verifier.verify_decision(
            completed.provider_qualification_decision_id
        )
        assert protocol_verification.matched is True
        assert protocol_verification.mismatch_count == 0
        assert decision_verification.matched is True
        assert decision_verification.mismatch_count == 0

        with psycopg.connect(target_database_url) as connection:
            counts = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM mra.provider_qualification_capture_member),
                  (SELECT count(*) FROM mra.provider_qualification_requirement_result),
                  (SELECT count(*) FROM mra.provider_qualification_decision)
                """
            ).fetchone()
        assert counts == (1, 10, 1)
        with psycopg.connect(target_database_url) as connection:
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    """
                    INSERT INTO mra.provider_qualification_decision (
                        provider_qualification_decision_id, decision_code,
                        provider_qualification_protocol_id, provider_product_id,
                        purpose, evidence_class, protocol_content_sha256,
                        decision_status, capture_count, capture_roster_sha256,
                        requirement_result_count, requirement_result_roster_sha256,
                        reason_code, content_sha256, request_identity, request_sha256
                    ) VALUES (
                        %s, 'forbidden-rehearsal-admission', %s, %s, %s, %s, %s,
                        'ADMITTED', 1, %s, 10, %s, 'FORBIDDEN', %s, 'forbidden', %s
                    )
                    """,
                    (
                        uuid4(), protocol_id, product.provider_product_id,
                        protocol.purpose.value, protocol.evidence_class.value,
                        str(protocol.content_sha256), "a" * 64, "b" * 64,
                        "c" * 64, "d" * 64,
                    ),
                )

        unknown_protocol_id = uuid4()
        unknown_protocol = replace(
            protocol,
            provider_qualification_protocol_id=unknown_protocol_id,
            protocol_code="wp14-unknown-commit-protocol",
            requirements=tuple(
                replace(
                    requirement,
                    provider_qualification_requirement_id=uuid4(),
                    provider_qualification_protocol_id=unknown_protocol_id,
                )
                for requirement in protocol.requirements
            ),
        )
        recovered = ProviderQualificationCommands(
            _UnknownCommitProvider(pool),
            id_factory=uuid4,
        ).register_protocol(
            unknown_protocol,
            _context("unknown-commit-protocol"),
        )
        assert recovered.replayed is True
        assert recovered.provider_qualification_protocol_id == unknown_protocol_id
        assert PostgresProviderQualificationQueryPort(pool).verify_protocol(
            unknown_protocol_id
        ).matched is True

        with psycopg.connect(target_database_url) as connection:
            connection.execute(
                """
                CREATE FUNCTION mra.test_fail_provider_requirement_result()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                  IF NEW.result_ordinal = 5 THEN
                    RAISE EXCEPTION 'injected Provider result failure'
                      USING ERRCODE = '23514';
                  END IF;
                  RETURN NEW;
                END
                $$
                """
            )
            connection.execute(
                """
                CREATE TRIGGER test_fail_provider_requirement_result_trigger
                AFTER INSERT ON mra.provider_qualification_requirement_result
                FOR EACH ROW EXECUTE FUNCTION mra.test_fail_provider_requirement_result()
                """
            )
            connection.commit()
        recovery_decision_id = uuid4()
        with pytest.raises(RuntimeStateConflictError) as failure:
            commands.complete(
                provider_qualification_decision_id=recovery_decision_id,
                decision_code="wp14-mid-result-recovery",
                provider_qualification_protocol_id=unknown_protocol_id,
                context=_context("mid-result-failure"),
            )
        assert "injected Provider result failure" in str(failure.value.__cause__)
        with psycopg.connect(target_database_url) as connection:
            partial = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM mra.provider_qualification_decision
                   WHERE provider_qualification_decision_id = %s),
                  (SELECT count(*) FROM mra.provider_qualification_capture_member
                   WHERE provider_qualification_decision_id = %s),
                  (SELECT count(*) FROM mra.provider_qualification_requirement_result
                   WHERE provider_qualification_decision_id = %s)
                """,
                (recovery_decision_id,) * 3,
            ).fetchone()
            connection.execute(
                "DROP TRIGGER test_fail_provider_requirement_result_trigger "
                "ON mra.provider_qualification_requirement_result"
            )
            connection.execute(
                "DROP FUNCTION mra.test_fail_provider_requirement_result()"
            )
            connection.commit()
        assert partial == (0, 0, 0)
        recovered_decision = commands.complete(
            provider_qualification_decision_id=recovery_decision_id,
            decision_code="wp14-mid-result-recovery",
            provider_qualification_protocol_id=unknown_protocol_id,
            context=_context("mid-result-recovery"),
        )
        assert recovered_decision.provider_qualification_decision_id == recovery_decision_id
        assert PostgresProviderQualificationQueryPort(pool).verify_decision(
            recovery_decision_id
        ).matched is True
    finally:
        pool.close()
