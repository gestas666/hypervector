# Cohort opportunity and exit-capture instrumentation

Date: 2026-08-04 EDT

## Problem and success criteria

The live review previously emphasized executed wins and losses. That is
insufficient for a lower-leverage, repeatable-edge portfolio because it cannot
separate three different failure modes:

1. the strategy did not identify a move;
2. one entry condition rejected a causally identified move;
3. an accepted trade identified the move but its exit returned too much MFE.

The required output is report-only evidence that preserves the side known at
decision time, does not invent fills or PnL, uses fixed cost assumptions, and
keeps overlapping paths distinct from effective non-overlapping samples.

## Implemented measurement contract

Provider evaluations now carry explicit opportunity-capture summaries at
5, 15, 30, and 60 minutes. The fixed assumptions are 13 bps estimated
round-trip friction and a stricter 26-bps gross robustness hurdle. They were
declared before reading the new summaries and are not fitted thresholds.

An exact one-blocker near miss requires:

- a causal long or short side in readiness telemetry;
- an ineligible provider evaluation;
- exactly one reported blocker;
- a contiguous completed-candle path.

The report distinguishes cost-clearing MFE, robust MFE, close above estimated
cost, and a move that cleared cost intrahorizon but reversed below cost by the
horizon close. Multi-blocker rows remain in the older overlapping blocker
diagnostics and are not counted as one-blocker near misses.

Every accepted closed lifecycle now also has `completed_hold_capture`. It uses
the authoritative entry and exit fills plus only candles fully completed after
entry and before exit. It reports MFE, MAE, realized gross return, MFE capture
ratio, peak giveback, and path coverage. The still-forming entry and exit bars
are not assigned full-bar highs or lows.

The TUI research inspector projects eligible, readiness-only, and exact
one-blocker paths with cost-clear, robust-move, and reversal counts. The closed
trade inspector projects MFE, MAE, gross exit return, capture ratio, giveback,
and completed-bar count. Both remain read-only.

## Initial compatible-history snapshot

At 11:08 EDT, the rolling checkpoint was `running_consistent`, coverage was
complete, and all nine compatible-profile closed lifecycles had resolved hold
capture. This is pooled compatible-profile history, not nine trades from the
current process run.

The two target exits captured 100% of observed completed-bar MFE with zero
giveback because the authoritative exit fill established the observed peak.
The five maximum-hold exits were heterogeneous:

- winning HYPE short: 184.54-bps MFE, 100.95-bps gross exit, 54.7% capture;
- winning BTC short: 102.52-bps MFE, 62.72-bps gross exit, 61.2% capture;
- winning HYPE long: 398.75-bps MFE, 369.89-bps gross exit, 92.8% capture;
- losing BTC long: 48.48-bps MFE, -40.95-bps gross exit, -84.5% capture;
- winning HYPE long: 128.78-bps MFE, 48.62-bps gross exit, 37.8% capture.

This makes maximum-hold timing a plausible improvement axis. It does not show
which causal exit would have captured the peaks, and the sample contains only
five timer exits.

The strongest one-blocker observation was
`range_onset_bidirectional_v1|HYPE` with `awaiting_hourly_sma_cross`: 55
resolved 30-minute annotations, 54 closes above estimated cost, 54 robust-MFE
paths, one reversal, and mean close after estimated friction of +46.35 bps.
However, those dense one-minute annotations collapse to only three
non-overlapping 30-minute windows. It is a candidate-generation clue, not an
edge or promotion result.

For comparison, the same 30-minute range-onset annotation averaged below
estimated cost on BTC, ETH, and SOL. Hulk/HYPE `squeeze_not_armed` resolved 12
30-minute paths with 10 robust MFE paths but mean close after estimated cost of
-2.21 bps. This suggests that some moves occurred but deterministic horizon
capture was not sufficient.

## Confidence, risks, and falsifiers

Confidence in the telemetry mechanics is high: targeted tests, the complete
non-network Python suite, the full Rust suite, and a production checkpoint
projection all passed. A missing completed candle, inconsistent path count, or
non-finite statistic fails explicitly.

Confidence in any strategy conclusion is low. The live window is short, path
annotations overlap, and the 13-bps cost assumption is not an exact fill model
for every asset and order type. These results would be falsified or materially
updated by:

- chronological venue-native replay that turns the HYPE observation negative;
- exact fill costs materially above the assumed hurdle;
- independent forward windows that lose the current directionality;
- a causal exit rule that fails to retain the observed MFE improvement after
  costs and funding.

## Next experiment

Build a report-only HYPE onset challenger on historical Hyperliquid data that
emits one event per new causal setup rather than one annotation per minute.
Compare 5m, 15m, and 30m event spacing and exit horizons chronologically with
exact long/short attribution, fixed realistic friction, funding, and an
untouched pseudo-holdout. Retain every candidate result. Do not hot-mutate the
currently armed backend.

Good enough for a next-run candidate means a positive after-cost result in
development, validation, and pseudo-holdout; no dependence on one trade; a
frequency observable within 3–5 live days; and execution mechanics compatible
with the shared portfolio controller. Failure on any of those items remains a
reported trial result rather than an implicit research abort.
