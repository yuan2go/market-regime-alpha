# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Sole current implementation-status document
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/046_close_reference_only_qualification.sql`, `tests`

## Implemented engineering boundary

The system is a PostgreSQL-only modular monolith with one Continuous Research Runtime. It has durable source freeze, Dataset/Feature materialization, Model Governance selection, State/StateSeries/Pool/Candidate, controlled minute/Signal/Forecast work, Research Summary, Canonical Lifecycle mechanics, manual-account Decision support, Research Shadow, prospective outcomes, Panel V2, Research Validation harnesses and isolated Strategy Shadow mechanics.

Actual positions derive only from observed manual fills. The system creates no broker order and does not automatically mutate actual positions.

Migration 046 removes reference-only qualification paths from the current architecture:

- Research Validation PostgreSQL rows cannot be qualified, Production-authorized or claim Formal OOS Authority;
- Historical Samples persist as `UNQUALIFIED` only;
- pure helpers cannot promote Calibration, Entry, Holding/Exit or Strategy Shadow;
- Production Admission has only `BLOCKED`;
- PostgreSQL Model Governance rejects all Production qualification with `PRODUCTION_EVIDENCE_OWNER_RESOLUTION_NOT_IMPLEMENTED`.

This is a deliberate fail-closed state. It does not mean the missing qualification work is complete.

## Complexity census

| Measure | Current count | Interpretation |
|---|---:|---|
| Python source files | 569 | broad modular monolith; size alone is not a defect |
| Python test files | 399 | strong contract/replay coverage, with some fixture-heavy history |
| Canonical all-day Runtime | 1 | `CONTINUOUS_RESEARCH` |
| Installed CLI entry points | 12 | one scheduler plus bounded operation/admin tools |
| PostgreSQL migrations | 46 | contiguous, checksummed, forward-only |
| PostgreSQL Authority-schema tables | 148 | exact `EXPECTED_AUTHORITY_TABLES` catalog; includes Authority owners, journals and projections, not 148 independent business Authorities |
| PostgreSQL owner/repository/journal classes | 32 | bounded owners; not 32 competing global Authorities |
| Repository/journal named classes | 49 | includes Protocols, in-memory research stores and compatibility types |
| Artifact/Receipt class names | 42 | immutable contracts across bounded contexts |
| Policy class names | 34 | time, risk, provider, state and research rules |
| Protocol/Port class names | 16 | external/composition seams |
| Qualification-named class types | 14 | contracts and statuses; only Model Governance is a current qualification writer |
| Current canonical docs | 10 | index, four architecture, four status, one runbook |
| Normative Constitution docs | 10 | unchanged `00` through `09` |
| Current research registries | 1 | negative/inconclusive results |
| Historical/superseded/archive docs | 2 | archive boundary index plus superseded Constitution implementation-status; detailed history lives in Git |
| Legacy `daily_research` | 10 files / about 1.6k lines | compatibility Readers and identities |
| Legacy `dividend_t` | 49 files / about 23.5k lines | isolated characterization and legacy UI/research |
| Explicit `legacy` and `migration/legacy` | 13 files / about 1.5k lines | adapters, migration and replay only |
| Retired `decision_replay_import` schema | 1 table | immutable historical rows retained by forward-only migrations; no current application writer/Reader |

## Complexity classification

- **Essential:** semantic time, immutable identities, PIT resolution, PostgreSQL fences/CAS, separate Candidate/Signal/Forecast/Decision/Position Authorities, replay, actual-Fill Position derivation.
- **Accidental:** many bounded internal `__main__` tools and some fixture-heavy test compositions; address only when touching those workflows.
- **Legacy:** `daily_research`, `dividend_t`, explicit legacy adapters and their compatibility tests. They are isolated from Canonical composition but still carry maintenance cost.
- **AI-generated:** 273 stale/historical Markdown files, five reference-only promotion functions, a generic Governance binding DTO, an 800-line uncomposed Decision replay library and its 400-line pseudo-Production test seeder were removed in this convergence.

## Evidence ceiling

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
formal_pit_established = false
formal_oos_alpha_established = false
production_ready = false
```

CI is separate from local verification. If GitHub Actions has not run on the final commit, the only valid statement is `CI_NOT_RUN`.
