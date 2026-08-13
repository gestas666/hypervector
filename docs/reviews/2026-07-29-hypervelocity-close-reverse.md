# Hypervelocity Close-and-Reverse Review

Date: 2026-07-29

## Problem restatement

Test whether the reverse-engineered creator behavior closes a position only when
a later opposite Hypervelocity entry becomes executable, then atomically submits
the reverse side. Success required positive net economics after venue-matched
fees, funding, mark liquidation, and public trade-through fills—not merely fewer
liquidations.

This was report-only research. Runtime, TUI, the faithful configuration, the 8%
gross margin target, 70% isolated allocation, 40x leverage, and ML observe-only
authority were not changed.

## Known facts and assumptions

- Four adverse creator close rows are each followed by an opposite position
  within 36.2 to 142.7 seconds. Their exact exit fills and exit reasons are not
  available.
- The candidate differs from target-only control only by the disabled-by-default
  `opposite_entry_close_reverse` replay option.
- Liquidation is evaluated before close/reverse. A qualifying reversal closes at
  adverse BBO with taker fees, then submits a post-only opposite order that cannot
  fill on the same snapshot.
- Every archive gap splits the portfolio into a new $10,000 block. No equity path
  is stitched through missing order books.

## Validation sequence

The implementation and development output were hash-frozen before the first
candidate-unseen block. The same implementation was then run on two later blocks
after their completed archive prefix became available. The later extension was
not used to change the rule.

After a separate shadow partial-close accounting defect was discovered, the
entire seven-block comparison was rerun with corrected residual fee/funding
basis. Forty partial-liquidation events traversed the corrected path. Every
per-block result and aggregate below reproduced to floating-point precision, so
the defect did not change this comparison. See
`docs/reviews/2026-07-29-shadow-partial-close-accounting.md`.

| Evidence | Blocks | Control final sum | Close/reverse final sum | Control liquidations | Candidate liquidations |
|---|---:|---:|---:|---:|---:|
| Development | 4 | $4,195.30 | $5,555.18 | 39 | 14 |
| First holdout | 1 | $573.43 | $1,244.08 | 9 | 4 |
| Later extension | 2 | $17,876.88 | $6,684.11 | 5 | 6 |
| All reset blocks | 7 | $22,645.61 | $13,483.36 | 53 | 24 |

The candidate improved the first five blocks but failed both later blocks. In
January 9-19, control grew to $12,847.15 while close/reverse fell to $3,741.29.
In January 19 22:00-February 7 22:00, control ended at $5,029.74 and the
candidate at $2,942.81. Only control produced a positive block.

## Lifecycle and cost analysis

Across all seven blocks, control recorded 252 targets and 53 liquidations. The
candidate recorded 250 targets, 61 reversals, and 24 liquidations. Candidate
fees were $16,892.47 versus $13,188.25 for control because atomic reversals
changed the path and generated more orders.

Shared lifecycle comparison found 26 control liquidations converted to
reversals, but 17 control targets were also closed as reversals. The loss-depth
distributions overlap:

| Later control outcome | Shared reversals | Median gross margin PnL at reversal | Observed range |
|---|---:|---:|---:|
| Liquidated | 26 | -31.79% | -47.77% to -17.21% |
| Target completed | 17 | -24.11% | -39.75% to -6.65% |

This overlap means a loss-depth threshold selected from these results would be
hindsight tuning, not a validated discriminator.

## Regime timing diagnosis

All 61 reversal closes had an opposite source direction available before or at
their exit. None of the 250 targets did. All 24 remaining liquidations occurred
without an opposite source direction before liquidation.

High confidence: the implementation did not wait materially beyond the first
confirmed opposite 5m source direction. The unresolved failure is that the
confirmed detector sometimes flipped on trades that later recovered and failed
to flip before every remaining liquidation. This rejects unconditional exit
authority from that state; it does not prove that no earlier intratrade warning
exists.

## Risks, uncertainties, and falsifiers

- Creator close timestamps lack exact fills and causal reasons. Authenticated
  order logs could show manual exits or a different invalidation signal.
- Public L2 cannot reproduce private queue rank or hidden liquidity. That affects
  exact fills, though it does not explain the directionally inconsistent block
  result by itself.
- Seven reset blocks are more informative than one 90-day path but still do not
  cover all volatility states.
- A larger complete creator ledger could falsify the rejection if it identifies a
  point-in-time feature that separates the recovered targets from actual losses
  and survives a frozen venue replay.

## Recommendation

Do not install unconditional close/reverse in runtime. Retain the replay
mechanism and creator reconstruction as research infrastructure, because they
made the tail-risk hypothesis measurable and preserve exact lifecycle identity.

Finish the one-year archive, audit its gaps, and evaluate the unchanged baseline
and already-frozen hypotheses on every complete block. Do not sweep reversal
delay or loss-depth thresholds. The next strategy candidate requires new causal
evidence about entry selection or earlier invalidation, not another threshold
chosen from these losses.

## Artifact identities

- Creator reconstruction:
  `f5bc2228f4bc8acdc63ad59910aa6fa8f830a1dcb8d26d1052c7eb4edff4b72d`
- Development:
  `69bcc52b459aa3902f9a5be3aeefc42a27fed0e6a4beefebcdfb6344b9a3a0e4`
- First holdout:
  `1b50ed3cec74d2d655d64bd8e1f63920a92306f51394a2390d4eb719cb2c63d6`
- Later extension:
  `315fb59b1b682f39fbfd451bd6f35151c00b66f3f1d027094ae9cfa66f5302d9`
- Accounting-corrected seven-block rerun:
  `1c4d16d7fb2c8534b4400a403708e16caa9712d1f714548fa1719e5bf3b3778c`
