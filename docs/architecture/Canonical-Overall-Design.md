# Current architecture

> **Status:** CURRENT_ARCHITECTURE
> **Code Evidence:** `pyproject.toml`, `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/interfaces`, `src/market_regime_alpha/application`, `tests/contracts`

The repository is a Python modular monolith. Current research execution has one
installed entry, `mra`, and one composition root, `bootstrap_application`.
Account and formal governance administration retain explicit separate commands
because their observed-Fill, claim-lineage and qualification contracts have no
canonical replacement. This is not full Runtime/CLI cutover.

## Executable entry points

`pyproject.toml [project.scripts]` installs four commands. The generated
[consumer graph](code-inventory.json) enumerates every installed entry, module
entry, callable CLI, script, historical tool and Python deployment template,
with its exact disposition, owner, scope, direct imports, transitive SQL adapters
and persistence dependencies. Static closure is not proof of deployment.

| Entry | Disposition | Actual route and scope |
|---|---|---|
| `mra` | RETAIN | `interfaces/cli:main` → canonical dispatch → `bootstrap_application` → context Applications |
| `decision-system` | RETAIN | `cli/decision_system.py` → DecisionSystem/DecisionRuntime; account administration requires the retained typed Runtime claim/fence |
| `model-governance` | RETAIN | `cli/model_governance.py` → formal Model governance; not experimental Model-use qualification |
| `pit-authority` | RETAIN | `cli/pit_authority.py` → Provider/PIT qualification, ACL and revocation owner |
| `continuous-research` | MIGRATE | Entry and old dispatch deleted. New work uses existing `mra backtest`, `mra research daily` and guarded prospective service; historical Runs are not translated or resumed by another owner |
| `state-system` | MERGE | Entry removed; exact historical pool verification retained in `legacy.inspect_runtime`; descriptive stage-list CLI removed, domain contracts retained |
| `research-shadow` | ARCHIVE | Entry/writer wiring removed; exact completed report/replay retained in `legacy.inspect_runtime`; no claim of new formal shadow qualification |

Uninstalled historical inspection is explicit:
`uv run python -m market_regime_alpha.legacy.inspect_runtime --help`.
It cannot schedule, create or resume Runs. Its database report/replay paths use
connection-level read-only transactions and exact supplied IDs. Other retained
historical lifecycle replay APIs are individually classified in the inventory:
the durable lifecycle replay creates its own verification journal, so it is
not advertised as zero-write inspection.

Fixed-protocol tools live under `historical_tools/`, outside installed/current
execution. Their original bytes remain intact. One tool retains its original
`scripts/` path because its historical reader verifies that source path/hash;
the inventory marks it `HISTORICAL_PINNED_PATH`. Historical tools can reproduce
their declared protocols; they do not authorize current service or new research.
The two old live-loop scripts and unconsumed writer CLI wrappers are deleted.
The orphaned recovery-command projection is also removed; owner replay remains.
No old subsystem is wrapped under `mra`.

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
