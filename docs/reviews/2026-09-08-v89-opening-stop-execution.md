# SNDK and SPCX opening stop execution

The two September 8 exits reconcile to **−$10.796513 net**. Reaching the
retained venue stop prices accounts for **−$9.7972 (90.744% of net loss)**;
trigger-to-fill price movement adds −$0.8236. Fees cost $0.172550 and funding
costs a net $0.003163. High confidence in this bounded accounting and the exact
public/native fill matches. Two trades do not establish deterioration, an
opening-session effect, or a profitable replacement rule.

| Component, USD | SNDK short | SPCX long | Total |
|---|---:|---:|---:|
| Entry → retained venue trigger | −6.4807 | −3.3165 | −9.7972 |
| Trigger → actual exit | −0.6226 | −0.2010 | −0.8236 |
| Gross price PnL | −7.1033 | −3.5175 | −10.6208 |
| Fees paid | 0.086740 | 0.085810 | 0.172550 |
| Funding received / paid | −0.026031 | +0.022868 | −0.003163 |
| Net PnL | **−7.216071** | **−3.580442** | **−10.796513** |

## Scope and evidence

Run `bidirectional-live-1788809099824`. SNDK entered short 0.283 at 1761.2,
OID 539043720855, September 8 07:00:19.183 UTC. Its full-size stop
539043759446 filled at 1786.3 at 13:30:27.920 UTC. SPCX entered long 3.35 at
148.76, OID 539125419115, 09:00:15.109 UTC. Stop 539125458790 filled at
147.71 at 13:32:33.954 UTC. These are distinct from the previously audited
first SNDK and SPCX closes.

Both complete current-run asset prefixes are frozen and verified against the
14:04:48 checkpoint hashes. Seven unsigned native Info responses retain exact
response bytes and individual request clocks. No signing client was constructed.
The configured public wallet was loaded through a wallet-only private mapping.
Fill fees are counted once; separate ledger fee events are not additional costs.
All ten lifecycle funding settlements match native amount, rate, signed size,
timestamp and transaction identity.

The ledger retains 1,563 native resting-stop observations at SNDK **1784.1** and
1,091 at SPCX **147.77**. Every retained observation has the expected side,
full quantity and reduce-only trigger status. These prices agree with venue
precision applied to the strategy anchors 1784.076817290642 and
147.77478360880863. Rounding contributes −$0.0225857962572245 within the barrier
component; it is not charged again. Final native order status confirms filled
Stop Market orders with matching client IDs, but clears `triggerPx` to zero.
The original wires are therefore supported by retained parsed venue observations,
not a raw pre-trigger order-status envelope.

## Execution qualification

Both actual exit TIDs match public aggressor trades in price, size, side and
millisecond timestamp. Complete focused windows contain 1,449 SNDK and 1,888
SPCX public trades. The initial six-minute requests hit their five-page bounds
and remain preserved as incomplete; they are not presented as full coverage.

Each six-minute price archive contains 120 marks. The first observed qualifying
mark through each fill is at that exact fill timestamp: SNDK 1785 ≥ 1784.1;
SPCX 147.75 ≤ 147.77. This supports the trigger explanation. Hyperliquid's
[TP/SL documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/take-profit-and-stop-loss-orders-tp-sl)
identifies mark price as the trigger reference. Maximum sampled mark gaps are
3,163 ms; matching timestamps do not measure zero trigger-to-fill latency.

All 787 books per asset have sufficient visible closing depth for the actual
quantity. Maximum observation gap is 500 ms. SNDK's adjacent hypothetical buy
VWAPs are 1782.8 at −420 ms and 1783.395053 at +80 ms relative to the fill;
SPCX's sell VWAPs are 147.75 at −343 ms and 148.18 at +46 ms. These snapshots
are not the execution instant and cannot prove an alternative achievable fill.
The public matches establish that the actual prices were traded.

Adverse trigger-to-fill movement is **12.331 bps SNDK** and **4.060 bps SPCX**.
The local ledger records the fills 11.998 and 5.832 seconds later respectively.
That is observation delay, not placement latency or measured stop-trigger delay.
No incorrect stop quantity, changed trigger, unmatched fee/funding settlement,
or failed full-position close is demonstrated in this scope.

## Validation and limitations

Source `cdf7a2f15db02d9b1a4c696c6c304d42c30d4a2f` is research-only in the isolated
worktree. **207 offline tests pass**, including corruption controls for both
directions and existing archive normalization/depth helpers. The two new pure
calculation modules cover 158/158 statements and 48/48 branches. This coverage
claim does not include all acquisition or I/O code. Ruff checks and structural
limits pass. All 5,087 archived Git blobs match their source identities; archive
replay reproduces the report byte-for-byte. A separate standard-library Decimal
calculation, importing no audit implementation, independently checks 18 economic
comparisons and both complete resting-observation counts.

Confidence is high in accounting and source identity, moderate in the sampled
trigger explanation, and low in a causal session diagnosis. Revised native
evidence, a conflicting retained stop observation, an unmatched settlement or
public TID, or failed source hashes would falsify the respective findings.
Continuous order-book/mark events around execution would improve latency and
liquidity attribution. The sealed prospective experiment remains unopened.

## Decision and next investigation

Retain the descriptive result. Do not change stop widths, sizing, entry filters
or execution from two losses. Existing all-run telemetry records five closed
trades totaling −$21.118639; the table above covers only these latest two.

| Option | Expected value / confidence | Cost and failure mode | Disposition |
|---|---|---|---|
| Leave rules unchanged while researching | Avoids fitting two outcomes; does not improve a weak strategy by itself | Further diagnostic work required | Current action |
| Change stops or impose a cash-open filter now | Expected return effect unverified | Could discard winners or increase loss size; strong selection bias | No proposal |
| Attribute cash-open exposure in the registered historical shared portfolio | Moderate diagnostic value; causal interpretation remains low confidence | Existing history is already explored; overlapping trades and event days confound attribution | Highest-priority next study |

Next hypothesis: `v89_noncrypto_cash_open_exposure_attribution_20260908_v1`.
Preregister the local-time window, session calendar and shared-account attribution
before calculating outcomes. Use existing registered historical SNDK/SPCX
lifecycles and marks; compare opening exposure with other exposure on the same
days, preserve asset/direction and chronological partitions, and report sample
counts. This is descriptive attribution, not threshold optimization or a live
filter. Prior session feasibility/source-availability studies and the deferred
SPCX crossing filter were checked; none answers this joint historical exposure
question. Positive results would still require independent prospective validation.

Operational observation at **15:15:54 UTC**: the approved TUI binary remains
installed, but monitor PID 88441 has exited and Terminal window 5958 says
`[Process completed]`. Tracked backend/supervisor/reporter PIDs remain absent.
Exit requester is unresolved. No process lifecycle action was taken in this audit.
The last native flat/no-orders snapshot remains 14:11 UTC; it is not a later
account-state claim. No live strategy, configuration or deployment changed.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_noncrypto_opening_stop_execution_20260908_v1/`.
