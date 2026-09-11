# V89 entry latency: measured transport candidate and stopped-run boundary

Prepared September 11, 2026 UTC. This is a report-only recommendation, with
no source installation, restart, financial instruction or automatic promotion.

**Recommendation:** approve source-only installation of candidate
`f59d54cf40cf80111b1691a86395326693b0c103`, which gives the existing serial public
candle fetcher one command-owned HTTP session. Keep activation separate from
installation while the operator-stop intent and open-position recovery remain
unresolved. Technical confidence is high for the measured timing and lifecycle
behavior; confidence in future latency savings is medium. No profit benefit
has been established.

**Current operating state:** run `bidirectional-live-1789122347122` ended with
seven `STOPPED / operator_stop` records at 15:37:14 UTC (11:37 Eastern). All five
original CLI/supervisor/backend/checkpoint/TUI processes were absent at the
15:54:41 verification, and all seven terminal ledger records were unchanged.
No runtime process was signaled during this investigation. The records identify
the shutdown category, not who initiated it. The earlier question about whether
that stop was intentional has no recorded answer at this review boundary.

Unsigned native reads completed at 15:52:43 UTC (11:52 Eastern) found core
flat/order-free and exactly one XYZ position: `xyz:SNDK`, size `-0.306`, entry
1629.2, 10x isolated. Its exact stop OID `542326955281` was open: buy, full size
0.306, reduce-only, Stop Market, trigger 1669.9. The marked unrealized result
was -$5.0796. These sequential observations do not prove uninterrupted protection
or future stop execution. Strategy-managed exits and new entries are not running.
The final checkpoint's two closes total -$27.994028 net; that excludes this open
lifecycle. Its `stale_running_heartbeat_after_asset_stop` diagnostic must not be
rendered or described as a running backend.

The Info-only roster producer PID 44983 and prospective collectors 75062/15448
retain their original process births. Actual-account monitoring is disclosed;
neither prospective hypothetical outcome study was evaluated. Their September
22 04:00 UTC and September 23 00:00 UTC outcome seals remain in force.

**Why now / observed opportunity:** the slowest actual entry used 27.706 seconds
of its configured 30-second SDK-dispatch allowance. The study identifies public
candle collection as a removable contribution without changing decision rules,
deadlines, protective order sequencing or request concurrency.

**Evidence reviewed:** three authenticated retained ledger prefixes from the
frozen live-acceptance packet; exact routed entry, intent, SDK dispatch,
acknowledgement, native fill and stop identities; one cold and two warm polls
through the configured seven-asset poller; four counterbalanced transport pairs;
offline regression and failure-path tests; current native position/order reads.
The study directory is
`data/logs/research/bidirectional_cohort/v89_entry_latency_20260911_v1`.
Its `evidence_manifest.json` enumerates the retained operators, inputs, results,
failed attempts, source copies and checksums.

**Timing attribution:** all figures below are milliseconds, with local event
timestamps truncated consistently to integer milliseconds. The last stage mixes
local and venue clocks and includes unmeasured clock skew.

| Measured stage | BTC long 13:00 | SNDK long 13:00 | SNDK short 14:00 |
| --- | ---: | ---: | ---: |
| Decision to cycle start | 4,780 | 4,780 | 2,783 |
| Initial reconciliation | 5,034 | 5,034 | 7,299 |
| Provider poll through market emission | 6,882 | 6,882 | 9,035 |
| Route wait, including preceding entry workflow | 2 | 10,145 | 1 |
| Entry preparation | 1,934 | 863 | 2,377 |
| Intent to SDK dispatch | 1 | 2 | 0 |
| SDK dispatch to first native fill, mixed clocks | 1,086 | 895 | 1,482 |
| Total decision to native fill | 19,719 | 28,601 | 22,977 |
| Decision to SDK dispatch | 18,633 | 27,706 | 21,495 |
| Remaining SDK-dispatch allowance | 11,367 | 2,294 | 8,505 |

All three SDK dispatches met the configured deadline. The 30-second control is
checked at SDK dispatch; it is not a venue-arrival or fill guarantee. The
13:00 SNDK route began one integer millisecond after BTC reached its protected
OPEN state. That preceding BTC workflow consumed about 10.142 seconds. The
proposal preserves that sequence. Routing-summary emission occurs after the
execution loop and is not an order-dispatch timestamp. The poll interval already
compensates for elapsed cycle time rather than adding a fixed 15-second sleep.

**Isolated profile and transport experiment:** the cold configured poll took
28.847 seconds, including 17.164 seconds of fetching. Two warm polls took
10.421/10.680 seconds, including 6.709/6.912 seconds of fetching. Their connection
validation profiler entries consumed 3.336/3.441 seconds. These instrumented
polls used different cutoffs from the actual entries; their durations are not
substitutes for the actual-entry stages above. The cold API response contained
roughly 5,000 rows per asset, not a complete requested 14-day history.

The follow-up held the seven-symbol order, parser, retry contract and completed
historical cutoff constant. It alternated baseline/reuse order AB, BA, AB, BA.
Each arm made serial unsigned public candle requests. All 28 paired frames
matched exactly, including values and dtypes. No orders or hypothetical outcome
returns were generated by this transport comparison.

| Pair | Request order | Seven-asset fetch seconds saved |
| --- | --- | ---: |
| 0 | Baseline, reuse | 2.759298 |
| 1 | Reuse, baseline | 3.337875 |
| 2 | Baseline, reuse | 3.072095 |
| 3 | Reuse, baseline | 2.981887 |

Median saving was **3.026991 seconds**, or **44.9513%** of fetch time. Four pairs
in one session do not establish a network latency distribution or tail bound.
The general pooling mechanism and context-manager closure are documented by
[Requests](https://requests.readthedocs.io/en/latest/user/advanced/#session-objects);
the measured benefit comes from this local experiment, not that documentation.

**Applicable market regime:** transport ownership is independent of the strategy
regime. Measured benefit depends on venue connection behavior, network conditions
and workload. No regime filter, model score, strategy selection or return forecast
is introduced.

**Alternatives considered:**

| Option | Expected benefit | Trade-off / disposition |
| --- | --- | --- |
| Keep current source | No change or migration | Retains measured repeated connection overhead; viable control |
| Reuse one public session | Observed median 3.03-second fetch reduction | Small lifecycle change; selected candidate, future savings unproven |
| Parallelize candle or entry operations | Unmeasured possible reduction | Larger concurrency, ordering and protection surface; deferred |

**Proposed live change:** two paths only, based on main
`c29c23d42078b9de14aa91ce81c049f54ef8432a`:

| Path | Candidate SHA-256 |
| --- | --- |
| `scripts/multi_asset_bidirectional_live.py` | `59daefa9bc2a9884f5f18fa0e4314669977299d5b563d24b680386f75233b7a7` |
| `tests/test_cohort_candle_session.py` | `f8fd1cac39b51085f7977e92a56e675c477d45d55b9d60159c4968f721ef5720` |

The existing authority, credential, accounting-epoch and STOP checks precede
session construction. The collector receives the existing fetch function with
that session bound. A context manager closes it on normal return, collector
startup failure and runtime failure. Strategy/profile/risk settings, public
request payloads, timeout/retries, native execution clients and TUI are unchanged.
The isolated worktree is
`/Users/gestas/Prototypes/hypervector-v89-candle-session-20260911` and is clean.

**Expected upside:** less serial public-data overhead and potentially more entry
deadline headroom. The measured 3.03-second median is a bounded observation,
not a promised saving on every cycle. There is no causal evidence that it would
have improved these fills, increased win rate or reversed the two losses.

**Main risks and failure modes:** persistent connection resets or idle closure;
session state persisting between reads; network conditions eliminating the
measured benefit; startup or runtime exceptions leaking resources; accidental
change to request values or authority checks. Existing public-read retries remain
unchanged. Same-process account/order ownership and protected-entry sequencing
remain untouched. Three entries and two completed trades cannot establish
strategy expectancy.

**Validation completed:** 40 offline evidence/deadline diagnostics passed; the
current analyzer reproduced all three reports exactly excluding its creation
timestamp. Analyzer statement coverage is 98.18%, branch coverage 90%; this does
not describe unrelated experiment operators. The candidate's 62 focused tests
passed, followed by five passes after a test-only structure refactor. The changed
`run_live` function has 100% statement/branch coverage; the whole script has
89.63% statement coverage. Ruff check/format passed. Both candidate files meet
500-line/50-line-function limits. Tests prohibit execution-client construction
and use mocked network boundaries.

The first broader test attempts failed because the isolated worktree lacked a
frozen profile artifact, pinned provider source files and a transitive storage
module. Each failed log is retained. Exact existing files were copied with
authenticated hashes; no dependency update or test skip resolved the failures.
The test-first failures before session wiring are retained separately.

The prior script and both candidate files are preserved in `before_installation/`
and `candidate_sources/`; `candidate.patch` is the exact two-path diff. An actual
reverse application in the isolated worktree restored the prior script and
removed the new test, then forward application restored the clean candidate.
All before/after hashes matched. Main remains at its prior source bytes.

**Validation still required:** explicit source-installation decision; same-path
hash checks and focused tests after installation; a separately authorized live
activation boundary with fresh account/order reconciliation and proved adoption
of any remaining open lifecycle. Then observe native protection, request failures
and dispatch ages from the new run. Source tests do not prove live activation,
future latency, original Terminal rendering or economic improvement.

**Success metrics:** unchanged input frames and request contract; context closure
on tested success/failure paths; exact approved source scope; no duplicate or
unprotected financial mutation; observed fetch latency improvement under recorded
conditions; unchanged 30-second dispatch enforcement. Return, drawdown and trade
count remain outcomes rather than new implicit rejection gates.

**Failure / rollback triggers:** source/hash mismatch, request/data mismatch,
resource leak, changed authority boundary, new transport failures attributable to
reuse or a material latency regression. Before activation, restore the preserved
prior script (SHA `08b9e9ebce9c1af21d92f3a9dd1365128327b2ead9e02567ba851f249d6888fb`)
and archive/remove only the new test, after checking for intervening edits. After
activation, restoring files alone does not replace loaded code; use an authorized
maintenance boundary that preserves the native position and protection. Do not
automatically stop/restart an open lifecycle merely to apply this optional change.

**Confidence / falsifier:** high for exact ledger joins, measured paired equality
and tested ownership, conditional on retained source hashes. Any identity mismatch,
different request values, failed resource closure or unaccounted clock ordering
would reopen that conclusion. Medium for future operational improvement; larger
or different-condition comparisons could eliminate the observed benefit. Economic
benefit remains unverified.

**Explicit approval requested:** source-only installation of the exact two-path
candidate, with no automatic restart, order action or profile change. The governing
[user mandate](/Users/gestas/.codex/attachments/0c1c6f2b-0568-4de5-a63c-f7f1e826d3a4/pasted-text-1.txt)
requires explicit approval before changing execution behavior or deployment
configuration. No SDK deadline violation was observed, so this optional measured
optimization is presented for that decision rather than treated as an emergency
repair. The separate stop-intent clarification remains pending.

**Highest-value next investigation:** prove, offline with exact retained SNDK
state and mocked venue boundaries, that a restart can adopt its position, native
stop and persisted execution plan without duplicate mutation, or identify the
specific blocker. This supports a concrete recovery decision while the optional
transport candidate awaits review. Keep both prospective outcome seals intact.
