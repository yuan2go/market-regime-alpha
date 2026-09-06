# Research Economics Correctness 01

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Bounded research economics contract under the canonical Evaluation owner
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-06
> **Code Evidence:** `src/market_regime_alpha/research_qualification/domain/episode_economics.py`, `src/market_regime_alpha/research_qualification/domain/episode_formula.py`, `tests/refoundation/research_qualification/test_episode_economics_postgres.py`

Frozen supported-model contract; final qualification is pending.

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

## Review correction checkpoint

V2 requires an unfiltered current-specification Validation parent for one arm.
The expected parent is derived from every participating Validation EVALUATION
session before checking exact Decision/Target commitments and complete Portfolio
line rosters. FIT, fold-filtered and Context-filtered partitions cannot claim V2
path economics. Generic prerequisite fold Evaluations retain their declared
non-V2 semantics; V2 belongs to the aggregate requirement.

Optional `episode_slice_kind`/`episode_slice_key` select ALL, an exact FOLD, or
TIME_MONTH (`YYYY-MM`, canonical Decision TradingSession date). ALL is the default
and forbids a key. The entire parent closes before whole episodes are selected;
an incomplete excluded episode still rejects completion. Context/regime selectors
are unsupported. Monetary numerators are summed before division by the independent
initial capital times the selected episode count. Sample floors count episodes,
including explicitly funded cash-only episodes, rather than instrument rows.

Outcome checkpoint facts cross an Outcome-owned typed read port after the
Evaluation input UoW closes. Request-local reuse includes revision and checkpoint
identities. Existing full Outcome reconstruction remains the owner verification;
its per-revision query cost requires representative measurement. The write UoW
rechecks the exact parent, source facts, complete line roster, Outcome price guard
and live Runtime fence before atomically writing results. V2 reconciliation checks
financial source values, classification and cost child rosters and their hashes
using shared writer serialization, with no second financial algorithm. Historical
V1 formula, result and report serialization remains conditional and unchanged.

Exit costs must also be payable from remaining cash and sale proceeds. A negative
final cash balance is `INSUFFICIENT_CASH_FOR_EXIT_COSTS`, never implicit borrowing.

## Result integrity and longitudinal acceptance continuation

The resumed main is `58640732b1c51ccec004dc574d3df790ccc4994d`, with the same
tree `a15ab010cc0df4e12ce2b808c2d0a5c8a028431e` as the retained local `6e9a0e16`
implementation. Its completed 4,043-case local regression is prior evidence;
new result-integrity and multi-episode acceptance requires a new exact revision.
No new economics package, model, formula version or schema migration is introduced.

Result reconciliation derives expected V2 metrics from the EvaluationRun's frozen
Protocol rather than filtering actual results through their possibly damaged
formula references. Writer and verifier share one typed record for all eleven
explicitly written business fields: result/run/protocol-metric/protocol identities,
metric state, decimal/boolean values, episode count, acceptance state, reason and
content hash. Actual fields must match the recomputed record even when the saved
hash has not changed. Child observations must bind the verified result identity.
Database-default `created_at` is lifecycle metadata, not a newly invented part of
the historical financial content hash.

Acceptance adds legal-domain root-field corruption, preserved child/input failure
cases and a small Generic PostgreSQL path spanning multiple Validation episodes,
folds and months. Independent arithmetic must cover cash and traded episodes,
shared capital, complete-parent then whole-episode slices, rejected incomplete
parents, and deterministic Report/resume/replay. Negative fixtures are isolated
from the positive result and restored exactly. Final full regression, historical
copy replay, installed-wheel smoke and measured resource evidence remain required.

The representative restored-input measurement retains the frozen 32-revision,
three-metric control. Before optimization its local acceptance budgets are 600 SQL
calls, one second each for input preparation and final write UoW, three seconds
total completion, and 200 MiB peak process RSS. These are engineering workload
budgets, not strategy thresholds or unbounded campaign scaling claims.

The complete-parent query also reloads the actual DecisionRun root, its Dataset
binding and OPENED state; a surviving Backtest binding row cannot replace a
missing Decision Authority. Known canonical-input/Outcome reconciliation failures
become explicit integrity mismatches, never a partial result or empty success.

The longitudinal fixture predeclares four Validation episodes over two folds:
January 28/29 and January 30/February 3. A fixed line Risk cap rejects two
positive-weight proposals; the other two episodes trade independently funded
capital through explicit +10%/-10% marks. The shared parent contains 68 canonical
members (2/32/32/2), while economic sample denominators are 4 overall, 2 per fold,
3 in January and 1 in February. Every Report value, count, result identity and
fold/month selector is checked against independent expected values. The negative
fixture has only a February selector, so an ALL metric cannot conceal premature
filtering of a broken January member. Temporary corruptions restore exact raw
PostgreSQL records, preserving numeric representations and whole-schema hashes.
