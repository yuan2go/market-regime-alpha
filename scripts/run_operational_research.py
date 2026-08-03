#!/usr/bin/env python3
"""Run or replay the verified Operational Research Bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from market_regime_alpha.application.operational_research.bridge import (
    OperationalResearchRunner,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="run from a verified H6 composite evidence package"
    )
    run.add_argument("--composite-package", type=Path, required=True)
    run.add_argument("--daily-artifact", type=Path, required=True)
    run.add_argument("--supplemental-artifact", type=Path, required=True)
    run.add_argument("--research-config", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--code-revision", required=True)
    replay = commands.add_parser(
        "replay", help="semantically replay a verified Research Artifact"
    )
    replay.add_argument("--artifact", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = OperationalResearchRunner()
    if args.command == "run":
        verified = runner.run(
            composite_artifact_path=args.composite_package,
            daily_artifact_path=args.daily_artifact,
            supplemental_artifact_path=args.supplemental_artifact,
            configuration=ResearchPipelineConfig.from_canonical_dict(
                _read_object(args.research_config)
            ),
            output_root=args.output_root,
            code_revision=str(args.code_revision),
        )
    elif args.command == "replay":
        verified = runner.replay(args.artifact)
    else:
        raise AssertionError("unreachable operational research command")
    inputs = verified.artifact.inputs
    composite_id = (
        str(inputs.composite_manifest_id)
        if hasattr(inputs, "composite_manifest_id")
        else None
    )
    print(
        json.dumps(
            {
                "artifact_id": str(verified.artifact.artifact_id),
                "content_hash": verified.artifact.content_hash,
                "research_status": verified.artifact.research_status.value,
                "data_eligibility": (
                    verified.artifact.envelope.data_eligibility.value
                ),
                "evidence_kind": inputs.evidence_kind.value,
                "composite_manifest_id": composite_id,
                "formal_pit": "NOT_ESTABLISHED",
                "formal_oos_alpha": "NOT_ESTABLISHED",
                "trading_authority": "NOT_GRANTED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _read_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid operational research JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("operational research JSON must contain an object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
