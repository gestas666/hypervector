# Historical entry economics and explicit venue assumptions

The historical source adapter now connects native entry publications to the
existing account's price, sizing, fee and barrier calculations without creating
captured-receipt records. Confidence is high in the synthetic behavior and exact
source checks below. Its full historical account outcomes remain unmeasured.

The frozen source is `7f690ac764bdfbb73e9509a92d5954562387ca8d`. All 555 selected
account, routing, entry, provider, initialization and venue tests pass in the
worktree and in its verified archive. The measured entry,
venue and envelope modules have 100% statement coverage; the five measured
modules together cover 198/200 statements (99%). The catalog constructor is
also exercised by the real-file qualification, outside unit coverage.

## Source and account behavior

The adapter authenticates complete historical price tables and exact provider
JSON-line membership. It preserves admitted and withheld publications, the
recovered initial-report identity, source variants and separate decision,
knowledge and modeled opening clocks. It rechecks consumed files after
compilation so cached publications cannot hide a later source change.

The shared entry calculation retains provider sizing precedence, original
stop/target anchors, side-dependent slippage and fee rates. Synthetic tests
cover all seven assets under both original allocations. A real account-object
test independently checks quantity rounding, entry fees and reserved margin
with Decimal arithmetic. This is a synthetic account test, not a historical
trade result or venue execution claim.

The original September 8 unsigned core/XYZ metadata captures supply explicit
static unit assumptions. Independent decoding verifies the complete native
members plus 42 selected field/type checks across seven assets. Capture times
remain later than the historical account window; historical availability is
explicitly unverified. No current fee or margin-tier observation is substituted
into the original historical cost or liquidation assumptions.

| Asset | Captured size decimals | Captured maximum leverage |
|---|---:|---:|
| BTC | 5 | 40 |
| ETH | 4 | 25 |
| SOL | 2 | 20 |
| HYPE | 2 | 10 |
| xyz:SPCX | 2 | 20 |
| xyz:SNDK | 3 | 10 |
| xyz:BRENTOIL | 2 | 20 |

The values above describe the retained capture, not verified rules throughout
July 21–September 7 or a fresh current-venue read. Changes to actual historical
precision could change accepted quantities and account results.

## Verification and remaining scope

All 5,512 archived Git blobs, file kinds and executable bits match the commit.
The 33,510,098-byte archive has SHA-256
`d9f836a48b9c43bab79b498cc41f82d987ad6f3c492b6ca94eae5d8153eb913f`.
Evidence is under
`data/logs/research/bidirectional_cohort/v89_historical_entry_qualification_20260909_v1/`.
The independent venue reports reproduce byte-for-byte: 334,332 bytes, SHA-256
`92a9489934c33b9a15e7bb913028a1b69117e0c266809126b9a5b2847b39c5cb`.

A separate 24-hour synthetic profile measured 1,465 account events at 3.84
seconds of profiled account advancement. It excludes source-calendar creation
and does not establish whole-history throughput. It does not support the
earlier unverified concern that phase-history scanning dominates this sample.

Complete historical calendar assembly, native decision-time routing, independent
canonical history and every original source/cost/clock/allocation case remain
required by the [account plan](../plans/2026-09-09-v89-gap-market-account-followup.md).
The subsequent historical completion projection is separate work in progress
outside this frozen source. No live strategy, configuration, process, execution
client or deployment changed; both prospective outcome seals remain intact.

Altered source identities, hidden price proxies, manufactured receipt times,
changed sizing precedence, detached anchors, incorrect rounding, failed archive
reproduction or unexplained account differences invalidate the affected claim.
