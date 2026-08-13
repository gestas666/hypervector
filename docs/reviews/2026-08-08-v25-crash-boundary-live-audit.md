# V25 Crash-Boundary Live Audit

## Problem Restatement

The v25 live backend stopped after its last cohort heartbeat at
`2026-08-08T08:34:55.408419Z`. The required outputs are an immutable account of
the evidence through that boundary, a distinction between technical failure and
strategy outcome, and a restart contract that cannot duplicate or abandon venue
positions.

Success requires all of the following:

- preserve the exact v25 run, profile, route, fill, fee, funding, and open-path evidence;
- report an absent backend as stale instead of allowing a fresh TUI sidecar to imply health;
- tolerate bounded transient read failures without treating order state as known;
- persist catchable terminal faults without exposing exception detail or credentials;
- prove that the three venue positions can be adopted with their existing reduce-only stops;
- avoid a strategy or portfolio transition unsupported by newly resolved evidence.

## Authoritative Evidence

The report-only audit is
[`v25_live_prefix_crash_boundary_20260808T092222Z.json`](../../data/logs/research/bidirectional_cohort/v25_live_prefix_crash_boundary_20260808T092222Z.json).

- SHA-256: `95ae2ec8e40a581dfb6137aa3ca6a508a5c6c92e4b73d2d540107b49c1b56e1b`
- Size: `6,499,541` bytes
- Run: `bidirectional-live-1786137154835`
- Profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`
- Profile fingerprint: `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`
- Evidence interval: `2026-08-07T21:14:31.740568Z` through
  `2026-08-08T08:34:55.408419Z`
- Authority: report-only; no execution authority and no runtime strategy change
- Coverage: complete, with no recorded technical data gaps

The v29 research-journal chain remains intact: five revisions, 22 matching
evidence objects, zero changed, and zero missing. V29 remains an inactive
candidate and is not altered by this review.

## Findings

### Technical boundary

The audit contains no graceful stop reason and no persisted runtime fault. That
does not establish that the process was healthy after its last heartbeat; it
means the termination bypassed application-level fault persistence. A separate
launcher experiment reproduced a child process disappearing when its invoking
execution session closed.

Assessment: **medium-high confidence** that the incident belongs to the external
process/session lifecycle failure class rather than an unhandled Hyperliquid 429.
This is not proven because no OS signal or supervisor record identifies the exact
termination cause.

This assessment would be falsified or updated by a durable future runtime-fault
event, an OS/supervisor termination record naming another cause, or a future
process loss while running under an independently persistent supervisor.

Implemented technical controls:

- a cohort heartbeat older than 60 seconds projects
  `backend_heartbeat_stale` and cannot be hidden by a fresh checkpoint sidecar;
- a catchable terminal exception emits a secret-safe `runtime_fault` record;
- `SIGINT`, `SIGTERM`, and `SIGHUP` request bounded shutdown between protected operations;
- retry-exhausted HTTP 429, timeout, connection, request, and HTTP 5xx read
  failures emit degraded telemetry and skip the cycle without attempting orders;
- non-transient errors continue to fail closed.

These controls detect or tolerate the observed failure classes. They do not make
an ordinary shell child process durable; production liveness still requires an
independent process owner or service supervisor.

### Realized strategy evidence

The run produced two closed trades:

| Route | Side | Result after costs |
|---|---:|---:|
| SOL Hulk Expansion | Long | `+$0.681124` |
| SPCX Swing/HA | Long | `-$0.656872` |
| **Total** | | **`+$0.024252`** |

Observed execution and resolved-lifecycle accounting:

- closed trades: 2 (`1W / 1L`)
- profit factor: `1.0369`
- closed-lifecycle fees: `$0.055802`
- closed-lifecycle funding: `-$0.003146`
- measured fills, including entries for open lifecycles: 8
- acknowledgement latency: median `936.5 ms`, maximum `1,333 ms`
- slippage: median `0.1828 bps`, range `-5.9840` to `+6.1204 bps`
- portfolio maximum realized-equity drawdown: `0.1696%`

Assessment: **high confidence** in the arithmetic and attribution because it is
reconciled from the immutable run ledger. **Low confidence** in any claim of
repeatable strategy edge because two resolved trades are not an adequate sample.
This edge assessment would materially update after a prospectively resolved,
after-cost sample across both sides and multiple market states.

### Open venue lifecycles at the boundary

The audit and a fresh read-only Hyperliquid reconciliation at
`2026-08-08T09:33:32.874635Z` agreed on three open, stop-protected, isolated 5x
long positions:

| Asset | Size | Entry | Venue U/PnL | Liquidation | Reduce-only stop OID | Stop trigger |
|---|---:|---:|---:|---:|---:|---:|
| ETH | `0.013` | `1917.9` | `+$0.0143` | `1566.5053` | `512630700867` | `1906.4` |
| SOL | `1.0` | `74.457` | `+$0.4240` | `61.1317` | `512630736897` | `73.861` |
| `xyz:GOLD` | `0.0172` | `4354.3` | `-$0.1290` | `3557.9266` | `512544517709` | `4319.5` |

Their provisional marked paths are excluded from realized strategy performance.
Exact recovery against fresh venue truth returned `restore_open` for all three
when each asset's own profile fingerprint was used. BTC, HYPE, SP500, SPCX,
SNDK, and BRENTOIL were flat and order-free at that reconciliation.

Assessment: **high confidence at the reconciliation timestamp**. Venue state can
change afterward, so this is not a current-position guarantee. A restart must
repeat the reconciliation and stop-coverage checks before routing new entries.

### Routing and missed opportunities

The run completed 1,710 cycles, evaluated 6,808 provider-symbol decisions,
published eight strategy intents, executed five actions, and withheld three
intents for explicit ownership/priority reasons. All five actions were long;
there is no resolved short-side execution evidence in this run.

The strongest one-blocker challenger was SOL Range Onset awaiting an hourly SMA
cross. At 60 minutes it had only seven independent resolved paths and a mean
`+6.14 bps` after the fixed `13 bps` round-trip friction estimate. Its gross mean
did not clear the predeclared `26 bps` robustness screen. This is a research lead,
not support for changing live routing.

Assessment: **medium confidence** that no immediate blocker relaxation is
justified; the evidence is complete but sparse and multiple comparisons can
produce chance-positive slices. This would update if a predeclared forward
challenger produces at least the required cost margin with independently spaced
paths and balanced route-side coverage.

## Decision and Trade-offs

| Option | Evidence fit | Operational risk | Decision |
|---|---|---|---|
| Change v25 thresholds now | Poor: two closes and sparse challengers | High attribution ambiguity | Reject for this boundary |
| Promote v29 now | Inactive candidate remains concentrated and partly contradictory | Changes strategy while three v25 lifecycles are open | Reject for this boundary |
| Resume unchanged v25 with exact adoption | Preserves causal continuity | Requires current venue reconciliation and durable process ownership | Prepared; requires explicit live authorization |
| Leave backend stopped | Preserves venue stops but loses timed exits and new telemetry | Reduced lifecycle management | Temporary fail-closed state only |

The strategy decision is therefore **no change from the crash-boundary evidence**.
That is not a claim that v25 is profitable. It preserves the only causal forward
sample while preventing a technical incident from being misread as strategy
evidence.

## Recovery Acceptance Contract

An authorized live recovery is acceptable only if startup proves all of the
following before new routing:

1. the profile ID and fingerprint exactly match v25;
2. current venue positions and open orders are fetched successfully;
3. ETH, SOL, and GOLD are either adopted with the exact current full-size
   reduce-only stops or any changed venue state is explicitly reconciled;
4. no duplicate entry or protective order is submitted;
5. a fresh cohort heartbeat reaches the checkpoint and TUI;
6. the TUI reports backend health from the execution heartbeat, not sidecar age;
7. the backend is owned by a process boundary that survives the launching shell;
8. any mismatch aborts entry routing and leaves existing venue protection intact.

No command in this review arms live execution. A fresh explicit authorization is
required by the live safety contract.

## Remaining Unknowns

- The exact OS-level cause of the prior process termination is not verified.
- The three open lifecycles may have changed after the recorded venue read.
- Two closes do not establish edge, trade-frequency stability, or side symmetry.
- Completed-bar and ledger evidence cannot reproduce private queue position,
  future funding, stop gaps, or latency during a venue outage.
- A durable process owner has not yet been validated end-to-end with this backend.
