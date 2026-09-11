# V89 installed HIP-3 funding telemetry correction

Reviewed September 11, 2026 UTC. Technical hypothesis accepted within the
observed scope; broader research remains active. This review has no order or
strategy authority.

The missing funding column was a producer defect: the existing TUI already
accepted `venue.funding_rate_hourly`, but the Info-only roster observer did not
supply it. The correction is installed at
`40154844348faf50dab7d905aa4d12defbad86bf`, matching the nine-path isolated
candidate `caa6904a0e5968552beafea876fd7bd5549c37c3`.
It adds one unsigned `metaAndAssetCtxs` request per poll for the exact `xyz`
namespace and binds funding to the position-aligned metadata identity.

High confidence applies to the tested parser, source wiring and captured
display values. A wrong symbol, sign, unit, stale-current label, missing error
state or evidence mismatch would falsify the affected conclusion. This repair
does not establish a trading edge or expected return.

## Authority and preserved boundaries

The mandate expressly preapproves evidenced corrective technical fixes. This
change repairs report-only source data and replaces its independently owned
Info-only observer with the same command arguments, output and 120-second
poll delay. It changes no strategy, asset universe, route, leverage, sizing,
risk setting, execution behavior, deployment configuration or supervision
policy. The process receives the public wallet identity and no signing key.

Seven prior files, their modes and hashes were preserved before installation;
the two newly added files are explicitly identified in
`installation_preservation.json`. The profile and TUI executable hashes were
verified unchanged. The existing CLI, supervisor, live backend, main checkpoint
writer, original TUI and both prospective collectors retained their original
process births. Neither prospective hypothetical outcome study was evaluated.

Only observer PID 37491 received SIGTERM. Its stopped publication was retained,
and both the native process probe and `ps` confirmed absence before replacement.
The new observer PID 44983, birth `31776092912024`, started at 15:04:12 UTC.
It uses the original output:
`data/runtime/research/hip3_roster_latest.json`.

## Implementation and validation

The nine-path change contains five implementation files and four test files.
The shared context selector reuses the recorder's strict position alignment;
the existing recorder still requires its funding field. The optional roster
reader distinguishes missing/null funding from an observed zero. Invalid
types, nonfinite values and ambiguous identities propagate to the existing
unavailable publisher. No prior successful funding value is cached.

The installed SDK convenience method lacks a dex argument, so the reader uses
the established unsigned `Info.post` surface with an explicit namespace. This
matches the [venue context endpoint contract](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals).
The venue documents [hourly funding payments](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding).
The implementation retains the existing project's hourly-rate convention and
does not multiply or divide the context value by eight.

Validation evidence:

- Red observer, source/factory and CLI-wiring regressions were retained before
  their corresponding fixes. The final focused installed suite passed **58
  tests in 20.73 seconds**. Its completion log and exact coverage report were
  recovered after interruption; the original shell exit code was not retained.
- Ruff passed on all nine installed paths. File/function limits and return and
  argument annotations passed on those paths and both new validation operators.
- The new funding module has **100% statement and branch coverage**. The shared
  selector, optional decoder, funding payload, observer snapshot and CLI wiring
  also have full measured coverage. Changed business-module statement coverage
  is 88.16% for the mark recorder, 97.56% for the factory and 93.33% for the
  observer. Legacy branches and overall script coverage remain partial; this
  is not a repository-wide coverage claim.
- Two candidate HTTP bodies were retained and authenticated. All **10 funding
  values** matched native metadata/context identities and decimal amounts.
  The candidate's fresh and stopped snapshots matched **18 funding cells** in
  the installed native TUI, including `CURRENT` versus `STALE SNAPSHOT` labels.
- The production observer published available/running snapshots at
  **15:04:44.511908** and **15:07:12.733438 UTC**. Their collection timestamps
  advanced from 15:04:15.860305 to 15:06:44.517915 UTC; both contain all five
  funding values. The poll argument is a delay after collection, so the
  observed publication interval includes collection time.
- A separate isolated native render of the first actual production report
  matched **nine more funding cells** across SPCX, SNDK and Brent depth views.
  Four captured views exited zero with no unsupported terminal sequences. The
  reconstructed Brent image was visually inspected.

The first production snapshot rendered SPCX **-0.105 bp**, SNDK **+0.169 bp**
and Brent **-5.262 bp** in the funding column. These are rounded hourly rates
at that captured time, not realized account funding or future rates.

The renderer uses copied actual checkpoint, ledger and roster bytes, preserves
source timestamps, denies network and file writes, and has detached lifecycle.
Its live-armed label reflects the captured backend state; the renderer has no
execution authority. The original Terminal window remains unverified:
Computer Use rejected access to that app. No alternate GUI-control method was
used to bypass the rejection.

Earlier coverage invocations produced a NumPy collection error and a coverage
source warning. Both logs remain retained. Directory-scoped coverage completed
cleanly without dependency or environment changes. The exact internal cause
of the initial import failure was not established. The bounded candidate
ended with a stopped report and absent PID; its OS exit code was not retained.

## Decision, trade-offs and rollback

| Alternative | Benefit | Limitation | Decision |
| --- | --- | --- | --- |
| Leave the producer unchanged | No additional request | Funding stays unavailable despite venue evidence | Rejected for this defect |
| Shared unsigned context read | Exact source-backed funding with existing display support | One additional request; malformed evidence makes the report unavailable | Installed after validation |
| Change trading settings or infer funding | No demonstrated benefit for this display defect | Changes unrelated behavior or fabricates evidence | Outside this correction |

Success means correctly bound signed/zero rates, explicit missing/error states,
advancing available reports and native display agreement. Future absent or
stale data must remain visibly unavailable; a stopped process or wrong source
value reopens the technical diagnosis. No automatic strategy promotion follows.

Rollback is scoped to this report-only repair. Preserve the installed files
first, verify the original backup hashes, restore the seven prior files and
remove only the two new owned files named in the preservation manifest.
Verify the exact roster process birth before stopping it, wait for confirmed
exit, and run the same Info-only observer arguments. Confirm its publications
and unchanged trading-owner identities. Do not restart the trading backend or
restore unrelated working-tree changes. Rollback would return funding to
explicitly unavailable, not manufacture a substitute.

The observer remains independently launched; durable future supervision needs
a separate concrete deployment design. Two advancing publications establish
bounded operation, not indefinite availability. No new approval is pending
for this completed technical repair.

## Current execution and next investigation

The retained checkpoint generated at **15:08:35.885978 UTC** reports the same
user-started run `bidirectional-live-1789122347122`, healthy and
`running_consistent`, with six fills, two closed losses totaling **-$27.994028**
net and one open SNDK lifecycle. The other six assets are flat. Those closed
results exclude the open lifecycle. This review does not claim a new independent
venue-fill reconciliation; that earlier evidence remains in the
[live acceptance review](2026-09-11-v89-live-acceptance.md).

Two closes are insufficient to attribute losses to a broken strategy.
Economic confidence remains low. The highest-value next investigation is
**entry-latency attribution**: reconstruct the causal decision, acquisition,
routing, SDK dispatch, acknowledgement and fill clocks for the three actual
entries. The slowest observed fill age was 28,601 ms against a configured
30,000-ms limit. Determine which measured stage consumes that budget before
proposing a change; missing stage clocks must remain explicit uncertainty.
This is report-only diagnosis, with no limit relaxation or parameter tuning.

Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_roster_funding_20260911_v1/`.
`funding_acceptance.json` contains the independent native comparisons;
`closing_validation.json` contains the scoped source and runtime checks;
`evidence_manifest.json` freezes the enumerated study files. The active
production log and runtime output are excluded from that immutable manifest;
their captured prefixes/reports are included.
