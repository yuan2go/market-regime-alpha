# ADR-007 — Controlled Decision-Time Operation and Immutable Evidence Archive

> **Status:** CURRENT_ARCHITECTURE
> **Date:** 2026-08-05
> **Decision Owners:** Market Regime Alpha maintainers
> **Related:** ../15-Controlled-Decision-Time-Operation.md

## Context

The exploratory DailyLoop retains a fixed Smoke Universe, Legacy Features and
B0/B1 flow. Extending it would mix historical compatibility with the canonical
Feature/Signal authority and would not solve deadline, fencing or longitudinal
evidence requirements.

## Decision

Introduce `ControlledDecisionTimeOperationRunner` as a new application
orchestrator. Keep DailyLoop, Feature Run and Canonical Lifecycle repositories
as independent authorities. The parent journal stores only immutable artifact
and child Receipt references. Split daily static Features from Candidate-only
intraday overlays and compose them through `CandidateFeatureViewV2`. Publish a
pending operation package and supersede it with a new settled package after T+1
factual evidence. Index immutable package references in a rebuildable,
append-only SQLite longitudinal index.

Publish the Signal/Path/Entry segment as a separately readable Canonical child
Run Receipt and bind that real identity/hash from the parent journal. Freeze T+1
provider bytes in an exact-file Outcome Source Archive, require its raw hashes
to match the SourceManifest, and reconstruct the Outcome Dataset from that
archive during offline replay.

Use database-enforced leases, CAS and monotonic fencing epochs for Feature and
parent operation claims. Reject post-DecisionTime source data and stop retry at
the hard cutoff. Keep PathForecast without samples and Entry blocked.

## Consequences

- The old 20-symbol Smoke path remains readable but is not the controlled
  default.
- Controlled research uses H6/platform observations plus static canonical
  Features and does not require B0/B1 PredictionRuns.
- Partial Candidate minute failures remain visible and become per-symbol
  `DATA_INSUFFICIENT` Signals; total failure produces a terminal evidence
  package.
- Replay is local and side-effect-free.
- Resume compares frozen input bytes and completed-stage Receipt references;
  immutable history cannot be silently combined with changed evidence.
- This decision does not implement H7, H8 scheduling, H9 validation,
  PostgreSQL, RBAC, frontend, Broker, order or Entry authority.

## Rejected alternatives

- Copying DailyLoop internals into the new runner.
- Recomputing full daily history after 14:55.
- Treating UUID claims as fencing without a monotonic epoch.
- Replacing missing VWAP with daily data, another symbol or zero.
- Updating the pending package in place during settlement.
