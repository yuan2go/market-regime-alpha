# CLAUDE.md — Market Regime Alpha Project Entry

@AGENTS.md

`AGENTS.md` is authoritative. This file keeps Claude startup context intentionally small.

## Startup

1. Inspect `git status --short --branch`, `git rev-parse HEAD`, worktrees and diffs.
2. Preserve user changes and never work directly on `main`.
3. Read, in order:
   - `docs/README.md`;
   - `docs/architecture/Canonical-Overall-Design.md`;
   - `docs/architecture/System-Architecture.md`;
   - `docs/architecture/Authority-Map.md`;
   - `docs/architecture/Data-and-Evidence-Architecture.md`;
   - `docs/architecture/Research-Strategy-Lifecycle.md`;
   - `docs/status/Current-State.md`;
   - `docs/status/Capability-Matrix.md`;
   - `docs/status/Gap-Register.md`;
   - `docs/status/Roadmap.md`;
   - the code, migrations, tests and runtime/evidence artifacts in the affected bounded context.
4. Reconstruct the real call chain, PostgreSQL owner and consumer before accepting a documentation claim.
5. Treat Canonical Design as the target; treat executable code/evidence as the truth about current completion.

## Current program

Work from the highest-information P0/P1 item in `docs/status/Roadmap.md`. The current program is **Alpha Proof**, not another infrastructure-expansion phase:

```text
Golden Loop
→ transparent baseline
→ factor/context ablation
→ Strategy/Portfolio economics
→ prospective evidence
→ Outcome/Attribution
→ evidence-driven next change
```

Preserve the single Runtime, PostgreSQL-only Authority, Fill-derived Position, fail-closed evidence boundaries and explicit Legacy boundary. Do not recreate the superseded Constitution/document hierarchy or resume historical work packages mechanically from Git history.

## Execution loop

```text
read Canonical Design
→ inspect code/schema/runtime/evidence
→ classify stale docs/Legacy/duplicate paths
→ choose highest-value real blocker
→ complete one dependency-coherent Work Package
→ wire into Canonical Runtime/owner/consumer where applicable
→ focused PostgreSQL/runtime verification
→ full repository gate
→ update only current canonical/status docs
→ review architecture compression opportunities
→ inspect diff and migration impact
→ checkpoint commit / Draft PR
```

Use `.claude/agents` only for bounded evidence/review. Historical plan-generating skills must not recreate deleted documentation hierarchies or bypass the evidence-driven Roadmap.

Do not stop at a stub, fixture-only proof or isolated helper when the accepted Work Package requires a real runtime/business closure. Conversely, do not expand into Future Scope merely to make the implementation look more industrial.