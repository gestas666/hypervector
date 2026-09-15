# SPCX September 15 entry: signal and execution reconciliation

**Finding:** the newly executed SPCX long satisfies the configured hourly band-reentry recipe. Its recorded decision, fill, fee, leverage, persisted exit plan and sampled protective stop reconcile. High confidence applies to this bounded technical evidence; one open trade does not establish strategy expectancy or a profitable outcome. A contradictory source candle, receipt, quantity, stop or cost would update the finding.

The audited run is `bidirectional-live-1789497016143`. Frozen SPCX rows end at **19:25:22 UTC on September 15**. The entry decision is **19:00 UTC**, entry OID **546010609566**, trade ID **981345012427962**, and stop OID **546010759610**. The audit did not control a financial process, place an order, or change strategy settings.

## Signal and regime

An independently implemented Decimal reference, reused byte-for-byte from its previously validated source archive, reconstructs the 20-hour population bands. The public response contains 1,500 ordered completed minute candles, aggregated into 25 complete hours. All 617 overlapping minutes from 857 previously recorded chart observations agree on every OHLCV field. The independent entry bands differ from the published values by at most **3.41e-13**, within the pre-existing **1e-10** tolerance.

| Long-entry condition | Recorded / independently reconstructed value |
| --- | --- |
| Previous hourly close below previous lower band | 143.59 < 144.0766978422 |
| New hourly close at or above new lower band | 144.00 >= 143.5504682666 |
| New close remains below new mean | 144.00 < 147.3635 |
| ATR update from observed prior seed | (0.9377620592 × 19 + 1.25) / 20 = 0.9533739562 |
| Structural stop anchor | 144.00 − 2 × ATR = 142.0932520875 |

The crossing consists of a **$0.41 price rise** and **$0.5262295756 lower-band decline**: **43.79% price / 56.21% band movement**. This is a new observed entry annotation for the previously deferred crossing-composition question. It does not reopen the historical threshold search or support a filter. The prior comparison had only four executed historical longs in the lower-contribution group, all in development data; the current lifecycle is still open at the capture cutoff.

The causal canonical regime was **1m RANGE, 5m TREND_DOWN, 15m TREND_DOWN**. Its observation preceded the asset decision and entry intent. The route reports directional opposition, score **−0.8333333**. This is consistent with the configured band-recovery entry contract, which has no regime veto. The same-minute SNDK short signal was withheld because its same-direction position was already open; it was not silently lost.

## Execution, costs and protection

| Check | Result |
| --- | --- |
| Requested / filled notional | $500.00 / $499.7147 |
| Fill | 3.47 long at $144.01 |
| Venue-reported leverage | Isolated 10x |
| Entry fee | $0.043175, approximately 0.864 bps |
| Fee versus recorded schedule | Difference −$0.00000035008 |
| First isolated margin | $499.7147 / 10 − $0.043175 = $49.928295 |
| Signal-reference-to-fill slippage | +0.694444 bps |
| Decision to SDK dispatch | 19.432 seconds; configured ceiling 30 seconds |
| Local intent to acknowledgement | Approximately 1.768 seconds |
| Native fill to observed stop acknowledgement | Approximately 4.659 seconds, mixing venue and local clocks |
| Protective order | Full-size 3.47 reduce-only sell Stop Market at $142.09 |
| Stop distance from fill | 133.324 bps, within configured 20–250 bps |
| Sampled protection | All 100 post-ack reconciliations retain the exact covering stop |
| Persisted exit plan | Honor recipe exits; no target/profit lock; fixed 24-hour hold |
| Recorded maximum-hold deadline | September 16 at 19:00 UTC |

The earlier book was 9.877 seconds old at local intent. Consequently, the reference-to-fill difference is measured, but instantaneous market impact is not identified. The 30-second control applies at SDK dispatch, not venue arrival or fill. Sampled stop presence does not prove uninterrupted protection or eventual fill price. No funding event occurred in the frozen entry prefix; the checkpoint's entry quantity, fee and zero lifecycle funding agree.

## Validation, limits and disposition

The offline validator accepted the frozen evidence and rejected **14 deliberate corruptions** of fill identity/side/size/fees, acceptance/deadline, stop acceptance/coverage/side/reduce-only/trigger, and native candle coverage/close. A second network-denied execution reproduced the audit, negative-control results and chart comparison exactly. Analysis source is 275 lines with a maximum function length of 44; the prior independent reference matches its archived source hash.

The public request used the documented HIP-3-prefixed candle-snapshot endpoint. Only recent candles are available; the response was captured after entry and is not the original startup input snapshot. [Hyperliquid Info endpoint documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).

The **original ATR initialization remains unverified**. The shorter independent history initializes ATR at 0.9072611523 for the entry hour, whereas the deployed process reports 0.9533739562. Their seeds differ. The exact one-hour update from the recorded prior ATR reconciles; the audit does not select a history window merely to force the initial values to match. This is the previously identified startup-input provenance gap, not newly demonstrated faulty ATR arithmetic.

**Recommendation / why now:** retain the entry evidence and the configured recipe. The observed regime opposition and provisional mark do not justify a strategy, size, leverage, stop or admission change. The technical checks support correct operation for this entry, with no established profitability upside from changing it.

**Alternatives:** a countertrend veto or crossing-composition filter would change the strategy and requires separate chronological cost-aware validation; the small prior group and current open lifecycle do not supply that evidence. Repeating earlier rejected threshold screens would add no new validation.

**Next highest-value investigation:** design and validate a bounded capture of the exact startup candle inputs so future indicator seeds can be reproduced. Keep that observability work separate from trading decisions and do not restart the financial backend to activate it. Continue reconciling the two open lifecycles when new fills, protection changes or exits arrive. The prospective outcome seals remain unopened.

**Approval / rollback:** no live change is proposed by this audit and no approval is requested. The work adds immutable research evidence only; there is no live configuration rollback. All source/data hashes, raw captures, query text, calculations, negative controls and reproduction receipts are in `data/logs/research/bidirectional_cohort/v89_spcx_entry_audit_20260915_v1/`.
