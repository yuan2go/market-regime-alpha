# Free Runtime V2 Canonical Convergence — Implementation Plan

> **Status:** ROADMAP
> **Authority:** Execution plan for Free Runtime V2 canonical convergence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-09-free-runtime-v2-canonical-convergence-design.md, ../../status/Current-State.md
> **Code Evidence:** Baseline `9d4b872eae9fb3bb56544f8dbb4ef14f6e6806d2`; `src/market_regime_alpha`; `tests`

## Phase 1 — Summary authority contract

- Add failing contract tests for structured Candidate/Signal/Forecast outcome.
- Add explicit evidence/stage/summary timestamps without rewriting historical
  schema readers.
- Derive Provider contracts from consumed immutable sources.
- Verify Selection receipts in PostgreSQL during Summary save.
- Focused tests: identity, purpose/slot/lineage/hash mismatch, corrections,
  evidence ceiling.

## Phase 2 — Stateful owner composition

- Add a production State stage composition over existing state evaluators and
  `PostgresStateSystemRepository`.
- Persist Market, ETF, Theme, Capital and Dynamic Pool with the active Tick
  claim; bind Candidate to the Pool and make excluded pool members ineligible.
- Replace synthetic FreeData children with `ExistingResearchServiceComposition`
  delegates and real owner receipts.
- Preserve deterministic ETF/Pool policy configuration as immutable lineage.
- Focused tests: positive states/pool/candidate, missing evidence, no-material
  reuse, stale fence and receipt reconstruction.

## Phase 3 — pre-Decision minute staging

- Split Controlled execution into idempotent pre-decision staging and final
  Signal/Forecast finalization.
- Persist a content-addressed staging bundle and PostgreSQL index.
- Enforce bounded Candidate scope, provider deadline and strict
  `response_received_at <= DecisionTime`.
- Make restart load accepted sources/coverage without a new Provider call.
- Restrict live CLI time to trusted clock; retain explicit simulated/replay.
- Focused tests: late response, timeout, restart, crash/resume, lineage scope.

## Phase 4 — Canonical E2E and documentation

- Seed real PostgreSQL Registry, qualifications and mode-specific Champion
  assignments for the six governed model slots.
- Prove RESEARCH positive path and SHADOW equivalence without trading mutation.
- Prove PRODUCTION free-data fail-closed and missing ETF/Theme/Capital Summary.
- Prove replay identities, provider no-fallback and Evidence Ceiling.
- Update Current State, Capability Matrix and Gap Register with observed facts
  only; keep live-provider rehearsal explicitly unproven when not observed.

## Phase 5 — Quality gate and checkpoint

- Run `uv sync --frozen --extra dev --extra postgres`.
- Run docs links, full pytest, Ruff, mypy, build and `git diff --check` against
  PostgreSQL 16.
- Inspect all changes, run the repository code-review workflow, fix findings and
  commit one dependency-coherent implementation checkpoint.

## Stop conditions

Stop only for an external-state blocker that cannot be replaced by safe,
in-scope engineering evidence: unavailable PostgreSQL 16, unrecoverable baseline
corruption, or a required authority decision absent from code/user scope. A live
Provider market-window miss is reported separately and does not invalidate the
engineering result.
