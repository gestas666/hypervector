# v31 HIP-3 pressure-adoption contract

Date: 2026-08-09

## Problem and diagnosis

The current v25 checkpoint reports incomplete technical coverage with
`provider_metric_telemetry_missing`. Exact provider attribution shows 1,194
metric-value gaps, all confined to the five HIP-3 breakout-pressure routes:

| Provider family | Symbols | Missing values |
|---|---|---:|
| Index breakout pressure | SP500, SPCX | 484 |
| Commodity breakout pressure | SNDK, GOLD, BRENTOIL | 710 |

Every gap is either `imbalance_10` or `pressure_age_seconds`. No evaluation
lacks its complete metrics object, market-path coverage is complete, direction
conflicts are zero, and no other provider has a metric gap.

This matches the previously hash-bound v25 pressure-clock diagnosis: the loaded
live runner sampled the provider cutoff before same-cycle book reconciliation.
The staged source fixes that ordering, and the isolated current-feed observer
produced finite pressure metrics on all five affected routes with no technical
gap or execution authority.

Confidence in the diagnosis is high. A newly discovered missing metric outside
those five routes, an altered artifact hash, or a current admissible book that
the staged observer still rejects would falsify it.

## Transition-contract improvement

The inactive v31 transition guide now binds both existing immutable artifacts:

- root-cause diagnostic SHA-256
  `aa24bb752350511f6d20ed492d1a992897a1d070abe5a4c845ed8ba8179fae78`;
- disarmed parity-observer SHA-256
  `b72817ae403a72aa1a5649174d1a9828d8aee954bd1db9fde4013bd9bfb3b22d`.

After a future authorized v31 launch, its first completed HIP-3
breakout-pressure evaluation must publish finite numeric `imbalance_10` and
`pressure_age_seconds` for all five symbols, with nonnegative age no greater
than 30 seconds and an exact-symbol authoritative book at or before the
provider cutoff. Funding reconciliation must have no overlap or skipped
window.

Historical v25 gaps remain attributed to v25. They are not rewritten, filled,
or used as evidence that the old run was complete. A new v31 run establishes a
new metric-coverage baseline.

## Validation and operational effect

Three transition-contract tests pass. They bind the exact v25/v31 authority
delta, all decision artifacts including the pressure evidence, the
flat-boundary fail-closed state, and the post-start pressure acceptance text.
Ruff passes after formatting.

No live runtime, sidecar, route, order, position, stop, sizing, strategy, or
transition state changed. V25 remains the source-bound evidence run; v31
remains inactive.

## Recommendation

Do not hide the current `provider_metric_telemetry_missing` status. It is an
honest historical v25 gap. At the eventual flat-boundary transition, require
the new-run pressure adoption check before describing v31 as technically
accepted. This is a technical validation condition, not a performance gate or
an implicit strategy filter.
