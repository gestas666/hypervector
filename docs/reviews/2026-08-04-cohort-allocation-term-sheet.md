# Cohort allocation experiment term sheet

**Written:** 2026-08-04 04:05 EDT  
**Status:** report-only candidate; not active  
**Runtime profile:** `multi_asset_bidirectional_canary_v2`  
**Execution authority:** none

## Objective

Increase useful live profit-and-friction information per resolved trade without
changing signal logic, direction eligibility, execution method, leverage, stop
logic, exit logic, or concurrent-position policy. The comparison isolates one
allocation variable: HYPE breakout notional.

The approximate funded balance is an arithmetic input, not an eligibility,
promotion, execution, or activation gate.

## Point-in-time inputs

- Account value: approximately `$504.20`.
- Maximum positions: four, with one position per coin.
- Margin mode: isolated.
- HYPE leverage: `5x`.
- HYPE breakout stop: `80 bps`.
- Current HYPE breakout cap: `$25`; planned margin approximately `$5`.
- Uncapped 3%-margin request: approximately `$75.63`.
- Resolved HYPE breakout sample: four trades, `3W/1L`, `+$1.004659`
  after recorded costs, profit factor `5.4867`.
- Long: three trades, `2W/1L`, `+$0.772171`, profit factor `4.4485`.
- Short: one trade, `1W/0L`, `+$0.232488`; profit factor is undefined because
  no loss is observed.
- A fifth HYPE breakout lifecycle is currently open long and protected. It is
  excluded from resolved performance.

## Controlled candidates

| Candidate | HYPE breakout cap | Other HYPE providers | Maximum portfolio margin | Estimated four-stop + taker-fee envelope |
|---|---:|---:|---:|---:|
| A: current baseline | `$25` | `$25` | `5.95%` | `$1.17` / `0.23%` equity |
| B: selective cap lift | `$75` | pinned at `$25` | `7.93%` | `$1.62` / `0.32%` equity |

The loss envelope assumes each coin's largest configured notional and stop,
plus `9 bps` round-trip taker fees. It excludes stop slippage, price gaps,
funding, venue failure, and correlated path effects; it is not a maximum-loss
guarantee.

Candidate B requires coordinated configuration changes after a verified
flat/no-orders boundary:

1. raise the HYPE asset adapter ceiling to `$75`;
2. set HYPE breakout/HYPE to `3%` and `$75`;
3. pin Hulk/HYPE and Range-Onset/HYPE to their existing `3%` and `$25`;
4. retain both long and short execution directions;
5. retain `5x`, isolated margin, the `80 bps` breakout stop, and current exit
   controller;
6. restart only at the lifecycle-safe flat boundary and verify the new profile
   fingerprint before any entry.

## Evaluation protocol

This is a controlled live allocation comparison, not allocator shopping.

- Preserve exact venue entry/exit fills, fees, funding, slippage, latency,
  liquidation distance, regime state, and exit attribution.
- Report baseline and larger-cap lifecycles separately as different profile
  generations.
- Compare notional-normalized after-cost return as well as dollar PnL so a
  larger order cannot appear better merely because it is larger.
- Compare observed fee/slippage rates and stop behavior; `$75` must not borrow
  the `$25` friction record without measurement.
- Keep every trial result. Do not suppress long, short, losing, sparse, or
  adverse-regime outcomes.
- Do not auto-pause, auto-promote, or use account balance, performance, or trade
  count as an execution gate.

## Decision and trade-offs

Candidate B is the recommended next allocation experiment after the current
HYPE lifecycle resolves and the account is flat for HYPE. It is more aligned
with the configured 3% margin intent while increasing the estimated simultaneous
stop-and-fee envelope by only about `$0.45` (`0.09%` of current equity).

This recommendation has medium confidence as a risk-utilization experiment and
low confidence as a profit improvement. Four closed trades support testing a
larger canary, not a durable edge claim. A linear three-times replay of historical
dollar PnL would be selection-biased and is not used as a forecast.

Evidence that would update the recommendation includes materially nonlinear
slippage at `$75`, a resolved current trade that changes HYPE's after-cost
profile, protection/reconciliation faults, or shared-account interactions not
present at `$25`. Those observations change the next configuration decision;
they do not retroactively gate valid live signals.
