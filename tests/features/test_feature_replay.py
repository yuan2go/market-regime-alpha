from dataclasses import replace
from pathlib import Path

import pytest

from market_regime_alpha.features.artifact import (
    bind_feature_artifact_identity,
    publish_feature_artifact,
    replay_feature_artifact,
)
from market_regime_alpha.features.technical.moving_average import (
    MovingAverageObservation,
    SimpleMovingAverageComputer,
)

from .test_moving_average import _request


def test_feature_replay_is_deterministic(tmp_path: Path) -> None:
    artifact = SimpleMovingAverageComputer().compute(_request())
    path = publish_feature_artifact(root=tmp_path, artifact=artifact)

    verified = replay_feature_artifact(path)

    assert verified.artifact.to_canonical_dict() == artifact.to_canonical_dict()


def test_feature_replay_detects_a_semantically_valid_but_false_output(
    tmp_path: Path,
) -> None:
    original = SimpleMovingAverageComputer().compute(_request())
    observations = list(original.observations)
    final = observations[-1]
    assert isinstance(final, MovingAverageObservation)
    dishonest_value = final.value + 1 if final.value else None
    observations[-1] = replace(final, value=dishonest_value)
    dishonest = bind_feature_artifact_identity(
        replace(original, observations=tuple(observations), score=dishonest_value)
    )
    path = publish_feature_artifact(root=tmp_path, artifact=dishonest)

    with pytest.raises(ValueError, match="replay differs"):
        replay_feature_artifact(path)
