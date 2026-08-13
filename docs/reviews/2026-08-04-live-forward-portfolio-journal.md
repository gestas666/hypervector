# Live forward portfolio journal — 2026-08-04

## Problem restatement

Evaluate the armed shared-account portfolio as an execution system and as a
source of forward research evidence. The required outputs are an exact current
trade record, protected live lifecycles, explicit missed-opportunity evidence,
and a falsifiable next-flat profile decision. Report-only challengers have no
order, sizing, exit, promotion, or portfolio authority.

## Authoritative live state

At `2026-08-04 22:56 EDT`, run
`bidirectional-live-1785826133777` remained `running_consistent` with zero
asset faults. BTC and HYPE were open; ETH and SOL were flat. Both open
positions had venue-native reduce-only stops.

| Symbol | Provider | Side | Entry | Mark | Marked net | Stop | Target |
|---|---|---:|---:|---:|---:|---:|---:|
| BTC | Hulk expansion | long | `63820` | `64391` | `+$0.210756` | `63423` | `65011` |
| HYPE | breakout onset | long | `54.958` | `55.858` | `+$0.393900` | `54.518336` | none |

The values are provisional while open. BTC had `19.66%` and HYPE `17.10%`
venue-reported liquidation distance at the captured checkpoint. No backend,
position, stop, target, or execution profile was changed during this review.

## Trade-record scopes

The active profile has two completed lifecycles, 2W/0L, `+$0.282014` net,
`$0.035675` fees, and `-$0.002411` funding. The compatible archive has ten
completed lifecycles, 7W/3L, `+$1.257135` net, `$0.200188` fees, and
`-$0.002767` funding. Its 23 venue fill legs are not 23 completed trades.

The TUI now leads current-profile capital-path panels with the two-trade scope
and retains the ten-trade archive as a separately labeled selectable record.
Mixing either scope back into the other would invalidate the display.

## Open-lifecycle reflection

BTC entry structure support was `+0.6667` and current support was `+1.0`.
HYPE entry structure support was `+0.8333`; its component overlay was
`-0.7778` at entry but reached `+1.0` while the trade advanced about 164 bps.
This is direct counterevidence to making the unvalidated component overlay a
hard entry gate. Both current structure contexts were
`still_directionally_supported`.

The HYPE stop remains below entry and there is no target. Generic trailing
protection is not selected: on 1,011 matched historical entries every tested
25/15/10, 40/15/20, and 60/15/30 activation/floor/giveback policy
underperformed the fixed-timer control. The current bounded maximum-hold
extension remains unchanged while direct live decision events accumulate.

## Frozen one-blocker evidence

The following results use recorded BBO capacity, the observed 4.32-bps taker
fee per side, official funding, fixed non-overlapping 60-minute windows, and
`$25` notional. They are executable estimates, not fills or portfolio PnL.

| Candidate | Resolved | W/L | Net bps | PF | State |
|---|---:|---:|---:|---:|---|
| HYPE relaxed 5m breakout blocker | 5 all / 4 deployable | 3/2 all / 2/2 deployable | `+16.90` all / `-28.14` deployable | `1.20` all / `0.67` deployable | losing when restricted to observed flat-entry opportunities |
| BTC structural range continuation | 3 | 1/2 | `-22.60` | `0.42` | weakened; all three overlapped the open BTC lifecycle |
| HYPE Hulk squeeze relaxation | 1 | 0/1 | `-27.57` | `0.00` | unfavorable and non-deployable; it overlapped the open HYPE lifecycle |
| HYPE range/OPI challenger | 1 | 1/0 | `+128.60` | no loss | favorable but non-deployable; it overlapped the open HYPE lifecycle |
| SOL aligned-book range relaxation | 0 | 0/0 | `0` | unavailable | one genuinely deployable fixed-horizon path pending |

The fifth relaxed-HYPE winner occurred while the portfolio already held HYPE.
It therefore cannot rescue the four genuinely deployable paths: those remain
2W/2L, `-28.14 bps`, PF `0.67`, with the largest absolute path contributing
`33.68%`. The all-path aggregate is useful mechanism evidence, but it is not
portfolio economics. The canonical 5m breakout requirement remains in place.
The BTC structural challenger is negative and remains report-only.

## HYPE range/OPI mechanism diagnostic

The frozen HYPE candidate entered counterfactually long at `55.447` after an
opposed routing-publication OPI of `-0.1520`. Its fixed horizon resolved at
`+128.60 bps` net. The live portfolio already held HYPE long, so the
compatibility journal correctly labels it `existing_symbol_position` rather
than a second deployable same-coin position. This favorable path is not
additive portfolio PnL and cannot be counted as another trade.

The independently recorded canonical public-trade tape was refreshed through
the event window. Aggressor notional was buy-dominant before and after entry:

| Window | Buy-minus-sell imbalance | Trade-price path |
|---|---:|---:|
| prior 1 minute | `+5.29%` | `-6.85 bps` |
| prior 5 minutes | `+42.92%` | `+10.11 bps` |
| prior 15 minutes | `+36.62%` | `+69.37 bps` |
| next 15 minutes | `+21.85%` | `+70.70 bps` |

This proves that negative displayed book pressure was not mirrored by
aggressive selling. It is consistent with, but does not prove, passive ask
liquidity being consumed. Displayed orders can cancel or replenish, and the
current tape does not provide private queue identity. The causal mechanism
therefore remains low-to-medium confidence despite the favorable fixed path.
The result is also a single long episode and is not independent from the
canonical HYPE trade or the HYPE Hulk observer. The later Hulk relaxation
resolved `-27.57 bps` over its own fixed horizon. That divergence within one
broader move is evidence that entry timing and setup identity matter; it does
not support using broad trend direction as sufficient entry permission. Both
observer paths were non-deployable and must not be summed into portfolio PnL.

## Research infrastructure checkpoint

All four immutable Hyperliquid event recorders were healthy, but the DuckDB
public L2/trade projection had not been refreshed since August 3. A sequential,
report-only import added the completed BTC, ETH, SOL, and HYPE parts. The
database then covered books and trades through approximately `22:51 EDT` for
all four symbols. Explicit recorder gap rows were retained rather than filled
or hidden.

Observed compatible-history execution friction remains aligned on average:
mean fill slippage was `+0.62 bps`, mean acknowledgement latency was
`1.194 s`, and observed taker fees were approximately `4.32 bps`. The worst
observed fill slippage was `+8.71 bps`, so small 10–20-bps candidate edges are
not robust to tail execution.

## Frozen SOL aligned-book forward observer

The flat-symbol opportunity ranking found only one positive non-HYPE/BTC
one-blocker row: SOL range onset blocked by the hourly cross and conditioned on
side-aligned routing-publication OPI. Discovery evidence was N5, 4W/1L,
`+49.74 bps`, PF `1.76`, but all paths were long and mean net was only
`+9.95 bps`. This is too thin for promotion and could be erased by the observed
slippage tail.

Before inspecting any newer result, experiment
`v8-sol-aligned-range-fixed` was frozen at `2026-08-05T03:45:00Z`: SOL, both
directions, exact `awaiting_hourly_sma_cross` blocker, aligned side-adjusted
OPI, full `$75` top-level capacity, first post-publication BBO entry, 60-bps
adverse-BBO stop proxy, fixed 60-minute horizon, observed `4.32 bps` taker fee
per side, and official funding. The `$75` size corrects the generic discovery
matrix's `$25` assumption to the active SOL provider-symbol override.

The first candidate became available at `23:45:09 EDT`, long at `73.781`.
SOL was flat, two portfolio slots were available, and no same-cycle SOL action
existed, so the portfolio journal classified it `deployable_flat_entry`. Its
fixed boundary is approximately `00:45:21 EDT`. The initial `-10.40 bps`
marked estimate is provisional and is neither a loss nor a fill. The observer
has `execution_authority=none` and cannot alter the live strategy.

Confidence is high in the cutoff, source identity, `$75` capacity contract,
and causal portfolio classification. Confidence in edge is low. Fresh PF at
or below one, a failed `$75` capacity check, continued absence of shorts, one
dominant path, or deployable results that do not survive observed friction
weakens or falsifies the candidate.

## Current decision and falsifiers

1. Keep the armed execution profile unchanged while BTC and HYPE are open.
2. Keep `multi_asset_bidirectional_range_retired_candidate.toml` staged for a
   verified-flat restart; do not reactivate range onset from a pending or
   single favorable HYPE path.
3. Retain canonical HYPE breakout and BTC/HYPE forward collection. Do not add a
   generic trailing stop or turn component telemetry into an entry gate.
4. Keep both resolved HYPE one-path challengers report-only. Collect distinct
   flat-entry and short-side paths before comparing their deployable economics.
5. Resolve the predeclared SOL aligned-book path without changing its fixed
   contract or treating intrahorizon marks as completed outcomes.

Confidence is high for ledger arithmetic, protection state, recorded public
trades, and the stated frozen contracts. Confidence is medium for average live
friction because the sample is 23 fill legs. Confidence is low for durable
strategy edge because current-profile N is two and the favorable compatible
HYPE result contradicts the negative one-year deployed-shape replay.

This assessment is falsified or materially updated by a venue/account-history
disagreement, a current-profile/archive scope leak, an unprotected open
position, a fresh frozen candidate PF at or below one, a single observation
dominating aggregate return, short-side evidence contradicting the direction
contract, or a repeated live outcome that reverses the current provider-side
ranking.

## Exact-run trade-record contract — 2026-08-05 00:16 EDT

The active capital path is now keyed by exact backend `run_id`, independently
of the strategy profile fingerprint. This removes a latent defect where a
prior run using the same profile could be presented as part of the active run.
The persistent record has three explicit scopes:

| Scope | Selection rule | Live count | W/L | Net PnL |
|---|---|---:|---:|---:|
| Current run | exact `source_run_id` match | 2 | 2/0 | `+$0.282014` |
| Same-profile prior runs | profile match, run mismatch | 0 | 0/0 | `$0` |
| Complete archive | every reconciled lifecycle | 10 | 7/3 | `+$1.257135` |

All ten closed archive lifecycles reconcile to venue evidence. For each row,
close-fill gross PnL minus both entry and exit fees plus signed funding equals
the reported net PnL. The 23 venue fill legs are not 23 trades: they include
entry/exit legs for ten completed lifecycles, two currently open entries, and
one partial close. The cockpit therefore presents completed trades and fill
legs in separate instruments.

The current-run aggregate is backend-authored and validated against the exact
reflected rows before the TUI accepts it. The equity path refuses to substitute
same-profile history if current-run identity is absent or inconsistent. This
trades compatibility for honesty: current-run performance resets after a
backend restart, while profile history and the archive remain visible as
separate persistent evidence.

Confidence is high for the current arithmetic and scope contract because the
regression tests include a prior run with the same profile, a one-shot report
was generated from the live ledger, and the optimized TUI was visually checked
against that report. A profile-matching prior-run row entering `RUN`, any
aggregate/row mismatch, loss of an archived lifecycle, or a fill leg displayed
as a completed trade falsifies this assessment.
