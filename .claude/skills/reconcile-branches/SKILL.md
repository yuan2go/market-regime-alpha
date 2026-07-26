---
name: reconcile-branches
description: Audit all remote branches against main, distinguish already-integrated PR branches from true unmerged content, and submit safe merges. Use when the user asks whether all branches are merged or requests branch cleanup/reconciliation.
disable-model-invocation: true
---

Audit branch integration conservatively.

## Procedure

1. Fetch all refs:

```bash
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune
```

2. Record `origin/main` SHA.
3. For every remote branch except `main` and `HEAD`, calculate:
   - branch head SHA;
   - ahead/behind counts against `origin/main`;
   - ancestry status;
   - associated PR and PR merge status;
   - effective file/content difference against `main`.
4. Do **not** treat `merge-base --is-ancestor=false` as proof that a branch is unmerged. Squash, rebase or reconstructed merges can integrate content without preserving the branch head as an ancestor.
5. Classify each branch:

```text
INTEGRATED_BY_MERGED_PR
CONTAINED_IN_MAIN
UNMERGED_UNIQUE_CONTENT
SUPERSEDED_OR_OBSOLETE
CURRENT_WORK_BRANCH
UNKNOWN_REQUIRES_REVIEW
```

6. For `UNMERGED_UNIQUE_CONTENT`:
   - inspect every unique commit and changed file;
   - check whether a later branch or PR supersedes it;
   - run required validation;
   - open a focused PR to `main`;
   - merge only after checks pass and the user has authorized merging.
7. Never merge stale historical branches again merely to make ancestry green.
8. Never delete remote branches unless explicitly requested.
9. Publish or update a commit-bound branch reconciliation audit.

## Report

Return a table:

```text
BRANCH | HEAD | PR | AHEAD/BEHIND | CLASSIFICATION | ACTION | EVIDENCE
```

Then report submitted/merged PRs, remaining work branches, and any branches requiring manual review.
