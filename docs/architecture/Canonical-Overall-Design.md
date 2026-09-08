# Current architecture

> **Status:** CURRENT_ARCHITECTURE
> **Code Evidence:** `pyproject.toml`, `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/interfaces`, `src/market_regime_alpha/application`, `tests/contracts`

The repository is a Python modular monolith with two explicit persistence and
entry-point families. The installed `mra` research path is implemented and wired;
legacy CLI/account paths remain executable. There has been no full Runtime/CLI
cutover. A module being retained or packaged does not establish production use.

## Executable entry points

`pyproject.toml [project.scripts]` is the installed entry-point inventory.

| Entry | Actual route |
|---|---|
| `mra` | `interfaces/cli/__init__.py:main` → `interfaces/cli/main.py:_dispatch` and `interfaces/cli/daily.py` → `bootstrap.py:bootstrap_application` |
| `continuous-research` | `cli/continuous_research.py:main` → `application/continuous_research` and explicit PostgreSQL repository composition |
| `state-system`, `decision-system` | `cli/state_system.py`, `cli/decision_system.py` → respective `application` owners |
| `model-governance`, `pit-authority`, `research-shadow` | corresponding `cli` modules → retained governance/PIT/shadow owners |

Additional `scripts/` and module CLIs still consume research, feature, strategy
and compatibility code. Do not declare these dead from the installed-script
list alone. See the inventory's consumer edges and the Roadmap's overlap debt.

## Research composition and call chains

`bootstrap_application` verifies schema before creating `TargetPostgresPool`.
`TargetApplication` binds narrow UoW providers, query ports, `LocalArtifactStore`,
the explicit Ridge trainer/predictor and context Applications. Startup does not
bootstrap or upgrade a database. Schema changes use separate guarded commands.

```text
mra backtest
  → BacktestApplication / BacktestExecutor / BacktestRuntimeActionExecutor
  → BacktestCanonicalActionHandler
  → owner Applications → domain calculations → narrow UoWs/repositories
  → PostgreSQL owner rows + Receipt/Audit/Attempt completion
  → owner queries → reconciliation → BacktestReportApplication

mra archive prospective serve
  → operation preflight + session admission + bounded process wakeup
  → ProspectiveArchiveRuntimeApplication → RuntimeApplication
  → due claim/lease/fence → MarketArchiveOperations → MarketApplication
  → Provider/Artifact effects outside write transaction → normalization/terminal
  → continuity + prospective health queries

same guarded service tick
  → daily_service.daily_tick → DailyResearchOperations
  → complete DataReady → Dataset/Candidate/Decision → independent model Forecast
  → immutable publication and pending Outcome Run
  → later frozen-plan recovery → canonical Outcome → Evaluation/report
```

Generic Backtest uses `exploratory_backtest_run` as its root;
`backtest_specification` and action/model/evaluation bindings refine that root.
There is no new root per consumer. `backtest progress` reads Runtime state and
explicitly does not perform full owner reconciliation. Inspect/replay/report
must reconcile complete identities, parent/child rosters and physical Artifacts.

The business dependency is Market → Universe/Eligibility → Dataset → Candidate
→ Decision/Target commitments → Context → Signal/Forecast → Opportunity
→ Portfolio → Risk. Outcome settles commitments; Evaluation consumes Outcome.
Model is optional. Candidate does not require a Target, Model or Outcome.
Daily publication has its own experimental Model-use contract and does not
invent a retrospective fold. Settling old publications reads each original plan,
not today's Model-use/template. No service layer owns business time.

## Boundaries that remain enforced

- Domain depends on its own types and shared value objects. Applications use
  ports; PostgreSQL adapters own SQL; the current research root composes them.
- Provider and file I/O occur outside business write transactions. Admission,
  input identities, complete rosters and fences are revalidated for commit.
- Market labels belong to Outcome. Evaluation owns typed metrics and episode
  economics. Reports do not read raw bars or calculate a second metric truth.
- Recommendation and simulated economics do not create Account/Position facts.
  Retained `execution`, `position`, `portfolio` and `application` account paths
  have separate observed-Fill and authorization contracts; no broker admission
  is implied by their presence.
- Exact historical decoders and versioned financial serializers remain where
  historical identities require them. They are not executable fallback owners.

See [Authority Map](Authority-Map.md) for concrete write/read paths,
[Data and Evidence](Data-and-Evidence-Architecture.md) for database scope, and
[Roadmap](../status/Roadmap.md) for unresolved overlap rather than a fictional
fully converged package layout.
