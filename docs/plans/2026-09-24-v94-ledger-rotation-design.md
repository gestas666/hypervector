# V94 ledger rotation: design, deferred

Status: designed, **not implemented**. Plan item C4 allows rotation in V94 only
if it is trivially safe. It is not: too many readers and too much restart
state assume one continuous ledger per asset and one for the cohort. This note
records why, what V94 ships instead, and the order in which to pursue the rest.

## The problem

An armed start re-reads the whole history before any engine runs. At the V93
launch (11.5 GB of ledgers) the first heartbeat came 914 s after launch, and the
start grows about 0.62 min per day of ledger growth (0.45 GB/day). That crosses
the supervisor's 30-min startup grace in roughly 3–4 weeks. Figures are from the
read-only restart investigation of 2026-09-24:

| Phase at V93 size | Seconds |
|---|---|
| Prestart bundle: gzip level 9, sequential | ~163 |
| Second full bundle verification | ~9 |
| Constructor validation, 8 asset ledgers + cohort ledger (A1, C2) | ~185 |
| Five redundant recovery passes (A2, C3, A4, C4 before engines; A3 in engine start) | ~460 |
| Venue checks, SDK, per-asset preflight, first poll | ~80 |

About 99.8% of asset-ledger bytes are per-poll telemetry (`book_observation`,
`reconciliation`, …), and 74.6% of cohort bytes are `cohort_snapshot` rows that
no recovery path reads.

## What V94 ships instead (C4, tested)

- **Declared recovery reads.** `SolLiveLedger.read_matching(predicate,
  event_types=…, profile_fingerprint=…)`. The constructor's full validation
  stays the only full decode per ledger per process. It now also records one
  small code per row for the decoded `(event_type, profile_fingerprint)` pair.
  A later declared read passes over a row only when this instance already
  validated it and its code falls outside the declaration. Every other row
  (line 1, rows appended by another instance, every row of a file that lacked a
  final newline) is decoded exactly as before. Selection is by decoded values,
  so writer formatting cannot change a result. There are five call sites:
  telemetry fill/fee/funding recovery, per-asset profile recovery, the history
  cache (by profile only), durable decisions, and the funding cursor.
- **Bundle.** gzip level 6 on four parallel workers, in manifest order. The
  bundle is fully verified once, in staging, before the rename that publishes
  it. After the rename only a structural check runs. The external verifier
  still does the full check on demand.
- **Venue probe before the bundle**, the **wall-clock blindness bound**, and the
  **uncharged relaunch after a blindness exit**, so an outage no longer burns
  bundles or the crash budget.

Projected armed start at V93 size: about 390 s instead of 914 s. Growth drops
to roughly 0.2 min/day, almost all of it from the constructor validation. This
is a projection until the first V94 start measures it; read it from
`supervisor_events.jsonl` (`backend_launched`) and the first cohort `heartbeat`.

## Option A: rotate ledgers at profile boundaries (deferred)

### Mechanics, if pursued

1. Rotate only at an armed start with `strategy_changed = true`, after the
   verified prestart bundle and after an archived, flat, order-free transition
   drain. Never rotate mid-lifecycle.
2. Rename each ledger atomically on the same volume, into
   `<ledger dir>/archive/<name>.<old fingerprint[:12]>.<UTC stamp>.jsonl`.
3. Write `ledger_lineage.json` next to it: archived path, bytes, rows, last
   sequence, and the `source_sha256` the bundle already computed.
4. Start the new ledger at sequence 1 with a new `ledger_genesis` event. It
   carries the predecessor's hash, row count and the state below that must
   survive the rotation.

### Why it is not trivially safe

- **A fresh ledger changes fill accounting.** `SolLiveTelemetry` treats an empty
  selection as a fresh ledger and baselines every venue fill as already seen
  (`sol_range_onset_live_telemetry.py`, `_fresh_ledger` and
  `_baseline_existing_fills`). It also anchors the run start at line 1
  (`_run_started_at_ms`) and silently marks older fills as seen. A rotated asset
  ledger would re-baseline: a venue fill not yet journaled at rotation would be
  marked seen without its `fill`/`fee` rows. Genesis would have to carry the
  seen trade ids and the original start anchor.
- **Previous-profile identity comes from the ledger.**
  `create_cohort_prestart_backup` finds the previous armed identity by
  scanning the cohort ledger (`_latest_configuration_identity`). The
  `strategy_changed` decision, the bundle's `previous_identity`, and therefore
  `previous_profile_config` / `validate_profile_change_approval`, all depend on
  it. After a rotation that row lives only in the archive.
- **Many full-history readers.** About 200 files under `src/`, `scripts/` and
  `crates/hypervector-tui/src` reference these ledgers. They include:
  - the checkpoint builders (`research/cohort_live_checkpoint.py`, the
    rolling and independent checkpoints);
  - accounting rollover;
  - ladder evidence;
  - the live audits;
  - the TUI's `backend_ledger_reader.rs`.

  Each would silently lose history unless it learns the archive chain.
- **Restart evidence spans runs.** Crash recovery after a mid-drain restart
  reads the current profile's rows. That is safe only if rotation can never
  separate a lifecycle from its opening rows, which the flat-drain precondition
  must guarantee and a test must prove.

What rotation would buy on top of V94 is the remaining constructor validation
(~185 s growing ~7.6 s/day) plus smaller bundles. Option B gets the time for far
less risk.

## Option B: hash-anchored incremental validation (recommended next)

The bundle already streams every ledger through sha256 before replay. The idea:

1. At a start that reached `emit_configuration`, record per ledger: byte length,
   row count and the sha256 of exactly that prefix. The bundle manifest's
   `source_bytes`/`source_sha256` are that record for the bytes present at
   bundle time.
2. At the next start, while the bundle streams the ledger, snapshot the running
   hash with `hashlib` `copy()` at the recorded byte boundary and compare it with
   the recorded digest.
3. If they are equal, the prefix is byte-identical to one already fully
   validated. The constructor validates only the suffix, starting at
   `sequence = rows + 1`, as `read_from_cursor` already does.
4. On any mismatch, or a missing or unverifiable record, fall back to full
   validation. Never fall back to a skip.

This composes with the declared reads only if the per-row envelope codes are
also available for the prefix. So persist a sidecar index sealed by the same
prefix hash: a code table plus one `(byte offset, code)` entry per row. It lets
declared reads seek straight to selected rows instead of scanning.

Tests needed:

- suffix-only validation equals full validation over any appended suffix;
- a tampered prefix byte, a truncated ledger, or a stale or foreign index falls
  back to full validation;
- the boundary is taken only from a start that reached `emit_configuration`
  with a verified bundle.

Expected saving: ~185 s at V93 size, and the start stops growing with history.

## Option C: move per-poll telemetry out of replay

Review item 14 pairs rotation with moving per-poll telemetry out of the replayed
ledgers. `build_live_journal` and the markouts read `book_observation`,
`reconciliation`, `position` and `liquidation_price` rows through the history
cache, so a separate telemetry ledger needs those readers ported first. With
Option B in place the byte volume stops mattering for startup. The remaining
motive would be disk: ledgers grow 0.45 GB/day, and each armed start's bundle
costs 1.2–1.3 GB.

## Option D: incremental or hash-chained bundles (not worth it)

After the level-6 parallel change the bundle is bounded by the cohort ledger,
about 61 s. Chained bundles would couple a restore to the retention of every
earlier bundle, and A3 just deleted 99 of them.

## Order

1. Ship V94 and measure the armed start.
2. Option B plus the sealed index, as its own source transition with a
   read-only equivalence checker run against the live ledgers before deploy.
3. Option C only if disk growth, not start time, becomes the constraint.
4. Option A only together with a lineage-aware reader for every consumer
   listed above.
