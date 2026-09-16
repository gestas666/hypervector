# V89 restart history: dated collector-receipt supplement

Original passive-collector receipts close the previously identified timestamp
gaps for BTC, ETH, SOL and HYPE. Each now has **20,160/20,160 expected minute
timestamps** when combined with the prior authenticated, dated sources. SPCX,
SNDK and Brent still lack complete native one-minute coverage.

This updates the earlier inventory after adding a distinct source family; it does
not change that inventory's results for its declared startup/cohort/vendor inputs.
Confidence is high for the authenticated coverage counts. Source-value precedence,
indicator stability and return improvement remain unqualified. No provider or
sealed prospective economic outcome was evaluated, and no live process/source
was changed.

Research commit: `c70739758da2c49c8d86feb2c0b55230c9cf63d9`, pushed on
`research/v89-restart-warmup-coverage-20260916`.

## Fixed scope and acquisition evidence

The original startup cutoff remains **September 16, 14:58:38.179 UTC** in run
`bidirectional-live-1789569979897`. The expected minute-open grid remains
September 2, 14:59 through September 16, 14:58 UTC inclusive. Its initial incomplete
minute belongs to the captured input; a provider replay must apply the original
completion cutoff.

The original seven-asset collector uses native **1m** bars for BTC, ETH, SOL and
HYPE, and **15m** bars for SPCX, SNDK and Brent. The four-core native scope was
declared before extracting source values. The later collector includes inherited
receipts and supplies no additional timestamp coverage in the preliminary index
inspection; this supplement uses the original collector once. Coarse noncrypto
bars do not supply native one-minute identities.

The collector manifest SHA256 is
`47d9a323ba375a986520d333d1a2a354bbb0b25568729eb292298d340cf66aa9`,
matching dated September 8 qualification copies. All **15 pinned collector
source files** matched before capture. SQLite's consistent backup API produced
a read-only research snapshot while the original collector continued running;
the frozen study/contract identity and SQLite integrity check were verified.
Snapshot SHA256:
`01c4c37ce2479af63b5d1bc300d7ae8c9cbcc8b90e53c05b24a28f2d74200de4`.

For each previously missing core minute, selection uses the earliest indexed
first receipt no later than the fixed cutoff. Later revisions and late-arriving
older event timestamps cannot bypass that cutoff. The selected original receipts
range from **September 8, 19:39:41.642** through **September 13, 03:38:06.596 UTC**.
These are retained local transport receipt clocks, distinct from the September 16
snapshot time. Original HTTP headers remain available; they are not asserted to
be externally trusted timestamps.

## Validated new coverage

**23,250 selected full candle values** match **21,887 original response files**,
totalling **57,309,001 bytes**. Every outer-envelope and response-body hash matches.
Validation checks endpoint, authority, schema, successful HTTP status, exact
one-minute public request, symbol, query bounds, receipt clock, minute completion,
finite/consistent OHLCV, trade count, normalized full indexed value, value hash and
availability timestamp. Duplicate selected identities cannot increase coverage.

Selected-row export SHA256:
`fccd8704a06e0fb4bbe0bf4ab9da970020ddf3558f6bcbe814af3dd0a9b5afaa`.

| Asset | Newly authenticated missing minutes | Dated-source coverage | Remaining gaps even with all prior potential vendor sources |
| --- | ---: | ---: | ---: |
| BTC | 5,774 | 20,160 | 0 |
| ETH | 5,776 | 20,160 | 0 |
| SOL | 5,786 | 20,160 | 0 |
| HYPE | 5,914 | 20,160 | 0 |
| SPCX | 0 | 10,723 | 3,104 |
| SNDK | 0 | 10,628 | 3,005 |
| Brent | 0 | 7,158 | 3,118 |

The new counts describe source coverage, not four completed history-length
strategy comparisons. The primary and independent results retain every remaining
noncrypto gap from the prior inventory; no all-asset completeness claim follows.

## Reproduction and controls

Three complete primary runs, including committed archive tooling, produce
identical results. Two SQL audits independently extract timestamps from the
original authenticated response bodies, construct unions through anti-joins and
reproduce every asset count and exact remaining gap. This independent coverage
audit does not import the primary receipt parser. Full OHLCV/index equality is
checked by the primary parser and its hand-constructed controls; no cross-source
OHLCV conflict policy is inferred from timestamp agreement.

**63 offline controls pass**, repeated from the committed archive. The two new
receipt selection/authentication modules have **102/102 statements and 48/48
branches** covered in both unit runs. Controls include late values, later
revisions, future receipts, coarse/private/wrong-symbol requests, request bounds,
failed transport, unsafe filenames, altered hashes/values, invalid OHLCV/counts,
duplicate timestamps, missing interval miscounts and incomplete/unrequested bars.

All fifteen archived tool files match after replay. Archive SHA256:
`148b8a0aac7eb216e78698eb7ec265b7b15bcc0985908d354a54dc17cf804361`.
Archive tests and full replays run with networking denied and writes restricted
to owned evidence. The first full archive replay failed when SQLite's sorter
attempted to use a system temporary directory. Setting `SQLITE_TMPDIR` to an
owned directory resolved that harness limitation without changing source or
weakening the sandbox. The original failure remains retained.

Other retained failures include the test-first missing module and two deliberate
strict-type regressions: the initial research parser accepted floating-point
schema/status values equal to integers. It now requires integer types. The actual
captured outputs remained identical after this correction. No collector or live
implementation was modified by these research-parser fixes.

## Decision and remaining work

Recommendation: retain the authenticated core receipt supplement and focus the
remaining native one-minute source search on the three noncrypto assets.
Why now: the prior inventory provided exact gaps, and a separate dated source
family supplies the core minutes. Applicable regime: initialization/source
integrity across regimes. Proposed live change: none. Expected upside: a more
faithful basis for the intended fixed-cutoff history-length experiment; no
demonstrated return improvement.

| Alternative | Benefit | Limitation | Decision |
| --- | --- | --- | --- |
| Authenticate original dated core receipts | Closes core timestamp gaps with original evidence | Value precedence and noncrypto history remain open | Retain |
| Treat later collector copies as independent observations | None for this missing-minute question | Duplicates inherited sources | Exclude duplicate coverage |
| Expand 15m noncrypto bars into 1m bars | Produces an artificial grid | Changes source semantics and conceals the requirement | Exclude |
| Seek original/native noncrypto minutes and their provenance | Can complete the intended seven-asset source requirement | Additional retrieval or absent-bar semantics may remain necessary | Next source investigation |

Next requirements: locate/authenticate the exact remaining noncrypto minute
intervals or establish native absent-bar semantics explicitly; retain acquisition
vintage; resolve all cross-source OHLCV overlaps/revisions; preserve actual startup
values on overlap; pin histories and first/latest policy before evaluating native
outputs at unchanged clocks and parameters. Do not relabel a partial or mixed-
frequency experiment as the full seven-asset comparison. The separate long native
source/reproduction/account qualification jobs remain active and independent.

Changed raw/index/manifest hashes, a post-cutoff receipt, omitted/duplicated
identities or different independently calculated gaps falsify the associated
coverage acceptance. Additional authenticated sources update the remaining-data
conclusion through a new journal revision. No live deployment or rollback is
indicated by this source audit; originals and prior results remain preserved.
No live approval is requested or exercised.

Evidence:
`data/logs/research/bidirectional_cohort/v89_restart_warmup_collector_receipts_20260916_v1/`.
