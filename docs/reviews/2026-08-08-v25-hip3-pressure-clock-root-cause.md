# V25 HIP-3 pressure clock root-cause review

**Reviewed:** 2026-08-08 15:36 EDT  
**Runtime:** `multi_asset_bidirectional_complete_portfolio_canary_v25`  
**Run:** `bidirectional-live-1786182011216`  
**Decision:** retain the protected runtime; stage the validated clock repair for
the next verified activation boundary

## 1. Problem restatement

The live portfolio audit reported `provider_metric_telemetry_missing` even
though the market-data coverage contract was complete. The affected HIP-3
breakout evaluations retained their metrics schema but intermittently emitted
null `imbalance_10` and `pressure_age_seconds` values.

Success requires proving the exact timing defect, preserving point-in-time
causality, preventing funding-window overlap or omission, validating the repair
without network calls, and avoiding an unsafe restart of protected live
positions.

## 2. Known facts

- All 324 metric gaps in the immutable 19:03 UTC prefix belonged to five
  HIP-3 breakout-pressure provider-symbol routes. No other provider had a
  metric gap.
- The only missing values were `imbalance_10` and
  `pressure_age_seconds`; every evaluation retained a metrics object.
- Exact-symbol `book_observation` rows with source
  `hyperliquid_mainnet_l2_rest` existed before the corresponding evaluation
  rows. At 19:15 UTC the five books were received about eight to nine seconds
  before routing telemetry was emitted.
- A direct current-ledger read returns fresh finite depth-ten pressure for all
  five symbols. This rejects the hypotheses that venue books were absent, the
  schema omitted the fields, or the latest ledger tail could not contain the
  newest book.
- The verified pre-start manifest proves PID 37897 loaded runner SHA-256
  `d651e3b7c72d5b3cf2647f15e606e27bbd4c94ead4daf7dc6c2193db86995854`.
  The staged runner is
  `31500a60f9c99fba036969ca5dba6de4a56539c92a82178dc50df82a139dad33`.

## 3. Root cause

The loaded runner sampled its provider `observed_at` before reconciling the
nine assets. Reconciliation then fetched and durably appended current venue
books. The provider poll reused the earlier timestamp as its causal cutoff.

`Hip3LedgerPressureSource.latest_at_or_before` correctly rejects observations
newer than that cutoff. Therefore, same-cycle books were treated as future
evidence even though they existed before provider evaluation and routing
telemetry were emitted. The null metrics are a clock-order defect, not an
economic blocker and not a missing venue feed.

Confidence is high because the active implementation is hash-bound by its
pre-start backup, its call order directly produces the observed rejection, and
the alternative source/schema/tail hypotheses contradict inspected ledger
evidence.

## 4. Staged repair

The staged runner separates two clocks:

1. sample the funding reconciliation boundary;
2. reconcile all assets and append their current books;
3. sample the provider causal cutoff;
4. poll providers with the post-reconciliation cutoff.

On no-action cycles, the funding cursor advances only to the earlier exact
reconciliation boundary. On action cycles, the required second reconciliation
permits advancement to the later provider boundary. This avoids silently
skipping the interval between the two samples.

The repair changes telemetry causality only. It does not change any provider
recipe, threshold, route, side, entry, exit, allocation, leverage, stop, target,
or portfolio-capacity policy.

## 5. Validation

- The clock-order and funding-cursor regression tests were created before the
  staged runner edit according to their filesystem modification times.
- Exact clock/funding/HIP-3 source and poller validation: 27 passed.
- Expanded runner/transient/HIP-3 validation: 47 passed.
- Full non-network suite: 4,122 passed, four deselected, 27 known deprecation
  warnings.
- Ruff lint and formatting checks passed.
- Immutable diagnostic:
  `data/logs/research/bidirectional_cohort/v25_hip3_pressure_clock_root_cause_20260808T193618Z.json`.

## 6. Live activation boundary

The staged repair is not loaded by PID 37897. Restarting a healthy process with
four open positions solely to improve telemetry would create an unnecessary
adoption and duplicate-order risk. V25 therefore remains unchanged until the
portfolio reaches a verified terminal boundary, unless the user separately
authorizes and the system verifies an existing-position adoption procedure.

At 19:35:57 UTC the backend was `running_consistent`, heartbeat age was under
one second, and runtime faults were zero. BTC, HYPE, GOLD, and SPCX retained
venue-native reduce-only stop OIDs `512826131342`, `512893829830`,
`512544517709`, and `512769547957`.

## 7. Risks and falsifiers

- Historical null metrics cannot be reconstructed as decision-time evidence;
  the repair only improves new evaluations after activation.
- The 30-second pressure-age limit may still reject genuinely stale books;
  that is intended causal behavior and must remain distinguishable from this
  clock defect.
- Offline tests cannot prove the next live process loaded the staged source.
  The pre-start bundle and post-start evaluation rows must verify it.
- The repair is falsified if a new evaluation has null pressure while an
  exact-symbol authoritative book exists between its completed-bar decision
  time and provider cutoff.
- Funding semantics are falsified by an overlapping or skipped funding window.
- Operational acceptance is falsified by profile drift, a missing stop, an
  unadopted venue position, a duplicate order, or a runtime fault after
  activation.

## 8. Recommendation and trade-offs

| Option | Benefit | Risk | Decision |
|---|---|---|---|
| Restart immediately | Activates complete pressure telemetry now | Four-position adoption and duplicate-order exposure | Rejected |
| Activate at a verified terminal boundary | Loads the repair without position adoption | Delays complete pressure metrics | **Selected** |
| Ignore the defect | No operational transition | Continued blind HIP-3 pressure attribution | Rejected |
| Relax the pressure-age gate | May reduce null values | Masks causality instead of fixing the clock | Rejected |

Confidence is high for the technical diagnosis and staged behavior. Confidence
is not yet high for live activation because the current process deliberately
retains the pre-repair implementation. A flat-boundary restart followed by
finite, causally aged HIP-3 metrics would update that confidence upward.
