# V90 aggressive bankroll builder — strategy profile review and plan

> **September 21, later — option B adopted.** The 100/25/50 profit lock proposed
> earlier the same day was measured on the routes V90 funds and removed about two
> thirds of the result, essentially all of it on xyz:SNDK
> (`docs/reviews/2026-09-21-v90-profit-lock-exit-review.md`). The operator chose
> **option B: no profit lock on any route**, and added **xyz:TSLA** on the same
> unlocked hourly Donchian 20/10 contract at the screened $500 size. The protected
> `…_profit_lock_bidirectional_v2` identity stays in source, frozen and
> unconfigured. Current candidate fingerprint:
> `360de4e99df22b2766a891b034fe76fd58a95a7bf7b1dd77ef9f86dd4b8b6a22`.
> The earlier protected amendment and the fingerprint `b34fd819…25d2` are
> superseded. Trading is stopped and flat; the approval remains a refused draft.


> Operational corrections and the current sizing decision are in
> `docs/reviews/2026-09-20-v90-transition-readiness.md`. Earlier numerical tables
> are historical observations, not deployment acceptance or approval.

Date: 2026-09-20 (checkpoint `bidirectional-live-1789586105858`, last observed
10:29:05 UTC, equity **$4,875.18**). Scope: a deep historical review of the
whole `growth_first_5000` lineage and a concrete aggressive redesign of
`configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml`.

This document proposes no automatic gate and changes nothing. Every item is a
human decision needing its own explicit approval under `SRS_HV1_NO_GATES` and
`SRS_HV1_HONESTY`. It supersedes nothing; it extends
`docs/reviews/2026-09-20-v89-bankroll-builder-performance-priorities.md`.

> **§9 was added after the out-of-sample replay in Step 0.4 was actually run.**
> It changes one roster decision, retires one mechanism, corrects one claim in
> §4, and records a research/live parity defect. Read §9 before acting on §5.
> Evidence: `data/logs/research/bidirectional_cohort/v90_oos_replay_20260920_v1/`
> (`replay.json` plus `CORRECTIONS.md`, which must be read with it).

---

## 1. Bottom line

**The account is not under-sized. It is mis-allocated, under-scheduled, and
sitting on a liquidation geometry that costs money for nothing.** Those three
things are arithmetic, and fixing them is where the aggression belongs.

Three measured facts carry the whole plan:

| # | Fact | Number |
| --- | --- | ---: |
| 1 | Share of the notional budget parked on routes that produced ≤1 eligible signal | **80%** ($6,000 of $7,500 → 2 signals) |
| 2 | Uninterrupted entry cadence vs realized cadence across the full history | **3.06x** (5.18/day vs 1.69/day) |
| 3 | Liquidations removed by cutting leverage at a bound cap, same entries, same notional | **3 → 0** (+$42.21 → +$94.37) |

And one fact that constrains everything else:

> **There is no measured edge to lever.** The 20-close live block is
> mean return-on-margin +1.601%, **t = 0.3165, p = 0.755**, 95% CI
> **[-8.99%, +12.19%]**. Remove the three SNDK timer winners (88.1% of all
> gross profit) and it is -$70.53, PF 0.127, Kelly **zero**. Remove only the
> single largest winner and Kelly is still **zero**. Reduce the big-winner rate
> from 3-in-20 to 2-in-20 and the mean goes negative. The 144-close lineage is
> t ≈ 0.11. A bootstrap of the Kelly statistic puts **39.7% of its mass at
> exactly zero — "do not bet."**

So the aggressive plan is **not** "size up the edge." It is: stop paying rent on
dead capacity, run the machine more hours, remove the free downside, and put the
released capital behind the one route with both a non-negative mechanism and
rank-1 live evidence — while budgeting **zero expected return** and sizing off
the loss distribution, which is the well-characterized half of the sample.

That is still genuinely aggressive: **per-trade dollar exposure on the earning
book goes up ~2.1x immediately and ~3.9x on SNDK, with a written ladder to
~7x** — and the trade-count increase from improved uptime remains unvalidated.

---

## 2. Verified current state

```
equity                    $4,875.18        faults 0, polls 20,654, run healthy
closed lifecycles         21 (7W/14L)      net +$5.52, PF 1.068, fees $3.79, funding +$0.99
all-time lineage          144 closes       net -$324.46, PF 0.570
open right now            5 positions      BTC long, SOL short, SPCX long, SNDK short, Brent long
realized peak margin      $325.34 (6.67%)  peak notional $4,498.85 (0.92x equity)
max drawdown              0.403%
```

### Where the budget sits vs where the signals come from

| Route | Evaluations | Eligible | Cap | % of budget |
| --- | ---: | ---: | ---: | ---: |
| `hype_breakout_compression_alignment_v2 \| HYPE` | 5,279 | **0** | $2,500 | 33.3% |
| `liquidity_sweep_long_1h_v2 \| BTC` | 88 | **1** | $2,500 | 33.3% |
| `eth_range_onset_long_dual_mtf_v2 \| ETH` | 5,279 | **0** | $500 | 6.7% |
| `sol_range_onset_short_dual_mtf_v2 \| SOL` | 5,279 | **1** | $500 | 6.7% |
| `hourly_band20_reentry_atr20_v1 \| xyz:SPCX` | 352 | 4 | $500 | 6.7% |
| `hourly_donchian_20_10_atr20_v1 \| xyz:SNDK` | 352 | 6 | $500 | 6.7% |
| `hourly_donchian_8_4_atr20_v1 \| xyz:BRENTOIL` | 352 | 6 | $500 | 6.7% |

**$6,000 of the $7,500 budget (80%) serves 2 eligible signals. $1,500 (20%)
serves 16.** Every one of the seven assets is `cap_binding: true`, which also
means the book does **not compound**: `planned_notional = min(equity ×
margin_fraction × leverage, max_notional_usd)` saturates at every equity above
$3,125, so position size has been frozen since well before launch.

---

## 3. What survived verification

Eleven load-bearing claims were put through adversarial verification against the
primary artifacts. Four survived in usable form.

### 3.1 Dead capacity is real and releasing it is free

80% of budget, 2 signals. HYPE is blocked in 5,279 of 5,279 evaluations;
ETH's `awaiting_hourly_sma_cross` appears in 100% of its blocked rows, so
relaxing its regime gate alone unblocks exactly zero. These are not routes
waiting for a regime — they are structurally silent.

The `equal-cap` study is the repo's own version of this finding, and it is
weaker than advertised: its "36 comparisons" are one deterministic rescale of
one window (equal_net = Σ control_asset_net × cap_ratio, verified to 2.27e-13),
its ex-top-3-winners result is **+$0.27**, and under its own preregistered
primary (adverse cost) its later window is **-$52.43**, not positive. But the
per-asset attribution underneath it is sound: **94% of its improvement and
105.5% of its net come from SNDK, SPCX and Brent.** Raising ETH's cap is
refuted outright — it is the only negative contributor.

### 3.2 Uptime is the largest honest multiplier in the book

| | Rate |
| --- | ---: |
| Current uninterrupted run (3.666 days, 19 enters) | **5.18 enters/day** |
| Full compatible history (12.418 days, 21 closes, 6 runs + a 3-day outage) | **1.69 closes/day** |
| Ratio | **3.06x** |

The 3.06x ratio is descriptive, not a measured causal multiplier: it compares
entries with closes across unequal windows. A matched event/window comparison is
required before forecasting additional trades from improved uptime. There
is **zero alerting code anywhere** in `src/hypervector/live/` (no
webhook/telegram/smtp/notify match), only `.disabled`/`.backup` plists in
`~/Library/LaunchAgents`, and a single-account runtime lock that makes a silent
death indistinguishable from a healthy idle. A further **27.8% of eligible
intents (5 of 18)** are withheld as `same_direction_position_open`.

Restoring uptime without changing execution parameters preserves nominal trade
sizing. The resulting trade count, aggregate exposure and P&L remain unverified.

### 3.3 Leverage at a bound cap is pure downside, and cutting it is free

`maintenance_rate = 0.5 / venue_max_leverage`; liquidation distance
`= 1e4 × (1/L − mr)/(1 − mr)`, independent of notional.

| Asset | Stop | Current | Cushion | At 8x | Cushion |
| --- | ---: | ---: | ---: | ---: | ---: |
| xyz:SNDK | 250 bps | 10x → 526.3 bps | **2.11x** | 789.5 bps | 3.16x |
| xyz:SPCX | 250 bps | 10x → 769.2 bps | 3.08x | 1,025.6 bps | 4.10x |
| xyz:BRENTOIL | 250 bps | 10x → 769.2 bps | 3.08x | 1,025.6 bps | 4.10x |
| SOL | 60 bps | 15x → 427.4 bps | 7.12x | 1,025.6 bps | 17.09x |
| BTC | 60 bps (route) | 20x → 379.7 bps | 4.75x | 10x → 1,139.2 bps | 14.24x |

Two independent judges reproduced the consequence on identical entries and
identical $500 notional (8-asset D20/10, adverse, continuous):
**10x → 3 liquidations, +$42.21; 8x → 1 liquidation, +$67.93; 6x → 0
liquidations, +$94.37.** Lower leverage requires more posted margin for the same notional and moves the
modeled liquidation boundary further from the stop. That collateral cost is real.

The inverse is the trap: **raising** `leverage` while caps bind adds no size at
all. At 20x, xyz:SPCX and xyz:BRENTOIL liquidate at 256.4 bps against a 250 bps
stop clamp — **cushion 1.03x, the stop sits on the liquidation boundary.** That
is precisely the v70 failure mode that produced 17 HYPE liquidations.

### 3.4 HIP-3 cost advantage is real but is a revocable subsidy, not structure

Measured on 55 HIP-3 fills spanning 0.00036 bps: **0.864 bps/side** vs
**4.32 bps/side** on core perps, ratio exactly 5.000. Confirmed live by a
private xyz:SNDK fill at 2026-09-20T03:00:14Z.

But the framing in the source material is backwards. HIP-3 at
`deployerFeeScale = 1.0` **without** growth mode is **8.64 bps/side — twice core
perps.** The 5x is a 10x discretionary discount granted by a third-party
deployer on a structurally 2x-worse base. Losing it is a **10x** cost event with
a **30-day minimum duration** (the cooldown prevents reversal), and
`deployerFeeScale` can reach 8.64 bps/side on its own **with no documented
cooldown at all**. Route new notional to HIP-3 on cost — correct — but do not
build a plan that requires the subsidy to persist.

*(Correction to the source material: "GOLD is permanently ineligible" is not
supported. The venue doc's gold clause is conditional, inside an explicitly
non-exhaustive list, adjudicated by validator vote. The repo's own status is
`unresolved_growth_mode`.)*

---

## 4. What I checked and rejected

These are the obvious aggressive moves. Each was verified against primary
artifacts and each failed. Listing them matters more than the plan, because
they are the moves a reasonable person would make next.

| Move | Verdict | Why |
| --- | --- | --- |
| **Add SOL hourly Donchian 20/10** ("+$89.31, PF 1.63, only route that strengthened") | **Downgraded to a dead-slot swap at unchanged size** | It is 18th of 216 cells, not 2nd. **8 of 24** routes flipped negative→positive in the later window — a market-wide effect (SOL ran +39.9%), not an edge. Development partition was **-$31.48, PF 0.556**. Ex-top-3 is **-$48.12**. It **underperforms buy-and-hold** ($124 vs ~$199). It contains a **liquidation** at 10x inside the "good" window. It was on the table at roster selection and was declined. |
| **Switch or add SNDK Donchian 8/4** (+49% trades) | **No** | Net is *lower* ($117.70 vs $120.85), PF lower, expectancy/trade **35% lower**. 8/4's entire result is 11 days of July (Jul +198.32 / Aug -64.45 / Sep -16.18); 20/10 is positive in **all three months**. Adding is physically impossible — one position per symbol, so 53% of the second provider's intents become withheld. |
| **Extend the SNDK hold** (`extend_while_regime_supported`) | **No — it is a mechanical no-op** | The checkpoint already recorded the computation: `structure_alignment_score = 0.2222` against `threshold = 0.5` at **both** winners' 24h boundaries. Two in-tree observers agree (`extend: 0, exit: 2`). It would have closed both winners anyway, at the cost of 4 touchpoints including a sha256-frozen artifact. Also: one of the three "timer wins" was the **96.724-hour outage**, not a timer. |
| **Per-route profit lock on Brent** (+81 to +90 bps) | **No** | Across all 9 eligible lifecycles the lock's delta sign is **perfectly determined by the trade's own outcome sign (9/9)**. "Brent yes, SNDK never" is arithmetically "lock the trades that are about to lose." n = 3 triggers, one run, short side only. Post-lock Brent is still PF 0.64–0.88. It also cannot ship — `hourly_price_contract.py:34-38` requires `profit_lock_policy == "none"`. |
| **Port `btc_hulk_delayed_component_exit_v2`** ("positive in all four partitions") | **No** | Three partitions, not four — cost-stress is validation+pseudo-holdout re-costed (same 27 entries, same 6 triggers). Out-of-development is **n = 6, t = 0.096**. "Improves leave-largest-winner" is an arithmetic tautology (it never touches the largest winner); the real sensitivity flips 3 of 4 negative. The repo **already tested this port on the sibling route and rejected it**. It is a loss-cutter that decapitates winners at ~-$120 each. |
| **Give the regime detector a size or filter role** | **No** | `regime_strength_score`, `ema_21_55_gap_abs` and the RANGE split are **one variable triple-counted** — RANGE is *defined* as low EMA-gap percentile. On identical rows a plain **ATR14 scores daily IC 0.3595 against the engine's 0.1765**; the engine is a strictly worse estimator of the thing it is credited for. The live counterfactual turns +$5.52 into **-$4.33** (proportional) or **-$15.57** (rank-scaled). Direction is falsified 0/32. **19 of 20 live closes are on HIP-3 assets that appear in no regime validation anywhere.** |
| **Add xyz:SKHX / SILVER / MU / CL / SP500 / XYZ100** | **No capital** | SILVER's own forward test **fired its preregistered falsifier**: 10 signals, 60m mean **-26.12 bps**. SKHX's "+25.98 bps prospective" is **n = 1**, and the two data transports **disagree that the trade existed** (archive imbalance 0.3998 → ineligible; observer 0.6498 → eligible; parity unresolved). Every SKHX entry-parity artifact reports **zero entry events**. All carry `out_of_sample_economics: WITHHELD_NOT_EVALUATED` and status `NOT_SUITABLE_TECHNICALLY_UNRESOLVED`. Growth-mode captures are 36–40 days stale. |
| **Raise leverage toward venue maxima** | **No** | See §3.3. At bound caps it adds zero size and collapses the liquidation cushion to 1.03x on SPCX/Brent. |

### The pattern behind all of it

- **0 of 24** adverse/continuous screen cells are positive after removing each
  cell's top three winners. Not one.
- Ranking cells by the development window **anti-predicts** the extension
  window: **Spearman = -0.56**.
- 2 of 24 cells are positive in both windows against **2.50 expected under pure
  independence** — the "positive in both windows" filter carries *literally zero
  information*, and it is the filter that justifies SPCX band20 and Brent D8/4.
- The only **statistically significant** result in the entire 216-cell screen is
  the band-20 mechanism aggregate: **n = 472, -$512.85, t = -3.07.** It is
  significantly **negative**, and xyz:SPCX is its in-sample argmax survivor.

---

## 5. The plan

### Step 0 — today, no transition, no approval, no capital at risk

Nothing here touches the live profile. All of it is free and all of it makes the
next decision better.

1. **Restart the roster observer.** `data/runtime/research/hip3_roster_latest.json`
   is stamped 2026-09-13T22:59:05Z — **7 days stale, with no process running
   while the engine is armed**, and the TUI is displaying that stale file. The
   growth-mode cost channel does not currently exist.
   ```bash
   uv run python scripts/hip3_roster_observer.py \
     --output data/runtime/research/hip3_roster_latest.json --poll-seconds 120
   ```
2. **Extend post-exit telemetry horizons.** One line, report-only,
   `execution_authority: none` — it cannot gate, size, route or close.
   `src/hypervector/research/cohort_trade_reflections.py:46`:
   `_DEFAULT_HORIZONS = (5, 15, 30, 60)` → `(5, 15, 30, 60, 240, 1440)`.
   The identical machinery already runs `(240, 720, 1440, 2880)` at line 47 off
   the same candle map, and the candles are already resident. This converts the
   24-hour-clock question from an argument into a reported number.
   *Preview of what it will show:* at 1440 minutes past exit, the two SNDK
   winners are **1W/1L** — one left **+927 gross bps (+$46.22)** on the table,
   the other **-107.92 bps**. Not the timer's 2-0.
3. **Root-cause the maximum-hold controller defect.** Lifecycle
   `xyz:SNDK:542326864971` ran **348,204,944 ms = 96.724 hours** against an
   86,400 s contract and is **absent from `audit.maximum_hold_decisions`
   entirely**. That is a live risk defect independent of any outage, and it is
   the only reason the "3W/0L timer" record exists in its current form. It is a
   hard prerequisite for any size increase.
4. **Score the roster on the untouched out-of-sample tape.** This is the single
   highest-value free action available and nothing in the repo has used it:
   - `data/logs/research/bidirectional_cohort/v89_native_candle_portfolio_20260914_v1/`
     — contiguous 1-minute bars, 7 of 8 screen symbols, 2026-09-08 00:31 →
     2026-09-13 11:59 UTC, 7,691–7,889 rows each.
   - `data/live/bidirectional_cohort/startup_inputs/1d65089.../candles-00{0..6}.parquet`
     — same 7 symbols, 2026-09-13 → 2026-09-16 19:27 UTC.
   - The frozen screen inputs **stop at 2026-09-06 23:45 UTC.**

   That is ~8.5 days of tape written *strictly after every selection decision in
   this repository*, on exactly the symbols in question, for unrelated purposes.
   Resample to 15m and point the existing replay at it. Eight days settles
   nothing and must not be called proof — but every alternative is a fifth dip
   into an exhausted window.
5. **Roll the development/extension boundary date.** Every "positive in both
   partitions" claim rests on one fixed date, 2026-08-18. Sweep it across ~20
   candidate dates and the 1-bit statistic becomes a distribution.
6. **Profile HIP-3 depth at the sizes actually intended.** At this original review,
   it had not been done; the subsequent corrected transition review now reports
   $500/$1,950/$2,600/$3,500 results, with a 45-day-old archive limitation. The CLI's
   default notionals are 25/50/75 USD. SNDK's p99 visible-depth exit cost is
   **34.31 bps at a $750 clip** (43,751 samples) — that tail is the one genuine
   liquidity constraint in the book and it sits below the proposed size.
   ```bash
   uv run python -m hypervector research-hip3-liquidity-profile \
     --database data/research/hip3_market.duckdb --symbol xyz:SNDK \
     --notional-usd 1000 --notional-usd 2000 --notional-usd 3500 \
     --sample-minutes 5 \
     --output data/logs/research/xyz_sndk_v90_depth_profile.json
   ```

### Step 1 — the V90 transition

The original proposal was to batch **everything** into one transition. The
corrected recommendation separates authorized V89 operational maintenance from
the pending V90 allocation decision. Each source/profile transition costs a drain-to-flat of all
open positions, a prestart backup, one drain archive, an approval JSON, a
~910 MB bundle and ~13 minutes of startup across three validated passes over a
5.84 GB ledger. At the original 10:29 UTC snapshot the book held **5 open positions** including a SOL
short on a 172,800 s contract, so plan the drain accordingly.

**Supervisor technical acceptance requires an induced-kill test using an isolated,
disarmed observe process and persistent-budget tests.** This does not approve
increased exposure. Restart only after verified venue and ownership reconciliation;
alert on heartbeat age; keep the overdue-max-hold close on restart.

#### The V90 roster

| Symbol | Strategy | Sides | Lev | `margin_fraction` | `max_notional_usd` | Notional @ $4,875 | Margin | Rationale |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| **xyz:SNDK** | `hourly_donchian_20_10_atr20_bidirectional_v1` | both | **8** (↓10) | **0.050** (↑0.02) | **2600** (↑500) | **$1,950** | $243.75 | Only route with a non-negative mechanism aggregate (+$42.21, n=339), rank 1 of 34 live routes, and **positive in all three calendar months**. This is where the size goes. |
| **xyz:SPCX** | `hourly_band20_reentry_atr20_bidirectional_v1` | both | **8** (↓10) | 0.015 | 800 | $585 | $73.13 | 4 eligible signals. Its mechanism is the only significant result in 216 cells and it is **negative at t = -3.07**. Hold near current size. **Do not scale.** |
| **xyz:BRENTOIL** | `hourly_donchian_8_4_atr20_bidirectional_v1` | both | **8** (↓10) | 0.015 | 800 | $585 | $73.13 | 6 eligible signals; mechanism aggregate -$259.08. Hold. **Seal opens 2026-09-22 04:00 UTC — decide the mechanism after, not before.** |
| **SOL** | `hourly_donchian_20_10_atr20_bidirectional_v1` *(swap)* | both | **8** (↓15) | 0.013 | 700 | $507 | $63.38 | Dead-slot swap only (1 eligible in 5,279). **Budget zero, not +$89.** Requires deleting `execution_side_overrides = { SOL = ["short"] }`. |
| **BTC** | `liquidity_sweep_long_1h_stop60_target60_v2` | long | **10** (↓20) | 0.011 | 700 | $536 | $53.63 | 1 eligible in 88. It paid **$2.15 — 56.7% of every fee the book has ever paid — on one trade that lost $17.72**. Cap cut ~5x. |
| **ETH** | `eth_range_onset_long_dual_mtf_v2` | — | — | — | — | **observe-only** | — | `execution_symbols = []`. 0 eligible in 5,279; `awaiting_hourly_sma_cross` in 100% of blocked rows. Keeps the evidence at zero cost. |
| **HYPE** | `hype_breakout_compression_alignment_bidirectional_v2` | — | — | — | — | **observe-only** | — | `execution_symbols = []`. 0 eligible in 5,279; negative in all nine of its own screen cells. |

```
total notional at full occupancy   $4,163   = 0.854x equity
total margin at full occupancy     $507     = 10.4% of equity
earning routes (SNDK+SPCX+Brent)   $3,120   vs $1,500 today  = 2.08x
xyz:SNDK alone                     $1,950   vs $500 today    = 3.90x
all-open stop wave at 250bps clamp $85.33   = 1.75% of equity
all-open wave at measured mean loss $55     = 1.13% of equity  (worst observed: 2.13%)
```

Note this is **less gross notional than today's $7,500 cap** — because $6,000 of
that cap was never deployable. What matters is that the deployed book doubles
and SNDK quadruples.

#### Two structural changes that come with it

1. **Caps set ~1.3x above the formula value so they stop binding.** Today all
   seven bind, which is why the book has never compounded. Set this way,
   `equity × margin_fraction × leverage` is the binding term and **position size
   grows with equity automatically** — for the first time in the lineage.
   ⚠️ `max_notional_usd` must be raised in the `[[assets]]` block. Raising only a
   provider `sizing_overrides` value trips a fail-closed `SolLiveEngineError` at
   `sol_range_onset_execution_plan.py:67-70`, and the adapter enforces the asset
   value a second time at `hyperliquid_btc_adapter.py:137`.
2. **Add `maximum_aggregate_margin_fraction` as a load-time assertion** in
   `multi_asset_live_config.py::_validate_config`. Today **no portfolio-level
   notional, margin or exposure cap exists anywhere in the live path.**
   `bidirectional_intents.py:211` tests only `open_count`, and
   `maximum_positions` is validated at `:493-499` as a **floor** (must be ≥ the
   executable symbol count), so it can never bind — `portfolio_position_capacity`
   occurs **0 times in 5.83 GB of `decisions.jsonl`**. The only risk control
   between a hand-edited `margin_fraction` and a collateral shortfall is the
   operator's arithmetic. This is a config assertion in the same class as
   `leverage <= venue_max_leverage`, not a runtime trade rejection, so it is
   `SRS_HV1_NO_GATES`-clean. Set it to **0.25** initially.

Also: `market_slippage_cap_fraction` is a **required** `[[assets]]` field. Set it
deliberately per route — SNDK's 34.31 bps p99 depth tail argues for raising it
on that route specifically.

### Step 2/3 — the ladder

Escalate `margin_fraction` on **xyz:SNDK only**. SPCX and Brent do not scale
until their own evidence changes.

| Rung | `mf` | Margin | Notional @8x | Stop risk | 3-open agg. margin | Mean wave | Worst wave |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 (today) | 0.0103 | $50 | $500 | 0.26% | 3.1% | 0.33% | 0.63% |
| **R1 = Step 1** | **0.050** | **$244** | **$1,950** | **1.00%** | **15.0%** | **1.63%** | **3.07%** |
| R2 | 0.070 | $341 | $2,730 | 1.40% | 21.0% | 2.28% | 4.30% |
| R3 | 0.090 | $439 | $3,510 | 1.80% | 27.0% | 2.93% | 5.53% |

*(Waves use the measured losing distribution: n = 13, mean ROM -10.84%, worst
-20.50%. The 250 bps clamp figure is the contractual maximum, not the observed
loss.)*

**Advance a rung only when ALL of these hold** — written down in advance, so it
is an operator contract and not a performance gate:

1. ≥ 40 new book closes **and** ≥ 8 new closes on xyz:SNDK since the last size change.
2. Zero unexplained faults, zero order rejections, no undetected outage > 30 min,
   supervisor alive, roster observer alive, growth mode intact.
3. Equity at the step is **at or above** equity when the current rung started —
   the rung must have paid for itself.
4. **Net excluding the interval's three largest winners is better than minus
   half the current rung's all-open stop wave.** Given that 0 of 24 screen cells
   survive that operation, this is the only forward test that discriminates.

**Step down one rung** on: -12% from the rung-start high-water mark; any
liquidation; any measured xyz fill above 1.5 bps/side against the
0.863642–0.863999 baseline; `growth_mode != enabled` or `deployer_fee_scale != 1.0`
on any roster symbol; or any undetected outage > 30 minutes.

Do **not** step down on low trade count. The one verified growth lever in this
repository *cuts* trade count while raising $/day; a cadence-based kill rule
would shoot the winning geometry on sight.

### Honest expectation

**Budget zero.** The point estimate of edge is zero, not positive. Under a
nested bootstrap that includes parameter uncertainty — the honest version —
**P(growth rate ≤ 0) is 40–45% at every sizing level**, and at R1-equivalent
risk P(drawdown ≥ 25%) is roughly **25%**. What R1 buys is not expected return;
it is a position from which a real edge, if one exists, produces a material
dollar result instead of $30/month. If the edge is not real, R1 loses about
2–3x faster than today, which is the trade being made deliberately.

*(For calibration on why the seductive number is wrong: the "half-Kelly = 18.5%"
framing is not merely optimistic, it is **unexecutable** — f × 7 concurrent
positions is 129.5% of equity in margin.)*

---

## 6. Direct answers to the questions asked

**Regime detector.** Use it for nothing with execution authority — not sizing,
not filtering, not stop width. It is a weak, redundant volatility estimator that
a 14-period ATR already beats at its own task (IC 0.3595 vs 0.1765), its
direction signal is falsified 0/32, the live counterfactual destroys the book,
and 19 of 20 live closes are on assets it has never been validated on. The three
hourly routes **already run ATR20 stops** — if you want volatility-scaled
aggression, the lever is the ATR multiple, not the regime engine. Leave it as
report-only telemetry and conflict tie-break, which is what its own authority
contract requires.

**Adding assets.** No. Every candidate's out-of-sample economics read
`WITHHELD_NOT_EVALUATED`, SILVER's forward falsifier has already fired, SKHX has
zero entry events in every parity artifact, and adding any of them to the
deployed engine requires editing `HOURLY_PRICE_SYMBOLS` — which the 216-cell
screen never covered, so the added expectancy would be entirely unmeasured. The
breadth play is real in principle and is the right *future* direction; it is not
ready, and buying it now is buying unmeasured routes at size, which is exactly
the v51 failure.

**New strategies.** No new mechanism is warranted. Of the three in the screen,
two have significantly or substantially negative aggregates (band20 t = -3.07;
D8/4 -$259.08) and one is indistinguishable from zero (D20/10 t = 0.146). The
one change worth making is the SOL dead-slot swap, budgeted at zero.

**Timeframes.** Do not shorten anything. Across the same 8 assets and 48 days:
20/10 = 339 trades, +$42.21; 8/4 = 572 trades, **-$259.07**; band-20 = 472
trades, **-$512.84**. Every sub-hourly family ever tested here was rejected
against its friction hurdle. Frequency must come from **uptime and breadth**,
never from channel length.

**Position amounts.** §5, R1: SNDK to $1,950 notional / $243.75 margin (3.9x),
SPCX and Brent to ~$585, ETH and HYPE to zero, BTC cut ~5x. Caps set above the
formula so the book finally compounds.

**Leverage.** Down, not up. SNDK/SPCX/Brent 10x → 8x, SOL 15x → 8x, BTC 20x →
10x. At a bound cap leverage buys zero notional and only moves the liquidation
price toward the stop.

---

## 7. What would change this

- **The Sep 22 04:00 UTC SNDK/Brent seal** and the **Sep 23 / Oct 7** blocks.
  Read them; do not open them early and do not select a favourable sub-window.
- **The out-of-sample replay (Step 0.4).** If the roster is negative on tape
  written after every selection decision, R1 should not be taken at all.
- **The extended post-exit horizons (Step 0.2).** If the 1440-minute
  distribution is materially positive across most lifecycles, the hold question
  reopens — properly, on measured data rather than on two trades.
- **Any `growth_mode` or `deployerFeeScale` change.** At 8.64 bps/side the
  48-day book goes from +$95.72 to **-$33.44** and Brent is unprofitable
  outright. The 30-day cooldown means that state lasts a month minimum.
- **A fourth SNDK timer winner, or the absence of one.** One fewer big winner in
  twenty flips the entire result. This is the single most informative
  observation the next block can produce.

## 8. Confidence

High confidence in the recorded arithmetic, the code facts, the liquidation
geometry, and every refutation in §4 — all recomputed from primary artifacts.
Medium confidence that releasing dead capacity and fixing uptime are the right
first moves; they are the two changes that do not depend on an edge existing.
**Low confidence in any forward return, at any sizing.** The measured edge is
not distinguishable from zero and the whole live result is three trades on one
route, one of which was an outage artifact. This document proposes no live
change and is not an approval record.

---

## 9. Out-of-sample replay — run 2026-09-20

Step 0.4 was executed. Unsigned public Info reads captured 15m bars and hourly
funding for **2026-09-07T00:00Z → 2026-09-20T00:00Z** (1,248 bars + 312 funding
rows per symbol, 8 symbols, complete chronology). The frozen selection screen
ends **2026-09-06T23:45Z**, so no bar used here existed when the roster was
chosen. Three mechanisms × 8 symbols × 3 costs, plus hold and leverage sweeps.

**Two validations before any number was used.** Pointing the same replay code at
the *frozen* inputs reproduced **210 of 216 published screen cells to the cent
and to the trade count** (the 6 misses are all xyz:SP500 band20, identical trade
counts, differing by $0.019). And matched against the live ledger, **19 of 20
live trades on replay routes correspond to a replay trade with entry time
identical to the minute**, direction 19/19, P&L sign 19/19, median difference
+$0.50 in the direction of replay conservatism. The engine is sound.

### 9.1 What the window was

This matters more than any cell. Entries 09-07 → 09-16: **n=72, −$90.87.**
Entries 09-17 → 09-19: **n=14, +$198.45.** The 8-symbol mean price fell 4.75%
over the first ten days and rose 7.75% over the last three. **It is one V-bottom,
and the result is the rebound.** Longs n=40 +$131.15; shorts n=46 −$23.58.

Against a naive always-long position at the same notional and cost model,
D20/10 on all 8 symbols returned **+$107.58 versus +$101.92**. The entire
measured value of the breakout geometry over buying and holding is **$5.66 over
13 days.** Exposure-matched, roughly one third of the P&L is signal and two
thirds is long beta captured inside the windows the mechanism occupied.

Separately, the live process was **dark for 169.45 of 312 wall-clock hours
(54%)** across six runs, so **60% of the replay's trades entered while the book
could not have taken them.**

### 9.2 The one result that survives

| Mechanism | In-sample 48d | OOS 13d | Symbols + | Verdict |
| --- | ---: | ---: | ---: | --- |
| D20/10 | +$42.21 | +$107.58 (n=86) | 6/8 | not distinguishable from zero (p=0.162; 0.294 screen-adjusted) |
| D8/4 | −$259.08 | −$3.49 (n=143, warmup-corrected) | 3/8 | indistinguishable from D20/10 (p=0.414) |
| **band20** | −$512.85 | **−$322.55 (n=123)** | **0/8** | **retire** |

**band20 is the only conclusion that clears a real evidential bar.** Pooled
against D20/10 with labels permuted within symbol, p = **0.0019**; all three
bootstrap schemes put P(net ≤ 0) ≥ 0.9999.

It is **not** a regime artifact. The OOS window was equal to or *less* trending
than in-sample on 8 of 9 measures (Kaufman efficiency 0.0262 vs 0.0530; drift
18.7 vs 44.8 bps/day; RANGE fraction 0.242 vs 0.262), and band20 lost at a
statistically identical rate in the near-driftless development window
(17.9 bps/day drift) and the 4.6× more directional extension window
(82.8 bps/day). The defect is structural: its exit is capped at the band mean
while its stop is not capped symmetrically, so it needs a **59–66% hit rate
against a realised 41–50%**. Across 622 resolved signals in three windows it
never beat its own random-walk fair hit rate.

Precise wording matters here: cost-free pooled expectancy is **−9.23 bps/trade,
t = −1.59, p = 0.113**. The claim is *no demonstrated gross edge*, not *negative
gross edge*. Costs convert zero edge into a reliable loss.

### 9.3 Roster change

**xyz:SPCX moves to observe-only — because its mechanism leaves, not because the
symbol failed.** SPCX is the one symbol whose band20 behaviour did *not* break
out-of-sample: its probability of reaching the band mean before its stop exceeded
random-walk fair in **all three** windows (+0.110 / +0.116 / +0.042). Its OOS
−$4.83 is friction, not edge collapse. On SPCX, band20 is nominally the **best**
of its three mechanisms (band20 −$4.83, D20/10 −$10.21, D8/4 −$15.32; and
D20/10 on SPCX is −$64.57 in-sample and **0 of 3 windows positive**).

So: **do not route SPCX to D20/10.** Set `execution_symbols = []` and keep the
evidence at zero capital cost. This also preserves whatever the 2026-09-22 and
2026-09-23 seals have to say about it.

The §5 roster is otherwise unchanged, with two labels corrected:

- **xyz:BRENTOIL → D20/10**: take it as a *consequence of standardising on one
  mechanism*, and label it **untested**. The contrast is p = 0.520, the
  corrected D8/4 aggregate is only −$3.49, and Brent's D20/10 cell is ~60%
  funding carry — a passive long beat it there by $26.04, of which $22.43 was
  funding received.
- **SOL → D20/10**: upgraded from "dead-slot swap, budget zero" to the best
  D20/10 cell out-of-sample (+$46.27) and second-best pooled over 61 days
  (+$135.58, 2/3 windows). Still size it at the screened $500 contract and still
  budget zero: it is rank 1 of 8, and **two thirds of the entire roster
  improvement is this one symbol swap**, which no mechanism test can validate.

### 9.4 Corrections to this document

- **§4's "cell selection anti-predicts (Spearman −0.56)" stands, and my initial
  reading of the replay as refuting it was wrong.** The −0.56 reproduces exactly
  (dev→ext pooled ρ = −0.559, p = 0.0045). The +0.473 I computed is a *different
  window pair* (continuous 48d → OOS 13d, p = 0.020, and only +0.413 once
  mechanism level is removed). Both are true. Rank persistence **flips sign
  between windows**, which makes per-symbol screen rank unreliable in *either*
  direction — a weaker and more useful statement than either figure alone.
- **"0 of 24 cells positive ex-top-3" is near-uninformative at these trade
  counts and should not be used to rank rosters.** Resampling 11-trade cells:
  with a *true* edge of $5.00/trade — four times what D20/10 showed —
  P(ex-top-3 < 0) is still **0.569**; at zero edge it is 0.973. Zero-of-24 is the
  expected outcome for a genuinely profitable strategy at this sample size. The
  roster-level figures also summed *per-cell* ex-top-3, removing 24 of 86 trades
  from one roster and 9 of 46 from another. Under one pooled rule the ordering
  changes. This applies to the in-sample finding in §4 as well.
- **The leverage cut (10x → 8x) has no out-of-sample support.** D20/10 and D8/4
  are bit-identical at 6x/8x/10x; the single liquidation in 357 trades was
  band20 on Brent, on the mechanism being retired, and it is priced with
  `liquidation_slippage_bps = 0.0`. The §3.3 argument is *arithmetic* — a wider
  liquidation buffer for the same notional — and it remains valid as a stated
  risk preference. It is not an empirical finding, and at a bound cap it raises
  margin posted per slot rather than reducing exposure.
- **The hold extension is retracted before it was ever proposed.** §4 rejected
  `extend_while_regime_supported` as a mechanical no-op; the replay's apparent
  48h gain is also not real. Entries are *not* identical across hold arms
  (D20/10 goes 86 → 71 → 70 trades), the sign-flip test gives p = 0.275, the
  curve has an interior maximum, and on SNDK the entire gain is one trade
  re-slicing a rally the live book had already banked as two 24-hour trades.

### 9.5 A research/live parity defect worth fixing

`build_donchian_atr_breakout_signals` has **no finite-ATR gate**, unlike its
sibling `build_hourly_band_reentry_signals` (`hourly_band_reentry.py:82`,
`warmed = adjacent & np.isfinite(atr)`). When `entry_channel_bars < atr_period`
— the 8/4 variant against ATR(20) — entries fire during warmup with
`stop_price = NaN`, and `evaluate_shared_bar_portfolio` runs them **with no stop
and no target**. Nine such signals occur in the OOS window, all on 8/4.

**Live capital is not at risk.** `hourly_price_provider._evaluation` sets
`eligible = side is not None and ready and stop is not None` and `_intent` raises
on a non-finite stop, so the live engine refuses exactly these decisions. The
published frozen screen also escaped, because its bars start 2026-07-19 while
every scored window starts 2026-07-21 — incidental protection, not designed.

But it is a genuine defect: **the backtester is more permissive than the engine
it is meant to model.** Any future mechanism with a shorter entry channel than
its ATR period will be scored on trades the live system would refuse. Fix by
adding the band20-style gate, or by rejecting NaN-stop entries in the portfolio.

### 9.6 What the replay licenses, and what it does not

**Licensed:**
1. Retiring band20, and with it moving xyz:SPCX to observe-only.
2. A ceiling on ambition: the whole 8-symbol D20/10 result is +2.21% of equity
   over 13 days, its lower CI bound is negative, and its edge over buy-and-hold
   is $5.66.
3. A schedule: **~106 days** of tape at the current 6.6 trades/day to settle
   D20/10 at 80% power if its edge is real at the observed level; **~425 days**
   at half that.

**Not licensed — most importantly, any size increase.** The replay never varied
size: **every one of the 357 published trades has `notional_usd` exactly
500.0.** There is zero evidence in this artifact about behaviour at larger size,
and the one adverse-size event it contains is under-priced at 0 bps liquidation
slippage. The §5 sizing ladder therefore still rests on the §3.1 dead-capacity
argument and the §5 loss-side budget — not on this replay.

### 9.7 One protocol change

Add to the research protocol: **every mechanism cell reports net alongside (a)
buy-and-hold at the same notional over the same window and (b) an
exposure-matched always-long benchmark over the same holding windows.** Without
those two columns a trending-window result is not evidence of skill — this
replay would have read as a 10x improvement without them, and it is $5.66. This
is a reporting requirement, not an abort condition, so it is
`SRS_HV1_NO_GATES`-clean.

---

## 10. Supervisor, V90 candidate, and the expansion screens — 2026-09-20

The operator's direction after §9: proceed, and keep it aggressive — frequent
trades, more strategies, more assets, more scalping. This section records what was
built and what the "more trades" hypotheses measured when they were actually run.

### 10.1 Supervisor — built, tested, not installed

`scripts/cohort_backend_supervisor.py` (stdlib only, outside `src/hypervector` so
it cannot perturb the live implementation-source identity and cannot import an
execution client). The initial version had 26 tests, including an **induced-kill acceptance test that
drives a disposable stub child through a real `SIGKILL`** → relaunch → operator stop.
That initial count is historical. The implementation acceptance report records
the expanded regression suite and production observe-entrypoint experiment.

A read-only `status` against the live system on 2026-09-20T12:55Z returned:
backend pid 83722 alive, heartbeat 1.3 s, checkpoint 82 s, maximum HIP-3 fill fee
0.864 bps, and exactly one problem — `roster_observer_stale` (568,563 s).

Restart table, install steps, acceptance procedure and rollback:
`docs/proposals/v90-supervisor-20260920/deployment-and-rollback.md`. Three
LaunchAgents are generated and `plutil`-clean but **not loaded**. The supervisor
agent ships `--adopt --adopted-exit-policy hold`, so loading it does not touch the
running backend.

### 10.2 V90 candidate profile — loads clean, inactive

`configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml`,
fingerprint `2b7a026b…698f`. Loads in observe **and** live mode against the real
validators. Four negative controls are correctly refused (48h hold on an hourly
route; SNDK at 12x; unlisted `xyz:MU`; hourly route on a 5m timeframe).

| Symbol | Route | Lev | `mf` | Cap | Notional @ $4,875 | Margin | Cap binds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| xyz:SNDK | D20/10, both sides | 8 | 0.050 | 2,600 | **$1,950** | $243.76 | no |
| xyz:BRENTOIL | D20/10 *(was D8/4; untested, p = 0.52)* | 8 | 0.015 | 800 | $585 | $73.13 | no |
| SOL | D20/10 *(was range-onset short)* | 8 | 0.013 | 700 | $507 | $63.38 | no |
| BTC | liquidity sweep long | 10 | 0.011 | 700 | $536 | $53.63 | no |
| ETH / HYPE / xyz:SPCX | unchanged providers, `execution_symbols = []` | — | — | — | observe-only | 0 | — |

Executable book **$3,578 notional (0.73x equity), $434 margin (8.9%)**. No
executable cap binds, so position size follows equity for the first time in the
lineage. The approval record is generated as a **draft the loader refuses**;
only the operator can approve it.

### 10.3 Scalping — tested at real costs, and it fails everywhere

Every sub-hourly family this repository had rejected was scored against a 13 bps
crypto friction hurdle. HIP-3 growth-mode markets cost ~1.7 bps in fees per round
trip. Whether the **same** mechanism clears that far lower hurdle on a faster
clock had never been measured. Now it has.

Method: the identical Donchian 20/10 + ATR(20)×2 mechanism, built from the
repository's own validated internals, on three signal clocks. A parity check
proved the generic builder reproduces the frozen hourly builder on **7 of 7**
symbols (entries, exits and stop prices). Hold cap = 24 signal bars on every
clock. Nothing tuned. **Costs are the measured live means** (0.864 / 4.32 bps
fees; 0.8 / 1.5 bps entry / exit slippage) — the most favourable honest basis.

| Clock | Window | Trades | per day | Net | Symbols positive | Buy-and-hold |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| **H1** (live mechanism) | 63 d, 8 symbols | 441 | 7.0 | **+$328.14** | 4 / 8 | +$1,166.46 |
| **M15** | 63 d, 8 symbols | 1,857 | 29.5 | **−$1,157.38** | **0 / 8** | +$1,166.46 |
| **M5** | 17 d, 16 symbols | 3,039 | 175.4 | **−$986.92** | **0 / 16** | +$476.94 |

**24 of 24 faster-clock cells are negative at the best-case cost model.** On M15
both the long *and* short sides lose on nearly every symbol, in a window where
simply holding long made +$1,166 — so this is not beta, the 15-minute breakout
signal has negative gross expectancy. Several cells are significantly negative:
xyz:SP500 M15 t = −3.77 (−9.45 at adverse cost), BTC M5 t = −5.53, SOL M5
t = −4.96.

The decomposition is what closes the question. On the twelve HIP-3 markets at M5:
**2,236 trades, implied gross +$141, costs $450.** That is about **$0.06 of gross
edge per trade against $0.20 of cost per trade at the cheapest venue rate that
exists.** Costs would have to fall to a third of the *measured* rate to break
even. Maker entry saves 1.15 bps per round trip, about $0.058 per trade — not
enough, before adverse selection on a breakout entry is even considered. On
crypto the gross itself is negative.

**Scalping this mechanism family at $500 clips is a reliable loss of roughly $58
per day.** More trades is not more money here; it is the same zero-edge signal
paying the spread more often. This is now a measured result on real fees, not an
inherited assumption.

### 10.4 What the 63-day hourly table says about the book that *is* running

| Symbol | n | Net | Blocks + | Buy-and-hold | Longs | Shorts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **xyz:SNDK** | 61 | **+$164.63** | **3/3** | +$158.59 | +$147.69 | +$16.94 |
| **SOL** | 47 | **+$172.13** | 2/3 | +$229.61 | +$181.64 | −$9.51 |
| **xyz:BRENTOIL** | 52 | +$41.80 | 2/3 | +$94.42 | +$42.31 | −$0.51 |
| BTC | 55 | +$23.64 | 1/3 | +$119.35 | +$70.44 | −$46.80 |
| HYPE | 59 | −$4.04 | 1/3 | +$256.85 | +$39.84 | −$43.88 |
| ETH | 48 | −$6.47 | 2/3 | +$198.45 | +$41.46 | −$47.93 |
| xyz:SP500 | 62 | −$27.69 | 0/3 | +$12.93 | −$19.75 | −$7.94 |
| xyz:SPCX | 57 | −$35.87 | 1/3 | +$96.25 | +$25.85 | −$61.72 |

Two facts, stated with their caveats:

- **The V90 roster is the three largest positive cells** (SNDK, SOL, Brent =
  +$378.56; the other five net −$50.43). BTC on D20/10 is the fourth positive cell
  but is +$23.64 at measured cost, −$1.38 at adverse, and positive in 1 of 3
  blocks, so it stays on its existing route at reduced size. The agreement is
  reassuring and is also in-sample: these 63 days include every window used to
  pick the roster.
- **The short side lost on 7 of 8 symbols** (−$201.35 in aggregate; longs
  +$529.48). The whole window was a broad rally — buy-and-hold beat the mechanism
  on 7 of 8 symbols — so this is a fact about the tape as much as about the
  mechanism. Going long-only on it is the post-hoc side selection the project's
  own retired-strategy review rejects. It is recorded, not recommended.

### 10.5 The edge-versus-clock curve is monotone, and H1 is its $/day optimum

| Clock | Symbols | Days | Trades/day | $ / trade | **$ / day** | Symbols positive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 *(added after M15/M5 were seen; the repo's own V75 default)* | 8 | 63 | 1.7 | +2.45 | +4.12 | 5/8 |
| **H1 — the live clock** | 8 | 63 | 7.0 | +0.74 | **+5.21** | 4/8 |
| M15 | 8 | 63 | 29.5 | −0.62 | −18.37 | 0/8 |
| M5 | 16 | 17 | 175.4 | −0.32 | −56.97 | 0/16 |

Per-trade expectancy falls monotonically as the clock speeds up and turns negative
between one hour and fifteen minutes. H4 earns 3.3x more per trade but trades 4x
less, so **the hourly clock already in production is the $/day maximum of the
family.** H4's cells are 10–16 trades each and carry no weight individually. One
is worth noting: xyz:SPCX on H4 is −$134.13 at t = −6.34. SPCX is negative on
every Donchian clock measured.

### 10.6 Breadth — 18 new markets, none passes a bar declared before the results

The venue lists **123 HIP-3 markets**; the repository's captures knew 12. A fresh
unsigned read on 2026-09-20 recorded volume, leverage and growth-mode state for all
of them (`venue_meta_20260920.json`). The 22 most liquid growth-mode markets plus
BTC/ETH/SOL/HYPE were screened on the hourly mechanism over the venue's full
retained 15m history (52 days, 2026-07-30 → 09-20). xyz:MSTR and xyz:GOLD were
excluded: `growthMode` is absent on both, so they pay 8.64 bps per side.

The admission bar was written to `PREDECLARED_BREADTH_BAR.md` at 13:09:12Z, while
inputs were still downloading and before the screen output existed: net > 0 at
measured **and** adverse cost, ≥ 2 of 3 blocks positive, net above
time-in-market-scaled buy-and-hold, ≥ 30 trades. It predicted 1–2 false passes
from luck alone.

| | New 18 | All 26 |
| --- | ---: | ---: |
| Trades (per day) | 854 (16.4) | 1,217 (23.4) |
| Net, measured cost | **−$58.51** | +$281.97 |
| Net, adverse cost | **−$469.41** | −$305.57 |
| Buy-and-hold, same notional | +$1,566.64 | +$2,991.28 |
| Positive at measured / adverse | 11 / 4 | — |
| **Passed the pre-declared bar** | **0 of 18** | SOL only |

No new market passed — fewer than the 1–2 luck alone should have produced. The four
that stayed positive at adverse cost are all within a few dollars of zero
(xyz:GOOGL +$13.79, xyz:INTC +$5.25, xyz:TSLA +$2.87, xyz:CL +$2.84) and each
fails a second condition. xyz:SKHX — the repository's "strongest never-deployed
market" — is **−$48.18**. No cell of 26 reaches t > 2; xyz:EUR reaches t = −2.03.
Longs +$775.50, shorts **−$493.53**, shorts positive on 9 of 26 symbols.

**The hourly breakout is not a general HIP-3 edge.** It is positive on SOL and SNDK
and marginal on Brent; everywhere else it is noise around zero that turns negative
under realistic slippage. Adding breadth on this mechanism would add roughly 16
trades a day of zero-to-negative expectancy. SOL is the only symbol of 26 to clear
all five conditions (+$188.44 measured, +$170.84 adverse, 2/3 blocks, +$68.63 over
beta-scaled buy-and-hold) — but it was already in the screened family, so this is
confirmation within an overlapping window, not independent evidence.

### 10.7 Leverage: §9.4's correction is itself corrected

§9.4 withdrew the 10x → 8x cut as "not an empirical finding" because the 13-day
window contained no liquidation on the retained mechanism. The 52-day window does.
On the two routes V90 sizes, at **identical entries and identical $500 notional**:

| Route | 10x | 8x | 6x |
| --- | --- | --- | --- |
| SOL D20/10 | 1 liquidation, +$188.28 | **0 liquidations, +$213.92** | 0, +$213.92 |
| xyz:SNDK D20/10 | 1 liquidation, +$132.71 | **0 liquidations, +$146.53** | 0, +$146.53 |

Two liquidations in 86 trades, both long, both removed at 8x, worth +$25.64 and
+$13.82. Across all 26 symbols at 10x there were 5 liquidations in 1,217 trades.
xyz:SNDK is running live at 10x — its venue maximum — today. At V90's SNDK notional
that single event scales from −$26 to roughly −$103, so **8x is now supported by
measurement on exactly the routes being sized**, not only by the geometry in §3.3.
The cost is real and stated: at a non-binding cap, 8x posts 25% more margin per
dollar of notional than 10x.

### 10.8 What "aggressive" can honestly mean here

All three routes to more trades have now been measured rather than assumed:

| Route to more trades | Result |
| --- | --- |
| Faster clock (scalping) | **Refuted.** 24 of 24 cells negative at best-case cost; −$18 to −$57 per day |
| Breadth on the working mechanism | **Refuted.** 0 of 18 new markets pass; aggregate negative |
| Uptime | Operational opportunity; **3.06x is not a validated forecast**. Requires durable restart acceptance. |

In every table in this section, **buy-and-hold beat the mechanism** — by 3.6x on the
known eight and 10.6x across all 26. The window was a broad rally and the book's
P&L is mostly long beta captured part-time. That is a statement about the tape and
it is not a recommendation to hold leveraged longs; it is the reason none of these
results should be read as skill without the benchmark column beside it.

So the aggression this evidence supports is the V90 shape and nothing wider:
**V90 is a candidate allocation concentrating on SNDK and SOL while retaining
Brent. Its larger-size behavior and forward edge remain unvalidated. Uptime
repair can be evaluated separately at existing V89 sizing.** Frequent trading and added markets are not
withheld out of caution. They were tested, on real fees, and they lose.

**There is no validated high-frequency edge in this repository, and finding one is a
research programme, not a configuration change.** What now exists is the means to
run that programme quickly: `scripts/v90_expansion_screen.py` scores a mechanism ×
universe × clock grid in minutes, with parity proof, live-parity stop handling, and
both benchmarks in every cell. The next hypotheses worth preregistering are the ones
structurally *different* from a per-symbol breakout, since that family is now
mapped:

1. **Cross-sectional momentum or reversal across the ~25 growth-mode HIP-3 names**,
   rebalanced daily. It uses breadth as the signal rather than as a multiplier, and
   is inherently frequent. 52 days of tape is too short to judge it; it needs the
   collector running.
2. **Oracle-premium reversion.** `metaAndAssetCtxs` publishes `premium`, `oraclePx`
   and `markPx` in asset contexts; these fields also exist on core perps, and
   `premium` can be null. The original roster observer kept only funding and
   latest telemetry. The reviewed capture extension archives the full returned
   xyz universe to daily `data/research/hip3_asset_context/*.jsonl` files using
   the existing request. Collection starts only after that extension is deployed.
   Receipt timestamps are local observation times, not venue event timestamps.
3. **Cash-session conditioning on the equity perps.** The census recorded xyz:MU
   outside US hours at PF 2.39 against 0.32 inside (development-only, n = 43 / 13).

Each enters through the same gate: declared grid, both benchmarks, a bar written
before the result, observe-only lane first.
