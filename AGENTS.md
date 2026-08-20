# AGENTS.md — Market Regime Alpha Execution Contract

> **Status:** CURRENT_STATUS
> **Authority:** Repository execution contract for coding and research agents
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-19
> **Related Documents:** `CLAUDE.md`, `docs/README.md`, `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Roadmap.md`

## Mission and product boundary

Market Regime Alpha is a Reliable A-share Alpha Research Operating System and human-in-the-loop trading decision-support platform. It is not unattended live trading.

The current engineering platform is multi-strategy capable, but the forward program is **Alpha Proof / evidence-driven research engineering**. Candidate, Signal, Forecast, Strategy, Portfolio, Decision, Execution, Position and Outcome remain distinct only where they have distinct semantics and consumers. A recommendation or target position cannot create an actual position; physical positions derive from observed effective fills.

## Agent entry points

Read `AGENTS.md`, then `docs/README.md`, the Canonical Overall Design, supporting architecture documents, Current State, Gap Register and Roadmap. `CLAUDE.md` adds only Claude-specific workflow. Do not create a parallel instruction or documentation hierarchy.

## Normative authority order

1. latest explicit user decision not superseded;
2. `docs/architecture/Canonical-Overall-Design.md`;
3. supporting current architecture documents linked from `docs/README.md`;
4. Current State, Gap Register and Roadmap;
5. accepted ADRs/evidence reports as subordinate provenance;
6. Git history for historical context only.

## Implementation fact authority order

1. current checked-out code and actual call chains;
2. current PostgreSQL schema and migrations;
3. current tests and static checks actually executed;
4. reproducible runtime/research artifacts;
5. `docs/status/Current-State.md` and Capability Matrix.

Never use prose to overrule executable evidence. Never recreate the superseded Constitution or another normative hierarchy. A change to the Canonical Overall Design must keep supporting current documents and real implementation/evidence status explicit.

## Current architecture boundary

- `CONTINUOUS_RESEARCH` is the sole all-day Runtime.
- PostgreSQL 16 is the only persistent Runtime, Journal, Repository, Replay, account, Position and Risk database; unavailability fails closed.
- Historical Research is a bounded runner that reuses canonical business/strategy semantics; it is not a second daily Runtime.
- Canonical Lifecycle, State System, Controlled Operation and Decision System are bounded children/tools, not competing daily runtimes.
- Model Governance owns model lifecycle/selection. Strategy Registry/Runtime owns Strategy Version semantics. Neither creates Alpha by existence.
- Research Validation and Strategy Shadow produce evidence only at the level their real inputs/protocols justify.
- Production Admission remains independently evidence-gated; broker execution is Future/Deferred.
- `daily_research`, `dividend_t`, `legacy/**` and `migration/legacy/**` have no Canonical write or execute authority.

## Non-negotiable domain and evidence rules

- Facts, derived indicators, inferred state, prediction, decision, execution facts, outcomes and qualification evidence are distinct.
- Target horizon is not automatically holding or exit time; Exit is not inverse Entry.
- Empty results, `WAIT`, `DATA_INSUFFICIENT`, `NO_ACTION` and `NOT_ESTIMABLE` are valid; `NO_ACTION != HOLD`.
- A score is not a probability without calibration.
- Public Capital proxies do not identify hidden institutional intent and must remain labelled proxies/derived evidence.
- Data Authority cannot inflate; no silent Provider substitution or invented PIT/finality/availability/adjustment semantics.
- Candidate does not automatically mean Entry. Forecast does not automatically mean trade action.
- Risk rejection cannot be bypassed by strategy code or ordinary operator action.
- References, DTOs, projections, protocols, policies and receipts are not Authority.
- Preserve negative, inconclusive and not-estimable research results; do not tune implementation parameters simply to make evidence positive.
- Historical artifacts and identities are immutable unless an explicit migration/supersession contract exists.
- Existing compatibility identities retain their historical meaning until explicitly retired with consumer/replay proof.

## Alpha Proof program

The forward organizing loop is:

```text
Golden Strategy Question
→ transparent quantitative baseline
→ factor/context ablation
→ Strategy / Portfolio economics
→ prospective Shadow
→ Outcome / Attribution
→ diagnosis
→ next evidence-driven change
```

Prefer the highest-information P0/P1 Work Package in `docs/status/Roadmap.md`. Build platform capability only when the loop exposes a real blocker. Treat Architecture Compression as active work: unused or duplicate abstractions should be simplified/merged/retired when consumer inventory and replay safety permit it.

Do not jump directly to complex ML before the baseline and incremental-value evidence exist.

## Provider and trading rules

Tencent, BaoStock, Tushare, AKShare and similar public sources remain auxiliary/exploratory unless formally qualified by the owning evidence policy. A runnable adapter is not Formal evidence. Any future qualified Provider direction remains subject to actual source/archive/version/availability evidence.

Agents may diagnose, implement approved scope and propose experiments/model changes. They do not auto-promote models, mutate approved risk, place broker orders or unlock Production/Broker authority.

## Workspace, branch and commit discipline

- Inspect current workspace before Git mutation; preserve unrelated user changes/local configuration.
- Never implement directly on `main`; use an isolated branch/worktree.
- Do not reset, clean, stash, force-push, rewrite history or delete branches unless explicitly authorized.
- Do not merge automatically.
- Before commit, run `git diff --check`, inspect scope and exclude credentials, generated secrets, personal paths and unrelated files.
- Never modify, stage, overwrite, stash or commit `.idea/modules.xml`.

## Engineering discipline

For broad work, continue across the dependency-coherent scope needed to complete one Work Package; do not stop after a ceremonial DTO/class/test. Core capability must enter the real canonical runtime/owner/consumer chain where applicable.

Use production-grade best practices but not maximum complexity. New Authority, Receipt, Evidence, Policy, Repository wrapper, Workflow, Qualification type or compatibility layer requires a concrete unresolved failure mode and real consumer.

Do not introduce broker integration, microservices, infrastructure expansion, complex Portfolio optimization or autonomous-agent trading unless explicitly scoped by current evidence and target architecture.

Stop only for a genuine external blocker that cannot be bypassed safely. A future market window or unavailable Formal Provider evidence blocks only that proof; it does not block engineering/research work that can be completed honestly now.

## Validation

```bash
uv sync --frozen --extra dev --extra postgres
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
git diff --check
```

Run focused PostgreSQL migration, idempotency, concurrency, replay and compatibility tests for affected owners. Report each command as `PASS`, `FAIL`, `NOT_RUN` or `BLOCKED`.

Strictly distinguish:

```text
CODE_IMPLEMENTED
CANONICAL_WIRED
TEST_EXECUTED
RUNTIME_PROVEN
RESEARCH_QUALIFIED
PRODUCTION_QUALIFIED
```

Never promote fixture/local/engineering evidence into Provider qualification, Formal PIT/OOS Alpha, calibrated probability, prospective proof, trading authority or Production qualification.