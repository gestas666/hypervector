# Frozen provider clock and history qualification

The receipt reader and historical account adapter are qualified components;
the complete prospective comparison is not. This investigation addresses the
remaining distinction between completed-bar decisions, actual knowledge time,
rolling history and modeled entry time. No live code, economic registration,
running collector or sealed outcome is changed.

Inspection found that all seven frozen providers use completion timestamps
(one minute for core, fifteen minutes for XYZ). The production poller takes
its clock before fetching. Its history trim uses the full millisecond clock,
so any positive subminute delay can remove the oldest minute relative to an
exactly fourteen-day, bar-aligned window. HYPE's observe setting changes its
authority annotation, not signal eligibility. The current worktree also has
the older daily core extractor; the separately qualified 9feb625 gap repair
must be reused before any future batched extraction. This audit calls each
production provider at individual cutoffs and does not use that extractor.

Before looking at differences, fix these historical probes: September 6, 2026,
every full UTC hour, plus 11:59 and 12:01 for the four core assets. Use both
registered first/last core sources and the common native XYZ sources, with the
configured fourteen-day history. Authenticate every consumed Parquet byte
against the existing allocation journal before parsing it. No source later
than September 7 is permitted. These are historical model-clock probes, not
measurements of actual historical receipt latency.

For each probe compare:

1. The provider on the exact completed history ending at decision time T.
2. The same complete history observed at T + 5 seconds. Signal identity, price,
   exits, stop anchors and readiness should be identical if only the observation
   clock changed. Entry-age validation uses the later clock separately.
3. The completed history trimmed using T + 5 seconds as the rolling cutoff.
   Retain every change in provider output, including small numerical changes.
   Do not relax exact comparisons or choose a history for favorable performance.

Independently check the selected grid endpoints and expected row counts. Compare
full serialized evaluations and intents, not just trade counts. Report exact
execution-field and diagnostic-field differences separately with their values.
Verify future source rows cannot alter the completed decision prefix. Include
synthetic clock/deadline and malformed-input tests; prohibit network in tests.

This establishes provider clock/history behavior, not standalone indicator
correctness, full signal parity on all historical minutes, receipt-source
assembly, future fills, funding or account integration. A discrepancy is a
qualification finding, not a reason to modify a frozen strategy. Preserve
evidence and prepare an explicit interpretation proposal if resolving a
discrepancy requires changing registered economics.

Success for this step is an authenticated, reproducible inventory and complete
report of the fixed probes, with all failures retained. Changed source hashes,
unreported output changes, future inputs in an earlier decision or different
results from the source archive invalidate its claims. Full prospective replay
and profitable live operation remain outstanding regardless of these results.
