# Hypervelocity Live Integrity and Order-Book Archive Plan

**Goal:** Make the backend the single execution/telemetry authority, prevent historical catch-up or incomplete candles from trading, archive the same live L2 snapshots used by shadow execution, and keep the TUI a faithful read-only projection.

## Verified problems

- The REST daemon processes every candle after the cached warm-up timestamp. If the cache is stale, historical catch-up candles can create fills and retroactive funding events.
- The TUI derives active position from the final ledger row. A later book row has no position fields, so it can incorrectly render an open backend position as flat.
- Live book observations are written to the decision ledger at five levels, but the existing replay-compatible 20-level archive is only populated by a separate recorder command.
- Hypervelocity's model is configured `off`, despite the intended annotation-only policy.
- The documented strategy permits rapid re-entry in 1–5 minutes. A long cooldown would be an unfaithful execution gate; the minimum must remain one completed 1m bar and be explicit.

## Implementation and validation

1. Add causal live-feed partitioning.
   - Treat candles whose close is at or before daemon activation as warm catch-up.
   - Process catch-up through `PaperSession.warm_up`, never `on_bar`.
   - Trade only completed candles whose close is after activation.
   - Regression test stale cache, incomplete current candle, no historical fills, no retroactive funding, and the first genuine live candle.

2. Integrate durable L2 archive into the backend poll.
   - Reuse the exact `BookSnapshot` already fetched for fill telemetry; do not make a second network request.
   - Append up to 20 bid/ask levels to `data/cache/book/<SYMBOL>_l2_<UTC_DAY>.jsonl`.
   - Include archive status/path/depth in `session_start` telemetry.
   - Unit test serialization and round-trip through `load_l2_jsonl` with network mocked.

3. Make position/equity telemetry authoritative.
   - Add mark-to-market position, realized PnL, unrealized PnL, and equity fields to per-bar regime telemetry.
   - Change the TUI parser to select the newest row carrying position state rather than the newest row of any type.
   - Add Rust regression tests where a book row follows an open-position regime row.

4. Expose faithful runtime policy.
   - Configure metalabel mode as `observe` only; it may annotate but not filter or scale.
   - Add explicit one-completed-bar re-entry cooldown and report it in effective configuration.
   - Report lookback, order-book archive, and target basis in the TUI configuration menu.
   - Validate one position per symbol remains enforced and range never opens a trade or force-closes an existing trade.

5. Verify end to end.
   - Run focused Python and Rust tests first, then all non-network Python tests and the TUI crate tests.
   - Capture one real public Hyperliquid L2 snapshot through the integrated storage function and reload it with the replay loader.
   - Inspect the produced JSONL without printing secrets. Shadow mode must show `submitted=false`, `place_attempted=false`, and no live client construction.

## Success criteria and rollback

- No fill/funding rows may be timestamped before daemon activation.
- No incomplete candle may be processed as live.
- A later book row cannot erase the TUI's active backend position.
- Each successful live L2 poll appends one replay-readable 20-level snapshot.
- Model output is annotation-only and cannot reject or resize a trade.
- Reverting the implementation commit restores the prior behavior; existing audit logs remain untouched.

## Known uncertainty

The external analysis supports a gross 8% margin target and 1–5 minute re-entry, but it cannot prove every hidden behavior of the original system. Direct comparison against fresh real-strategy logs is the falsification test for these assumptions.
