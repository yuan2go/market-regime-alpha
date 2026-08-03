# H6 Composite Operational Evidence Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Task-level execution plan for approved H6 implementation
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-04-h6-composite-operational-evidence-design.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md
> **Code Evidence:** Plan starts from `feat/h6-composite-operational-evidence@e2cb9add258056815d15462bc83dfc64f43ddb8e`; hardened implementation checkpoint `654e025b97c5d9553d7614b4b5be0898272aacbc`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the operational bridge's false historical-archive label and implicit dual-source lineage with a verified, content-addressed H6 composite authority and V2 research input path.

**Architecture:** Build a terminal manifest from two existing verified package Readers and an explicit policy, publish it as an immutable three-file package, then atomically index it in append-only SQLite. Feed only verified manifests into an independent ResearchInputBundle V2 while preserving the Daily SourceManifest as the primary Envelope authority and preserving V1 Readers.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum/Protocol, canonical JSON/SHA-256, existing Artifact Readers, SQLite `BEGIN IMMEDIATE`, argparse, pytest, Ruff, mypy and `python -m build`.

## Global constraints

- Start from `origin/main@e2cb9add258056815d15462bc83dfc64f43ddb8e` on `feat/h6-composite-operational-evidence`.
- Preserve and never stage `.idea/modules.xml`.
- Add migration 009; do not alter migrations 007 or 008.
- Preserve V1 canonical and hash semantics.
- Preserve `ArtifactEnvelope.source_manifest_id/hash` as the Daily primary SourceManifest.
- No H4.5, H7, H8, H9, Broker, ManualTrade/Fill, Entry or model-calibration implementation.
- Every behavior slice runs red, minimal green and focused regression before the next slice.
- Authority always remains exploratory, non-formal-PIT, non-formal-OOS and non-trading.

---

### Task 1: Policy, roles, references and terminal manifest

**Files:**
- Create: `src/market_regime_alpha/application/operational_research/composite_manifest.py`
- Create: `tests/application/operational_research/test_composite_manifest_domain.py`
- Modify: `src/market_regime_alpha/application/operational_research/__init__.py`

**Interfaces:**
- Produces `CompositeOperationalCompositionStatus`,
  `CompositeOperationalComponentRole`, `CompositeOperationalFieldGroup`,
  `CompositeOperationalFieldAuthorityRequirement`,
  `CompositeOperationalComponentReference`,
  `CompositeOperationalFieldAuthorityReference`,
  `CompositeOperationalCompositionPolicy` and
  `CompositeOperationalInputManifest`.
- All public constructors are strict frozen types; configuration and manifest
  provide `to_canonical_dict()` and `from_canonical_dict()`.

- [ ] Write failing public-interface tests for canonical round trips,
  content-derived IDs/hashes, sorted uniqueness, unknown/duplicate roles,
  same Artifact ID with another hash, policy binding and authority inflation.
- [ ] Run `python -m pytest -q tests/application/operational_research/test_composite_manifest_domain.py`; expect import failures.
- [ ] Implement only the tested immutable domain contracts and stable exports.
- [ ] Re-run the test and `python -m ruff check` on the two affected files; expect PASS.

### Task 2: Deterministic builder and authority classification

**Files:**
- Modify: `src/market_regime_alpha/application/operational_research/composite_manifest.py`
- Create: `tests/application/operational_research/composite_fixtures.py`
- Create: `tests/application/operational_research/test_composite_manifest_builder.py`

**Interfaces:**
- Consumes existing `VerifiedPhaseDDailyDecisionArtifact`,
  `VerifiedSupplementalResearchEvidence`, policy and aware `created_at`.
- Produces `CompositeOperationalManifestBuilder.build(...) -> CompositeOperationalInputManifest`.

- [ ] Write one valid-builder test proving all component and field authority
  references and `VERIFIED` status; run it and observe the missing Builder.
- [ ] Implement canonical input restoration, source lookup and the valid
  population/theme/capital/ETF composition path; rerun to PASS.
- [ ] Add failing parameterized tests for unpublished/missing Daily snapshots,
  missing supplemental evidence, required role/field absence and empty
  authorities; implement `DATA_INSUFFICIENT` classification.
- [ ] Add failing parameterized tests for DecisionTime, eligibility, SourceManifest,
  Artifact hash, prediction population, membership, symbol, theme/capital and
  ETF conflicts; implement `CONFLICTED` with conflict-over-missing priority.
- [ ] Run the complete builder test and existing bridge test; expect PASS.

### Task 3: Immutable composite package

**Files:**
- Create: `src/market_regime_alpha/application/operational_research/composite_artifact.py`
- Create: `tests/application/operational_research/test_composite_artifact.py`

**Interfaces:**
- Produces `VerifiedCompositeOperationalManifest`,
  `publish_composite_operational_manifest()`,
  `load_verified_composite_operational_manifest()` and
  `cleanup_orphan_composite_staging()`.
- Package file set is exactly `artifact.json`, `manifest.json`,
  `SHA256SUMS.json`.

- [ ] Write a failing publish/load/idempotent-repeat test and implement staging,
  checksum, atomic rename and semantic reconstruction.
- [ ] Add failing exact-file, checksum, artifact JSON, package manifest,
  component, policy and authority tamper tests; make the Reader fail closed.
- [ ] Add a conflicting-existing-path and injected-staging-failure test;
  implement safe H6-only staging cleanup.
- [ ] Run package tests and Ruff; expect PASS.

### Task 4: ResearchInputBundle V2 and common view

**Files:**
- Modify: `src/market_regime_alpha/research/platform_v2/inputs.py`
- Modify: `src/market_regime_alpha/research/platform_v2/pipeline.py`
- Modify: `src/market_regime_alpha/research/platform_v2/artifact.py`
- Modify: `src/market_regime_alpha/research/platform_v2/reader.py`
- Modify: `src/market_regime_alpha/application/research_layer/runner.py`
- Modify: Market/Theme/Capital/Candidate model type annotations to consume `ResearchInputView`.
- Create: `tests/research/platform_v2/test_composite_input_v2.py`

**Interfaces:**
- Adds `ResearchEvidenceKind.OPERATIONAL_EXPLORATORY_ARCHIVE`,
  `ResearchInputView`, `ResearchInputBundleV2` and schema-dispatch
  `research_input_bundle_from_canonical_dict()`.
- V2 operational construction is exposed through
  `adapt_verified_composite_operational_inputs(composite, daily, supplemental)`;
  it reloads verified inputs and replays the Builder before constructing V2
  directly, without creating an intermediate V1 bundle.

- [ ] Prove existing V1 canonical fixture and Reader hashes are unchanged.
- [ ] Write failing V2 round-trip and status-gate tests; implement V2 with
  exact composite/primary SourceManifest bindings.
- [ ] Change only shared type seams and Reader dispatch; keep one model
  implementation and make V1/V2 pipeline tests pass.
- [ ] Prove Research Layer input lineage contains the V2 bundle and Composite
  Manifest while every component Envelope retains the Daily SourceManifest.

### Task 5: Migration 009 and SQLite publication/replay index

**Files:**
- Create: `src/market_regime_alpha/application/operational_research/composite_repository.py`
- Create: `src/market_regime_alpha/application/operational_research/sqlite_composite_repository.py`
- Create: `src/market_regime_alpha/application/operational_research/migrations/009_composite_operational_evidence_up.sql`
- Create: `src/market_regime_alpha/application/operational_research/migrations/009_composite_operational_evidence_down.sql`
- Modify: `pyproject.toml`
- Create: `tests/application/operational_research/test_sqlite_composite_repository.py`

**Interfaces:**
- Protocol supports command resolution, atomic save and load by manifest ID.
- SQLite adapter stores package/source paths and replay metadata but reloads
  original packages and re-runs the Builder on every authority read.

- [ ] Write failing repeat-safe up/down migration and initialization tests;
  implement tables, FKs, checks and append-only triggers and package the SQL.
- [ ] Write failing save/read/restart and same-command replay tests; implement
  `BEGIN IMMEDIATE` save and canonical reconstruction.
- [ ] Add semantic idempotency conflict, manifest identity conflict, component,
  field, command and package projection tamper tests; validate every projection.
- [ ] Add builder replay mismatch, transaction failure rollback, weak schema and
  spoofed-trigger tests; fail initialization or reads closed.
- [ ] Run repository tests and mypy over operational research; expect PASS.

### Task 6: File-first Application Service and crash recovery

**Files:**
- Create: `src/market_regime_alpha/application/operational_research/composite_service.py`
- Create: `tests/application/operational_research/test_composite_service.py`

**Interfaces:**
- Produces `CompositeOperationalEvidenceApplicationService.build_and_publish(...)`.
- The command binds source package checksum hashes, policy, created time,
  builder revision and result manifest.

- [ ] Write a failing happy-path and same-key/same-command replay test; implement
  load → build → publish → index orchestration.
- [ ] Add same-key/different-command rejection and transaction rollback tests.
- [ ] Inject failure before rename and after publish/before DB commit; prove
  staging cleanup and idempotent index repair.
- [ ] Prove DB row with missing/mismatched package fails closed and valid
  package without a DB row is repairable.

### Task 7: Composite CLI and operational research V2 route

**Files:**
- Create: `scripts/build_composite_operational_manifest.py`
- Modify: `scripts/run_operational_research.py`
- Modify: `src/market_regime_alpha/application/operational_research/bridge.py`
- Create: `tests/scripts/test_build_composite_operational_manifest.py`
- Modify: `tests/application/operational_research/test_bridge.py`

**Interfaces:**
- Build CLI accepts only source package paths, policy, DB, package root,
  created time and idempotency key.
- Operational CLI run accepts `--composite-package`; direct Daily +
  Supplemental arguments are not a new production path.

- [ ] Write a failing build CLI test and implement terminal JSON output with
  status/reasons/authority limits and no research/trade side effects.
- [ ] Rename/document the V1 direct adapter as legacy compatibility, then write
  a failing CLI test proving new run requires a verified Composite package.
- [ ] Implement V2 conversion and Platform runner invocation; add rejection
  tests for DATA_INSUFFICIENT, CONFLICTED and ASSEMBLING.
- [ ] Prove CLI output includes Composite identity and unchanged non-authority.

### Task 8: H5 integration and compatibility regression

**Files:**
- Create: `tests/application/operational_research/test_h5_composite_integration.py`
- Modify only confirmed compatibility seams in H5 if executable evidence requires it.

**Interfaces:**
- End-to-end seam is Daily + Supplemental → H6 package → V2 Research Artifact
  → Signal → PathForecast → H5 V2 Observation.

- [ ] Build the end-to-end fixture and assert exact H6 lineage, one Daily
  primary SourceManifest and H5 `NOT_H6_AUTHORITY` private replay boundary.
- [ ] Assert no PIT/OOS/Trading authority inflation.
- [ ] Run H4 focused tests, H5 focused tests, V1 Reader tests, historical
  Research Layer Reader and synthetic Platform fixture tests.

### Task 9: Documentation and delivery evidence

**Files:**
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md`
- Create: `docs/audit/H6-Composite-Operational-Evidence-Delivery.md`

- [ ] Record exact implemented H6 boundaries and the baseline/final commits.
- [ ] Register the H5 Decision authority, assessment freshness, H5 module size,
  H4.5 and H7 gaps without implementing them.
- [ ] Preserve all formal-PIT/OOS, Shadow, production, broker and trading
  non-claims and run documentation-link validation.

### Task 10: Final review, gates and publication

- [ ] Run focused operational, research, platform, position and application tests.
- [ ] Run `python -m pytest -q`, `python -m ruff check .`, `python -m mypy`,
  `python -m build`, `python scripts/check_docs_links.py` and
  `git diff --check`; record exact results.
- [ ] Inspect staged/unstaged diff, exclude `.idea/modules.xml`, generated
  distributions, secrets and unrelated files.
- [ ] Perform Standards and specification review and fix actionable findings.
- [ ] Create bounded implementation/documentation commits, push
  `feat/h6-composite-operational-evidence` and open Draft PR
  `feat: add composite operational evidence authority`.
