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
| Artifact | `runtime/application/artifacts.py:ArtifactApplication`; Runtime UoW and artifact repository | `artifact`, dependencies/verification/GC rows; `infrastructure/artifacts/LocalArtifactStore` and exact downstream bindings | Hash/size/physical bytes; no path-based authority; Receipt replay before repeated effects |
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
| Backtest / report | `application/backtests.py`, `backtest_execution.py`, `backtest_reports.py` under Research; `backtest_uow.py` | Existing `exploratory_backtest_run` + specification/action/model/evaluation/report bindings | Generic owner dispatch; exact replay; report is reconciled projection; comparison checks semantics before values |

The SQL adapter paths in this table are under `infrastructure/postgres`.
Schema bootstrap, verify and controlled upgrade are owned by
`infrastructure/postgres/schema.py:SchemaManager`; they are explicitly separate
from ordinary business startup.

`interfaces/prospective_operation_guard.py` and
`infrastructure/postgres/prospective_operation_session.py` enforce exact scope
and shared atomic Runtime admission. Session supervision is not the business
lease/fence. Daily work receives explicit admission for its own Run; it does
not select a different database if blocked.

The retained account family uses `execution/postgres_manual_repository.py`,
`position/postgres_*`, `portfolio/postgres_*` and
`persistence/repository_factory.py`. Its actual observed-Fill, allocation,
approval and account-risk tests remain. It has not been replaced by the
hypothetical research economics kernel.

Source tables alone do not prove every intended command exists. Planned
Execution/Attribution surfaces from former designs are not advertised as
implemented `mra` commands. Discover the actual surface with `uv run mra --help`.
