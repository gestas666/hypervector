# V89 checkpoint recovery and stopped-backend TUI correction

Candidate `a0352a5c81603129563dfbabf286c558a2e6d72c` repairs inherited-position
checkpoint publication and incorrect stopped-backend presentation. It includes
the previously reviewed funding-recovery candidate `0c2b819`. The complete
proposal is a 34-file source/test patch plus the exact tested TUI executable.
It has **not been installed**, and the original backend has not been restarted.

**Recommendation:** approve installation of this technical correction after
reviewing the bounded evidence below. Continue compact-screen and complete
seven-asset readiness validation independently. This proposal does not establish
that every asset and strategy is ready for live operation.

**Why now:** a stopped run can retain an open position that a later run must
recover. The installed current-run checkpoint path failed on that inherited
lifecycle. Native rendering then exposed incorrect authority labels and
historical fills included in current-run execution-quality statistics. These
are reproducible implementation defects; two losing completed trades alone do
not establish a strategy defect.

**Evidence reviewed:** exact original asset/cohort ledgers; the advancing-clock
full-backend V4 replay and its verified prestart backup; installed and candidate
checkpoint attempts V2–V7; Rust red/green regressions; native captures of both a
simulated recovery checkpoint and the recorded final V3 checkpoint; an unsigned
venue capture completed at **20:05:34 UTC on September 11**; and a disposable
installation/rollback rehearsal completed at **20:04:37 UTC**.

The evidence root is
[`v89_checkpoint_recovery_fix_20260911_v1`](../../data/logs/research/bidirectional_cohort/v89_checkpoint_recovery_fix_20260911_v1/).
The separate [funding proposal](2026-09-11-v89-restart-accounting.md) describes
the durable funding cursor and pagination changes included in this candidate.

**Observed problem or opportunity:**

- A new run's asset-only history omitted earlier entry acknowledgements,
  original entry context and costs needed to represent an inherited position.
  Candidate recovery expands only assets with an identified earlier execution
  dependency, using compatible profile/run identities and bounded history.
- Missing historical provider readiness initially made the Rust journal reject
  a valid recovered checkpoint. Explicit unavailable-provider context is now
  accepted; duplicate or conflicting provider identities still reject.
- The first parser-fixed native capture still displayed `BACKEND CONNECTED`,
  `LIVE BACKEND ARMED` and active request routing on a stopped snapshot. The
  shared stopped-state predicate now controls the header and manual controls.
  It is checked again immediately before writing a previously confirmed request.
- The recovered run had zero new fills, while execution-quality statistics
  included 17 historical fills. That panel now filters by exact `origin_run_id`,
  counts prior/unattributed fills separately, and reports missing run identity
  as unavailable. Historical journal entries remain visible.

The earlier fixed-clock chronology failure, comparator/cache failures, installed
parser failure and first stopped-state/friction failure are retained. The
fixed-clock fixture failure is not evidence of a production clock defect.

**Applicable market regime:** these are restart, accounting and display
contracts across market regimes. No regime threshold, route, strategy, asset,
leverage, size, risk limit or entry frequency is changed by this proposal.

**Alternatives considered:**

| Alternative | Benefit | Cost / reason |
|---|---|---|
| Keep the installed source and TUI | No deployment work | Retains the reproduced recovery and display defects |
| Install only funding recovery | Repairs cursor recovery and pagination | Leaves checkpoint publication and TUI defects unresolved |
| Install the combined candidate | Repairs the tested accounting and stopped-state contracts together | Requires source/binary installation and further operational qualification |
| Wait until complete all-asset acceptance | One broader installation decision | Defers already validated repairs; full acceptance remains the end-state requirement |

**Proposed live change:** install the source/test patch described in
[`installation_candidate.json`](../../data/logs/research/bidirectional_cohort/v89_checkpoint_recovery_fix_20260911_v1/installation_candidate.json)
and replace the TUI with the retained candidate executable. The patch SHA-256
is `c1c7f17a03b3aab971ae6ab2386a63a191f40e16989fdbb965df33871698e68b`.
The candidate executable SHA-256 is
`4cde01777046c6a9e2fd3738d7b6066466499f4c5daf30360f8348b14bfe4fb9`.
The base production commit at review is `a60f107022be9500453afeec927a230141992f67`.
The optional candle-session candidate `f59d54c` is separate and excluded.
Installation approval would cover these exact artifacts only. A restart and
financial execution are separate actions.

**Expected upside:** recovered positions and funding remain inspectable;
current-run execution statistics reflect their stated scope; stopped snapshots
cannot advertise enabled manual execution through the corrected path. No
increase in returns, win rate, trade count or profit capture is established.

**Main risks and failure modes:** unfamiliar historical ledger contracts,
truncated or replaced files, stale checkpoint/ledger combinations, missed
provider context, and a process state changing between observation and action.
Regressions cover the identified cases, including a stop arriving after manual
confirmation. They do not prove every production ordering. The UI still has a
known compact limitation: at 100x28, OPS action details compress or clip. The
nine initial views were traversed; every paged asset/detail was not.

**Validation completed:**

| Check | Observed result | Boundary |
|---|---|---|
| Focused Python recovery suite | 158 passed | Recovery/checkpoint tests, not the complete Python suite |
| Python measured coverage | Both new recovery modules 100% statement and branch; four-module aggregate 88% | Existing reflection module 90%, ledger reader 81%; not repository-wide coverage |
| Final Rust suite | 564 passed, 0 failed, 23 existing ignored | 72 reported test harness results |
| Rust formatting and Clippy | Passed, all targets with warnings denied | Offline, locked dependencies |
| Final Python Ruff | Passed for all 19 Python files in the combined patch | Static checks only |
| Post-Clippy library rerun | 155 passed | Final small test-fixture cleanup |
| Full-backend V4 replay | Two complete simulated accounting cycles; worker exit 0 | Real orchestration, scripted empty bars/intents, mocked financial adapters |
| Readiness | 655.943 seconds within the unchanged 900-second timeout | One local run; separate initial inventory 23.031 seconds; not a worst-case SLA |
| V4 accounting | Exactly one +$0.004137 funding row; zero new fill/charged-fee rows | Fixed accounting scenario; no real financial instruction |
| Ledger/backup preservation | Eight originals and eight clone prefixes unchanged; 1,889 backup files verified | Original frozen evidence retained |
| Actual candidate checkpoint publisher | Completed in 0.669425 seconds | Small authenticated recovery suffix, with only necessary inherited asset history |
| Simulated recovered-run native display | 27 frames, nine views at three sizes, exit 0 | Historical/synthetic fixture; zero new fills, unavailable provider/candle context explicit |
| Recorded V3 native display | 27 further frames, same binary, exit 0 | Actual historical checkpoint: seven provider contexts, 978 evaluations, candles/depth/trades/regime data |
| Native input preservation | Hashes unchanged for both captures; network and file writes denied | Navigation only; original user Terminal not inspected |
| Installation and rollback | All 34 source/test files applied, reversed and reapplied exactly; executable replacement/rollback/replacement matched hashes | Disposable copy only; prior sources and executable retained |

All nine wide views in each final native capture were visually inspected.
All 54 frames passed the scoped stopped-authority text checks. Neither native
acceptance receipt claims full live acceptance. The earlier parser-only capture
is retained as a failure rather than substituted by the final success.

**Validation still required:** complete the 100x28 OPS usability correction;
traverse paged non-crypto assets and strategy details; qualify fresh completed
candles and provider outputs for all seven configured assets; run the required
full acceptance checks when that complete candidate is ready; reconcile fresh
venue ownership, collateral, fees, precision and runtime state before any
separately authorized live operation; and verify the actually installed TUI in
the user's terminal. Current successful recovery replay did not calculate real
strategy signals. Historical native displays do not prove present data freshness.

**Success metrics:** exact accounting without duplicate fills, fees or funding;
authenticated compatible identity for inherited context; unavailable evidence
rendered honestly; stopped backend authority shown consistently; no local
request emitted from a stopped snapshot, including after confirmation; execution
quality scoped to current-run fills; unchanged source/profile/runtime outside
a separately approved installation; and complete source/binary rollback.

**Failure / rollback triggers:** checkpoint integrity or chronology errors;
lost, duplicated or misattributed lifecycle costs; wrong run/profile identity;
manual authority enabled by a stopped snapshot; incorrect current-run fill
quality; or source/binary mismatch after installation. Preserve new evidence,
stop the installation procedure on mismatch, and restore only the reviewed
source paths and retained previous executable. Do not reset ledgers or alter
venue positions as part of this rollback. A running backend needs a separate
operator-controlled lifecycle decision; rollback evidence here is offline.

**Confidence level:** high for the reproduced technical defects, tested repairs,
artifact identities and isolated rollback. Confidence is limited for complete
operational readiness; it remains unproven. There is no verified economic
improvement estimate. Any altered original byte, unexpected adapter operation,
incorrect inherited accounting, stale authority claim, or reproducible failing
case would update or invalidate the relevant acceptance.

At the **20:05:34 UTC** unsigned capture, core had no position or open order.
SNDK remained **short 0.306 at 1629.2, 10x isolated**, with unrealized PnL
**-$1.071**. The exact full-size reduce-only Stop Market order `542326955281`
remained open at **1669.9**. Six native hourly funding credits sum to
**+$0.033164** since this entry; position-summary funding signs are
not used as cash-flow direction. The six values were read from authenticated
`userFunding` response bodies. These sequential observations are not an atomic
account snapshot or a current quote after that time. Seven original STOPPED
records and the original cohort/SNDK ledger hashes remain unchanged. All five
original process IDs were absent; the three read-only observers were present.
The process-name scan had system-process permission limits, so it does not
prove machine-wide absence of every possible launcher.

**Explicit approval requested:** install only the exact combined source/test
patch and tested TUI executable above. This request follows the objective's
[Human control clause](/Users/gestas/.codex/attachments/0c1c6f2b-0568-4de5-a63c-f7f1e826d3a4/pasted-text-1.txt),
which requires explicit approval before live execution-behavior or deployment
changes. This review grants no execution authority and requests no change to
strategy parameters or asset allocation.

**Single highest-value next investigation:** repair and validate compact OPS
usability, then complete all seven assets' paged data and strategy-readiness
checks with the same truthful stopped/running distinction. The broader goal
remains active; this technical candidate is one completed investigation within
that improvement pipeline. Prospective hypothetical outcomes remain sealed.
