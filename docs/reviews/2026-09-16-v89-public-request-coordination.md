# Public-request duplication and shared-budget validation

High confidence in this authenticated one-hour trace and reproducible arithmetic;
limited confidence in deployment benefit until collector integration is tested.
The observed opportunity is redundant public research traffic. These results do
not establish a live execution failure, a profitability effect or future savings.
Financial execution and all five active collectors remained unchanged.

## Evidence and findings

The declaration fixed September 16 19:30–20:30 UTC request starts, plus the
preceding minute solely for rolling accounting and simulation initialization.
Read-only index prefixes were retained at 20:32:14.490364 UTC. All referenced
file hashes, body hashes, indexed receipt clocks and public request scopes were
authenticated. The analysis contains 590 requests including eight warmup requests;
582 fall inside the hour. All 582 returned HTTP 200. Median receipt latency was
319 ms, p95 588 ms, maximum 1,146 ms. No observed response weight exceeded its
planned query bound. No price, PnL or sealed prospective outcome was evaluated.

Estimated request weight was 11,917–12,479 over the hour. The rolling-minute peak
was 1,220–1,256 at 20:00:16.203 UTC. Both floor and ceiling interpretations of
additional-item charges are reported because the published wording does not
explicitly state their rounding operation. The documentation specifies an
aggregate per-IP REST limit of 1,200 weight per minute, most Info requests at 20,
and additional charges per 60 candle or 20 funding-history items.
[Hyperliquid rate-limit documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

| Collector | Hour requests | Estimated weight, lower–upper |
| --- | ---: | ---: |
| Original seven-asset | 265 | 5,415–5,674 |
| Followup seven-asset | 265 | 5,415–5,674 |
| Original pair | 20 | 416–432 |
| Followup pair | 20 | 416–432 |
| Native-minute continuation | 12 | 255–267 |

Exact canonical payload grouping found 286 extra requests in 262 groups, with
identical body bytes inside every group. Some repeats are minutes apart; treating
all 286 as immediately removable would overstate the opportunity. The stricter
in-flight grouping admits a follower only if it starts before the earliest
leader's receipt, without chaining through later followers. It found 264 groups
and 264 extra requests, representing 5,650 upper-bound weight: 45.4% of requests
and 45.3% of estimated upper weight. All corresponding body bytes matched.
This is a trace opportunity, not a deployed deduplication result. The retained
receipts remain separate and preserve their own point-in-time provenance.

A separately retained 326-byte backend log segment, from approved launch through
20:30:30 UTC, contains no 429, rate-limit text, traceback or named read exception.
This small segment is not complete HTTP telemetry. Financial requests, other
clients on the IP, server accounting and earlier periods remain unmeasured.
Estimated load above the documented limit does not prove that a financial request
failed, and the trace must not be used to explain earlier protection latency.

## Fixed-workload simulations

All twelve variants conserve the same 590 request identities and payloads, never
dispatch earlier than observed release, preserve each collector's observed order
and allow only one request in flight per collector. Admission uses planned query
weight without consulting future response values. FIFO and fresh-first priority
may choose only among ready collector heads; their results are identical here.

| Shared budget/minute | Requests delayed in hour | Maximum added wait | Newly late fresh-query proxies |
| --- | ---: | ---: | ---: |
| 600, observed duration | 41 | 110.126 seconds | 8 |
| 900, observed duration | 25 | 52.532 seconds | 0 |
| 1,200, observed duration | 11 | 49.253 seconds | 0 |
| Each budget, ten-second duration | 462 | 179.310 seconds | 64 |

Timeliness uses the latest requested candle close plus 60 seconds as a query
deadline proxy across 529 fresh queries. It is not a per-observation replay.
The model fixes requests and release times; real deadline deferral, replanning,
recovery query construction and changed future values can alter that workload.
Ten-second stress is an assumption, not observed latency. No scheduler optimality
or universal failure of 600-weight scheduling is claimed. Zero new late proxies
at 900 in this hour does not qualify that setting for deployment.

## Validation and source identity

Candidate commit `4b60bfca85ce63f7737485cf49500704bac20678` is committed and pushed
on `research/v89-public-request-coordination-20260916`. All 46 tests pass both
in the isolated worktree and extracted archive, with network denied and live
data/configuration/source writes denied. Tests cover malformed scope, authority,
clocks and hashes; exact window boundaries; unknown response weight; non-chained
overlap; queue ordering; capacity; starvation and mutation detection.

The three audit/model modules cover 190/191 statements and 79/80 branches. The
remaining branch is a defensive impossible-progress check under validated model
inputs; it is not reported as exercised. Source files and functions satisfy the
500/50-line limits, and Ruff checks pass. The standard-library independent
verifier reauthenticates raw bytes, directly recomputes weights/rolling sums and
overlap groups, and checks every simulated request for conservation, causality,
collector order, serialization and rolling capacity. It makes no optimality claim.

The archive contains 3,662 files, each verified against committed bytes. Archive
SHA is `0f01d9c4677b7680a2f29cd55f67f36411aca2f38cb792707c50217ca1b6cd23`.
Running from the extracted archive reproduced the complete load analysis, all
twelve simulation objects and the independent verification object exactly.
Original failing controls and subsequent passes remain retained separately.

## Decision and next experiment

| Alternative | Evidence and trade-off | Decision |
| --- | --- | --- |
| Keep existing collectors | Preserves their declared evidence; redundancy remains | Retain during offline work |
| Apply a blanket 600-weight budget | Tested replay adds eight late query proxies | Defer deployment |
| Apply 900-weight budget | No new late proxy in this trace; other traffic unmeasured | Insufficient deployment evidence |
| Share identical in-flight public requests | 264 matched opportunities; requires new provenance/failure semantics | Highest-value next offline prototype |

Prototype exact-scope in-flight sharing with separate subscriber receipt identity,
without relabeling old receipts or changing active study manifests. Validate
deadline expiry, follower cancellation, leader failure, HTTP 429, crash recovery,
source revisions and durable attribution. Success requires exact subscriber
payload/receipt lineage, no early availability, no silent loss, preserved study
continuity and measured aggregate budget/timeliness improvement on a later fixed
trace. A failure or replay mismatch rejects the relevant prototype behavior.
One hour does not establish generality across volatility or market regimes.

No live change is proposed for installation by this report. A later approval
request must identify the concrete source, integration results, affected study
declarations, restart procedure and rollback; existing deployment approvals do
not imply approval for a new sharing service. Rollback of this offline candidate
means leaving the isolated branch unused; active processes require no rollback.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_public_request_coordination_20260916_v1/`.
The continuous goal remains active; the next experiment above is available now.
