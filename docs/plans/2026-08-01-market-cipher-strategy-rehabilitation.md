# Market Cipher Strategy Rehabilitation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reconstruct the prompt-only MC 15m Scalper and the executable Hulk Smash engine as separate, deterministic research candidates, then evaluate them causally on Hyperliquid data with realistic execution and shared-capital accounting.

**Architecture:** Treat `/Users/gestas/dev/command-center/hands/mc-scalper` and `/Users/gestas/dev/market-cipher-cli` as read-only source evidence. Add pure, typed Market Cipher feature and signal modules to Hypervector, then pass their completed-bar signals into a report-only replay that models next-bar entry, intrabar barriers, fees, slippage, funding, isolated liquidation, partial exits, and one shared portfolio. Keep execution authority absent until a candidate passes chronological validation and a separate explicit live-arm decision.

**Tech Stack:** Python 3.13, pandas, NumPy, DuckDB, pytest, Ruff, existing Hypervector Cipher adapters and shared-portfolio models.

---

## Evidence and constraints

### OG restoration source set

- `/Users/gestas/dev/market-cipher-cli`
- `/Users/gestas/dev/command-center/hands/mc-scalper`
- `https://github.com/gestas666/brain-ecosystem`
- `/Users/gestas/Prototypes/mc-a`
- `/Users/gestas/Prototypes/mc-b`

These are read-only provenance inputs. Their recovered behavior is retained as an
immutable baseline, while repaired or redesigned behavior receives a new candidate
identity inside Hypervector.

- `mc-scalper` is `runtime: prompt_only`; it contains no executable strategy implementation.
- Its intended 15m contract requires WaveTrend cross, RSI+MFI confirmation within three bars, price/VWAP alignment, volume above its 20-bar average, distance from major 4h/1d levels, a minimum score of 7, and 1h opposition veto.
- The spec is ambiguous about the TP1 reduction fraction and uses “Green Dot / Red X” as a synonym for money flow. Those ambiguities must be represented as explicit variants, not silently guessed.
- `market-cipher-cli` currently implements a distinct BTC 30m Hulk Smash formation engine. Its working tree is user-owned and dirty; do not modify it.
- Reproduced legacy result on Binance BTC 30m, 2025-03-31 through 2026-03-31: 663 trades, 39.52% wins, +$11,900 gross on a nominal $10,000 start, and 59.1% reported drawdown.
- That legacy result is not promotion evidence: formation discovery reused the four-year sample, the indicator lookback uses the latest ribbon state for earlier bars, `mfi_series` is populated from RSI, and the simulator omits fees, slippage, funding, liquidation, and intrabar stops.
- Existing Hypervector research code already supplies Pine-fidelity Cipher primitives, causal timeframe alignment, immutable reports, and realistic shared-capital mechanics. Reuse those rather than porting bot or exchange code.

## Task 1: Freeze source identity and legacy reproduction

**Files:**

- Create: `src/hypervector/research/market_cipher_source_contract.py`
- Create: `tests/test_market_cipher_source_contract.py`
- Create: `scripts/market_cipher_legacy_audit.py`
- Test: `tests/test_market_cipher_legacy_audit_script.py`

**Step 1: Write the failing source-contract tests**

Assert that the contract hashes `HAND.toml`, `SKILL.md`, the current `market-cipher-cli` commit, its dirty diff, and the referenced Pine files without importing or executing either external project.

**Step 2: Run the tests and verify failure**

Run: `uv run pytest tests/test_market_cipher_source_contract.py tests/test_market_cipher_legacy_audit_script.py -q`

Expected: FAIL because the contract and script do not exist.

**Step 3: Implement the minimal read-only contract**

Use explicit paths supplied by CLI arguments. Refuse missing files, record SHA-256 identities, include the legacy date range and metrics, and set:

```python
report_only = True
execution_authority = "none"
place_attempted = False
```

**Step 4: Run tests and lint**

Run: `uv run pytest tests/test_market_cipher_source_contract.py tests/test_market_cipher_legacy_audit_script.py -q`

Run: `uv run ruff check src/hypervector/research/market_cipher_source_contract.py scripts/market_cipher_legacy_audit.py tests/test_market_cipher_source_contract.py tests/test_market_cipher_legacy_audit_script.py`

Expected: PASS.

**Step 5: Commit when explicitly requested**

Stage only the four files from this task and use a dedicated commit message.

## Task 2: Add causal Market Cipher component frames

**Files:**

- Create: `src/hypervector/research/market_cipher_components.py`
- Modify: `src/hypervector/research/backtest_lab_cipher_adapter.py`
- Create: `tests/test_market_cipher_components.py`
- Modify: `tests/test_backtest_lab_cipher_adapter.py`

**Step 1: Write failing golden-vector tests**

Cover:

- WaveTrend 9/12/3 cross pulses with no future bars.
- RSI+MFI area using `sma(((close-open)/(high-low))*150, 60) - 2.5`.
- Rolling price VWAP as a separate field from Cipher B's `wt1-wt2` oscillator.
- 20-bar volume ratio.
- Stoch RSI 14/14/3/3.
- EMA 11/34 trend and slope.
- Recalculation at each historical row so an earlier row is unchanged when later bars are appended.

**Step 2: Verify tests fail**

Run: `uv run pytest tests/test_market_cipher_components.py tests/test_backtest_lab_cipher_adapter.py -q`

Expected: FAIL for missing public component frame and append-invariance behavior.

**Step 3: Implement the pure component frame**

Return a timezone-indexed DataFrame with finite/unknown state kept explicit. Do not convert missing warmup values into neutral confluence. Keep each public function fully typed and below 50 lines.

**Step 4: Verify append invariance and Pine identity**

Run the Task 2 tests twice: once on a fixed fixture and once after appending future rows. Values at the original decision timestamps must remain byte-identical.

**Step 5: Lint and commit when explicitly requested**

Run Ruff on only the touched files, then stage only Task 2 files.

## Task 3: Reconstruct two separate signal families

**Files:**

- Create: `src/hypervector/research/market_cipher_scalper_signals.py`
- Create: `src/hypervector/research/hulk_smash_signals.py`
- Create: `tests/test_market_cipher_scalper_signals.py`
- Create: `tests/test_hulk_smash_signals.py`

**Step 1: Write failing tests for the MC 15m Scalper**

Required entry state:

```python
core_ready = (
    wave_cross == direction
    and money_flow_confirmed_within_3_bars
    and price_vwap_aligned
    and volume_ratio > 1.0
    and not near_major_htf_level
)
score = 3 + 2 + 1 + volume_bonus + htf_bonus + stoch_bonus
entry = core_ready and score >= 7 and not opposite_1h_trend
```

Test that money flow sign is not replaced with Green Dot/Red X, volume above 1.0 is required while 1.5 adds a point, and an opposite completed 1h trend vetoes the signal.

**Step 2: Write failing tests for Hulk Smash**

Encode the current formation sets as named, immutable candidates. Correct the known RSI-for-MFI defect and ensure fingerprints use only component values available at that bar. Keep the uncommitted quality-threshold 3 and committed threshold 4 as separate trial identities.

**Step 3: Run tests and verify failure**

Run: `uv run pytest tests/test_market_cipher_scalper_signals.py tests/test_hulk_smash_signals.py -q`

Expected: FAIL for missing modules.

**Step 4: Implement signal construction**

Emit rows containing candidate, decision time, side, component booleans, score, stop anchor, and reason. Do not expose execution functions or silently discard signals for performance reasons.

**Step 5: Run tests, lint, and commit when explicitly requested**

The test set must include both long and short fixtures, warmup insufficiency, gaps, conflicting signals, and append-invariance.

## Task 4: Implement staged exits and realistic portfolio replay

**Files:**

- Create: `src/hypervector/research/market_cipher_replay_models.py`
- Create: `src/hypervector/research/market_cipher_replay.py`
- Create: `src/hypervector/research/market_cipher_replay_reporting.py`
- Create: `tests/test_market_cipher_replay.py`

**Step 1: Write failing lifecycle tests**

Cover next-bar adverse entry, wick stop clipped to 20–50 bps, liquidation-before-stop-before-target ordering, gaps through stops, maker/taker fees, adverse slippage, hourly funding, and one position per symbol.

**Step 2: Define the TP1 ambiguity as bounded variants**

Pre-register:

- `all_at_2r_control`: no partials, full close at 2R.
- `staged_25_50_trail`: close 25% at 1R, close 50% of remaining size at 2R, trail the remainder on an opposite completed 15m WaveTrend cross.

Both variants use a 12-bar time stop. No other fractions may be selected after seeing validation results.

**Step 3: Implement shared-capital mechanics**

Use one portfolio, isolated leverage, at most one position per coin, at most three concurrent positions, and total configured risk no greater than 2% of current equity. Deterministically rank simultaneous candidates by score, then symbol, and report every conflict or capacity rejection.

**Step 4: Verify accounting identity**

For every run assert:

```python
ending_equity == starting_equity + gross_pnl - fees + funding - liquidation_penalties
```

Also reconcile partial quantities exactly to zero at final close.

**Step 5: Run tests, lint, and commit when explicitly requested**

Run: `uv run pytest tests/test_market_cipher_replay.py -q`

Expected: PASS with critical accounting and liquidation paths fully covered.

## Task 4A: Rebuild Hulk Smash and Trading Brain challengers

**Baseline rule:** The recovered Hulk formations and legacy synapse behavior are
diagnostic controls, not protected production designs.

**Core identity rule:** Hulk Smash remains the directional strategy's central
signal-fusion identity. The implementation is free to replace its indicators,
formations, thresholds, timeframe, exits, sizing, learning, and tuning mechanics.
What remains invariant is that independent causal evidence combines into named,
auditable Hulk setup archetypes rather than one opaque model prediction.

**Hulk challenger work:**

- Replace exact formation lookup with causal component-level scoring and explicit
  long/short calibrations.
- Separate trend continuation, exhaustion reversal, and volatility expansion so
  contradictory evidence cannot collapse into one opaque fingerprint.
- Learn thresholds only on development windows; freeze them before forward use.
- Compare every rebuilt candidate against the immutable recovered baseline.

**Brain challenger work:**

- Use hierarchical similarity pooling instead of one exact fingerprint bucket.
- Decay stale evidence toward neutral, not toward automatic rejection.
- Weight outcomes by bounded net-return magnitude after friction, not only win/loss.
- Require explicit sample support and Wilson uncertainty telemetry.
- Remain annotation-only until chronological ablation shows incremental value over
  the deterministic signal without the brain.

**AutoResearch / AutoTune work:**

- Preserve the legacy test-record-keep/revert loop and complete trial journal.
- Replace its full-sample formation mining and contaminated evaluator with nested
  chronological development folds and one untouched forward window.
- Tune coherent parameter families, not one giant unrestricted search surface.
- Include deterministic-only, statistical/ML annotation, repaired-brain
  annotation, and combined annotation as separate ablation arms.
- Retain negative and sparse trials in DuckDB; no performance outcome aborts a
  trial or disappears from the comparison.

**Success criterion:** A rebuilt candidate must improve forward net profit factor
or drawdown at equal signals and friction. A result that disappears under a
one-bar delay or modest cost perturbation falsifies the improvement claim.

## Task 5: Add an immutable research command

**Files:**

- Create: `scripts/market_cipher_strategy_screen.py`
- Create: `tests/test_market_cipher_strategy_screen_script.py`

**Step 1: Write failing CLI contract tests**

Require explicit database, source roots, symbol set, start/end timestamps, segment identity, and output path. Reject existing output. Do not include wallet, live, private key, or order placement flags.

**Step 2: Implement the report-only command**

The artifact must include source hashes, data hashes, exact parameters, friction, funding coverage, missing-data counts, trades, profit factor, drawdown, liquidation count, long/short split, monthly returns, and all rejected signals.

**Step 3: Verify no execution authority**

Run: `uv run pytest tests/test_market_cipher_strategy_screen_script.py -q`

Assert `execution_authority == "none"` and `place_attempted is False`.

**Step 4: Run lint and commit when explicitly requested**

Stage only the script and its test.

## Task 6: Run chronological experiments

**Files:**

- Create: immutable artifacts under `data/logs/research/`
- Update: `docs/reviews/2026-08-01-market-cipher-strategy-rehabilitation.md`

**Step 1: Audit available Hyperliquid coverage**

Record exact date ranges, gaps, bar counts, trade counts, funding coverage, mark coverage, and source hashes before defining splits.

**Step 2: Freeze development candidates**

Evaluate the exact MC 15m Scalper, the corrected Hulk Smash formations, quality threshold 3 versus 4, long/short separation, and the two staged-exit variants. Report all cells; do not abort sparse or losing trials.

**Step 3: Freeze one or more challengers before validation**

Selection may use development evidence only. Minimum evidence is not an execution gate; low counts lower confidence and remain reported.

**Step 4: Run forward chronological validation once**

Do not retune on validation. Compare against do-nothing, prior Cipher cells, and the current Apex cohort using the same capital and friction assumptions.

**Step 5: Run robustness checks**

Perturb fees, slippage, signal delay, stop distance, and funding. Report the break-even friction and the first parameter perturbation that reverses the conclusion.

## Task 7: Add TUI telemetry only for a selected shadow/live candidate

**Files:**

- Modify only after research selection: `rust/hypervector-tui/`
- Add corresponding Rust tests.

**Step 1: Define backend telemetry fields**

Show strategy identity, symbol/timeframe, signal components, score, 1h context, VWAP/volume/HTF-level state, open risk, stop/targets, fees, funding, liquidation price, and last decision reason.

**Step 2: Keep the TUI read-only**

The TUI consumes the authoritative backend ledger and performs no signal generation, simulation, or order placement.

**Step 3: Verify truthful unavailable states**

Missing backend telemetry must display as unavailable, not be synthesized locally.

## Task 8: Canary only after explicit arm authorization

**Files:**

- Create a dedicated backend live adapter and tests only if a candidate is selected.

**Step 1: Shadow parity run**

Require exact decision parity between replay and shadow for identical completed bars.

**Step 2: Live preflight**

Verify mainnet identity, isolated leverage limits, quantity rounding, available collateral, zero unintended positions/orders, and recovery after restart.

**Step 3: Arm only with explicit flags**

Require both `--enabled` and `--i-accept-live-risk`. Start at the user-approved canary notional and journal every intent, acknowledgement, fill, fee, funding settlement, markout, and reconciliation.

**Step 4: Falsification criteria**

Suspend promotion—not research—if order identity cannot reconcile, stops are absent, accounting does not balance, TUI differs from backend, or observed execution friction materially exceeds the validated robustness envelope.
