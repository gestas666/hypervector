# V89 stale TUI status: display-only deployment proposal

Recommendation: approve the detached monitor update built from source
`d10b05bf69baf88301726db1c53dc3c10b485299`. High confidence in the tested display behavior; activation and
human acceptance of the visible monitor remain pending. The release executable
is preserved in the evidence bundle's `bin/tui-regime-detector`.

Why now: the September 8 shutdown left the reporter checkpoint at 14:04:48 UTC.
All seven asset ledgers ended with STOPPED / operator_stop at 14:05:33 UTC.
The detached monitor's header correctly said BACKEND STALE, while its archive
panel still said RUNNING CONSISTENT and its footer said IMPORT OK (79s).
Those footer and lifecycle values described the old checkpoint.

Evidence reviewed: the frozen incident, timed unsigned core and XYZ account
reads, final asset records, unchanged main source, bounded OS logs, the reader
and renderer contracts, regression tests, and baseline/candidate incident
renders. Venue reads at 14:11:02–03 UTC found no positions or open orders.
The stop requester remains unidentified. The current signal latch records only
a boolean, and a stop file is absent; a bounded Terminal/launchd query returned
no matching events. This does not establish whether a person, terminal closure
or another process sent a signal.

Observed problem: publication freshness and backend health shared a stale flag.
Using that flag alone to relabel the importer failed a control test: a fresh
reporter can describe an unhealthy backend. The candidate adds a local
publication-stale field to the Rust projection while retaining the existing
backend-health flag and its behavior.

Applicable market regime: every regime; this is an observation contract.

Proposed live change: replace the detached monitor using the preserved release
binary. Its four changed production Rust files are enumerated, with prior and
candidate hashes, in `source_and_build.json`; `display_only.patch` contains the
source change. Publication timeout or a retained checkpoint after read failure
shows IMPORT STALE // WAS <recorded state>. The absolute last-success time and
recorded error/count remain visible; the frozen relative age is omitted.
The analysis row says CHECKPOINT STALE and AT SNAPSHOT <lifecycle>. A freshly
published backend problem says SOURCE ISSUE and keeps the current import state.
The patch requires no Python checkpoint-schema migration or backend restart.

Expected upside: clearer operational status when reporting stops or fails.
No increase in returns, trade count or win probability has been demonstrated.

Alternatives considered:

| Option | Benefit | Limitation |
| --- | --- | --- |
| Keep current monitor | No deployment transition | Retains contradictory-looking cached status |
| Relabel using the existing stale flag | Smaller patch | Failed the fresh-reporter / unhealthy-backend control |
| Separate publication freshness | Preserves both status meanings | Requires a monitor update and visible acceptance |

Validation completed: 521 Rust tests pass across 70 targets, with 23 existing
runtime-dependent checks ignored. Nine added tests cover all import states,
fresh recovery, the exact existing 90-second publication boundary, missing and
malformed refreshes, separate backend health, and pane preservation. Formatting
and Clippy with warnings denied pass. The initial full run exposed missing
historical V86 fixture files in the isolated checkout; copying and verifying
those existing archived files allowed the unchanged full suite to pass.

A frozen 135,320,440-byte current-run ledger is anchored to the verified reporter
prefix plus its 14 terminal cohort records. The normal read-only reader rendered
all nine views at 100x28, 120x36 and 160x45. Final optimized-release replay
changed only the intended status rows across all 27 views. Every other rendered
row is byte-identical to baseline. The wide portfolio retains all seven assets,
five closed trades and −$21.12. All 5,072 source-archive members match committed
Git blob identities. The release binary is 10,160,480 bytes, SHA-256
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.

Validation still required: approval and visible acceptance after opening the
candidate detached monitor. Automated headless rendering does not establish
that the operator's currently open window has been updated. The shutdown's
origin remains unresolved, and no restart-reliability correction is claimed.
The Rust coverage instrumentation tool is unavailable; no measured line or
branch coverage percentage is claimed.

Success metrics: cached status is visibly historical, a fresh reporter remains
independent of backend health, the frozen age is absent on retained evidence,
and all existing panes and recorded financial values remain available.

Main risks and failure modes: the file reader retains its existing clock and
mtime semantics. The projection cannot identify a stopped process from the
old checkpoint alone. A stale research-roster feed remains a separate source.
At compact widths, long recorded errors can still clip within the footer;
existing pane geometry is preserved. This candidate does not establish a
profitable trading strategy.

Failure / rollback triggers: missing or contradictory status qualifiers,
unexpected source or binary hashes, changed financial values, lost panes or
changed operator-control eligibility invalidate acceptance. The preserved
`bin/prior_tui-regime-detector` supports reopening the prior detached monitor.
No ledger restoration or trading-process lifecycle operation is part of this
rollback.

Confidence level: high for the tested display behavior. Different source/data
hashes, a failed source-bound replay, or a fresh-reporter control regression
would update that confidence. Confidence in shutdown attribution is low.

Explicit approval requested: approve this exact TUI-only update. The goal
attachment's Human control clause requires explicit approval before changing
live deployment configuration. The entry-deadline and mapped-reader proposals
remain separate, unanswered proposals.

Next economic investigation: reconcile the latest SNDK short and SPCX long
protective-stop exits against native wire thresholds, fills, fees/funding and
bounded public execution evidence. Keep the sealed prospective outcomes closed.

Evidence bundle:
`data/logs/research/bidirectional_cohort/v89_stale_checkpoint_presentation_20260908_v1/`.
