# V94 size ladder (pre-registered; no size change today)

Plan item D of `docs/plans/2026-09-24-v94-review-actions.md`, approved by the
operator on 2026-09-24. Source: `docs/reviews/2026-09-24-v93-full-review.md`
(sections 7 and 9D). This document fixes the rungs, the advance and step-down
rules and the evidence procedure **before** any V94 result exists. It changes no
size: V94 ships at rung 0. Moving to another rung is its own config transition
(drain to flat, new fingerprint, approval JSON), never an automatic action.

Reference equity: **$4,831** (2026-09-24 14:53 UTC). Every Donchian route runs at
**8x** isolated. Dollar figures below are at that equity; all rung-1 limits are
fractions of equity, so they compound until a dollar cap binds.

## 1. How the runtime sizes a Donchian entry

1. Planned notional = `min(equity × margin_fraction × leverage, max_notional_usd)`
   (side-specific override, then provider-symbol override, then the asset table;
   the Donchian provider has no overrides, so the asset table governs).
   Write `k = margin_fraction × leverage`, the notional cap as a share of equity.
2. The stop-risk budget then caps notional at `B / m`, where
   `B = maximum_loss_fraction_of_equity × equity` and `m` is the modeled loss per
   dollar of notional from `size_for_stop_risk`: the stop distance priced from the
   worst fill inside the 20 bps IOC entry bound, plus the 20 bps cost buffer. For
   a structural stop `d` bps from the mark this is `m = d + 39.96` bps (short) or
   `d + 40.04` bps (long), about `d + 40`.
3. So `notional = min(k × equity, B / m)`. The budget binds when
   `m ≥ fraction / k`. The `k` cap is what keeps tight stops from being sized up:
   the ladder never sizes by 1/stop.

Observed structural stop distances `d` (initial stop vs fill):

| Route | d used | Source |
|---|---|---|
| SOL | 210 bps | No live D20 entry yet. Median journaled 2×ATR20 stop since 09-19 (n=112; IQR 205–216). |
| xyz:SNDK | 185 bps | Median of the 11 live D20 entries since 09-08 (IQR 100–203, range 73–250). The journaled 2×ATR20 median since 09-10 is 162 bps. |
| xyz:BRENTOIL | 151 bps | The one V93 live D20 entry. The journaled 2×ATR20 median is 158 bps (IQR 147–161). |
| xyz:TSLA | 81 bps | Mean of the two V93 entries (74.3 and 86.7). The journaled 2×ATR20 median is 83 bps. |

Realized loss at the stop is smaller than modeled because the fill is rarely at
the 20 bps bound: about `d + 12` bps on HIP-3 (fees 1.7 bps round trip; SNDK
median stop slip 9.3 bps, n=5) and about `d + 18` bps on SOL (crypto taker fees
about 8.6 bps round trip).

## 2. Rung 0 = V94 (exact sizing at $4,831)

Donchian provider: `stop_risk_budget = { maximum_loss_fraction_of_equity = 0.006,
cost_buffer_bps = 20.0 }`, so `B = 0.006 × 4,831 = $28.99`. BTC and ETH keep the
fixed `maximum_loss_usd = 25.0`. HYPE and SPCX are watch-only
(`execution_symbols = []`).

| Route | margin_fraction / cap | k | Planned notional | B / m at d | Notional | Binding | Modeled at stop |
|---|---|---|---|---|---|---|---|
| SOL | 0.013 / $700 | 0.104 | min(502.42, 700) = **502.42** | 28.99 / 2.50% = 1,159 | 502.42 | margin | $12.56 |
| xyz:SNDK | 0.05 / $2,600 | 0.40 | min(1,932.40, 2,600) = 1,932.40 | 28.99 / 2.25% = **1,288.27** | 1,288.27 | **0.006 budget** | $28.99 |
| xyz:BRENTOIL | 0.015 / $800 | 0.12 | min(579.72, 800) = **579.72** | 28.99 / 1.91% = 1,518 | 579.72 | margin | $11.07 |
| xyz:TSLA | 0.013 / $700 | 0.104 | min(502.42, 700) = **502.42** | 28.99 / 1.21% = 2,396 | 502.42 | margin | $6.08 |
| BTC (60/60) | 0.011 / $700 at 10x | 0.11 | min(531.41, 700) = 531.41 | fixed 60 bps: m = 80.2 bps | 531.41 | margin | $4.26 vs $25: budget non-binding |
| ETH (long) | 0.02 / $500 at 15x | 0.30 | min(1,449.30, 500) = 500.00 | fixed 60 bps: m = 80.2 bps | 500.00 | cap | $4.01 vs $25: budget non-binding |

SNDK is budget-bound whenever `d > 110` bps (`28.99 / (d + 40) < 1,932.40`); below
that its margin cap binds. At d = 185 the modeled $28.99 realizes about $25.4.

Book check (`scripts/cohort_runtime_validation_check.py --equity 4831`, which
prices every route at its maximum stop clamp of 250 bps plus the buffer):
at-stop risk **$80.02 (1.66%)**, margin **$526.10 (10.89%)**. Both are inside the
3% and 25% limits.

## 3. Rung 1 (earned; exact TOML at $4,831)

Rung 1 extends the calibrated 0.006 budget to all four Donchian routes. It raises
margin fraction and caps so that the budget, not the margin, sets size at the
observed stops. It uses `k = 0.30` (the top of the 0.25–0.30 range), so
`k × equity = $1,449.30` and the budget binds whenever `m ≥ 0.006 / 0.30 = 200`
bps, that is `d ≥ 160` bps.

`k = 0.30` compared with `k = 0.25` ($1,207.75):

| Route | m | B / m | k = 0.25 | k = 0.30 |
|---|---|---|---|---|
| SOL | 250.0 bps | 1,159.44 | 1,159.44, budget binds | 1,159.44, budget binds |
| xyz:SNDK | 225.0 bps | 1,288.27 | 1,207.75, cap binds | 1,288.27, budget binds (SNDK keeps k = 0.40, see below) |
| xyz:BRENTOIL | 191.0 bps | 1,517.59 | 1,207.75, cap binds | 1,449.30, cap binds (4.5% short of the budget) |
| xyz:TSLA | 121.0 bps | 2,395.54 | 1,207.75, cap binds | 1,449.30, cap binds (1/stop would need k = 0.50) |

At `k = 0.25` the budget binds on SOL only, so it would not "extend the budget".
`k = 0.30` makes it bind on SOL and SNDK, and within 5% on BRENT. TSLA's tight
stop stays capped by `k`. That cap is the anti-1/stop property, and the plan
keeps it deliberately.

Exact TOML changes, relative to V94, in the four Donchian asset tables:

```toml
# SOL, xyz:BRENTOIL and xyz:TSLA (leverage stays 8.0)
margin_fraction = 0.0375      # k = 0.0375 × 8 = 0.30
max_notional_usd = 2200.0     # hard ceiling; binds only above $7,333 of equity

# xyz:SNDK: unchanged from V94 (margin_fraction = 0.05, max_notional_usd = 2600.0)
```

The Donchian provider keeps `stop_risk_budget = { maximum_loss_fraction_of_equity
= 0.006, cost_buffer_bps = 20.0 }`, with no sizing overrides. BTC and ETH are
unchanged.

**Why SNDK is unchanged.** SNDK is already budget-bound at its observed stops
under V94. Moving it to `k = 0.30` would cut its notional from up to $1,932 to
$1,449 on every stop tighter than 160 bps. That would be a step down hidden inside
a step up, on the one route that carries the tail. The rung raises SNDK only
through `B`: it already compounds as a fraction.

Rung-1 sizing at $4,831 and the observed stops:

| Route | Notional | Binding | Margin | Modeled at stop | Realized at stop (est.) |
|---|---|---|---|---|---|
| SOL | 1,159.44 | budget | 144.93 | $28.99 (0.60%) | about $26.4 (0.55%) |
| xyz:SNDK | 1,288.27 | budget | 161.03 | $28.99 (0.60%) | about $25.4 (0.53%) |
| xyz:BRENTOIL | 1,449.30 | k cap | 181.16 | $27.68 (0.57%) | about $23.6 (0.49%) |
| xyz:TSLA | 1,449.30 | k cap | 181.16 | $17.54 (0.36%) | about $13.5 (0.28%) |

That is about 0.5% of equity realized at the stop on the budget-bound routes,
which is the plan's stated rung-1 risk.

Book check at the maximum clamp (every Donchian route charged
`min($28.99, planned × 270 bps)`):

| Equity | At-stop risk | Margin |
|---|---|---|
| $3,500 | 2.60% | 18.30% |
| **$4,831** | **$124.20 (2.57%)** | **$871.51 (18.04%)** |
| $6,500 | 2.55% | 17.84% |
| $9,000 | 2.51% | 13.93% (dollar caps binding) |

Both limits hold at every equity in the range. With all four Donchian positions
open, a simultaneous gap through every stop to isolated liquidation is bounded by
the posted margin. That bound is about $785 (16.2%) at rung 1 against $440 (9.1%)
at rung 0.

There is a known tension with the review. Its "do not fund up SOL or TSLA" is a
verdict on present evidence. Rung 1 funds them up only after the forward
evidence below, and TSLA only as far as the `k` cap, about 0.36% modeled.

## 4. Advance and step-down rules (as the plan states them)

- **Advance** (rung 0 → rung 1) after the next **30 closed Donchian lifecycles
  since the V94 start** show both of these at measured cost, with timer exits
  capped at the configured hold (outage holds capped):
  - **mean R > 0**;
  - **ex-top-3 net ≥ 0**.
- **Step down** to rung 0 on **−12% from the rung high**, or **mean R < 0 over any
  50 trades**.
- There is no rung 2. Proposing one requires a new pre-registration.

Operational definitions (implemented in `scripts/cohort_ladder_evidence.py`):

- A Donchian lifecycle is any closed position whose provider identity starts with
  `hourly_donchian_20_10_`. That covers the V93/V94 identity and the
  weak-short-filtered identity if it ships.
- The advance sample is the **first 30** such closes, by exit time, whose entry
  is at or after the V94 start. It is a fixed sample: later closes cannot rescue
  or spoil it.
- R is the lifecycle's net dollars (venue PnL minus both fees, plus funding)
  divided by `size × |entry − initial stop|`. The initial stop is the first
  protective-stop order the lifecycle placed. "Ex-top-3" removes the 3 largest
  net winners.
- A hold longer than the configured maximum hold (86,400 s) plus a 15-minute
  grace is an outage hold. For the ladder, its outcome is replaced by the
  executable mark at `opened_at + maximum_hold` (bid for longs, ask for shorts),
  at the lifecycle's measured exit-fee rate. If no book observation exists within
  15 minutes of that time (the bot was dark), the verdict is **indeterminate**
  until a mark is supplied with `--supplemental-marks`. The outage hold is never
  counted at its uncapped value.
- The rung high is the running maximum of journaled `account_value_usd` since the
  rung start. The drawdown trigger fires if equity is ever at or below 0.88 × that
  high. The 50-trade trigger fires if any 50 consecutive closes since the rung
  start have mean R < 0, on either the capped or the realized basis. This is the
  risk-reducing reading, because a step-down only ever removes risk.
- Advancing needs the operator's approval of the rung-1 profile transition. The
  evidence tool only reports `advance`. A step-down is prepared as the reverse
  transition, pre-authored when rung 1 is installed.

## 5. The price of rung 1 under zero edge

From the review's day-block bootstrap of the book with **zero edge**, 90-day
probability of a drawdown of 20% or more:

| Risk per trade | P(DD ≥ 20%) | |
|---|---|---|
| 0.27% (V93 today, and about rung 0) | 0.2% | |
| **0.5% (rung 1)** | **about 12%** | the price of rung 1 if the edge is zero |
| 0.75% | 40% | not approved |
| 1.0% | 65% | not approved |

Kelly on the pooled evidence is about zero (the recent 8-asset pool is
+0.049R, t = 0.66; the one-year crypto pool is −0.083R). Rung 1 is therefore
earned by forward results, not justified by past ones. The −12% step-down exists
so that the ~12% zero-edge tail is cut before it reaches 20%.

## 6. Explicitly not approved

- The optional **SNDK 0.75% variance sleeve** (about $36). It is not part of this
  approval, and not part of any rung.
- **Leverage increases.** Margin is not the binding constraint. Every rung keeps
  8x on the Donchian routes and the V94 leverage elsewhere.
- **1/stop parity sizing.** The `k` cap stays. Tight-stop trades (< 80 bps) lose
  −0.28R.
- Restoring SNDK to $1,930, or a $45–52 budget, on an edge claim.
- Making a fixed-dollar budget bind on every route.
- Cross margin, or any change to the v2 exit constants.

## 7. Evidence procedure

Read-only, no execution authority, standard library only:

```bash
uv run python scripts/cohort_ladder_evidence.py \
  --profile-id <profile id from the V94 TOML> \
  --since <V94 armed start, ISO-8601 UTC> \
  --out <scratch>/v94_ladder_evidence.json
```

It prints and writes:

- the advance and step-down statistics;
- every Donchian lifecycle with its own-stop R;
- outage holds, flagged and capped;
- equity high-water and drawdown;
- breakout extension on every Donchian short, as `(prior 20-bar low − close) /
  ATR20` from the journaled `intent_routing` readiness metrics;
- the floor-armed 24h-timer counterfactual;
- 240- and 1,440-minute post-exit marks;
- time-in-market-scaled buy-and-hold.

Before arming any rung:

```bash
uv run python scripts/cohort_runtime_validation_check.py \
  --config <rung profile> --mode live --equity <current account value>
```

This exits 3 when the book exceeds 3% at-stop risk or 25% margin.

Baseline check on 2026-09-24, run against the live V93 ledgers
(`bidirectional-live-1790196314874`, read-only):

- 2 closed Donchian lifecycles. Both TSLA shorts hit their protective stops, for
  −$8.39 net and a mean of −1.04R. Two more are open: an SNDK short and a BRENT
  long.
- All 3 Donchian shorts were weak breakouts: SNDK 0.91 ATR, TSLA 0.02 and 0.95.
- The equity high-water was $4,846.85; the maximum drawdown from it was −0.79%.
- The same tool, run on the V89 profile, flags the 09-11 SNDK 96.7-hour hold as
  an outage hold whose 24h mark was never observed (`cap_mark_unavailable`).
