# Live forward allocation reversal

**Evidence cutoff:** 2026-08-05 07:26 EDT  
**Active run:** `bidirectional-live-1785826133777`  
**Execution effect:** next-flat profile selection only  
**Automatic restart:** false

## Decision

Withdraw the pending threefold canonical-HYPE notional increase. Select
`configs/multi_asset_bidirectional_range_retired_candidate.toml` for the next
flat-boundary run instead of the `$75` HYPE candidate. This keeps canonical
HYPE execution at `$25` and 5x isolated leverage while continuing to collect
live evidence. The active backend, its BTC/HYPE positions, and their venue
protection are unchanged.

This is a sizing decision, not an execution gate. Canonical HYPE remains long
and short executable. Broad range-onset becomes observe-only because its only
resolved live trade lost and its new portfolio-compatible BTC/SOL challengers
are below PF 1. Hulk and BTC source-follow remain executable at their existing
provider-specific sizes.

## Evidence update

| Evidence | Resolved | Result | Interpretation |
|---|---:|---:|---|
| Canonical HYPE venue lifecycles | 5 | 4W/1L, `+$1.234701`, PF `6.5141` | favorable but small live sample |
| Canonical HYPE fixed-60m forward entries | 10 | 5W/5L, `-110.5705 bps`, PF `0.6660` | crossed its declared PF-at-or-below-one falsifier |
| Historical deployed HYPE extension | 956 development + 200 opened holdout | PF `0.8524` development; PF `0.9629` holdout | large, directly adverse sizing context |
| HYPE Hulk fixed-60m challenger | 4 | 1W/3L, `-184.6386 bps`, PF `0.1045` | does not justify inheriting the larger cap |
| HYPE range/absorption challenger | 3 | 2W/1L, `+136.3885 bps`, PF `21.8654` | 86.0% outcome concentration; all long and too sparse |

The fixed-60m challenger does not reproduce the deployed 8h-soft/24h-hard exit,
so it does not prove the canonical live contract is losing. It does test the
same entry timestamps under causal venue BBO, fees, funding, capacity, and a
fixed observation horizon. Its negative result, together with the much larger
negative deployed-shape replay, contradicts increasing exposure threefold from
five favorable live closes.

The live result is not discarded. Keeping the exact `$25` route running is the
experiment that can determine whether its divergence from historical evidence
persists. Increasing size now would combine edge validation with allocation
validation and make a later result harder to attribute.

## Replacement profile verification

A report-only one-shot checkpoint loaded the replacement profile and produced:

- profile `multi_asset_bidirectional_range_retired_v3`;
- fingerprint `4910312f67ea9fcdaea552ae7802a04b34aa85b68a7657356ab43c7fc296d8e8`;
- HYPE asset maximum notional `$25` at 5x;
- range-onset `execution_symbols = []`;
- `execution_authority = none` and `automatic_restart = false`; and
- `wait_for_flat_and_no_orders`, blocked by the protected BTC and HYPE opens.

The SOL asset adapter ceiling remains `$75`, but its only executable SOL
provider, Hulk, has an explicit `$25` provider override. The falsified SOL
aligned-range provider is absent. Therefore no automatic SOL route in this
profile receives `$75` sizing.

## Open exit-path evidence to resolve before activation

The current HYPE long opened at 20:10 EDT on August 4, crossed its 8-hour soft
boundary at 04:10 EDT on August 5, and has a 20:10 EDT hard boundary. The
backend extended it because the completed regime context was directionally
supportive. As of 07:34 EDT it had:

- `+528.40 bps` completed-bar MFE since entry;
- `+391.21 bps` current directional return;
- `137.20 bps` giveback from peak;
- approximately `+$0.9551` marked net after entry fee and funding; and
- an original venue stop that could still convert the lifecycle to about
  `-$0.2209` net before future slippage/funding.

The frozen post-soft 20/30/40-bps trails all triggered between 04:28 and 04:37
EDT at reference prices above the current mark. The only already-resolved HYPE
extension also underperformed its estimated soft-boundary exit by `$0.1516`;
all three post-soft trails would have improved its actual exit, although the
estimated soft exit remained better than the trails.

This is actionable exit research but not yet a policy change: one resolved and
one open extension cannot establish the best giveback. The active trade is not
altered. When it closes, compare its exact fill, exit fee, funding, actual net,
soft-boundary estimate, and all three causal trail estimates before starting
the next profile. A trail that improves both completed extensions after costs
would support a narrowly staged post-soft protection experiment; a late rally
that makes the actual extension superior would falsify that recommendation.

## Validation and revision conditions

Before activation, the startup must prove venue flat with no owned orders,
create and restore-verify the immutable pre-start backup, and emit a fresh
configuration identity matching the fingerprint above. Every new position must
then retain a venue stop and complete fill, fee, funding, slippage, regime, and
missed-opportunity telemetry.

Confidence in withdrawing the size increase is **medium-high**: the historical
sample is large and the new forward sample crossed its own declared falsifier,
but the live exit contract differs from the fixed-hour challenger. Additional
reconciled canonical HYPE trades that remain profitable after costs without one
trade dominating would support reconsidering allocation. Continued PF below
one, adverse short-side evidence, or live friction materially above the current
sample would strengthen the decision to retain or reduce the current size.
