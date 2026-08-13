# ETH Pullback-Routed v17 Candidate Review

## 1. Problem restatement

The active v14 portfolio grants automatic execution to the generic
`hype_breakout_onset_bidirectional_v1` provider on BTC, ETH, SOL, and HYPE.
Historical evidence rejects the unchanged ETH transfer, while the portfolio
still needs a credible long-capable ETH mechanism. The decision is whether to
prepare a next-run profile that replaces only generic ETH execution with the
distinct ETH precompression-pullback provider.

Success for this review means:

- preserve BTC, SOL, and HYPE execution exactly;
- preserve both long and short capability;
- prevent two automatic ETH providers from competing for the same coin;
- retain one position per coin and four positions portfolio-wide;
- retain 5x isolated leverage and the existing per-asset notional caps;
- make no live runtime, order, position, stop, or exit-policy change;
- bind the decision to immutable evidence and an explicit falsifier.

## 2. Known facts and assumptions

### Known from current artifacts

- Active v14 run: `bidirectional-live-1786028939765`, profile fingerprint
  `e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900`.
- The immutable live prefix ends at `2026-08-07T05:57:13.520209+00:00`, has
  11,144 rows, complete coverage, zero faults, one completed SOL short, and one
  protected open HYPE short.
- The ETH pullback observer recorded 887 forward evaluations and zero eligible
  signals in that prefix. This is valid liveness evidence but no outcome
  evidence.
- Generic ETH breakout transfer was negative after modeled costs in development
  (797 trades, PF 0.8426, -7,679.54 bps) and the opened final 60-day block
  (154 trades, PF 0.8220, -1,593.88 bps).
- The immutable v14 opportunity matrix also rejects relaxing the exact
  five-minute breakout prerequisite for generic ETH longs:

| OPI cohort | Resolved | W/L | Net bps | PF |
|---|---:|---:|---:|---:|
| Aligned | 6 | 1/5 | -91.5914 | 0.1128 |
| Opposed | 6 | 1/5 | -96.1737 | 0.1250 |
| All | 5 | 1/4 | -98.8639 | 0.1220 |

- The distinct ETH precompression-pullback mechanism produced:

| Scope | Side | Trades | W/L | Net bps | PF |
|---|---|---:|---:|---:|---:|
| Development | Both | 282 | 67/215 | +1,657.98 | 1.1111 |
| Development | Long | 142 | 32/110 | +254.70 | 1.0332 |
| Development | Short | 140 | 35/105 | +1,403.28 | 1.1932 |
| Opened final 60d | Both | 56 | 18/38 | +322.33 | 1.1208 |
| Opened final 60d | Long | 26 | 10/16 | +345.18 | 1.3109 |
| Opened final 60d | Short | 30 | 8/22 | -22.85 | 0.9853 |

### Assumptions

- The current provider implementation continues to match the reviewed
  historical contract: completed one-minute evaluations, fresh completed
  five-minute breakout onset, completed-hour SMA10/SMA30 side, prior BBWP
  compression, directional pullback, 60-bps venue stop, and 12-hour hold.
- The modeled 13-bps round-trip friction is a screening assumption, not a
  promise of live cost parity. Venue fills must measure the difference.
- Historical trades are selected and overlapping research evidence; they are
  not independent live trials.

## 3. Analysis

The generic ETH route fails at the signal level, not merely at allocation. Its
unchanged transfer lost in two chronological blocks, and the live-window
single-blocker counterfactual remained negative whether order-book pressure was
aligned, opposed, or ignored. Increasing leverage, changing portfolio weights,
or removing the five-minute breakout requirement would change the rate or
frequency of loss without supplying a positive signal.

The ETH pullback mechanism is materially different. It requires both prior
compression and a directional pullback around a fresh breakout onset. Its
opened final block was positive overall and on longs, which makes it a plausible
bidirectional research candidate. However, it was selected from a 20-cell
stop/hold surface, its fifth development fold lost 1,630.88 bps, 245 of 338
historical exits were protective stops, and long/short leadership reversed
between development and the opened final block. Confidence therefore remains
low.

The current zero-signal live observation does not falsify the implementation:
all 887 evaluations were blocked by the absent fresh canonical breakout onset,
and the latest readiness telemetry still contained the expected three-part
contract. It also does not validate economic edge because no eligible signal
has resolved.

## 4. Candidate contract and exact change

Inactive profile:
`configs/multi_asset_bidirectional_hype75_eth_pullback_routed_candidate_v17.toml`

Relative to active v14, only three textual fields change:

1. Profile identity changes to
   `multi_asset_bidirectional_hype75_eth_pullback_routed_candidate_v17`.
2. Generic breakout execution changes from BTC/ETH/SOL/HYPE to BTC/SOL/HYPE.
3. ETH pullback execution changes from observe-only to ETH.

Unchanged portfolio mechanics include Hulk execution on BTC, generic breakout
execution on BTC/SOL/HYPE, both sides for every provider, 5x isolated leverage,
BTC/ETH $25 caps, SOL/HYPE $75 caps, maximum four concurrent positions, and one
position per coin.

ETH pullback execution remains taker IOC, maximum signal age 60 seconds,
60-bps venue-protective stop, no target, fixed 12-hour maximum hold, and $25
maximum notional.

## 5. Risks and failure modes

- Live IOC fees, slippage, acknowledgement latency, funding, or stop gap-through
  can consume the thin historical surplus.
- The selected stop/hold surface and opened final block are not pristine sealed
  confirmation evidence.
- A quiet forward window can leave the candidate too sparse to evaluate.
- Side leadership may continue to rotate, producing an aggregate that conceals
  an unstable long or short component.
- A provider/runtime feature mismatch, stale breakout onset, missing venue stop,
  duplicate ETH position, or any route beyond ETH is a technical failure and
  invalidates the experiment.
- Restarting while the current HYPE lifecycle is open risks mixing profile and
  lifecycle ownership. v17 must remain inactive until a verified-flat boundary.

## 6. Validation plan

Before any activation:

1. Verify active v14 is flat on all four assets and has no owned entry, stop,
   target, or close orders.
2. Publish the final immutable v14 audit and reconcile every lifecycle.
3. Create and independently verify a new prestart backup for the exact v17
   fingerprint.
4. Re-run config tests proving the only route replacement is generic ETH to ETH
   pullback, both sides remain enabled, and live start fails closed without both
   authority flags.
5. Obtain explicit operator approval for the flat-boundary profile transition.

During a future v17 canary, measure exact venue entry/exit fills, fees, funding,
slippage, acknowledgement latency, stop identity, holding time, direction,
entry features, and one-position-per-coin enforcement. Twenty resolved ETH
lifecycles is a first review checkpoint, not proof of edge.

## 7. Recommendation and trade-offs

| Option | Evidence benefit | Main cost | Recommendation |
|---|---|---|---|
| Keep v14 indefinitely | No transition risk | Retains historically negative generic ETH execution | Reject as next profile |
| Loosen generic ETH breakout | Higher cadence | Current aligned/opposed/all relaxations are all negative | Reject |
| Add ETH pullback beside generic ETH | More signals | Same-coin conflict and ambiguous attribution | Reject |
| Replace only generic ETH with ETH pullback | Distinct long-capable mechanism and clean attribution | Sparse, selected, low-confidence candidate | Prepare inactive v17 |
| Disable ETH execution entirely | Simplest portfolio | No ETH contribution or live transfer evidence | Valid fallback if v17 falsifies |

Recommendation: freeze v17 as the next verified-flat research candidate, but do
not activate it while HYPE is open. This is a portfolio routing improvement over
keeping a historically rejected generic ETH transfer; it is not a profitability
claim.

Confidence: medium for the routing decision because the negative generic ETH
evidence is consistent across historical and current counterfactual sources.
Confidence: low for the ETH pullback economic hypothesis because it is selected,
sparse in forward operation, and has zero eligible live signals.

The routing recommendation is falsified by any non-ETH route difference,
one-sided authority, missing stop, duplicate ETH route, or implementation
mismatch. The economic hypothesis is weakened or falsified by materially
negative after-cost prospective ETH outcomes, persistent losses on both sides,
or measured friction consuming the historical surplus. These outcomes remain
reported trial results rather than implicit runtime gates.

## 8. Runtime decision

No live strategy, provider authority, position, order, stop, target, sizing
policy, backend process, checkpoint process, or portfolio configuration changed
as a result of this review. v14 remains authoritative until a later verified-flat
transition receives explicit approval.
