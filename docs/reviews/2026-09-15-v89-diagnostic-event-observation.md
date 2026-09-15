# V89 diagnostic event observation coverage

The passive lifecycle watcher selected orders, fills, protection, closes and
faults, but omitted degraded heartbeats, strategy intents and routing outcomes.
An entry that expired before engine admission could therefore produce durable
withholding evidence without waking that watcher. The backend recorded the
evidence correctly in the inspected source; this is an agent observation gap.

## Evidence and applied diagnostic change

The source contracts show three relevant paths:

- `emit_poll_degraded` writes a `heartbeat` with `status=degraded`.
- A deadline expiring at engine admission becomes `stale_before_submission`
  withholding. Cohort telemetry publishes the strategy intent and
  `intent_routing` outcome without requiring an order or terminal fault.
- Later expiry and confirmed IOC no-fill publish `entry_not_submitted` and
  `entry_not_filled`. Their preceding order events can already wake the
  lifecycle observer; the additional diagnostic receipt still merits capture.

Four compressed pre-start sources authenticate against the retained manifest.
Five relevant function ASTs match the inspected current source exactly. This
binds these paths to the source retained for backend PID 30603, without
claiming that every hypothetical failure happened in the current run.

A complementary, agent-owned watch now selects degraded heartbeats, strategy
intents, explicit non-submission/no-fill receipts, and routing rows containing
withholding, an action or an eligible evaluation. Ordinary heartbeats, empty
routing rows, ineligible exit-only evaluations without an action, and the
separate lifecycle watch's fills do not wake it. A withheld signal is evidence
to inspect; it is not automatically classified as a technical error.

The new watch reuses the pinned ledger reader and the qualified final-read and
saved-offset adapter. It preserves exact run binding, changed/truncated-ledger
detection, incomplete prefixes and terminal cursors. It has no financial
execution authority or network access code. The original lifecycle watcher
remains running: this is a distinct diagnostic scope, not a restart caused by
an observation timeout.

## Validation and current native observation

The retained baseline produced **14 failing cases**: seven diagnostic types
tested both at initial read and during the final sleep returned a quiet
deadline. The corrected scope passes **31 tests**, including healthy/no-action
exclusions, other-run isolation, malformed heartbeat/routing rejection and
changed/missing backend identity. These use temporary files and deterministic
clocks, with no venue calls or financial process access.

The diagnostic watch started at **23:09:07.268269 UTC September 15**, PID
**67653**, tool session **82480**, with a 7,200-second duration. Its expected
deadline is near **01:09:07 UTC September 16**, subject to scheduling. Lifecycle
watcher PID **17371**, session **27304**, retains its separate deadline near
00:49:45 UTC. Poll each existing handle; inspect a terminal result before any
replacement or continuation.

The first scan resumes from the eight anchors saved at **22:37:54.202074 UTC**.
An independent in-memory DuckDB query authenticated **10,295,189 bytes / 4,064
complete rows** through the first-scan endpoints. It agrees with the watcher:
**zero qualifying diagnostics**, no incomplete suffix. Seven positive SQL
controls are detected; routine heartbeat, fill and other-run controls are
excluded. No actual missed rejection or degraded cycle is demonstrated in
these saved intervals. Later observations remain pending.

The first verifier attempt failed because SQL JSON-arrow operator precedence
misparsed a conjunction. Explicit JSON extraction fixed that research harness;
the initial source/log and successful verification are retained. That failure
did not alter either watcher or production code.

Financial-session PIDs **29190, 29191, 30603, 62016 and 62017** retain their
recorded birth times. No financial process, strategy, route, profile, leverage,
sizing, deployment setting or production implementation changed.

## Decision, limits and next investigation

**Recommendation / why now:** retain the validated complementary scope because
the previous observer could remain quiet despite an explicit degraded cycle or
pre-submission withholding. Applicable to every asset and market regime.

**Alternatives / trade-off:** waiting only for fills or terminal faults leaves
this gap. Repeated full audits would reread historical evidence. The bounded
companion adds one local reader and a small 15-second polling workload, while
the existing lifecycle observer continues uninterrupted.

**Expected upside:** earlier evidence for missed-opportunity and degraded-data
diagnosis. No return, win-rate or trade-frequency improvement is established.

**Confidence / success / falsifiers:** high confidence in the tested event
selection, source binding and authenticated overlap. An omitted matching row,
ordinary-row false alert, wrong run binding, schema change, changed source hash,
native/SQL mismatch or leaked process requires review. Terminal native results
for both watches remain pending. These observers do not diagnose every possible
silent stall, corruption or semantic strategy error.

**Rollback:** retain all source, anchors and receipts; retire only the specifically
identified agent-owned diagnostic watch if validation fails. The original
lifecycle watch and user financial session remain outside its ownership.
This read-only diagnostic change is within the existing research authority;
no live-change approval is requested.

**Highest-value next investigation:** inspect the first qualifying diagnostic
or lifecycle result, reconcile it with the native routing/order history, and
distinguish normal withholding from technical loss of an executable opportunity.
On an actual deadline, retain terminal cursors before another handoff. The
installed band-history/startup-candle changes still await a normal user-controlled
backend start. Completed strategy studies and September 22/23 outcome seals
remain closed.

Evidence: `data/logs/research/bidirectional_cohort/v89_diagnostic_event_watch_20260915_v1/`.
