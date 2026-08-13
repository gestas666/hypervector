# Apex MM live transport and TUI review — 2026-08-01

## Scope

Repair the Apex MM canary's rate-limited live loop, preserve its one-second
decision clock, make shutdown independent of streaming health, and make the
read-only TUI explain the strategy in plain language. The latest repair also
removes serial bid/ask submission so both quote legs share one book snapshot
and one official-SDK bulk action.

## Observed failures

- The original one-second loop repeatedly called weighted account, open-order,
  fill, funding, and L2 REST endpoints. Hyperliquid returned HTTP 429 after
  accepting live orders.
- A temporary 15-second refresh avoided the rate limit but no longer represented
  the frozen one-second market-maker candidate.
- First streamed startup attempt failed closed when its L2 snapshot aged to
  1,184 ms against the 1,000 ms quote limit. No quote was submitted; REST cleanup
  verified flat.
- An idle ten-second mainnet stream probe delivered L2/account/order snapshots
  about every 5.1–5.4 seconds. That cadence cannot supply fresh one-second quote
  inputs by itself.
- The TUI showed order plumbing without directly explaining current intent,
  fill behavior, or loss response.
- A periodic REST reconciliation discovered older account fills absent from the
  initial stream snapshot. Telemetry incorrectly queued six of those historical
  fills for current-run markouts, so the first long-window audit was invalid.
- A real maker fill arrived in a `userFills` update without `isSnapshot`.
  Strict parsing stopped the run; fail-closed cleanup flattened the exposure.
- A later no-fill run accepted two quote cancellations, but the `openOrders`
  stream did not publish the resulting empty order set within five seconds.
  REST cleanup independently confirmed the account was flat. The canary had
  subscribed to the full open-order snapshot without also consuming the
  venue's explicit incremental `orderUpdates` lifecycle feed.
- The longest post-repair no-fill run still submitted its buy and sell legs as
  two sequential REST mutations. Retrospective intent timing found all 147 buy
  intents within the 1,000 ms book-age contract, but 114/147 sell intents
  exceeded it. Median sell-side book age was 1,176.5 ms versus 510.4 ms for
  buys. The prior audit omitted this timing dimension and was superseded.

## Implemented repair

- Public/private WebSocket subscription injection with explicit disconnect
  evidence and complete unified-account snapshot readiness.
- Streamed account, open-order, and fill state with incremental fill deduplication.
- One-second low-weight REST L2 observations, streamed private state, a periodic
  60-second authoritative REST drift challenge, and REST-only shutdown cleanup.
- Exact streamed order-ID confirmation after submit/cancel mutations.
- Conditional quote replacement: unchanged calculated prices retain their
  existing venue order IDs instead of cancel/requote churn.
- Hourly funding-history polling rather than polling on every decision tick.
- A fixed-period runner that subtracts processing latency from the next sleep.
- A TUI explainer with `NOW`, `WHY`, `NEXT`, bid/ask fill consequences, and the
  explicit loss response. The TUI remains read only.
- Run-start attribution prevents historical fills discovered later by REST from
  entering current-run quality metrics. The report-only auditor rejects orphan
  metric order IDs and reconstructs inventory that falls between samples.
- Missing `userFills.isSnapshot` is treated as an incremental update. A present
  non-boolean value remains a hard schema error.
- Known streamed venue-state/schema failures now emit an explicit backend fault
  before REST-only cancel/flatten cleanup, so the journal and TUI preserve the
  stop reason.
- The private stream now consumes Hyperliquid `orderUpdates` and applies only
  documented `open` or terminal statuses to its open-order projection. If an
  incremental confirmation still times out, exact REST order identity may
  recover it; a mismatch fails closed, and stream/REST agreement must return
  within three reconciliations.
- A bounded mainnet schema probe established that the live `open` update uses a
  lean seven-field order shape (`coin`, `limitPx`, `oid`, `origSz`, `side`,
  `sz`, `timestamp`) rather than the richer frontend-open-order shape. The
  stream now parses that shape separately under the Apex non-trigger,
  non-reduce-only quote contract; terminal updates require only an order ID.
- A venue order ID retains the limit price bound at acknowledgement time even
  while newer theoretical quotes are observed. The report-only auditor rebuilds
  the client-order-ID to venue-order-ID chain and rejects expected prices that
  differ from the submitted limit.
- Paired quote legs now enter Hyperliquid through one `bulk_orders` action with
  independent client order IDs. Ordered partial rejection is preserved rather
  than treated as atomic success: any accepted leg is canceled, exact status is
  reconciled, and the engine faults. An ambiguous batch response recovers every
  client order ID before deciding whether rollback is required.
- Quote lifetime begins at the pre-call batch submission timestamp. Each maker
  intent records a shared batch ID, the source book exchange timestamp, and the
  batch submission timestamp. The audit reports book age overall and by side.
- Direct `SIGTERM` requests for both the backend and unified TUI supervisor are
  translated into the same verified cancel, reconcile, flatten, and prove-flat
  shutdown path used by operator stop and Ctrl-C.
- The TUI reads `submission_transport` from backend configuration identity. It
  labels the repaired path as one batched action only when that field is
  present; older ledgers display an unreported transport instead of inventing
  the new behavior.

## Mainnet validation evidence

Legacy four-maker-fill run: `apex-mm-live-1785570631759`.

| Metric | Observed |
|---|---:|
| Runtime | 2,821.0 seconds |
| Maker fills | 4 |
| Filled notional | $59.9173 |
| Recorded fees | $0.008626 |
| Available markouts | 3/4; mean -0.1322 bps |
| Final venue position / open orders | Flat / 0 |
| Reconstructed final size from recorded fills | +0.00011 BTC |
| Faults | 1 quote-identity reconciliation fault |

The missing fourth markout was not the only gap: the four recorded maker fills
reconstruct a residual long even though the authoritative final venue state is
flat. The shutdown taker close filled but was not yet visible in REST fill
history when the engine stopped journaling. Its new immutable audit correctly
reports `fill_inventory_reconciliation_mismatch` and is
`data/logs/live/apex_regime_mm_canary_apex-mm-live-1785570631759_legacy_four_fill_gap_v2.json`.
This run is useful sparse execution evidence but is incomplete session-PnL
evidence.

The shutdown path now waits for the exact cleanup OID in the private fill
stream, falls back to a bounded eventually-consistent REST challenge, journals
the fill and fee, attributes slippage to that close's own submitted reference
price, and requires a book at the configured one-second markout horizon before
reporting `STOPPED`. The report-only auditor independently rejects any final
venue position that cannot be reconstructed from journaled fills.

Fill/cleanup run: `apex-mm-live-1785578486597`.

| Metric | Observed |
|---|---:|
| Runtime | 130.8 seconds |
| Quote observations | 38 |
| Live order intents | 52 |
| Accepted acknowledgements | 52/52 |
| Fills | 1 maker entry + 1 taker cleanup |
| Filled notional | $23.93145 total |
| Maximum reconstructed inventory | $11.96601 |
| Fees | $0.006892 |
| Closed price PnL | -$0.00057 |
| Net account change | -$0.007462 |
| Ledger fault events | 0; missing runtime-fault attribution fixed afterward |
| Acknowledgement latency | 609–1,296 ms; median 857.5 ms |
| Final position | Flat |
| Final open orders | 0 |
| Final account equity | $153.58137449 |

The fill run is valid execution evidence but not complete quality evidence:
the stream error forced shutdown before a one-second markout or in-position
liquidation sample. The audit explicitly reports those gaps rather than
inventing values. A later attribution audit also rejected its originally
reported `+0.6352 bps` slippage: the resting bid was submitted and filled at
`$62,979`, but repeated state telemetry had rebound that order ID to a newer
`$62,975` theoretical bid. This changed no order, fill, fee, or account PnL;
it invalidated only the derived slippage row.

Post-repair bounded run: `apex-mm-live-1785579099783`.

| Metric | Observed |
|---|---:|
| Runtime | 161.8 seconds |
| Quote observations | 73 |
| Live order intents | 52 |
| Accepted acknowledgements | 52/52 |
| Fills / faults | 0 / 0 |
| Acknowledgement latency | 604–1,169 ms; median 885.5 ms |
| Orphan quality metrics | 0 |
| Final position / open orders | Flat / 0 |
| Final account equity | $153.58137449 |

The repaired run's report-only audit is
`/tmp/apex-mm-live-1785579099783-audit.json` for the current workstation
session. The authoritative append-only source is
`data/live/apex_regime_mm/decisions.jsonl`. An independent read-only venue query
matched its final equity, flat position, and zero open orders.

Post-attribution-repair observation run: `apex-mm-live-1785579914397`.

| Metric | Observed |
|---|---:|
| Runtime | 499.3 seconds |
| Quote observations | 322 |
| Live order intents / accepted acknowledgements | 88 / 88 |
| Acknowledgement latency | 599–1,241 ms; median 819.5 ms |
| Fills / faults | 0 / 0 |
| Orphan or mismatched quality metrics | 0 |
| Final position / open orders | Flat / 0 |
| Final account equity | $153.58137449 |

The immutable attribution-aware audits are:

- `data/logs/live/apex_regime_mm_canary_apex-mm-live-1785578486597_attribution_v2.json`
- `data/logs/live/apex_regime_mm_canary_apex-mm-live-1785579914397_attribution_v2.json`

Pre-order-update fault run: `apex-mm-live-1785580914097`.

| Metric | Observed |
|---|---:|
| Runtime | 30.8 seconds |
| Quote observations | 19 |
| Live order intents / accepted acknowledgements | 4 / 4 |
| Fills | 0 |
| Faults | 1 order-stream confirmation timeout |
| Final position / open orders | Flat / 0 |
| Final account equity | $153.58137449 |

Its immutable pre-fix audit is
`data/logs/live/apex_regime_mm_canary_apex-mm-live-1785580914097_pre_order_updates_fix.json`.
The run demonstrates safe cleanup but falsifies reliable cancellation liveness
when `openOrders` is used without `orderUpdates`.

The first `orderUpdates` run, `apex-mm-live-1785581759611`, then falsified reuse
of the richer REST parser: both quotes were accepted, but the live update did
not contain a boolean `reduceOnly` field. Verified shutdown canceled both
quotes and finished flat at unchanged equity. A subsequent bounded schema probe
captured field names and types only, canceled its far-from-market quote, and
also finished flat at unchanged equity. This evidence produced the dedicated
lean update parser and its deterministic contract test.

First post-lean-parser fill run: `apex-mm-live-1785582168300`.

| Metric | Observed |
|---|---:|
| Runtime | 576.5 seconds |
| Quote observations | 486 |
| Live order intents / accepted acknowledgements | 128 / 128 |
| Fills | 1 maker entry + 1 taker cleanup |
| Maker execution slippage | 0.00 bps |
| Filled notional | $23.94551 total |
| Maximum inventory | about $11.97 |
| Minimum liquidation distance | 32.48% |
| Fees | $0.006896 |
| Closed price PnL | +$0.000570 |
| Net account change | -$0.006326 |
| Final position / open orders | Flat / 0 |

The fill retired the bid from the streamed open-order projection, but the
facade's mutation-expected ID set still retained it. Canceling the remaining
ask therefore waited for the already-filled bid and produced a false REST
confirmation mismatch. Cleanup remained correct, but the fault prevented the
one-second markout. The facade now synchronizes its expected ID set from every
confirmed non-mutation stream snapshot before later cancel/replace mutations.
The exact fill-then-cancel sequence is covered by a deterministic regression
test. Its immutable audit is
`data/logs/live/apex_regime_mm_canary_apex-mm-live-1785582168300_first_post_lean_fill.json`.

Post-fill-state-repair no-fill run: `apex-mm-live-1785582984143`.

| Metric | Observed |
|---|---:|
| Runtime | 1,275.6 seconds |
| Quote observations | 1,082 |
| Live order intents / accepted acknowledgements | 324 / 324 |
| Acknowledgement latency | 581–1,270 ms; median 870 ms |
| Fills / faults | 0 / 0 |
| Final position / open orders | Flat / 0 |
| Final account equity | $153.57504849 |

The immutable report-only audit is
`data/logs/live/apex_regime_mm_canary_apex-mm-live-1785582984143_fill_state_revalidation.json`.
An independent public-wallet-only mainnet query matched the final account
equity and verified zero BTC position and zero BTC open orders. This run
increases confidence in sustained no-fill transport and cleanup. It does not
validate the repaired fill-followed-by-cancel path because no order filled.

The operator dashboard now gives its plain-language strategy flow the full
terminal width: `INPUT -> DECISION -> ORDERS -> FIRST FILL -> EXIT/RISK`. It
explicitly says that resting quotes are not trades, regime and ML are unused,
profitability is unproven, and the policy has no fixed TP/SL. A 140-column
rendering test prevents the prior half-width truncation from recurring.

Cancel/fill race run: `apex-mm-live-1785585968515`.

| Metric | Observed |
|---|---:|
| Runtime | 421.7 seconds |
| Order intents / accepted acknowledgements | 77 / 76 |
| Acknowledgement latency | 620–1,447 ms; median 892 ms |
| Maker / cleanup taker fills | 1 / 1 |
| Filled notional / fees | $23.97477 / $0.006904 |
| Maker / cleanup prices | $63,090 / $63,093 |
| Closed price PnL | -$0.00057 |
| Account-value change | -$0.007474 |
| Final position / open orders | Flat / 0 |

The maker ask filled while its cancel request was in flight. Hyperliquid
correctly rejected the cancel because the order was already filled, but the
engine treated that terminal fill status as an unrecovered cancel failure. The
repaired lifecycle now (1) resolves rejected or ambiguous cancels by exact
venue order ID, (2) accepts only `filled` or `canceled` as terminal completion,
(3) retires that ID from the streaming facade's expected-open set, and (4)
journals a true open cancel rejection as a `FAULT` rather than allowing an
unreported exception.

The immutable report-only audit is
`data/logs/live/apex_regime_mm_canary_apex-mm-live-1785585968515_cancel_fill_race_post_cleanup_evidence.json`.
It records both fills and proves the final venue projection flat, but correctly
marks evidence incomplete: neither fill-time inventory nor liquidation
distance was sampled, and the actual markout horizons were 3,162 ms and 10,513
ms rather than the configured 1,000 ms. The auditor now accepts only the first
book from 1,000 through 2,000 ms, where the extra 1,000 ms is the configured
maximum book age; later samples remain visible but cannot masquerade as
one-second evidence.

Latest serial-transport no-fill run: `apex-mm-live-1785587744224`.

| Metric | Observed |
|---|---:|
| Maker intents | 294: 147 buy / 147 sell |
| Explicit batches in old ledger | 0 |
| Fills / faults | 0 / 0 |
| Acknowledgement latency | 578–4,015 ms; median 882 ms |
| Buy book age | median 510.4 ms; maximum 826.5 ms |
| Sell book age | median 1,176.5 ms; maximum 3,499.9 ms |
| Intents over 1,000 ms | 114, all sell-side |
| Final position / open orders | Flat / 0 |
| Final account equity | $153.56757449 |

The authoritative superseding audit is
`data/logs/live/apex_regime_mm_canary_apex-mm-live-1785587744224_quote_freshness_v3.json`
with SHA-256
`3de443be7cb58c3d0128d4452f22f06f38deae4f8337f530ffc115423c2de2aa`.
It marks coverage incomplete with
`maker_quote_intent_exceeded_maximum_book_age`. This is the direct evidence for
the batch transport repair. No post-repair live batch has been authorized or
run yet, so real venue timing for the new path remains unverified.

## Confidence and falsifiers

- **Transport repair: high confidence for bounded no-fill operation.** Supported by
  deterministic failure-injection tests, real private-stream schema validation,
  bounded live lifecycles, and independent flat-account checks. A longer
  canary producing HTTP 429, stream/REST drift, orphan orders, or non-flat
  shutdown would falsify this assessment.
- **Fill-update repair: medium confidence.** The missing-field case is covered
  deterministically, and the next 162-second and 499-second live runs remained
  healthy, but neither had a fill. A new real fill processed without a schema
  stop would increase confidence; another stop would falsify the repair.
- **Cancel/fill race repair: medium confidence.** The exact engine and streaming
  identity sequences are reproduced by deterministic tests, including a true
  open-order rejection path that must emit `FAULT`. A new mainnet maker fill
  followed by continuous inventory-aware quoting without a false cancel fault
  would raise confidence; another terminal-status mismatch would falsify it.
- **Single-action batch repair: medium confidence in implementation, low in live
  behavior.** Official-SDK request shape, ordered acknowledgements, partial
  rejection rollback, ambiguous-response recovery, shared timestamps, and TUI
  identity are covered by deterministic tests. A fresh authorized run with any
  maker intent older than 1,000 ms, mismatched batch identities, or unreconciled
  partial acceptance would falsify the repair.
- **Markout horizon attribution: high confidence as an audit rule.** Actual and
  requested horizons are separate fields, and delayed observations fail
  coverage. A report labeling a markout beyond 2,000 ms as complete would
  falsify this assessment.
- **Fill-price attribution repair: medium confidence.** The historical defect
  is reproduced and rejected by deterministic tests and the new auditor. A new
  real fill whose expected price equals the acknowledged submitted limit would
  raise confidence.
- **Continuous operation: medium confidence.** The periodic drift challenge ran,
  but reconnects and multiple real fills remain untested.
- **Profitability: low confidence / not demonstrated.** The final run had zero
  fills. After-cost maker/taker fees, funding, markouts, adverse selection, and
  inventory recovery require real fills before any edge claim can be updated.

Fresh offline verification passed 2,520 Python tests with four network tests
deselected, the complete Rust TUI test suite, strict Clippy, Rust formatting,
task-scoped Ruff, and diff hygiene. The backend and unified launcher both
refused a no-flag invocation before constructing execution authority. The
repository-wide Ruff baseline still contains 33 unrelated legacy findings.
A signing-incapable public-wallet snapshot at `2026-08-01T20:24:03Z` reported
$153.56757449 account value and withdrawable balance, BTC flat, zero BTC open
orders, 1.5/4.5 bps maker/taker rates, a $1 tick, 0.00001 BTC size step,
unified-account mode, and the expected 40x BTC venue maximum. Armed startup must
still revalidate this time-sensitive state.

## Next evidence cycle

Run the unified live backend plus read-only TUI, monitor every journal event,
and stop only for an operator request or technical fault. After each real fill,
review fee, liquidity side, latency, slippage, one-second markout, inventory
path, liquidation distance, and realized after-cost PnL. Apply one bounded,
test-first strategy change only when that evidence identifies a specific defect
or opportunity.
