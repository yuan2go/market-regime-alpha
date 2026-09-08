# Roadmap

> **Status:** ROADMAP
> **Code Evidence:** `src/market_regime_alpha`, `tests`, `scripts/check_docs_links.py`

This is the sole active plan. Evidence and historical results do not authorize
the next experiment or deployment. The current task is repository hygiene;
business feature development and live configuration changes are outside it.

## Current dependency chain

1. Reconstruct installed/module/script entry points, composition, owner SQL and
   test contracts; preserve the original workspace and running evidence scopes.
2. Archive historical instructions/evidence without changing their bytes;
   replace active docs with this small source-linked set.
3. Remove proved fixture self-tests and dead helpers, rename valid contracts,
   separate external-history qualification from default regression, and remove
   misleading comments without changing research semantics.
4. Add lightweight document/comment/schema/inventory guards; run all retained
   Python tests, including PostgreSQL and explicitly provisioned history tests,
   plus lint, types, links, build and installed-artifact smoke.
5. Freeze local implementation and record exact outcomes, counts, deletion
   reasons, remaining gaps and evidence limits. No push or automatic merge.

## Remaining architectural debt

| Boundary | Executable evidence | Smallest next investigation |
|---|---|---|
| Two persistence families | `infrastructure/postgres/schema.py` and `persistence/postgres/migrator.py`; installed legacy CLIs remain | Per-consumer invariant migration before any authorized cutover or deletion |
| Research package overlap | `research`, `research_qualification`, `application/historical_corpus`, `platform`; imported by scripts and CLIs | Trace one concrete consumer before moving or deleting its owner |
| Large orchestration modules | `bootstrap.py`, `interfaces/daily_research.py`, `interfaces/cli/main.py` | Extract only when an independently demonstrated correctness/change boundary requires it |
| SQL source-text architecture tests | Several retained tests inspect strings rather than AST/behavior | Replace only against an equivalent mutation-sensitive contract; names alone do not establish duplicates |
| Historical external evidence | Explicit history tests require an exact database and Artifact root | Keep opt-in and fail closed when prerequisites are absent; never copy successful rows into failed history |
| Operational and research qualification | Canonical status/health/replay commands and original immutable evidence | Observe the explicitly authorized scope; source tests do not prove current service, successful capture or Alpha |

No new abstraction, scheduler, generic registry, strategy experiment or model
qualification is authorized by this Roadmap.
