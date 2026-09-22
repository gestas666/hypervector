# V90 profit lock — independent exit review

Date: 2026-09-21. Execution authority: none. Report-only; proposes no gate and
changes nothing. Reviews the 100 / 25 / 50 bps completed-bar trailing lock in
`docs/reviews/2026-09-21-v90-profit-protection-readiness.md` against the stated
objective: aggressive bankroll building.

Evidence: `data/logs/research/bidirectional_cohort/v90_expansion_screen_20260920_v1/`
— `exit_policy_v90_roster_63d.json`, `exit_policy_mechanism_26sym_52d.json`,
`exit_policy_resolution_{15m,5m}_17d.json`. Script: `scripts/v90_exit_policy_screen.py`.

## 1. Verdict

**The engineering is sound and the readiness review is honest about its own
trade-off. The policy is wrong for this book.** On the three routes V90 actually
funds, the proposed lock removes about two thirds of the measured result, and it
removes essentially all of it on xyz:SNDK — the one route V90 sizes up 3.9x.

The requirement behind it is legitimate and measurable: **37 of 160 roster trades
(23%) reached +1% and then closed at a loss, costing $236 over 63 days.** That is
57% of the roster's net. But the same book's 17 trades above $20 paid **$721 —
3.1x what the round-trips cost** — and a 50 bps trail cannot tell the two apart
while they are still open.

## 2. Why the 27-lifecycle replay and this one disagree

The readiness replay scored 27 live lifecycles and found −$10.81 → −$3.80. It is
correct as far as it goes. But most of those lifecycles come from mechanisms V90
retires (band-20 on SPCX, Donchian 8/4 on Brent, SOL range-onset, BTC sweep) —
losing routes, on which almost any early exit helps. It contains two SNDK trend
winners, and the lock cut both: +$27.25 → +$4.86 and +$25.30 → +$3.92.

This review scores the **same function the live controller calls**
(`evaluate_profit_lock_path`) on the routes V90 runs, 160 control trades instead
of 27, identical signal frames across arms. Six arms were declared in the script
before any result, as families rather than a tuning grid.

## 3. V90 roster — SOL + xyz:SNDK + xyz:BRENTOIL, hourly Donchian 20/10, 63 days, 8x, $500/trade

| Arm (activation / floor / trail, bps) | Trades | Net, measured | Net, adverse | Win rate | Payoff ratio | Trades > $20 | Lock exits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **none** | 160 | **+$417.31** | **+$329.66** | 38.1% | **2.62** | 17 | 0 |
| 60 / 15 / 30 | 265 | +$59.77 | −$37.08 | 60.4% | 0.72 | 3 | 191 |
| **100 / 25 / 50 — proposed** | 237 | **+$137.43** | **+$21.58** | 58.6% | **0.84** | 6 | 141 |
| 150 / 35 / 75 | 211 | +$203.97 | +$160.74 | 51.7% | 1.20 | 7 | 103 |
| 100 / 25 / no trail (pure floor) | 189 | +$208.74 | +$170.60 | 50.3% | 1.32 | 14 | 76 |
| 300 / 100 / 300 (wide) | 171 | +$351.66 | +$274.30 | 40.4% | 2.23 | 18 | 29 |

Per route, measured cost:

| Route | none | proposed 100/25/50 | wide 300/100/300 | Largest trade: none → proposed |
| --- | ---: | ---: | ---: | --- |
| **xyz:SNDK** | **+$177.96** | **+$1.48** | +$63.41 | $91.48 → $25.68 |
| SOL | +$197.56 | +$125.30 | +$232.43 | $54.83 → $22.73 |
| xyz:BRENTOIL | +$41.79 | +$10.65 | +$55.82 | $28.92 → $28.60 |

What the proposed lock does, mechanically:

- **It inverts the payoff geometry.** Win rate rises from 38% to 59%, which feels
  like protection. Payoff ratio falls from 2.62 to 0.84. A breakout system that
  wins a third of the time earns its whole return from the right tail; at a payoff
  below 1.0 it has become a scalper that needs a 54% win rate just to break even
  before costs. That is the penny-scraper profile the objective rules out.
- **It removes SNDK's edge entirely** (+$178 → +$1). No tested lock of any shape
  helps SNDK: the least harmful, 300/100/300, still costs it $115. SNDK's winners
  retrace deeply on the way up, and even a pure +25 bps floor stops them out.
  Scaled linearly to V90's SNDK notional the comparison is roughly **$694 against
  $6** — V90 as drafted multiplies the variance and fees of a route whose measured
  edge the lock has just removed.
- **It raises trade count 48%** (160 → 237) because early exits free the slot for
  re-entries. More fee and slippage surface: at adverse cost the locked roster
  keeps 7% of the unlocked result.

## 4. Mechanism scale — 26 markets, 52 days, 1,217 control trades

| Arm | Net | vs none | Payoff | Symbols improved |
| --- | ---: | ---: | ---: | ---: |
| none | +$301.51 | — | 2.14 | — |
| 60 / 15 / 30 | +$0.87 | −$300.64 | 0.83 | 14/26 |
| **100 / 25 / 50** | +$241.80 | **−$59.71** | 1.03 | 15/26 |
| 150 / 35 / 75 | +$58.27 | −$243.24 | 1.29 | 11/26 |
| pure floor 100 / 25 | +$326.32 | +$24.81 | 1.40 | 13/26 |
| wide 300 / 100 / 300 | +$341.43 | +$39.92 | 1.90 | 14/26 |

In aggregate the proposal is close to neutral, and that aggregate is the trap. It
**helps the markets where the breakout has no trend edge** (xyz:SKHX +$76, xyz:MU
+$71, xyz:SKHY +$60, xyz:META +$50, xyz:SPCX +$46) and **hurts most the two where
it does: xyz:SNDK −$172 and SOL −$99** — the two largest losers of 26, and the two
routes V90 funds. A tight trail turns a trend follower into a harvester of
chop-then-reverse; it pays on choppy names and destroys trending ones.

The response is also not smooth across trail width (−$301, −$60, −$243 for
60/100/150). With no monotone response there is no robust optimum; that 100/25/50
lands near neutral while both neighbours lose heavily is itself noise.

## 5. Resolution bias

Live evaluates the lock on completed one-minute candles; this replay uses
15-minute bars. Re-running the same 17-day window at both resolutions: the
proposal costs the roster $109 at 15m and **$123 at 5m**. A finer clock ratchets
the best price sooner and triggers more often. Live on one-minute candles should
be expected to do somewhat worse than the 15m figures above, not better.

## 6. Implementable options, scored on the 63-day roster

| Option | Measured | Adverse | Needs |
| --- | ---: | ---: | --- |
| A. As proposed: 100/25/50 on all three | +$137.43 | +$21.58 | nothing |
| **B. No lock (the unprotected v1 identity)** | **+$417.31** | **+$329.66** | **config only** |
| C. SNDK on v1 unlocked; SOL + Brent stay on protected v2 | +$313.91 | +$192.58 | config only |
| D. Wide 300/100/300 on all three | +$351.66 | +$274.30 | new frozen identity |
| E. SNDK unlocked; SOL + Brent on wide 300/100/300 | +$466.21 | +$376.82 | new frozen identity |

Both identities already validate in the modified `hourly_price_contract.py` — the
unprotected `…_bidirectional_v1` with `profit_lock_policy = "none"`, and the
protected `…_profit_lock_bidirectional_v2` pinned to exactly 100/25/50 — so
**options B and C are TOML edits with no further source change.** The wide arm is
not expressible today: the v2 contract pins its three parameters, so D and E need
a third identity, tests and a new approval.

Option E is the best row and should not be trusted as such: it is the best of a
3-route × 6-arm table read after the fact, and its +$49 over B is two cells. What
is robust is the ordering of families — none and wide at the top, tight trails at
the bottom — which holds on the roster at both cost levels and at mechanism scale.

## 7. Recommendation

1. **Do not arm 100/25/50 on xyz:SNDK under any circumstances**, and do not size
   SNDK 3.9x while it carries that lock. If protection must exist somewhere, option
   C costs $103 of measured result against B; option A costs $280.
2. **Preferred: option B.** For a 35–38% win-rate trend follower the correct exit
   stack is the one it already has — ATR(20)×2 initial stop, the 10-bar Donchian
   exit channel, the 24h fallback. The exit channel *is* a trailing stop, and it is
   scaled to each market's own volatility instead of a fixed 50 bps. Measured on
   the 63-day tape, xyz:SNDK's median **hourly** range is 87.6 bps and 71% of its
   hours move more than 50 bps on their own (SOL 61.4 bps / 62%; Brent 55.3 bps /
   55%). A 50 bps trail is 0.57 of one ordinary SNDK hour — inside the noise of a
   position meant to be held for up to 24.
3. **If profit protection is a hard requirement, make it wide, late, and never on
   SNDK** (option E's shape), as a new frozen identity with its own approval —
   and treat a volatility-scaled trail (a multiple of ATR rather than fixed bps) as
   the design worth preregistering next, since fixed-bps locks are tight on volatile
   names and loose on quiet ones by construction.
4. The giveback is real — $236 per 63 days on this roster — and it is the price of
   the tail, not a defect to be engineered out at the tail's expense. Budget it.

## 8. Additional asset

The 2026-09-20 breadth screen put the unlocked hourly mechanism on 18 new
growth-mode HIP-3 markets against a bar written before the results. **None
passed.** Any addition is therefore a position without validated edge, and should
be sized and described that way. Closest candidates, 52 days, measured / adverse:

| Market | Net | Blocks + | Under tight locks | Note |
| --- | --- | ---: | --- | --- |
| **xyz:TSLA** | +$25.29 / +$2.87 | **3/3** | hurt (−$12.60) | only new market positive in all three blocks; same "hurt by tight trails, fine unlocked" signature as SNDK and SOL; not semis, not oil |
| xyz:INTC | +$26.52 / +$5.25 | 2/3 | positive in all six arms | a second semiconductor name beside SNDK |
| xyz:CL | +$20.75 / +$2.84 | 2/3 | positive in all six arms | most liquid HIP-3 market, but a second crude contract beside Brent |
| xyz:GOOGL | +$33.53 / +$13.79 | 1/3 | ≈ 0 | one block carries it |

If one market is added, **xyz:TSLA at the screened $500 contract on the unlocked
v1 identity** is the most defensible: three of three blocks, positive at adverse
cost, a trend signature matching the two routes that work, and a different sector.
It failed the bar on one condition (net below time-in-market-scaled buy-and-hold by
$20.65), its t-statistic is 0.54, and it is the pick of 18 — **budget zero**. At
$500 the maximum loss at the 250 bps stop clamp is $12.50.

It is not a TOML edit. `HOURLY_PRICE_SYMBOLS` in
`src/hypervector/live/hourly_price_provider.py` must gain the symbol, with a
modelled friction contract and tests. That file currently carries another session's
uncommitted changes, and the prepared V90 package's fingerprint
(`b34fd819…25d2`), approval-draft hashes and test evidence were computed against it
— so it should be changed once, deliberately, together with whatever exit decision
is taken above, not underneath the prepared package.

## 9. Limits of this review

Candle-based conditional fills at a fixed $500; nothing here measures behaviour at
the proposed SNDK size. Lock exits fill at the next bar's open; live latency is not
modelled. Every window is a broadly rising tape that includes the 2026-09-17 → 19
rebound, which flatters trend-following and therefore flatters the no-lock arm —
in a range-bound regime a tight trail would look better than it does here. Sixty-three
days cannot establish forward expectancy for any arm. High confidence in the
arithmetic and in the ordering of exit families; low confidence in any forward
dollar figure.
