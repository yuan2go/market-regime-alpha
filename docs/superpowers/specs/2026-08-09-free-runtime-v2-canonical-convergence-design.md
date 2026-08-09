# Free Runtime V2 Canonical Convergence — Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Current user request, Constitution, Architecture 09–11/15, WP-STATE-01
> **Baseline:** `origin/main@9d4b872eae9fb3bb56544f8dbb4ef14f6e6806d2`
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../plans/2026-08-09-free-runtime-v2-canonical-convergence.md, ../../status/Current-State.md
> **Code Evidence:** Baseline `9d4b872eae9fb3bb56544f8dbb4ef14f6e6806d2`; `src/market_regime_alpha`; `tests`
> **Authority ceiling:** Free-data exploratory engineering evidence only; no Entry, Order, Fill, Broker, or Position mutation authority

## Objective

Make the one Continuous Research Runtime execute the existing PostgreSQL State
System and preserve a real prospective chain:

```text
explicit BaoStock/Tencent/free-supplemental inputs
→ Daily Dataset → Static Features
→ Stateful Market → ETF → Theme → Capital
→ Dynamic Pool → pool-constrained Candidate
→ bounded Tencent minute freeze before DecisionTime
→ Signal → Forecast → Research/Shadow Daily Summary
```

The endpoint remains account-neutral. It cannot create Order, Fill, Broker or
Position mutation, and free evidence cannot authorize Production.

## Verified starting defect

`CanonicalFreeDataResearchComposition` executes `FreeDataOperationService` and
then hashes Summary stages to synthesize the `STATE_SYSTEM`,
`CONTROLLED_OPERATION`, and `CANONICAL_LIFECYCLE` child receipts. The actual
`StateSystemRuntimeDelegate` is absent from that call chain. Candidate discovery
also starts inside the 14:55 decision-window call, so candidate-scoped minute
requests cannot satisfy `response_received_at <= DecisionTime` in a real run.

`ResearchDailySummary` derives WATCH and RESEARCH_CANDIDATE by scanning reason
strings, and the Decision repository does not reload Model Governance receipts
before accepting a Summary.

## Authority ownership

| Child / fact | Sole owner | Durable evidence |
|---|---|---|
| Provider attempts and immutable evidence commit | Continuous Research / explicit Provider | PostgreSQL attempt, EvidenceCommit, SourceManifest |
| Daily Dataset | Daily Dataset service | verified content-addressed Dataset + owner receipt |
| Static and intraday Features | Feature materialization service | verified bundle + feature run receipt |
| Market/ETF/Theme/Capital state, Dynamic Pool, pool binding | State System | state tables, pool tables, `state_runtime_receipt` |
| pre-Decision candidate-scoped acquisition | Controlled Operation | frozen acquisition coverage/source/dataset/overlay receipts |
| Signal/Forecast and Entry blocker | Canonical Lifecycle | canonical stage and run receipts |
| Research/Shadow endpoint | Decision System | immutable `research_daily_summary` revision |
| schedule/lease/fence/change detection/child references | Continuous Research | PostgreSQL journal only |

Continuous Research orchestrates these owners. It does not fabricate their
facts or reconstruct owner receipts from a final Summary.

## Execution phases

### Pre-decision staging

The composition root exposes one idempotent staging operation used in the
14:54 acquisition interval. It freezes explicit supplemental evidence, selects
the configured models through PostgreSQL Governance, evaluates the deterministic
State chain, derives a bounded pool-constrained Candidate set, and requests
Tencent minute data only for that set. Every accepted response must have
`response_received_at <= DecisionTime`; retries share an explicit hard deadline.

The staging bundle is immutable, content-addressed and PostgreSQL-indexed by the
future Continuous run/tick/DecisionTime lineage. Restart loads accepted Provider
sources and never repeats a completed call. Staging grants no trading authority.

### Decision finalization

At DecisionTime the admitted Continuous Tick loads the frozen staging bundle.
The real `StateSystemRuntimeDelegate` recomputes/verifies and writes State and
Pool facts under the active lease/fence, then emits its own receipt. Controlled
Operation and Canonical Lifecycle consume the frozen minute dataset and emit
their own receipts. Decision System builds the Summary from those real outputs.

Missing stage evidence is a normal typed Stage result and propagates to a
`DATA_INSUFFICIENT` Summary. Identity/hash/future-time/fence/lineage corruption
is a fatal Tick failure.

## Outcome contract

Summary outcome is derived from structured fields, in precedence order:

1. any mode-specific model rejection → `MODEL_NOT_QUALIFIED_FOR_MODE`;
2. any required Stage insufficiency → `DATA_INSUFFICIENT`;
3. no selected pool-constrained Candidate → `NO_ACTION`;
4. selected Candidate with observation-only Signal → `WATCH`;
5. selected Candidate with research-confirmed Signal and usable Forecast →
   `RESEARCH_CANDIDATE`.

Reason codes explain the result but do not decide it.

## Governance and policy

Market, Theme, Capital, Candidate, Signal, and Forecast executions require a
stored mode-specific Champion and immutable Selection Receipt. The Decision
repository reloads every receipt and verifies hash, RuntimePurpose, slot and
runtime lineage before saving the Summary. ETF rotation and Dynamic Pool remain
deterministic versioned domain policies; their configuration IDs and hashes are
part of lineage.

No caller-declared qualification is accepted. Research/Shadow selections never
authorize Production. Production plus free data fails closed before child
execution.

## Provider lineage

The Summary records contracts actually consumed from SourceManifest and frozen
attempt/source artifacts. BaoStock history/status and Tencent quote are present
only when consumed. Tencent minute is present only when accepted minute sources
were used. Supplemental providers are explicit inputs. There is no automatic
fallback and no authority promotion to Formal PIT.

## Time contract

The immutable chain distinguishes:

- `decision_time`: semantic decision cutoff;
- `evidence_available_at`: latest accepted input availability;
- `stage_completed_at`: owner computation completion;
- `summary_created_at`: Decision owner creation time;
- database persistence time: PostgreSQL audit clock.

Live staging uses the operational/PostgreSQL clock. CLI `--at` is accepted only
with an explicit simulated/replay flag; it cannot impersonate live evidence.
Replay retains original identities and timestamps.

## Compatibility and recovery

Existing historical Summary and State receipts remain readable. New writes use
the V2 contracts. Successful artifacts are content-addressed and reused when
material inputs do not change. Restart resolves the persisted staging/owner
receipts first. Stale leases and fencing tokens fail before mutation. Corrections
append a new Summary revision; Original Final remains immutable.

## Non-goals

No T+1 outcome, Economic Validation, Holding/Exit, Formal OOS, professional data,
Xuntou, broker, Order/Fill, Production Entry, frontend or unrelated refactor.

## Acceptance evidence

PostgreSQL 16 tests must prove the positive Stateful chain with real Governance
assignments, minute receipt before DecisionTime and `RESEARCH_CANDIDATE`; Shadow
safety; Production rejection; missing-stage Summary; provider/late/future
failure; no fallback; no-material reuse; restart/crash recovery; deterministic
replay; and stale-fence rejection.

## Rollback / forward repair

All new database changes are additive. Disable the V2 composition entry to stop
new writes; immutable V2 artifacts remain readable. Correct content through an
append-only Summary correction or a new State Tick—never mutate historical
identities.
