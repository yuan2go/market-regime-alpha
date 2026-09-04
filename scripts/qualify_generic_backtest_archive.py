#!/usr/bin/env python3
"""Materialize a deterministic research archive from exact immutable captures.

The source database and Artifact root are read only.  Every target mutation is
performed through the canonical Artifact, MarketArchive, Capture, and
Normalization applications.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

import psycopg

from market_regime_alpha.bootstrap import (
    TargetSettings,
    bootstrap_application,
    database_identity,
)
from market_regime_alpha.infrastructure.providers.artifact_capture_replay import (
    ArtifactCaptureReplayEntry,
    ArtifactCaptureReplayProvider,
)
from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveQuery,
)
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import (
    BaoStockArchiveNormalizer,
)
from market_regime_alpha.market.application import (
    ArchiveManifestSlice,
    ArchiveOperatorManifest,
    ArchiveSliceExecutionRequest,
)
from market_regime_alpha.market.application.archive_replay import (
    relabel_retrospective_manifest,
)
from market_regime_alpha.market.domain import ArchiveSealDisposition
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.shared.hashing import canonical_json_sha256


_IDENTITY_KEY = "generic-platform-qualification-20260904-v1"
_ARCHIVE_CODE = "generic_platform_qualification_20260904"
_PILOT_CODES = (
    "sh.600018",
    "sh.600160",
    "sh.600219",
    "sh.600460",
    "sh.600519",
    "sh.600600",
    "sh.600690",
    "sh.600875",
    "sh.600886",
    "sh.600938",
    "sh.601229",
    "sh.601600",
    "sh.601601",
    "sh.601808",
    "sh.601857",
    "sh.601877",
    "sh.601901",
    "sh.601919",
    "sh.603260",
    "sh.688036",
    "sh.688256",
    "sh.688396",
    "sh.688472",
    "sz.000538",
    "sz.000776",
    "sz.001965",
    "sz.002179",
    "sz.300014",
    "sz.300015",
    "sz.300059",
    "sz.300347",
    "sz.300832",
)
_BAR_MONTHS = frozenset({"2026-02", "2026-03", "2026-04"})
_MEMBERSHIP_DATES = frozenset(
    {"2026-01-30", "2026-02-27", "2026-03-31", "2026-04-30"}
)


@dataclass(frozen=True, slots=True)
class _SourceCapture:
    capture_key: str
    request_sha256: str
    content_sha256: str
    size_bytes: int
    media_type: str
    locator: str
    payload_encoding: str
    limitation_code: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-database-url", required=True)
    parser.add_argument("--source-artifact-root", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--target-database-url", required=True)
    parser.add_argument("--target-artifact-root", required=True, type=Path)
    parser.add_argument("--expected-target-database-name", required=True)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--actor-id", default="generic-backtest-qualification-operator")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    source_bytes = arguments.source_manifest.read_bytes()
    source = ArchiveOperatorManifest.from_json(source_bytes.decode("utf-8"))
    selected = _selected_slices(source)
    source_captures = _load_source_captures(
        arguments.source_database_url,
        source_artifact_root=arguments.source_artifact_root.resolve(),
        source_slices=selected,
    )

    settings = TargetSettings(
        database_url=arguments.target_database_url,
        artifact_root=arguments.target_artifact_root.resolve(),
    )
    identity = database_identity(settings)
    if identity.database_name != arguments.expected_target_database_name:
        raise ValueError("target database identity differs from operator intent")
    if arguments.source_database_url == arguments.target_database_url:
        raise ValueError("source and target databases must be distinct")

    source_manifest_sha256 = sha256(source_bytes).hexdigest()
    code_payload = _json_bytes(
        {
            "code_sha": arguments.code_sha,
            "schema": "generic-backtest-qualification-code-v1",
        }
    )
    config_payload = _json_bytes(
        {
            "bar_months": sorted(_BAR_MONTHS),
            "membership_dates": sorted(_MEMBERSHIP_DATES),
            "pilot_codes": list(_PILOT_CODES),
            "schema": "generic-backtest-qualification-archive-config-v1",
            "source_archive_id": str(source.start_request.market_archive_id),
            "source_manifest_sha256": source_manifest_sha256,
            "source_slice_ordinals": [item.plan.ordinal for item in selected],
        }
    )
    provenance_sha256 = canonical_json_sha256(
        {
            "code_sha": arguments.code_sha,
            "config_sha256": sha256(config_payload).hexdigest(),
            "source_archive_id": source.start_request.market_archive_id,
            "source_manifest_sha256": source_manifest_sha256,
        }
    )
    scope_sha256 = canonical_json_sha256(
        {"algorithm": "LEXICOGRAPHIC_EXACT_ROSTER", "codes": _PILOT_CODES}
    )

    with bootstrap_application(settings) as application:
        code_artifact = application.artifacts.publish(
            code_payload,
            media_type="application/json",
            context=_context(arguments.actor_id, "publish-code"),
            expected_sha256=sha256(code_payload).hexdigest(),
            pin_reason_code="GENERIC_BACKTEST_QUALIFICATION",
        )
        config_artifact = application.artifacts.publish(
            config_payload,
            media_type="application/json",
            context=_context(arguments.actor_id, "publish-archive-config"),
            expected_sha256=sha256(config_payload).hexdigest(),
            pin_reason_code="GENERIC_BACKTEST_QUALIFICATION",
        )
        manifest = relabel_retrospective_manifest(
            source=source,
            selected=selected,
            identity_key=_IDENTITY_KEY,
            archive_code=_ARCHIVE_CODE,
            code_artifact_id=code_artifact.artifact_id,
            config_artifact_id=config_artifact.artifact_id,
            instrument_scope="DETERMINISTIC_32_SYMBOL_QUALIFICATION",
            instrument_scope_sha256=scope_sha256,
            provenance_sha256=provenance_sha256,
            reserved_free_bytes=256_000_000,
            maximum_archive_bytes=500_000_000,
        )
        manifest_bytes = manifest.to_bytes()
        application.artifacts.publish(
            manifest_bytes,
            media_type="application/json",
            context=_context(arguments.actor_id, "publish-archive-manifest"),
            expected_sha256=sha256(manifest_bytes).hexdigest(),
            pin_reason_code="GENERIC_BACKTEST_QUALIFICATION",
        )
        _write_exact(arguments.output_manifest, manifest_bytes)
        provider = _replay_provider(
            manifest,
            selected,
            source_captures,
            arguments.source_artifact_root.resolve(),
        )
        # Reconcile every immutable source byte before the first Market mutation.
        for item in manifest.slices:
            provider.capture(item.capture_request)
        started = application.market_archives.start(
            manifest.start_request,
            _context(arguments.actor_id, "start-archive"),
        )
        status_counts: dict[str, int] = {}
        for item in manifest.slices:
            query = BaoStockArchiveQuery.from_resource(item.capture_request.resource)
            result = application.archive_operations.execute_slice(
                ArchiveSliceExecutionRequest(
                    market_archive_id=manifest.start_request.market_archive_id,
                    market_archive_slice_id=item.plan.market_archive_slice_id,
                    capture_request=item.capture_request,
                    schedule_slot=item.schedule_slot,
                ),
                provider=provider,
                normalizer=BaoStockArchiveNormalizer(
                    expected_query=query,
                    revision_lineage=application.market_revision_lineage,
                    trading_sessions=application.archive_trading_sessions,
                ),
                context=_context(arguments.actor_id, f"slice-{item.plan.ordinal}"),
            )
            status_counts[result.status.value] = status_counts.get(result.status.value, 0) + 1
        seal = application.market_archives.seal_retrospective(
            market_archive_id=manifest.start_request.market_archive_id,
            disposition=ArchiveSealDisposition.COMPLETE,
            context=_context(arguments.actor_id, "seal-archive"),
        )
        verification = application.archive_verification.verify(
            manifest.start_request.market_archive_id
        )

    print(
        json.dumps(
            {
                "archive_content_sha256": started.content_sha256,
                "archive_id": str(started.market_archive_id),
                "archive_replayed": started.replayed,
                "manifest_sha256": sha256(manifest_bytes).hexdigest(),
                "seal_content_sha256": seal.content_sha256,
                "seal_id": str(seal.market_archive_seal_id),
                "seal_replayed": seal.replayed,
                "slice_count": len(manifest.slices),
                "status_counts": status_counts,
                "verification": _json_value(verification),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


def _selected_slices(
    source: ArchiveOperatorManifest,
) -> tuple[ArchiveManifestSlice, ...]:
    selected = []
    counts: dict[str, int] = {}
    for item in source.slices:
        resource = json.loads(item.capture_request.resource)
        kind = str(resource["kind"])
        include = kind == "TRADE_DATES"
        if kind == "CSI300_MEMBERS":
            include = resource.get("start_date") in _MEMBERSHIP_DATES
        if kind in {"HISTORY_DAILY_RAW", "HISTORY_5M_RAW"}:
            start_date = str(resource.get("start_date", ""))
            include = (
                resource.get("code") in _PILOT_CODES
                and start_date[:7] in _BAR_MONTHS
            )
        if include:
            selected.append(item)
            counts[kind] = counts.get(kind, 0) + 1
    expected = {
        "CSI300_MEMBERS": 4,
        "HISTORY_5M_RAW": 96,
        "HISTORY_DAILY_RAW": 96,
        "TRADE_DATES": 1,
    }
    if counts != expected or len(selected) != 197:
        raise ValueError("source manifest does not contain the exact qualification subset")
    return tuple(selected)


def _load_source_captures(
    database_url: str,
    *,
    source_artifact_root: Path,
    source_slices: tuple[ArchiveManifestSlice, ...],
) -> dict[str, _SourceCapture]:
    keys = tuple(item.capture_request.capture_key for item in source_slices)
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            rows = connection.execute(
                """
                SELECT capture.capture_key, capture.request_hash,
                       artifact.content_sha256, artifact.size_bytes,
                       artifact.media_type, artifact.locator,
                       capture.payload_encoding, capture.limitation_code,
                       capture.status, artifact.integrity_state
                FROM mra.data_capture AS capture
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE capture.capture_key = ANY(%s)
                ORDER BY capture.capture_key
                """,
                (list(keys),),
            ).fetchall()
    if len(rows) != len(keys):
        raise ValueError("source capture roster is incomplete or duplicated")
    captures: dict[str, _SourceCapture] = {}
    for row in rows:
        if str(row[8]) != "CAPTURED" or str(row[9]) != "AVAILABLE":
            raise ValueError("source capture or Artifact is not readable Authority")
        capture = _SourceCapture(
            capture_key=str(row[0]),
            request_sha256=str(row[1]),
            content_sha256=str(row[2]),
            size_bytes=int(row[3]),
            media_type=str(row[4]),
            locator=str(row[5]),
            payload_encoding=str(row[6]),
            limitation_code=str(row[7]),
        )
        if capture.capture_key in captures:
            raise ValueError("source capture key is duplicated")
        captures[capture.capture_key] = capture
    for item in source_slices:
        source_capture = captures[item.capture_request.capture_key]
        if source_capture.request_sha256 != canonical_json_sha256(
            item.capture_request
        ):
            raise ValueError("source CaptureRequest differs from source Authority")
        path = source_artifact_root / source_capture.locator
        content = path.read_bytes()
        if (
            len(content) != source_capture.size_bytes
            or sha256(content).hexdigest() != source_capture.content_sha256
        ):
            raise ValueError("source Artifact bytes differ from source Authority")
    return captures


def _replay_provider(
    target: ArchiveOperatorManifest,
    source_slices: tuple[ArchiveManifestSlice, ...],
    source_captures: dict[str, _SourceCapture],
    source_artifact_root: Path,
) -> ArtifactCaptureReplayProvider:
    entries = []
    for target_slice, source_slice in zip(
        target.slices,
        source_slices,
        strict=True,
    ):
        source = source_captures[source_slice.capture_request.capture_key]
        entries.append(
            ArtifactCaptureReplayEntry(
                capture_key=target_slice.capture_request.capture_key,
                request_sha256=canonical_json_sha256(target_slice.capture_request),
                content_sha256=source.content_sha256,
                size_bytes=source.size_bytes,
                media_type=source.media_type,
                payload_encoding=source.payload_encoding,
                locator=source.locator,
                limitation_code=source.limitation_code,
            )
        )
    return ArtifactCaptureReplayProvider(source_artifact_root, tuple(entries))


def _context(actor_id: str, suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"{_IDENTITY_KEY}:{suffix}",
        actor_type=ActorType.OPERATOR,
        actor_id=actor_id,
        reason_code="GENERIC_BACKTEST_QUALIFICATION",
    )


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_exact(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("existing output manifest differs from exact replay")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _json_value(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _json_value(getattr(value, key))
            for key in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "value"):
        return _json_value(value.value)
    if isinstance(value, Path):
        return str(value)
    return str(value) if value.__class__.__module__ == "uuid" else value


if __name__ == "__main__":
    raise SystemExit(main())
