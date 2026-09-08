# Frozen prospective quarter-entry comparison

Declared after the exploratory comparison and before the evaluation block.
This is a research-only collection and evaluation protocol; it grants no live
strategy, sizing, order, restart or promotion authority.

## Fixed block and hypotheses

- Evaluation: September 8, 2026 04:00 UTC inclusive through September 22, 2026
  04:00 UTC exclusive, fourteen calendar days.
- Symbols: exactly `xyz:SNDK` and `xyz:BRENTOIL`.
- Four arms: each asset's hourly baseline and the already implemented quarter
  entry candidate from source commit `1dc57ec`. No parameter search.
- Channels, ATR, exits, execution, cost assumptions and output metrics are those
  in `docs/plans/2026-09-08-v89-quarter-entry-comparison.md`.
- Preserve the existing July 19–September 7 warmup inputs and append the missing
  completed quarters and funding before this block. The seam must be complete,
  unique and explicitly source-backed. No fabricated or forward-filled candles.

## Required collection behavior

Implement and test a read-only public Hyperliquid Info collector before the
block starts. It must load no credentials and construct no order client. Retain
the exact request, raw candle/funding response, request/receipt timestamps and
content hashes. Capture each newly completed quarter after its close. Preserve
the first valid observed complete candle and any differing later revision;
never select a revision by its economic result. Missing or late observations
remain explicit coverage gaps. Retries are bounded and observable.

Retain official hourly funding and public HIP-3 fee-mode metadata with their
observation timestamps. Entry depth/latency and native stop ordering remain
unobserved unless separately captured; neither historical nor prospective candle
results may claim exact private fills. Existing nominal/adverse/full-fee cases
remain fixed sensitivity scenarios, not inferred actual all-period fees.

Capture-only status can report request failures, source completeness, timing
and storage. Do not calculate candidate trade outcomes before the block ends.
Routine monitoring of the actual live account continues; disclose that exposure
when interpreting the prospective result rather than claiming fully blinded
market observation. Code or protocol changes require a new explicitly dated
revision and cannot silently reuse this block as untouched confirmation.

## Evaluation and disposition

After the full block ends, first audit source identity, first-observation timing,
revisions, gaps and funding. Re-run causal prefix and baseline-exit checks. Report
all four arms, all three costs, complete trade records, event censoring,
drawdown, frequency, win/loss distributions and largest-winner removal. A small
sample remains a small sample; overlapping cases are not independent evidence.

The current decision is rejection of the live faster-entry proposal. Future
evidence may revise it only through a documented comparison, including adverse
costs and concentration. There is no automatic promotion threshold or live
policy change. If capture misses the start or cannot establish the declared
source coverage, label the block incomplete and predeclare a later block;
do not backfill a claim of timely availability.

Collector implementation and deployment remain pending. This protocol alone is
not evidence that a collection process is running or that the future study has
been completed.
