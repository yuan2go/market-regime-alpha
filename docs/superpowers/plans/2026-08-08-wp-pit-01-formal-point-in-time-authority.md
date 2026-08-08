# WP-PIT-01 Formal Point-in-Time Authority Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Executable implementation plan for WP-PIT-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-08
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-08-wp-pit-01-formal-point-in-time-authority-design.md, ../../status/Current-State.md
> **Code Evidence:** Completion is established only by final-commit PostgreSQL, replay, leakage and repository gates.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PostgreSQL-only bitemporal PIT Authority that emits replayable Formal PIT evidence and feeds the existing Model Governance evidence seam.

**Architecture:** Add immutable PIT fact/revision and validation contracts in the Data bounded context, persist them through migration 028 and one PostgreSQL repository, then bridge passed evidence into `ModelQualificationEvidence(FORMAL_PIT)`. Existing Source, Dataset, Universe, Eligibility, Feature and Runtime authorities remain owners of their current responsibilities.

**Tech Stack:** Python 3.12, frozen dataclasses/enums, psycopg 3, PostgreSQL 16, pytest, Ruff, mypy, uv/build.

## Global Constraints

- PostgreSQL is the only PIT state and replay authority.
- Public/free data remains EXPLORATORY and cannot be promoted by this work package.
- No automatic qualification, Champion assignment, Production authorization or trading action.
- Every mutation is append-only, idempotent and actor/reason audited.
- Every replay is pinned to the original PIT authority revision.

---

### Task 1: PIT contracts and temporal policy

**Files:**
- Create: `src/market_regime_alpha/data/pit_authority.py`
- Test: `tests/data/test_pit_authority.py`

**Interfaces:**
- Produces: `PITSourceQualification`, `PITFactRevision`, `PITAsOfQuery`, `PITAsOfSnapshot`, `PITValidationLineage`, `FormalPITValidationRequest`, `FormalPITEvidenceArtifact`.

- [x] Write failing public-contract tests for canonical identities, time ordering, required coverage and reason codes.
- [x] Implement immutable contracts and pure validation projection.
- [x] Run `uv run pytest -o addopts='' -q tests/data/test_pit_authority.py`.

### Task 2: PostgreSQL fact, revision and as-of Authority

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/028_formal_pit_authority.sql`
- Create: `src/market_regime_alpha/data/postgres_pit_authority.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Test: `tests/persistence/postgres/test_pit_authority.py`
- Modify: `tests/persistence/postgres/test_migrator.py`

**Interfaces:**
- Produces: `PostgresPITAuthority.record_source_qualification`, `record_fact`, `as_of`, `validate`, `get_evidence`, `replay_evidence`.

- [x] Write RED migration, idempotency, CAS, concurrency and append-only tests.
- [x] Implement migration 028 with append-only source admission, indexed foreign keys and composite as-of indexes.
- [x] Implement deterministic record/as-of/validation/replay transactions.
- [x] Run the real PostgreSQL PIT suite.

### Task 3: Leakage closure

**Files:**
- Test: `tests/persistence/postgres/test_pit_leakage.py`
- Modify: `src/market_regime_alpha/data/postgres_pit_authority.py`

**Interfaces:**
- Consumes: `PostgresPITAuthority.validate` and `replay_evidence`.
- Produces: stable rejection reason codes for temporal and lineage attacks.

- [x] Add RED attacks for future facts, late availability/recording, revision overwrite, future Universe membership, future Feature availability, current-state substitution and back-adjustment.
- [x] Implement the minimum fail-closed checks required by each attack.
- [x] Prove later revisions do not change historical replay.

### Task 4: Existing Model Governance bridge

**Files:**
- Create: `src/market_regime_alpha/data/pit_governance.py`
- Modify: `src/market_regime_alpha/platform/postgres_runtime_governance.py`
- Test: `tests/persistence/postgres/test_pit_governance.py`

**Interfaces:**
- Produces: `record_formal_pit_governance_evidence(...) -> ModelQualificationEvidence`.

- [x] Write RED tests proving forged, rejected and lineage-mismatched PIT references cannot enter Model Governance.
- [x] Implement the bridge and PostgreSQL reference guard.
- [x] Prove a passed fixture records FORMAL_PIT evidence without qualification or Champion creation.

### Task 5: Inspection CLI and documentation

**Files:**
- Create: `src/market_regime_alpha/cli/pit_authority.py`
- Modify: `pyproject.toml`
- Modify: `docs/README.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Test: `tests/cli/test_pit_authority_cli.py`

**Interfaces:**
- Produces JSON commands for fact recording, as-of inspection, validation, evidence inspection and replay.

- [x] Implement strict JSON CLI commands and credential-redacted output.
- [x] Document actual authority, leakage closures and remaining data qualification gap.
- [x] Run CLI and documentation tests.

### Task 6: Final qualification and publication

- [x] Run the focused PostgreSQL/replay/leakage matrix.
- [x] Run full pytest with `MARKET_REGIME_ALPHA_TEST_DATABASE_URL`.
- [x] Run docs links, Ruff, mypy, build and `git diff --check`.
- [x] Inspect wheel/sdist for migration 028 and PIT modules.
- [x] Review the diff against this design and repository standards.
- [x] Commit, push `agent/formal-pit-authority`, open a Draft PR and report GitHub Actions billing blockage separately from local gates.
