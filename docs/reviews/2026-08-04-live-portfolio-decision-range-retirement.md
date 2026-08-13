# Live portfolio decision: retire range-onset at the next flat restart

**Decision time:** 2026-08-04 20:51 EDT
**Execution authority:** none; this review did not submit, cancel, resize, or close an order
**Runtime observed:** `bidirectional-live-1785826133777` / `multi_asset_bidirectional_canary_v2`
**Candidate:** `configs/multi_asset_bidirectional_range_retired_candidate.toml`

## Decision

Keep the currently armed backend unchanged while BTC and HYPE remain open and
venue-protected. At the next verified-flat restart, use the range-retired
candidate. The candidate changes only the range-onset provider's execution
scope from BTC/ETH/SOL/HYPE to none. It retains range-onset telemetry for
research and preserves every non-range provider, risk policy, asset, side, and
portfolio limit from the active profile.

Do not add the HYPE target-20 relaxed-entry provider. Do not replace the
canonical HYPE breakout requirement with the fixed-60-minute one-blocker
challenger. Do not turn regime-opposition telemetry into an early live exit on
the current evidence.

## Decision-time evidence

The rolling checkpoint generated at 2026-08-05 00:49 UTC reported a
`running_consistent` lifecycle, zero faults, complete technical coverage, and
two open protected lifecycles. BTC retained target `509798120490` and stop
`509798094894`; HYPE retained stop `510231986579`.

Compatible-profile resolved execution evidence was:

| Provider / symbol | Closed | W/L | Net USD | PF | Interpretation |
|---|---:|---:|---:|---:|---|
| HYPE canonical breakout / HYPE | 5 | 4/1 | +1.234701 | 6.5141 | Favorable but small live sample |
| Source-follow / BTC | 3 | 2/1 | +0.063001 | 1.5075 | Mixed and small |
| Hulk / BTC | 1 | 1/0 | +0.133813 | unavailable | Single outcome only |
| Range-onset / ETH | 1 | 0/1 | -0.174380 | 0.0 | Adverse exact live mapping |

The favorable canonical HYPE sample does not erase contradictory historical
evidence. Its deployed-shape development and opened-holdout replays remained
below PF 1.0. The live result is therefore descriptive rather than an edge or
profit forecast.

The current live journal also resolved the missed-entry challengers:

| Challenger | Forward sample | Result | Decision |
|---|---:|---:|---|
| HYPE `5m_not_breakout`, fixed 60m | 4 longs | 2W/2L, PF 0.6676, -28.1350 bps | Falsified |
| HYPE `5m_not_breakout`, target 20 bps then 60m | 3 longs | 2W/1L, PF 0.6738, -15.5073 bps | Falsified |
| BTC range one-blocker, fixed 60m | 1 long | 0W/1L, -39.1212 bps | Adverse N1; continue observe-only |

These are simulated, BBO-constrained, fee-and-funding-adjusted forward
opportunities; they are not venue fills or portfolio PnL. Their value is in
falsifying looser entry hypotheses. They support retaining the real HYPE
breakout requirement rather than claiming the canonical strategy failed.

## Exit analysis

Five closed canonical HYPE lifecycles had complete opposition episodes. The
two lifecycles that reached 1/3/5 consecutive opposed decisions both ultimately
won, totaling +0.329088 USD. Therefore, persistent regime opposition is not yet
supported as an automatic early-exit rule. The currently open HYPE long may be
opposed, but that fact alone does not justify an unplanned close.

One resolved HYPE soft-deadline extension finished 0.151589 USD worse than the
estimated soft-boundary reference. This is a useful exit-capture hypothesis but
only one observation, and the soft-boundary price is an estimate rather than a
submitted fill.

## Validation and operational state

The candidate-versus-active diff and configuration-generation tests passed.
A report-only one-shot checkpoint using the candidate reported:

- `matches_runtime=false`
- `restart_state=wait_for_flat_and_no_orders`
- blocking assets BTC and HYPE
- zero backend faults and complete technical coverage

The launchd checkpoint publisher now uses the candidate config only for
read-only generation telemetry. The armed backend still runs the active V2
profile. The TUI therefore exposes the pending restart truth without hot
mutation or duplicate execution.

## Confidence and falsifiers

**High confidence** that the candidate removes only range-onset execution
authority; this is proven by the structural config comparison and loader tests.
Any non-range provider difference or a range-onset route after the candidate is
activated would falsify that claim.

**High confidence** that current fills and lifecycle arithmetic reconcile; all
ten closed lifecycles reconcile entry, exit, holding time, fees, funding, and
net PnL. A venue fill missing from the ledger or a lifecycle net mismatch would
falsify that claim.

**Low confidence** that any current provider has durable positive expectancy.
The samples are small and canonical HYPE has contradictory historical evidence.
More resolved, venue-filled, forward lifecycles with after-cost PF above one,
both-side coverage, and no dominant single winner would increase confidence.
Fresh PF at or below one, concentration in one outcome, or repeated entry-state
contradiction would reduce it.
