# Hypervelocity Live Canary Operations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the verified Hypervelocity execution foundation to NautilusTrader's Hyperliquid adapter, validate isolated 40x venue state, run a mirrored $120 mainnet canary, and produce evidence that calibrates shadow execution without changing strategy rules.

**Architecture:** This plan consumes the typed execution contract, event archive, simulated venue, isolated-margin model, and shared coordinator built in [Hypervelocity Nautilus Execution Fidelity and Live Canary Implementation Plan](2026-07-26-hypervelocity-nautilus-live-canary.md). A dedicated fail-closed Hypervelocity runner translates coordinator commands through Nautilus, reconciles every venue order/fill/account event into the backend ledger, and projects those facts to the read-only TUI.

**Tech Stack:** Python 3.13, NautilusTrader 1.230.0 Hyperliquid adapter, Hyperliquid mainnet, pytest, Rust/Ratatui 0.29, TOML.

---

## Preconditions and fixed constraints

- Complete and verify Tasks 1-8 in the foundation plan first.
- BTC must be configured as isolated 40x through Hyperliquid before the runner is armed; Nautilus reports but does not set leverage.
- The canary uses approximately $120 of explicitly expendable build capital.
- Strategy behavior remains one position, 70% margin, 8% gross margin target,
  post-only entry/target, range hold, one-bar minimum cooldown, durable
  same-direction regime-reset re-arm, and observe-only metalabeling.
- The TUI remains display-only.
- Technical state mismatches may refuse submission; performance, drawdown, trade count, and model probability remain reported evidence.
- Tests use mocks and sanitized fixtures; no test performs a network call.
- Execute in a dedicated worktree without stopping or resetting the active shadow session.

### Task 9: Implement the Nautilus Hyperliquid live execution port

**Files:**
- Create: `src/hypervector/execution/nautilus_hyperliquid.py`
- Create: `tests/test_nautilus_hyperliquid_port.py`
- Modify: `src/hypervector/execution/__init__.py`

**Step 1: Write mocked adapter tests**

Test ALO entry, reduce-only target, post-only rejection, partial fills, client/venue order IDs, cancel/replace, external orders, reconnect reconciliation, liquidation fill, ADL notification, and commission propagation.

**Step 2: Verify tests fail without constructing network clients**

Run `uv run pytest tests/test_nautilus_hyperliquid_port.py -q`.

**Step 3: Wrap Nautilus's live factories and event stream**

Translate `OrderCommand` into Nautilus orders and Nautilus order/fill/account events into `VenueOrderEvent` and `AccountSnapshot`. Preserve exchange-reported fill quantity, price, liquidity side, commission, and timestamps.

**Step 4: Test reconciliation idempotence**

Replay duplicate WebSocket and REST reconciliation events and prove position, cumulative fill, and fees change once.

**Step 5: Commit**

```bash
git add src/hypervector/execution tests/test_nautilus_hyperliquid_port.py
git commit -m "feat: add nautilus hyperliquid execution port"
```

### Task 10: Add isolated-margin and account-specific live preflight

**Files:**
- Create: `src/hypervector/live/hypervelocity_preflight.py`
- Create: `tests/test_hypervelocity_live_preflight.py`
- Modify: `src/hypervector/strategies/hypervelocity_profile.py`

**Step 1: Write failing preflight tests**

Mock account snapshots for isolated 40x, cross 40x, isolated wrong leverage, wrong symbol precision, insufficient venue metadata, stale account state, and account-specific fee rates.

**Step 2: Verify tests fail**

Run `uv run pytest tests/test_hypervelocity_live_preflight.py -q`.

**Step 3: Implement technical validation**

Require the venue to report BTC isolated 40x before the first live command. Load actual maker/taker rates from account telemetry and report deviations from base tier. This check validates configuration and data freshness only; it must not reject based on PnL, drawdown, regime confidence, or model probability.

**Step 4: Verify secret-safe errors**

Assert errors include expected/actual margin mode and leverage but never wallet or key values.

**Step 5: Commit**

```bash
git add src/hypervector/live/hypervelocity_preflight.py src/hypervector/strategies/hypervelocity_profile.py tests/test_hypervelocity_live_preflight.py
git commit -m "feat: validate isolated hypervelocity venue state"
```

### Task 11: Build a dedicated fail-closed Hypervelocity live runner

**Files:**
- Create: `src/hypervector/live/hypervelocity_runner.py`
- Create: `tests/test_hypervelocity_live_runner.py`
- Modify: `src/hypervector/cli.py`
- Modify: `src/hypervector/runtime_lock.py`

**Step 1: Add failing CLI and lifecycle tests**

Add `hypervelocity-live-check` and `hypervelocity-live-run`. Require the faithful config, `--enabled`, `--i-accept-live-risk`, configured secrets, isolated preflight, and the singleton data-root lock. Assert check mode never constructs an execution client.

**Step 2: Verify tests fail because commands do not exist**

Run `uv run pytest tests/test_hypervelocity_live_runner.py tests/test_cli_status.py -q`.

**Step 3: Implement the runner**

Use the shared coordinator and Nautilus execution port. Warm-up may classify history but cannot submit. After entry fills, submit/maintain a reduce-only ALO target for exactly the filled quantity. Freeze new entries on technical data/reconciliation failure while leaving a confirmed exchange target intact.

**Step 4: Add durable reconciliation**

On restart, query open orders, fills, position, fees, funding, and liquidation events before generating a new command. Refuse state fabrication when venue and ledger disagree.

**Step 5: Commit**

```bash
git add src/hypervector/live/hypervelocity_runner.py src/hypervector/cli.py src/hypervector/runtime_lock.py tests/test_hypervelocity_live_runner.py tests/test_cli_status.py
git commit -m "feat: add reconciled hypervelocity live runner"
```

### Task 12: Persist one normalized execution ledger and mirror shadow predictions

**Files:**
- Create: `src/hypervector/execution/ledger.py`
- Create: `src/hypervector/execution/mirror.py`
- Create: `tests/test_execution_mirror.py`
- Modify: `src/hypervector/live/hypervelocity_runner.py`
- Modify: `src/hypervector/paper/session.py`

**Step 1: Write append/idempotence tests**

Use separate `actual` and `counterfactual_shadow` event namespaces under the same run ID. Test duplicate fills, partial fills, fee/funding rows, and process restart.

**Step 2: Verify tests fail**

Run `uv run pytest tests/test_execution_mirror.py -q`.

**Step 3: Implement the mirror**

One backend regime decision creates one command identity. The actual lane consumes Hyperliquid events; the shadow lane consumes the same command and public market tape without placing. Never allow the shadow lane to generate a second strategy decision.

**Step 4: Verify no double execution**

Assert one command ID, one live submission, and any number of independently labeled predicted/actual execution events.

**Step 5: Commit**

```bash
git add src/hypervector/execution src/hypervector/live/hypervelocity_runner.py src/hypervector/paper/session.py tests/test_execution_mirror.py
git commit -m "feat: mirror hypervelocity shadow and live execution"
```

### Task 13: Project actual execution and margin telemetry into the TUI

**Files:**
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/src/model.rs`
- Modify: `crates/hypervector-tui/src/ui/mod.rs`
- Modify: `crates/hypervector-tui/src/config_view.rs`
- Modify: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

**Step 1: Write Rust projection tests**

Cover isolated/cross mode, initial and maintenance margin, liquidation price/distance, submitted/accepted/rejected/partial/filled/canceled order states, maker/taker, actual fee, target resting status, reconciliation state, and shadow/live divergence.

**Step 2: Verify tests fail**

Run `cargo test -p hypervector-tui`.

**Step 3: Render backend facts only**

Add execution and isolated-margin fields to the dashboard/configuration screens. Do not calculate liquidation, infer fills, or construct orders in Rust.

**Step 4: Run visual-size tests**

Verify 80x24 degrades explicitly and 120x32 shows all critical canary telemetry without overlapping existing journal columns.

**Step 5: Commit**

```bash
git add crates/hypervector-tui
git commit -m "feat: display live execution reconciliation"
```

### Task 14: Build the canary comparison report

**Files:**
- Create: `src/hypervector/research/canary_compare.py`
- Create: `tests/test_canary_compare.py`
- Modify: `src/hypervector/cli.py`

**Step 1: Write report tests**

Measure decision-to-submit, submit-to-ack, ack-to-first-fill, fill fraction, reject/cancel rates, predicted-versus-actual maker fill precision/recall, fee/funding error, target resting coverage, restart reconciliation, and 1s/5s/30s/60s post-fill markout.

**Step 2: Verify tests fail**

Run `uv run pytest tests/test_canary_compare.py -q`.

**Step 3: Implement `hypervelocity-canary-report`**

Require an explicit run ID and overlapping actual/shadow evidence. Report missing evidence and uncertainty; never convert metrics into an implicit promotion decision.

**Step 4: Verify JSON and human-readable output**

Assert all denominators, timestamps, and source paths are included and no secrets appear.

**Step 5: Commit**

```bash
git add src/hypervector/research/canary_compare.py src/hypervector/cli.py tests/test_canary_compare.py
git commit -m "feat: report hypervelocity canary execution parity"
```

### Task 15: Exercise failure and recovery scenarios

**Files:**
- Create: `tests/test_hypervelocity_live_chaos.py`
- Create: `tests/fixtures/hypervelocity_execution_events.jsonl`
- Modify production files only when a failing scenario exposes a defect.

**Step 1: Add recorded-event chaos cases**

Test WebSocket disconnect, REST timeout, ALO rejection, partial entry, partial target, cancel/replace race, duplicate fill, fill while process is down, external manual order, stale account snapshot, incorrect margin mode, fee-tier change, hourly funding, liquidation, and ADL.

**Step 2: Run each case and verify explicit state**

No broad catch or success-shaped fallback is allowed. Each scenario must end reconciled or in a named technical error state.

**Step 3: Verify target behavior under backend failure**

A confirmed exchange target remains resting; the backend creates no new entry while reconciliation is stale. Range remains non-exiting and does not alter this rule.

**Step 4: Run the failure suite repeatedly**

```bash
uv run pytest tests/test_hypervelocity_live_chaos.py -q --count=5
```

If `pytest-repeat` is unavailable, run the command five times from the shell without adding a dependency solely for this step.

**Step 5: Commit**

```bash
git add tests/test_hypervelocity_live_chaos.py tests/fixtures/hypervelocity_execution_events.jsonl src/hypervector
git commit -m "test: harden hypervelocity live recovery"
```

### Task 16: Write and dry-run the $120 isolated canary runbook

**Files:**
- Create: `docs/guides/hypervelocity-live-canary.md`
- Modify: `HANDOFF.md`
- Test: `tests/test_hypervelocity_live_runner.py`

**Step 1: Document operator preparation**

Include: dedicated wallet/subaccount, approximately $120 deposited, BTC isolated 40x configured through Hyperliquid UI/API, no unrelated orders/positions, secrets present but never printed, faithful config, and resolved data root.

**Step 2: Document preflight and launch commands**

Use placeholders for secrets and require `hypervelocity-live-check` before the explicitly armed runner. Document one-command backend/TUI supervision only after the live backend writes a fresh reconciled session row.

**Step 3: Document stop and recovery**

Explain cancel-all behavior, how to confirm the reduce-only target, how to restart and reconcile, and how to preserve the ledger/event archive before any reset.

**Step 4: Execute a no-submit rehearsal**

Use mocks/recorded fixtures to run the complete operator sequence. Expected: all preflight, telemetry, and report artifacts appear; zero venue submissions occur.

**Step 5: Commit**

```bash
git add docs/guides/hypervelocity-live-canary.md HANDOFF.md tests/test_hypervelocity_live_runner.py
git commit -m "docs: add hypervelocity live canary runbook"
```

### Task 17: Rebuild the Hypervelocity metalabel dataset and runtime feature contract

**Files:**
- Create: `src/hypervector/ml/hypervelocity_dataset.py`
- Create: `src/hypervector/ml/hypervelocity_features.py`
- Create: `tests/test_hypervelocity_ml_dataset.py`
- Modify: `src/hypervector/ml/train_bundle.py`
- Modify: `src/hypervector/ml/features.py`
- Modify: `src/hypervector/ml/replay_models.py`
- Modify: `src/hypervector/paper/conviction.py`
- Modify: `src/hypervector/cli.py`
- Modify: `configs/hypervelocity_faithful.toml`
- Modify: `tests/test_ml_walk_forward.py`
- Modify: `tests/test_paper_conviction.py`

**Step 1: Write failing causal-schema and label-contract tests**

Prove the current defect explicitly: a bundle whose metadata claims an L2 runtime
lane must be rejected when its feature schema contains only the legacy 17
OHLCV/indicator/time fields. Require every new training row to carry the exact
decision-time 1m state, canonical 5m regime, 15m context, breakout direction,
entry direction, L2 availability timestamp, and eventual outcome provenance.

Assert that regime labels are decision-time features and lane selectors, not the
prediction target. The binary target is the closed trade's net result after
fees, funding, slippage, and actual Hypervelocity lifecycle handling. Exclude
still-open/unresolved observations as censored instead of silently treating them
as losses. Reject any row whose bar, regime, or L2 availability timestamp is
later than its entry decision timestamp.

**Step 2: Verify the tests expose the current contract mismatch**

Run:

```bash
uv run pytest tests/test_hypervelocity_ml_dataset.py tests/test_ml_walk_forward.py tests/test_paper_conviction.py -q
```

Expected: new tests fail because the current `l2-runtime` candidates contain no
L2 or explicit regime features and the generic trainer hard-codes
`FEATURE_NAMES`.

**Step 3: Build one versioned point-in-time feature contract**

Create `hypervelocity_features_v2` containing:

- the existing causal 1m technical fields;
- deterministic one-hot fields for 1m state, canonical 5m regime, 15m context,
  and breakout direction;
- entry direction;
- spread, OBI at configured depths, depth ratio, microprice displacement,
  book pressure, depth, aggressor ratio, cancel rate, feature age, and declared
  stream-gap/freshness state.

Use the same typed builder for offline dataset construction and backend
inference. Persist `feature_schema_version`, ordered feature names, source event
IDs, source timestamps, strategy/config fingerprint, label definition, and cost
definition in every candidate's metadata. Do not label a bundle `l2-runtime`
unless the ordered runtime schema includes and successfully resolves the L2
fields.

**Step 4: Train directional candidates on strategy-eligible decisions**

Build long samples only from `TREND_UP` or upward-confirmed `BREAKOUT` decisions
and short samples only from `TREND_DOWN` or downward-confirmed `BREAKOUT`
decisions. Preserve the regime fields inside each row so the model can learn
differences within a directional lane. Train LightGBM, regularized temporal
logistic, and lagged-logistic candidates over identical chronological
walk-forward folds with outcome purging. Report sample count, effective class
balance, fold log loss, Brier score, AUC where defined, calibration, baseline
comparison, and temporal stability without turning any result into a hidden
trial-abort or strategy gate.

**Step 5: Verify replay/runtime parity and install only as observe-only candidates**

Replay stored entry decisions through the online builder and assert exact
ordered feature equality plus probability equality with offline inference.
Update the faithful profile to reference immutable long and short v2 candidates
only after schema loading and replay/runtime parity pass. Keep
`metalabel_mode = "observe"`, `may_filter = false`, and `may_scale = false`
regardless of model score. Record weak or negative evidence honestly rather
than fabricating a promotion threshold.

Run:

```bash
uv run pytest tests/test_hypervelocity_ml_dataset.py tests/test_ml_walk_forward.py tests/test_paper_conviction.py tests/test_paper_session.py -q
uv run python -m hypervector hypervelocity-metalabel-train --config configs/hypervelocity_faithful.toml --annotation-only
```

Expected: tests pass; candidate metadata contains the v2 regime and L2 schema;
the command reports chronological evidence; shadow decisions and sizing are
unchanged while model probability, bundle ID, and schema version are ledgered.

**Step 6: Commit**

```bash
git add src/hypervector/ml src/hypervector/paper/conviction.py src/hypervector/cli.py configs/hypervelocity_faithful.toml tests/test_hypervelocity_ml_dataset.py tests/test_ml_walk_forward.py tests/test_paper_conviction.py
git commit -m "fix: align hypervelocity metalabel features and labels"
```

### Task 18: Final verification and implementation audit

**Files:**
- Modify only documentation or defects found by verification.

**Step 1: Run focused execution suites**

```bash
uv run pytest tests/test_execution_contract.py tests/test_hl_events.py tests/test_nautilus_hl_catalog.py tests/test_nautilus_hypervelocity_sim.py tests/test_hyperliquid_margin.py tests/test_hypervelocity_runtime.py tests/test_nautilus_hyperliquid_port.py tests/test_hypervelocity_live_preflight.py tests/test_hypervelocity_live_runner.py tests/test_execution_mirror.py tests/test_canary_compare.py tests/test_hypervelocity_live_chaos.py tests/test_hypervelocity_ml_dataset.py tests/test_ml_walk_forward.py -q
```

Expected: all pass with network mocked.

**Step 2: Run project verification**

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run python -m hypervector status
```

Expected: green, aside from any explicitly documented pre-existing failure reproduced before this plan.

**Step 3: Run static and secret checks**

Run targeted Ruff, Rust formatting/build, and repository secret scanning. Inspect produced ledgers to confirm wallet/key values are absent.

**Step 4: Review requirements traceability**

Map every fixed behavior and gap at the top of this plan to at least one automated test and one telemetry field. Record unresolved queue uncertainty explicitly.

**Step 5: Commit final documentation**

```bash
git add HANDOFF.md docs/guides/hypervelocity-live-canary.md
git commit -m "docs: record hypervelocity canary readiness"
```

## Canary evidence interpretation

The $120 run is an execution experiment, not a profitability gate. A losing trade, missed maker fill, partial fill, ALO rejection, or liquidation is still useful if the actual order/account lifecycle is captured completely and the backend reconciles correctly.

Evidence that would update the simulator:

- Frequent live misses after simulated one-tick-through evidence: strengthen queue-ahead assumptions.
- Frequent full fills where conservative replay predicts misses: reduce the queue penalty.
- Partial target fills: preserve pro-rata targets and calibrate resting-liquidity consumption.
- Material fee differences: replace configured base fees with account-reported values.
- Funding discrepancies: reconcile against account funding history rather than the latest public estimate.
- Isolated liquidation mismatch: correct venue-specific mark/maintenance calculations before relying on simulated liquidation telemetry.

## Deferred but connected work

- The native Ratatui chart becomes Screen 3 and moves Config to Screen 4 after event/candle telemetry is stable. It must consume backend OHLCV/event projections and never open its own Hyperliquid connection.
- Metalabel authority beyond observation remains deferred until the v2 venue-matched
  candidates demonstrate incremental walk-forward edge; Task 17 fixes the data,
  feature, and runtime-parity contracts without granting filtering or sizing authority.
- Additional range strategies remain separate strategy IDs; they must not change Hypervelocity's no-range-entry contract.

## Rollback

- Each task is independently revertible by its commit without deleting append-only market, shadow, or live evidence.
- If the Nautilus live spike cannot expose required ALO/reduce-only/reconciliation events, retain Tasks 1-8 and implement the same typed `ExecutionPort` over a custom Hyperliquid client. Do not re-enable the market-IOC Hypervelocity route.
- A failed canary does not trigger a data reset. Preserve the complete run, cancel/reconcile venue orders, document the failure, and update the simulator from the evidence.
