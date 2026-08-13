# ETH side and breakout-relation mechanism decision

## Problem restatement

The portfolio research queue continued to recommend separating ETH long and
short mechanisms. The exact 338-trade attribution had already divided those
lifecycles by side and by whether the entry direction aligned with or opposed
the preceding breakout, but that result had not been converted into an
explicit research decision. The objective was to resolve that stale queue item
without changing the current entry rule, 60-bps stop, 12-hour hold, costs,
route, or live runtime.

## Frozen inputs and validation

The decision binds two immutable sources:

- the exact 282-development and 56-opened-final side/relation attribution;
- the fixed-entry duration comparison that identifies the retained 720-minute
  control.

The validator requires identical strategy, symbol, partition, coverage, and
report-only contracts. It also reconciles the 720-minute long and short trade
counts, wins, losses, net return, PF, and largest-winner-adjusted return back to
the attribution. A mismatch fails closed.

An arm is called stable only when both chronological partitions are nonempty,
net-positive after costs, above PF 1, and remain positive after removing the
largest winner. This is a research repeatability definition, not a live entry
gate.

## Results

Neither pooled side and none of the four side/relation arms passed.

| Arm | Development net | Development ex-largest | Opened-final net | Opened-final ex-largest |
|---|---:|---:|---:|---:|
| Long | +254.70 bps | -405.50 bps | +345.18 bps | +16.82 bps |
| Short | +1,403.28 bps | +232.97 bps | -22.85 bps | -691.50 bps |
| Long aligned | +970.70 bps | +310.51 bps | -288.40 bps | -473.20 bps |
| Long opposed | -716.00 bps | -1,267.42 bps | +633.58 bps | +305.22 bps |
| Short aligned | -291.01 bps | -942.26 bps | +525.82 bps | -142.83 bps |
| Short opposed | +1,694.29 bps | +523.98 bps | -548.67 bps | -760.62 bps |

The apparent mechanism rotates rather than generalizes. Development favors
long-aligned and short-opposed entries; the opened-final block reverses toward
long-opposed and short-aligned. Pooled long is positive in both but depends on
its largest development winner. Pooled short fails the opened-final block.

## Decision and next action

Retain the 12-hour exit as the least contradicted tested duration. Reject the
tested static side/relation split as a successor mechanism, without rejecting
ETH or claiming that no ETH mechanism can work. Any next ETH challenger must
declare a new causal mechanism identity before evaluation rather than repeat a
side or breakout-relation filter.

Research revision 6 is appended with all 13 cumulative evidence references
matching their hashes. The hash-verified portfolio improvement overlay now
moves ETH from `separate_long_short_mechanisms` to
`new_side_mechanic_version_required`. It cannot promote or execute a route.

## Uncertainty and falsifiers

Confidence is medium. The exact cohorts and 720-minute identity reconcile, but
the opened-final block was previously inspected, friction remains modeled, and
the current live sample contains only one resolved long and one resolved
short. Source-hash drift, cost/stop/hold changes, relation-label drift,
partition mismatch, or a preregistered new mechanism that survives both
partitions and later independent long/short live paths would update the
decision.

## Evidence

- Decision:
  `data/logs/research/bidirectional_cohort/eth_side_mechanism_decision_20260809T214223Z.json`
- Journal:
  `docs/research-journal/eth-breakout-precompression-pullback-v6.json`
- Exact attribution:
  `data/logs/research/bidirectional_cohort/eth_pullback_mechanism_attribution_exact_v4_20260809T123838Z.json`
- Duration identity:
  `data/logs/research/bidirectional_cohort/eth_pullback_mechanism_duration_20260809T203358Z.json`
