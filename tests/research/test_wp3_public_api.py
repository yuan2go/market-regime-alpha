from __future__ import annotations

import market_regime_alpha.research as research


def test_wp3_public_api_exports_only_intended_composition_contracts() -> None:
    intended = {
        "CandidateDataSource",
        "CandidateRunSourceMode",
        "ProviderAvailabilityStatus",
        "ProviderCapabilityReport",
        "ProviderSelectionDecision",
        "ProviderRoutingError",
        "select_candidate_data_source",
        "ProviderCandidateRun",
        "ProviderCandidateRunOutcome",
        "run_provider_candidate_experiment",
        "WP3RunRequest",
        "execute_wp3_candidate_run",
    }

    assert intended <= set(research.__all__)
    for name in intended:
        assert getattr(research, name) is not None
    assert "_xuntou_report" not in research.__all__
    assert "_render_report" not in research.__all__
    assert "_source_artifact" not in research.__all__
