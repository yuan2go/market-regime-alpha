from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from market_regime_alpha.application.research_layer.runner import (
    PlatformResearchRunner,
)
from market_regime_alpha.research.platform_v2.artifact import (
    RESEARCH_LAYER_ARTIFACT_FILES,
    ResearchLayerStatus,
)
from market_regime_alpha.research.platform_v2.configs import (
    default_research_pipeline_config,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundle
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)

from .test_candidate_discovery import _qualified


def _run(
    inputs: ResearchInputBundle, root: Path
):
    return PlatformResearchRunner().run(
        inputs=inputs,
        configuration=default_research_pipeline_config(),
        output_root=root,
        code_revision="fixture-code-revision",
    )


def test_research_pipeline_publishes_readable_exact_artifact(
    research_input_bundle: ResearchInputBundle,
    tmp_path: Path,
) -> None:
    verified = _run(_qualified(research_input_bundle), tmp_path)

    assert verified.artifact.research_status is ResearchLayerStatus.RESEARCH_RESTRICTED
    assert len(verified.artifact.candidate_set.selected) == 5
    assert {item.name for item in verified.root.iterdir()} == set(
        RESEARCH_LAYER_ARTIFACT_FILES
    )
    assert load_verified_research_artifact(verified.root) == verified


def test_research_pipeline_replay_is_fully_deterministic(
    research_input_bundle: ResearchInputBundle,
    tmp_path: Path,
) -> None:
    runner = PlatformResearchRunner()
    first = _run(_qualified(research_input_bundle), tmp_path)
    second = _run(_qualified(research_input_bundle), tmp_path)
    replayed = runner.replay(first.root)

    assert first.root == second.root == replayed.root
    assert first.artifact == second.artifact == replayed.artifact
    assert first.checksums_hash == second.checksums_hash == replayed.checksums_hash


def test_theme_data_insufficient_blocks_without_direct_stock_fallback(
    research_input_bundle: ResearchInputBundle,
    tmp_path: Path,
) -> None:
    inputs = replace(_qualified(research_input_bundle), theme_observations=())
    verified = _run(inputs, tmp_path)

    assert verified.artifact.research_status is ResearchLayerStatus.RESEARCH_BLOCKED
    assert "THEME_ROTATION_DATA_INSUFFICIENT" in verified.artifact.reason_codes
    assert not verified.artifact.candidate_set.selected


def test_capital_data_insufficient_blocks_without_b0_b1_bypass(
    research_input_bundle: ResearchInputBundle,
    tmp_path: Path,
) -> None:
    qualified = _qualified(research_input_bundle)
    observations = tuple(
        replace(item, symbol_amount_expansion=None)
        for item in qualified.symbol_observations
    )
    verified = _run(
        replace(qualified, symbol_observations=observations), tmp_path
    )

    assert verified.artifact.research_status is ResearchLayerStatus.RESEARCH_BLOCKED
    assert not verified.artifact.candidate_set.selected
    assert all(
        "CAPITAL_EVOLUTION_NOT_QUALIFIED" in item.reason_codes
        for item in verified.artifact.candidate_set.records
    )


def test_research_reader_rejects_tamper_and_unknown_schema(
    research_input_bundle: ResearchInputBundle,
    tmp_path: Path,
) -> None:
    verified = _run(_qualified(research_input_bundle), tmp_path)
    candidate_path = verified.root / "candidate_set.json"
    candidate_path.write_text(
        candidate_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_research_artifact(verified.root)

    manifest = json.loads((verified.root / "manifest.json").read_text())
    manifest["schema_version"] = "unknown-research-schema"
    (verified.root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unsupported"):
        load_verified_research_artifact(verified.root)


def test_research_input_bundle_round_trip_rejects_unknown_fields(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    payload = inputs.to_canonical_dict()
    assert ResearchInputBundle.from_canonical_dict(payload) == inputs
    with pytest.raises(ValueError, match="fields mismatch"):
        ResearchInputBundle.from_canonical_dict({**payload, "unknown": True})

