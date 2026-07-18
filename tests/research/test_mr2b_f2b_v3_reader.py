from market_regime_alpha.research.mr2b_f2b_v3_artifacts import (
    F2B_V3_IMPLEMENTATION_MODULES,
)


def test_verifier_registry_is_not_part_of_f2b_v3_statistical_identity() -> None:
    assert "research_artifact_verifier_registry.py" not in F2B_V3_IMPLEMENTATION_MODULES
    assert "mr2b_verifier_registry.py" not in F2B_V3_IMPLEMENTATION_MODULES
    assert set(F2B_V3_IMPLEMENTATION_MODULES) == {
        "mr2b_f2b_v3_protocol.py",
        "mr2b_f2b_v3_statistics.py",
        "mr2b_f2b_v3_primary.py",
        "mr2b_f2b_v3_competing_events.py",
        "mr2b_f2b_v3.py",
        "mr2b_f2b_v3_artifacts.py",
        "mr2b_f2b_v3_reader.py",
    }
