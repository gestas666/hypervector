## September 15 cleanup: storage headroom and bounded journal verification

Installed research-only source commit **f1088d1** replaces whole-artifact reads
with the existing 1 MiB streaming checksum helper. Six regressions failed before
repair; candidate and installed checks each pass **19 tests**. Module statement
coverage is 91.11%, with 100% of statements in both changed functions exercised.
The real 1,689,844,989-byte backup verifies through append and report at about
2.14 MiB peak traced Python allocation; this excludes native allocations/RSS.
The initial coverage-import failure was retained and resolved by file selection.

Two inactive Rust incremental caches were removed only after full backup restore
and all 21,897 file comparisons passed. Observed net headroom gain was **1.54 GiB**
with the **1.57 GiB** archive retained. Headroom remains limited; future Rust
builds can recreate the caches. Compiled binaries, source, trading evidence,
prior versions and all five financial-process birth identities were preserved.

Two prior SNDK journal revisions referenced mutable source paths. New revisions
preserve the original reviewed bytes and all economic findings: **6,992 current
references match**, none changed or missing. Four older source drifts were also
recovered exactly from Git. Original revisions remain intact and correctly show
six changed historical references. No old experiment was rerun or reopened.

Review: `docs/reviews/2026-09-15-v89-build-cache-headroom.md`.
Main journal: `docs/research-journal/v89-build-cache-headroom-20260915-v1.json`.
Revision **af874ec0ff19ed8616de39cdf9bd4f6aefd3a1580227c0efb2dacb0fc50d94b6**:
**42 matching evidence references**, none changed or missing.
Evidence: `data/logs/research/bidirectional_cohort/v89_build_cache_headroom_20260915_v1/`.
Backup: `data/backups/build_cache_cleanup/20260915T233304Z/`.
The source rollback patch passed reverse-check; no financial restart occurred.

**Next:** inspect the first real event or actual terminal receipt from the same
lifecycle observer **PID 17371 / session 27304** and diagnostic observer
**PID 67653 / session 82480**. Both were polled live during this continuation;
empty tool output is not termination. Their deadlines remain near September 16
00:49:45 and 01:09:07 UTC. Save and inspect final cursors before a successor.
Financial process control remains prohibited, prospective seals remain unopened,
and the continuous research goal remains active. This turn made implementation,
validation, storage and evidence-traceability progress; profitability is unproven.

# Current V89 research index

Updated September 12, 2026 UTC. This is research navigation, not a live-state checkpoint.
The mandate permits research, testing and proposals. Its Human control clause
requires explicit approval before live execution-behavior or deployment changes. Both prospective hypothetical outcome seals remain active.
Historical studies remain bounded to their recorded windows.

## Current finding and next action

**Completed SNDK source/exit reconciliation:** the
[review](../reviews/2026-09-12-v89-sndk-source-reconciliation.md) establishes
**-674.5263651827 bps (-6.7453%)** for the selected August 19 hour in all four
price reconstructions. Native raw matches its Parquet normalization exactly.
Native/vendor differences remain in 11 opening and five closing cells, with
maximum differences **2.5181/1.2793 bps**; highs, lows and the selected
13:00/13:30/13:45/14:00 completed-close anchors agree.

The original **-$13.6563** modeled net loss and recorded 5.5 bps entry/exit
slippage reconcile. Its **13:30 UTC** exit is a historical modeled bar-opening
clock; completion is **13:45** and source knowledge **13:45:10**. Vendor minute
trade prices first cross the stop reference within **13:30–13:31**, which does
not establish a physical mark trigger or fill timestamp. High confidence is
limited to the scoped measurements and original model semantics. This explored
diagnostic adds no out-of-sample or future-profit evidence.

Source **b4aaf94a56f77556497fe2f0da1490fbb3f7e4a6** is frozen and clean.
**78 offline tests** pass, arithmetic statement/branch coverage is 100%, and
combined analysis coverage is 92%. The corrected **142-file** archive reproduces
**10 outputs byte-for-byte**. Independent SQL verifies **1,728 comparison
cells**, **1,440 minute rows**, **18 summaries** and all four anchor series.
Earlier failed capture/analysis/archive attempts remain retained.

Journal **1ff84a1b3724f2a86d902f7a2e6fbc251d1055dcd7b106ba9c0b6a04e61f5429**
([source record](v89-sndk-source-reconciliation-20260912-v1.json)) binds
**30 references**, **296 frozen files** and **24 original input refs**. The
**09:56:00 UTC** audit verifies all 21 normalized journal columns, source archive,
reproduction, 13 retained HTTP responses and unchanged installed/candidate hashes.
The primary price report preserves its pre-independent stage marker; the separate
completed SQL and reproduction receipts establish final verification.

**Single next investigation:** quantify propagation of the 16 source opening/closing
differences into the already-published SNDK entry-quality and matched-background
measurements touching August 19. Preserve original entries, outcomes and control
memberships; compare both sources symmetrically, without PnL-based source choice
or filter fitting. Acquisition, source numerical comparison and exit-clock
reconciliation are complete and should not be repeated as new trials.

The latest retained unsigned account boundary is **09:37:22 UTC**: existing
**-0.306 SNDK** short with full-size **1669.9** reduce-only stop, **-$0.0612**
unrealized, **+$0.081031** funding cash over 19 rows, core flat/order-free and
no additional bounded fill. Original runner PIDs are absent in the observed
scope; process visibility is limited. Refresh before current-state claims.
Both installation questions remain pending and both prospective seals remain unopened.
Broad live readiness is unproven.

## Previous day-influence finding

**September 12 SNDK day influence audit:**
The [review](../reviews/2026-09-12-v89-sndk-day-influence.md) retains every one
of 48 date omissions under two fixed modes: remove that date's entry anchors,
or remove all overlapping signal/control price windows. Both original matching
methods and all four horizons remain fixed. This is 96 dependent sensitivity
scenarios over 47 entries, not new independent market observations.

The later-minus-earlier long one-hour matched-excess gap retains its negative
sign in every scenario, but dropping August 19's entry moves it from **-66.25
to -8.28 bps**; day-class matching moves from **-61.23 to -3.10 bps**. Price-window
omission leaves corresponding gaps at **-8.65/-2.89 bps**. Long 15-minute and
four-hour gap signs also survive every omission; long 24-hour signs can reverse.
Several short-side signs depend on omitted dates and matching method. High
confidence applies to historical measurement, not causal regime attribution
or future profit. The ranges are not confidence intervals or a live filter.

**65 offline tests** pass; new arithmetic has **72/72 statements and 28/28
branches** covered. Independent SQL reconciles **35,246 included comparisons**,
**850 exclusions**, **3,072 groups**, **1,536 decompositions**, **64 group ranges**
and **32 gap ranges**. All 36,096 roster slots remain accounted for. The 24-file
source archive reproduces **104 artifacts byte-for-byte**, including all 96
trials and the independent receipt. A fresh prepublication SQL/replay check passes.

Source **0654f937d95ceb9fd3876d6527197844c7d806e3** is frozen and clean in
`hypervector-v89-sndk-influence-20260912`. Journal **d72bdcb3acebc59fc46c85ada2add4ef831b3fc902b683503c2d00f627d1bf32**
binds **25 direct references**, **273 frozen files**, **2,375 prior input
references**, **10 baseline pins** and **12 operator source pins**. All **21
normalized database fields** pass the 08:06:18 UTC publication audit. Both
installation candidates remain unchanged and uninstalled; both seals remain unopened.

At **07:47:23 UTC**, seven authenticated unsigned responses retain the existing
**-0.306 SNDK** position, **-$0.306 unrealized**, and full-size **1669.9** reduce-only
native stop. Seventeen funding cash rows sum to **+$0.091831**. Core is
flat/order-free; the bounded fill query has the original entry and no additional
fill. Original runner PIDs are absent and terminal/profile/TUI/ledger identities
are unchanged. Refresh before current-state claims; process visibility is limited.

**Historical next step (now completed above):** qualify independently collected historical SNDK
prices, including existing 0xArchive coverage, and reconcile the influential
August 19 path with the original modeled entry, stop exit and one-hour target.
Separate feed disagreement and post-exit price movement from the actual modeled
loss. Preserve all sources and do not choose a feed or fit a filter by PnL.
The held-path, fixed-horizon, matched-background and day-influence studies are
complete; do not repeat their measurements as new trials.

## Previous matched-background finding

**September 12 SNDK matched-background comparison:**
The [review](../reviews/2026-09-12-v89-sndk-background.md) compares all 47 accepted
entries with fixed non-entry hours in the same cohort and UTC hour, plus a
weekday/weekend sensitivity. Both use the native completed close at the anchor.
Earlier/later long one-hour entry means are **-16.10/-90.07 bps**, versus
**+7.82/+0.09 bps** in their matched backgrounds. The **-73.98 bps** entry gap
splits into **-7.73 bps** background change and **-66.25 bps** excess change.
Day-class matching retains **-61.23 bps** excess change. This is consistent with
entry-associated weakness under these controls; causality and future profit
remain unproven. Short-side changes vary across horizons.

All **4,608 calendar rows**, **376 comparisons**, **32 groups**, **16 decompositions**
and **1,128 modeled/native price-basis rows** reconcile independently. One unique
24-hour entry target is missing; all missing calendar targets and control
memberships remain explicit. The price-basis bridge explains the difference
from the preceding modeled-entry study without revising fees, fills or PnL.

**67 offline tests** pass. Arithmetic has full statement/branch coverage;
orchestration coverage is separately disclosed. The first archive replay found
sub-tolerance parallel SQL aggregation differences in the verifier digest.
A one-line single-thread setting and failing-then-passing repeatability test
resolve that issue. Final source **03f153f131a1b1dcf7d2ca9a4ccfc312315f9f47** is
clean and frozen; all seven data files plus the independent receipt reproduce
byte-for-byte from the 15-file archive. Original source/results are preserved.

Journal **b73568200da6adfb09b1327e896c39847f4c80755d25a3bcccd1c92c5f470bd0**
binds **25 direct references**, **117 frozen files** and **2,375 prior input
references**, plus 11 pinned prior-study artifacts. All 21 normalized database
fields and the source archive were verified. Both installation proposals remain
unchanged and uninstalled; both prospective seals remain unopened.

At **06:47:14 UTC**, seven authenticated unsigned responses show the existing
**-0.306 SNDK** position, **-$0.7956 unrealized**, and its full-size 1669.9
reduce-only native stop. Funding cash totals **+$0.092131** across 16 rows.
Core is flat/order-free, the bounded fill query contains the original entry,
and original runner PIDs are absent. Terminal/profile/binary/ledger identities
are unchanged. Refresh before current-state claims; process visibility is limited.

**Single next investigation:** predeclare a day-level influence audit of the
new matched excess and earlier/later gap, retaining every omission scenario.
Large moves and the small later cohort warrant this sensitivity check before
claiming a stable regime or signal cause. Fit no live filter from this explored
history. The original held-path, fixed-horizon and matched-background studies
are complete and should not be repeated as new trials.

## Previous holding-period selection finding

**September 12 SNDK fixed-horizon entry diagnostic:**
The [new review](../reviews/2026-09-12-v89-sndk-fixed-horizon.md) includes all
47 accepted entries at predeclared 15-minute, 1-hour, 4-hour and 24-hour targets,
including trades that exited earlier. Holding-period selection materially changes
the old first-hour interpretation: earlier long means move from **+22.21 to
-20.49 bps**, later long means from **-38.83 to -97.38 bps**. The later long
cohort remains weaker. Short-side changes are mixed, and price paths after exit
are not actual trade PnL or a validated holding-policy counterfactual.

All **1,128 case-entry-horizon rows**, **288 groups**, **96 selection effects**
and **282 old one-hour observations** reconcile independently. There are 47
unique identities, not 282 independent case entries. Six missing rows represent
one later-long 24-hour target beyond the source end. All 47 one-hour targets
are observed. **68 offline tests** pass; metric and input-validation statement/
branch coverage is complete. Nine outputs reproduce byte-for-byte from the
10-file archive. Operator/verifier branch coverage remains separately disclosed.

Source **feabbfa6641087692419cebc5f150c192a70f24b** is frozen and clean in
`hypervector-v89-sndk-fixed-horizon-20260912`. Journal
**aeeb16da596109ef885b9c5bbae7fde1164685434dc7802f174d4e34fe2ca0f0** binds
19 direct references, 75 frozen files and 2,375 authenticated prior inputs.
The two-file session and 64-file heartbeat/TUI proposals remain unchanged and
uninstalled. Both prospective hypothetical outcome seals remain unopened.

At **06:01:13 UTC**, seven authenticated unsigned responses retain the existing
0.306 SNDK short and full-size 1669.9 native stop, **-$1.53 unrealized** and
**+$0.092131** summed funding cash across 16 rows. Core is flat/order-free;
original trading PIDs are absent and terminal/profile/binary/ledger identities
are unchanged. Refresh before current-state claims.

**Single next investigation:** predeclare calendar-hour matched background SNDK
forward-price controls using the same causal price convention and historical
periods. Test whether weaker later longs are entry-specific or reflect background
asset movement. Preserve all controls and missing horizons; do not fit a live
filter from this explored history. Held-path and fixed-horizon diagnostics are
complete and should not be repeated.

## Previous public transport finding

**September 12 public session-latency extension:**
The [supplemental review](../reviews/2026-09-12-v89-session-latency-extension.md)
records a completed fixed 16-pair experiment: reuse is faster in all 16, with
median paired saving **1.856397 seconds / 44.5684%**. All **112 paired frames**
match; **9,408 raw-derived cells** reconcile. All **225 HTTP attempts** are
retained, including one recovered baseline ConnectionError. Four independent
session contexts close after their final requests. Actual idle intervals reach
83.635 seconds; session identities do not prove underlying TCP reuse.

Research source **ce60c08** passes **53 offline tests**, including 29 synthetic
corruption controls. Its independent report reproduces byte-for-byte. This is
one location, one short fixed five-minute candle window, and no economic or
live-fill experiment. Keep the older four-pair workload separate. High confidence
applies to measured evidence; future latency benefit has medium confidence.

Journal **afdc83805f111fb7cb76d0a30d36fe3562a48e46596c9c576c85a31a33b0c3b4** binds
16 direct references, 631 frozen study files and 11 archived source/plan files.
The original two-file session proposal remains distinct from the pending
64-file heartbeat/lifecycle installation packet. Neither is installed, expanded
or activated by this experiment. Both prospective outcome seals remain unopened.

At **05:32:18 UTC**, seven authenticated unsigned responses retain the existing
**0.306 SNDK short and full-size 1669.9 stop**, -$1.4076 unrealized, and
+$0.089007 summed funding cash flows across 15 rows. Core is flat/order-free in
that capture. Original trading PIDs remain absent, terminal rows and installed
profile/binary/ledger identities unchanged. Refresh before current-state claims.

**Single next investigation:** reconstruct fixed-horizon forward paths for all
47 accepted SNDK entry identities, including early-exit trades and both sides,
to remove holding-period selection from the prior first-hour diagnostic.
Predeclare horizons and source requirements, retain missing/censored observations,
and select no fitted policy or live change. Existing held-bar excursion work is
complete and should not be repeated.

## Previous historical cadence finding

**September 12 historical waiting-time analysis:**
The [new review](../reviews/2026-09-12-v89-entry-waiting-time.md) extends the
already completed September 10 matrix and report, which were not restarted.
All 48 scenarios share **177 trades and 167 unique entry timestamps**. Complete
hourly-start four/eight/twelve-hour windows had no portfolio entry in
**51.44%/24.80%/11.74%** of observations. Core crypto supplied 17 trades and
35 zero-entry calendar days. Under adverse costs, **8 of 27** portfolio entry
episodes after waits of at least twelve hours were profitable; their net was
**-$127.61**. Fixed wait bins select no new entry filter or sizing rule.

This is a previously explored 48-day historical sample. Hourly windows overlap;
separate fixed-grid windows can remain serially dependent. The three cases after
24-hour waits are especially sparse. These fractions do not establish future
waiting times, return probabilities or current execution health.

Source **f1fa951** remains in the isolated `hypervector-v89-entry-waiting-20260912`
worktree. **29 offline tests** pass, covering all 50 arithmetic statements and
14 branches. Independent SQL on original account case files reconciles **150,432
window/day/gap rows and 2,520 outcome fields**, with maximum cash residual
5.6843e-14 USD. Eight corrupted results are rejected. Five final outputs reproduce
byte-for-byte; 64 direct historical/presentation inputs authenticate.

At **04:34:55 UTC**, seven unsigned responses retain the existing **0.306 SNDK
short and full-size 1669.9 stop**, -$1.4076 unrealized, and +$0.095742 in 14 summed
funding cash rows. Core is flat/order-free in that capture. Original trading PIDs,
terminal rows and source/profile/binary/ledger boundaries are unchanged; process
visibility has documented limits. Both prospective seals remain unopened.

**Next research:** extend the pending candle-fetch session candidate's four paired
public observations using a predeclared payload-parity and timing experiment.
No deployment or financial behavior changed; the latest 64-file installation
decision below remains pending. The journal is
`v89-entry-waiting-time-20260912-v1.json`; full verification receipts are in
`data/logs/research/bidirectional_cohort/v89_entry_waiting_time_20260912_v1`.

**September 12 04:00 UTC heartbeat and terminal health:**
The [installation review](../reviews/2026-09-12-v89-heartbeat-freshness.md) records
candidate **1b5eaa9**, which repairs the previous freshness gap. The exact
**64-file package and executable** passed apply/rollback/reapply on disposable
copies. No installation or trading restart occurred.

**605 Rust tests and 176 Python tests passed**, with Clippy, formatting, Ruff
and release build. Twenty-three existing Rust tests remain ignored. The two
changed Python modules exceed 85% statement coverage; broader branch coverage
remains incomplete. The new terminal emitter's lines and branches are covered.

**66 native frames** independently verify advancing, stopped and stale states
at three terminal sizes. All 21 asset/chart cases match source candle and book
clocks, and the header follows actual heartbeats. A 14-poll public observer
covered all seven provider scopes, emitted 98 books, and ended normally with
an explicit terminal event that preserves polling statistics. It supplied no
eligible entries, orders, fills or new economic evidence.

Journal **deb6157577730f7fce086c57d25f59c995a16afb48694581a1e72532591b6a79** verifies 21 stored fields, 25 direct references and
253 frozen files. Preserve this candidate and study; continue new work in an
isolated worktree. Both prospective hypothetical outcome seals remain unopened.

**Next:** installation decision on this exact package, followed by actual
installed-runtime acceptance after approval. While pending, investigate entry
frequency and opportunity cost for the seven configured routes using unsealed
evidence. Full live/strategy readiness remains unproven.

The 03:54:54 UTC unsigned boundary retained the SNDK short and full-size
1669.9 stop, with −$1.8666 unrealized and +$0.096169 summed funding cash flows.
Core was flat/order-free; original process and ledger checks were unchanged.
These are bounded sequential observations, not current-state guarantees.

## Previous configuration-workflow acceptance

**September 12 03:00 UTC / September 11 23:00 Eastern configuration workflow:**
The [new review](../reviews/2026-09-12-v89-configuration-workflow.md) records
candidate **ca8247b**, combining prior recovery/chart fixes with complete CFG
paging, retained inactive policy, and matching staging outcomes. The exact
**52-file package and TUI** passed disposable apply/rollback/reapply; neither
was installed and no trading backend was restarted.

**587 Rust and 439 Python tests passed**, plus Clippy, formatting, Ruff and
release build. Twenty-three existing Rust tests remain ignored; broader Python
branch coverage is incomplete. **588 native frames** independently verify
21 asset/size cases, all 231 selected editor rows, complete scope/outcome text,
21 real disarmed staged profiles and exact chart closes/decision clocks.
Three representative native-cell images were inspected. Installed Terminal and
live activation remain untested.

The new unsigned five-poll observer provided 7/7 provider scopes, 10 unique
HOLD evaluations, 35 books and 361 causal completed minute candles per asset.
Its ledger spans 71.459 seconds and its process exited before staging captures.
Incremental six-symbol and SPCX updates were correctly merged. This does not
establish trade cadence, execution quality or profitability.

**Next: heartbeat and per-asset market freshness independent of operator
acknowledgements.** The exited observer still displays BACKEND CONNECTED;
source inspection finds only armed-live inactivity checking, based on file
mtime, and a shared SYNC clock advanced by operator events. Test observer
inactivity and armed acknowledgement-only updates, then an advancing public
observer/checkpoint lifecycle. This is a remaining operational requirement.

At 02:51:59 UTC the SNDK short and full-size 1669.9 stop were still present,
with −$2.0808 unrealized and +$0.095905 summed native funding cash flows.
Core was flat/order-free. Original trading PIDs were absent and ledger hashes
were preserved. These are bounded sequential observations.

Journal **2df98c9cf91657a1b8100349dc19be46e238cd061e6220b318bb87f593bd37de**
verifies 21 stored fields, 23 direct references and **1,570 frozen files**.
Keep its candidate worktree and artifacts unchanged. Full live/strategy
readiness remains unproven; no economic promotion or deployment. Both
prospective outcome seals remain unopened.

## Previous chart and control acceptance

**September 11 21:30 UTC / 17:30 Eastern complete chart/control evidence:**
The [updated installation review](../reviews/2026-09-11-v89-complete-chart-controls.md)
proposes candidate **05809a9**, including funding/checkpoint recovery, compact
controls, BTC hourly candles and complete scrollable chart evidence. The exact
44-file package and executable passed apply/rollback/reapply on copies; neither
was installed and the trading backend was not restarted.

**578 Rust tests**, Clippy, formatting and release build passed; 23 existing tests
remain ignored. Prior focused Python recovery evidence applies to 19 byte-identical
Python files. **410 native frames** passed scoped all-asset checks: 21 chart,
21 OPS and 21 setup-inspector cases, plus all 840 distinct depth levels. Earlier
failures and capture/test-fixture errors remain preserved.

Five fresh unsigned observer polls yielded 7/7 provider coverage, 10 unique
HOLD evaluations, 35 native books and 361 completed consecutive candles per
asset. Exact providers/assets/policies/runtime settings matched the recorded
configuration. Current completed provider clocks were verified; this 76-second
window supplies no trade-frequency or profitability proof. The observer exited
0 at its poll bound; its last heartbeat is not proof it remains alive.

At 21:25:15 UTC the SNDK short and full-size 1669.9 stop remained present,
with -$0.5508 unrealized and +$0.036281 native cash funding. Original run PIDs
were absent; ledger/profile/binary identities were preserved.

Journal **8db64a648c339d93184cb222483e27a60febc357afef191cf8993af8f022a27f**
verifies 21 stored fields, 19 direct references and **2,675 frozen files**.
Highest-value next investigation: **fresh observer checkpoint/TUI and complete
configuration-workflow acceptance**. Installed-terminal and full live/strategy
readiness remain unproven. No economic promotion; prospective seals intact.

## Earlier checkpoint recovery finding

**September 11 20:12 UTC / 16:12 Eastern checkpoint and TUI recovery evidence:**
The [combined technical review](../reviews/2026-09-11-v89-checkpoint-recovery.md)
binds candidate **a0352a5** (including funding candidate **0c2b819**) to a complete
34-file source/test patch and the exact tested TUI binary. Inherited lifecycle
publication, explicit missing provider context, stopped-backend authority and
current-run fill-quality scope are corrected in the isolated candidate. Exact
source and executable installation/rollback/reinstallation passed on copies.
No source/TUI installation, restart or real financial instruction occurred.

The 158 focused Python tests, 564 Rust tests, all-target Clippy, formatting and
19-file Python Ruff checks passed; 23 existing Rust tests remain ignored. The
advancing-clock V4 full-backend replay completed two simulated cycles, produced
one +$0.004137 funding row with no new fills/charged fees, preserved all eight
original ledgers and clone prefixes, and verified 1,889 backup files. Readiness
was 655.943 s within 900 s, plus 23.031 s initial inventory; this single local
measurement is not a worst-case startup guarantee. Actual checkpoint publication
then completed in 0.669425 s on the bounded recovered-run inputs.

The same final binary rendered 54 native frames across two source-backed cases:
27 from simulated recovery and 27 from the actual stopped V3 checkpoint. All
passed scoped stopped-state/accounting checks; the actual recording includes
seven provider contexts, 978 evaluations, candles, depth, trades and regimes.
**Full live acceptance is unproven.** At 100x28, OPS details compress/clip; all
paged assets/details and fresh complete strategy/data readiness remain pending.

At 20:05:34 UTC unsigned native reads still found the 0.306 SNDK short, 10x
isolated, exact full-size stop at 1669.9, and -$1.071 unrealized. Six native
hourly funding credits total +$0.033164. Core was flat/order-free. Original
terminal records and cohort/SNDK hashes were unchanged; original trading/TUI
PIDs were absent and three read-only observers present. Permission-limited
process-name inspection is not proof of machine-wide launcher absence.

Journal **d055d1e5838e6a47f54bd2e2e38b837fb8b9ae538f7238cffd56564a968614f3**
verifies all 21 stored columns, 22 direct references and 529 frozen files.
Earlier failed attempts remain retained. Highest-value next investigation:
**compact OPS usability, followed by complete seven-asset paged data and provider
readiness**. Explicit approval is requested for the reviewed combined source/TUI
installation under the objective's Human control clause; no economic promotion
is supported. Both prospective hypothetical outcome seals remain intact.

The following dated entries retain their original evidence boundaries.

**September 11 18:02 UTC / 14:02 Eastern full-backend recovery evidence:**
The [recovery review](../reviews/2026-09-11-v89-whole-launcher-recovery.md) verifies
the unchanged candidate `0c2b819` on complete, authenticated ledger clones.
Fresh identity appeared after **678.716 s**, within the actual 900-second default;
two complete accounting cycles finished with worker exit zero after **694.902 s**.
The supervisor's initial ledger inventory took a separate 23.962 s. This single
local result is not a worst-case startup or real-network latency guarantee.

One +$0.004137 credit was appended exactly once. Both funding windows, snapshots
and heartbeats agree; retained fills and charged fees are unique. Exact SNDK
ownership and execution plan persist, and all seven final clone states are
`STOPPED / bounded_run_complete`. Six configured flat-asset leverage settings
were acknowledged only by strict mocks; no orders were requested. All original
ledgers and clone prefixes, three complete backups, and eleven candidate source
files were verified. The candidate remains **uninstalled**.

The first two attempts remain preserved: V1 exposed the existing flat-asset
leverage reassertion; V2 reached fresh identity but failed on missing scripted
market-bar keys before complete publication. A subsequent actual checkpoint
projection rejected the fixed clock's duplicate book-receive timestamps for all
seven assets. That is a simulation limitation, not a demonstrated production
defect. No checkpoint/TUI acceptance is claimed from this replay.

At 17:34:32 UTC, actual Info-only preflight reconciled all seven assets, resolved
fees, sizing and visible planned depth, and observed unified account reference
equity **$4,807.25695649**. Its flat-transition condition is false because protected
SNDK remains open. At 17:51:05 UTC, further native reads confirmed the same
-0.306 short, 10x isolated, exact full-size stop at 1669.9, and -$2.9988 unrealized.
These are sequential point-in-time facts. The five original trading/TUI owners
remain absent and seven original terminal records unchanged; all three observer
births and both prospective outcome seals are preserved.

Journal `e5a8faa2fa8241147d550cc27e227a63a727a60c9ff7d76c9f1c096d66ebd4be`
verifies 21 stored fields, 16 direct references and 109 manifest members. The
initial journal contract omission rejected before database access; its invalid
source and error log remain preserved with the corrected verified append.
Highest-value next investigation: **advancing-clock recovery and checkpoint/TUI
projection**, retaining the actual checkpoint chronology validator and complete
accounting history. No real runtime, source installation or financial change
occurred. Stop intent and both source-only proposals remain separate pending
decisions; no economic-return claim is supported.

The following dated entries retain their original evidence boundaries.

**September 11 16:55 UTC / 12:55 Eastern funding-recovery correction:**
The [restart accounting review](../reviews/2026-09-11-v89-restart-accounting.md)
records the installed same-day recovery of +$0.004137 funding exactly once, with
four retained native fills and their fees still unique across three replays and
two telemetry instances. A separately labeled synthetic restart beyond 24 hours
excludes that known credit under the installed fixed lookback. Candidate
`0c2b81933f4df480e0e8bb6b5289b8ea47504761` restores the actual committed cursor
at 15:37:02.134 UTC and paginates funding account-wide before symbol filtering.
The known credit remains in both tested candidate windows. There is no proven
irrecoverable omission at the same-day capture and no economic-return claim.

The isolated 11-file source-only proposal is **not installed**. The exact commit
passed 136 focused tests, Ruff, source-size checks and actual isolated rollback
and restoration. The two new modules have full measured statement/branch
coverage; this is not full-system coverage or live-launch acceptance. Six prior
files and all candidate files are preserved. Its installation decision is
separate from the pending candle-session proposal and stop-intent clarification.

At 16:47:52 UTC, native reads found the same -0.306 SNDK short at 10x isolated,
with exact full-size reduce-only stop `542326955281` open at 1669.9. Marked
unrealized PnL was -$0.5202 at that capture; core was flat/order-free. Seven
terminal records, original cohort/SNDK hashes, profile/TUI hashes and surviving
observer process births were verified. Original trading processes remain absent;
strategy-managed exits and new entries remain stopped. No prospective outcomes
were evaluated and no financial instruction was sent.

Journal `09ce322fd1b8f3190bea4c597ed5876367d9caa85f1282529f956707aa4c75e9`
verifies 21 stored fields, 13 references and 65 manifest members.
Highest-value next investigation: **whole-launch recovery readiness and first
reconciled accounting projection**, using actual retained ledger sizes with
isolated state and mocked financial boundaries. Measure the added 4.3 GB scan
against the launcher's 900-second default readiness timeout. Fresh venue
reconciliation remains required before an authorized live recovery.

The following dated entries retain their original evidence boundaries.

**September 11 16:07 UTC / 12:07 Eastern offline recovery evidence:**
The [SNDK adoption review](../reviews/2026-09-11-v89-sndk-restart-adoption.md)
records an exact installed-engine startup replay from 22,569 profile records.
It restored size -0.306, entry OID `542326864971`, stop OID `542326955281`, original
entry time and the complete provider plan. Only mocked preflight/reconciliation
reads occurred; no financial mutation or original ledger change occurred.
Seven altered-ownership cases rejected at the pure reconciler; 22 existing
restart/reconciliation regressions passed. Synthetic preflight metadata does not
prove fresh venue eligibility or a full live launcher. The initial missing HIP-3
fee fixture failure is retained alongside the successful replay.

Unsigned native reads completed **16:07:50 UTC**: the same 0.306 SNDK short at
10x isolated and full-size reduce-only Stop Market at 1669.9 remained open;
core was flat/order-free. Marked unrealized PnL was -$3.4272 at that capture.
The original trading/TUI processes remained absent and seven terminal records
unchanged. Strategy-managed exits remain stopped. The stop-intent clarification
and optional source-only latency installation decision remain pending.

Adoption journal `c30d2adfb8d23ab5c132a90f7545bc95f45bf9d835dc0bd40037cf6a39910ba4`
verifies 21 stored fields, 13 direct references and 20 manifest members.
Next: **stop-to-restart fill/funding continuity** using exact ledger and unsigned
venue records. Engine ownership restoration is supported within the replay;
accounting continuity and fresh whole-launcher preflight remain separate checks.
No live source/runtime/profile/order/TUI change occurred. Both prospective
hypothetical outcome seals and their original collectors remain intact.

The following dated entries retain their original capture boundaries and actions.

**September 11 15:54 UTC / 11:54 Eastern stopped boundary and latency candidate:**
The [entry-latency review](../reviews/2026-09-11-v89-entry-latency.md) records
seven `STOPPED / operator_stop` terminal records at 15:37:14 UTC, unchanged at
15:54:41, with the five original CLI/supervisor/backend/checkpoint/TUI processes
absent. No runtime owner was signaled by this investigation. The stop category
does not prove who initiated it; the stop-intent clarification remains pending.
The stale final running heartbeat does not establish active execution.

Native reads completed **15:52:43 UTC**: core flat/order-free; XYZ has one SNDK
short **-0.306 at 10x isolated**, with exact full-size reduce-only buy Stop Market
OID `542326955281`, trigger **1669.9**, still open. Its marked unrealized result
was -$5.0796 at that capture. Strategy-managed exits and new entries are stopped.
The final checkpoint's **two closes / -$27.994028 net** exclude this open position.
Refresh account/process observations before interpreting these as current state.

Three exact entry lifecycles were decomposed and reproduced. SDK dispatch ages
were 18.633, 27.706 and 21.495 seconds against a 30-second limit; no observed
violation exists. The SNDK long waited through BTC's preceding protected-entry
workflow. The candidate preserves that sequencing. Four counterbalanced public
candle comparisons saved **3.026991 seconds median / 44.9513% of fetch time**;
all 28 paired frames were identical. This measures transport, not profit or
future latency guarantees.

Candidate `f59d54cf40cf80111b1691a86395326693b0c103` is clean in the isolated
candle-session worktree and **not installed**. Its exact two-path source-only
installation is approval-ready, with no automatic restart or order action.
62 focused tests passed; a subsequent test-only refactor passed its five tests.
The changed command function has 100% statement/branch coverage. Ruff and actual
isolated rollback/restoration passed; diagnostic tests passed 40 cases and the
current analyzer reproduced all three reports. Initial fixture/test-first
failures are retained in the evidence packet.

Journal `a986c57ae736900a2cbc46f3cbe39c6dde9277c092cb5835c708ff056abf09ff`
verifies all 21 stored fields, 18 direct references and 123 manifest members.
Highest-value next investigation: **offline exact-state restart adoption** for the
remaining SNDK lifecycle, proving no duplicate position/stop/plan mutation before
a concrete recovery decision. Both prospective outcome studies remain sealed.
The roster producer 44983 and collectors 75062/15448 retain their original births.

The following dated notes preserve prior capture boundaries. Their running-state
and next-action statements are historical, not current instructions.

**September 11 15:08 UTC / 11:08 Eastern funding repair:**
The [funding review](../reviews/2026-09-11-v89-roster-funding.md) records the
source omission and its installed correction at
`40154844348faf50dab7d905aa4d12defbad86bf`. The nine paths match isolated
candidate `caa6904a0e5968552beafea876fd7bd5549c37c3`; 58 focused tests passed,
the new funding reader and affected critical paths have full measured coverage,
and Ruff passed. Ten candidate rates matched raw venue responses. Eighteen
candidate and nine production funding cells matched the installed native TUI,
including explicit fresh/stopped labels. Original Terminal access remains
blocked; isolated native rendering does not verify that window.

Only Info-only observer PID 37491 was gracefully replaced after confirmed
exit. PID 44983, birth `31776092912024`, published available/running reports
at 15:04:44 and 15:07:12 UTC with all five funding values. Its output and
120-second post-collection delay are unchanged. The original trading owners
and both collectors retained their process births. Seven prior files were
preserved; the profile, binary, trading parameters and supervision policy are
unchanged. The old full-source match to candidate `564d72e` now has this
explicit nine-path report-only correction; no trading release change is implied.

The 15:08:35 UTC checkpoint reports the same running-consistent live run, six
fills, two closes totaling **-$27.994028 net**, and one open SNDK lifecycle.
The next investigation is **decision-to-fill latency attribution** for the
three actual entries, especially 28,601 ms against the configured 30,000-ms
limit. Reconstruct available stage clocks and report missing timing evidence
before proposing a correction. No limit relaxation, strategy retuning or
prospective hypothetical outcome evaluation is authorized by this research.

Funding journal
`73e6355fccb9a36f619ec799e11ad5d9981aaf71540458f714795ead68dd2c60`
has all 21 stored fields, 17 direct references and 100 manifest members
verified. The first append met a transient lock held by PID 45970; that
process was confirmed absent before the successful retry. The evidence and
rollback are complete; no approval is pending for this report-only correction.

The following live-acceptance and installation notes describe their dated
capture boundaries; their former missing-funding action is resolved above.

**September 11 14:17 UTC / 10:17 Eastern live acceptance:**
The [live acceptance review](../reviews/2026-09-11-v89-live-acceptance.md) records
user-started run `bidirectional-live-1789122347122`, active since its first
backend event at 10:35:44 UTC. All seven assets have complete telemetry. The
first two closes, BTC and SNDK longs, lost **$27.994028 net after fees**.
All six native fills reconcile, including a subsequent SNDK short; its observed
0.306 position at 10× isolated leverage has a full-size reduce-only stop.
All three entries dispatched and filled within their 30-second limits.
These are actual-account observations, not evidence that the strategy will win.

The 15-minute reporting observation retained 181 process samples, 31 checkpoint
captures / 28 distinct publications and 248 exact ledger-prefix comparisons.
Reporter writes measured 79.16 MiB; maximum captured checkpoint age was 33.856 s.
Nine views at three sizes, all seven depth selections and all twenty Brent
levels at each size were captured with the installed native binary. The
original Terminal window remains unverified because Computer Use blocked access.
The isolated native renderer does not satisfy that original-window check.

The stopped September 5 auxiliary roster producer was restored without
restarting the trading owner, primary reporter or TUI. Fresh native panels now
show `HIP-3 LIVE` / `CURRENT`. Twelve observer/factory tests passed. Funding
still shows `N/A` because the Info-only producer omits its optional hourly
funding field. This is the **next source-backed telemetry repair**, to be
developed in isolation with missing/invalid/stale-input and display-unit checks.
The observer's future supervision also needs an explicit deployment design.

Runtime source/profile/binary identities still match the approved installation;
the run-specific backup reverified 1,928 files, including 1,874 implementation
sources. No trading settings changed. Both prospective outcome seals and both
original collectors remain active. Actual-account monitoring is disclosed;
neither compared hypothetical outcome study was evaluated. The broader goal
remains active. The following installation/stopped-state notes are historical.

Live acceptance journal
`2fd93dbb082ee4cb9f2101a3f3253f67bc83991aedaa2ddaed94cabb144193da`
has all 21 stored fields, 20 direct references and 513 manifest members
verified. The first append encountered a transient DuckDB lock; its owner
exited before the successful retry. No trading process was restarted.

**September 11 03:32 UTC / September 10 23:32 Eastern V3 installed:**
The [installation review](../reviews/2026-09-11-v89-v3-installed.md) records the
actual approval, exact 72-path source installation at `4b241ef0b5fe5c5c785ad11804be5417a7bf5dab`,
and TUI SHA256 `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.
The full selected source scope matches candidate `564d72e81539afdd3e2979beea4086a655ec4350`.
All 354 related Python regressions passed in main; two mocked command probes and
native executable help passed. The exact binary retains its prior 320-test and
nine-view native replay qualification. Current live account display acceptance
still requires a new run.

Fresh unsigned core/XYZ reads, seven-asset preflight and native settings checks
passed at approximately 03:27–03:28 UTC: flat/order-free, reconciled, no technical
readiness reasons. Nine locks were unowned, pending/claimed commands were empty,
and no canonical live process was present. All 530 provider files, ten SDK files
and 1,924 backup archives/current source files reauthenticated. The new boundary
preserves the approval, prior TUI/profile and 78 current operator-control files.

Installation journal `604cfccd31e115ba5ae4535a88f34150a5286946bfa14ae87959f99f623b7ee4`
has all 21 stored fields and 54 direct evidence references verified. The source
installation is committed separately from this report-only journal append.

The next action is the **user-run command in the installation review**, followed
by fresh same-run nine-view/Brent acceptance, eight mapped-reader publications
and a 15-minute I/O observation. No further installation approval is pending.
The prior afternoon ETA is superseded by this completed installation. The V89
trading profile and both prospective seals remain unchanged. Everything below
is dated historical evidence; earlier uninstalled/pending statements describe
their capture time.

**September 10 19:32 UTC fresh operational readiness and backup:**
The [readiness review](../reviews/2026-09-10-v89-release-readiness.md) records fresh
native core/XYZ account reads at 19:17:32–33 UTC: no positions or open orders.
The existing Info-only seven-asset preflight completed zero at 19:18:59, with
sizing, displayed depth and ledger reconciliation passing. Native saved leverage
and isolated margin settings match all seven configured assets at 19:22:02–04.
Account value is approximately $4,836.47; this observation is not a return estimate.

Seven current live ledgers end in September 8 `STOPPED` records with zero size
and no owned order IDs. Nine existing ownership locks have no active owner;
their contents/times remain unchanged. STOP and drain markers are absent, and
the operator inbox has zero pending and zero claimed commands. At 19:27:36 UTC
no canonical local runtime is present and both original collectors remain active.
These observations supersede reliance on the old September 8 venue snapshot;
they are sequential and must be refreshed at the actual maintenance boundary.

Pre-transition preservation completed 19:27:01 UTC. The verified bundle contains
1,924 files, including 1,869 implementation sources, 8,175,290,477 restored bytes
and 881,638,405 compressed bytes. Manifest SHA256 is
`928ebd40d92c056b62fff7e3f687cbc14ae54b4ddd41f881bae91bdc6ec6df9f`.
The prior TUI and 78 operator-control/history files are separately preserved.
The stopped ledger sizes/times remain unchanged. This is not a live launch;
the eventual launcher must create its own run-specific backup.

Journal `39f2564884af077e79f1f74203b9b84304a432409e3bea9f54a6336778b8dbd5`
has all 21 stored fields and 45 direct references verified. The readiness archive
verifies 41 members, 3,894,587 bytes, SHA256
`bb96c0653fef509b58c47209f1315cfc06251d28501fb643afa9a429aa45176b`.

The exact V3 source/TUI installation is now approval-ready. The next action is
the selected installation decision, followed by authorized installation and
user-run activation with fresh boundary reads and same-run nine-view/reporting
acceptance. The conditional activation window remains 16:00–18:00 Eastern today.
Installed runtime/profile/TUI are unchanged, the original financial pipeline is
complete, and both prospective outcome seals remain intact.

**September 10 19:13 UTC combined release and review completed:**
The [V3 combined recommendation](../proposals/v89-technical-release-20260910-v3/recommendation.md)
selects candidate `564d72e81539afdd3e2979beea4086a655ec4350`, 72 source/test
paths (46 implementation, 26 tests/fixtures) and TUI executable SHA256
`382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.
Exact isolated installation and compatible rollback finished at 18:57:14 UTC.
Both compositions passed the same 129 related regressions and two mocked
live/monitor command probes. Rollback restores 63 paths and retains exactly nine
compatibility paths. This is not a claim of 258 distinct tests or live startup.

Thirty-three packaging controls pass. The new native source-identity guard has
full statement/branch coverage; other operator coverage remains partial. All
117 retained source copies, 530 provider files, ten SDK files and 78 direct
prior/native journal references reauthenticate. The 48 completed case reports,
financial manifest/report, thirteen prepared presentation artifacts and final
HTML also match. The original pipeline remains complete and was not restarted.

The proposal combines the separately completed 320-test/native nine-view TUI
acceptance with the 48-case/144-comparison financial results. Cost sensitivity,
later-period weakness and increased equal-allocation exposure remain material.
It preserves the current V89 profile; no higher-return live strategy is claimed.
All older packets, reports and prospective outcome seals remain preserved.

Journal revision 3
`15aa0be4dbe5c2d9e52f90367d89c1d8627144fd6ae257cf061fa083c750d617`
has all 21 stored fields, 47 direct references and its predecessor verified.
The release archive is 7,704,294 bytes and verifies 168 members, SHA256
`5fb9aeae579f8ad24e933b2e3831f0bc3be6e51c6e9a860031cda068653b9557`.

The corrected 19:09:41 UTC process inventory confirms both original collectors
active and finds no canonical local live process. The first inventory's macOS
`comm` field was truncated; it is retained as superseded evidence and cannot
prove process absence. Current venue positions/orders remain unverified.
Installed runtime/profile/TUI are unchanged; the V3 rehearsal checkout is left
in compatible rollback state and is not a launch directory.

The next action is fresh account/order/owner/native-setting reconciliation and
the selected release approval, followed by user-run activation and same-run
TUI/reporting acceptance. The conditional activation-ready estimate remains
**16:00–18:00 Eastern today**, moderate confidence. A failed technical check
would update that estimate. No new historical matrix is needed for this release.

**September 10 18:45 UTC native TUI qualification and completed financial report:**
The original reporter completed **48/48 case audits** at 18:36:32 UTC and exited
zero. Its original observer and automatic handoff also exited zero. The
[complete financial report](../../data/logs/research/bidirectional_cohort/v89_complete_review_presentation_20260910_v2/report.html)
contains all 48 cases and 144 paired comparisons. Its three charts, seven tables,
source interaction and desktop/narrow browser verification pass. Thirteen
prepared artifact identities plus the final HTML match the completion receipts.
Do not restart or duplicate the completed pipeline.

The completed matrix retains 177 trades and 3.6875 entries/day in every case.
Core-history revisions leave the compared economics unchanged; XYZ-history
differences are under $0.000003 net. Recorded/repaired exit clocks leave cash
unchanged but affect measured exposure and some drawdowns. Cost assumptions and
allocation drive the material differences. The earlier six-case findings remain
consistent: current sizing returns +$196.85 nominal, +$95.72 with adverse slippage,
and -$33.44 under full HIP-3 fee stress. Equal caps have about twice the average
exposure; their larger dollar profits do not establish independent edge. The
later period remains negative for current sizing in all three cost cases. These
are historical results, not a newly unseen holdout or future-profitability proof.

The [native depth correction](../reviews/2026-09-10-v89-native-depth-freshness.md)
is committed separately at `564d72e81539afdd3e2979beea4086a655ec4350`.
Candidate executable SHA256 is
`382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.
It adds dated book age, independent checkpoint health, visible depth ranges and
bounded arrow/page navigation. All 320 related Rust tests pass, twelve native
depth checks pass and fifteen native paging checks pass. All nine views are
visited at three sizes; all 24 non-Depth view texts match the baseline. Seven
historical fixture assets are selected individually and 4,424 displayed values
independently reconcile. Current V89/Brent/account acceptance remains separate.

Journal `9e481c5a1465c4ca2a4e41f7c6867af031e0798802aa5aa3434ab04bbb7b4e77`
has all 21 stored fields and 37 direct references verified. The evidence archive
verifies 542 members; the Rust source archive authenticates 354 Git blobs/modes.
No installed runtime, profile, TUI or live process changed. The prior V2 package
remains preserved; composing this correction selects 72 source/test paths.

The next action is the exact 72-path combined installation/compatible rollback
rehearsal and final combined recommendation. Fresh account/order/owner checks,
selected release approval and same-run live acceptance remain required. Following
the completed audit and TUI qualification, the working user-run activation
window is **16:00–18:00 Eastern today**, low-to-medium confidence and conditional
on those remaining steps. Both prospective outcome seals remain intact.

**September 10 17:19 UTC revised technical package:**
The [V2 release proposal](../proposals/v89-technical-release-20260910-v2/recommendation.md)
supersedes the preserved V1 deployment scope. Candidate
`e8dbdaff68700bd2fe61c4104e4e4d317f429db0` contains 60 paths: 38 implementation
files and 22 tests/fixtures. Exact installation and compatible rollback pass in
the separate V2 rehearsal checkout. Both resulting compositions pass 129 related
launcher tests and live/monitor command probes against the intended executable.
All foreground invocation is mocked; no native TUI or live process starts.

Rollback restores 51 paths and retains exactly nine compatibility paths: the
restart reader and eight launcher source/test paths. The prior binary therefore
also uses explicit authenticated selection. Twenty packaging control tests pass;
the archive verifies all 141 members, bytes and modes. All 530 provider and ten
SDK source pins match at 17:15 UTC. The old 602 Python/544 Rust qualifications are
reused only for unchanged source, not reported as new runs.

Journal revision 2
`19755ad57b9fc8ba245146ba6547454a1d1973406917e39b5a8dd5f735ebf121`
has all 21 stored fields, 41 direct references and its revision chain verified.
The source archive is 7,619,897 bytes, SHA256
`1b498a3ae8bec33fdebaeabf711a77dd9b4a20cb69ab5c859eeead0d6b341810`.
Installed runtime/profile/TUI remain unchanged. The rehearsal checkout is not a
launch directory; use only the revised approved deployment instructions later.

At the saved 17:16 UTC observation, the original reporter is active with **33/48
final case audits** complete; all 48 simulations are finished. The report observer,
automatic final-review handoff and both collectors remain active. No canonical
local live process is present, and current venue state has not been reverified.
The highest-value next step is the original complete financial publication and
its already-running final-review handoff; do not duplicate preparation. Final
selected approval, fresh account/order/owner/native checks and actual nine-view
TUI/reporting acceptance remain required. The conditional **16:00–19:00 Eastern**
live planning window remains low confidence. Both prospective seals are intact.

**September 10 16:59 UTC launcher qualification:**
The [prebuilt launcher correction](../reviews/2026-09-10-v89-prebuilt-tui-launch.md)
at `e8dbdaff68700bd2fe61c4104e4e4d317f429db0` passes 129 related tests in the
worktree and restored source. Explicit path/hash selection reaches both CLI
layers, refuses executable drift before child startup and foreground invocation,
and preserves existing lifecycle behavior. The selected native executable passes
help-only invocation. Actual terminal and live acceptance remain unverified.

Correction to the prior packaging readiness scope: the old file-installation
rehearsal did not prove executable selection; the installed launcher still uses
Cargo and its build metadata is absent. A superseding 60-path installation and
compatible rollback packet is the next technical step. The old 52-path packet
remains preserved. No candidate code or TUI has been installed.

Journal `23e39426da3800404b7d3b6dcd2eaee49c549e7294a63e737921d70015c5b88d`
has all 21 stored fields and 25 direct references verified. Two temporary restored
source copies were removed after all 10,430 source/fixture/log files matched
retained backups; all archives and supplemental evidence remain available.

At 16:52:27 UTC the original reporter remains active at 100% CPU with **28/48
final case audits** complete. All 48 simulations are finished; both original
observers and collectors remain active, and no canonical local live process is
present. Final report publication is pending. Do not start duplicate preparation.
The conditional live ballpark remains **16:00–19:00 Eastern today**, low confidence,
requiring the report, revised package, final selected approval and fresh
account/order/TUI acceptance. Current venue flatness is not established by the
local process check. Both prospective financial outcome seals remain intact.

**September 10 15:51 UTC prospective-health refresh:**
The [fresh timing audit](../reviews/2026-09-10-v89-prospective-health-refresh.md)
reconciles **12,964 committed responses and 23,611 first-observation identities**
at the two saved 15:46 UTC heartbeats. No mature prospective candle or funding
identity is missing or late. The exact qualified audit source and retained-only
reproduction agree; 74 prior qualification references, 26 collector sources
and both protocols match. The unchanged timing implementation reuses its
26-test, full statement/branch qualification; no fresh test run is claimed.

The original collectors retain their process identities and writer locks. Both
economic outcome seals remain intact. The new journal revision
`1eec81a936d2ea1e2568c73ebc2873894efb0e3f26ab433928e5a224ad715a8c`
has all **21 stored fields, 24 direct references and 50 captured manifest files**
verified. Preserve the earlier snapshots; this refresh adds 1,947 requests and
1,835 first identities without a collector or live change.

At **15:48:08 UTC**, reporter **35528** is active at 99% CPU with **17/48 final
case audits complete**. All 48 simulations are finished; observer **27361** and
automatic final-report handoff **40699** remain active. Complete financial
publication and final HTML acceptance are pending. Do not launch duplicate
preparation. The highest-value economic step remains the original full report.
The **16:00–19:00 Eastern** conditional user-run live estimate remains low
confidence, requiring complete reporting, exact release approval and fresh
account/order/TUI acceptance. Installed source and TUI remain unchanged.

**September 10 15:30 UTC automatic report-handoff update:**
The [final-review handoff](../reviews/2026-09-10-v89-final-review-handoff.md) is
running as **PID 40699 / session 57237**. It waits for the exact original
reporting observer **27361** to terminate, then runs only the frozen V2
preparation and canonical HTML delivery/verification. Do not manually launch
the same V2 preparation concurrently. No live process or deployment is started.

All **51 tests** pass, including stage-failure, exact dependency-path and
browser-receipt controls. Source coverage is 70/71 statements and 27/28 branches;
the remaining top-level invocation has now been observed running. The operator
pins 2,184 references and a byte-verified three-member source archive. Journal
`848da4e39495c017da9d59552271182ccfa489d734cff6314e0f338c3904ef56`
has all 21 stored fields and 15 direct references verified.

At **15:24:28 UTC**, the original reporter **35528** remains active at 100% CPU
with **12/48 case audits complete**. All 48 simulations are finished; neither
new report stage has started. The reused wait helper's matrix event label refers
here to waiting on reporting observer 27361. The complete original publication,
real final reconciliation and HTML acceptance remain pending. The prior
**16:00–19:00 Eastern** conditional user-run live estimate remains low confidence.

[Collateral qualification](../reviews/2026-09-10-v89-aligned-quote-qualification.md)
maps all seven markets to token 0, USDC. The legacy alignment request returns
HTTP 422 and is absent from current API documentation. Current documentation
also distinguishes AQAv1 fee benefits from AQAv2, which gives none. Eligibility
therefore remains unresolved; no extra discount or historical substitution is
applied, and the frozen V2 report needs no further revision. Do not repeat that
legacy request without new contract evidence. Journal
`42a310ce41ac92a75f3eed7eb3cd11487be7adbde14e573b28af1972778387e4`
has all 21 stored fields and 11 direct references verified. Both prospective
seals, the root implementation, installed TUI and live settings remain unchanged.

**September 10 15:00 UTC current-fee and report-context update:**
[Fresh fee evidence](../reviews/2026-09-10-v89-current-fee-refresh.md), captured
at 14:46:13–14:46:15 UTC, confirms growth mode enabled and scale 1.0 for SPCX,
SNDK and Brent. The account's base 4.5 bps taker rate and 4% referral discount
project **0.864 bps per side** for those three and **4.32 bps** for core assets.
The 9 bps full-fee scenario remains an adverse fee-state stress. Today's inputs
do not reconstruct historical fees and replace no frozen scenario assumptions.
All 30 focused tests, 140 source references and seven independent rate checks
pass. Fee journal revision
`577635ebf5ba7227d6dbdc3c046cf59e6fa3c941c081772b98b9d31e8bea883d`
has all 21 stored fields and 17 direct references verified.

[Complete-review preparation V2](../reviews/2026-09-10-v89-complete-review-fee-context.md)
adds that accepted snapshot, summarizes all three cost anchors and explicitly
labels the full-fee path/concentration/cohort displays as stress. It preserves
all 48 original cases and 144 paired comparisons. All **93 tests** pass; seven
report modules cover 361/361 statements and 124/124 branches. The source-bound
fee loader separately covers nine statements and four branches. Fifteen archive
members, 2,171 references and 390 imported local modules are verified. Journal
`28db9d2a50b52f3a041e550cd3c4cf31cc47ad040762b660ca25f4ba7f946e9c`
has all 21 fields and 18 direct references verified. Use V2's
`prepare_command.json` after the unchanged original publisher completes.
The V1 preparation and its unexecuted command remain preserved.

At 14:58:15 UTC, original reporter **35528** is running at approximately 100%
CPU with **7/48 case audits complete**; all 48 simulations have finished. The
full publication and real final reconciliation/HTML acceptance remain pending.
The prior conditional user-run live estimate of **16:00–19:00 Eastern today**
remains low confidence, subject to complete reporting, final selected approval,
fresh account/order/source checks and successful TUI acceptance. No original
job, live setting, installed TUI or prospective outcome seal is changed.

**September 10 14:19 UTC complete-matrix and review-preparation update:**
All **48/48 original historical cases are complete**. The exact resumed coordinator
exited successfully at 14:14:28 UTC; the unchanged full-report observer started
reporter 35528 at 14:14:32 UTC. That reporting process is confirmed running.
The completed matrix is not yet the final 48-case financial analysis publication.

[Complete-review preparation](../reviews/2026-09-10-v89-complete-review-preparation.md)
is frozen in a 14-member archive. All **84 worktree/archive tests** pass, with
353/353 statements and 124/124 branches covered across the seven tested modules.
It retains 48 cases, 144 paired differences, original companion bindings,
negative/undefined results and explicit financial units. Source checks pin 2,006
references and verify 390 imported local modules. Journal
`0c840ed6848277082e4b9bfa42dc70457b46f435f6a120453775af2dc4a2bc06`
has all 21 stored fields and 22 direct references verified. The actual entrypoint,
historical reconciliation and portable HTML/browser acceptance remain pending.

The review planning window is now **14:15–16:30 Eastern today**, with low-to-medium
confidence, using the actual reporter start plus the existing four-to-six-hour
reporting allowance. The user-requested **conditional live ballpark is 16:00–19:00
Eastern**, with low confidence. It assumes complete reporting, an explicitly
approved final release scope, fresh account/order/source/dependency checks and
successful user-run startup/TUI acceptance. It is not a confirmed launch time.
Both prospective seals remain intact; the technical package is still uninstalled.

**September 10 12:54 UTC daily concentration and recovery update:**
[Corrected daily attribution](../reviews/2026-09-10-v89-daily-asset-interactions.md)
reconciles the current 177-trade account across six fixed historical cases.
Under full fees, SNDK contributes **64.51%** of daily variance with current sizing
and **72.86%** with equal caps. At least two assets lose marked cash on **26/48**
days in both cases; the worst days are -$69.94 and -$149.88. Equal caps do not
produce equal observed economic risk. These are explored strategy-PnL statistics,
not underlying-market correlations or a forecast of future diversification.

Research source 1e85d79 passes all 100 worktree/archive tests, covering 146/146
new statements and 52/52 branches. All 288 scenario-day totals and earlier/later
asset components reconcile. Independent Decimal cash checks pass 16,128 values;
DuckDB passes 1,548 statistics checks. Journal
`6493f7458331677b0f05b7ebea82636a72b422d132fcd770ef636c33c467f177`
has all 21 fields and 29 direct references verified.

The original matrix reached **45/48** and terminated with `paused_storage`;
its old observer then refused the absent complete report. The
[verified package-cache recovery](../reviews/2026-09-10-v89-uv-cache-recovery.md)
retains a 508.82 MB archive of 102,808 entries and measures 1.914 GB of free-space
increase during targeted cleanup. Installed environments, project configuration,
TUI bytes and unrelated cache archives are preserved. The exact original research
resume command continues the same matrix and 45 receipts, with unchanged source
and storage reservations. At 12:46:59 UTC, coordinator 27267, workers 27279/27280
and reporter observer 27361 are live; one final case remains queued and free space
is 4.094 GB. Both old terminal records remain available.

The revised complete-review planning target is **14:00–16:30 Eastern today**,
with low-to-medium confidence. This replaces the earlier 13:00–16:30 estimate;
it is not a live-start ETA. Capacity for the last launch, measured case duration
and the four-to-six-hour reporting allowance remain assumptions. Recovery journal
`3949d2d4f89621e2726bd52a99af672da19f0c80cfc3cdaaef056780e567afa2`
has all 21 fields and 29 direct references verified.

Next complete the original matrix and its unchanged full-report command, then
combine the cost/source/clock contrasts with the corrected concentration and SNDK
follow-through evidence. No allocation, strategy, leverage or live execution
change is selected here. Both prospective seals and the uninstalled technical
release remain intact. The earlier updates below retain their evidence lineage.

**September 10 11:49 UTC SNDK and capacity update:** the original historical
matrix has **42/48** receipts. Storage pressure temporarily reduced concurrency
to one worker. Five [verified release-cache recoveries](../reviews/2026-09-10-v89-release-cache-recovery.md)
preserve all top-level executable/library files and retain 917.81 MB of complete
archives covering 9,535 entries. At 11:42 UTC, capacity is 5.38 GB and the original
coordinator has restored three workers without restarting or changing its 2 GiB
reserve and 1 GiB per-case reservation. Main source/configuration and the installed
TUI bytes remain unchanged. Further capacity growth can reduce concurrency again.

The revised complete-review target is **13:00–16:30 Eastern, September 10**,
with low-to-medium confidence. It uses six remaining original identities, the
three captured active elapsed times, two/three subsequent-worker scenarios and
the existing four-to-six-hour full-report allowance. This replaces the earlier
12:30–16:00 planning range and is not a live-start ETA. Fewer than two sustained
workers or further technical delays require another update.

The [SNDK trade trace](../reviews/2026-09-10-v89-sndk-trade-drivers.md) is complete
for six fixed historical cases. Full-fee long entry cohorts have seven winners
from eighteen earlier entries and two from eleven later entries. All nine
winners reach the 24-hour hold limit. Stop exits rise from seven to eight while
mean gross stop returns remain near -207 bps. This supports a descriptive
follow-through hypothesis, not a validated entry filter or profit-lock policy.
First-hour returns are conditional on continued holding and remain explicitly
censored for shorter trades. Earlier/later entry cohorts differ from marked
periods for one carried long.

Forty synthetic tests pass in the operators and frozen archive, with 89/89
statements and 28/28 branches covered in the metric/context module. The trace
authenticates 2,367 references and retains the same 47 SNDK identities per case.
Independent raw-account Decimal arithmetic and DuckDB native-price queries pass
2,070 comparisons; eighteen marked cash totals match the prior attribution.
Journal 18ce14aafaf13ae9a62e467bda74c6af5d769d74085c6ddd5fe0a58c9cbe00fa
has 21 fields and 30 direct references verified. Recovery journal
b8b10920fcb0066028e92530b1ab877d18d2727e5ff14675a272d235278a7de9
has 21 fields and 85 references verified.

Next finish the original matrix and unchanged full-report handoff, then combine
the complete source/cost/clock/allocation contrasts with the retained period and
SNDK diagnoses. Do not reopen the rejected faster-entry study or repeat accepted
clock/stop work without new evidence. Both prospective outcome seals and the
uninstalled technical release remain intact; live execution remains off locally.

The earlier updates below retain their evidence lineage.

**September 10 11:16 UTC period-driver diagnostic:** the original matrix has
**38/48** receipts and four active workers. The original coordinator and reporting
handoff were polled live. The historical completion/review forecast remains
provisional; no live-start time is established.

The [six-case marked-period attribution](../reviews/2026-09-10-v89-historical-period-drivers.md)
and [portable report](../../data/logs/research/bidirectional_cohort/v89_historical_period_driver_diagnostics_20260910_v1/report.html)
are complete. Gross weakening explains most of the earlier-to-later decline.
Full-fee fees per day fall, although the later fee bills deepen losses. SNDK
contributes 61.15% of control and 81.97% of equal-allocation daily deterioration.
Entries fall 14.73%, from 3.93 to 3.35 per calendar day. The earlier/later windows
remain the original 28/20-day historical periods.

Research source c72682e passes 104 worktree and archive tests; new modules have
148/148 statements and 48/48 branches covered. The evaluation authenticates
2,353 references. Independent raw-account Decimal arithmetic reconciles 1,302
values with a maximum residual below $0.000000000003. All 65 report aggregates
match the retained calculations and actual local SQL projections; packaged
browser/source verification passes at desktop and narrow widths.

Journal revision
`677a81b8aa11494b5fa1ecbee1a743c647a3db3743a33ede8abea0339ae1d5c2`
has all 21 fields and 53 direct references verified. Retain this descriptive
diagnostic without choosing an allocation or removing an asset. Next trace SNDK
long concentration, entry evidence and exit paths, reusing earlier clock/stop
research rather than repeating accepted studies. The original 48-case work,
both prospective seals and the uninstalled technical package remain unchanged.

The earlier updates below retain their evidence lineage.

**September 10 10:22 UTC XYZ-history comparison:** the original matrix has
**34/48** completed receipts, four active workers and its original coordinator
and reporting handoff active. Sessions 33137 and 44667 were polled live. Free
disk is 7.74 GB; no local live backend or TUI matched.

The [original adverse-cost XYZ-history comparison](../reviews/2026-09-10-v89-adverse-xyz-history-comparison.md)
is complete for cases 4/16 and 5/17. The new account analyses finish at 10:13:55
UTC; sessions 77458, 91301 and comparison session 96911 are terminal and
successful. All 177 ordered trades, entry prices, exit times, quantities,
holding periods, funding and capital exposure agree per allocation. Reported
proposal dispositions are byte-identical; other economic sections retain small
numeric differences rather than rounding them away.

Twenty-six stop exits per allocation differ: six SPCX, eight SNDK and twelve
Brent. An independent trace authenticates 44 provider files, finds only changed
raw stop anchors in the affected intents, and reproduces exit prices and cash.
The largest price difference is $0.0000020703; rolling-minus-full account changes
are -$0.0000012488 control and -$0.0000026781 equal. Cash residuals stay below
1.34e-12 dollars. The earlier zero-difference provider checks compared each
variant to its own reference; they did not assert equal anchors across variants.

All 2,464 unique references authenticate, all four cases conserve seven equity
totals and their fresh/retained independent audits match. Twenty other manifest
fields agree; 144 daily provider bindings change between history variants.
Ten scope tests pass with the isolated frozen-source configuration. Initial
pytest import failures are retained and excluded from validation. Journal
`fdf5d6f6e8b5de8116ff6d0d0a8ed320930366fdf22401a149781c5e592babe8`
has all 21 fields and 45 direct references verified.

Retain this completed contrast without selecting a history window by its tiny
cash difference. Next finish the original matrix and qualified full report,
then assess the complete fee/allocation/source/clock contrasts and segment and
concentration evidence together. Do not repeat the accepted partial studies
merely to show progress. Main runtime/configuration and installed TUI remain
unchanged; both prospective outcome seals remain intact. The complete-review
target remains provisionally September 10 **12:30–16:00 Eastern**, with
low-to-medium confidence and no verified live-start ETA.

The earlier updates below retain their evidence lineage.

**September 10 09:58 UTC core-revision comparison:** the original matrix now
has **34/48** completed receipts, four active workers and its original coordinator
and reporting handoff active. Sessions 33137 and 44667 were polled live. Free
disk is 8.47 GB; no local live backend or TUI matched.

The [original adverse-cost core comparison](../reviews/2026-09-10-v89-adverse-core-revision-comparison.md)
is complete for cases 4/28 and 5/29. The two new analyses finish at 09:50 UTC;
sessions 37395, 6066 and comparison session 67882 are terminal and successful.
All 177 ordered trades and canonical serialized path, trade, group, concentration
and proposal-disposition sections match exactly within each allocation. No prices,
fees, funding, PnL, exposure or reported proposal dispositions change. This extends
the earlier older-replay first/latest result to the current complete account engine
and equal-allocation counterpart; it supplies no additional financial advantage.

Nineteen non-source manifest fields match per contrast. Route execution, units,
funding and counts match; declared core price/canonical bindings change, while
XYZ keeps its physical inputs. All 2,516 unique references authenticate, and all
four cases conserve seven equity totals with matching independent audits. Separate
section hashes reproduce the economic equality. The journal revision
`0876adec09206ee71ff8d877626907e6f6b9a75c9c5bf614a88677d7c58b7776`
has all 21 fields and 34 direct references verified. Main runtime/configuration
and installed TUI remain unchanged, and both prospective seals remain intact.

Retain the completed comparison; do not repeat it merely to show progress. The
remaining predeclared XYZ-history axis can be inspected while the original matrix
and full-report handoff continue. The complete-review target remains provisionally
September 10 **12:30–16:00 Eastern**, with low-to-medium confidence and no verified
live-start ETA.

The earlier updates below retain their evidence lineage.

**September 10 09:40 UTC higher-fee clock comparison:** original cases 10/11
are now independently analyzed and [compared with cases 8/9](../reviews/2026-09-10-v89-full-fee-exit-clock-comparison.md).
The two new analyses finished successfully around 09:30 UTC; sessions 15529 and
56172 are terminal. The comparison session 97445 is terminal and successful.
No native replay was repeated.

Both allocations preserve all 177 ordered trade identities and every non-clock
field. Fifty-six exits move 899,999 ms, thirteen move 59,999 ms, and 108 remain
unchanged. Mean holding increases 4.81920 minutes; average gross exposure rises
0.7325% for control and 0.7481% for equal. Fees, funding, prices, net results and
maximum marked drawdown remain identical. This measures the modeled exit-clock
convention and provides no adverse-live-fill or additional profitability proof.

All 2,321 unique references authenticate; each new case checks 2,294 references,
and all four cases conserve seven equity totals with matching fresh/retained
independent audits. Separate arithmetic reproduces every timing/holding change.
Qualified reporter source is unchanged. The journal revision
`5ca7cd0154b0f3673158d0bd5078b4b4952b5f991e544398ab6fdf7fa900bb67`
has all 21 fields and 29 direct evidence references verified. The new 6.99-minute
late-clock runs remain consistent with the full-report four-to-six-hour allowance.

At 09:39:58 UTC the original matrix still has **30/48** receipts, four active
workers and the original coordinator/handoff active. Sessions 33137 and 44667
were polled live. Free disk is 8.62 GB; no local live backend or TUI matched.
Main runtime/configuration and the installed TUI remain unchanged. Preserve both
prospective seals. Next finish the remaining original cases and qualified full
report; do not repeat this accepted partial analysis merely for progress. The
review target remains provisionally September 10 **12:30–16:00 Eastern**, with
low-to-medium confidence and no substantiated live-start ETA.

The earlier updates below retain their evidence lineage.

**September 10 09:25 UTC execution-time forecast:** 30/48 receipts are complete,
with four workers active and fourteen queued. The [measured operational forecast](../reviews/2026-09-10-v89-historical-completion-forecast.md)
uses 27 comparable completed runtimes and preserves original case order. Its
worker-finish scenarios span 08:22–09:15 Eastern; the revised complete-review
planning target is September 10 **12:30–16:00 Eastern**, with low-to-medium
confidence. Final authentication and resource changes remain uncertainties.
Free disk is 9.26 GB; remaining retained output is 3.37 GB at the largest observed
case size. These are scenarios, not hard future bounds or a live-start ETA.

While the original jobs continue, the already complete predeclared higher-fee
late-exit-clock cases 10/11 are being analyzed using unchanged reporter 3400457.
Their outputs will be compared with cases 8/9. This is partial progress on an
original contrast, not a replacement for the complete 48-case report. The clock
convention is not arbitrary venue latency or adverse fill-price simulation.
Evidence root: `v89_full_fee_exit_clock_comparison_20260910_v1/`.
Both prospective seals and the live deployment state remain unchanged.

The earlier updates below retain their evidence lineage.

**September 10 09:09 UTC prospective collection-integrity update:** the original
matrix has **30/48** completed receipts. The original coordinator and reporting
handoff remain active with four historical workers; sessions 33137 and 44667
were polled live. Main source/configuration and the installed TUI are unchanged.

The [independent timestamp audit](../reviews/2026-09-10-v89-prospective-collection-health.md)
authenticates 11,017 committed raw requests and reconciles all 21,776 first
candle/funding identities with the two SQLite snapshots. All four coverage
sections per asset match the saved 08:58 UTC health clocks. Mature prospective
rows have zero missing or late observations. Warmup first-receipt delays remain
separate. Both original collector PIDs/locks and 26 source pins plus two protocols
match before/after; no prospective market values or trading outcomes are evaluated.

The timing module passes 26 synthetic tests with 97/97 statements and 44/44
branches covered. Archive membership and in-place reproduction pass. The
[portable reproduction addendum](../reviews/2026-09-10-v89-prospective-health-reproduction.md)
corrects the first helper's absolute-path comparison: reproduce_v2.py obtains
identical results from 40 unchanged copied evidence files. Original evidence
and the first journal revision are retained. Latest revision
`f96eb1f962d78a494e5bf7adf1573186c4ff6e69566287770ba01a2df945f30b`
has all 21 fields and 33 direct references verified.

This completes the current bounded collection audit; do not repeat it without
new drift, coverage or fault evidence. Keep both economic outcome seals intact.
Next complete the original historical matrix and full report, then finalize
the concrete deployment decision. Review ETA remains provisionally September 10
13:00–19:00 Eastern; no live-start ETA or financial improvement is established.

The earlier updates below retain their evidence lineage.

**September 10 08:32 UTC combined deployment-review update:** the original
matrix has **26/48** completed receipts, four active workers and the reporting
handoff waiting on its original coordinator. Sessions 33137 and 44667 were
polled live. Free disk is 10.04 GB; no local live backend or TUI matched.

The [combined technical proposal](../proposals/v89-technical-release-20260910/recommendation.md)
is now concrete, with its [verified rehearsal](../reviews/2026-09-10-v89-combined-deployment-review.md).
The package contains 33 implementation files and 19 tests/fixtures from f00b6b8,
plus the accepted TUI binary. In a new detached rehearsal checkout, all 52 paths
and complete code/config/test scope matched the candidate after application.
Compatible rollback restored the prior package and binary while retaining only
qualified sol_order_restart.py. Its Python baseline and recovery-reader bytes
match the prior flat fake-venue proof. Open-position rollback remains unqualified.
Main source/configuration and the installed TUI remain unchanged.

The packet independently restores 104 files, including before/after source and
both binaries, with exact contents and modes. All 530 pinned provider Python
files and ten SDK source files match. The previously accepted 602 Python and
544 Rust tests were reused after proving relevant source equality; no accepted
suite was repeated merely for packaging. Journal revision
`8b7fa6e540c7cece7a2ed6e60b62fde0940cc81e64b8ce5b0d3dc8ec1b35d2dc`
has all 21 fields and 35 direct references verified.

The reviewed runbook specifies static verification, exact pending approval scope,
fresh prestart ownership/account evidence, coordinated source/binary loading,
nine-view TUI acceptance, reporting observation and history-preserving rollback.
No deployment, process transition or live activation was authorized or performed.
Do not rerun this completed rehearsal or mutate its retained artifacts. Its
isolated checkout is intentionally left in the compatible rollback state.

Next finish the original 48-case matrix and qualified full report. While those
jobs continue, check the two prospective collectors' current process identity,
heartbeat, source pins and collection coverage only; their outcomes remain sealed.
The last collector PID inventory was September 10 01:10 UTC and the earlier
full heartbeat/source check was September 9 13:32 UTC. Do not reconstruct signals,
positions, trades or returns. Replay/report timing remains the prior provisional
September 10 09:00–13:00 / 13:00–19:00 Eastern ranges; live-start timing remains
unestablished and requires the remaining evidence and explicit selected scope.

The earlier updates below retain their evidence lineage.

**September 10 08:16 UTC current venue-specification update:** the original
matrix is now **24/48** complete, with four active workers and reporting handoff
PID 79587 waiting on coordinator 72423. Sessions 33137 and 44667 were both
polled live in this turn. Free disk is 10.41 GB; no local live backend or TUI
matched the final process inventory. Preserve the original matrix/report sources.

The [fresh specification qualification](../reviews/2026-09-10-v89-current-venue-specification.md)
reconciles all seven asset identities and 30 direction rows across the unchanged
live and inactive control/equal profiles. Requested leverage fits current tiers;
configured venue maxima and size precision match public metadata. Official SDK
IDs match an independent dex/index calculation. XYZ IDs 10/20 use the explicitly
documented builtin margin rule; optional margin-mode flags remain unreported.
No current account state, native order acceptance, liquidity, fees or profitability
was established. This sample indicates no venue-limit, sizing or routing correction.

All 56 focused tests pass in working and frozen source, with matching identities
and coverage. Specification logic covers 77/77 statements and 32/32 branches;
the independent auditor covers 88/88 statements and 10/10 branches. All 275
archive files and 242 actually imported analysis/SDK modules are byte-verified.
No unexpected socket event occurs under the tested network guard. Journal
revision `e1e1edf07415bb87eca494da8deedb2a936631527c213181781b16d6d92fcdb3`
has all 21 fields and 36 direct references verified. Main source, three profiles,
and installed TUI remain unchanged. No live start or deployment was performed.

The next economic action remains completing all original matrix cases and the
qualified full report. Replay is provisionally 09:00–13:00 Eastern September 10;
full reporting is 13:00–19:00 Eastern, with low-to-medium confidence and fresh
execution/TUI acceptance additional. No live-start ETA is established. Prepare
the exact combined technical deployment/rollback review from the already
qualified candidates without re-running accepted suites or changing live files.
Both prospective outcome seals remain intact.

The earlier updates below retain their evidence lineage.

**September 10 07:43 UTC coverage qualification update:** the original
coordinator remains active with **22/48** completed cases and four workers.
The reporting handoff remains active; preserve sessions 33137 and 44667 and
all original replay/reporting sources. Free disk is 11.06 GB after the verified
coverage-cache cleanup. No local live backend or TUI matched.

The [coverage-qualified test candidate](../reviews/2026-09-10-v89-entry-deadline-tui-coverage.md)
is frozen as `f00b6b8d22cf59285a313b7de1166cccecbe52ca`, with runtime source
unchanged from `b73b112`. Checkout and archive both pass 544 release tests,
with the same 23 runtime-dependent tests ignored and identical test identities.
All 5,156 Git blobs match. The decoder and display helper have 130/130 and
43/43 measured lines covered; regions are 183/185 and 58/58. The changed
integration functions and predicate closure cover 54/54 regions. These exact
metrics reproduce from the archive. Branch and MC/DC metrics are unavailable;
this is scoped coverage, not a whole-TUI or live-acceptance claim. Clippy and
formatting pass. Journal revision
`f4e05d5c78baf4da3921148eb90a0cc25c0e8e9bb6b5d3314c9f34bb82a46902`
has all 21 fields and 44 direct references verified.

The temporary coverage target was backed up, independently restored and all
1,571 entries verified before removal. The retained archive is 166.32 MB;
cleanup showed 601.19 MB additional free space. Exact test binaries, profiles,
source archives and reports remain. Do not recreate the completed coverage
cache or rerun these accepted checks without a new change or failure.
The [original TUI qualification](../reviews/2026-09-10-v89-entry-deadline-tui.md)
retains its configured inspector captures and the September 4 V86 fixture.
The installed TUI remains unchanged at
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.
Next perform a public venue/configuration-specification check, while preserving
both prospective outcome seals, then finish the complete original matrix and
report for the combined deployment review. No live change is authorized here.

The [full-fee allocation comparison](../reviews/2026-09-10-v89-full-fee-account-comparison.md)
is complete and journaled. Control returns -$33.44 (-0.69%) with $233.56 maximum
marked drawdown; equal returns +$92.00 (+1.89%) with $365.68 drawdown. Both have
177 closed trades, 66 wins and 111 losses. Later segments are -$137.03 and
-$158.60. The full-period equal-allocation difference is +$125.43, with $132.11
more drawdown and 2.0236 times average gross exposure. Each case authenticates
2,297 references and seven equity totals. The higher entry fee also moves one
modeled SNDK liquidation price; independent collateral arithmetic explains
that gross-price effect, and all other non-fee trade fields match. The journal
revision is `53fde070dd6f0a1bc2168a3722c70274e9b25c5cde9b83230aa0c0727e2e5247`;
all 21 fields and 25 direct references are verified. Both case analyses are
terminal; do not rerun sessions 16258 or 19954.

The [Python technical integration base](../reviews/2026-09-10-v89-technical-release-integration.md)
was frozen as `71fbf0541fd1360e726f49b7de89ae905912020c` in the isolated technical
release checkout; its Python, scripts and profiles are unchanged in the new TUI candidate. Its 26 implementation files preserve the exact deadline,
mapped-reader and staging proposals. All 602 focused tests across 56 modules
pass in the worktree and retained archive, with identical test identities and
no unexpected Python socket events. All 5,144 Git blobs and 530 adjacent provider
sources match before and after archive testing. This is journal revision
`5d8d234f53ef20c2655206b60e340f8cdba8ec15efeab9757880cb2cee3454b7`;
all 21 fields and 19 direct references are verified. Main source/configuration
and the installed TUI remain unchanged. No combined deployment is authorized.

New retained timing observations put sequential full reporting at about
4.37 hours before additional overhead. Use **4–6 hours after replay**
as a low-to-medium-confidence planning range, not a statistical interval.
Together with the existing 09:00–13:00 Eastern replay estimate, the first full
historical report is provisionally **13:00–19:00 Eastern September 10**.
Reproduction, deployment approval and live acceptance are additional and have
no established ETA. The timing basis and caveats are retained in
`v89_full_fee_historical_account_comparison_20260910_v1/reporting_duration_estimate.json`.
Both prospective outcome seals and the complete original 48-case scope remain
intact. Next finish the remaining original source/timing cases and the complete
report before a concrete deployment recommendation.

The earlier updates below retain their evidence lineage.

**September 10 05:23 UTC reporting-handoff update:** the original matrix has
**8/48** completed cases and four active workers. The qualified
[reporting handoff](../reviews/2026-09-10-v89-complete-reporting-handoff.md)
is now waiting as PID 79587 / session 44667 on original coordinator PID 72423.
Its ownership lock is held; 25 focused tests pass in both worktree and retained
source (94% statement coverage). Real preflight authenticates 1,951 references.
After original producer completion it invokes unchanged reporter 3400457 for
all 48 cases. It cannot restart replay or promote a strategy. Preserve its
operator and source while active. Free disk is 14.95 GB; no local live backend,
checkpoint writer or TUI matched. Replay is estimated around 09:00–13:00 Eastern
September 10, medium confidence; final reporting/reproduction are additional.
No go-live ETA is established. Both prospective outcome seals remain active.

The earlier updates below retain their findings and evidence lineage.

**September 10 04:58 UTC storage and primary-comparison update:**
the original matrix now has **7/48** completed receipts and four active workers.
Session **33137** / coordinator PID 72423 remains active; workers at 04:55:31 UTC
were 76470, 76472, 76810 and 77207. The initial four coordinator-launched workers
finished in approximately 39.99, 41.07, 50.38 and 50.62 minutes. Their inferred
start times and receipt timestamps are retained in
`v89_matrix_resource_diagnosis_20260910_v1/first_batch_timing.json`.
This supersedes the incomplete-prefix estimate: remaining replay is approximately
**8–12 hours at four workers**, with medium confidence and final reporting and
reproduction additional. Larger variants or resource contention can extend it.

The [worktree cache recovery](../reviews/2026-09-10-v89-worktree-storage-recovery.md)
resolves the current matrix capacity shortfall. Both inactive debug trees were
completely archived, their 114,230 source entries reverified, then only those
backed-up trees removed. Observed cleanup increases total 13.59 GB; the retained
archives occupy 3.95 GB. Available disk was 15.67 GB at 04:55:31 UTC. The installed
release TUI hash is unchanged, and no research data, live ledger or configuration
was removed. An additional drive is no longer needed for this run at measured
case sizes. Recovery is journaled as database revision
`9ba38172a938d68a98130c87e160d231dc056da77c9d3e12671b5c28165596e6`;
all 21 fields and 20 references match, including both retained archives.

The [fixed primary adverse-cost pair](../reviews/2026-09-10-v89-primary-adverse-account-comparison.md)
is complete and independently reconciled. Control returns +$95.72 (+1.97%) with
$198.28 drawdown; equal allocation returns +$368.92 (+7.59%) with $287.72 drawdown.
The same 177 closed trade identities occur in both, with 40.68% wins. Equal
allocation adds $273.20 net and $89.44 marked drawdown with 2.0236 times average
gross exposure. Later 20-day results are -$87.24 and -$51.87. Removing the three
largest winners leaves -$132.05 and -$119.81. These are sensitivity diagnostics,
not implicit gates, and the full matrix is still required.
This comparison is database revision
`8a99c663a2e0662ffb953d92143e8bdf1633df1e1833a2b54f88987e42a2747b`;
all 21 fields and 16 direct references match. Each case separately reauthenticates
2,297 references and conserves seven equity totals.

Cases 04/05 and their analyses/verification are complete; do not rerun sessions
45167 or 30353. Both cache archives, verifiers and cleanups are complete. Preserve
the backups and operator evidence under `v89_worktree_debug_recovery_20260910_v1`.
No live backend, checkpoint writer or TUI matched the 04:55 process inventory.
Both prospective seals remain intact; no live-start ETA or live change is claimed.
Next finish the registered full HIP-3 fee and remaining source/timing cases,
then publish the complete authenticated 48-case analysis using frozen reporter
3400457. Avoid changing the active 69dd84a engine or 2486adf coordinator.

The older job states below are retained lineage, superseded by this update.

**September 10 04:20 UTC active-matrix update:**
the [resumable coordinator](../reviews/2026-09-10-v89-resumable-account-matrix.md)
is frozen as `2486adf`, with 55 passing tests in both worktree and verified
archive, plus the real registered-source preflight. All three original completed
cases were adopted with fresh independent audits. Session **33137** remains
active: coordinator PID 72423 and four workers 72894, 72895, 73247 and 73270.
Do not duplicate or restart them. All 48 original cases remain required.

The [initial account comparison](../reviews/2026-09-10-v89-initial-account-comparison.md)
authenticates 2,303 unique references and seven equity totals per case. Equal
allocation returns +$491.17 (+10.11%) versus control +$196.85 (+4.05%), alongside
2.0209 times average gross exposure and drawdown $264.87 versus $140.67.
Both contain the same 177 closed trade identities, with 41.81% wins. Removing
the equal case's three largest winners leaves +$0.27. The nominal control late
clock retains the same net return and drawdown, with 68 changed exit timestamps.
These three cases do not establish a dependable improvement or live readiness.
The comparison journal is database revision
`267a25b8eb5e43c1d04efd68cd2ff6bd9a69896bf209b4ad0bfbf01845fc653a`;
all 21 fields and 16 direct references match the retained record.

The [backup block-sharing operation](../reviews/2026-09-10-v89-backup-block-sharing.md)
preserved all 36.85 GB of historical backup bytes and checked metadata, with a
verified recovery image retained before replacement. Twenty tests pass in both
worktree and retained source. The current database remained unchanged during
that operation. No physical storage savings are established. Do not repeat this
capacity hypothesis without new evidence or remove either historical image.
The later authorized journal append updates the current research database.
Free space was 5.13 GB at 04:18:36 UTC; another-drive question remains pending.

At 04:20 UTC the first two active workers had 23,214/69,121 and 39,260/138,241
complete event lines in their bounded XZ prefixes, after about 24 minutes of
worker lifetime. Their XZ files remain incomplete. This supersedes the isolated
runtime estimate: a provisional 16–20 hours of remaining replay at current
concurrency has low confidence until the first parallel batch completes, with
reporting and reproduction additional. Storage or resource contention can extend
it. No matching local live backend, checkpoint writer, TUI launcher or TUI was
observed in the 04:18:36 UTC process snapshot. No live-start ETA is established.
Both prospective seals remain intact. Next complete the original adverse-cost
comparisons and all remaining cases; no live process or configuration changed.

The older job states below are retained lineage, superseded by this update.

**September 10 02:25 UTC completed-account update:**
the [first complete historical account](../reviews/2026-09-10-v89-first-complete-account-result.md)
finished at 02:02:46 UTC, analysis at 02:10:14 UTC, and retained verification at
02:20:24 UTC. Sessions 91963 and 38167 are complete; do not restart them.
Nominal control: +$196.85 (+4.05%), 177 closed trades, 41.81% wins, maximum marked
drawdown $140.67 (2.74%). Earlier 28 days: +$214.58; later 20 days: -$17.73.
Removing three largest closed winners leaves -$31.83. This is one of 48 cases,
not a complete comparison, prospective result or evidence of live improvement.
Both independent audits agree; 2,281 references and seven equity totals reconcile.

Measured account/audit runtime is 1,931.31 seconds, setup 199.62 seconds, peak RSS
15.75 GiB and complete case output 184,712,040 bytes. Four-worker full-matrix
runtime projects to roughly 6.5 hours before reporting and reproduction, with
medium confidence. Output at this case's size projects to 8.87 GB before overhead;
available disk is 5.01 GB. The alternate-storage question remains pending.
No matching local live backend, checkpoint writer, TUI or account replay worker
was observed. The full matrix has not started; no live-start ETA is established.
Preserve the original 48-case scope and completed evidence. Next resolve output
storage and execute all cases, followed by authenticated comparison and reproduction.

The older job states below are retained lineage, superseded by this update.

**September 10 01:55 UTC reporting and resource update:**
the [complete reporting pipeline](../reviews/2026-09-10-v89-complete-account-reporting.md)
is frozen as `34004579e2cb21d13c55e01c47fa6f69e70d76ff`. All 199 integrated tests
pass in the worktree (186.28 seconds) and verified archive (188.20 seconds), with
998/1,030 measured statements covered. Archive session **20419** returned zero;
all 5,574 regular files and 1,933 implementation members were rechecked afterward.
Session 12717 is also complete. Do not repeat those runs without changed evidence.
Use `v89_historical_account_reporting_qualification_20260910_v1/verified.json`.

The archive repair is [journaled](v89-canonical-archive-layout-repair-20260910-v1.json)
as database revision `d76f0a26ed8f098b136a8317717457ebae89f8cb2c1c0b023c32d0e0db9b07c7`.
All 1,255 references, 21 database fields and three journal copies match as checked
at 01:48:25 UTC. The new research review and journal are now pinned evidence.

The real first case remains active as **91963 / PID 62107**. At 01:48:30 UTC,
an explicitly bounded compressed-prefix read counted 14,980 of 69,121 expected
event lines (21.7%) in 40,053,732 compressed bytes. It decoded 1,998,433,350 bytes;
no XZ footer or completed pilot report was present. This was process progress
only, without evaluating account metrics. Events and manifest now exist, so the
run has progressed beyond calendar construction. Preserve the active attempt.

Available disk was approximately 4.8 GiB at 01:51 UTC. Linear extrapolation of
that single prefix suggests roughly 9 GB for 48 event files before account and
late-clock overhead; this is a planning estimate, not measured full-case storage.
There is no additional mounted user data drive. Disposable pytest data totals only
113 MiB and the main Rust release tree 535 MiB; neither resolves the projected
shortfall. Ten retained source extractions total 2.17 GiB and their archives remain
intact; none was removed. An asynchronous question asks for an alternate drive
with at least 15 GB available. The current first case still has room and continues;
do not substitute a partial matrix or remove source evidence to fit the disk.

**September 10 01:40 UTC update:** the original canonical export is complete:
session 32156 returned zero at 01:17:49 UTC with all eight streams, 384 daily
chunks and 552,960 checks. The first waiting account attempt returned one before
simulation because its archive reader did not recognize the original `source/`
wrapper. The [archive-layout correction](../reviews/2026-09-10-v89-canonical-archive-layout-repair.md)
is frozen as `69dd84a990836c30cd56b1effa524b0e20f88acd`; all 29 relevant tests and
the full original catalog preflight pass in both worktree and verified archive.
Exactly one predecessor implementation member changes. Preserve the completed
export, failed first attempt and all qualified source archives.

The same original first 48-day account case is now running as session **91963**,
PID **62107**, under `v89_first_complete_historical_account_20260910_v2/`.
Its source assembly completed in 199.62 seconds at 01:30:35 UTC. At 01:38 UTC it
was active at about one CPU core with roughly 13.5 GiB RSS, no observed swap use
and 5.22 GiB free disk. The machine has 96 GiB physical RAM. No completed account
result or full-matrix runtime estimate exists yet. Do not restart the active
attempt or modify its operator, launch record or frozen source.

The isolated reporting worktree now includes the authenticated matrix catalog
reader, complete case publisher and CLI. Its 15 catalog tests and eight publisher/
CLI tests pass separately; the latter covers explicit report identity, source
conservation, fresh-versus-retained audit agreement and deterministic complete
publication. These tests use catalog and metric fixtures, not historical financial
outcomes. The real native per-case integration remains separately required.
The complete integrated reporting suite is running in session **12717**, logged
as `historical_account_reporting_integrated_20260910.log`. Preserve its Python,
lock and test sources until terminal. Current additions are not yet committed or
archive-qualified. Next finish this reporting qualification while preserving the
real account attempt, then use its measured resources to run every original case.

The older job states below are retained lineage and are superseded by this update.

The [complete account runner and resource revision](../reviews/2026-09-09-v89-historical-account-runner-resources.md)
is frozen as `a86bd6f` in
`/Users/gestas/Prototypes/hypervector-v89-history-storage-20260909`.
Its combined worktree suite passed **81 tests in 613.77 seconds**, with
541/583 measured statements covered (93%). The preceding runner `4409147`
passed 54 focused tests and **1,809 regressions** across 99 additional modules.
The resource revision changes three implementation members; the other 1,921
Python/lock members and those 99 test modules remain identical.

Lossless XZ reduced one complete two-day event stream from 16,660,872 to
1,262,280 bytes. Streaming independent reconciliation reduced observed peak
memory from 623.69 to 58.83 MiB and from 795.78 to 78.03 MiB across the two
synthetic exit clocks. Both full ledger results match, including when run from
the verified archive. These measurements do not qualify full-history resource
use, financial performance or live readiness.

The archive's full suite completed: **81 passed in 615.05 seconds**, with the
same coverage. Session **92583** returned zero and must not be restarted. Results are under
`data/logs/research/bidirectional_cohort/v89_historical_account_storage_qualification_20260909_v1/`.
All 5,549 extracted regular files, their executable bits, source-commit metadata
and 1,924 implementation members were verified before that run. Archive real-file
loader preflight session **89888** completed zero: all 14 original market cases,
580,608 prices and 16,128 funding observations match the previous raw-member
hashes and counts. Its report is `archive_market_preflight.json`.
All tests, extracted source files, original input references and complete
resource comparisons were reauthenticated after completion. This is recorded
in [runner/resource revision 1](v89-historical-account-runner-resources-20260909-v1.json),
database revision `9d964102839c2efb72a42fcc596be2787ed5070e0fc01afa5f94b0bef497b2c7`.
All 88 evidence references, 21 database fields and four journal copies match.
Preserve the frozen implementation and completed evidence.
Do not repeat the completed worktree suites or resource probes without new evidence.

At September 10 01:14:11 UTC, the waiting first-case operator confirms that the
original canonical export **32156**, parent 26037, remains active under its
original process identity. It has 379/384 daily summaries (98.7%); the final export
report remains absent. The September 9 21:00–22:00 EDT export estimate remains
a throughput estimate, not a live launch deadline. At September 10 01:10 UTC both
known prospective collector PIDs were present; no matching local live backend,
checkpoint writer or TUI was observed. The checkpoint remains generated September 8
14:04:48.752796 UTC, with file mtime 14:04:56.843048 UTC. This is not a fresh venue
account observation. Available disk was 5.43 GiB at 01:10 UTC.

The [first complete case operator](../plans/2026-09-09-v89-first-complete-account-timing.md)
is active in session **87769**, PID 52810. Its read-only check completed zero,
and its explicit research run is waiting for the original producer to finish.
It will use the qualified `a86bd6f` engine for the first predeclared full 48-day
case, then independently audit the account and measure runtime, disk and memory.
No completed pilot result or full 48-case matrix exists yet. Preserve its
`operator.py` and exclusive `launch.json` under
`v89_first_complete_historical_account_20260909_v1/`.

The separate [complete account analysis](../plans/2026-09-09-v89-complete-account-analysis.md)
worktree is `/Users/gestas/Prototypes/hypervector-v89-history-analysis-20260909`,
source `e3b55984bfeb3aef3276facb86f37598a232482c`. Its authenticated artifact reader,
path metrics and closed/open trade attribution passed **87 tests** in the worktree
(172.11 seconds) and verified archive (172.00 seconds). Coverage is 400/413 measured
statements: path and trade arithmetic 100%, reader 90%. All 1,927 implementation
members and seven pinned test/support sources remained unchanged during each run;
all 5,559 regular archive members and executable modes were rechecked afterward.
The [account analysis qualification](../reviews/2026-09-10-v89-account-analysis-qualification.md)
records the complete evidence under
`v89_historical_account_analysis_qualification_20260910_v1/`.
This is bounded synthetic reporting qualification. It retains incurred fees and
funding on open positions, reconciles all contributions to terminal equity and
preserves audited near-zero closed-result signs. The earlier 29-test path
component and its retained probes remain lineage under
`v89_historical_account_path_metrics_qualification_20260909_v1/`.
No prospective outcome, live process or live configuration changed.

Subsequent report assembly is implemented in the same isolated analysis worktree,
with its new files still uncommitted and not yet frozen or archive-qualified.
Native source-priced proposal fates conserve route exclusions and committed
account dispositions. Group reports retain all seven assets, every registered
strategy and both directions, with explicit zero-activity rows. Marked-day
concentration remains distinct from closed-winner concentration. The complete
per-case facade freshly authenticates sources and independently reconciles the
account before combining these reports. Its combined native suite completed:
**67 passed in 184.82 seconds**, covering 231/235 statements (98%). Evidence is
`historical_account_case_report_native_20260910.log` under the research log directory.

The pure 48-case comparison component now retains canonical case order and every
single-axis contrast: 144 pairs, including all three pairwise cost comparisons.
Its fixed primary allocation contrast is first/full-prefix/adverse/recorded-clock
control versus equal. Negative results survive; undefined ratios remain null.
Incomplete or duplicate cases, conflicting contracts, live authority and sealed
outcomes fail explicitly. The comparison and grouped-metric suite completed:
**32 passed in 1.84 seconds**, with 95/95 comparison and 46/48 grouping statements
covered. Evidence is `historical_account_comparisons_scope_20260910.log`.
These are synthetic arithmetic and scope tests, not historical financial results.
The final authenticated matrix publishing coordinator, its integration tests and
frozen reproduction remain unfinished. A pure metric comparison does not itself
authenticate original account files; that responsibility remains with its caller.

Next authenticate the full canonical catalog and run, independently reconcile and
reproduce the complete original 48-case historical matrix. No full historical
account outcome or profitable live improvement has been established. There is
no defensible go-live ETA. Current handoff notes are
`v89_historical_account_storage_qualification_20260909_v1/next_complete_account_notes.md`
under the same research log directory.

The preceding qualification and progress records below are retained lineage;
their earlier job states and implementation status are superseded by this entry.

The [historical calendar/native account qualification](../reviews/2026-09-09-v89-historical-calendar-qualification.md)
is complete from frozen source `d7b44cb`: **1,034 selected tests pass in both
worktree and archive**, with ten unclosed SQLite connection warnings in each.
Seven measured modules cover 564/591 statements (95%); this is bounded mechanics
validation, not full-system or resource-lifecycle qualification. Both original
regression sessions 44606/32391 returned zero and must not be restarted.

All 1,916 Python/lock implementation members remain unchanged in both source
trees. The fixed 35-day first-source canonical prefix reproduces byte-for-byte:
201,600 observations, 57 missing-current and 6,470 UNKNOWN. All 291 references
were reauthenticated after the suites finished. The completed qualification is
[journaled as revision 1](v89-historical-calendar-binding-20260909-v1.json).

The separate implementation in
`/Users/gestas/Prototypes/hypervector-v89-history-runner-20260909` now includes
the complete-export catalog, original-file loader, account-source assembler,
full account runner, independent committed-ledger audit and 48-case coordinator.
It remains uncommitted integration work outside the frozen qualification.
Its combined focused suite completed: **54 passed in 299.51 seconds**, covering
520/569 measured statements (91%). The independent audit module alone measures
77%; the aggregate is not a claim of complete fault-path coverage. Both
two-day synthetic clock controls reconcile and reproduce every output byte.
These synthetic checks do not qualify full historical financial outcomes.

The original-file preflight completed September 9 22:14:34 UTC. All fourteen
market cases match the preceding qualification's raw price/funding members:
580,608 prices and 16,128 funding observations. Original provider registrations,
snapshot and initial files authenticate. Complete canonical export qualification
remains pending; later venue captures remain explicit historical assumptions.
Evidence is under `data/logs/research/bidirectional_cohort/` in
`historical_account_runner_focused_20260909.log` and
`v89_historical_account_runner_preflight_20260909_v1.json`.

Additional regressions across **99 affected test modules** started September 9
22:24:42 UTC in session **67677**, with results under
`v89_historical_account_runner_regressions_20260909_v1/`. They were still running
at 22:25 UTC. Preserve that job and leave the tested Python/lock and test sources
unchanged. Next finish technical qualification, freeze and reproduce this runner,
then time the first full historical account case and complete all original 48
comparisons. No complete historical financial result or profitable live fix is
established. The original
[full account plan](../plans/2026-09-09-v89-gap-market-account-followup.md) remains
in force; do not repeat completed source probes without new evidence.

At September 9 22:22:39 UTC, canonical export session **32156**, parent PID 26037,
remains active. All four first-source streams have 48 daily summaries; last-source
counts are BTC 8, ETH 7, SOL 7 and HYPE 7. Thus 221/384 daily summaries are present
(58%), but the complete eight-stream report is absent. Roughly three more hours
for the export is a medium-confidence throughput estimate, not a launch deadline;
slower remaining work or an export failure would change it. Preserve the export.
Both previously identified prospective collector PIDs remain present. No matching
local trading backend, checkpoint writer or TUI is found; checkpoint file mtime
remains September 8 14:04:56 UTC. This does not refresh venue positions or account
PnL. Both outcome seals remain intact, and no live configuration or process was
changed. A defensible go-live ETA is not yet available.

The preceding completed entry qualification and retained lineage follow.

The [historical entry and venue binding](../reviews/2026-09-09-v89-historical-entry-venue-binding.md)
is reproduced from `7f690ac`: 555 selected tests passed in both worktree and
verified archive, with 198/200 measured statements covered. The original
seven-asset venue report reproduces byte-for-byte; all 42 independent field/type
checks agree. September 8 captured size/leverage units remain explicit static
assumptions, with historical availability unverified. See
[entry binding revision 1](v89-historical-entry-binding-20260909-v1.json).

The subsequent completion projection has 195 passing focused/calendar tests,
but complete historical calendar assembly and native decision-time routing are
unfinished. Continue the full original account plan, preserving every source,
cost, clock and allocation case. No revised historical return or profitable
live recommendation is established.

At September 9 20:29 UTC, the original canonical export parent and both source
collectors are present. The last independently verified canonical prefix is
122,400 checks in 85 complete daily chunks at 19:56 UTC; the full export remains
unfinished. Preserve that job and both prospective outcome seals. No local
trading backend, checkpoint writer or TUI is found; the checkpoint remains
September 8 14:04:48 UTC. This does not refresh venue positions or account PnL.

The preceding native holding qualification and retained lineage follow.

The [native HYPE holding correction](../reviews/2026-09-09-v89-native-hype-hold-qualification.md)
is independently reproduced from `5fcb533`: 363 account regressions plus five
oracle tests pass in the worktree, and all 368 pass in its archive. Every one
of 69,984 synthetic policy combinations agrees with independent Fraction
arithmetic; complete comparison files are byte-identical. Provider/canonical
observations remain independent, observed UNKNOWN follows the native policy,
and original accepted-entry clocks and protective-stop precedence survive.
See [holding revision 1](v89-native-hype-hold-20260909-v1.json).

This supersedes the earlier unsupported-UNKNOWN limitation for native synthetic
account routing. It does not establish historical financial improvement. New
historical venue-unit and entry bindings are being implemented separately.
Finish the full original account matrix and independent canonical history;
retain both prospective outcome seals. The original canonical job is confirmed
live in exec session 32156 and has not been restarted.

The preceding completed market-input qualification and retained lineage follow.

The [complete historical price/funding binding](../reviews/2026-09-09-v89-historical-market-binding.md)
is qualified from source `c55c04b`: all fourteen price cases, 580,608 prices and
16,128 funding observations reproduce from the verified archive. All 67 focused
tests pass in both trees. Original provider grids remain separate from 152
explicit continuity rows (76 per source variant); all funding references use
retained candle prices. The named timestamp-index reader defect is corrected.
See [market binding revision 1](v89-historical-market-binding-20260909-v1.json).

Next connect these tables to native entry sizing, actual decision-time positions
and configured exits under the full account plan. Historical venue precision,
complete canonical history and HYPE UNKNOWN compatibility remain required.
At 18:43:31 UTC, canonical parent PID 26037/four workers remain alive in exec
session **32156**. Twelve complete chunks contain 17,280 independently checked
observations; the full export is unfinished. Preserve the job and both outcome
seals. The source/probe jobs for this market qualification are complete.

The [market binding and canonical export startup](../reviews/2026-09-09-v89-market-binding-canonical-export-start.md)
is recorded from source `c02c9c6`: 39 focused tests pass in source and archive;
all eight real initial canonical payloads match. At September 9 18:24:42 UTC,
the complete historical canonical export is running with four workers, parent
PID 26037, exec session **32156**, and zero finished daily chunks. Preserve the
job under `v89_historical_canonical_history_20260909_v1`; do not restart it.
Original real-history market binding and full native account outcomes remain
unfinished. Next join those inputs while the independent canonical export runs,
preserving the complete account plan and both prospective outcome seals.
Startup free disk is 7,505,145,856 bytes; monitor output growth and source health.

The [historical publication binding](../reviews/2026-09-09-v89-historical-provider-binding.md)
is qualified as an account input: all 580,608 publications across fourteen
unique streams retain native admission, complete exits, original gaps and
explicit modeled timing. The final frozen source `28c1b34` reproduces the
complete binding report and the recovered initial publications; 338 tests pass
in both worktree and archive. All fourteen initial provider publications and
eight core canonical observations bind with zero initial entry intents.
See [binding revision 1](v89-historical-provider-binding-20260909-v1.json).

Next assemble the complete historical price/account calendar, keeping original
provider grids separate from observed-market evidence and explicit conditional
price proxies. Whole-history canonical availability and HYPE UNKNOWN soft-hold
handling remain required. Preserve all 48 days and original source/cost/clock/
allocation cases; these input checks are not account outcomes or live changes.

The preceding complete-history qualification and retained lineage follow.

The [complete provider history](../reviews/2026-09-09-v89-complete-provider-history.md)
is now independently verified: 552,960 core checks in 384 daily chunks and
27,648 XYZ quarter checks plus 6,912 archived hours in 288 chunks, with zero
differences. Final reports, manifests, frozen implementations and source inputs
reconcile. The original jobs are complete; do not restart them.

All four complete source pairs pass authenticated payload decoding: each has
69,120 minute sets, 290,304 provider records and 295 entry intents. Raw-to-typed
publication fields and raw comparison/intent relationships reconcile exactly.
These are source observations, not routed positions, trades or account returns.
The initial July 21 boundary now has 14 native provider and eight core canonical
publications, independently reproduced from direct SQL source reads and an older
frozen archive. XYZ warmup/canonical limits and original source gaps remain explicit.
See [complete-history revision 1](v89-complete-provider-history-20260909-v1.json).

Next implement explicit historical availability at the provider/account boundary,
keeping the native signal grid separate from conditional execution prices. Supply
required canonical history and preserve all 48 days, original source/cost/clock/
allocation cases, native decision positions, configured exits and terminal open
positions. The [account plan](../plans/2026-09-09-v89-gap-market-account-followup.md)
remains the complete scope. HYPE UNKNOWN soft-deadline compatibility and full
historical dynamic account outcomes remain outstanding.

Prior checkpoint and retained lineage follow; the complete-history finding above
supersedes earlier progress counts and initial-boundary omissions.

The [missing-candle market study](../reviews/2026-09-09-v89-gap-market-observations.md)
qualifies separate observed quotes for both unmatched August 1 SOL minutes.
Each has 131 book observations, no observed public trades and one sparse mark.
Missing candles do not establish a flat market or absent quotes; exact fills and
continuous stop paths remain unresolved. Original provider grids are unchanged.
Source `f2808cc` passes 126 offline tests in worktree and archive; both reports
reproduce exactly, and all 24 consumed references are reauthenticated.
See [source-gap revision 2](v89-historical-source-gaps-20260909-v2.json), which
preserves revision 1 and its 76 account/21 warmup gap qualification.

The original core comparison finished September 9 at 16:08:41 UTC. Its completion
log reports eight streams, 552,960 checks and zero mismatches. Independent final
payload verification remains outstanding. Do not restart the completed job.
Next follow the [complete account qualification plan](../plans/2026-09-09-v89-gap-market-account-followup.md):
authenticate final provider outputs, qualify the initial boundary and explicit
market availability, then assemble the complete dynamically sized native account.
Preserve all 48 days and every original source/cost/clock/allocation case. No
economic result or live state was refreshed by this source-only study.

The [typed native account integration](../reviews/2026-09-09-v89-typed-native-account-routing.md)
is frozen as `585b484747b33acd948bff5c38f090f896e58418`: 341 tests pass in both
worktree and archive; all 96 diagnostic artifacts reproduce exactly and their
account values match the previous diagnostic. Its 2,880 native cycles preserve
actual decision-time positions and complete controller payloads. Independent
Decimal checks total 5,328. Native entry admission/ranks and reconciled configured
close prices now drive the research account; publication is atomic.

Complete two-day synthetic tests cover both HYPE holding deadlines and clocks,
open terminal positions, and protective-stop precedence. UNKNOWN at the HYPE soft
boundary still fails explicitly without account mutation. These are bounded
research findings, not historical profits, live changes or complete evaluator
qualification. See [revision 2](v89-native-account-routing-20260909-v2.json).

Next, qualify historical source gaps before complete dynamic account assembly.
Core account-window missing minutes are BTC 18, ETH 20, SOL 19 and HYPE 19 in
both first/last variants. XYZ quarter bars cover the account window completely,
with the previously declared short warmup. Preserve all 48 days and original
axes; retain missing intervals explicitly instead of silently replacing sources.
The [source-gap plan](../plans/2026-09-09-v89-historical-account-source-gaps.md),
original [integration plan](../plans/2026-09-09-v89-native-account-routing-integration.md),
and preceding [diagnostic](../reviews/2026-09-09-v89-native-account-entry-boundary.md)
retain the full scope and lineage.

Journal revision 22 qualifies native configured-exit routing compatibility from
`9e3ecac3d5a63564e2065052c0bbaaa340b2d006`: 748,800 exact hypothetical cycles,
zero native differences and independent reconciliation to raw provider publications.
See the [routing review](../reviews/2026-09-09-v89-native-configured-exit-routing.md)
and [revision 22](v89-equal-cap-prospective-20260909-v22.json).

Two first-core/XYZ history pairs cover all 48 days, July 21 through September 7.
Each supplies 69,120 minute sets, 290,304 provider records, 295 entry intents and
1,605 evaluations with exit flags. Two last-core pairs cover the common four-day
prefix through July 25, each with 5,760 minute sets and 29 intents. These are
provider observations repeated across explicit hypothetical position contexts,
not executed trades or account returns. All four full 48-day pairs remain required.

The shared native decoder now preserves target anchors, numeric types and all
complete evaluation/readiness fields. Configured native closes, timer/recipe/
profit scopes, fresh publication order, source withholding and entry-only ranks
are preserved by the routing projection. All 221 focused tests are recorded as
passing in worktree and archive; all 178 statements and 50 branches in the three
measured modules are covered. All 5,421 archived Git blobs/modes remain exact.
The independent verifier reauthenticates 1,088 consumed references and rejects
mutated target anchors, entry ranks, omitted withholding and duplicate entries.

Next, continue the original [historical routing plan](../plans/2026-09-09-v89-historical-routing-qualification.md)
by integrating native routing at the actual decision-position boundary, after
earlier-bar exits and before current-opening exits/risk. Join native actions to
source-priced entry plans; retain every withholding reason and rank. Reconcile
configured closes against original frozen pending-exit/holding semantics before
applying account events. Preserve source decision, knowledge and model clocks.
The account must carry dynamic equity, rounded size, fees, funding, barriers and
terminal open positions across the fixed source/cost/clock variants.

The historical compatibility probe uses five declared synthetic position contexts
and a $100 close reference. It does not qualify full native poll transport,
historical source-age withholding receipts, independent canonical history, HYPE
soft-extension intervals or active profit-lock policies. Complete native controller
journal payloads are not retained in cycle rows, only counts. No economic result,
strategy-reachable position path or prospective result is inferred.

The complete XYZ comparison remains 27,648 quarter decisions, 6,912 archived
hourly checks and 288 daily chunks with zero differences; its job finished at
11:29:37 UTC. Do not restart it. Missing initialization and native minute data
remain explicit. The independent 13:00:08 UTC core snapshot contains 426,240
checks in 296 chunks. At 13:32:11 UTC the original core parent/four workers are
present, with 450,720/552,960 checks and zero differences reported in its log.
That later log progress is not fresh independent payload verification. Preserve
session 34414 and its frozen archive while the remaining last-source streams run.

At the same health check both source collectors have live PIDs, no reported
errors, heartbeats under five seconds and all 26 source pins unchanged. Both
live-profile hashes are unchanged. Research process health establishes neither
live armed execution nor current account outcomes.

Revision 19's signal-time occupancy correction remains qualified in its reproduced
synthetic scope; historical financial impact is unmeasured. Revision 20's HYPE
canonical probes cover two inherited soft deadlines, not whole-history or future
UNKNOWN handling. Revision 21's authenticated reader remains available; its older
prefix measurements are retained as historical evidence, not current scope.

Revision 22 contains 4,020 references, preserving revision 21's complete 3,831
reference prefix. Evidence is under
`data/logs/research/bidirectional_cohort/v89_historical_exit_routing_20260909_v1/`.
No profitable live recommendation or complete prospective evaluator is established.

## Historical September 8 findings and intermediate next actions

Operational update at September 8 14:11 UTC: all seven asset ledgers end in
`STOPPED / operator_stop` at 14:05:33 UTC. The tracked backend, supervisor and
reporter processes are absent; the detached TUI remains open and displays stale
telemetry. Its last checkpoint is from 14:04:48 UTC and cannot establish current
armed execution. Unsigned native core and XYZ reads at 14:11:02–03 UTC report no
positions or open orders. Confidence is high in those observed states; the
shutdown requester remains unidentified. No stop file is currently present.
The generic stop reason also covers termination and terminal-hangup signals.
Evidence: `data/logs/research/bidirectional_cohort/v89_stopped_status_20260908T141101Z/`.
The [stale-display correction](../reviews/2026-09-08-v89-stale-checkpoint-presentation.md)
was [approved and installed](../reviews/2026-09-08-v89-stale-tui-deployment.md),
source `d10b05b`, main source commit `02dd3b9`. The detached monitor was verified as PID
88441 in Terminal window 5958 at 160x50 with all seven assets and nine-view
navigation. At 15:15:54 UTC that monitor is absent and the window reports
`[Process completed]`; its exit requester is unresolved. The approved binary
remains installed. The backend and reporter remain stopped. No process lifecycle
action was taken by the subsequent economic audit. Shutdown attribution remains
unresolved after the bounded log search.

[Chronological shared-account attribution](../reviews/2026-09-08-v89-shared-chronological-stability.md)
is complete. Recorded/adverse results are +$183.56 over the first 28 days and
−$87.44 over the later 20 days, with HYPE contributing −$71.47 in the latter.
The full 48 days earn a modeled $96.12; removing the three largest positive
marked-day contributions gives −$77.62. Confidence is high in the reconciled
arithmetic and low in a causal regime-shift interpretation. Both periods have
already been explored.

The subsequent [HYPE executable-price reconstruction](../reviews/2026-09-08-v89-hype-executable-price.md)
is also complete. All 84 post-publication books have sufficient depth at both
modeled quantities; maximum entry VWAP is $81.888, below the modeled adverse
$81.91002575. Every resulting unrounded 80-bps stop is below the recorded
09:23 candle low. Confidence is high in the bounded arithmetic and low in any
revised-trade claim; this does not establish client fills or venue stop triggers.

The [HYPE mark and historical execution study](../reviews/2026-09-08-v89-hype-mark-trigger.md)
is complete. Ten public-matched fills reconcile an older V61 trade to +$52.769613
net, with different size and exit settings. The 476 vendor marks and 1,899 native
position marks show no observed threshold touch; their gaps prevent a continuous
trigger claim. No current V89 PnL is revised. There is no reason to repeat the
same sparse acquisition without denser evidence.

The [HYPE exit attribution](../reviews/2026-09-08-v89-hype-exit-attribution.md)
is complete. Six recorded-source modeled longs produce −$46.23 nominal and
−$99.26 adverse over 48 days. Price PnL is negative before fees/funding in every
retained case. The August 26 stop-switch explains 91.54% of the nominal/adverse
difference, but excluding it still leaves the other later-period adverse trades
at −$47.69. This is descriptive arithmetic, not a fitted exit recommendation.

The [two-stop execution audit](../reviews/2026-09-08-v89-opening-stop-execution.md)
is complete: SNDK −$7.216071 and SPCX −$3.580442 net. Retained stop-price loss
accounts for −$9.7972 (90.744% of combined net loss), trigger-to-fill movement
−$0.8236, fees −$0.172550 and net funding −$0.003163. Both exits match public
trade identities; sampled marks cross the stop at each fill timestamp. All
2,654 resting-stop observations are consistent. Exact latency remains unresolved.
207 offline tests pass and the source-archive report replays byte-for-byte.
Confidence is high in this arithmetic, low in a causal opening-session diagnosis.

The [cash-open exposure study](../reviews/2026-09-08-v89-cash-open-exposure.md)
is complete. All 18 inherited cases reconcile across 99 SNDK/SPCX lifecycles.
Primary opening attribution changes from −$3.887588 to −$83.505224 under the
inherited late-intrabar clock while whole-trade net is conserved. Zero-duration
boundary events account for −$13.261976 in the primary recorded result; positive
opening exposure contributes +$9.374388 over 17 dates and 9.5 hours. These clocks
and selected exposure dates cannot establish a useful live session filter.
33 offline tests passed; independent SQL verifies 21,132 components, and the
source archive reproduces all 55 output files byte-for-byte. Confidence is high
in accounting and low in causal or policy interpretation.

The [SNDK exit-clock qualification](../reviews/2026-09-08-v89-sndk-exit-clock.md)
is complete. August 7's first observed stop contact at 13:32:22.136 UTC precedes
the first observed liquidation contact by 465.082 seconds; adjacent books have
full modeled closing capacity. August 6's local stop contact occurs near the bar
end at 13:44:14.141. Confidence is high in the sampled measurements, moderate
in the challenge to liquidation-first bar attribution, and low in revised fills
or profitability. No historical or live PnL was changed. Ninety offline tests,
220 independent threshold-field checks, six Decimal depth walks and exact
source-archive replay passed. The August 6 13:30 trade minute remains explicitly
partial; same-millisecond end prints leave unique closes unresolved.

The [SNDK conditional event replay](../reviews/2026-09-08-v89-ambiguous-exit-replay.md)
is complete. Full entry-window marks confirm no earlier observed stop contact.
All 18 original baselines reproduce exactly; all 144 conditional full-account
replays reconcile. Primary SNDK loss changes from $26.36 to $13.79, full-period
modeled net from $96.12 to $108.68, while later-20-day net stays −$87.44 and
maximum dollar drawdown stays $198.69. Full-fee recorded cases remain negative.
Seventy-nine offline tests, 120 independent Decimal fields, 9,999,696 independently
checked path rows and frozen-source replay pass. Confidence is high in arithmetic
and low in actual hypothetical-fill attainability or future profitability.

The [fixed equal-cap benchmark](../reviews/2026-09-08-v89-equal-cap-allocation.md)
is complete. All 36 comparisons improve full-window modeled net and increase
maximum dollar drawdown. Recorded/adverse/original-exit net changes from $96.12
to $369.09, dollar drawdown from $198.69 to $288.19, and later-period net from
−$87.44 to −$52.43. Full-fee later net worsens from −$137.28 to −$159.23. The
$7,500 summed cap budget is preserved, but average entry-notional exposure
roughly doubles from $871.82 to $1,763.33. Retain a research candidate, with
high confidence in arithmetic and low confidence in future edge or actual
changed-size execution. Ninety-two offline tests, independent Decimal/funding/
path checks and source-archive replay pass. Fit no intermediate weights.

The [bounded quote and cost qualification](../reviews/2026-09-08-v89-equal-cap-quote-feasibility.md)
is complete, source `c28c241`. All 252 snapshots and 720 direction/cap probes
are usable/complete in the fixed 18:03:20–18:09:13 UTC sample. Equal-cap minimum
visible capacity is 20.95 times quantity (HYPE); all current leverage and size
metadata qualify. Current unaligned taker assumptions are 4.32 bps/side core
and 0.864 bps/side XYZ, with a separate 8.64 bps/side no-growth XYZ stress.
Fifty-seven offline tests, all 27,216 independent Decimal fields and byte-exact
archive replay pass. Confidence is high in this narrow sample, low in durable
liquidity or future edge. Current capacity does not revise the historical
drawdown/exposure trade-off or prove changed-size historical fills.

The [staging correction](../reviews/2026-09-08-v89-staging-roundtrip-correction.md)
is prepared in isolated commit `a676db5`, not deployed. The serializer's BTC
direction widening and omitted entry caps were reproduced; the correction also
preserves flat-entry position policy and validates generated fingerprints before
publication. Forty-one acceptance tests and archived reproduction pass. The
original main source remains unchanged; financial impact or shutdown causation
is not established.

The [exact inactive allocation proposal](../proposals/v89-equal-cap-20260908/recommendation.md)
contains separate original/equal configs, complete typed and independent raw-TOML
parity, and fixed cost contracts. Source `1e720d5` reproduces both files and the
comparison byte-for-byte. The prospective economic contract is registered for
**September 9 00:00–September 23 00:00 UTC**, with 24 cells / 12 pairs and a
first-receipt/adverse/recorded-bar primary. It is **not running**: source collector
and replay qualification remain outstanding. No live allocation approval is
requested; preserve both the new and existing outcome seals.

Next: implement and qualify the separate seven-asset prospective source collector
against that fixed calendar, preserving raw/version/timing evidence. Do not alter
the existing SNDK/Brent collector or inspect either experiment's early outcomes.
No live change is authorized by the research result.

At 18:55:38 UTC the tracked backend, supervisor, reporter and former monitor
remain absent, and the checkpoint remains from 14:04:48. The live profile bytes
are unchanged. This process/configuration observation does not refresh the
14:11 native account snapshot or identify the shutdown requester.

Operational note: research import briefly deferred below 8 GiB free space and
resumed automatically. A 180-sample observation at 13:43–13:46 UTC stayed above
11.7 GiB and captured a successful import. It did not reproduce the shortage.
The capacity cause remains unresolved; the mapped-reader proposal measures write
I/O reduction and is not established as a net-space fix.

## Completed evidence to reuse

| Question | Current evidence and interpretation |
|---|---|
| Shared 48-day source coverage | [Core source fidelity](../reviews/2026-09-07-v89-core-replay-source-fidelity.md); newer verified core inputs exist through September 7. The older annual cache ending July 27 is incomplete as a project inventory. |
| Seven-asset joint cash and marked risk | [Shared marking](../reviews/2026-09-07-v89-seven-asset-shared-marking.md); completed, 176 archive-source trades, six retained sensitivity cases. |
| Recorded candle sensitivity | [Recorded-native study](../reviews/2026-09-07-v89-recorded-native-source-sensitivity.md); 177 modeled trades, first/latest variants agree, one added HYPE long switches between profit and stop loss under slippage assumptions. |
| Current HIP-3 fees | [Fee qualification](../reviews/2026-09-07-v89-current-fee-qualification.md); current metadata is separately qualified and does not establish historical fees. |
| Core inactivity | [Opportunity attribution](../reviews/2026-09-08-v89-core-opportunity-attribution.md); frozen run prefix through 10:40 UTC has zero eligible core entries. This is a bounded observation, not a forecast. |
| HYPE input arithmetic | [Native compression parity](../reviews/2026-09-08-v89-hype-native-compression.md); 907 publications match the independent calculation. Revision 2 corrects the obsolete follow-up, preserving the numerical result. |
| HYPE August 26 entry price | [Executable-price reconstruction](../reviews/2026-09-08-v89-hype-executable-price.md); 131 books, 253 public trades, 93 offline tests and exact source-archive replay. The adverse entry exceeds every observed post-publication depth walk; the complete lifecycle remains unresolved. |
| HYPE August 26 marks and actual execution | [Mark qualification](../reviews/2026-09-08-v89-hype-mark-trigger.md); older V61 +$52.769613 reconciled, 30 sampled threshold comparisons unresolved between observations; 81 offline tests and exact archive replay. |
| HYPE losses by exit mechanism | [Exit attribution](../reviews/2026-09-08-v89-hype-exit-attribution.md); all 18 cases and 54 marked-period totals reconcile; six distinct recorded longs, no opposite-signal exits; 22 offline tests and exact archive replay. |

The four September 7 studies were found in
`/Users/gestas/Prototypes/hypervector-v89-portfolio-20260907` and registered in
DuckDB. Their eight review/journal files have now been copied exactly into main
and the current research worktree. Preserve original source-record paths and
hashes; do not append the same revisions under new identities just to copy docs.

## Do not repeat or open early

- `v89_seven_asset_common_window_joint_marking_v1`: withdrawn duplicate proposal.
  The shared study already existed; the completed chronological study is the
  distinct follow-up.
- `v89-quarter-entry-20260908`: faster entry rejected; 177→200 modeled trades
  worsened net and drawdown in all three shared cost cases. Do not reopen without
  new evidence or a changed assumption.
- `v88-hype-onset-missing-early-window-20260906`: no favorable measured relaxation
  lead; do not repeat onset removal from the same evidence.
- `spcx_long_crossing_composition_v1`: completed descriptive split; an entry
  filter remains deferred. This ID does not begin with `v89`.
- Sealed SNDK/Brent prospective experiment: September 8 04:00 through September
  22 04:00 UTC. Do not read early outcomes. Collector health is distinct from
  strategy results.

## Prepared proposals, not deployed

| Candidate | Evidence and remaining boundary |
|---|---|
| Entry dispatch deadline, source `3d204863af40536187df96f161f4874d9fa42166` | [Review](../reviews/2026-09-08-v89-entry-deadline-dispatch-proposal.md); 454 focused tests. Deployment approval is pending; do not re-ask without a relevant update. |
| Bounded memory snapshot reader, source `7a30d04` | Journal `v89-memory-snapshot-20260908`, revision 3; reporting-only deployment proposal remains pending. Keep the rejected earlier candidate distinct. |
| Configuration-staging correction, source `a676db5` | [Review](../reviews/2026-09-08-v89-staging-roundtrip-correction.md); exact V89/flat-entry regressions, serialized fingerprint validation and 41 acceptance tests. Source application only requires explicit approval; no trading/profile restart accompanies it. |

These are not deployment authorizations. Existing live process and configuration
identity must be read from current evidence before reporting their state.

## How to find the latest evidence

The authoritative append-only table is
`data/research/market.duckdb:portfolio_research_revisions`. Query the highest
revision per hypothesis across all prefixes, then inspect source-record paths
and verify bytes/SHA-256. A worktree-local document list is not a complete
experiment ledger. Respect the reporter's database writer window; a temporary
lock is not a missing record.

Frozen navigation inventories and copy verification are under
`data/logs/research/bidirectional_cohort/v89_research_navigation_reconciliation_20260908_v1/`.
`journal_inventory.json` is the immutable input used by chronological attribution;
`all_recent_hypotheses.json` also captures non-V89-prefixed work. New revisions
appended after those snapshots must be queried from the database.

Current research source worktree:
`/Users/gestas/Prototypes/hypervector-v89-storage-spcx-20260908`.
Shared portfolio/source worktree:
`/Users/gestas/Prototypes/hypervector-v89-portfolio-20260907`.
The main workspace receives reviewed documentation without importing research
source into the live execution code.

Re-read the active goal attachment at each resumed goal turn. Select one
unresolved investigation from current evidence, preserve rejected dispositions,
and update this index when that investigation is completed or superseded.
