# V90 critical review response

Reviewed 2026-09-22, approximately 09:13–09:25 UTC. Scope: current working tree,
authenticated startup backup, loaded service state, and the external
`/Users/gestas/Downloads/hypervector-v90-critical-review.md`. The repository copy
`v90-critical-review.md` is byte-identical (SHA-256
`3f7568b019afa6e4721d13b1fbf33e4dc38fde2b103431eeb943d058364456d4`).

**Verdict: changes required before signing off on operational reliability.**
The external review correctly identifies the unlocked Option B configuration,
but overstates several configuration risks and misses three reproducible failure
paths in the latest source. Passing existing tests does not establish that these
paths work, or that the running services contain the recent repairs.

Review only: no production source, configuration, approval, service ownership,
orders, drain, or live process was changed. New review artifacts and offline
failure probes were saved separately.

## Findings, highest priority first

### 1. P1 — Mutation-capable reconciliation bypasses the new execution guard

**High confidence: reproduced with the real runner and engine against synthetic
venue ports.** [multi_asset_live_runner.py](../../src/hypervector/live/multi_asset_live_runner.py)
lines 322–339 call `reconcile_engines()` before entering `execution_phase()`.
Reconciliation is not exclusively a read: the engine calls
`SolPartialProtectiveRecovery.reconcile()`, whose
[_close_remainder](../../src/hypervector/live/sol_partial_protective_recovery.py)
submits a reduce-only close at line 250 and reads the venue at line 256.
Bracket reconciliation can also cancel sibling orders.

Injecting a 502 after an actual simulated partial close produces:

```text
post-close 502 swallowed
local state=EXIT_PENDING
execution_phase_failed=False
degraded_records=1
orders_attempted=False
venue_remaining=6.25000  [synthetic fixture units, not live exposure]
```

The run loop returns normally after the bounded poll, and emits a degraded
heartbeat claiming no order was attempted, although a close was submitted.
The remaining synthetic position is still awaiting completion. A subsequent
successful reconciliation may recover it; this reproduction does not establish
that it remains stuck indefinitely. It does establish that the promised
post-mutation error boundary and telemetry truthfulness remain incomplete.

**Required correction and validation:** cover lifecycle reconciliation's
mutation-capable sections with an explicit execution-failure boundary, while
preserving retry treatment for genuinely read-only acquisition. Make the
post-close probe propagate a runtime fault, retain exact durable close identity,
and test recovery without duplicate closes. Include bracket-cancel failures and
the existing pre-execution transient-read regression.

### 2. P1 — A failed event writer also breaks the supervisor's fault handler

**High confidence: isolated fault injection reproduced it.** In
[cohort_supervisor_runtime.py](../../scripts/cohort_supervisor_runtime.py)
lines 183–193, the exception handler calls `_event()` before persisting the hold
or entering monitoring. `_event()` uses the same writer that may have caused
the original exception. `_hold()` also requires that writer on entry.

With event-log writes raising `OSError`, a disposable backend starts, its
`backend_launched` event fails, and the handler's `supervisor_faulted` event
fails again. The exception escapes; monitored-hold calls equal zero. The
supervisor can exit after spawning its child, losing ownership monitoring.
Loaded launchd policy can restart the supervisor, but that does not restore
reliable monitoring while the logging failure persists. Backend singleton
locking remains a separate protection against duplicate account owners.

Alert delivery has the same dependency: the JSONL sink precedes optional
notification sinks, so its failure can prevent their delivery too.

**Required correction and validation:** latch the failure independently of
event/alert storage, preserve health polling, and report unavailable durability
through a channel that does not depend on the failed path. Inject event-log,
alert-log, and journal failures independently and together; verify no new child,
no abandoned ownership, and continued observable fault status. Do not silently
treat a failed durable write as successful.

### 3. P1 operational gap — The live processes predate the repairs

**High confidence: process age, loaded configuration, and authenticated startup
source agree.** Backend PID `78254` and supervisor PID `78251` started at
05:01:44 UTC. The supervisor reports one launch and no exit. Its loaded
`ExitTimeOut` remains **5 seconds**, whereas
[the current generator](../../scripts/cohort_backend_supervisor.py) specifies
**180 seconds** and the child shutdown routine allows **120 seconds**.

The running cohort's prestart backup is
`prestart_20260922T050145.835341Z_c8938787268c`. Its manifest SHA-256 was verified:
`17f233da8b8abd98970beb2c66f188c5acf827eceac8656fd7343c6d2495791e`.
The decompressed entrypoint and runner match their manifest hashes and differ
from the current files. That archived runner lacks `execution_phase` and
`maximum_consecutive_degraded_polls`; the archived entrypoint lacks the new
runtime preflight and `EXIT_START_REFUSED` handling.

Consequently, the current source's successful tests do not validate the active
backend. The loaded shutdown timeout can also expire before the supervisor
finishes its intended graceful-stop sequence. This is a deployment gap, not
evidence that an execution failure is occurring now.

**Required validation:** after correcting the remaining source failures, use a
controlled transition boundary with fresh venue/order reconciliation, retained
rollback evidence, and exact source identity. Verify the installed and loaded
plist timeout, new process/run identity, and startup manifest. Do not treat a
matching configuration fingerprint or a fresh heartbeat as proof of current
implementation identity.

### 4. P2 — An unpersisted stop can disappear at the next supervisor launch

**High confidence: two isolated supervisor invocations reproduced rearming.**
[RestartJournal.hold()](../../scripts/cohort_supervisor_state.py) records
`hold_persisted=False` when saving fails. Its docstring requires the caller to
remain alive and alert, but the runtime does not inspect that flag. In
[cohort_supervisor_runtime.py](../../scripts/cohort_supervisor_runtime.py)
lines 394–397, a clean exit returns success after an unsuccessful hold write.

The probe permits launch reservations to persist but rejects hold writes. After
the first clean exit, the on-disk journal still says `hold_reason=null`.
A second supervisor invocation launches another backend: **two launches where
one is required**. A similar unchecked flag exists in operator-stop paths.

This does not imply an immediate launchd loop: successful exit suppresses
KeepAlive. The risk occurs at a later RunAtLoad/kickstart/recovery after the stop
was lost. A surviving STOP file independently blocks a launch.

**Required correction and validation:** consume `hold_persisted` at every exit
boundary. Preserve an observable non-launching state when persistence fails and
define explicit recovery of that state. Test both clean exit and operator signal,
including a subsequent supervisor lifetime and retained STOP behavior.

### 5. P2 — The operating documents still describe incompatible candidates

**High confidence: directly observable text.** The external review's finding 5
is still valid:

- [Profit-protection plan](../plans/2026-09-21-v90-profit-protection.md), lines
  3–19: pending activation, completed drain, proposed 100/25/50 protection.
- [Profit-protection readiness](2026-09-21-v90-profit-protection-readiness.md),
  lines 3–20: stopped trading and the protected v2 candidate.
- [Activation runbook](../proposals/v90-supervisor-20260920/v90-activation.md),
  lines 7–35: an executed banner is followed by pending protected approval, old
  fingerprint `360de4…`, and claims that no backend/supervisor is running.

These are actionable operating instructions, so the contradiction is more than
historical wording. **Required correction and validation:** mark historical
proposals superseded and publish one current recovery/activation procedure with
the actual fingerprint, authority, and service state. Preserve historical
approval evidence; several documents are content-hashed by the approval record,
so editing them in place without maintaining that evidence can break validation.
Validate approval hashes and dry-run the revised procedure afterward.

## Assessment of the external review's seven findings

| External finding | Assessment of current V90 |
| --- | --- |
| 1. HYPE envelope, High | **Downgrade to future configuration cleanup.** HYPE is observation-only. An offline test first validated the present approval, then enabled only HYPE execution; the altered fingerprint was rejected by the exact approval boundary. It is not a demonstrated one-edit live-arming bypass. $2,500 is notional, not an assertion that half the bankroll is posted as margin or lost at the stop. Review its size if execution is deliberately reauthorized; do not introduce an unrequested observation ceiling. |
| 2. Refusal exits 1, High | **Correct historical issue; repaired in current source, deployment still outstanding.** Startup validation now runs before backup/client construction and exits 2; run-phase failures remain exit 1. Avoid mapping every `MultiAssetLiveRunnerError` to 2 regardless of phase. The backend's exit 2 is handled by the supervisor's hold; launchd observes the supervisor, not the backend's exit directly. |
| 3. BTC 80 vs 60 bps, Medium | **Low-priority clarity issue.** The bound sweep uses 60-bps stop and target; the asset fallback is 80. No demonstrated live widening. A blanket asset/provider equality rule would constrain legitimate provider-specific contracts. Align/document deliberately and refresh identity if changed. |
| 4. Brent mechanism evidence, Medium | **Valid research limitation, already disclosed and scoped in approval.** The repository labels 20/10 versus 8/4 unvalidated, with the cited contrast p≈0.52. This does not establish that either is superior, and is not a wiring failure. |
| 5. Superseded protection documents, Medium | **Confirmed; still unresolved.** See finding 5, including the contradictory activation procedure. |
| 6. Observation sides, Low | **No execution leak established.** Observation directions and execution overrides are separate concepts. Empty execution scope remains empty. Document the distinction; do not remove diagnostic directions merely to make the fields identical. |
| 7. Eight slots versus five executable assets | **Informational.** The current one-position-per-asset executable set cannot occupy eight slots. Reducing the limit does not repair a demonstrated current fault and changes profile identity. |

The configuration is consistent with the later Option B record: BTC sweep plus
unlocked Donchian 20/10 on SOL, SNDK, Brent, and TSLA; ETH, HYPE, and SPCX observe.
BTC retains a fixed take-profit. The four hourly routes have initial stops,
recipe exits, and a 24-hour maximum-hold contract, **but no profit lock**.
V90 therefore should not be described as implementing the earlier 100/25/50
profit-retention proposal or as preventing unrealized-profit givebacks.

Confidence in future profitability remains low. Brent's mechanism change,
TSLA's failed predeclared selection bar, and SNDK's increased size are explicitly
disclosed research/risk choices. Code correctness cannot validate those returns.
Forward evidence or a separately specified study would update that assessment.

## Validation and current-state limits

- Offline runtime configuration validation accepted the current V90 live-mode
  configuration without constructing live execution clients.
- **160 existing targeted tests passed in 8.35 seconds** across V90 Option B,
  protection/transition contracts, runtime preflight, entrypoint, runner,
  degraded deadlines, and supervisor boundaries/restart persistence.
- **Three new safety assertions failed; one approval-boundary assertion passed.**
  [Reproduction source](../../data/logs/research/bidirectional_cohort/v90_critical_review_20260922/test_review_gaps.py)
  and [captured output](../../data/logs/research/bidirectional_cohort/v90_critical_review_20260922/reproduction_results.txt)
  are retained. These expected failing review probes are outside the normal test
  directory. They use disposable stub children and mocked/offline venue ports;
  live services are untouched.
- The native partial-close probe reuses the seven-asset replay fixture and actual
  shared runner/engine. It bypasses a duplicate `start()` because the fixture is
  already started, and suppresses bounded-run shutdown solely to inspect the
  failure state. It is not a live fill reconstruction or full V90 venue test.
- The 09:23:39 UTC checkpoint reported `running_consistent`, the expected
  `c8938787268cfa94fd6c92026c191985a11c0225325452f415787b23fe6cb841`
  fingerprint, and eight FLAT asset states. This is checkpoint evidence, not a
  newly fetched independent venue/order-free proof.
- At 09:22:22 UTC the fresh status command reported PID 78254 alive, no health
  problems, and 25.79 GiB free. Disk capacity remains a real operational concern;
  any retention cleanup must preserve authenticated replay/rollback dependencies.
- The full Python/Rust suites, real service restart, real failure injection, and
  independent venue reconciliation were not run in this review. Existing claims
  elsewhere about those checks are not presented as newly verified here.

Reproduce the new assertions from the repository root:

```sh
PYTHONPATH=src:scripts:tests:. .venv/bin/python -m pytest \
  data/logs/research/bidirectional_cohort/v90_critical_review_20260922/test_review_gaps.py \
  -q --tb=short
```

Recommended sequence: correct the three reproduced failures, run their regression
tests plus relevant existing coverage, reconcile the operating documents without
invalidating approval evidence, then validate the deployment at a controlled
boundary. Leaving the current deployment untouched avoids a restart immediately
but retains the documented old-code exposure. Changing sizes or profit-lock
policy would be a separate strategy decision and would not repair these defects.
