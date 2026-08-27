# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA implementation read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-27T11:05:01Z
> **Repository SHA:** `d0d1f3152a20f1a3f4f9b8a1d9c4383a49162fb7`
> **Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epoch:** `LEGACY_MIGRATIONS_001_106`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-02 repository audit v1`
> **Source Tree IDs:** source `13e8922bb42a0054a2f168eac5ce3ab61f5694ed`; migrations `6d3730548780ad6244d2cfecb4fb3559064b6f06`; tests `7c525ee274be34d9cae7dbe1d76c700d9f21a54c`
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

This snapshot is invalid after any source, migration, test, or composition change
until regenerated. It can report implementation and validation facts; it cannot
write business state or promote research/Production qualification.

## Current implementation truth

| Area | Exact current fact at the snapshot SHA |
|---|---|
| Package shape | Python 3.12 modular monolith with global technical/domain packages and multiple historical compositions; target context-first packages do not exist |
| PostgreSQL | PostgreSQL 16-only persistent implementation; 106 packaged incremental migrations and 283 expected Authority tables |
| Runtime | Continuous Research is the current all-day control plane; Canonical Lifecycle, State, Decision, daily, controlled, historical, shadow, and research paths remain bounded or legacy children with overlapping persistence |
| CLI | Six installed scripts: `continuous-research`, `state-system`, `decision-system`, `model-governance`, `pit-authority`, `research-shadow` |
| Market/PIT | Public-provider capture, PIT/calendar, historical corpus, revisions, and gaps exist across several packages/tables; no target Market/PIT owner exists |
| Universe/Candidate | Current Universe, Eligibility, State/Candidate, daily and historical paths are implemented but not converged on the target aggregates |
| Research | Dataset/experiment/evaluation/evidence/qualification capability exists across campaign- and phase-specific owners; no target unified evidence model exists |
| Decision/Outcome | Signal, Forecast, Opportunity, Strategy, Portfolio, Risk, Outcome, and Attribution capabilities exist through multiple current paths; target single write paths do not exist |
| Execution/Account | Human/manual execution only; observed effective Fill drives trade-caused Position. No broker writer or unattended execution authority exists |
| Target epoch | `MRA_REFOUNDATION_1`, the target 91-table `001_baseline.sql`, target `bootstrap.py`, and target `mra` CLI are not implemented |
| Legacy | `daily_research`, `daily_decision`, `dividend_t`, `legacy/**`, `migration/legacy/**`, old migrations, and compatibility tests remain physically present |

The approved Target Architecture is therefore `DESIGN_APPROVED / CODE_NOT_STARTED`.
No target bounded context may be reported implemented merely because a current
class/table has similar vocabulary.

## Exact-SHA verification

The complete command ledger is
[WP-02 Pre-Refoundation Verification Baseline](../references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md).
At this snapshot:

- dependency sync, documentation checks, 3,034-test full regression, platform
  tests, focused PostgreSQL migration/schema tests, focused Runtime/replay/
  recovery/idempotency tests, Ruff, mypy, build, and diff checks pass;
- clean explicit schema migration applies 001→106 and verifies 283 tables;
- the migration operator fails if its configured application schema does not
  already exist, because `search_path` falls through to `pg_catalog`; Foundation
  must replace this implicit precondition with the new epoch bootstrap contract.

This proves the pre-refoundation implementation is reproducible locally. It
does not prove the target schema/runtime or any Provider, Alpha, broker, or
Production claim.

## Research and production ceiling

Existing immutable reports retain negative, inconclusive, and not-estimable
results. They are historical evidence, not an active Roadmap and not a reason to
preserve old persistence identities.

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
formal_pit_established = false
formal_oos_alpha_supported = false
sustained_prospective_value_proven = false
```

The current engineering implementation may be tested and replayable while every
stronger empirical or operational claim remains false.

## Refresh contract

A future generated Current State must obtain facts read-only from Git identity,
the configured schema epoch/migration registry, code-owned inventories, executed
test receipts, and canonical Evidence IDs/hashes. It must display missing or
unavailable sources explicitly. It receives no database write credentials and
cannot infer “current” from filenames, latest rows, documents, or artifact
directories.
