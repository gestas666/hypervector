# Hypervelocity Capacity Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether the planned $120 live-canary capital produces materially different Hyperliquid maker execution and profitability from the $10,000 shadow/research control.

**Architecture:** Expose initial equity only in the report-only BBWP replay command and forward it to the existing `MakerReplayConfig`. Keep all strategy, regime, risk-fraction, leverage, target, fee, liquidation, cooldown, and TTL rules fixed; run the single user-grounded $120 challenger on the full archive and source window.

**Tech Stack:** Python 3.13, argparse, pytest, chunked checksum-verified 0xArchive public L2/trade replay.

---

## Frozen Evidence and Contract

- The $10,000 control allocates $7,000 isolated margin and approximately
  $280,000 notional per entry.
- Normal source rows imply roughly $31–$78 account equity from their reported
  margin under the confirmed 70% allocation, with approximately $876–$2,178
  notional. Split rows must be aggregated; two deliberately tiny later rows
  are not treated as normal sizing evidence.
- The explicitly planned $120 live canary allocates $84 margin and $3,360
  notional. This is much closer to source capacity than $10,000, without
  changing the 70%/40x strategy contract.
- Test exactly `$120`; do not add a post-result capital grid.
- Base decisions remain hard BBWP25 plus 1m recovery age 6. Entry TTL and
  post-exit cooldown remain 300 seconds; target remains 8% gross margin return.
- Runtime/shadow initial capital remains $10,000. This experiment cannot mutate
  backend configuration or promote live execution.
- Metalabel remains observe-only and cannot filter or scale.

### Task 1: Expose and test report-only initial equity

**Files:**
- Modify: `scripts/hypervelocity_bbwp_precedence.py`
- Modify: `tests/test_hypervelocity_bbwp_script.py`

1. Write a failing test that parses `--event-initial-equity 120` and proves the
   resulting maker-replay config receives `120.0`.
2. Confirm the test fails because the argument is absent.
3. Add a `10_000.0` default, forward the value through the existing typed
   replay-config helper, and let `MakerReplayConfig` reject non-positive input.
4. Stamp non-default capital in candidate identity and report metadata.
5. Run focused tests and Ruff.

### Task 2: Run the complete 90-day capacity replay

**Files:**
- Create: `data/logs/research/hypervelocity_bbwp_recovery6_equity120_20260727.json`

1. Replay April 28–July 27 with all 2,160 checksum-verified bundle pairs.
2. Compare fills, expirations, targets, full/partial liquidations, final return,
   drawdown, and path overlap with the $10,000 control.
3. Profit requires final return above 0% after modeled costs; report dollars and
   percentage so capital scale cannot make a smaller dollar loss look better.

### Task 3: Run the source-window capacity replay

**Files:**
- Create: `data/logs/research/hypervelocity_source_window_equity120_20260727.json`

1. Replay the 372 containing hourly bundles from July 9 04:00 through July 24
   16:00 UTC.
2. Compare direction/timing, cadence, fills, return, and drawdown with both the
   source log and the $10,000 same-window result.
3. State clearly whether capacity improves profitability, behavioral alignment,
   both, or neither.

### Task 4: Record the decision

1. Retain both valid results even if they lose.
2. Do not change the $10,000 shadow portfolio from a research result.
3. A positive $120 result remains a canary-scale edge hypothesis requiring
   fresh shadow/live-canary validation; it is not evidence that $10,000 has the
   same capacity.

## Verification

```bash
uv run pytest tests/test_hypervelocity_bbwp_script.py \
  tests/test_hypervelocity_bbwp_precedence.py -q
uv run ruff check scripts/hypervelocity_bbwp_precedence.py \
  tests/test_hypervelocity_bbwp_script.py
```

Confidence is medium that capital changes public-trade-through fill paths and
low that it will produce a robust edge. Identical percentage outcomes or a
still-negative 90-day return would falsify capacity as the missing mechanism.

## Measured Result

Both $120 runs verified every required archive bundle. Capital scale changed
the fill path materially, but did not produce a profitable and source-aligned
edge.

| Window/capital | Fills | Targets | Full liq. | Partial liq. | Return | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| 90d / $10,000 | 407 | 368 | 39 | 24 | -58.77% | -94.38% |
| 90d / $120 | 447 | 406 | 41 | 0 | -3.83% | -97.52% |
| Source / $10,000 | 57 | 52 | 5 | 5 | +8.47% | -60.94% |
| Source / $120 | 65 | 59 | 6 | 0 | -4.69% | -77.78% |

The $120 90-day path shared 371 resolved signal/direction identities with the
$10,000 control. It removed 36 resolved control outcomes and introduced 76
different outcomes. Smaller quantity reduced expirations from 114 to 66 and
increased fills, but the 41 full liquidations still offset 406 targets. The
absence of partial liquidations below the modeled $100,000 notional threshold
made the drawdown path worse even though final return improved.

Source timing did not improve: the $120 source replay matched 0/35 entries
within five minutes, 2/35 within ten minutes, and 4/35 within thirty minutes,
while producing 65 fills versus 35 logical source positions. It ended below
its $120 start whereas the $10,000 source-window path was positive.

Artifacts:

- `data/logs/research/hypervelocity_bbwp_recovery6_equity120_20260727.json`
- `data/logs/research/hypervelocity_source_window_equity120_20260727.json`

## Decision

Capacity is a real execution variable and $120 is the least-negative complete
90-day return measured for the hard/recovery path, but it is not the missing
mechanism by itself. Do not change the $10,000 shadow portfolio or arm the live
canary from this evidence. The next hypothesis must reduce bad entry episodes
without relying on partial-liquidation accounting or a post-result capital
grid. Runtime configuration and metalabel observe policy remain unchanged.
