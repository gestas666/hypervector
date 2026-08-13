# Source-follow short candidate review

Date: 2026-07-28

## Problem restatement

The faithful bidirectional runtime is directionally close to visible creator
entries but fails economically in the 90-day venue replay. A narrower source
experiment showed profitable `TREND_DOWN` onset shorts, but its prior package
also carried unsupported Recipe-B longs. This review isolates the short arm,
tests it under three fill assumptions, and compares it with the literal source
long-fade direction and the legacy classifier.

This is report-only research. It does not change the faithful runtime, TUI,
position sizing, target, regime authority, or observe-only ML setting.

## Frozen contract

- Source classifier: `ad15f2bdc949619be495a5f516babd08f7f52a90`.
- Signal: confirmed 5m `TREND_DOWN` onset during 07:00-16:00 UTC.
- Direction: short; this deliberately flips literal Recipe C from fade-long.
- Availability: five minutes after the source bar; one-minute maker TTL.
- Shock annotation: completed-5m range at most 100 bps.
- Portfolio: one BTC position, 70% isolated margin, 40x leverage.
- Exit: fixed 8% gross margin target, no stop, maximum hold 24 hours.
- Friction: maker/taker fees, official funding, causal mark liquidation.
- Fill sensitivity: touch, one-tick book-through, public trade-through.

The 100-bps value was selected on development evidence and is an explicit
overfit risk. It is frozen here rather than retuned against later windows.

## Development results

| Fill assumption | Fills | Targets | Liquidations | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Touch | 51 | 48 | 3 | $23,366.73 | -57.54% |
| One-tick through | 49 | 47 | 2 | $35,678.79 | -56.69% |
| Public trade-through | 20 | 20 | 0 | $25,600.17 | -32.50% |

All three execution assumptions are profitable. The strict trade-through path
contains 76 source events: one range exclusion, two path-dependent
non-submissions, 53 canceled maker orders, and 20 completed targets. Total
fees are $2,712.80 and net funding is +$209.56. Intratrade marking still
produces -32.50% maximum drawdown despite every completed trade winning.

The strict closed-trade chronology is positive in all three fixed 30-day
slices:

| Slice | Resolved fills | Targets | Net PnL |
|---|---:|---:|---:|
| Apr 28-May 28 | 8 | 8 | +$4,526.09 |
| May 28-Jun 27 | 9 | 9 | +$7,664.05 |
| Jun 27-Jul 27 | 3 | 3 | +$3,410.03 |

The final slice has only three fills, so positive chronology reduces but does
not remove small-sample risk.

## Forward evidence

- Jul 27: one short filled and targeted for +$476.87 net; maximum marked
  drawdown was -8.78%.
- Jul 28: one short filled at $63,182.00 and targeted at $63,055.636 after
  10 minutes 52 seconds for +$476.08 net after $83.92 fees; maximum drawdown
  was -3.58%.
- The Jul 28 signal range was 20.45 bps, so it passes the frozen 100-bps
  annotation without changing the retained lifecycle.

Two forward fills and two targets are directionally supportive but remain too
few to estimate a durable live win rate or liquidation tail.

## Long-arm and classifier comparison

The literal current-revision fade-long at the Jul 28 onset canceled unfilled.
The legacy classifier emitted its onset five minutes later: its long filled at
$63,182.00 and targeted on the rebound for +$475.92, but experienced -11.96%
maximum drawdown. Its short order canceled. The short and long signal windows
overlap, so the one-position policy cannot claim both wins.

The full legacy fade-long replay falsifies that later winner as a complete
strategy. Under public trade-through it produced 55 fills, 41 targets, 12
liquidations, two time exits, and $133.39 final equity with -99.46% drawdown.
Touch and book-through ended at $116.22 and $110.94. Every 30-day slice lost.

Removing Recipe B from the current short package improved touch and through
equity and left strict trade-through trades and final equity unchanged. No
validated long arm remains: reconstructed Recipe B, symmetric trend-up longs,
four-hour trend-up longs, and the legacy fade population all failed their
full-window tests.

## Recommendation and confidence

Freeze the current-revision short arm as the leading annotation-only candidate
in `configs/research/hypervelocity_source_follow_short.toml`. Do not install it
as the faithful runtime. It is sparse, short-only, session-constrained, and
therefore does not yet reproduce the creator's full bidirectional cadence.

Confidence in the replay accounting and relative development comparison is
high because source hashes, causal availability, canonical venue evidence,
costs, funding, and three fill assumptions are retained. Confidence in a real
short-side edge is medium. Confidence in a complete Hypervelocity strategy is
low because only two forward fills exist and no long arm survives.

The short-side assessment would be weakened or falsified by later frozen
signals producing a liquidation, negative aggregate forward PnL, profit
isolated to one execution model, or observed shadow maker behavior that
contradicts the modeled 60-second fills. Complete creator no-entry and losing
trade logs would update source-fidelity claims.

## Range-direction challenger closure

One non-filtering extension used the already-frozen 100-bps completed-5m range
boundary to choose direction at the same Recipe C onsets: short follow at or
below the boundary and long fade above it. It changed no event time, sizing,
target, hold, fee, funding, or liquidation assumption.

The extension ended at $24,478.79 under touch and $37,376.80 under one-tick
book-through, improvements of $1,112.06 and $1,698.01 over short-only. Its one
high-shock long targeted under both assumptions. Public trade-through ended at
the identical $25,600.17 because that long canceled unfilled. Drawdown and
liquidation counts were unchanged. Jul 27 and Jul 28 remained short targets
under every fill assumption.

This does not validate the long arm. Only one of 76 development events exceeded
100 bps. Across the 25 events with unanimous cross-fill direction preferences,
the split selected only 12 correctly (48%); fade- and follow-preferred range
distributions substantially overlap. The short-only contract remains the
leading candidate. The high-shock fade remains a report-only annotation whose
next useful evidence is an independent above-100-bps event with a strict fill.
See `docs/plans/2026-07-28-hypervelocity-recipe-c-range-direction.md`.

## Immutable evidence

- Touch: `c1d3fae3480a41e17fad4f6b8ae8384ddd09c49acd2a6ddb9625f7341a711f26`.
- One-tick through:
  `6b76d48a0029f32cfb8e5260b4068432b9147f1a39d0c8c710008f27cda4b451`.
- Public trade-through:
  `551b8ed6ba32eb1273398f6331b51f8e7d89b5d0efbd2955472322fe181cfe46`.
- Strict candle cache:
  `7ecfcf42cafe4143c6bfe525a47209a40f23fd3e53d31f8be572dbb5d4e29e43`.
