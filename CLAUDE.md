# CLAUDE.md — Market Regime Alpha Project Entry

@AGENTS.md

`AGENTS.md` is authoritative. This file keeps Claude startup context intentionally small.

## Startup

1. Inspect `git status --short --branch`, `git rev-parse HEAD`, worktrees and diffs.
2. Preserve user changes and never work directly on `main`.
3. Read, in order:
   - `docs/README.md`;
   - `docs/architecture/System-Architecture.md`;
   - `docs/architecture/Authority-Map.md`;
   - `docs/architecture/Data-and-Evidence-Architecture.md`;
   - `docs/architecture/Research-Strategy-Lifecycle.md`;
   - `docs/status/Current-State.md`;
   - `docs/status/Gap-Register.md`;
   - `docs/status/Roadmap.md`;
   - the code, migrations and tests in the affected bounded context.
4. Reconstruct the current call chain and owner Repository before accepting a documentation claim.

## Current program

Work from P0 to P1 in `docs/status/Roadmap.md`: preserve the single Runtime, PostgreSQL-only Authority, reference-not-Authority rule, fail-closed qualification and explicit Legacy boundary. Do not resume superseded WP-PDL work packages from Git history.

## Execution loop

```text
code/schema/test facts
-> bounded objective and invariants
-> smallest coherent implementation
-> focused PostgreSQL verification
-> full repository gate
-> update only current canonical docs
-> inspect diff and migration impact
-> checkpoint commit
```

Use `.claude/agents` only for bounded evidence/review. Historical plan-generating skills must not recreate deleted documentation hierarchies.
