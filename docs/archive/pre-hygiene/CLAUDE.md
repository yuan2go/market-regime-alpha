# CLAUDE.md — Market Regime Alpha Project Entry

@AGENTS.md

`AGENTS.md` is authoritative. This file adds only Claude-specific startup
behavior and must not duplicate architecture, status, evidence, or Roadmap
rules.

## Startup

1. Inspect `git status --short --branch`, exact HEAD, ancestry, worktrees, and
   all diffs before editing.
2. Preserve user changes and use an isolated non-`main` worktree.
3. Read `docs/README.md`, the target architecture set, Current State,
   Capability Matrix, Roadmap, and then the affected code/schema/tests.
4. State whether each claim describes the approved Target, current
   implementation, executed validation, research evidence, or Production
   qualification.
5. Follow only the dependency-ready Architecture Re-foundation checkpoint. Do
   not revive historical Alpha Proof plans from prose or Git history.

## Execution

Use current code and PostgreSQL call chains to establish implementation facts.
Treat the approved Target as the destination, not as evidence that a cutover has
already occurred. Keep incomplete target modules non-canonical and never create
dual Authority, fallback, or compatibility write paths.

## Validation

Use the repository gate defined in `AGENTS.md`; do not copy or fork its command
list here. `uv sync` does not activate the project environment, so invoke every
Python-based gate through `uv run`, including from a clean or non-activated
shell.

Project-local persistent reviewer prompts and generic implementation/
verification Skills are intentionally absent. Use
`.claude/skills/reconcile-branches/SKILL.md` only when the user explicitly asks
for branch reconciliation; otherwise follow `AGENTS.md` directly.
