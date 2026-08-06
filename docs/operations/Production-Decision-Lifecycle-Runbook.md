# Production Decision Lifecycle Runbook

> **Status:** CURRENT_SPECIFICATION
> **Mode:** RESEARCH / MANUAL_DECISION_SUPPORT
> **Database:** PostgreSQL 16 authority only
> **Execution authority:** none

## Authority boundary

This lifecycle is operated through Application Services and CLI adapters. It
does not grant Entry, Order, cancellation, Fill, Position mutation or Broker
authority. A recommendation, Risk result or ManualTrade intent is not a Fill;
only an observed valid Fill can change the Fill-derived Position.

All durable commands require an explicitly configured PostgreSQL authority.
Database unavailability stops the operation. No file database, compatibility
backend or automatic fallback is available.

## Current operating procedures

- database bootstrap, migration, recovery and isolated replay:
  [PostgreSQL Authority Runbook](PostgreSQL-Authority-Runbook.md);
- Continuous Runtime and fencing:
  [Continuous Research Runtime Runbook](../runbooks/Continuous-Research-Runtime.md);
- State and Dynamic Pool child:
  [Stateful Research Runtime Runbook](../runbooks/Stateful-Research-Runtime.md);
- Daily Summary, Manual Account, Reconciliation, Portfolio and independent
  Risk: [Daily Decision System Runbook](Daily-Decision-System-Runbook.md).

## Incident response

Stop the affected operation and preserve evidence when PostgreSQL, an Artifact
Reader, identity/lineage validation, Claim, Lease, fencing, CAS, Fill ledger or
account reconciliation fails. Resume through the owning Journal only. Never
repair an incident by overwriting an immutable decision, fabricating a trade or
Fill, editing a Position, selecting an unbound latest record, weakening a
blocker, or switching databases.

Corrections append a new version with actor, reason and predecessor identity.
Forward database repair is a new reviewed migration. Production restore,
authenticated operators, sustained Shadow operation and Broker integration
remain separate future admission work.
