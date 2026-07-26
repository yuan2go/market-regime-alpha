# Phase D Contract Conventions

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Shared encoding, identity, nullability, persistence and API conventions  
> **Owner:** Research Artifact domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Error-Catalog.md, ../architecture/03-Research-Artifact-Architecture.md  
> **Code Evidence:** DESIGNED_ONLY; path:scripts/check_docs_links.py

## Primitive types

| Type | Encoding |
|---|---|
| `string` | UTF-8, Unicode NFC |
| `date` | `YYYY-MM-DD` |
| `datetime` | RFC3339 with numeric offset; canonical hash form is UTC `Z` |
| `decimal-string` | base-10 plain notation, no exponent, no thousands separator |
| `number` | finite JSON number; NaN/Infinity forbidden |
| `boolean` | JSON true/false |
| `array[T]` | ordered unless the field explicitly says sorted unique |
| `object` | closed keys unless an extension namespace is declared |

## Canonical identity algorithm

1. Select the specification's declared identity fields.
2. Preserve the semantic difference between absent and explicit null.
3. Normalize strings to Unicode NFC.
4. Normalize datetimes to UTC RFC3339 with microseconds removed unless contract requires them.
5. Normalize decimal strings by removing redundant leading/trailing zeroes while preserving exact value.
6. Sort object keys lexicographically.
7. Preserve array order except fields declared as sets; set fields are de-duplicated and sorted.
8. Serialize as compact UTF-8 JSON with no insignificant whitespace.
9. Compute SHA-256.
10. Prefix the digest with the aggregate-specific ID prefix.

## Versioning

- Patch: documentation/validation clarification with identical semantics.
- Minor: backward-compatible optional field or enum extension behind version negotiation.
- Major: changed meaning, required field, identity payload or null rule.
- Producers declare one schema version; consumers reject unsupported major versions.

## Persistence

PostgreSQL stores indexed metadata plus immutable `payload_json`. Object storage mirrors the canonical JSON. Neither representation may change the identity payload.

## API behavior

- Read APIs return canonical IDs and source references.
- Computed aggregate creation is internal; public POST is validation-only unless the record is human-entered.
- `ETag` equals content hash.
- Errors use [Error Catalog](Error-Catalog.md).
- Pagination is cursor-based and stable against later inserts.

## Security and privacy

Account scope IDs are pseudonymous. Credentials, tokens, raw account numbers and broker secrets never enter Phase D artifacts.
