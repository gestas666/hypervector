# Durable public request sharing: offline qualification

High confidence in the tested broker contracts and retained replay calculations.
Production savings, delivery latency and strategy benefit remain unverified.
This work qualifies an isolated research kernel; it does not install a sharing
service or change live trading, collector processes or sealed study declarations.

## Implemented behavior

The SQLite broker grants one transport for eligible concurrent requests with an
exact canonical public Info payload. Every subscriber supplies its own request
ID, study ID, declaration hash, deadline and earliest permitted admission time.
The default rejects a transport admitted before that subscriber's request time.
Earlier sharing requires explicit consent. Completed responses are not cached.

Transport admission, actual supplied transport start/receipt, publication and
subscriber delivery remain distinct clocks. Each subscriber receives a separate
immutable receipt linked to the transport bytes and its sealed registration.
Delivery cannot precede publication. A follower discovered to have joined after
transport receipt gets an explicit missed-transport result. Cancellation affects
only that subscriber; a cancelled leader does not erase its followers' results.

Deadline expiry, lost leaders and lease expiry remain explicit. An expired
publisher cannot resurrect a transport. Exact subscription retries do not grant
another dispatch. HTTP 429 is retained and defers subsequent admission for the
declared five-minute cooldown. Publication is atomic: an injected SQL failure
rolls back transport and subscriber updates together. The kernel has no HTTP
client, sockets, automatic retry or financial execution authority.

## Development evidence and the failure-driven scope change

The original one-hour development trace contains 582 window requests, plus eight
warmup requests. Strict timing permits five shares at identical recorded
milliseconds. Explicit one-second earlier-admission consent permits 264 shares,
with no changed bodies or response outcomes. Modeled known peak request weight
falls from 1,256 to 846; three collector requests are delayed to preserve their
serial order. Maximum subscriber delay against the original receipt is 300 ms;
maximum advance is 517 ms. Neither number measures production broker latency.

The first later window was fixed before inspection for 21:15–21:35 UTC and
captured at 21:36:47.497427. It contains 208 requests, plus eight warmup requests:
207 HTTP 200 and one transport failure. The native-minute collector's SPCX
request at 21:31:36.851 UTC ended after 105 ms with ConnectionError / remote
disconnect and no HTTP response. Its raw hash is
`5099eae9da7d7bddf81811ba239ef90da460a00b0132f56cebf8e181d570cdbd`.
Subsequent collector health is fresh with no current error. This establishes a
public request failure, not a financial order failure or evidence of rate-limit
causation. Other IP traffic and server accounting remain unmeasured.

At 21:52:42.986337 UTC, all seven minutes requested by that failed query are
present. Their earliest indexed receipts were independently matched to
authenticated successful HTTP bodies: one minute was captured before the failed
attempt and six afterward. There is no remaining gap in that query range. The
later receipt times remain intact; recovery does not create earlier availability.

The initial success-only replay rejected that complete trace. Its failed attempt
is retained. The driver was extended to retain explicit transport errors, their
unknown response weight and status/error/body equivalence. That window therefore
became development evidence for the expanded failure handling. No timing-consent,
lease or scheduling parameter was retuned in response to its results.

| Trace and policy | Window requests | Shared requests | Known modeled peak weight | Changed outcomes | Newly late query proxies |
| --- | ---: | ---: | ---: | ---: | ---: |
| 19:30–20:30, strict | 582 | 5 | 1,256 | 0 | 0 |
| 19:30–20:30, one-second consent | 582 | 264 | 846 | 0 | 0 |
| 21:15–21:35, strict | 208 | 2 | 516 | 0 | 0 |
| 21:15–21:35, one-second consent | 208 | 93 | 302 | 0 | 0 |
| Fresh 21:45–21:55, strict | 105 | 2 | 474 | 0 | 0 |
| Fresh 21:45–21:55, one-second consent | 105 | 48 | 258 | 0 | 0 |

The 20-minute comparison retains one failed subscriber and one transport with
unknown response weight in both policies. It adds no unavailable query in this
trace. Three collector requests move later under sharing; maximum subscriber
delay is 276 ms and maximum advance is 567 ms. Unknown weight is reported
separately, not counted as zero known cost or proof of aggregate IP headroom.

A deliberate failure-fanout control shows an important downside: sharing a
failed leader can withhold a response from a follower whose separate observed
request succeeded. The driver reports that changed outcome without using later
success or matching body bytes to choose which request becomes the leader.

## Fresh comparison after the failure-handling update

The revised declaration was retained at 21:39:30.306718 UTC, before its fresh
21:45–21:55 window. Capture occurred at 21:57:13.772307, after the declared 21:56
earliest capture. The frozen candidate was committed before this inspection.
All 105 window requests returned HTTP 200; eight additional requests initialize
the model. Observed median latency is 311 ms, p95 464 ms, maximum 654 ms, and
observed estimated upper rolling weight peaks at 516.

One-second consent shares 48 window requests, reducing modeled known peak weight
to 258 and total known weight from 2,217 to 1,203. One collector request moves
later to preserve serialization. Maximum subscriber delay is 45 ms and maximum
advance is 447 ms. Bodies and status/error outcomes match their original sources;
there are no newly late or unavailable queries. Strict consent shares two
same-millisecond requests, with peak weight 474. These results support repeating
the sharing opportunity in a fresh trace, not generality across regimes or a
production deployment benefit.

The complete fresh source analysis, both replay objects, both SQLite ledgers and
independent verification reproduce byte for byte from the extracted final archive.

## Qualification and reproducibility

Final candidate `4a13f106230ae85c1acd64792d606b7b2d9c22d3` is committed and pushed
on `research/v89-public-request-sharing-20260916`. There are 119 passing tests
in both the isolated worktree and the extracted archive, with network denied
and writes to live data, runtime, configuration and ROOT source denied.
Four real processes obtain one dispatch grant; a separate worker exits abruptly
after admission and recovery preserves its expired outcome without regranting it.
This is process-death evidence, not a power-loss or filesystem-fault guarantee.

The three broker modules exercise all 221 statements and 72 branches. Including
the replay driver, coverage is 307/308 statements and 101/102 branches. The
remaining branch is a defensive unexpected-delivery guard under validated replay
inputs. File/function limits and Ruff checks pass. Early missing-feature failures,
the metadata-integrity and zero-duration defects caught during development, and
the original rejected later replay remain retained separately from passing runs.

The independent standard-library verifier checks original raw hashes, body bytes,
study/request identity, SQLite registration and receipt hashes, transport lineage,
single dispatch grants and causal per-collector serialization. Mutation controls
reject altered source bytes, database bodies, timestamps, lost requests, false
body-equivalence labels and changed declaration identity. It makes no optimality
claim. Both complete development replay JSON objects and all four SQLite ledgers
reproduce byte for byte from the extracted archive; independent checks agree.

The final archive contains 3,675 files verified against Git blobs, worktree and
extracted bytes. Archive SHA:
`4bf7ec9c7d9d546f6456c5d35cfafc9aa97382224d89e3aa9a19c92353fe6eec`.
Earlier source/archive `62b22ab` remains retained to explain the replay scope
change. The broker's lease, cancellation, publication and receipt contracts did
not change during the transport-error replay extension.

## Limits and next implementation

The fixed-workload model preserves collector ordering but assumes the observed
leader duration and body after a modeled dispatch. Real replanning and later
responses can differ. It assumes zero broker/IPC/commit overhead. Fresh-query
timeliness uses a latest-requested-candle deadline proxy; it does not establish
per-observation timeliness, fills, returns, fees, slippage or a market-regime edge.
HTTP status errors and lease-expiry replay still reject explicitly; direct broker
controls cover those cases independently, not a full adaptive workload model.

The next implementation is an isolated transport/IPC adapter with broker-clock
sampling, bounded queueing, real publication/delivery timestamps and aggregate
request admission. Test follower disconnect, cancellation, lost acknowledgments,
worker death, deadline expiry, 429 and correlated failure against actual process
boundaries and a controlled local transport. Validate the eventual collector
adapter and study declaration continuity before using the service for acquisition.
Actual IPC overhead, global IP load and complete failure/replanning replay remain
requirements before a concrete deployment proposal.

| Alternative | Evidence and trade-off | Decision |
| --- | --- | --- |
| Preserve existing collectors | Maintains declared receipt semantics; duplication remains | Retain during offline integration |
| Install current kernel directly | No qualified IPC, clock adapter or aggregate admission | Not deployment-ready |
| Continue adapter qualification | Measured sharing opportunity; explicit earlier-time consent and correlated-failure risk | Next offline task |

Falsifiers include altered source/receipt hashes, incorrect causal availability,
duplicate dispatch grants, lost subscriber outcomes, unreported unknown weight,
or representative later evidence showing changed data/failure concentration that
outweighs the opportunity. A later deployment approval request must identify the
tested integration, source, affected declarations, restart and rollback procedure.
The existing installation approvals do not authorize that future deployment.

Evidence: `data/logs/research/bidirectional_cohort/v89_public_request_sharing_20260916_v1/`.
The continuous goal remains active; no financial or sealed prospective outcomes
were evaluated in this investigation.
