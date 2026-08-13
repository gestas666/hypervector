# Hypervelocity source-derived Tier-0 peak protection

Date: 2026-07-29
Status: predeclared, report-only

## Problem and hypothesis

The frozen session short candidate remains aggregate-positive but suffered two
liquidations in the April 4-18 extension. The April 11 short first reached
+7.152% gross margin PnL before reversing into liquidation; the April 13 short
reached only +0.057%. Entry-time source confidence, 5m/15m agreement, spread,
and order-book pressure did not separate the losses.

Hypertrader revision `ad15f2bdc949619be495a5f516babd08f7f52a90` contains a
live position-protection Tier 0 in
`backend/app/services/hyperliquid_tiers.py`: activate at +6% margin PnL and
lock 55% of the observed peak. Its position monitor updates peak PnL from the
venue mark and executes a reduce-only stop at adverse market liquidity. This
mechanism belongs to Hypertrader's live position monitor, not its selective
classification dry-run, so it is a source-derived robustness challenger rather
than proof of the creator strategy's exit rule.

Hypothesis: a source-exact +6%/55% peak lock can remove profitable-to-liquidated
reversals without stopping entries that never establish favorable excursion.

## Frozen causal semantics

- Default replay behavior remains unchanged; both fields are disabled unless
  explicitly configured together.
- Update peak margin PnL only on causal authentic Hyperliquid mark events.
- On the first observed peak at or above +6%, compute locked margin PnL as
  `peak * 0.55` and translate it to a side-aware stop price at 40x.
- Never widen an existing stop. Subsequent updates require at least a 0.05%
  entry-price improvement and 60 seconds since the prior update, matching the
  source monitor. Because the fixed target is +8% margin, Tier 0 will normally
  arm once before target completion.
- Execute a triggered stop at adverse BBO with the configured taker fee.
- Authentic mark liquidation retains priority. Maker target, official funding,
  one-position policy, 70% isolated margin, 40x leverage, and 8% gross-margin
  target remain unchanged.
- Report arm and exit counts separately. Do not label the mechanism as a model
  or allow it to change runtime, shadow, TUI, or ML authority.

## Experiment and evidence boundaries

Compare the unchanged control with Tier 0 on every completed gap-free
`source-follow-session-06-15-confidence-70` block through April 18. This is
development/extension evidence: the candidate was selected after inspecting
the two April loss paths.

Reserve April 18-28 as the first candidate-unseen block. Do not alter the
constants, entry stream, target, or fill rule after seeing that result. Use
public trade-through maker fills, authentic mark/oracle/funding context, and
separately reset $10,000 portfolios at archive gaps.

## Acceptance and falsification

Tier 0 is not promotable unless it:

1. improves aggregate net PnL and worst-block maximum drawdown through April 18;
2. does not convert enough control targets into stops to lower aggregate net
   expectancy;
3. remains positive and non-inferior to control on the untouched April 18-28
   block; and
4. preserves checksum-conclusive execution evidence and exact lifecycle
   accounting.

A negative or materially worse untouched block rejects the mechanism for this
candidate. A positive single block remains insufficient for live promotion;
fresh shadow comparison is still required. Missing creator loss exits remain a
source-fidelity limitation regardless of replay performance.

## Verification

- Unit-test configuration pairing, mark-only activation, side-aware stop price,
  no widening, cooldown/minimum-move behavior, and BBO taker execution.
- Re-run the existing maker-replay and source-recipe suites.
- Hash every report and preserve control/candidate event identities.
- Confirm `runtime_strategy_changed=false`, `selection_is_promotion=false`, and
  `model_authority=observe` in generated reports.
