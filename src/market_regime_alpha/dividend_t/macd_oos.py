"""Sealed MACD out-of-sample manifests, gates, and immutable artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence

from market_regime_alpha.dividend_t.macd import PriceAdjustmentMode
from market_regime_alpha.dividend_t.macd_bars import expected_a_share_5m_closes
from market_regime_alpha.dividend_t.macd_experiments import (
    MACD_PROFILE_NAMES,
    AblationArmContext,
    MACDExperimentIdentity,
    canonical_experiment_config,
    canonical_json,
    experiment_config_hash,
    validate_four_arm_contexts,
)
from market_regime_alpha.dividend_t.signal_intent import MACDPolicyConfig


DATASET_MANIFEST_SCHEMA_VERSION = "macd-dataset-manifest-v1"
DATA_SPLIT_SCHEMA_VERSION = "macd-data-split-v1"


class DatasetClassification(str, Enum):
    FIXTURE = "FIXTURE"
    REHEARSAL = "REHEARSAL"
    FORMAL_FINAL_CANDIDATE = "FORMAL_FINAL_CANDIDATE"


@dataclass(frozen=True)
class DatasetFileManifest:
    logical_path: str
    sha256: str
    symbols: tuple[str, ...]
    start_time: str
    end_time: str
    bar_count: int
    source_frequencies: tuple[str, ...]


@dataclass(frozen=True)
class DatasetQualityStats:
    finalized_bar_count: int
    provisional_bar_count: int
    missing_expected_bar_count: int
    unexpected_timestamp_count: int
    invalid_price_bar_count: int
    duplicate_timestamp_count: int
    nonpositive_volume_bar_count: int
    bar_final_column_present: bool


@dataclass(frozen=True)
class DatasetSymbolManifest:
    symbol: str
    start_time: str
    end_time: str
    bar_count: int


@dataclass(frozen=True)
class DatasetManifest:
    schema_version: str
    classification: DatasetClassification
    files: tuple[DatasetFileManifest, ...]
    symbols: tuple[str, ...]
    symbols_detail: tuple[DatasetSymbolManifest, ...]
    start_time: str
    end_time: str
    total_bar_count: int
    data_source: str
    price_adjustment_mode: PriceAdjustmentMode
    pit_adjustment_complete: bool
    trading_calendar_version: str
    trading_calendar_hash: str
    universe_hash: str
    corporate_action_hash: str
    suspension_hash: str
    quality: DatasetQualityStats
    volume_unit: str = "UNKNOWN"
    amount_unit: str = "UNKNOWN"
    price_unit: str = "UNKNOWN"
    vwap_formula_version: str = "UNKNOWN"


@dataclass(frozen=True)
class DatasetBundle:
    manifest: DatasetManifest
    frame: Any
    expected_bar_times: tuple[Any, ...]
    suspension_times: frozenset[Any]


@dataclass(frozen=True)
class DataSplitManifest:
    train_range: tuple[str, str]
    validation_range: tuple[str, str]
    rehearsal_range: tuple[str, str]
    test_range: tuple[str, str]
    train_symbols: tuple[str, ...]
    validation_symbols: tuple[str, ...]
    rehearsal_symbols: tuple[str, ...]
    test_symbols: tuple[str, ...]
    symbol_holdout_definition: str
    split_policy_version: str
    schema_version: str = DATA_SPLIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        ranges = (self.train_range, self.validation_range, self.rehearsal_range, self.test_range)
        normalized = [_date_range(item) for item in ranges]
        if any(start > end for start, end in normalized):
            raise ValueError("DATA_SPLIT_RANGE_REVERSED")
        for (_, previous_end), (next_start, _) in zip(normalized, normalized[1:]):
            if previous_end >= next_start:
                raise ValueError("DATA_SPLIT_RANGES_OVERLAP")
        if any(not symbols for symbols in (
            self.train_symbols,
            self.validation_symbols,
            self.rehearsal_symbols,
            self.test_symbols,
        )):
            raise ValueError("DATA_SPLIT_SYMBOLS_REQUIRED")
        if not self.symbol_holdout_definition.strip() or not self.split_policy_version.strip():
            raise ValueError("DATA_SPLIT_POLICY_METADATA_REQUIRED")


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class FinalTestReadiness:
    checks: tuple[ReadinessCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)

    def require_ready(self) -> None:
        if not self.ready:
            raise ValueError(f"FINAL_TEST_NOT_READY: {','.join(self.failed_checks)}")


@dataclass(frozen=True)
class ExperimentRunManifest:
    run_id: str
    run_timestamp: str
    run_mode: str
    git_commit: str
    dataset_version: str
    dataset_manifest_hash: str
    data_split_hash: str
    train_range: tuple[str, str]
    validation_range: tuple[str, str]
    rehearsal_range: tuple[str, str]
    test_range: tuple[str, str]
    symbol_holdout_definition: str
    split_policy_version: str
    execution_config_hash: str
    baseline_config_hash: str
    score_only_config_hash: str
    policy_only_config_hash: str
    full_config_hash: str
    random_seed: int
    python_version: str
    dependency_lock_hash: str
    dependency_lock_source: str
    platform_metadata: tuple[tuple[str, str], ...]


def build_dataset_manifest(
    paths: Sequence[Path],
    *,
    data_source: str,
    price_adjustment_mode: PriceAdjustmentMode,
    pit_adjustment_complete: bool,
    trading_calendar_version: str,
    trading_calendar_path: Path,
    universe_path: Path,
    corporate_actions_path: Path,
    suspensions_path: Path,
    classification: DatasetClassification,
    volume_unit: str = "UNKNOWN",
    amount_unit: str = "UNKNOWN",
    price_unit: str = "UNKNOWN",
    vwap_formula_version: str = "UNKNOWN",
) -> DatasetManifest:
    """Hash every point-in-time input and derive reproducible bar-quality statistics."""

    return load_dataset_bundle(
        paths,
        data_source=data_source,
        price_adjustment_mode=price_adjustment_mode,
        pit_adjustment_complete=pit_adjustment_complete,
        trading_calendar_version=trading_calendar_version,
        trading_calendar_path=trading_calendar_path,
        universe_path=universe_path,
        corporate_actions_path=corporate_actions_path,
        suspensions_path=suspensions_path,
        classification=classification,
        volume_unit=volume_unit,
        amount_unit=amount_unit,
        price_unit=price_unit,
        vwap_formula_version=vwap_formula_version,
    ).manifest


def load_dataset_bundle(
    paths: Sequence[Path],
    *,
    data_source: str,
    price_adjustment_mode: PriceAdjustmentMode,
    pit_adjustment_complete: bool,
    trading_calendar_version: str,
    trading_calendar_path: Path,
    universe_path: Path,
    corporate_actions_path: Path,
    suspensions_path: Path,
    classification: DatasetClassification,
    volume_unit: str = "UNKNOWN",
    amount_unit: str = "UNKNOWN",
    price_unit: str = "UNKNOWN",
    vwap_formula_version: str = "UNKNOWN",
) -> DatasetBundle:
    """Load bars once and return both the content manifest and the shared in-memory frame."""

    import pandas as pd

    if not paths:
        raise ValueError("DATASET_FILES_REQUIRED")
    if not data_source.strip() or not trading_calendar_version.strip():
        raise ValueError("DATASET_SOURCE_AND_CALENDAR_REQUIRED")
    if not isinstance(price_adjustment_mode, PriceAdjustmentMode):
        raise TypeError("price_adjustment_mode must be a PriceAdjustmentMode")
    if not isinstance(pit_adjustment_complete, bool):
        raise TypeError("pit_adjustment_complete must be boolean")
    if not all(isinstance(value, str) and value.strip() for value in (volume_unit, amount_unit, price_unit, vwap_formula_version)):
        raise ValueError("DATASET_UNIT_METADATA_REQUIRED")
    sidecars = (trading_calendar_path, universe_path, corporate_actions_path, suspensions_path)
    for path in (*paths, *sidecars):
        if not path.is_file():
            raise FileNotFoundError(path)

    calendar_dates = _calendar_dates(trading_calendar_path)
    suspension_times = _suspension_times(suspensions_path)
    file_entries: list[DatasetFileManifest] = []
    frames: list[Any] = []
    for path in paths:
        frame = pd.read_csv(path)
        required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"DATASET_COLUMNS_MISSING: {','.join(missing)}")
        frame = frame.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        if frame["timestamp"].isna().any():
            raise ValueError("DATASET_TIMESTAMP_INVALID")
        frames.append(frame)
        file_entries.append(
            DatasetFileManifest(
                logical_path=path.name,
                sha256=_sha256_file(path),
                symbols=tuple(sorted(frame["symbol"].astype(str).unique())),
                start_time=_timestamp_text(frame["timestamp"].min()),
                end_time=_timestamp_text(frame["timestamp"].max()),
                bar_count=len(frame),
                source_frequencies=tuple(sorted(frame.get("source_freq", pd.Series(["unknown"])).astype(str).unique())),
            )
        )

    data = pd.concat(frames, ignore_index=True)
    symbols = tuple(sorted(data["symbol"].astype(str).unique()))
    duplicate_count = int(data.duplicated(subset=["symbol", "timestamp"]).sum())
    final_column_present = "bar_final" in data.columns
    if final_column_present:
        final_values = data["bar_final"]
        finalized_count = int((final_values == True).sum())  # noqa: E712
        provisional_count = len(data) - finalized_count
    else:
        finalized_count = 0
        provisional_count = len(data)
    invalid_prices = _invalid_price_count(data)
    nonpositive_volume = int((pd.to_numeric(data["volume"], errors="coerce").fillna(0.0) <= 0).sum())
    actual = {
        (str(row.symbol), row.timestamp)
        for row in data[["symbol", "timestamp"]].itertuples(index=False)
    }
    expected = {
        (symbol, timestamp)
        for symbol in symbols
        for day in calendar_dates
        for timestamp in expected_a_share_5m_closes(day)
    }
    suspended = {(symbol, timestamp) for symbol in symbols for timestamp in suspension_times}
    missing_expected = expected - actual - suspended
    unexpected = actual - expected
    quality = DatasetQualityStats(
        finalized_bar_count=finalized_count,
        provisional_bar_count=provisional_count,
        missing_expected_bar_count=len(missing_expected),
        unexpected_timestamp_count=len(unexpected),
        invalid_price_bar_count=invalid_prices,
        duplicate_timestamp_count=duplicate_count,
        nonpositive_volume_bar_count=nonpositive_volume,
        bar_final_column_present=final_column_present,
    )
    symbols_detail = tuple(
        DatasetSymbolManifest(
            symbol=str(symbol),
            start_time=_timestamp_text(group["timestamp"].min()),
            end_time=_timestamp_text(group["timestamp"].max()),
            bar_count=len(group),
        )
        for symbol, group in data.groupby(data["symbol"].astype(str), sort=True)
    )
    manifest = DatasetManifest(
        schema_version=DATASET_MANIFEST_SCHEMA_VERSION,
        classification=classification,
        files=tuple(sorted(file_entries, key=lambda item: item.logical_path)),
        symbols=symbols,
        symbols_detail=symbols_detail,
        start_time=_timestamp_text(data["timestamp"].min()),
        end_time=_timestamp_text(data["timestamp"].max()),
        total_bar_count=len(data),
        data_source=data_source.strip(),
        price_adjustment_mode=price_adjustment_mode,
        pit_adjustment_complete=pit_adjustment_complete,
        trading_calendar_version=trading_calendar_version.strip(),
        trading_calendar_hash=_sha256_file(trading_calendar_path),
        universe_hash=_sha256_file(universe_path),
        corporate_action_hash=_sha256_file(corporate_actions_path),
        suspension_hash=_sha256_file(suspensions_path),
        quality=quality,
        volume_unit=volume_unit,
        amount_unit=amount_unit,
        price_unit=price_unit,
        vwap_formula_version=vwap_formula_version,
    )
    expected_bar_times = tuple(
        timestamp for day in calendar_dates for timestamp in expected_a_share_5m_closes(day)
    )
    return DatasetBundle(
        manifest=manifest,
        frame=data,
        expected_bar_times=expected_bar_times,
        suspension_times=suspension_times,
    )


def dataset_manifest_hash(manifest: DatasetManifest) -> str:
    payload = asdict(manifest)
    payload.pop("classification")
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def dataset_version(manifest: DatasetManifest) -> str:
    return f"dataset-{dataset_manifest_hash(manifest)[:16]}"


def data_split_hash(manifest: DataSplitManifest) -> str:
    return hashlib.sha256(canonical_json(asdict(manifest)).encode("utf-8")).hexdigest()


def load_data_split_manifest(path: Path) -> DataSplitManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("DATA_SPLIT_MANIFEST_OBJECT_REQUIRED")
    fields = {
        "train_range",
        "validation_range",
        "rehearsal_range",
        "test_range",
        "train_symbols",
        "validation_symbols",
        "rehearsal_symbols",
        "test_symbols",
        "symbol_holdout_definition",
        "split_policy_version",
    }
    missing = sorted(fields - set(payload))
    if missing:
        raise ValueError(f"DATA_SPLIT_MANIFEST_FIELDS_MISSING: {','.join(missing)}")
    return DataSplitManifest(
        train_range=tuple(payload["train_range"]),
        validation_range=tuple(payload["validation_range"]),
        rehearsal_range=tuple(payload["rehearsal_range"]),
        test_range=tuple(payload["test_range"]),
        train_symbols=tuple(payload["train_symbols"]),
        validation_symbols=tuple(payload["validation_symbols"]),
        rehearsal_symbols=tuple(payload["rehearsal_symbols"]),
        test_symbols=tuple(payload["test_symbols"]),
        symbol_holdout_definition=str(payload["symbol_holdout_definition"]),
        split_policy_version=str(payload["split_policy_version"]),
        schema_version=str(payload.get("schema_version", DATA_SPLIT_SCHEMA_VERSION)),
    )


def validate_four_arm_identities(
    identities: Mapping[str, MACDExperimentIdentity],
    contexts: Mapping[str, AblationArmContext],
) -> None:
    """Allow only score weight and policy enablement to differ across the four arms."""

    expected = set(MACD_PROFILE_NAMES)
    if set(identities) != expected:
        raise ValueError("ABLATION_PROFILES_INCOMPLETE")
    validate_four_arm_contexts(contexts)
    hashes = {name: experiment_config_hash(identity) for name, identity in identities.items()}
    if len(set(hashes.values())) != 4:
        raise ValueError("ABLATION_CONFIG_HASH_NOT_UNIQUE")
    expected_variables = {
        "baseline": (0.0, False),
        "score-only": (0.15, False),
        "policy-only": (0.0, True),
        "full": (0.15, True),
    }
    normalized: dict[str, dict[str, object]] = {}
    for name, identity in identities.items():
        if (identity.score_weight, identity.conflict_gate_enabled) != expected_variables[name]:
            raise ValueError(f"ABLATION_PROFILE_VARIABLES_INVALID: {name}")
        payload = canonical_experiment_config(identity)
        payload.pop("score_weight")
        payload.pop("conflict_gate_enabled")
        normalized[name] = payload
    reference = normalized["baseline"]
    mismatches = [name for name in MACD_PROFILE_NAMES[1:] if normalized[name] != reference]
    if mismatches:
        raise ValueError(f"ABLATION_NON_EXPERIMENT_FIELD_MISMATCH: {','.join(mismatches)}")
    context_mismatches = [
        name for name in MACD_PROFILE_NAMES if contexts[name].experiment_config_hash != hashes[name]
    ]
    if context_mismatches:
        raise ValueError(f"ABLATION_CONTEXT_HASH_MISMATCH: {','.join(context_mismatches)}")


def write_immutable_run_artifact(
    root: Path,
    *,
    run_id: str,
    writer: Callable[[Path], None],
) -> Path:
    """Write a complete run in a temporary sibling and atomically publish it once."""

    if not run_id.strip() or "/" in run_id or "\\" in run_id:
        raise ValueError("RUN_ID_INVALID")
    root.mkdir(parents=True, exist_ok=True)
    target = root / run_id
    if target.exists():
        raise FileExistsError(target)
    lock = root / f".{run_id}.lock"
    descriptor: int | None = None
    stage: Path | None = None
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        stage = Path(tempfile.mkdtemp(prefix=f".{run_id}.tmp-", dir=root))
        writer(stage)
        _validate_artifact_layout(stage)
        _write_checksums(stage)
        (stage / "COMPLETED").write_text(
            canonical_json({"run_id": run_id, "status": "COMPLETED"}) + "\n",
            encoding="utf-8",
        )
        if target.exists():
            raise FileExistsError(target)
        stage.rename(target)
        stage = None
        return target
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        lock.unlink(missing_ok=True)


def verify_artifact_checksums(path: Path) -> bool:
    checksum_path = path / "checksums.sha256"
    if not checksum_path.is_file():
        return False
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        file_path = path / relative
        if not separator or not file_path.is_file() or _sha256_file(file_path) != digest:
            return False
    return True


def evaluate_final_test_readiness(
    *,
    manifest: DatasetManifest,
    split: DataSplitManifest,
    identities: Mapping[str, MACDExperimentIdentity],
    contexts: Mapping[str, AblationArmContext],
    working_tree_clean: bool,
    quality_checks_pass: bool,
    cache_identities_valid: bool,
    production_policy_config: MACDPolicyConfig,
) -> FinalTestReadiness:
    """Return every sealed-test gate; callers must reject final execution unless all pass."""

    quality = manifest.quality
    dataset_valid = (
        manifest.schema_version == DATASET_MANIFEST_SCHEMA_VERSION
        and manifest.total_bar_count > 0
        and all(len(value) == 64 for value in (
            manifest.trading_calendar_hash,
            manifest.universe_hash,
            manifest.corporate_action_hash,
            manifest.suspension_hash,
        ))
        and quality.invalid_price_bar_count == 0
        and quality.duplicate_timestamp_count == 0
        and quality.missing_expected_bar_count == 0
        and quality.unexpected_timestamp_count == 0
        and quality.nonpositive_volume_bar_count == 0
    )
    split_valid = _split_matches_dataset(split, manifest)
    four_arm_valid = True
    four_arm_detail = "four canonical hashes are distinct and differ only by score/policy variables"
    try:
        validate_four_arm_identities(identities, contexts)
    except ValueError as exc:
        four_arm_valid = False
        four_arm_detail = str(exc)
    expected_dataset = dataset_version(manifest)
    expected_split = data_split_hash(split)
    identity_links_valid = all(
        identity.dataset_version == expected_dataset and identity.data_split_hash == expected_split
        for identity in identities.values()
    )
    production_baseline = (
        production_policy_config.score_weight == 0.0
        and production_policy_config.conflict_gate_enabled is False
    )
    checks = (
        ReadinessCheck("working_tree_clean", working_tree_clean, "git worktree must be clean"),
        ReadinessCheck("all_tests_lint_type_checks_pass", quality_checks_pass, "pytest, Ruff, and mypy"),
        ReadinessCheck(
            "all_bars_finalized",
            quality.bar_final_column_present and quality.finalized_bar_count == manifest.total_bar_count,
            f"finalized={quality.finalized_bar_count}/{manifest.total_bar_count}",
        ),
        ReadinessCheck("no_provisional_bars", quality.provisional_bar_count == 0, f"provisional={quality.provisional_bar_count}"),
        ReadinessCheck(
            "pit_adjustment_complete",
            manifest.pit_adjustment_complete
            and manifest.price_adjustment_mode is PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
            manifest.price_adjustment_mode.value,
        ),
        ReadinessCheck("dataset_manifest_valid", dataset_valid, dataset_manifest_hash(manifest)),
        ReadinessCheck("data_split_manifest_valid", split_valid, expected_split),
        ReadinessCheck("all_four_config_hashes_distinct", four_arm_valid, four_arm_detail),
        ReadinessCheck(
            "cache_identities_valid",
            cache_identities_valid and identity_links_valid,
            "cache metadata and dataset/split identity links",
        ),
        ReadinessCheck("production_profile_remains_baseline", production_baseline, "score_weight=0.0, gate=false"),
        ReadinessCheck(
            "formal_dataset_selected",
            manifest.classification is DatasetClassification.FORMAL_FINAL_CANDIDATE,
            manifest.classification.value,
        ),
    )
    return FinalTestReadiness(checks=checks)


def selected_segment_range(
    split: DataSplitManifest,
    *,
    segment: str,
    final_test: bool,
) -> tuple[str, str]:
    allowed = {
        "train": split.train_range,
        "validation": split.validation_range,
        "rehearsal": split.rehearsal_range,
        "test": split.test_range,
    }
    if segment not in allowed:
        raise ValueError(f"UNKNOWN_EXPERIMENT_SEGMENT: {segment}")
    if segment == "test" and not final_test:
        raise ValueError("FINAL_TEST_SEGMENT_SEALED")
    if final_test and segment != "test":
        raise ValueError("FINAL_TEST_FLAG_REQUIRES_TEST_SEGMENT")
    return allowed[segment]


def build_run_manifest(
    *,
    run_timestamp: str,
    git_commit: str,
    dataset_version: str,
    dataset_manifest_hash_value: str,
    split: DataSplitManifest,
    identities: Mapping[str, MACDExperimentIdentity],
    execution_config_hash_value: str,
    random_seed: int,
    dependency_lock_hash: str,
    dependency_lock_source: str,
    platform_metadata: Mapping[str, str],
    run_mode: str,
) -> ExperimentRunManifest:
    if set(identities) != set(MACD_PROFILE_NAMES):
        raise ValueError("ABLATION_PROFILES_INCOMPLETE")
    split_hash = data_split_hash(split)
    if any(identity.dataset_version != dataset_version for identity in identities.values()):
        raise ValueError("RUN_MANIFEST_DATASET_IDENTITY_MISMATCH")
    if any(identity.data_split_hash != split_hash for identity in identities.values()):
        raise ValueError("RUN_MANIFEST_SPLIT_IDENTITY_MISMATCH")
    if any(identity.execution_config_hash != execution_config_hash_value for identity in identities.values()):
        raise ValueError("RUN_MANIFEST_EXECUTION_IDENTITY_MISMATCH")
    if len(dataset_manifest_hash_value) != 64 or len(dependency_lock_hash) != 64:
        raise ValueError("RUN_MANIFEST_HASH_INVALID")
    if not dependency_lock_source.strip():
        raise ValueError("DEPENDENCY_LOCK_SOURCE_REQUIRED")
    config_hashes = {name: experiment_config_hash(identity) for name, identity in identities.items()}
    compact_time = "".join(character for character in run_timestamp if character.isalnum() or character in {"+", "-"})
    mode = run_mode.strip().lower()
    run_id = (
        f"{mode}-{compact_time}-{dataset_manifest_hash_value[:12]}-"
        f"{split_hash[:12]}-{git_commit[:7]}"
    )
    return ExperimentRunManifest(
        run_id=run_id,
        run_timestamp=run_timestamp,
        run_mode=run_mode.upper(),
        git_commit=git_commit,
        dataset_version=dataset_version,
        dataset_manifest_hash=dataset_manifest_hash_value,
        data_split_hash=split_hash,
        train_range=split.train_range,
        validation_range=split.validation_range,
        rehearsal_range=split.rehearsal_range,
        test_range=split.test_range,
        symbol_holdout_definition=split.symbol_holdout_definition,
        split_policy_version=split.split_policy_version,
        execution_config_hash=execution_config_hash_value,
        baseline_config_hash=config_hashes["baseline"],
        score_only_config_hash=config_hashes["score-only"],
        policy_only_config_hash=config_hashes["policy-only"],
        full_config_hash=config_hashes["full"],
        random_seed=random_seed,
        python_version=sys.version,
        dependency_lock_hash=dependency_lock_hash,
        dependency_lock_source=dependency_lock_source.strip(),
        platform_metadata=tuple(sorted((str(key), str(value)) for key, value in platform_metadata.items())),
    )


def _date_range(value: tuple[str, str]) -> tuple[Any, Any]:
    import pandas as pd

    if len(value) != 2:
        raise ValueError("DATA_SPLIT_RANGE_INVALID")
    start = pd.Timestamp(value[0]).normalize()
    end = pd.Timestamp(value[1]).normalize()
    return start, end


def _split_matches_dataset(split: DataSplitManifest, manifest: DatasetManifest) -> bool:
    import pandas as pd

    dataset_symbols = set(manifest.symbols)
    symbol_groups = (
        split.train_symbols,
        split.validation_symbols,
        split.rehearsal_symbols,
        split.test_symbols,
    )
    symbols_valid = all(set(group) <= dataset_symbols for group in symbol_groups)
    dataset_start = pd.Timestamp(manifest.start_time).normalize()
    dataset_end = pd.Timestamp(manifest.end_time).normalize()
    ranges = (
        split.train_range,
        split.validation_range,
        split.rehearsal_range,
        split.test_range,
    )
    ranges_valid = all(dataset_start <= start <= end <= dataset_end for start, end in map(_date_range, ranges))
    return symbols_valid and ranges_valid and split.schema_version == DATA_SPLIT_SCHEMA_VERSION


def _validate_artifact_layout(stage: Path) -> None:
    required = (
        "manifest.json",
        "baseline",
        "score-only",
        "policy-only",
        "full",
        "attribution",
        "report.md",
    )
    missing = [name for name in required if not (stage / name).exists()]
    if missing:
        raise ValueError(f"ARTIFACT_LAYOUT_INCOMPLETE: {','.join(missing)}")


def _write_checksums(stage: Path) -> None:
    files = sorted(
        path for path in stage.rglob("*")
        if path.is_file() and path.name not in {"checksums.sha256", "COMPLETED"}
    )
    lines = [f"{_sha256_file(path)}  {path.relative_to(stage).as_posix()}" for path in files]
    (stage / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _calendar_dates(path: Path) -> tuple[str, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    dates = payload.get("trading_dates") if isinstance(payload, dict) else None
    if not isinstance(dates, list) or not dates or not all(isinstance(item, str) for item in dates):
        raise ValueError("TRADING_CALENDAR_DATES_REQUIRED")
    return tuple(sorted(set(dates)))


def _suspension_times(path: Path) -> frozenset[Any]:
    import pandas as pd

    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("suspension_times", []) if isinstance(payload, dict) else []
    if not isinstance(values, list):
        raise ValueError("SUSPENSION_TIMES_INVALID")
    return frozenset(pd.Timestamp(value) for value in values)


def _invalid_price_count(data: Any) -> int:
    import pandas as pd

    invalid = pd.Series(False, index=data.index)
    for column in ("open", "high", "low", "close"):
        values = pd.to_numeric(data[column], errors="coerce")
        invalid |= values.isna() | ~values.map(math.isfinite) | (values <= 0)
    return int(invalid.sum())


def _timestamp_text(value: Any) -> str:
    import pandas as pd

    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")
