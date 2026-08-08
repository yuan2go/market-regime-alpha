# WP-PIT-01 Formal Point-in-Time Authority Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Draft PR #42 merge-ready by closing required-fact collisions, resolving canonical Artifact authority, separating prospective and historical PIT, removing global write serialization safely, and replaying from explicit immutable selections.

**Architecture:** Keep one PIT bounded context. `pit_authority.py` owns immutable contracts and pure policy, `pit_artifact_authority.py` adapts existing strict canonical Readers into typed resolution receipts, and `postgres_pit_authority.py` owns append-only resolution/admission/snapshot/replay transactions. PostgreSQL `REPEATABLE READ` supplies validation consistency; explicit Fact, Qualification and Resolution bindings supply replay truth.

**Tech Stack:** Python 3.12, frozen dataclasses/enums, psycopg 3, PostgreSQL 16, pytest, Ruff, mypy, uv/build.

## Global Constraints

- Correct unmerged migration 028 in place; no PIT v1 compatibility layer.
- PostgreSQL is the only PIT ledger, snapshot and replay authority.
- Reuse existing canonical Readers; do not create parallel Dataset, Universe, Eligibility or Feature owners.
- Missing reliable Readers fail closed.
- Public/free Providers cannot reach `FORMAL_PIT_PROVIDER` under the default policy.
- No automatic Model qualification, lifecycle transition, Champion assignment, Entry, Broker, UI, H8 or H9 work.
- Preserve the user's `.idea/modules.xml` modification and exclude it from every commit.

---

### Task 1: Contract attacks, typed evidence and temporal modes

**Files:**
- Modify: `src/market_regime_alpha/data/pit_authority.py`
- Modify: `tests/data/test_pit_authority.py`

**Interfaces:**
- Produces: `PITContractError`, `PITArtifactKind`, `PITFactEvidenceMode`, `PITSourceEvidenceLevel`, `PITProviderEvidenceKind`, `PITProviderEvidence`, `ProviderQualificationPolicy`, `PITFactTemporalAuthority`, `PITSelectedFactBinding`.
- Produces: `require_unique_required_fact_keys(required_facts: tuple[PITRequiredFact, ...]) -> None`.
- Preserves: `FormalPITValidationRequest`, `PITAsOfQuery`, `PITFactRevision`, `FormalPITEvidenceArtifact` as the public PIT contracts.

- [ ] **Step 1: Write RED collision and direct-construction attacks**

```python
@pytest.mark.parametrize(
    "facts",
    [
        (
            PITRequiredFact("same", PITFactKind.MARKET_DATA, "600000.SH"),
            PITRequiredFact("same", PITFactKind.ST_STATUS, "600000.SH"),
        ),
        (
            PITRequiredFact("same", PITFactKind.ST_STATUS, "600000.SH"),
            PITRequiredFact("same", PITFactKind.ST_STATUS, "600001.SH"),
        ),
        (
            PITRequiredFact("same", PITFactKind.ST_STATUS, "600000.SH"),
            PITRequiredFact("same", PITFactKind.ST_STATUS, "600000.SH"),
        ),
    ],
)
def test_required_fact_logical_keys_are_globally_unique(facts):
    with pytest.raises(PITContractError, match="logical_key collision"):
        FormalPITValidationRequest.create(**request_values(required_facts=facts))
    with pytest.raises(PITContractError, match="logical_key collision"):
        PITAsOfQuery.create(
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            required_facts=facts,
        )
```

- [ ] **Step 2: Run the attacks and confirm RED**

Run: `uv run pytest -o addopts='' -q tests/data/test_pit_authority.py`

Expected: collision cases fail because the current contracts silently normalize them.

- [ ] **Step 3: Implement typed contracts and no-dedup normalization**

```python
class PITContractError(ValueError):
    """A caller attempted to bypass a PIT contract invariant."""


def require_unique_required_fact_keys(
    required_facts: tuple[PITRequiredFact, ...],
) -> None:
    seen: dict[str, PITRequiredFact] = {}
    for item in required_facts:
        previous = seen.get(item.logical_key)
        if previous is not None:
            raise PITContractError(
                "required_facts logical_key collision: " + item.logical_key
            )
        seen[item.logical_key] = item
```

Call this helper from both dataclass `__post_init__` methods and both `create`
methods before sorting. Add the typed Provider evidence, policy, temporal mode
and selected-binding dataclasses with canonical hashes and exact field checks.

- [ ] **Step 4: Add pure policy tests**

```python
def test_default_provider_policy_prevents_public_source_inflation():
    policy = ProviderQualificationPolicy.default()
    for provider in ("tencent", "baostock", "akshare", "tushare-free"):
        with pytest.raises(PITContractError, match="evidence ceiling"):
            policy.require_level(provider, PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER)


def test_historical_mode_requires_revision_archive_and_typed_evidence():
    with pytest.raises(PITContractError, match="historical Provider PIT"):
        PITFactTemporalAuthority(
            mode=PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT,
            provider_available_at=DECISION_TIME,
            provider_recorded_at=DECISION_TIME,
            provider_revision=None,
            provider_dataset_version=None,
            provider_archive=None,
            provider_evidence=(),
        )
```

- [ ] **Step 5: Run contract tests and commit**

Run: `uv run pytest -o addopts='' -q tests/data/test_pit_authority.py`

Expected: PASS.

Commit: `git commit -m "fix(pit): close contract and temporal authority gaps"`

### Task 2: Canonical Artifact resolution through existing Readers

**Files:**
- Create: `src/market_regime_alpha/data/pit_artifact_authority.py`
- Create: `tests/data/test_pit_artifact_authority.py`

**Interfaces:**
- Produces: `PITArtifactAuthorityResolver.resolve(reference: PITArtifactReference, locator: Path, *, resolved_at: datetime, actor: str, reason: str) -> PITArtifactAuthorityResolution`.
- Produces: `FilesystemPITArtifactAuthorityResolver` and `PITArtifactAuthorityUnavailableError`.
- Consumes existing Readers: `load_controlled_source_manifest`, `load_controlled_trading_calendar`, `load_verified_market_data_dataset`, `load_operational_universe`, `load_verified_feature_bundle_v2`.

- [ ] **Step 1: Write RED real-Reader and forgery tests**

```python
def test_filesystem_resolver_reconstructs_source_manifest(controlled_manifest_path, now):
    manifest = load_controlled_source_manifest(controlled_manifest_path)
    reference = PITArtifactReference(
        PITArtifactKind.SOURCE_MANIFEST,
        manifest.source_manifest_id,
        manifest.content_hash,
    )
    resolution = FilesystemPITArtifactAuthorityResolver().resolve(
        reference,
        controlled_manifest_path,
        resolved_at=now,
        actor="test-reader",
        reason="resolve canonical SourceManifest",
    )
    assert resolution.reference == reference
    assert resolution.canonical_schema == manifest.schema_version


def test_filesystem_resolver_rejects_forged_identity(controlled_manifest_path, now):
    forged = PITArtifactReference(
        PITArtifactKind.SOURCE_MANIFEST,
        ArtifactId("forged-source-manifest"),
        "sha256:" + "f" * 64,
    )
    with pytest.raises(PITArtifactAuthorityUnavailableError, match="identity"):
        FilesystemPITArtifactAuthorityResolver().resolve(
            forged,
            controlled_manifest_path,
            resolved_at=now,
            actor="attacker",
            reason="forged",
        )
```

- [ ] **Step 2: Implement the resolver routing table**

```python
class FilesystemPITArtifactAuthorityResolver:
    def resolve(self, reference, locator, *, resolved_at, actor, reason):
        if reference.reference_kind is PITArtifactKind.SOURCE_MANIFEST:
            artifact = load_controlled_source_manifest(locator)
            actual_id = artifact.source_manifest_id
            actual_hash = artifact.content_hash
            schema = artifact.schema_version
        elif reference.reference_kind is PITArtifactKind.MARKET_DATA_DATASET:
            verified = load_verified_market_data_dataset(locator)
            artifact = verified.artifact
            actual_id = ArtifactId(str(artifact.dataset_id))
            actual_hash = artifact.content_hash
            schema = artifact.schema_version
        else:
            raise PITArtifactAuthorityUnavailableError(
                f"no reliable canonical Reader for {reference.reference_kind.value}"
            )
        if (actual_id, actual_hash) != (reference.artifact_id, reference.content_hash):
            raise PITArtifactAuthorityUnavailableError("canonical Artifact identity mismatch")
        return PITArtifactAuthorityResolution.create(
            reference=reference,
            canonical_schema=schema,
            reader_contract=type(self).__name__ + "/v1",
            data_eligibility=getattr(artifact, "data_eligibility", None),
            formal_pit_status=getattr(artifact, "formal_pit_status", None),
            effective_at=getattr(artifact, "effective_at", None),
            available_at=getattr(artifact, "available_at", None),
            physical_checksums_hash=getattr(locals().get("verified"), "checksums_hash", None),
            resolved_at=resolved_at,
            actor=actor,
            reason=reason,
        )
```

Complete the exact routing for Calendar, Universe and Feature Bundle. Explicitly
raise the unavailable error for Eligibility, Model Configuration and Validation
Protocol until a reliable Reader exists.

- [ ] **Step 3: Prove wrong authority kinds and missing Readers fail closed**

Run: `uv run pytest -o addopts='' -q tests/data/test_pit_artifact_authority.py`

Expected: PASS, including strict package tamper tests and fail-closed unsupported types.

- [ ] **Step 4: Commit**

Commit: `git commit -m "feat(pit): resolve canonical artifact authority"`

### Task 3: Migration 028 and durable resolution/source admission

**Files:**
- Modify: `src/market_regime_alpha/persistence/postgres/migrations/028_formal_pit_authority.sql`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/data/postgres_pit_authority.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `tests/persistence/postgres/test_migrator.py`
- Modify: `tests/persistence/postgres/test_pit_authority.py`
- Modify: `tests/persistence/postgres/pit_fixture.py`

**Interfaces:**
- Produces: `PostgresPITAuthority.record_artifact_resolution(...)`.
- Changes: `record_source_qualification` requires source/evidence resolutions and the repository-bound qualification policy.
- Persists: `pit_artifact_authority_resolution` plus exact resolution and policy bindings.

- [ ] **Step 1: Write RED migration/catalog and forged-resolution tests**

```python
def test_migration_028_adds_artifact_resolution_authority(postgres_factory):
    PostgresMigrator().apply_all(postgres_factory)
    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT to_regclass('pit_artifact_authority_resolution')"
        ).fetchone() == ("pit_artifact_authority_resolution",)


def test_source_qualification_rejects_unresolved_manifest(postgres_factory):
    authority = fixture_authority(postgres_factory)
    with pytest.raises(PITAuthorityConflictError, match="SourceManifest resolution"):
        authority.record_source_qualification(
            source_qualification(),
            idempotency_key="unresolved-manifest",
        )
```

- [ ] **Step 2: Correct migration 028 in place**

Add an append-only `pit_artifact_authority_resolution` table whose primary
identity is the resolution ID/hash and whose unique canonical key is
`(reference_kind, artifact_id, artifact_hash)`. Add foreign keys from source
qualification and fact rows to their exact resolution and qualification IDs.
Extend action types with `RESOLVE_ARTIFACT`. Preserve append-only triggers.

- [ ] **Step 3: Implement resolver admission and default policy composition**

```python
def record_artifact_resolution(
    self,
    reference: PITArtifactReference,
    *,
    locator: Path,
    actor: str,
    reason: str,
    idempotency_key: str,
) -> PITArtifactAuthorityResolution:
    resolved_at = _whole_second(self._clock())
    resolution = self._artifact_resolver.resolve(
        reference,
        locator,
        resolved_at=resolved_at,
        actor=actor,
        reason=reason,
    )
    with self._connect() as connection:
        _acquire_idempotency_lock(connection, idempotency_key)
        acquire_scope_lock(
            connection,
            namespace="pit-artifact-resolution",
            identity=f"{reference.reference_kind.value}:{reference.artifact_id}:{reference.content_hash}",
        )
        return _insert_or_restore_resolution(connection, resolution, idempotency_key)
```

`RepositoryFactory.pit_authority()` uses the default fail-closed resolver and
default policy unless a test or CLI explicitly injects another resolver.

- [ ] **Step 4: Run PostgreSQL admission tests**

Run: `uv run pytest -o addopts='' -q tests/persistence/postgres/test_migrator.py tests/persistence/postgres/test_pit_authority.py`

Expected: PASS for migration, append-only resolution, typed policy ceiling,
idempotency and source suspension.

- [ ] **Step 5: Commit**

Commit: `git commit -m "feat(pit): persist artifact and source authority"`

### Task 4: Fact admission and prospective/historical time semantics

**Files:**
- Modify: `src/market_regime_alpha/data/pit_authority.py`
- Modify: `src/market_regime_alpha/data/postgres_pit_authority.py`
- Modify: `tests/persistence/postgres/pit_fixture.py`
- Modify: `tests/persistence/postgres/test_pit_authority.py`
- Modify: `tests/persistence/postgres/test_pit_leakage.py`

**Interfaces:**
- Changes: `record_fact` attaches exact source qualification and Artifact resolutions.
- Changes: `RecordedPITFactRevision.system_imported_at` is database-clock evidence.
- Preserves compatibility property: none; the unmerged `ingested_at` shape is corrected directly.

- [ ] **Step 1: Write RED temporal-mode attacks**

```python
def test_prospective_late_system_import_is_not_visible(postgres_factory):
    authority = complete_fixture_authority(postgres_factory, clock=MutableClock(NOW))
    recorded = authority.record_fact(prospective_fact(required_facts()[1]), **FACT_COMMAND)
    assert recorded.system_imported_at == NOW
    snapshot = authority.as_of(current_query((required_facts()[1],)))
    assert snapshot.outcome is PITValidationOutcome.REJECTED
    assert "LATE_PROSPECTIVE_IMPORT_REJECTED" in snapshot.rejection_codes[0]


def test_historical_provider_import_may_be_late_with_authority(postgres_factory):
    authority = complete_fixture_authority(postgres_factory, clock=MutableClock(NOW))
    recorded = authority.record_fact(
        historical_fact(
            required_facts()[1],
            provider_revision="rev-2024-04-30-1",
            provider_dataset_version="pit-archive-2024-v1",
            provider_archive=resolved_archive_reference(),
        ),
        **FACT_COMMAND,
    )
    assert recorded.system_imported_at == NOW
    assert authority.as_of(current_query((required_facts()[1],))).outcome is PITValidationOutcome.SATISFIED
```

- [ ] **Step 2: Implement shared-source/exclusive-qualification locking**

Add `acquire_scope_shared_lock` beside the existing PostgreSQL helper. Source
qualification takes the existing exclusive lock; fact admission takes the
shared form and then its exclusive `(scope_id, logical_key)` lock. Query the
latest qualification under this lock and store its exact ID/hash.

- [ ] **Step 3: Implement mode-specific as-of visibility**

Prospective selection applies all three provider/system cutoffs. Historical
selection applies historical Provider availability and typed authority but does
not compare `system_imported_at` to the historical DecisionTime. Both modes
still enforce Event Time, Effective interval and expiry.

- [ ] **Step 4: Add revision-correction and unqualified-provider tests**

Run: `uv run pytest -o addopts='' -q tests/persistence/postgres/test_pit_authority.py tests/persistence/postgres/test_pit_leakage.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `git commit -m "fix(pit): separate captured and provider historical time"`

### Task 5: Repeatable-read validation, explicit replay and concurrency

**Files:**
- Modify: `src/market_regime_alpha/data/postgres_pit_authority.py`
- Create: `tests/persistence/postgres/test_pit_concurrency.py`
- Modify: `tests/persistence/postgres/test_pit_authority.py`
- Modify: `tests/persistence/postgres/test_pit_governance.py`

**Interfaces:**
- Changes: `authority_revision` is an audit watermark, not a replay prefix.
- Changes: public `PITAsOfQuery.authority_revision` is removed with the unmerged contract.
- Produces: `replay_evidence` restores exact selected Fact/Qualification/Resolution bindings.

- [ ] **Step 1: Write RED replay and unrelated-progress tests**

```python
def test_old_global_lock_does_not_block_unrelated_fact(postgres_factory):
    with hold_advisory_lock(
        postgres_factory,
        namespace="pit-authority-revision",
        identity="global",
    ):
        future = executor.submit(record_unrelated_fact, postgres_factory)
        assert future.result(timeout=1).fact.subject == "600001.SH"


def test_replay_uses_selected_fact_set_after_correction_and_suspension(postgres_factory):
    authority, original = validated_complete_scope(postgres_factory)
    evidence = authority.validate(pit_request())
    record_later_correction(authority, original)
    suspend_source(authority)
    assert authority.replay_evidence(evidence.evidence_id) == evidence
```

- [ ] **Step 2: Replace prefix evaluation with snapshot selection**

At the first statement of `as_of` use:

```python
connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
```

At the first statement of `validate` use:

```python
connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
```

Select current commit-visible facts without `authority_revision <= cutoff`,
materialize `PITSelectedFactBinding` values, and store them in snapshot/evidence
payloads in the same transaction.

- [ ] **Step 3: Implement explicit replay**

```python
def replay_evidence(self, evidence_id: ArtifactId) -> FormalPITEvidenceArtifact:
    with self._connect() as connection:
        request, snapshot, original = _load_replay_inputs(connection, evidence_id)
        selected = tuple(
            _load_bound_fact(connection, binding)
            for binding in original.selected_fact_bindings
        )
        resolutions = tuple(
            _load_bound_resolution(connection, binding)
            for binding in original.lineage_resolution_references
        )
        replayed = _evaluate_explicit_selection(
            request=request,
            snapshot=snapshot,
            selected=selected,
            lineage_resolutions=resolutions,
            recorded_at=original.recorded_at,
        )
        if replayed != original:
            raise PITAuthorityIntegrityError("Formal PIT replay differs from stored evidence")
        return replayed
```

- [ ] **Step 4: Prove the concurrency matrix**

Run: `uv run pytest -o addopts='' -q tests/persistence/postgres/test_pit_concurrency.py tests/persistence/postgres/test_pit_authority.py tests/persistence/postgres/test_pit_governance.py`

Expected: different symbols/keys/scopes complete concurrently; same-key
correction has one success and one typed CAS conflict; source qualification
races are deterministic; validation remains on one snapshot while ingestion
continues.

- [ ] **Step 5: Commit**

Commit: `git commit -m "fix(pit): replay immutable snapshot selections"`

### Task 6: CLI and governance seam hardening

**Files:**
- Modify: `src/market_regime_alpha/cli/pit_authority.py`
- Modify: `src/market_regime_alpha/data/pit_governance.py`
- Modify: `src/market_regime_alpha/platform/postgres_runtime_governance.py`
- Modify: `tests/cli/test_pit_authority_cli.py`
- Modify: `tests/persistence/postgres/test_pit_governance.py`

**Interfaces:**
- Adds CLI: `resolve-artifact --input` using the strict filesystem resolver.
- Keeps CLI: qualification/fact/validate/inspect/replay, now bound to persisted resolution/policy authority.
- Preserves: Model Governance records evidence only.

- [ ] **Step 1: Add CLI forgery and public-provider attacks**

```python
def test_cli_cannot_qualify_public_provider_with_strings(postgres_factory, tmp_path):
    payload = public_provider_qualification_payload(status="QUALIFIED")
    path = write_input(tmp_path, payload)
    with pytest.raises(PITContractError, match="evidence ceiling"):
        main([*_authority(postgres_factory), "record-source-qualification", "--input", str(path)])
```

- [ ] **Step 2: Route only resolution commands through the strict Reader**

Construct `FilesystemPITArtifactAuthorityResolver` only for
`resolve-artifact`. All later commands use persisted resolution receipts and
the repository default Provider policy. Do not accept policy overrides from
ordinary JSON input.

- [ ] **Step 3: Verify governance remains decoupled**

Run: `uv run pytest -o addopts='' -q tests/cli/test_pit_authority_cli.py tests/persistence/postgres/test_pit_governance.py tests/application/decision_system/test_runtime.py`

Expected: satisfied fixture evidence can be recorded as FORMAL_PIT evidence;
qualification and assignment counts remain zero; forged/rejected/mismatched
evidence is rejected.

- [ ] **Step 4: Commit**

Commit: `git commit -m "fix(pit): harden CLI and governance evidence seam"`

### Task 7: Status, architecture and evidence-ceiling reconciliation

**Files:**
- Modify: `docs/architecture/domains/00-Data-Source-and-PIT.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/superpowers/plans/2026-08-08-wp-pit-01-formal-point-in-time-authority.md`

**Interfaces:**
- Documents the actual authority graph, lock scopes, snapshot semantics, replay truth and real evidence ceiling.

- [ ] **Step 1: Replace revision-prefix claims with explicit-selection claims**

Document:

```text
Provider Evidence
→ typed Source Qualification under bounded policy
→ Canonical Reader and Artifact Resolution receipt
→ PIT Fact Admission with exact Qualification binding
→ repeatable-read As-of selection
→ immutable explicit PIT Snapshot
→ Formal PIT Validation
→ FormalPITEvidenceArtifact
→ Model Governance Evidence only
```

- [ ] **Step 2: Record the compatibility and Reader gaps**

State that no durable PIT v1 instance existed, migration 028 was corrected
before merge, and real Formal PIT remains fail closed because qualified Provider
packages and reliable Readers for all required authority types are absent.

- [ ] **Step 3: Run documentation validation and commit**

Run: `uv run python scripts/check_docs_links.py`

Expected: PASS.

Commit: `git commit -m "docs: reconcile formal PIT authority evidence"`

### Task 8: Final gates, review and merge decision

**Files:**
- Review all changes from `6b952e34f415f2f10fd5e5934f5880ddc87153d0`.

**Interfaces:**
- Produces the final GO/NO-GO report and exact command evidence.

- [ ] **Step 1: Run the frozen dependency gate**

Run: `uv sync --frozen --extra dev --extra postgres`

Expected: exit 0.

- [ ] **Step 2: Run the complete quality gate**

```bash
uv run python scripts/check_docs_links.py
uv run pytest
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

Record collected/passed/failed/skipped/warnings/duration and the PostgreSQL 16
version. Do not report remote CI PASS unless it was observed.

- [ ] **Step 3: Inspect all staged and unstaged changes**

Run:

```bash
git status --short
git diff --check
git diff --stat 6b952e34f415f2f10fd5e5934f5880ddc87153d0
git diff 6b952e34f415f2f10fd5e5934f5880ddc87153d0 -- src tests docs
```

Confirm `.idea/modules.xml` remains unstaged and no credentials, secrets,
personal paths or unrelated files enter the checkpoint.

- [ ] **Step 4: Run the required code review and fix actionable findings**

Review standards and spec conformance against the convergence design, rerun
focused tests after fixes, then rerun affected full gates.

- [ ] **Step 5: Commit the final bounded correction**

Commit: `git commit -m "fix(pit): close formal authority merge blockers"`

- [ ] **Step 6: Report merge decision**

Return `GO` only if correctness, canonical authority, concurrency, explicit
replay and all local gates pass. Otherwise return `NO-GO` with exact blockers.
