from __future__ import annotations

from typing import Any

import pytest

from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolFreezeScope,
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.cli.continuous_research import _record_phase_c_owner_package
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.phase_c_owner_fixture import (
    record_phase_c_protocol_owners,
)


def test_typed_owner_and_protocol_operator_workflow_is_idempotent_and_audited(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    package = _owner_package_from_canonical_rows(postgres_factory, fixture)

    first = _record_phase_c_owner_package(postgres_factory, package)
    second = _record_phase_c_owner_package(postgres_factory, package)

    assert first == second
    assert first["operation"] == "QUALIFICATION_TYPED_OWNERS_RECORD"
    assert first["production_authorized"] is False
    assert len(first["owners"]) == 11

    protocol = PostgresFormalProtocolRepository(postgres_factory).freeze_protocol(
        scope=FormalProtocolFreezeScope.from_protocol_references(fixture.protocol),
        actor="phase-c-operator-test",
        reason="freeze owner-resolved Formal Protocol",
        idempotency_key="phase-c-operator-protocol",
    )
    assert PostgresFormalProtocolRepository(postgres_factory).freeze_protocol(
        scope=FormalProtocolFreezeScope.from_protocol_references(fixture.protocol),
        actor="phase-c-operator-test",
        reason="freeze owner-resolved Formal Protocol",
        idempotency_key="phase-c-operator-protocol",
    ) == protocol

    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT action_kind, actor, reason, created_at
            FROM phase_c_formal_operator_command ORDER BY idempotency_key
            """
        ).fetchall()
    assert len(rows) == 12
    assert {str(item[0]) for item in rows} >= {
        "FREEZE_TARGET_PROTOCOL",
        "FREEZE_TRADING_CALENDAR",
        "FREEZE_EVALUATION_PROTOCOL",
        "FREEZE_FEATURE_DEFINITION_SET",
        "FREEZE_FACTOR_CATALOG",
        "FREEZE_THRESHOLD_POLICY",
        "FREEZE_FORMAL_OOS_POLICY",
        "FREEZE_CALIBRATION_POLICY",
        "FREEZE_STRATEGY_POLICY",
        "FREEZE_COST_POLICY",
        "FREEZE_ENTRY_HOLDING_EXIT_POLICY",
        "FREEZE_FORMAL_PROTOCOL",
    }
    assert all(str(item[1]).strip() and str(item[2]).strip() for item in rows)
    assert all(item[3].tzinfo is not None for item in rows)

    conflicting = {**package, "reason": "different operator command"}
    with pytest.raises(ValueError, match="idempotency conflict"):
        _record_phase_c_owner_package(postgres_factory, conflicting)


def _owner_package_from_canonical_rows(
    factory: PostgresConnectionFactory,
    fixture: Any,
) -> dict[str, Any]:
    with factory.connection(read_only=True) as connection:
        def artifact(
            kind: str,
            id_name: str,
            hash_name: str,
        ) -> dict[str, Any]:
            row = connection.execute(
                """
                SELECT artifact_id, artifact_hash, payload_json
                FROM research_validation_artifact
                WHERE artifact_kind = %s
                """,
                (kind,),
            ).fetchone()
            assert row is not None and isinstance(row[2], dict)
            return {id_name: str(row[0]), hash_name: str(row[1]), **row[2]}

        oos = connection.execute(
            "SELECT payload_json FROM formal_oos_qualification_policy"
        ).fetchone()
        calibration = connection.execute(
            "SELECT payload_json FROM calibration_qualification_policy"
        ).fetchone()
        strategy = connection.execute(
            """
            SELECT policy_id, policy_hash, policy_json
            FROM strategy_shadow_policy_authority
            """
        ).fetchone()
        portfolio = connection.execute(
            "SELECT policy_json, portfolio_json FROM strategy_shadow_portfolio"
        ).fetchone()
        entry = connection.execute(
            "SELECT policy_json FROM entry_holding_exit_qualification_policy"
        ).fetchone()
        evaluation_payload = artifact(
            "FORMAL_EVALUATION_PROTOCOL", "protocol_id", "protocol_hash"
        )
        feature_payload = artifact(
            "FEATURE_DEFINITION_SET", "definition_set_id", "definition_set_hash"
        )
        enrichment_payload = artifact(
            "PANEL_ENRICHMENT", "enrichment_id", "enrichment_hash"
        )
        factor_payload = artifact(
            "FACTOR_RESEARCH_CATALOG", "catalog_id", "catalog_hash"
        )
        threshold_payload = artifact(
            "THRESHOLD_POLICY", "policy_id", "policy_hash"
        )
        calibration_protocol_payload = artifact(
            "CALIBRATION_PROTOCOL", "protocol_id", "protocol_hash"
        )
    assert oos is not None and isinstance(oos[0], dict)
    assert calibration is not None and isinstance(calibration[0], dict)
    assert strategy is not None and isinstance(strategy[2], dict)
    assert portfolio is not None and all(isinstance(item, dict) for item in portfolio)
    assert entry is not None and isinstance(entry[0], dict)
    strategy_payload = {
        "policy_id": str(strategy[0]),
        "policy_hash": str(strategy[1]),
        **strategy[2],
    }
    return {
        "target_protocol": fixture.targets.to_canonical_dict(),
        "trading_calendar": fixture.calendar.to_canonical_dict(),
        "evaluation_protocol": evaluation_payload,
        "feature_definition_set": feature_payload,
        "panel_enrichment": enrichment_payload,
        "factor_catalog": factor_payload,
        "threshold_policy": threshold_payload,
        "formal_oos_policy": oos[0],
        "calibration_protocol": calibration_protocol_payload,
        "calibration_policy": calibration[0],
        "strategy_policy": strategy_payload,
        "portfolio_policy": portfolio[0],
        "portfolio": portfolio[1],
        "entry_holding_exit_policy": entry[0],
        "actor": "phase-c-operator-test",
        "reason": "freeze typed Phase C owner package",
        "idempotency_key": "phase-c-operator-owner-package",
    }
