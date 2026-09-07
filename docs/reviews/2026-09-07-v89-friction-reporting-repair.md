# V89 hourly friction reporting repair

**Recommendation:** Retain the installed reporting correction. SPCX, SNDK and
BRENTOIL now have exact modeled-cost mappings in the checkpoint consumed by
the running TUI. The live strategy, configuration and trading process were
not restarted or modified by this maintenance.

**Why now:** The live checkpoint showed seven runtime contracts but only four
modeled contracts. Its three hourly additions were labeled
`unsupported_contract`, leaving their model fees, slippage and exit mechanics
unavailable in the research inspector.

**Evidence reviewed:** Frozen V89 history replay v1, its pinned source hash,
the actual live configuration event, before/after checkpoints, regression
tests, the installed Rust viewer and current process identities. Evidence is
under `data/logs/research/bidirectional_cohort/` in the original checkout.
The append-only record
`docs/research-journal/v89-hourly-friction-reporting-20260907-v1.json` pins
the immutable files. Runtime logs that continue changing are not pinned.

**Observed problem:** `modeled_contract()` omitted the exact new strategy and
asset pairs. Their runtime execution descriptions were present. This was
missing reporting coverage, not evidence that those routes were disarmed.

**Applicable market regime:** Reporting integrity applies across regimes.
Cost values remain assumptions from the exploratory July 21–September 6
replay; they are not a claim about current fee tiers or a stable live edge.

**Alternatives considered:**

| Option | Benefit | Limitation | Decision |
| --- | --- | --- | --- |
| Leave unavailable | Does not invent data | Known research evidence remains hidden | Replaced |
| Reuse older HIP-3 mappings | Small edit | Wrong recipe, costs and holding period | Rejected |
| Map exact V89 pairs to frozen nominal replay | Source-backed model/observation comparison | Nominal costs may differ from live costs | Installed |

**Proposed live change / final implementation:** Reporting-only installation
`7e09bbe` on original main, equivalent to isolated commit `e473c1c`.
Only two reporting modules and their tests changed. The prior main commit
`aaae79b` is preserved by `backup/pre-v89-friction-reporting-20260907` and
exact copies of the old reporting sources. The separate SPCX numerical fix
in `9574435` remains isolated; it was not included in this installation.

| Exact route | Modeled fee / entry slippage | Modeled stop | Hold / target |
| --- | --- | --- | --- |
| SPCX hourly band20 reentry | 0.90 / 2.50 bps | Structural, clamped 20–250 bps | 86,400 seconds / none |
| SNDK hourly Donchian 20/10 | 0.90 / 2.50 bps | Structural, clamped 20–250 bps | 86,400 seconds / none |
| BRENTOIL hourly Donchian 8/4 | 0.90 / 2.50 bps | Structural, clamped 20–250 bps | 86,400 seconds / none |

These mappings apply only to the researched strategy/asset pairs. Unknown
symbols remain unsupported. The new evidence source explicitly names the
nominal scenario and preserves adverse and full-fee scenarios alongside it.
Observed costs remain unavailable until owned fills exist; measured values
and signed deltas retain their separate fields. The four older comparisons
were byte-for-byte equivalent in the before/after projection.

The old report worker 8439 was retired using SIGINT after its identity was
verified and its output backed up. Replacement reporter 11730 is owned by
controller 11727, which watches the original backend and supervisor process
lifetimes. It controls only its own reporting child and stops that child when
the original owners end. Backend 4965, launcher 4954 and TUI 8440 retained
their original start times and run `bidirectional-live-1788809099824`.
The replacement uses the same run, configuration, output path, venue readers
and 120-second research synchronization settings as the old worker.

**Expected upside:** Complete model visibility and usable model-versus-fill
cost deltas for the three additions. No demonstrated profit increase is
attributed to a reporting repair.

**Main risks and failure modes:** Nominal costs can differ from actual costs;
the display continues labeling them as model values. A mismatch in stop
bounds remains a reported contract mismatch. A later configuration change
or new asset requires its own evidence mapping. An already-running launcher
cannot adopt a replacement `Popen` object: it retains the retired reporter
PID and may report that worker's SIGINT exit when the user eventually closes
the original TUI. The retired process is awaiting its parent's reap. This
known shutdown-message limitation does not restart or stop trading now.
It remains a lifecycle follow-up before declaring the whole system complete.

**Validation completed:** Six missing-mapping assertions failed before the
implementation. The final focused suite passed 32 tests with 100% statement
coverage of the modified recent-contract module. The intermediate test used
`maximum_stop_bps` as a mismatch label; the established API uses `stop_bounds`.
That test-only expectation was corrected, with both logs retained.
Three isolated ownership tests passed: missing owner prevents launch, reporter
failure does not stop its owner or cause automatic restart, and owner exit
cleans up the reporter.

The installed Rust binary passed 129 offline terminal captures across
100x28, 120x36 and 190x52. Separate assertions checked all three new routes
at each size. A subsequent 19-capture attachment used the actual current
live ledger and checkpoint, with no backend launcher or operator inbox.
It displayed the repaired fees, slippage and aligned contracts for all three.
The 20:19:35 UTC checkpoint reported seven aligned mappings, zero unsupported
contracts, complete coverage and a consistent running lifecycle. No fills or
submissions were recorded in that snapshot. Later runtime events can update
those observations.

**Validation still required:** Actual fill costs and lifecycle reconciliation;
joint seven-asset portfolio economics; prospective minute-source parity;
clean report-worker replacement ownership in a future launcher lifecycle.
The existing 48-day selection and top-winner concentration limitations remain.

**Success metrics:** Seven supported current mappings, no invented observed
costs, unchanged older projections, fresh real checkpoint data, and no
change to the backend run or live configuration hash.

**Failure / rollback triggers:** New parser failures, missing researched pairs,
wrong model costs, hidden contract mismatches or stale reporting reopen this
repair. Restore only the saved reporting version and refresh its report-only
worker if rollback is needed. The prior sources and checkpoint are preserved
in `v89_reporting_worker_refresh_20260907_v1/`; trading process ownership and
its configuration are outside that rollback.

**Confidence level:** High for the reproduced omission, tests, source matching
and rendered data; medium for the replacement worker's longer-running
ownership behavior, given the documented original-launcher limitation.
No live performance confidence is inferred. A new data mismatch or ownership
failure would reduce these assessments.

**Explicit approval requested:** None. Reporting repair and verification fall
within the user's supplied corrective authorization. This work did not submit
orders, activate execution or change a live trading decision.

**Highest-value next investigation:** Reconcile the exact seven-asset shared
portfolio economics, including concurrent margin use and loss interaction,
on the available common historical window. Keep the separate deployment and
prospective-source gaps explicit; do not use economic results as new implicit
execution gates. The full thread goal remains active.
