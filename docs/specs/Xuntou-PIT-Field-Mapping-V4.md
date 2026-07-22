# Xuntou PIT Field Mapping V4

> **Contract:** `xuntou-pit-validation-field-mapping-v4`

This specification is constrained by the repository's first-party evidence note. A documented API
name is not proof of historical availability, finality, entitlement, or PIT correctness.

| Domain | Required canonical evidence | Current official-evidence status |
|---|---|---|
| Security master | effective-dated identity, listing/delisting, `available_at`, completeness | native identity/listing fields documented; historical revision/PIT unverified |
| Universe | dated members/non-members, source, availability, completeness | historical ContextInfo capability documented with limits; complete PIT history unverified |
| ST | ST/*ST/PT intervals plus export completeness | historical API documented; PIT publication/revision semantics unverified |
| Suspension | decision-time status and availability | daily `suspendFlag` documented; 14:55 historical status unverified |
| Orderability | quote book, limits, status, observed/available/finalized times | no documented historical orderability fact; remains `UNKNOWN` without full evidence |
| Amount | CNY, yuan, scale 1, per-period native amount and aggregation evidence | raw `amount` documented; exact unit/PIT/finality remains unverified |
| Bars | unadjusted OHLCV/amount plus availability/finality/revision | historical intraday supported; label/finality/revision semantics unverified |
| 10:30 mark | next-session minute path and exact mark rule | raw minute API documented; qualified exported evidence unavailable |
| Path order | complete versioned minute horizon | daily high/low cannot establish event order |

No mapping converts missing ST rows to non-ST, missing suspension rows to tradable, or missing quote
rows to orderable. Current instrument detail cannot be projected backward. `daily close` cannot
replace the next-session 10:30 evaluation mark.

Decision-Time quote evidence is exact-time evidence: `quote_observed_at` must equal the frozen
14:55 `decision_time`. Earlier snapshots are stale and later snapshots are unavailable at the
decision; both derive `UNKNOWN`, even when all book fields are populated.
