# V89 first prospective source slot

High confidence in the first-slot capture acceptance. The first completed
15-minute candles for the frozen SNDK/Brent study were received within the
declared 60-second deadline. Exact raw response bytes, normalized value hashes,
source identity and causal availability timestamps reconcile with a consistent
SQLite backup. Changed checksums, a later first receipt or missing observations
would falsify this acceptance.

| Observation | SNDK receipt delay | Brent receipt delay |
| --- | ---: | ---: |
| Candle opened 2026-09-08 04:00 UTC, closed 04:15 UTC | 5,560 ms | 5,890 ms |
| Funding at 04:00:00.012 UTC | 6,338 ms | 6,652 ms |

Both metadata observations also reconcile. Six observations across five raw
responses were checked with the collector's frozen envelope decoder and
normalizer. The collector's eleven source files, frozen protocol and four
warmup files all retained their recorded hashes. PID 75062 was observed alive
with its original start time during acceptance.

This is data-capture evidence. No candidate outcome, return comparison or
promotion was calculated. Future coverage remains unproven; the next candle is
due at 04:30 UTC and the declared study ends at 2026-09-22 04:00 UTC. The SQLite
backup is internally consistent, while status and raw files have separate
capture times. The first-slot audit validates each raw response against the
index rather than assuming that those copies are simultaneous.

Immutable artifacts are under
`data/logs/research/bidirectional_cohort/v89_prospective_first_slot_acceptance_20260908_v1/`.
The standalone executed acceptance source and its log are beside that directory.
The journal revision records these sources without replacing the earlier
collector qualification evidence.
