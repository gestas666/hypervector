# Startup candle provenance implementation plan

**Goal:** Preserve the full initial retained candle inputs so future provider and regime initialization can be replayed exactly.

**Architecture:** A once-only poller observer captures the actual merged 1m frames before resampling or provider evaluation. An immutable Parquet bundle and hashed manifest bind those inputs to the run, profile, activation boundary and observation cutoff. A small ledger event reports either the bundle reference or an explicit capture failure; archival availability does not introduce a trading gate.

**Tech stack:** Existing Python, pandas/PyArrow, SHA256, filesystem atomic directory publication, pytest with offline fixtures.

## Evidence, constraints and alternatives

The September 15 SPCX audit reproduced the published band crossing and ATR recurrence, but the original startup input frame was not retained: chart telemetry keeps only 360 minutes. This is a reproducibility gap, not evidence that the ATR calculation or strategy is wrong. The existing process cannot recover its discarded startup inputs through this change.

Preserve provider calculations, retained-frame selection, request count/order, execution settings and process ownership. Keep configured symbol order and all actual frame columns/dtypes. Capture includes an incomplete final candle if the provider input contains it; completion filtering remains an explicit replay step. Do not represent requested lookback as actual coverage or this archive as a raw venue response.

Alternatives: doing nothing leaves the seed gap; expanding chart telemetry repeatedly grows the ledger and TUI footprint; fetching a second snapshot may observe different candles. A once-only sidecar reuses the exact in-memory input. It adds startup disk I/O, which must be measured. Expected filesystem/serialization failure is recorded as unavailable and does not prevent normal provider evaluation. Failure to append the authoritative ledger remains an existing technical failure.

## 1. Reproduce the gap with an offline test

Create `tests/test_cohort_startup_candles.py` and shared fixture support. Bind a recording observer to the real poller, supply more than 360 rows including a current incomplete bar, and compare a second unobserved poller. Require one capture before collectors, unchanged requests/results, and no capture on subsequent cycles. Run the new test with the installed Python and `PYTHONPATH=src:.`; expect failure because the observer is absent.

## 2. Archive and replay

Create `src/hypervector/live/cohort_startup_candles.py` with typed context, immutable writer and externally hashed loader. Use indexed symbol-safe filenames, complete metadata and per-file SHA256. Publish a fully written temporary directory atomically, with durable file writes. Reject existing destinations, changed hashes, malformed metadata, mismatched context and path substitution. Retain no extra full frame after the callback.

Tests: exact pandas equality (including float bits, timezone, index and auxiliary columns), more than 360 rows, exact 15m/hourly band/ATR replay, mutated/truncated/missing payload, modified manifest, different run/profile/cutoff, duplicate capture and publication failure. Use no network or execution clients.

## 3. Wire observable capture without execution authority

Create `src/hypervector/live/cohort_startup_candle_recorder.py`. Extend `ConfiguredMultiAssetIntentPoller` with pre-activation observer binding and one invocation before source resampling. Add a recorder factory to `MultiAssetCohortTelemetry`, a `startup_candle_inputs` ledger event type, and bind it in `scripts/multi_asset_bidirectional_live.py` before runner activation. Expected archival errors emit an explicit unavailable record; unexpected exceptions and ledger failures propagate.

Tests: cannot bind after activation or twice; no partial capture on transient fetch failure; capture follows successful retry; ledger reference uses the exact profile/run; archive failures remain visible and leave provider output unchanged; ledger failure does not masquerade as successful capture. Mock runner construction and signal installation in command wiring tests.

## 4. Qualification and reviewable handoff

Run affected archive, poller, telemetry, ledger, command and provider tests. Measure new-code coverage and structure limits. Replay frozen September 15 public SPCX input and measure seven-asset-sized archive time, bytes and memory. Reconcile against the same unmodified input, not an invented retrospective seed. No Rust change is required.

Save failed/passing receipts, immutable experiment evidence, source patch/rollback, review and DuckDB hypothesis revision. Only install source after qualification and backup; never activate or restart a financial process. At the next user-controlled startup, inspect the new event and reverify the bundle. No profit improvement is claimed. A provider/request mismatch, inexact replay, hidden failure, unbounded storage or material measured startup delay falsifies acceptance.
