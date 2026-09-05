from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.interfaces.wp17p_models import wp17p_model_plan
from market_regime_alpha.research_qualification.domain import ArtifactBinding


@pytest.mark.parametrize(
    ("generation", "expected_code"),
    [(1, "wp17p_deterministic_ridge"), (2, "wp18_deterministic_ridge")],
)
def test_model_plan_freezes_exact_target_feature_and_artifacts(
    generation: int, expected_code: str
) -> None:
    artifact = ArtifactBinding(uuid4(), "a" * 64, 9)
    catalog = SimpleNamespace(
        target=SimpleNamespace(
            target_definition_id=uuid4(),
            version=1,
            content_sha256="b" * 64,
        ),
        feature=SimpleNamespace(
            feature_definition_id=uuid4(),
            content_sha256="c" * 64,
        ),
        backtest=SimpleNamespace(
            generation=generation,
            exploratory_backtest_run_id=uuid4(),
            code_artifact=artifact,
            config_artifact=artifact,
            provenance_sha256="d" * 64,
        ),
    )

    plan = wp17p_model_plan(catalog)

    assert plan.target_definition_id == catalog.target.target_definition_id
    assert tuple(
        (identity, str(content_hash))
        for identity, content_hash in plan.feature_definitions
    ) == (
        (catalog.feature.feature_definition_id, catalog.feature.content_sha256),
    )
    assert plan.code_artifact == artifact
    assert plan.model_code == expected_code
