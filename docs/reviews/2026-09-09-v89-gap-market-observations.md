# Historical missing candles with observed market quotes

The two August 1 SOL account minutes outside the scheduled-maintenance windows
contain changing order-book quotes despite missing trade candles. Confidence is
high in the authenticated observations and low in any inference about actual
fills, continuous stop triggers or profitability. This updates the bounded
retained-source inventory in revision 1; it does not replace the original
provider grids. Research source is `f2808ccbadaa19b33aadad6ce4d3a029d2922783`.

| August 1, 2026 UTC minute | Book observations | Public trades observed | Mark observations | Observed best bid range | Observed best ask range |
|---|---:|---:|---:|---|---|
| 13:55 | 131 | 0 | 1 | 72.926–72.928 | 72.927–72.929 |
| 16:47 | 131 | 0 | 1 | 72.794–72.798 | 72.795–72.799 |

In each minute the first book is at the minute boundary, the last is 500 ms
before the end, and the largest observed book interval is 500 ms. The retained
marks occur 760 ms and 56,423 ms after the respective minute boundaries. Those
sparse marks do not establish a continuous mark-trigger path. Absence of public
prints in this vendor response is not proof of venue-wide absence of trading.

Six bounded public-data captures cover 13:54–13:57 and 16:46–16:49 UTC. Together
they contain 787 book observations, 66 participant fills normalized into 33
public trades, and six price contexts. Those trades fall outside the two missing
minutes. All responses terminate after one page, with no next cursor. This is
consistent with the documented [pagination contract](https://docs.0xarchive.io/rest-api/pagination).
The documentation observation is retained; a separate raw documentation download
returned HTTP 403 and is not represented as an archived source document.

The existing archive replay helper now accepts an explicit core market family,
while retaining its original HIP-3 default. Family and symbol conflicts fail
before source consumption. The report verifies manifest identities, raw-to-
normalized agreement, bounds and counts. A separate raw-JSON/Decimal verifier
reconciles all 30 summary fields and rejects four deliberately changed records.
No order client is constructed and no candle is synthesized.

All 126 focused offline tests pass in both the worktree and the authenticated
source archive. Both report artifacts reproduce byte-for-byte. All 24 consumed
references are reauthenticated, and all 5,453 archived Git blobs and modes verify.
The pure minute-summary logic has full measured statement and branch coverage.
Combined unit/regression tests and offline CLI replay cover 142 of 149 statements
and 33 of 40 branches in the report module; that combined figure is not claimed
as unit-only coverage. The five changed files pass the recorded structure checks.

The initial independent verifier incorrectly required a present `next_cursor`
key. It now accepts absent or null terminal cursors, consistent with the primary
documentation. Failed attempts and corrected results remain separate. Earlier
coverage attempts missed the CLI entry point; the final filename-based coverage
artifact is the qualified measurement.

The original core provider comparison completed at September 9 16:08:41 UTC.
Its completion log reports eight streams, 552,960 checks and zero mismatches.
That final count has been observed in the log; independent verification of all
final payloads remains outstanding. It is not a financial result.

Retain these quotes as separate market observations. Missing candles, missing
quotes, sparse marks and locally constructed continuity prices are different
availability states. Do not infer a flat market, manufacture OHLC, or assign
historical observations a contemporaneous local receipt time. The next experiment
is the [complete historical account qualification](../plans/2026-09-09-v89-gap-market-account-followup.md).
It preserves all 48 days and all original source/cost/clock/allocation cases.

Changed source identities, failed raw reconciliation, incorrect minute bounds or
archive differences would falsify the relevant findings. Denser mark evidence
could update trigger uncertainty. No account outcome was evaluated, no live
change was deployed, and both prospective outcome seals remain intact.

Evidence: [journal revision 2](../research-journal/v89-historical-source-gaps-20260909-v2.json).
