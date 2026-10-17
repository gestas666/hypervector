# Unified CLI cleanup and validation — 2026-10-17

## Scope and confidence

Implementation is isolated in `codex/unified-cli-cleanup`, based on
`32c65f054d8a9555804c10ed90f7fdfaea2591de`. The original checkout and its
pre-existing changes are retained. No live process was started, armed, merged
or restarted. This review establishes software behavior under the recorded
checks; it does not establish trading expectancy or authorize deployment.

High confidence applies to observed commands, tests and synthetic measurements.
Medium confidence applies to classifying code with unknown external consumers
as unused. A failed retained-command contract, changed fixture replay result,
network access in a unit test, or broken fail-closed boundary updates those
conclusions and blocks this branch's software acceptance.

## System overview

The pipeline is Hyperliquid/0xArchive acquisition → provenance-bearing Parquet
and DuckDB → VectorBT/Rust research and Karpathy tuning → strict strategy
exports → Nautilus historical validation → paper/shadow evaluation. Explicitly
armed execution consumes the same strategy/profile contracts through the
existing Hyperliquid adapters. Shared cohort journals remain the authority for
monitoring, accounting, operator outcomes and report-only projections.

The CLI now exposes ten focused workflows: system, data, archive, research,
nautilus, paper, live, cohort, regime and model. Packaged option declarations
feed both grouped help and legacy non-visual aliases. Handlers import services
only when dispatched. Operational commands resolve installed Python modules;
the repository's scripts are compatibility wrappers.

## Audit finding disposition

| Finding | Disposition and validation |
| --- | --- |
| Rendering and execution mixed in TUI launchers | Removed rendering, Rust crates/workspace, launchers, layouts and screen tests after extracting Python lifecycle, identity, dependencies and operator-request services. Backend safety assertions remain in headless tests. |
| Unused Backtrader and broad required integrations | Removed Backtrader. VectorBT/Rust and TA-Lib remain required. Other VectorBT add-ons use the `integrations` extra; Optuna/hybrid uses `optuna`; LightGBM uses `ml`. Direct Python imports have declared dependencies. |
| Monolithic eager CLI and incomplete inventory | Split handlers/option contracts by workflow; preserve non-visual aliases and helper imports. Added public-to-service option parity checks. Status schema version is 2. |
| Checkout-relative operational imports | Promoted cohort live/observe/checkpoint/audit/import and pressure observers into the package. Native replay uses the shared router directly. Wheel contains CLI declarations and build manifests for source identity. |
| Help/status initialized engines and probed models | Lazy package exports and metadata-only capability checks. Status is read-only and model probing is explicit. Help/status import tests forbid pandas/VectorBT/Nautilus initialization. |
| Unbounded accepted-entry recovery | Stream a captured complete-row prefix. Commit recovered offsets/cadence only after validation; retain corrupt, truncated, UTF-8 and identity refusal behavior. |
| Repeated full ledger scan while monitoring | Cache validated identity and inspect only appended complete rows. Refuse truncation/replacement and wrong run/profile/accounting epoch. |
| SQLite handles leaked across CLI invocations | Sweep persistence, board reporting and export close their database on success, early refusal and query failure. Regressions inspect the actual closed connection. |
| Paper reports materialized full journals | Single-pass counters and bounded sample deque; explicit `--last 0` returns no samples. Materialized research APIs remain available. Memory may still grow with distinct counter values or an unusually large row. |
| Implicit model roots and success-shaped model fallback | Explicit data root scopes discovery; removed sibling-machine paths; probe only the model header. An explicitly selected unavailable model raises a technical error. |
| Silent optimizer substitution | Karpathy is the CLI/API default. Unknown sampler or explicitly requested missing Optuna fails before data acquisition. No new implicit performance rejection gate. |
| Nautilus offline flag ineffective | Propagate `allow_network=False`; offline cache miss/incompatible cache is a technical error and does not fetch. |
| Public acquisition flags silently ignored | Backtest, book alignment and regime evaluation use the shared loader; autotuning forwards explicit source/refresh policy. Boundary tests prove both flags reach acquisition. |
| Fresh wheel selected incompatible Plotly | Reproduced VectorBT 1.1.0 import failure with Plotly 7.1.0; constrain Plotly below 7 and repeat installed research/indicator tests. |
| Duplicate exchange candle parsers | Share one kline-to-frame parser while preserving the Binance/Bybit wrapper contracts. |
| Tests read operational ledgers or made public requests | Rebind temporary ledgers and explicit model/funding fixtures; default suite denies network sockets. Classify artifact-dependent checks separately. |
| Frozen evidence tests failed before cleanup | Retain evidence byte-for-byte. Do not rewrite signatures or manufacture local bundles. Exact opt-in groups and prerequisites are in the adjacent test-disposition file. |
| Duplicate current operator skills and stale TUI acceptance | Canonical current skills, compatibility symlinks and headless acceptance procedure. Historical transition runbooks remain evidence. |
| Large local data/build outputs and historical journals | Retained. Deleting operational evidence is not an appropriate software-performance fix; retention/export destination remains a domain decision. |
| Experimental modules and deprecated public aliases | Retain tested ensemble/adaptive/portfolio APIs and deprecated impulse alias until external consumer/retention decisions exist. They are not invoked by default CLI discovery. |
| Oversized legacy modules and duplicate historical research scripts | CLI and promoted operational modules were decomposed. The remaining 58 oversized production files and 277 oversized functions are legacy debt; broad execution rewrites require behavior-specific work rather than mechanical splitting. |

## Pruning manifest

Git records the exact removed paths. Removed groups are `crates/hypervector-tui`,
the unused Rust core crate, root Cargo manifests, terminal launchers and
`src/hypervector/live/cohort_tui_*`. The TUI candidate preview and terminal-only
independent-monitor wrapper are retired; their checkpoint service remains.
`src/hypervector/live/sol_range_onset_cancel.py` had no identified consumer and
is removed. Backtrader's installation test and terminal screen tests are removed.

Tracked originals remain in Git. Additional pre-deletion archives are
`/tmp/hypervector-audit.6Kvyw2/retired-tui-backup.tar.gz` and
`/tmp/hypervector-audit.6Kvyw2/retired-orphan-backup.tar.gz`; temporary archives
are supplemental, not a durable retention system. Shelved D1 code, strategy
profiles, immutable approvals, journals and vendor inputs remain retained.
The shared `data.sources` fixture API is also retained for tests and external
imports; it is not connected to product data acquisition.

The largest retained modules are `scripts/d1_sleeve_executor.py` (6,194 lines),
`src/hypervector/paper/session.py` (2,504), and
`scripts/cohort_ladder_evidence.py` (2,220). New CLI/operational modules meet the
500-line file and 50-line function limits. These figures do not claim that
the entire legacy repository satisfies those limits.

## Performance evidence

Five fresh subprocess samples per startup command, same Python interpreter and
required dependency environment; median wall time includes interpreter startup.
Baseline source is the branch's base commit extracted to a temporary directory.
Measurements are local warm-cache observations, not production guarantees.

| Operation | Baseline | Updated |
| --- | ---: | ---: |
| CLI import | 1.143 s | 0.049 s |
| Build/format root help | 1.185 s | 0.065 s |
| Status, absent data root | Not compared | 0.077 s |
| Recovery peak traced memory, 2 MiB | 8,833,626 B | 6,650 B |
| Recovery peak traced memory, 8 MiB | 35,382,258 B | 6,642 B |
| Recovery duration under tracing, 2 MiB | 0.222 s | 0.273 s |
| Recovery duration under tracing, 8 MiB | 0.893 s | 1.086 s |

Recovery's demonstrated benefit is bounded memory; latency did not improve in
this experiment. A production ledger with huge individual rows or many distinct
report-counter values has different bounds. The original audit observed a
26.3 GB test-process footprint and exit 137, but did not establish the cause of
that termination. No causal OOM claim is made here.

Reproduce with:

```sh
.venv/bin/python scripts/profile_core_runtime.py --samples 5 --out /tmp/hv-profile.json
```

For comparable startup baselines, extract the base commit's `src` and `scripts`
into a temporary directory and provide `--baseline-root DIRECTORY`. Do not
run baseline operational commands against production data.

## Validation results

Final offline unit command:

```sh
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile
```

**11,091 passed, 8 skipped, 24 warnings, 137.48 seconds.** The test population
changed through terminal-test removal and explicit artifact classifications;
its count should not be compared directly with the audit baseline as a
regression count. Other completed checks:

- Targeted statement coverage: 93.56% across seven selected modules. Monitor
  command handling, operator request handling/publication and accepted-entry
  recovery each reached 100% statement coverage. This is not repository-wide
  coverage and does not claim exhaustive branch or production coverage.
- Installed wheel, outside the checkout with network calls denied: ten group
  help pages, nine packaged service entry points, VectorBT backtest, TA-Lib SMA,
  two Karpathy trials, a 400-bar Nautilus backtest, paper/shadow stop lifecycle
  and unarmed live refusal passed. Plotly 6.9.0 satisfies the corrected bound.
- Local loopback shutdown integration: 2 passed, 10 non-integration cases
  deselected. No venue was contacted.
- `ruff check --select F401,F811,F821 src scripts`, Python compilation,
  `git diff --check`, dependency consistency and `uv lock --check` passed.
- All 3,901 audited original-source hashes remained unchanged, and the
  original checkout retained its pre-existing tracked and untracked changes.

Wheel: `/tmp/hv-unified-wheel-final/hypervector-0.1.0-py3-none-any.whl`,
3,638,865 bytes, SHA-256
`3935dc5fd8566507dad8d8fdb0b47c5261612e22488c636f3793f3d0526eb75f`.
The wheel carries source/lock metadata, not the full installed-environment
inventory. A selected deployment must bind its actual dependency environment
as well as the source identity.

The eight pre-existing unit skips cover three operator-local V90 screen
artifacts and five unavailable `backtest-lab` Pine/component probes. They are
reported as skipped, not passed. Broad integration, network and frozen-evidence
selections were not claimed as passing; their prerequisites remain explicit.
The final run reported Nautilus/Pandas deprecation warnings. It reported no
SQLite ResourceWarnings after the CLI database ownership fix.

## Remaining decisions and deployment boundary

- Select the deployment profile, required `backtest-lab`/Hypertrader snapshot,
  model bundles and exact historical evidence. Source-bound approvals from an
  older implementation cannot authorize newly changed execution sources.
- Decide whether shelved D1 and experimental public APIs remain supported.
  Keeping them preserves compatibility; deleting them reduces scope but needs
  a clear consumer and evidence-retention decision.
- Select an archive destination and retention policy before removing local
  ledgers, vendor artifacts, historical journals or stale build outputs.
- Rehearse selected-profile native replay, recovery, accounting and transition
  with those exact inputs before any approved merge/restart. STOP markers and
  double arming remain authoritative. A unit pass cannot replace that proof.

Rollback is a branch revert or retention of the original checkout. There was no
deployment transition to roll back. A proposed merge into an armed checkout
remains a separate, explicit transition decision.
