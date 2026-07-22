from datetime import date, datetime, timezone

from market_regime_alpha.research.pit_partition_v2 import (
    PartitionOpenReceipt,
    ValidationPartitionSpecification,
    seal_validation_partition,
)
from market_regime_alpha.research.pit_replication_success_v2 import PITReplicationSuccessInputs
from market_regime_alpha.research.pit_replication_success_v2_features import (
    frozen_b1e_feature_registry,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    frozen_pit_replication_success_v2_protocol,
)


def build_test_success_inputs() -> PITReplicationSuccessInputs:
    protocol = frozen_pit_replication_success_v2_protocol(test_only=True)
    dates = (date(2026, 1, 5), date(2026, 1, 6))
    symbols = tuple(f"00000{index}.SZ" for index in range(1, 7))
    created = datetime(2025, 12, 31, tzinfo=timezone.utc)
    specification = ValidationPartitionSpecification(
        "pit-validation-partition-specification-v1",
        "TEST_ONLY_VALIDATION_PARTITION",
        "XUNTOU",
        "EXPLICIT_DATE_RANGE_V1",
        dates[0],
        dates[-1],
        2,
        "NO_RESULT_DRIVEN_EXCLUSIONS_V1",
        protocol.protocol_id,
        protocol.ranking_model_spec_hash,
        created,
        "SPECIFIED_NOT_OPENED",
    )
    seal = seal_validation_partition(
        specification,
        included_sessions=dates,
        excluded_sessions=(),
        development_sessions=(),
        calendar_identity="test-calendar",
        provider_source_hashes=("sha256:" + "1" * 64,),
        universe_identity="test-pit-universe",
        sealed_at=created,
    )
    receipt = PartitionOpenReceipt(
        "pit-validation-partition-open-receipt-v1",
        specification.partition_id,
        created,
        "PENDING",
        "sha256:" + "2" * 64,
        seal.partition_content_hash,
    )
    universe = []
    eligibility = []
    orderability = []
    population = []
    features = []
    marks = []
    registry = frozen_b1e_feature_registry()
    for date_index, decision_date in enumerate(dates):
        decision_time = f"{decision_date.isoformat()}T14:55:00+08:00"
        for symbol_index, symbol in enumerate(symbols):
            key = f"{decision_date.isoformat()}|{symbol}"
            universe.append(
                {"decision_date": decision_date.isoformat(), "symbol": symbol, "decision_time": decision_time, "is_member": True, "membership_source": "HISTORICAL_PIT_COMPLETE", "row_id": "u|" + key}
            )
            eligibility.append(
                {"decision_date": decision_date.isoformat(), "symbol": symbol, "decision_time": decision_time, "status": "ELIGIBLE", "buyability": "RESEARCH_ORDERABLE", "row_id": "e|" + key}
            )
            orderability.append(
                {"decision_date": decision_date.isoformat(), "symbol": symbol, "decision_time": decision_time, "orderability_status": "RESEARCH_ORDERABLE", "evidence_id": "o|" + key}
            )
            population.append(
                {
                    "decision_date": decision_date.isoformat(),
                    "symbol": symbol,
                    "dataset_id": "test-provider-artifact",
                    "universe_row_id": "u|" + key,
                    "eligibility_row_id": "e|" + key,
                    "orderability_evidence_id": "o|" + key,
                    "decision_time": decision_time,
                }
            )
            for feature_index, definition in enumerate(registry):
                features.append(
                    {
                        "decision_date": decision_date.isoformat(),
                        "symbol": symbol,
                        "decision_time": decision_time,
                        "feature_id": definition.feature_id,
                        "feature_value": float((symbol_index + 1) * (feature_index + 1) + date_index),
                        "feature_observed_at": decision_time,
                        "feature_available_at": decision_time,
                        "feature_status": "AVAILABLE",
                        "feature_rejection_reason": None,
                    }
                )
            marks.append(
                {
                    "decision_date": decision_date.isoformat(),
                    "symbol": symbol,
                    "evaluation_mark_id": protocol.primary_evaluation_mark_id,
                    "evaluation_time": "10:30",
                    "reference_price": 10.0,
                    "evaluation_price": 10.0 * (1.0 + 0.001 * (symbol_index + 1 + date_index)),
                    "mark_status": "AVAILABLE",
                    "fallback_close_price": None,
                }
            )
    return PITReplicationSuccessInputs(
        provider_artifact_id="test-provider-artifact",
        provider_source_hashes=("sha256:" + "1" * 64,),
        provider_source_content_hash="sha256:" + "3" * 64,
        pit_qualification={
            "pit_correct_for_scope": True,
            "evidence_classification": "TEST_ONLY_NOT_RESEARCH_EVIDENCE",
        },
        partition_specification=specification,
        partition_seal=seal,
        partition_open_receipt=receipt,
        amount_unit_contract={
            "currency": "CNY",
            "unit": "YUAN",
            "scale": 1.0,
            "aggregation": "SUM_NATIVE_PERIOD_AMOUNT",
            "adjustment_basis": "NONE",
            "provider_field": "amount",
            "evidence_source": "TEST_ONLY",
        },
        universe_rows=tuple(universe),
        eligibility_rows=tuple(eligibility),
        orderability_rows=tuple(orderability),
        population_rows=tuple(population),
        feature_rows=tuple(features),
        evaluation_mark_rows=tuple(marks),
        path_rows=(),
        test_only=True,
    )
