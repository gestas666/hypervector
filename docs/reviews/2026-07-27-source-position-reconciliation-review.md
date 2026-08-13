# Hypervelocity Source Position Reconciliation Review

## Problem and correction

The external CSV contains 37 rows but not 35 independent entry decisions. One
July 18 BTC long appears twice: a `position_peak_only` observation and a later
`trade_only` record have the same side, $64,522 entry, 0.01358 BTC quantity,
overlapping lifetime, and closes only 5.2 seconds apart. Counting both as
entries double-counted one position and treated contradictory tracker/trade
open timestamps as two decisions.

Source reconciliation now drops a peak-only row only when a trade-only row has
the same symbol, side, entry, quantity, overlapping lifetime, and a close
within 60 seconds. It preserves the two true split-exit pairs because their
quantities differ and their records are not a peak-only/trade-only duplicate.

Measured source identity is now:

- 37 raw records;
- 36 records after removing the superseded peak-only observation;
- 34 entry decisions after clustering the two sub-second split-exit pairs;
- 33 closed position episodes and one open episode.

## Corrected regime evidence

The faithful BBWP detector matches 23/34 exact entry directions (67.65%), marks
two entries RANGE, and has five no-entry states. Chronological tuning now uses
23 training entries and 11 holdout entries. The current configuration scores
15/23 on training and 8/11 on holdout with zero holdout false-RANGE entries.

The raw train-score winner, trial 36, improves training to 18/23 but falls to
7/11 on holdout and raises training-slice churn from 1,462 to 5,758. No trial
satisfies the existing zero-no-entry/zero-false-RANGE training contract. It is
therefore not a promotion candidate.

Timestamp provenance is also material. Twenty-one reconciled entries have
trade-backed timestamps; thirteen rely only on tracker first-observation
times. On the trade-backed subset, the current configuration is itself the
train-selected winner among the same frozen 100 candidates: 10/14 training and
5/7 holdout exact directions, zero false-RANGE entries in both slices, and no
contract candidate. This sensitivity result supports retaining current regime
parameters; it is not strong confirmation because seven holdout entries are
too few for stable inference.

## Mechanical source-path audit

Using Hyperliquid 1m candles as a cross-venue proxy, 23/33 closed reconciled
episodes cross the fixed 0.2% price target during their recorded lifetime. Ten
do not; those are dominated by early peak-only tracker records without booked
exit prices. Only one trade-backed episode reaches the proxy target more than
five minutes before its recorded close. A separate isolated-liquidation audit
finds one borderline source short whose candle high exceeds the modeled proxy
boundary by about 1.1 bps; the other 32 closed episodes do not cross it.

## Artifacts and decision

- Corrected evaluation:
  `data/logs/research/hypervelocity_regime_eval_hl90d_reconciled_v2_20260727.json`
- Corrected 100-trial board:
  `data/logs/research/hypervelocity_regime_tuning_hl90d_reconciled_20260727.json`

Keep the faithful regime configuration unchanged. Confidence is high that the
specific duplicate is one position because four independent fields and the
close interval agree. Confidence is medium in the corrected 34-entry identity
because tracker-only open timestamps remain indirect. A source export with
authoritative order/fill IDs for the early records would falsify or strengthen
that reconciliation.
