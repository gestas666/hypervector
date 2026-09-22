# V90 monitoring and research capture implementation plan

**Goal:** Repair monitoring and bounded restart behavior, retain oracle-premium research history, and restore sidecars only at the operator-authorized flat boundary.

**Architecture:** Keep supervision in stdlib-only script modules outside the live implementation tree. Extend the existing unsigned context read and append durable research records before publishing latest telemetry. Preserve V89 trading parameters; V90 remains a reviewed, pending proposal.

**Tech stack:** Python 3.13, pytest, JSONL, atomic JSON, macOS launchd.

## Authorization and boundary

The operator approved full implementation on 2026-09-20, conditioned on flat state, followed by proposal review and code review. Preparation occurs in an isolated worktree. Deployment requires fresh flat/order-free venue reconciliation. On 2026-09-21 the operator explicitly authorized the transition drain; V89 acknowledged activation at 05:37:30 UTC under request `af62626d50cc4b10880109cb6eef735c`. New entries are withheld while existing exits continue. No size increase is included in this implementation.

## 1. Monitoring

Files: `scripts/cohort_backend_supervisor.py`, extracted `scripts/cohort_supervisor_*.py`, `tests/test_cohort_backend_supervisor*.py`.

Write regression tests reproducing null markets, malformed documents, stale embedded timestamps, unresolved active-market fees, and absent processes. Confirm failures, then implement explicit unavailable probes without crashing or reporting success. Keep each module under 500 lines and functions under 50 lines. Existing alert and child-process tests must continue passing.

## 2. Restart lifecycle

Write failing tests for budget exhaustion across independent supervisor invocations, corruption, operator STOP, clean exit and fail-closed entrypoint refusal. Persist restart accounting before each launch, bind it to the command, and hold without spawning when exhausted. Test induced kill using disposable children only. Verify launchd behavior and prevent competing supervisors through a singleton lock.

## 3. Research history

Files: `src/hypervector/research/hip3_roster_funding.py`, `hip3_roster_observer.py`, a research-history module, `scripts/hip3_roster_observer.py`, corresponding tests.

Test exact symbol mapping of premium, oracle price and mark price; missing/null values; invalid/nonfinite values; one context request per poll; successive snapshots and restart retention. Persist timestamped context rows to an append-only daily journal, without account or wallet fields. Record gaps/errors explicitly and fail visibly on storage errors. Reuse the existing public request and preserve legacy funding callers.

## 4. Operational procedure and proposal

Correct the runbook to boot out/bootstrap edited service definitions, inspect registered arguments, back up installed plists, and use isolated observe-mode acceptance. Correct the uptime multiplier, research-capture claims and candidate identity. Separate the existing-size operating alternative from the unvalidated larger-size candidate. Refresh pending approval evidence hashes after document edits; retain pending status.

## 5. Acceptance and review

Run focused regression tests with coverage, full non-network Python tests, Rust TUI tests and status. Review the full diff and new files against failure modes, secret handling, source identity, rollback, typing and structural limits. Repair findings and rerun affected checks. No network calls in tests. Public read-only operational probes are separate acceptance evidence.

## 6. Flat-boundary rollout

Recheck fresh checkpoint and unsigned venue positions/orders. Back up the exact files and installed definitions before deployment. Install only validated files; restore the observer and read-only watch service, verify fresh telemetry and durable research samples. Restart ownership requires the documented V89 process handoff and explicit arm flags already associated with the authorized repair; do not activate V90 sizing. Preserve a recoverable rollback and record evidence in the handoff.

## September 21 incident amendment: public candle server failures

The live backend exited on an HTTP 502 in `fetch_hl_ohlcv_snapshot`, after the
drain had been active for approximately 39 minutes. Reproduce that failure with
mocked responses, then extend the existing bounded candle-read retry budget to
HTTP 500/502/503/504. Classify exhausted transient reads as degraded polling, with
no successful heartbeat or new entries for that failed poll. Preserve causal
boundaries, required deadline exits, permanent HTTP failures and ambiguous
signed-order identities. Validate existing classifier callers and order recovery.

These source changes remain isolated until flat. Recovery of the existing V89
drain uses unchanged production source and its supported resume flag, mandatory
verified backup, venue reconciliation and a checkpoint writer bound to the new
run. Record that incident and recovery separately from flat-boundary deployment.

## September 21 rollout amendment: checkpoint restart following

Install a read-only checkpoint LaunchAgent with explicit `--follow-latest-run`,
without an old `--run-id`. Each publication selects the latest complete live
snapshot matching the configured profile and stays bounded to that run. Reject
different profiles, nonlive evidence and conflicting run pins. A regression
exposed the latest-event reader admitting an incomplete JSONL tail; bound reads
to newline-terminated records present at the captured byte boundary. Retain
committed malformed-row failures rather than silently selecting older data.
Verify the actual checkpoint advances to the supervisor's new backend run.

## Success and remaining uncertainty

Success requires passing regression tests, retained research samples, no signing client in observer paths, bounded restart attempts across process restarts, exact installed service identity and fresh operational evidence. Green tests do not prove profitability or absence of every defect. The magnitude of any uptime-related trade increase remains unverified.
