from __future__ import annotations

from market_regime_alpha.daily_research.artifacts import (
    DAILY_QUANT_DECISION_IMPLEMENTATION_MODULES,
    DAILY_QUANT_DECISION_SCHEMA_VERSION,
    implementation_module_hashes,
)
from market_regime_alpha.daily_research.contracts import (
    CANDIDATE_RECOMMENDATION_SCHEMA_VERSION,
    DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION,
    ENTRY_ASSESSMENT_SCHEMA_VERSION,
    DailyDataAuthority,
    DecisionDataQuality,
    EntryState,
    InstrumentType,
)

from .conftest import make_entry, make_recommendation, make_snapshot


EXPECTED_V1_MODULE_HASHES = {
    "_contract_support.py": "sha256:4b30db054ad541a8230510ed25b9deb83de3868208e3d1086c46b5307e2245b7",
    "artifacts.py": "sha256:c632ed5595e5b552b82e686f083777dcb195b3e3e7fc2d3caddeee2bbd53cb54",
    "contracts.py": "sha256:d0b42f10f4f0c22784d7b9635f507ef8ff6b8dbe2a224cb3665477b7c5ca8309",
    "entry.py": "sha256:c80131d9dd29fc4c8d655d83b3dfef7966b93cba161424e212c369a77b780cfc",
    "policy.py": "sha256:4fd823f8f9b9494324b231e8c5a6ebf2eee77682c7b259a8b5acc346565b88e3",
    "reader.py": "sha256:a17a7c279c4fc704a7455864c5817e8a2238b1e3d36a2e1c1c0dccf8a13661a1",
    "recommendation.py": "sha256:5219646e12f51f14136827241381c0b7a32285239712a9461a7e8d4aa9b42b39",
    "report.py": "sha256:cb1b719eaa147f41f7d0244e9252a80b63a5d7548173f70b1bc7f7f692fad169",
    "snapshot.py": "sha256:03381455bfc97ef9b1b587af9405c83eda08613ed4a787e9c138c7685f8b90ee",
}


def test_v1_implementation_module_set_and_bytes_are_frozen() -> None:
    assert set(DAILY_QUANT_DECISION_IMPLEMENTATION_MODULES) == set(EXPECTED_V1_MODULE_HASHES)
    assert implementation_module_hashes() == EXPECTED_V1_MODULE_HASHES


def test_v1_schema_versions_and_enums_are_frozen() -> None:
    assert DAILY_QUANT_DECISION_SCHEMA_VERSION == "daily-quant-decision-artifact-v1"
    assert DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION == "daily-research-snapshot-v1"
    assert CANDIDATE_RECOMMENDATION_SCHEMA_VERSION == "candidate-recommendation-v1"
    assert ENTRY_ASSESSMENT_SCHEMA_VERSION == "entry-assessment-v1"
    assert tuple(item.value for item in DailyDataAuthority) == (
        "EXPLORATORY",
        "AUXILIARY",
        "TEST_ONLY_NOT_RESEARCH_EVIDENCE",
    )
    assert tuple(item.value for item in DecisionDataQuality) == (
        "COMPLETE",
        "DEGRADED",
        "INSUFFICIENT",
    )
    assert tuple(item.value for item in InstrumentType) == ("A_SHARE_STOCK", "ETF")
    assert tuple(item.value for item in EntryState) == (
        "ENTER",
        "WAIT_PULLBACK",
        "WAIT_CONFIRMATION",
        "REJECT",
    )


def test_v1_canonical_json_field_sets_are_frozen() -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    entry = make_entry(snapshot, recommendation)

    assert set(snapshot.to_canonical_dict()) == {
        "schema_version",
        "snapshot_id",
        "decision_date",
        "decision_time",
        "timezone",
        "universe_identity",
        "market_data_identity",
        "feature_registry_identity",
        "registered_component_identities",
        "model_identity",
        "configuration_identity",
        "market_context_identity",
        "etf_snapshot_identity",
        "theme_snapshot_identity",
        "holdings_identity",
        "source_artifacts",
        "data_authority",
        "created_at",
        "content_hash",
    }
    assert set(recommendation.to_canonical_dict()) == {
        "schema_version",
        "recommendation_id",
        "decision_snapshot_id",
        "instrument_type",
        "symbol",
        "candidate_rank",
        "candidate_score",
        "score_components",
        "industry",
        "themes",
        "related_etfs",
        "selection_reasons",
        "risk_reasons",
        "expected_horizon",
        "target_definition",
        "invalidation_conditions",
        "data_quality",
        "model_identity",
        "data_authority",
        "content_hash",
    }
    assert set(entry.to_canonical_dict()) == {
        "schema_version",
        "entry_assessment_id",
        "decision_snapshot_id",
        "recommendation_id",
        "entry_state",
        "entry_score",
        "entry_reasons",
        "blocking_reasons",
        "reference_price",
        "preferred_price_zone",
        "maximum_acceptable_price",
        "invalidation_price",
        "expected_mfe",
        "expected_mae",
        "risk_reward_estimate",
        "uncertainty",
        "model_identity",
        "configuration_identity",
        "data_authority",
        "content_hash",
    }
