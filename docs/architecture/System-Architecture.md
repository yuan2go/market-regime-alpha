# System Architecture

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical implementation architecture
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** `src/market_regime_alpha/cli/continuous_research.py`, `src/market_regime_alpha/application/continuous_research`, `src/market_regime_alpha/persistence/repository_factory.py`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`

## Shape

Market Regime Alpha is one Python modular monolith with one PostgreSQL 16 authority. It is a human-in-the-loop research and decision-support system. It has no broker writer and no automatic Order, Fill or Position authority.

There is one canonical all-day runtime owner:

```text
continuous-research run-due
  -> ContinuousResearchScheduleRunner
  -> ContinuousResearchTickRunner
  -> PostgresContinuousResearchJournal
  -> Provider attempt / immutable evidence commit / change decision
  -> ordered bounded-context children
```

`canonical_lifecycle`, `controlled_operation`, `state_system` and `decision_system` are bounded children or operator tools. They are not parallel daily schedulers.

## Actual runtime chain

The current free-data Research/Shadow composition is:

```text
BaoStock/Tencent recorded provider evidence
-> DailyLoop source freeze
-> Canonical market-data Dataset
-> Feature materialization
-> PostgreSQL Model Governance selection
-> State System
   -> Market Regime
   -> ETF Rotation
   -> Theme Rotation
   -> Capital State
   -> StateSeries
   -> Dynamic Stock Pool
   -> Candidate
-> Controlled Operation
   -> pre-decision minute evidence
   -> Signal
   -> uncalibrated PathForecast
   -> optional Canonical Lifecycle child
-> ResearchDailySummary
-> Continuous child receipts and terminal tick
```

The runtime denies `PRODUCTION` when the input is free public evidence. A missing or invalid stage is represented by typed blocked evidence; the runtime does not synthesize a missing Canonical Lifecycle receipt.

The post-runtime research chain is separately invoked and is not part of the canonical daily writer:

```text
ResearchDailySummary
-> Research Shadow frozen decision
-> factual Outcome / Target settlement
-> prospective attestation (currently prospective_proven=false)
-> Evaluation Dataset / Research Panel V2
-> canonical Factor Extraction
-> engineering Ablation / Calibration / Formal Evaluation
-> Entry research
-> isolated Strategy Shadow
-> Holding / Exit engineering validation
-> blocked Production Admission projection
```

## Installed CLI boundary

There are 12 installed scripts:

- six bounded free-data operation commands: prepare, run-window, resume, replay, report and inspect;
- `continuous-research`, the sole all-day scheduler/runtime entry;
- `state-system` and `decision-system`, bounded operator commands;
- `model-governance` and `pit-authority`, Authority administration commands;
- `research-shadow`, a research operation command.

Additional modules with `__main__` guards are internal tools, compatibility utilities or research harnesses. They do not become canonical merely because Python can execute them.

## Package responsibilities

| Package | One responsibility |
|---|---|
| `application/continuous_research` | Own the all-day schedule, tick lease/fence, provider attempt and child composition. |
| `application/free_data_operation` | Freeze and run one bounded public-data decision-window operation. |
| `application/state_system` | Persist ordered State, StateSeries, Pool and Candidate owner receipts. |
| `application/controlled_operation` | Coordinate one decision-time acquisition/calculation package. |
| `application/canonical_lifecycle` | Recover one downstream research-to-manual lifecycle run; never schedule the day. |
| `application/decision_system` | Own Research Summary and the separate manual-account decision-support projection. |
| `application/shadow_research` | Freeze research decisions and settle factual prospective outcomes. |
| `application/research_evaluation` | Build immutable outcome datasets, target protocols and complete Research Panel V2. |
| `application/research_validation` | Compute engineering-only factor, ablation, calibration, evaluation and Entry evidence. |
| `application/strategy_shadow` | Simulate Entry/Fill/Position/Holding/Exit without real execution mutation. |
| `research/**` | Hold pure research models and observable State algorithms. |
| `market_data`, `data`, `universe`, `features` | Own source semantics, datasets, eligibility, materialization and feature lineage. |
| `signals`, `forecasting`, `candidates` | Compute distinct Candidate, Signal and Forecast artifacts. |
| `platform` | Own Model Registry, Model Governance, experiment governance and selection receipts. |
| `decision`, `portfolio`, `execution`, `position` | Own Opportunity/Thesis, Portfolio/Risk, manual Fill and fill-derived Position lifecycles. |
| `persistence` | Compose PostgreSQL-only repositories and validate the full schema. |

## Dependency rules

- Domain objects do not schedule runtimes or select repositories.
- Application compositions call bounded owners; they do not recreate their persistence.
- Projection, DTO, protocol, policy and reference objects never grant Authority.
- New writers use `RepositoryFactory` and PostgreSQL. No file or SQLite persistence fallback exists.
- Legacy may be read or characterized only through explicit compatibility/migration boundaries.
