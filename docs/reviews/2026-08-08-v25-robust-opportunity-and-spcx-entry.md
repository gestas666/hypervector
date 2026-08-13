# v25 robust opportunity telemetry and SPCX live entry review

## Problem restatement

The live research cockpit previously displayed an arithmetic mean for causal
missed-opportunity paths without showing whether that mean was representative.
The immediate systems requirements were to expose a robust distribution,
preserve compatibility with older checkpoints, keep execution unchanged, and
reconcile any live event occurring during the report-only reload.

Acceptance evidence is
`data/logs/research/bidirectional_cohort/v25_robust_opportunity_and_spcx_entry_20260808T1215Z.json`.
Its SHA-256 is
`3d5c7366adaba55d5035003fb7015629feb68eb8d4afb548238502192016cb72`.

## Implemented telemetry

The report-only opportunity summary now publishes mean, median, minimum, and
maximum close return after the fixed 13-bps estimated round-trip friction. The
Rust checkpoint projection rejects non-finite, partial, and misordered new
distributions while continuing to accept legacy checkpoints that omit all
three new fields. The strategy and order-book inspector views show mean and
median; the strategy path view also shows the compact minimum-to-maximum range.

This change has no execution authority and does not alter routing, entries,
position sizing, stops, or exits.

## Real checkpoint result

For the SOL HT-Breakout long path blocked only by `5m_not_breakout` at 30
minutes, the fresh checkpoint contained five independent resolved paths:

- mean after estimated friction: `+5.01 bps`;
- median after estimated friction: `-4.85 bps`;
- range after estimated friction: `-34.76` to `+44.10 bps`;
- two cost-clearing closes, two robust favorable excursions, and one reversal
  after first clearing estimated costs.

The positive mean is therefore not representative of the typical observation.
The evidence does not support removing the 5m breakout condition. Confidence
in that narrow decision is medium: the direction of the median is clear, but
five independent paths remain a small sample. A materially positive median
and stable lower tail across substantially more independent venue-matched
paths would update the decision.

## SPCX live entry reconciliation

While verification ran, the unchanged v25 owner opened `xyz:SPCX` long through
`hip3_swing_ha_sp500_spcx_bidirectional_v2`.

- The 15-minute completed-bar decision was recorded at sequence `105814`; the
  router selected it at sequence `105815` with no withheld action.
- All four provider conditions aligned: fast EMA above slow EMA, green
  Heikin-Ashi state, qualifying pivot state, and bullish active order block.
- The fill was `0.56` at `133.24`, exactly the recorded reference price, for
  approximately `$74.61` notional at isolated `5x`.
- Recorded entry fee was `$0.006446`, slippage was `0.0 bps`, acknowledgement
  latency was `1230 ms`, and the 6.527-second markout was `-0.375 bps`.
- Venue stop `512769547957` protects the full position at `132.17408`, exactly
  80 bps below entry. The sampled liquidation price was `109.3470750916`.
- The bound `provider_recipe_exit_policy` resolves to `ignore`. Alignment-loss
  signals are telemetry only; executable exits are the venue stop, fixed
  24-hour maximum hold, or selected same-symbol opposite-intent arbitration.

The mechanics are internally consistent at this sample. Economic confidence
is low because the lifecycle remains open. Canonical regime context is also
unavailable for this HIP-3 instrument, so this entry was driven by the route's
own EMA/HA/pivot/order-block state rather than the canonical regime engine.
That is an explicit limitation, not evidence of a routing fault.

The earlier SPCX loss provides one favorable alignment-loss counterexample: a
15-minute mismatch appeared at reference `132.96` before the eventual stop fill
at `132.46`. It is not sufficient to override the frozen exit contract. The
predeclared direct-honor challenger was negative for SPCX in validation:
nominal net `-$5.57` with PF `0.406`, and stress net `-$9.19` with PF `0.240`.
Retaining `ignore` is therefore consistent with the broader evidence. A future
profile should honor these exits only if combined-priority, after-cost forward
evidence reverses that result.

## Natural-fill cache validation

The SPCX entry advanced the exact raw fill identity from 61 events to 62. The
first checkpoint cycle refreshed the complete archive and retained 28 closed
lifecycles because the new lifecycle is open. A subsequent report-only import
matched the new identity exactly and returned `reused_by_fill_identity` in
2.77 seconds at 330,268,672 bytes maximum RSS. This validates the intended
invalidate-once, reuse-thereafter behavior on a natural venue fill.

## Validation

- 17 focused opportunity and order-book research tests passed.
- 44 checkpoint, sidecar, and cached-import tests passed.
- The complete `hypervector-tui` library and integration target set passed.
- Ruff, Python format, Cargo format, trailing-whitespace, and 500-line checks
  passed.
- The actual fresh checkpoint parsed and rendered in monitor mode, then exited
  cleanly.
- Only `com.hypervector.v25.checkpoint` restarted. The live owner remained PID
  `37897`, launch count one, and never exited.

## Failure modes and next evidence

The telemetry conclusion would be falsified by a checkpoint that cannot be
read by the TUI, a partial distribution accepted as valid, or a later
independent sample whose median and lower tail become durably positive. The
SPCX mechanical assessment would be falsified by a missing/mismatched stop,
duplicate owner, position-size mismatch, or venue fill that disagrees with the
ledger. Its economic assessment remains unresolved until exit fees, funding,
slippage, reason, and net PnL reconcile at lifecycle close.
