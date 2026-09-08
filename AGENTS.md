# Agent execution contract

Market Regime Alpha is an A-share research and human decision-support system.
Research predictions and Portfolio proposals are not orders, Fills or Positions.

## Authority

Read [documentation navigation](docs/README.md), Architecture, Authority Map,
Current State and Roadmap, then trace the affected code, schema and consumers.

Normative authority order: latest explicit user decision; enduring business and
safety invariants below; current documents listed in `docs/README.md`.
Archived plans and evidence are provenance, never active instructions.

Implementation fact authority order: executable call chains; PostgreSQL schema
and owner queries; tests actually executed; reproducible runtime evidence;
documentation. A declaration or passing fixture cannot establish deployment.

## Invariants

- Reuse the existing Runtime and composition root. PostgreSQL owns durable
  state; its clock, atomic admission, lease and fence govern execution. Process
  supervision only wakes and drains work. No availability-selected Authority.
- Each business fact has one owner. Cross-owner reads use exact identities and
  read ports; writes use owner commands. DTOs, policies, reports and inventories
  cannot promote authority. Artifact bytes must match PostgreSQL hash/bindings.
- Universe → Eligibility → Dataset → Candidate precedes Decision commitments,
  Context and Forecast. Same-generation outcomes cannot change frozen inputs.
  Outcome alone owns market labels; Evaluation owns metrics; Report projects
  reconciled results. Feedback and model training respect knowledge cutoffs.
- Account changes require observed Fills or explicitly authorized typed basis
  events. Risk rejection cannot be bypassed. Target horizon is not holding time;
  hypothetical episode economics is not continuous-account NAV or actual P&L.
- Preserve complete populations, exclusion reasons and negative/inconclusive
  results. Missing, UNKNOWN, abstention and NOT_ESTIMABLE are meaningful states;
  never replace them with zero, a probability, invented data or implied success.
- Never infer calendar sessions from weekdays, backdate knowledge/publication,
  silently substitute Providers, or claim PIT/finality without exact evidence.
  Released schemas, historical identities and evidence retain their bytes and
  meaning. Corrections use the owner's explicit revision/supersession contract.
- Engineering evidence does not confer Provider, Alpha, Model, broker or
  Production qualification. Do not change research semantics outside scope.

## Work and validation

- Inspect worktrees, status and ancestry first. Work on an isolated branch;
  preserve unrelated changes. Never touch or stage `.idea/modules.xml`.
- Fetch, switch, destructive Git actions, push, PR, merge, operational upgrades,
  service changes and external communications require task authorization.
  Never reset, clean, stash or rewrite history to clear someone else's work.
- Operational databases are not test fixtures. Use an explicitly disposable
  database for destructive tests. Operational writes require exact identity,
  backup, disk and single-writer preflight; upgrades use registered bundles.
- Keep Provider/Artifact I/O and expensive computation outside business write
  transactions. Recheck input identities and active fences before atomic
  result/Receipt/Audit/Runtime completion. Reconcile unknown effects before retry.
- Use locked dependencies: `uv sync --frozen --extra dev --extra postgres`.
  Every Python command uses `uv run`. Follow [Development](docs/Development.md)
  for focused and full gates; never skip failures, weaken assertions or add a
  fallback to get PASS. Delete tests only with an explicit contract disposition.
- Before each coherent local commit inspect staged/unstaged scope and run
  `git diff --check`. Exclude credentials, personal configuration and artifacts.
- Report commands as PASS / FAIL / BLOCKED / NOT_RUN at their verified revision.
  Distinguish implemented, wired, tested, runtime observed, research qualified
  and production admitted. State unresolved gaps without upgrading old evidence.
