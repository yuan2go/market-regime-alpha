# WP-ALPHA-PROOF-02 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Authority:** Execution plan subordinate to the frozen WP-ALPHA-PROOF-02 protocol

**Goal:** Execute the frozen WP-ALPHA-PROOF-02 protocol through the existing Historical Corpus, Historical Research, Research Validation, Continuous/Shadow and PostgreSQL authorities, producing reproducible positive, negative, not-estimable or data-blocked evidence without consuming Locked OOS Outcomes unless Formal PIT and physical correctness both pass.

**Architecture:** Keep the PostgreSQL-centered modular monolith and its single Historical/Continuous runtimes. Extend the current Historical Corpus package encoding with descriptor-driven staged publication so real Daily+5m acquisition and normalization remain bounded in memory, freeze a label-blind Locked OOS scope in the existing Research Validation authority, and compose existing Phase-II/Candidate/Forecast/Strategy kernels through thin operator inputs and immutable evidence. Legacy in-memory package loading remains readable for V1 artifacts; new campaign code uses `open_index` and selective reads.

**Tech Stack:** Python 3.12, uv, psycopg/PostgreSQL 16, PyArrow/Parquet, pytest, Ruff, mypy, `python -m build`, existing `continuous-research` CLI.

## Global Constraints

- Baseline protocol is commit `a926b95`; Discovery, External, T+1 10:30 Target, three higher-is-better Factors, equal weights, Top-5, `0.002100` cost, inference, multiple testing, Forecast search space, purge/embargo, seed and stopping rule are immutable.
- Formal PIT and physical correctness are hard gates before any Locked OOS Outcome read, projection, aggregation or report.
- BaoStock remains `RETROSPECTIVE_EVENT_TIME / HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED / PIT_INCOMPLETE`; never infer `available_at`.
- Reacquired Raw and Normalized packages receive new content identities and bind the frozen parent protocol; they never overwrite or impersonate old evidence.
- No second Daily Runtime, Historical Runner, Scheduler, Evidence Authority, Qualification hierarchy, Backtest Framework, workflow engine or broker execution path.
- Tests may not be skipped, xfailed, deleted or weakened; research floors and expected outcomes may not be changed to obtain PASS or positive evidence.
- Migrations `001` through `097` are immutable; any schema change begins at `098` and is forward-only.
- `.idea/modules.xml` and unrelated workspace changes are never modified, staged or committed.

---

## File map

- `application/historical_corpus/staged_package.py`: bounded staged Parquet writer/finalizer for the existing Historical Corpus owner identity.
- `application/historical_corpus/baostock_archive.py`: checkpoint-only acquisition loop that hands one logical partition at a time to staged publication.
- `application/historical_corpus/normalization.py`: per-partition Raw-to-Normalized transformation shared by legacy and staged paths.
- `application/historical_corpus/postgres_repository.py`: exact descriptor/index registration and reload without whole-package decoding.
- `application/historical_corpus/locked_oos_scope.py`: label-blind Calendar/Universe/Target roster identity and access decision.
- `application/historical_corpus/postgres_locked_oos_scope.py`: typed writer/reloader in the existing Research Validation PostgreSQL authority.
- `application/historical_corpus/vertical_slice.py`: frozen-protocol composition and status projection; it delegates research computation to existing owners and is not a runner.
- `application/historical_corpus/alpha_correctness.py` and `raw_normalization_correctness.py`: independent physical reproduction and negative-control evidence extensions.
- `application/historical_corpus/phase_ii_service.py`: persistence/reload of the frozen reproduction, external, Candidate and Forecast evidence through the existing Evidence owner.
- `application/continuous_research/validated_alpha.py`: exact Candidate V2 contribution-to-Daily-Alpha projection guarded by External/Candidate evidence lineage.
- `application/continuous_research/free_data_runtime.py`: consumes that projection only after owner reload and keeps exploratory/unsupported chains empty.
- `application/strategy_shadow/economics.py`: V2 executable-entry semantics while preserving all V1 identities.
- `application/strategy_shadow/attribution.py`: owner-bound market/strategy/cost attribution projection.
- `application/source_freeze/acquisition.py`: retained acquisition/source-freeze primitive extracted from compatibility-only DailyLoop orchestration.
- `cli/continuous_research.py`: parse and delegate new staged acquire/replay, Locked scope freeze/report and vertical-slice report inputs.
- `persistence/postgres/migrations/098_wp_alpha_proof_locked_scope.sql`: only the append-only Locked scope owner/projection schema and artifact-kind admission.

---

### Task 1: Descriptor-driven staged Historical packages

**Files:**
- Create: `src/market_regime_alpha/application/historical_corpus/staged_package.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/artifacts.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/postgres_repository.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/__init__.py`
- Test: `tests/application/historical_corpus/test_staged_package.py`
- Test: `tests/persistence/postgres/test_historical_corpus_repository.py`

**Interfaces:**
- Consumes: `HistoricalDataPartition`, `HistoricalCorpusCoverage`, `HistoricalPackageIndex`, `ValidationArtifactReference` and the current V1 Parquet encoding.
- Produces: `StagedHistoricalPackageWriter.add_partition(partition)`, `StagedHistoricalPackageWriter.finalize(metadata) -> HistoricalPackageIndex`, and `PostgresHistoricalCorpusRepository.register_index(index) -> HistoricalPackageIndex`.

- [ ] **Step 1: Write public-seam red tests for bounded publication, exact identity, crash recovery and corruption rejection**

```python
def test_staged_writer_releases_partition_records_and_replays_exact_index(tmp_path: Path) -> None:
    writer = StagedHistoricalPackageWriter(
        artifact_root=tmp_path,
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        bucket_count=2,
    )
    descriptor = writer.add_partition(_normalized_partition(bucket=0))
    assert descriptor.row_count == 2
    assert writer.decoded_record_count == 0
    first = writer.finalize(_metadata(parent_reference=_raw_reference()))
    second = load_historical_package_index(first.root)
    assert second.reference == first.reference
    assert second.physical_hash == first.physical_hash


def test_staged_writer_never_publishes_partial_package(tmp_path: Path) -> None:
    writer = StagedHistoricalPackageWriter(
        artifact_root=tmp_path,
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        bucket_count=2,
        failure_injector=lambda stage: (_ for _ in ()).throw(RuntimeError(stage))
        if stage == "AFTER_STAGING_VALIDATED"
        else None,
    )
    writer.add_partition(_raw_partition(bucket=0))
    with pytest.raises(RuntimeError, match="AFTER_STAGING_VALIDATED"):
        writer.finalize(_metadata(parent_reference=None))
    assert not tuple((tmp_path / "historical-corpus").glob("**/historical-data-owner-*"))
```

- [ ] **Step 2: Run the staged-package tests and verify RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_staged_package.py`

Expected: FAIL because `staged_package` and its public writer do not exist.

- [ ] **Step 3: Implement the staged writer with one-partition-at-a-time decoding**

```python
@dataclass(frozen=True, slots=True)
class HistoricalOwnerMetadata:
    provider_id: str
    normalization_version: str | None
    parent_reference: ValidationArtifactReference | None
    created_at: datetime
    retrieved_at: datetime
    coverage: HistoricalCorpusCoverage
    limitations: tuple[str, ...]


class StagedHistoricalPackageWriter:
    def add_partition(
        self, partition: HistoricalDataPartition
    ) -> HistoricalPartitionDescriptor:
        partition.verify_identity()
        _write_partition(self._stage / partition.relative_path, partition)
        descriptor = HistoricalPartitionDescriptor.from_reference_dict(
            partition.reference_dict()
        )
        self._descriptors.append(descriptor)
        return descriptor

    @property
    def decoded_record_count(self) -> int:
        return 0

    def finalize(self, metadata: HistoricalOwnerMetadata) -> HistoricalPackageIndex:
        manifest = build_historical_owner_manifest(
            artifact_kind=self._artifact_kind,
            bucket_count=self._bucket_count,
            partitions=tuple(self._descriptors),
            metadata=metadata,
        )
        return self._atomically_publish(manifest)
```

The finalizer writes `manifest.json`, `encoding.json`, `SHA256SUMS.json`, fsyncs the tree, validates with `load_historical_package_index`, then atomically renames to the owner-ID directory. It rejects duplicate timeframe/year/month/bucket keys, path escape, metadata/descriptor drift and conflicting pre-existing owner identity.

- [ ] **Step 4: Add descriptor-only PostgreSQL registration and exact reload**

```python
def register_index(
    self, package: HistoricalPackageIndex
) -> HistoricalPackageIndex:
    verified = load_historical_package_index(package.root)
    if verified != package:
        raise HistoricalCorpusIntegrityError(
            "Historical package changed between verification and registration"
        )
    verify_historical_package_files(verified)
    self._register_projection(verified)
    return self.open_index(verified.reference)
```

`register()` delegates its SQL projection to `_register_projection`; no migration runs in the repository constructor. The SQL validates parent reference, exact manifest, physical hash, ordered partition descriptors and checksums.

- [ ] **Step 5: Run focused package/repository tests and verify GREEN**

Run: `python -m pytest -q tests/application/historical_corpus/test_artifacts.py tests/application/historical_corpus/test_staged_package.py tests/persistence/postgres/test_historical_corpus_repository.py`

Expected: PASS, including legacy V1 full-package reload and new descriptor-index reload.

- [ ] **Step 6: Commit the package seam**

```bash
git add src/market_regime_alpha/application/historical_corpus tests/application/historical_corpus/test_staged_package.py tests/persistence/postgres/test_historical_corpus_repository.py
git commit -m "feat: stage bounded historical corpus packages"
```

### Task 2: Checkpointed real-data acquisition and streaming normalization

**Files:**
- Modify: `src/market_regime_alpha/application/historical_corpus/baostock_archive.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/normalization.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/historical_corpus/test_baostock_normalization.py`
- Test: `tests/application/continuous_research/test_cli.py`

**Interfaces:**
- Consumes: Task 1 `StagedHistoricalPackageWriter`; existing request checkpoints and `PostgresHistoricalCorpusRepository.register_index`.
- Produces: `BaoStockHistoricalArchiveClient.acquire_to_package(...) -> HistoricalPackageIndex`, `normalize_historical_package(...) -> HistoricalPackageIndex`, and CLI `historical-corpus-acquire`/`historical-corpus-replay` outputs containing exact owner/hash/physical-hash/coverage/performance fields.

- [ ] **Step 1: Write red tests for resume without network, bounded partition batches and normalized parent lineage**

```python
def test_acquire_to_package_resumes_checkpoints_without_provider_calls(tmp_path: Path) -> None:
    provider = FakeBaoStock()
    client = BaoStockHistoricalArchiveClient(baostock_module=provider)
    first = client.acquire_to_package(
        symbols=("000001.SZ", "600000.SH"),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
        acquisition_id="wp-alpha-proof-fixture",
        bucket_count=2,
    )
    calls = provider.query_calls
    second = client.acquire_to_package(
        symbols=("000001.SZ", "600000.SH"),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
        acquisition_id="wp-alpha-proof-fixture",
        bucket_count=2,
    )
    assert provider.query_calls == calls
    assert second.reference == first.reference
    assert second.physical_hash == first.physical_hash
```

- [ ] **Step 2: Run the acquisition test and verify RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_baostock_normalization.py -k 'package or resume'`

Expected: FAIL because package-oriented acquisition/normalization do not exist.

- [ ] **Step 3: Implement checkpoint catalog and staged Raw publication**

```python
@dataclass(frozen=True, slots=True)
class HistoricalRequestCheckpointDescriptor:
    path: Path
    symbol: str
    timeframe: Timeframe
    request_start: date
    request_end: date
    symbol_bucket: int
    source_row_count: int


def acquire_to_package(
    self,
    *,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
    artifact_root: Path,
    checkpoint_root: Path,
    acquisition_id: str,
    timeframes: tuple[Timeframe, ...] = (Timeframe.DAILY, Timeframe.MINUTE_5),
    timeframe_ranges: Mapping[Timeframe, tuple[date, date]] | None = None,
    bucket_count: int = 16,
) -> HistoricalPackageIndex:
    catalog = self._acquire_checkpoint_catalog(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        checkpoint_root=checkpoint_root,
        acquisition_id=acquisition_id,
        timeframes=timeframes,
        timeframe_ranges=timeframe_ranges,
        bucket_count=bucket_count,
    )
    return self._publish_checkpoint_catalog(
        catalog=catalog,
        artifact_root=artifact_root,
        bucket_count=bucket_count,
    )
```

The catalog stores paths and counts only. Publication groups exact checkpoint paths by existing partition key, decodes one group, adds one partition, releases it, and validates request ceilings, finite retry, corrupt checkpoints, missing requests, empty results and duplicate identities.

- [ ] **Step 4: Refactor normalization to a public per-partition transform and staged package path**

```python
def normalize_baostock_requests(
    requests: tuple[HistoricalRawRequest, ...]
) -> tuple[HistoricalNormalizedBar, ...]:
    bars = tuple(
        _normalize_row(request, row_number, row)
        for request in requests
        for row_number, row in enumerate(request.rows, 1)
    )
    return tuple(sorted(bars, key=_bar_sort_key))


def normalize_historical_package(
    *, raw: HistoricalPackageIndex, artifact_root: Path
) -> HistoricalPackageIndex:
    writer = StagedHistoricalPackageWriter(
        artifact_root=artifact_root,
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        bucket_count=raw.bucket_count,
    )
    for descriptor in raw.partitions:
        request_partition = read_verified_partition(raw, descriptor)
        bars = normalize_baostock_requests(
            tuple(cast(HistoricalRawRequest, item) for item in request_partition.records)
        )
        writer.add_partition(HistoricalDataPartition.create(
            artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
            timeframe=descriptor.timeframe,
            symbol_bucket=descriptor.symbol_bucket,
            bucket_count=descriptor.bucket_count,
            records=bars,
        ))
    return writer.finalize(normalized_metadata(raw))
```

The legacy `normalize_baostock_archive` calls the same per-request transform, preserving old identities.

- [ ] **Step 5: Make CLI an adapter and add no-network replay**

`historical-corpus-acquire` delegates acquire → `register_index` → normalize → `register_index`. `historical-corpus-replay` accepts exact Raw and Normalized references, uses `open_index`, verifies every physical file, independently regenerates the Normalized package in a temporary staging area, and requires the same logical owner/hash and physical checksum manifest.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/application/historical_corpus/test_baostock_normalization.py tests/application/continuous_research/test_cli.py tests/persistence/postgres/test_historical_corpus_repository.py`

Expected: PASS with provider call count unchanged during resume/replay and maximum decoded batch bounded by one partition.

- [ ] **Step 7: Commit acquisition and normalization**

```bash
git add src/market_regime_alpha/application/historical_corpus/baostock_archive.py src/market_regime_alpha/application/historical_corpus/normalization.py src/market_regime_alpha/cli/continuous_research.py tests/application/historical_corpus/test_baostock_normalization.py tests/application/continuous_research/test_cli.py
git commit -m "feat: acquire historical corpus with bounded replay"
```

### Task 3: Label-blind Locked OOS scope and Formal PIT access gate

**Files:**
- Create: `src/market_regime_alpha/application/historical_corpus/locked_oos_scope.py`
- Create: `src/market_regime_alpha/application/historical_corpus/postgres_locked_oos_scope.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/098_wp_alpha_proof_locked_scope.sql`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/historical_corpus/test_locked_oos_scope.py`
- Test: `tests/persistence/postgres/test_locked_oos_scope.py`
- Test: `tests/persistence/postgres/test_migrations.py`

**Interfaces:**
- Consumes: exact Calendar, historical constituent timeline, frozen protocol reference/hash and External final target `2026-01-19`; never consumes an Outcome owner.
- Produces: `FrozenLockedOOSScope`, `LockedOOSAccessDecision`, `PostgresLockedOOSScopeAuthority.freeze/get/assess_access` and CLI freeze/report.

- [ ] **Step 1: Write red tests for non-overlap, exact T+1 bindings, replay and fail-closed Outcome access**

```python
def test_locked_scope_freezes_after_external_without_reading_outcomes() -> None:
    outcome_loader = Mock(side_effect=AssertionError("outcome read"))
    scope = freeze_locked_oos_scope(
        protocol_reference=PROTOCOL,
        calendar=_calendar(),
        universe_timeline=_timeline(),
        external_final_target_session=date(2026, 1, 19),
        data_cutoff=CUTOFF,
    )
    decision = assess_locked_oos_access(
        scope=scope,
        formal_pit_references=(),
        physical_correctness_reference=None,
        owner_loader=outcome_loader,
    )
    assert scope.decision_sessions[0] > date(2026, 1, 19)
    assert decision.outcome_access_allowed is False
    assert decision.reason_codes == (
        "FORMAL_PIT_NOT_SUPPORTED",
        "PHYSICAL_CORRECTNESS_NOT_SUPPORTED",
    )
    outcome_loader.assert_not_called()
```

- [ ] **Step 2: Run Locked scope tests and verify RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_locked_oos_scope.py tests/persistence/postgres/test_locked_oos_scope.py`

Expected: FAIL because the typed owner and migration do not exist.

- [ ] **Step 3: Implement the immutable scope and pure gate**

```python
@dataclass(frozen=True, slots=True)
class FrozenLockedOOSScope:
    scope_id: ArtifactId
    scope_hash: str
    protocol_reference: ValidationArtifactReference
    calendar_reference: ValidationArtifactReference
    universe_timeline_reference: ValidationArtifactReference
    external_final_target_session: date
    data_cutoff: datetime
    decision_sessions: tuple[date, ...]
    target_session_bindings: tuple[tuple[date, date], ...]
    session_universe_hashes: tuple[tuple[date, str], ...]
    outcome_values_read: bool = False
    schema_version: str = "frozen-locked-oos-scope/v1"


def assess_locked_oos_access(
    *,
    scope: FrozenLockedOOSScope,
    formal_pit_supported: bool,
    physical_correctness_supported: bool,
) -> LockedOOSAccessDecision:
    reasons = tuple(sorted({
        *(()) if formal_pit_supported else ("FORMAL_PIT_NOT_SUPPORTED",),
        *(()) if physical_correctness_supported else (
            "PHYSICAL_CORRECTNESS_NOT_SUPPORTED",
        ),
    }))
    return LockedOOSAccessDecision(
        scope_reference=scope.reference,
        outcome_access_allowed=not reasons,
        reason_codes=reasons or ("LOCKED_OOS_ACCESS_ELIGIBLE",),
    )
```

The freezer derives sessions only from explicit Calendar entries, requires each target session to be the next Calendar session, binds effective PIT universe hashes without reading prices/labels, rejects Discovery/External overlap and rejects changed cutoff/protocol/calendar/timeline identity.

- [ ] **Step 4: Add append-only PostgreSQL owner and migration 098**

Migration 098 adds `FROZEN_LOCKED_OOS_SCOPE` to the existing Research Validation artifact-kind check and an append-only projection table keyed by `(scope_id, scope_hash)` with exact protocol/calendar/timeline references, session/target counts and `outcome_values_read = false`. It uses the existing `reject_append_only_mutation()` trigger.

- [ ] **Step 5: Add typed CLI freeze/report without Outcome dependencies**

`locked-oos-scope-freeze` accepts exact owner IDs/hashes and the frozen cutoff. `locked-oos-scope-report` accepts only `scope_id` and reloads the exact typed owner. Neither command imports Target Outcome, Shadow Outcome or Formal Evaluation value loaders.

- [ ] **Step 6: Run unit/PostgreSQL/migration tests and verify GREEN**

Run: `python -m pytest -q tests/application/historical_corpus/test_locked_oos_scope.py tests/persistence/postgres/test_locked_oos_scope.py tests/persistence/postgres/test_migrations.py`

Expected: PASS, including idempotent same-hash freeze, conflicting identity rejection and update/delete rejection.

- [ ] **Step 7: Commit Locked scope**

```bash
git add src/market_regime_alpha/application/historical_corpus/locked_oos_scope.py src/market_regime_alpha/application/historical_corpus/postgres_locked_oos_scope.py src/market_regime_alpha/persistence/postgres/migrations/098_wp_alpha_proof_locked_scope.sql src/market_regime_alpha/cli/continuous_research.py tests/application/historical_corpus/test_locked_oos_scope.py tests/persistence/postgres/test_locked_oos_scope.py tests/persistence/postgres/test_migrations.py
git commit -m "feat: freeze locked oos scope behind pit gate"
```

### Task 4: Independent physical correctness and frozen negative controls

**Files:**
- Modify: `src/market_regime_alpha/application/historical_corpus/raw_normalization_correctness.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/alpha_correctness.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/alpha_diagnostics.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_service.py`
- Test: `tests/application/historical_corpus/test_raw_normalization_correctness.py`
- Test: `tests/application/historical_corpus/test_alpha_correctness.py`
- Test: `tests/application/historical_corpus/test_alpha_correctness_diagnostics.py`

**Interfaces:**
- Consumes: exact Raw/Normalized package indexes, frozen Calendar/Universe/security-fact owners and protocol reference.
- Produces: an existing `HistoricalResearchEvidence` correctness payload containing physical verification, independent reproduction and negative controls, plus terminal `SUPPORTED`, `REJECTED`, `NOT_ESTIMABLE` or `DATA_BLOCKED`.

- [ ] **Step 1: Add failing tests for package-index correctness, future-data rejection and deterministic controls**

```python
def test_correctness_reads_physical_owners_and_emits_all_frozen_controls() -> None:
    result = run_raw_normalization_correctness_from_packages(
        raw_index=_raw_index(),
        normalized_index=_normalized_index(),
        queries=_bounded_queries(),
        protocol=FROZEN_CORRECTNESS,
    )
    assert result.physical_package_verified is True
    assert result.control_statuses == (
        ("FACTOR_LAG", "SUPPORTED"),
        ("PLACEBO", "SUPPORTED"),
        ("RANDOM_RANKING", "SUPPORTED"),
        ("SYMBOL_PERMUTATION", "SUPPORTED"),
        ("TARGET_PERMUTATION", "SUPPORTED"),
        ("TARGET_TIME_SHIFT", "SUPPORTED"),
    )
```

- [ ] **Step 2: Run correctness tests and verify RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_raw_normalization_correctness.py tests/application/historical_corpus/test_alpha_correctness.py tests/application/historical_corpus/test_alpha_correctness_diagnostics.py`

Expected: FAIL on the missing package-index campaign/result fields.

- [ ] **Step 3: Implement bounded package correctness and explicit terminal status**

The campaign verifies every checksum before selective reads; independently parses Raw rows; reproduces normalized identities, features, Decision cutoff, T+1 10:30 return, MFE/MAE and eligibility; checks duplicate/missing bars, adjustment/corporate-action limitations and future membership/status/revision. It partitions queries by timeframe/month/bucket and caps `max_rows`/`batch_size` through the existing selective-read contract.

- [ ] **Step 4: Add the frozen controls through existing diagnostics**

Use the fixed seed `20260813`, 2,000 moving-block draws and blocks `(1, 5, 10)`. Symbol/target permutations, target shift, factor lag and deterministic random ranking are identity-bound artifacts. Redundancy/ablation records pairwise rank/value association and leave-one-out deltas. Any missing control becomes `NOT_ESTIMABLE`; leakage, drift or corruption becomes `REJECTED`/`DATA_BLOCKED` and prevents Alpha qualification.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest -q tests/application/historical_corpus/test_raw_normalization_correctness.py tests/application/historical_corpus/test_alpha_correctness.py tests/application/historical_corpus/test_alpha_correctness_diagnostics.py tests/application/historical_corpus/test_phase_ii_evidence.py`

Expected: PASS.

```bash
git add src/market_regime_alpha/application/historical_corpus tests/application/historical_corpus
git commit -m "feat: prove physical historical correctness"
```

### Task 5: Frozen Discovery reproduction, Factor tournament and External execution

**Files:**
- Create: `src/market_regime_alpha/application/historical_corpus/vertical_slice.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/frozen_experiment.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_operator.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_service.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/historical_corpus/test_vertical_slice.py`
- Test: `tests/application/historical_corpus/test_phase_ii_operator.py`

**Interfaces:**
- Consumes: correctness evidence, reacquired physical owner references, existing Discovery Experiment/Evidence, External window, `FrozenAlphaHypothesis` and existing Phase-II evaluators.
- Produces: exact reproduction definition, Discovery drift result, complete frozen Factor family report, External evaluation and a consolidated read-only `AlphaProofStatus`.

- [ ] **Step 1: Write red tests that enforce protocol constants and dependency stops**

```python
def test_vertical_slice_cannot_change_preregistered_external_inputs() -> None:
    protocol = create_wp_alpha_proof_02_protocol(_owners())
    assert protocol.factor_directions == (
        ("intraday_return_to_decision_time", "HIGHER_IS_BETTER"),
        ("price_vs_vwap_return", "HIGHER_IS_BETTER"),
        ("vwap_slope", "HIGHER_IS_BETTER"),
    )
    assert protocol.top_k == 5
    assert protocol.cost_assumption == Decimal("0.002100")
    assert protocol.bootstrap_iterations == 2000
    assert protocol.block_lengths == (1, 5, 10)


def test_external_is_not_run_when_correctness_is_not_supported() -> None:
    external = Mock(side_effect=AssertionError("external executed"))
    status = execute_alpha_proof_vertical_slice(
        request=_request(correctness="DATA_BLOCKED"),
        external_evaluator=external,
    )
    assert status.external_validation == "NOT_ESTIMABLE"
    external.assert_not_called()
```

- [ ] **Step 2: Run vertical-slice tests and verify RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_vertical_slice.py tests/application/historical_corpus/test_phase_ii_operator.py`

Expected: FAIL because frozen WP composition/status do not exist.

- [ ] **Step 3: Implement immutable reproduction definition and thin composition**

`create_wp_alpha_proof_02_protocol` binds the existing Discovery and External parents plus new Raw/Normalized/Calendar/Universe/security owners. `execute_alpha_proof_vertical_slice` calls existing correctness, Discovery, External and Candidate services in dependency order. It never embeds Factor math, makes no OOS value request and has no scheduler/journal of its own.

- [ ] **Step 4: Persist every Factor outcome and External terminal result**

The Factor report includes coverage, RankIC, ICIR, positive IC ratio, Top/Bottom-5, spread, turnover, gross/net, confidence intervals, adjusted p-values, placebo, redundancy, ablation and temporal stability. The three frozen Factors alone feed External. Unsupported Factors remain negative/inconclusive evidence; no policy owner is admitted from them.

- [ ] **Step 5: Expose operator adapter and read-only report/replay**

Add `historical-alpha-proof` to `historical-phase-ii` operation parsing or as a sibling adapter that delegates the same service. Inputs are exact references, not inline computed panels. `historical-alpha-proof-report` reloads evidence; `replay` verifies hashes and emits the same status.

- [ ] **Step 6: Run focused tests and commit**

Run: `python -m pytest -q tests/application/historical_corpus/test_vertical_slice.py tests/application/historical_corpus/test_phase_ii_operator.py tests/application/historical_corpus/test_external_validation.py tests/application/historical_corpus/test_alpha_discovery.py`

Expected: PASS.

```bash
git add src/market_regime_alpha/application/historical_corpus src/market_regime_alpha/cli/continuous_research.py tests/application/historical_corpus
git commit -m "feat: execute frozen alpha evidence slice"
```

### Task 6: Candidate gate attribution and validated Alpha contribution

**Files:**
- Modify: `src/market_regime_alpha/candidates/policy.py`
- Create: `src/market_regime_alpha/application/continuous_research/validated_alpha.py`
- Modify: `src/market_regime_alpha/application/continuous_research/free_data_runtime.py`
- Modify: `src/market_regime_alpha/application/continuous_research/daily_alpha.py`
- Test: `tests/candidates/test_candidate_policy_v2.py`
- Test: `tests/application/continuous_research/test_validated_alpha.py`
- Test: `tests/persistence/postgres/test_free_data_continuous_runtime.py`

**Interfaces:**
- Consumes: owner-reloaded supported External evidence, admitted Candidate policy evidence and exact `CandidatePolicyRecord`.
- Produces: `ValidatedAlphaContributionProjection` and non-empty `DailyAlphaSymbolProjection.validated_alpha_contributions` only for the exact supported chain.

- [ ] **Step 1: Write red tests for Context separation and fail-closed contribution projection**

```python
def test_missing_unvalidated_context_does_not_hard_reject_challenger() -> None:
    evaluation = evaluate_candidate_policy(
        _challenger(context_adjustments=()),
        (_eligible_input(context_values={"theme": None}),),
    )
    record = evaluation.records[0]
    assert record.hard_integrity_eligible is True
    assert record.factor_available is True
    assert "CONTEXT_MISSING" not in record.hard_gate_failure_reasons


def test_validated_contribution_requires_same_external_candidate_lineage() -> None:
    with pytest.raises(ValueError, match="lineage"):
        project_validated_alpha_contribution(
            candidate=_candidate_record(),
            external_evidence=_external_evidence(experiment="external-a"),
            candidate_evidence=_candidate_evidence(experiment="external-b"),
        )
```

- [ ] **Step 2: Run Candidate/Daily tests and verify RED**

Run: `python -m pytest -q tests/candidates/test_candidate_policy_v2.py tests/application/continuous_research/test_validated_alpha.py tests/persistence/postgres/test_free_data_continuous_runtime.py`

Expected: FAIL because the owner-resolved contribution projection is absent.

- [ ] **Step 3: Implement immutable per-symbol explanation**

```python
@dataclass(frozen=True, slots=True)
class ValidatedFactorContribution:
    factor_id: str
    exposure: Decimal
    percentile: Decimal
    direction: str
    weight: Decimal
    contribution: Decimal


@dataclass(frozen=True, slots=True)
class ValidatedAlphaContributionProjection:
    candidate_reference: ValidationArtifactReference
    external_evidence_reference: ValidationArtifactReference
    candidate_evidence_reference: ValidationArtifactReference
    factor_contributions: tuple[ValidatedFactorContribution, ...]
    context_adjustment: Decimal
    final_score: Decimal
```

The projector verifies exact experiment/hypothesis/dataset/factor/policy references, `SUPPORTED` External status, non-superseded Candidate evidence and arithmetic equality between contributions, Context and final score. Missing/drifted/rejected evidence emits no validated projection.

- [ ] **Step 4: Wire Daily Alpha without changing Signal semantics**

Continuous runtime reloads the evidence root through existing typed owners. Supported same-lineage Candidate rows populate validated contributions; incumbent and exploratory rows remain in diagnostics. Context stays in `conditional_context`; it is never renamed as Alpha.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest -q tests/candidates/test_candidate_policy_v2.py tests/application/continuous_research/test_validated_alpha.py tests/application/continuous_research/test_daily_alpha.py tests/persistence/postgres/test_free_data_continuous_runtime.py`

Expected: PASS, including the old empty-contribution behavior for inactive evidence.

```bash
git add src/market_regime_alpha/candidates/policy.py src/market_regime_alpha/application/continuous_research tests/candidates/test_candidate_policy_v2.py tests/application/continuous_research/test_validated_alpha.py tests/persistence/postgres/test_free_data_continuous_runtime.py
git commit -m "feat: project validated alpha contributions"
```

### Task 7: Forecast baseline comparison under the frozen sample contract

**Files:**
- Create: `src/market_regime_alpha/application/historical_corpus/forecast_comparison.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_service.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_operator.py`
- Test: `tests/application/historical_corpus/test_forecast_comparison.py`
- Test: `tests/application/historical_corpus/test_context_conditional.py`

**Interfaces:**
- Consumes: supported Candidate evidence, exact PathForecast/sample/model owners, three frozen inputs and only Discovery/External sessions.
- Produces: immutable naive/Path/Conditional metrics, lift status and `FORECAST_BASELINE_BEATEN` without calibration promotion.

- [ ] **Step 1: Write red tests for purge/embargo, search budget and negative lift**

```python
def test_forecast_comparison_rejects_conditional_without_baseline_lift() -> None:
    result = compare_forecasts(
        samples=_walk_forward_samples(),
        penalties=(Decimal("0.1"), Decimal("1")),
        maximum_candidate_fits_per_fold=2,
        purge_target_sessions=1,
        seed=20260813,
    )
    assert result.conditional.status == "REJECTED"
    assert result.forecast_baseline_beaten is False
    assert result.calibration_status == "NOT_CALIBRATED"
```

- [ ] **Step 2: Run Forecast tests and verify RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_forecast_comparison.py tests/application/historical_corpus/test_context_conditional.py`

Expected: FAIL because the three-way comparison owner is absent.

- [ ] **Step 3: Implement deterministic comparison by composing existing model owners**

The naive baseline uses only prior admissible target observations. Path metrics reload the exact empirical PathForecast. Conditional fitting delegates the current deterministic regularized-linear owner with penalties `(0.1, 1)`, at most two fits/fold, one-target-session purge/embargo and frozen seed. The result reports coverage, return/MFE/MAE error, barrier discrimination, temporal stability and lift; raw barrier heads are never probabilities.

- [ ] **Step 4: Persist and replay comparison evidence**

The Phase-II service records the comparison under existing Historical Evidence with exact sample/model/baseline/Candidate references. Rejected/not-estimable comparison cannot create Calibration admission and cannot be swapped for another model family.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest -q tests/application/historical_corpus/test_forecast_comparison.py tests/application/historical_corpus/test_context_conditional.py tests/application/historical_corpus/test_phase_ii_evidence.py`

Expected: PASS.

```bash
git add src/market_regime_alpha/application/historical_corpus tests/application/historical_corpus
git commit -m "feat: compare frozen forecast baselines"
```

### Task 8: Executable A-share economics and exact attribution

**Files:**
- Modify: `src/market_regime_alpha/application/strategy_shadow/economics.py`
- Create: `src/market_regime_alpha/application/strategy_shadow/attribution.py`
- Modify: `src/market_regime_alpha/application/historical_research/multi_strategy.py`
- Test: `tests/application/strategy_shadow/test_economics.py`
- Test: `tests/application/strategy_shadow/test_attribution.py`
- Test: `tests/application/historical_research/test_multi_strategy.py`

**Interfaces:**
- Consumes: exact owner-resolved post-cutoff bar observations, Target Outcome, liquidity/capacity, Candidate/Signal/Forecast/Opportunity/Strategy/Portfolio references and V1 policy compatibility.
- Produces: V2 `FIRST_POST_INFORMATION_CUTOFF_OBSERVABLE` execution economics plus `StrategyAttributionResult`; V1 identities decode/replay unchanged.

- [ ] **Step 1: Write red tests for executable entry, A-share constraints and attribution balance**

```python
def test_v2_uses_first_post_cutoff_bar_and_conservative_fill() -> None:
    result = evaluate_strategy_economics(
        policy=_v2_policy(entry_kind="FIRST_POST_INFORMATION_CUTOFF_OBSERVABLE"),
        label=_label(),
        liquidity=_liquidity(fillability="0.5"),
        entry_execution=_entry_bar(at="2026-01-20T14:56:00+08:00", price="10"),
        exit_execution=_exit_bar(price="10.2"),
        requested_notional=Decimal("2500"),
        evaluated_at=AVAILABLE_AT,
    )
    assert result.filled_quantity == Decimal("100")
    assert result.gross_return == Decimal("0.02")
    assert result.net_return == result.gross_return - result.cost_return


def test_limit_up_buy_and_limit_down_sell_fail_closed() -> None:
    assert _evaluate(entry_condition="LIMIT_UP").status is StrategyEconomicsStatus.NO_ENTRY
    assert _evaluate(exit_condition="LIMIT_DOWN").status is StrategyEconomicsStatus.NOT_ESTIMABLE
```

- [ ] **Step 2: Run economics tests and verify RED**

Run: `python -m pytest -q tests/application/strategy_shadow/test_economics.py tests/application/strategy_shadow/test_attribution.py tests/application/historical_research/test_multi_strategy.py`

Expected: FAIL because V2 entry kind/attribution are absent.

- [ ] **Step 3: Add V2 entry semantics while preserving V1 schemas**

Add `FIRST_POST_INFORMATION_CUTOFF_OBSERVABLE`, `NEXT_ELIGIBLE_BAR_OPEN` and `SESSION_CLOSE` to a V2 policy schema. V2 requires entry observation effective time strictly after information cutoff, exact source bar owner/hash and historical price-limit/listing/trading condition facts. Existing `FROZEN_DECISION_REFERENCE` remains V1-only and produces byte-identical identities.

- [ ] **Step 4: Complete conservative cost/fill accounting**

Compute round lots, T+1 sell availability, participation/capacity ceiling, partial filled notional, commission, stamp duty, spread/slippage and impact with each parameter provenance. Suspension, ST restriction, missing quote, limit-up buy, limit-down sell and corporate-action ambiguity fail closed. Outputs separate gross, explicit cost, slippage/impact, fillability loss, net, turnover, MFE/MAE and entry delay.

- [ ] **Step 5: Add exact additive attribution**

`StrategyAttributionResult` binds Factor, Context, Candidate, Signal, Forecast, Risk, Opportunity, Strategy, Portfolio, Market Outcome, Strategy Outcome and cost owners. Its validation requires `strategy_net = gross - explicit_cost - slippage_impact - fillability_loss` within exact Decimal arithmetic and never equates Market Outcome with Strategy PnL.

- [ ] **Step 6: Run focused tests and commit**

Run: `python -m pytest -q tests/application/strategy_shadow/test_economics.py tests/application/strategy_shadow/test_attribution.py tests/application/historical_research/test_multi_strategy.py tests/application/historical_corpus/test_external_validation.py`

Expected: PASS, including V1 characterization/replay.

```bash
git add src/market_regime_alpha/application/strategy_shadow src/market_regime_alpha/application/historical_research/multi_strategy.py tests/application/strategy_shadow tests/application/historical_research/test_multi_strategy.py
git commit -m "feat: add executable research economics attribution"
```

### Task 9: Source-freeze extraction and affected architecture compression

**Files:**
- Create: `src/market_regime_alpha/application/source_freeze/acquisition.py`
- Modify: `src/market_regime_alpha/application/source_freeze/service.py`
- Modify: `src/market_regime_alpha/application/daily_loop/runner.py`
- Modify: `src/market_regime_alpha/application/daily_loop/__init__.py`
- Test: `tests/application/source_freeze/test_acquisition.py`
- Test: `tests/application/daily_loop/test_runner.py`
- Test: `tests/platform/test_architecture_boundaries.py`

**Interfaces:**
- Consumes: current provider acquisition/freeze commands used by Continuous runtime.
- Produces: `acquire_and_freeze_source(command, provider, repository)` under the existing Source Freeze boundary; DailyLoop remains a compatibility decoder only.

- [ ] **Step 1: Write characterization and differential red tests**

```python
def test_source_freeze_primitive_matches_daily_loop_compatibility_receipt() -> None:
    direct = acquire_and_freeze_source(_command(), _provider(), _repository())
    legacy = DailyLoopRunner(_provider(), _repository()).acquire_and_freeze(_command())
    assert direct.to_canonical_dict() == legacy.to_canonical_dict()
```

- [ ] **Step 2: Run Source Freeze/architecture tests and verify RED**

Run: `python -m pytest -q tests/application/source_freeze/test_acquisition.py tests/application/daily_loop/test_runner.py tests/platform/test_architecture_boundaries.py`

Expected: FAIL because the primitive is still owned by DailyLoopRunner.

- [ ] **Step 3: Extract the primitive and thin the wrapper**

Move only provider acquisition, immutable source freeze and receipt construction. `DailyLoopRunner.acquire_and_freeze` delegates for replay compatibility; obsolete B0/B1/finalization branches with no consumer are removed only after `rg` consumer proof and differential tests. Continuous/Historical runtime imports must not point to DailyLoop.

- [ ] **Step 4: Run tests and commit**

Run: `python -m pytest -q tests/application/source_freeze/test_acquisition.py tests/application/daily_loop/test_runner.py tests/application/daily_loop/test_cli.py tests/platform/test_architecture_boundaries.py`

Expected: PASS.

```bash
git add src/market_regime_alpha/application/source_freeze src/market_regime_alpha/application/daily_loop tests/application/source_freeze tests/application/daily_loop tests/platform/test_architecture_boundaries.py
git commit -m "refactor: retire daily loop acquisition ownership"
```

### Task 10: Real acquisition and canonical research campaign

**Files:**
- Create during execution only: immutable files below the configured Artifact Root and append-only PostgreSQL rows; no CSV authority or repository fixture.
- Modify after execution: `docs/status/Current-State.md`
- Modify after execution: `docs/status/Capability-Matrix.md`
- Modify after execution: `docs/status/Gap-Register.md`
- Modify after execution: `docs/status/Roadmap.md`
- Create: `docs/research/results/WP-ALPHA-PROOF-02-Execution-Report.md`

**Interfaces:**
- Consumes: Tasks 1–9 operator surfaces and the frozen protocol.
- Produces: real Raw/Normalized owners, PIT assessment, correctness/Discovery/External/Factor/Candidate/Forecast/Strategy/Attribution evidence and final status; no Locked OOS Outcome when the gate is closed.

- [ ] **Step 1: Create a fresh migrated campaign database and discover its schema from the catalog**

Run explicit migration tooling against a newly named database, then query `pg_namespace`, `pg_class`, `pg_attribute` and `schema_migration` discovered from packaged migrations. Record actual schema, migration 098, PostgreSQL version and database size. No schema name is inferred from database name.

- [ ] **Step 2: Resolve latest completed session and PIT universe through canonical owners**

Run the existing Calendar and `historical-universe-history-sync`/`historical-security-facts-sync` operators for `2025-01-01` through the frozen cutoff. Require effective CSI300 membership per session; persist listing/ST/suspension/eligibility/adjustment facts actually available. Record every provider limitation and missing fact.

- [ ] **Step 3: Freeze the Locked OOS scope before any outcome-accessing command**

Run `locked-oos-scope-freeze` with exact protocol/Calendar/timeline IDs and cutoff. Verify report/replay hash and `outcome_values_read=false`. Run access assessment; if Formal PIT is incomplete, verify `outcome_access_allowed=false` and do not create or invoke any Locked OOS panel/Target/Forecast/Strategy/Evaluation input.

- [ ] **Step 4: Acquire and publish real Daily+5m data**

Run `historical-corpus-acquire` for the PIT union plus exact context instruments from `2025-01-01` through the owner-resolved latest completed session. Capture acquisition ID, request counts, provider failures, durations, peak RSS, Artifact Root size and PostgreSQL size. Interrupt once after durable checkpoints, resume with the same acquisition ID, then replay without network and require identical semantic/physical identities.

- [ ] **Step 5: Execute independent physical correctness**

Run `historical-phase-ii CORRECTNESS` against exact new Raw/Normalized owners, Calendar, timeline and security facts. Record checksum, bar integrity, cutoff, feature/Target/MFE/MAE reproduction, leakage controls, permutations/placebo/redundancy/ablation and replay. If terminal status is not supported, stop Alpha qualification but continue reporting, prospective engineering checks and regression.

- [ ] **Step 6: Reproduce Discovery and run frozen External once when dependencies permit**

Use canonical Historical Research/Phase-II owners for the exact frozen rosters. Record Discovery reproduction/drift, the complete Factor tournament and External evaluation separately. Do not change protocol values or run External again based on results.

- [ ] **Step 7: Run permitted downstream Candidate/Signal/Forecast/Strategy/Attribution stages**

Only supported upstream evidence may enter each stage. Record Incumbent/Challenger coverage, gates and contributions; Signal states/reasons; naive/Path/Conditional comparison; calibration eligibility; Overnight/Swing/Conditional economics; Portfolio decisions; and additive attribution. Preserve rejected/not-estimable/data-blocked evidence and stop result-driven searches.

- [ ] **Step 8: Verify prospective-ready composition without historical prediction backfill**

Resolve the frozen Experiment/Candidate/Forecast/Strategy/economics/Portfolio references through the existing Continuous/Shadow composition. Do not fabricate a past prediction and do not promote. Record `PROSPECTIVE_READY` or its blockers, `PROSPECTIVE_PROVEN=false`, `PRODUCTION_QUALIFIED=false`.

- [ ] **Step 9: Write the execution report and status documents from actual owner results**

The report includes Data counts/coverage/missingness, PIT, physical correctness, Factor metrics, External, Candidate, Signal, Forecast, Strategy, Portfolio, Attribution, negative evidence, performance, validation and Evidence Ceiling. It explicitly states `LOCKED_OOS_CONSUMED=false` whenever Formal PIT is not supported.

- [ ] **Step 10: Commit campaign evidence documentation**

```bash
git add docs/research/results/WP-ALPHA-PROOF-02-Execution-Report.md docs/status/Current-State.md docs/status/Capability-Matrix.md docs/status/Gap-Register.md docs/status/Roadmap.md
git commit -m "docs: record alpha proof campaign evidence"
```

### Task 11: Fresh/upgrade PostgreSQL, full regression, final convergence and delivery

**Files:**
- Modify: `docs/research/protocols/WP-ALPHA-PROOF-02-Implementation-Plan.md` (delete after execution; Git history preserves it)
- Modify: current status/operations docs only if validation changes facts.
- Test: entire repository.

**Interfaces:**
- Consumes: all implementation/evidence commits.
- Produces: clean branch, full validation ledger, pushed branch and Draft PR.

- [ ] **Step 1: Validate PostgreSQL fresh install and main-to-098 upgrade**

Apply `001→098` to a fresh database. Clone a database at main migration 097, apply only 098, then verify migration idempotency/concurrency, append-only constraints, exact ID/hash reload and no runtime implicit migration. Run affected PostgreSQL acquisition/replay/outcome/strategy/portfolio tests.

- [ ] **Step 2: Run the required full validation ledger**

```bash
uv sync --frozen --extra dev --extra postgres
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
git diff --check
```

Every command is recorded as PASS or FAIL. Any failure is diagnosed and fixed through a new red/green cycle; no historical failure is waived.

- [ ] **Step 3: Self-review implementation against the frozen protocol**

Verify no changed partition, Factor direction, Top-K, cost, search budget, threshold, seed or stopping rule; no Locked OOS Outcome access; no inferred PIT timestamps; no new runtime/authority framework; no modified migration 001–097; no `.idea/modules.xml` change.

- [ ] **Step 4: Remove the executed implementation plan and finalize current docs**

Delete this plan from the active docs tree after all tasks are completed, retain the frozen protocol and immutable result report, run docs validation again, and commit:

```bash
git add docs
git commit -m "docs: finalize alpha proof evidence status"
```

- [ ] **Step 5: Review commits and repository cleanliness**

Run `git status --short --branch`, `git log --oneline origin/main..HEAD`, `git diff --stat origin/main...HEAD`, `git diff --check origin/main...HEAD`, and inspect staged/unstaged files. Working tree must be clean.

- [ ] **Step 6: Push and create Draft PR**

```bash
git push -u origin agent/wp-alpha-proof-02
gh pr create --draft --base main --head agent/wp-alpha-proof-02 --title "WP-ALPHA-PROOF-02: formal PIT alpha evidence slice" --body-file /tmp/wp-alpha-proof-02-pr.md
```

The PR body separates Engineering, Real Data, Physical Correctness, Formal PIT, Exploratory, External, Locked OOS, Strategy Economics, Prospective and Production statuses and never upgrades unsupported evidence.

---

## Plan self-review

- **Spec coverage:** Tasks 1–2 cover resumable bounded physical acquisition and independent package replay; Task 3 freezes Locked OOS without label access; Task 4 covers physical correctness/leakage/controls; Task 5 covers frozen Discovery/Factor/External; Task 6 covers Candidate gating and validated contribution; Task 7 covers Forecast baselines; Task 8 covers A-share economics/attribution; Task 9 covers affected legacy convergence; Task 10 runs the real campaign and prospective-ready check; Task 11 covers PostgreSQL/full regression/Git delivery.
- **Evidence discipline:** Every research stage is dependency-gated and accepts negative, not-estimable or data-blocked outcomes. Formal PIT and physical correctness gate Locked OOS before any value loader.
- **Type consistency:** Staged package methods return `HistoricalPackageIndex`; PostgreSQL registers/reloads exact indexes; downstream physical reads use existing `HistoricalReadQuery`; all Evidence references use `ValidationArtifactReference`; Locked scope is a typed owner in the existing Research Validation authority.
- **No parallel platform:** `vertical_slice.py` is a composition/status projection over current operators, not a runner, journal, scheduler or authority.
