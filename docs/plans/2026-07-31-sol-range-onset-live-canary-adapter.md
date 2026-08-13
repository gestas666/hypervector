# SOL Range-Onset Live Canary Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver one fail-closed command that runs the frozen SOL range-onset backend and its read-only TUI in shadow or explicitly armed $150 mainnet-canary mode, with venue-authoritative fills, positions, stops, fees, funding, liquidation, and reconciliation telemetry.

**Architecture:** The Python backend remains the only execution authority. A typed strategy state machine produces intents; a narrow Hyperliquid adapter translates them into isolated entry, protective-stop, reduce-only exit, and reconciliation operations. The Rust TUI consumes a selected backend ledger and never creates orders. Historical replay, forward shadow, and live execution share the same frozen strategy contract but preserve distinct evidence sources and ledgers.

**Tech Stack:** Python 3.12, uv, pytest, DuckDB, official Hyperliquid Python SDK, Rust, Ratatui, Cargo.

**Implementation checkpoint (2026-07-31):** Tasks 1-9 are implemented and
covered by mocked non-network tests. The complete public-trade four-block audit
selected the 80-bps arm as `supportive_but_fragile`; it did not establish a
forward profitability claim. Task 11 software and funded-wallet preflight are
green under unified-account mode. Exact CLOID/OID response-loss and restart
recovery is implemented and verified for entry, stop, close, and cancellation.
The stale observer was replaced with current-code no-submit shadow without
resetting evidence. The configured signing key still reports main-wallet role
`user` rather than API-agent role `agent`; Task 12 remains blocked on that
credential correction and no live order has been placed.

---

## Constraints and measurable acceptance criteria

- Paper/shadow constructs no authenticated exchange client and cannot submit.
- Live remains disarmed unless both `--enabled` and `--i-accept-live-risk` are present.
- Mainnet only; SOL isolated leverage is explicitly set to 5x and venue maximum is revalidated.
- Canary sizing is the smaller of 3% of venue equity at 5x and a $22.50 notional cap.
- Exactly one SOL position may exist. Reversal requires a verified flat state first.
- A completed entry must have a venue-native reduce-only stop sized from the reconciled fill.
- Restart reconciles venue position, open orders, fills, and local state before strategy evaluation.
- TUI Screen 4 shows requested mode, effective mode, armed state, backend run identity, and ledger path.
- One launcher supervises backend and TUI in one terminal while preserving process separation.
- Unit and integration tests make no network calls. No live call is made during implementation verification.
- Replay friction reports include entry/exit fees, depth VWAP, observed latency, oracle-referenced funding, mark-trigger limitations, stop/liquidation outcomes, and evidence gaps.

## Task 1: Correct funding reference evidence

**Files:**
- Modify: `src/hypervector/research/sol_range_onset_shadow.py`
- Create: `src/hypervector/research/oracle_price_series.py`
- Modify: `scripts/multi_asset_range_onset_event_replay.py`
- Create: `tests/test_sol_range_onset_funding_reference.py`
- Modify: `tests/test_multi_asset_range_onset_event_replay_script.py`

1. Add failing tests proving forward funding uses `AssetContextEvent.oracle_price`, not mark price.
2. Add failing tests for a typed causal oracle series that selects the latest sample at or before settlement, enforces a maximum staleness bound, and rejects missing evidence.
3. Run the focused tests and confirm the intended failures.
4. Implement the smallest typed oracle-price lookup and replace the bar-open historical proxy.
5. Emit funding-reference source, observation timestamp, and gap in replay evidence.
6. Run focused tests, then all non-network research tests.

## Task 2: Add measured decision-latency replay

**Files:**
- Modify: `src/hypervector/research/range_onset_event_models.py`
- Modify: `src/hypervector/research/range_onset_event_replay.py`
- Modify: `scripts/multi_asset_range_onset_event_replay.py`
- Create: `scripts/sol_range_onset_latency_surface.py`
- Create: `tests/test_range_onset_event_latency.py`
- Create: `tests/test_sol_range_onset_latency_surface_script.py`

1. Add failing tests for a non-negative `decision_delay_ms` configuration value.
2. Prove entry and signal-driven exit fills use decision time plus delay; venue stop crossings remain driven by mark evidence rather than delayed strategy polling.
3. Preserve original decision timestamps separately from submission and snapshot timestamps.
4. Implement the frozen robustness surface at 0, 8,000, and 16,000 ms for both 60 and 80 bps stop candidates.
5. Record forward-observer latency provenance and quantiles in the artifact.
6. Run focused tests and reproduce the zero-delay baseline hash-compatible metrics where schema changes permit.

## Task 3: Finish the preregistered held-out replay

**Files:**
- Modify: `docs/reviews/2026-07-31-sol-range-onset-backward-validation.md`
- Create: `docs/reviews/2026-07-31-sol-range-onset-friction-audit.md`
- Create: `data/logs/research/sol_range_onset_*_block02_*.json`
- Create: `data/logs/research/sol_range_onset_*_block04_*.json`

1. Verify immutable archive coverage and hashes for exact Blocks 2 and 4.
2. Run the frozen 60/80 bps, 3%-margin, 5x, 48-hour replay without parameter changes.
3. Run the preregistered 0/8/16-second latency surface.
4. Report per block and pooled trades, long/short split, PF, net return, realized and mark drawdown, fees, funding, stop exits, liquidation exits, depth failures, and evidence failures.
5. Select 60 or 80 bps using the declared held-out rule. If evidence is inconclusive, retain both as shadow-only hypotheses rather than choosing post hoc.

## Task 4: Define the frozen canary profile

**Files:**
- Create: `src/hypervector/live/sol_range_onset_config.py`
- Create: `configs/sol_range_onset_canary.toml`
- Create: `tests/test_sol_range_onset_live_config.py`

1. Add failing tests for mode, symbol, isolated leverage, equity percentage, notional cap, stop, maximum hold, ledger location, and required live acknowledgements.
2. Reject cross margin, non-SOL symbols, leverage above venue metadata, non-mainnet endpoints, non-positive caps, and unknown fields.
3. Encode 3% margin, 5x isolated leverage, $22.50 maximum notional, one position, frozen stop result, and 48-hour maximum hold.
4. Keep `metalabel_mode = "off"`; no model output can gate or resize the canary.
5. Verify parsing and stable profile fingerprint tests.

## Task 5: Add a narrow venue protocol and mocked adapter

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/hypervector/live/hyperliquid_protocol.py`
- Create: `src/hypervector/live/hyperliquid_sol_adapter.py`
- Create: `tests/test_hyperliquid_sol_adapter.py`

1. Verify and lock a compatible official Hyperliquid SDK release; do not infer an unverified version.
2. Define typed responses for metadata, fee schedule, clearinghouse state, open orders, order status, fills, and exchange order acknowledgements.
3. Add mocked failing tests for isolated leverage setup, rounded SOL size, entry submission, actual-fill reconciliation, reduce-only market trigger stop, exact order cancellation, reduce-only close, and flat verification.
4. Implement explicit boundary validation and structured errors; never use `cancel_all` for an open protected position.
5. Query and log current SOL tick/lot/max-leverage metadata and the account fee tier during preflight without logging secrets.
6. Run tests with all network transports mocked.

## Task 6: Implement the fail-closed execution state machine

**Files:**
- Create: `src/hypervector/live/sol_range_onset_state.py`
- Create: `src/hypervector/live/sol_range_onset_engine.py`
- Create: `tests/test_sol_range_onset_live_state.py`
- Create: `tests/test_sol_range_onset_live_engine.py`

1. Add failing state-transition tests for `DISARMED`, `PREFLIGHT`, `FLAT`, `ENTRY_PENDING`, `PROTECTING`, `OPEN`, `EXIT_PENDING`, `FAULTED`, and `STOPPED`.
2. On entry acknowledgement, poll actual fills and clearinghouse position; size the stop from reconciled quantity.
3. On partial fill, protect only the actual position and cancel remaining entry quantity where supported.
4. If stop placement fails while exposure exists, submit an emergency reduce-only close, reconcile flat, and fault.
5. For opposite signal or max hold, cancel the exact protective stop, submit a reduce-only close, verify flat, and only then permit a reversal.
6. Preserve the venue stop during operator shutdown or transport failure while a position remains open.
7. Make an unknown position/order on startup a fail-closed reconciliation fault; do not guess ownership.
8. Verify every transition and failure injection with deterministic mocks.

## Task 7: Add authoritative live telemetry and restart recovery

**Files:**
- Create: `src/hypervector/live/sol_range_onset_ledger.py`
- Create: `src/hypervector/live/sol_range_onset_reconcile.py`
- Create: `tests/test_sol_range_onset_live_ledger.py`
- Create: `tests/test_sol_range_onset_live_reconcile.py`

1. Test append-only records for session start, effective mode, configuration identity, regime decision, theoretical quote, order acknowledgement, fill, stop order, position, fee, funding, liquidation price, close, and fault.
2. Persist venue order IDs/client IDs and exact exchange timestamps.
3. Reconcile local state against clearinghouse state, frontend open orders, order status, and fills before accepting a new signal.
4. Record theoretical-versus-actual latency, price impact, size, fee, and funding deltas for every canary trade.
5. Rotate or checkpoint without resetting prior history by default; fresh-run reset remains an explicit operation.

## Task 8: Make TUI mode inline and backend-authoritative

**Files:**
- Modify: `crates/hypervector-tui/src/main.rs`
- Modify: `crates/hypervector-tui/src/app.rs`
- Modify: `crates/hypervector-tui/src/config_view.rs`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Create: `crates/hypervector-tui/tests/execution_mode_test.rs`

1. Add failing tests for a configurable backend-ledger path and effective-mode telemetry.
2. Render Screen 4 mode as a backend-confirmed value with `DISARMED`, `SHADOW`, or `LIVE ARMED`; never infer live state from a TUI selection alone.
3. Show isolated leverage, notional cap, fee tier, funding, stop order status, venue liquidation price, reconciliation age, and last fault.
4. Keep all TUI controls read-only with respect to exchange execution.
5. Run Cargo unit and integration tests.

## Task 9: Add the one-command supervisor

**Files:**
- Create: `src/hypervector/sol_range_onset_launcher.py`
- Modify: `src/hypervector/cli.py`
- Create: `tests/test_sol_range_onset_launcher.py`
- Modify: `skills/hypervector-cli/SKILL.md`

1. Add failing tests proving shadow launches an execution-incapable backend and the TUI against the same ledger.
2. Add failing tests proving live cannot start without both risk flags and configured credentials.
3. Supervise backend and TUI in one terminal; propagate termination and preserve protective-order semantics.
4. Provide one shadow command and one explicitly armed live command, with live documentation withheld from copy-paste readiness until preflight passes.
5. Test child failure, signal handling, ledger mismatch, and mode mismatch.

## Task 10: Keep Trade Oracle advisory and auditable

**Files:**
- Create: `docs/reviews/2026-07-31-sol-range-onset-trade-oracle-contract.md`

1. Define optional pre-trade, in-trade, and post-trade queries as research annotations.
2. Record prompt, notebook/source identity, timestamp, answer hash, and backend state snapshot.
3. Prohibit oracle output from placing, canceling, resizing, gating, or overriding orders in the canary.
4. Reject stale or unavailable oracle responses without affecting the deterministic execution state machine.

## Task 11: Verify without arming live execution

**Files:**
- Modify: `HANDOFF.md`
- Create: `docs/reviews/2026-07-31-sol-range-onset-live-preflight.md`

1. Run `uv run pytest tests/ -q -m "not network"`.
2. Run `cargo test -p hypervector-tui`.
3. Run `uv run python -m hypervector status`.
4. Run a shadow launcher integration session and verify one backend ledger feeds the TUI.
5. Run a read-only mainnet preflight for metadata, account state, fees, and reconciliation. Missing credentials must fail with an actionable message and no secret output.
6. Confirm no order-submission method was called in tests or preflight.
7. Produce an FMEA covering duplicate entry, partial fill, missing stop, stale state, WebSocket gap, REST timeout, unknown venue position, shutdown while open, and TUI/backend mismatch.

## Task 12: Run the explicitly authorized $150 canary and compare evidence

**Files:**
- Create: `docs/reviews/2026-07-31-sol-range-onset-canary-results.md`

1. Require the human-provided explicit live flags at launch time; funding the account alone does not arm execution.
2. Capture every venue acknowledgement, fill, fee, funding payment, position snapshot, stop state, liquidation price, and close reason.
3. Compare each actual trade against the shadow counterfactual at the same decision timestamp.
4. Report price/size/latency/fee/funding errors and any lifecycle divergence; do not convert four days of backtesting into a claim of live profitability.
5. Treat unexpected duplicate exposure, unprotected exposure, reconciliation mismatch, or capital above the $22.50 notional cap as a technical fault and stop new entries while preserving/closing existing exposure safely.
6. Update confidence only from observed evidence. Queue behavior, venue latency, and real stop execution remain unverified until this task produces actual fills.
