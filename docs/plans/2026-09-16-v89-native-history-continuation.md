# Native-minute history: bounded search result and continuation plan

The original September 16 fourteen-day startup comparison remains deferred.
High confidence in the inspected sources, not in an exhaustive filesystem
claim: this additional bounded search found no native one-minute candles for
the remaining noncrypto gaps documented in the qualified snapshot supplement.

- Four older source exports contain official 15-minute candles ending August 6,
  plus funding records. They do not supply September native minute candles.
- Eleven Git worktrees dated September 2–8 expose no qualifying noncrypto
  minute cache in their inspected top-level cache directories. Two contain an
  older BTC cache; this is not a recursive scan of every worktree file.
- The research database has no matching noncrypto shadow observations in the
  missing September 2–7 interval before the original startup cutoff. Its
  canonical one-minute trade-bar view aggregates trades and is not evidence
  of native candleSnapshot values.
- Older snapshot directories and documented trade/midpoint reconstructions
  inspected in this search do not add qualifying native September history.

Paths, four export hashes, schemas, worktree inventory, SQL query and relevant
view definitions are retained in
`data/logs/research/bidirectional_cohort/v89_native_history_continuation_20260916_v1/bounded_source_search.json`.
A transient database writer lock cleared after its owner exited; no process was
stopped or restarted to obtain the read-only result.

The venue documents limited recent candleSnapshot history. The actual startup
snapshots contained more than 5,000 rows for several assets, so the documented
count must not be treated as an empirically proven hard row limit for these
captures. Neither observation establishes that the missing September 2–7
minutes remain retrievable now.
[Official Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).

The proposed continuation is a separate public, credential-free native 1m
collector for SPCX, SNDK and Brent. Existing core minute collectors and the
sealed noncrypto 15-minute collectors would remain unchanged. Reuse the
existing immutable public HTTP recorder and qualified candle validation;
the existing noncrypto query builder and index assume 15m and therefore cannot
be reused unchanged for this purpose.

Before acquisition, freeze and qualify the request scope, event window,
receipt cutoff, first/latest revision policies, source and configuration hashes,
restart recovery and singleton ownership. Preserve original responses,
zero-volume candles, gaps and revisions. Reject unsupported or malformed
sources instead of synthesizing missing minutes. Offline tests must cover
incomplete tails, conflicts, interrupted writes, restart recovery, deadline and
rate handling; no network calls belong in those tests.

A candidate budget is one public request per minute across the three assets,
with a maximum one-day request window and explicit backoff. This is a design
proposal, not a deployed setting or exact billing claim. Rate qualification
must include the other clients sharing the IP and the venue's documented
candle-response weighting.
[Official rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits).

The recovered native history is continuous for all three assets from
September 7 13:34 UTC through the original qualified completed prefix. Subject
to uninterrupted continuation, September 21 13:34 UTC is the earliest end of a
new fourteen-day event window excluding the old gaps. It is conditional
coverage eligibility, not a go-live ETA or completion of the original
September 16 experiment. The exact future observation and receipt cutoffs
must be declared before capture and must not backdate later responses.

The eventual experiment should compare one fixed startup boundary using the
recent native window versus the complete fourteen-day window, retaining all
seven provider outputs and fourteen regime outputs, source variants and
technical failures. History-length differences are reported results, not
implicit economic rejection gates. It must not compute sealed performance
outcomes early or replace the original requirement with a shorter test.

Status: planned, not implemented or running. A newly observed live SPCX entry
took priority during preparation. Its signal and stop receipts are reviewed in
`docs/reviews/2026-09-16-v89-spcx-short-entry-1800.md`; explaining the observed
entry-to-protection latency is the next bounded execution investigation.

New authenticated native bytes in the missing intervals would update the
negative search result. Missing future minutes or unqualified receipt/revision
policies would defer the new comparison. No financial process, live source,
deployment or strategy setting was changed by this search or plan.
