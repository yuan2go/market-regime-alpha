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
    ├── implement-work-package/SKILL.md
    ├── reconcile-branches/SKILL.md
    └── verify-repository/SKILL.md
```

## Usage

- `CLAUDE.md` is the always-loaded project memory and imports `AGENTS.md`.
- Subagents are bounded specialists. They should return evidence and recommendations to the main Claude session rather than edit the repository independently.
- Skills are repeatable procedures and may be invoked explicitly, for example:

```text
/implement-work-package docs/roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md
/verify-repository
/reconcile-branches
```

## Security and permissions

This repository deliberately does not commit `.claude/settings.json` with broad allow rules and never commits `.claude/settings.local.json`, credentials, API keys or personal environment paths.

Use the normal Claude Code permission system. Review project skills and subagents before granting workspace trust. Do not use bypass-permission modes for work that can modify Git history, provider evidence, research Artifacts or trading-related code.

## Maintenance

- Keep `CLAUDE.md` concise and focused on durable project facts and invariants.
- Move repeatable multi-step procedures into Skills.
- Use project subagents only for stable, recurring review roles.
- Update these assets whenever authority order, current Work Package, validation commands or evidence boundaries materially change.
