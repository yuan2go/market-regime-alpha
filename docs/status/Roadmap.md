# Roadmap

> **Status:** ROADMAP
> **Code Evidence:** `src/market_regime_alpha`, `tests`, `scripts/check_docs_links.py`

This is the sole active plan. Evidence and historical results do not authorize
the next experiment or deployment. Repository hygiene is complete at the
implementation recorded in the archive index. Business feature development and
live configuration changes require their own explicit scope.

## Completed repository maintenance

Current entry points, owner call chains, schema facts and test contracts are
indexed and source-linked. Historical documents are isolated without byte
changes; dead private helpers and obsolete tests have explicit dispositions.
Default and external-history regressions, PostgreSQL, static/document guards,
build and installed-artifact checks have executed. The
[archive index](../archive/README.md) records exact revisions, failures and
results. These facts do not authorize deployment or a new experiment.

Keep the current documentation set small. For future changes regenerate the
inventory, run affected behavior and hygiene checks, and preserve historical
identities. The items below are investigations requiring concrete consumer and
invariant evidence; they are not permission for a broad refactor.

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
