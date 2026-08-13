# Source-session gate and shared-direction validation

Date: 2026-07-30

## 1. Problem restatement

After correcting report-only replay callers to apply the 12-100 bps range
contract to completed five-minute candles, this experiment asks two bounded
questions:

1. Do the 0.70 source-confidence floor and 12-bps completed-range floor add
   stable edge, or do they merely suppress trades?
2. Does the frozen liquidity-sweep long improve the corrected session-short
   portfolio when both directions share one $15,000 account and one BTC
   position?

All lanes are report-only. They retain 35% isolated allocation, 30x leverage,
an 8% gross-margin target, 60-second post-only entries, authentic funding and
mark/oracle context, venue fees, isolated liquidation, and a 24-hour maximum
hold. ML remains observe-only and no runtime configuration changed.

## 2. Corrected recent gate factorial

The exact 2026-04-28 through 2026-07-28 replay processed 12,202,083 canonical
L2 snapshots and 36,931,672 deduplicated public trades. Every lane used the
same half-open `[06:00,15:00)` UTC decision session.

| Candidate | Confidence floor | Range floor | Signals | Fills | Outcomes | Final equity | PF | Max DD |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| Frozen tuned | 0.70 | 12 bps | 51 | 26 | 26 targets | $28,511.41 | no realized loss | -12.22% |
| Range relaxed | 0.70 | 0 bps | 81 | 35 | 35 targets | $35,671.87 | no realized loss | -12.22% |
| Confidence relaxed | 0.00 | 12 bps | 52 | 28 | 27 targets, 1 time exit | $25,978.84 | 7.288 | -14.45% |
| Both relaxed | 0.00 | 0 bps | 83 | 38 | 37 targets, 1 time exit | $33,322.53 | 11.240 | -14.51% |

Removing confidence admitted a 2026-05-08 14:10 UTC signal that filled short
at $79,782 and time-exited 24 hours later at $80,589. It lost $1,745.95 in the
range-filtered path and $1,789.35 in the both-relaxed path because earlier
portfolio history changed size. The confidence relaxation is rejected.

Removing only the range floor added nine filled trades, no liquidation, and
$7,160.45 of final equity relative to the tuned control. This is meaningful
recent-window evidence, but it was inspected after the older range threshold
was selected and is not sufficient by itself for promotion.

## 3. Older gap-safe and intermediate range controls

The range-only comparison was then replayed with the same 35%/30x/session
contract across the twelve older gap-safe archive segments and the intervening
ten-day slice.

| Window | Range floor | Selected signals | Fills | Outcomes | Final equity | PF | Max DD |
|---|---:|---:|---:|---|---:|---:|---:|
| 2025-07-28 to 2026-04-18 | 12 bps | 108 | 42 | 40 targets, 2 full/7 partial liquidations | $24,300.69 | 2.372 | -31.80% |
| 2025-07-28 to 2026-04-18 | 0 bps | 162 | 56 | 50 targets, 5 full/13 partial liquidations, 1 time exit | $22,315.35 | 1.504 | -26.76% |
| 2026-04-18 to 2026-04-28 | 12 bps | 2 | 1 | 1 target | $15,221.67 | no realized loss | -2.27% |
| 2026-04-18 to 2026-04-28 | 0 bps | 5 | 2 | 2 targets | $15,597.18 | no realized loss | -9.02% |
| 2026-04-28 to 2026-07-28 | 12 bps | 51 | 26 | 26 targets | $28,511.41 | no realized loss | -12.22% |
| 2026-04-28 to 2026-07-28 | 0 bps | 81 | 35 | 35 targets | $35,671.87 | no realized loss | -12.22% |

The range floor is not a stable winner or loser. It improves older PF,
liquidation count, and final equity, while the no-floor control wins the small
intermediate slice and recent return. The April comparison has only two
no-floor fills and cannot estimate tail behavior. Promoting zero based on the
recent window would be retrospective parameter chasing; rejecting it entirely
would discard contradictory forward-period evidence. It remains a declared
observer challenger.

## 4. Creator-cadence attribution

Within the visible July creator history, the tuned signal set has one short
signal within ten minutes of a creator short, and that signal fills. Range
relaxation adds one additional approximate timestamp match, but its maker order
expires unfilled. It therefore does not materially close the creator cadence
gap. Timestamp conversion for screenshot-only rows remains inferred, so this
is diagnostic rather than exact identity evidence.

## 5. Corrected shared-direction portfolio

The frozen liquidity-sweep long was replayed with the tuned session short on
the same recent tape. Both directions shared one account, one pending entry,
and one BTC position. Simultaneous signals would prefer the source short, and
signals observed while occupied could not become stale entries later.

| Lane | Fills | Direction mix | Outcomes | Final equity | PF | Max DD |
|---|---:|---|---|---:|---:|---:|
| Short control | 26 | 26 short | 26 targets | $28,511.41 | no realized loss | -12.22% |
| Long control | 5 | 5 long | 4 targets, 1 stop | $15,376.31 | 1.323 | -7.39% |
| Shared portfolio | 30 | 26 short, 4 long | 29 targets, 1 long stop | $28,521.80 | 7.734 | -18.23% |

The shared path reproduced every short fill and earned only $10.38 more than
short-only. Its maximum drawdown worsened by 6.01 percentage points. The long
stop lost $2,007.86 after prior compounding, while one standalone long target
did not become a completed shared trade. The long challenger does not provide
a favorable shared risk/return trade-off and remains annotation-only.

## 6. Decision, risks, and falsifiers

Keep the active 0.70-confidence, 12-bps-floor session-short shadow profile
unchanged. Do not relax confidence, do not promote the long, and do not change
ML from observe. Record the 0-bps range rule beside it as a report-only forward
observer; compare both from the same future decisions before considering a
cutover.

The active choice is not claimed optimal. It is the frozen candidate with
positive older, intermediate, and recent results and lower older liquidation
frequency than the no-floor alternative. Its remaining failure modes are
private maker queue uncertainty, fixed-clock selection bias, short-side macro
dependence, sparse loss observations, and a large creator cadence/direction
gap. Both recent exact paths cross 21 global empty-book hours, although no
pending order or position overlaps them; execution economics remain marked
non-conclusive conservatively.

Confidence is medium in the historical short edge, low in live repeatability,
low in the current long challenger, and low-to-medium that the fixed range
floor is stationary. Forward PF at or below one, clustered liquidations,
materially worse real fill conversion, a persistent no-floor advantage on
predeclared new data, or runtime/replay decision mismatch would update or
falsify this decision.

## 7. Immutable evidence

- Corrected recent gate factorial:
  `data/logs/research/hypervelocity_source_session_strict_factorial_20260428_20260728_trade_through_hv35x30_v2.json`
  (`dde4bfad223c278a6336d7e37a4a66df0df446a58f7413d158a52bcd85acf49c`).
- Older zero-floor gap-safe replay:
  `data/logs/research/hypervelocity_source_session_decision_06_15_minrange0_alloc35_lev30_continuous_20250728_20260418_v1.json`
  (`0a09968cde6ca82d29fff8c7d6625b5bf6bb678f6818da9b1289bd30195ddb95`).
- Intermediate zero-floor replay:
  `data/logs/research/hypervelocity_source_session_decision_06_15_minrange0_alloc35_lev30_holdout_20260418_20260428_v1.json`
  (`be92f0de8eacb0f8ed66b3e9ada5776fee1764d70e1ea64fcee9bf5eadd62f22`).
- Corrected shared-direction replay:
  `data/logs/research/hypervelocity_shared_direction_session_06_15_20260428_20260728_trade_through_hv35x30_v2.json`
  (`58a42460f2f23e88d4ea76f38ac2041785f410bd189804f87236bba4d2ef16c1`).
