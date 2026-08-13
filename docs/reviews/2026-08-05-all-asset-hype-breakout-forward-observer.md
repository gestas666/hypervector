# All-asset HYPE-breakout forward observer

**Started:** 2026-08-05 15:25 EDT  
**Run:** `bidirectional-observe-1785957950856`  
**Execution authority:** none; report-only  
**Symbols:** BTC, ETH, SOL, HYPE  
**Sides:** long and short

## Purpose

Collect prospective, venue-matched signal and blocker telemetry for the exact
`hype_breakout_onset_bidirectional_v1` rule on all four portfolio assets. This
observer is a measurement complement to the completed historical transfer
study. It cannot place orders, cannot alter the live profile, and cannot promote
a mapping automatically.

## Bound runtime identity

- profile: `all_asset_hype_breakout_transfer_observer_v1`
- profile fingerprint:
  `5d7bed06a4e26c93aa7c480f6fa6f28d801c8b624f7e12100356be304ffb35b5`
- ledger: `data/observe/all_asset_hype_breakout_transfer/decisions.jsonl`
- checkpoint:
  `data/runtime/all_asset_hype_breakout_transfer/latest_checkpoint.json`
- cadence: one evaluation cycle per 60 seconds
- provider execution symbols: empty
- live loader behavior: refuses to arm because no execution mapping exists

The first checkpoint observed all four expected provider-symbol mappings, zero
technical gaps, zero duplicate evaluations, zero eligible signals, and zero
routed actions. This proves initial collection and authority separation; it is
not evidence of profitability or trade frequency.

## Evidence shown in telemetry

The configuration identity now binds each exact mapping to the completed
365-day transfer review:

- BTC: low-confidence prospective observer. The unchanged rule was negative in
  development but positive in the already-opened final 60 days, entirely due to
  shorts. The sign reversal prevents an edge claim.
- ETH: unchanged transfer rejected for execution after negative development and
  final-60-day results in both directions.
- SOL: unchanged transfer rejected for execution after materially negative
  development and final-60-day results in both directions.
- HYPE: historical deployed-shape replay remains negative; the existing live
  HYPE route is governed by its separate sparse live-evidence decision.

The previous BTC/HYPE-only observer was stopped after the four-asset observer
passed startup validation. Its ledger was preserved. This removes duplicate BTC
and HYPE public-data requests while retaining broader coverage.

## Success criteria and falsifiers

Operational success requires continuous four-symbol coverage, no duplicate or
future evaluations, no observer order or fill events, no execution authority,
and no correlated increase in live rate-limit faults.

Transfer evidence improves only after resolved prospective signal paths accrue
with direction, regime context, and measured live market data. A positive
counterfactual path is descriptive; it does not establish executable PnL because
the observer does not submit orders. Repeated negative after-cost paths would
reinforce rejection. Repeated positive paths across more than one market state
would justify a separately frozen execution-friction challenger, not automatic
promotion.

## Confidence and limitations

**Operational confidence: medium.** Startup and the first complete cycle passed,
but a longer uninterrupted window is required. A missing symbol, cadence gap,
fault event, or any order/fill record would lower or invalidate this assessment.

**Economic confidence: low.** No eligible prospective signal has occurred in
this run. Historical transfer evidence is adverse or contradictory, and
observer paths do not reproduce private queue position, acknowledgements, or
realized slippage.

