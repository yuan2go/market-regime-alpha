# WP-DECISION-01 — Daily Research Decision Closure

> **Status:** ROADMAP
> **Mode:** RESEARCH / MANUAL_DECISION_SUPPORT

## Objective

Close the PostgreSQL-authoritative engineering chain from Stateful Research
outputs through a windowed Daily Summary, Manual Account observation,
Fill-derived reconciliation, research Portfolio proposal and independently
reloaded Risk decision.

## Invariants

- 14:30–14:55 Asia/Shanghai is an inclusive window, not a point schedule;
- every input is explicitly identity/lineage bound and As-of constrained;
- account observations and corrections are append-only;
- only observed valid Fill authority can change Position;
- unresolved reconciliation blocks OPEN/ADD;
- Portfolio is research advice and cannot create execution behavior;
- Independent Risk reloads PostgreSQL authority inputs by ID;
- expired claims and fencing tokens cannot write;
- original Final is unique and immutable; Correction is another version;
- no uncalibrated probability is emitted;
- Entry, Order, Fill, Position and Broker authority do not expand.

## Migration 025

Migration 025 adds ten append-only authority tables covering Manual Account,
Reconciliation, Daily Summary/Candidates, Research Portfolio/lines, Independent
Risk and Decision Runtime receipt. Domain decisions remain in application code;
database triggers only enforce append-only integrity.

## Non-goals

No Web page, model/threshold change, economic validation, Formal PIT/OOS,
automatic promotion, Shadow qualification, QMT/PTrade/XtQuant, Broker or
automatic execution is included.
