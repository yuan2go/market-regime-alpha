# Repository Convergence Inventory

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target package, Legacy, documentation, prompt, and Skill disposition
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-01
> **Code Evidence:** `src/market_regime_alpha`, `pyproject.toml`, `tests/architecture`, `AGENTS.md`, `scripts/reconcile_branches.py`, `.claude/skills/reconcile-branches/SKILL.md`

This inventory freezes what the business implementation phase will converge and
delete. A governance checkpoint may apply its documentation, Skill, and
persistent-prompt dispositions without claiming that the business Target is
implemented or changing business source, migrations, fixtures, or test semantics.

## 1. Current structural facts

Exact source-module, test, CLI, migration, relation, and tree-object counts are
volatile implementation facts and live only in
[Current State](../status/Current-State.md) or exact-SHA Verification records.
The durable convergence facts are:

- the Legacy migration line through 106 and its 283-table disposition remain
  current business implementation until Hard Cutover;
- nested Continuous, Controlled Operation, Canonical Lifecycle, State,
  Decision, Historical, Research Shadow, and Strategy Shadow journals/owners
  remain reachable;
- repository-wide factories and compatibility paths still participate in
  composition and replay;
- the unreleased target draft now contains Target/Decision commitment, Market
  Target Outcome, and the focused-validated WP-11 Partition/Experiment/
  Evaluation implementation. Runtime dispatch remains absent, and the WP-11Q
  audit found that the three WP-11 command modules are not yet composed by the
  sole `bootstrap.py` target application;
- WP-11 remains below its engineering exit gate: Partition does not yet freeze
  one explicit exchange-calendar identity, and Experiment persistence does not
  yet close a complete ordered multi-Partition binding roster. Those are
  correctness blockers, not deferred cutover work.

The current all-day call chain is recovered from code, not documentation:

```text
continuous-research CLI
→ Continuous Schedule Runner
→ Continuous Tick Runner
→ Canonical Free-Data Research Composition
→ Free-Data Operation Service
→ Daily Loop + Controlled Operation
→ Feature + State + Decision Summary + Multi-Strategy + Daily Alpha
→ Shadow / Outcome / Historical consumers
```

This proves substantial real capability and also the duplicated Runtime/
persistence shape that the target removes.

## 2. Target package convergence

| Current package/path | Real retained value | Target location | Disposition after target replacement |
|---|---|---|---|
| `application/continuous_research`, `canonical_lifecycle`, `controlled_operation`, `daily_loop`, `free_data_operation`, `historical_research` | scheduling, recovery, bounded use-case order | `runtime/{domain,application}` and context Application handlers | **MERGE**, then delete parallel journals/compositions |
| `application/state_system` and `research/state_system` | Regime/ETF/Theme/Capital inference and Candidate funnel rules | `decision` Context handlers; approved `selection` Candidate handlers | **SPLIT BY OWNER**, delete generic State System after independent invariant replacement |
| `data`, `data_sources`, `market_data`, source-freeze and historical fact acquisition | Provider capture, normalization, calendar, PIT/source lineage | `market/{domain,application,ports}` plus Provider adapters | **MERGE**, one Market/PIT owner |
| `universe` and Runtime Scope/free Universe operators | Universe policy, membership, Eligibility/orderability | `selection/{domain,application,ports}` | **MERGE**, preserve invariants but do not import the Legacy `universe` Authority |
| `candidates` and candidate discovery | limited arithmetic-midrank/competition-rank invariant clues plus incompatible Model/Target/gate/float/identity-tie paths | permanent `selection` Candidate aggregate consuming real Research Feature Definitions through a Selection-owned port | **REDESIGNED / IMPLEMENTED DRAFT / EXIT GATE PASS / NOT CUT OVER**, one five-table Candidate Authority and one write path; no Legacy import, compatibility path, dual write, or fallback |
| `features` | deterministic technical/context Feature calculations | pure Research Feature kernels; definitions owned by `research_qualification` | **KEEP LOGIC / MOVE**, no artifact writer inside Feature code |
| `signals` | setup assertions | `decision` Signal aggregate | **MOVE**, remove caller DTO duplicates |
| `forecasting` and research-model inference | path estimates and model kernels | Model in `research`; Forecast in `decision` | **SPLIT BY OWNER**, one target-bound write path |
| `strategies` | immutable Strategy semantics and actions | `decision` Strategy/Opportunity handlers | **MERGE**, remove Strategy Shadow duplicate business plane |
| `portfolio` and Portfolio parts of Strategy Shadow | allocation and Risk kernels | `decision` Portfolio/Risk | **MERGE**, simulated ledgers become Evaluation artifacts |
| `execution` and trading-lifecycle application | human Intent, observed Fill, allocation, reconciliation | `execution/{domain,application,ports}` | **MERGE**, one execution command path |
| `position` | Fill projection, T+1, Thesis/holding/exit invariants | Position query in `execution`; Thesis/Strategy in `decision` | **SPLIT BY OWNER**, no mutable Position book |
| Shadow/Prospective settlement, Target labels and Strategy/Path Outcome producers | factual post-Decision observations and Market attribution | `outcome/{domain,application,ports}` | **MERGE**, one revisioned Market Target Outcome per Decision Target Commitment; all label consumers use its read-only port |
| `evaluation/lifecycle.py` plus Fill/Position result readers | realized trade PnL/return/path facts | separate TradeOutcome branch in `outcome/{domain,application,ports}` | **KEEP SEMANTICS / MOVE**, concrete effective Fill/allocation and closed Position-episode subject; never merge with Market Target Outcome |
| Legacy `research`, `evaluation`, research-evaluation/validation/corpus application | Dataset, Target, Partition, Experiment, optional Model, Evaluation, evidence and qualification rules | permanent target `research_qualification/{domain,application,ports}` | **MERGE BY PROVEN OWNER**; Evaluation binds label-free Dataset/Candidate/Partition to exact Outcome revisions through the port; no bars-to-label writer |
| `evidence` | content identity/envelope logic | `research` Evidence types plus `runtime` Artifact metadata | **SPLIT**, no generic evidence payload registry |
| `persistence` and repository factory | PostgreSQL adapters and transactions | `infrastructure/postgres/{repositories,queries,migrations}` | **REWRITE**, remove mega-factory/table CRUD |
| `cli` | operator entry points | `interfaces/cli` | **REWRITE** into one `mra` command tree |
| `core` and `platform` | stable value types plus some mixed infrastructure | minimal `shared`, Runtime, or owning context | **SPLIT**, `shared` cannot become a new grab bag |
| `legacy/**`, `migration/legacy/**` | compatibility interpretation only | none | **DELETE** after invariant replacement; no historical data migration |
| `daily_research/**` and `daily_decision/**` | retained identity/invariant clues, no canonical future writer | mapped Candidate/Decision/Outcome target owners | **DELETE** after cataloged tests are rewritten |
| `dividend_t/**` | legacy calculation/characterization fragments | retained Feature/Strategy invariants only | **DELETE** after independent target coverage |
| old `backtesting`/web/scheduler planes already absent | no current consumer | none | **REMAIN ABSENT** |

## 3. Post-Candidate writer/reader convergence

The WP-08 repository-wide search found every current path that durably or
transiently derives realized return, MFE, MAE, barrier, path, or trade labels.
The [WP-08 design record](../references/WP-ARCHITECTURE-REFOUNDATION-08-Post-Candidate-Authority-Design.md)
retains the call-chain evidence and exact future FK map.

| Current writer/calculator | Current downstream reach | Target owner and deletion condition |
|---|---|---|
| `application/controlled_operation/outcome_evidence.py` | Prospective settlement package and replay | **MERGE** Decision reference/checkpoint/return/MFE/MAE into Market Target Outcome; Artifact retains bytes only; delete writer after exact replay parity |
| `application/controlled_operation/prospective_outcome.py` | Shadow settlement, qualification and Runtime queries | **MERGE** checkpoints/availability/barriers into the same Outcome revision command; delete independent settlement tables/readers after consumer cut |
| `application/research_evaluation/target_semantics.py` and `targeted_outcome.py` | Evaluation panel, calibration, Formal OOS, model training, Shadow economics | **KEEP ONE PURE KERNEL / MOVE** behind Outcome Application, then delete every Research writer/property label path and bars input |
| `application/historical_corpus/historical_target_semantics.py` | Historical materializer, correctness comparison and replay | **CHARACTERIZE**, use as replay parity evidence until the Outcome kernel covers exact semantics; never target Authority |
| `application/historical_corpus/decision_materializer.py` | Historical labels, Forecast samples, strategy economics/performance and evidence | **SPLIT** adapter registration/commitment from Outcome settlement; consumers move to the Outcome port; delete local label/forecast-sample path |
| `application/historical_corpus/alpha_correctness.py` and `phase_ii_service.py` | independent Target reconstruction, correctness/failure evidence and execution-proxy diagnostics | **MERGE REPLAY / SPLIT DIAGNOSTICS**; exact source-bar recomputation becomes Outcome replay, while execution proxies become Evaluation diagnostics and never Fill proof |
| `application/historical_corpus/alpha_diagnostics.py` and `external_validation.py` | Target/gross-return diagnostics and external-validation evidence | **DELETE TARGET-RETURN TRUTH**; Evaluation combines exact Outcome with a declared hypothetical-execution proxy |
| `application/research_validation/free_historical_samples.py` | Historical samples, Forecast and qualification | **DELETE AFTER ADMISSION** of exact archived facts through Outcome; no local return/MFE/MAE/barrier calculation remains |
| `candidates/rehearsal_targets.py` and `candidates/rehearsal_opportunity_targets.py` | direct next-session close return plus rehearsal Opportunity Target artifacts | **PRESERVE TARGET IDENTITY / DELETE VALUES**; read exact Outcome revisions |
| `research/tencent_composite_materialization.py` | PRR composite materialization and artifacts | **PRESERVE TARGET IDENTITY / DELETE VALUES**; read exact Outcome revisions |
| `research/mr1_morning_pop.py` | MR1 research results | **PRESERVE MR1 TARGET CONTRACT / DELETE VALUES**; read exact Outcome revisions |
| `daily_decision/outcome.py` | daily MR1 Outcome Artifact | **MERGE** into named Target resolver/Outcome command, then delete Artifact-as-label Authority |
| `strategies/entry/materialization.py` | future-bar/suspension barrier-first, timeout, missing and ambiguous Entry path observations | **PRESERVE ENTRY RULE / DELETE LABEL AUTHORITY**; exact Target barrier facts arrive through Outcome/Evaluation |
| `strategies/path_outcomes.py` | `strategies/feedback.py`, strategy feedback and `strategy_path_outcome` | **DELETE LABEL AUTHORITY**; Evaluation consumes Market Target Outcome; strategy comparison is diagnostic Attribution |
| `research/mr1_candidate_baselines.py` | exploratory trade/forward return reports | **REPLACE OR DELETE** under declared Evaluation over Outcome; preserve result ceiling/history only |
| `research/prr_mvp_1.py` | exploratory PRR forward returns | **REPLACE OR DELETE** under declared Evaluation over Outcome; preserve result ceiling/history only |
| `research/pit_replication_success_v2.py` | PIT replication portfolio-return report | **REPLACE** with declared Evaluation metrics over exact Outcome observations |
| `dividend_t/memory.py` | future-close setup-memory labels | **DELETE FUTURE-LABEL PATH**; retain only separately characterized pre-Decision Feature semantics, if any |
| `application/strategy_shadow/contracts.py` and `strategy_shadow/economics.py` | synthetic Fill/Position/exit returns, caller MFE/MAE and scorecards | **MOVE TO EVALUATION/ATTRIBUTION** over Outcome; synthetic fills never qualify for TradeOutcome |
| `evaluation/lifecycle.py` | rolling trade scorecards | **MOVE TO TRADEOUTCOME**; retain concrete effective Fill roster, zero-to-zero closed Position episode, fees/costs and trade-path evidence; Fill Allocation belongs only to sleeve attribution; prohibit Market Target subject |

The two currently active settlement compositions are:

```text
continuous-research CLI
→ ContinuousOutcomeSettlementService
→ FreeDataSettlementOperator.settle_day
→ BaoStock 5m capture + outcome Artifact
→ ResearchShadowOperations.settle
→ prospective_outcome_settlement + targeted_shadow_outcome(_label)
→ Research Evaluation panel/enrichment → Path calibration

HistoricalDecisionMaterializer._outcome_stage
→ historical normalized-bar windows
→ historical_target_semantics / targeted_outcome
→ historical_corpus_outcome_label
→ PathForecastSample / strategy economics / performance
→ historical_research_evidence / qualification
```

Their persistence and reader disposition is complete by family:

| Current SQL/Artifact family | Current consumers | Target disposition |
|---|---|---|
| `prospective_outcome_settlement`, `outcome_target_protocol`, `outcome_target_definition`, `targeted_shadow_outcome`, `targeted_shadow_outcome_label` | settlement, Runtime query, Shadow, qualification | **MERGE** Target identity and revisioned Market Target Outcome; no dual write/read |
| `research_evaluation_dataset`, `research_evaluation_dataset_settlement`, `research_evaluation_panel_v2*`, `historical_path_sample_record` | Evaluation, training, calibration, reports | **SPLIT** label-free Dataset from Evaluation observation; latter binds exact Outcome revision |
| `calibration_partition_binding`, `locked_oos_evidence_consumption`, `locked_oos_raw_evidence_unlock`, `locked_oos_target_observation_consumption`, `frozen_locked_oos_scope` | Calibration/Formal OOS admission | **MERGE** immutable Research Partition/member roster and ordinal Outcome access; delete mutable unlock state |
| `historical_corpus_partition`, `historical_corpus_outcome_label`, `historical_corpus_outcome_forecast_index` | Historical materializer/replay/Forecast | **SPLIT** physical corpus partition from Research Partition; Outcome owns label and Evaluation owns observation; forecast index becomes replaceable query |
| `research_model_training_*`, `research_model_artifact`, `research_model_inference_*`, `model_registrations` and governance tables | training/inference/selection | **MERGE AFTER EVALUATION** into optional Model/ModelVersion; ModelVersion requires training Evaluation and Artifact; no other aggregate requires Model |
| `formal_evaluation_observation_*`, `formal_oos_qualification_decision`, calibration qualification and historical sample qualification | formal metrics and admission | **MERGE** into Evaluation plus subject-specific qualification; raw labels enter only through Outcome port |
| `research_validation_artifact`, `historical_research_evidence*` | evidence/replay/qualification | **SPLIT** Artifact bytes from concrete Evaluation-bound Evidence/Assessment/Research Qualification FK chain; delete generic payload/weak subject references |
| `strategy_path_outcome`, `strategy_realized_outcome` | strategy feedback/economics | **SPLIT** Market Evaluation from Fill-derived TradeOutcome; no polymorphic Outcome table |

`postgres_research_model.py`, `postgres_qualification.py`,
`postgres_calibration_qualification.py`, `path_calibration.py`,
`strategy_shadow/postgres_observations.py`, `strategy_shadow/economics.py`,
`formal_evaluation.py`, `ablation.py`, historical materialization/evidence/
performance, `forecasting/path.py`, `forecasting/conditional.py`,
`holding_exit_validation.py`, `strategies/feedback.py`, historical
multi-strategy, and Runtime query code are direct or caller-built label
consumers. `application/research_evaluation/targets.py`, `target_semantics.py`,
and `platform/target_evaluation.py` are definition/DTO sources whose useful
non-calculation vocabulary moves to TargetDefinition/Checkpoint/Metric without
writer authority. Each consumer must lose bars/path or caller-label construction and
accept exact Outcome DTOs before its old writer, reader, table, or Artifact
binding is deleted. Existing replay that merely reloads stored JSON/payload is
replaced by exact source-FK/cutoff recomputation with `matched=true` and zero
mismatches.

Current/past-return arithmetic in Feature code remains Decision input rather
than Outcome. Open-Position mark-to-cost in `position/assessment.py` and
`strategies/runtime.py` remains a Fill-derived query for later decisions, not a
Market label or closed TradeOutcome. Strategy Shadow synthetic fills/results
are Evaluation inputs, never observed Fill evidence. These exclusions do not
permit any of those paths to publish Evaluation labels.

## 4. Legacy deletion contract

Hard Cutover has no permanent compatibility phase:

1. characterize valuable behavior as a Domain invariant;
2. implement and pass the target invariant test;
3. compare target behavior where comparison is meaningful;
4. redirect the final real consumer and composition root;
5. delete the old writer, reader, adapter, table, fixture, and import in the same
   dependency-coherent checkpoint;
6. prove architecture imports and installed CLIs cannot reach it.

No `legacy_read_enabled` flag, schema fallback, dual write, runtime dispatch by
v1/v2/v3, or “prefer target else legacy” path is permitted. Because business
data is not migrated, byte-stable legacy readers whose only purpose is old row/
artifact compatibility are deleted. Git history preserves archaeology; it is not
a runtime dependency.

The correctness rules that survive are frozen in the
[Domain Invariant Catalog](../references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md).

## 5. PostgreSQL convergence result

The complete ledger classifies every current table:

| Disposition | Count | Meaning |
|---|---:|---|
| KEEP | 1 | migration checksum responsibility retained in the new epoch |
| MERGE | 262 | semantics re-homed under a canonical aggregate/table/evidence edge |
| DERIVE | 14 | replaceable current/transition/index/summary query |
| DELETE | 6 | pseudo-RBAC roots, guard rows, or compatibility replay import |
| **Total** | **283** | complete current catalog |
| **Target** | **see sole logical catalog** | semantic destination in Data and Evidence Architecture; mutable target counts stay in exact checkpoint records and are not quotas or cutover claims |

The detailed writer/reader/owner/reason record is the
[283-table Disposition](../references/WP-ARCHITECTURE-REFOUNDATION-01-Table-Disposition.md).
Current rows are not migrated.

## 6. Documentation governance

Documents are classified by what they may authoritatively say, not by how many
historical claims they contain.

| Current/target asset | Target disposition | Authority after cutover |
|---|---|---|
| `README.md` | **REWRITE** | product boundary, install/bootstrap, five-minute start path |
| `AGENTS.md` | **REWRITE/KEEP ONE** | sole repository execution/safety/evidence contract |
| `CLAUDE.md` | **REWRITE MINIMAL** | imports `AGENTS.md` and adds only tool-specific startup |
| `docs/README.md` | **REWRITE/KEEP** | documentation navigation and precedence |
| Context Map + five current architecture documents | **KEEP/CONSOLIDATE** | target architecture; never implementation/evidence status |
| ADR-014 | **KEEP HISTORICAL** | provenance for the implemented pre-refoundation correctness repair; valid temporal rules are restated in the Target architecture |
| ADR-015 | **KEEP** | durable Hard Cutover and schema epoch decision |
| ADR-008 through ADR-013 | **ARCHIVE FROM DEFAULT TREE** after implementation | historical rationale only; cannot constrain target compatibility |
| `docs/status/Current-State.md` | **GENERATE/REWRITE** | non-authoritative read model with generated time, SHA, schema epoch, source queries/tests |
| Capability Matrix/status view | **GENERATE**, not manually promote | non-authoritative read model from code/schema/test/evidence queries |
| Gap Register and Roadmap | **MERGE** into one short dependency plan | planning only, never business/qualification Authority |
| Runbook | **REWRITE** for the target CLI, epoch, recovery, artifact/reconciliation procedures | operational procedure, not state |
| frozen research protocols/results | **KEEP only when bound to immutable Evidence** | evidence provenance with stated ceiling |
| delivery reports, temporary plans, superseded status, duplicate architecture | **DELETE from default tree** | Git history only |
| this Capability/Table/Invariant checkpoint annex set | **KEEP through implementation review, then archive/reference** | design traceability, never live state |
| Evidence Ledger or manually edited Current State | **GENERATED VIEW ONLY** | cannot write or promote canonical data |

Every generated document/report must display `generated_at`, code SHA, schema
epoch, query/tool version, source IDs/hashes, and proof ceiling. A generator reads
canonical data; it has no write credentials.

## 7. Skill and prompt governance

The approved-design audit found three Skills and three persistent reviewer
prompts. The required repository dispositions are:

| Asset | Current responsibility | Target disposition | Reason |
|---|---|---|---|
| `.claude/skills/implement-work-package/SKILL.md` | generic read-plan-code-test-commit loop | **DELETE** | duplicates `AGENTS.md` and ordinary engineering; no stable domain-specific interface |
| `.claude/skills/verify-repository/SKILL.md` | runs repository quality commands | **DELETE** | a Make/task/CI target plus `AGENTS.md` should own executable gates |
| `.claude/skills/reconcile-branches/SKILL.md` | squash/rebase-aware branch reconciliation | **KEEP/REWRITE** | distinct, reusable, high-risk workflow; require explicit user authorization, read-only audit by default, stable report schema, no automatic fetch/merge/delete |
| `.claude/agents/platform-kernel-reviewer.md` | platform/identity/database review checklist | **DELETE** | overlaps architecture documents, tests, and general review instructions |
| `.claude/agents/research-evidence-reviewer.md` | PIT/evidence research review checklist | **DELETE** | durable rules move to architecture plus invariant tests; no persistent prompt fork |
| `.claude/agents/repository-verifier.md` | diff/test/docs verification | **DELETE** | duplicates validation command and `AGENTS.md` |
| `.claude/README.md` asset inventory | documents the above prompts | **DELETE** after convergence | redundant hierarchy once one Skill remains |

Target Skill contract for `reconcile-branches`:

- trigger: explicit branch-integration/reconciliation request only;
- input: repository, comparison ref, named branch scope, authorization level;
- output: stable read-only classification table and proposed actions;
- side effects: none unless separately authorized;
- failure: unknown PR/auth state remains unknown;
- tests: fixture repositories covering merge, squash, rebase, supersession, and
  unique content through `scripts/reconcile_branches.py`;
- no architecture/business/evidence instructions duplicated from `AGENTS.md`.

No versioned Skill forks, prompt packs, generic implementation Skill, test wrapper
Skill, per-domain reviewer prompt, or hidden agent instruction tree remains.

## 8. Composition/entry-point deletion gate

The target is complete only when:

- one `bootstrap.py` is the sole concrete composition root;
- one `mra` CLI command tree is installed;
- only the target Runtime schedules work;
- no current Repository Factory or legacy package is importable from target
  contexts;
- no SQL exists outside PostgreSQL adapters;
- architecture tests reject every deleted direction;
- `rg`/import graph/entry-point inspection shows zero old writer consumers;
- the old 106 migrations and 283-table schema do not appear in the target epoch;
- the worktree is clean after reviewable commits.

## 9. Governance checkpoint acceptance boundary

A conforming governance checkpoint must apply the instruction, status, Skill,
and persistent-prompt dispositions while leaving business source, 001–106
migrations, fixtures, Runtime behavior, and business test semantics unchanged.
Completion is reported by an exact-SHA Current State or checkpoint record, never
by this Target document.
