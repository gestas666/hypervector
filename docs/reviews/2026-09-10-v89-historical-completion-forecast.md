# Historical completion forecast from observed work

At September 10 09:15:57 UTC, the original coordinator has 30/48 completed
receipts, four active workers and fourteen queued cases. Eighteen cases remain
in total: six full-prefix and twelve rolling-history cases. Both original
coordinator and reporting-handoff sessions were polled live in this review.

The 27 newly run cases with coordinator log clocks took 39.7–50.7 minutes.
The three adopted cases lack comparable coordinator log clocks and are excluded.
Durations use log creation to receipt modification; they are filesystem-clock
proxies for launch/completion, not instrumented CPU benchmarks.

Scheduling the remaining original case order across the same four workers,
subtracting each active worker's elapsed time, gives these scenarios:

| Per-group duration assumption | Remaining worker time | Completion, September 10 Eastern |
| --- | ---: | --- |
| Observed minimum | 3.10 hours | 08:22 |
| Observed median | 3.37 hours | 08:38 |
| Observed maximum | 3.99 hours | 09:15 |

These scenarios are not statistical bounds on future execution. High confidence
applies to captured counts and verified scheduling arithmetic; forecast confidence
is low-to-medium. Changed throughput, fewer workers, growing output, host contention
or slower final authentication would update the estimate. Each scenario includes
all eighteen remaining identities exactly once, with no worker overlap; independent
worker-load sums reproduce the reported completion horizon. All thirty receipt
hashes are authenticated.

Free space is 9,260,732,416 bytes. Completed five-artifact cases range from
184.71 to 187.22 MB. Applying the largest observed size to every remaining case
gives 3,369,931,182 further retained bytes and 5,890,801,234 projected free bytes,
above the unchanged 2 GiB coordinator reserve. This is an observed-size scenario,
not a bound on temporary writes or unrelated filesystem growth. It provides no
reason to stop or restart the active jobs or change their reservations.

Two retained report runs with explicit launch-record/completion clocks took
4.59 and 4.53 minutes. A direct 48-case extrapolation is 3.62–3.67 hours; the
planning allowance remains four to six hours because only two clock samples
are available and variants/final authentication can differ. Four existing case
report files imply approximately 51.12 MB for 48 reports at the largest observed
size, excluding final manifests and any temporary resources.

The revised planning target is **08:20–09:20 Eastern for worker completion**
and **12:30–16:00 Eastern for the complete review**, September 10. Final producer
authentication, reporter startup and final report inspection remain additional
uncertainties. This refines the prior broad 13:00–19:00 review estimate; it is
not a live-start estimate, a completion claim or a performance forecast.

The original case definitions, active processes, source and reporting handoff
remain unchanged. No economic result or prospective outcome was evaluated for
this operational forecast. Continue the existing jobs and revise this estimate
when new completion or resource evidence changes it.

Evidence: `data/logs/research/bidirectional_cohort/`
`v89_historical_completion_forecast_20260910_v1/forecast.json`,
`arithmetic_verification.json`, `report_planning_basis.json` and
`evidence_manifest.json`.
