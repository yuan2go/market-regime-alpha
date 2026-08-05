"""Replay one Controlled evidence package entirely offline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from market_regime_alpha.application.controlled_operation.replay import (
    replay_controlled_operation,
)
from market_regime_alpha.application.controlled_operation.evidence_package import (
    load_controlled_operation_package,
)
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.cli._controlled_operation import (
    ControlledCLIError,
    ControlledExitCode,
    StructuredParser,
    emit,
    emit_error,
    repository_exception,
    safety_declarations,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.persistence.settings import DatabaseBackend


def build_parser() -> StructuredParser:
    parser = StructuredParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    add_database_arguments(parser, legacy_sqlite_flag="--database")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        package_path = args.package.resolve()
        package = load_controlled_operation_package(package_path)
        repositories = RepositoryFactory(settings_from_namespace(args))
        repositories.assert_runtime_binding(
            "CONTROLLED_OPERATION",
            str(package.command.run_id),
        )
        feature_receipt_loader: Callable[
            [Path], tuple[FeatureMaterializationReceipt, ...]
        ] | None = None
        if repositories.settings.backend is DatabaseBackend.POSTGRES:
            feature_repository = repositories.feature_materialization(
                clock=_utc_now,
            )

            def load_feature_receipts(
                _path: Path,
            ) -> tuple[FeatureMaterializationReceipt, ...]:
                return feature_repository.receipts()

            feature_receipt_loader = load_feature_receipts
        report = replay_controlled_operation(
            package_path,
            canonical_repository_factory=(
                repositories.controlled_canonical_repository
            ),
            feature_receipt_loader=feature_receipt_loader,
        )
        emit({**report.to_canonical_dict(), **safety_declarations()})
        return ControlledExitCode.SUCCESS
    except ControlledCLIError as exc:
        emit_error(status="FAILED", reason_code="ARGUMENT_ERROR", exc=exc)
        return ControlledExitCode.ARGUMENT_ERROR
    except Exception as exc:
        emit_error(status="REPLAY_DIVERGENCE", reason_code="REPLAY_DIVERGENCE", exc=exc)
        if repository_exception(exc):
            return ControlledExitCode.REPOSITORY_ERROR
        return ControlledExitCode.REPLAY_DIVERGENCE


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


if __name__ == "__main__":
    raise SystemExit(main())
