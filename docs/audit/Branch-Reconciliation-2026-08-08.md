# Branch Reconciliation Audit — 2026-08-08

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound remote-branch integration audit
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-08
> **Supersedes:** Branch-Reconciliation-2026-07-26.md
> **Superseded By:** None
> **Related Documents:** Branch-Reconciliation-2026-07-26.md, Post-Merge-Reconciliation-2026-07-26.md, ../status/Current-State.md, ../../AGENTS.md
> **Code Evidence:** refreshed remote baseline `bd3f9753fbf1431f6b8d53e121c6ac252b224cbc`; reconciliation merge `1b187da`; source branch `169f620d3b8bc62a0f746898f398cc1d289e0d02`

## Purpose

Re-audit every current remote branch against the latest `origin/main`, merge
genuinely unique content, and avoid reintroducing historical work whose content
already entered through a merged pull request or a later consolidation.

## Method

The audit refreshed all remote refs without pruning, enumerated every remote
head, queried pull-request state, calculated branch-ahead/main-ahead counts,
checked ancestry and inspected effective file differences. Non-ancestry alone
was not treated as missing integration because several historical branches were
merged by GitHub PRs without preserving their archived tips as ancestors.

`ahead/behind` below means commits reachable only from the branch / commits
reachable only from `origin/main` at baseline `bd3f975`.

## Remote branch result

| Branch | Head | PR | Ahead/behind | Classification | Action and evidence |
|---|---:|---:|---:|---|---|
| `agent/research-runtime-foundation` | `8de820c` | — | 0/28 | CONTAINED_IN_MAIN | Points at the PR #38 merge baseline; no unique content. |
| `agent/update-docs-current-main-audit` | `a8821f2` | #29 merged | 0/154 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `architecture/daily-research-contract-convergence` | `169f620` | — | 1/254 | UNMERGED_UNIQUE_CONTENT | Reconciled by merge `1b187da`; retained the V1 freeze ADR/test and discarded superseded status prose. |
| `archive/merged/agent/research-platform-kernel-v1` | `f75af7f` | #12/#19 merged | 1/263 | CONTAINED_IN_MAIN | Effective diff from its merge base is empty; do not merge again. |
| `archive/merged/chore/consolidate-all-branches` | `0485303` | #21 merged | 0/257 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `archive/merged/codex/tencent-composite-exploratory` | `1af8e56` | — | 0/374 | CONTAINED_IN_MAIN | Tip is an ancestor of main. |
| `archive/merged/docs/agent-guidance-and-branch-reconciliation` | `3d2c074` | #15 merged | 0/282 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `archive/merged/docs/agent-guidance-finalization` | `f6113c2` | #17 merged | 0/266 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `archive/merged/docs/finalize-branch-audit-state` | `d38275f` | #18 merged | 0/264 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `archive/merged/docs/reconstruct-system-design-20260726` | `ddf9104` | #13 merged | 0/309 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `archive/merged/feat/daily-quant-selection-research-foundation` | `b9791c8` | #21 merged | 0/314 | INTEGRATED_BY_MERGED_PR | Entered main through the consolidation merge. |
| `archive/merged/feat/mr2b-f2-conditionality-core` | `e9dc4ff` | #2 merged | 8/329 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/feat/mr2b-f2b-postmerge-hardening` | `5670271` | #4 merged | 4/327 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/feat/mr2b-f2b-statistical-closure` | `32cdedd` | #3 merged | 5/328 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/feat/mr2b-pit-expansion-validation` | `1c9bf21` | #5 merged | 4/326 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/feat/pit-replication-success-path-v2` | `6e476e6` | #8 merged | 2/323 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/feat/prr-mvp-1` | `f657c7e` | #1 merged | 23/330 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/feat/research-artifact-identity-v3` | `5e35a57` | #6 merged | 2/325 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/feat/xuntou-pit-evidence-v4` | `58d1892` | #7 merged | 2/324 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/fix/pit-replication-success-v2-review-closure` | `f32a77e` | #11 merged | 2/319 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `archive/merged/fix/post-merge-authority-and-ci-reconciliation` | `d4ae2f2` | #14/#16 merged | 0/282 | INTEGRATED_BY_MERGED_PR | No remaining unique content. |
| `archive/merged/fix/research-artifact-identity-v3-review-closure` | `704a808` | #9 merged | 3/321 | INTEGRATED_BY_MERGED_PR | Duplicate PR #39 was closed; do not merge again. |
| `archive/merged/fix/xuntou-pit-evidence-v4-review-closure` | `b46afcd` | #10 merged | 2/320 | INTEGRATED_BY_MERGED_PR | Historical archived tip; do not merge again. |
| `audit/post-consolidation-full-review` | `17e0cea` | #22 closed | 1/256 | SUPERSEDED_OR_OBSOLETE | Temporary workflow was intentionally not merged; later permanent audit replaced it. |
| `docs/post-consolidation-state-reconciliation` | `fae66ef` | #23 merged | 0/230 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/canonical-feature-spine-and-signal-inputs` | `3696f05` | #35 merged | 0/67 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/canonical-runtime-and-legacy-migration` | `d021380` | #34 merged | 0/91 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/canonical-signal-authority-and-operational-feature-handoff` | `13101db` | #36 merged | 0/63 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/continuous-research-runtime` | `3bbcd8d` | #40 merged | 0/1 | INTEGRATED_BY_MERGED_PR | Latest feature branch is already in baseline main. |
| `feat/controlled-1455-operational-evidence` | `8de820c` | #37/#38 merged | 0/28 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/h4-5-risk-reduction-manual-intent` | `3f25bef` | #33 merged | 0/122 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/h5-artifact-derived-thesis-health` | `05789ce` | #31 merged | 0/137 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/h6-composite-operational-evidence` | `24bf0fc` | #32 merged | 0/131 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/platform-architecture-v2-research-layer` | `a9afc69` | #27 merged | 0/208 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/public-live-semantic-closure` | `50c0f98` | #25 merged | 0/235 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/run-first-exploratory-daily-platform` | `d023116` | #24 merged | 0/244 | INTEGRATED_BY_MERGED_PR | Do not merge again. |
| `feat/wp-d3-1-real-decision-evidence` | `619b3d3` | #26/#28 merged | 1/163 | CONTAINED_IN_MAIN | The branch-only commit merges main into the feature branch; effective diff is empty. |
| `fix/h4-risk-route-baseline` | `dccef12` | #30 merged | 0/146 | INTEGRATED_BY_MERGED_PR | Do not merge again. |

## Conflict resolution

Merging `architecture/daily-research-contract-convergence` produced conflicts
in five documentation files. The reconciliation retained current main's newer
implementation facts and authority ceilings, added only the ADR links needed
to make the preserved contract discoverable, and did not restore the branch's
obsolete July status tables. The new characterization test proves that the
historical V1 module set, module bytes, schema versions, enums and canonical
JSON field sets remain frozen.

## Pull-request cleanup

PR #39 attempted to merge the archived PR #9 branch a second time. It was
closed with an integration note. No remote branch was deleted.

## Conclusion

At baseline `bd3f975`, exactly one current remote branch contained reviewed,
non-superseded unique content. Merge `1b187da` reconciles that content. Every
other remote branch is either integrated by a merged PR, contained in main, or
explicitly superseded/obsolete and unsafe to merge again.
