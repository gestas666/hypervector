# V30 Live Forward-Readiness Prefix Review

## Problem restatement

The opened historical comparison selected three fixed v30 routes, but it did
not establish prospective execution edge. This review freezes the first exact
live-prefix evidence available from the running v25 backend for those routes:
SOL Range Onset, ETH Range Onset, and SPCX Swing/HA.

The artifact is report-only. It cannot infer counterfactual fills, change the
active strategy, request a transition drain, place or close an order, resize a
position, or activate v30.

## Source identity

- Checkpoint observed at 2026-08-09 17:45:33 UTC.
- Active run: `bidirectional-live-1786182011216`.
- Active profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- Inactive candidate fingerprint:
  `4cb3ca7905b8d5817066cc7f4cdb5e28f04f93ce298c55fe34d96d5065eecf54`.
- Decisions prefix: 880,077,104 bytes, SHA-256
  `faafd11b5a56d0227da8960355610ca34a258db0cbd4adb60fccd732f4ee9475`.
- Candidate TOML SHA-256:
  `303c8e9ae1c8947481ab64e2894cffb964c9de4b17811bb44ae6d8ce9dd3d81c`.

## Exact selected-route evidence

| V30 route | Forward evaluations | Eligible signals | Exact closes | Exact net | Net ex largest winner |
|---|---:|---:|---:|---:|---:|
| ETH Range Onset | 1,922 | 0 | 0 | N/A | N/A |
| SOL Range Onset | 1,922 | 0 | 0 | N/A | N/A |
| SPCX Swing/HA | 128 | 21 | 2 | +$0.910830 | -$0.656872 |

SPCX produced one win and one loss, PF 2.3866, $0.025905 in fees, and
-$0.048865 in funding. Both resolved executions were long, so there is no exact
short execution evidence. Its only winner supplied all gross profit.

The 21 eligible SPCX paths were directionally adverse before applying a fixed
cost hurdle:

- 5 minutes: -4.45 bps mean, 33.3% positive;
- 15 minutes: -0.93 bps mean, 38.1% positive;
- 30 minutes: -2.52 bps mean across 11 independent paths, 47.6% positive; and
- 60 minutes: -10.09 bps mean across seven independent paths, 31.6% positive.

Eligible paths are not fills and these measurements cannot be converted into
avoided-loss or counterfactual-PnL claims.

## Current live state

V25 had 11 resolved lifecycles and +$3.063513 net PnL after $0.456238 in fees
and -$0.082829 in funding at the frozen prefix. Portfolio equity was
$504.626656, or +$2.964888 from the checkpoint's run baseline. Six positions
were open: ETH short, HYPE short, SOL long, GOLD long, SNDK short, and SPCX
long. Every open position had an owned venue stop and the checkpoint reported
zero faults.

## Updated assessment

Correction: the earlier low-medium v30 assessment was based on opened
historical and concurrent mark-to-market evidence. Exact current forward
coverage lowers immediate activation confidence to low because two of three
selected routes have no eligible signal or execution, while the only positive
route is one-winner-dependent and has adverse eligible-path markouts.

The fixed v30 profile remains a reconstructable canary candidate; it is not an
economic promotion. This finding does not create an implicit performance or
trade-count gate. The operator may still authorize a bounded trial under the
project charter, but the evidence does not currently support claiming that
v30 is more likely profitable than v25 prospectively.

## Recommendation

1. Keep v25 unchanged while it owns six protected positions.
2. Keep v30 inactive and preserve its exact profile bytes.
3. Continue collecting exact SOL/ETH eligible signals and SPCX long/short
   execution evidence from the backend ledger.
4. Do not increase v30 sizing, leverage, slots, or route count.
5. Do not add the rejected one-minute impulse or five-minute sweep families.
6. Do not add a global regime or ML gate from this prefix.
7. If the operator explicitly authorizes a v30 canary despite low confidence,
   use the existing fail-closed drain, flat/order-free reconciliation, backup,
   and launch contract. Do not hot-swap the current positions.

## What would update the assessment

Confidence would rise if independent prospective ETH and SOL signals resolve
after costs on both sides, SPCX becomes positive without its largest winner,
and route-matched live stop gaps and adverse excursions remain inside the
modeled envelope. Confidence would fall further if SPCX's current open trade
resolves adversely, selected-route eligible paths remain negative, or live
friction exceeds the frozen assumptions.

The record is invalidated if its source prefix cannot be reproduced, a selected
route was substituted, future evidence entered an earlier decision, open stop
protection was omitted, or eligible signals were represented as fills.

## Validation performed

- Four focused unit tests passed.
- Exact candidate routes and both-direction authority were loaded from v30.
- Missing no-execution structures are reported explicitly rather than
  defaulted to zero-valued performance.
- The checkpoint and append-only decisions prefix were SHA-256 bound.
- All six open positions and venue stops were retained in the artifact.
- No runtime, profile, route, position, order, stop, size, leverage, or drain
  state changed.
