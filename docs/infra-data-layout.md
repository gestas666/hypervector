# hypervector data layout (I2)

**Status:** Implemented local research/runtime separation. **Implemented:**
`hypervector.infra.ensure_data_layout`, DuckDB market store, and CLI lifecycle.

All runtime data lives under a configurable `--data-root` (default `./data`).  
The repo root `/data/` is **gitignored**. Do not commit market data, ledgers, or keys.

## Directory map

```text
data/
  cache/                 # Parquet OHLCV and public market evidence
    events/
      hyperliquid/
        BTC/YYYY-MM-DD/
          l2.parquet/    # Immutable Parquet parts of full L2 snapshots
          trades.parquet/# Immutable Parquet parts of public matches
          asset_context.parquet/ # Mark/oracle/funding observations by receipt time
          gaps.jsonl     # Declared reconnect/freshness uncertainty
    vendor/
      0xarchive/
        hyperliquid/BTC/<utc-window>_d20/
          raw/           # Gzip REST envelopes with request IDs
          books.jsonl.gz # Compressed replay-compatible native L2 snapshots
          manifest.json  # Bounds, coverage, cursors, and SHA-256 checksums
        hyperliquid/BTC/<utc-window>_trades/
          raw/           # Gzip participant fills (maker and taker rows)
          trades.jsonl.gz # One compressed public match per venue trade_id
          manifest.json  # Raw/normalized counts, bounds, cursors, checksums
        hyperliquid/BTC/<utc-window>_candles_1m/
          raw/           # Gzip inclusive vendor candle pages
          candles.parquet # Half-open venue-native research bars
          manifest.json  # Bounds, request IDs, cursors, and checksums
  research/
    market.duckdb        # Market, shadow, labels, and portfolio research revisions
  runs/                  # SQLite research trials (hypervector.db)
  exports/               # Phase 1 → Phase 2 bundles <id>/meta|params|metrics
  models/
    metalabel/           # LightGBM bundle (lgbm + optional calibrator + metadata)
  logs/
    research/            # CLI / sweep logs
    nautilus/            # Phase 2/3 engine logs
  nautilus/
    backtest/            # Phase 2 catalogs / reports
  paper/
    ledger/              # Would-be fills / positions (paper only)
    decisions/           # Decision jsonl/parquet + fill model
    # optional: paper.db
  live/                  # Live only — never share files with paper/
    bidirectional_cohort/
      decisions.jsonl    # Append-only cohort authority and telemetry
      transition_drain.json # Durable active/completed next-start blocker
      operator_commands/ # Identity-bound TUI requests and outcomes
    hulk_smash/
      decisions.jsonl    # Append-only observe/live backend authority and evidence
      STOP               # Ephemeral verified-cleanup request; not a reset control
  runtime/
    hulk_smash/
      backend.log        # Unified launcher child output; contains no secret values
    research/
      hip3_roster_latest.json # Atomic report-only current HIP-3 venue checkpoint
  backups/
    bidirectional_cohort/
      prestart_<UTC>_<fingerprint>/
        manifest.json    # Exact source/archive hashes and old/new strategy identity
        files/*.gz       # Verified restorable config, ledger, and checkpoint snapshots
      transition_drains/
        transition_drain_<UTC>_<request>.json # Recoverable completed drain evidence
```

### Metalabel bundle (optional conviction scale)

- **Default off** — sizing stays fixed until `paper-run --metalabel`.
- **Ready path:** `data/models/metalabel/` with `metalabel_lgbm.txt`, optional
  `metalabel_calibrator.joblib`, and `metalabel_metadata.json` (feature_names).
- **Override:** `HYPERVECTOR_METALABEL_ROOT` (or legacy `HYPERVECTOR_IMPULSE_BTC_ROOT`).
- **Probe:** `status` / `paper-check` report `metalabel.ready` / `metalabel_ready`
  without enabling the flag.
- Weights are gitignored under `/data/` — install locally, do not commit.

## Rules

1. **Paper ≠ live storage** — separate roots; tag every row with `execution_mode`.
2. **Cache-first** research history; live paper decisions use **HL feed** after warm-up.
3. **Configs** stay tracked under `configs/` (costs, risk, exits, fee_model).
4. **Secrets** only via environment / `.env` (gitignored); not in exports.
5. **DuckDB owns historical analytics/replay.** Redis remains deferred until
   measured live multi-process coordination or fan-out requires an event bus.
   LanceDB remains deferred until an annotation-similarity retrieval experiment
   has enough resolved labels; neither belongs on the execution authority path.
6. **Vendor history is separate from live events** — no fabricated local receive
   timestamp is added to historical 0xArchive snapshots.
7. **Source evidence remains intact.** DuckDB source tables retain manifest row
   counts. Canonical replay retains every unique L2 timestamp, deduplicates
   repeated venue trade IDs, and applies half-open bounds only to the requested
   replay window. Vendor request provenance remains available in source tables.
8. **Shadow imports remain analytical.** The paper JSONL ledger stays the runtime
   source of truth. DuckDB imports are idempotent copies stamped `report_only`
   with `execution_authority=none`; they cannot submit, filter, size, or cancel.
9. **DuckDB is a single-writer service boundary.** Run database imports
   sequentially. Concurrent read-only reports are acceptable when no writer is
   active; concurrent revision imports fail with an explicit DuckDB lock error.
10. **Live event parts are bounded buffers.** The runtime flushes after 2,000
    combined events and always flushes remaining L2/trade/context rows during a
    graceful stop. A hard process crash can lose the unflushed batch; detecting
    and declaring that cross-process discontinuity remains an open requirement.
11. **Hulk history is durable.** Normal TUI/backend exit appends shutdown and
    reconciliation evidence; it does not clear `live/hulk_smash/decisions.jsonl`.
    Post-run audits snapshot and hash a stable prefix and never overwrite an
    existing artifact.
12. **Cohort operator requests preserve backend authority.** The Rust TUI may
    atomically publish narrow, expiring, run/profile-bound requests below the
    cohort `operator_commands/` inbox. It stores no secret and has no exchange
    client. Only an explicitly armed Python backend may validate and execute an
    entry or reduce-only close. Configuration requests validate into a separate
    restart-only profile while disarmed and never mutate the active process.
13. **Cohort live starts are backup-gated.** After acquiring the singleton live
    lock and before constructing authenticated venue adapters, the backend
    publishes and restore-verifies an immutable pre-start bundle. Partial
    ledger sets, missing prior strategy sources during a profile change, gzip
    corruption, or checksum mismatch abort startup. The bundle never selects
    `.env` or credential files.
14. **Cohort profile transitions are drain-gated.** A backend-accepted,
    run/profile-bound drain withholds only new entries and retains exit and
    protection authority. Completion requires flat lifecycle state, zero signed
    position size, and no owned order identities across all configured assets.
    Active or completed drain evidence blocks every later start until the
    stopped-run marker is explicitly and recoverably archived under the live
    runtime lock. If an active drain's backend is interrupted, only an explicit
    same-profile recovery start may rebind it to a new process run; that start
    backup-verifies the old run-bound drain bytes before authenticated adapter
    construction and preserves origin/resume provenance in telemetry.
15. **Process-run performance is report-only.** Closed cohort lifecycles retain
    their backend process run and profile identities. The checkpoint may group
    those trades by run for restart-window comparisons, but explicitly declares
    that statistical independence is not established. These groups cannot
    pause, size, route, retune, promote, or reject a strategy.

## CLI

```bash
uv run python -m hypervector infra-init --data-root data

uv run python -m hypervector --data-root data research-db-build \
  --symbol BTC \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-28T00:00:00Z

uv run python -m hypervector --data-root data research-db-build \
  --database data/research/hip3_market.duckdb \
  --market-family hip3 --books-only \
  --symbol 'xyz:SPCX' \
  --start 2026-05-17T22:00:00Z \
  --end 2026-08-06T15:00:00Z

uv run python -m hypervector --data-root data research-db-status

uv run python -m hypervector --data-root data research-db-journal-append \
  --record docs/research-journal/<hypothesis>-v1.json

uv run python -m hypervector --data-root data research-db-journal-report \
  --hypothesis-id <stable-hypothesis-id>

uv run python -m hypervector --data-root data \
  research-db-live-event-import --symbol BTC

uv run python -m hypervector --data-root data research-db-shadow-import

uv run python -m hypervector --data-root data research-db-shadow-trades

uv run python -m hypervector --data-root data research-db-regime-label-import \
  --labels data/logs/research/<labels>.parquet \
  --metadata data/logs/research/<labels>.json

uv run python -m hypervector --data-root data research-db-regime-compare
```

`research-db-build` verifies every manifest and declared SHA-256 before loading,
commits at most 24 hourly pairs per transaction, and skips an already imported
bundle only when its manifest fingerprint is unchanged. It stores full 20-level
books, public trades, BBO, top-five/top-ten imbalance, spread, midpoint, and
best-level microprice. A checksum, identity, or row-count mismatch fails the
affected transaction explicitly.

HIP-3 imports require explicit `--market-family hip3 --books-only`, retain the
namespaced venue symbol and HIP-3 book source, record market-family provenance,
and materialize zero public trades. Use the separate HIP-3 database while the
live checkpoint periodically writes `market.duckdb`; DuckDB writers must remain
sequential.

`portfolio_research_revisions` is an append-only, report-only decision ledger.
Tracked JSON records under `docs/research-journal/` preserve the human-reviewable
hypothesis, decision, confidence, falsifier, metrics, limitations, and exact
evidence hashes. The database stores immutable revision identities and requires
an exact supersession chain. It cannot grant execution authority, promote a
strategy, or claim a runtime change. Append and report commands must run
sequentially because DuckDB permits one local process to hold the database lock.

`research-db-live-event-import` hashes and tracks every immutable WebSocket
Parquet part and gap log. Source tables retain every observed row, while
`replay_live_public_trades` removes only identical cross-process trade-ID
repeats. A conflicting live trade ID or conflicting vendor/live overlap aborts
the transaction. `canonical_public_trades` prefers the manifest-verified
archive on exact overlap and adds live-only trades after the archive cutoff;
`canonical_trade_5m_bars` is the shared deterministic OHLCV projection.

`research-db-shadow-import` copies every paper/shadow event by canonical event
hash, rejects a `live` execution mode atomically, and exposes only complete
five-minute OHLCV groups in `shadow_completed_5m_bars`. The strict and legacy
Hypertrader label importer verifies each label file against its generation
metadata, accepts only the two pinned source revisions, requires the explicit
observe-only contract, and rejects a conflicting label for the same revision
and timestamp. `shadow_hypertrader_regime_comparison` joins labels only when
their five-minute decision delay has elapsed.

`shadow_completed_trade_attribution` reconstructs one row per terminal shadow
position from the entry and exit fills that actually occurred. The originating
intent is linked by client order ID so expired maker attempts are not mistaken
for the decision that filled. The view reports weighted prices, quantities,
fees, signed funding payments, gross/net PnL, and the latest backend, strict,
and legacy regime observations causally available at that intent. The
`research-db-shadow-trades` command summarizes those rows read-only; it has
`execution_authority=none` and does not change strategy or model policy.
