# Hypervelocity RSI Re-entry Reconfirmation Plan

**Goal:** Determine whether a fresh same-direction 1m RSI(14)/EMA(7) crossover
after a successful 8% target can reproduce original same-regime re-entry without
turning a persistent trend label into a continuously true entry signal.

**Architecture:** Keep initial entries and structural regime classification
unchanged. In report-only serial screening, a completed same-side target remains
consumed until the existing causal RSI crossover emits a fresh same-direction
event after cooldown. Liquidations still require a structural regime reset. Add
the equivalent event signal to L2 replay only if serial evidence survives.

## Frozen Evidence and Contract

- Original log: 20 non-overlapping same-side re-entries after collapsing split
  exits; 14/20 had a same-direction RSI crossover after the prior close and no
  later than the next entry.
- The full BBWP tactical breakout occurred in only 1/20 windows and is therefore
  too sparse to explain the source behavior.
- RSI parameters remain the configured 14-period RSI and 7-period EMA; no
  threshold is tuned after performance is observed.
- Fixed matrix: `regime_reset_60s` control and one
  `target_rsi_reconfirmation_60s` challenger.
- Preserve one position, 70% allocation, 40x isolated leverage, fixed 8% target,
  maker costs, RANGE hold policy, and ML observe-only operation.
- Do not change runtime configuration during this experiment.

## Task 1: Test the Serial State Machine

**Files:**
- Modify: `src/hypervector/research/hypervelocity_portfolio_eval.py`
- Test: `tests/test_hypervelocity_portfolio_eval.py`

1. Prove a target cannot immediately re-enter on a persistent trend label.
2. Prove a fresh same-side RSI cross after cooldown permits one re-entry.
3. Prove a liquidation cannot re-arm from an RSI cross in the same structure.
4. Preserve control, cooldown-only, and target-continuation behavior.

## Task 2: Retain the Fixed Screen

**Files:**
- Modify: `src/hypervector/research/hypervelocity_reentry_compare.py`
- Modify: `tests/test_hypervelocity_reentry_compare.py`
- Modify: `scripts/hypervelocity_reentry_compare.py`
- Create if executed:
  `data/logs/research/hypervelocity_target_rsi_reconfirmation_20260727.json`

1. Report original-window coverage, cadence, equity, drawdown, and liquidations.
2. Retain control and challenger regardless of outcome.
3. Require final serial equity above control and cadence within 0.5x-2x the
   original 2.27 positions/day before any full event replay.

## Task 3: Event Replay Only if Serial Survives

1. Project causal RSI re-entry events into the maker replay without changing
   initial-entry directions.
2. Run checksum-verified Hyperliquid trade-through replay over the complete
   archive.
3. Require ending equity above $10,000 after modeled costs for evidence of
   profitability; report rather than hide every valid losing trial.

## Failure Modes and Falsifiers

- A crossover anywhere in a long source window is compatibility evidence, not
  proof that it caused the historical entry.
- RSI may fire too frequently in noisy directional states; excessive cadence or
  liquidation count falsifies it.
- Serial next-bar-open fills omit queue position, public trade-through volume,
  and historical funding. A survivor still requires event replay.
- Fresh original logs lacking RSI reconfirmation before same-side entries would
  weaken the source-alignment hypothesis.

## Verification

```bash
uv run pytest tests/test_hypervelocity_portfolio_eval.py \
  tests/test_hypervelocity_reentry_compare.py -q
uv run ruff check src/hypervector/research/hypervelocity_portfolio_eval.py \
  src/hypervector/research/hypervelocity_reentry_compare.py \
  scripts/hypervelocity_reentry_compare.py
```

## Execution Result

Completed and falsified at the fixed serial gate. RSI reconfirmation recovered
14/20 original same-side re-entry windows, but produced 986 completed trades
(10.96/day), 849 targets, 137 liquidations, and $0.000002 final marked equity.
The control produced 328 trades (3.64/day), 289 targets, 39 liquidations, and
$173.00. The challenger therefore failed both equity and cadence requirements;
full L2 replay was skipped. Evidence is retained in
`data/logs/research/hypervelocity_target_rsi_reconfirmation_20260727.json`.

Runtime strategy configuration and ML observe-only policy were not changed.
