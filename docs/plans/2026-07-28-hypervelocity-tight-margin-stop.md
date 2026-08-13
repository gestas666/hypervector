# Hypervelocity Tight Margin Stop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test the original reverse-engineering note's untested 2-3% gross-margin stop hypothesis without changing the runtime strategy, regime detector, TUI, target, sizing, or model authority.

**Architecture:** Extend the existing report-only shared-tape stop comparison with one frozen control/2%/3%/4% family. Replay every candidate through the same checksum-verified Hyperliquid books, trades, authentic mark/oracle series, and official funding series; retain all outcomes and chronological slices regardless of performance.

**Tech Stack:** Python 3.13, pandas, pytest, verified 0xArchive Hyperliquid L2/trades, Hyperliquid mark/oracle/funding context.

---

## Frozen evidence contract

- Development window: 2026-04-28T00:00:00Z through 2026-07-27T00:00:00Z.
- Configuration SHA-256: `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.
- Initial equity $10,000; isolated margin allocation 70%; leverage 40x.
- Maker entry, public trade-through fill, 300-second TTL, 60-second cooldown, and regime-reset same-side re-entry remain fixed.
- Fixed +8% gross-margin target remains fixed.
- A stop uses the first adverse BBO after the authentic mark crosses its boundary and charges the taker fee. Liquidation retains priority on the same event.
- RANGE never closes a position. No regime, confidence, strength, orderbook, funding, or ML gate is added.
- The candidate order is exactly no-stop control, 2%, 3%, and 4% gross-margin stop. No adjacent threshold will be added after inspection.
- All 90 days are previously inspected development evidence; no holdout or statistical significance claim is permitted.

## Task 1: Add the exact candidate family with TDD

**Files:**
- Modify: `tests/test_hypervelocity_margin_stop_compare.py`
- Modify: `src/hypervector/research/hypervelocity_margin_stop_compare.py`

1. Add a failing test asserting the exact candidate names, stop values, equity, fill rule, and unchanged re-entry policy.
2. Run the focused test and confirm it fails because the tight family is absent.
3. Add the smallest typed public factory for the frozen family.
4. Run the focused comparison tests and Ruff.

## Task 2: Expose the report-only command family with TDD

**Files:**
- Modify: `tests/test_hypervelocity_margin_stop_script.py`
- Modify: `scripts/hypervelocity_margin_stop_compare.py`

1. Add failing parser, candidate-selection, identity, creator-context, and limitation tests for `tight-margin-stop`.
2. Confirm the failures are caused by the missing family.
3. Wire the family to the existing verified shared-tape replay without changing any runtime path.
4. Identify it as `reverse_engineered_tight_margin_stop_grid_v1` and retain creator scorecard calibration context.
5. Run both focused test files and Ruff.

## Task 3: Run and retain the complete comparison

**Files:**
- Create: `data/logs/research/hypervelocity_tight_margin_stop_20260728.json`
- Modify: `docs/plans/2026-07-28-hypervelocity-tight-margin-stop.md`

1. Run all four candidates over all 2,160 verified hourly bundles.
2. Record fills, targets, stops, liquidations, partial liquidations, final equity, maximum drawdown, fees, funding, lifecycle substitutions, and each 30-day slice.
3. Compare target rate and cadence with both inconsistent creator scorecards without merging them into one ledger.
4. Retain the artifact and hash even if every candidate loses.

## Task 4: Validate the decision boundary

**Files:**
- Modify: `docs/reviews/2026-07-28-source-fidelity-runtime-audit.md`
- Modify: `HANDOFF.md`

1. Run focused tests, Ruff, format checks, file-size checks, and artifact accounting checks.
2. Confirm the faithful config hash is unchanged and the report states `runtime_strategy_changed=false`.
3. If no candidate is profitable, reject this fixed-stop family and do not change runtime.
4. If a candidate is profitable, label it development-only and require a fresh venue-matched shadow confirmation before promotion.
5. Record confidence, failure modes, contradictory evidence, and falsifiers.

## Expected failure modes

- Tight stops may convert liquidation losses into high-frequency stop/re-entry fee churn.
- A 2-4% margin move is only 5-10 basis points in BTC price at 40x and may be dominated by microstructure noise.
- Public BBO understates hidden depth and live stop-market impact.
- The creator note labels the stop as inferred; no authoritative losing fill or reason is available.
- Previously inspected data and multiple prior trials make any apparent winner selection-biased.

## Execution note

The active user goal authorizes continued testing, so this plan is executed immediately in the current shared worktree. No commit, push, runtime promotion, or live execution is authorized by this plan.

## Measured result

The complete report is
`data/logs/research/hypervelocity_tight_margin_stop_20260728.json`, SHA-256
`17a7aaa306a70fa2e9f6a2fc413d787854916e366ec0048f216ec179a315fb9b`.
It retains all 2,160 checksum-verified hourly bundles, 127,814 authentic
mark/oracle observations, 2,160 official funding rows, and configuration
SHA-256
`801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.

| Candidate | Fills | Targets | Stops | Full liq. | Final $10,000 | Max drawdown | Fees | Net funding |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| No-stop control | 281 | 241 | 0 | 40 | $3.8034 | -99.9794% | $5,886.41 | +$11.88 |
| Stop 2% | 407 | 64 | 342 | 1 | $2.1217 | -99.9788% | $6,982.51 | -$8.87 |
| Stop 3% | 404 | 96 | 307 | 1 | $3.2913 | -99.9692% | $7,386.30 | -$18.85 |
| Stop 4% | 393 | 120 | 272 | 1 | $5.3764 | -99.9497% | $8,683.57 | -$26.26 |

The tight candidates reduced full liquidations to one and eliminated partial
liquidations, but target rates collapsed to 15.7%, 23.8%, and 30.5%. Each
candidate lost money in every chronological 30-day slice. Stops also changed
the path broadly: the three candidates introduced 148-159 resolved lifecycles
that the control never entered and converted 140-178 shared eventual targets
into stops.

Decision: reject the 2-4% fixed-margin stop family and retain the no-stop
runtime. Confidence is high for this exact entry path and inspected tape.
Confidence remains low that the creator never uses an unobserved discretionary
exit. A materially more selective creator entry recipe can change stop-path
economics and would require a separately frozen replay rather than another
stop threshold.
