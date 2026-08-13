# Evidence-routed next-flat portfolio candidate

**Decision timestamp:** 2026-08-05 13:53 EDT  
**Candidate:** `multi_asset_bidirectional_evidence_routed_hype75_v9`  
**Authority:** inactive, report-only decision; no staging, restart, or live mutation

## Objective and constraints

The portfolio needs to remain bidirectional and capable of frequent low-timeframe
participation while allocating live research capital to the strongest currently
observed mechanisms. All configured providers must continue producing telemetry
so missed opportunities and rejected routes remain measurable. The candidate
must preserve one position per coin, isolated venue leverage limits, venue-native
protection, and the current HYPE lifecycle contract.

## Current evidence

The immutable live audit resolves 14 trades across compatible profiles:

| Executed mechanism | Closes | W/L | Net USD | PF | Interpretation |
|---|---:|---:|---:|---:|---|
| HYPE breakout / HYPE | 6 | 5/1 | `+$2.0995` | `10.3762` | Favorable but sparse; historical deployed shape is negative |
| Hulk expansion / BTC | 2 | 2/0 | `+$0.3439` | no losses | Favorable but only two long trades; historical blocks conflict |
| Source Follow / BTC | 5 | 3/2 | `-$0.1046` | `0.6951` | Live result agrees with negative one-year deployed-shape replay |
| Range Onset / ETH | 1 | 0/1 | `-$0.1744` | `0.0` | Single live loss; broader route already selected for retirement |

The one-year Source Follow deployed-shape replay contains 782 trades and ended
at `-$17.82`, profit factor `0.6193`, after `$13.08` in fees. Both long and short
subsets were negative. That is stronger negative mechanism evidence than the
five-trade live sample alone.

Hulk-on-SOL failed its prior validation block. Hulk-on-ETH and Hulk-on-HYPE do
not yet have accepted matched execution evidence. Keeping those mappings armed
would allow an unreviewed Hulk signal to occupy HYPE before the canonical HYPE
breakout provider because Hulk has the higher router priority.

## Candidate contract

Executable provider-symbol pairs:

- `hulk_expansion_bidirectional_tuned_v2|BTC`, long and short, `$25` maximum
  notional, 5x isolated, structural stop clamped to 20-75 bps, 3R target, and
  24-hour maximum hold;
- `hype_breakout_onset_bidirectional_v1|HYPE`, long and short, `$75` maximum
  notional, 5x isolated, 80-bps stop, eight-hour soft hold, and extension while
  regime-supported to a 24-hour hard limit.

Observe-only provider-symbol pairs:

- Hulk expansion on ETH, SOL, and HYPE;
- Range Onset on BTC, ETH, SOL, and HYPE; and
- Hypervelocity Source Follow on BTC.

Observe-only means the same providers continue to generate readiness, intents,
blockers, and forward paths. It does not erase them, disable research, or claim
that they can never recover. Re-enabling any route remains an explicit operator
decision rather than an automatic performance gate.

At the audit's `$505.8873` equity, simultaneous capped BTC and HYPE positions
would use at most `$20` margin, approximately `3.95%` of equity, and `$100`
notional. This is an aggressive research allocation relative to the current
signal evidence, not a forecast of production returns.

## Alternatives and trade-offs

| Profile | Benefit | Failure mode |
|---|---|---|
| Allocation-isolation v8 | Changes fewer routing variables | Keeps negative Source Follow and unreviewed Hulk mappings executable |
| Evidence-routed fixed-eight-hour v7 | Narrows execution scope | Confounds routing and allocation with a HYPE exit change |
| Evidence-routed extension v9 | Concentrates capital while preserving HYPE lifecycle semantics | Only two executable coin mappings; both edge estimates remain sparse or contradictory |

The v9 profile is the recommended portfolio candidate. The v8 profile remains
preserved as the clean allocation-only comparator and rollback alternative.

## Confidence and falsifiers

**Configuration confidence: high.** A contract test proves the v9 profile
differs from v8 only in provider execution scope and the required removal of
now-inapplicable sizing overrides. Both selected providers retain long and short
capability. A loaded scope other than Hulk/BTC plus HYPE-breakout/HYPE, a changed
HYPE hold policy, or widened live authority falsifies this claim.

**Portfolio-edge confidence: low-to-medium.** HYPE live evidence is favorable but
historically contradictory, and Hulk BTC has only two live closes. Twenty to
thirty profile-matched HYPE closes with after-cost PF at or below one, or 10-20
Hulk BTC closes with negative after-cost PnL/PF at or below one, would materially
weaken the portfolio thesis. These are manual review thresholds, not runtime
gates.

Failure modes include regime shift, sparse cadence, HYPE profit concentration,
stop gaps, canceled public depth, rate-limit interruption, and opportunity cost
from an observe-only mechanism recovering before review. Observer telemetry and
missed-opportunity reporting are required to detect the last failure mode.

## Validation and transition

1. Leave the active backend and open HYPE position unchanged.
2. Keep v8 and v9 as separate inactive candidate files.
3. Continue all provider observers and the BTC/HYPE transfer observer.
4. At a venue-flat, order-free boundary, compare the latest compatible live
   audit and missed-opportunity matrix before choosing v8 or v9.
5. Any live transition requires the mandatory verified prestart backup and a
   fresh explicit live command. No automatic promotion is authorized.

