# Xuntou P0 Native Adapter Implementation Plan

> **For agentic workers:** Execute inline against the current branch. Do not dispatch implementation work; the official-document research note may be prepared independently. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the minimum truthful Xuntou P0 field semantics and provide a normalized native/export adapter that builds the existing R5 rehearsal market artifact without inventing PIT, availability, finality, or buyability facts.

**Architecture:** Xuntou-specific parsing, validation, state materialization, and error translation remain in `market_regime_alpha.research.xuntou_provider_adapter`. The module consumes a content-identified normalized export, reuses the existing Calendar, Universe, Eligibility, and Provider Rehearsal contracts, and always emits `REHEARSAL` with `pit_correct_for_scope=False`.

**Tech Stack:** Python 3.12 standard library, frozen slotted dataclasses, existing Market Regime Alpha contracts, Markdown specifications, official ThinkTrader/XtQuant documentation.

## Global Constraints

- Do not modify the Constitution, B0/B1 semantics, Entry, Exit, Portfolio, Execution, or Legacy code.
- Do not add an import-time or mandatory `xtquant` dependency.
- Preserve unknown evidence as `None`, `UNKNOWN`, an explicit limitation, or a semantic adapter error.
- Never infer historical PIT state from a current value, retrieval time from market availability, or price limits from a simple percentage formula.
- All produced market artifacts remain `DataEligibility.REHEARSAL`.
- Do not create or modify tests, and do not run pytest, ruff, mypy, tox, nox, coverage, or CI.

---

### Task 1: Reconcile authority and existing implementation

**Files:**
- Read: `AGENTS.md`
- Read: `docs/constitution/*.md`
- Read: current R5 authority documents
- Read: current Candidate and provider/canonical contracts

**Produces:** A bounded architecture decision: provider-specific export translation in Research composition, existing canonical contract reuse, and no XtQuant runtime dependency.

- [x] Re-scan the actual HEAD, branch, worktree, recent commits, and current exports.
- [x] Confirm WP-0 B1 integration remains closed and out of scope.
- [x] Reconcile provider work with Data Constitution PIT, availability, finality, provenance, and authority rules.

### Task 2: Establish official P0 evidence

**Files:**
- Create: `docs/research/R5-Xuntou-P0-Official-Documentation-Evidence.md`
- Review: `docs/specs/Xuntou-P0-Native-Field-Mapping.md`

**Produces:** Source-linked official evidence for API and field names plus explicit unverified semantics.

- [x] Record the official XtData runtime relationship, calendar, instrument, sector, K-line, ST, and historical price-limit capabilities.
- [x] Separate confirmed native field meaning from unproven historical PIT, availability, finality, revision, and minute-label semantics.
- [x] Reconcile every formal mapping statement with a first-party source or downgrade it to `UNVERIFIED`/`UNAVAILABLE_IN_P0`.

### Task 3: Review and close the mapping contract

**Files:**
- Modify: `docs/specs/Xuntou-P0-Native-Field-Mapping.md`

**Produces:** `xuntou-p0-native-field-mapping-v2` covering all fifteen P0 evidence groups.

- [x] Verify provider/product/API distinctions, mapping classifications, and all result-affecting convention identities.
- [x] Verify raw price adjustment, 14:55 reference-price selection, liquidity, Universe, buyability, and next-session semantics.
- [x] Align the normalized export schema description exactly with the adapter implementation.

### Task 4: Review and close the minimum adapter

**Files:**
- Modify if required: `src/market_regime_alpha/research/xuntou_provider_adapter.py`
- Review: `src/market_regime_alpha/research/provider_rehearsal_market_artifact.py`
- Review: `src/market_regime_alpha/research/__init__.py`

**Produces:** Public file/mapping entry points that construct the existing rehearsal artifact with deterministic provenance and identity.

- [x] Verify content hashing, versioned conventions, symbol/type filtering, Calendar/Universe construction, bar parsing, 14:55 selection, eligibility materialization, and next-session resolution.
- [x] Verify no missing value becomes false, zero, `BUYABLE`, or a formula-derived price limit.
- [x] Verify no XtQuant import exists and no authority can exceed `REHEARSAL`.
- [x] Export only intended constants, classifications, errors, and adapter entry points.

### Task 5: Update current status and review drift

**Files:**
- Modify: `docs/research/R5-Current-Status.md`
- Modify: `docs/research/R5-Xuntou-P0-Adapter-Status.md`

**Produces:** Accurate current state and next-step boundary.

- [x] Record specification, export adapter, runtime extraction, and real-run status without claiming execution evidence.
- [x] Read the final diff for current-vs-historical confusion, time conflation, silent defaults, canonical-contract expansion, model coupling, and evidence inflation.
- [x] Run only non-test repository checks: `git diff --check`, `git status --short --branch`, and commit/history inspection.
- [x] Create intentional local commits and leave the worktree clean.
