# Portfolio-wide continuous-improvement digest

## Problem restatement

The live portfolio needs a bounded answer to what should be investigated next,
while preserving the separation between evidence collection and order
authority. Success requires all configured routes, long/short evidence,
after-cost outcomes, missed opportunities, evidence gaps, and experiment
priority to remain visible without silently retuning, promoting, gating, or
changing the running v25 strategy.

## Implemented tracking contract

The report-only monitor runs every 120 seconds as
`com.hypervector.portfolio-improvement`. It reads the existing bounded cohort
checkpoint and atomically publishes
`data/runtime/bidirectional_cohort/latest_improvement_digest.json`. Its contract
explicitly sets execution authority, automatic retuning, automatic promotion,
automatic strategy changes, and runtime strategy changes to false.

Malformed, execution-capable, or non-report-only input is rejected. A failed
refresh preserves the last valid artifact and emits an actionable technical
error. The digest never imports or constructs an execution client.

The first source-bound publication contains all 24 provider-symbol routes and
the bounded long and short research frontiers. Its source checkpoint reports:

| Metric | Current value |
|---|---:|
| Closed trades | 14 |
| Wins / losses | 7 / 7 |
| Net PnL | +$2.791652 |
| Profit factor | 2.143047 |
| Maximum drawdown | 0.408818% |
| Fees | $0.555521 |
| Funding | -$0.086737 |
| Runtime faults | 0 |

These are descriptive values from the current checkpoint, not a durable edge
claim. Fourteen closes remain sparse and combine multiple route identities.

## Ranked next experiments

The queue ranks research work rather than live orders:

1. SOL range-onset: collect independent live evidence from both directions.
   The favorable generic one-blocker path has four resolved all-long BBO
   estimates, +37.61 bps, PF 14.81, and +9.99 bps excluding its largest winner.
   It does not validate an exact successor. The identity-related frozen aligned
   fixed-60 provider already failed nine prospective all-long paths at
   -113.09 bps and PF 0.3472, so the generic path is a research lead only.
2. SPCX Swing/HA was initially queued for separate long and short mechanisms.
   Exact attribution subsequently exhausted four existing entry clocks by
   side: none survived development, validation, nominal/stress costs, and
   largest-winner removal. SPCX now requires a new causal mechanism identity
   and ranks below evidence-collection work rather than repeating the split.
3. ETH precompression pullback was initially queued for separate long and
   short mechanisms. Exact attribution subsequently showed that neither side
   and none of four side/breakout-relation arms survived both partitions and
   largest-winner removal. Retain the least contradicted 12-hour duration, but
   require a new causal mechanism identity rather than repeating the split.
4. GOLD Swing/HA was initially queued for separate long and short mechanisms.
   Exact attribution subsequently exhausted eight timing/side arms: GOLD long
   was negative in both partitions, short reversed from negative development
   to positive validation, next-bar confirmation did not repair the reversal,
   and fast-EMA pullback produced no trades. GOLD now requires a new causal
   mechanism identity and ranks below evidence-collection work.
5. BTC HT-Breakout: diagnose direction transfer and cost behavior before
   proposing a new mechanic identity.

No result above changes v25, activates v31, or creates a performance or trade
count gate.

## Evidence quality and failure modes

At the 17:08 EDT validation snapshot, the audit reports
`provider_metric_telemetry_missing`, 1,268 missing metric values, and 1,064
right-censored observations. These rolling counts can increase while v25
continues, and the digest republishes them rather than treating them as fixed.
The deficiencies are reported explicitly, so `audit_complete` is false. The
first completed v31 HIP-3 evaluations must demonstrate the staged
pressure-clock repair; the current v25 prefix cannot be retroactively repaired.

Confidence is high that the monitor is execution-incapable and that the output
is source-bound and atomically replaced. Confidence is medium that the queue
orders the highest-value experiments because route evidence is sparse and
mixed-profile. Confidence is low that the SOL generic path represents an
executable edge because its exact related provider was contradicted and no
short path resolved.

The tracking claim is falsified by a source hash mismatch, a missing configured
route, acceptance of an execution-capable checkpoint, loss of the last valid
artifact after a malformed refresh, or any runtime/order side effect. The
experiment ranking is updated by hash-verified report-only decision overlays
without restarting the checkpoint or live engine. An overlay may only revise
or stop research work; it cannot request `PROCEED`. The ranking should be
updated further by independent both-side outcomes, complete repaired provider
metrics, materially different after-cost evidence, or exact-mechanic results
that contradict the current queue.

## Validation evidence

- Twenty-eight focused digest, monitor, successor-triage, side-composition,
  opportunity-matrix, ETH attribution, and research-journal tests pass.
- The monitor rejects execution-capable inputs and preserves last-valid output
  on malformed input.
- Ruff passes for the digest, monitor, and focused tests.
- The complete non-network Python suite passes 4,371 tests with four intentional
  deselections and 27 existing dependency/deprecation warnings. The complete
  `hypervector-tui` Rust suite and doc tests pass.
- The launchd service has published multiple checkpoint generations, is running
  with one launch count, and has never exited.
- V25, its checkpoint service, and the v31 route tracker were not restarted or
  changed by this implementation.
