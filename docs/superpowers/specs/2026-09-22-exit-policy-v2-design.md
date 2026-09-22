# Exit policy v2 design: regime-flip ratchet, profit floor, venue break-even stop

Status: approved by the operator on 2026-09-22 ("approved please complete").
Scope: the multi-asset cohort live runner (`src/hypervector/live`), its Rust
cockpit projection, a V93 proposal profile, and the research reproduction of the
evidence. No live restart is authorized by this document.

## Problem

Since 2026-09-07 the live cohort closed 29 trades. The median trade reached
+64 bps of favorable excursion and closed at −33 bps; 12 trades were up 30 bps or
more and still lost. Exits were passive: a native initial stop, the hourly
recipe exit and a 24-hour timer. The V91 adaptive overlay required a favorable
excursion of `max(60 bps, 2x one-minute ATR, friction + 20)` before it could act;
on the only V91 trade that was 123 bps, so it never armed.

## Evidence that constrains the design

All numbers are in `data/logs/research/bidirectional_cohort/v93_exit_design_probe_20260922/`.

1. Unconditional trailing loses. On the frozen 430-trade recent eight-asset
   Donchian screen (matched entries), every ATR-scaled ratchet arm in a 3x3 grid
   loses $140 to $400 against baseline because it cuts the SNDK and SOL runs;
   partial scale-outs and stale-peak timers also lose. This matches the repo's
   earlier fixed-bps lock results.
2. A composite that acts only when a run has failed wins on both partitions and
   on the live paths, with zero winners over $20 cut:

   | Composite C1 | Recent, adverse | Recent, measured | One-year crypto, adverse | Live paths (29) |
   |---|---:|---:|---:|---:|
   | Baseline | +$176.56 | +$381.12 | −$1,183.93 | −$32.28 |
   | Delta | +$93.3 to +$114.6 | +$90.9 to +$113.7 | −$25.9 to +$33.1 | +$23.3 |
   | Winners over $20 cut | 0 | 0 | 6 to 8 | 0 |

   Each component is positive on its own on the recent screen (floor +$65 to
   +$87, regime gate +$27 to +$35); all three entry-time blocks are positive.
3. A venue-resident break-even stop after +2R is positive on every screen and
   cost scenario (+$21 to +$90) and cuts no winner over $20.

## Policy `regime_flip_floor_retention_v2`

Units: `R` is the trade's own initial stop distance in bps of entry price,
computed from the bound execution plan at the actual entry price; `pnl_bps` is
the executable-quote excursion (best bid for longs, best ask for shorts) used by
v1. `peak_bps` is the running maximum of `pnl_bps`.

Frozen constants (declared before the evidence above was read, then kept):

| Constant | Value |
|---|---|
| `ACTIVATION_R` | 0.5 |
| `GIVEBACK_R` | 0.5 |
| `OPPOSED_ALIGNMENT` | −0.5 (canonical alignment, weights 1/3/2, same as routing) |
| `FLOOR_ACTIVATION_R` | 2.0 |
| `FLOOR_R` | 0.5 |
| `BREAKEVEN_BPS` | 25 (venue stop distance beyond entry after `FLOOR_ACTIVATION_R`) |

Transitions, evaluated once per poll on a fresh executable quote:

1. `armed = armed or peak >= ACTIVATION_R * R`.
2. `floor_armed = floor_armed or peak >= FLOOR_ACTIVATION_R * R`; when it first
   becomes true, `floor_bps = FLOOR_R * R` and `breakeven_stop_requested = true`.
3. Exit `profit_floor` when `floor_armed and pnl_bps <= floor_bps`.
4. Exit `regime_flip_giveback` when `armed and alignment is not None and
   alignment <= OPPOSED_ALIGNMENT and pnl_bps <= peak - GIVEBACK_R * R`.
5. Unknown regime (`alignment is None`) never fires rule 4; a missing quote
   produces a degraded telemetry row and no action, exactly as v1.
6. State is monotone: `armed`, `floor_armed` and `floor_bps` never decrease;
   an exit reason is terminal; the clock cannot move backwards.

The initial native stop, the provider recipe exit and the maximum-hold contract
are unchanged and remain backstops.

## Venue break-even stop

When `breakeven_stop_requested` is true and not yet applied, the runner asks the
engine to raise the resting reduce-only stop to
`entry * (1 ± BREAKEVEN_BPS / 10_000)` (favorable side). The engine uses a single
venue `modify` action on the owned stop order, waits for the replacement to be
visible and covering, records the new order id through a new OPEN-to-OPEN state
transition, and journals `protective_stop_raised` with both order ids and both
trigger prices. A rejected modify leaves the original stop untouched, is
journaled, and is retried on later polls up to three times per lifecycle; it
never faults the process. The raise happens inside the order-capable execution
phase after exit actions, at most once per lifecycle.

## Structural anchor hazard fix

`BoundExecutionPlan._stop_distance_bps` returns the minimum clamp distance when
a structural anchor is not adverse to the price being protected, instead of
raising; `BoundExecutionPlan.structural_anchor_overrun(entry_price, side)`
reports the condition so the engine journals `structural_anchor_overrun` when it
places or recovers a stop. `execute_routing_action` refuses, journals and skips
an entry whose structural anchor is not adverse to the action's reference
price, instead of submitting it.

## Registry

`cohort_adaptive_exit_policy.ADAPTIVE_EXIT_POLICIES` is the single Python source
of allowed names (`none`, v1, v2). The two research mirrors import it. The Rust
cockpit carries the same three names in one constant used by its validators, and
labels v2 as `ADAPTIVE REGIME-FLIP RATCHET / PROFIT FLOOR v2`.

## V93 proposal profile

`configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml` is V91 with
`adaptive_exit_policy = "regime_flip_floor_retention_v2"` on all five providers
and `stop_risk_budget = { maximum_loss_usd = 25.0, cost_buffer_bps = 20.0 }`.
$25 is about 0.5% of current equity; the operator approved the design with that
suggested value. It has no transition approval and is not selected by launchd.

## Acceptance

- Policy unit tests cover both sides, activation boundaries, floor monotonicity,
  unknown regime, terminal exit, backwards clock, and restart recovery.
- Engine replay tests open, arm, raise the venue stop, and exit through each
  reason with the ledger showing observation rows before order intents.
- The V91 profile fingerprint is unchanged; legacy payloads round-trip.
- Full non-network Python suite and the Rust suite pass; Ruff is clean.
- The research script reproduces the composite table from the frozen artifacts.

## Rollback

Omit `adaptive_exit_policy` (or bind v1) in the profile; v2 code is inert
without a binding. The venue stop raise runs only for v2 lifecycles. The anchor
fix has no configuration and changes behavior only where the previous code
raised or would have faulted.
