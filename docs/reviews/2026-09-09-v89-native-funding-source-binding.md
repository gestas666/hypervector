# Native funding sources: exact offsets, separate receipt clocks and an explicit price proxy

The isolated component at `1d8ad990ac1b87e40c7df3fb754d994619bdeb62` binds captured
funding rates to their original native settlement milliseconds and the declared
settlement-hour candle open. It preserves source knowledge separately. All 714
preregistered source-only queries agree exactly with an independent reconstruction
from authenticated raw responses. The archived source reproduces the report and
audit byte for byte and passes all 102 offline tests.

Confidence is high for this fixed source, clock and synthetic arithmetic scope.
It does not establish real settlement-time marks, attainable fills, complete
portfolio replay or future profitability. No prospective strategy signals,
positions, cash flows or returns were computed. No live implementation, profile,
TUI, collector source, order or trading process changed.

## Fixed experiment and observed coverage

The plan was committed before real-source measurement in `2a53096`. Inputs are
the previously registered complete-source snapshot and receipt tape, authenticated
through journal revision 8. The snapshot ends at September 9 00:32:06.584 UTC.
It contains 1,336 indexed raw requests. The independent auditor imports no
Hypervector implementation and reconstructs first/latest occurrences at fifteen
knowledge cutoffs directly from their authenticated raw responses.

| Query scope | Queries | Ready bindings | Explicitly unavailable |
| --- | ---: | ---: | ---: |
| Snapshot tail: 49 hours, seven assets, two source variants | 686 | 686 | 0 |
| One millisecond before joint first-rate/price knowledge | 14 | 0 | 14 |
| At joint first-rate/price knowledge | 14 | 14 | 0 |
| Total | 714 | 700 | 14 |

All fourteen unavailable cases identify the missing opening-price candle and
produce no accounting observation. The report retains the available funding
records alongside that absence. Missing funding is never replaced by zero.
Queries repeat source identities across variants and boundaries; they are not
714 independent funding events or trades.

There are 343 distinct asset/hour identities. Thirty-five first funding receipts
meet the registered sixty-second limit. The other 308 are older bootstrap
observations before the study starts, not late study-period arrivals. Each asset
has five timely hours in this snapshot. All seven study-opening rates are timely:
their receipt delays range from 11,761 to 13,950 milliseconds after native
settlement. These bounded observations do not establish future collection health.

Native settlement offsets range from 3 to 85 milliseconds after the hour across
these inputs; the study-opening offset is 76 milliseconds. Rounding to the hour
would erase observed timing. First/latest funding-rate and opening-price outputs
agree for all 343 identities in this snapshot. Synthetic revisions and reversions
separately verify that source changes and different receipt identities survive.

## Price and account meaning

All 700 ready queries retain `price_known_by_settlement=false`. The completed
opening candle arrives after settlement: study-opening core candles were first
received 65.332–66.574 seconds after the hour, and the three XYZ fifteen-minute
candles at 906.674–907.376 seconds. Their opens remain explicitly conditional
price proxies, not contemporaneously observed venue settlement marks. The
adapter does not retime the funding event to candle completion or receipt.

The component validates selected and first rate payloads, their native availability,
hourly identity, source kind, symbol, receipt ordering and normalized hashes.
It validates full candle values and requires the same asset/hour opening candle.
Historical funding with unknown native offsets is outside this captured-source
adapter; its separate historical representation remains unchanged.

Six synthetic account cases cover long/short exposure and positive, negative and
zero funding rates. They use the existing incremental account and independent
Decimal arithmetic. Other controls cover exact timeliness boundaries, native
settlement revisions, price knowledge immediately before/at/after settlement,
future or premature receipts, missing rates, corrupted provenance and ambiguous
price windows. No real account quantities or cash flows enter this qualification.

## Verification, corrections and limits

All 102 targeted offline tests pass in the worktree and from the frozen archive.
The two adapter modules have complete unit coverage: 110/110 executable statements
and 24/24 branches. Across those modules and the two qualification/audit drivers,
combined unit tests plus archived real-source runs cover 335/342 statements and
53/60 branches. Seven qualification-driver rejection lines remain unexercised.
The independent auditor's full line/branch coverage includes the real-source
audit; its unit-only coverage is lower and is recorded separately. These figures
do not describe the provider library or the full portfolio evaluator.

Fault tests exposed a prototype omission: a valid selected revision could conceal
an invalid first-rate payload. Five failing tests preceded validation of both
rates. A separate audit regression exposed an overly broad file-identity comparison
that included the journal's descriptive role; it now checks registered path,
bytes and SHA256. The initial failures are preserved. A missing nested-test
docstring was also corrected before final structural and archive acceptance.

All ten new source/test files pass Ruff, formatting, file/function limits,
annotations, public docstrings and indentation checks. All 5,286 Git blobs in
the archive match their committed identities. Archive SHA256:
`690dbcd971fd90ab762109151348873020050dea0dfb0599612ca7f0d94c5f8b`.
Both the 2,287,237-byte report and 952-byte audit reproduce exactly.

At September 9 02:45:09 UTC both public collectors were alive; all fifteen pinned
collector source files and the live profile hash were unchanged. All 2,257 prior
journal evidence files, totaling 826,710,861 bytes, were reverified. This is source
health evidence, not a fresh venue account reconciliation.

Any changed source identity, hidden missing input, altered native timestamp,
incorrect price proxy, fabricated receipt, independent mismatch or failed archive
reproduction invalidates the affected qualification. Remaining work is frozen
route cost/trigger handling, metadata semantics, complete provider/regime behavior,
source-to-modeled-fill mapping and all 24 account cells. Both prospective outcome
seals remain in force. The next implementation task is the route cost and trigger
adapter, preserving the existing contracts and using synthetic accounting controls.

Evidence: `data/logs/research/bidirectional_cohort/v89_native_funding_source_binding_20260909_v1/`.
