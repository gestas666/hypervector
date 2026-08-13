# GOLD side and entry-timing mechanism attribution

## Problem restatement

The continuous portfolio queue requested separate GOLD long and short
mechanisms even though the exact HIP-3 entry-timing experiment already
contained side-attributed GOLD trades. The objective was to determine whether
the existing provider, alignment-onset, next-bar-confirmation, or fast-EMA
pullback clocks contained a stable side-specific mechanism before scheduling
another experiment or changing a live route.

## Frozen evidence and contract

The attribution consumes the immutable 2,082-row trade sidecar already bound
to the HIP-3 timing report. It validates the exact commodity Swing strategy,
`xyz:GOLD`, development and validation partitions, nominal and stress
friction, both directions, all four clocks, and the sealed holdout contract.
It has no execution, retuning, promotion, routing, or model authority.

An arm is stable only when all four partition/friction cells are nonempty,
net-positive after costs, above profit factor one, and remain positive after
removing the largest winner. This is a research repeatability definition, not
a runtime performance gate.

## Result

Zero of eight side/timing arms passed.

| Stress arm | Development | Development ex-largest | Validation | Validation ex-largest |
|---|---:|---:|---:|---:|
| Provider long | -$2.0697 | -$4.5873 | -$1.4958 | -$3.2502 |
| Provider short | -$2.9703 | -$4.6884 | +$1.8862 | +$0.2357 |
| Next-bar long | -$2.2032 | -$4.7344 | -$1.6452 | -$3.4240 |
| Next-bar short | -$4.9907 | -$6.6803 | +$1.1923 | -$0.1664 |

Provider and alignment-onset clocks are identical for this onset recipe. The
fast-EMA pullback produced zero GOLD trades in every partition and friction
cell. GOLD long was adverse in both partitions. GOLD short looked favorable
only in validation; it was negative in development. Next-bar confirmation did
not repair the reversal and made the validation short dependent on its largest
winner.

## Decision

Retire the tested static GOLD side/timing set. Do not repeat a long-only,
short-only, onset, next-bar, or fast-EMA-pullback rescue under this mechanism
identity. This rejects the tested set, not GOLD as a market. A successor needs
a new causal mechanism identity and new preregistration.

The running v25 strategy, its open protected GOLD lifecycle, and the inactive
v31 candidate are not changed by this artifact. Because v31 retains this exact
GOLD Swing route, the new evidence must be considered before any v31
authorization; it does not silently edit or promote that candidate.

## Uncertainty and falsifiers

Confidence is medium. The source identity, sidecar hash, all 32 cells, and
sealed holdout state are exact, but development and validation were already
opened, friction is modeled, and the evaluation is an independent-asset
15-minute approximation rather than a shared-router replay. The decision is
updated by source-hash drift, partition or cost changes, holdout access, a
reproducible cell mismatch, or a preregistered new GOLD mechanism that survives
chronological partitions, stress costs, concentration removal, and later
independent live outcomes.

## Evidence

- Attribution:
  `data/logs/research/bidirectional_cohort/gold_side_mechanism_attribution_20260809T215535Z.json`
- Source report:
  `data/logs/research/hip3_entry_timing_challenger_v3_20260809T134637Z.json`
- Trade sidecar:
  `data/logs/research/hip3_entry_timing_challenger_v3_20260809T134637Z.trades.parquet`
