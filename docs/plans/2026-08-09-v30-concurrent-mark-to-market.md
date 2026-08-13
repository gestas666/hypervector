# v30 Concurrent Mark-to-Market Validation Plan

## Objective

Measure the path-dependent shared-account drawdown of the fixed v30 candidate
without changing live v25, selecting new entries, or tuning against the result.

## Frozen candidate

- `range_onset_bidirectional_v1|SOL`: $75 notional, 5x
- `range_onset_bidirectional_v1|ETH`: $25 notional, 5x,
  `dual_mtf_not_opposed`
- `hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX`: $75 notional, 5x
- one position per symbol, three positions maximum
- priority: Range Onset, then SPCX Swing/HA
- initial shared equity: $500

The accepted lifecycle identities must come from the existing immutable lean
successor artifact and reconcile exactly to its nominal closed-trade ledger.

## Inputs

- ETH official 1-minute Hyperliquid candles
- SOL official 1-minute Hyperliquid candles through 2026-07-30
- SPCX verified 0xarchive L2 midpoint 15-minute bars
- exact ETH, SOL, and SPCX lifecycle rows used by the lean successor comparison
- existing nominal fees and funding recorded by each source lifecycle

## Method

1. Rebuild the fixed nominal route inputs and priority arbitration.
2. Join every accepted lifecycle back to its exact source row.
3. Scale entry price, quantity, fees, and funding to the accepted shared-account
   sizing base.
4. Revalue all simultaneously open positions on each completed source bar.
5. Report two paths:
   - completed-bar close mark;
   - adverse intrabar bound using low for longs and high for shorts.
6. Charge entry fees at entry, accrue recorded funding linearly only as an
   approximation, and charge exit fees at exit through the exact recorded net.
7. Require terminal equity and every accepted lifecycle to reconcile to the
   immutable realized ledger.
8. Run fixed, predeclared sizing multipliers: 0.50x, 0.75x, 1.00x, 1.25x,
   1.50x, and 2.00x. This is sensitivity analysis, not optimization.

## Acceptance criteria

- No execution or model authority.
- No accepted lifecycle is missing its source row.
- No lifecycle lacks a mark between entry and exit without being named.
- Terminal marked equity equals the closed-trade replay within one cent.
- Full-opened and opened-final-common windows are reported separately.
- Both close-mark and adverse-intrabar maximum drawdown are reported.
- Sizing recommendation remains provisional because all source windows are
  opened and selection-contaminated.

## Failure modes and falsifiers

- A source identity mismatch invalidates the report rather than silently
  dropping a trade.
- Missing candle coverage is reported and blocks a sizing recommendation for
  the affected route.
- Linear funding accrual is not equivalent to venue settlement timing; large
  funding relative to drawdown would require exact settlement replay.
- Midpoint SPCX bars are a price-path proxy, not executable trade OHLC.
- A materially larger live adverse excursion or stop gap falsifies the sizing
  estimate and requires reducing risk before expansion.
