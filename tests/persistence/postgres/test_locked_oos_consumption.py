from __future__ import annotations

from datetime import date

import pytest
from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationObservation,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    OutcomeTargetForecastEstimate,
    OutcomeTargetForecastStatus,
    build_outcome_target_bound_forecast,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.application.research_validation.postgres_qualification import (
    ResearchQualificationConflict,
    _consume_locked_oos_evidence,
    _locked_oos_evidence_identity_payload,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalEvaluationObservationBinding,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.phase_c_owner_fixture import (
    NOW,
    record_phase_c_protocol_owners,
)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_locked_oos_consumption_is_label_evidence_not_forecast_identity(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    protocol = fixture.protocol
    repository = PostgresFormalProtocolRepository(postgres_factory)
    repository.record_protocol(protocol=protocol)
    forecasts = tuple(
        build_outcome_target_bound_forecast(
            target_protocol=fixture.targets,
            symbol=symbol,
            decision_time=NOW,
            estimates=tuple(
                OutcomeTargetForecastEstimate(
                    target.target_id,
                    target.target_hash,
                    OutcomeTargetForecastStatus.NOT_ESTIMABLE,
                    None,
                    None,
                    None,
                    None,
                    (),
                    ("TEST_NO_ESTIMATE",),
                )
                for target in fixture.targets.targets
            ),
            source_references=(_reference("FROZEN_DECISION", f"decision-{symbol}"),),
            model_reference=protocol.model_reference,
            created_at=NOW,
        )
        for symbol in ("000001.SZ", "000002.SZ")
    )
    for forecast in forecasts:
        repository.record_forecast(forecast)

    target = protocol.target_references[0]
    label = _reference("TARGET_OUTCOME_LABEL", "underlying-oos-label-x")
    bindings = tuple(
        FormalEvaluationObservationBinding.create(
            forecast_reference=ValidationArtifactReference(
                "OUTCOME_TARGET_BOUND_FORECAST",
                forecast.forecast_id,
                forecast.forecast_hash,
            ),
            label_reference=label,
            panel_slice_reference=_reference("RESEARCH_PANEL_SLICE_V2", "slice"),
            panel_row_reference=_reference(
                "RESEARCH_PANEL_ROW_V2", f"row-{index}"
            ),
        )
        for index, forecast in enumerate(forecasts, start=1)
    )
    observations = tuple(
        EvaluationObservation(
            observation_id=binding.observation_id,
            session_date=date(2026, 1, 22),
            label_end_date=date(2026, 1, 23),
            symbol=forecast.symbol,
            score=0,
            realized_return=0,
            mfe=None,
            mae=None,
            regime="UNKNOWN",
            liquidity_slice="UNKNOWN",
            market_cap_slice="UNKNOWN",
            theme_slice="UNKNOWN",
        )
        for binding, forecast in zip(bindings, forecasts, strict=True)
    )
    set_ids = tuple(ArtifactId(f"locked-oos-set-{index}") for index in (1, 2))

    def seed_parents(connection: object) -> None:
        panel_payload = {
            "schema_version": "frozen-research-panel/v2",
            "fixture": "locked-oos-ledger-parent",
        }
        panel_hash = canonical_hash(panel_payload)
        connection.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO research_evaluation_panel_v2(
                panel_id, panel_hash, target_protocol_id, target_protocol_hash,
                slice_count, row_count, payload_json, artifact_locator, created_at
            ) VALUES ('locked-oos-panel', %s, %s, %s, 1, 1, %s, %s, %s)
            """,
            (
                panel_hash,
                str(protocol.outcome_target_protocol_reference.artifact_id),
                protocol.outcome_target_protocol_reference.content_hash,
                Jsonb(panel_payload),
                "/fixture/locked-oos-panel.json",
                NOW,
            ),
        )
        for set_id in set_ids:
            payload = {
                "schema_version": "formal-evaluation-observation-set/v1",
                "set_id": str(set_id),
            }
            connection.execute(  # type: ignore[attr-defined]
                """
                INSERT INTO formal_evaluation_observation_set(
                    observation_set_id, observation_set_hash,
                    formal_protocol_id, panel_id, target_protocol_id,
                    target_id, target_hash, observation_count,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, 'locked-oos-panel', %s, %s, %s, 1, %s, %s)
                """,
                (
                    str(set_id),
                    canonical_hash(payload),
                    str(protocol.protocol_id),
                    str(protocol.outcome_target_protocol_reference.artifact_id),
                    str(target.artifact_id),
                    target.content_hash,
                    Jsonb(payload),
                    NOW,
                ),
            )

    postgres_factory.run_transaction(seed_parents)
    postgres_factory.run_transaction(
        lambda connection: _consume_locked_oos_evidence(
            connection,
            formal_protocol=protocol,
            evaluation_protocol=fixture.evaluation,
            target_reference=target,
            observation_set_id=set_ids[0],
            bindings=(bindings[0],),
            observations=(observations[0],),
        )
    )
    with pytest.raises(
        ResearchQualificationConflict,
        match="already formally consumed",
    ):
        postgres_factory.run_transaction(
            lambda connection: _consume_locked_oos_evidence(
                connection,
                formal_protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                target_reference=target,
                observation_set_id=set_ids[1],
                bindings=(bindings[1],),
                observations=(observations[1],),
            )
        )

    changed_payload = protocol.identity_payload()
    changed_payload["model_reference"] = _reference(
        "MODEL_VERSION_LINEAGE", "model-b"
    ).to_canonical_dict()
    changed_hash = canonical_hash(changed_payload)
    model_b_protocol = FormalResearchProtocol.from_canonical_dict(
        {
            "protocol_id": f"formal-research-protocol:{changed_hash[7:]}",
            "protocol_hash": changed_hash,
            **changed_payload,
        }
    )
    assert _locked_oos_evidence_identity_payload(
        formal_protocol=protocol,
        target_reference=target,
        binding=bindings[0],
        observation=observations[0],
    ) == _locked_oos_evidence_identity_payload(
        formal_protocol=model_b_protocol,
        target_reference=target,
        binding=bindings[0],
        observation=observations[0],
    )

    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT first_forecast_id, first_model_id, label_id, partition_kind
            FROM locked_oos_evidence_consumption
            """
        ).fetchone()
    assert row == (
        str(forecasts[0].forecast_id),
        str(protocol.model_reference.artifact_id),
        str(label.artifact_id),
        "LOCKED_OOS",
    )
