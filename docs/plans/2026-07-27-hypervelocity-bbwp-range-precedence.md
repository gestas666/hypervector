# Hypervelocity BBWP Range-Precedence Diagnostic Plan

**Goal:** Determine whether the active classifier's BBWP precedence permits
harmful directional entries during 5m volatility compression and whether
treating that compression as RANGE improves venue-matched outcomes.

**Observed Implementation:** `_assign_primary` marks BBWP compression as RANGE,
then allows a strong EMA trend to overwrite it. Choppiness blocks that overwrite;
BBWP does not. This may be intentional tactical semantics, so it is a hypothesis,
not a confirmed defect.

**Architecture:** Add a report-only transformation over causal classifier output.
The control remains the faithful runtime classifier. The single challenger masks
5m `TREND_UP`/`TREND_DOWN` to `RANGE` whenever the completed 5m BBWP percentile is
below 25. Breakouts retain their existing precedence. No runtime file changes.

## Frozen Contract and Acceptance

- Matrix: faithful BBWP control versus `5m_bbwp_hard_range_25` only.
- Preserve 1m execution, 5m primary authority, 15m non-veto context, 8% target,
  70% allocation, 40x isolated leverage, maker costs, one position, and ML
  observe-only behavior.
- Challenger must beat control serial equity and remain within 0.5x-2x the
  original 2.27 positions/day before full L2 replay.
- Report original entry direction recall, false-RANGE-at-entry count, targets,
  liquidations, drawdown, and cadence. Do not hide a valid failing trial.

## Tasks

1. Test a pure transformation that masks only compressed 5m trends, preserves
   breakouts, and emits an explicit reason.
2. Build the completed 5m BBWP context without future bars and compare both
   decision frames over the full 90-day Hyperliquid candle cache.
3. Retain a checksum-identified JSON report with original-log alignment and
   serial portfolio outcomes.
4. Run checksum-verified trade-through L2 replay only if the challenger survives
   the predeclared serial/cadence requirements.

## Risks and Falsifiers

- Low BBWP measures volatility compression, not necessarily a horizontal range;
  treating it as a hard range can erase valid low-volatility trend continuation.
- More RANGE transitions can accidentally re-arm completed-direction entries and
  increase churn; cadence and liquidation counts expose that failure.
- Original entries classified RANGE by the challenger would falsify source
  alignment even if the serial loss shrinks.
- Serial fills are next-bar approximations and omit historical funding; a survivor
  is not evidence of live profitability until event replay.

## Verification

```bash
uv run pytest tests/test_hypervelocity_bbwp_precedence.py -q
uv run ruff check src/hypervector/research/hypervelocity_bbwp_precedence.py \
  tests/test_hypervelocity_bbwp_precedence.py
```

## Execution Result

The 25th-percentile hard-range challenger was the only threshold with positive
serial equity. With a 300-second cooldown it reached $19,877.77 in serial
screening, but checksum-verified public trade-through replay ended at $191.20
with 416 completed trades, 370 targets, 46 liquidations, 12 partial
liquidations, and -99.34% maximum drawdown. This improved substantially over the
faithful control's $6.54 but falsified profitability. Exact source direction
recall also fell from 24/35 to 20/35.

Evidence is retained in
`data/logs/research/hypervelocity_bbwp_range_precedence_20260727.json`. Runtime
configuration and ML observe-only policy were not changed.
