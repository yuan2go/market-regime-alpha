from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.policy import (
    default_continuous_decision_window_policy,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
HASH_3 = "sha256:" + "3" * 64
TRADING_DATE = date(2026, 8, 6)
OBSERVED_AT = datetime(2026, 8, 6, 6, 42, 17, tzinfo=timezone.utc)
LIMITATIONS = (
    "ENTRY_BLOCKED",
    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
    "FORMAL_PIT_NOT_ESTABLISHED",
    "NO_BROKER_AUTHORITY",
)


def _command(
    *,
    research_hash: str = HASH_3,
    authority_mode: RuntimeAuthorityMode = RuntimeAuthorityMode.RESEARCH,
) -> ContinuousResearchCommand:
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key="continuous-research-2026-08-06-scope-a",
        trading_date=TRADING_DATE,
        requested_symbols=("000001.SZ", "600000.SH"),
        trading_calendar_id=ArtifactId("calendar-2026-a-share"),
        trading_calendar_hash=HASH_1,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("provider-config-v1"),
        provider_configuration_hash=HASH_2,
        research_configuration_id=ArtifactId("research-config-v1"),
        research_configuration_hash=research_hash,
        authority_mode=authority_mode,
        code_revision="8de820cd149278bfebbaf18f150a90f36380176d",
        limitations=LIMITATIONS,
    )


def test_continuous_command_is_content_addressed_and_scope_order_is_canonical() -> None:
    first = _command()
    reordered = ContinuousResearchCommand.create(
        idempotency_key=first.idempotency_key,
        trading_date=first.trading_date,
        requested_symbols=tuple(reversed(first.requested_symbols)),
        trading_calendar_id=first.trading_calendar_id,
        trading_calendar_hash=first.trading_calendar_hash,
        policy_id=first.policy_id,
        policy_hash=first.policy_hash,
        provider_configuration_id=first.provider_configuration_id,
        provider_configuration_hash=first.provider_configuration_hash,
        research_configuration_id=first.research_configuration_id,
        research_configuration_hash=first.research_configuration_hash,
        authority_mode=first.authority_mode,
        code_revision=first.code_revision,
        limitations=first.limitations,
    )
    restored = ContinuousResearchCommand.from_canonical_dict(
        first.to_canonical_dict()
    )

    assert first.requested_symbols == ("000001.SZ", "600000.SH")
    assert reordered == first
    assert restored == first
    assert str(first.run_id).startswith("continuous-research-run-")
    assert first.request_scope_hash.startswith("sha256:")


def test_continuous_command_rejects_duplicate_scope_and_incomplete_authority() -> None:
    first = _command()

    with pytest.raises(ValueError, match="requested_symbols"):
        replace(first, requested_symbols=("600000.SH", "600000.SH"))
    with pytest.raises(ValueError, match="authority ceiling"):
        replace(first, limitations=("FORMAL_PIT_NOT_ESTABLISHED",))


def test_configuration_change_produces_a_different_run_identity() -> None:
    assert _command(research_hash=HASH_2).run_id != _command().run_id


def test_runtime_mode_changes_run_identity_and_round_trips() -> None:
    research = _command()
    shadow = _command(authority_mode=RuntimeAuthorityMode.SHADOW)
    production = _command(authority_mode=RuntimeAuthorityMode.PRODUCTION)

    assert len({research.run_id, shadow.run_id, production.run_id}) == 3
    assert ContinuousResearchCommand.from_canonical_dict(
        shadow.to_canonical_dict()
    ).authority_mode is RuntimeAuthorityMode.SHADOW


def test_tick_identity_binds_run_time_scope_and_configuration() -> None:
    command = _command()
    tick = RuntimeTickCommand.create(
        idempotency_key="tick-2026-08-06T06:42:17Z",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=OBSERVED_AT,
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
        authority_mode=command.authority_mode,
    )

    restored = RuntimeTickCommand.from_canonical_dict(tick.to_canonical_dict())
    changed = RuntimeTickCommand.create(
        idempotency_key=tick.idempotency_key,
        run_id=tick.run_id,
        trading_date=tick.trading_date,
        observed_at=datetime(2026, 8, 6, 6, 43, 17, tzinfo=timezone.utc),
        request_scope_hash=tick.request_scope_hash,
        provider_configuration_id=tick.provider_configuration_id,
        provider_configuration_hash=tick.provider_configuration_hash,
        research_configuration_id=tick.research_configuration_id,
        research_configuration_hash=tick.research_configuration_hash,
        authority_mode=RuntimeAuthorityMode.SHADOW,
    )

    assert restored == tick
    assert str(tick.tick_id).startswith("continuous-research-tick-")
    assert changed.tick_id != tick.tick_id
    assert restored.authority_mode is RuntimeAuthorityMode.RESEARCH


def test_tick_rejects_naive_or_non_second_observation_time() -> None:
    command = _command()
    common = {
        "idempotency_key": "tick-invalid",
        "run_id": command.run_id,
        "trading_date": command.trading_date,
        "request_scope_hash": command.request_scope_hash,
        "provider_configuration_id": command.provider_configuration_id,
        "provider_configuration_hash": command.provider_configuration_hash,
        "research_configuration_id": command.research_configuration_id,
        "research_configuration_hash": command.research_configuration_hash,
        "authority_mode": command.authority_mode,
    }

    with pytest.raises(ValueError, match="timezone-aware"):
        RuntimeTickCommand.create(
            observed_at=datetime(2026, 8, 6, 6, 42, 17),
            **common,
        )
    with pytest.raises(ValueError, match="whole-second"):
        RuntimeTickCommand.create(
            observed_at=OBSERVED_AT.replace(microsecond=1),
            **common,
        )
