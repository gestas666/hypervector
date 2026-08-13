# Hypervelocity Creator-Calibrated Margin Stop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether a bounded fixed gross-margin stop family can reproduce the creator's observed loss economics and make the faithful Hypervelocity strategy profitable after authentic Hyperliquid costs.

**Architecture:** Keep the exact faithful 1m/5m/15m decisions, maker entry and target, one-position lifecycle, regime-reset re-entry, 70% allocation, 40x isolated leverage, and 8% target. Replay the no-stop control and four predeclared stop distances through one shared, checksum-verified Hyperliquid event tape so every candidate sees identical books, trades, marks, oracle prices, and funding.

**Tech Stack:** Python 3.13, pandas, pytest, verified 0xArchive Hyperliquid L2/trades, authentic Hyperliquid mark/oracle/funding context.

---

## Frozen Evidence Boundary

- Runtime and TUI behavior remain unchanged; every stop is report-only.
- The 90-day April 28-July 27 archive is development evidence because prior
  experiments already inspected all periods. No result is called out-of-sample.
- Faithful configuration SHA-256:
  `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.
- Decisions come directly from `faithful_regime_config()` and
  `classify_multitimeframe()`. No OBI, strength, confidence, 15m, or model gate
  is introduced.
- Initial equity is $10,000 to match the current shadow portfolio.
- The no-stop control and gross margin stops at 6%, 10%, 14%, and 18% are all
  retained regardless of performance.
- Stop execution uses the adverse BBO and taker fee. A mark-price liquidation
  crossing at the same evidence event is handled first, preserving the
  existing conservative gap ordering.
- Open positions otherwise continue through RANGE and target at +8% gross
  margin return.

## Threshold Derivation

The creator aggregate card displays 42 wins and 18 losses, or 70% wins. At
40x, a maker-entry plus maker-target round trip costs approximately 1.2% of
margin, leaving about +6.8% net margin on an 8% gross target. A maker-entry plus
taker-stop costs approximately 2.4% of margin. The arithmetic break-even gross
stop under a 70% win rate is therefore:

`0.70 * 6.8 = 0.30 * (stop + 2.4)`, so `stop ~= 13.47%`.

The less consistent 43W/16L card implies about 15.88%. Tracker-disappearance
mark proxies contain four negative observations near -5.02%, -5.66%, -15.40%,
and -24.13% gross margin. The declared 6/10/14/18 grid brackets the small-loss
pair, the proxy median region, the 70% break-even boundary, and a wider
sensitivity point without fitting an exact threshold to replay outcomes.

### Task 1: Prove shared-tape replay equivalence

**Files:**
- Modify: `src/hypervector/research/maker_replay_stream.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Write a failing test comparing two grid candidates with two independent
   `replay_maker_order_chunks()` calls on the same immutable fixture.
2. Verify failure because `replay_maker_order_grid_chunks()` does not exist.
3. Implement a typed mapping API that validates each evidence chunk once,
   builds one event tape, advances one isolated state per named config, and
   returns one `MakerReplayReport` per candidate.
4. Require at least one candidate and preserve each candidate's own fees,
   stop, liquidation, funding, and equity state.
5. Run the focused replay tests and Ruff.

### Task 2: Define the immutable candidate and summary contract

**Files:**
- Create: `src/hypervector/research/hypervelocity_margin_stop_compare.py`
- Create: `tests/test_hypervelocity_margin_stop_compare.py`

1. Write failing tests for the exact control/6/10/14/18 candidate identities.
2. Write a failing test for the fee-adjusted 70% break-even calculation.
3. Write failing tests for lifecycle status counts, net target rate, average
   target/stop/liquidation PnL, and three chronological 30-day slices.
4. Implement typed dataclasses and pure report summarizers. Preserve missing
   or unresolved evidence explicitly rather than treating it as a win/loss.
5. Include closed-trade geometric growth by slice as a diagnostic, labeled as
   excluding intratrade drawdown; the full replay remains authoritative.

### Task 3: Add a reproducible offline comparison command

**Files:**
- Create: `scripts/hypervelocity_margin_stop_compare.py`
- Modify: `tests/test_hypervelocity_margin_stop_compare.py`

1. Write failing parser and small-fixture report tests.
2. Load the faithful config, strict Hyperliquid bars, verified 90-day bundles,
   authentic price context, and official funding context.
3. Fail fast on config hash mismatch, incomplete archive, invalid bounds, or
   existing output path.
4. Use the shared-tape replay API for all five candidates and write one atomic,
   source-hashed JSON artifact.
5. Stamp `runtime_strategy_changed=false` and the observe-only model contract.

### Task 4: Run the complete authentic 90-day comparison

**Files:**
- Create: `data/logs/research/hypervelocity_creator_margin_stop_grid_20260727.json`
- Modify: this plan with measured results.

1. Replay all five candidates from $10,000 under public trade-through fills.
2. Report submissions, fills, expirations, targets, stops, liquidations,
   partial liquidations, funding, final/realized equity, maximum drawdown,
   average outcome, cadence, and each chronological slice.
3. Compare the replayed win/loss mix with the creator's aggregate 70% card,
   while retaining the card inconsistency and tracker-proxy limitations.
4. Do not select a threshold from final equity alone. A viable historical
   candidate must exceed starting equity after costs, avoid catastrophic
   drawdown, and retain creator-like cadence and target/loss proportions.
5. Even a viable development result remains a shadow-confirmation candidate,
   not an automatic runtime promotion.

### Task 5: Verify and decide

**Files:**
- Modify: `docs/reviews/2026-07-27-creator-screenshot-forward-validation.md`
- Modify: `HANDOFF.md`

1. Run focused tests and Ruff on every new/modified Python file.
2. Run `uv run pytest tests/ -q -m "not network"`.
3. Run `cargo test -p hypervector-tui`, `cargo fmt --check --all`,
   `git diff --check`, and `uv run python -m hypervector status`.
4. Recompute the faithful config hash and confirm no runtime/TUI strategy
   behavior changed.
5. Record confidence, contradictory evidence, failure modes, and the fresh
   creator/shadow evidence that would falsify the conclusion.

## Expected Failure Modes

- A stop can improve arithmetic loss size while re-entry churn destroys
  geometric equity.
- The creator aggregate cards may represent different accounts or filtered
  views; their 70% win rate is not an authoritative sequential ledger.
- Tracker disappearance is not a fill and does not reveal intratrade maximum
  adverse excursion.
- Public trade-through cannot recover private queue position or cancellations.
- A stop-market order can slip beyond displayed BBO in live execution; the
  replay lacks depth-aware stop impact.
- Threshold comparison on an already-inspected archive is selection-biased.

## Execution Note

The active user goal explicitly requests continued testing and tuning, so the
plan is executed immediately in the current worktree. Git commit and push stay
deferred until explicitly requested.

## Measured Result

The complete report is
`data/logs/research/hypervelocity_creator_margin_stop_grid_20260727.json`,
SHA-256
`b0e6c9d584db7ffd631da810cdca7ca656025c07af681a36345843e800884b37`.
It uses faithful configuration SHA-256
`801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`,
2,160 checksum-verified archive bundles, authentic mark/oracle prices, and
official funding event timestamps.

| Candidate | Fills | Targets | Stops | Liquidations | Final equity | Maximum drawdown |
|---|---:|---:|---:|---:|---:|---:|
| No-stop control | 281 | 241 | 0 | 40 | $3.80 | -99.979% |
| 6% margin stop | 394 | 159 | 234 | 1 | $6.06 | -99.943% |
| 10% margin stop | 389 | 204 | 184 | 1 | $4.34 | -99.965% |
| 14% margin stop | 371 | 227 | 143 | 1 | $6.31 | -99.956% |
| 18% margin stop | 362 | 230 | 131 | 1 | $0.47 | -99.997% |

Every candidate lost money in each chronological 30-day slice. Stops reduced
full liquidations but rearmed the strategy sooner, increasing fills and
converting the failure mode into repeated stop/re-entry churn. The 14% result
is numerically least bad by final equity, but it still loses more than 99.9%
and therefore does not satisfy any survival or profitability criterion.

Decision: reject all four fixed stops for runtime promotion and retain the
unchanged faithful shadow configuration. Confidence is high for rejection on
this development window because all thresholds and all three chronological
slices fail decisively. Confidence remains low that fixed stops are absent
from the creator strategy because visible losing creator fills and exit
reasons are still unavailable. Losing-trade exports with authoritative entry,
exit, and reason fields would update that assessment.
