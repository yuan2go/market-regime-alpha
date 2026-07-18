from pathlib import Path
from types import MappingProxyType

import pytest

from market_regime_alpha.research.research_artifact_verifier_registry import (
    RESEARCH_ARTIFACT_VERIFIER_REGISTRY,
    ArtifactVerifierRegistration,
    build_verifier_registry,
)


class _Verified:
    root = Path(".")
    run_id = "run"
    manifest = MappingProxyType({"schema_version": "test"})


def test_new_registry_routes_all_f2b_schema_versions() -> None:
    assert set(RESEARCH_ARTIFACT_VERIFIER_REGISTRY) == {
        "mr-2b-f2b-run-v1",
        "mr-2b-f2b-run-v2",
        "mr-2b-f2b-run-v3",
    }


def test_new_registry_rejects_duplicate_registration() -> None:
    registration = ArtifactVerifierRegistration("test", "test-reader", lambda **_: _Verified())
    with pytest.raises(ValueError, match="duplicate"):
        build_verifier_registry((registration, registration))
