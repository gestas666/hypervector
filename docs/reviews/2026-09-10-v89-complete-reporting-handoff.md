# Complete historical reporting handoff

At September 10, 2026 05:23:28 UTC the original replay coordinator remains
active as PID 72423, with 8/48 completed cases and four workers. The new
reporting observer is PID 79587, session 44667. Its exclusive ownership lock
was verified held. Available disk is 14.95 GB. No local live backend, checkpoint
writer or TUI matched the process inventory. These are observed local process
facts, not a fresh venue account reconciliation.

The observer waits for the exact original coordinator to stop and publish its
complete 48-case report. It then invokes the unchanged qualified reporter
34004579e2cb21d13c55e01c47fa6f69e70d76ff against replay engine
69dd84a990836c30cd56b1effa524b0e20f88acd. Missing or partial output, changed
producer identity, source changes and reporter failure stop the handoff
explicitly. The reporting child inherits the ownership descriptor. Completion
requires successful reporter exit plus exact ordered case and artifact checks.

The new helper is frozen in analysis commit
a79e125908e09f1e314cab118cdda1050f6a66b2. All 25 focused tests pass in the
worktree and retained source, with 91/97 statements covered (94%). Tests cover
process identity and PID reuse, incomplete scope, authority changes, immutable
artifacts, child failure and cleanup, lock inheritance, and full output identity.
The real preflight authenticates 1,951 retained references, including all 1,933
reporter implementation files. High confidence applies to tested orchestration
and the observed waiting state; actual full-matrix publication remains pending.

All handoff evidence is under
`data/logs/research/bidirectional_cohort/v89_complete_account_reporting_handoff_20260910_v1/`:
`source.json`, `launch.json`, `retained_tests.log`, `preflight.log`,
`observer_started.json`, and `waiting_acceptance.json`. `observer.log` grows;
its acceptance hash records only the initial snapshot. Preserve the active
operator and retained source. The future full analysis output is
`v89_complete_historical_account_analysis_20260910_v1/`.

Replay completion is estimated around 09:00–13:00 Eastern on September 10,
with medium confidence from the first parallel cases. Larger variants or
resource contention can extend this. Final reporting and reproduction are
additional; this is not a go-live estimate. The simplest alternative was manual
reporter launch after replay; the observer removes that handoff delay while
retaining the existing calculations and validation. No replay engine, live
strategy, configuration, execution process, or TUI installation changed. Both
prospective seals remain active. No automatic promotion is authorized or added.
