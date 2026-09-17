# Native source retention failure and repair

High confidence: three full-window fabricated-source runs failed at the same
storage boundary. Their tracebacks end at `pickle.dump` with
`TypeError: cannot pickle 'mappingproxy' object`. Native readiness metrics use
`MappingProxyType`. The original writer reached that line only after checking
84,679 decisions and 2,352 funding records for the first variant. All three
retained files are 32-byte XZ streams that decompress to zero bytes. The
dependent account handoff correctly stopped when its source process disappeared.
Neither variant pair nor the complete account qualification passed.

The prior serialization probe checked canonical JSON, not the pickle path used
by the long jobs. It therefore did not validate this boundary. This distinction
corrects any interpretation of that earlier probe as persistence qualification.
The failed logs, source files, scopes and empty artifacts remain unchanged.

## Repair and validation

The repair is isolated in
`/Users/gestas/Prototypes/hypervector-v89-native-retention-repair-20260917`,
branch `research/v89-native-retention-repair-20260917`, committed and pushed at
`9be01119925b7f3a0ddbb75580d2c8ab78ac3f08`.

A Pickler-specific reducer reconstructs immutable mappings without changing
global pickle registration or native strategy/readiness classes. Compressed
objects are written to a private staging file, closed and synchronized before
exclusive hard-link publication. Existing files and dangling symlinks are
preserved. JSON receipts use the previously qualified atomic publication helper.
The adapter changes only the original research driver's module-local persistence
bindings, source-root declaration and technical deadline; it restores those
bindings on failure. Frozen archived native implementations are untouched.

- **38 candidate tests and 38 archived tests pass**, with network access denied.
  Controls cover the original failure, exact values/types, nested immutable
  mappings, no global registration, incomplete encoding/publication, overwrite
  refusal, source/tooling identity, authority, restoration and failed execution.
- Persistence code covers **41/41 statements and 4/4 branches**. Together with
  the driver, unit coverage is **127/130 statements**, with remaining CLI and
  authenticated-evidence loop paths exercised separately by actual execution.
  This is not a claim of complete combined measured coverage.
- Actual native first decisions and first-hour funding for seven providers in
  both variants survive the save/load path: **14 decisions, 14 funding records,
  14 immutable readiness mappings** per probe. Canonical fields match exactly.
- The frozen archive repeats the actual probe. A third, independent decoding
  process authenticates both artifact sets and confirms equal typed objects
  and identical canonical JSON. Raw pickle bytes differ: opcode inspection
  shows reordered frozen-set members and memo references. Binary reproducibility
  is not claimed; each individual artifact remains hash-authenticated.
- Nine archived files match Git and the worktree. The 51,200-byte archive SHA-256
  is `9a48920501e29d0d621813c1dfd359ce891376c5869027b6aa39dcc2b60dcc95`.
  Ruff and function/file-size/type-annotation checks pass.

The first development probe launch selected a same-named driver copy through
incorrect Python path ordering and failed before computation. Its traceback is
retained. Correct ordering loads the original pinned driver before the separate
comparator directory; frozen launch commands use that ordering.

## Restarted qualifications

New output root:
`data/logs/research/bidirectional_cohort/v89_native_retention_repair_20260917_v1`.
Every run authenticates the original fabricated inputs and source archives,
checks the actual loaded native-module path, and completes a native persistence
probe before entering full collection. Its sandbox denies network, credential
reads and writes outside that run's output and temporary directory.

| Run | PID | Started UTC, September 17 | Native source commit | Current qualification |
| --- | ---: | --- | --- | --- |
| Baseline | 47871 | 12:14:08 | `38bdf78c5ef5ee2c777e90dfac2ce478a26af554` | Probe passed; full run pending |
| Independent reproduction | 47885 | 12:14:09 | `38bdf78c5ef5ee2c777e90dfac2ce478a26af554` | Probe passed; full run pending |
| Decision-reuse candidate | 47893 | 12:14:13 | `3d4de3cab712129353d2e4710846d7da475fbfde` | Probe passed; full run pending |

Baseline and reproduction use the existing authenticated account archive, whose
three reporting/runner changes relative to original native archive `76f4b50`
are checked by the original preparation routine. Native collector bytes remain
unchanged. The candidate's four previously reviewed implementation differences
and original frozen tooling request are also authenticated. The persistence
repair adds no native calculation changes to either archive.

Both complete source variants remain required. At prior observed throughput,
baseline generation could take roughly **40–45 hours**, and the candidate roughly
**30–35 hours**; these are low-confidence estimates pending new-run progress,
not completion deadlines or a go-live ETA. Each run retains the 72-hour technical
bound. Complete source comparison and downstream account validation remain
separate work. No replacement account consumer has been launched against
incomplete outputs. The next continuation must authenticate completed catalogs,
compare both full variants using the existing full-grid comparator, then prepare
the account handoff with the new scopes and retained-source identities.

At 12:15:17 UTC, the live backend 83722, reporter 18490, TUI 42506 and all five
collectors retained their established process identities. The live checkpoint
was `running_consistent`, with zero faults and all seven assets flat. Collector
health ages were 6.7–9.9 seconds. No financial source, configuration, process or
existing collector changed during this repair. No real sealed study outcomes
were evaluated. Shared public transport integration is deferred behind this
observed qualification failure; its prior offline findings remain intact.

## Decision, limits and falsifiers

Retain the repaired research persistence boundary and finish the restarted
qualifications. Confidence is high for the reproduced storage defect and tested
repair, and incomplete for whole-window/account correctness. This improves
research reliability; it does not establish improved trading expectancy.

| Alternative | Benefit | Limitation |
| --- | --- | --- |
| Repeat the old writer unchanged | No tooling change | Reproduced failure remains |
| Local reducer and atomic publication | Preserves native types/calculations and original evidence | Lost in-memory work must be recomputed |
| Redesign streaming checkpoints | Could retain incremental progress across crashes | Larger computation and provenance change; deferred |

The minimum next evidence is two complete 84,679-decision / 2,352-funding variants
per run, authenticated retained bytes, exact independent source comparison and
the separate account tests. A later save/load failure, changed canonical field,
mutable restored metric, source identity mismatch, early-visible final file or
failed full comparison would reopen the repair. Interruptions may leave private
staging files, but cannot publish an incomplete final artifact; power-loss
durability and hostile pickle decoding are outside this qualification. Decoding
remains restricted to trusted, authenticated local research artifacts.

Rollback means stop using this new research driver and preserve its evidence;
the original archived implementation and failed outputs remain available. There
is no proposed live change and no new live approval is needed for this offline
repair. Existing unrelated deployment approvals remain separate.
