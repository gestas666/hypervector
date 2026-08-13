# Hypertrader legacy regime recovery review — 2026-07-28

## Problem restatement

Determine why the creator's visible Recipe B/C rows were absent from the
reconstructed current Hypertrader labels, then test any recovered classifier
causally on Hyperliquid-native execution evidence. Success requires source
timestamp fidelity plus improved serialized portfolio results; screenshot
matching alone is insufficient.

Runtime strategy, TUI, faithful config, 8% target, 70% isolated allocation,
40x leverage, one-position rule, and observe-only ML authority were not
changed.

## Known facts and assumptions

- The five visible Recipe B labels occurred before Hypertrader introduced its
  strict multi-bar breakout classifier.
- The three visible Recipe C labels occurred while the legacy classifier was
  still the default. Revisions `96014462` and `459dc767` have identical
  classification behavior; their state-file difference is logging-only.
- The source historical runner consumes an external SQLite label history.
  That history was generated while classifier code evolved, so a constant
  revision over 90 days is a counterfactual challenger, not an exact rebuild
  of every historical stored row.
- Creator entry timestamps are treated as label-bar timestamps. Hypervector
  maker replay waits until the completed 5m bar is causally available, five
  minutes later.
- Canonical DuckDB public trades reconstruct 5m OHLCV. Across 26,184 intact
  candle bins, open/high/low matched exactly and close matched 26,183 times.
  The trade stream also repairs two candle-vendor outage spans containing
  real trading activity.

## Source-fidelity result

Legacy revision `96014462c8f3911abff1babc925448893d65676d` reproduced all
eight visible rows at their exact inferred UTC timestamps: five
`BREAKOUT/BK_UPWARD` rows and three `TREND_DOWN` rows. The pinned current
revision reproduced three of eight.

On the same 26,208 canonical 5m bars:

| Revision | Recipe B | Recipe C | Total |
|---|---:|---:|---:|
| Current strict `ad15f2bd` | 2 | 77 | 79 |
| Legacy `96014462` | 89 | 120 | 209 |

This falsifies the earlier working conclusion that the creator's visible B
population could not be reconstructed from committed source. The missing
variable was classifier revision, not absent market data. It does not prove
that all 15-B/11-C advertised rows came from one constant revision.

## Causal venue replay

All comparisons use 60-second post-only maker eligibility, public
trade-through fills, authentic maker fees, funding, mark/oracle liquidation,
70% isolated allocation, 40x leverage, an 8% gross-margin target, cooldown,
and one BTC position.

| Candidate | Dev fills | Targets | Liquidations | Final equity | Max DD |
|---|---:|---:|---:|---:|---:|
| Current strict C short-follow | 26 | 25 | 1 | $19,370.46 | -47.67% |
| Legacy C short-follow | 30 | 29 | 1 | $25,219.35 | -46.95% |
| Legacy B long only | 30 | 22 | 1 | $9,833.38 | -46.47% |
| Legacy B long + C short-follow | 52 | 44 | 2 | $19,094.47 | -51.81% |
| Legacy literal B/C fade | 97 | 75 | 13 | $225.87 | -99.07% |

The untouched Jul 27 window contains one C event under both revisions. Both
filled short and completed the target for about $476.87 net. One fresh event
does not distinguish revisions statistically.

The legacy C-only challenger adds four completed development winners and
$5,848.89 final equity relative to current strict C-only, without adding a
liquidation or worsening maximum drawdown. Legacy B restores source
population but has no independent executable edge in this test.

## Fixed-stop falsification

The predeclared 6/10/14/18% margin-stop grid was applied only to legacy C
short-follow. The no-stop control reproduced the accepted result exactly.

| Stop | Final equity | Max DD | Stops | Liquidations |
|---|---:|---:|---:|---:|
| None | $25,219.35 | -46.95% | 0 | 1 |
| 18% | $12,764.53 | -31.35% | 7 | 0 |
| 14% | $8,750.77 | -39.04% | 13 | 0 |
| 10% | $5,820.70 | -50.78% | 20 | 0 |
| 6% | $3,080.98 | -71.22% | 32 | 0 |

Every fixed stop is rejected for return. Six and ten percent also stopped the
fresh target winner. This does not test a prior-consolidation wick/pivot stop.

## Uncertainties and failure modes

- Medium confidence: source-row reconstruction is strong at 8/8, but the
  profitable revision comparison was discovered on the same 90-day window.
- Maximum drawdown near 47% and one liquidation remain material tail risks.
- The legacy 90-day label series is a constant-revision counterfactual; the
  source SQLite history was version-mixed.
- Public trade-through proves price/volume crossing but cannot recover private
  queue rank.
- The single fresh trade supports direction only; it cannot estimate win rate,
  drawdown, or revision lift.

The legacy recommendation is falsified if new venue-matched shadow data shows
its additional C onsets do not fill, increase liquidation frequency, or fail
to improve serialized equity versus strict on the same forward window.

## Recommendation and trade-offs

| Option | Benefit | Risk | Decision |
|---|---|---|---|
| Promote legacy globally | Restores creator label density | In-sample and changes all regime consumers | Reject now |
| Trade legacy B longs | Matches creator B rows | Flat equity, liquidation tail | Reject |
| Fixed margin stop | Removes liquidation | Destroys development edge | Reject |
| Observe legacy C beside strict | Clean forward comparison, no authority change | Requires time/new events | Recommend |
| Keep current runtime unchanged | Preserves validated shadow behavior | Delays possible lift | Current action |

The next smallest experiment is an annotation-only dual classifier in shadow:
persist strict and legacy C onsets from the same completed native 5m bars,
then compare causal submissions, fills, target/liquidation outcomes, and
serialized counterfactual equity. No model or classifier receives execution
authority during collection.

## Evidence

- Legacy labels parquet SHA-256:
  `b22a9d5b6cd396a2c2bf56bc5c308582c873df62796501483c364245a5ff637c`
- Legacy C replay SHA-256:
  `30684541327eddba9ba480958f77aa455af3be0ca9edd0c9dd439c097f848d9d`
- Current C control SHA-256:
  `8f4cb969bbf363be9266710fe874b37333d7e1d22559028dd2fb459f5b7e9833`
- Legacy B replay SHA-256:
  `32b3397c809bc7e040e98fae6601871aa544b7c86ff5ae5f2df32d4c7772c4a9`
- Legacy fixed-stop grid SHA-256:
  `e20934ab28e05fd31cca46b27755e0b84300052295d29e97a0034bf795cfbcd9`
