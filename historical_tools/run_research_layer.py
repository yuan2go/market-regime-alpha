#!/usr/bin/env python3
"""Offline Fixture/Archive CLI for Platform V2 Research Layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Sequence

from market_regime_alpha.application.research_layer.runner import (
    PlatformResearchRunner,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
    default_research_pipeline_config,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run-research-v2", help="compute and publish a Research Layer Artifact"
    )
    run.add_argument("--input-bundle", type=Path, required=True)
    run.add_argument("--research-config", type=Path)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--code-revision", default=None)

    replay = subparsers.add_parser(
        "replay-research-v2", help="recompute a verified Research Layer Artifact"
    )
    replay.add_argument("--artifact", type=Path, required=True)

    report = subparsers.add_parser(
        "report-research-v2", help="reconstruct a verified Research Layer report"
    )
    report.add_argument("--artifact", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = PlatformResearchRunner()
    if args.command == "run-research-v2":
        inputs = ResearchInputBundle.from_canonical_dict(
            _read_object(args.input_bundle)
        )
        configuration = (
            ResearchPipelineConfig.from_canonical_dict(
                _read_object(args.research_config)
            )
            if args.research_config is not None
            else default_research_pipeline_config()
        )
        verified = runner.run(
            inputs=inputs,
            configuration=configuration,
            output_root=args.output_root,
            code_revision=args.code_revision or _current_revision(),
        )
        _print_result(verified.artifact)
        return 0
    if args.command == "replay-research-v2":
        verified = runner.replay(args.artifact)
        _print_result(verified.artifact)
        return 0
    if args.command == "report-research-v2":
        print(runner.report(args.artifact), end="")
        return 0
    raise AssertionError("unreachable Research Layer command")


def _read_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Research Layer input JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Research Layer input JSON must contain an object")
    return payload


def _current_revision() -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _print_result(artifact: object) -> None:
    from market_regime_alpha.research.platform_v2.artifact import (
        ResearchLayerArtifact,
    )

    if not isinstance(artifact, ResearchLayerArtifact):
        raise TypeError("expected ResearchLayerArtifact")
    print(
        json.dumps(
            {
                "artifact_id": str(artifact.artifact_id),
                "content_hash": artifact.content_hash,
                "research_status": artifact.research_status.value,
                "evidence_kind": artifact.inputs.evidence_kind.value,
                "selected_candidate_count": len(artifact.candidate_set.selected),
                "data_eligibility": artifact.envelope.data_eligibility.value,
                "formal_pit": "NOT_ESTABLISHED",
                "formal_oos_alpha": "NOT_ESTABLISHED",
                "trading_authority": "NOT_GRANTED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

