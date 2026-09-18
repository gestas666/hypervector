# Complete-history recovery: small cases qualified; larger pilot stopped

As of September 18, 2026, source **29765f3c0c7002258f189d10a775c1d43aa351cb**
is committed and pushed on `research/v89-complete-history-scale-20260918`.
Confidence is high in the bounded results below. Full observed-scale recovery,
original scheduler integration at that scale, and live adoption remain unqualified.
No live strategy, execution rule, collector declaration, or TUI was changed.

## Problem and implemented measurement

The preceding scale probe measured only the status reader over synthetic begins.
It could not establish the cost or correctness of recovery with complete raw,
return, service-authorization, and original normalization evidence.

The new offline builder calls each of the five frozen sources' actual
`_capture_once`, immutable raw writer and original store. Real service workers,
admission, acknowledgements, return witnesses and ingestion permission remain in
the path. Only HTTP response bodies are synthetic; network access and writes to
the protected live/source roots are OS-denied during qualification.

Fresh original-source interpreters reopen the real broker and namespaces through
`CaptureBridge.recover`. Independent checks compare original logical tables and
raw bytes, validate normalized values against authorized bodies, and reauthenticate
all five import trees. Recovery submits no new transport requests in qualified cases.

The initial before/after assertion incorrectly included a newly sampled accounting
clock and its checksum. The corrected comparison verifies both seals, requires a
nondecreasing observation clock, and compares every other accounting field.
The initial failure and regression evidence remain preserved.

Synthetic worker fixtures are retained as immutable, checksum-verified recipes.
Workers receive a fixed database path instead of a growing body dictionary.
A 256-recipe test proves the serialized recipe handle does not grow with history.
This fixes a measurement-harness scaling risk; no production race is claimed.

## Validation and its limits

- Candidate: **275 passed, one skipped**, 204.47 seconds wall time.
- Archive: **275 passed, one skipped**, 207.11 seconds wall time.
- Complete and mixed cases each contain nine requests per original source.
  Mixed fixtures include HTTP 503 and a read timeout after one received byte.
  Original rows, raw hashes, service facts and availability survive fresh recovery.
- Twelve corruption cases cover missing/altered raw and missing/altered service
  authorization across old quarter, budgeted quarter and native schemas.
  Each stops with the expected evidence error and preserves committed index rows.
- Original full-loop, process-crash, owner-loss and workload regressions also run.
  The skip is a separately selected long continuation; its prior evidence is
  independently checked, not a newly repeated 300-second study.
- Both final suites have zero `ResourceWarning` occurrences across 156 inspected
  log files each. Resource/unraisable warnings are errors in the parent suite.
- Measured parent/helper coverage: **339/342 statements, 87/90 branches**.
  This excludes instrumentation inside the isolated original child interpreters
  and is not whole-system coverage. New contract, recipe, message and evidence
  modules have complete measured statement/branch coverage.
- All **5,849** committed files match source and archive: **11,698 matches**,
  zero changed/missing. Archive SHA-256:
  `759058f2b19322dccd0893bbeee4a4daeacc5e69b71b48dc6fb992aebd480091`.

At nine requests per source, measured child recovery spans approximately
0.72–1.03 seconds, with about 111 MB cumulative process peak RSS. These are small,
shared-host measurements, not estimates of 46,807-request recovery.

## Larger pilot: retained technical failure

The declared 1,500-attempt pilot, `[300,300,300,300,300]`, stopped during generation
after **315 admissions**, before fresh-process recovery. It retained **310 raw
receipts and 310 indexed requests**, plus five incomplete original attempts.
The broker recorded 301 distinct transports. It is not a successful scale result.

The parent rejected `1789712102592 < 1789712102649`, a 57 ms clock regression;
a worker independently rejected a 42 ms regression against the same prior tick.
Both failing paths sample actual wall time after `BEGIN IMMEDIATE`, which makes
the simple pre-lock stale-sample hypothesis less likely. It does not prove the
underlying OS-clock cause: no paired wall/monotonic trace covers that exact instant.

A subsequent 120-second probe retained **40,015 paired samples**, with no backward
jump; the largest negative offset change was 29 microseconds. Two existing
rollback-rejection tests pass, confirming the fail-closed behavior is intentional.
No clock clamp, fabricated timestamp, deadline extension, or automatic retry was
introduced to obtain a passing study. Confidence in the underlying cause remains
low pending event-time instrumentation or independent host-clock evidence.

The full observed target remains **[3889,46807,3899,46796,1576]**. It has not been
replaced by the small passing cases. Capture generation does not run original
scheduler pacing, quarter reservations/budgets or native spacing. Those acceptance
boundaries, power loss, production network headroom and economic validation remain.

## Storage and runtime continuity

Disk space fell below the configured 8 GiB research-sync reserve. The reporter
explicitly deferred imports; the live backend continued with zero reported faults.
Completed archive-copy replacement produced no net observed space gain and is not
counted as a reclamation result.

Idle generated build files in five retired worktrees were compressed and verified
before removal: 1,057 files, 159,952,258-byte backup, SHA-256
`77dc85700e0283ac107a57152e71b9ee84cb8a0a34551a8ee742e218d09df4f7`.
Installed release executables remain intact. The first archive verifier rejected
tar hard links; validation was corrected to authenticate their archive-local
targets and resolved bytes before any deletion.

Selected mypy, llvmlite, pyarrow and onnxruntime package caches were backed up and
reverified: 23,318 files, 888,824,523-byte archive, SHA-256
`13374f87571785afca3bbe928b9c45cada56109c629b6b475f110fc1ddf8fbdb`.
Normal uv cleanup waited on two long-running application-server locks. Its owned
waiting process was cancelled. After proving no installer was active, no selected
cache handles were open, and the relevant installed environments had no cache
symlinks, package-specific uv cleanup used its explicit force option. No application
server was stopped. Backup manifests retain exact paths for restoration.

Observed free space rose from 7.84 to 9.77 GB during that cleanup; background writes
and the retained backup mean this is not a claim of net 2.8 GiB reclaimed.
Installed dependency imports and the installed TUI checksum verified unchanged.
At **06:21:28 UTC**, research sync completed **2,461 imported events** and returned
to `ready` with no error. Runtime snapshots retain all eleven protected identities.

## Decision and next investigation

Retain the qualified offline harness and failed pilot. The single highest-value
next investigation is clock provenance at serialized broker operations during a
new, explicitly declared larger pilot. Preserve the failed pilot unchanged and
determine whether host time moved or an unobserved future timestamp was committed.
A passing repeat alone does not explain or remove the observed failure.

Compared with doing nothing, instrumentation supplies missing causal evidence.
Compared with clamping time or relaxing deadlines, it preserves the original
receipt contract. Only after the cause and operating behavior are qualified should
the complete-history target and original scheduler deadline effects be measured.
No performance or profitability improvement is inferred from this harness.

Falsifiers: changed original rows/raws, new recovery requests, accepted corrupt
permission, failed source reproduction, or a causal clock trace contradicting the
current diagnosis would revise these conclusions. No live approval is requested
for this offline work; a future live deployment still requires explicit approval.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_complete_history_scale_20260918_v1`.
See `terminal_qualification.json`, `pilot_candidate_failure_measurement.json`,
`host_clock_observation.json`, and the candidate/archive test and coverage reports.
