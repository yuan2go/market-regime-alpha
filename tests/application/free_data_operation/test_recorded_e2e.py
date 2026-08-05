from __future__ import annotations

from pathlib import Path

import pytest

from market_regime_alpha.application.free_data_operation import (
    prepare_free_data_inputs,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.data.providers.public_composite import (
    load_verified_public_source_stage_artifact,
)
from market_regime_alpha.universe import load_operational_universe
from tests.application.free_data_operation.test_builders import (
    _request,
    _source_inputs,
)


@pytest.mark.parametrize("count", (20, 100, 300))
def test_recorded_scales_have_stable_hashes_and_fail_closed_without_theme_evidence(
    tmp_path: Path,
    count: int,
) -> None:
    roots = (tmp_path / "first", tmp_path / "replay")
    results = []
    for root in roots:
        stage_path, provider_result, source_manifest = _source_inputs(
            root,
            count=count,
        )
        results.append(
            prepare_free_data_inputs(
                request=_request(count),
                history_source=load_verified_public_source_stage_artifact(
                    stage_path
                ),
                provider_result=provider_result,
                full_source_manifest=source_manifest,
                output_root=root,
            )
        )

    first, replayed = results
    assert replayed.manifest == first.manifest
    assert load_operational_universe(first.paths.operational_universe).symbols == (
        _request(count).symbols
    )
    evidence = load_verified_supplemental_research_evidence(
        first.paths.supplemental_research_evidence
    ).bundle
    assert len(evidence.symbol_observations) == count
    assert evidence.theme_observations == ()
    assert evidence.capital_observations == ()
    assert len(
        [
            item
            for item in evidence.missing_evidence
            if item.evidence_kind == "THEME_MEMBERSHIP"
        ]
    ) == count
    assert "TRADING_AUTHORITY_NOT_GRANTED" in evidence.reason_codes
    assert not tuple(tmp_path.rglob("*manual*trade*"))
    assert not tuple(tmp_path.rglob("*fill*"))
    assert not tuple(tmp_path.rglob("*broker*"))
