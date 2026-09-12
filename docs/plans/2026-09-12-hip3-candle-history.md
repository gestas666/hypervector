# HIP-3 Candle History Implementation Plan

> Execute locally with the writing-plans, test-driven-development and verification-before-completion skills. Existing user authorization covers this research importer correction; no execution changes are included.

**Goal:** Acquire and verify explicitly identified HIP-3 traded candles through the documented vendor endpoint, preserving core candle compatibility.

**Architecture:** Reuse the bounded candle client, existing market-symbol validator, immutable bundle publisher and raw-to-Parquet verifier. Extract request and source identity into a small module so the existing candle module stays below 500 lines. Add an explicit CLI family option; neither infer nor rewrite builder symbols.

**Tech Stack:** Python dataclasses, requests, pandas/Parquet, pytest, Ruff.

## Evidence and constraints

The current request validates core symbols only and fetches `/candles/{symbol}`. The vendor documents `/v1/hyperliquid/hip3/candles/{symbol}` with case-sensitive builder identifiers. A bounded GET for xyz:SNDK on July 1, 14:00–15:00 UTC returned HTTP 200 and five candle timestamps including the inclusive end. Only metadata was inspected; no returns were computed.

Source: https://docs.0xarchive.io/schemas/operations/get-hip3-candles (checked September 12, 2026). Retain the raw response and digest in `data/logs/research/bidirectional_cohort/v89_sndk_prior_history_20260912_v1/hip3_candle_probe_http.json` in the main workspace.

Good enough means exact family routing, namespace-separated storage, verified manifest identity, unchanged core positional calls/legacy bundles, explicit failure for malformed symbols or tampered provenance, and offline tests plus one bounded acquisition/reproduction. Earlier L2 and funding records are not substitutes for traded OHLCV. This work does not establish complete earlier history or predictive strategy value.

## Task 1: Request, route and provenance

Files: add `src/hypervector/data/oxa_candle_request.py`; modify `src/hypervector/data/oxa_candles.py`; add `tests/test_oxa_hip3_candles.py`.

1. Write offline tests for core/HIP-3 routes, exact symbol validation, immutable family-separated paths, round-trip raw verification, wrong-family/source/API rejection, and legacy core manifests.
2. Run the new tests against unchanged source and retain expected failures.
3. Move the existing request model without changing its first seven positional fields. Append `market_family: MarketFamily = "core"`. Use `validate_market_symbol`; derive `route`, `source` and `source_api` from the explicit family. Re-export the public request and interval types from their old module.
4. Pass the correct route to the REST client. Preserve the existing core cache path; insert `hip3` for HIP-3. Include family in new manifests/reports. Require exact HIP-3 provenance; accept only omitted family in legacy core manifests. Verify source API for both families.
5. Run new and existing candle tests. Commit only tested files.

## Task 2: CLI

Files: modify `src/hypervector/cli_oxa.py`; extend `tests/test_oxa_candle_cli.py`.

1. Write offline tests for `--market-family hip3 --symbol xyz:SNDK`, explicit defaults, wrong-family rejection before acquisition, and secret-free reports.
2. Observe the missing-option failures before implementation.
3. Add `--market-family` with `choices=("core", "hip3")`, default core, and pass it by keyword to the request.
4. Run all 0xArchive tests with network excluded, Ruff and structural checks. Do not alter live data/configuration.

Inspection update: `_install_candle_cache` unconditionally uses one-minute gap repair for every requested interval, risking mislabeled higher-interval caches. Add a failing test that a nonminute cache-install request stops before acquisition. Extract that focused helper into `src/hypervector/cli_oxa_candle_cache.py` (keeping CLI below 500 lines), reject unsupported intervals explicitly, and retain existing one-minute behavior. Raw higher-interval acquisition remains supported. This is a technical input-validation correction, not a strategy change.

## Task 3: Acceptance and installation

1. Run a bounded July 1, 14:00–15:00 UTC HIP-3 request with limit 10 and at most two pages into this study's isolated data root; do not install a strategy cache.
2. Verify raw hashes, normalized reproduction and exact four-row half-open cadence. Only report metadata, not price or return outcomes.
3. Back up the modified installed source files; rehearse the patch, install the validated importer and tests in the main workspace, then rerun affected tests there. Preserve unrelated dirty files and installed TUI binary.
4. Publish review, evidence hashes and research journal. Retain failures and rollback backup. Full-period historical validation is a separate next task with a fixed protocol before outcome inspection.

## Risks and alternatives

The vendor may omit optional volume/count fields, withhold older dates, or return sparse bars; retain explicit parser/cadence failures rather than fabricate values. A successful one-hour probe does not establish full-period completeness. Existing older studies mean temporal separation alone does not establish an untouched holdout. Doing nothing leaves the importer unable to request these assets; a one-off script fetches data but misses reusable identity and reproduction checks. No trading runtime, strategy parameters, risk settings, orders, or prospective seals are changed.

Rollback: restore only this change's backed-up source files after verifying no intervening edits. Keep immutable acquired evidence. Failure criteria: incorrect route/identity, core regression, unverifiable raw reproduction, or unexpected workspace changes.
