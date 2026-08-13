# v25 open-lifecycle prospective checkpoint

## Problem restatement

The live v25 process has three protected positions whose final economics are
not yet known. The purpose of this checkpoint is to freeze the actual live
state and already-declared exit counterfactuals before those positions close.
It does not select a strategy, alter an order, or treat open marks as profit.

## Runtime and evidence boundary

- Run: `bidirectional-live-1786182011216`.
- Profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- Profile fingerprint:
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`.
- Compared prefix: `2026-08-08T21:05:15.707140Z` through
  `2026-08-08T21:17:30.912249Z`.
- The delta contains 90 cohort rows, zero fills, zero closes, and zero changes
  to resolved fees, funding, or net PnL.
- BTC, `xyz:GOLD`, and `xyz:SPCX` remained open with full-size venue-native
  stops. Runtime faults remained zero and the transition drain remained
  inactive.

## Prospective open-position evidence

The values below are point-in-time marks, not realized outcomes.

| Asset | Provider | Hold | Marked net | Funding | Exit time remaining |
|---|---|---:|---:|---:|---:|
| BTC | Hulk expansion v2 | 6.29 h | -$0.049595 | -$0.001135 | 17.71 h |
| GOLD | HIP-3 Swing/HA v1 | 22.54 h | -$0.185949 | -$0.007721 | 1.46 h |
| SPCX | HIP-3 Swing/HA v2 | 9.54 h | +$0.926986 | -$0.046568 | 14.46 h |

All three liquidation distances were greater than 18% at this boundary. That
is a point-in-time venue observation and does not guarantee future protection
or execution quality.

### Ignored provider exits

- GOLD's first ignored long-exit signal occurred at 4344.7, already 22.0472
  bps below entry. At this checkpoint the completed path after that signal was
  +6.9050 bps in the original long direction, with +17.0322 bps MFE and
  3.4525 bps MAE. Ignoring it was provisionally better than exiting at that
  reference, but the position remained below its original entry.
- SPCX's first ignored alignment-loss exit occurred at 133.16, 6.0042 bps
  below entry. The completed path after that signal was +137.4287 bps in the
  original long direction. Ignoring it was provisionally much better at this
  boundary, although the path had reached +566.2361 bps MFE and surrendered
  428.8074 bps from its peak.

These are causal reference-price paths, not counterfactual venue fills. Fees,
funding, queueing, and slippage prevent treating the differences as realized
cash.

### SPCX profit-lock challengers

All three predeclared report-only policies had triggered before this boundary:

| Policy | Trigger reference | Comparison with 134.99 mark |
|---|---:|---|
| 25/15/10 bps | 133.6662 | Earlier exit would currently be worse |
| 40/15/20 bps | 133.5324 | Earlier exit would currently be worse |
| 60/15/30 bps | 139.3700 | Earlier exit would currently be better |

The split result is why no profit-lock policy is promoted from an unresolved
trade. The actual venue-costed SPCX close is the predeclared discriminator.

## Missed-opportunity evidence

The delta matured 50 unique directional paths from 91 provider observations.
At 5, 15, 30, and 60 minutes, the newly independent/non-overlapping cohort had
zero cost-clearing close outcomes. One independent path cleared the MFE hurdle
at 15 and 30 minutes, but it reversed afterward and no independent robust-MFE
result appeared. This prefix does not support relaxing an entry blocker.

Overlapping paths did clear costs in places, but they are repeated minute-level
observations of shared market episodes. Pooling them as independent trades
would overstate evidence.

### Ranked one-blocker scan

A cumulative scan of exact one-blocker cohorts used the independent mean close
after the predeclared 13-bps friction estimate, plus the mean after removing the
single largest close. Three superficially positive rows require restraint:

| Candidate relaxation | Horizon | Independent n | Mean after friction | Mean excluding largest |
|---|---:|---:|---:|---:|
| SPCX Swing/HA: pivot state missing | 30m | 12 | +9.7076 bps | -14.6583 bps |
| SOL range onset: hourly cross missing | 60m | 4 | +7.0945 bps | +0.3768 bps |
| SOL HT-Breakout: 5m breakout missing | 60m | 11 | +3.6431 bps | -1.2789 bps |

The SPCX and SOL HT-Breakout means are driven by their largest paths. The SOL
range-onset row survives removal of its largest path by only 0.3768 bps, has
four samples, and is negative at 5, 15, and 30 minutes. None qualifies for a
live relaxation. The SOL range-onset row can remain a report-only challenger;
additional independent episodes must determine whether the 60-minute result is
repeatable or horizon selection noise.

The TUI already renders open lifecycle path excursion, ignored provider exits,
and profit-lock status on the regime command deck. It presents the legacy
`hype_breakout_onset_bidirectional_v1` provider as `HT-Breakout`; retaining the
internal ID preserves ledger and research identity across assets.

## Technical coverage and decision

Evidence coverage remains incomplete because eight additional null metric
values accrued under the already-known
`provider_metric_telemetry_missing` identity. No technical-gap identity was
added or removed. This is consistent with the old live process not containing
the staged HIP-3 pressure-clock repair; it does not prove that the staged repair
will work after a future safe restart.

No research-journal revision is warranted because no lifecycle resolved and
the delta explicitly reports `journal_revision_recommended=false`. Keep v25
unchanged, let the three protected lifecycles resolve, and compare their actual
fees, funding, slippage, MFE/MAE/giveback, and net PnL with this frozen boundary.

## Validation and falsification

- Immutable audit:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_open_paths_20260808T2116Z.json`,
  SHA-256 `30f4c216060c7b73f660d616726f134c1c611e753ae4f20da87177d08c81350a`.
- Immutable delta:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_delta_20260808T210508Z_20260808T2116Z.json`,
  SHA-256 `76d8c49d55a0f324e523af878bcce959d28d08a6bc894ad9e957247dd9b93e7f`.
- Both artifacts are report-only with `execution_authority=none` and
  `runtime_strategy_changed=false`.

Confidence is high for the frozen identities, current marks, path arithmetic,
and lack of execution mutation. Confidence is low that any one exit challenger
has durable edge because all three positions are unresolved and the sample is
tiny. A hash mismatch, removed lifecycle without a matching close, protection
mismatch, new technical-gap identity, or materially different final close
would update or falsify the corresponding assessment.
