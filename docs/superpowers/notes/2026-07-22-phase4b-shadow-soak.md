# Phase 4b shadow soak + expert verification notes

**Date:** 2026-07-22 (session end 2026-07-23 UTC)  
**Branch:** `feat/phase4a-book-fills-metalabel`  
**HEAD at verification start:** `9579981` (Phase 4b Task 6 tip)  
**HEAD after honesty fix:** post-commit banner mode label (see git log)  
**Export:** `data/exports/downtrend_crown_stack_short_c4fd7067`  
**Network:** Hyperliquid **mainnet** public info API reachable  

## Goal of this session

Complete remaining hand items for **4b shadow**: re-prove offline suite, barrier honesty, `paper-check` surface, dual real `paper-run` smokes, bounded mainnet shadow soak against HANDOFF pass criteria 1–6, expert review of success bar, fix any honesty defects with tests, update HANDOFF.

## Evidence (local agent scratch — not committed)

| Artifact | Result |
|----------|--------|
| Offline pytest ×2 (`-m "not network"`) | **227 passed** each at tip `9579981` |
| Offline pytest after banner fix | **228 passed** (+1 banner unit) |
| Barrier suite (`test_paper_no_submit`, order_intent, cli, ledger, fills) | **green** |
| `paper-check` surface | shadow / mainnet / no_submit / submitted_default=false / hv_order_intent_v1 / l2_walk_v1 / live.enabled=false |
| Dual short smokes (`max-live-bars 2`) | both **PASS** — all `execution_mode=shadow`, `submitted=false`, `network=mainnet`, intents `submit_enabled=false`, **0** `live/` files |
| Bounded mainnet soak (`max-live-bars 6`, ~5 min warm + live) | **PASS** — see counters below |

## Bounded mainnet soak counters

| Metric | Value |
|--------|-------|
| warm_bars | 43200 |
| live_bars | 5 |
| decision rows | 1358 |
| market fills | 372 |
| funding rows | 986 |
| execution_mode | **shadow × 1358** |
| submitted | **false × 1358** |
| network | **mainnet × 1358** |
| market fill models | `bar_close_slippage_v1` × 371, **`l2_walk_v1` × 1** |
| market fallbacks | `book_missing` × 371 (warm / no book); l2 fill has `null` fallback |
| order_intent | 372/372 market; schema `hv_order_intent_v1`; **submit_enabled=false** always |
| live/ files | **0** |
| stop_reason | `poll_exhausted` (honest short bound; not a hang) |

### Live L2 fill observed (criterion 4)

```text
feed_ts=2026-07-23T03:11:00+00:00 action=close
fill_model_id=l2_walk_v1 fill_fallback_reason=null
execution_mode=shadow submitted=false network=mainnet
order_intent.schema=hv_order_intent_v1 submit_enabled=false
```

Warm-up market fills correctly stayed on `bar_close_slippage_v1` + `book_missing` (no live BBO on historical bars). Live close after book arm used `l2_walk_v1` when depth was fresh.

## HANDOFF soak pass criteria (4b shadow)

| # | Criterion | Verdict |
|---|-----------|---------|
| 1 | `execution_mode=shadow`, `submitted=false`, `network=mainnet` on market rows | **PASS** |
| 2 | Market fills include `order_intent` with `submit_enabled=false`, schema `hv_order_intent_v1` | **PASS** |
| 3 | Warm-up: `bar_close_slippage_v1` + `book_missing` | **PASS** |
| 4 | Live bars: when book fresh, may be `l2_walk_v1`; never invent depth | **PASS** (1× l2 observed) |
| 5 | Zero files under soak `live/`; ledger under `paper/` | **PASS** |
| 6 | Offline suite green; `tests/test_paper_no_submit.py` green | **PASS** (228 offline) |

## Expert review — locked 4b success bar

| Success bar item | Evidence | Verdict |
|------------------|----------|---------|
| Offline suite green | 227×2 then 228 after fix | **PASS** |
| Order intent schema + always `submit_enabled=false` | builder + engine + soak + barriers | **PASS** |
| Ledger accepts `paper\|shadow`; refuses live | unit tests + zero live writes in soak | **PASS** |
| Engine stamps `submitted=false`, `network=mainnet`, `order_intent` on market fills | fills.py + soak counters | **PASS** |
| Daemon default `shadow`; offline can force `paper` | CLI/runner defaults + tests | **PASS** |
| `paper-check` shadow/mainnet/no_submit; `live.enabled` false | real CLI JSON | **PASS** |
| No testnet in `HL_INFO_URL`; no exchange-submit imports in `paper/` | structural tests | **PASS** |
| No `data/live/` writes; no venue orders | dual smoke + soak | **PASS** |

### Defect found and fixed

**Banner honesty:** daemon always printed `PAPER MODE — no venue orders` even when `execution_mode=shadow` (default). Decision rows and CLI payload were correct; stderr ops banner lied about mode label.  

**Fix:** `banner_for_mode()` → `SHADOW MODE — no venue orders` when shadow; keep paper banner for offline `paper` mode. Tests: `test_daemon_banner_matches_execution_mode`, CLI default-path expects `SHADOW MODE`.  

**Not a capital/safety regression** (submit already impossible); still fixed because 4b success bar and HANDOFF require mode to be obvious.

### Residual risks (honest)

- Short soak does not prove multi-hour liveness or signal density; longer soaks remain optional for ops confidence.  
- Live L2 observation depends on strategy firing post-warm with a fresh book; one close is sufficient proof of the arm path, not a statistical fill study.  
- Shadow PnL ≠ guaranteed live match (design DG residual; model residual vs exchange).  
- **4b-live** (real submit, kill switch, `data/live/`) **not** started — correctly out of scope.

## Commands used

```bash
uv sync --all-extras
uv run pytest tests/ -q -m "not network"   # ×2 then post-fix
uv run python -m hypervector paper-check
uv run python -m hypervector --data-root "$SOAK_ROOT" paper-run \
  --path data/exports/downtrend_crown_stack_short_c4fd7067 \
  --conviction 0.5 --preferred-fill-model l2_walk_v1 \
  --max-book-age-ms 3000 --no-metalabel --poll-interval 5 \
  --max-live-bars 6
```

## Verdict

**Phase 4b shadow verification: PASS.**  
Mainnet-honest shadow path proven offline + dual smoke + bounded live soak (including one real `l2_walk_v1` fill). No venue orders. No `data/live/` writes. Ready for optional longer soak ops confidence; next design when Albert asks is **4b-live**.
