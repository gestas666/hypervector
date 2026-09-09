# Authenticated historical routing snapshot reader

The reusable reader now preserves complete provider publications, including
readiness, exit fields, empty results and source diagnostics. Confidence is high
in its tested file/clock/payload contract and the reproduced historical prefixes.
Native routing actions, configured exit execution, dynamic account equivalence
and a profitable live recommendation remain unestablished.

## Implemented and verified

Source `eba80126287845b2d77875d6f961b6bdf49241e9` authenticates the supplied
snapshot, every consumed summary and the exact compressed bytes read later.
Summary and snapshot payload references must agree. Each requested stream must
begin at the explicit original start and remain contiguous. Missing streams,
duplicate identities, wrong variants, substituted paths, invalid clocks and
incorrect row counts fail explicitly. A shorter shared prefix remains partial.

Records retain each original JSON line and its compressed-file identity and line
number. Detached provider payloads preserve all fields and JSON numeric types.
The reader distinguishes absent evaluations from a published hold evaluation,
validates current provider/intent identity and causal native source clocks, and
retains explicit exit sides and reasons. It rejects duplicate JSON fields and
non-finite values. Streams merge chronologically in configured asset order while
holding at most one decoded chunk per asset. Full validation requires consuming
the iterator; a validated catalog alone is not a validated payload collection.

The existing typed compiler consumes the resulting scheduled batches. Its
inactive-authority and one-provider-per-asset validation is shared with the
reader. The compiler intentionally projects intents; complete evaluations and
exit data remain available through the authenticated record iterator.

Sixty-six new tests plus the existing 61 compiler/projection/preference checks
pass in the worktree and archive: **127 tests**, with all **222 statements and
72 branches** in the three new reader modules covered. A failing identity test
exposed whitespace normalization of an altered summary symbol; the correction
rejects it. This was a new undeployed reader defect, not a live execution defect.
Ruff and whitespace checks pass. All 5,412 archived Git blobs and executable
modes remain unchanged after the tests and historical exercise.

## Historical source reproduction

The revision-20 snapshot, independently verified at 11:41:31 UTC on September 9,
is authenticated through the immutable revision-20 journal. The requested final
scope remains every minute in `(July 21, September 7] UTC` and all four core/XYZ
variant pairs.

Both available `first/full_prefix` and `first/rolling_14d` pairs provide the
common prefix `(July 21, August 21] UTC`. **Each** contains:

- 44,640 complete minute sets and 187,488 scheduled provider records;
- 143,550 evaluations and 43,938 explicitly absent provider results;
- 195 entry intents across 182 minutes, with at most two intents per minute;
- 1,044 evaluations containing exit-side flags.

The exit counts are provider observations, not executed exits, trades or account
cashflows. Matching counts between variants do not establish identical values.
Every selected source line matches an independent compressed-file traversal by
per-asset SHA-256. All typed intents preserve their original serialized values
and types. The first/full-prefix result also reproduces all 30,240 prior compiled
minute rows exactly, including their 139 intents and empty decisions.

Both `last/*` requests fail with an explicit missing-original-stream error for
SOL in that frozen snapshot. No alternate source or later convenient start is
substituted. This remains two partial prefixes, not four complete 48-day runs.
All 824 consumed evidence references reauthenticate after the exercise. The
original XYZ initialization gap and missing native one-minute source evidence
remain unchanged; this reader does not supply independent canonical telemetry.

## Next step and operational scope

Continue the original [historical routing plan](../plans/2026-09-09-v89-historical-routing-qualification.md):
compare complete native/research publication and routing, retaining economic
action fields, global ordering and withholding reasons. Use the full provider
payloads for configured exits. Counterfactual position contexts must remain
explicit, and independent canonical evidence must come from the existing native
source binder. The existing HYPE payload decoder omits target anchors and uses
normalizing value helpers; it cannot be assumed to provide lossless general
evaluation decoding without verification. Do not invent XYZ minute candles.

At 12:24:34 UTC, the core parent and four workers are present. Its mutable log
reports 383,040 of 552,960 checks in 266 completed chunks, with zero differences.
These fresh log totals are not a new independent verification of every payload.
Both source collectors have matching live PIDs, no reported error, heartbeats
under 29 seconds and all 26 code pins unchanged. Both live-profile hashes match
their prior value. No live lifecycle, execution, strategy, sizing, deployment or
TUI change was made, and no sealed outcome or account state was read.

Changed source identities, dropped evaluations or exits, lost JSON types,
missing scheduled rows, noncausal clocks, shifted starts, substituted variants
or failed archived reproduction would invalidate the respective qualification.
Future economic performance remains low confidence until the remaining routing,
exit, account and prospective evidence is complete.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_historical_snapshot_20260909_v1/`.
