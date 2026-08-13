# v25 closed ignored-exit durability acceptance

## Problem restatement

The open-lifecycle observer made provider recipe-exit signals visible while a
trade remained active, but that evidence was not yet durable in the selectable
closed-trade journal. A signal-reference price also cannot be treated as an
executable counterfactual fill because venue acknowledgement, fee, slippage,
and funding evidence do not exist for an order that was never sent.

Acceptance therefore required a report-only closed outcome that preserves the
first ignored signal and its completed-candle path while keeping the actual
venue exit authoritative. It also required every selectable all-time trade to
have an explicit coverage state, including older lifecycles.

Evidence is stored at
`data/logs/research/bidirectional_cohort/v25_closed_ignored_exit_durability_acceptance_20260808T1353Z.json`.
Its SHA-256 is
`a4ba7e028e25241427244693f8359b0cc7ae030f673999f2b95cb7b515e7ca0d`.

## Implemented contract

Each closed lifecycle now carries one of four strict states:

- `observed`: a same-side, post-fill provider exit was ignored and its causal
  completed-candle path reaches the actual venue exit;
- `no_ignored_exit_observed`: the bound policy was `ignore`, but no eligible
  provider exit occurred before close;
- `not_applicable_policy_honors`: the bound policy honored provider exits;
- `unavailable_bound_policy`: legacy evidence cannot prove the bound policy.

The actual exit retains its venue timestamp, price, realized net PnL, fees,
funding, reason, and controller. `counterfactual_signal_exit_net_pnl_usd` must
remain null. Rust rejects execution-bearing contracts, claimed counterfactual
net PnL, partial observed shapes, non-finite actual economics, and disagreement
between the reported continuation and the projected path.

The closed-trade inspector displays the policy, signal count, first reason,
reference and time, entry-relative return, signal-to-actual gross path, actual
exit/controller, actual net/fees/funding, and the explicit warning that the
signal reference is not a venue fill.

## Cache defect found and corrected

The first live sidecar reload upgraded the two current-profile closes but not
the 28-trade all-time archive. The bounded checkpoint cache validated unchanged
fill identity but had no projection-schema identity, so it legitimately reused
old report bytes after the report schema changed.

All-time reflections now publish `history_schema_version=1`. A cached complete
history without that exact value raises `HistoricalProjectionStale`, causing
one full-ledger rebuild before bounded refreshes resume. The live rebuild
produced 28/28 explicit outcomes: 23 `no_ignored_exit_observed` and five
`unavailable_bound_policy`. None claims a counterfactual fill or net result.

## Live isolation and validation

- The execution owner remained PID `37897`, launch count one, and never
  exited. Its run stayed `bidirectional-live-1786182011216` under v25.
- Only `com.hypervector.v25.checkpoint` reloaded. The accepted sidecar PID was
  `69414`; the live state remained `running_consistent` with zero faulted
  assets.
- ETH, SOL, GOLD, and SPCX retained stops `512630700867`, `512630736897`,
  `512544517709`, and `512769547957`.
- Thirty-two focused lifecycle tests passed. The checkpoint/history/CLI group
  passed 57 tests. The complete `hypervector-tui` Rust package suite exited
  with code zero; Ruff and Rust/Python format checks passed.
- The rebuilt production checkpoint parsed in the real monitor. The 80x24
  validation PTY produced the expected minimum-size diagnostic and exited
  cleanly.
- Touched production modules remain within the project 500-line limit.

## Current evidence and uncertainty

No closed lifecycle yet has an `observed` ignored-exit outcome, so there is no
resolved economic comparison. GOLD and SPCX currently have open observed
signals. At the accepted checkpoint, GOLD had seven ignored HA-flip signals
and was `+3.68` bps from its first signal; SPCX had three ignored alignment-loss
signals and was `+0.75` bps from its first signal. Both remain protected and
unresolved.

Confidence is high for lifecycle attribution, cache invalidation, strict
projection, TUI rendering, and execution isolation. Economic confidence is
low. The assessment changes when GOLD or SPCX closes and the journal can pair
the frozen signal path with the actual venue exit and costs. Any lifecycle
losing its outcome during a cached refresh, any non-null counterfactual net,
any execution-owner restart, or a valid current checkpoint failing strict TUI
projection falsifies the mechanical acceptance.
