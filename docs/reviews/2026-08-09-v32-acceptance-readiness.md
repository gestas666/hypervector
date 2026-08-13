# V32 technical acceptance readiness review

## Problem and success criterion

The inactive v32 profile could not be considered transition-ready because the
existing post-start and raw-ledger validators intentionally recognized only
v31. Success required an execution-incapable v32 path that preserved v31
isolation, bound exact v32 authority and evidence identity, failed closed on
incomplete causal telemetry, and left live v25 untouched.

## Implemented boundary

`scripts/v32_acceptance.py` creates one immutable bundle containing separate
`v32_poststart_acceptance_v1` and `v32_raw_ledger_acceptance_v1` results. The
input snapshot requires the exact v32 profile and fingerprint, 21 executable
routes, three observe-only commodity Swing routes, bidirectional observation,
the exact route-authority journal hash, and protected open positions.

The aggregate check requires complete provider metrics with finite
`imbalance_10` and `pressure_age_seconds` values no older than 30 seconds. The
raw check independently resolves the causal top-ten depth books, proves one
common provider cutoff, checks that the selected book is the latest admissible
book, verifies contiguous funding cursors, and rejects duplicate funding
payments. Either rejection makes the combined command return exit status 2.

## Validation evidence

- Red-first tests proved the generic functions and named v32 modules were
  absent before implementation.
- Twenty-one focused builder, identity, raw-ledger, snapshot, and command tests
  pass.
- Fifty combined v31/v32 transition, journal, tracker, and script tests pass.
- The complete post-tracker non-network Python suite passes 4,406 tests with four
  intentional deselections and 27 existing warnings.
- The complete `hypervector-tui` Rust unit, integration, and doc-test suite
  passes.
- Ruff lint and formatting checks pass; touched source files remain below 500
  lines and public functions retain explicit types and docstrings.
- A read-only command probe against active v25 rejected exact v32 identity and
  created no output file.
- Live v25 and checkpoint PIDs, run counts, profile fingerprint, protected
  positions, and healthy lifecycle remained unchanged after verification.

## Forward-tracking evidence

The route-forward core is now versioned rather than hardcoded to v31. Existing
v31 behavior remains covered while v32 has separate publisher, monitor,
snapshot schema, and hash-chained event schema. The first one-shot v32 baseline
was captured against active v25 at 2026-08-09T22:51:06Z. It records v32 as
inactive, all three commodity Swing routes as proposed observe-only routes,
seven eligible signals, 12 resolved horizons, and no execution authority. The
initial material event hash is
`8645e61f1ed0570be5a478e1b8b6736d7b1de0d0ef01443dfe775797ab426284`.

Correction: the initial monitor call exposed an adapter defect after the
bounded snapshot was safely written. The monitor supplied a path to a function
expecting a parsed snapshot, so no material event was written. A failing test
reproduced that exact boundary. The corrected adapter loads and validates the
JSON mapping before invoking the appender; the retry wrote one valid event.
The incident had no order, strategy, profile, process, or live-ledger effect.
No continuous v32 service has been started, so tracking readiness and tracking
activity remain separate states in the transition contract.

## Remaining risks and falsifiers

This proves technical readiness of the verifier, not strategy profitability,
transition readiness, or future live acceptance. V32 remains inactive because
the current portfolio has seven open positions and lacks a completed drain,
flat/order-free snapshot, verified prechange bundle, and explicit v32 live-risk
authorization.

The technical conclusion must be revised if a wrong profile or phase is
accepted, route or journal drift passes, incomplete/stale pressure telemetry
passes, funding gaps or duplicate payments pass, an immutable artifact is
overwritten, the verifier imports execution authority, or the live v25 process
changes as a side effect. Confidence is high for the tested technical boundary
and low for future v32 economics until resolved forward/live evidence exists.
