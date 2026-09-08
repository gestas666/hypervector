# SNDK historical exit-clock qualification

**Finer historical marks support a stop contact well before the modeled August 7
liquidation.** The first observed stop-level contact is 13:32:22.136 UTC; the
first observed adverse liquidation-level contact is 13:40:07.218 UTC, **465.082
seconds later**. Nearby books show sufficient visible depth to close the modeled
quantity around the earlier contact. High confidence in these recorded samples;
medium confidence that liquidation-first bar attribution misrepresents the
within-bar sequence; low confidence in any revised fill or profitability claim.
No portfolio PnL or live rule is changed by this study.

## Scope and observed clocks

Hypothesis `v89_sndk_opening_exit_clock_qualification_20260908_v1`, preregistered
in commit `62e282c`. The two selected lifecycles explain $51.526027 of the prior
$79.617635 opening-attribution clock sensitivity. They are diagnostic selections
from already explored history, not independent evidence of economic improvement.

| Original adverse modeled lifecycle | Last sampled mark before local stop contact | First observed stop contact | First observed liquidation contact |
|---|---|---|---|
| SNDK short `xyz:SNDK\|19`, August 6 | 13:44:11.049, mark 1243 | **13:44:14.141**, mark 1246.3 | None in the acquired window |
| SNDK long `xyz:SNDK\|20`, August 7 | 13:32:19.121, mark 1286.6 | **13:32:22.136**, mark 1282.2 | **13:40:07.218**, mark 1246.7 |

All times are UTC on the respective dates. The short's stop is
1243.7680511249996, liquidation threshold 1271.1701587573423. Its observed
stop contact occurs 854.141 seconds after the recorded 13:30 bar timestamp,
near that bar's end. The long's stop is 1285.269009375 and adverse liquidation
threshold 1248.9692660171054. The previous sampled mark before the long's
liquidation contact is 1249.7 at 13:40:04.087.

Each price window contains 340 samples over 13:29–13:46 UTC with no missing
mark/oracle/mid fields. Maximum gaps including boundaries are 3,367 ms on
August 6 and 3,262 ms on August 7. Local first contact does not establish the
first contact since entry; the original entries were at 11:00 and 13:00 UTC,
outside part of these short acquisition windows. A mark may cross a threshold
between samples. No continuous absence-of-contact or exact trigger-time claim
is made.

Current venue documentation identifies marks as the reference for
[stop triggering](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/take-profit-and-stop-loss-orders-tp-sl)
and [liquidation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations).
The retained documentation is current evidence of that contract, not proof
that the sampled historical feed is complete.

## Visible execution context

| Sampled contact | Closing side / modeled quantity | Before-sample visible VWAP | After-sample visible VWAP |
|---|---|---:|---:|
| August 6 stop | Buy 0.41205432117060653 | 1241.8, −141 ms | 1242.0, +359 ms |
| August 7 stop | Sell 0.3792980274511258 | 1282.5, −136 ms | 1282.2, +364 ms |
| August 7 liquidation | Sell 0.3792980274511258 | 1246.804482, −218 ms | 1247.9, +282 ms |

Both brackets have enough visible quantity. All 2,229 August 6 context books
and 2,226 August 7 context books can accommodate the respective modeled close;
maximum snapshot gaps are 500 and 1,500 ms. These walks do not model order
arrival, queue competition, latency, stop ownership or actual client fills.
Mark-trigger and book prices are distinct observations, explaining why the
short's nearby executable asks can be below its mark-based trigger.

The engine deliberately prioritizes liquidation, then stop, then target when
15-minute bar extrema contact multiple barriers. The August 7 row therefore
records liquidation at 1248.9692660171054 despite the observed earlier stop
contact. Its full-fee variant records 1250.0932259605263 because the isolated
margin calculation includes entry fees. These are inherited model assumptions,
not evidence of an actual venue liquidation or a newly observed live fault.

An exact inventory of all 18 registered source/cost/clock variants finds
**one ambiguous accepted noncrypto lifecycle per case: this August 7 SNDK
long, among 99 accepted SNDK/SPCX lifecycles**. Nominal stop/liquidation thresholds
differ from adverse, so the next replay must retain every cost contract. The
18 variants reuse the same event and do not supply 18 independent examples.

## Data qualification and corrections

Thirty-two fixed one-minute trade requests cover 13:29–13:45 on the two dates.
August 7 completes all sixteen partitions: 32,536 participant rows normalize
to 16,268 public trades, including 16,101 in the 13:30 bar. August 6 preserves
58,608 participant rows and 29,304 public trades, but its 13:30–13:31 partition
hits ten pages at **13:30:55.391**, retaining an explicit continuation cursor.
The remaining tail is unresolved; the study did not expand its registered cap.
No full-bar OHLC assertion is made for August 6, even though its observed
high/low/open match the registered candle.

For August 7, reconstructed open/high/low exactly match the registered candle:
1310.2 / 1310.5 / 1246.8. Final prints at **13:44:59.805** have prices 1264.7,
1264.8 and 1264.9. The registered close 1264.9 is among them. Sorting trade IDs
cannot resolve their within-millisecond order. The initial diagnostic selected
1264.7 by that arbitrary ordering; the finalized report leaves close unavailable
and preserves all candidates. A regression test reproduces and prevents that
false precision. This is not evidence of a candle-price error.

The existing August 6 hour of L2 data was reused. Its old manifest lacks a
zero-size censor count, which initially failed the newer strict helper. The
final replay derives **zero censored rows and zero coalesced timestamps** from
all 7,871 raw rows and matches the publication exactly. Missing metadata was
not treated as an assumed zero, and the original archive was not modified.
The new August 7 bundle retains 2,227 normalized rows including its right
boundary; the context measurement excludes that endpoint.

## Validation and disposition

Research source **`89345494eac8494909751c1730e202537c4db189`** is isolated from
the main live Python source. **90 offline tests passed**; the pure threshold
module covers 36/36 statements and 14/14 branches. Coverage does not include
all acquisition, archive I/O or the full project. Tests also cover legacy
normalization metadata, false declared counts, missing samples, directions,
partial pagination, boundary duplicates and uncertain OHLC endpoints.

A separate standard-library check imports no research implementation, verifies
203 source files, independently matches **220 threshold fields** and **six
Decimal depth walks** (maximum VWAP difference about 2e−13). All 5,109 archived
Git members match their blobs. Replay from the frozen archive reproduces the
104,520-byte report exactly. Source checks, Ruff and structural limits pass.
Initial failures and intermediate reports remain preserved separately.

Changed hashes, raw/publication disagreement, denser marks contradicting the
observed sequence, or inadequate book capacity would update the respective
findings. Only a full entry-to-exit event replay with explicit execution costs
can support revised modeled economics. Realized live losses remain unchanged.

| Option | Value / confidence | Trade-off and next evidence | Disposition |
|---|---|---|---|
| Retain the original conservative row as the baseline | Exact prior reproducibility; high confidence | Does not represent the observed intrabar sequence | Preserve as control |
| Replace liquidation with a stop fill immediately | Economic effect unverified | Earlier lifecycle contacts, latency and fill assumptions remain unresolved | No live or PnL change |
| Replay all accepted ambiguous noncrypto exits with event clocks | High diagnostic value; one unique event across all cost cases | Need complete entry-to-exit marks and declared executable-price assumptions | Next research study |

Next: `v89_noncrypto_ambiguous_exit_event_replay_20260908_v1`. Preregister the
complete August 7 13:00 entry through the exit bar, verify marks before 13:29,
retain nominal/adverse/full-fee thresholds and bounded fill/latency assumptions,
then compare the resulting lifecycle and shared-account attribution against the
original baseline. The completed inventory defines the entire accepted
ambiguous noncrypto sample, avoiding favorable-case selection. Do not change
live execution or claim improved expected returns from this one historical row.
The sealed September 8–22 experiment remains unopened.

Evidence:
`data/logs/research/bidirectional_cohort/v89_sndk_opening_exit_clock_qualification_20260908_v1/`.
