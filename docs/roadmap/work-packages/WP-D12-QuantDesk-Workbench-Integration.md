# WP-D12 — QuantDesk Workbench Integration

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D12  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Expose research, daily decision and review workbenches through typed read/query APIs and controlled human commands.

## Bounded contexts

- Application and QuantDesk

## Dependencies

- stable Phase D APIs from D4–D10

## Inputs

- authoritative artifacts/read models
- manual decision/proposal approval commands

## Outputs

- Research Workbench
- Daily Decision Workbench
- Review Workbench
- typed API client

## Expected files/modules

- src/market_regime_alpha/application/**
- external QuantDesk repository/integration adapters
- tests/application/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- WorkbenchReadModel
- TaskRequest
- ApprovalRequest
- ManualDecisionCommand

## Code work

- read projections
- pagination/filtering
- manual capture
- approval workflow
- artifact drill-down

## Tests

- UI cannot recompute model
- stale projection warning
- command idempotency
- source IDs visible
- authorization boundary

## Acceptance conditions

- three workbenches available
- all values trace to artifacts
- no provider credentials/model logic in UI
- manual commands validated by domains

## Evidence required

- API contract tests
- UI flow recordings
- authority-boundary review

## Risks

- logic duplication
- stale cache
- UI treated as account truth

## Stop conditions

- required APIs unstable
- UI needs direct DB/provider access
- business logic cannot stay server-side

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Retires Legacy dashboard as current authority after parity and evidence; historical tools remain available.

## Documentation updates

- docs/architecture/07-QuantDesk-Integration-Boundary.md
- docs/status/Capability-Matrix.md
- docs/README.md

## Explicit non-goals

- model implementation in UI
- broker credential ownership
- automatic execution
