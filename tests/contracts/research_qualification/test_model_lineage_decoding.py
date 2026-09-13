"""The read-only lineage consumer preserves both registered baseline formats."""

import json

import pytest

from market_regime_alpha.infrastructure.postgres.queries.model_lineage import _decode_fitted_artifact
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def _artifact(version, kind):
    return json.dumps({"schema": f"mra-research-baseline-v{version}", "kind": kind,
        "feature_definition_ids": ["00000000-0000-0000-0000-000000000001"],
        "intercept": "2.5" if kind == "TRAINING_MEDIAN" else "0", "coefficient": "0",
        "seed": 18, "sample_roster_sha256": "a" * 64}, sort_keys=True, separators=(",", ":")).encode()


@pytest.mark.parametrize("version,kind", [(1, "ZERO"), (2, "ZERO"), (2, "TRAINING_MEDIAN")])
def test_lineage_decodes_each_registered_baseline_format(version, kind):
    model = _decode_fitted_artifact("research_baseline", f"{version}.0.0", _artifact(version, kind))
    assert model.format_version == version and model.kind == kind


@pytest.mark.parametrize("algorithm_version,artifact_version", [("1.0.0", 2), ("2.0.0", 1)])
def test_lineage_refuses_cross_version_artifact_identity(algorithm_version, artifact_version):
    with pytest.raises(ArtifactIntegrityError, match="MODEL_FITTED_ALGORITHM_VERSION_DIFFERS"):
        _decode_fitted_artifact("research_baseline", algorithm_version, _artifact(artifact_version, "ZERO"))


def test_lineage_does_not_infer_support_for_future_baseline_versions():
    with pytest.raises(ArtifactIntegrityError, match="MODEL_LINEAGE_UNSUPPORTED_ARTIFACT_ALGORITHM"):
        _decode_fitted_artifact("research_baseline", "3.0.0", _artifact(2, "TRAINING_MEDIAN"))
