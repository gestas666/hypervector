# Recorded SNDK interruption and lifecycle receipt candidate

The native SNDK ledger resolves the earlier uncertainty about the local
engine: it records `STOPPED`, reason `operator_stop`, at **September 15
16:41:33.263198 UTC** and recovered `OPEN` at **18:41:39.019858 UTC**.
The recorded state interval is **7,205.756660 seconds**, or two hours and
5.76 seconds. High confidence applies to these authenticated state records.
The reason does not identify a person or distinguish a stop file from a
termination signal; the runner maps both shutdown sources to that label.

## Native protection and scope

The last prior venue reconciliation at **16:41:22.382846 UTC** and first new
reconciliation at **18:41:38.640023 UTC** show the same stop order
**545845630697**: a **0.326** reduce-only buy Stop Market at **1561.5**.
The short remains **0.326 at 1531.7 with 10x isolated leverage**.
Entry identity **545845583477**, original opening time, execution plan and
protective state match across stop and adoption. All **23** captured new-run
reconciliations preserve that stop and the same native fill-trade identities.
The new-run prefix contains **zero new order operations**.

The new audit authenticates **2,024 prior-run records and 99 new-run records**
against original bytes, offsets, sequence numbers and hashes. The two asset
prefixes join without a sequence or byte-range gap. Sixteen offline tests
reject altered stop size, side, trigger, reduce-only status, exposure,
leverage, ownership, plan, recovery ordering and added order operations.
Two network-denied runs produce identical 943-byte results, SHA-256
`1efe84c8f769a35ed29c32161e830b0074b92b697de94fa384bf4b3448d82749`.

This establishes a local state interruption and successful observed adoption.
It does **not** prove continuous venue stop presence between those two
reconciliations. The seven missing quarter-hour evaluations and unavailable
17:00/18:00 exit decisions remain as documented in the
[exit signal audit](2026-09-16-v89-sndk-exit-signal-reconstruction.md).
No earlier-fill counterfactual or new P&L result is calculated here.

## Reproduced reporting defects and candidate repair

1. `MultiAssetLiveRunner._stop_all` stops individual engines but does not
   publish the existing cohort `runtime_stopped` event. The observed prior
   cohort therefore ends on a running heartbeat despite SNDK's later stopped
   state. The candidate emits normal completion after the engine stop loop
   returns. It supports the three existing reasons: operator stop, bounded
   completion and completed transition drain. An engine stop failure propagates
   without a normal completion receipt.
2. The backup announcement uses buffered stdout. An actual offline subprocess,
   still alive and blocked after the announcement, leaves redirected output
   empty until exit. The candidate adds `flush=True` to that existing print;
   receipt text is byte-for-byte unchanged. The current backend's log lacks its
   startup receipt, consistent with this reproduced buffering behavior. Its
   in-memory output buffer was not inspected.

Candidate commit:
`e49f2fa61f569f69f88d783bf50a7a2937117d96`, based on
`889eba26138b7becfcd8d9f4becdf7fd04911cc8`.
Worktree: `/Users/gestas/Prototypes/hypervector-v89-lifecycle-receipts-20260916`.
The patch changes four production reporting/source-interface files, updates
one test fixture, and adds regression tests and an implementation plan.
It has **not been installed** in the active checkout.

## Validation and exact artifacts

Four meaningful regressions failed before implementation: the three missing
normal-stop receipts and delayed startup output. Failure-propagation and
unknown-reason controls already passed. An earlier test draft used the wrong
ledger return shape; those fixture errors were corrected before implementation
and their failed receipt is retained separately.

The final candidate and frozen-source runs each passed **115 tests** covering
live/observer runners, transient errors, entry deadlines, native telemetry,
startup boundaries and TUI supervision. The frozen run initially lacked the
external provider package required by one existing startup test. All **530**
provider source files selected by the actual source-discovery contract were
then captured and hashed; the same test passed without omission or substitution.
Ruff and patch whitespace checks passed. This is targeted validation, not a
whole-project or newly installed live acceptance claim.

Artifacts are under
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/sndk_restart_continuity_v1/`.
`candidate_manifest_v1.json` records every old/new file hash and the
35,595,083-byte candidate archive. `lifecycle_provider_sources_v1.json` pins
the external source dependency. `verification_v1.json` pins final checks and
the native reconciliation. The full patch is `lifecycle_candidate.patch`;
prior overwritten bytes are in `lifecycle_previous_source_v1/`.

## Approval-ready recommendation

**Recommendation / why now:** install the exact lifecycle reporting patch so
normal shutdowns and completed backups become visible promptly. These defects
complicated interpretation of the observed restart interval.

**Applicable regime:** all assets and regimes; the change concerns lifecycle
reporting, not signal selection. **Proposed live strategy change:** none.
**Proposed deployment:** apply the seven-file candidate patch; it becomes
effective at the next normal backend start. No agent-controlled restart is
included. The running backend has not loaded this candidate.

| Alternative | Benefit | Limitation |
| --- | --- | --- |
| Keep current reporting | No deployment action | Retains both reproduced omissions |
| Flush startup output only | Immediate backup receipt | Leaves cohort stop state ambiguous |
| Apply the complete receipt patch | Addresses both measured defects | Requires a later normal process start to load it |

**Expected upside:** clearer operational status and dependable recorded
shutdown boundaries. No profitability improvement or recovery of missing
historical decisions is claimed. **Risks:** normal-stop publication adds one
ledger write; write failure must remain explicit. Abrupt process death cannot
promise a normal-stop event, and this patch does not restart stopped trading.

**Validation remaining / success metrics:** after a separately authorized
normal start, observe the flushed receipt; after a normal stop, verify one
same-run completion event after the asset stop records and its correct reason.
**Failure / rollback triggers:** changed receipt text, false normal completion
after stop failure, altered financial operations or failed ledger publication.
The patch applies cleanly to the current base, and its reverse check passes
against the candidate. Before rollback, verify installed hashes and restore
only the manifest-listed previous bytes; no financial process action follows
from source rollback alone.

**Confidence:** high for reproduced defects, native boundaries and tested
repairs; installed live behavior and continuous venue protection remain
unqualified. **Explicit approval requested:** install this exact reporting
patch, with activation deferred to a normal backend start. The operating
mandate requires approval before live deployment changes. Existing long-running
source/account research continues while that decision is pending.
