from __future__ import annotations

import pytest

from market_regime_alpha.data.pit_contracts import (
    PITFactKind,
    PITSourceEvidenceLevel,
    ProviderFactCeiling,
    ProviderQualificationPolicyV2,
)
from market_regime_alpha.data.postgres_provider_qualification import (
    PostgresProviderFactQualificationAuthority,
    ProviderFactQualificationStatus,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


def test_provider_fact_assessment_is_owner_resolved_and_idempotent(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    authority = PostgresProviderFactQualificationAuthority(postgres_factory)
    policy = ProviderQualificationPolicyV2.default()

    first = authority.assess(
        policy=policy,
        provider_id="provider-baostock-public",
        provider_contract="baostock-public-history-v1",
        fact_kind=PITFactKind.MARKET_DATA,
        actor="phase-c-operator",
        reason="assess current free-data evidence ceiling",
        idempotency_key="baostock-market-data-c1",
    )
    duplicate = authority.assess(
        policy=policy,
        provider_id="provider-baostock-public",
        provider_contract="baostock-public-history-v1",
        fact_kind=PITFactKind.MARKET_DATA,
        actor="phase-c-operator",
        reason="assess current free-data evidence ceiling",
        idempotency_key="baostock-market-data-c1",
    )

    assert duplicate == first
    assert first.status is ProviderFactQualificationStatus.REJECTED
    assert first.qualified is False
    assert first.reason_codes == ("FORMAL_PROVIDER_EVIDENCE_CEILING_NOT_MET",)
    assert first.source_qualification_references == ()
    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM provider_fact_qualification_decision"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM provider_fact_qualification_command"
        ).fetchone()[0] == 1

    with pytest.raises(ValueError, match="idempotency conflict"):
        authority.assess(
            policy=policy,
            provider_id="provider-baostock-public",
            provider_contract="baostock-public-history-v1",
            fact_kind=PITFactKind.MARKET_DATA,
            actor="different-actor",
            reason="different command",
            idempotency_key="baostock-market-data-c1",
        )


def test_formal_capable_scope_remains_incomplete_without_postgres_source_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    policy = ProviderQualificationPolicyV2.create(
        scope_ceilings=(
            ProviderFactCeiling(
                "future-qualified-provider",
                "contract-v1",
                PITFactKind.TRADING_CALENDAR,
                PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER,
            ),
        ),
        default_ceiling=PITSourceEvidenceLevel.PIT_INCOMPLETE,
    )
    decision = PostgresProviderFactQualificationAuthority(
        postgres_factory
    ).assess(
        policy=policy,
        provider_id="future-qualified-provider",
        provider_contract="contract-v1",
        fact_kind=PITFactKind.TRADING_CALENDAR,
        actor="phase-c-operator",
        reason="resolve evidence from PIT source authority",
        idempotency_key="future-provider-calendar-c1",
    )

    assert decision.status is ProviderFactQualificationStatus.INCOMPLETE
    assert decision.reason_codes == ("ACTIVE_SOURCE_QUALIFICATION_MISSING",)
    assert decision.qualified is False


def test_provider_fact_revocation_is_append_only_and_assessment_cannot_reinstate(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    authority = PostgresProviderFactQualificationAuthority(postgres_factory)
    assessed = authority.assess(
        policy=ProviderQualificationPolicyV2.default(),
        provider_id="provider-tencent-public",
        provider_contract="tencent-current-quote-v1",
        fact_kind=PITFactKind.MARKET_DATA,
        actor="phase-c-operator",
        reason="establish scope before revocation",
        idempotency_key="tencent-market-data-before-revoke",
    )
    revoked = authority.revoke(
        provider_id="provider-tencent-public",
        provider_contract="tencent-current-quote-v1",
        fact_kind=PITFactKind.MARKET_DATA,
        actor="phase-c-operator",
        reason="explicitly revoke the scope",
        idempotency_key="tencent-market-data-revoke",
    )
    reassessed = authority.assess(
        policy=ProviderQualificationPolicyV2.default(),
        provider_id="provider-tencent-public",
        provider_contract="tencent-current-quote-v1",
        fact_kind=PITFactKind.MARKET_DATA,
        actor="phase-c-operator",
        reason="ordinary assessment cannot reinstate a revoked scope",
        idempotency_key="tencent-market-data-after-revoke",
    )

    assert assessed.status is ProviderFactQualificationStatus.REJECTED
    assert revoked.status is ProviderFactQualificationStatus.REVOKED
    assert revoked.revision == assessed.revision + 1
    assert revoked.supersedes_decision_id == assessed.decision_id
    assert reassessed == revoked
    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM provider_fact_qualification_decision"
        ).fetchone()[0] == 2
