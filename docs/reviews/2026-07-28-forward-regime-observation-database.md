# Forward regime observation database — 2026-07-28

## Problem and acceptance boundary

The runtime paper ledger was durable JSONL, while the exact Hypertrader
strict/legacy labels and the 90-day Hyperliquid tape were separate artifacts.
That made causal, same-bar comparison possible only through ad hoc scripts.

The accepted slice is deliberately annotation-only:

- preserve the paper ledger as execution truth;
- import events idempotently into DuckDB;
- materialize a 5m bar only from five distinct completed 1m observations;
- bind each upstream label to its exact source revision and file metadata;
- join a label only at or after its recorded `available_at` time;
- expose disagreements without changing entry, sizing, model, or order logic.

## Implemented relations

- `shadow_ledger_events`: canonical-hash-deduplicated paper/shadow events with
  the raw JSON payload retained.
- `shadow_regime_observations`: typed causal 1m regime and OHLCV observations.
- `shadow_completed_5m_bars`: exact five-minute groups only; partial buckets and
  older observations lacking complete OHLCV remain excluded.
- `hypertrader_regime_annotations`: immutable strict/legacy labels with label
  and metadata SHA-256, five-minute availability, and no execution authority.
- `shadow_hypertrader_regime_comparison`: same-symbol, same-bar, causally
  available backend/strict/legacy comparison.
- `live_event_files`: immutable part hashes, row counts, dates, and dataset
  identities for L2, trades, asset context, and declared gaps.
- `canonical_public_trades` and `canonical_trade_5m_bars`: vendor/live union
  with conflict rejection and deterministic trade-ID deduplication.

## Measured local result

The current ledger import contained 2,898 events, 125 regime observations, and
seven complete five-minute bars. Both 26,208-row exact source label sets were
imported:

- strict revision `ad15f2bdc949619be495a5f516babd08f7f52a90`;
- legacy revision `96014462c8f3911abff1babc925448893d65676d`.

For the seven comparable bars from `2026-07-27T09:10:00Z` through
`2026-07-27T09:40:00Z`:

- shadow OHLCV matched the canonical Hyperliquid public-trade aggregation 7/7;
- strict and legacy disagreed on 0/7 labels;
- both source revisions labeled all seven `TRANSITION`;
- the executing backend labeled all seven `TREND_DOWN`, so backend/source
  disagreement was 7/7.

The imported live WebSocket archive contains 187 files: 5,350 L2 rows, 75,137
trade rows, 28,196 asset-context rows, and one declared reconnect gap. Six
cross-process trade repeats collapse to 75,131 canonical live identities.
The original 74,474 rows overlap the vendor table and match exchange time,
side, price, and size; the forward run adds 657 post-cutoff trades with zero
identity conflicts. Its graceful flush also persisted 51 L2 and 264 context
rows. The historical 2,077 ms reconnect gap remains explicit.

The same evidence measured a 5,385 ms median and 5,578 ms p99 L2 interval.
Only 55.15% of public trades had both a preceding book and receipt lag inside
the former 3,000 ms execution-age boundary; 99.69% qualified at 6,000 ms.
The faithful profile now uses 6,000 ms. A bounded migration permits only a
flat, unfilled pending maker with `requeue_behind_displayed_liquidity` to cross
that exact 3s-to-6s change. An already-filled position still fails closed.

## Confidence, risks, and falsification

Confidence in data alignment is high for these seven bars because all five
OHLCV fields match the independently materialized trade tape exactly.
Confidence in detector quality remains low because seven bars and zero closed
shadow trades cannot estimate edge.

Potential failure modes include missing `open` in older telemetry, incomplete
minute groups, gaps between the historical archive and a future shadow window,
DuckDB's single-writer lock, or a mutated event part. None are silently filled.
A nonzero OHLCV
mismatch, a label available before its five-minute close, or an import that
changes the paper ledger would falsify the accepted data boundary.

The next evidence threshold is a continuous venue-matched forward window with
resolved entries/exits across backend/source agreement and disagreement cells.
Until then, strict and legacy remain annotations and the runtime strategy is
unchanged.

## Later append-only checkpoint

Without stopping the running shadow process, a later idempotent import retained
4,843 ledger events, 267 regime observations, and 34 complete five-minute bars.
Fourteen bars remain comparable to the downloaded source labels and tape;
13/14 match exact OHLCV, with the known 0.00096 BTC volume mismatch on the
remaining bar. Twenty completed bars are explicitly unlabeled because they are
newer than the 22:00 UTC archive boundary. The import reports no execution
authority and did not alter the runtime ledger.
