# 0xArchive Hyperliquid History Ingest Implementation Plan

> **Execution note:** Implement task-by-task with test-first review checkpoints.

**Goal:** Add a bounded, auditable 0xArchive ingestion path that acquires venue-native Hyperliquid BTC L2 history without exposing credentials and produces replay-compatible JSONL plus immutable raw evidence.

**Architecture:** A typed REST client will call the pinned 0xArchive OpenAPI routes with explicit Hyperliquid core, symbol, UTC window, page size, and maximum page count. Every successful response retains its request ID and raw envelope before validated order-book snapshots are normalized into the existing `book-align`/maker-replay JSONL contract. Historical vendor rows will not be inserted into the live `EventArchive`, because they do not contain a genuine local receipt timestamp.

**Tech Stack:** Python 3.13, requests, Decimal, dataclasses, JSON/JSONL, pytest, 0xArchive REST/OpenAPI.

---

### Task 1: Freeze the vendor contract and security boundary

**Files:**
- Create: `tests/test_oxa_history.py`
- Create: `src/hypervector/data/oxa_history.py`

1. Write a failing test proving the client requires `OXA_API_KEY`, sends it only as `X-API-Key`, uses the Hyperliquid core route, and never includes the value in output metadata or exceptions.
2. Run `uv run pytest tests/test_oxa_history.py -q` and confirm RED because the module does not exist.
3. Implement typed request configuration and an injected `requests.Session` boundary with explicit timeout.
4. Reject missing keys, non-UTC or inverted windows, page limits outside `1..1000`, non-positive maximum pages, and symbols outside a conservative identifier syntax.
5. Run the focused test and confirm GREEN.

### Task 2: Validate and normalize native L2 snapshots

**Files:**
- Modify: `tests/test_oxa_history.py`
- Modify: `src/hypervector/data/oxa_history.py`

1. Add failing tests for the documented REST envelope: `success`, `data`, `meta.request_id`, and `meta.next_cursor`.
2. Add failing tests for malformed timestamps, symbol mismatch, empty/crossed books, non-positive price or size, negative order count, more than 20 levels, unsorted bids/asks, duplicate timestamps with conflicting content, and missing request IDs.
3. Add a valid fixture proving decimal strings remain unmodified in raw evidence while the normalized JSONL uses the existing `px`/`sz` structure accepted by `load_l2_jsonl`.
4. Implement immutable typed snapshot/level/page models and fail-fast validation.
5. Implement a replay-compatible row containing exchange timestamp, explicit source `0xarchive_hyperliquid_native_l2`, 20 measured levels, and no fabricated receive timestamp.
6. Run focused tests and confirm GREEN.

### Task 3: Implement bounded pagination and atomic evidence storage

**Files:**
- Modify: `tests/test_oxa_history.py`
- Modify: `src/hypervector/data/oxa_history.py`
- Modify: `src/hypervector/infra.py`
- Modify: `docs/infra-data-layout.md`

1. Add failing tests proving pagination reuses the original symbol/window/depth, passes only the returned cursor, stops at `max_pages`, and records a continuation cursor when intentionally bounded.
2. Add a failing test proving an existing output directory is not overwritten.
3. Add a failing test proving raw pages, a manifest, and normalized JSONL are committed atomically only after all fetched pages validate.
4. Add `cache/vendor/0xarchive` to the data layout.
5. Implement atomic staging-to-final-directory publication with raw page envelopes, SHA-256 checksums, request IDs, coverage timestamps, row counts, cursor status, and OpenAPI/source identifiers.
6. Run focused tests and confirm GREEN.

### Task 4: Add a safe Hypervector CLI command

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_paper_cli.py`
- Modify: `src/hypervector/cli.py`
- Modify: `skills/hypervector-cli/SKILL.md`

1. Add a failing CLI test for `oxa-book-fetch` with required `--start` and `--end`, default `--limit 1000`, default `--max-pages 1`, fixed Hyperliquid core venue, and no secret fields in JSON output.
2. Add a failing CLI test proving technical/API failure returns an actionable non-success result without success-shaped fallback data.
3. Add `oxa-book-fetch` to command discovery and route it to the bounded ingestion service.
4. Report paths, request IDs, rows, exact observed coverage, validation results, and continuation state.
5. Document a one-page qualification command and state that broad backfills belong in the Data Catalog.
6. Run focused CLI and ingestion tests.

### Task 5: Qualify a real overlapping window

**Runtime artifacts:**
- Create under: `data/cache/vendor/0xarchive/hyperliquid/BTC/`
- Compare with: `data/cache/events/hyperliquid/BTC/`

1. Fetch one bounded minute overlapping current WebSocket evidence with `max_pages=1`.
2. Verify request ID retention, timestamp monotonicity, 20-level depth, positive values, non-crossed books, and cursor reporting.
3. Compare exact/common timestamps against independent `hyperliquid_ws_l2Book` rows and report top-of-book and level agreement.
4. If the sample disagrees materially, stop before widening and preserve both sources for diagnosis.
5. If it passes, fetch one hour with an explicit page bound and record whether pagination fully covers the window.

### Task 6: Complete verification and publication

1. Run:

```bash
uv run pytest tests/test_oxa_history.py tests/test_cli.py tests/test_paper_cli.py -q
uv run pytest tests/ -q -m "not network"
uv run ruff check src/hypervector/data/oxa_history.py src/hypervector/cli.py tests/test_oxa_history.py
git diff --check
```

2. Review secrets, error paths, type hints, public docstrings, 500-line files, 50-line functions, and raw-data provenance.
3. Record any unresolved Data Catalog purchase/size quote as an external action, not as completed ingestion.
4. Commit, push, fast-forward into `main`, clean up the feature branch, and leave the live shadow daemon running.

## Success and falsification criteria

- The key never appears in stdout, stderr, manifests, normalized output, exceptions, tests, or Git.
- Every stored page has a non-empty 0xArchive request ID and checksum.
- All normalized rows pass native 20-level book invariants and load through `load_l2_jsonl`.
- Bounded calls stop deterministically and expose continuation rather than silently truncating.
- At an identical exchange timestamp, 0xArchive and the independent Hyperliquid WebSocket archive agree at the top of book; persistent disagreement falsifies source qualification.
- Bulk 30/180-day acquisition remains a Data Catalog operation unless measured API pagination cost and duration support a different decision.
