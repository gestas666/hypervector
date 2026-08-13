# Hypervelocity Extended Creator-Window Replay Plan

**Status:** Completed; control improved, challenger rejected; report-only.

## Goal

Use the creator's newly supplied Jul 24/25 outcome screenshots to extend the
venue-matched validation window and retest the already-frozen 1m-trend breakout
challenger without changing or retuning its logic.

## Frozen comparison

- Window: 2026-07-09 04:00 UTC through 2026-07-27 00:00 UTC.
- Control: hard 5m BBWP25 RANGE precedence, 1m recovery age six, strict
  canonical breakout confirmation, 300-second maker TTL/cooldown.
- Challenger: the same configuration plus the existing 1m same-direction
  trend confirmation for a directional 5m breakout.
- Initial equity: $120. Allocation: 70% isolated margin. BTC leverage: 40x.
  Gross margin target: 8%.
- Public trade-through maker fills, authentic Hyperliquid mark/oracle context,
  official settled funding, and the existing liquidation model remain fixed.
- The supplemental screenshot entries are used for source alignment and
  evidence only. They do not schedule replay trades or alter market decisions.
- Runtime, TUI, faithful configuration, and ML observe-only policy remain
  unchanged.

## Validation and decision

1. Preserve the supplemental exit prices when normalizing screenshot evidence
   and expose an optional supplemental positions input on the existing report
   command.
2. Add unit tests for parser behavior, evidence hashing, deduplication, and
   preservation of the original no-supplemental path.
3. Run separate immutable control and challenger reports over the same local,
   checksum-verified archive interval.
4. Compare fills, targets, liquidations, funding, fees, terminal equity,
   drawdown, source-direction alignment, and exact lifecycle substitutions.
5. Do not promote from this development extension alone. A favorable update
   must improve both terminal equity and drawdown relative to control without
   reducing alignment to the new creator entry.

Confidence is medium that this is a valid update to the earlier source-window
test and low that one newly visible trade can establish generalization. Missing
losing-trade exits and the conflicting aggregate scorecards remain material
limitations. A sealed later window reversing the result would supersede this
development comparison.

## Measured result

Both reports consumed the same 428 checksum-verified hourly Hyperliquid
bundles from Jul 9 04:00 UTC through Jul 27 00:00 UTC. Every hour contained
book and public-trade evidence. Authentic mark/oracle and settled-funding
context was complete at the replay boundary, with zero missing mark or oracle
settlements.

| Candidate | Submissions | Fills | Targets | Liquidations | Fees | Funding | Final $120 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Hard/recovery control | 84 | 70 | 64 | 6 | $85.51 | -$2.59 | $126.85 | -77.96% |
| 1m-trend breakout | 80 | 67 | 61 | 6 | $81.11 | -$2.57 | $110.42 | -81.56% |

Fifty-six resolved signals were shared, comprising 50 target-to-target and six
liquidation-to-liquidation outcomes. The challenger removed 14 control
lifecycles and introduced 11 others without changing any shared terminal
status. It improved exact tactical direction alignment from 17/35 to 20/35,
but the additional alignment lost economic value through path substitution.

The two new outcome screenshots agree with the authoritative regime at their
causal decision bars:

- Jul 24 15:06:32 UTC short: 5m and 15m were `TREND_DOWN`; 1m was `RANGE`.
  Canonical, control, and challenger entry direction were all short.
- Jul 25 18:50 UTC long: 1m, 5m, and 15m were all `TREND_UP`. Canonical,
  control, and challenger entry direction were all long.

This raises confidence that the 5m primary regime is directionally correct on
the new evidence and independently argues against making 1m agreement a hard
gate. The 1m-breakout challenger remains rejected because the extended source
window again worsened both equity and drawdown. The control's $6.85 gain is a
positive development slice, not proof of a stable edge: maximum drawdown is
still 77.96%, the full 90-day $120 control remains below its start, and this
interval overlaps the source-calibration period.

Artifacts:

- Control:
  `data/logs/research/hypervelocity_extended_source_control_20260727.json`,
  SHA-256
  `06b47f8dc70ca84f4661abbac4a8c7f03c08484e95b0735b222a7a25dd9cc023`.
- Challenger:
  `data/logs/research/hypervelocity_extended_source_1m_trend_20260727.json`,
  SHA-256
  `f1741af83ef5ee1dd90bf683ce61663787c356467688189d1fbbc62eb93c5b23`.

Runtime, TUI, faithful configuration, and ML observe-only policy were not
changed. Confidence is high for the exact replay comparison, medium for the
new entries' regime agreement, and low that this development interval alone
will generalize.
