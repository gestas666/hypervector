# Installed HIP-3 candle acquisition and cache cadence correction

Explicit HIP-3 archived candle acquisition is now installed. The previous client rejected `xyz:SNDK` and offered only the core endpoint. The new `--market-family hip3` option preserves the exact builder identity, uses the dedicated route, separates its immutable bundles and verifies the source family/API when reading them. Core positional calls and legacy core bundles remain supported.

The optional research-cache installer also had a cadence defect: it applied one-minute gap repair to every requested interval. Unsupported nonminute cache-install requests now fail before acquisition with an actionable message. Higher-interval raw acquisition remains available. One-minute repair behavior is preserved and covered by a regression test.

Confidence: **high for these bounded technical corrections**, supported by failing-before/passing-after tests, installed-source tests, authenticated data acquisition and raw reproduction. Wrong namespace routing, accepted contradictory provenance, a core regression or minute bars installed under a higher-interval key would falsify this assessment. No predictive or profitability improvement is established.

## Validation

- Initial feature tests: 26 expected failures and one existing pass before implementation. The cache guard separately reproduced three expected failures.
- Final importer suite: **206 passed** in the isolated worktree and **206 passed** after installation. The dependent BTC research-script test also passed in the main workspace: **207 installed tests** total.
- New request/provenance and cache-helper modules: **100% statement and branch coverage**. The three measured modules combined have approximately **88%** coverage; the older candle module retains untested defensive branches.
- Ruff lint and formatting passed. All seven changed Python source/test files remain within 500 lines per file and 50 lines per function, with explicit return types and no `Any`.
- A bounded July 1, 2026, 14:00–15:00 UTC request returned HTTP 200. The installed importer verified **four 15-minute bars**, exact half-open cadence, raw HTTP/body hashes, saved raw-page equality and raw-to-Parquet reproduction. The vendor's inclusive 15:00 bar was excluded.
- Forward and reverse patch rehearsal reproduced exact prior/new file bytes. Nine implementation/test/guide/plan files were installed from candidate `5a671cb3e178ee68dbede4286711e34fcfb9f8b6` onto base `cdb8c67620c569b23d8d4c8ad07a2b1ed42d5917`.
- The installed TUI binary and 77 other protected source, configuration, ledger and unrelated-work files retained their prior hashes.

The first coverage command failed during NumPy import before collection completed. A file-filtered coverage invocation passed without source changes to resolve that instrumentation failure; the initial log is retained. The precise instrumentation failure was not independently isolated. An unavailable `python -m ruff` invocation was replaced with the already installed Ruff executable.

## Earlier-history availability findings

Metadata inspection found **3,463** pre–July 21 SNDK archive manifests declaring **19,661,957 L2 rows**, spanning February 26 to July 21. All declared child files exist; payload hashes for this entire L2 inventory were not verified. These are order-book snapshots, not traded candles.

Two earlier research source exports contain February funding records, while their native SNDK candle records cover only July 31–August 6. Other older trade exports include prior experiments before July 21. Consequently, a separate date interval cannot be presented as an untouched holdout merely because it precedes the latest 47-entry study.

The native SNDK 15-minute source used by the recent studies contains 4,800 bars from July 19 through September 6. The inspected files therefore did not establish a substantial separate older native-candle sample.

The [vendor contract](https://docs.0xarchive.io/schemas/operations/get-hip3-candles) identifies a dedicated HIP-3 endpoint, case-sensitive symbols and trade-aggregated candles. The bounded successful probe establishes availability for one earlier SNDK hour. It does **not** establish full-period completeness, equivalence to native candleSnapshot bars or usable entry-arrival provenance. Price/return outcomes from the newly acquired historical hour were not inspected or calculated.

A targeted impact check inspected all three nonminute cache keys directly under the main `data/cache` directory. Their 95,040 rows have the expected 5-minute/15-minute cadence, with no over-dense or off-cadence rows and no `hl_gap_fill` labels. Thus this check found no evidence of the repaired cadence defect in those three files. They contain explicitly labeled Binance and Hyperliquid sources, so their cadence check does not qualify them as venue-matched Hyperliquid history. Other data roots were outside this check.

## Runtime boundary

No trading process was started or restarted and no strategy, leverage, sizing, asset universe or order was changed. At **13:58:01 UTC**, unsigned venue evidence showed the existing **0.306 SNDK short at 10x isolated** and a full-size reduce-only buy stop at **1669.9**, reported open. Seven HTTP response envelopes were verified. A subsequent process inventory found no matching backend, reporter or TUI processes. This is a timestamped observation, not a guarantee of future account state.

The newer TUI remains installed with SHA-256 `eaf4d25836ff0533b6b451f887921d97eed9af9aa021a70fade47408c5aeb9a1`. This importer change does not require a Rust rebuild. The actual Terminal window was not inspected in this task.

## Next investigation and limits

The highest-value next investigation is a fixed overlap qualification of archived HIP-3 traded candles against the already available native source, including timestamp semantics, missing bars, volume and OHLC agreement. Specify the comparison window and acceptance rules before acquisition; retain discrepancies. Only then choose a separate historical test protocol, with realistic costs and an explicit inventory of earlier reuse. Do not search new strategy filters on the existing 47 entries.

No live strategy recommendation follows from this data-access correction. The September 22 and September 23 prospective seals remain unopened. Missing vendor request identifiers, quote volume or trade count remain explicit parser failures rather than synthesized evidence.

## Evidence and rollback

Evidence directory: `data/logs/research/bidirectional_cohort/v89_sndk_prior_history_20260912_v1/` in the main workspace. Key files are `installation_verified.json`, `installation_prepared.json`, `installed_source.patch`, `source_backup.tar.gz`, `acceptance_verified.json`, `installed_runtime_verified.json`, `existing_nonminute_cache_audit.json`, `prior_manifest_metadata.json` and `earlier_research_provenance.json`.

The backup preserves every previously existing file modified by the implementation patch. The prepared manifest records old/new SHA-256 values and identifies newly created files. Rollback must first confirm no intervening edits, then restore only this patch's files; retain acquired evidence. The forward/reverse rehearsal verified this boundary. Operator usage is documented in `docs/guides/oxa-hip3-candle-history.md`.
