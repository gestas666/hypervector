# V89 public candle session: fixed 16-pair extension

The independently verified extension found lower seven-asset fetch time with
session reuse in **16/16 pairs**: median paired saving **1.856397 seconds**, or
**44.5684%**. All **112 paired frames** matched exactly, and all **9,408 cells**
across both arms were reconstructed from retained raw HTTP responses. This is
high-confidence evidence for this recorded workload, conditional on the pinned
sources and authenticated files. Future latency benefit has medium confidence;
better fills, trading frequency and profitability remain unverified.

**Recommendation:** retain the existing two-file candle-session candidate
`f59d54cf40cf80111b1691a86395326693b0c103` for its pending source-installation
decision. This supplements the [original review](2026-09-11-v89-entry-latency.md)
without modifying that frozen candidate or installing it. The separate 64-file
heartbeat/lifecycle candidate `1b5eaa90118b868e5084cd750fb0fa96faabbd40` remains
unchanged and uninstalled; this experiment does not silently expand its scope.

**Why now / observed opportunity:** the original evidence identified public
candle overhead and one actual SDK dispatch at 27.706 seconds against its
30-second allowance. All three measured dispatches met that deadline. Four old
transport pairs were too narrow to address repeated sessions and idle periods.
This extension tests those specific technical uncertainties, without interpreting
the two original closed losses as proof of strategy failure.

## Fixed experiment and measured results

The plan was committed at `144f57e` before preparation. Active driver/recorder
source was `64b359e`; the independent verifier was subsequently committed at
`ce60c08e7af750eb6e0ff58da7b4fb062fb50c90`. The one actual process, PID 26600,
started at **05:05:05 UTC** on September 12, finished at **05:17:38 UTC**, and
its original exec session returned exit code 0. Observation did not restart it.

Four blocks each used a fresh candidate Session for four pairs. Arm order was
balanced within each phase and across the 16 pairs. Both arms requested BTC,
ETH, SOL, HYPE, xyz:SPCX, xyz:SNDK and xyz:BRENTOIL serially, using the unchanged
production fetcher, parser, request values, 30-second timeout and retry loop.
The common five-minute 1m window ended at **04:54 UTC**; six rows per symbol
were returned. It remained fixed for every pair. This isolates an incremental
transport workload and does not qualify a complete 14-day cold start.

Every actual HTTP attempt was recorded with payload, context, clocks, response
bytes/checksum/status, or the explicit exception class. Recording persistence
occurred after timed work. Both arms had the same in-memory instrumentation;
its small overhead and the machine's concurrent workload remain limitations.
No signer or exchange client was constructed and credential-presence checks
were false. Requests were restricted to the public candleSnapshot endpoint.

| All 16 pairs | Baseline | Reused session |
| --- | ---: | ---: |
| Median fetch duration, seconds | 4.201949 | 2.340185 |
| Observed nearest-rank 90th percentile, seconds | 4.327583 | 2.723434 |
| Maximum observed duration, seconds | 6.183234 | 2.975518 |

The median paired saving differs from subtracting the two marginal medians.
Individual savings ranged from **1.288837 to 3.848688 seconds**; no slower or
equal candidate pair was discarded. Sample maxima and nearest-rank percentiles
describe these observations and are not population tail bounds.

| Phase, four pairs each | Actual reuse idle range, seconds | Median seconds saved |
| --- | ---: | ---: |
| Fresh session | No preceding request in that session | 1.423204 |
| First configured 15-second pause | 15.027578–23.354221 | 1.843665 |
| Configured 75-second pause | 75.026191–83.634559 | 1.918866 |
| Second configured 15-second pause | 15.024625–23.349366 | 1.993001 |

Actual inactivity includes intervening baseline work and recording, so it is
not labeled as exactly the configured pause. All eight baseline-first and all
eight reuse-first pairs favored reuse; their median paired savings were
1.856397 and 1.875872 seconds respectively. Each candidate session has one
recorded closure after its final response. There are four distinct reused
session identities and 112 distinct baseline call sessions. Session identity
does not directly prove TCP connection reuse.

**Failure evidence:** there were **225 attempts: 224 HTTP 200 responses and one
recovered baseline ConnectionError** in pair 3. The existing retry path handled
it. Its elapsed time and retry delay remain in the primary result; this pair
also has the largest saving. No throttled response or terminal failure occurred
in this run. Separate offline tests exercise connection reset followed by 429
and success, retaining the actual retry sequence and session identity.

The original four pairs had a 3.026991-second median under their larger fetch
workload. They remain a separate experiment. Neither set is subtracted from old
live timestamps as if improved historical fills had actually occurred.

## Validation, decision and operating boundary

**Evidence reviewed:** the fixed plan and dependency/source pins; 225 raw
attempt records; 224 retained arm frames and 112 agreed frames; all 16 pair
reports and contexts; aggregate and terminal records; independent reconstruction;
focused tests; non-mutating patch applicability; and seven new unsigned account
responses. Frozen source, logs and references live under
`data/logs/research/bidirectional_cohort/v89_session_latency_extension_20260912_v1`.

**Validation completed:** 53 offline tests pass. Thirty target the independent
verifier, including 29 synthetic corrupted-evidence cases. Initial controls
found that its draft accepted an extra frame column and an incomplete aggregate;
both gaps were fixed before verification of the public run. The independent
report reproduces byte-for-byte. All 11 archived source/plan files match Git;
seven operator/test files meet 500-line/50-line-function and annotation checks.
Ruff check and format checks pass. No network calls occur in these tests.

Statement/branch coverage is 85/85 and 18/18 for the request recorder; 136/154
and 28/38 for the fixed operator; 127/149 and 56/74 for the independent verifier;
64/70 and 29/36 for timing/session checks. These scoped figures do not claim
complete branch coverage of the entire pipeline. The original candidate's
existing live-entrypoint success/failure/authority tests remain separate evidence.

**Applicable market regime:** this proposal changes HTTP session ownership,
independent of signal regime. Venue/network behavior and fetch size determine
whether the measured reduction persists. No strategy-regime filter is added.

**Alternatives considered:**

| Option | Upside | Cost or uncertainty | Disposition |
| --- | --- | --- | --- |
| Keep installed source | No migration | Retains current public-data overhead | Valid control |
| Existing session candidate | Measured lower serial fetch delay | Idle resets and future network conditions | Retain pending proposal |
| Parallel fetching or order dispatch | Unmeasured possible reduction | New ordering and concurrency behavior | Deferred |
| Repeat the same short benchmark | More highly related timing samples | Does not resolve economic weakness | Lower priority now |

**Proposed live change:** only the two paths and hashes in the original review.
The exact patch applies non-mutatingly to both current main and the pending
heartbeat candidate. This compatibility check is not an integrated deployment
or activation test. It changes no trading rule, asset, risk limit, leverage,
protective-order ordering or TUI behavior.

**Expected upside:** lower public-data delay and potentially more dispatch
headroom. No quantified return, fill-quality or win-rate gain is established.
**Main risks and failure modes:** new connection-reset behavior, session state
persisting between calls, different workloads eliminating savings, resource
leaks, changed payloads, or altered authority checks. One local 12.5-minute run
does not characterize other days, outages, throttling or hours-long session life.

**Validation still required:** explicit installation decision; approved-file
hashes and focused tests after installation; then a separately authorized live
activation boundary with fresh reconciliation and proven adoption of any open
position and stop. Native dispatch/protection behavior and actual installed-TUI
acceptance remain required. Research does not establish full live readiness.

**Success metrics:** unchanged raw inputs and resulting frames; complete error
retention; serial request ownership and closure; measured transport durations;
unchanged execution authority and deadline semantics. Economic results remain
reported outcomes, not new implicit rejection gates.
**Failure / rollback triggers:** source or data mismatch, lifecycle leaks,
authority changes, or measured transport regression attributable to the candidate.
Use the original review's preserved prior script and tested reverse patch;
loaded runtime code requires an authorized maintenance boundary. Do not restart
an open lifecycle solely to apply this optional change.

At **05:32:18 UTC**, seven authenticated unsigned responses showed core flat
and order-free, and the existing **0.306 SNDK short at 1629.2, 10x isolated**,
with **-$1.4076 unrealized**. Its full-size buy reduce-only Stop Market OID
**542326955281** at **1669.9** remained open. Fifteen funding cash rows sum to
**+$0.089007**. The bounded fill query contains the original entry, not a new
fill. Original trading PIDs were absent; the seven terminal rows and installed
profile/binary/ledger hashes were unchanged. Process permissions limit global
absence claims. Sequential reads do not establish uninterrupted protection or
future execution. Strategy-managed exits and new entries remain stopped.

**Confidence / falsifier:** high for the authenticated measurements; request,
frame, timing, source, ownership or reproduction disagreement would invalidate
that finding. Medium for future latency improvement; different-condition
observations can reverse the result. Economic improvement remains unproven.

**Explicit approval requested:** the original two-file source-only installation
decision remains pending under the objective's Human control clause. This
supplement grants no approval, changes neither pending package, and adds no
automatic restart. The separate 64-file installation decision also remains
pending. Both prospective outcome seals remain unopened.

**Single highest-value next investigation:** remove holding-period selection
from the existing SNDK first-hour diagnostic by reconstructing predeclared
fixed-horizon forward paths for all 47 accepted entry identities, including
early-exit trades and both directions. The prior study conditions first-hour
returns on remaining open; it already measured held-bar excursions, so that
descriptive work should not be repeated. Reuse authenticated historical sources,
retain missing/censored horizons explicitly, and test whether the earlier/later
follow-through difference persists. This is an entry-quality diagnostic, not a
fitted exit policy, fresh holdout or live-change authorization.
