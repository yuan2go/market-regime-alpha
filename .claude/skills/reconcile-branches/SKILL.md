---
name: reconcile-branches
description: Classify explicitly named branches against an explicitly named comparison ref and propose safe integration actions. Use only when the user asks for branch integration or reconciliation.
disable-model-invocation: true
---

# Reconcile Branches

This Skill is a bounded, high-risk Git audit procedure. It contains no Market
Regime Alpha architecture, business, research, or evidence rules; those remain
in `AGENTS.md`.

## Required input

Before any command, resolve and report:

- repository path;
- comparison ref and its locally resolved SHA;
- exact named branch scope;
- authorization level: `READ_ONLY`, `FETCH_ALLOWED`, `PR_ALLOWED`, or
  `MERGE_ALLOWED`.

Missing or ambiguous input fails closed. Do not infer authorization from a prior
task, branch name, UI label, or remote configuration.

## Default procedure

1. Inspect workspace status, worktrees, remotes, local refs, and the comparison
   SHA without mutation.
2. Do not fetch unless the current request explicitly grants `FETCH_ALLOWED` or
   stronger authority.
3. Run the repository-local classifier for ancestry and content evidence:

   ```bash
   python scripts/reconcile_branches.py \
     --repository REPOSITORY \
     --comparison COMPARISON_REF \
     --branch NAMED_BRANCH \
     --authorization AUTHORIZATION
   ```

   It is local and read-only: it never fetches, queries PRs, or mutates refs.
   Independently establish known PR state with an authorized read-only remote
   query when available.
4. Do not treat non-ancestry as unmerged content: squash, rebase, and recreated
   commits require patch/content comparison.
5. Classify exactly one of:

```text
INTEGRATED_BY_MERGED_PR
CONTAINED_IN_COMPARISON
UNMERGED_UNIQUE_CONTENT
SUPERSEDED_OR_OBSOLETE
CURRENT_WORK_BRANCH
UNKNOWN_REQUIRES_REVIEW
```

6. Unknown authentication, PR, remote, or content state remains `UNKNOWN`; do
   not guess.
7. Side effects require their matching authorization and a fresh preflight.
   Never force-push, rewrite history, delete a branch, merge, or clean a
   worktree unless that exact action is explicitly requested.

## Output contract

Return:

```text
REPOSITORY | COMPARISON_REF | COMPARISON_SHA | AUTHORIZATION
BRANCH | HEAD | PR | AHEAD/BEHIND | CLASSIFICATION | EVIDENCE | PROPOSED_ACTION
SIDE_EFFECTS_PERFORMED
UNRESOLVED_STATE
```

The default output is read-only. Do not create a persistent audit-document
hierarchy. `tests/scripts/test_reconcile_branches.py` covers merge, squash,
rebase-equivalent, divergent supersession, and unique-content fixtures. The
classifier intentionally leaves divergent supersession `UNKNOWN`; only explicit
external evidence may promote it to `SUPERSEDED_OR_OBSOLETE`. It never automates
mutation.
