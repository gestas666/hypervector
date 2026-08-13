# v31 compact material-change journal

## Problem restatement

The v31 route monitor refreshed a bounded current snapshot every 120 seconds,
while its structured log retained only cycle success or failure. Raw ledgers
made prior states reconstructable, but there was no compact durable sequence of
the moments when route evidence, economics, authority, health, or position
protection materially changed.

## Implemented control

`src/hypervector/research/v31_route_change_journal.py` now validates the exact
report-only v31 route snapshot and appends a canonical JSONL event only when its
material-state SHA-256 changes. Every event binds the prior event SHA-256, so a
truncated, reordered, malformed, or edited chain fails explicitly.

Material triggers are:

- run, profile, phase, or candidate identity;
- current or candidate route authority;
- eligible-signal and resolved-horizon evidence;
- route execution outcomes and forward assessment;
- closed portfolio wins, losses, fees, funding, net PnL, and profit factor;
- open-position identity, size, stop identity, and protection; and
- runtime faults or the declared transition recommendation.

Refresh timestamps, raw forward-evaluation counts, and provisional open-mark
equity changes are not triggers. The latter remain attached as observations to
the next material event and remain continuously available in the bounded
checkpoint. This prevents the journal from growing every two minutes while
positions fluctuate.

The continuous monitor writes
`data/logs/research/bidirectional_cohort/v31_route_material_changes.jsonl` only
after a successful snapshot refresh. A failed refresh cannot enter the durable
journal. The journal has no execution, transition, sizing, closing, restart, or
promotion authority.

## Validation evidence

- Red phase: tests first failed because the journal module and monitor option
  did not exist.
- A live-data regression then proved provisional mark-to-market changes would
  have appended repeatedly; the material-state contract was narrowed and the
  test now proves those refreshes deduplicate.
- First append, identical refresh, material economic change, hash chaining,
  corrupt-history rejection, execution-capable input rejection, and
  success-only monitor integration pass.
- The actual v25/v31 snapshot produced a valid first event and an identical
  second read produced no event.
- Three early baseline/migration rows were retained rather than erased. The
  third row captured a real transition from five to four open positions and
  from 12 to 13 closed trades; the chain was valid at 15,630 bytes.
- Two subsequent 120-second monitor refreshes plus a direct current-snapshot
  check left the journal at exactly three rows and 15,630 bytes while open
  marks moved.
- The complete non-network Python suite passed 4,365 tests with four
  intentional deselections and 27 dependency/deprecation warnings.
- Only the report-only v31 tracker was restarted to load the hook. The v25 live
  backend and checkpoint writer were not restarted.

## Uncertainties and falsifiers

The journal is a decision-state index, not the detailed evidence store. Exact
fills, books, mark paths, and funding rows remain in the checkpoint and raw
ledgers. A missing material event, an append caused solely by a later open mark,
an accepted corrupt chain, a failed tracker cycle entering the journal, or any
execution side effect falsifies the implementation claim.

Confidence is high for the tested deduplication and chain contract. Economic
confidence remains medium because the underlying v31 route evidence is sparse;
the journal makes changes auditable but does not create an edge.
