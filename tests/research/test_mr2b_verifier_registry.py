import pytest

from market_regime_alpha.research.mr2b_verifier_registry import (
    MR2B_VERIFIER_REGISTRY,
    ArtifactVerifierRegistration,
    build_verifier_registry,
)


def test_registry_keeps_historical_v1_and_current_v2_verifiers() -> None:
    assert set(MR2B_VERIFIER_REGISTRY) == {"mr-2b-f2b-run-v1", "mr-2b-f2b-run-v2"}
    assert MR2B_VERIFIER_REGISTRY["mr-2b-f2b-run-v1"].verifier_id == "mr2b-f2b-v1-semantic-reader"


def test_duplicate_verifier_registration_fails_closed() -> None:
    registration = ArtifactVerifierRegistration("same", "one", lambda *args, **kwargs: object())
    with pytest.raises(ValueError, match="duplicate"):
        build_verifier_registry((registration, registration))
