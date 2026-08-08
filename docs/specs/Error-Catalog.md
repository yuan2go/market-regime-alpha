# Phase D Error Catalog

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Shared machine-readable validation and operational error codes  
> **Owner:** Research Artifact and Operations domains  
> **Last Updated:** 2026-08-06
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Contract-Conventions.md, README.md  
> **Code Evidence:** DESIGNED_ONLY; path:scripts/check_docs_links.py

| Code | Name | Meaning | Default severity |
|---|---|---|---|
| `DOCON-001` | `MISSING_REQUIRED_FIELD` | Required key absent | ERROR |
| `DOCON-002` | `INVALID_TYPE` | Value does not match declared type | ERROR |
| `DOCON-003` | `INVALID_ENUM` | Unknown enum value | ERROR |
| `DOCON-004` | `NULLABILITY_VIOLATION` | Null/absence violates field or state rule | ERROR |
| `DOCON-005` | `REFERENCE_NOT_FOUND` | Referenced aggregate/artifact is unavailable | ERROR |
| `DOCON-006` | `TIME_ORDER_VIOLATION` | Event/availability/decision time order invalid | BLOCKING |
| `DOCON-007` | `PIT_VIOLATION` | Future information entered a decision artifact | BLOCKING |
| `DOCON-008` | `IDENTITY_MISMATCH` | ID/hash does not match canonical payload | BLOCKING |
| `DOCON-009` | `EVIDENCE_LEVEL_INFLATION` | Output authority exceeds an input | BLOCKING |
| `DOCON-010` | `SCHEMA_VERSION_UNSUPPORTED` | Consumer cannot interpret major version | ERROR |
| `DOCON-011` | `DUPLICATE_IDEMPOTENCY_KEY` | Command conflicts with prior payload | ERROR |
| `DOCON-012` | `AUTHORITY_VIOLATION` | Non-owning domain attempted a write | BLOCKING |
| `DBAUTH-001` | `DATABASE_UNAVAILABLE` | Required PostgreSQL authority cannot be reached; no fallback is permitted | BLOCKING |
| `DBAUTH-002` | `POSTGRESQL_OPERATION_FAILED` | PostgreSQL authority operation failed and was rolled back | ERROR |
| `DECSYS-001` | `DECISION_INPUT_BLOCKED` | Decision lineage or authority validation failed closed | BLOCKING |
| `DECSYS-002` | `DECISION_WINDOW_BLOCKED` | Decision preview/finalization violated the decision-window contract | BLOCKING |
| `DECSYS-003` | `DECISION_CONFLICT` | Decision CAS, idempotency, Final uniqueness, Lease or fencing rejected a write | BLOCKING |

Errors are append-only operational evidence. They are not silently converted to empty values or fallback predictions.
