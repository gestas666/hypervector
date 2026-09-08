# SNDK historical exit-clock qualification

Hypothesis `v89_sndk_opening_exit_clock_qualification_20260908_v1`.
Research only; no live strategy, parameter, deployment or process changes.
The sealed September 8–22 prospective experiment remains unopened.

## Fixed question and selection

Qualify the two largest clock drivers from the completed registered cash-open
attribution study: SNDK short `xyz:SNDK|19`, August 6 2026 13:30 UTC, and long
`xyz:SNDK|20`, August 7 13:30 UTC. They explain $51.526027 of the $79.617635
opening-attribution sensitivity. This is selection for measurement diagnosis,
not an independent economic sample or a fitted strategy experiment.

The original adverse short stop is 1243.7680511249996 and liquidation threshold
1271.1701587573423. The adverse long stop is 1285.269009375 and modeled
liquidation threshold 1248.9692660171054. Its full-fee liquidation threshold
1250.0932259605263 is a declared sensitivity, not a pure fee adjustment.
Preserve original trade IDs, quantities, entry prices and whole-lifecycle results.
Treat original engine rows as simulated positions, not actual account orders.

Existing inventory found one complete SNDK L2 bundle for August 6 13:00–14:00 UTC;
no overlapping price/trade archive was found in the two standard SNDK vendor
directories. DuckDB's archive_bundles has no overlapping registered bundle.
This establishes a bounded inventory result, not absence of all possible data.

## Acquisition fixed before examining finer price outcomes

Use route-family-correct HIP-3 clients and only the vendor credential in a
private mapping. Preserve raw envelopes, vendor request IDs, manifests, exact
bytes/hashes and continuation status. Never print credentials or load a signing key.

- Acquire sampled mark/oracle/mid context for each date, 13:29–13:46 UTC,
  at most five pages of 1,000 observations.
- Reuse the verified August 6 hour of native 20-level books; acquire August 7
  13:29–13:46 books with at most five pages of 1,000 observations.
- Acquire public trades for each date over 13:29–13:45 UTC, partitioned into
  sixteen fixed one-minute requests, each capped at ten pages of 1,000 raw
  participant rows. Retain truncated bundles explicitly. Do not infer full-bar
  extrema or coverage if any required partition remains incomplete.
- Do not expand acquisition merely because results are unfavorable. A failed
  or incomplete boundary identifies a concrete additional-data requirement.

These small windows supplement existing registered 15-minute OHLCV and the
original raw engine report. Verify current venue documentation that stops and
liquidations use marks; this does not establish historical feed completeness.

## Measurements and interpretation

Reconstruct normalized rows from raw responses and compare them to publications.
Verify identity, bounds, monotonic clocks, duplicates, missing marks, continuity
and boundary gaps. Preserve distinct public trade IDs sharing a millisecond.
Compare observed public-trade OHLC with the registered 13:15 and 13:30 candles
only where the acquired trade coverage permits it; no fabricated pre-open bar.

For each frozen threshold, report the last sampled non-touch and first sampled
touch in the acquired window, both relative to 13:30 UTC, all later touches,
and separate mark, oracle, mid and public-trade ranges. A threshold may have
been touched before this short window; do not call the local first sample the
first lifecycle trigger. Mark gaps cannot prove continuous absence of touches.
Long touches are price <= threshold; short touches are price >= threshold.

For the long, compare observed stop and liquidation touch timestamps. A sampled
stop touch earlier than liquidation supports sequence qualification, but does
not prove that an actual stop would fill before liquidation. Same-sample touches,
missing marks or gaps preserve ambiguity. Candle extrema or public prints alone
cannot establish venue trigger order. Original engine priority is liquidation,
then stop, then target when bar extrema touch multiple barriers.

Use existing depth-walk arithmetic to report full modeled closing-quantity
capacity at books bracketing the first observed stop and liquidation touches.
These are hypothetical visible executions with explicit book ages and gaps, not
client fills. Do not rewrite portfolio PnL, optimize stops or fit session filters.

## Validation, disposition and next step

Tests must cover long/short threshold direction, exact/between-sample touches,
same-timestamp public prints, missing observations, out-of-window data,
nonmonotonic/duplicate clocks, and no-touch evidence. Verify original source
hashes and raw normalization; independently recompute key threshold comparisons.
Freeze source and replay the report from its archive.

High confidence is permitted for validated arithmetic and exact source identity.
Confidence in executable policy or causal improvement remains low without full
event ordering, execution evidence and a complete chronological policy replay.
Changed source hashes, unresolved normalization or contradictory finer events
falsify the corresponding measurement. Retain a qualified sequence finding or
record the exact unresolved coverage. Then select one next investigation based
on the new evidence, without reopening rejected ideas or the sealed experiment.
