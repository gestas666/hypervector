# V89 exact startup candle inputs

The full initial retained candle frames are now archived once per future backend run, before resampling or provider evaluation. Installed source commit `d373079c6dbd55f2fc538e21bc757432ff6c28e4` matches candidate `bd8f15fd8e108eef2a430364dea67b74a78b6e5e`. The running financial session was not restarted or signalled; this capture has not activated there.

## Observed problem and recommendation

The [September 15 SPCX audit](2026-09-15-v89-spcx-entry-reconciliation.md) reproduced the band crossing and ATR recurrence, but could not verify the original ATR initialization because only the last 360 startup minutes were present in chart telemetry. The original retained provider input was no longer available. This is an evidence-retention defect; it does not demonstrate an incorrect ATR calculation or a profitable strategy change.

Accept the bounded capture repair for all configured assets and regimes. Each immutable bundle contains the actual initial merged 1m input frames, preserving their values, columns, dtypes and source timestamps. The manifest records run/profile fingerprints, activation time, observation cutoff, requested lookback, actual row/time coverage, library versions and individual file hashes. Safe indexed filenames preserve symbol identity in metadata. An incomplete current candle is retained if present in the actual input; offline replay applies the same provider completion cutoff.

The ledger stores a small `startup_candle_inputs` reference with an externally recorded manifest hash. The loader checks identity, coverage, metadata and hashes, then decodes the same authenticated bytes. It rejects corrupt, missing, substituted or conflicting evidence. Existing run bundles are not overwritten. Expected archival errors produce `status=unavailable` and an explicit reason while provider evaluation continues. Failure to write the authoritative ledger retains the existing fatal technical-failure behavior.

## Alternatives and trade-offs

| Option | Benefit | Limitation |
| --- | --- | --- |
| Leave chart telemetry unchanged without a capture | No added I/O | Original indicator initialization remains unrepeatable |
| Repeatedly expand chart payloads | More history in existing records | Additional ledger and display memory on recurring cycles |
| Fetch another snapshot later | Easy acquisition | Does not establish the input actually consumed |
| One initial sidecar, installed | Exact original retained input with bounded per-run work | Additional startup I/O; archives accumulate per run |

No price, indicator, signal, route, asset, leverage, sizing, stop or holding parameter changed. Capture makes no network requests and constructs no execution client. Its upside is stronger diagnosis and reproducibility, not a demonstrated increase in trading returns.

## Validation

- The original regression failed because the full-input observer was absent. The final candidate and installed suites each passed **131 tests**. The two new modules have **100% statement coverage across 156 statements**; this is targeted coverage, not whole-system coverage.
- Tests cover once-only capture before collectors, unchanged complete poller outputs and request sequences, all configured source frames beyond the 360-bar chart tail, explicit incomplete-bar retention, exact pandas and hourly-indicator replay, profile/run/cutoff binding, corruption, missing data, invalid source coverage, duplicate publication, failed durable publication, transient fetch retry, visible archival failure and propagated ledger failure.
- A deliberate file substitution after checksum verification reproduced a race in the candidate loader. The final loader decodes the authenticated in-memory bytes, and the regression now passes. This candidate defect was fixed before installation.
- The first coverage invocation using importable module names failed during NumPy collection. The preserved failing receipt is not counted as a test pass. Coverage using filename include patterns completed with all 131 tests passing.
- Frozen real SPCX evidence contains **1,500 one-minute candles**. Archive/reload produces bit-exact frame equality, identical hourly signals and identical actual provider batches: **four evaluations and one entry intent**. The final ATR for that fixed retrospective input is **0.9072611523437502**. It is not substituted for the live process's original seed.
- A synthetic seven-asset capture of **35,007 rows** used **1,606,417 bytes**, taking **20.1 ms** to write and **11.6 ms** to replay. The configured 14-day retention-bound case of **141,127 rows** used **6,487,780 bytes**, taking **50.0 ms** to write and **16.1 ms** to replay. These are two local single-run measurements, not latency percentiles or hard upper bounds. Process peak RSS increased about **16.2 MB** and **22.8 MB** respectively during capture/replay; this is a high-water measurement rather than precise allocation attribution.
- All modified Python files remain within 500 lines and all their functions within 50 lines. The 12-file installation preserved **5,508 other files**, both TUI binaries and the exact identities of user PIDs **29190/29191/30603/62016/62017**. The reverse patch passes its applicability check. No agent-owned financial process was created.

The tests and native replay were offline. No additional public candle fetch was needed. Evidence is under `data/logs/research/bidirectional_cohort/v89_startup_candle_provenance_20260915_v1/`.

## Activation, limits and rollback

At the next normal user-controlled backend startup, check the new ledger event. A `captured` event must authenticate a bundle for that exact run/profile/cutoff; `unavailable` is an explicit remaining evidence gap. The existing financial backend continues with its already loaded implementation and cannot retroactively capture discarded initial inputs. No restart is requested for this reporting change.

This archive covers initial retained provider inputs, not raw HTTP responses or every subsequent candle revision. Later input changes require their own source evidence. Per-run storage is measured and row-bounded, but there is no automatic archive deletion. Exact replay here establishes calculation reproducibility for the captured input; it does not prove market forecasts, future profitability or universal bug freedom. Prospective outcome seals remain unopened.

Rollback uses `installation/source.patch` in the evidence directory, with original overwritten files under `installation/previous/` and a file/hash manifest in `installation/before.json`. Verify the reverse patch against the current source before applying it. Keep the original combined session open: its process ownership is unrelated to source rollback.

**Success metrics / falsifiers:** exact source and provider-output parity, one capture per startup, unchanged request sequences, explicit failure reporting and correct run binding. A mismatched frame, provider result, hash, identity, hidden capture failure, recurring capture or material startup overhead reopens acceptance. Confidence is high for these tested boundaries and measured inputs; activation in the existing run remains unverified.

**Approval:** existing corrective reporting authorization covers this source installation. No new trading policy or financial execution action was taken.

**Next highest-value investigation:** use new entry/exit or protection receipts from the open SPCX/SNDK lifecycles to test execution consistency and final costs. Validate the first real startup bundle when a normal user-controlled restart occurs. Do not repeat unchanged leverage, seed or strategy-filter tests without new evidence.

The separate leverage display repair remains installed. At the 20:14:12 UTC checkpoint, both open SPCX and SNDK positions report **10x** venue leverage, with 20/20 compatible-history fills, eight closed and two open lifecycles. The original running TUI still uses its earlier binary; the versioned independent monitor command is in [the monitor guide](../guides/cohort-strategy-regime-monitor.md).
