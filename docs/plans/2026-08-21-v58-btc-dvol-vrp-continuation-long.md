# V58 BTC DVOL-VRP Continuation Long Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and falsify one report-only BTC bullish-continuation candidate using a point-in-time Deribit implied-versus-realized volatility spread, without changing or restarting V58.

**Architecture:** Acquire immutable hourly BTC DVOL candles from Deribit's official public API, conservatively treat each candle as knowable only after its hour closes, and join them to completed Hyperliquid BTC bars. Generate one preregistered high-VRP bullish-breakout onset plus fixed controls, then replay next-bar entries and signal/protective exits through the existing event-driven shared-portfolio engine across the frozen chronological partitions. Publish source-bound, generator-bound artifacts and stop after standalone rejection; only a survivor may proceed to shared-route interaction research, and neither outcome grants live authority.

**Tech Stack:** Python 3.13, pandas, requests with injected test fetchers, PyArrow Parquet, existing Hypervector immutable-storage and shared-portfolio helpers, pytest.

---

## Constraints and frozen research contract

- Active runtime remains `multi_asset_growth_first_5000_eight_asset_incremental_v58`; do not edit, stop, restart, drain, arm, place, cancel, or resize through it.
- Hypothesis ID: `V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1`.
- Trial accounting: one new candidate, three mechanism controls, the unchanged V58 sweep control, and no action. No threshold, horizon, exit, delay, or cost sweep is authorized after results are inspected.
- Source family: Deribit BTC DVOL from official `public/get_volatility_index_data`, `resolution=3600`, paired with immutable Hyperliquid BTC one-minute bars and exact hourly funding.
- DVOL semantics: timestamp is conservatively treated as the hour-open label; OHLC becomes available at `timestamp + 1 hour`. A signal computed at that boundary executes no earlier than the next one-minute open.
- DVOL definition: a smoothed 30-day annualized options-implied volatility index. It is an action/volatility gauge, not a directional long signal by itself.
- Realized volatility: population standard deviation of the prior 720 completed hourly BTC log returns, annualized by `sqrt(24 * 365) * 100`.
- VRP feature: squared-volatility spread `(DVOL_close / 100)^2 - (realized_vol_30d / 100)^2`.
- Causal threshold: the current spread must be at or above the 75th percentile of the **previous** 2,160 hourly spreads, with a minimum 720 prior observations. The current observation is excluded.
- Bullish structure: completed hourly BTC close is above the prior 24-hour high and above EMA168. The prior-high window is shifted one hour.
- Primary entry: one pulse when `high_vrp AND bullish_structure` changes from false to true. A persistent state cannot repeatedly enter.
- Primary exits: one completed-hour exit pulse when BTC closes below EMA24 or VRP falls below its prior-window median; plus a fixed 100-bps protective stop, 250-bps target, and 72-hour maximum-hold fallback.
- Controls:
  - `price_only_bullish_breakout_long`: same bullish structure without the VRP condition, same exits and economics.
  - `high_vrp_only_long`: same high-VRP onset without bullish structure, same exits and economics.
  - `low_vrp_bullish_breakout_long_placebo`: bullish structure while VRP is at or below the causal prior-window 25th percentile, same exits and economics.
  - unchanged V58 hourly liquidity-sweep long and no action.
- Partitions: development `[2025-07-28, 2026-01-28)`, validation `[2026-01-28, 2026-04-28)`, pseudo-holdout `[2026-04-28, 2026-07-28)` UTC. All price partitions were previously opened; pseudo-holdout is a label, not a claim of pristine evidence.
- Scenarios:
  - nominal: 2 bps taker slippage per market side, conservative hour-close availability.
  - stress: 5 bps taker slippage per market side plus five additional minutes of signal delay.
  - delayed: 10 bps taker slippage per market side plus sixty additional minutes of signal delay.
- Fees: 4.5 bps taker entry/market exit, 1.5 bps maker target, 4.5 bps liquidation fee; exact hourly Hyperliquid funding.
- Sizing: $5,000 initial equity, 10% current-equity margin, 10x isolated leverage, $5,000 notional ceiling, BTC venue maximum 40x.
- Minimum sample: at least 10 completed primary trades in validation and 10 in pseudo-holdout under nominal timing.
- Standalone acceptance in validation and pseudo-holdout under all scenarios: positive net PnL, PF > 1, positive net excluding largest winner, zero liquidations, and no insolvency. Survival of the delayed 10-bps-per-side scenario is the preregistered lower-bound cost-headroom test; do not fabricate an exact break-even cost from bar data.
- Incremental acceptance: primary must exceed no action, the price-only control, and the unchanged V58 sweep on net PnL in both nominal out-of-development partitions. The low-VRP placebo must not match or exceed the primary in both partitions.
- A standalone survivor still requires semantic reproduction, unfavorable-regime disclosure, shared-V58 BTC route competition, and untouched prospective observation before any live proposal.
- The Deribit API and index methodology can change. Freeze raw pages, response parameters, retrieval times, page continuations, bytes, SHA-256, row ordering, and methodology URLs. Never silently restate a source bundle.
- Shared dirty worktree is authoritative. Do not revert, clean, commit, amend, or push unrelated/user work; this project rule supersedes generic plan commit steps.

### Task 1: Freeze the preregistration before acquiring source bytes or computing signals

**Files:**
- Create: `tests/test_v58_btc_dvol_vrp_preregistration.py`
- Create: `docs/research-journal/v58-btc-dvol-vrp-continuation-long-preregistration-20260821-v1.json`

**Step 1: Write the failing contract test**

Assert the JSON freezes the hypothesis ID, source endpoint, point-in-time availability, formulas, prior-only thresholds, entry/exit rules, controls, partitions, scenarios, costs, sizing, acceptance checks, search disclosure, and `execution_authority=none`.

**Step 2: Run test to verify RED**

Run: `uv run pytest tests/test_v58_btc_dvol_vrp_preregistration.py -q`

Expected: FAIL because the preregistration artifact does not yet exist.

**Step 3: Add the minimum preregistration JSON**

Record that only endpoint documentation and outcome-blind row coverage were inspected: 8,761 inclusive hourly observations over the one-year boundary. Candidate signal counts, forward returns, trade outcomes, and acceptance results must remain null/uninspected.

**Step 4: Run test to verify GREEN**

Run the same focused command and require PASS.

### Task 2: Acquire immutable official Deribit DVOL pages

**Files:**
- Create: `src/hypervector/research/deribit_dvol_acquisition.py`
- Create: `scripts/v58_btc_dvol_acquire.py`
- Create: `tests/test_deribit_dvol_acquisition.py`
- Create: `tests/test_v58_btc_dvol_acquire_script.py`

**Step 1: Write failing acquisition tests**

Inject a byte fetcher. Cover JSON-RPC errors, malformed OHLC rows, unsupported continuation direction, duplicate boundaries, gaps, non-hour timestamps, nonpositive/nonfinite DVOL, incomplete bounds, changed preregistration, preexisting output, and authority drift.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_deribit_dvol_acquisition.py tests/test_v58_btc_dvol_acquire_script.py -q`

Expected: import/behavior failure before the module exists.

**Step 3: Implement immutable backward pagination**

Fetch only `currency=BTC`, the frozen millisecond bounds, and `resolution=3600`. Preserve each raw JSON page, normalize unique ascending hourly OHLC rows, require exactly 8,761 inclusive timestamps and one-hour continuity, and publish `dvol.parquet` plus a manifest using existing immutable helpers. No candidate logic belongs in acquisition.

**Step 4: Verify GREEN**

Run the same focused command and require PASS without network calls.

### Task 3: Build point-in-time DVOL/realized-volatility features

**Files:**
- Create: `src/hypervector/research/btc_dvol_vrp_features.py`
- Create: `tests/test_btc_dvol_vrp_features.py`

**Step 1: Write failing feature tests**

Use synthetic hourly BTC and DVOL frames. Prove hour-close availability, prior-only 720-hour realized volatility, prior-only 2,160-hour quantiles, minimum history, squared-volatility units, shifted prior-high construction, EMA values, exact missing-data failures, and no full-sample fitting.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_btc_dvol_vrp_features.py -q`

Expected: import failure.

**Step 3: Implement the typed feature builder**

Expose one public documented function returning an ordered aware-UTC frame. Fail on missing/gapped/nonfinite source values rather than forward-filling. Keep all helper functions below 50 lines and the module below 500 lines.

**Step 4: Verify GREEN**

Run the focused test and require PASS.

### Task 4: Generate the primary and controls

**Files:**
- Create: `src/hypervector/research/btc_dvol_vrp_continuation.py`
- Create: `tests/test_btc_dvol_vrp_continuation.py`

**Step 1: Write failing signal tests**

Prove one-shot state onsets, reset/rearm behavior, long-only entries, completed-hour mapping to minute availability, strategic exits, control identity, no same-minute execution claim, and no signal on incomplete/missing inputs.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_btc_dvol_vrp_continuation.py -q`

Expected: import failure.

**Step 3: Implement the minimum signal builder**

Return a frozen dataclass containing four exact signal frames and their event times. Every frame must include `long_entry`, `short_entry`, `long_exit`, `short_exit`, and `signal_name`; shorts remain false.

**Step 4: Verify GREEN**

Run the focused test and require PASS.

### Task 5: Replay through one frozen economic contract

**Files:**
- Create: `src/hypervector/research/btc_dvol_vrp_replay.py`
- Create: `tests/test_btc_dvol_vrp_replay.py`

**Step 1: Write failing replay tests**

Cover next-bar entry, next-bar signal exit, fixed 100/250-bps barriers, 72-hour fallback, exact funding requirement, all three delay/slippage scenarios, gap cancellation, sizing, fees, and unchanged sweep/no-action controls.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_btc_dvol_vrp_replay.py -q`

Expected: import failure.

**Step 3: Compose existing event-driven helpers**

Reuse `validated_btc_replay_market`, `shift_btc_entry_signals`, `mask_btc_entry_window`, `SharedPortfolioConfig`, `evaluate_shared_bar_portfolio`, and the unchanged sweep builder. Do not duplicate the simulator or import live order code.

**Step 4: Verify GREEN**

Run the focused test and require PASS.

### Task 6: Run the complete chronological experiment

**Files:**
- Create: `src/hypervector/research/btc_dvol_vrp_experiment.py`
- Create: `src/hypervector/research/btc_dvol_vrp_historical.py`
- Create: `tests/test_btc_dvol_vrp_experiment.py`
- Create: `tests/test_btc_dvol_vrp_historical.py`

**Step 1: Write failing orchestration tests**

Require exactly 3 partitions x 3 scenarios x 6 arms, complete trade rows, cadence/interarrival, gross/net/fees/funding/ex-largest metrics, delayed-scenario cost-headroom disposition, all acceptance failures, unfavorable slices, and no performance abort.

**Step 2: Verify RED**

Run both focused tests and expect failure.

**Step 3: Implement chronological orchestration**

Reuse the frozen partition boundaries. Include enough pre-partition warmup for the 2,160-hour prior window, but mask entries half-open after signal delay. Never fit thresholds on validation or pseudo-holdout future observations.

**Step 4: Verify GREEN**

Run both focused tests and require PASS.

### Task 7: Bind source and generator identities, then execute once

**Files:**
- Create: `scripts/v58_btc_dvol_vrp_experiment.py`
- Create: `tests/test_v58_btc_dvol_vrp_experiment_script.py`
- Create after acquisition: `docs/research-journal/v58-btc-dvol-vrp-continuation-long-input-registration-20260821-v1.json`
- Create through immutable publisher: `data/logs/research/bidirectional_cohort/v58_btc_dvol_vrp_continuation_long_20260821_v1/`

**Step 1: Write failing publisher tests**

Require verified preregistration, DVOL manifest/parquet, BTC bars, BTC funding, and generator hashes. Reject changed bytes, incomplete coverage, output reuse, outcome-inspected registration, or any execution authority.

**Step 2: Verify RED, then implement publisher and verify GREEN**

Run: `uv run pytest tests/test_v58_btc_dvol_vrp_experiment_script.py -q`

The publisher must emit `report.json`, `trades.parquet`, and `manifest.json` atomically and refuse preexisting output.

**Step 3: Acquire and audit source without outcomes**

Run: `uv run python scripts/v58_btc_dvol_acquire.py`

Verify page continuity, exact inclusive bounds, 8,761 rows, finite positive OHLC, raw-page and normalized hashes, and no candidate fields.

**Step 4: Bind exact inputs with `apply_patch`**

Record every source and generator byte/hash identity before any candidate signal or return output is inspected.

**Step 5: Execute exactly once**

Run: `uv run python scripts/v58_btc_dvol_vrp_experiment.py`

Preserve losing, sparse, or technically rejected outcomes without threshold revision.

### Task 8: Reproduce, journal, and decide

**Files:**
- Create: `docs/research-journal/v58-btc-dvol-vrp-continuation-long-result-20260821-v1.json`
- Create only through publisher: a distinct reproduction directory.

**Step 1: Reproduce from registered bytes**

Require byte-identical trades and semantically identical reports after removing only generation/path-local manifest fields.

**Step 2: Apply preregistered gates**

If any standalone check fails, journal `reject_exact_candidate_without_retuning` and stop. If every check passes, run a separately preregistered shared-route comparison; do not create or edit a live profile.

**Step 3: Append the immutable journal revision**

Use `research-db-journal-append`, then `research-db-journal-report`; require every evidence identity `matching`, `execution_authority=none`, and `runtime_strategy_changed=false`.

### Task 9: Verification and live-safety refresh

**Files:**
- Verify only; no live mutation.

**Step 1: Run focused and non-network tests**

Run all new tests plus `tests/test_shared_bar_portfolio.py`, relevant immutable-storage tests, and finally `uv run pytest tests/ -q -m "not network"` when practical.

**Step 2: Audit source standards**

Require explicit types, public docstrings, no `Any` without justification, files <=500 lines, functions <=50 lines, no broad catches, no live imports, no network tests, and actionable errors.

**Step 3: Refresh current V58 safety**

Verify the active process/profile fingerprint, heartbeat, venue position/order reconciliation, protection for every open lifecycle, zero unexpected faults, and unchanged order/config authority. Keep the BTC recorder running.

**Step 4: Report the disposition**

Provide recommendation, why now, evidence, regime, alternatives, proposed live change, upside, risks, validation completed/remaining, success and rollback criteria, confidence, and exact human approval needed for any later live transition.
