# Survivor live-canary order — 2026-08-01

> **Superseded:** The sequential Hulk-first/SOL-second order was rejected on
> 2026-08-01 because the required portfolio must operate long and short sleeves
> together. The replacement design is
> `docs/plans/2026-08-01-bidirectional-shared-live-cohort.md`. This document is
> retained only as an evidence snapshot and grants no live authority.

## Problem restatement

Choose the first live canary from the surviving directional candidates without
using the failed Apex MM economics, running conflicting account authorities, or
presenting technical readiness as proof of profit. Success for this phase is one
fully attributed real lifecycle with exact fills, costs, protection, inventory,
and final reconciliation—not a statistically meaningful profit estimate.

## Current facts

- The account was read through public-wallet-only clients and was flat at
  `$153.56757449`, with the same amount withdrawable and no open BTC or SOL
  orders. These values are time-sensitive and armed startup must revalidate
  them.
- Hulk's bounded observer run `hulk-observe-1785625546363` recorded 101 rows,
  sequences 203–303, from `2026-08-01T23:05:58Z` through `23:06:00Z`. It was
  `live_armed=false`, `execution_authority=none`, flat, fault-free, and received
  current five-level BTC L2. It did not retro-trigger a startup trade.
- Hulk's full ledger at that boundary is 378,556 bytes with SHA-256
  `b586dc2fbf374ae2df767ecac032547b1796169a87e64a7bcff5ffdf591f9c54`.
- SOL's immutable read-only preflight at `2026-08-01T23:06:53Z` was technically
  ready, flat, execution-incapable, and observed current SOL L2. Its artifact is
  1,615 bytes with SHA-256
  `126109bf83460aaa635503162ed4d3ab639954631d65e69e8e13bbb57a5047a7`.
- The five exact Apex recovery audits contain 11 real Apex fills and
  `-$0.042815` aggregate net cashflow. Apex remains measurement-only and is not
  a survivor canary.

## Selection matrix

| Property | Hulk Smash BTC short | SOL range-onset long/short |
|---|---:|---:|
| Historical resolved trades | 66 continuous diagnostic | 42 clean-block trades |
| Historical headline | +$758.57, PF 1.41 | +8.84%, PF 3.86 |
| Strongest contradiction | Final 9 trades: -$18.35, PF 0.93 | Winner concentration and post-selection blocks |
| Approximate observed cadence | 1.4 trades/week | 0.8 trades/week |
| Canary leverage | 5x isolated | 5x isolated |
| Maximum notional | $150 | $22.50 |
| Intended setup risk | 0.25% account equity before friction | 80-bps stop on $22.50 notional |
| Direction | Short only | Long and short |
| Live profit confidence | Low-to-medium | Low-to-medium |

The headline results are not directly comparable: Hulk is a continuous
chronological portfolio, while SOL compounds clean blocks around provider gaps.
The ordering therefore prioritizes evidence cadence and runtime maturity rather
than whichever historical percentage is larger.

## Frozen order and scope

1. Run Hulk first, sequentially on the shared account.
2. Stop and audit after one completed position lifecycle or 14 calendar days,
   whichever occurs first.
3. Preserve a zero-fill 14-day result as cadence evidence; do not relax the
   signal or retro-enter an expired setup.
4. Run SOL second under a separate fresh approval after Hulk is stopped and its
   account lock is released.
5. Do not run Apex MM concurrently. It would consume BTC ownership and its
   measured economics are negative.

The Hulk profile remains unchanged: 30-minute completed-bar signal, next-bar
market entry no more than 60 seconds late, 5x isolated leverage, 0.25% equity
risk, $150 maximum notional, structural 20–75 bps stop, 3R target, and 24-hour
maximum hold. At the observed account value, intended gross setup risk is about
`$0.38` before fees, slippage, gaps, and stop execution error. The notional cap
does not mean the entire account is at risk.

## Required live evidence

One completed lifecycle must preserve and reconcile:

- exact Hyperliquid `tid`, order ID, exchange timestamp, and transaction hash;
- entry/exit price, size, liquidity side, fees, funding, and closed PnL;
- submitted price versus fill slippage and configured-horizon markout;
- position, isolated margin, liquidation price/distance, and bracket OIDs;
- target, stop, or maximum-hold exit attribution;
- TUI equality with the backend ledger; and
- final venue-flat state with no open owned orders.

Profit, loss, or zero trades are reported outcomes, not strategy abort gates.
Technical faults remain fail-closed. An unprotected position, unknown fill,
identity mismatch, stale entry, backend/venue divergence, missing final
reconciliation, or TUI-invented value invalidates the canary.

## Recommendation and confidence

Run Hulk first only after a fresh explicit live authorization using the unified
launcher. No live authority is granted by this document. The command to be used
after approval is:

```bash
uv run python scripts/hulk_smash_canary_tui.py \
  --mode live --enabled --i-accept-live-risk
```

Confidence is medium-high that the tested launcher, bracket, ledger, and TUI
paths are ready for a bounded canary. Confidence in profitable live Hulk
economics is low-to-medium because the latest pseudo-holdout was negative and
the cadence is sparse. A fresh lifecycle with missing protection or accounting
falsifies technical readiness; repeated fully reconciled after-cost losses or a
14-day zero-fill result materially weakens the economic/cadence case.
