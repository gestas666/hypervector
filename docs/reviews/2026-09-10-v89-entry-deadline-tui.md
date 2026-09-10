# Entry deadline evidence: TUI candidate qualified offline

Candidate `b73b112282d5e7ab7ec04d431f87554739a98f8a` adds the missing
entry-check evidence to the existing Setups inspector. It builds on the
[602-test Python technical candidate](2026-09-10-v89-technical-release-integration.md).
The Python implementation, scripts and profiles are identical to that qualified
base. The new change covers seven Rust source files, five test/fixture files
and its qualification plan. It is retained in an isolated checkout and has
not been deployed. Confidence is high for the measured offline behavior;
fresh live presentation and profitability are not established.

The reproduced omission was specific: Python publishes
`audit.routing.entry_age_diagnostics`, but the existing Rust routing wire type
discarded it. The inspector therefore could not show whether the recorded
check occurred at admission, the adapter or the SDK boundary. This correction
is applicable across market regimes and does not choose a strategy or asset.

The inspector now projects the exact provider-symbol's run aggregate, including
its declared limit, entry actions, stale withholding, named check counts,
maximum recorded age and minimum headroom. It labels the evidence report-only
and states that an SDK check precedes signing and network delivery. It makes
no venue-arrival or fill claim. Missing older evidence stays unavailable;
legacy enforcement wording cannot become SDK proof. Counts, ages, headroom,
stage coverage and current status must reconcile. Exact `xyz:SNDK` evidence
cannot be borrowed by `SNDK` or a different provider.

Both the checkout and retained archive pass **534 Rust tests**, with the same
23 existing runtime-dependent tests ignored and identical test identities.
Clippy with warnings denied and formatting checks pass. All **5,153 Git blobs**
match before and after archived testing. Ten actual Python-produced synthetic
2030 cases verify SDK, adapter, admission, legacy, exact/late deadline,
unrecorded-clock, stale-withholding, no-action and mixed-stage inputs. The
compact checked-in JSON equals the retained producer output when parsed;
four producer files are also bound to the frozen archive.

Three accepted configured, disarmed inspector buffers cover 100x28, 120x36 and
190x52. The minimum-size buffer retains the existing route plan and displays
the 60-second configured limit consistently with the 60,000-ms audit limit,
59,000-ms recorded age and 1,000-ms headroom. Scrolling reaches the final old
indicator. Existing nine-view and historical screen tests remain in the suite.
These are constructed render fixtures, not a current-market run or human
visual sign-off. Statement/branch coverage was not measured in this Rust run.

The first full run failed because the isolated checkout lacked the existing
September 4 V86 observer fixture. The dated ledger and checkpoint were copied,
hashed and then exercised by the unchanged screen test. They precede the
prospective seals. Two new negative tests also reproduced contradictory age
and adapter-stage claims before their validation corrections. Those failures
remain retained. Earlier unconfigured or mismatched render fixtures are
superseded by `accepted_inspector_*`; they are not acceptance captures.

Evidence is under
`data/logs/research/bidirectional_cohort/v89_entry_deadline_tui_20260910_v1/`.
Use `source.tar.gz`, `candidate.json`, `complete_technical_patch.diff`,
`archive_acceptance.json`, `archive_tests.log`, `full_rust_tests_v4.log`,
`clippy_v2.log`, `fmt_v2.log` and `accepted_inspector_captures.json`.
The unchanged local V86 test also needs the two paths retained in
`historical_fixture.tar.gz`, extracted alongside the source archive. Cargo
testing used offline, locked, release mode and the isolated checkout's cache.
The retained candidate binary hash is
`604307380b4b047453e0492a349760e737c58da3a917f37305feb39072af3ea3`;
the installed binary remains
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.

| Alternative | Benefit | Limitation or trade-off |
| --- | --- | --- |
| Include this correction in the technical deployment proposal | Makes the backend timing evidence visible in the existing operator workflow | Requires matching-source deployment and fresh presentation acceptance |
| Read the JSON audit manually | Requires no TUI deployment | Leaves the diagnosed cockpit omission |
| Leave the installed version unchanged | Avoids a transition now | Continues to omit this evidence |

Recommendation: retain this complete candidate for the combined deployment
review. Expected upside is correct operator evidence, not an established
increase in trade frequency, win rate or return. Malformed producer data or
future schema drift could make checkpoint projection fail; a fresh supported
checkpoint that fails or displays another route's evidence falsifies this
acceptance. Quantified coverage and supervised current-run acceptance remain
to be completed before claiming full technical readiness.

Any live transition still needs a concrete selected scope, current source and
profile checks, ownership/protection reconciliation, retained prestart backup
and explicit approval under Human control. Then verify the new checkpoint and
all operator views during supervised startup. The report-only field introduces
no new performance gate. The original 48-case economic matrix remains active;
the two prospective outcome seals are unchanged.

A TUI-only display rollback can restore the retained prior binary, losing this
new display while preserving backend data. For the combined backend package,
retain corrected `sol_order_restart.py` once new unsent-entry markers exist;
do not restore old ledgers over subsequent history. A source/profile mismatch,
lost protection, duplicate dispatch or inconsistent fresh reporting prevents
acceptance of that live transition. No new deployment approval is requested
at this qualification step, and this record supplies no execution authority.
