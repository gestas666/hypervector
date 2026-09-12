# SNDK source reconciliation: capture and coverage checkpoint

The August 19 source reconciliation is **being tested**. Its acquisition and
timestamp qualification are complete; price agreement, original exit-clock
semantics, independent numerical reconciliation and the final journal revision
remain unfinished. This note does not declare the full diagnosis complete.

The preceding [day-influence study](2026-09-12-v89-sndk-day-influence.md) remains
complete. It identified August 19 as influential in an already-explored sample.
The present check is diagnostic and selected after those outcomes were observed.

## Qualified acquisition

The frozen plan is **6db59ea**, in `hypervector-v89-sndk-source-20260912`.
The local archive inventory found 38 SNDK trade/price manifests and 3,865 HIP-3
book manifests, but no candle bundle or August 19-start bundle in those two
roots. Bounded database queries found no overlapping SNDK archive bundle,
August 19 local event file or canonical minute bar. These are scoped findings,
not a claim that no other local source exists.

The [documented HIP-3 candle route](https://docs.0xarchive.io/rest-api/candles)
was used with exact symbol `xyz:SNDK`, August 19 00:00 through August 20 00:00
UTC, limit 10,000 and a two-page budget per interval. Four quality GETs and two
candle GETs returned HTTP 200. Raw request/response evidence and hashes remain
retained, with no execution authority.

| Interval | Raw rows | In the half-open day | Preserved end-boundary rows | Duplicate timestamps | Missing slots |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 minute | 1,441 | 1,440 | 1 | 0 | 0 |
| 15 minutes | 97 | 96 | 1 | 0 | 0 |

Confidence is **high for these captured clock grids**: exact ordered timestamp
lists match the expected day and each response's checksum is authenticated.
This does not yet establish numerical validity, source-price agreement or
historical mark-price/stop-trigger semantics.

The vendor reports HIP-3 operational. Its overall degraded state concerns
funding/open-interest. Exact SNDK quality metadata omits candles; completeness
figures for its other data families are not candle-coverage evidence. The
August 18-and-later incident query returns zero records, which cannot rule out
an earlier-starting incident. These limitations remain recorded.

## Retained capture failure and recovery

Initial source **a601a63** stopped after saving the successful minute response:
the reader incorrectly required an explicit `next_cursor` field. The saved
[OpenAPI contract](https://docs.0xarchive.io/openapi.json) makes that property
optional. A regression reproduced the failure before the reader was corrected.
The original failed terminal record and raw bytes were preserved.

Final capture source **a17dadbb416d5f95608e799f0cc0d819069d2cc6** accepts an
omitted cursor while retaining malformed/repeated-cursor and page-budget checks.
The remaining-15m phase made only the outstanding quarter-hour request; the
minute page was authenticated and reused without another network request.

**38 offline tests pass** both in the worktree and from its nine-file source
archive. Capture statement coverage is **111/117**, branch coverage **37/38**;
remaining uncovered code is the CLI entry path. Ruff, formatting and source
size checks pass. The capture worktree is clean. These checks cover acquisition,
not the pending price/exit analysis.

## Next action and account boundary

Next, validate every selected source row and reproduce the native Parquet from
its retained response; compare full-day native/vendor OHLCV and complete vendor
minute aggregates. Trace the original account engine's exit-clock convention
before assigning movement before or after the modeled stop. Reconcile all
reported differences independently, then publish the full review and journal.
No source is selected by PnL and no alternative exit policy is being simulated.

At **September 12 08:35:12 UTC**, seven authenticated unsigned venue responses
retain the **-0.306 SNDK short**, entry **1629.2**, **10x isolated**,
**-$0.0918 unrealized**, and the full-size buy reduce-only native stop
**542326955281** at **1669.9**. Eighteen funding cash rows sum to **+$0.084062**.
Core is flat/order-free. The bounded fill query contains the original entry and
no additional fill. Original runner PIDs are absent; seven terminal rows and
installed profile/TUI/ledger hashes remain unchanged. Process visibility is
limited, and the snapshot does not establish later account state.

No production code, TUI, strategy, risk, deployment or financial action occurred.
Both prospective outcome seals remain unopened. Existing installation questions
remain pending; the standing continuous objective remains active.

Evidence: [capture qualification](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/capture_qualification.json),
[quality decision](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/quality_decision.json),
[account boundary](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/current_boundary/response_integrity.json).
