# V88 live startup and read-only monitoring

The operator's retry on corrected source `260c8904e4da324b8125253846626af3e038fc15`
started V88 run `bidirectional-live-1788707880582`. Its first runtime record is
`2026-09-06T15:26:28.819216+00:00`; the fresh checkpoint reports
`running_consistent`. This supersedes the stopped-state handoff and the earlier
[router refusal](2026-09-06-v88-runtime-router-correction.md).

The runtime profile fingerprint is
`06e90a0c59b4b767fd14a61f3927553fc00b3017405193170101531204761d5f`, and the run
fingerprint is `4f28c495b7c7c08dc9ffa174f31867430c8db405c9697d700028b82cd4f0b8fb`.
BTC long, ETH long, SOL short, and HYPE long are the four executable routes.
Position capacity is four, one per asset. The approved strategy TOML, sizing,
leverage, entry-age limits, and exit contracts are unchanged.

The live run's verified backup is
`data/backups/bidirectional_cohort/prestart_20260906T151800.582287Z_06e90a0c59b4`.
Its manifest SHA-256 is
`47ee76a1af9ccb455dbf7618a10ac8f4c4248b3024fdfcb18889acde6cec623e`; its 1,860-file
implementation identity is
`f98a36e0b232a674839ae5ac4f8c92f835b820c7ed57848fc931d55c004a7a8f`.
The agent inspected the operator-started backend and started only read-only
collectors and display checks. It did not activate or restart trading.

## Completed acceptance

The immutable startup report
`data/logs/research/bidirectional_cohort/overhaul_v88_live_startup_acceptance_20260906_v1.json`
passed 12 technical checks: report-only evidence authority, checkpoint/heartbeat
freshness, current configuration, provider coverage, current position/protection
state, execution-contract shape, exact direction scopes, canonical regime
telemetry, identity/capacity, approved sizing, runtime backup identity, and the
observed backend process. Its source snapshot contains 30 polls and zero fills.
A later checkpoint at `2026-09-06T15:38:34.243871+00:00` contains 48 polls, all four
assets flat, no runtime faults, and a 13.23-second heartbeat age.

Actual standalone read-only terminal sessions captured all nine tabs and four
strategy inspectors at 120x36, 180x50, and 190x52: 21 captures per size, with each
session exiting successfully. Additional checks exercised all tabs at the 100x28
usability floor and verified the explicit resize notice at 99x27. Evidence is in
`overhaul_v88_live_terminal_acceptance_20260906_v2.json` and
`overhaul_v88_live_terminal_floor_acceptance_20260906_v1.json` under the same
artifact directory. Portfolio, setups, chart, depth, trades, journal, operations,
regime, configuration, and the four exact provider/risk inspectors were inspected.

The capture process had no command inbox and submitted no operator requests.
Its Operations panel therefore correctly showed the request channel unavailable;
this does not describe the operator's separately owned supervised TUI. Text-cell
captures do not establish color rendering or live order behavior. The initial
capture helper lacked its optional terminal parser and then waited on the wrong
initial tab; temporary display-only dependencies and an explicit Setup tab fixed
the helper. Production dependencies and runtime source were unchanged.

Historical and auxiliary research panels remain separate from the four current
execution scopes. BTC's initial hourly readiness seed is explicitly labeled as
pre-activation evidence; it is not a submitted historical entry. The live screens
show zero current-run fills and distinguish mixed historical results from V88.

## Active research and ownership

Four immutable preregistrations freeze the actual run, provider, executable side,
source hashes, cumulative evaluation counters, and prospective cutoff
`2026-09-06T15:27:39.837256+00:00`:

- [BTC long](../research-journal/v88-btc-exact-execution-lifecycle-20260906-v1.json)
- [ETH long](../research-journal/v88-eth-exact-execution-lifecycle-20260906-v1.json)
- [SOL short](../research-journal/v88-sol-exact-execution-lifecycle-20260906-v1.json)
- [HYPE long](../research-journal/v88-hype-exact-execution-lifecycle-20260906-v1.json)

All four collectors publish every 120 seconds. The live improvement configuration
is `configs/research/cohort_improvement_decision_overrides_v88_live_20260906.json`.
It binds the collectors to the digest while preserving the approved research
routes. The now-implemented proposal leaves the pending proposal queue; its frozen
proposal, approval, and earlier monitor variants remain preserved.

The digest is `data/runtime/bidirectional_cohort/latest_v88_improvement_digest.json`;
material changes append to `data/live/research/v88_continuous_improvement.jsonl`.
The loop has published multiple successful reports with no technical evidence gaps,
four queued experiments, and HYPE as the highest-priority investigation. Neither
the digest nor its collectors can place orders, resize, retune, or promote a route.

Observed process ownership at setup:

| Process | PID | Owner |
|---|---:|---|
| Live supervisor | 93287 | Operator |
| Live backend | 93376 | Operator supervisor |
| Checkpoint writer | 94028 | Operator supervisor |
| Foreground TUI | 94029 | Operator supervisor |
| BTC lifecycle collector | 94213 | Agent |
| ETH lifecycle collector | 94214 | Agent |
| SOL lifecycle collector | 94215 | Agent |
| HYPE lifecycle collector | 94221 | Agent |
| Improvement monitor | 94326 | Agent |

PIDs are historical identity evidence and must be revalidated before any process
action. Quitting the operator's supervised TUI stops its owned backend. Stop the
separate read-only collectors when that run ends; stale retained artifacts remain
historical. A collector exits after its diagnostic minimum is complete. Review its
immutable result and update the hypothesis and monitor configuration at that point;
do not represent a terminal collector as fresh ongoing observation.

## Evidence still required

High confidence in the timestamped startup and monitoring checks. A changed
profile/source identity, stale heartbeat, reconciliation failure, undeclared
direction, or missing protection on actual exposure would update that assessment.
The full offline suite for the deployed correction passed 8,001 tests; those tests
and current flat-state checks do not establish future profitability.

No current-run entry or completed lifecycle existed in the inspected snapshots.
The first future attributable decision, native entry, protective acknowledgement,
hold/recipe action, exit, fees, funding, and slippage remain to be reconciled for
each route. HYPE's source-to-execution fidelity and winner concentration remain the
highest-value investigation. One resolved lifecycle tests plumbing, not economic
repeatability; several losses alone do not establish a broken strategy.

The live-start requirement is now observed. The broader goal remains active for
the prospective execution evidence and continuing research; no further launch or
approval is currently pending.
