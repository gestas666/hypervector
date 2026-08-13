# Hypervelocity Authentic Mark and Funding Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the research replay's L2-midpoint liquidation proxy and missing historical funding with point-in-time Hyperliquid mark/oracle prices and settled hourly funding, then remeasure the unchanged strategy.

**Architecture:** Acquire immutable 0xArchive Hyperliquid price history with raw response envelopes, cursors, checksums, and normalized decimal-safe records. Acquire official public Hyperliquid `fundingHistory` rows over the same window. Feed both streams into the existing chronological maker tape: authentic mark drives liquidation/drawdown, BBO still determines executable fills, and funding is booked only at exact hourly settlement events while a position is open. Preserve the old proxy path as the default until the new replay is complete and verified.

**Tech Stack:** Python 3.13, pandas, Decimal, requests, pytest, 0xArchive Hyperliquid Core API, public Hyperliquid Info API.

---

## Authoritative evidence and constraints

- Official 0xArchive schema: `GET /v1/hyperliquid/prices/{symbol}` returns UTC
  snapshots containing nullable `mark_price`, `mid_price`, and `oracle_price`,
  with string cursors and a maximum page size of 1,000.
- A bounded live qualification returned 59 BTC rows for one hour, with mark,
  oracle, and mid prices at approximately one-minute cadence. A two-day query
  returned 1,000 rows and a continuation cursor as documented.
- Official Hyperliquid public `fundingHistory` is already the backend's
  downtime-reconciliation authority. The long replay must paginate rather than
  assume one response contains all 90 days.
- Liquidation execution remains adverse BBO. Authentic mark determines only
  whether the isolated maintenance boundary is crossed.
- Funding uses oracle-price notional and the venue's signed hourly rate: a
  positive rate is paid by longs and received by shorts. It affects isolated
  collateral, equity, liquidation state, and final PnL exactly once per
  settlement timestamp.
- Missing/stale mark, oracle, or funding evidence must be counted and exposed;
  no neutral zero or silently fabricated midpoint may be labeled authentic.
- Keep all strategy rules fixed: hard BBWP25/recovery-6 research control,
  300-second BBO maker entry, regime-reset re-entry, one position, 70% isolated
  margin, 40x, 8% target, RANGE hold, and existing fee schedule.
- Runtime, TUI, faithful config, and ML observe policy remain unchanged.

## Frozen comparison

- Control artifact: `hypervelocity_bbwp_recovery6_equity120_20260727.json`:
  447 fills, 406 targets, 41 liquidations, $115.40 final equity, and -97.52%
  maximum drawdown.
- The authentic-context replay is diagnostic. It is profitable only if final
  equity exceeds $120 after fees and funding.
- Report which control liquidations disappear, move, or are newly introduced;
  funding paid/received by side; mark freshness/coverage; final equity; and
  drawdown. A changed result updates replay fidelity, not strategy parameters.
- A profitable full-window result still requires the exact source-window replay
  and later fresh shadow evidence before any runtime promotion.

### Task 1: Immutable 0xArchive price-history acquisition

**Files:**
- Create: `src/hypervector/data/oxa_prices.py`
- Modify: `src/hypervector/cli_oxa.py`
- Modify: `src/hypervector/cli.py`
- Test: `tests/test_oxa_prices.py`
- Test: `tests/test_oxa_price_cli.py`

1. Write failing tests for request bounds, cursor propagation, nullable decimal
   fields, duplicate conflict rejection, raw-envelope retention, checksums, and
   exhausted-page failure.
2. Implement typed requests/pages/records and immutable normalized storage.
3. Add `oxa-price-fetch` with explicit UTC bounds, page limit, max pages, and
   secret-safe errors.
4. Run focused tests and Ruff.

### Task 2: Complete official funding-history acquisition

**Files:**
- Create: `src/hypervector/data/hl_funding_archive.py`
- Test: `tests/test_hl_funding_archive.py`

1. Write failing tests for forward pagination, exact UTC-hour deduplication,
   non-progress rejection, source identity, and immutable storage.
2. Implement bounded public Info API pagination without credentials.
3. Retain raw response pages and normalized `timestamp`, `funding_rate`, and
   source rows with checksums.
4. Run focused tests and Ruff.

### Task 3: Acquire and audit the complete 90-day context

**Files:**
- Create: immutable price/funding bundles under `data/cache/vendor/`
- Create: `data/logs/research/hypervelocity_mark_funding_coverage_20260727.json`

1. Fetch April 28–July 27 BTC price history and public hourly funding.
2. Verify every stored file checksum, requested bounds, cursor completion,
   monotonic timestamps, duplicates, coverage, and maximum gaps.
3. Stop integration if the context is incomplete or timestamps cannot be
   causally aligned; report the exact missing interval.

### Task 4: Add authentic context to research replay

**Files:**
- Create: `src/hypervector/research/maker_replay_context.py`
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `src/hypervector/research/maker_replay_risk.py`
- Modify: `src/hypervector/research/maker_replay_stream.py`
- Test: `tests/test_hypervelocity_maker_replay.py`

1. Write failing tests for backward-only mark selection, stale/missing mark,
   BBO execution after mark liquidation, long-pay/short-receive funding,
   no-position boundaries, partial liquidation, and chunk boundaries.
2. Add typed context state and explicit coverage/funding report fields.
3. Interleave context updates causally without shifting future snapshots.
4. Keep the no-context replay behavior unchanged.
5. Run full replay tests and Ruff.

### Task 5: Exact unchanged-strategy comparison

**Files:**
- Create: `data/logs/research/hypervelocity_equity120_authentic_context_20260727.json`
- Modify: this plan
- Modify if material: `HANDOFF.md`

1. Replay the unchanged hard/recovery control across all verified L2/trade
   bundles with authentic context.
2. Compare lifecycle identities, liquidation timestamps, funding, equity, and
   drawdown against the proxy control.
3. If profitable and coverage-complete, run the exact source window.
4. Record confidence, failure modes, and a falsifier; do not mutate runtime.

### Task 6: Verification

1. Run all focused acquisition/replay tests, changed-file Ruff, full
   non-network Python tests, Rust tests, and `git diff --check`.
2. Verify the faithful TOML checksum and observe-only fields remain unchanged.
3. Do not commit or push unless explicitly requested.

## Measured result

The checksum-verified authentic-context replay reproduced exactly across two
independent executions. The frozen strategy and configuration were unchanged.

| Context | Submissions | Fills | Targets | Liquidations | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| L2 midpoint proxy, no funding | 517 | 447 | 406 | 41 | $115.40 | -97.52% |
| Hyperliquid mark + official funding | 513 | 445 | 402 | 43 | $20.26 | -99.43% |

The authentic replay consumed 127,814 mark/oracle observations and applied 982
funding settlements while positions were open. Funding paid was $4.94, funding
received was $5.23, and net funding was +$0.29; funding therefore did not cause
the loss. Authentic mark timing produced a net two additional liquidation
outcomes. Because each full liquidation is path-dominant at 40x, those two
events explain the large compounded equity difference and also shift later
re-entry availability.

Price evidence had no nulls or duplicate timestamps, but 21 gaps exceeded 120
seconds and the maximum gap was 353.004 seconds. The replay reported 425 stale
mark evaluations while positions were open and did not replace them with
midpoint. All 2,160 expected hourly funding rows were present; no applied
funding settlement had a missing or stale oracle.

The source-window replay was not run because the frozen plan required the full
window to be profitable first. Runtime, TUI, faithful configuration, 8% target,
and metalabel observe policy remain unchanged.

Confidence is medium. Independent reproduction and checksums support the result,
while unobserved private queue position, liquidation depth, and the 21 mark gaps
remain material failure modes. A denser checksum-verified mark stream plus
depth-aware liquidation execution that removes the two net added liquidation
outcomes would falsify or materially update this assessment.

Artifacts:

- `data/logs/research/hypervelocity_equity120_authentic_context_20260727.json`
- `data/logs/research/hypervelocity_mark_funding_coverage_20260727.json`
