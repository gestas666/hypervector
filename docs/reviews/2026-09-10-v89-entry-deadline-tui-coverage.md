# Entry deadline TUI coverage reproduced from frozen source

Candidate `f00b6b8d22cf59285a313b7de1166cccecbe52ca` strengthens the regression
tests for the [entry-deadline TUI correction](2026-09-10-v89-entry-deadline-tui.md).
Its runtime implementation is identical to `b73b112`; this revision changes one
test file and adds its qualification plan. High confidence applies to the
measured offline scope. No installation, live startup or profitability claim
follows from the result.

The earlier qualification lacked measured Rust coverage. Initial instrumentation
found 122/130 decoder lines and 41/43 display-helper lines covered. Ten additional
tests now exercise malformed provider-symbol identities, mixed stage schemas,
overflow, incomplete clocks, unsupported legacy/current claims and late adapter
attribution. Existing Python-oracle scenarios also check rendered clock values
and explicit unavailability. These tests required no implementation correction.

| Measured scope | Lines | Regions |
| --- | ---: | ---: |
| New deadline decoder | 130/130 (100%) | 183/185 (98.92%) |
| New deadline display helper | 43/43 (100%) | 58/58 (100%) |
| Changed projection/inspector functions and predicate closure | Executed | 54/54 (100%) |

Both checkout and archive produce the same metrics. The two unhit decoder
regions are checked-add error returns for aggregate submitted and SDK counts.
Earlier checks establish nonnegative counts, `submitted <= enter`,
`SDK <= submitted`, and an enter sum bounded by `usize::MAX`. Those two sums
cannot overflow under these established conditions. Separate reachable overflow
paths for entry aggregates, withholding aggregates and within-route stages are
tested. No guard was removed and no coverage exclusion was added to the code.

The exporter reports zero branch and MC/DC entries, so those metrics are
unavailable; region coverage is not branch coverage. The old containing files
measure 90.74% and 72.69% line coverage under these targeted suites. This record
does not claim whole-TUI coverage. It closes the measured-coverage gap for the
new modules and changed integration functions.

Normal release validation passes **544 tests** in both checkout and archive,
with identical test identities and 23 unchanged runtime-dependent tests ignored.
Clippy with warnings denied and formatting checks pass. Instrumented validation
runs 20 decoder tests and 116 existing view tests. All **5,156 Git blobs** match
before and after the frozen-source run; the four measured source-file hashes
also match across checkout and archive. No compiler, merge or export warning
was recorded in the final coverage run.

The measurement uses Rust 1.93.0 and matching LLVM 21.1.8 tooling, with a separate
instrumented build at optimization level 0. Normal release validation remains
separate. Build-script profiles are excluded from test measurements. The
workflow follows the [Rust compiler coverage guide](https://doc.rust-lang.org/rustc/instrument-coverage.html).

Evidence is under
`data/logs/research/bidirectional_cohort/v89_entry_deadline_tui_coverage_20260910_v1/`.
Use `candidate.json`, `source.tar.gz`, `test_delta.diff`,
`archive_acceptance.json`, `release_tests.log`, `archive_tests.log`,
`round_4/summary.json`, `round_4/selected_modules.json`, and
`changed_glue_acceptance.json`. Exact final test binaries, raw profiles, merged
profile, full export and commands remain under `round_4/`. The unchanged V86
screen test also needs the prior qualification's retained September 4 fixture
bundle. The installed TUI hash remains
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.

After qualification, only this task's temporary coverage build cache was
retired. Its 1,571 entries were archived, independently restored, and checked
for matching contents, permissions and symlink destinations before removal.
The retained `cache_backup/target.tar.zst` is 166,317,570 bytes with SHA256
`2f411afd64ff9cd40c8744347a2bb009ae741d94cffe8cae51e65926c04093bf`.
The cleanup window showed 601,194,496 additional free bytes. Test binaries,
profiles, source archives and reports remain present. Do not recreate the
completed coverage cache merely to repeat this accepted measurement.

Recommendation: use this stronger test set with the existing technical deployment
proposal. The simpler alternative is retaining the earlier passing tests, which
leaves the newly identified failure cases unmeasured. The expected benefit is
better regression detection; no increase in trade frequency or returns is
established. This correction is independent of market regime and grants no
strategy, allocation, execution or promotion authority.

Changed source/fixture hashes, a failed regression, a mismatched coverage export
or a fresh supported checkpoint displaying incorrect route/stage/clock evidence
would update or invalidate the conclusion. Fresh source/profile/ownership checks,
retained prestart backup, explicit deployment approval and supervised live/TUI
acceptance remain outstanding. The original economic matrix and both prospective
outcome seals remain unchanged. No new deployment approval is requested here.
Rollback constraints remain those in the prior technical proposal; this test-only
revision introduces no new runtime or ledger format.
