from __future__ import annotations

from market_regime_alpha.forecasting.sample_provider import (
    UnavailablePathForecastSampleProvider,
)
from tests.forecasting.test_path_forecast import _config, _signal


def test_default_sample_provider_fails_closed_without_fabricating_samples() -> None:
    signal = _signal()
    batch = UnavailablePathForecastSampleProvider().load_samples(
        signal_snapshot=signal,
        configuration=_config(),
        decision_time=signal.envelope.decision_time,
    )

    assert batch.samples == ()
    assert batch.reason_codes == ("FORMAL_PATH_SAMPLE_PROVIDER_NOT_CONFIGURED",)
    assert "NO_SAMPLES_FABRICATED_FROM_CURRENT_SIGNAL" in batch.limitations
    assert "H9_SAMPLE_AUTHORITY_NOT_IMPLEMENTED" in batch.limitations
