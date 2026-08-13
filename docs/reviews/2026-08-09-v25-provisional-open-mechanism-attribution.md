# v25 provisional open-mechanism attribution

Date: 2026-08-09

## Problem restatement

The live audit separated resolved strategy performance by provider, symbol,
side, regime stance, and breakout-side relation, but excluded open positions
from that mechanism view. The open-trade reflection already retained causal
entry context, marked economics, MFE, MAE, giveback, and venue-stop identity.
The missing aggregation made it harder to inspect current mechanisms without
mistakenly counting unresolved marks as wins or losses.

Success requires a report-only open-mechanism section, explicit separation from
closed performance, complete attribution coverage when source telemetry exists,
and no live process, route, order, stop, sizing, or exit change.

## Implementation and validation

`cohort_live_entry_alignment_mechanism_v3` adds a `provisional_open` section
grouped by provider, symbol, and side. Each lifecycle discloses:

- decision-time component stance and breakout-side relation;
- marked net PnL and return on margin;
- MFE, MAE, and peak giveback;
- venue-stop protection status; and
- explicit marked-economics and path coverage.

The section states `pooled_with_closed_performance=false`. Closed-trade counts,
profit factors, and outcomes retain their prior scope. The unit test failed on
the absent `open_trades` contract before implementation and passed afterward.

## Current immutable prefix

The audit contains 11 resolved trades, 6 wins, 5 losses, and +$3.063513 net.
Portfolio maximum drawdown is 0.303499%. All four open positions have venue
stops and zero recorded asset faults.

| Mechanism | Marked net | Return on margin | MFE | MAE | Giveback | Identity |
|---|---:|---:|---:|---:|---:|---|
| ETH pullback short | +$0.033401 | +0.6687% | 50.46 bps | 1.04 bps | 33.29 bps | breakout-opposed fade |
| SOL HT-Breakout long | +$0.248316 | +1.6341% | 53.12 bps | 16.40 bps | 14.69 bps | breakout-aligned |
| GOLD Swing/HA long | -$0.081563 | -0.5473% | 3.67 bps | 17.22 bps | 5.51 bps | regime relation unavailable |
| SNDK Swing/HA short | -$0.164036 | -1.1168% | 0.00 bps | 27.12 bps | 21.37 bps | regime relation unavailable |

These are provisional marks, not resolved performance. ETH has surrendered
part of its favorable excursion, but the exact historical ETH profit-lock
comparison was materially worse than the unchanged exit. SOL is favorable but
is one path. GOLD and SNDK currently lack comparable regime-component
attribution because their HIP-3 provider contract carries its own HA, EMA,
pivot, and order-block features instead of canonical crypto regime telemetry.

## Decision and next action

Retain v25 execution unchanged. Adopt the provisional mechanism section as an
observability improvement and continue resolving the four protected paths.
Do not infer an entry or exit change from their open marks.

The next research implementation should normalize HIP-3 Swing identity using
its causal provider features: side, entry mode, HA color, EMA relation, pivot
state, order-block direction, and declared exit mode. That attribution should
be used to compare resolved long and short mechanisms and ignored exit signals;
it must not fabricate canonical regime labels or become an automatic gate.

Confidence is high that the new section reflects the immutable audit fields,
medium that it improves decision hygiene, and low that any current open path
establishes economic edge. A lifecycle mismatch, missing stop, changed audit
hash, open mark entering resolved statistics, or a field inconsistent with the
underlying reflection falsifies the implementation. Resolved after-cost paths
that contradict the provisional marks update the economic interpretation.

## Evidence

- Immutable audit:
  `data/logs/research/bidirectional_cohort/v25_live_audit_provisional_mechanisms_20260809T130817Z.json`
- SHA-256:
  `b8493c571f2ce772a58802f9f1e70620e4681c0430d1316c11db26b3f6b6eb2e`
- Bytes: `14984891`
- Execution authority: none
- Runtime strategy changed: false

