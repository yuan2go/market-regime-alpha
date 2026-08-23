# Repository Convergence Inventory

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Consumer/import inventory and Legacy disposition
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-24
> **Executable guards:** `tests/architecture/`
> **Code Evidence:** `src/market_regime_alpha`, `pyproject.toml`, `tests/architecture`

This inventory follows actual imports, installed entry points, composition
roots and PostgreSQL writers. A directory name is not treated as Authority.
Historical files remain immutable even when their producing code is retired.

The disposition column is an audited target, not proof that physical code was
already removed. At `main@b617844`, several `RETIRED` paths still exist. Closure
requires a current import/consumer graph, deletion of zero-consumer producers
and an explicit replay/migration consumer plus deletion condition for every
retained compatibility layer.

## Canonical package inventory

| Package / seam | Actual consumers | Runtime | Authority / persistence | Canonical replacement | Disposition |
|---|---|---|---|---|---|
| `application/continuous_research` | installed `continuous-research` CLI, Dataset/State/Controlled/Decision/Strategy child adapters | sole all-day Runtime | Continuous PostgreSQL journal, Evidence commit and child identities | none | **KEEP**, Daily Alpha terminal projection added |
| `application/historical_research` | `continuous-research historical-*`, Phase-II owner services | sole Historical Runtime | Historical PostgreSQL journal; delegates business facts | standalone backtests | **KEEP** |
| `features` | Continuous and Historical Decision materialization | both canonical runtimes | Feature artifacts and PostgreSQL owner bindings | `dividend_t` indicator execution | **KEEP**; MACD, Chan, Volume/Price and trend kernels already have canonical implementations |
| `candidates` and `research/candidate_discovery` | State System, Historical Panels, Strategy Runtime | shared business semantics | CandidateSet PostgreSQL owner | legacy Candidate scripts | **KEEP** |
| `signals`, `forecasting` | State System and Strategy Opportunity resolver | shared business semantics | State Signal/Forecast owners and model lineage | caller-only prediction DTOs | **KEEP**; Opportunity reload must use typed owner loaders, not recursive JSON inference |
| `strategies` | Continuous/Historical adapters and Strategy Shadow | shared Strategy kernel | Multi-Strategy, pre-Strategy Risk and Opportunity PostgreSQL owners | `dividend_t.strategy` | **KEEP / REFACTORED** |
| `application/shadow_research` | existing `settle-day`, Continuous post-close settlement | Continuous control plane | immutable factual and targeted prospective Outcome owners | ad-hoc next-day review | **KEEP / MERGE** into the sole scheduling path |
| `application/research_validation` | Model Governance, Historical Evidence and qualification reload | bounded child/tool | PostgreSQL Research Validation owners | scattered qualification flags | **KEEP / SIMPLIFY**; no new qualification layer introduced |
| `application/historical_corpus` | Historical Runtime and Phase-II research | Historical Runtime | Raw/Normalized, component, Panel, Outcome and Historical Evidence owners | standalone research scripts | **KEEP / REFACTOR**; Raw correctness split into an independent kernel |
| `persistence/postgres` | every canonical runtime/repository | both canonical runtimes | sole persistent database; migration head is forward-only | SQLite/local runtime stores | **KEEP** |

## Legacy and compatibility inventory

| Package / path | Actual consumers | Runtime / write status | Valuable logic disposition | Canonical replacement | Disposition |
|---|---|---|---|---|---|
| `dividend_t/**` | old scripts, old web app, characterization tests, migration comparison only | no installed CLI, no Canonical composition, no PostgreSQL write or execute Authority | MACD/Chan/Volume/Support-Resistance/Trend semantics are represented by `features/technical`, `features/chan` and `features/volume_price`; legacy code remains for exact characterization | Feature pipeline + Strategy Runtime | **RETIRED / COMPATIBILITY_ONLY** |
| `backtesting/**` and `backtesting.py` | manually invoked historical scripts only | no installed entry point, journal or canonical writer | frozen results remain historical evidence; new research must use Historical Experiment/Runtime | Historical Research Runtime | **RETIRED** |
| `daily_research/**` | compatibility readers/tests only | no current write/execute capability in the Authority catalog | V1 identities/readers retained | Continuous Research + Decision System | **COMPATIBILITY_ONLY** |
| `daily_decision/**` | Canonical Lifecycle compatibility, old Daily Loop, immutable readers | bounded compatibility contracts; not the all-day Runtime | existing MR1/daily-decision identities must retain meaning | Decision System for current writes | **COMPATIBILITY_ONLY / MIGRATE_GRADUALLY** |
| `application/daily_loop/**` | legacy tests/explicit callers; no installed CLI | not current Runtime | none requiring a second scheduler | Continuous Research | **RETIRED** |
| `legacy/**` | characterization and import adapters | read/replay only | exact identity translation | typed canonical owners | **COMPATIBILITY_ONLY** |
| `migration/legacy/**` | migration comparison harness only | no canonical write/execute import permitted | reproducibility adapters | canonical Feature/Dataset contracts | **COMPATIBILITY_ONLY** |
| `research/mr1*`, `research/mr2*` | old scripts/tests and historical artifact readers | no Runtime or canonical writer | immutable experiment interpretation only | Historical Research Experiments | **RETIRED / COMPATIBILITY_ONLY** |
| Tencent composite facades and old provider adapters | exploratory scripts, compatibility comparison | auxiliary Provider evidence only; never formal Provider Authority | source-specific parsing retained where replay requires it | canonical source manifests and FreeData composition | **COMPATIBILITY_ONLY** |

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
