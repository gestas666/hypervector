# V95 issue sweep assessment and recovery priorities

Reviewed for the operator on September 29, 2026, America/New_York; current
checkpoint observations were taken after midnight September 30 UTC.

The sweep is a useful defect inventory, but its grouped plan needs tighter
correctness and performance criteria before V96 implementation. Prioritize
exit recovery, protection evidence, bounded monitoring and definitive rejection
handling. The evidence reviewed here does not justify strategy retuning or
claim that V96 will improve returns. This review stages one small generator fix
and documentation corrections; it does not deploy V96.

## Scope and evidence

Input: `data/logs/research/v95_issue_sweep_20260928/v95sweep_plan.md`, its
36 raw findings in `v95sweep_result.json`, the grouped 24-item table and selected
reproductions under `evidence/verify`. The JSON plan equals the Markdown plan.
Baseline HEAD: `32c65f0`; the sweep used `761a2ef`. The intervening commit records
operations notes. The working tree was clean at review start.

High confidence means direct source inspection or a reproduced local result,
not proof of current venue state. Medium confidence identifies an engineering
recommendation whose runtime benefit still needs measurement. External event
dates, current agent authorization and live venue settlement payloads were not
independently queried. Historical dates in the sweep remain source claims.

Fresh read-only observations:

- At 01:55Z, the checkpoint reported all six asset states FLAT,
  `running_consistent`, no faulted assets and the original V95 run ID. This is
  backend-authored evidence, not a fresh unsigned venue clearance for restart.
- Its current-run cohort share was 413,547,050 bytes. A later publication had
  a 20.389-second generated-time-to-mtime gap. An earlier sampled publication
  had about 3.124 seconds. This variability makes a single linear calendar
  forecast unsuitable as the sole deployment trigger.
- `df -h .` reported about 16 GiB available, compared with the sweep's recorded
  24 GiB. No burn rate or deletion authorization is inferred.

## Priority corrections

| Priority | Finding and confidence | Recommendation and acceptance evidence |
| --- | --- | --- |
| P1 | B5 loses a valid exit across sides. High: BL-6 reproduced both startup and in-process catch-up returning no long close despite a later-than-entry long exit. | Retain latest state separately from per-side exit facts. Test both sides, out-of-order batches, exits before entry, provider/symbol isolation, repeated recovery and no duplicate close. |
| P1 | B1 and B3 must be designed together. High: `raise_protective_stop` writes `venue_visible` from position nonzero; the poller returns its final observation even when its predicate never succeeds. | Preserve initial stop as the R basis. Derive current covering stop from exact owned-order reconciliation, including side, quantity and trigger. Missing evidence must remain unknown. Test an accepted replacement absent from the final snapshot. |
| P1 | B7 is a partial performance fix. High on repeated scanning; medium on future latency. Current code recopies, hashes and parses the suffix, then rebuilds audit output. | Measure the entire publish cycle and freshness of underlying observations. Require a bounded fast lifecycle/position/protection projection or a demonstrated supported run-length budget. Do not accept a fast snapshot benchmark alone. |
| P1 | B6 failures affect backend availability. High: three definitive rejection variants faulted; first restart failed, second recovered. | Handle only exact, unambiguous rejections with no fill and no remaining exposure/orders as withheld. Preserve fail-closed behavior for unknown outcomes, mismatched identity and conflicting receipts. Test crash boundaries and first-restart recovery. |
| P1 | BL-9 and external alert delivery determine whether a held book is noticed. Source-backed concern; delivery unverified here. | Persist deduplicated refusal alerts and a hold without a tight relaunch loop. Verify locally with stub processes; external delivery needs operator-provided destinations and an authorized test. |
| P2 | B2 fails a checkpoint during delayed entry evidence. High on the inspected pending-evidence design; not rerun here. | Allow only the precisely identified `entry_unfilled` lifecycle to publish provisional economics. Preserve unknown fee/PnL values and recover exact economics on the next receipt; malformed unrelated fees still fail. |
| P2 | B4 can reduce scheduling delay, but cannot remove serial entry/protection latency. Medium on benefit. | Test the full poll-to-third-submission path with delayed candles, slow stop acknowledgements, overruns and clock changes. Keep the 30-second deadline and protection before the next IOC. |
| P2 | B8 prevents latent config/runtime disagreement. Source-backed, not all cases replayed here. | Reject nonfinite, nonpositive and fractional leverage. Share liquidation validation with the offline checker, test both directions and provider overrides, and document model limits. |
| Conditional | B9 settlement handling lacks real receipt evidence. High on synthetic reconciliation failure; unknown production payload. | Keep fail-closed behavior until a real redacted payload and lifecycle attribution exist. A halt flag alone cannot prove a close or its economics. |

These are implementation priorities, not claims about defect frequency or a
reason to interrupt the current book. They should be revised if production
evidence demonstrates a different impact or if the reproductions cease to hold.

## Changes required to the proposed fixes

1. **Do not confuse a cursor guard with prefix integrity.** Inode, file size
   and a boundary-line hash cannot detect an edit elsewhere in the old prefix.
   The raw LF-6 recommendation to verify a prefix this way weakens the existing
   full-prefix check. Explicitly choose an append-only trust boundary, immutable
   segments or separately scheduled full verification. Test a same-size interior
   mutation as well as append, partial tail, truncation and file replacement.
   Truncation must surface an integrity event; a successful reload must not erase
   the fact that previously published evidence disappeared.

2. **Move hashing outside the database lock with concurrency checks.** Read the
   saved cursor, hash/parse an exact bounded prefix, reacquire the connection and
   compare the saved cursor before committing. Restart the import if another
   importer advanced it. Test concurrent workers, rotation between reads and
   exact event counts. Single-pass hashing alone does not make this atomic.

3. **Do not hide stale evidence behind a larger threshold.** Track observation
   age, checkpoint build duration and publication interval separately. A cadence
   threshold needs a fixed operational upper limit; otherwise a slower publisher
   can continuously redefine itself as healthy. A retrying independent monitor
   must visibly report unavailable/stale evidence until recovery.

4. **Specify poll-boundary arithmetic before coding.** The plan's
   `min(remaining, next 15-min boundary + 0.25 s)` mixes a duration and a timestamp
   unless the latter is converted to a delay. Document the chosen boundary and
   grace, handle the final fraction of a second before grace, avoid duplicate
   polls and preserve the existing interruptible wait. Measure whether the
   proposed grace is sufficient for actual candle availability.

5. **Define failure handling separately from stop telemetry.** Adding
   `replacement_stop_visible` corrects a claim, not the operational policy after
   an accepted but unseen stop modification. Trace subsequent reconciliation,
   ensure it cannot display verified protection, and test it with an open
   position. Do not infer replacement visibility from the legacy boolean.

6. **Separate configuration identity from deployment authority.** An unchanged
   fingerprint does not by itself authorize a restart or prove a flat boundary.
   Same-profile fallback requires the applicable operator authority, fresh
   venue/process evidence and preserved deployment settings. An approval JSON
   must record actual authorization; creating a candidate does not supply it.

7. **Preserve the experiment.** Leave sizing, routes, deadline and frozen ladder
   documents unchanged for this reliability batch. Distinguish expected
   opportunity improvements from measured returns. Maintain the conditional
   settlement work and sparse slippage evidence as separate research tasks.

## Proposed execution order and tradeoffs

| Option | Value | Cost and residual risk | Assessment |
| --- | --- | --- | --- |
| Do nothing | No immediate deployment disturbance | Existing recovery defects and growing monitoring cost remain | Accept only as a short monitored hold while preparing fixes |
| Generator and runbook corrections now | Removes a reproducible import-path omission and contradictory procedures | Does not change installed services or fix backend defects | Implemented locally in this review |
| Focused V96 reliability batch | Repairs lifecycle recovery, trustworthy protection reporting and rejection availability | Requires isolated development, full acceptance and an authorized transition | Recommended, medium confidence until tests and replay pass |
| Larger V96 including bounded fast checkpoint | Addresses recurring run-age degradation instead of only delaying it | More engineering and projection-equivalence testing | Include if end-to-end benchmarks show the smaller patch misses the support window |
| Same-profile flat restart | Temporarily resets current-run scanning cost | Does not repair source defects; startup cost and operational risk remain | Contingency under existing authority, not an automatic calendar action |

Engineering should first convert the scratch repros into hermetic pytest
fixtures with temporary roots and fake adapters. Several scratch scripts embed
absolute paths or write beside themselves; do not run the entire evidence tree
indiscriminately. Fixes belong in a separate checkout and its own environment.

Proposed acceptance targets, subject to measurement: fast projection p95 publish
cost below 10 seconds at 1-, 7-, 14- and 30-day equivalent ledger sizes; no normal
cycle exceeding the intended 30-second publication budget; no lost or duplicate
lifecycle events; explicit unavailable status for stale/malformed inputs. Use
operation-count assertions in CI and repeated wall-clock benchmarks separately
to avoid flaky timing tests. Record peak RSS and disk writes with the timings.

Before deployment, run the full non-network Python suite, Rust tests and
runtime validator in the isolated checkout. Reconcile the final candidate
against frozen V95 parameters, obtain real deployment authority, and preserve
source/config/plist/journal backups. After activation, verify source identity,
fresh observations, first lifecycle recovery and alerts. Rollback must name
both implementation and profile; a profile-only rollback leaves new code active.

Operator inputs still needed for those later actions: alert endpoints, key
rotation completion, the frozen ladder decision and transition timing. None is
needed to review or develop the offline fixes. I do not have verified current
agent-expiry information; validate with an unsigned agent-status query before
using the sweep's October 22 deadline operationally.

## Applied changes and validation

- `scripts/cohort_backend_supervisor.py`: generated `supervise` plists now set
  `PYTHONPATH` to the selected repository's `src`; watch plists stay independent.
  Installed plists and running services were not modified.
- Added three tests: both restart opt-in states and watch import isolation.
  Before the fix: two failures for missing PYTHONPATH, one pass. After the fix:
  155 tests passed across generator, supervisor, health failure, host restart,
  restart persistence and alert debounce suites in 12.47 seconds.
- The report-only runtime validator accepted the unchanged V95 TOML in live
  validation mode; it constructed no live execution client and placed no orders.
- Ruff and `git diff --check` passed. A generated disposable supervisor plist
  passed `plutil -lint`; the three new tests passed again after formatting.
- Updated AGENTS, current HANDOFF and transition/rollback documentation to use
  the existing environment, preserve installed plist settings and explain
  interrupted supervised drains and durable stop semantics.
- Replayed BL-6, VR-1 and VR-2 offline against current source. BL-6 and VR-1
  behaved as described above. VR-2 reproduced contradictory faulted restart
  evidence. Its zero-ID parsing cases are synthetic probes, not known venue
  settlement formats; its unscoped control is not proof of valid recovery.

The full Python and Rust suites were not run for this two-line script change.
V96 source implementation, live venue acceptance, external alerts, credential
rotation and deployment remain outstanding. Backend source, live configuration,
original sweep evidence and frozen approvals were not edited.
