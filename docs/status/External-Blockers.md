# External Blockers

> **Status:** CURRENT_STATUS  
> **Authority:** External dependencies that cannot be resolved by repository code alone  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-06
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Gap-Register.md, ../runbooks/Xuntou-PIT-Validation-Export.md  
> **Code Evidence:** Xuntou runtime/preflight blocker artifacts

## Xuntou/XtQuant

Required:

- a supported external XtQuant runtime;
- access to the required historical/native fields;
- export of a qualified `xuntou-pit-validation-bundle-v4`;
- explicit validation partition specification;
- provider availability/finality and orderability evidence.

Until provided, status remains `BLOCKED_EXTERNAL_INPUT`; test fixtures cannot upgrade it.

## Historical PIT mappings

Reliable historical theme/industry/ETF membership and time-of-availability data may require licensed or separately qualified sources. Current labels cannot be backfilled silently.

## Public free-data availability

The WP-CRR-01 live two-symbol Tencent smoke attempt timed out during the TLS
handshake before valid Evidence. This is `EXTERNAL_PROVIDER_BLOCKED`, not proof
that public data is generally unavailable and not a reason to substitute a
Fixture as live evidence. A later controlled run must preserve exact request,
response, timing and SourceManifest evidence.

## Broker truth

Actual order/fill/account position synchronization requires a broker/QMT/PTrade environment and explicit future scope. It is not a Phase D prerequisite because manual records are the current authority.
