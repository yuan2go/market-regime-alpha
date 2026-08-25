# Repository Convergence Inventory

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Consumer/import inventory and Legacy disposition
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-25
> **Executable guards:** `tests/architecture/`
> **Code Evidence:** `src/market_regime_alpha`, `pyproject.toml`, `tests/architecture`

This inventory follows actual imports, installed entry points, composition
roots and PostgreSQL writers. A directory name is not treated as Authority.
Historical files remain immutable even when their producing code is retired.

The disposition column reflects the consumer graph at implementation checkpoint
`main@adbc7857e261835eccbe2acf4902910363dae724`. Zero-consumer producers have been physically deleted. Every retained
compatibility layer below names a current replay/migration consumer and a
deletion condition.

## Canonical package inventory

| Package / seam | Actual consumers | Runtime | Authority / persistence | Canonical replacement | Disposition |
|---|---|---|---|---|---|
| `application/continuous_research` | installed `continuous-research` CLI, Dataset/State/Controlled/Decision/Strategy child adapters | sole all-day Runtime | Continuous PostgreSQL journal, Evidence commit and child identities | none | **KEEP**, Daily Alpha terminal projection added |
| `application/historical_research` | `continuous-research historical-*`, Phase-II owner services | sole Historical Runtime | Historical PostgreSQL journal; delegates business facts | standalone backtests | **KEEP** |
| `features` | Continuous and Historical Decision materialization | both canonical runtimes | Feature artifacts and PostgreSQL owner bindings | `dividend_t` indicator execution | **KEEP**; MACD, Chan, Volume/Price and trend kernels already have canonical implementations |
| `candidates` and `research/candidate_discovery` | State System, Historical Panels, Strategy Runtime | shared business semantics | CandidateSet PostgreSQL owner | legacy Candidate scripts | **KEEP** |
| `signals`, `forecasting` | State System, Daily Alpha and Strategy Opportunity resolver | shared business semantics | typed State Signal/Forecast, PathForecast and conditional owner lineage | caller-only prediction DTOs | **KEEP**; Opportunity and Daily projection typed-reload exact owners |
| `strategies` | Continuous/Historical adapters and Strategy Shadow | shared Strategy kernel | Multi-Strategy, pre-Strategy Risk and Opportunity PostgreSQL owners | `dividend_t.strategy` | **KEEP / REFACTORED** |
| `application/shadow_research` | existing `settle-day`, `ContinuousOutcomeSettlementService` post-close path | Continuous control plane | immutable factual and targeted prospective Outcome owners with exact Daily snapshot lineage | ad-hoc next-day review | **KEEP**; orchestration is merged into the sole scheduling path |
| `application/research_validation` | Model Governance, Historical Evidence and qualification reload | bounded child/tool | PostgreSQL Research Validation owners | scattered qualification flags | **KEEP / SIMPLIFY**; no new qualification layer introduced |
| `application/historical_corpus` | Historical Runtime and `continuous-research historical-phase-ii` | Historical Runtime | Raw/Normalized, component, Panel, Outcome and Historical Evidence owners | standalone research scripts | **KEEP / REFACTORED**; one bounded operator delegates to the existing Phase-II service |
| `persistence/postgres` | every canonical runtime/repository | both canonical runtimes | sole persistent database; migration head is forward-only | SQLite/local runtime stores | **KEEP** |

## Legacy and compatibility inventory

| Package / path | Actual consumers | Runtime / write status | Valuable logic disposition | Canonical replacement | Disposition |
|---|---|---|---|---|---|
| retired Dividend-T execution plane: `backtest`, `bar_store`, `brokers`, `cache`, `scheduler`, `sell_side`, `signal_audit`, `strategy_modes`, `grid_25t_test`, `point_hit_rate`, `risk`, `universe` | no canonical/runtime/replay/migration consumer | no installed CLI, PostgreSQL writer or execute Authority | frozen output/evidence remains immutable; quantitative equivalents already live in canonical Feature/Research | Feature pipeline + Historical/Strategy Runtime | **DELETE — completed** |
| retained `dividend_t` technical/trend/MACD identity subset | `migration/legacy/adapters/technical_observables.py`, `migration/legacy/adapters/tencent_dividend_t.py`, `legacy/dataset_contract_adapter.py` | read/compare/replay only | exact old observable, Tencent trend snapshot and MACD dataset/experiment identity interpretation | canonical Feature/Dataset owners | **COMPATIBILITY_ONLY**; delete after those adapters and every referenced artifact identity are superseded with differential replay proof |
| `backtesting/**` and `backtesting.py` | zero consumers after identity fixtures were decoupled | no entry point, journal or writer | frozen results remain historical evidence; new work uses Historical Research | Historical Research Runtime | **DELETE — completed** |
| `web/dividend_t_app.py`, `web/tushare_app.py` and manual Dividend-T schedulers | zero canonical/replay/migration consumers | parallel web/schedule execution removed; FastAPI/Uvicorn/APScheduler dependencies removed | none retained | installed canonical CLIs | **DELETE — completed** |
| `daily_research/**` | no current production import; compatibility tests and Authority catalog preserve existing identity meaning | no write/execute capability | V1 identities/readers retained by repository contract | Continuous Research + Decision System | **COMPATIBILITY_ONLY**; delete only after immutable `daily_research` artifacts no longer require their readers |
| `daily_decision/**` | Canonical Lifecycle replay/stages, Operational Research, thesis health and old Daily Loop readers | bounded compatibility contracts; not the all-day Runtime | existing MR1/daily-decision identities retain meaning | Decision System for current writes | **COMPATIBILITY_ONLY / MIGRATE_GRADUALLY**; delete after named consumers reload typed canonical replacements and differential replay passes |
| `application/daily_loop/**` | `FreeDataOperationService`, Source Freeze and repository factory plus compatibility tests | not the current all-day Runtime; no scheduler entry point | request/repository identities still consumed | Continuous Research | **MIGRATE / COMPATIBILITY_ONLY**; delete after FreeData/SourceFreeze consumers move to canonical contracts |
| `legacy/**` | characterization and import adapters | read/replay only | exact identity translation | typed canonical owners | **COMPATIBILITY_ONLY** |
| `migration/legacy/**` | migration comparison harness only | no canonical write/execute import permitted | reproducibility adapters | canonical Feature/Dataset contracts | **COMPATIBILITY_ONLY** |
| `research/mr1*`, `research/mr2*` | historical artifact verifier registry, readers, scripts and tests | no Runtime or canonical writer | immutable experiment interpretation only | Historical Research Experiments | **COMPATIBILITY_ONLY**; delete after verifier registry no longer recognizes those immutable schemas |
| Tencent composite facades and old Provider adapters | Tencent composite acquisition/replay and migration comparison | auxiliary Provider evidence only; never formal Provider Authority | source-specific parsing retained where exact artifact replay requires it | canonical source manifests and FreeData composition | **COMPATIBILITY_ONLY**; delete per Provider/schema after all referenced artifacts are superseded |

No historical Evidence, migration or artifact identity is deleted by this
classification. “Retired” means no canonical schedule, write or execute
consumer; it does not mean that provenance is rewritten.

## Enforced dependency direction

The architecture tests fail if:

- Continuous or Historical Runtime imports a Legacy Runtime plane;
- canonical Feature code imports Strategy, execution or Legacy producers;
- research helpers import Position or Execution mutation domains;
- `legacy`, `migration/legacy`, `dividend_t` or old backtests import canonical
  Runtime/PostgreSQL write paths;
- Strategy imports the post-Portfolio Complete Account Risk owner;
- an installed CLI entry point names a retired producer.

This preserves one business fact → one owner → one canonical runtime path while
allowing compatibility readers to keep old Evidence replayable.
