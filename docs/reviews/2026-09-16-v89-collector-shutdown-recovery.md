# September 13 collector interruption: cause evidence and qualified recovery

**Finding:** high confidence that the common collector interruption was associated with a macOS host shutdown. The retained desktop log records `macOS system shutdown requested` at **2026-09-13 23:01:06.566 UTC**. Both original research collectors published `stopped`, with no error, at **23:01:29.064 UTC**, **22.498 seconds later**. macOS `last` independently records a shutdown at September 13 19:01 local time and a reboot at 19:24. The exact shutdown initiator and signal sender remain unverified.

The pair's final cycle completed at 23:00:07.291 UTC with five complete queries. The seven-asset cycle completed at 23:01:07.058 UTC with four complete queries, zero deferred and zero incomplete. These facts support host lifecycle interruption over a reported capture fault; they do not prove every network request before the outage was successful. Source code handles SIGTERM/SIGINT by setting the stop event and then publishing stopped. The same terminal state can also be produced by a one-shot invocation, so the stopped state alone does not identify a signal sender. The independent OS timestamps support the shutdown association.

The current readable launch-service scan covers 33 user LaunchAgents, two system LaunchAgents and six LaunchDaemons, with no matching collector/recovery job and no parsing errors. This is a current configuration observation, not a historical inventory. The original collectors remained stopped through subsequent reboots until the separately documented September 16 manual research resumption. Their first-receipt records and late classifications remain intact. No original prospective window is retroactively considered complete.

## Qualified change

Candidate source commit: `0903791` (full identity in `launcher_sources.json`). Frozen launcher worktree: `/Users/gestas/Prototypes/hypervector-v89-collector-recovery-20260916`.

A new research startup guard authenticates an immutable job specification, the frozen collector manifest/source/protocol, a supported public collector entrypoint and the Python executable. It checks the recorded process plus writer-lock ownership. An existing healthy collector is left running; an existing unhealthy or ambiguous process produces an alert. An absent collector can restart only before its fixed end, using its existing collection directory and unchanged collector code.

Each start attempt is recorded before exec. The allowance is at most three starts per hour and at least 60 seconds between attempts, retained across wrapper invocations. A final inspection immediately before exec catches a changed state or elapsed window. This is technical process recovery, independent of trading returns, drawdown, regime confidence or strategy acceptance. An alert or failed exec remains explicit and retained.

The collector receives a newly constructed environment with no inherited wallet/API credentials, proxies or user Python site. The existing collector lock and manifest checks remain the final protection against concurrent starts. No trading client, order, position or financial-process lifecycle is controlled by this launcher.

## Validation completed

- **145 tests passed**, including actual harmless Python exec, safe inspection default, expired final inspection, failed exec receipts, malformed/changed source and job pins, PID reuse, conflicting locks, corrupt health, clock reversal, persistent retry allowance and concurrent wrapper exclusion.
- Changed health/recovery modules: **323/323 statements and 154/154 branches covered**. The CLI has explicit behavioral tests and a real subprocess rehearsal; the module coverage figure does not claim coverage of the whole application.
- A real temporary macOS launchd job ran the harmless fixture once, invoked the wrapper again, and produced a retained rate-limit result. Its test interval was two seconds; proposed production definitions use 60 seconds. The temporary job was then removed and absence verified. **No host reboot was performed.**
- All three actual collectors returned `already_running` through the new guard. Their process births and the five user financial-process births were identical before and after qualification.
- Three exact LaunchAgent plist artifacts pass `plutil -lint`. Their RunAtLoad and interval behavior are explicit; unconditional KeepAlive is disabled. **These production definitions have not been installed or loaded.**
- The first real-exec test used an out-of-range synthetic PID which macOS rejected. The corrected test uses a confirmed exited harmless process. Initial failures, corrected tests, source copies and the temporary-job cleanup receipts are retained.

## Recommendation and alternatives

**Recommendation / why now:** enable the three prepared research-only recovery jobs after explicit approval. The 49-hour unnoticed interruption materially reduced the usable prospective evidence and delayed strategy validation.

**Applicable regime:** all market regimes; this change concerns public-data process continuity.

| Alternative | Benefit | Limitation |
| --- | --- | --- |
| Current manual resumption and finite passive watches | No persistent OS configuration change | Requires an active observer/session and a person or agent to recover after reboot |
| Prepared user LaunchAgents | Rechecks at login and restarts absent pinned collectors while a study remains open | Cannot collect while the host is off, asleep or before login; needs explicit deployment approval |
| Always-on external collection host | Could reduce dependence on this Mac's lifecycle | Separate infrastructure, cost, source/environment qualification and approval required; not proposed in this change |

**Proposed live trading change:** none. Proposed deployment change is limited to the three public-research startup jobs.

**Expected upside:** shorter unattended research collection gaps after login or process exit, and retained failed-start evidence. No profitability improvement or uninterrupted uptime is established.

**Risks and limitations:** a stale but still-running collector is not automatically killed; it needs diagnosis. After exec, launchd owns the collector itself, so this wrapper is not an independent continuous heartbeat monitor. Existing finite health watches remain separately necessary. OS throttling, sleep, login delays, source/interpreter changes, corrupt state or exhausted retries can still delay collection. Dependency or OS changes require requalification. These checks do not defend against a malicious actor modifying approved code between authentication and exec. A host restart was not simulated on the user's working machine. No historic lateness or fixed study deadline is changed.

**Validation still required:** installation/readback and loaded-job inspection after approval, plus verification of the first natural real-collector recovery. Existing collectors should remain untouched at activation. Keep the original September 22/23 and later October 7 seals.

**Success / falsifiers:** a healthy existing collector remains single-owned; only an absent pinned public collector starts; actual receipts preserve original observations; all starts occur before the fixed end and obey the persistent allowance. A duplicate writer, changed source accepted, inherited secret, post-window start, missing failure receipt, affected financial process or loss of first-receipt provenance rejects this implementation.

## Exact deployment artifacts and rollback

Artifacts are under `data/logs/research/bidirectional_cohort/v89_collector_shutdown_recovery_20260916_v1/launchagents/`:

- `local.hypervector.research.recovery.pair.20260916.plist`: original SNDK/Brent capture, fixed end September 22 04:00 UTC.
- `local.hypervector.research.recovery.seven.20260916.plist`: original seven-asset capture, fixed end September 23 00:00 UTC.
- `local.hypervector.research.recovery.followup_pair.20260916.plist`: separate later pair capture, fixed end October 7 04:00 UTC.

The `jobs/` files pin each collector and the `launcher_sources.json` receipt identifies the frozen wrapper and preserved copies. After approval, reauthenticate those files and the Python executable, require no conflicting job/file, exclusively install these exact plist bytes in `~/Library/LaunchAgents/`, and bootstrap each into the user's GUI domain. Verify loaded program arguments and the first same-process `already_running` receipt. Do not start, stop or restart a financial process.

Rollback consists of removing only these newly added autostart definitions and unloading only their exact labels. **Unloading a recovery job that currently owns a research collector also stops that collector**; inspect ownership and preserve its records before choosing that step. Original collector worktrees, data, study protocols, financial configuration and financial processes are unchanged. No earlier plist needs replacing; if an unexpected existing one appears, stop for reconciliation.

**Approval requested:** enabling these three persistent research-only recovery jobs. The user goal file explicitly requires human approval before changing deployment configuration. Preparation and qualification are complete; activation awaits that specific approval.

**Next highest-value investigation:** inspect the next retained native entry/exit/protection or diagnostic event against its source, costs and regime context while awaiting deployment approval. Do not repeat completed leverage or original gap-recovery studies without contradictory evidence.
