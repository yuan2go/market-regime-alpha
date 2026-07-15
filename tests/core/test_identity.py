from __future__ import annotations

import pytest

from market_regime_alpha.core.identity import DatasetId, ExperimentId, StableId


def test_stable_id_is_immutable_and_stringifiable() -> None:
    identifier = DatasetId("dataset-v1")
    assert str(identifier) == "dataset-v1"
    with pytest.raises(AttributeError):
        identifier.value = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", ["", " leading", "trailing ", "line\nbreak"])
def test_stable_id_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(ValueError):
        StableId(value)


def test_distinct_identity_types_do_not_compare_equal() -> None:
    assert DatasetId("same") != ExperimentId("same")
