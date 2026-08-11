from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationObservation,
)
from market_regime_alpha.application.research_validation.formal_hypothesis_family import (
    FamilyEvaluationObservationBindings,
    FrozenHypothesisFamily,
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
    _consume_family_locked_oos,
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
    freeze_phase_c_protocol,
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
    repository = PostgresFormalProtocolRepository(postgres_factory)
    protocol = freeze_phase_c_protocol(
        postgres_factory, fixture, idempotency_key="locked-oos-protocol-legacy"
    )
    forecasts = tuple(
        build_outcome_target_bound_forecast(
            target_protocol=fixture.targets,
            symbol="000001.SZ",
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
            source_references=(
                _reference("FROZEN_DECISION", f"decision-{index}"),
            ),
            model_reference=protocol.model_reference,
            created_at=NOW,
        )
        for index in (1, 2)
    )
    for forecast in forecasts:
        repository.record_forecast(forecast)

    target = protocol.target_references[0]
    labels = (
        _reference("TARGET_OUTCOME_LABEL", "underlying-oos-label-x-revision-1"),
        _reference("TARGET_OUTCOME_LABEL", "underlying-oos-label-x-revision-2"),
    )
    bindings = tuple(
        FormalEvaluationObservationBinding.create(
            forecast_reference=ValidationArtifactReference(
                "OUTCOME_TARGET_BOUND_FORECAST",
                forecast.forecast_id,
                forecast.forecast_hash,
            ),
            label_reference=labels[index - 1],
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

    def consume(index: int) -> str:
        try:
            postgres_factory.run_transaction(
                lambda connection: _consume_locked_oos_evidence(
                    connection,
                    formal_protocol=protocol,
                    evaluation_protocol=fixture.evaluation,
                    target_reference=target,
                    observation_set_id=set_ids[index],
                    bindings=(bindings[index],),
                    observations=(observations[index],),
                )
            )
        except ResearchQualificationConflict as exc:
            assert "already formally consumed" in str(exc)
            return "REJECTED"
        return "CONSUMED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(consume, (0, 1)))
    assert sorted(results) == ["CONSUMED", "REJECTED"]

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
    assert _locked_oos_evidence_identity_payload(
        formal_protocol=protocol,
        target_reference=target,
        binding=bindings[0],
        observation=observations[0],
    ) == _locked_oos_evidence_identity_payload(
        formal_protocol=protocol,
        target_reference=target,
        binding=bindings[1],
        observation=observations[1],
    )

    substituted_target = _reference("OUTCOME_TARGET", "post-hoc-target-b")
    with pytest.raises(
        ResearchQualificationConflict, match="already formally consumed"
    ):
        postgres_factory.run_transaction(
            lambda connection: _consume_locked_oos_evidence(
                connection,
                formal_protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                target_reference=substituted_target,
                observation_set_id=set_ids[1],
                bindings=(bindings[1],),
                observations=(observations[1],),
            )
        )

    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT first_forecast_id, first_model_id, label_id, partition_kind
            FROM locked_oos_evidence_consumption
            """
        ).fetchone()
    assert row[0] in {str(item.forecast_id) for item in forecasts}
    assert row[1] == str(protocol.model_reference.artifact_id)
    assert row[2] in {str(item.artifact_id) for item in labels}
    assert row[3] == "LOCKED_OOS"

    family = repository.get_hypothesis_family(protocol.protocol_id)
    family_group = FamilyEvaluationObservationBindings(
        target_reference=target,
        panel_reference=_reference("RESEARCH_PANEL_V2", "locked-oos-panel"),
        observation_bindings=(bindings[0],),
    )
    with pytest.raises(ResearchQualificationConflict, match="legacy Formal Evaluation"):
        postgres_factory.run_transaction(
            lambda connection: _consume_family_locked_oos(
                connection,
                protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                family=family,
                observation_sets=(
                    (
                        ValidationArtifactReference(
                            "FORMAL_EVALUATION_OBSERVATION_SET",
                            set_ids[0],
                            canonical_hash(
                                {
                                    "schema_version": "formal-evaluation-observation-set/v1",
                                    "set_id": str(set_ids[0]),
                                }
                            ),
                        ),
                        family_group,
                        (observations[0],),
                    ),
                ),
                consumed_at=NOW,
            )
        )


def test_frozen_family_unlocks_one_raw_path_for_all_preregistered_targets(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    repository = PostgresFormalProtocolRepository(postgres_factory)
    protocol = freeze_phase_c_protocol(
        postgres_factory, fixture, idempotency_key="locked-oos-protocol-family"
    )
    family = repository.get_hypothesis_family(protocol.protocol_id)
    targets = protocol.target_references[:2]
    forecast = build_outcome_target_bound_forecast(
        target_protocol=fixture.targets,
        symbol="000001.SZ",
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
        source_references=(_reference("FROZEN_DECISION", "family-decision"),),
        model_reference=protocol.model_reference,
        created_at=NOW,
    )
    repository.record_forecast(forecast)
    forecast_reference = ValidationArtifactReference(
        "OUTCOME_TARGET_BOUND_FORECAST",
        forecast.forecast_id,
        forecast.forecast_hash,
    )
    set_references: list[ValidationArtifactReference] = []
    groups: list[FamilyEvaluationObservationBindings] = []
    observations: list[tuple[EvaluationObservation, ...]] = []
    panel_id = ArtifactId("family-locked-oos-panel")
    panel_payload = {
        "schema_version": "frozen-research-panel/v2",
        "fixture": "family-locked-oos-ledger-parent",
    }
    panel_hash = canonical_hash(panel_payload)
    panel_reference = ValidationArtifactReference(
        "RESEARCH_PANEL_V2", panel_id, panel_hash
    )
    for index, target in enumerate(targets, start=1):
        binding = FormalEvaluationObservationBinding.create(
            forecast_reference=forecast_reference,
            label_reference=_reference(
                "TARGET_OUTCOME_LABEL", f"family-oos-label-{index}"
            ),
            panel_slice_reference=_reference(
                "RESEARCH_PANEL_SLICE_V2", f"family-slice-{index}"
            ),
            panel_row_reference=_reference(
                "RESEARCH_PANEL_ROW_V2", f"family-row-{index}"
            ),
        )
        groups.append(
            FamilyEvaluationObservationBindings(
                target_reference=target,
                panel_reference=panel_reference,
                observation_bindings=(binding,),
            )
        )
        observations.append(
            (
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
                ),
            )
        )
        set_payload = {
            "schema_version": "formal-evaluation-observation-set/v1",
            "fixture": f"family-set-{index}",
        }
        set_references.append(
            ValidationArtifactReference(
                "FORMAL_EVALUATION_OBSERVATION_SET",
                ArtifactId(f"family-locked-oos-set-{index}"),
                canonical_hash(set_payload),
            )
        )

    def seed(connection: object) -> None:
        connection.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO research_evaluation_panel_v2(
                panel_id, panel_hash, target_protocol_id, target_protocol_hash,
                slice_count, row_count, payload_json, artifact_locator, created_at
            ) VALUES (%s, %s, %s, %s, 1, 1, %s, %s, %s)
            """,
            (
                str(panel_id),
                panel_hash,
                str(protocol.outcome_target_protocol_reference.artifact_id),
                protocol.outcome_target_protocol_reference.content_hash,
                Jsonb(panel_payload),
                "/fixture/family-locked-oos-panel.json",
                NOW,
            ),
        )
        for index, (set_reference, target) in enumerate(
            zip(set_references, targets, strict=True), start=1
        ):
            connection.execute(  # type: ignore[attr-defined]
                """
                INSERT INTO formal_evaluation_observation_set(
                    observation_set_id, observation_set_hash,
                    formal_protocol_id, panel_id, target_protocol_id,
                    target_id, target_hash, observation_count,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
                """,
                (
                    str(set_reference.artifact_id),
                    set_reference.content_hash,
                    str(protocol.protocol_id),
                    str(panel_id),
                    str(protocol.outcome_target_protocol_reference.artifact_id),
                    str(target.artifact_id),
                    target.content_hash,
                    Jsonb(
                        {
                            "schema_version": "formal-evaluation-observation-set/v1",
                            "fixture": f"family-set-{index}",
                        }
                    ),
                    NOW,
                ),
            )

    postgres_factory.run_transaction(seed)
    consumption_scope = tuple(
        (set_reference, group, target_observations)
        for set_reference, group, target_observations in zip(
            set_references, groups, observations, strict=True
        )
    )
    def consume_exact(_: int) -> str:
        postgres_factory.run_transaction(
            lambda connection: _consume_family_locked_oos(
                connection,
                protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                family=family,
                observation_sets=consumption_scope,
                consumed_at=NOW,
            )
        )
        return "CONSUMED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert tuple(executor.map(consume_exact, (1, 2))) == (
            "CONSUMED",
            "CONSUMED",
        )
    postgres_factory.run_transaction(
        lambda connection: _consume_family_locked_oos(
            connection,
            protocol=protocol,
            evaluation_protocol=fixture.evaluation,
            family=family,
            observation_sets=consumption_scope,
            consumed_at=NOW,
        )
    )

    substituted_binding = FormalEvaluationObservationBinding.create(
        forecast_reference=forecast_reference,
        label_reference=_reference(
            "TARGET_OUTCOME_LABEL", "family-oos-label-revision"
        ),
        panel_slice_reference=groups[0].observation_bindings[0].panel_slice_reference,
        panel_row_reference=groups[0].observation_bindings[0].panel_row_reference,
    )
    substituted_group = FamilyEvaluationObservationBindings(
        target_reference=targets[0],
        panel_reference=panel_reference,
        observation_bindings=(substituted_binding,),
    )
    substituted_observation = EvaluationObservation(
        observation_id=substituted_binding.observation_id,
        session_date=observations[0][0].session_date,
        label_end_date=observations[0][0].label_end_date,
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
    with pytest.raises(ResearchQualificationConflict, match="consumed differently"):
        postgres_factory.run_transaction(
            lambda connection: _consume_family_locked_oos(
                connection,
                protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                family=family,
                observation_sets=(
                    (
                        set_references[0],
                        substituted_group,
                        (substituted_observation,),
                    ),
                ),
                consumed_at=NOW,
            )
        )

    alternate_forecast = build_outcome_target_bound_forecast(
        target_protocol=fixture.targets,
        symbol=forecast.symbol,
        decision_time=forecast.decision_time,
        estimates=forecast.estimates,
        source_references=(_reference("FROZEN_DECISION", "alternate-forecast"),),
        model_reference=protocol.model_reference,
        created_at=forecast.created_at,
    )
    repository.record_forecast(alternate_forecast)
    alternate_binding = FormalEvaluationObservationBinding.create(
        forecast_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_BOUND_FORECAST",
            alternate_forecast.forecast_id,
            alternate_forecast.forecast_hash,
        ),
        label_reference=groups[0].observation_bindings[0].label_reference,
        panel_slice_reference=groups[0].observation_bindings[0].panel_slice_reference,
        panel_row_reference=groups[0].observation_bindings[0].panel_row_reference,
    )
    alternate_group = FamilyEvaluationObservationBindings(
        target_reference=targets[0],
        panel_reference=panel_reference,
        observation_bindings=(alternate_binding,),
    )
    with pytest.raises(ResearchQualificationConflict, match="consumed differently"):
        postgres_factory.run_transaction(
            lambda connection: _consume_family_locked_oos(
                connection,
                protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                family=family,
                observation_sets=(
                    (
                        set_references[0],
                        alternate_group,
                        (substituted_observation,),
                    ),
                ),
                consumed_at=NOW,
            )
        )

    revised_target = ValidationArtifactReference(
        "OUTCOME_TARGET",
        targets[0].artifact_id,
        canonical_hash({"target_revision": "post-oos"}),
    )
    revised_target_group = FamilyEvaluationObservationBindings(
        target_reference=revised_target,
        panel_reference=panel_reference,
        observation_bindings=groups[0].observation_bindings,
    )
    with pytest.raises(ResearchQualificationConflict, match="consumed differently"):
        postgres_factory.run_transaction(
            lambda connection: _consume_family_locked_oos(
                connection,
                protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                family=family,
                observation_sets=(
                    (
                        set_references[0],
                        revised_target_group,
                        observations[0],
                    ),
                ),
                consumed_at=NOW,
            )
        )

    for role, revised_reference in (
        (
            "dataset_reference",
            _reference("MARKET_DATA_DATASET", "post-oos-dataset-revision"),
        ),
        (
            "model_reference",
            _reference("MODEL_VERSION_LINEAGE", "post-oos-model-revision"),
        ),
    ):
        revised_payload = protocol.identity_payload()
        revised_payload[role] = revised_reference.to_canonical_dict()
        revised_hash = canonical_hash(revised_payload)
        revised_protocol = FormalResearchProtocol.from_canonical_dict(
            {
                "protocol_id": f"formal-research-protocol:{revised_hash[7:]}",
                "protocol_hash": revised_hash,
                **revised_payload,
            }
        )
        revised_family = FrozenHypothesisFamily.create(
            formal_protocol_reference=ValidationArtifactReference(
                "FORMAL_RESEARCH_PROTOCOL",
                revised_protocol.protocol_id,
                revised_protocol.protocol_hash,
            ),
            evaluation_protocol=fixture.evaluation,
            target_references=revised_protocol.target_references,
            frozen_at=NOW,
        )
        with pytest.raises(
            ResearchQualificationConflict, match="another frozen family"
        ):
            postgres_factory.run_transaction(
                lambda connection: _consume_family_locked_oos(
                    connection,
                    protocol=revised_protocol,
                    evaluation_protocol=fixture.evaluation,
                    family=revised_family,
                    observation_sets=(consumption_scope[0],),
                    consumed_at=NOW,
                )
            )

    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM locked_oos_raw_evidence_unlock"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM locked_oos_target_observation_consumption"
        ).fetchone()[0] == 2

    with pytest.raises(ResearchQualificationConflict, match="frozen family"):
        postgres_factory.run_transaction(
            lambda connection: _consume_locked_oos_evidence(
                connection,
                formal_protocol=protocol,
                evaluation_protocol=fixture.evaluation,
                target_reference=targets[0],
                observation_set_id=set_references[0].artifact_id,
                bindings=groups[0].observation_bindings,
                observations=observations[0],
            )
        )
