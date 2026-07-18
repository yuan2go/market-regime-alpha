# Xuntou PIT Validation Export Runbook

Run this only in an authorized Windows/MiniQMT/XtQuant environment.

1. Run `tools/xuntou/probe_xtquant_pit_capabilities.py` and retain its JSON output.
2. Verify account entitlement and first-party documentation for every required evidence domain.
3. Invoke `tools/xuntou/export_pit_validation_bundle_v4.py` with explicit dates, symbols file,
   immutable raw-output root, and status output.
4. Preserve each raw provider response separately and hash its exact bytes before normalization.
5. Run the V4 preflight. Do not edit qualification fields or substitute public-source evidence.

On a machine without XtQuant, the exporter returns `EXTERNAL_XTQUANT_RUNTIME_REQUIRED`. If XtQuant
imports but required semantics/entitlements remain unverified, it returns
`INSUFFICIENT_PROVIDER_CAPABILITY`. It does not create mock data or a normalized research bundle.

The current repository implementation intentionally stops at this boundary until the authorized
runtime can prove the required capabilities. Any future API calls must be added only after their
first-party evidence and normalized field semantics are recorded.
