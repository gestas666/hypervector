# ETH Pullback Metalabel Challenger

Status: reject fixed model family  
Execution authority: none  
Automatic promotion: false  
Runtime strategy changed: false

## Problem and decision

This experiment tested whether two fixed, low-complexity return models could
rank the exact ETH precompression-pullback entries well enough to improve
selection after modeled Hyperliquid friction. It did not retune the entry,
stop, maximum hold, route, side, allocation, or live runtime.

Reject the tested Ridge and shallow LightGBM family. Neither model produced a
supported development result, and side/breakout-relation attribution did not
identify a stable rescue. Keep the current ETH strategy unchanged and keep ML
out of routing, sizing, entry, and exit decisions.

This rejects only the fixed feature/model contract in this review. It does not
establish that every possible ETH model or the underlying ETH entry rule lacks
edge.

## Frozen protocol

- Source: 525,600 venue-matched ETH one-minute bars from 2025-07-28 through
  2026-07-27, plus 8,760 matched Hyperliquid funding events.
- Route: exact `eth_breakout_precompression_pullback_bidirectional_v1` replay.
- Signal population: 1,546 directional entries, 392 policy-eligible signals,
  and 338 resolved non-overlapping model rows.
- Development boundary: signal and outcome strictly before
  2026-05-28 12:00 UTC.
- Opened final block: 2026-05-29 through 2026-07-28, previously inspected and
  therefore descriptive rather than sealed confirmation.
- Features: 23 fixed causal entry features, including side and breakout
  relation.
- Models: fixed Ridge and fixed shallow LightGBM; zero hyperparameter sweeps.
- Validation: five outcome-time-purged expanding walk-forward folds with a
  720-minute embargo and transforms fitted inside each fold.
- Training target: gross return in basis points.
- Economic evaluation: actual replay net return with a 13-bps modeled round
  trip. The top-versus-bottom tail spread therefore had to clear 26 bps.

## Development results

| Candidate | Median rank IC | Positive IC folds | Median gross tail spread | Median top net | Supported |
|---|---:|---:|---:|---:|---|
| Ridge | -0.1064 | 0/5 | -112.16 bps | -70.87 bps | No |
| LightGBM | -0.2823 | 0/5 | -120.82 bps | -36.35 bps | No |

Both candidates also had model MAE above the median-only baseline MAE. Across
the combined out-of-sample development predictions, Ridge's top quintile lost
867.72 bps with PF 0.513, while LightGBM's lost 835.11 bps with PF 0.490.

The least-negative post-model subgroup did not provide a stable exception.
Ridge short/opposed top-quintile rows earned 484.05 bps in development and only
18.59 bps after removing the largest winner, but the subgroup contained ten
selected rows, seven losses, and negative rank IC. In the opened final block,
the same short/opposed cell lost 196.28 bps. Conversely, the final-period
Ridge short/aligned cell looked strong on only three selected rows but had zero
winners and lost 356.30 bps in its five selected development rows.

These rotations are contradictory evidence against inverting the model or
promoting a post-hoc side/relation gate.

## Opened final descriptive results

Ridge's final-block pooled top quintile earned 499.41 bps with PF 2.005, but
became negative after removing its largest winner. LightGBM earned 230.50 bps
and likewise became negative without its largest winner. Because this block
was previously opened and both models failed development, these outcomes
cannot rescue either candidate.

## Evidence integrity

The authoritative report is
`data/logs/research/eth_pullback_metalabel_challenger_v1_20260809T150520Z.json`
with SHA-256
`fc96eab47046708cd4d94213e847e04a93c3745d4cc3d6f5cf8ec827c7817e48`.
Its 394-row prediction sidecar has SHA-256
`3894e9a44335be4767f4a929b8f299b1fbd76bf91e20d4f291cd7fb465291af3`.

The sidecar contains 141 development out-of-sample and 56 opened-final rows
per model, complete side/relation identity, and zero duplicate
phase/candidate/signal identities. Earlier immutable artifacts remain on disk:
the first lacked development mechanism identity, the second corrected the
sidecar, and the third added development attribution but did not explicitly
state the 13-bps model cost contract. Their economic results are unchanged;
they are not cited as the authoritative decision artifact.

## Recommendation and next experiment

1. Keep the current ETH route and open ETH lifecycle unchanged.
2. Do not install, invert, filter with, or size from either tested model.
3. Preserve side and breakout-relation identities in the successor telemetry.
4. Do not run another broad model or hyperparameter sweep on the same labels.
5. A materially new ML trial should be predeclared and use distinct
   route-side mechanisms plus venue-native event/orderbook features and exact
   after-cost labels. It remains annotation-only until independent development
   evidence clears its registered hurdles.

## Confidence, risks, and falsifiers

Confidence is medium-high that this fixed Ridge/LightGBM family should be
rejected: both models had zero positive-IC development folds, negative tail
spreads, negative pooled top-quintile economics, and unstable subgroup
leadership. Confidence is low that no future ETH model can add value because
this trial used bar-derived features and only two simple model families.

The decision is invalidated by changed source or artifact bytes, a timestamp
or side mismatch, leakage across the outcome-time purge, an incorrect
13-bps cost contract, or a replay mismatch with the exact ETH route. It should
be updated if a separately registered venue-native route-side model produces
stable positive development ranking and after-cost tail economics across
non-adjacent folds, remains positive without its largest winner, and then
repeats prospectively. A favorable result obtained only by inverting these
predictions or selecting a final-period subgroup after inspection is a new
hypothesis, not falsification of this decision.
