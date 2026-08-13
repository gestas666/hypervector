# Hypervelocity One-Tick Maker Depth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether posting Hypervelocity entries one BTC tick behind the current best passive price improves venue-replayed fill quality without adding a regime or model gate.

**Architecture:** Add a report-only non-negative integer entry-depth field to `MakerReplayConfig`, defaulting to zero. At submission, long entries use best bid minus `ticks * tick_size` and shorts use best ask plus the same amount; target, sizing, TTL, regime cancellation, and all runtime behavior remain unchanged. Expose exactly one one-tick challenger through the existing research script.

**Tech Stack:** Python 3.13, pandas, pytest, checksum-verified Hyperliquid L2/public trades.

---

## Evidence and frozen contract

- The current replay posts at best bid for longs and best ask for shorts.
- The external source records cannot calibrate a Hyperliquid offset: all 21
  trade-backed timestamps had a book no older than one second, but 13 recorded
  maker prices crossed the contemporaneous Hyperliquid passive BBO. This is
  consistent with their documented external-venue origin or tracker-time lag.
- Test exactly one venue-native candidate: one configured BTC tick deeper than
  touch. Do not add an offset grid after observing the result.
- Preserve hard BBWP25, recovery age six, 300-second maker TTL/cooldown,
  regime-reset re-entry, one position, 70% isolated margin, BTC 40x, fixed 8%
  gross margin target, fees, liquidation behavior, and RANGE hold policy.
- Runtime, TUI, and faithful TOML remain unchanged. ML stays observe-only and
  cannot filter or scale.

## Frozen acceptance

- Run one exact $120 April 28–July 27 public-trade-through replay.
- Survival requires final equity above the zero-depth control's $115.40 and
  maximum drawdown better than -97.52%. Profitability requires final equity
  above $120 after modeled costs.
- Report submissions, fills, expirations, targets, liquidations, fill-wait
  distribution, lifecycle overlap, and cadence. Fewer fills are a result, not
  an abort condition.
- A full-window survivor advances to the exact July 9 04:00–July 24 16:00
  source window. It must beat the zero-depth $114.37 final equity and -77.78%
  drawdown without materially worsening source-period cadence to support any
  later promotion discussion.
- Failure at either event stage ends this mechanism. No adjacent tick depth is
  added post hoc.

### Task 1: Add typed replay-only entry depth

**Files:**
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Test: `tests/test_hypervelocity_maker_replay.py`

1. Write a failing config-validation test for negative and non-integer depth.
2. Write failing long and short tests proving one tick changes the submitted
   limit in the passive direction and that the fill records that exact price.
3. Run the focused tests and confirm failures are caused by the absent field.
4. Add `entry_depth_ticks: int = 0` with fail-fast validation.
5. Add one helper that derives the passive entry limit and use it only for new
   submissions. Preserve zero-depth behavior byte-for-byte at the report level.
6. Run the full maker replay tests and Ruff.

### Task 2: Expose the frozen candidate

**Files:**
- Modify: `scripts/hypervelocity_bbwp_precedence.py`
- Test: `tests/test_hypervelocity_bbwp_script.py`

1. Write a failing parser/config test for `--event-entry-depth-ticks 1`.
2. Forward the value into `MakerReplayConfig` and stamp non-zero depth in the
   candidate identity/report.
3. Preserve the zero default and reject invalid values in the config boundary.
4. Run focused script tests and Ruff.

### Task 3: Replay, compare, and decide

**Files:**
- Create: `data/logs/research/hypervelocity_equity120_entry_depth1_20260727.json`
- Create only after survival: `data/logs/research/hypervelocity_source_window_equity120_entry_depth1_20260727.json`
- Modify: this plan

1. Replay all 2,160 verified archive bundles and compare against the frozen
   zero-depth control.
2. Run the exact source-window replay only if both full-window survival
   requirements pass.
3. Record outcome counts, fill waits, lifecycle overlap, final equity,
   drawdown, limitations, confidence, and falsifier.

### Task 4: Verify preservation

1. Run focused tests, changed-file Ruff, full non-network Python tests, and
   `git diff --check`.
2. Verify the faithful config checksum and observe-only fields are unchanged.
3. Do not commit or push unless explicitly requested.

## Measured result and decision

The exact replay verified all 2,160 hourly archive bundles. The one-tick
candidate failed both full-window survival requirements:

| Metric | Zero-depth control | One-tick depth |
|---|---:|---:|
| Submissions | 517 | 514 |
| Fills | 447 | 440 |
| Targets | 406 | 399 |
| Liquidations | 41 | 41 |
| Expirations | 66 | 70 |
| Final equity | $115.40 | $83.92 |
| Maximum drawdown | -97.52% | -97.85% |
| Median entry wait | 11.53 s | 13.37 s |
| Mean entry wait | 36.52 s | 39.64 s |

There were 512 shared signal identities and 506 retained the same terminal
status. Six control targets became expirations. One control liquidation was
displaced to the following minute and remained a liquidation, while other
path substitutions did not reduce total liquidations. The source-window replay
was therefore not authorized.

**Decision:** keep zero-depth maker submission and do not test adjacent depths.
The one-tick improvement to entry price selected fewer fills, removed seven
targets, removed no liquidations, and worsened both equity and drawdown.
Confidence is high for rejecting this exact depth on the measured archive and
medium for future venue windows because private queue position is unavailable.
A fresh shadow window showing repeatable one-tick fills with better realized
target/liquidation odds would update the decision. Runtime configuration and
ML observe policy remain unchanged.
