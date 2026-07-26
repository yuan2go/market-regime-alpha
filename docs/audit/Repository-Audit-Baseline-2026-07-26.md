# Repository Audit Baseline — 2026-07-26

> **Status:** CURRENT_STATUS  
> **Authority:** Audit evidence for the documentation reconstruction; implementation facts remain governed by code/tests/artifacts  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Conversation-Decision-Ledger.md, Repository-Coverage-Ledger.tsv, Docs-Inventory-and-Migration-Plan.md, Conflict-Register.md  
> **Code Evidence:** main@96e41a12d86b3b5f7472c2d4e44011736b087b6b

## Baseline identity

| Field | Value |
|---|---|
| repository | `yuan2go/market-regime-alpha` |
| audited branch | `main` |
| audited HEAD | `96e41a12d86b3b5f7472c2d4e44011736b087b6b` |
| HEAD commit time | `2026-07-22T15:34:40Z` |
| audit start time | `2026-07-26T09:46:27Z` |
| tracked file count | 474 |
| docs file count | 87 |
| first-party source/script/backtesting/tool file count | 221 |
| first-party test file count | 142 |
| working tree at export | clean |

The temporary audit-export workflow used to obtain the complete workspace is excluded from baseline counts and removed before final delivery.

## Coverage method

1. GitHub Actions checked out the PR merge against exact `main` baseline with full Git history.
2. `git ls-files` generated the authoritative tracked-file list.
3. The repository workspace and per-file last-commit metadata were exported as a short-retention Artifact.
4. Every tracked file was read locally as UTF-8; all 360 Python files were parsed with `ast`.
5. Markdown headings, metadata, links, implementation claims and cross-references were indexed.
6. Code/test evidence was checked against requested capabilities and current status claims.

Coverage outcome:

```text
474 / 474 baseline tracked files read
87 / 87 docs files read
181 / 181 src Python files parsed
142 / 142 test Python files parsed
23 / 23 scripts read
13 / 13 backtesting files read
2 / 2 tools read
```

Excluded from semantic code review but retained in the ledger:

- `.idea/**`: IDE metadata, not project behavior authority;
- generated/sample data under `data/**`: inspected as assets, not treated as source logic;
- binary/cache/virtual-environment directories: not tracked in the baseline.

## Main factual conclusion

The repository has a substantial, test-backed V2 research spine for identity, time, dataset eligibility, trading calendar, PIT universe, eligibility, Feature materialization, Candidate datasets, B0/B1 ranking, diagnostics, Provider routing, Entry Path Target infrastructure, Research Artifact verification and Xuntou/PIT replication semantics.

It does **not** yet have a complete Phase D daily decision loop with canonical DailyResearchSnapshot, CandidateRecommendation, Entry Assessment, Position authority, Holding/Exit Assessment, Manual Trade attribution, Daily Review, Portfolio Decision and rolling model comparison.

Real qualified Xuntou v4 input is unavailable in the current environment, so formal PIT replication remains externally blocked. Test fixtures demonstrate contract and reader semantics; they do not establish formal OOS Alpha.

## Pending PR boundary

Draft PR #12 (`agent/research-platform-kernel-v1`) contains a CI-verified platform kernel proposal. Because it is not merged into `main`, this audit records it as `PENDING_PR`, not as current implementation fact.

## Reconstruction validation

The documentation reconstruction workflow executed the following checks against the generated branch tree:

```text
python scripts/check_docs_links.py                         PASS
python -m py_compile scripts/check_docs_links.py          PASS
documentation metadata/status validation                 PASS
python -m pytest -q                                      PASS (946 tests)
python -m ruff check .                                   PASS
python -m mypy                                           PASS (128 source files)
```

Pytest emitted an existing invalid-escape `SyntaxWarning` in one test and existing pandas DataFrame fragmentation `PerformanceWarning` messages in the Top-1000 backtesting module. No test, Ruff or mypy failure was produced.
