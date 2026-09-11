# V89 stopped-run funding recovery — September 11, 2026

The installed accounting path recovers the observed post-stop funding credit
once at the tested same-day restart. Its fixed 24-hour startup lookback omits
that credit in a separately labeled longer-downtime simulation. Isolated
candidate `0c2b81933f4df480e0e8bb6b5289b8ea47504761` corrects cursor recovery and
paginates funding history. It is **not installed**; no trading process was
restarted, no financial instruction was sent, and no live setting changed.

Technical confidence is **high for the reproduced boundary defect and tested
correction**. Complete live-launch acceptance remains unproven. This accounting
repair provides no evidence of improved strategy returns.

## Evidence and observed behavior

The experiment plan was recorded before replay. Its input is the frozen exact
SNDK profile history from the [adoption study](2026-09-11-v89-sndk-restart-adoption.md),
four authenticated native SNDK fills, and unsigned venue funding records.
Thirty first/configuration and financial records were copied into an isolated,
contiguously reindexed ledger; original source sequence numbers were retained.
Three replays across two telemetry instances added no duplicate fills or fees.
They added exactly one funding event: **+$0.004137 at 16:00:00.047 UTC**.
The earlier **+$0.008767 at 15:00:00.047 UTC** remained unique. Total native cash
funding for these two observations is **+$0.012904**; the position API reports
the opposite sign in `cumFunding.sinceOpen`.

| Tested activation clock | Installed query start | Candidate query start | Known 16:00 credit included |
|---|---|---|---|
| September 11 16:10:00 UTC | September 10 16:10:00 UTC | Same 24-hour overlap | Both |
| September 12 16:00:00.048 UTC, synthetic | September 11 16:00:00.048 UTC | September 11 15:37:02.134 UTC | Candidate only |

The synthetic clock is one millisecond beyond the credit's 24-hour retention
in the startup window. It introduces no future market prices or hypothetical
trade outcomes. There is **no demonstrated irrecoverable omission at the
same-day capture**: the stopped original ledger has not yet reconciled the
credit, and its installed lookback still includes it.

The candidate read the actual 4,336,519,850-byte cohort ledger and recovered
committed cursor `1789141022134` for profile fingerprint
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
Its actual command factory, with mocked engines, signal installation and inbox,
produced both expected startup windows. No engine method was called.
The original cohort and SNDK ledger hashes remained unchanged.

The installed SDK method makes one funding-history request. Extending the
window alone therefore does not establish complete recovery. Hyperliquid's
[Info pagination documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
describes a 500-element or distinct-block limit and continuation from the last
returned timestamp. The correction paginates account-wide records before
filtering by asset and deduplicates the inclusive boundary by native identity.
Malformed, conflicting, out-of-window, unordered or full nonadvancing pages
fail explicitly instead of silently advancing the committed boundary.

## Exact proposed change

Candidate worktree:
`/Users/gestas/Prototypes/hypervector-v89-funding-recovery-20260911`.
Base: `419c58db2fc59312860bdb10979d52e23241aea3`.
Eleven files: eight implementation files and three tests; no dependency changes.

- Recover the latest exact-profile committed funding cursor. If a legacy
  profile has configuration history but no committed window, use its first
  recorded activation. A new profile retains the existing 24-hour overlap.
- Choose the earlier of the recovered boundary and that overlap; reject an
  invalid or future cursor before starting engines.
- Share strict funding-window decoding with the existing research acceptance
  reader, expose the recovered boundary through cohort telemetry, and wire it
  through the live command factory.
- Paginate the shared core/HIP-3 funding reader. Standalone legacy readers
  outside the configured seven-asset cohort are outside this patch's scope.

The runner's dependency-assignment ordering was adjusted to keep its constructor
within 50 lines; those assignments perform no financial action. No entry rule,
exit rule, leverage, sizing, asset universe, dispatch deadline or protection
sequence changes. The TUI and its panes are unchanged.

## Validation and rollback

The exact committed candidate passed **136 focused tests in 4.28 seconds** in
the final post-commit run. An earlier measured run covered **29/29 statements
and 16/16 branches** in cursor recovery and **42/42 statements and 14/14 branches**
in pagination. This is full measured coverage of those two new modules, not a
whole-system coverage claim. Existing accounting, runner, telemetry, command,
adapter and shared-window tests are included. Tests use mocked network boundaries.
Ruff, formatting, the 500-line file and 50-line function bounds passed on all
eleven candidate files.

The original failing cursor case and five failing pagination cases are retained,
along with intermediate runs and their fixture/import failures. Eleven pinned,
existing ignored fixtures were copied byte-for-byte; dependencies were not
updated and tests were not skipped to obtain a passing result.
The executed native replay operator is retained as
`verify_candidate.executed_v1.py`. Its subsequent helper extraction only meets
the function-size rule; the refactored operator was linted but not replayed.
Simulated ledger rows retain engine-authored live-mode fields but have no
runtime consumer or financial authority.

Six prior source files and all eleven candidate files are preserved under
`data/logs/research/bidirectional_cohort/v89_restart_accounting_20260911_v1/`.
`candidate_manifest.json` binds each file's bytes and SHA-256.
The patch passed a nonmutating forward-apply check against main. In the isolated
worktree, actual reverse application restored all six prior files and removed
the five additions; forward application then restored the exact clean candidate.
Main source was untouched. A future rollback must verify installed hashes first
and restore only these owned changes, preserving later unrelated work.

## Current observed runtime boundary

Unsigned native reads completed **16:47:52 UTC / 12:47:52 Eastern**: core was
flat and order-free; XYZ held the same **-0.306 SNDK at 1629.2, 10x isolated**.
Its exact full-size reduce-only buy Stop Market OID `542326955281` was open at
trigger **1669.9**. Marked unrealized PnL was **-$0.5202** at that capture.
These sequential point-in-time reads do not prove uninterrupted protection.

The five original trading/TUI processes remain absent and the seven terminal
`STOPPED / operator_stop` asset records are unchanged. Strategy-managed exits
and new entries are stopped. The stop's origin and intent remain unproven.
The roster observer and both prospective collectors retain their process births;
their hypothetical outcome seals were not opened. The profile and installed
TUI hashes are unchanged. Two completed trades remain **-$27.994028 net** in
the stopped checkpoint, excluding the open SNDK lifecycle.

## Decision proposal

**Recommendation / why now:** install this evidenced accounting correction as a
source-only change before a future authorized recovery. Longer downtime can
move unreconciled funding outside the installed fixed query window.

**Applicable regime:** a recovery/accounting defect independent of market regime.
**Expected upside:** retain missing funding exactly once across downtime; no
return, win-rate or profit forecast is supported.

| Alternative | Benefit | Trade-off |
|---|---|---|
| Leave source unchanged | No deployment change | Known longer-downtime omission remains |
| Extend the fixed lookback | Small patch | Another finite cutoff and incomplete single-page reads |
| Durable cursor plus pagination, proposed | Covers the tested recovery interval and page boundaries | Extra startup scan and potentially more unsigned requests |

**Risks / remaining validation:** the cursor adds a full validated scan of the
large cohort ledger, so whole-launch startup time must be measured against its
readiness timeout. Very long histories may require many requests. A dense full
page that cannot advance its timestamp stops recovery explicitly. Legacy
profiles depend on available retained configuration history; this cannot
recover deleted history. Fresh venue reconciliation, fees, precision, launcher
readiness, first funding commit and TUI accounting remain live acceptance checks.

**Success metrics:** the exact saved boundary reaches the runner; the known
credit appears once; retained fills/fees remain unique; complete page retrieval
precedes cursor advancement; fresh launcher telemetry and accounting agree.
**Failure / rollback triggers:** missing/duplicate funding, changed financial
identity, unexpected source changes, incorrect cursor advancement, or a startup
timeout attributable to the correction. A changed venue position/stop requires
revalidating recovery ownership rather than applying this open-position replay.

**Explicit approval scope:** source-only installation of candidate `0c2b819`;
no automatic restart or financial action. The optional candle-session candidate
`f59d54c` is a separate pending decision and is not incorporated here. Both
touch the launcher; if both are approved, verify their composed source and
tests before installation rather than copying either whole file over the other.
Approval is requested because the mandate's Human control clause requires
explicit approval before live execution/deployment changes.

**Highest-value next investigation:** exercise whole-launch recovery with the
actual retained ledger sizes, including readiness timing and projection of the
first reconciled funding batch, using isolated state and mocked financial
boundaries. Engine adoption and accounting replay do not replace that evidence.
