# v25 HIP-3 provider-native mechanism attribution

Date: 2026-08-09

## Problem restatement

HIP-3 Swing/HA trades appeared as `unavailable` in canonical regime alignment
because those instruments use a provider-native 15-minute recipe rather than
the crypto regime classifier. Their causal entry records still contain recipe,
EMA, Heikin-Ashi, order-block, eligibility, side, and exit-mode evidence.

The objective was to recover that exact mechanism identity without fabricating
canonical regimes, changing execution, or pooling open marks with resolved
performance.

## Result

The live entry-alignment report now attributes eligible HIP-3 Swing lifecycles
using:

- `entry_mode`: `state` or `onset`;
- `exit_mode`: `alignment_loss` or `ha_flip`;
- EMA relation to the position side;
- Heikin-Ashi relation when structurally recorded;
- order-block relation when structurally recorded; and
- pivot confirmation derived explicitly from an eligible provider decision.

Legacy rows with null HA or order-block metrics preserve the known recipe and
EMA identity while reporting those individual components as `unavailable`.
The first real-ledger audit failed on this partial-coverage condition. A
regression test was added before the compatibility correction, and the next
immutable audit completed.

## Current evidence

Resolved HIP-3 Swing paths remain too sparse for a strategy update:

| Route identity | Trades | Result |
|---|---:|---:|
| SPCX state/alignment-loss, legacy partial metrics | 1 | -$0.656872 |
| SPCX state/alignment-loss, full aligned metrics | 1 | +$1.567702 |
| GOLD onset/HA-flip, legacy partial metrics | 1 | -$0.242433 |

The apparent full-metric SPCX advantage is one winner versus one older loss and
does not isolate the feature effect. The rows also come from different live
times and cannot support a causal before/after claim.

The current fully attributable open paths are:

| Route | Side | Marked net | MFE | MAE | Native identity |
|---|---|---:|---:|---:|---|
| GOLD Swing/HA | Long | -$0.085003 | 3.67 bps | 17.22 bps | onset, HA-flip, EMA/HA/order-block aligned |
| SNDK Swing/HA | Short | -$0.176236 | 0.00 bps | 29.59 bps | onset, HA-flip, EMA/HA/order-block aligned |

These observations show that the entries were not random direction mistakes:
the provider-native entry components were aligned. They instead focus the next
research question on entry timing and exit economics, especially SNDK's zero
favorable excursion. Open marks remain provisional.

The HA-flip exit observer is mixed. Across the two current open commodity
paths, continuation after the first ignored flip is +9.19 bps for one and
-1.64 bps for the other. Only one resolved commodity lifecycle exists, where
ignoring the first flip added +8.06 bps before the actual exit. This is
insufficient to change the current fixed maximum-hold policy or honor HA flips.

## Decision and next action

Retain v25 execution unchanged. Preserve provider-native identity in every
future audit and wait for the current GOLD and SNDK paths to resolve. After
resolution, compare the actual exits with their first ignored HA-flip, entry
MFE/MAE, fees, funding, and stop path. Do not relax entry components or change
leverage from these provisional paths.

The next strategy experiment should be an immutable, report-only HIP-3 entry
timing comparison that holds the same eligible Swing identity fixed and tests
whether entry at the provider onset, first pullback, or next completed-bar
confirmation changes after-cost outcomes. It must separate GOLD, SNDK, SPCX,
long, and short, and include missed fills and largest-winner sensitivity.

Confidence is high that the provider-native identities reproduce recorded
entry features, medium that the loss mechanism is timing/exit rather than
directional misrouting, and low that a specific timing change improves edge.
A provider-entry mismatch, changed evidence hash, noncausal feature, missing
stop, or open mark entering resolved economics falsifies the implementation.
Resolved paths showing a different feature identity or stable benefit from the
ignored exit would update the economic recommendation.

## Evidence

- Immutable audit:
  `data/logs/research/bidirectional_cohort/v25_live_audit_provider_native_mechanisms_20260809T131632Z.json`
- SHA-256:
  `788a9d76492462d8b5a3fdfa71de7907e3831484582a7f6d1daaf1822e269737`
- Bytes: `15006793`
- Execution authority: none
- Runtime strategy changed: false

