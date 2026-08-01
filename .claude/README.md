# Claude Code Project Assets

This directory contains shared, version-controlled Claude Code assets for `market-regime-alpha`.

## Layout

```text
.claude/
├── agents/
│   ├── platform-kernel-reviewer.md
│   ├── research-evidence-reviewer.md
│   └── repository-verifier.md
└── skills/
    ├── advance-production-lifecycle/SKILL.md
    ├── implement-work-package/SKILL.md
    ├── reconcile-branches/SKILL.md
    └── verify-repository/SKILL.md
```

## Entry points

- `CLAUDE.md` is the always-loaded Claude Code project memory and imports `AGENTS.md`.
- `AGENTS.md` is the shared cross-agent execution contract.
- `docs/prompts/Claude-Code-Production-Decision-Lifecycle.md` is the master implementation prompt for advancing the complete production decision lifecycle.
- `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md` owns the dependency order, phase acceptance conditions and stop conditions.

## Skills

Use `/advance-production-lifecycle` when the user asks Claude Code to continue improving or complete the whole engineering program. It executes dependency-ready WP-PDL phases continuously, with tests, documentation and checkpoint commits after each coherent phase.

```text
/advance-production-lifecycle
```

Use `/implement-work-package` when the scope is exactly one declared Work Package or one bounded phase and the user does not request continuous program execution.

```text
/implement-work-package docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md
```

Use `/verify-repository` for read-only or validation-focused repository verification, and `/reconcile-branches` only for an explicitly requested branch audit or reconciliation task.

## Subagents

Subagents are bounded specialists. They should collect evidence and return recommendations to the main Claude session rather than independently modify overlapping files.

Recommended uses:

- `platform-kernel-reviewer`: identity, time, evidence, registry, persistence and authority boundaries;
- `research-evidence-reviewer`: PIT, target leakage, calibration, evaluation and evidence-ceiling review;
- `repository-verifier`: independent diff, test, documentation and compatibility verification.

The main Claude session remains responsible for implementation, integration, state management, validation and final claims.

## Continuous execution behavior

When continuous execution is requested, Claude Code should not stop after a scan, plan, expected red test, ordinary implementation failure, documentation update or checkpoint commit. It should fix ordinary problems and continue to the next dependency-ready phase.

It should stop only for a genuine blocker such as unavailable required external input, an unresolved business or risk parameter with no fail-closed default, a Constitution/ADR conflict, inability to preserve historical authority, or a prohibited live-broker requirement.

Every completed phase must remain independently reviewable and reversible. Use semantic checkpoint commits, preserve unrelated user changes, and do not merge automatically.

## Security and permissions

This repository deliberately does not commit `.claude/settings.json` with broad allow rules and never commits `.claude/settings.local.json`, credentials, API keys, brokerage secrets or personal environment paths.

Use the normal Claude Code permission system. Review project skills and subagents before granting workspace trust. Do not use bypass-permission modes for work that can modify Git history, Provider evidence, research Artifacts, risk limits, manual execution records or trading-related code.

Do not run destructive Git commands, fetch/pull/switch/reset/clean/stash user work, or change the current workspace baseline unless explicitly authorized.

## Maintenance

- Keep `CLAUDE.md` focused on durable project facts, current program priority and non-negotiable invariants.
- Keep cross-agent rules in `AGENTS.md`.
- Move repeatable multi-step procedures into Skills.
- Keep the long-form executable program prompt under `docs/prompts/`.
- Use project subagents only for stable, recurring review roles.
- Update these assets whenever authority order, current Work Package, phase sequence, validation commands, workspace rules or evidence boundaries materially change.
