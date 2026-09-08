# Entry deadline gap inside the execution engine

Status: confirmed in an offline reproduction; no breach observed among the four
current-run live entries audited. No production source, deployment, strategy,
configuration, process, or venue order changed in this investigation.

High confidence in the reproduced boundary gap and frozen live timestamps.
The evidence does not establish how often the gap causes a live breach or its
financial impact. A changed source path, inconsistent event identity, changed
evidence bytes, or a clock reconstruction contradicting these results would
require revision.

## Finding

`execute_fresh_routed_actions` samples the configured entry deadline before
calling the engine. `SolRangeOnsetLiveEngine.enter` subsequently waits for a
venue-flat reconciliation before submitting an entry. That blocking read can
consume the remaining deadline without another freshness check.

The production factory in `scripts/multi_asset_bidirectional_live.py` constructs
this same engine for every configured asset, including the HIP-3 markets. The
deadline is 30 seconds for BTC, SPCX, SNDK, and Brent, and 60 seconds for the
other three active providers. These are existing configuration values.

The current reporting label `submission_contract_enforced` derives from the
earlier action timestamp. It verifies admission at that check; it does not
prove freshness at the subsequent transport boundary. Preserve that distinction
when reviewing historical diagnostics.

## Controlled reproduction

Research source commit: `52c7cf6` in
`/Users/gestas/Prototypes/hypervector-v89-storage-spcx-20260908`.
The replay uses the real cohort runner, routing executor, engine, state machine,
and ledger, with the existing scripted SOL adapter and a deterministic clock.
No execution client is constructed; connection, name-resolution, and datagram
send attempts are denied by an audit hook.

| Scenario | Recorded check | Added flat-check delay | Fake transport | Result |
| --- | ---: | ---: | ---: | --- |
| Fresh entry | 29 s | 0 s | 29 s | Submitted within 30 s |
| Exact boundary after check | 28 s | 2 s | 30 s | Submitted at the allowed boundary |
| Already stale | 30.001 s | 0 s | None | Correctly withheld |
| Provider processing crosses deadline | 31 s | 0 s | None | Correctly withheld |
| Flat check crosses 30 s deadline | 29 s | 2 s | 31 s | Reproduced breach |
| Flat check crosses 60 s deadline | 59 s | 2 s | 61 s | Reproduced breach |

The desired-invariant regression has **two failures and four passing controls**.
Those failures are preserved explicitly; this is not an accepted fix. A separate
nine-case diagnostic replay measures quote aging and the phase of the failure.
Its Brent-calibrated case reproduces the observed 8.010353-second quote age by
injecting 6.522333 seconds before the routed decision and 1.488020 seconds before
the order intent. This calibrates stage timing, not Brent economic behavior or
the actual seven-asset provider calculation. The test market keeps its strategy
reference price of 73.0; its book midpoint of 73.05 is not substituted for it.

## Current-run live scope

The read-only audit verifies complete checkpoint-bounded source prefixes by
SHA-256, run identity, and sequence continuity. It retains original routing,
quote, decision, order-intent, and acknowledgement lines with source offsets.
All four routed entries match the corresponding asset entries and checkpoint
fill order IDs.

| Entry | Recorded check age | Order-intent age | Acknowledgement age | Limit |
| --- | ---: | ---: | ---: | ---: |
| SNDK long, 01:00 UTC | 12.713 s | 13.015977 s | 14.405170 s | 30 s |
| SPCX long, 02:00 UTC | 20.241 s | 21.523855 s | 22.737536 s | 30 s |
| Brent long, 06:00 UTC | 21.471 s | 22.959418 s | 24.373103 s | 30 s |
| SNDK short, 07:00 UTC | 16.773 s | 17.968622 s | 19.281372 s | 30 s |

Every acknowledgement was inside its configured deadline. No live deadline
breach is demonstrated in this sample. The earlier check understates the
order-intent age by 0.302977–1.488418 seconds. Recorded quote ages at intent were
6.677164–8.330902 seconds. Elapsed stages combine reads, calculation, and local
persistence; they do not separately identify network latency or price impact.

Eight audit tests passed: exact reconstruction of all four published entry
results from retained raw events, plus seven controls rejecting corrupted
deadline, age, clock order, acknowledgement, or timezone evidence. All 318
source members in the replay archive matched their recorded hashes. All eight
frozen live-audit files matched the manifest. Source formatting and lint passed;
both research scripts meet the file/function length and annotation checks.

## Proposed implementation and validation

Recommendation: prepare an isolated patch that carries the existing route
deadline to the final local submission check, after blocking pre-entry work,
and exposes the timestamp for the boundary actually checked.

Why now: the reproduced failure is supported by real delays inside the same
engine path, even though the four observed entries had sufficient headroom.
Applicable regime: any; this is a technical timing contract, not a market filter.

Expected upside: enforce the already configured deadlines and make reported
timing faithful to the checked boundary. No improvement in trade frequency,
returns, or win rate is claimed.

| Alternative | Benefit | Limitation | Disposition |
| --- | --- | --- | --- |
| Keep current behavior | No deployment | Gap remains and reporting overstates its scope | Current state |
| Widen deadlines | More time for slow cycles | Changes the strategy contract and leaves the same gap | Not supported by this evidence |
| Shorten the global polling interval | May reduce decision age | Does not enforce the boundary inside the engine | Separate investigation |
| Recheck after blocking work | Honors existing limits | Requires correct state recovery and telemetry | Prepare and test |

The patch must preserve strict-greater-than semantics: an entry at its exact
deadline remains eligible. An expired entry must produce an explicit
`stale_before_submission` non-action, stay flat, and allow later cohort work to
continue. It must not submit or leave an entry pending merely because the
state machine advanced before detecting expiry. Automatic exits and protective
orders must remain independent of the entry deadline. Submission retries and
slow persistence must be included in the boundary analysis; an uncertain prior
submission still requires order-identity reconciliation rather than duplication.

Validation still required: implement the isolated candidate; make the two
preserved red cases pass; cover exact-boundary, already-stale, slow provider,
slow reconciliation, slow persistence, retries, IOC no-fill, subsequent routes,
exit/protection behavior, and raw-to-report timing parity. Check constructor and
protocol coverage for every executable adapter. No candidate patch exists yet.

Success metrics: no expired local dispatch in injected boundary tests; exact
non-action attribution; continued flat state and subsequent routing; no exit or
protection regression; telemetry names and timestamps match their actual stage.
Failure triggers: an overdue dispatch, stale check faulting the cohort, a pending
state without an order, duplicate retry, incorrect attribution, or delayed exit.

Explicit approval requested: none at diagnosis stage. Prepare and verify the
candidate and its rollback before requesting deployment approval under the
continuous-agent brief's Human control clause. The separately prepared mapped
reporting-reader proposal remains staged and unchanged.

## Evidence and next investigation

Artifacts are under
`/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/`:

- `v89_entry_deadline_replay_20260908_v2/`: nine cases, fake ledgers, source archive.
- `v89_entry_deadline_live_audit_20260908_v1/`: checkpoint, configuration, selected raw events, report, manifest.
- `v89_entry_deadline_contract_reproduction_20260908_v1/`: desired-invariant test and the two-failure result.
- `v89_entry_deadline_validation_20260908_v1/`: corruption controls, source/wiring evidence, verification and package versions.

The first replay attempt stopped before a cycle because the harness omitted
the required startup timestamp. Its source is retained in the v1 directory;
v2 supplies the explicit timestamp. A first live-audit import attempt failed
before capture because a prior-worktree helper depended on unavailable modules;
the completed audit reuses the helper available in its own source tree.

Single highest-value next investigation: implement and test the final-boundary
deadline candidate against the preserved failing regression, without changing
live execution. Prospective strategy outcomes remain sealed for their existing
predeclared observation block.
