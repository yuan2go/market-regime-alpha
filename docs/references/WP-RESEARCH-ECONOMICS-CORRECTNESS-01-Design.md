# Research Economics Correctness 01

Status: implementation contract; qualification is pending.

The execution-time fetched main is `32bcb2922e6ced805c51f320e5f5657521f8cf14`,
tree `dddfe02092562989037140f8aff88250117be627`. The original worktree remains
on `10689a4db772be5a546a64448fcc6f39f6988412`; its unrelated IDE modification
is untouched. Local R2 checkpoints exist and are merged in this baseline.
No existing economics correction branch or commit was found in local refs.
The frozen R2 campaign, its worktree and operational database are not modified.

## Chosen model and evidence boundary

V2 supports **independent closed hypothetical mark-execution episodes**. Each
Decision's complete allocation roster receives one explicitly declared capital
amount; each arm is an independent experiment, never pooled account capital.
Every episode starts in cash and ends with an explicitly declared liquidation.
Subsequent episodes receive the same independent capital, not prior proceeds.
Continuous accounts, opening holdings, carry-forward, partial rebalancing,
sell-only opening inventory, and overlapping capital occupation are rejected.
This choice matches the existing checkpoint Outcome facts. A continuous model
would require an additional, independently justified valuation/corporate-action
contract; changing previous weights alone cannot supply it.

Decision information cutoff/proposal precedes the explicitly frozen entry
checkpoint close. A different explicitly frozen exit checkpoint close follows
entry. Neither Decision reference nor Target horizon selects a simulated fill.
Only exact canonical Outcome observations supply prices. Historical information
may be recorded later, under the existing exploratory dual-clock contract, but
both checkpoint facts must be known by the Evaluation acquisition cutoff.

Execution is explicitly **ASSUMED_CHECKPOINT_CLOSE_FRACTIONAL**: a hypothetical
mark transaction, not demonstrated exchange executability, an A-share trading
rule simulation, or an actual Fill. It assumes fractional units, unconstrained
liquidity, and same-session raw prices without a corporate action. It cannot
support broker, intraday resale legality, suspension, price-limit, volume or
corporate-action claims. Recorded gaps/unavailable or incompatible price/source
facts reject calculation; missing observations never compress a return series.
Different-session prices are rejected until a corporate-action contract exists.

Risk AUTHORIZED permits the hypothetical buy. REJECTED, UNKNOWN and NO_ACTION
leave the episode in cash. An existing position cannot be passed to this model;
rejecting a proposal never acts as an implicit liquidation instruction.
Universe membership at a later Decision does not select the exit: the original
episode's frozen Outcome checkpoint does. No pool-exit shortcut exists.

Weights allocate initial-capital notional. Units round down to 18 decimal
places; notional and side-specific bps fees round to currency cents, half even,
under explicit Decimal precision of at least 34. Cash must fund both notional
and fees or the episode is rejected. V2 requires explicitly zero slippage and
minimum fees; nonzero assumptions are rejected. These are versioned research
assumptions, not assertions about current market fee regulations. Exit fees use
actual exit notional. Entry cash + entry holdings + buy fees reconcile to
capital; final cash reconciles to capital + gross profit - all fees.

The full episode path precedes slicing. Slices may select whole episodes only;
partial capital rosters and duplicate samples are rejected. Fold state always
resets through independent capital. Available metrics are episode gross/net
return, gross two-sided traded-notional/capital, entry exposure and episode win
rate. Arithmetic episode means are not continuous NAV. Cumulative return,
annualization, volatility, Sharpe, Sortino, Calmar and drawdown are rejected for
this model rather than mislabelled as account statistics.

## Authority, identities and implementation steps

1. Preserve an independent rejected-40%-then-approved counterexample against the
   baseline. Add hand-calculated public pure-core tests, then implement the
   typed deterministic episode core. Keep negative logs.
2. Freeze a V2 formula/parameter identity, exact entry/exit checkpoint identities,
   cost roster and economic policy before Outcome access. Preserve V1 and
   formula-less historical result bytes and meaning. Their affected economic
   values cannot qualify V2. The old financial transform becomes a private pure
   historical decoder; Repository has no financial state algorithm.
3. Load exact Outcome-owned facts and complete allocation rosters; compute
   outside the write transaction; revalidate inputs and live fence before atomic
   Evaluation/Receipt/Audit/Runtime completion. Existing Evaluation owns output;
   Report projects reconciled results. No Fill/Account/Position writes or schema
   byte rewrites. Reuse the existing typed formula and source persistence.
4. Exercise hand arithmetic, unsupported cases, complete-path slicing,
   determinism, PostgreSQL idempotency/concurrency/fence/rollback/unknown commit,
   historical replay and report projection. Use a fresh isolated database and
   optionally a fresh restore of sealed R2 evidence; never the operational DB.
5. Freeze implementation and run clean exact-SHA full regression, static,
   architecture/docs, migration, build and wheel smoke gates. Record all actual
   outcomes in a new immutable Verification. WP18Q remains independently BLOCKED;
   neither its large campaign nor a future window is a dependency of this work.
