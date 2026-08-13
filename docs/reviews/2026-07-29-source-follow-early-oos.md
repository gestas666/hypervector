# Source-follow early out-of-sample review

Date: 2026-07-29

## Problem and frozen evidence contract

The April-July current-revision `TREND_DOWN` short candidate looked profitable,
but its 90-day window was used for discovery. This review moves backward to an
untouched July-September Hyperliquid window and asks whether that apparent edge
survives causal, stateful, venue-matched execution.

Both candidates use confirmed five-minute source labels, a five-minute causal
decision delay, a 60-second post-only maker order, public trade-through fills,
70% isolated margin, 40x leverage, one BTC position, an 8% gross-margin target,
official funding, causal mark liquidation, a 24-hour maximum hold, and no stop.
The all-day candidate retains the later-selected 40-bps completed-bar range
limit. The frozen session candidate retains its original 07:00-16:00 UTC and
100-bps contract. Neither candidate, the runtime, the TUI, nor ML authority was
changed by this evaluation.

## Archive integrity and replay correction

The exact July 28-September 28 prefix contains 2,976/2,976 expected hourly
book/trade bundles, 9,766,417 book snapshots, 16,521,194 public trades, and
four zero-book hours from 2025-09-09 20:00 UTC through 2025-09-10 00:00 UTC.
Checksums passed. The audit is
`data/logs/research/oxa_btc_l2_trades_prefix_audit_ranges_20250728_20250928_20260729.json`.

The first database replay failed to expose intra-day empty-book intervals
because daily replay chunks hid empty hourly bundles. The database evidence
stream now splits at every declared empty-L2 interval. The combined artifact
correctly reports four empty-book windows and is conservatively non-conclusive,
even though no order or position was active during the gap. Final conclusions
therefore use two independently initialized, checksum-verified gap-free
segments on either side of the outage.

## Results

| Candidate and gap-free segment | Fills | Targets | Liquidations | Other | Final/marked equity | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| All-day, range 40, Jul 28-Sep 9 20:00 | 40 | 30 | 9 | 1 time exit | $514.93 | -96.54% |
| All-day, range 40, Sep 10-Sep 28 | 18 | 15 | 2 | 1 open | $7,426.93 | -45.50% |
| Frozen session, range 100, Jul 28-Sep 9 20:00 | 21 | 17 | 3 | 1 time exit | $3,850.48 | -74.12% |
| Frozen session, range 100, Sep 10-Sep 28 | 4 | 3 | 0 | 1 open | $10,521.27 | -14.56% |

The all-day 40-bps candidate resolved 56 target-or-liquidation outcomes across
the two segments: 45 targets and 11 liquidations, an 80.4% target rate. The
frozen session candidate produced 25 fills in total: 20 targets, three
liquidations, one time exit, and one open position. Its second segment was
positive, but the earlier segment independently falsifies temporal stability.

Signal confidence and completed-bar range did not separate all-day winners
from liquidations. In the broader combined replay, mean confidence was 0.859
for targets and 0.800 for liquidations; mean signal range was 16.96 and 17.07
bps respectively. These are descriptive diagnostics, not calibrated tests.

## Regime attribution

The faithful EMA21/55 plus BBWP classifier was recomputed causally on the same
one-minute venue bars. At source signal time it labeled all 56 resolved
target-or-liquidation entries as five-minute `TREND_DOWN`. A hard bearish 15m
context retained 33 targets and nine liquidations; the non-bearish context
contained 12 targets and two liquidations. On this evidence a hard 15m veto
would not improve the target rate and would not repair the tail loss.

This does not prove the regime detector is optimal. It does falsify the narrow
hypothesis that these losses came mainly from entries that the current 5m or
15m direction already contradicted.

## Assessment

High confidence: the all-day range-40 candidate and frozen session candidate
do not have stable positive execution economics across the tested gap-free
segments. The result would be updated by an audit finding incorrect causal
timing, fee, funding, liquidation, or fill accounting, or by multiple additional
predeclared gap-free segments showing positive aggregate economics.

Low confidence: a profitable full Hypervelocity implementation has been
identified. With 70% allocation, an 8%-of-margin target contributes about 5.6%
gross account equity, while a full allocated-margin loss can remove roughly
70%. Ignoring fees and partial-liquidation effects, this payoff shape needs
about a 92.6% target rate. The creator's reported 39W/4L alone is insufficient
to reconstruct the missing loss distribution or exit rule.

Do not narrow hours, confidence, or range thresholds against this result.

## Wider emergency-stop follow-up

A predeclared stateful grid compared 25%, 35%, and 45% gross-margin stops with
the exact no-stop control. At 40x these correspond to approximately 0.625%,
0.875%, and 1.125% adverse price moves before fees and execution slippage.

| Window and candidate | Targets | Stops | Liquidations | Final/marked equity | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Jul 28-Sep 9 no stop | 17 | 0 | 3 | $3,850.48 | -74.12% |
| Jul 28-Sep 9 stop 25% | 14 | 5 | 0 | $6,621.25 | -59.81% |
| Jul 28-Sep 9 stop 35% | 15 | 6 | 0 | $3,180.44 | -78.63% |
| Jul 28-Sep 9 stop 45% | 16 | 3 | 0 | $4,840.18 | -67.68% |
| Sep 10-Sep 28 all four lanes | 3 | 0 | 0 | $10,521.27 | -14.56% |
| Apr 28-Jul 27 no stop | 20 | 0 | 0 | $25,600.17 | -32.50% |
| Apr 28-Jul 27 stop 25% | 22 | 3 | 0 | $14,662.42 | -46.73% |
| Apr 28-Jul 27 stop 35% | 23 | 3 | 0 | $11,516.85 | -58.16% |
| Apr 28-Jul 27 stop 45% | 20 | 1 | 0 | $16,998.17 | -37.69% |

The 25% stop materially reduced the failed segment's tail loss but still lost
33.8% of initial equity. All stops were inactive and identical to control in
the small positive post-gap segment. In April-July every stop underperformed
no-stop because it interrupted paths that later reached target. That 90-day
comparison contains 21 empty-book hours across ten explicit UTC ranges and is
therefore conservatively non-conclusive, although no candidate had an active
order or position in a declared gap. The gap-free early segment alone is
sufficient to reject this stop family as a profitable repair.

High confidence: the grid is useful risk-reduction evidence but does not
establish positive entry economics. It would be updated by a replay-accounting
defect or a predeclared new gap-free segment where one fixed stop is both
positive and superior without target churn. No stop is promoted.

The next bounded work is to finish and segment the one-year venue archive,
then rerun the existing purged logistic, temporal-logistic, and LightGBM
annotation challengers on the larger resolved population. Separately, the
creator's four reported losing trades remain the highest-value missing source
evidence because no available record reports their loss size or exit reason.

## Immutable artifacts

- Gap-aware combined diagnostic:
  `1bbd8d084e88e39c5cf5cb2154dfa545111e8913e8d11671719a48f2512e5563`.
- All-day pre-gap:
  `1892181dd6f2260fa3294daf5c8ecfbaa563b8eab769571b3d5f9fa478e0e1f6`.
- All-day post-gap:
  `0d11513b5659d5ef33698c662e5f4d98fed3d166cf74ca74db0fed10e3404c6a`.
- Frozen session pre-gap:
  `5b78c2762b43f9fca125f2f2dcc2476fa389226cdc3d75160dafd9dab1c9a86e`.
- Frozen session post-gap:
  `db26128b639dae76fd123d2a419fb9a61d972eb4902d40950b483660bd3985cd`.
- Wide-stop pre-gap:
  `9b609d797a179bacb55dffa83f4142d1c2db5ec4f49083e660e104861f1e447f`.
- Wide-stop post-gap:
  `26f0dbff877266ee845ec0ccae3323d539adbd781953cd34a5c9dc2c2818dcd6`.
- Wide-stop April-July:
  `ce6a0346ae6c05d2ca33381e0cf058906558b96f74edcbca7bb3c59fcae37ed9`.
- April-July exact archive-gap audit:
  `7b479ad3f5bd76fa48dff4f1305d62831b4e15164cd439d4bbd7b76faa4e5b0a`.
