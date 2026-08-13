# Forward source observer review — 2026-07-29

## Problem restatement

Extend the pinned Hypertrader source classifier onto newly recorded
Hyperliquid L2/trade/context evidence without changing the running shadow
strategy. Success requires an exact reproduction of every previously imported
label, ingestion of only new timestamps, and report-only authority.

## Infrastructure corrections

The first live-event refresh failed closed because daily `gaps.jsonl` files are
append-only while the DuckDB importer treated every source path as immutable.
The corrected importer now:

1. requires the previously ingested bytes to be an exact SHA-256-verified
   prefix;
2. rejects truncation, mutation, or same-length rewrites;
3. transactionally replaces the prior gap-file snapshot with the complete
   append-only version; and
4. reports only the newly appended gap-row count.

Parquet L2, trade, and asset-context parts retain strict immutable-file
semantics. The real refresh then imported 361 new files: 9,012 L2 rows,
183,286 trades, 47,365 asset-context rows, and five new gap rows.

The first source-label attempt also failed closed because a July 27 restart of
the path-dependent state machine conflicted with existing labels. Empty event
windows additionally exposed a columnless empty-frame bug and non-atomic
Parquet/metadata publication. The generator now preserves the event schema for
zero events and removes both outputs if publication fails.

## Continuous-anchor validation

Immutable prior metadata identified the correct state anchor as
2026-04-28 00:00 UTC. A pinned detached source worktree at revision
`ad15f2bdc949619be495a5f516babd08f7f52a90` passed every declared source-file
checksum.

The continuous extension classified 26,678 completed 5m bars through
2026-07-29 15:05 UTC. DuckDB accepted the result as follows:

| Measurement | Result |
|---|---:|
| Prior labels reproduced and skipped | 26,517 |
| New labels imported | 161 |
| Overlapping shadow bars | 59 |
| Backend/source label disagreements | 6 |
| Runtime authority | none |

Reproducing all 26,517 overlap rows is the critical path-dependence check. A
single conflicting revision/timestamp value would have rejected the entire
import.

## Fresh evidence

The 161 new labels cover 2026-07-29 01:45-15:05 UTC:

| Source primary | Bars |
|---|---:|
| RANGE | 78 |
| TREND_UP | 51 |
| TRANSITION | 32 |
| TREND_DOWN | 0 |

No confidence-qualified 06:00-15:00 UTC short onset occurred. Therefore this
slice validates collection and classifier continuity but contributes no new
candidate trade outcome.

## Confidence, risks, and falsifiers

- **High confidence in continuity for this extension:** every historical
  overlap value was identical. This is falsified by any future overlap
  conflict using the same source revision and anchor.
- **High confidence that the observer has no execution authority:** both the
  importer and label metadata declare report-only/none and the running backend
  was not restarted or modified.
- **Low confidence in forward profitability remains unchanged:** zero new
  qualifying short events means zero new fills, targets, or liquidations.
- Full-anchor regeneration consumed roughly ten minutes and high temporary
  memory while scanning the canonical trade history. It is operational but
  not an efficient continuous service; explicit state checkpointing is a
  future infrastructure optimization, not a requirement for evidence
  correctness.

## Verification

- Focused live-ingest, replay, source-label, overlap, and shadow-database tests:
  31 passed.
- Ruff and format checks: passed.
- Extended labels SHA-256:
  `08991f5266b94b82456f2be50cf849ade00ce52e953f47857bb8687b4b418227`.
- Extended metadata SHA-256:
  `a0af5031929a721a59dd475a2f8333020f482897381706e50334353170df2f27`.
