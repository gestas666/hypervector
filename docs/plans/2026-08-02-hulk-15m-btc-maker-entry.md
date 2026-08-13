# BTC 15m Hulk maker-entry validation freeze

Status: development-falsified; report-only; no execution authority. Validation
and pseudo-holdout remain unconsumed.

## Problem and success criterion

The current executable SOL sleeve is historically sparse. A fixed 15-minute
version of the bidirectional Hulk signal increased cadence, but the combined
BTC/SOL development replay lost after realistic friction. BTC alone was near
break-even and needed approximately 1.16 bps of entry improvement. This test
asks whether a causally reconstructed post-only BTC entry can provide that
improvement without assuming every signal fills.

Success requires positive net PnL and profit factor above one in the untouched
validation window, both long and short signals retained, zero liquidation,
complete entry-evidence coverage, and no unexplained accounting discrepancy.
That result would authorize fresh forward observation only, not live execution.

## Frozen identity

- Symbol: BTC perpetual on Hyperliquid.
- Signal: `hulk_expansion_bidirectional_tuned_v2`, completed 15-minute bars.
- Directions: long and short; no directional selection after outcomes.
- Maker submission: first L2 snapshot no more than 1,000 ms after the original
  next-bar decision time.
- Limit: current best bid for a long and best ask for a short.
- Fill rule: opposite-aggressor public volume at or through the limit must clear
  the full displayed queue plus the intended order quantity.
- Entry TTL: 300 seconds. Unfilled signals expire and do not become market
  orders.
- Lifecycle: first complete one-minute bar after the reconstructed fill;
  pessimistic liquidation-before-stop-before-target ordering.
- Risk/exit: 0.25% account risk, 5x isolated leverage, 20–75 bps stop clipping,
  3R target, 24-hour maximum hold, one BTC position.
- Friction: 1.5 bps maker entry and target fees, 4.5 bps market-exit fee,
  2 bps adverse market-exit slippage, and authentic hourly funding.
- Capital: standalone $15,000 research equity. Shared-capital interaction with
  the SOL sleeve is a later test only if this candidate survives.
- Development: 2025-08-23 09:00 UTC through 2026-02-01 00:00 UTC.
- Validation: 2026-02-01 00:00 UTC through 2026-05-01 00:00 UTC.
- Pseudo-holdout remains sealed unless validation is positive.

## Known approximation and falsifiers

The fill-to-next-complete-minute interval is not replayed in the lifecycle.
Its duration must be reported and cannot exceed 60 seconds. Public L2 cannot
prove private queue rank or cancellations, so the fill rule remains a bounded
reconstruction rather than venue truth.

The candidate is falsified for further historical promotion if validation net
PnL is non-positive, profit factor is at or below one, either direction is
absent, any liquidation occurs, required L2/public-trade evidence is missing,
or the one-minute path gap is hidden. A favorable result remains provisional
until exact event-path or fresh forward evidence resolves the path gap.

## Development result

The frozen development run was published as
`data/logs/research/20260802_hulk_bidirectional_tuned_v2_btc_15m_maker_development_v1.json`.
It is a paired counterfactual over the 64 trades accepted by the original
market-entry replay; it is not a standalone replay of all 83 signals.

- Reconstructed fills: 35/64 (54.69%).
- Missing book within 1,000 ms: 15; unfilled before 300 seconds: 14.
- Mean entry improvement: 2.03 bps; mean wait: 70.23 seconds.
- Net PnL: -$5.62; profit factor: 0.995; maximum drawdown: 3.91%.
- Directions: long 14 trades / -$14.09 / PF 0.965; short 21 trades /
  +$8.46 / PF 1.013.
- Fees: $159.11; funding cashflow: -$5.31; liquidations: zero.
- The replay exposed 22 internal one-minute source gaps, with a maximum gap of
  seven minutes, and reported a maximum fill-to-lifecycle gap of 59.77 seconds.

The development criterion failed because net PnL and PF were non-positive and
15 accepted baseline decisions lacked the frozen book evidence. The validation
window was therefore not consumed. Relaxing the one-second book bound, changing
the 300-second TTL, selecting only shorts, or otherwise tuning this identity
after seeing the result would be a new post-hoc experiment rather than a repair
of this frozen candidate.
