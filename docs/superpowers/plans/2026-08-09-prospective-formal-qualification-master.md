# Prospective Research to Formal Qualification — Implementation Plan

> **Status:** ROADMAP
> **Authority:** Execution plan for the current master program
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-09-prospective-formal-qualification-master-design.md, ../../status/Current-State.md
> **Code Evidence:** Baseline `ecbe40ab7a39ba87e460be0c268ffaab2baf4dd0`; `src/market_regime_alpha`; `tests`

## Phase protocol

Every phase follows:

```text
audit → freeze contracts/invariants → failing tests → minimal implementation
→ PostgreSQL/replay/adversarial tests → docs/status → full gates → commit
```

No phase changes the evidence status of a later phase.

## WP-EVIDENCE-OPS-01 — dependency-ready now

### Objective and contracts

- Add one explicit supplemental acquisition stage to the existing Daily
  acquisition journal and source-stage Artifact contract.
- Add a versioned, content-addressed free operational ETF/Theme policy.
- Add a BaoStock ETF-history client adapter with no fallback.
- Materialize ETF/Theme/Capital supplemental evidence from verified ETF bytes,
  canonical stock Dataset and Operational Universe.
- Feed the resulting existing supplemental bundle into the existing State owner;
  do not introduce a parallel pipeline.

### TDD acceptance

- complete recorded Provider evidence produces non-empty ETF/Theme/Capital,
  memberships/mappings, coverage and immutable replay identity;
- missing/partial ETF history produces typed missingness and no invented value;
- late/future source is rejected;
- Provider failure has no fallback;
- restart loads the acquisition receipt without repeating the client;
- actual lineage contains BaoStock product, policy source and exact attempts;
- PostgreSQL Canonical Runtime reaches the real State/Dynamic Pool/Candidate
  chain without an externally built supplemental bundle;
- evidence remains exploratory and all trading authorities remain false.

### Rollback / repair / stop

The stage enum and policy schema are additive; disable the configured client to
retain the old missing-evidence result. A real BaoStock outage blocks a live
producer rehearsal but not recorded-provider engineering proof. Commit after
focused and full quality gates.

## WP-LIVE-01 — after producer engineering gate

- Add/verify trusted-clock exact-window command, lease/heartbeat/provider/stage
  latency report, timeout/deadline and recovery runbook.
- Rehearse only with wall-clock `LIVE`; preserve every immutable receipt.
- Exit only after multiple real trading-day runs. A Sunday/single run is not an
  exit and blocks downstream prospective claims.

## WP-SHADOW-01

- Add one Summary-scoped prospective Shadow Session/Decision authority after
  LIVE exit, with missed-window/outage/model-rejection statuses and replay.
- Prove consecutive pre-outcome freezes and zero trade/position mutation.

## WP-OUTCOME-01

- Adapt the existing factual outcome/source archive to Summary/Candidate/Signal/
  Forecast/model-selection lineage.
- Add 09:30, 10:00, 10:30, MFE, MAE, returns, suspension/limit/corporate-action
  reason codes and a single PostgreSQL settlement index.

## WP-ATTR-01 and WP-EVAL-01

- Produce immutable grouped baseline/ablation layer attribution.
- Produce explicitly exploratory ranking, path and portfolio diagnostics with
  frozen simple baselines and `KEEP/REWORK/REJECT/INSUFFICIENT_SAMPLE`.
- Never emit Formal OOS or qualification evidence.

## WP-DATA-QUAL-01, WP-OOS-01, WP-COST-01, WP-QUAL-01

- Route real Provider/archive validation through the existing PIT authority.
- Freeze purged/embargoed walk-forward and locked OOS protocols before access.
- Add A-share cost/capacity sensitivity only after statistical evidence exists.
- Feed real evidence to existing Governance; qualification, assignment and
  promotion remain explicit operator actions.

## Repository gates per checkpoint

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL=... uv run pytest
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

Report commands as PASS/FAIL/NOT_RUN/BLOCKED with exact PostgreSQL version and
test counts. Never collapse an engineering gate into a Live/Prospective claim.
