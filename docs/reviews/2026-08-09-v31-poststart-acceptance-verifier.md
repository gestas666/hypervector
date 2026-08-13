# v31 post-start technical acceptance verifier

## Problem restatement

The v31 transition guide required a first-run pressure-clock adoption check,
but the check was prose. A future operator could therefore describe v31 as
accepted without applying the same identity, coverage, pressure, health, and
protection rules.

## Implemented control

`scripts/v31_poststart_acceptance.py` now produces one immutable report-only
artifact for the exact checkpoint it reads. It rebuilds the identity-bound v31
route snapshot and accepts only when all of the following are true:

- phase and profile fingerprint identify the exact v31 candidate;
- checkpoint and signal-outcome coverage are complete from the new run;
- every HIP-3 breakout-pressure route has at least one evaluation;
- `imbalance_10` and `pressure_age_seconds` are finite numeric values for every
  evaluation, with no missing observations;
- pressure age remains within 0–30 seconds;
- runtime faults are zero;
- every open position is protected; and
- the transition drain is inactive.

A structurally valid rejection is persisted with `accepted=false` and returns
exit status 2. Unknown-identity or malformed-evidence errors fail explicitly. The
verifier imports no venue order client and grants no transition, execution,
sizing, closing, or promotion authority.

## Validation evidence

- Red phase: the new tests initially failed during collection because
  `hypervector.research.v31_poststart_acceptance` did not exist.
- Green phase: accepted, wrong-identity, incomplete-coverage, stale-pressure,
  missing-pressure, runtime-fault, unprotected-position, immutable-output, and
  input-nonmutation contracts pass.
- The real current v25 checkpoint was tested end to end and was correctly
  persisted as rejected for wrong identity and incomplete historical pressure
  coverage.
- The complete v31-focused suite passed 27 tests.
- Ruff, format checks, `git diff --check`, file length, and function length
  passed for the new path.
- Live v25 PID `37897`, checkpoint PID `23577`, and v31 tracker PID `79448`
  each remained on launchd run count one.

## Uncertainties and failure modes

The verifier consumes aggregate checkpoint metric diagnostics. It relies on
the separately hash-bound causal-book repair and parity observer; it does not
independently reconstruct exact raw-book selection or funding cursor
continuity. Those remain explicit raw-ledger checks in the transition guide.
Technical acceptance also does not establish positive expectancy.

Confidence is high that the command deterministically distinguishes the exact
tested technical states. Confidence in the economic value of v31 remains
medium because resolved live route samples are sparse and one-sided.

The technical claim is falsified by any accepted report with the wrong
profile, incomplete pressure observations, pressure age outside 0–30 seconds,
runtime faults, an unprotected open position, or execution side effects. The
economic pruning recommendation is updated by independent both-side forward
outcomes favoring SNDK or BRENTOIL Swing after costs.
