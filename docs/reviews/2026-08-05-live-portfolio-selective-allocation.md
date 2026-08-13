# Live portfolio decision — range retirement and selective HYPE/SOL allocation

**Evidence cutoff:** 2026-08-05 05:57 EDT  
**Live run:** `bidirectional-live-1785826133777`  
**Execution state:** armed backend unchanged; BTC and HYPE open and protected  
**Decision authority:** next-flat configuration only; no automatic restart

## Problem and success criteria

The portfolio needs repeated, after-cost live opportunities without returning
to indiscriminate high leverage or adding a universal regime gate that removes
valid trades. The decision inputs are venue-reconciled live lifecycles,
causal provider evaluations, explicit portfolio-compatibility journals,
observed fill friction, and frozen forward challengers. A useful next profile
must:

1. preserve bidirectional automatic execution for the providers that produced
   live evidence;
2. remove a demonstrated weak provider rather than filter every strategy;
3. increase information from research capital without changing leverage;
4. activate only from a venue-flat, no-owned-orders boundary; and
5. remain falsifiable from exact run, provider, coin, side, fees, funding, and
   missed-opportunity records.

## Authoritative live record

The exact current run has two resolved lifecycles, both wins, for `+$0.282014`
after `$0.035675` fees and `-$0.002411` funding. It also has two open protected
longs, BTC and HYPE. At the evidence cutoff the marked portfolio increase was
approximately `+$0.96` from a `$504.14269549` initial execution-collateral
baseline. Marked PnL is provisional until venue-flat reconciliation.

The compatible archive is descriptive rather than one capital path:

| Provider and coin | Closed | W/L | Net USD | PF | Evidence interpretation |
|---|---:|---:|---:|---:|---|
| canonical HYPE breakout | 5 | 4/1 | `+$1.234701` | `6.51` | favorable live sample; historical deployed shape remains negative |
| BTC source-follow 5m | 3 | 2/1 | `+$0.063001` | `1.51` | positive but mixed and sparse |
| BTC Hulk | 1 | 1/0 | `+$0.133813` | no loss | favorable single trade; historical evidence contradictory |
| ETH range-onset | 1 | 0/1 | `-$0.174380` | `0.00` | only resolved range execution and structurally opposed at entry |

Confidence is high in these arithmetic identities because every lifecycle
reconciles to venue fills, both fill fees, signed funding, and close-fill gross
PnL. Confidence in durable edge is low-to-medium because only ten compatible
lifecycles exist and three profile fingerprints are represented.

## Regime and entry finding

A generic structure-alignment gate is contradicted by the live record:

- BTC Hulk won `+$0.133813` with a `-0.4444` structure-support score and
  `-0.7778` component alignment.
- A BTC source-follow winner earned `+$0.051972` with only `0.3333` structure
  support.
- Raising the retrospective HYPE structure threshold to `0.75` would remove
  two winners totaling `+$1.131976` while retaining the only HYPE loss.
- The ETH range-onset loss entered with `0.0833` structure support and
  `-0.7778` component alignment.

This supports provider-specific range retirement. It does not support turning
the regime detector or component stack into a universal entry gate. Regime,
component, and order-book telemetry remain causal descriptive evidence for
provider-specific challengers.

## Missed-opportunity record

Only portfolio-compatible paths can inform deployable economics:

| Frozen challenger | All resolved | Deployable resolved | Deployable result | Decision |
|---|---:|---:|---:|---|
| relaxed canonical HYPE breakout | 5 | 4 | `2W/2L`, `-28.14 bps`, PF `0.67` | retain canonical 5m breakout requirement |
| BTC structural range continuation | 3 | 0 | unavailable | all paths overlapped open BTC; do not activate |
| HYPE range/OPI absorption | 1 | 0 | unavailable | favorable path overlapped open HYPE; mechanism evidence only |
| HYPE Hulk squeeze relaxation | 1 | 0 | unavailable | losing path overlapped open HYPE; do not activate |
| SOL aligned range relaxation | 1 | 1 | `0W/1L`, `-14.01 bps`, PF `0.00` | keep range retired; one loss does not establish a general effect |

The favorable and adverse non-deployable HYPE paths cannot be added to
portfolio PnL. They demonstrate that setup identity and timing matter even
inside the same broad directional move. The SOL path was different: SOL was
flat and account capacity was available, so its fixed 60-minute result is a
genuine missed-opportunity observation. Its modeled `-$0.105094` is observer
evidence rather than venue PnL because no SOL order was submitted.

### Forward update: standalone alpha versus incremental portfolio alpha

By 03:09 EDT the frozen relaxed-HYPE observer had seven resolved fixed-hour
paths after its prospective cutoff: `5W/2L`, `+135.8623 bps`, PF `2.61` after
modeled taker fees and funding. That standalone result initially looks
favorable, and its largest absolute contribution was only `20.1%`. It is not,
however, the deployable portfolio result.

The causal portfolio journal recorded ten attempts. Six were unavailable
because the canonical HYPE strategy already occupied the one permitted HYPE
position. The four incrementally deployable paths remained `2W/2L`,
`-28.1350 bps`, PF `0.67`; three later attempts were still pending. The
favorable standalone paths therefore overlapped a canonical position already
capturing the same HYPE move. Adding the relaxed provider alongside canonical
HYPE would double-count that move in research while admitting only the weaker
incremental paths in live routing.

The relaxed-HYPE profile remains staged but unselected. Replacing canonical
HYPE would be a different experiment and is not supported by this comparison:
canonical HYPE has five reconciled closes at `+$1.234701`, PF `6.51`, plus the
current protected open lifecycle. New deployable relaxed paths with aggregate
PF above one would update this conclusion; continued overlap or deployable PF
at or below one would falsify incremental value.

The SOL aligned-range observer subsequently reached four portfolio-deployable
fixed-hour resolutions: `3W/1L`, `+31.1801 bps`, PF `3.2251`. The largest
absolute outcome contributes `51.3%`, and all four paths were long. This is
enough to test the exact mechanism at small live size, not enough to claim a
durable or bidirectional edge. The selected profile therefore retains general
range-onset retirement and adds only the frozen exact-one-blocker SOL
challenger: the sole canonical blocker must be `awaiting_hourly_sma_cross`,
the decision must be no older than 60 seconds, current Hyperliquid L2 OPI must
align with the intended side, and a recorded accepted entry enforces a
75-minute rearm. The execution contract is both-side, `$75` maximum notional,
5x isolated leverage, a 60-bps venue stop, and a fixed 60-minute exit.

### Exit-policy update: isolate sizing from holding behavior

The first resolved regime-supported HYPE extension finished `-$0.151589`
below its estimated fixed-8h exit. That single result motivated a staged fixed
8-hour policy, but the next live extension contradicted a one-sided conclusion.
At 05:15 EDT the still-open HYPE lifecycle was `+42.25 bps` beyond its 8-hour
boundary, with `+103.02 bps` post-boundary MFE, while 5m and 15m structure
remained directionally supportive. Its estimated exit-now net was `+$1.1263`;
that value is provisional and can reverse before the lifecycle closes.

The extension sample is therefore one resolved underperformer and one
unresolved outperformer. It does not establish that either fixed-8h or
regime-supported extension has superior expectancy. Changing both allocation
and exit behavior in the same next-flat HYPE experiment would also prevent
causal attribution. The selected profile consequently preserves the running
8-hour soft boundary, regime-supported extension, and 24-hour hard boundary;
only canonical HYPE sizing changes. Closed extension outcomes continue to be
journaled against the fixed-soft and predeclared post-soft trail challengers.

## Selected next-flat experiment

The selected profile is
`configs/multi_asset_bidirectional_range_retired_hype75_candidate.toml`.
It is not active. Relative to the running profile it:

- removes all range-onset execution symbols;
- retains long and short automatic execution for Hulk on BTC/ETH/SOL/HYPE;
- retains long and short BTC source-follow execution;
- retains long and short canonical HYPE breakout execution;
- leaves leverage at `5x` and margin mode isolated;
- raises only canonical HYPE maximum notional from `$25` to `$75`; and
- pins HYPE Hulk at `$25` so the allocation change is provider-specific; and
- adds the exact SOL aligned-range challenger at `$75`, while leaving the
  broad range-onset provider execution-disabled; and
- preserves canonical HYPE's 8-hour soft boundary, regime-supported extension,
  24-hour hard boundary, and 80-bps venue stop.

At approximately `$505` execution collateral, canonical HYPE would use about
`$15` margin. The modeled maximum simultaneous configured margin fraction
rises from approximately `5.94%` to `7.92%`. This is a canary information-size
increase, not an edge or profit forecast. A full 80-bps HYPE stop at `$75`
notional is approximately `$0.60` gross before fees, funding, and slippage.

The HYPE live-capacity instrument walks the candidate quantity through the latest
240 selected-run HYPE public-L2 snapshots. At 05:33 EDT, both buy and sell
orders visibly completed in `240/240` books. Buys filled entirely at BBO in
`96.25%` of snapshots, with approximately `0.00 bps` p95 and `0.48 bps`
maximum impact. Sells were BBO-only in `93.75%`, with `0.12 bps` p95 and
`1.36 bps` maximum impact. This supports current visible capacity at `$75` but
does not assume fills: displayed liquidity can cancel during the observed
approximately `1.28s` acknowledgement path, and the rolling books are not
conditioned on future signal timestamps.

The checkpoint reports `wait_for_flat_and_no_orders`, blocked by BTC and HYPE,
with `automatic_restart=false` and `execution_authority=none`. The TUI Config
screen now renders the running and pending profile identities separately and
shows the exact queued caps as `BTC $25 / ETH $25 / SOL $75 / HYPE $75` plus
`NEXT HYPE EXIT REGIME EXTEND 8H → HARD 24H`.

## Validation and falsifiers

The next profile must not activate until every venue position and every owned
order is reconciled flat. Before a live restart, regenerate the checkpoint and
require `candidate_flat_no_orders`, verify the exact candidate fingerprint,
and confirm all provider-symbol direction and sizing contracts.

The allocation hypothesis is weakened or falsified by any of the following:

- canonical HYPE live PF falls to or below one after costs;
- one HYPE lifecycle dominates aggregate absolute PnL;
- short-side results contradict the bidirectional contract;
- `$75` top-level capacity or realized slippage materially differs from the
  `$25` sample;
- rolling candidate-depth completion falls below 100% or impact materially
  exceeds the modeled 2-bps entry-slippage assumption;
- resolved maximum-hold extensions underperform the soft boundary on a larger,
  causally complete sample;
- a non-canonical HYPE provider receives the `$75` cap;
- broad range-onset routes in the selected profile;
- the SOL challenger routes without the exact sole blocker, a fresh aligned
  Hyperliquid L2 observation, a flat SOL position, or its 75-minute rearm;
- SOL short-side paths lose after costs, aggregate PF falls to or below one,
  or realized IOC friction materially exceeds the observer model;
- run, profile, archive, fill-leg, fee, or funding scopes stop reconciling.

Good enough for the next canary means exact configuration identity, venue-flat
startup, protected positions, complete after-cost journaling, and enough new
canonical HYPE executions to compare `$75` friction against the `$25` sample.
It does not mean the current sample establishes a durable profitable strategy.

## Early profit-lock challenger

The live audit now compares actual closed lifecycles with three previously
declared early profit-lock mechanisms: activation/floor/trailing giveback of
25/15/10, 40/15/20, and 60/15/30 bps. The calculation is causal: activation
and stop updates use only completed one-minute bars and a newly activated stop
cannot trigger from the same bar. Gap-through exits use the adverse next-bar
open. Each counterfactual reuses the lifecycle's measured exit
fill/reference ratio and fee rate and includes exact funding through its
counterfactual exit. Missing holding candles withhold the lifecycle.

The compatible N10 archive contradicts all three early-lock settings:

| Frozen policy | Triggered | Estimated net | Actual net | Delta vs actual | PF |
|---|---:|---:|---:|---:|---:|
| 25/15/10 bps | 7 | `-$0.035027` | `+$1.257135` | `-$1.292162` | `0.91` |
| 40/15/20 bps | 6 | `+$0.152794` | `+$1.257135` | `-$1.104341` | `1.38` |
| 60/15/30 bps | 5 | `+$0.133574` | `+$1.257135` | `-$1.123561` | `1.26` |

Canonical HYPE N5 is the clearest negative partition: the three deltas are
`-$1.230449`, `-$1.209249`, and `-$1.146263`. Early profit locking at these
settings would have surrendered most of the actual HYPE net. These policies
are therefore not promoted and the open HYPE trade was not altered.

BTC source-follow N3 is a small contrary observation. Its 40/15/20 policy
estimated `+$0.104908` more than actual. Confidence in that mechanism is low
because three overlapping live lifecycles cannot establish repeatability.
More resolved BTC source-follow trades that retain a positive after-cost delta
would increase confidence; a negative expanded sample would falsify it.

Screen 6 exposes the archive, HYPE, BTC, and current-run conclusions with
`REPORT ONLY`, `UNDERPERFORMED`, and `OBSERVE` labels. The strict parser rejects
authority, changed policy definitions, lifecycle count disagreement, and
economic totals that do not reconcile. The checkpoint publisher was refreshed
without signaling the armed backend.

## Post-soft exit challenger

The read-only checkpoint now evaluates frozen 20, 30, and 40 bps giveback
trails after the configured HYPE soft maximum-hold boundary. The challenger
uses only prior completed one-minute extrema, charges the actual lifecycle's
measured exit fill/reference ratio and fee rate, and includes funding through
the counterfactual trigger. It has no execution authority and cannot change,
retain, or close a live position.

Only one resolved extended HYPE lifecycle is eligible. Its actual later exit
netted `$0.096600`; the estimated fixed soft-boundary exit netted `$0.248189`.
The 20/30/40 bps trails all triggered and estimated `$0.200382`, `$0.175017`,
and `$0.149964` net respectively. They improve on the actual late exit by
approximately `$0.104`, `$0.078`, and `$0.053`, but each remains worse than
the fixed soft-boundary estimate.

Confidence is high in the report's arithmetic and authority separation because
the parser rejects lifecycle, cost, policy, or contract imbalance and the live
checkpoint rendered the exact values. Confidence that any trail has exit edge
is low because `N=1` cannot distinguish a repeatable effect from one path. New
resolved HYPE extensions in which a trail repeatedly beats both the actual and
soft-boundary references would update that assessment; failure to do so would
falsify promotion.

The checkpoint publisher was rotated without signaling the armed backend.
At the latest acceptance, publisher PIDs were `9452/9463`; backend PIDs
remained `12301/12381`, state `running_consistent`, with BTC and HYPE open and
protected.
The optimized Screen 6 render displayed the three frozen policies and exact
actual-PnL deltas. Fresh validation passed 3,387 non-network Python tests and
248 Rust tests, plus Ruff, formatting, strict Clippy, and the release build.

## Open-profit protection observation

The checkpoint now publishes report-only open-profit protection evidence. For
each open lifecycle it reconciles marked net PnL from the entry, signed size,
entry fee, and funding; estimates the prospective exit fee using the measured
entry fee rate; and evaluates both immediate exit and the already-existing
venue stop. It excludes future funding and slippage and has
`execution_authority=none`. No stop, target, position, or strategy setting was
changed.

At the 02:09 EDT acceptance render, HYPE was approximately `+$0.82` net on an
estimated immediate exit but approximately `-$0.22` at its existing stop. The
resulting marked-to-stop giveback was about `$1.04`, with no marked profit
protected. BTC was approximately `+$0.16` on immediate exit and `-$0.18` at
its existing stop, a `$0.34` giveback. These values are point-in-time exposure
measurements, not evidence that moving either stop would improve expectancy.

The next HYPE soft boundary is 04:10 EDT. The predeclared resolved-lifecycle
comparison is actual venue net versus estimated fixed-soft exit, the frozen
20/30/40 bps post-soft trails, and the observed profit-giveback path. A tighter
profit-lock challenger gains support only if it repeatedly preserves more net
profit after fees and slippage. It is falsified if it repeatedly exits before
profitable continuation that the current stop/extension policy captures.

Screen 8 now orders open lifecycle evidence with the selected coin first while
retaining other open positions. This corrected a clipping defect where BTC
consumed the panel and hid HYPE's risk line. The optimized 170x48 live render
selected HYPE and displayed its venue stop, soft timer, `$1.04` giveback line,
path excursion, and the BTC summary afterward. The backend remained
`running_consistent`; no execution process was restarted.

## Restart-safe maximum-hold decisions

Maximum-hold boundary state is now recovered from the durable cohort ledger
rather than a process-local set. A recovered extension is not emitted again
with a conflicting timestamp, and a persisted exit decision remains binding
if the backend recovers before the venue close completes. Focused policy,
controller, telemetry, and runner tests passed 32 cases; the full non-network
Python suite passed 3,392 tests with four intentional deselections.

An extended lifecycle now receives two non-conflicting causal records: the
soft decision that chose extension and a terminal exit decision when support
later disappears or the hard deadline arrives. The research projection counts
soft choices independently from terminal exits, so exit attribution does not
rewrite the earlier decision. The complete Rust TUI suite, strict Clippy,
Ruff, formatting, and focused checkpoint projections also passed.

This source change is inactive in the currently running backend until a future
verified-flat restart. The current armed process was not signaled. A duplicate
decision for the same lifecycle, a recovered exit changing outcome, or a
recovery-time scheduler fault would falsify this acceptance.
