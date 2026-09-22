# V93 exit policy v2: regime-flip ratchet, profit floor, venue break-even stop

## Decision and confidence

The operator approved replacing the passive exit stack with an active one on
2026-09-22 after the V91 first-trade incident. This document records what was
built, the evidence that shaped it, and what remains unproven. **V91 stays
paused**; the V93 profile is a proposal with no transition approval, and no live
process, binary or approval was replaced.

High confidence in the mechanics: every path is exercised by offline tests
against the real engine, adapter parser and ledger. Medium confidence in the
historical comparisons as mechanism diagnostics on data that had already been
examined. Low confidence that the measured deltas will hold prospectively; the
repository's own acceptance bar requires at least one sealed forward block.

## What was wrong

The 29 live trades since 2026-09-07 reached a median +64 bps favorable excursion
and closed at a median −33 bps. Eleven native stops cost $103.65 with a mean
peak of only 53 bps; twelve hourly recipe exits gave back a mean 114 bps; the
only three winners were 24-hour timer exits. The V91 adaptive overlay required
`max(60 bps, 2 x one-minute ATR, friction + 20)` before it could act, which was
123 bps on the only V91 trade at the US cash open, so it never armed.

## Evidence

Probe scripts, inputs and every result table live under
`data/logs/research/bidirectional_cohort/v93_exit_design_probe_20260922/`;
`scripts/v93_exit_v2_matrix.py` reproduces the decisive tables into
`reproduction_v1/report.json` with input hashes.

Unconditional ATR-scaled ratchets were tested first and rejected. On the frozen
430-trade recent eight-asset Donchian screen (matched entries), every cell in a
3x3 activation/giveback grid lost $140 to $400 against baseline, because it
cut the SNDK and SOL runs that carry the edge; partial scale-outs and stale-peak
timers also lost. This agrees with the repository's earlier fixed-bps lock
results and with the 26-market mechanism screen.

The composite that acts only when a run has failed is different:

| Composite C1 = floor(after 2R, at +0.5R) + regime-gated ratchet(after 0.5R, 0.5R giveback) | Recent 8-asset, adverse | Recent, measured | One-year crypto, adverse | One-year crypto, measured | Live paths (29) |
|---|---:|---:|---:|---:|---:|
| Baseline net | +$176.56 | +$381.12 | −$1,183.93 | −$672.25 | −$32.28 |
| Delta, software execution | +$93.3 | +$90.9 | +$33.1 | +$44.0 | +$23.3 |
| Delta, native intrabar floors | +$114.6 | +$113.7 | −$25.9 | +$40.8 | n/a |
| Winners over $20 cut | 0 | 0 | 6 to 8 | 7 to 8 | 0 |
| Entry-time blocks (software) | +39, +38, +16 | +28, +47, +16 | +14, +37, −17 | +7, +55, −18 | n/a |

Each component is positive on its own on the recent screen (floor only +$65 to
+$87; regime gate only +$27 to +$35). A venue break-even stop after 2R is
positive on every screen and cost scenario (+$20 to +$90) and cuts no winner
over $20. On the 110 pre-V89 live trades, which came from mechanisms since
retired, the floor component costs $10.63 while the regime gate cannot be
evaluated because no canonical rows exist for that period.

The 15m trend gate is an EMA21/55 proxy; the live policy uses the canonical
1m/5m/15m alignment the router already computes. Fixed-entry overlays omit new
entries made possible by freed capital.

## What was built

`regime_flip_floor_retention_v2` (`src/hypervector/live/cohort_adaptive_exit_policy.py`):
units are the lifecycle's own stop distance R. Once up 0.5R, close when the
canonical alignment is at or below −0.5 and the executable quote has given back
0.5R from the peak. Once up 2R, never close below +0.5R. State is monotone,
exits are terminal, the clock cannot move backwards, and an unknown regime never
fires the gate. The controller journals every state change before an order can
exist, recovers the state on restart, and refuses a v1 row for the same
lifecycle. The provider recipe exit, initial stop and maximum hold remain.

Venue break-even stop: once the floor arms, the runner asks the engine to move
the resting reduce-only stop to entry plus 25 bps using a single venue modify.
The engine verifies the replacement is visible and covering, records the new
order id through an OPEN-to-OPEN transition, and journals
`protective_stop_raised`. A rejected modify leaves the original stop and is
retried at most three times per lifecycle. An interrupted raise is resolved at
restart from the venue's view of the durable client order id without faulting.

Structural anchor hazard: a fill more favorable than a structural anchor now
falls back to the contract's minimum clamp and journals
`structural_anchor_overrun` instead of raising after the fill; routing refuses
and journals an entry whose anchor is not adverse to the reference price.

Registry: the three policy names live in `ADAPTIVE_EXIT_POLICIES` (Python) and
`ADAPTIVE_EXIT_POLICIES` (Rust); the cockpit labels v2 on every screen.

Profile: `configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml` is
V91 with v2 on all five providers and a $25 estimated stop budget including a
20 bps cost allowance. Fingerprint
`aaf4fe14a15129b4ddbb009c30370ac6007b26587788325dd6371d2b695c1586`; the V91
fingerprint is unchanged.

## Limitations

- The composite's one-year crypto result is small and mixed by execution
  variant; the recent-screen gain is concentrated in SNDK (+$51 to +$58).
- Historical blocks are entry-time groups, not purged folds, and the data were
  examined before the arms were declared.
- The venue modify path is verified against the synthetic exchange only; the
  first live raise should be watched.
- A software floor is not a venue-resident floor until the break-even raise has
  been applied; between 2R and the raise, a process outage leaves only the
  initial stop.

## Rollback

Bind v1 or omit `adaptive_exit_policy` in the profile; v2 code is inert without
a binding and the break-even raise runs only for v2 lifecycles. The anchor fix
changes behavior only where the previous code raised.
