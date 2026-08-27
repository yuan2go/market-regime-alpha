# Repository Convergence Inventory

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Target package, Legacy, documentation, prompt, and Skill disposition
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-27
> **Implementation State:** DESIGN_CHECKPOINT_ONLY
> **Code Evidence:** `src/market_regime_alpha`, `pyproject.toml`, `tests/architecture`, `.claude/skills/*/SKILL.md`, `.claude/agents/*.md`

This inventory freezes what the implementation phase will converge and delete.
No source, Skill, prompt, migration, or test file is removed in this design-only
checkpoint.

## 1. Current structural facts

At starting SHA `0382dad416d6d50d1eea0bda1603d7c359d65274`:

- 673 Python modules and approximately 298,278 source lines;
- 499 test files and approximately 115,589 test lines;
- 1,201 dataclasses, 415 enums, and 15 static import cycles;
- six installed CLIs with approximately 140 subcommands;
- importing CLI help loads roughly 500 project modules;
- 67 modules write artifacts and 57 modules control transactions;
- 106 PostgreSQL migrations and 283 expected tables;
- nested Continuous, Controlled Operation, Canonical Lifecycle, State,
  Decision, Historical, Research Shadow, and Strategy Shadow journals/owners;
- repository-wide factories and compatibility paths still participate in
  composition and replay.

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
| `application/state_system` and `research/state_system` | Regime/ETF/Theme/Capital inference and Candidate funnel rules | `decision` Context handlers; `universe` Candidate handlers | **SPLIT BY OWNER**, delete generic State System |
| `data`, `data_sources`, `market_data`, source-freeze and historical fact acquisition | Provider capture, normalization, calendar, PIT/source lineage | `market/{domain,application,ports}` plus Provider adapters | **MERGE**, one Market/PIT owner |
| `universe` and Runtime Scope/free Universe operators | Universe policy, membership, Eligibility/orderability | `universe/{domain,application,ports}` | **MERGE**, preserve three-state evidence |
| `candidates` and candidate discovery | ranking, tie/missingness/score logic | `universe` Candidate aggregate and pure research Feature definitions | **MERGE**, one Candidate write path |
| `features` | deterministic technical/context Feature calculations | pure Research Feature kernels; definitions owned by `research` | **KEEP LOGIC / MOVE**, no artifact writer inside Feature code |
| `signals` | setup assertions | `decision` Signal aggregate | **MOVE**, remove caller DTO duplicates |
| `forecasting` and research-model inference | path estimates and model kernels | Model in `research`; Forecast in `decision` | **SPLIT BY OWNER**, one target-bound write path |
| `strategies` | immutable Strategy semantics and actions | `decision` Strategy/Opportunity handlers | **MERGE**, remove Strategy Shadow duplicate business plane |
| `portfolio` and Portfolio parts of Strategy Shadow | allocation and Risk kernels | `decision` Portfolio/Risk | **MERGE**, simulated ledgers become Evaluation artifacts |
| `execution` and trading-lifecycle application | human Intent, observed Fill, allocation, reconciliation | `execution/{domain,application,ports}` | **MERGE**, one execution command path |
| `position` | Fill projection, T+1, Thesis/holding/exit invariants | Position query in `execution`; Thesis/Strategy in `decision` | **SPLIT BY OWNER**, no mutable Position book |
| Shadow/Prospective settlement, Target labels and Strategy/Path Outcome producers | factual post-Decision observations, metrics and attribution | `outcome/{domain,application,ports}` | **MERGE**, one factual Outcome/Attribution owner |
| `research`, `evaluation`, research-evaluation/validation/corpus application | Dataset, Target, Experiment, Evaluation, evidence and qualification rules | `research/{domain,application,ports}` | **MERGE**, one evidence/qualification model; reads Outcome through a port |
| `evidence` | content identity/envelope logic | `research` Evidence types plus `runtime` Artifact metadata | **SPLIT**, no generic evidence payload registry |
| `persistence` and repository factory | PostgreSQL adapters and transactions | `infrastructure/postgres/{repositories,queries,migrations}` | **REWRITE**, remove mega-factory/table CRUD |
| `cli` | operator entry points | `interfaces/cli` | **REWRITE** into one `mra` command tree |
| `core` and `platform` | stable value types plus some mixed infrastructure | minimal `shared`, Runtime, or owning context | **SPLIT**, `shared` cannot become a new grab bag |
| `legacy/**`, `migration/legacy/**` | compatibility interpretation only | none | **DELETE** after invariant replacement; no historical data migration |
| `daily_research/**` and `daily_decision/**` | retained identity/invariant clues, no canonical future writer | mapped Candidate/Decision/Outcome target owners | **DELETE** after cataloged tests are rewritten |
| `dividend_t/**` | legacy calculation/characterization fragments | retained Feature/Strategy invariants only | **DELETE** after independent target coverage |
| old `backtesting`/web/scheduler planes already absent | no current consumer | none | **REMAIN ABSENT** |

## 3. Legacy deletion contract

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

## 4. PostgreSQL convergence result

The complete ledger classifies every current table:

| Disposition | Count | Meaning |
|---|---:|---|
| KEEP | 1 | migration checksum responsibility retained in the new epoch |
| MERGE | 262 | semantics re-homed under a canonical aggregate/table/evidence edge |
| DERIVE | 14 | replaceable current/transition/index/summary query |
| DELETE | 6 | pseudo-RBAC roots, guard rows, or compatibility replay import |
| **Total** | **283** | complete current catalog |
| **Target** | **91** | semantic target catalog; not a quota |

The detailed writer/reader/owner/reason record is the
[283-table Disposition](../references/WP-ARCHITECTURE-REFOUNDATION-01-Table-Disposition.md).
Current rows are not migrated.

## 5. Documentation governance

Documents are classified by what they may authoritatively say, not by how many
historical claims they contain.

| Current/target asset | Target disposition | Authority after cutover |
|---|---|---|
| `README.md` | **REWRITE** | product boundary, install/bootstrap, five-minute start path |
| `AGENTS.md` | **REWRITE/KEEP ONE** | sole repository execution/safety/evidence contract |
| `CLAUDE.md` | **REWRITE MINIMAL** | imports `AGENTS.md` and adds only tool-specific startup |
| `docs/README.md` | **REWRITE/KEEP** | documentation navigation and precedence |
| Context Map + five current architecture documents | **KEEP/CONSOLIDATE** | target architecture; never implementation/evidence status |
| ADR-014 and ADR-015 | **KEEP** | durable Target temporal semantics and Hard Cutover decision |
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

## 6. Skill and prompt governance

Current repository audit found three Skills and three persistent reviewer
prompts.

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
  unique content;
- no architecture/business/evidence instructions duplicated from `AGENTS.md`.

No versioned Skill forks, prompt packs, generic implementation Skill, test wrapper
Skill, per-domain reviewer prompt, or hidden agent instruction tree remains.

## 7. Composition/entry-point deletion gate

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

## 8. Design checkpoint stop

This document only records the target. Business source, migrations, tests,
fixtures, Skills, prompts, and operational instructions remain unchanged until a
later implementation authorization.
