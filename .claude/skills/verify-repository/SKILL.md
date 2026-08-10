---
name: verify-repository
description: Run and report the full Market Regime Alpha validation protocol before review or merge. Use when the user asks to verify, validate, check CI readiness, or prepare a PR for merge.
disable-model-invocation: true
---

Verify the current branch without changing model semantics.

## Procedure

1. Read `CLAUDE.md` and `AGENTS.md`.
2. Record branch, HEAD, `git status --short --branch` and diff summary against `main`.
3. Confirm there is no temporary audit workflow, payload, secret, local environment path or generated cache in the diff.
4. Run, in order:

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

5. Run additional focused tests required by the changed bounded contexts.
6. Inspect CI configuration and compare local commands with GitHub Actions.
7. Check Current State, Capability Matrix, Gap Register and Roadmap against the actual code/tests.
8. Use the `repository-verifier` subagent for an independent read-only review when available.

## Reporting

Report every command separately as:

```text
PASS
FAIL
NOT_RUN
BLOCKED
NOT_APPLICABLE
```

Include exact failure output or blocker reason. Never report “all passed” when only focused tests ran.

End with one of:

```text
READY_FOR_REVIEW
NOT_READY
BLOCKED
```

Do not merge unless the user explicitly requested it and all required checks succeeded.
