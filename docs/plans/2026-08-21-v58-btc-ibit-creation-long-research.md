# V58 BTC IBIT Creation Long Research Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and falsify a report-only BTC long candidate based on persistent point-in-time IBIT share creations, without changing the active V58 runtime.

**Architecture:** Acquire one immutable official BlackRock fund-data response, parse only the `Historical` worksheet, and map creation/redemption episode onsets to conservatively delayed UTC availability times. Replay the primary and controls through the existing V58-compatible 60-bps stop, 60-bps target, 24-hour maximum-hold engine with exact Hyperliquid funding, then publish an immutable source- and generator-bound result. Standalone survival is required before shared-route portfolio comparison; no component imports live order code or grants execution authority.

**Tech Stack:** Python 3.13, pandas, requests with injected test fetchers, PyArrow Parquet, pytest, existing Hypervector shared-bar replay and immutable storage helpers.

---

## Constraints and frozen research contract

- Active live profile remains `multi_asset_growth_first_5000_eight_asset_incremental_v58`; this work must not edit, restart, drain, arm, or place through that runtime.
- Hypothesis ID: `V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1`.
- Source mechanism: IBIT shares outstanding increase on two consecutive issuer observations; enter once at the onset of the two-positive-observation state.
- Point-in-time availability: an issuer row with as-of date `D` is treated as unavailable until `D + 1 calendar day at 12:00 UTC`; the replay enters at the next one-minute open.
- Primary signal: `delta_shares[D] > 0`, `delta_shares[previous observation] > 0`, and the preceding observation did not already form a two-positive streak.
- Controls: first-positive-observation creation onset; two-consecutive-redemption onset traded long as a direction placebo; unchanged V58 hourly liquidity-sweep long; no action.
- Partitions: development `[2025-07-28, 2026-01-28)`, validation `[2026-01-28, 2026-04-28)`, and previously opened pseudo-holdout `[2026-04-28, 2026-07-28)` UTC.
- Scenarios: nominal 2 bps taker slippage per side; stress 5 bps per side; publication-delay sensitivity adds 1,440 minutes to the frozen availability timestamp at nominal slippage.
- Execution geometry: taker IOC entry, 60-bps protective stop, 60-bps target, 24-hour maximum hold, 10x isolated leverage, 10% current equity margin, $5,000 notional ceiling, exact hourly funding, current 4.5-bps taker and 1.5-bps target-maker research fees.
- Minimum validation and pseudo-holdout sample: 10 completed primary trades per partition under nominal timing.
- Acceptance: primary net PnL positive, PF above one, net PnL excluding largest winner positive, zero liquidations, and no insolvency in validation and pseudo-holdout under all three scenarios; primary must exceed no action and the unchanged sweep in both nominal out-of-development partitions; the redemption-long placebo must not equal or exceed the primary in both out-of-development partitions.
- Search accounting: all BTC price partitions were previously opened and several other BTC-long families were already tested. The source mechanism is new, but the result is not a pristine holdout and cannot by itself authorize live promotion.
- Corporate-action safety: fail the source if adjacent shares/NAV ratios resemble an unregistered 2x, 3x, 4x, 5x, or 10x split or reverse split. Do not silently adjust or reinterpret the discontinuity.
- The shared dirty worktree is authoritative. Do not revert, clean, commit, amend, or push unrelated/user changes; this plan intentionally omits the generic skill's commit steps.

### Task 1: Freeze preregistration before source acquisition or candidate outcomes

**Files:**
- Create: `docs/research-journal/v58-btc-ibit-creation-persistence-long-preregistration-20260821-v1.json`
- Test: `tests/test_v58_btc_ibit_creation_preregistration.py`

**Step 1: Write the failing contract test**

Assert the JSON freezes the hypothesis, source URL and still-unacquired state, point-in-time availability, primary/control definitions, exact partitions, costs, scenarios, acceptance checks, prior-search disclosure, and `execution_authority=none`.

**Step 2: Run the focused test and verify RED**

Run: `uv run pytest tests/test_v58_btc_ibit_creation_preregistration.py -q`

Expected: FAIL because the preregistration file is absent.

**Step 3: Add the minimum preregistration JSON**

The source record must have `state=not_acquired_before_preregistration` and null path/bytes/SHA-256. It may disclose already-observed technical metadata (worksheet names and expected latest date), but no signal count, returns, PnL, or acceptance result.

**Step 4: Run the focused test and verify GREEN**

Run: `uv run pytest tests/test_v58_btc_ibit_creation_preregistration.py -q`

Expected: PASS.

### Task 2: Parse and validate the official BlackRock historical worksheet

**Files:**
- Create: `src/hypervector/research/blackrock_ibit_history.py`
- Create: `tests/test_blackrock_ibit_history.py`

**Step 1: Write failing parser tests**

Cover ordered extraction of `as_of_date`, `nav_per_share`, and `shares_outstanding`; malformed/missing worksheets; duplicate or unordered dates; nonpositive/nonfinite fields; unexpected columns; and a synthetic 3-for-1 split-like discontinuity.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_blackrock_ibit_history.py -q`

Expected: collection failure because the parser module is absent.

**Step 3: Implement the minimum tolerant parser**

Use a private `html.parser.HTMLParser` state machine because the issuer response embeds HTML inside SpreadsheetML and is not strict XML. Expose one public typed function with a docstring returning an ascending DataFrame; reject source-identity and split-discontinuity drift explicitly.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_blackrock_ibit_history.py -q`

Expected: PASS.

### Task 3: Acquire and publish an immutable outcome-blind BlackRock bundle

**Files:**
- Create: `src/hypervector/research/blackrock_ibit_acquisition.py`
- Create: `scripts/v58_btc_ibit_creation_acquire.py`
- Create: `tests/test_blackrock_ibit_acquisition.py`
- Create: `tests/test_v58_btc_ibit_creation_acquire_script.py`

**Step 1: Write failing acquisition tests**

Inject a byte fetcher; prove empty responses, preregistration drift, preexisting output, parser failure, and authority drift fail explicitly. Prove a valid response publishes `fund_data.xml`, normalized `history.parquet`, and `manifest.json` with exact SHA-256/bytes and no candidate fields.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_blackrock_ibit_acquisition.py tests/test_v58_btc_ibit_creation_acquire_script.py -q`

Expected: collection failure because the acquisition modules are absent.

**Step 3: Implement immutable acquisition**

Reuse `publish_immutable_directory`, `write_immutable_parquet`, `write_json`, and `file_evidence`. The script must validate the preregistration identity before `requests.get`, expose no live flags, and record `candidate_outcomes_computed=false`.

**Step 4: Verify GREEN**

Run the same command and expect PASS.

### Task 4: Construct point-in-time creation and placebo episode signals

**Files:**
- Create: `src/hypervector/research/btc_ibit_creation_long.py`
- Create: `tests/test_btc_ibit_creation_long.py`

**Step 1: Write failing signal tests**

Prove the primary fires only on the second consecutive positive issuer observation, does not repeat on a third positive day, treats zero as a reset, uses consecutive issuer rows across weekends, sets availability to next-calendar-day 12:00 UTC, maps the pulse to the market index, and never emits shorts. Cover first-positive and two-redemption-long controls, out-of-range events, missing market minutes, duplicates, and naive timestamps.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_btc_ibit_creation_long.py -q`

Expected: collection failure because the signal module is absent.

**Step 3: Implement the minimum signal builder**

Return a frozen dataclass containing three signal frames and their exact UTC event times. Each frame must include `long_entry`, `short_entry`, `long_exit`, `short_exit`, and `signal_name`; absent events remain false rather than becoming missing data.

**Step 4: Verify GREEN**

Run the focused test and expect PASS.

### Task 5: Replay the primary and controls through unchanged V58 economics

**Files:**
- Create: `src/hypervector/research/btc_ibit_creation_replay.py`
- Create: `tests/test_btc_ibit_creation_replay.py`

**Step 1: Write failing replay tests**

Prove next-bar entry, 60/60/24h economics, exact funding requirement, nominal/stress slippage, 1,440-minute publication delay, entry-window masking after the delay, gap cancellation, all four active-arm reports, event timestamps, and `execution_authority=none`.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_btc_ibit_creation_replay.py -q`

Expected: collection failure because the replay module is absent.

**Step 3: Implement by composing existing replay helpers**

Reuse `validated_btc_replay_market`, `btc_fixed_60_60_portfolio_config`, `shift_btc_entry_signals`, `mask_btc_entry_window`, `evaluate_shared_bar_portfolio`, and the unchanged sweep-control signal builder. Do not duplicate the simulator.

**Step 4: Verify GREEN**

Run the focused test and expect PASS.

### Task 6: Build the complete chronological experiment and acceptance report

**Files:**
- Create: `src/hypervector/research/btc_ibit_creation_experiment.py`
- Create: `src/hypervector/research/btc_ibit_creation_historical.py`
- Create: `tests/test_btc_ibit_creation_experiment.py`
- Create: `tests/test_btc_ibit_creation_historical.py`

**Step 1: Write failing matrix/report tests**

Require exactly 3 partitions x 3 scenarios x 5 arms, complete trade rows, signal frequency/interarrival, fees/funding/gross/net/ex-largest metrics, comparison rows, every frozen acceptance failure, no performance abort, and explicit opened-holdout limitations.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_btc_ibit_creation_experiment.py tests/test_btc_ibit_creation_historical.py -q`

Expected: collection failure because the experiment modules are absent.

**Step 3: Implement orchestration and reporting**

Reuse the frozen BTC partition dataclass/bounds and existing replay summaries. Slice with enough warmup for EMA55 and map all issuer observations causally; mask entries half-open by partition only after the frozen reporting delay.

**Step 4: Verify GREEN**

Run the focused command and expect PASS.

### Task 7: Publish a source- and generator-bound immutable experiment

**Files:**
- Create: `scripts/v58_btc_ibit_creation_experiment.py`
- Create: `tests/test_v58_btc_ibit_creation_experiment_script.py`

**Step 1: Write failing publisher tests**

Require an input-registration schema with verified preregistration, BlackRock manifest/history, BTC bars, and BTC funding identities. Prove changed bytes, incomplete source coverage, output reuse, generator drift, or any outcome-inspected registration flag fail before publication.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_v58_btc_ibit_creation_experiment_script.py -q`

Expected: collection failure because the publisher is absent.

**Step 3: Implement the immutable publisher**

Load exact sources, attach funding, run once, reverify sources/generators after calculation, and atomically publish `report.json`, `trades.parquet`, and `manifest.json`. The report must state that live promotion is unauthorized regardless of outcome.

**Step 4: Verify GREEN**

Run the focused test and expect PASS.

### Task 8: Acquire, bind inputs, and run exactly once

**Files:**
- Create through immutable script: `data/cache/vendor/blackrock/IBIT/20240105_20260820_history_v1/`
- Create: `docs/research-journal/v58-btc-ibit-creation-persistence-long-input-registration-20260821-v1.json`
- Create through immutable script: `data/logs/research/bidirectional_cohort/v58_btc_ibit_creation_persistence_long_20260821_v1/`

**Step 1: Run acquisition**

Run: `uv run python scripts/v58_btc_ibit_creation_acquire.py`

Expected: one immutable bundle path; no signal/outcome fields.

**Step 2: Audit source quality without returns**

Verify worksheet identity, exact row/date coverage, no duplicate dates, no split discontinuity, and every manifest checksum.

**Step 3: Bind all exact source files with `apply_patch`**

The registration must state candidate signal count/returns/PnL were not inspected and record every path, byte count, and SHA-256.

**Step 4: Run the experiment once**

Run: `uv run python scripts/v58_btc_ibit_creation_experiment.py`

Expected: one immutable report/trade/manifest bundle, whether accepted or rejected.

### Task 9: Disposition and optional shared-route comparison

**Files:**
- Create: `docs/research-journal/v58-btc-ibit-creation-persistence-long-result-20260821-v1.json`
- Modify only if standalone survives: report-only BTC route-competition research modules/tests.

**Step 1: Reproduce the immutable result**

Run the publisher against a new reproduction output and require report/trade semantic equality after excluding generation timestamps and path-local manifest fields.

**Step 2: Apply the preregistered acceptance checks**

If any standalone check fails, journal `rejected` and do not perform portfolio selection. If all survive, compare candidate+sweep+both unchanged Hulk shorts against unchanged V58 BTC routes under the same partitions/scenarios.

**Step 3: Journal the evidence**

Record exact hashes, observed metrics, uncertainty, failure modes, falsifier, and `execution_authority=none`. A survivor becomes an approval-ready proposal, not an automatic live change.

### Task 10: Verification and live-safety refresh

**Files:**
- Verify only; do not modify active live files.

**Step 1: Run focused and non-network regression tests**

Run all new tests, relevant shared replay/storage tests, then `uv run pytest tests/ -q -m "not network"` when practical.

**Step 2: Verify source standards**

Check all new functions have explicit types, public APIs have docstrings, files remain below 500 lines, functions below 50 lines, and no broad catches, secrets, live imports, or network tests exist.

**Step 3: Refresh live safety separately**

Read the current V58 checkpoint, backend heartbeat, venue reconciliation, open-position protection, and faults. Confirm the experiment did not alter profile fingerprint, runtime strategy, orders, sizing, or execution authority.

**Step 4: Deliver the approval-ready result**

Report recommendation, evidence, applicable conditions, upside, risks, completed/remaining validation, success and rollback predicates, confidence, and the exact approval required for any later live transition.
