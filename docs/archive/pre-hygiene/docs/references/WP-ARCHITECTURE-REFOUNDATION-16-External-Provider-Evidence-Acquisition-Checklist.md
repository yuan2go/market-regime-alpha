# WP-16 External Provider Evidence Acquisition Checklist

> **Status:** CURRENT_STATUS
> **Authority:** Re-entry evidence request checklist; never Provider Qualification Authority
> **Owner:** Market & PIT
> **Frozen:** 2026-09-02

Use this checklist before commissioning an adapter. Do not request credentials in
documents, tickets, chat logs, Artifacts, or database rows; arrange them through
the existing secure configuration channel.

## Provider and Product identity

- legal Provider identity and exact Product/entitlement name;
- API/SDK/runtime version and supported operating environment;
- versioned data dictionary and response schema;
- market, instrument, timeframe, price-basis, retention, and redistribution
  scope;
- stable request and source revision/snapshot identity.

## P0 — required before engineering starts

### Historical availability/publication

- Does every historical observation or snapshot expose its exact
  `source_available_at` or publication timestamp?
- Is that timestamp the availability of the exact source revision, rather than
  event time, download time, API request time, database load time, or the
  consumer's `known_at`?
- Is the timestamp retained for historical revisions and available through API,
  export, header, change feed, or a versioned vendor attestation?
- What timezone, precision, delayed/publication window, and correction behavior
  apply?

### Revision history and finality

- What is the stable snapshot/revision ID?
- Are preliminary, corrected, superseded, and final states distinguishable?
- Does the Product expose correction lineage and each revision's publication
  time?
- What event marks `FINAL`, and can a final record later change?
- If later change is possible, how is it versioned and announced?
- Can historical revision bytes be re-requested or exported exactly?

Both sections require direct recorded evidence. A marketing statement, current
download, repeated equal response, or undocumented support answer is
insufficient.

## P1 — historical scope integrity

- exchange-specific trading sessions and exceptional closures;
- listing, delisting, suspension/resumption, and ST/special-treatment history;
- stable security identifiers and symbol-change history;
- historical index/universe membership with effective and publication times;
- correction/version semantics for every calendar/membership/status product.

Today's membership or weekday inference cannot reconstruct history.

## P2 — frozen Target coverage

- exact DecisionTime reference timeframe and bar boundary;
- raw/unadjusted versus forward/backward-adjusted basis and corporate-action
  behavior;
- all required observation sessions and intra-session checkpoints;
- complete Outcome path, including suspension/gap/conflict representation;
- request limits, archive depth, retention, and reproducible export shape.

## Evidence package requested from the vendor

- versioned official contract/data dictionary;
- redacted entitlement confirmation without secrets;
- one small real raw response for each required Product;
- exact response headers and Provider timestamps;
- one documented correction/revision example, including predecessor and final
  state;
- one historical calendar/membership/status example;
- one Decision-reference plus full Outcome-path example;
- vendor contact or contract section that answers unresolved publication and
  finality questions.

Only after this package makes both P0 requirements directly verifiable may the
team design a typed adapter, Product revision, or multi-Product relational
binding. Until then, adapter/schema/Protocol work remains prohibited.
