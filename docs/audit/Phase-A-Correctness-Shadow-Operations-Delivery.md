# Phase A Correctness and Research Shadow Operations Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Delivery record for Phase A correctness convergence and Research Shadow operations
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../architecture/16-Phase-A-Correctness-and-Research-Shadow-Operations.md, ../operations/Research-Shadow-Operations-Runbook.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md
> **Code Evidence:** Implementation branch based on `4ab425d956f76c1e06d410592ff4c7842f2cc574`; the final clean-SHA verification record is emitted outside the repository and reported with delivery so the verified SHA remains unchanged

## 1. Delivered scope

| Work package | Delivered authority |
|---|---|
| WP-CANONICAL-BOUNDARY-01 | machine-readable Canonical/Legacy authority registry and AST guard against Legacy executable imports |
| WP-STATE-CROSS-SESSION-02 | stable State Series, immutable cross-Run links, CAS/fenced heads and V1-compatible Readers |
| WP-STATE-POLICY-01 | immutable State/Pool policy ID, version, hash and complete transition parameter lineage |
| WP-TARGET-01 | six-horizon Target Protocol and factual Targeted Outcome V2 without Decision mutation |
| WP-RESEARCH-SHADOW-OPS-01 | CLI/Application schedule-to-report loop, crash-safe idempotent settlement and prospective attestation mechanism |
| Evaluation V2 Foundation | complete frozen Pool/Candidate research panel with factor, State, model, policy, target and outcome lineage |
| WP-RUNTIME-READMODEL-02 | real owner assignment, Shadow DAG and `NOT_OBSERVED` metrics instead of fabricated zeroes |

No package creates an Order, Fill, Broker call or Position mutation.

## 2. Migration evidence

The actual prior head was 037. This phase appends migrations 038–042 without
changing a published migration:

- 038: cross-session State Policy/Series/link/head;
- 039: Outcome Target Protocol and Targeted Outcome;
- 040: Prospective Evidence Attestation;
- 041: frozen Research Evaluation Panel V2;
- 042: Shadow Decision V2 State Policy binding.

Fresh and incremental migration checks use PostgreSQL 16. Historical State,
Outcome and Evaluation V1 Readers remain available.

## 3. Acceptance evidence before the final clean-SHA gate

Observed during implementation:

```text
State/Policy pure domain tests = PASS
State Series real PostgreSQL tests = PASS
Recorded-provider SHADOW end-to-end = PASS
Ruff = PASS
mypy = PASS
```

These are development checks. The final clean-tree SHA-bound record, exact
full-suite result and CI observation are reported with delivery only after all
code and documentation are committed and the repository-wide verification
script completes. The record is intentionally outside the Git worktree so it
cannot change the SHA it attests.

## 4. Explicit evidence ceiling

This delivery may establish only:

```text
CORRECTNESS_CONVERGENCE_ENGINEERING_PROVEN
CROSS_SESSION_STATE_ENGINEERING_PROVEN
RESEARCH_SHADOW_OPERATIONS_ENGINEERING_READY
MULTI_TARGET_EVALUATION_ENGINEERING_READY
```

It does not establish `LIVE_PROVEN`, `PROSPECTIVE_PROVEN`, `ALPHA_PROVEN`,
`FORMAL_PIT`, `FORMAL_OOS`, `ENTRY_QUALIFIED` or `PRODUCTION_AUTHORIZED`.
Current fixtures and simulated clocks produce structurally valid but ineligible
Prospective Evidence Attestations with `prospective_proven=false`.

## 5. Forward priority

The next research dependency sequence is real Provider historical
qualification, full PIT A-share Universe, PIT Theme/ETF membership, a locked
formal evaluation protocol, factor ablations, Path Sample Authority,
calibration and formal OOS. Sustained real Shadow capture and authenticated
operators remain external/operational work, not implied by this engineering
delivery.
