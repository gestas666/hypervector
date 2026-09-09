# Historical Provider and Regime Parity Implementation Plan

> Execute task by task in the existing research worktree, using the local
> `executing-plans` and `test-driven-development` workflows. The active goal
> already authorizes research implementation; no execution-choice pause is needed.

**Goal:** Compare the complete historical provider, regime and routing contracts
with their registered controls before qualifying the prospective evaluator.

**Architecture:** Authenticate existing controls and their exact native source
files, then compare every scheduled decision against a fresh rolling-window
evaluation. Preserve every inactive, absent, changed and conflicting result.
Publish source-pinned, complete chunks so the long comparison remains observable.
Historical provider comparison is separate from new account or prospective returns.

**Tech Stack:** Python 3.13, pandas, PyArrow, existing native collectors and
regime/router primitives, pytest, deterministic JSON/gzip and immutable source
archives. Use the established Python environment and up to four local workers.

## Task 1: Authenticate the historical core controls

Create `scripts/v89_provider_history_sources.py` and
`tests/test_v89_provider_history_sources.py`.

1. Write tests rejecting altered registration/manifest/bar/batch bytes, wrong
   source variants, conflicting or duplicated decision identities, out-of-window
   controls and missing contract columns. Use temporary local files only.
2. Run `PYTHONPATH=src:scripts:tests:. ../hypervector/.venv/bin/python -m pytest
   tests/test_v89_provider_history_sources.py -q -m 'not network'`; verify failures
   precede implementation.
3. Reuse `ReplayInputEvidence`, `read_authenticated`, `evaluation_contract` and
   the registered recorded-native study. Load the first/last core manifests and
   their referenced `bars.parquet` files, not the later `continuity.parquet`
   warmup substitutes. Return typed source/control records.
4. Rerun the tests and check source/code limits before committing.

## Task 2: Compare every rolling core decision

Create `scripts/v89_provider_history_compare.py` and
`tests/test_v89_provider_history_compare.py`.

1. Test a collector spy against exact completed-time windows: exclude future
   bars, retain the fourteen-day lower bound, preserve source gaps, and request
   only the current decision. Test present/absent, changed side/exit/regime/value,
   duplicate and wrong-time outputs. Compare finite floats exactly.
2. Implement a typed iterator that calls the existing collector with
   `observed_at=D` and `after_decision_time_ms=D-1`, selecting only
   `D-14 days <= timestamp < D`. Compare each native minute against the archived
   execution/regime contract, including minutes absent from either side.
3. Retain actual and expected contract values and every differing field. A
   comparison mismatch is a measured result; malformed evidence is an error.
   Do not equate the archived contract with unavailable historical readiness
   fields or independent indicator reimplementation.
4. Verify unit tests, exact source-bound controls and relevant existing replay
   tests. Do not tune strategies to make a comparison pass.

## Task 3: Run the complete fixed historical comparison

Create `scripts/v89_full_provider_regime_parity.py` and its focused CLI tests.

1. Test immutable publication, declared scope/counts, source identity checks and
   refusal to overwrite completed results.
2. Fix core decision bounds to `(2026-07-21 00:00, 2026-09-07 00:00]` UTC,
   preserving the archived controls' convention. Compare all native minutes for
   BTC/ETH/SOL/HYPE and both source variants: 552,960 variant/minute checks.
   These are repeated decisions, not independent trades.
3. Use bounded workers and immutable per-day result files with progress output.
   Record process handles and actual completed chunks; poll the same live run
   across continuations. Do not restart because observation timed out.
4. Freeze and verify the source archive before the long run. Preserve all
   mismatches and gaps; no favorable subset can establish full agreement.

## Task 4: Resolve the remaining noncrypto and routing contracts

1. The registered XYZ candles begin July 19. Retain the missing July 7–19
   fourteen-day prefix explicitly. Earlier mixed-source files contain funding,
   not candles; unregistered SPCX trade bars are not interchangeable source
   evidence. Do not shorten the declared comparison or pad missing candles.
2. Compare all original XYZ signal/exit/anchor rows using their actual shorter
   initialization, then separately assess the fourteen-day rolling convention.
   Reuse `build_hourly_price_signals` and the original model contracts. Any new
   recovered source requires separate provenance and sensitivity evidence.
3. Compare canonical preference and the native router on complete eligible
   historical sets plus controlled conflicts. Same-symbol descending provider
   priority and cross-symbol first-occurrence order are distinct contracts.
4. Preserve historical HYPE 5m-based support weighting and inclusive hold time.
   Trace UNKNOWN/unavailable inputs through the frozen helper before changing
   any adapter; report unresolved compatibility without inventing a state.

## Acceptance and remaining authority

Archive reproducibility, full declared counts, exact source/control identities
and explicit differences are required. Full provider/regime/routing agreement
remains unqualified until all applicable contracts pass; a smaller component
result is not a complete evaluator. Source windows and native inputs may remain
incomplete even when arithmetic is correct.

Record source hashes, tests, complete or running-job scope and findings in the
research ledger. Both prospective outcome seals remain intact. No live strategy,
configuration, sizing, execution, TUI, process or order change is part of this
plan. This work does not establish profitability or authorize deployment.
