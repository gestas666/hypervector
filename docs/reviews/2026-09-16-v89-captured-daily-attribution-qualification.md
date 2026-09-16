# Captured account daily and split-period attribution

The isolated research candidate now reports cash contributions for every day,
asset and original before-actions split. It preserves actual marked inventory
across boundaries, funding timestamps and terminal open positions. The captured
entrypoint continues to authenticate the registered study, original outcome seal,
expected allocation/configuration, source calendar and complete independently
reconciled account before calculating these results.

The boundary reader requires one explicit mark for all seven original assets,
matching source/committed marks, exact event indices and the complete native
clock sequence. It authenticates source bytes before and after the read. Missing,
repeated, extra or retimed events, altered source clocks, missing/duplicate/
unknown assets, nonpositive prices, changed hashes and disagreeing source marks
are rejected. Interior dates retain the original before-actions snapshots;
initial and terminal phases are preserved. Nearby marks are not substituted.

The historical public entrypoints retain their scope checks. Only their shared
cash arithmetic was extracted for use after captured-scope authentication.
No real captured contract was relabeled historical or synthetic, no date was
shifted to evade an outcome seal, and no real prospective outcome was opened.

## Validation and limits

- The missing shared calculation bodies first failed six control tests. Missing
  captured daily report integration separately failed with `KeyError` before
  implementation. The boundary reader's initial eleven failures were retained.
- The first complete daily integration suite passed 85 tests. Final qualification
  passed **88 tests**, with warnings treated as errors. Additional cases cover
  a truncated terminal event, an extra terminal event and changed source clock.
- Both new modules have **100% statement coverage**. The shared daily module has
  79/82 statements (96.34%); the period module has 112/118 (94.92%). The coverage
  artifact names nine unexercised existing defensive rejection statements.
  This run measured statement coverage, not branch coverage.
- A hand-calculated fourteen-day control keeps one BTC long open throughout.
  Net is $31 in the first seven days, $31.50 in the second seven and $62.50 full.
  Moving one funding debit from 176 ms after the split to 176 ms before changes
  the period totals to $30.50/$32.00 while preserving the full result. Six inactive
  assets remain explicit zero contributors; no terminal exit fee is invented.
- Two complete two-day source-calendar accounts use deliberately programmed
  provider outputs. The existing stop-spike control closes all seven positions.
  The calm-source control retains five positions at the day split; BTC's actual
  configured holding rule closes it in day two, while ETH remains open at the
  terminal boundary. Entry and exit fees belong to the correct periods. Both
  account ledgers pass independent reconciliation with all 336 native funding
  observations. These controls are not strategy-return evidence.
- The archived source independently passed **88 tests**. For both complete cases,
  source calendar, event stream and account output are byte-identical. All
  non-evidence report fields, including daily boundaries and daily/period cash,
  are exactly equal. Config source bytes match, every artifact reference is
  authenticated, and manifest differences are limited to the local config path.
  Whole report bytes differ because local paths and dependent hashes differ.
- Scoped Ruff checks and `git diff --check` passed. No live strategy, leverage,
  sizing, asset universe, route or backend process was changed.

Reporting commit: `465ad65` in the captured-reporting worktree. Integrated research
candidate: `75b2c29e5cd507f0792b85b64886ad71e919b2ea`, based on `d534174`.
The source archive authenticates 5,763 members and has SHA256
`a12343b62d1935af0c4c025ae6c2a43306974a879e6b8dff02dcbad52cd8fc0f`.

High confidence applies to these tested accounting and artifact boundaries.
It does not establish a full fourteen-day native strategy replay, all 24 complete
paired cases, source/strategy profitability, or private venue executability.
The hand-calculated fourteen-day control is not a substitute for that full study.

## Decision and next investigation

Recommendation: retain the qualified reporting component in the isolated
research candidate. Why now: daily and split-period ownership are required to
compare the declared allocation cases without attributing marked carry, entry
fees, exit fees or financing to the wrong period. Applicable regime: accounting
is regime-independent; economic conclusions still require the declared source
window and actual strategy conditions.

| Alternative | Trade-off |
| --- | --- |
| Preserve exact carried-account boundaries | Supports the intended paired study; requires full source and account evidence. |
| Compare terminal cash alone | Simpler, but omits inventory and period ownership; insufficient for this study. |
| Restart or force-close a replay at the split | Creates different trades, financing and fees; violates the intended comparison. |

Proposed live change: none. Expected upside: accurate attribution for decisions
about portfolio growth; no forecast return improvement is claimed. Main risks:
mistaking programmed controls for native strategy qualification, opening sealed
outcomes early, missing source clocks or treating conditional modeled fills as
private execution evidence. Validation completed: the controls and reproduction
above. Validation still required: explicit market/cost assumption reporting,
all 24 complete paired cases, full-period native throughput, and additional
nontrivial native route/hold controls before evaluating the real registered study.

The single highest-value next investigation is the complete 24-case reporting
and comparison pipeline, with explicit assumptions and the unchanged study
registration, followed by full-window native execution qualification. Success
means all declared cells retain complete source/account identity and reconcile
every daily and seven/seven cash component. A changed seal, wrong native clock,
cash mismatch, omitted cell, historical regression or failed reproduction
reopens the corresponding component. Rollback is removal of the isolated research
commit through a new corrective commit; no active financial process is involved.
Explicit live approval requested: none for this research-only change.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/`.
Key artifacts are `captured_period_metrics_red_v1.txt`,
`captured_daily_integration_red_v1.txt`, `captured_daily_tests_v2.txt`,
`captured_daily_coverage_v2.json`, `daily_source_manifest_v1.json`,
`daily_archive_tests_v1.txt`, `reproduce_daily_v1.py` and
`daily_archive_reproduction_v1.json`. The two retained qualification directories
contain the complete synthetic accounts and reports.
