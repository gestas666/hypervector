# V89 native HYPE hold controls and complete captured matrix orchestration

This review records research qualification and candidate code. It does not install a live strategy, change leverage or control the financial backend. The full fourteen-day native experiment remains open.

## Findings and changes

The HYPE controls now exercise the actual default provider and canonical classifier over fabricated complete fourteen-day one-minute candle windows. A final-hour half-percent rise, fall or flat path produces native `TREND_UP`, `TREND_DOWN` or `RANGE` evidence. That evidence reaches the original maximum-hold policy without substituting regime labels. Favorable fresh evidence permits extension at the soft deadline; opposed or range evidence does not. The 60,000 ms freshness boundary is inclusive, 60,001 ms is stale, the accepted twenty-second entry delay remains part of the deadline, and the twenty-four-hour hard cap holds with stale or absent evidence.

These controls begin with a manually accepted synthetic long. The complete held interval stays above its original stop, avoiding a scenario that assumes a position survived an earlier stop. They do not demonstrate a native HYPE entry, public receipt capture, a complete native account, or profitability.

The new `scripts/v89_captured_account_matrix.py` connects the existing components across all 24 registered source/cost/timing/allocation cases. It authenticates the original study and fixed seal, verifies the running implementation against its exact git archive, collects each source variant once through the complete study end, executes each corresponding native calendar/account, and invokes the existing independently reconciled comparison publisher. It retains the fixed primary pair and losses or empty activity; it does not select cases by results. A JSON request supplies explicitly pinned absolute source references. There is no seal override, arbitrary case selection, pickle loader or live authority option.

A new failure experiment found an actual defect in the initial runner: changes to its retained manifest or source-summary bytes could escape input verification and still receive a completed root report. Two failing regressions reproduced this. The corrected runner pins those artifacts immediately after writing them, includes their original identities in case evidence, and reauthenticates them before and after comparison publication. A technical failure retains partial evidence without a completed root `report.json`.

## Frozen source and validation

HYPE qualification commit: `d580b7d4f4b576c898b93485b0859180507e5f6b`.

- Candidate: **14 passed** in 5.02 seconds; extracted archive: **14 passed** in 4.86 seconds.
- Archive SHA-256: `3978502385ea33a5df6d20b18e9af557104ce4014a70dee21cfd31fe00f152c3`; 5,775 extracted members independently matched their archived bytes.
- The qualification receipt explicitly distinguishes actual native classification/hold behavior from the manually supplied entry and fabricated prices.

Runner commit: `e207f6ea24f390ddffed4e9741b8d97198e9254e` in the isolated prospective-account candidate.

- Final candidate scope/orchestration/comparison suite: **99 passed** in 26.96 seconds. Coverage of the new runner is **104/104 statements and 12/12 branches**; that measures exercised implementation, not completeness of the financial model.
- The runner's 23 orchestration controls substitute expensive collection, calendar, account and publication stages while checking their exact boundaries. The adjacent scope and comparison tests retain their own established qualification limits.
- Two retained-metadata corruption regressions failed before the fix. The earlier broad regression run was deliberately superseded after that defect was reproduced; it terminated with 143 and is not reported as passing.
- Archive SHA-256: `2e4a4ec1b0b57ce334da33547562c4e9312d4361e35635c7450ba97fe24daa6f`; 5,779 members verified at extraction.
- The actual archived CLI was invoked against the real follow-up registration, manifest SHA-256 `14341a8df3ebdabb4e4d6a8f61f86f0b7a5e00991f99955709476d09e7cd1b41`, with a deliberately absent market tape. It returned the expected fixed **2026-10-07T00:00:00+00:00** seal error before opening that tape or creating output. No real prospective outcomes were evaluated.
- Final archive regression execution: **122 passed** in 249.25 seconds, including the 99 scope/orchestration/comparison controls and 23 adjacent account tests with complete two-day, zero-trade, terminal-open and failure cases. This is not a full fourteen-day native runner result.

All evidence is below `data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/`. Key records are `native_hype_hold_qualification_v1.json`, `captured_matrix_runner_source_manifest_v1.json`, `captured_matrix_runner_retained_metadata_red_v1.txt`, `captured_matrix_runner_tests_v4.txt`, `captured_matrix_runner_coverage_v3.json` and `captured_matrix_runner_preseal_receipt_v1.json`.

## Ongoing qualification and monitoring

The original full-window native job remains the same research process, PID 29346/session 49265, started at 08:18 UTC on September 16. It uses unchanged archived collectors and complete fabricated sources, with a 72-hour technical bound. Each source variant requires 84,679 publications and 2,352 funding observations. Its outputs must still flow through complete fourteen-day native calendars, all account cases and report reproduction. Neither the HYPE controls nor orchestration tests replace that requirement. The original economic outcome seals remain in force for actual public captures.

Archive comparison found 1,960 matching Python implementation files. The only differences are the new runner and the two previously qualified original-entry-margin reporting files. Native collector, classifier, source binding and native routing files match byte-for-byte. Reuse of the ongoing job's results still requires its completed qualification result, exact retained-output hashes, full study/tape identity and retention of both collection and account/reporting archive provenance. No incomplete source prefix is qualified for full accounts.

The later seven-asset health watch reached its normal six-hour deadline at 08:50:53 UTC: 1,430 observations, final collector state healthy, exit 0. Its exact terminal result was retained before starting the next passive watch, PID 18380/session 26726. The public collector remains PID 51194 with its original process identity. No collector or financial process was restarted. Historical late warmup receipts in its coverage snapshot remain explicit; healthy current process status does not establish timely historical coverage.

## Recommendation, alternatives and limits

**Recommendation / why now:** retain the HYPE boundary qualification and candidate matrix orchestration because they close identified gaps between source evidence, native policy and whole-account comparison. Keep the candidate isolated until the remaining full native experiment and reproduction finish.

**Observed problem:** programmed labels alone did not qualify actual candle classification reaching HYPE hold policy; separate account/reporting APIs lacked one complete authenticated captured-study runner; initial runner metadata could change without invalidating completion.

**Applicable regime:** the HYPE test covers fabricated uptrend, downtrend and range context. Matrix scope and evidence checks apply to the full registered study across regimes and do not introduce a regime filter.

| Alternative | Benefit | Cost or limitation |
| --- | --- | --- |
| Keep manual harnesses only | No new orchestration code | Repeated wiring and incomplete-run reporting remain easier to misinterpret |
| Use the isolated complete runner | One explicit original-scope flow with authenticated completion | Requires full native integration and immutable output storage |
| Treat unit success as strategy validation | None established | Would confuse substituted control stages with strategy/account evidence |

**Proposed live change:** none. **Expected upside:** more reliable research evidence and detection of incomplete or corrupted comparisons; no expected-return uplift has been estimated.

**Main risks:** missing or late captured inputs, long native runtime, conditional candle execution differing from venue fills, incorrect economic interpretation despite internally reproducible arithmetic, and candidate integration defects outside covered controls. HYPE's frozen replay model still lacks a liquidation trigger; shared ambiguous bars retain their existing liquidation/stop/target ordering.

**Validation still required:** finish the existing native collection process; compile and reconcile all full fourteen-day native accounts, including original daily/split attribution and terminal opens; reproduce from frozen code; evaluate actual source blocks only after their registered seals.

**Success metrics / falsifiers:** every registered case and full clock grid present; original source, economics and archive identities retained; exact independent account reconciliation; HYPE support/freshness/deadline behavior remains consistent with native evidence. Changed inputs, missed cases, successful publication after corruption, altered seals or archive disagreement reopen the affected qualification.

**Confidence:** high for the reported test outcomes and observed pre-seal rejection; limited to the exercised sources and boundaries. Full native account and strategy performance confidence remains unestablished.

**Rollback:** the implementation exists only in its isolated candidate commit. Retain the prior source archives and evidence; no financial process action is part of candidate rollback. **Explicit approval requested:** none for this research work. Any proposed live strategy, sizing, risk or deployment change remains subject to the separate human-control instruction.
