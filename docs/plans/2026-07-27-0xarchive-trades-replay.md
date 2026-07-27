# 0xArchive Venue Data and Trade-Aware Replay Implementation Plan

> **Execution note:** Execute task-by-task in this session with test-first checkpoints.

**Goal:** Acquire auditable Hyperliquid-native public trades alongside L2 books, then use those prints as a conservative maker-fill challenger in Hypervelocity replay.

**Expanded measured scope:** Persist a compressed, resumable 90-day BTC L2 and
trade archive plus a 90-day venue-candle cache. Raw vendor candles remain
unchanged; missing vendor minutes are explicitly labeled continuity fills only
in the installed research cache so the regime engine retains exact cadence.

**Architecture:** A shared secret-safe 0xArchive REST boundary will support independent book and trade importers. The trade importer will preserve participant-fill envelopes while normalizing one public match per venue `trade_id` by selecting the taker (`crossed=true`) fill. Historical data remains outside the live `EventArchive`; replay consumes explicit exchange timestamps without inventing local receipt times.

**Tech Stack:** Python 3.13, requests, Decimal, dataclasses, JSON/JSONL, pandas, pytest, existing Hypervelocity maker replay.

---

### Task 1: Extract the shared 0xArchive REST boundary

**Files:**
- Create: `src/hypervector/data/oxa_api.py`
- Modify: `src/hypervector/data/oxa_history.py`
- Test: `tests/test_oxa_history.py`

1. Keep the existing 27 book-ingestion tests green while extracting API root,
   symbol validation, injected HTTP session typing, authentication, timeout,
   HTTP error handling, and secret-safe network exceptions.
2. Retain the public `OxaHistoryClient` interface and existing CLI behavior.
3. Run `uv run pytest tests/test_oxa_history.py -q` after the refactor.

### Task 2: Validate and normalize public trades

**Files:**
- Create: `src/hypervector/data/oxa_trades.py`
- Create: `tests/test_oxa_trades.py`

1. Write failing tests for explicit UTC bounds, safe symbols, limit `1..1000`,
   positive page bounds, and secret-safe header authentication.
2. Write failing tests for malformed envelopes, missing request IDs, symbol or
   window mismatch, invalid sides, non-positive decimal price/size, invalid or
   missing trade IDs, and conflicting duplicate fills.
3. Prove raw decimal strings and all participant fills remain unchanged.
4. Normalize one public trade per `trade_id`: prefer exactly one
   `crossed=true` taker fill; accept a sole unambiguous legacy fill; reject
   contradictory groups rather than guessing.
5. Emit replay JSONL fields `ts_exchange_ms`, `symbol`, `trade_id`,
   `aggressor_side`, `price`, `size`, `vendor_request_id`, and source. Never
   add `received_ts_ns` or participant fee/PnL as market-wide execution cost.

### Task 3: Add bounded pagination, atomic storage, and CLI

**Files:**
- Modify: `src/hypervector/data/oxa_trades.py`
- Modify: `src/hypervector/cli.py`
- Modify: `tests/test_oxa_trades.py`
- Modify: `tests/test_cli.py`
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `docs/infra-data-layout.md`

1. Test cursor reuse, `max_pages` truncation reporting, cross-page participant
   grouping, per-trade originating request IDs, and conflicting duplicates.
2. Test atomic publication of raw pages, `trades.jsonl`, checksums, and a
   manifest; refuse overwrite of an existing window.
3. Add `oxa-trade-fetch` with required start/end and fixed Hyperliquid core.
4. Return non-success on transport/schema/storage errors without fallback data
   and without printing `OXA_API_KEY`.

### Task 4: Add conservative trade-through maker replay

**Files:**
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `src/hypervector/cli.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Write failing tests proving a sell-aggressor print strictly below a resting
   buy fills a long entry and a buy-aggressor print strictly above a resting
   sell fills a short entry; same-price prints remain unresolved.
2. Apply the same strict print-through rule to maker exits.
3. Merge book and trade events causally by exchange timestamp. Books establish
   displayed limits and signals; prints may fill only previously submitted
   orders.
4. Add optional `--trade-path` and `trade-through` replay output. Preserve the
   existing touch/through reports for comparison and label queue/partial-fill
   uncertainty explicitly.

### Task 5: Qualify samples, then acquire the paired 90-day BTC window

**Runtime artifacts:**
- `data/cache/vendor/0xarchive/hyperliquid/BTC/`
- `data/logs/research/`

1. Fetch trades for the already-qualified `2026-07-26T23:00:00Z` to
   `2026-07-27T00:00:00Z` book window and compare normalized trade IDs, sides,
   prices, and sizes with overlapping local WebSocket trade evidence.
2. Stop widening if common trade identities materially disagree.
3. Fetch bounded books and trades for `2026-07-26T00:00:00Z` to
   `2026-07-27T00:00:00Z`, exposing any continuation rather than claiming full
   coverage.
4. Record rows, pages, bytes, cadence/gaps, duplicate counts, checksum status,
   exact coverage, and API elapsed time.
5. Acquire hourly immutable book/trade bundles from `2026-04-28T00:00:00Z`
   through `2026-07-27T00:00:00Z` with bounded concurrent workers and resumable
   retries. Do not publish incomplete tasks.
6. Audit all 4,320 expected hourly bundles, manifest identities, declared file
   sizes, and SHA-256 checksums. Report zero-row vendor windows separately from
   missing bundles.

### Task 6: Run the real Hypervelocity friction comparison

1. Generate point-in-time canonical regime decisions for the paired window.
2. Run touch, book-through, and trade-through maker replay with the faithful
   70% margin, venue 40x leverage, 8% leveraged-margin target, configured maker
   fee, and current entry TTL.
3. Store a report-only JSON artifact. Report completed/open/pending trades,
   entry waits, holding times, fees, PnL, and disagreement between fill models.
4. Treat performance as an observed result, never as an implicit abort or
   strategy gate.

### Task 7: Verify and publish

1. Run focused importer, CLI, replay, and paper tests.
2. Run `uv run pytest tests/ -q -m "not network"` and
   `cargo test -p hypervector-tui`.
3. Run Ruff check/format, `git diff --check`, line/function limits, secret
   exclusion, and manifest checksum verification.
4. Commit, push, fast-forward into `main`, remove the merged branch locally and
   remotely, return to clean `main`, and confirm the shadow daemon remains live.

## Success and falsification criteria

- Every normalized trade represents one venue match, not two participant fills.
- Common 0xArchive/local WebSocket trade IDs agree on timestamp, aggressor side,
  price, and size. Persistent mismatch falsifies trade-source qualification.
- Trade-through never fills from a print at or before submission and never uses
  a same-price print as proof of queue completion.
- Bounded acquisition exposes continuation, raw request IDs, and checksums.
- The 90-day archive is complete only when all 4,320 hourly book/trade bundles
  are present and every declared evidence checksum validates.
