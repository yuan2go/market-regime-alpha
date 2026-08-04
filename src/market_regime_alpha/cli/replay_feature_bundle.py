"""Recompute a Feature Bundle from its bound Market Data Dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn, Sequence

from market_regime_alpha.cli._feature_output import (
    EXIT_ARGUMENT_ERROR,
    EXIT_INPUT_TAMPERED,
    EXIT_IO_ERROR,
    EXIT_SUCCESS,
    emit,
    emit_error,
)
from market_regime_alpha.features import replay_feature_bundle_v2
from market_regime_alpha.market_data import load_verified_market_data_dataset


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--market-data-manifest", type=Path, required=True)
    parser.add_argument("--feature-bundle", type=Path, required=True)
    parser.add_argument("--feature-artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        dataset = load_verified_market_data_dataset(args.market_data_manifest.resolve())
        report = replay_feature_bundle_v2(
            bundle_path=args.feature_bundle.resolve(),
            artifact_root=args.feature_artifact_root.resolve(),
            verified_dataset=dataset,
            report_root=(
                args.output_dir.resolve() if args.output_dir is not None else None
            ),
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        emit_error(status="IO_ERROR", reason_code="FEATURE_REPLAY_IO_ERROR", error=exc)
        return EXIT_IO_ERROR
    except ValueError as exc:
        emit_error(status="REJECTED", reason_code="FEATURE_REPLAY_REJECTED", error=exc)
        return EXIT_INPUT_TAMPERED
    except TypeError as exc:
        emit_error(status="REJECTED", reason_code="FEATURE_REPLAY_ARGUMENT_ERROR", error=exc)
        return EXIT_ARGUMENT_ERROR
    emit(
        {
            "status": "STABLE" if report.semantic_match else "DIVERGED",
            "run_id": str(report.report_id),
            "feature_bundle_hash": report.original_bundle_hash,
            "replay_feature_bundle_hash": report.replayed_bundle_hash,
            "artifact_hashes_match": (
                report.original_artifact_hashes == report.replayed_artifact_hashes
            ),
            "limitations": list(report.limitations),
        }
    )
    return EXIT_SUCCESS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
