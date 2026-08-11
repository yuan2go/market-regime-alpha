from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    MultipleTestingMethod,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    OutcomeTargetForecastEstimate,
    OutcomeTargetForecastStatus,
    build_outcome_target_bound_forecast,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolConflict,
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


NOW = datetime(2026, 8, 11, 8, tzinfo=UTC)


def _ref(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind, ArtifactId(name), canonical_hash({"kind": kind, "name": name})
    )


def _component_payloads(
    protocol: FormalResearchProtocol,
) -> dict[str, dict[str, object]]:
    return {
        role: {"kind": reference.artifact_kind, "name": str(reference.artifact_id)}
        for role, reference in protocol.component_references().items()
    }


def test_protocol_and_outcome_target_forecast_replay_from_postgres(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    targets = engineering_multi_horizon_protocol()
    PostgresTargetOutcomeRepository(postgres_factory).register_protocol(targets)
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("formal-calendar-source"),
        market="XSHG-XSHE",
        calendar_version="phase-c0-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                date(2026, 1, day),
                datetime(2026, 1, day, 7, tzinfo=UTC),
            )
            for day in range(5, 31)
        ),
    )
    evaluation = FormalEvaluationProtocol.create(
        protocol_version="phase-c0-evaluation-v1",
        target_protocol=targets,
        windows=(
            EvaluationWindow("train", EvaluationPartition.TRAIN, date(2026, 1, 5), date(2026, 1, 12), 1),
            EvaluationWindow("validation", EvaluationPartition.VALIDATION, date(2026, 1, 13), date(2026, 1, 20), 1),
            EvaluationWindow("locked-oos", EvaluationPartition.LOCKED_OOS, date(2026, 1, 21), date(2026, 1, 30), 1),
        ),
        bootstrap_iterations=100,
        confidence_level=Decimal("0.95"),
        multiple_testing_method=MultipleTestingMethod.BONFERRONI,
        locked_at=NOW,
    )
    protocol = FormalResearchProtocol.create(
        protocol_version="phase-c0-v1",
        target_protocol=targets,
        trading_calendar=calendar,
        evaluation_protocol=evaluation,
        universe_reference=_ref("UNIVERSE", "universe-v1"),
        dataset_reference=_ref("DATASET", "dataset-v1"),
        historical_sample_dataset_reference=_ref(
            "HISTORICAL_SAMPLE_DATASET", "sample-dataset-v1"
        ),
        feature_reference=_ref("FEATURE_DEFINITION_SET", "features-v1"),
        factor_reference=_ref("FACTOR_CATALOG", "factors-v1"),
        model_reference=_ref("MODEL_VERSION_LINEAGE", "model-v1"),
        threshold_policy_reference=_ref("THRESHOLD_POLICY", "threshold-v1"),
        formal_oos_qualification_policy_reference=_ref(
            "FORMAL_OOS_QUALIFICATION_POLICY", "formal-oos-v1"
        ),
        cost_policy_reference=_ref("SHADOW_PORTFOLIO_POLICY", "cost-v1"),
        calibration_policy_reference=_ref("CALIBRATION_POLICY", "calibration-v1"),
        strategy_policy_reference=_ref("STRATEGY_SHADOW_POLICY", "strategy-v1"),
        entry_holding_exit_qualification_policy_reference=_ref(
            "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY", "entry-exit-v1"
        ),
        locked_at=NOW,
    )
    repository = PostgresFormalProtocolRepository(postgres_factory)
    component_payloads = _component_payloads(protocol)
    component_payloads["trading_calendar_reference"] = calendar.semantic_payload()

    assert repository.record_protocol(
        protocol=protocol,
        target_protocol=targets,
        evaluation_protocol=evaluation,
        component_payloads=component_payloads,
    ) == protocol
    forged_payload = protocol.identity_payload()
    forged_payload["frozen_trading_dates"] = [
        item
        for item in forged_payload["frozen_trading_dates"]
        if item != "2026-01-15"
    ]
    forged_hash = canonical_hash(forged_payload)
    forged_calendar_projection = FormalResearchProtocol.from_canonical_dict(
        {
            "protocol_id": f"formal-research-protocol:{forged_hash[7:]}",
            "protocol_hash": forged_hash,
            **forged_payload,
        }
    )
    with pytest.raises(FormalProtocolConflict, match="Protocol dates diverge"):
        repository.record_protocol(
            protocol=forged_calendar_projection,
            target_protocol=targets,
            evaluation_protocol=evaluation,
            component_payloads=component_payloads,
        )
    forged = dict(component_payloads)
    forged["threshold_policy_reference"] = {"forged": True}
    with pytest.raises(FormalProtocolConflict, match="payload hash mismatch"):
        repository.record_protocol(
            protocol=protocol,
            target_protocol=targets,
            evaluation_protocol=evaluation,
            component_payloads=forged,
        )
    assert repository.record_protocol(
        protocol=protocol,
        target_protocol=targets,
        evaluation_protocol=evaluation,
        component_payloads=component_payloads,
    ) == protocol

    forecast = build_outcome_target_bound_forecast(
        target_protocol=targets,
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
                ("QUALIFIED_HISTORICAL_SAMPLE_MISSING",),
            )
            for target in targets.targets
        ),
        source_references=(_ref("FROZEN_DECISION", "decision-v1"),),
        model_reference=_ref("MODEL_VERSION_LINEAGE", "model-v1"),
        created_at=NOW,
    )
    assert repository.record_forecast(forecast) == forecast
    assert repository.record_forecast(forecast) == forecast

    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM formal_research_protocol"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM outcome_target_bound_forecast"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM outcome_target_bound_forecast_estimate"
        ).fetchone()[0] == len(targets.targets)
