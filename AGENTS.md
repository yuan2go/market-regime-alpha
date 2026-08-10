# AGENTS.md — Market Regime Alpha Execution Contract

> **Status:** CURRENT_STATUS
> **Authority:** Repository execution contract for coding and research agents
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Related Documents:** `CLAUDE.md`, `docs/README.md`, `docs/architecture/Authority-Map.md`, `docs/status/Roadmap.md`

## Mission and product boundary

Market Regime Alpha is an A-share Alpha Research Operating System. The current product is a production-grade human-in-the-loop research and trading decision-support platform, not unattended live trading.

Candidate, Signal, Forecast, Opportunity, Thesis, Portfolio, Risk, Execution, Position, Holding, Exit and Evaluation are distinct. A recommendation or target position cannot create an actual position. Actual positions come only from observed manual or future broker fills.

## Agent entry points

Read `AGENTS.md`, then `docs/README.md`, the four current architecture documents, Current State, Gap Register and Roadmap. `CLAUDE.md` adds only Claude-specific workflow. Do not create a parallel instruction or document hierarchy.

## Normative authority order

1. latest explicit user decision not superseded;
2. `docs/constitution/00` through `09`;
3. current documents linked from `docs/README.md`;
4. current research program and Roadmap;
5. Git history for context only.

## Implementation fact authority order

1. current checked-out code and actual call chains;
2. current PostgreSQL schema and migrations;
3. current tests and static checks;
4. reproducible runtime/research artifacts;
5. `docs/status/Current-State.md` and Capability Matrix.

Never use prose to overrule executable evidence. Never change Constitution without explicit authorization.

## Current architecture boundary

- `CONTINUOUS_RESEARCH` is the sole all-day Runtime.
- PostgreSQL 16 is the only persistent Runtime, Journal, Repository, Replay, account, Position and Risk database; unavailability fails closed.
- Canonical Lifecycle, State System, Controlled Operation and Decision System are bounded children/tools, not competing daily runtimes.
- Model Governance is the sole model qualification/selection owner. Production qualification is currently forced closed because all evidence-floor owners do not exist.
- Research Validation and Strategy Shadow emit engineering evidence only. Production Admission is always blocked.
- `daily_research`, `dividend_t`, `legacy/**` and `migration/legacy/**` have no Canonical write or execute authority.

## Non-negotiable domain and evidence rules

- Target horizon is not an automatic holding or exit time; Exit is not inverse Entry.
- Empty results, `WAIT`, `DATA_INSUFFICIENT` and `NO_ACTION` are valid; `NO_ACTION != HOLD`.
- A score is not a probability without calibration.
- Public capital proxies do not identify hidden institutional intent.
- Data authority cannot inflate; no silent Provider substitution or invented PIT/finality/availability/adjustment semantics.
- Risk rejection cannot be bypassed by strategy code or ordinary operator action.
- References, DTOs, projections, protocols and policies are not Authority. Qualification requires owner reload, hash, time, status, lineage and semantic verification.
- Preserve negative and inconclusive research results; one primary research change per experiment.
- Historical artifacts and identities are immutable unless an explicit migration/supersession contract exists.
- Existing MR1 next-session 10:30 and `daily_research` compatibility identities retain their meaning.

## Provider and trading rules

Xuntou/ThinkTrader/XtQuant remains the formal Provider direction unless later qualified evidence changes it. Tencent, BaoStock, Tushare, AKShare and EastMoney are auxiliary/exploratory unless formally qualified. A runnable adapter is not formal evidence.

Agents may diagnose, implement approved scope and propose model changes. They do not auto-promote models, mutate approved risk, place orders or unlock broker authority.

## Workspace, branch and commit discipline

- Inspect the current workspace before Git mutation and preserve all unrelated changes and local configuration.
- Never implement directly on `main`; use the current isolated branch/worktree.
- Do not fetch, pull, switch, reset, clean, stash, force-push, rewrite history or delete branches unless explicitly authorized.
- Use one dependency-coherent correction per checkpoint commit. Do not merge automatically.
- Open/update a Draft PR only when requested or required.
- Before every commit run `git diff --check`, inspect staged/unstaged scope and exclude credentials, generated secrets, personal paths and unrelated files.
- Never modify, stage, overwrite, stash or commit `.idea/modules.xml`.

## Engineering discipline

For broad completion work, continue across dependency-ready P0/P1 Roadmap items. A phase needs executable behavior, tests, compatibility evidence, current documentation and a reviewable checkpoint. Stop only for a genuine blocker such as missing external evidence, a Constitution conflict, an absent approved business parameter or prohibited live mutation.

Do not introduce model optimization, formal OOS experiments, formal Provider claims, broker integration, dashboards, microservices or infrastructure expansion unless explicitly scoped.

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

Run focused PostgreSQL migration, idempotency, concurrency, replay and compatibility tests for affected owners. Report every command as `PASS`, `FAIL`, `NOT_RUN` or `BLOCKED`. Never promote fixture/local/CI evidence into Provider, OOS Alpha, trading or Production authority.
