# Hypervelocity Source-Window Replay Plan

**Goal:** Measure the current research leader over the same July 9–24 observation window as the reverse-engineering logs, independently of the broader 90-day survival test.

**Frozen contract:** Use hard 5m BBWP25, 1m recovery age 6, 300-second maker TTL/cooldown, regime-reset re-entry, $10,000 fresh equity, 70% isolated margin, 40x leverage, one 8% target, and public-trade-through fills. Do not alter runtime or ML observe policy.

## Validation

1. Replay the containing immutable archive bundles from
   `2026-07-09T04:00:00Z` through `2026-07-24T16:00:00Z`, then report the
   source comparison separately from `2026-07-09T04:50:00Z` through
   `2026-07-24T15:09:00Z`. The 50-minute lead-in and 51-minute tail must remain
   explicit.
2. Verify every required archive bundle checksum.
3. Report submissions, fills, expirations, targets, liquidations, final equity,
   drawdown, trade cadence, and direction/timing alignment against the 35
   logical source positions.
4. Keep this result distinct from the 90-day replay. Same-window profit does
   not prove general robustness; 90-day loss does not prove the source-window
   behavior was absent.

## Success and falsification

- A profitable same-window replay requires final equity above $10,000 after
  modeled costs.
- Behavioral alignment requires comparable cadence and materially overlapping
  entry direction/timing, not merely a positive balance.
- The hypothesis that the current candidate reproduces the source window is
  falsified if it remains unprofitable or its entries/cadence materially differ.

Confidence is medium for measuring this exact archive window and low for
generalization. Missing historical funding, authentic mark price, and private
queue position remain explicit limitations.

The first command used the non-hour-aligned source timestamps as archive bundle
identities and failed before replay because no `04:50-05:50` immutable bundle
exists. The downloaded archive is partitioned and manifested on exact UTC-hour
boundaries. This was a technical input failure and produced no result artifact;
the corrected command uses the containing verified bundles rather than
fabricating or rewriting evidence.

## Measured Result

Both exact-window replays verified all 372 hourly book/trade bundles. Every
modeled fill occurred inside the narrower first-to-last source-entry window;
the archive lead-in/tail added no filled trade.

| Candidate | Fills | Targets | Full liq. | Partial liq. | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Faithful runtime classifier | 45 | 39 | 6 | 6 | $3,598.25 | -79.93% |
| Hard BBWP25 + recovery-6 | 57 | 52 | 5 | 5 | $10,847.07 | -60.94% |

The hard/recovery candidate is profitable on this exact interval (+8.47%),
while the faithful runtime classifier loses 64.02%. This establishes that the
hard compression/recovery state materially improved this source-period replay.
It does not establish a deployable edge: the same hard/recovery candidate ends
at $4,123.47 over the full 90-day replay.

Behavioral alignment also remains weak. The hard/recovery classifier reports
17/35 exact directions at recorded source entry times versus 24/35 for the
faithful classifier. One-to-one actual fill matching is weaker still:

- hard/recovery: 1/35 source entries matched within five minutes, 2/35 within
  ten minutes, and 4/35 within thirty minutes;
- faithful: 1/35 within five or ten minutes and 2/35 within thirty minutes.

The hard/recovery candidate also produces 57 fills versus 35 logical source
positions. It therefore reproduces positive interval PnL but not source timing
or cadence, and its -60.94% drawdown is unlike the available source record of
only positive booked outcomes. The artifacts are
`data/logs/research/hypervelocity_source_window_replay_20260727.json` and
`data/logs/research/hypervelocity_faithful_source_window_20260727.json`.

## Decision

Retain hard BBWP25 + recovery-6 as the source-window research leader, not as a
runtime promotion. Future entry work must improve actual source timing without
sacrificing the exact-window profit and must survive the full 90-day archive.
A larger source log containing losing and skipped opportunities would update
the alignment assessment.
