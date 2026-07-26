# Repository Map

> **Status:** CURRENT_STATUS  
> **Authority:** Read-only structural map of the audited baseline  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/01-Domain-Boundaries.md, Repository-Coverage-Ledger.tsv  
> **Code Evidence:** main@96e41a12d86b3b5f7472c2d4e44011736b087b6b

| Directory/module | Primary responsibility | Upstream | Downstream | Tests | Docs | State |
|---|---|---|---|---|---|---|
| `src/market_regime_alpha/core` | stable IDs, status and semantic time | none | every V2 domain | core tests | Constitution 02–04/09 | IMPLEMENTED_AND_VERIFIED |
| `data` | provider/dataset eligibility, path evidence, calendar | external source artifacts | universe/features/research | data/calendar tests | Data Constitution | IMPLEMENTED_AND_VERIFIED |
| `universe` | PIT membership and eligibility | data/calendar | Candidate population | universe/eligibility tests | R5/PIT docs | IMPLEMENTED_AND_VERIFIED |
| `features` | Feature definition/materialization and baseline features | data/universe | Candidate models | feature tests | Factor Constitution | IMPLEMENTED_AND_VERIFIED |
| `candidates` | population, datasets, targets, B0/B1, diagnostics | universe/features | research runners | candidate tests | Candidate Research | IMPLEMENTED_AND_VERIFIED |
| `strategies/entry` | Entry path target/evidence materialization | Candidate/path evidence | future Entry model | Entry path tests | Entry Path Target spec | IMPLEMENTED_AND_VERIFIED infrastructure |
| `research` | experiment IDs, provider routing, MR1/MR2, artifacts, Xuntou/PIT | canonical domains/providers | reports/validation | extensive research tests | research history/status | IMPLEMENTED_AND_VERIFIED mechanics |
| `legacy` | compatibility adapters into V2 contracts | dividend_t artifacts | V2 boundaries | adapter tests | R1/R2 docs | PARTIALLY_IMPLEMENTED |
| `dividend_t` | Legacy single-stock/timing/indicator/backtest/risk platform | public data/providers | Legacy dashboard/reports | extensive Legacy tests | Legacy runbooks | LEGACY_ONLY |
| `web` | Legacy FastAPI applications | Legacy services | browser users | web tests | Usage/Tushare docs | LEGACY_ONLY |
| `scripts` | CLI runners, exports, reports and schedulers | source packages | artifacts/reports | some script tests | runbooks/plans | MIXED |
| `backtesting` | sample/Legacy backtest entry points | data/Legacy engine | reports | backtest tests | README/Legacy docs | LEGACY_OR_PROTOTYPE |
| `tools/xuntou` | external runtime probing/export | XtQuant | qualified bundles | Xuntou tests | export runbook | IMPLEMENTED, EXTERNAL_RUNTIME_REQUIRED |
| `tests` | contract, semantic, reader and characterization evidence | all code | CI | n/a | capability matrix | 142 files read |
| `docs/constitution` | normative mission/rules | user decisions | all design/work | link/status checks | docs index | CONSTITUTION |
| `docs/architecture` | current target architecture plus historical audits | Constitution/status | roadmap/specs | docs checks | docs index | CURRENT + HISTORICAL separated |
| `docs/research` | current programs and historical research results | architecture/data | experiments/roadmap | docs checks | docs index | CURRENT + HISTORICAL separated |
| `docs/specs` | Phase D and provider contracts | architecture/research | implementation | future contract tests | specs index | CURRENT_SPECIFICATION |
| `docs/status` | unique implementation truth and gaps | code/tests/artifacts | roadmap/agents | docs checks | docs index | CURRENT_STATUS |
| `docs/archive` | dated plans and Legacy/historical evidence | migration | audit only | link checks | archive index | HISTORICAL |

## Exclusions

`.idea/**` is tracked IDE metadata and does not define runtime behavior. Data assets were read and catalogued but are not treated as source code. No untracked virtual environments, caches, binary build products or generated reports were included in the baseline.
