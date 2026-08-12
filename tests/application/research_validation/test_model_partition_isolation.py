from __future__ import annotations

from dataclasses import replace

import pytest

from tests.application.research_validation.test_research_model import _request


def test_validation_cannot_precede_training_and_embargo_reaches_locked_oos() -> None:
    request = _request()
    reverse = replace(
        request.folds[0],
        train_sample_ids=request.folds[0].validation_sample_ids,
        validation_sample_ids=request.folds[0].train_sample_ids,
    )
    with pytest.raises(ValueError, match="training must precede validation"):
        _request(folds=(reverse, request.folds[1]))

    excessive_embargo = replace(request.folds[1], embargo_sessions=3)
    with pytest.raises(ValueError, match="embargo window"):
        _request(folds=(request.folds[0], excessive_embargo))
