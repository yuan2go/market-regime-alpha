#!/usr/bin/env python3
"""Build, publish and index one terminal H6 composite evidence manifest."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Sequence

from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionPolicy,
)
from market_regime_alpha.application.operational_research.composite_service import (
    CompositeOperationalEvidenceApplicationService,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-artifact", type=Path, required=True)
    parser.add_argument("--supplemental-artifact", type=Path, required=True)
    parser.add_argument("--composition-policy", type=Path, required=True)
    add_database_arguments(parser)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--idempotency-key", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with RepositoryFactory(settings_from_namespace(args)) as repositories:
        result = CompositeOperationalEvidenceApplicationService(
            repositories.composite()
        ).build_and_publish(
            daily_package_path=args.daily_artifact,
            supplemental_package_path=args.supplemental_artifact,
            composition_policy=(
                CompositeOperationalCompositionPolicy.from_canonical_dict(
                    _read_object(args.composition_policy)
                )
            ),
            package_root=args.output_root,
            created_at=datetime.fromisoformat(str(args.created_at)),
            idempotency_key=str(args.idempotency_key),
        )
    manifest = result.manifest
    print(
        json.dumps(
            {
                "manifest_id": str(manifest.manifest_id),
                "content_hash": manifest.content_hash,
                "package_path": str(result.root),
                "status": manifest.status.value,
                "missing_evidence": list(manifest.missing_evidence),
                "source_conflicts": list(manifest.source_conflicts),
                "reason_codes": list(manifest.reason_codes),
                "data_eligibility": manifest.data_eligibility.value,
                "formal_pit": manifest.formal_pit,
                "formal_oos_alpha": manifest.formal_oos_alpha,
                "MANIFEST_ONLY": True,
                "NO_RESEARCH_MODEL_RUN": True,
                "NO_TRADE_ACTION_CREATED": True,
                "TRADING_AUTHORITY_NOT_GRANTED": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid H6 composition policy JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("H6 composition policy JSON must contain an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
