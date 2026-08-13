# v31 change sequence and continuous tracking

## Problem restatement

The operator needs an exact answer to three questions: what changes next, when
the change can occur, and whether material live evidence is retained while the
current generation continues trading. Success requires an identity-bound
candidate, an event-based transition boundary, durable evidence, and no silent
mutation of protected v25 lifecycles.

## Next runtime change

V31 is the next prepared runtime generation. Its economic change is narrow:

- SNDK Swing/HA becomes observation-only;
- BRENTOIL Swing/HA becomes observation-only;
- GOLD Swing/HA remains executable; and
- SNDK, GOLD, and BRENTOIL Breakout remain executable.

The candidate retains all nine assets, both directions, one position per
asset, nine slots, isolated 5x configuration, current sizing, stops, targets,
maximum holds, priorities, and the crypto and index route set. The HIP-3
pressure-clock repair and funding-window commitments are staged technical
changes that must be accepted from the new source-bound ledger after launch.

## Transition timing

The transition is event-based, not scheduled for a clock time. At the current
snapshot, v25 has four venue-protected positions and zero faults. V31 remains
inactive. Because v25 may open another position after a symbol becomes flat,
natural flatness is not a deterministic transition mechanism.

The controlled sequence is:

1. receive explicit authority to start the v25 transition drain;
2. withhold new entries while all existing v25 exits and stops remain active;
3. prove all nine positions and owned-order sets are empty;
4. archive the exact v25 boundary and verify fresh v31 backups;
5. run the disarmed v31 preflight; and
6. receive renewed explicit live-risk authority before v31 launch.

No calendar estimate is defensible because the remaining positions own their
normal exit contracts. The observable transition ETA is therefore the latest
remaining lifecycle exit after an authorized drain, followed by the bounded
archive, backup, and preflight checks.

## Continuous tracking evidence

The report-only tracker runs every 120 seconds as
`com.hypervector.v31.route-forward`. Its compact hash-chained journal is
`data/logs/research/bidirectional_cohort/v31_route_material_changes.jsonl`.
The first five events retain the five-to-four, four-to-three, and three-to-four
position-set changes plus the corresponding closed economics. The latest event
records 14 closed trades, seven wins, seven losses, +$2.791652 net, PF 2.143047,
four protected positions, and zero faults. Open marks are excluded from
material triggers, so they do not inflate the journal every two minutes.

The tracker has no execution, transition, sizing, closing, restart, or
promotion authority. Detailed fills, fees, funding, order books, and lifecycle
paths remain in the checkpoint and raw ledgers rather than being compressed
into the change index.

## Next strategy research decision

The resolved ETH short supports investigating exit capture but does not support
promoting the tight profit lock. The 25/15/10 lock improved the two newest exact
ETH live reconstructions, but the exact fixed-entry replay produced:

| Segment | Control net | 25/15/10 net | Decision |
|---|---:|---:|---|
| Development | +1,657.98 bps / 282 trades | -3,461.07 bps | Reject |
| Opened final 60 days | +322.33 bps / 56 trades | -671.23 bps | Reject |

The control policy identifier `generic_8h_control` is legacy naming; the ETH
attribution test and replay configuration enforce a 720-minute hold. This is a
reporting-name limitation, not an eight-hour behavioral replay.

The next strategy investigation should therefore preserve exact side and
breakout-relation identity and compare exit capture prospectively. It should
not add a broad entry gate, a static side veto, or the rejected 25/15/10 lock.

## Confidence, risks, and falsifiers

Confidence is high that the tracker captures the tested material fields and
that v31's route-authority delta is identity-bound. Confidence is medium that
the two-route prune improves shared-portfolio behavior because live evidence
for the removed routes is sparse. Confidence is high that the measured ETH
25/15/10 policy should not be promoted from the current evidence.

The tracking claim is falsified by a missing lifecycle/economic event, a broken
hash chain, an append caused only by a new mark, or any execution side effect.
The v31 recommendation should be updated by repeated both-side live outcomes
favoring either removed Swing route, candidate identity drift, missing
protection, or failed pressure/funding acceptance. The ETH lock rejection
should be revisited only if a preregistered policy wins after costs in both
historical partitions and independent forward lifecycles without largest-winner
dependence.

## Evidence

- Transition contract:
  `docs/guides/cohort-live-transition-and-rollback-v31.md`
- Current exact live audit:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_successor_refresh_20260809T201446Z.json`
- Current successor triage:
  `data/logs/research/bidirectional_cohort/v25_successor_triage_refresh_20260809T201446Z.json`
- Exact ETH attribution:
  `data/logs/research/bidirectional_cohort/eth_pullback_mechanism_attribution_exact_v4_20260809T123838Z.json`
- Continuous material journal:
  `data/logs/research/bidirectional_cohort/v31_route_material_changes.jsonl`

