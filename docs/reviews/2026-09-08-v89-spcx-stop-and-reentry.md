# SPCX stop and fresh re-entry audit

The first V89 SPCX long closed in full through its original venue stop, losing
$3.754698 after fees and funding. The 09:00 UTC re-entry has a new completed-hour
decision and distinct entry/stop identities. No applicable long-side provider
exit was recorded before the first position stopped out. Confidence is high for
these bounded execution conclusions; this audit does not establish profitability.

All times below are UTC on 2026-09-08. Execution authority is `none`; no runtime
strategy, sizing, leverage, risk, order, deployment, or process control changed.

## Exact lifecycle and costs

| Item | Verified value |
|---|---|
| Run | `bidirectional-live-1788809099824` |
| First entry | 3.34 long at $149.70, 02:00:22.492, OID 538846317314 |
| Stop fill | 3.34 sold at $148.60, 08:00:48.855, OID 538846363686 |
| Gross PnL | −$3.674000 |
| Entry and exit fees | $0.086081 |
| Six funding settlements | +$0.005383 |
| Net PnL | −$3.754698 |
| Holding time | 21,626,363 ms |
| Native entry fill to original stop-open time | 2,809 ms |
| Native exit fill to local fill record | 15,219.778 ms |

Both native fills match ledger price, quantity, order/trade ID, timestamp,
transaction hash, direction, taker status, fee, and fee token. Each funding
payment matches its timestamp, signed size, cash amount, rate, and hash. The
closed native snapshot at approximately 08:52:55 contains no SPCX position or
open order. That historical flatness precedes the subsequent re-entry.

The strategy stop anchor was $148.6731728235845 and the resting native trigger
was $148.67. The $148.60 fill is 4.70841461 bps below the rounded trigger; the
dashboard's 4.92172341 bps uses the unrounded strategy anchor. Rounding accounts
for $0.01059723 and movement from the rounded trigger to the fill for $0.2338.
Those price differences do not isolate instantaneous market impact.

The audit checks 1,443 resting-stop reconciliation samples from 02:00:27.035175
through 08:00:48.539260. Each contains the full 3.34 reduce-only sell stop at
$148.67. Sampled agreement cannot prove continuous presence between reads.
The dashboard's 1,047 ms stop acknowledgement describes original placement,
not the latency from the later stop trigger to its fill.

After execution, the native stop status reports `triggerPx=0`, `isTrigger=false`,
and `limitPx=133.81`. The earlier resting record preserves the actual $148.67
trigger and limit fields; the adapter submitted `isMarket=True`. The venue
documents mark-price triggering and a 10% tolerance for market TP/SL orders.
The post-trigger status is therefore not evidence that the adapter originally
submitted a $133.81 trigger or that the trade filled at that price.
[Hyperliquid TP/SL documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/take-profit-and-stop-loss-orders-tp-sl), checked 2026-09-08.

## Exit directions and the new entry

All 24 quarter-hour publications after the first fill and before the stop are
present in the frozen cohort prefix. Six hourly publications say
`close_open_position`, with `exit_sides=["short"]`. The owned position was long.
The configured controller requires the owned side in `exit_sides`, so these
records do not establish an ignored long exit. There are no routed SPCX actions
in that open interval.

The fresh 09:00 decision satisfies the recorded band-recovery inequalities:

| Input | Previous hour | Current hour |
|---|---:|---:|
| Completed-hour close | 148.83 | 148.84 |
| Lower band | 148.8689790920661 | 148.73150784648055 |
| Current mean | — | 149.767 |

The prior close is below its lower band; the new close is above its lower band
and below the mean. These are checks of the recorded indicators, not an
independent recomputation of the original 15-minute input history. A falling
lower band contributes to this crossing, so a price-recovery or momentum claim
would require separate evidence.

The router admitted the new entry 12,908 ms after the hourly boundary; the
entry intent was persisted at +13,937.698 ms, and its fill is recorded at
+15,109 ms. It bought 3.35 at $148.76 under OID 539125419115. The new full-size
stop intent binds to accepted resting stop OID 539125458790. Entry acknowledgement
to stop acknowledgement took 2,891.160 ms locally. This re-entry binding uses
the backend ledger, without a second independent native-account capture.
The admission timestamp does not prove a final SDK dispatch deadline check.

## Validation and next investigation

The isolated audit and controller selection passes 87 tests with network
lookup, connection, and datagram calls denied. The two audit modules cover
267/267 executable statements and 92/92 branches. Tests reject corrupted
economics, duplicate/missing settlements, wrong-side exits, incomplete signal
coverage, stale entry identities, broken client/stop bindings, and prefix
checksum/sequence corruption. A fresh temporary workspace replay passes the
same 87 tests from the archived source; all 3,368 archive members are verified.
Eight new Python files pass Ruff, formatting, function/file-size, annotation,
and public-docstring checks.

Evidence lives under `data/logs/research/bidirectional_cohort/` in
`v89_spcx_exit_native_20260908_v1`, `v89_spcx_lifecycle_20260908_v1`, and
`v89_spcx_exit_acceptance_20260908_v2`, with the earlier resting stop from
`v89_spcx_native_20260908_v1`. The initial audit and its executed source remain
preserved in `v89_spcx_exit_acceptance_20260908_v1`. The final report, exact test
invocation, coverage, source archive, and archive replay are separately pinned.

No live change is recommended from this one completed SPCX trade. The next
investigation is an independent replay of the completed 15-minute inputs behind
the two SPCX entries, including the contribution of a moving band to eligibility.
This must not inspect the locked 14-day prospective challenger outcomes early.
Conflicting native identity/cost evidence, a missing eligible long exit, broken
stop ownership, or an indicator replay disagreement would falsify the relevant
technical conclusion and require a new journal revision.
