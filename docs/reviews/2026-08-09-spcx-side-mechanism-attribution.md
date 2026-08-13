# SPCX side-mechanism attribution

## Problem restatement

The rolling portfolio queue repeatedly recommended separating SPCX Swing/HA
long and short mechanics. That recommendation became stale after the existing
provider, alignment-onset, next-bar-confirmation, and fast-EMA-pullback entry
clocks had already been evaluated by side. The correction needed to preserve
the exact frozen trade rows, avoid the sealed holdout, remain report-only, and
prevent a research decision from granting live authority.

## Frozen evidence and method

The attribution binds the exact entry-timing report and its 2,082-row Parquet
sidecar by path, byte length, and SHA-256. The exact SPCX route contributes 317
after-cost trade rows. It produces 32 cells:

- four entry clocks;
- long and short directions;
- development and validation partitions;
- nominal and stress friction.

A timing/side arm is classified as stable only if all four of its
partition/friction cells are nonempty, net-positive after costs, above PF 1,
and remain positive after removing the largest winner. This is a research
repeatability definition, not a runtime entry gate.

## Results

No tested arm passed all cells.

| Stress-friction cell | Trades | Net PnL | PF | Net excluding largest winner |
|---|---:|---:|---:|---:|
| Provider long, development | 13 | +$14.2647 | 3.1526 | -$0.9192 |
| Provider long, validation | 3 | -$1.9682 | 0.0000 | -$1.9682 |
| Provider short, development | 24 | -$3.8732 | 0.7254 | -$14.1025 |
| Provider short, validation | 19 | +$3.1560 | 1.3672 | -$0.3367 |
| Confirmed long, development | 9 | +$16.7559 | 5.1767 | +$0.7010 |
| Confirmed long, validation | 3 | -$1.9619 | 0.0000 | -$1.9619 |

The provider long and short effects rotate across partitions. Next-bar
confirmation improves development long concentration but all three validation
longs lose. The fast-EMA pullback produces no trades. Therefore another static
side split or entry-clock shift would repeat an exhausted experiment rather
than test a new hypothesis.

## Decision and tracking

The tested timing set is rejected, but the SPCX asset and the possibility of a
different SPCX mechanism are not rejected. Further work requires a new causal
mechanism identity declared before evaluation. The current v25 route, sizing,
orders, stops, and positions were not changed.

The decision is revision 1 of
`hip3-spcx-side-mechanism-attribution` in the research database. All three
evidence files match their stored hashes. A hash-verified report-only decision
overlay moves SPCX from the repeated side-split queue to
`new_side_mechanic_version_required`. The continuous improvement monitor still
runs every 120 seconds and cannot request `PROCEED` through an overlay.

## Uncertainty and falsifiers

Confidence is medium. The conclusion is supported by exact frozen rows and
partition reversal, but development and validation were already opened,
friction is modeled, and the exercise is not a shared-router replay. A source
hash mismatch, changed fill clock, holdout leakage, failure to reproduce the 32
cells, or a preregistered new mechanism that survives costs, partitions, and
largest-winner removal would update the decision.

## Evidence

- Attribution:
  `data/logs/research/bidirectional_cohort/spcx_side_mechanism_attribution_20260809T212208Z.json`
- Journal:
  `docs/research-journal/spcx-side-mechanism-attribution-v1.json`
- Decision overlay:
  `configs/research/cohort_improvement_decision_overrides_v1.json`
- Focused tests cover source-hash drift, cell metrics, zero-trade arms, no
  stable arm, triage correction, no-promotion overlays, and monitor provenance.
