# Frozen collector capture/store handoff qualification

The research relay now executes the **actual five frozen capture/store versions**
in separate interpreters and compares direct fabricated responses with the real
durable public service. **24 tests pass from candidate and archive**, and nine
complete cases per source independently authenticate raw bytes, persisted index
rows, imported source hashes, original requests and service acknowledgements.
High confidence applies to these bounded synthetic contracts. Full collector
adoption and financial improvement remain unqualified.

The most material finding is an adoption incompatibility: a shared 429 cooldown
changes the older collectors' subsequent retries into local deferrals without
HTTP. A session-level replacement therefore needs explicit admission and physical
transport accounting; it cannot be described as preserving all current behavior.

No live strategy, route, order, sizing, leverage, risk setting, collector, TUI,
or research job changed. No sealed prospective economics were inspected.

## Executed source and isolation

Source **7ce7c8dce568d1f030df4af17f6491264983cce4** is committed/pushed on
`research/v89-collector-adapter-20260917`, worktree
`/Users/gestas/Prototypes/hypervector-v89-collector-adapter-20260917`.
The written plan is `docs/plans/2026-09-17-public-collector-adapter-contract.md`
in that branch. Six research modules and three test modules were added; no
production module was changed. Ruff, return annotations and file/function
limits pass. Coverage percentages were not measured; there is no full-coverage
claim and the research relay is not qualified production adapter code.

Before launch the runner authenticates all 88 manifest-listed source references.
Each child gets a minimal environment, its exact frozen `PYTHONPATH`, disabled
bytecode writes and an isolated synthetic store. Imported Hypervector modules
must originate in that selected source tree; paths and hashes are retained.
Network, secret-file reads, live/runtime/database/config/source writes, and
writes to the five original frozen worktrees are denied by the test sandbox.

The quarter-hour producers call their original `capture_query` and original
store. Native execution calls its original `_Collector._capture`, including
one-admission and original peer-traffic checks against four empty synthetic
peer indexes. The outer native scheduling loop and durable slot reservation
are **not** exercised by this step. Instrumentation wraps ingestion to record
when the original ingest returns; it does not replace its storage logic.

## Results and what they establish

Each matrix scenario executes four quarter-hour producers and one native-minute
producer. A ninth complete service case supports ten integrity controls. Counts
below reproduced in the archive; physical timestamps and UUIDs naturally differ.

| Scenario | Local attempts, each mode | Direct mock calls | Service mock calls | Service deferrals without HTTP | Final stored observations |
|---|---:|---:|---:|---:|---|
| Complete candle | 5 | 5 | 2 | 0 | One per producer |
| Incomplete HTTP 200, then complete | 9 | 9 | 3 | 0 | Four quarter-hour producers; native remains incomplete |
| HTTP 503, then complete | 9 | 9 | 3 | 0 | Four quarter-hour producers; native remains incomplete |
| HTTP 429 throughout | 13 | 13 | 2 | 8 | None |

The older producers retain two attempts for incomplete/503 then success, or
three attempts for persistent 429. Native retains exactly one admitted attempt.
Its normal inner retry wait can occur before its admission closure rejects a
second attempt. Reopening and original raw recovery reproduce every request and
observation row exactly. No recovery behavior was simulated by copying expected
rows into the store.

The relay waits for a durable service acknowledgement before returning through
the producer's HTTP abstraction. The producer then stamps its own raw receipt,
fsyncs, and ingests. Verification requires ordered actual clocks:
service read <= acknowledgement <= session return <= raw receipt <= ingestion.
Raw body/status must match authenticated service delivery, and every raw file
must match its indexed hash and receipt timestamp. All local attempts and all
owned subscriptions are conserved; a deferral has no owned subscription and
no HTTP status. Deferral traces remain separate research evidence.

One-second earlier consent is explicit in this research fixture. A retry's lower
bound cannot precede its own previous call return, preventing reuse of its prior
incomplete response solely because that response lies inside the consent window.
This timing policy is proposed research behavior, not active collector consent.

Direct delivery is also mediated by the research parent, with serialized small
fabricated HTTP responses. This is a capture/storage correctness comparison,
not a latency benchmark or a replay of full independent network concurrency.
Response bodies are valid synthetic candles and response headers are empty.
Header preservation, large responses, other public query kinds and arbitrary
caller timeout values remain unqualified here.

## Failures retained and corrected

- The initial candle fixture omitted `n` (trade count). The actual legacy store
  rejected it. The fixture was corrected; no original decoder was weakened.
- A combined rerun happened inside the native guard's existing +/-90-second
  quarter-hour blackout. Native correctly made no request; the harness expected
  one, yielding nine failures and nine passing negative controls. The retained
  fixture heartbeat clocks reproduce the original guard's blackout result in
  all nine cases. These are guard rechecks at retained clocks, not nonexistent
  native HTTP timestamps.
- Response scenarios now stage before producer startup in a declared quiet
  interval, with actual waiting recorded in `staging.json`. Six boundary controls
  test that staging; no in-flight request deadline is extended. The response
  verifier now explicitly rejects an empty admitted-attempt set instead of
  indexing an empty list. The failed blackout run remains separate evidence.
- Independent verifier controls reject changed return clocks, raw hashes,
  payloads, acknowledgements, omitted producers, completion flags, index rows,
  imported source hashes and duplicated traces.

Final candidate tests: **24 passed in 19.04 seconds**. Final archive tests:
**24 passed in 19.01 seconds**. Nine candidate and nine archived cases independently
verify. Earlier development failures and intermediate runs remain retained.

## Reproducibility

Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_collector_adapter_20260917_v1`.

Harness/source archive `source.tar`: **1477 files, 13,373,440 bytes**, SHA
`b6843557beb4471d649146c87a81248a0468bc00a593cbc47ba510fd7c5ff796`.
Committed blobs, worktree and extraction match. Frozen producer archive
`producer_sources.tar`: **152 files, 901,120 bytes**, SHA
`2abfb95ea146f04520ece9d1772e61a9c607aaea8f6dffee02c5933a2036cf9b`.
It includes original manifest-listed sources plus actual imported dependencies;
the source manifest maps exact original paths and hashes to archive members.
The archive inventory rebases paths explicitly while preserving source/manifest
bytes. Both archives and original producer files were rechecked after execution.

Authoritative final runs are `candidate_final_v2_tmp/` and `archive_test_tmp/`.
`candidate_final_tmp/` is the retained blackout failure, not a passing run.
`candidate_final_verification.json`, `archive_verification.json`, source manifests,
`blackout_recheck.json`, final test logs and `post_archive_source_verification.json`
record the bounded acceptance evidence. Preserve these roots after journaling.

## Decision, trade-offs and remaining work

Retain this as an offline contract harness. It reduces uncertainty about source
mixing, raw receipt timing, persistence and retry behavior. It does not establish
a deployable adapter, venue rate headroom, or portfolio returns. The results apply
across market regimes because this step tests data acquisition mechanics only.

| Alternative | Benefit | Cost / unresolved behavior |
|---|---|---|
| Keep independent collectors | Preserves current studies and accounting | Repeated requests remain |
| Replace only their HTTP session | Demonstrated body/receipt/storage handoff | Cooldown changes retries; deferrals still look like local failed attempts to older schemas |
| Versioned admission and transport lineage | Can distinguish local intent, subscriber receipt and physical request | Requires explicit implementation, accounting, recovery and continuity qualification |

The **single next investigation** is a versioned admission/lineage adapter that
represents a no-dispatch deferral explicitly and binds each subscriber receipt to
authenticated physical transport evidence. It must preserve per-study budgets
and explain the changed shared-cooldown semantics rather than discounting unknown
traffic or silently rewriting the frozen raw schema.

Then qualify original full scheduling and store-driven recovery, 429 policy,
native reservations, cancellation, lost acknowledgement, delayed API return,
expiry, header preservation, crash/restart and study continuity. Unknown external
IP traffic and long-duration resource behavior remain separate requirements.
Wrong receipt availability, false physical-call accounting, changed source bytes,
missing attempts or unqualified study migration would invalidate adoption.

No live change or approval is requested at this stage. An eventual deployment
requires a concrete, fully reviewed proposal and explicit human approval.
