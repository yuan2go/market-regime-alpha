# Claude Code Engineering Program Update — 2026-08-01

> **Status:** CURRENT_STATUS  
> **Authority:** Delivery record for Claude Code execution assets aligned with WP-PDL  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../../CLAUDE.md, ../../AGENTS.md, ../../.claude/README.md, ../prompts/Claude-Code-Production-Decision-Lifecycle.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md  
> **Code Evidence:** Documentation and Claude Code asset updates on `main`; no runtime implementation is claimed.

## 1. Delivery conclusion

```text
CLAUDE_CODE_WP_PDL_EXECUTION_MEMORY_UPDATED
CONTINUOUS_PRODUCTION_LIFECYCLE_SKILL_ADDED
MASTER_IMPLEMENTATION_PROMPT_UPDATED
RUNTIME_IMPLEMENTATION_NOT_CHANGED_BY_THIS DELIVERY
```

This delivery aligns Claude Code project memory, shared agent rules, project Skills and the master prompt with the accepted Production Decision Lifecycle architecture.

It does not claim that WP-PDL runtime phases have been implemented or that the repository is ready for live trading.

## 2. Updated assets

| Path | Change |
|---|---|
| `CLAUDE.md` | Replaced the obsolete WP-D0-only priority with the dependency-ordered WP-PDL engineering program; added continuous execution, workspace preservation, stop conditions, validation and completion-report rules. |
| `AGENTS.md` | Updated authority order, implementation boundary, domain invariants, workspace rules and continuous program discipline. |
| `.claude/README.md` | Documented the master prompt, continuous-program skill and current subagent/skill usage. |
| `.claude/skills/implement-work-package/SKILL.md` | Updated the single-work-package procedure to preserve current workspace state and support bounded WP-PDL phases. |
| `.claude/skills/advance-production-lifecycle/SKILL.md` | Added the continuous dependency-ordered implementation skill for the full WP-PDL program. |
| `docs/prompts/Claude-Code-Production-Decision-Lifecycle.md` | Converted the prompt into an implementation-first master prompt that begins with Phase 0 and continues across dependency-ready phases. |

## 3. Accepted execution behavior

Claude Code is instructed to:

1. inspect current code, tests and call chains before editing;
2. preserve the current workspace and unrelated user changes;
3. avoid destructive or remote-changing Git commands without explicit authorization;
4. use a dedicated feature branch rather than implementing on `main`;
5. execute WP-PDL phases in dependency order;
6. implement vertical, testable slices rather than future horizontal shells;
7. fix ordinary failures and continue without pausing after plans, red tests, commits or documentation checkpoints;
8. stop only for genuine external, governance, authority or prohibited-live-execution blockers;
9. run focused and full validation after each phase;
10. create semantic checkpoint commits and maintain implementation-state documentation;
11. preserve all evidence ceilings and compatibility identities;
12. avoid automatic merge, model promotion, risk-limit mutation or live broker execution.

## 4. Program boundary

The continuous skill and master prompt cover:

```text
Phase 0  Code facts and baseline
Phase 1  Operational Research Bridge
Phase 2  Durable governance
Phase 3  Signal and PathForecast
Phase 4  Opportunity and Thesis
Phase 5  Portfolio and Risk
Phase 6  Manual Execution and Position
Phase 7  Holding, Exit and Attribution
Phase 8  Shadow operations and operator surface
```

A future broker adapter remains outside this program and requires a separate accepted work package and explicit trading-authority approval.

## 5. Authority and safety constraints

The update preserves these non-negotiable constraints:

- no duplicate identity, time, data, Artifact, registry, runtime or position authority;
- no silent change to MR1 or frozen `daily_research` semantics;
- no conversion of scores into probabilities without calibration;
- no interpretation of observable capital proxies as hidden institutional intent;
- no position derived from a recommendation or target position;
- no strategy override of hard Risk rejection;
- no LIVE_ORDER, QMT/PTrade mutation or unattended trading;
- no automatic model promotion or live risk-limit mutation.

## 6. Verification status

This action updated repository documentation and Claude Code assets through GitHub. It did not execute the repository test suite in a local workspace. The first Claude Code Phase 0 run must execute and report:

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

Any documentation-validator or test failure must be fixed before runtime implementation proceeds.

## 7. Start command

From Claude Code in the repository workspace, use either:

```text
/advance-production-lifecycle
```

or paste the full prompt from:

```text
docs/prompts/Claude-Code-Production-Decision-Lifecycle.md
```

Claude Code must begin with the startup protocol and Phase 0 rather than returning another planning-only answer.
