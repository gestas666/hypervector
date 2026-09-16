# V89 restart history: noncrypto archive source parity

The newly acquired fourteen-day HIP-3 candles fail the predeclared replacement
criteria for all three assets. In the captured completed overlap, 451 native
zero-volume minutes are absent and **1,416 of 14,872 shared candles have at least
one differing OHLC price**. An independent reader reproduces every difference
object, field count and missing interval. Filling missing minutes alone would
not make these sources equivalent.

**Confidence: high for this fixed source comparison.** These results do not
identify which differing source is economically preferable, prove an error in
the live strategy, or measure the effect of fourteen-day initialization on
signals or returns. Changed source hashes, a boundary/parsing defect, or failure
to reproduce the complete objects would invalidate this acceptance of the audit.
New native captures or corrected, documented source semantics would justify a
new experiment; unchanged vendor data would not.

## Scope, provenance and declared acceptance

Evidence is retained at
`data/logs/research/bidirectional_cohort/v89_restart_noncrypto_history_20260916_v1/`.
Tool commit **9defa8bb6558da1b860ca1e4c342ab1c11e316c1** is pushed on
`research/v89-restart-warmup-coverage-20260916` in the isolated worktree.

The declaration was written at **2026-09-16 17:08:48.218931 UTC**, before this
acquisition and comparison. It fixes SPCX, SNDK and Brent, the HIP-3 route, 1m
interval, **September 2 14:59 through September 16 14:59 UTC exclusive**, and
**20,160 expected minutes per asset**. It requires a complete grid and agreement
with every completed captured-native overlap value on open, high, low, close and
volume. Exact agreement is reported separately from the predeclared **1e-10
absolute tolerance**, with zero relative tolerance.

The baseline is the actual startup bundle already qualified by
`docs/reviews/2026-09-16-v89-actual-startup-input-replay.md`. Its manifest SHA256 is
`1a0efd1b534de28a942001ff8ea3a0900ab5c56fe906b2f15fb85682b8c680d5`.
The original observation cutoff is 14:58:38.179 UTC. Comparison excludes the
then-incomplete 14:58 candle, so completed overlap ends at **14:58 exclusive**.

Six HTTP pages were acquired through the correct case-sensitive
`/v1/hyperliquid/hip3/candles/{symbol}` route, two per asset. Acquisition finished
at 17:08:52.333965 / 17:08:56.766491 / 17:08:58.913848 UTC for SPCX / SNDK /
Brent. These are **retrospective responses received after startup**, not original
pre-cutoff receipts. Original bodies, request parameters, response status,
receipt dates, hashes, pagination and normalized bundles remain retained.
Request headers and credentials are not included in the HTTP recorder output.

The official contract describes these candles as aggregated from HIP-3 trades
with symbol-specific coverage. It does not establish equality with the captured
native inputs or specify the missing-minute behavior observed here.
[0xArchive HIP-3 candle contract](https://docs.0xarchive.io/schemas/operations/get-hip3-candles).
All three older vendor source families were also correctly labeled HIP-3;
incorrect selection of the core route is not the explanation established here.

## Observed coverage and values

| Asset | Vendor minutes / 20,160 | Full-window missing minutes | Completed native overlap | Shared minutes | Missing overlap minutes, all native volume zero | Shared rows with differing OHLC |
|---|---:|---:|---:|---:|---:|---:|
| SPCX | 18,804 | 1,356 | 5,197 | 4,779 | 418 | 553 |
| SNDK | 19,620 | 540 | 5,102 | 5,072 | 30 | 446 |
| Brent | 19,981 | 179 | 5,024 | 5,021 | 3 | 417 |

No missing overlap minute has positive native volume. No returned vendor row
has zero volume. The correspondence between missing minutes and zero native
volume is established **only within this captured overlap**; the entire
fourteen-day missing set lacks equivalent native evidence.

All five fields are compared on **74,360 shared field values**. Maximum absolute
price differences are below; all exceed the declared tolerance when nonzero.

| Asset | Open | High | Low | Close |
|---|---:|---:|---:|---:|
| SPCX | 0.15 | 0 | 0.02 | 0.05 |
| SNDK | 3.40 | 0 | 0.40 | 0.70 |
| Brent | 0.05 | 0.02 | 0.06 | 0.06 |

Numerical volume differences must not inflate the price disagreement count.
The complete reports retain 2,557 / 3,182 / 3,440 nonexact rows respectively,
many solely because of tiny floating-point volume differences. All SNDK and
Brent shared volumes meet the declared tolerance. SPCX has one shared volume
error of approximately **1.0550e-10**, slightly above it. The stated tolerance
was not relaxed after observing that result. SPCX has 554 rows with any field
beyond tolerance, including 553 with an OHLC price difference.

These observations establish source incompatibility under the declared use.
They do not establish corruption of either feed. Different trade aggregation,
bar-boundary behavior or retrospective revisions remain possible explanations;
none was resolved by this experiment.

## Validation and implementation

The acquisition driver reuses the earlier pinned HTTP recorder and native
immutable vendor-bundle writer. The primary auditor verifies raw-to-parquet
reproduction and original HTTP-body equality before comparing the entire
completed native overlap. It preserves every discrepancy and exact gap.

The independent auditor imports neither the primary comparator nor the vendor
normalizer. It reads original HTTP bodies and native parquet directly, verifies
the request/cursor chain and hashes, compares values using Decimal arithmetic,
and groups missing intervals independently. Both initial and archived runs
produce identical complete comparison objects, including all changed values,
errors, field counts, source-only timestamps and gap endpoints.

**79 offline controls pass**, repeated from the committed Git archive. The new
comparison helper has **36/36 statements and 12/12 branches covered**. Controls
include incomplete-minute exclusion, exact versus tolerance counts, empty
overlap, missing zero/positive-volume bars, extra interior minutes, malformed
boundaries/tolerances, duplicate/unsorted clocks, naive timestamps and nonfinite
values. Coverage is specific to that helper, not every acquisition/audit driver.
Ruff passes. New files are at most 127 lines and functions at most 33 lines.

The archive contains twenty tool files, all reverified after replay. Its 112,640
bytes hash to
`83060db222d820dfe40c8ce188d189685751aa88594d854301005ef8f3a2ec4a`.
Nine declared implementation/input references remain unchanged. Archived tests
and both full auditors ran with network and `.env` access denied and writes
limited to the owned evidence directory. The network acquisition is a separate
retained operation and was not repeated during offline validation.

The initial seven-control green result and missing-module red result remain
retained. Additional boundary controls bring the research suite to 79. Two
semicolon lint findings in the independent driver were corrected before commit;
comparison behavior remained equal after archive reproduction.

## Decision, alternatives and next evidence

| Option | Benefit | Limitation / failure mode | Decision |
|---|---|---|---|
| Replace missing native history with this vendor source | More historical timestamps | Fails full-grid and observed price equality | Reject as an equivalent replacement |
| Fill missing vendor minutes | Could repair cadence under an explicit reconstruction model | Leaves observed OHLC differences; creates unobserved values | Does not satisfy this experiment |
| Leave live inputs unchanged | Preserves the qualified original startup behavior | Fourteen-day stability remains unknown | Retain current deployment |
| Locate earlier exact native 1m captures | Could complete the required source evidence | Coverage, dates and revision policy must be authenticated | Next source investigation |

The separate collector supplement still supplies complete timestamp coverage for
BTC, ETH, SOL and HYPE. It does not qualify their cross-source value precedence
or first/latest revision policy. Existing noncrypto collectors use 15m and
cannot supply missing native 1m candles. The seven-asset history-length
comparison therefore remains deferred. Minimum additional evidence is native
1m history for the remaining noncrypto intervals, with source identity and
availability/revision handling, followed by the fixed-setting provider replay.

Do not repeat this acquisition or comparison without new sources, a corrected
contract or contradictory evidence. Preserve the existing full native source,
independent reproduction and account-qualification jobs; their completed
results remain the highest-value pending evidence. Real prospective outcomes
remain sealed.

No live source, profile, parameter, position, stop or financial process was
changed by this work. No cache was installed, synthetic candle inserted, provider
output calculated or return estimated. This source audit proposes no live
deployment; rollback is unnecessary. Separate previously pending installation
approvals remain separate from the already executed backend-resume approval.
