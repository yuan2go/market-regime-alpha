# AGENTS.md — Market Regime Alpha Execution Contract

> **Status:** CURRENT_STATUS
> **Authority:** Sole repository execution, safety, and evidence contract
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-05
> **Related Documents:** `CLAUDE.md`, `docs/README.md`, `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Roadmap.md`

## Mission and current program

Market Regime Alpha is an A-share research operating system and human-in-the-loop
decision-support platform. It is not unattended live trading.

The approved Hard Cutover Architecture Re-foundation is the sole engineering
program. The target is frozen by
`docs/architecture/Canonical-Overall-Design.md` and ADR-015. The current source,
106 migrations, 283-table PostgreSQL schema, and existing Runtime remain the
implementation truth until an explicit Runtime/CLI cutover checkpoint succeeds.
Target prose never makes an unimplemented capability current.

The active checkpoint is WP-18Q Qualification Closure, under its approved
Design and Implementation Plan. Freeze the existing Generic Backtest / Model /
Evaluation / Report / Prospective architecture; correct only correctness,
qualification and hard-cut blockers. WP-17P remains historical engineering
proof, not the current implementation or qualification state. Current exact-SHA
facts and catalog counts live in `docs/status/Current-State.md`; dependency
order and re-entry conditions live only in `docs/status/Roadmap.md`.

A real generic campaign, deterministic reports, exact resume/replay, historical
zero-write compatibility, a real due prospective Runtime Attempt and full
engineering regression are mandatory before WP-18Q PASS. Missing operational
state, missing canonical archive lineage or an unavailable real window blocks
the corresponding gate. Never backdate or wait for a future window to manufacture
proof. Keep WP-specific executors until every hard-cut prerequisite passes.

WP-15's Provider rejection and WP-16's external-evidence blocker remain closed.
Retrospective work is EXPLORATORY_RETROSPECTIVE only. Model Qualification,
Calibration, broker integration, Runtime/CLI full cutover, Legacy deletion and
Production admission remain unstarted or unauthorized.

Do not resume the former Alpha Proof Roadmap as an engineering program. Existing
protocols, results, and negative evidence remain immutable provenance. New
research execution requires a separately approved request and must not interrupt
the active re-foundation dependency chain.

## Agent entry points

Read in this order:

1. `AGENTS.md`;
2. `docs/README.md`;
3. the Canonical Overall Design and supporting target architecture documents;
4. `docs/status/Current-State.md`, `docs/status/Capability-Matrix.md`, and
   `docs/status/Roadmap.md`;
5. current code, migrations, tests, and reproducible evidence for the affected
   context.

`CLAUDE.md` may add only Claude-specific startup behavior. Do not create a
parallel instruction, prompt, status, roadmap, or architecture hierarchy.

## Normative authority order

1. latest explicit user decision not superseded;
2. `docs/architecture/Canonical-Overall-Design.md` and accepted ADR-015;
3. supporting target architecture documents linked from `docs/README.md`;
4. the dependency plan in `docs/status/Roadmap.md`;
5. historical ADRs, frozen protocols, and evidence reports as provenance only;
6. Git history for historical context only.

## Implementation fact authority order

1. current checked-out code and actual call chains;
2. current PostgreSQL schema, migrations, writers, and readers;
3. tests and static checks actually executed at an exact SHA;
4. reproducible Runtime, replay, and research evidence;
5. generated or exact-SHA status read models.

Current State, Capability views, Roadmap, reports, Evidence Ledgers, artifacts,
DTOs, policies, receipts, and documentation are not business or qualification
Authority. They may summarize canonical facts but cannot mutate or promote them.

## Re-foundation execution rules

- Work on one dependency-coherent checkpoint from `docs/status/Roadmap.md`.
- Do not implement a later context before its declared predecessor exit gate.
- An incomplete target path has no current business cutover authority. Do not dual-write,
  fall back between old and target owners, or choose Authority by availability.
- The existing Runtime stays canonical until the explicit Runtime/CLI Cutover.
- The target baseline bootstraps a newly provisioned empty database. Ordinary
  startup must fail before DDL on legacy, unknown, or mismatched schema epoch.
- Never edit released migration bytes or carry the Legacy catalog into the
  target epoch. Existing target-draft operational evidence may use only the
  exact approved additive upgrade route after OID/checksum, readable backup,
  disk and active-attempt preflight; never recreate operational evidence.
- Legacy code/tests are deleted only after every mapped invariant has passing
  target coverage and the last executable consumer is absent.
- No permanent `v1`/`v2`/`v3`, compatibility reader, registry, snapshot, journal,
  or parallel composition root may survive cutover.
- Do not introduce microservices, a message broker, event sourcing, generic
  workflow/registry frameworks, dashboards, or infrastructure expansion unless
  a later explicit scope changes the approved architecture.

## Domain and evidence invariants

- Market fact, inferred Context, Universe membership, Eligibility, Candidate,
  Signal, Forecast, Opportunity, Thesis, Portfolio, Risk, Fill, Position,
  Outcome, Attribution, Assessment, and Qualification remain distinct.
- Universe → Eligibility → Dataset → Candidate → `OPEN_DECISION_RUN`
  completes before same-run Context. Context cannot feed back into that same
  Candidate Set or Target commitment. Candidate consumes the immutable
  Decision-input Dataset and Feature Definition identities through a
  Selection-owned port; Candidate Set existence never depends on a Decision Run,
  Model Version, Target, Outcome, Evidence, Assessment, or Qualification.
- `OPEN_DECISION_RUN` must freeze the explicit requested Target roster, the
  complete Candidate × Target commitment roster, and independent Decision
  references before Outcome visibility. It creates no Outcome placeholder.
- Market Target Outcome is the only market-label Authority. Research, Model,
  Evaluation, Calibration, Forecast evaluation, Shadow economics, and
  Qualification may consume realized facts only through its narrow read-only
  port; they do not reread bars or construct a second label truth.
- Market Target Outcome and effective-Fill/closed-Position-derived TradeOutcome
  are different concrete subjects. No generic Outcome or Qualification subject
  registry is permitted.
- Feedback crosses generations only:
  `Outcome(n) → Evaluation(n) → Qualification(n) → DecisionRun(n+1)`.
  The later Run uses a concrete
  `decision_run_research_qualification_roster` plus member FK binding whose
  source is known by the new DecisionTime and whose Outcome generations are
  strictly earlier; prose or a current/latest lookup is not a binding.
  Model is an optional post-training branch, never a prerequisite for Candidate,
  Target, Outcome, ordinary Evaluation, Evidence, or Research Qualification.
- Opportunity contains decision input evidence, not a Risk authorization. The
  sole Risk Decision follows a complete Portfolio Proposal.
- Target horizon is not a holding or exit time; Exit is not inverse Entry.
- Empty, `UNKNOWN`, `WAIT`, `DATA_INSUFFICIENT`, `NO_ACTION`,
  `NOT_ESTIMABLE`, rejection, and inconclusive evidence are valid results.
- Scores are not probabilities without exact calibration evidence.
- No silent Provider substitution or invented PIT/finality/availability/
  adjustment semantics is permitted.
- Trade-caused Position changes derive only from observed effective Fills.
  Opening balances, corporate actions, and reconciliation adjustments use the
  separately authorized typed basis-event rules in the Authority Map.
- Risk rejection cannot be bypassed by Strategy code or ordinary operator retry.
- Evidence classes, Assessment status, and purpose-scoped Qualification floors
  cannot be collapsed into one maturity flag.
- Fixture/local/CI evidence never proves Provider quality, Formal PIT/OOS Alpha,
  Prospective value, broker authority, trading authority, or Production.

## Provider and trading boundary

Provider adapters remain unqualified until exact source/archive/version,
availability, finality, adjustment, identity, and lineage evidence satisfies the
declared purpose. Public-source availability gaps remain `UNKNOWN` or
Exploratory rather than guessed.

Agents may diagnose and implement an approved checkpoint. They do not place
orders, invoke a broker mutation, promote a model, change approved Risk, unlock
Production, or reinterpret a passing Runtime as trading authority.

## Workspace, branch, and commit discipline

- Inspect the workspace, exact HEAD, ancestry, worktrees, and diffs before Git
  mutation. Preserve unrelated user changes and local configuration.
- Never implement directly on `main`; use an isolated branch/worktree.
- Do not fetch, pull, switch, reset, clean, stash, force-push, rewrite history,
  delete branches, merge, or open a PR unless explicitly authorized.
- Use dependency-coherent checkpoint commits. Before every commit, inspect all
  staged/unstaged/untracked scope and run `git diff --check`.
- Exclude credentials, generated secrets, personal paths, build output, and
  unrelated files.
- Never modify, stage, overwrite, stash, or commit `.idea/modules.xml`.

## Validation and reporting

Repository gate:

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
uv run python -m pytest -q tests/scripts/test_check_docs_links.py
uv run python -m pytest -q tests/platform
uv run python -m pytest -q
uv run python -m ruff check .
uv run python -m mypy
uv run python -m build
git diff --check
```

`uv sync` does not activate the project environment in the current shell. Keep
every Python-based gate behind `uv run` so its interpreter and tools resolve
from the locked project environment.

Use a dedicated PostgreSQL test database and run the focused migration,
bootstrap, constraint, repository, concurrency, idempotency, replay, recovery,
and architecture tests required by the checkpoint. Never weaken an assertion,
skip/xfail a failure, or add a compatibility path merely to make a gate green.

Report every command as `PASS`, `FAIL`, `BLOCKED`, or `NOT_RUN`, including the
exact SHA, prerequisites, and failure cause. Keep these evidence levels separate:

```text
CODE_IMPLEMENTED
CANONICAL_WIRED
TEST_EXECUTED
RUNTIME_PROVEN
RESEARCH_QUALIFIED
PRODUCTION_QUALIFIED
```

## Repository-local Skill boundary

The only retained project Skill is `.claude/skills/reconcile-branches/SKILL.md`.
It is invoked only for an explicit branch-reconciliation request and is
read-only unless the user separately authorizes side effects. Ordinary coding,
verification, architecture review, and research-evidence rules live here, in
code/tests, or in the target architecture—not in persistent prompt forks.
