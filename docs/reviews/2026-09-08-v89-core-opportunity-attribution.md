# Core inactivity reflects recorded setup scarcity in the frozen V89 prefix

No eligible core entry was lost between its recorded provider evaluation and
routing in this prefix: all four providers emitted zero eligible fresh entries,
zero core strategy intents, zero routing actions and zero withholding records.
High confidence in this bounded finding. It does not establish profitability or
prove every upstream classifier input independently correct.

The cutoff is **2026-09-08 10:40:18.410578 UTC**, run
`bidirectional-live-1788809099824`, profile fingerprint
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
The checkpoint and all five ledger prefixes are frozen and checksum-verified.

| Asset | Fresh evaluations | Eligible entries | Observed explanation |
|---|---:|---:|---|
| BTC | 15 hourly | 0 | Below EMA55 in all 15; another prerequisite also failed each time |
| ETH | 907 minute publications | 0 | No completed hourly SMA10/30 crossover |
| SOL | 907 minute publications | 0 | No completed hourly SMA10/30 crossover |
| HYPE | 907 minute publications | 0 | Two fresh onsets; both failed prior compression and directional pullback |

BTC has one additional startup-history row for the 19:00 UTC completed decision.
Its `backend_non_action_reason` explicitly marks it as a pre-activation readiness
seed. The checkpoint's 16-row readiness count includes that row; it is not a new
live entry opportunity. All subsequent BTC decisions are one hour apart. The
other providers have complete one-minute publication cadence. Minute publication
counts do not imply that an hourly crossover can occur every minute.

## Independent arithmetic and routing evidence

For ETH and SOL, 82 venue-native hourly candles per asset supply the finite
history needed to calculate SMA10, SMA30 and the prior/current crossing relation
independently with Decimal arithmetic. All 907 publications per asset match
within the fixed absolute tolerance of 1e-9; no raw long or short crossover is
present. The audit permits a crossover only at a completed-hour boundary. It also
checks that recorded regime admission follows the recorded 5m state, and that
context admission follows the recorded two-timeframe bias rule. Those regime and
bias primitives are not independently reconstructed here.

BTC's native prior 20-hour low, current low and close match exactly. Its volume
ratio has maximum absolute residual 3e-16. Fifteen EMA55 recurrence updates match
from the first recorded EMA seed, with maximum residual approximately 1.61e-11.
The initial EMA value remains unverified independently. The failed prerequisites
among fresh decisions are: EMA 15, sweep 12, volume 10, reclaim 2. Every row fails
at least two prerequisites, so the EMA condition alone cannot explain inactivity.

The HYPE onsets occurred at **02:55 and 06:35 UTC on September 8**. Both were
recorded as short and aligned with their recorded breakout direction. At 02:55,
5m BBWP was 83.33 against a maximum of 50, prior 1m BBWP minimum was 95.42 against
40, and directional body was +4.74 bps against a maximum of zero. At 06:35, 5m
BBWP passed at 33.33, while prior BBWP 57.50 and body +9.42 bps failed. The current
HYPE entry scope is long-only; a fully qualifying short would have opposite-side
exit authority, not permission to open a short. No position was open in HYPE.

This checks HYPE's fixed inequalities, readiness counts, blocker lists, side
agreement and consecutive recorded state transitions. Its compression/price
inputs remain backend observations. The first prior-state observation is taken
from the recorded initial row; later prior states match the preceding publication.

Each core asset has 3,624 position observations and 3,624 venue reconciliations.
All observed positions are flat, all order lists are empty, and no reconciliation
fill identity is new relative to the first observation. Historical fill IDs in
reconciliation records are not counted as new trades. There are no core order
submission or fill events in the frozen asset prefixes.

## Validation and scope

Fifteen configuration/provider/routing source files match both the archived
pre-start versions and the original/research working trees. The new diagnostic
source is revision `01da656`; it is isolated from the live source tree.

All 53 offline tests pass in both the working tree and a fresh extracted archive.
Predicate arithmetic covers 92/92 statements and 48/48 branches. Tests plus the
real replay cover 259/265 statements and 116/122 branches across the two analysis
scripts. Coverage is not a claim that unexercised execution paths are qualified.
The 5,021-member archive is hash-verified and produces an identical report.
Ruff, formatting, file/function limits, annotations and public docstrings pass.

Evidence directories under the primary repository's
`data/logs/research/bidirectional_cohort/` are:

- `v89_core_opportunity_inputs_20260908_v1`
- `v89_core_hourly_inputs_20260908_v1`
- `v89_core_opportunity_audit_20260908_v1`

No live configuration, deployment, strategy, risk setting, process lifecycle or
order was changed. This prefix contains no eligible core entry that could
exercise the separately documented entry-deadline issue; this result does not
qualify or supersede that pending engineering proposal.

## Disposition and next investigation

Retain this as descriptive evidence of configured setup scarcity. No restart,
gate removal, direction change or profitability claim follows from these counts.
The earlier V52 diagnosis and its adverse HYPE onset-removal sensitivity were
reviewed; that rejected experiment was not reopened.

The highest-value next investigation is independent HYPE compression-input
verification at the two frozen onsets: reconstruct 5m BBWP, the preceding
15-minute minimum of 1m BBWP, and directional body from native minute candles
using the existing fixed calculation definitions. This is a finite-window source
check, with no threshold search or trade-outcome comparison. It addresses the
remaining input limitation before another entry-rule proposal.

A native arithmetic mismatch, a missing/duplicate evaluation, an eligible entry
without disposition, or an unbound core fill would update the conclusion.
Retrospective candle differences would require version-aware investigation;
they would not by themselves identify which original input was wrong.
