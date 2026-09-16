# Research Collector Recovery Launcher Implementation Plan

> Implementation uses the writing-plans, executing-plans, systematic-debugging and test-driven-development workflows in the existing isolated worktree. Continue autonomously within the research scope.

**Goal:** Recover an absent frozen public-data collector after host/session interruption, with no financial authority and no change to original observation timestamps or study windows.

**Architecture:** A bounded startup guard authenticates an immutable job specification, manifest and source pins. A user-level launchd interval invokes the guard; a valid absent collector replaces the guard through exec with a clean environment. A running collector is observed and left alone. The existing collector writer lock remains the final concurrency authority. launchd configuration is generated as a reviewable artifact before any activation.

**Tech Stack:** Python 3.13 standard library, existing health/pin and runtime-lock helpers, pytest, macOS launchd.

## Task 1: Preserve the interruption evidence

Create immutable evidence under `data/logs/research/bidirectional_cohort/v89_collector_shutdown_recovery_20260916_v1`: sanitized Codex shutdown excerpt and original-file hash, original two stopped health records, macOS reboot/shutdown records and readable launch-agent scan. Correlate UTC timestamps. State that shutdown initiator and exact signal sender remain unverified. Do not read sealed trading outcomes.

## Task 2: Qualify a frozen research startup guard

Create `src/hypervector/research/prospective_collector_recovery.py`, `scripts/prospective_collector_recover.py` and `tests/test_prospective_collector_recovery.py`. Reuse source authentication from `prospective_collector_health.py` via a public helper rather than duplicate it.

Write tests first: legitimate absent collector; already-live lock owner; stale/unhealthy live collector; reused PID; occupied/unowned/ambiguous lock; malformed health/spec; source/interpreter/manifest mismatch; non-research entrypoint; expired window; bounded persistent restart attempts; clock rollback; no inherited credentials; immutable receipts; concurrent invocations. Every rejected condition must preserve the collection and produce actionable evidence. Missing venue data or economic performance must not enter restart decisions.

Run `.venv/bin/python -m pytest` from ROOT with `PYTHONPATH` set to WORK/src:WORK/tests; expect failures before implementation, then pass with meaningful changed-module branch coverage. Use mocked process/clock boundaries; tests make no network requests. Preserve failing output.

Use exact supported research entrypoint names, absolute source/output/interpreter paths and hash pins. Reject unknown fields/commands. Before starting, record an immutable attempt; no more than three starts in one hour, with a minimum 60-second interval, persistent across launcher invocations. Refuse starts at/after the fixed end. An existing healthy job is never restarted; an existing unhealthy job is an alert, not a kill. Exec only the frozen collector, which independently enforces its writer lock and source identity. The wrapper cannot guarantee capture while the host is asleep/off or before user login.

## Task 3: Qualify installation artifacts and lifecycle

Create exact three job specifications, authenticated wrapper/source copies, and launchd plist artifacts with `RunAtLoad=true`, `StartInterval=60`, no unconditional KeepAlive and credential-free `/usr/bin/env -i` invocation. Validate with `plutil`; retain configuration bytes. Exercise real exec and source/lock rejection against a harmless private fixture, never a financial process. Run read-only inspections against all three actual collectors and verify existing process births and study pins remain unchanged.

Keep OS activation separate from artifact generation. If activation is outside the user-authorized research scope, present concrete files and commands for final approval only after qualification. Preserve rollback instructions, limitations, evidence journal revision and the next single investigation. Do not claim reboot survival without a relevant lifecycle rehearsal; do not reboot the host.
