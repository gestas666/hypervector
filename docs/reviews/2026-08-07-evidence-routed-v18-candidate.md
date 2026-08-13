# Evidence-routed v18 candidate review

**Prepared:** 2026-08-07 EDT  
**Runtime effect:** none; report-only preparation  
**Active predecessor:** `multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14`  
**Candidate:** `multi_asset_bidirectional_evidence_routed_candidate_v18`

## Problem restatement

The active v14 experiment grants the native HYPE breakout provider execution on
BTC, ETH, SOL, and HYPE. The required next decision is whether that cross-asset
scope remains justified after historical transfer research and the first exact
v14 live outcome, while preserving bidirectional observation, one position per
coin, shared-capital accounting, and fail-closed live activation.

Success for this preparation means one immutable candidate generation whose
execution routes are explicit, whose only differences from v14 are attributable,
whose runtime collectors construct, and which cannot arm without the existing
two explicit live-risk flags. It does not mean the portfolio has proven edge.

## Known facts and assumptions

- **High confidence:** the immutable v14 prefix audit is technically complete,
  reports zero faults, and records one closed SOL short at `-$0.095959` net after
  `$0.064723` fees and `+$0.001724` funding. The HYPE short remains open and
  protected by reduce-only stop `511973207990`. This is directly recorded in
  the immutable audit.
- **High confidence:** unchanged HYPE-breakout transfer to ETH and SOL was
  negative after modeled costs in both the development and opened final blocks.
  BTC reversed from negative development to a short-driven positive recent
  block, making it unstable rather than established. The equal-window transfer
  review contains the exact counts and costs.
- **Low confidence:** the separate ETH precompression-pullback mechanism may
  have positive edge. It produced development PF `1.1111` and opened-final PF
  `1.1208`, but it was selected from a 20-cell stop/hold surface, had one large
  negative fold, and has no eligible outcome in the current forward prefix.
- **Low confidence:** retaining native HYPE execution will produce positive
  future results. Its exact historical deployed shape is negative and the
  currently identifiable exact live history is also negative. It remains a
  bounded live-research hypothesis because it is the native mechanism currently
  under test, not because profitability has been established.
- **Low confidence:** BTC Hulk will add positive portfolio return. Its historical
  blocks are contradictory and the current prefix has no eligible forward
  outcome. v18 leaves its existing `$25` authority unchanged so the routing
  transition does not conflate a third mechanism change.

## Candidate routing

| Coin | Executable provider | Sides | Notional cap | Status |
|---|---|---|---:|---|
| BTC | Hulk expansion | long + short | $25 | unchanged, contradictory evidence |
| ETH | precompression pullback | long + short | $25 | new low-confidence canary route |
| SOL | none | observed long + short | $75 configured ceiling | generic transfer removed |
| HYPE | native breakout onset | long + short | $75 | unchanged bounded live research |

All five providers continue generating attributable observations. A provider is
not silently removed merely because its execution scope is empty.

## Exact change from v14

1. Assign a new immutable profile identity.
2. Narrow `hype_breakout_onset_bidirectional_v1` execution symbols from
   `BTC/ETH/SOL/HYPE` to `HYPE`.
3. Enable `eth_breakout_precompression_pullback_bidirectional_v1` only for ETH.

No leverage, asset cap, margin mode, stop, hold, target, poll cadence, shared
portfolio limit, one-position-per-coin rule, provider signal implementation, or
currently running process is changed.

## Failure modes and validation

| Failure mode | Detection | Required response |
|---|---|---|
| Route widens or overlaps | Config contract test and startup fingerprint | Refuse start; correct candidate generation |
| Live starts without approval | Two-flag fail-closed test | Refuse start |
| HYPE current lifecycle is interrupted | Venue/ledger reconciliation | Do not transition; preserve stop and v14 process |
| ETH signal/runtime drift | Exact collector attribution and entry-feature journal | Fail closed for that intent; retain evidence |
| Stop missing after any entry | Venue order reconciliation | Technical fault; restore protection or close safely |
| Thin edge disappears after costs | Per-lifecycle fees, funding, slippage, and net PnL | Report result; reassess route without hidden gate |
| Candidate trades too rarely | Eligible/withheld/missed-opportunity journal | Evaluate a distinct mechanism, not an undocumented relaxation |

The economic hypothesis is falsified by materially negative prospective
after-cost lifecycles, persistent losses on both sides, or measured friction
consuming the historical ETH surplus. A quiet window with no eligible signals
tests liveness and cadence but does not establish or refute PnL edge.

## Trade-off matrix

| Option | Benefit | Cost / risk | Assessment |
|---|---|---|---|
| Keep v14 unchanged after flat | More cross-asset live samples | Executes mappings already rejected historically | Not recommended for the next generation |
| Activate v17 | Adds ETH pullback | Retains unsupported BTC and SOL generic transfers | Inferior isolation |
| Prepare v18 | Removes rejected transfers and adds distinct ETH hypothesis | Fewer executable mappings; remaining routes still unproven | Recommended inactive candidate |
| Stop all live research | No new execution losses | Cannot measure venue friction or prospective behavior | Does not advance the stated objective |

## Decision

Prepare v18 as an inactive next-flat candidate. Do not activate it while HYPE is
open. After the current lifecycle closes, publish a final v14 audit, verify the
venue is flat and order-free, create and verify a prestart backup, compare the
resolved HYPE result with the frozen hypothesis, and request explicit operator
approval before any live restart.

**Overall confidence: low-to-medium.** Confidence is high in configuration
isolation and the rejection of unchanged ETH/SOL transfer, but low in the
economic value of the remaining portfolio. Positive, attributable, after-cost
forward lifecycles across both directions would raise confidence. Continued
negative native HYPE results, no usable ETH signals, or adverse BTC Hulk outcomes
would lower it and require a different mechanism rather than wider unguided scope.
