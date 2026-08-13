# V25 HIP-3 pressure-clock parity observer review

## Problem restatement

The armed v25 process was started from a source bundle that samples the
provider cutoff before its latest public-book reconciliation. Five HIP-3
breakout-pressure routes consequently report missing `imbalance_10` and
`pressure_age_seconds` even though the same cycle later records a fresh book.
The staged runner reverses that ordering. The validation requirement was to
exercise that staged ordering against current Hyperliquid mainnet public data
without restarting v25, adopting its positions, or constructing execution
authority.

Success required:

- a separate ledger root that cannot alias the armed live root;
- the exact v25 provider and symbol roster;
- 24 unique provider-symbol evaluations with no duplicates or future clocks;
- finite pressure values for all five HIP-3 pressure routes;
- every row stamped `live_armed=false` and `execution_authority=none`;
- no routed actions, orders, fills, or portfolio mutation.

## Known facts and provenance

- Observer run: `bidirectional-observe-1786219921063`.
- Profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- Source ledger:
  `data/observe/v25_pressure_parity_20260808T201151Z/decisions.jsonl`.
- Source ledger SHA-256:
  `94a8118729d36cb6c2714fd3574b390eee9f46918070ff093abbfea8a01b9744`.
- Immutable observer audit:
  `data/logs/research/bidirectional_cohort/v25_pressure_parity_observer_20260808T201243Z.json`.
- Observer audit SHA-256:
  `b72817ae403a72aa1a5649174d1a9828d8aee954bd1db9fde4013bd9bfb3b22d`.
- Audit duration: 42.714208 seconds across two bounded polls.
- Technical coverage: 24 expected and 24 observed provider-symbols, zero
  duplicates, zero future decisions, and zero technical gaps.
- The first decision cycle evaluated all 24 routes. The second cycle had no
  new completed provider bar and correctly emitted no repeated evaluation.
- All eight ledger rows are disarmed and report no execution authority.

## Results

All five exact HIP-3 breakout-pressure routes received a causally admissible
book and emitted finite metrics:

| Symbol | `imbalance_10` | Pressure age | Maximum age | Recorded blockers |
|---|---:|---:|---:|---|
| `xyz:SP500` | -0.0241047362 | 0.002 s | 30.0 s | breakout not crossed; pressure opposed |
| `xyz:SPCX` | +0.1538219214 | 0.002 s | 30.0 s | breakout not crossed |
| `xyz:SNDK` | -0.0266343312 | 0.002 s | 30.0 s | breakout not crossed; pressure opposed |
| `xyz:GOLD` | +0.3033381317 | 0.002 s | 30.0 s | breakout not crossed; pressure opposed |
| `xyz:BRENTOIL` | -0.2456516865 | 0.002 s | 30.0 s | breakout not crossed; pressure opposed |

The prior `provider_metric_telemetry_missing` symptom did not recur. The
remaining blockers are strategy-state observations rather than a missing-data
fallback. No signal was eligible, no action was routed, and the observer audit
explicitly reports no orders, fills, fees, funding, slippage, markout, or PnL.

## Safety hardening

The observer now accepts a dedicated `--ledger-root` that rebinds the cohort
ledger, every asset ledger, the STOP path, operator command inbox, and staged
profile below one isolated root while preserving all strategy parameters. It
refuses the configured ledger root and broad targets `/`, the home directory,
and the current workspace root. The command exposes neither live-arm flag and
imports no order-client factory.

## Uncertainties and failure modes

High confidence applies to the observed public-book ordering, finite metric
values, exact provider coverage, and lack of execution authority. This is
supported by the hashed raw ledger, immutable audit, and command-boundary
tests.

Live activation confidence remains unverified. Observe mode does not prove
that a newly armed process loads the staged runner bytes, adopts existing
positions, or preserves venue order ownership. It also does not establish
strategy profitability; the run produced no eligible entry or execution
outcome.

The technical conclusion would be falsified by any of the following on a new
hash-bound process:

- a null pressure value despite an exact-symbol book inside the decision
  cutoff;
- a pressure age above the configured 30-second maximum being accepted;
- missing or duplicate provider-symbol coverage;
- funding cursor overlap or gap after the clock-order change;
- any observer row with live authority or a routed action;
- an immutable evidence hash mismatch.

## Recommendation and trade-offs

| Option | Evidence | Trade-off | Decision |
|---|---|---|---|
| Restart v25 while positions are open | No adoption proof for this exact staged source | Activates the fix sooner but risks lifecycle/order duplication | Reject at this boundary |
| Keep current v25 and activate at verified flat boundary | Current process is healthy and positions are protected | Missing pressure telemetry persists in the old process until restart | Recommended |
| Revert the staged clock ordering | Contradicted by the isolated current-feed observer | Preserves the known five-route telemetry defect | Reject |

At the terminal boundary, require a fresh verified pre-start bundle, a new
process identity bound to the staged implementation hash, current-profile
reconciliation, zero duplicate orders, and finite HIP-3 pressure metrics on
the first completed evaluation. Until then, this result is a validated staged
technical repair, not a live activation claim or strategy promotion.
