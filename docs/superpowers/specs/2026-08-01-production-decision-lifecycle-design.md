# Production Decision Lifecycle Approved Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved implementation design for WP-PDL Phases 0–7
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md, ../plans/2026-08-01-production-decision-lifecycle.md
> **Code Evidence:** `origin/main@83a3168bc8550d862bd8b675277dd587ea71182c`; delivery evidence is added by phase checkpoint commits

## Approved execution boundary

Implement WP-PDL in the existing modular monolith and Python package. The
first operational profile is A-share, long-only and CLI-first. `14:55
Asia/Shanghai` is a versioned decision profile, not an immutable domain
constant. SQLite is the first durable adapter; Repository Protocols remain
storage-neutral for future PostgreSQL adapters.

Path, Portfolio and Risk parameters are explicit, versioned and replaceable
configuration inputs. No unvalidated parameter is an implicit production
default. Missing configuration fails closed. Synthetic and exploratory fixture
profiles are allowed only when their names, DataEligibility and authority
ceilings make that status explicit.

No phase creates LIVE_ORDER, broker mutation, formal PIT, formal OOS Alpha,
calibrated probability or trading authority. Xuntou remains the provider
direction, but missing qualified Provider or PIT Theme mapping evidence fails
closed.

## Architecture and ownership

- `core`, `data` and `evidence` retain identity, time, SourceManifest and
  immutable Artifact authority.
- `research` retains market, theme, capital and Candidate research facts.
- `signals` owns replayable signal snapshots; `forecasting` owns PathForecast.
- `decision` owns Opportunity, Thesis and independent RiskDecision facts.
- `portfolio` owns constraints, budgets, target positions and decisions.
- `execution` owns append-only manual records, fills and corrections.
- `position` projects authoritative snapshots only from accepted fills and
  owns holding/exit assessments without reading Providers.
- `evaluation` consumes versioned evidence and authoritative positions; it
  cannot mutate model weights or lifecycle state.
- `application` orchestrates cross-context commands and owns no domain facts.

Mutable aggregates use optimistic versions and idempotency keys. Transition,
access, risk, fill and correction histories remain append-only or completely
recoverable. Immutable Artifact content is referenced by identity and hash and
is never copied into SQLite as a competing authority.

## Operational Research Bridge

The bridge combines a verified Phase D DailyLoop Artifact with a typed
`SupplementalResearchEvidenceBundle`. The supplemental bundle owns no new raw
facts; it packages exact immutable references to the SourceManifest, PIT Theme
Membership, ETF/Theme mappings, Theme, Capital and Symbol observations, their
content hashes, DecisionTime, AvailabilityTime, DataEligibility, missingness
and reason codes.

The adapter verifies both inputs, rejects late or mismatched evidence, reuses
the existing PIT Universe and Eligibility snapshots, and produces the existing
`ResearchInputBundle` without adding a LIVE evidence kind or increasing
DataEligibility. Missing Theme, Capital or mapping evidence is a closed
failure. Repeated commands resolve to the same content-addressed Research
Artifact.

## Delivery and verification

Each Phase 0–7 is a separate semantic checkpoint commit. Tests are written at
the owning seam before implementation and include tamper, time leakage,
idempotency, optimistic conflict, restart recovery, state transition, replay
and compatibility cases. Every phase runs focused tests plus the repository
quality gate. Current State, Capability Matrix, Gap Register, WP-PDL and the
delivery audit are updated only for observed implementation facts.

## Non-claims

This design does not approve a Path profile, Risk limit, Position size, Theme
concentration, model promotion, formal provider qualification or live trading.
Manual fills become position evidence only after explicit operator recording;
plans, theses and simulated executions can never create actual positions.
