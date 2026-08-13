# Hypervelocity Entry-Filter Factorial Plan

**Goal:** Determine whether hard 5m BBWP range precedence, 1m recovery delay,
or their interaction causes the source-timing mismatch or changes the
stateful authentic Hyperliquid portfolio result.

**Evidence boundary:** The active faithful runtime remains canonical and is
not changed by this report. The prior hard-BBWP25/recovery-6 replay is a
research candidate. The creator set has 35 normalized entries; canonical 5m
structure matches 27, while the combined research entry direction matches 17.

## Frozen candidates

All candidates use the same faithful regime parameters, $10,000 initial
equity, 70% isolated allocation, 40x leverage, 8% gross margin target, maker
entry/target fees, taker liquidation fee, 300-second maker TTL and post-exit
cooldown, regime-reset re-entry, authentic mark/oracle, and official funding.

| Candidate | Hard 5m BBWP precedence | Recovery age 6 |
|---|---|---|
| `canonical_control` | no | no |
| `hard_bbwp_only` | yes | no |
| `recovery6_only` | no | yes |
| `hard_bbwp_recovery6` | yes | yes |

No threshold, stop, orderbook gate, confidence gate, ML action, 15m veto, or
exit change may be added after inspecting results.

## Success evidence

- Correctness: all four named decision streams consume one validated event
  tape; only the two declared transformations differ; completed-bar
  availability remains causal.
- Source fidelity: report exact direction matches, opposite directions,
  no-candidate reasons, false RANGE rows, and fill-time proximity for all 35
  creator entries.
- Economics: report submissions, fills, targets, liquidations, partial
  liquidations, fees, funding, final equity, maximum drawdown, lifecycle path
  substitutions, and three chronological 30-day slices.
- Promotion is not automatic. A candidate must improve source fidelity,
  full-window final equity, and maximum drawdown without relying on one slice.
  Losing trials remain valid results.

## Task 1: Candidate-specific shared-tape replay

- Add a tested stream adapter accepting a name-matched mapping of decisions and
  configs.
- Reject missing/extra candidate identities and decision-index contract
  violations.
- Keep the existing same-decision config grid behavior unchanged.

## Task 2: Immutable factorial report

- Build the exact four decision streams from the strict 90-day bars.
- Add source-alignment and reason attribution without fabricating missing
  creator outcomes.
- Replay all four states through the same 2,160 verified bundles and authentic
  price/funding context.
- Hash inputs and decision identities; retain full lifecycle reports.

## Task 3: Validation and decision

- Compare economics, 30-day consistency, source fidelity, and path
  substitutions.
- Keep runtime, TUI, target, and observe-only ML unchanged.
- Run full Python/Rust verification and record the immutable artifact.

## Risks and falsifiers

- Better exact-minute source recall may merely increase overtrading and
  liquidation; that would reject relaxation despite better alignment.
- A candidate can win through path dependence rather than stable outcome
  improvement; poor 30-day consistency would lower confidence.
- The screenshots are selected and incomplete. New complete creator rows may
  change which filter appears source-compatible.
- Public trade-through and BBO liquidation cannot reconstruct private queue
  rank or hidden depth; a survivor still requires fresh shadow validation.

## Measured result and decision

The complete replay processed 2,160 checksum-verified hourly bundles with
127,814 authentic mark/oracle observations and all 2,160 official funding
rows. All candidates used the exact same execution configuration.

| Candidate | Submissions | Fills | Targets | Liquidations | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Canonical control | 345 | 277 | 241 | 36 | $27.04 | -99.85% |
| Hard BBWP only | 519 | 419 | 370 | 49 | $21.66 | -99.94% |
| Recovery-6 only | 345 | 290 | 249 | 41 | $3.26 | -99.98% |
| Hard BBWP + recovery-6 | 522 | 408 | 369 | 39 | $2,466.13 | -97.83% |

Hard BBWP and recovery-6 each worsen final equity and drawdown when applied
alone. Their interaction is nonlinear and materially less bad, but still
loses 75.3%, reaches -97.8% drawdown, and loses money in its first two 30-day
slices. Only its final slice grows. It shares only 107 resolved signal
identities with canonical, so the apparent improvement is a different serial
portfolio path rather than a narrow removal of bad entries.

The source evidence rejects promotion more directly. For all 35 normalized
entries, canonical structure/executable direction matches are 27/24. They are
23/20 for hard-only, 27/20 for recovery-only, and 23/17 for the combination.
For the 23 outcome-backed entries, the same structure/execution pairs are
20/17, 18/15, 20/14, and 18/13. The previously quoted 20/23 canonical figure
is structural alignment; executable eligibility is 17/23 because three
same-direction `BREAKOUT` rows await the narrow 1m confirmation.

No factor or interaction satisfies the predeclared promotion criteria. Both
filters remain report-only and the active canonical runtime is unchanged.
Confidence is high for the tested replay comparison and medium for external
generalization because the creator evidence is selected and incomplete. A
later venue-matched window that improves source eligibility, final equity,
drawdown, and every chronological slice would falsify this rejection.

Artifact:
`data/logs/research/hypervelocity_entry_filter_factorial_20260728.json`,
SHA-256
`1c56f8cf8b53aef2b253b6ebe8f675a883c6fb87e55471623cc2fad0071b01c3`.
