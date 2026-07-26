# Historical Dated Work Package

> **Status:** HISTORICAL  
> **Authority:** Preserved dated design/plan; not current roadmap authority  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../../../roadmap/work-packages/README.md  
> **Code Evidence:** Historical references may no longer match main

# Daily Quant Decision Artifacts V1 Implementation Plan

> **For agentic workers:** Execute inline under the repository AGENTS.md contract. Subagent execution is intentionally not used for this bounded work package.

**Goal:** Implement an immutable, content-addressed daily snapshot with separate Candidate Recommendation and Entry Assessment evidence, plus a semantic Reader.

**Architecture:** Add a new `market_regime_alpha.daily_research` bounded context. Domain contracts own validation and semantic payloads; the Publisher owns deterministic staged filesystem publication; the Reader owns exact-file/checksum verification and semantic reconstruction. Existing Candidate, Entry Target, and research Artifact code remains unchanged.

**Tech Stack:** Python 3.12 dataclasses/enums, pathlib, hashlib/json, pytest, Ruff, mypy.

## Global Constraints

- Preserve Candidate/Entry separation.
- Permit only exploratory, auxiliary, and test-only data Authority.
- Reject evidence unavailable after Decision Time.
- Never overwrite an Artifact.
- Do not implement a strategy model, broker action, manual trade, lifecycle, Exit, review, Dashboard, or scheduler.
- Add every new production module to ordinary mypy coverage.

## Task 1: Freeze WP-DQS-0 evidence

- [x] Audit Constitution, current research programs, code, tests, scripts, and data layout.
- [x] Write `docs/research/Daily-Quant-Selection-Current-State-Audit.md`.
- [x] Write `docs/specs/Daily-Quant-Decision-Artifact-Specification-V1.md`.
- [x] Run Markdown/diff checks and commit as `docs: audit daily quant selection research gaps`.

## Task 2: Add failing contract tests

**Files:**

- Create `tests/daily_research/test_contracts.py`.
- Create `tests/daily_research/test_artifacts.py`.
- Create `tests/daily_research/test_reader.py`.

**Cases:** frozen records, exact enums/fields, future evidence rejection, deterministic IDs,
Candidate/Entry separation, exact file set, non-overwrite, test-only Authority, tampering with rewritten
checksums, bad ranks/references, and report reconstruction.

**Command:**

```bash
.venv/bin/python -m pytest -q tests/daily_research
```

Expected before implementation: collection fails because `market_regime_alpha.daily_research` is absent.

## Task 3: Implement immutable domain contracts

**Files:**

- Create `src/market_regime_alpha/daily_research/__init__.py`.
- Create bounded domain modules behind `src/market_regime_alpha/daily_research/contracts.py`.

**Steps:**

- [x] Add Authority, instrument, Entry-state, data-quality, source-evidence, score-component, snapshot,
  recommendation, and assessment types.
- [x] Add canonical semantic payload and SHA-256 identity helpers.
- [x] Validate timezone, Decision Date, availability, finite values, structured reasons, price states,
  sorting, and exact reference semantics.
- [x] Run contract tests and mypy for the new modules.

## Task 4: Implement Publisher

**Files:**

- Create `src/market_regime_alpha/daily_research/artifacts.py`.

**Steps:**

- [x] Validate the aggregate and score-reconstructed per-instrument ranks.
- [x] Write the exact six-file set to an owned staging path.
- [x] Hash all files, bind exact manifest fields and implementation hashes, then atomically rename.
- [x] Render a deterministic report solely from structured records.
- [x] Run Publisher tests.

## Task 5: Implement semantic Reader

**Files:**

- Create `src/market_regime_alpha/daily_research/reader.py`.

**Steps:**

- [x] Verify exact file set, checksums, manifest fields, Schema, Authority, and implementation hashes.
- [x] Parse exact field sets into immutable objects and recompute every identity.
- [x] Recheck temporal, rank, reference, aggregate, and report semantics.
- [x] Return a typed verified Artifact with a read-only manifest.
- [x] Run all daily-research tests.

## Task 6: Integrate type and status authority

**Files:**

- Modify `pyproject.toml`.
- Modify `docs/research/R5-Current-Status.md`.

**Steps:**

- [x] Add all daily-research production modules to normal mypy coverage.
- [x] Record the Daily Quant Selection and Manual Trading program as the current engineering mainline.
- [x] Retain Xuntou PIT status as blocked and state that auxiliary engineering does not gain formal Authority.

## Task 7: Verify and review

**Commands:**

```bash
.venv/bin/python -m pytest -q tests/daily_research
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
git diff --check
```

- [x] Run independent standards and specification reviews against the fixed branch base.
- [x] Commit WP-DQS-1 as an intentional feature commit, followed by a bounded review-hardening commit.
- [x] Report exact commands, results, remaining data blockers, and Git status.
