# V89 restart history: retained native snapshot supplement

Sixteen retained native sources add **27,454 previously missing one-minute
observations** across SPCX, SNDK and Brent. The declared source pairs agree
exactly on **295,415 OHLCV field comparisons** after excluding incomplete
captured candles. Independent reconstruction and committed-archive replay
reproduce all coverage counts, gap endpoints and compared values.

**Confidence: high for this bounded source qualification.** Complete fourteen-day
coverage is still absent. These observations do not establish that the current
strategy would trade differently with a longer initialization, recover the
discarded inputs of earlier live processes, or predict improved returns.
Changed source bytes, incorrect local availability records, a missing source
pair or independently differing values/gaps would falsify this acceptance.

## Fixed scope and source provenance

The experiment retains the existing startup observation cutoff,
**September 16 14:58:38.179 UTC**, and expected input grid from **September 2
14:59 through September 16 14:58 inclusive**, 20,160 minutes per asset.
The original startup frame includes its then-incomplete final minute as actual
input evidence. Pairwise value comparisons exclude that final minute.

Evidence is under
`data/logs/research/bidirectional_cohort/v89_restart_native_snapshot_supplement_20260916_v1/`.
The declaration names all sixteen additional sources before their combined
coverage/value audit. Tools are committed and pushed as
**15338eda071f3dbbdb8c773360926941cf527d49** on
`research/v89-restart-warmup-coverage-20260916`.

| Retained source | Scope | Availability evidence | Captured rows |
|---|---|---|---:|
| September 7 native minute parity frames | All three assets, September 4–6 | September 7 journal pins the report and frame hashes | 12,960 |
| September 8 native HTTP response | SPCX, September 6 noon–September 8 09:00 exclusive | Original receipt 09:34:16.932187 UTC; dated journal and manifest | 2,700 |
| September 11 cold/warm profiler inputs | Three packets for each of the three assets | Dated journal pins the evidence manifest, frame hashes and 15:26:48.232080 completion receipt | 15,406 |
| September 14 native HTTP responses | All three assets, recent history through September 13 noon | Original per-response receipts at 12:09:32–12:09:33 UTC and manifest | 10,893 |

The four retained HTTP bodies and their hashes are revalidated along with exact
public request symbols, 1m interval, bounds, successful status, local receipt
ordering and original candle identities, close clocks and OHLCV. The retained
capture scripts name the Hyperliquid mainnet info endpoint. Their response
envelopes do not separately retain the URL. The twelve parquet sources carry
`hl` labels throughout; no `hl_gap_fill` or substituted source is accepted.
They are retained normalized frames, not raw HTTP response captures.

All local availability records precede the fixed restart cutoff. These are
local dated records, not externally authenticated timestamps. Their candle
dates precede their capture dates; the later snapshot must not be treated as an
earlier trading decision's first receipt. Profiler completion is distinct from
its requested observation cutoff. One source-incomplete tail row is excluded
from each of nine profiler frames: **41,959 captured rows / 41,950 completed
rows** remain across the sixteen sources, including overlaps.

The September 12 source discovered during the bounded search was a **15m SNDK
response** and supplies no missing 1m input. The September 14 prepared portfolio
parquets identify the underlying September 11 frames and September 14 bodies;
the audit reads those original inputs rather than counting the prepared copies
as independent evidence. Existing noncrypto passive collectors also use 15m.

## Validated coverage and unresolved intervals

The prior known noncrypto coverage is independently reconstructed from the
frozen pre-start cohort publications and actual startup frames. No vendor
timestamp union contributes to these new native counts.

| Asset | Prior known native minutes | Added native minutes | Known native minutes / 20,160 | Remaining missing |
|---|---:|---:|---:|---:|
| SPCX | 10,723 | 8,983 | 19,706 | 454 |
| SNDK | 10,628 | 8,264 | 18,892 | 1,268 |
| Brent | 7,158 | 10,207 | 17,365 | 2,795 |

Exact remaining intervals, with inclusive endpoints and all times UTC:

- **SPCX:** September 2 23:14–September 3 06:47, 454 minutes.
- **SNDK:** the same 454-minute interval, plus September 7 00:00–13:33,
  814 minutes.
- **Brent:** September 2 14:59–September 3 23:59, 1,981 minutes; plus
  September 7 00:00–13:33, 814 minutes.

All 92 named source pairs are represented; 62 share completed timestamps.
Their **59,083 shared minute comparisons** cover all five OHLCV fields and
include both first and latest retained cohort-publication variants. Every
comparison is exactly equal, so tolerance does not hide a discrepancy. These
are repeated overlaps, not 59,083 independent market observations. The complete
report preserves empty intersections as no-overlap evidence rather than
successful full-source equality.

## Validation and audit-reader repair

The primary audit checks all 36 declared source/metadata/dependency references,
reconstructs the prior native coverage and compares every source pair. The
independent audit reads original JSON bodies and publication records plus Arrow
parquet, uses independent interval grouping and Decimal comparison, and verifies
complete coverage and pairwise value objects. It imports neither the primary
snapshot decoder nor its coverage/pair driver. It is independent value/coverage
reconstruction, not a second implementation of every protocol rejection rule.

**119 offline controls pass**, repeated from the committed Git archive. The new
receipt helper has **73/73 statements and 32/32 branches covered**. Controls
reject wrong symbols/intervals, malformed request/receipt clocks, a receipt only
one microsecond beyond cutoff, changed body hashes, malformed candle identities,
duplicate/unordered minutes, invalid OHLCV, substituted sources, wrong counts,
unknown formats and absent completed input. Legitimate zero-volume candles are
retained.

A new source-replacement test exposed a race in the initial research reader:
it authenticated bytes, then reopened the parquet path for decoding. Replacing
the file between those steps caused a failure under the already checked source
identity. The corrected primary and independent readers decode the authenticated
in-memory bytes. The failing control remains retained; it now passes. Complete
native reports remain identical after this repair. No live reader changed.

Archived tests and both full auditors ran with network and `.env` access denied
and writes limited to the owned evidence directory. No new API request was
made. All **24 archived files** match their manifest after replay. The
143,360-byte tool archive SHA256 is
`d93216fc2ec76761f55c04668cca31f67ab4f3caec469da6d08f7645b8ad1586`.
Ruff and source-size/function-size checks pass. Coverage applies to the new
receipt helper, not every orchestration or independent-audit function.

## Decision and next evidence

| Option | Benefit | Limitation | Disposition |
|---|---|---|---|
| Retain these authenticated native sources | Closes 27,454 missing observations with observed value agreement | Explicit older intervals remain absent | Accept the source supplement |
| Fill the remaining intervals or reverse-resample 15m bars | Creates a complete-looking timestamp grid | Does not recover observed native 1m inputs | Does not satisfy this experiment |
| Use the previously tested HIP-3 vendor replacement | Adds timestamps | Already failed native price and grid parity | Remains rejected as an equivalent replacement |
| Leave live initialization unchanged while completing evidence | Preserves the qualified actual startup behavior | Fourteen-day output stability remains unknown | Current deployment unchanged |

The minimum next source requirement is now the exact older intervals above.
Search retained September 3–6 native responses or startup inputs for the early
gap, and September 7–8 native inputs for SNDK/Brent. Do not rerun the completed
sixteen-source audit without new data or a contradiction. If no such source can
be authenticated, record that historical limit and use a separately declared
future native capture for a complete fourteen-day experiment. Do not substitute
a shorter replay and call the original requirement complete.

Core timestamp coverage from the previous collector supplement remains
qualified, with its cross-source precedence/revision qualification still
separate. The complete seven-asset changed-history provider replay remains
pending. Preserve the ongoing native source/reproduction/account jobs; their
terminal results remain the highest-value pending evidence. Real prospective
outcome seals remain unchanged.

No strategy, route, asset scope, leverage, sizing, stop, execution setting, live
source or financial process changed. No provider output or economic result was
computed in this experiment. There is no live deployment or rollback proposal.
