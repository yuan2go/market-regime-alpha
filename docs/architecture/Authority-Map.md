# Authority and consumers

> **Status:** CURRENT_ARCHITECTURE
> **Code Evidence:** `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/infrastructure/postgres/repositories`, `src/market_regime_alpha/infrastructure/postgres/queries`, `tests/contracts`

Paths below are relative to `src/market_regime_alpha`. Each row names an actual
composed command boundary; child rosters and SQL references are enumerated in
[the generated inventory](code-inventory.json). A table, dataclass or policy is
not an independently authorized writer.

| Owner / fact | Application and UoW / Repository | Relational roots; readers / consumers | Protected contract |
|---|---|---|---|
| Runtime | `runtime/application/service.py:RuntimeApplication`; `infrastructure/postgres/uow.py`, `repositories/runtime.py` | `runtime_schedule/run/step/attempt`, `command_receipt`, `audit_event`; runtime queries and all fenced commands | DB-clock lease; dependency closure; atomic admission; stale fence zero writes; unknown effect reconciliation |
| Artifact | `runtime/application/artifacts.py:ArtifactApplication`; Runtime UoW and artifact repository | `artifact`, dependencies/verification/GC rows; `infrastructure/artifacts/LocalArtifactStore` and exact downstream bindings | Hash/size/physical bytes; content-addressed byte publication; receipt-based metadata idempotency |
| Market | `market/application`; `market_uow.py`, capture/reference/normalization repositories | `data_capture`, `trading_session`, `market_bar_revision`, `source_gap`; `queries/market*`, Selection and Outcome | Preserve source, first-observation, revision, knowledge and price basis |
| Archive / prospective | `market/application/archive_operations.py`, `prospective_runtime.py`; `archive_uow.py` | `market_archive`, slices/seals; prospective generation/schedule/terminal/planning-gap rows; continuity and health queries | Complete frozen roster; exact sessions; distinct retrospective and prospective lanes; no backdated timely capture |
| Selection | `selection/application`; `selection_uow.py`, `candidate_uow.py` | Universe, Eligibility and Candidate roots/children; `queries/selection_market.py`, candidate queries | Explicit population; every row has a disposition; strict complete-case ranking and boundary ties |
| Research definitions | `research_qualification/application/service.py`, Target commands; `research_uow.py`, `target_uow.py` | `dataset/source`, `feature_definition`, Target/checkpoints/metrics; candidate and Decision input ports | Decision-input Dataset excludes future labels; immutable definitions and exact Feature order/units |
| Decision | `decision_support/application`; decision/context/inference/opportunity/portfolio/risk UoWs | Decision/commitment/reference, Context, Signal/Forecast, Opportunity, Portfolio/Risk; corresponding queries/verifiers | Complete Candidate × Target commitments; Context after Candidate; Risk after Portfolio |
| Outcome | `outcome/application`; `outcome_uow.py`, Outcome repositories | `market_target_outcome`, revisions/observations/metrics/source rosters; `queries/outcomes.py`, `outcome_verification.py` | Sole market labels and episode prices; complete immutable revisions; path and checkpoint windows remain distinct |
| Partition / Experiment | `research_qualification/application/partitions.py`, `experiments.py`; separate UoWs | `research_partition`, members/access; `experiment`, partition/Run bindings | Complete owner-derived population, time order, first-access ledger, purge/embargo |
| Model | `research_qualification/application/research_models.py`; `research_model_uow.py` | `model`, TrainingRun/sample/reproducibility, ModelVersion, experimental use/revocation; model input/forecast query ports | Completed FIT; mature known labels; frozen fitted Artifact/preprocessing; exact later use, no latest-model selection |
| Evaluation | `research_qualification/application/evaluations.py:EvaluationCommands`; `evaluation_uow.py`, `repositories/research_evaluations.py` | `evaluation_run/metric`, complete observations/sources/costs/formula rosters; `queries/research_verification.py` | Prepare outside write UoW; commit revalidation; actual root and child fields agree with typed recomputation, not just saved hashes |
| Evidence / Assessment / Qualification | Respective commands in `research_qualification/application`; separate UoWs | Concrete evidence/assessment/qualification roots and complete floor/source bindings; qualification verification/admission queries | Purpose-scoped floors, no self-promotion; feedback only into later generations |
| Backtest / report | `research_qualification/application/backtests.py`, `backtest_execution.py`, `backtest_holdout.py`, `backtest_reports.py`; `backtest_uow.py` | Existing `exploratory_backtest_run` + specification/action/model/evaluation/report bindings; exploratory holdout reservation/opening | Generic owner dispatch; frozen selection and exact Partition access; report is reconciled projection; comparison checks semantics before values |
| Daily research observations | `interfaces/daily_observations.py`; `queries/daily_predictions.py` | Existing Prediction, acquired Outcome revisions and Evaluation; read-only CLI consumer | Reconciled reports; exact commitment/Partition/acquisition roster; complete population; no new labels, metrics or truth table |
| Research Validity interpretation | `research_qualification/application/validity.py`; `domain/validity_protocol.py`, `validity_statistics.py`, `validity_temporal.py`; `queries/daily_validity.py` | Frozen source protocol plus exact daily observation read ports; `mra research validity daily` | Evaluation-owned Decimal interpretation; complete common population and temporal exclusions; original metrics unchanged; source declaration is not a registered DB Artifact or qualification |

The SQL adapter paths in this table are under `infrastructure/postgres`.
Schema bootstrap, verify and controlled upgrade are owned by
`infrastructure/postgres/schema.py:SchemaManager`; they are explicitly separate
from ordinary business startup.

`interfaces/prospective_operation_guard.py` and
`infrastructure/postgres/prospective_operation_session.py` enforce exact scope
and shared atomic Runtime admission. Session supervision is not the business
lease/fence. Daily work receives explicit admission for its own Run; it does
not select a different database if blocked.

`interfaces/deployment_profile.py` verifies source/wheel/installation and exact
operation scope before emitting a new local profile. It writes no business facts
and grants no model or data qualification. Retained PostgreSQL write connections
share Runtime admission for database exclusion, while keeping their existing
Account/Fill/governance transactions and Authority. Historical read-only scopes
do not request writer admission.

Canonical owner connections also participate when their command has no Runtime
Attempt. An unsupervised narrow write connection holds a shared database
reservation until returned; a supervisor needs the exclusive reservation.
Supervised connections verify the authentic reservation and database scope.
Thus startup cannot overtake an existing owner transaction, and foreign owner
commands cannot bypass the service by avoiding claim. Read-only queries remain
available. Arbitrary SQL credentials are outside this cooperative boundary and
must be excluded by the operational handoff.

The retained account family uses `execution/postgres_manual_repository.py`,
`position/postgres_*`, `portfolio/postgres_*` and
`persistence/repository_factory.py`. Its actual observed-Fill, allocation,
approval and account-risk tests remain. It has not been replaced by the
hypothetical research economics kernel.

Source tables alone do not prove every intended command exists. Planned
Execution/Attribution surfaces from former designs are not advertised as
implemented `mra` commands. Discover the actual surface with `uv run mra --help`.

## Consumer dispositions and retained boundaries

The `consumer_graph` in [code-inventory.json](code-inventory.json) is the complete
per-file matrix; `scripts/repository_inventory.py:CONSUMER_DISPOSITIONS` records
reviewed maintenance decisions. It does not route commands or grant business
admission. Hygiene rejects any executable root without a closed disposition.

| Consumer class | Disposition and owner | Persistence / invariant |
|---|---|---|
| Current research, archive qualification, prospective/daily deployment | RETAIN canonical composition | `infrastructure/postgres`; exact Runtime admission, narrow owner UoWs, owner reconciliation |
| Decision and manual risk/Fill/portfolio/thesis scripts | RETAIN account/Execution owners | `RepositoryFactory`, `execution`, `position`, `portfolio`, `application/decision_system`; observed Fill and approval lineage cannot be replaced by Portfolio proposal or episode economics |
| Formal Model and PIT administration | RETAIN governance owners | `platform` governance + `application/pit_authority`; evidence floors, revocation and ACL remain distinct from experimental research Model use |
| Legacy database bootstrap/migration/DR/engineering tools | RETAIN explicit account schema administration | `persistence/postgres`; their schema-head checks do not qualify the canonical research schema |
| Raw Provider exports and Xuntou probes | RETAIN auxiliary source tooling | Raw files/products are not canonical Capture/Archive or qualified Provider facts |
| Fixed historical research tools | ARCHIVE, uninstalled | Existing protocol/serializer/Artifact identities; no default current research dispatch |
| Exact historical inspection | MERGE read-only runtime/shadow/pool operations | Retained PostgreSQL journal and serializer owners; explicit database and IDs, no scheduling |
| Exact lifecycle/Feature replay APIs | RETAIN historical API | Exact package/Dataset; lifecycle durable replay writes only its separate verification journal |
| Repository and deployment utilities | RETAIN respective tooling/evidence owners | No second scheduler or business Authority |

### Package and migration ownership

| Package/family | Disposition | Concrete remaining consumer or removal |
|---|---|---|
| `research_qualification` | RETAIN | Canonical Dataset/Target/Model/Evaluation/Backtest Applications, narrow UoWs and queries |
| `research` | ARCHIVE research protocols; RETAIN bound value contracts | Historical tool/Artifact readers; `position/thesis_health.py` consumes CandidateSet, capital, regime and theme contracts. Replacing them would alter account review inputs |
| `application/historical_corpus` | ARCHIVE | Historical corpus/Artifact materialization and reader tests; absent from canonical research import closure |
| `platform` | RETAIN formal governance; ARCHIVE protocol readers | Installed Model/PIT and Decision Runtime lineage consume governance contracts; historical tools consume fixed protocol serializers. This is not a second current research Model owner |
| `persistence/postgres` | RETAIN account/governance/history storage | Actual account, approval, Fill, Model/PIT and historical replay consumers remain. Shared `RepositoryFactory.model_registry` duplicate alias removed; callers use `model_governance` |
| `infrastructure/postgres` | RETAIN sole current research/schema owner | `bootstrap_application`; new research SQL and registered upgrades belong here |
| Empty per-package migration globs | DELETE | Removed package-data entries for platform, decision, portfolio, position, execution, features and three application families; none contained released SQL |
| Released numbered legacy migrations | RETAIN immutable | Account/Decision Runtime journals and formal governance constraints still consume the numbered schema; no research additions to that family |

`application/decision_system/runtime.py:_claim` requires the retained
`ClaimedRuntimeTick`; PostgreSQL account writes reload its claim/fence/lease.
Retiring the old scheduler entry does not migrate that lineage, grant a new
claim or enable canonical account execution. A future cutover must first map
that invariant into the canonical Runtime owner with account-specific tests.
The old journal/domain readers remain for those exact references and replay.
No availability fallback, dual write or implicit restored writer is introduced.
