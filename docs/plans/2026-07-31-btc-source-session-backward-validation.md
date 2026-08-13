# BTC source-follow backward validation

Date: 2026-07-31

## Objective

Challenge the selected BTC five-minute source-follow short on an earlier,
previously unavailable Hyperliquid window before changing shadow or live
authority. The experiment separates the entry-session effect from the
completed-five-minute range floor while preserving the source classifier and
execution contract.

## Frozen evidence window

- Classifier warmup and market acquisition: `[2025-04-25, 2025-07-28)` UTC.
- Scored replay: `[2025-04-28, 2025-07-28)` UTC.
- Venue: Hyperliquid BTC perpetual.
- Required evidence: checksummed L2, deduplicated public trades, sampled
  mark/oracle context, official funding, and pinned source labels.
- Pinned classifier revision:
  `ad15f2bdc949619be495a5f516babd08f7f52a90`.

The scored interval predates the existing BTC archive and the parameter-search
period. No result from this interval may alter the declared arms after data are
inspected.

## Predeclared 2x2 arms

| Arm | Entry session | Minimum completed-5m range | Confidence |
|---|---|---:|---:|
| A: current canary control | 24/7 | 12 bps | 0.70 |
| B: selected session | `[06:00,15:00)` UTC | 12 bps | 0.70 |
| C: session range challenger | `[06:00,15:00)` UTC | 0 bps | 0.70 |
| D: all-day range control | 24/7 | 0 bps | 0.70 |

All arms use confirmed completed-5m `TREND_DOWN` onsets, short only, maximum
completed-bar range 100 bps, one 60-second post-only entry pulse, one BTC
position, 35% isolated margin, 30x leverage, an 8% gross-margin maker target,
no fixed stop, and a 24-hour first-fresh-BBO taker maximum-hold exit. Funding,
maker/taker fees, partial fills, partial/full liquidation, and venue depth stay
enabled. ML remains observe-only.

## Measurements

Retain and report every arm regardless of performance:

- raw decisions, submitted entries, fill conversion, and canceled entries;
- completed targets, maximum-hold exits, partial and full liquidations;
- net PnL, final equity, profit factor, and marked maximum drawdown;
- maker/taker fees, signed funding, and depth/queue uncertainty;
- direction and timestamp overlap with creator evidence where timestamps exist;
- block and leave-one-block-out concentration when sample size permits.

Trade-through is the primary public-execution comparator. A finalist must also
be challenged with the production queue model; touch-only profitability cannot
support a configuration change. Missing market evidence censors the affected
lifecycle rather than fabricating a fill or price.

## Interpretation contract

This is report-only research under `SRS_HV1_NO_GATES`; poor performance is a
result, not a technical abort. No runtime or live configuration changes from
this experiment alone. A configuration recommendation requires the same arm to
remain positive after costs, avoid materially worse liquidation/drawdown, and
improve or preserve creator cadence across the earlier window. Contradictory
metrics are reported rather than collapsed into an undocumented score.

The session hypothesis is materially weakened if its advantage disappears or
reverses on this earlier interval. It is strengthened, but not proven, if the
session arm remains positive and improves the 24/7 control under both
trade-through and production-queue evidence. Private queue priority and future
regime drift remain unresolved even after a positive result.
