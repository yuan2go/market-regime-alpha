# Pre-Live Engineering Hardening — Implementation Plan

> **Status:** ROADMAP
> **Authority:** Execution plan for the current user program
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Related Documents:** ../specs/2026-08-09-pre-live-engineering-hardening-design.md, ../../status/Current-State.md
> **Code Evidence:** Baseline `94c1f99f56deeb5019a9a014f9b752328020f8fd`; checkpoints `04d8ee6b6734e00b8361956e6b94914d1f5511bd`, `385213601fbfed2e8262cb9ae7e27b6a05b9fba4`, `f68893cb79985564400991298ceb06eeb0b77694`, `d0f630f5a8be55dece3febaecd5b0625692c8e5b`, `ac350db8665efb456adbecd3d022a47e5e7a7bc1`, `0134fbe3c00e242adf3fe3634493f9ab08a5dadf`, `2a40c59a145a7ab08746520b5b300f2f86d944c6`; `src/market_regime_alpha`; `tests`

## Phase protocol

Every checkpoint follows:

```text
audit → failing contract/PostgreSQL tests → minimal implementation
→ adversarial replay/recovery tests → documentation → focused gates → commit
```

No checkpoint promotes evidence beyond engineering readiness.

## Checkpoint 1 — PREFLIGHT, OBSERVABILITY, QUERY

Add typed Preflight `READY/DEGRADED/BLOCKED` checks for PostgreSQL, migration
head, trusted Shanghai clock/skew, calendar/configuration/provider/policy,
Governance assignments, Artifact root/capacity/permissions, recoverable Tick and
Lease state. Add one read-only query service that projects the Canonical DAG and
trace/metrics from current owners. Extend `continuous-research` with machine-
readable `preflight`, `inspect-*`, `trace`, and `metrics` operations.

Acceptance: complete/partial/blocked/recovered runs are explainable; observations
contain trace, Stage/provider timing, retries, coverage, deadline margin and
fence/Lease facts without writes or decision recomputation.

## Checkpoint 2 — SHADOW ENGINEERING FOUNDATION

Migration 034 and a PostgreSQL Shadow repository add Session, Decision and event
state with CAS. Freeze only an existing immutable Research Summary V3 after
validating Run/Tick/Summary lineage. Repeated freeze is idempotent; conflicting
lineage and stale versions fail. Frozen decision columns are database-immutable.

Acceptance: `SCHEDULED → RUNNING → FROZEN → OUTCOME_PENDING` plus terminal
`SETTLED/FAILED/INVALIDATED` mechanisms, historical events and replay; zero
Order/Fill/Broker/Position writes.

## Checkpoint 3 — OUTCOME ENGINEERING FOUNDATION

Migration 035 adapts the existing factual Outcome/source-archive boundary to a
frozen Shadow Decision and Summary lineage. Add T+1 09:30/10:00/10:30, open and
checkpoint returns, MFE/MAE, first-passage +1/+2/-1, suspension/limits/missing/
calendar/corporate-action states. Settlement is append-only/idempotent and sets
only the Shadow outcome status through CAS.

Acceptance: future/forged/stale lineage fails; identical recorded bytes replay to
the same identity; conflicting settlement fails; fixtures are labelled
engineering-only.

## Checkpoint 4 — FROZEN EVALUATION DATASET

Migration 036 indexes immutable content-addressed manifests built only from
frozen decisions and settled outcomes. Rows bind the existing Summary State,
Pool, Candidate, Signal, Forecast, model/configuration and source references.
Inclusion, exclusion and missing sample reasons are explicit.

Acceptance: deterministic build/replay, missing-sample accounting, immutable
historical Reader, no arbitrary production SQL or outcome back-write.

## Checkpoint 5 — ETF/THEME REFERENCE FOUNDATION

Migration 037 and reference contracts store ETF identity/tracking/listing/
liquidity/primary-alternative relations and Theme taxonomy/hierarchy/membership
with effective/available/source time. Publish the existing `510300 +
FREE_A_SHARE_OPERATIONAL_UNIVERSE` policy only as an explicit exploratory V1
proxy; publish no unsupported memberships.

Acceptance: temporal overlap, future availability, invalid hierarchy and source
conflicts fail; historical Reader and replay preserve identity; no Formal PIT.

## Checkpoint 6 — DISASTER RECOVERY AND VERIFICATION EVIDENCE

Add a bounded backup/restore verifier using PostgreSQL custom-format archives and
an immutable Artifact hash inventory. Restore into an explicit isolated database,
verify migrations/repositories, replay selected Run/Summary/PIT identities and
compare hashes. Add a SHA/environment/tool-result Engineering Verification
Artifact generator that represents unavailable CI as `CI_EXTERNAL_BLOCKED`.

Acceptance: archive creation alone does not pass; isolated restore plus replay and
hash comparison are required. A dirty tree or missing command result cannot emit
a successful final-SHA verification record.

## Repository gates

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL=... uv run pytest
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

Report each command as PASS, FAIL, NOT_RUN or BLOCKED with actual counts,
PostgreSQL version, migration head and elapsed time. The only allowable aggregate
claim from this plan is `ENGINEERING_READY`; Live and prospective gates remain
external observations.
