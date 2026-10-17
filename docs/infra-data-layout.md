# hypervector data layout

All runtime data lives under the data root, set with `--data-root`. The default
is `./data`, which is gitignored. Never commit market data, ledgers, models or
keys.

- **Creating the layout.** `hypervector system init` creates the base layout.
  Commands create the other directories just before their first write.
- **Read-only commands** (`system status`, `export list`, `pipeline list`,
  `archive audit`, `backtest report`) create nothing.
- **Fixed paths.** The live commands whose paths come from the cohort profile or
  launchd (`live start`, `live check`, `live request`, `live validate`,
  `live backup*`, `live rollback-profile`, `live audit-delta`, `live supervisor`)
  refuse a non-default data root.

## Directory map

```text
data/
  cache/                                   # research history and public market evidence
    <SYM>_<tf>_<N>d.parquet                # "the last N days" bars; <key>_hlonly for --strict-hl-only
    book/<SYM>_l2_<YYYYMMDD>.jsonl         # data book-record snapshots
    events/hyperliquid/<SYM>/YYYY-MM-DD/
      l2.parquet/  trades.parquet/  asset_context.parquet/   # immutable Parquet parts
      gaps.jsonl                           # declared reconnect/freshness gaps
    vendor/0xarchive/hyperliquid/
      <SYM>/<window>_d20/                  # archive book-fetch / backfill: raw/, books.jsonl.gz, manifest.json
      <SYM>/<window>_trades/               # archive trade-fetch: raw/, trades.jsonl.gz, manifest.json
      <SYM>/<window>_candles_<tf>/         # archive candle-fetch: raw/, candles.parquet, manifest.json
      hip3/<deployer:asset>/...            # HIP-3 bundles (--market-family hip3)
      <bundle>_partial/                    # --allow-partial; never read by backfill, audit or db build
  research/
    market.duckdb                          # db default (--database); single writer
    hip3_asset_context/                    # data hip3-roster rolling asset-context archive
  runs/
    hypervector.db                         # RunsDB: backtest sweep trials
    pipeline/<pipeline-id>/
      pipeline.json                        # pipeline run manifest, rewritten atomically per stage
      model/                               # pipeline --train-model output (never installed)
  exports/
    <candidate-id>/meta.json params.json metrics.json   # strict strategy bundles
    regime_snapshots.json                  # regime export default
  models/
    metalabel/                             # installed metalabel bundle (model train --install)
      wf_<strategy>_<time>/                # model train output
  logs/
    research/                              # tune boards (autotune_*.json, regime_autotune_*.json)
    nautilus/                              # engine logs
  nautilus/
    backtest/                              # Nautilus reports
    catalog/<symbol>/                      # nautilus catalog default
  paper/
    decisions/decisions.jsonl              # paper run / shadow decisions (paper report, db import-paper)
    ledger/                                # synthetic fills and positions
    cohort/                                # paper observe ledgers (zero execution authority)
      decisions.jsonl                      # paper checkpoint / paper audit default
  live/                                    # live only; never shares files with paper/
    decisions/decisions.jsonl              # live run (generic daemon) decisions; live report
    bidirectional_cohort/                  # the cohort backend (paths fixed by the profile)
      decisions.jsonl                      # append-only cohort authority and telemetry
      <symbol>.jsonl                       # per-symbol journals
      operator_commands/                   # identity-bound operator requests and outcomes
      startup_inputs/<run-id-sha256>/      # startup candle frames + manifest
      transition_drain.json                # active/completed drain: blocks the next start
      process.lock  observer.lock
      STOP                                 # durable operator stop
  runtime/
    bidirectional_cohort/
      latest_checkpoint.json               # live checkpoint (live monitor, live preflight default)
      latest_opportunity_matrix.json
      supervisor_events.jsonl              # supervisor journal
      supervisor_events_restart_state.json # restart journal (hold state)
      supervisor_alerts.jsonl
      supervised_backend.log
    cohort_observer/
      latest_checkpoint.json               # paper checkpoint output (never the live checkpoint)
    research/
      hip3_roster_latest.json              # data hip3-roster checkpoint
  backups/
    bidirectional_cohort/
      prestart_<UTC>_<fingerprint>/        # pre-start and pre-change bundles: manifest.json, files/*.gz
      transition_drains/                   # archived completed drain markers
      reboot_hold_<UTC>/                   # restart journals archived by live supervisor resume
```

## Rules

1. **Paper and live storage never mix.** They use separate roots, and every row
   carries its `execution_mode`.
2. **Research history is cache-first, and every load reports what it served:**
   `start`, `end`, `coverage_ratio`, `age_seconds`, `stale`, `partial`,
   `fetched_at`, cache key and path, and backfill sources.
   - **Refresh.** A window is refreshed when network is allowed and its last bar
     is older than `--max-cache-age-hours` (default 24), or it holds under 95%
     of the lookback. Offline, it is served with a warning instead.
   - **Pinning.** `--pin-cache` serves the cached window as it is.
   - **Strict HL-only.** These loads use `<key>_hlonly` and never overwrite the
     default (backfilled) entry.
   - **Preserved files.** A refresh renames a file the loader did not write to
     `<key>__preserved_<start>_<end>.parquet` instead of deleting it.
   - **Book features.** Aligned book features are NaN where no snapshot matched
     (`book_available`, `book_age_ms`).
3. **Configs** stay tracked under `configs/`: costs, risk, exits, cohort
   profiles.
4. **Secrets** come only from the environment or `.env` (gitignored), never from
   exports or ledgers. The full `.env` loads only for an armed `live start` or
   `live run`.
5. **DuckDB holds historical analytics and replay.** It is not on the execution
   path.
6. **Vendor history stays separate from live events.** No fabricated local
   receive timestamp is added to 0xArchive snapshots.
7. **Source evidence stays intact.**
   - DuckDB source tables keep manifest row counts.
   - Canonical replay keeps every unique L2 timestamp and de-duplicates repeated
     venue trade IDs.
   - Half-open bounds apply only to the requested replay window.
8. **Paper imports are analytical.** The paper JSONL ledger is the runtime
   source of truth. `db import-paper` copies are idempotent, stamped
   `report_only` with `execution_authority=none`, and cannot submit, filter,
   size or cancel anything.
9. **DuckDB takes one writer at a time.**
   - Run imports and builds sequentially.
   - Concurrent read-only reports are fine while no writer is active.
   - A concurrent writer fails with an explicit lock error.
   - Use a separate database file (for example `research/hip3_market.duckdb`)
     while the live checkpoint syncs `market.duckdb`.
10. **Live event parts are bounded buffers.** The runtime flushes after 2,000
    combined events and flushes everything left on a graceful stop. A hard crash
    can lose the unflushed batch.
11. **Operator requests keep backend authority.** `live request` publishes
    narrow, expiring, run- and profile-bound requests into `operator_commands/`.
    It stores no secret and has no exchange client. Only an armed backend
    validates and executes an entry or a reduce-only close. A `stage_profile`
    request validates into a separate restart-only profile and never changes the
    running process.
12. **Cohort starts are backup-gated.** After the backend takes the singleton
    live lock, and before it builds an authenticated venue client, it publishes
    and restore-verifies an immutable pre-start bundle. Any of these aborts the
    start:
    - partial ledger sets;
    - prior strategy sources missing during a profile change;
    - gzip corruption;
    - a checksum mismatch.
    The bundle never includes `.env` or credential files.
13. **Profile transitions are drain-gated.**
    - **What a drain does.** An accepted drain withholds only new entries. It
      keeps exit and protection authority.
    - **Completion** needs flat lifecycle state, zero signed size and no owned
      order on every configured asset.
    - **Blocking.** A completed or active marker blocks every later start until
      `live drain-archive --yes` archives it under the runtime lock.
    - **Interruption.** An interrupted active drain can resume only through a
      same-profile `live start --resume-transition-drain`.
14. **Process-run performance is report-only.** The checkpoint may group closed
    lifecycles by run. These groups never pause, size, route, retune, promote or
    reject a strategy.

## Startup candle evidence

The cohort backend captures its startup candle inputs once, before resampling
and provider evaluation. The `startup_candle_inputs` ledger event records
either `captured`, with the manifest SHA-256, or `unavailable`, with the
failure.

- **Coverage.** The manifest separates requested lookback from actual coverage.
  A forming candle can be present, so replay applies the provider's completion
  cutoff.
- **Replay.** Authenticate it with
  `hypervector.live.cohort_startup_candles.load_startup_candles(manifest_path, manifest_sha256, context)`.
- **Retention.** Bundles are immutable and accumulate one per run.

## Metalabel bundle

- **Off by default.** Sizing stays fixed unless `paper run --metalabel-mode
  observe|scale|filter` is set.
- **Layout.** A bundle holds `metalabel_lgbm.txt`, an optional
  `metalabel_calibrator.joblib` and `metalabel_metadata.json`.
- **Selection.** `--metalabel-bundle REF` selects a directory, a name under
  `models/metalabel/`, or `latest`, for that process only.
- **Override.** `HYPERVECTOR_METALABEL_ROOT` (or `HYPERVECTOR_IMPULSE_BTC_ROOT`)
  points elsewhere.
- **Probe.** `system status --probe-model` and `paper check` report readiness.

## Commands

```bash
hypervector --data-root data system init
hypervector --data-root data system status

hypervector archive backfill --symbol BTC --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z
hypervector archive audit    --symbol BTC --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z
hypervector db build         --symbol BTC --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z
hypervector db build --database data/research/hip3_market.duckdb --market-family hip3 --books-only \
  --symbol 'xyz:SPCX' --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z
hypervector db status
hypervector db import-events --symbol BTC
hypervector db import-paper
hypervector db import-cohort --ledger-root data/live/bidirectional_cohort
hypervector db paper-trades
```

- **`db build`** needs every bundle in the window. It identity-checks every
  manifest, and verifies the declared SHA-256 of every bundle it will import,
  before it writes anything. A missing or invalid bundle fails the build (run
  `archive audit` first to list the gaps). It commits at most 24 hourly pairs
  per transaction.
- **Skipped bundles.** An imported bundle is skipped only when its manifest
  fingerprint is unchanged. `--verify-all` re-checksums ingested bundles, and
  `--replace-changed` replaces bundles that were repaired at source.
- **What it stores:**
  - full 20-level books and public trades;
  - BBO, top-five and top-ten imbalance;
  - spread, midpoint and best-level microprice.
- **Mismatches.** A checksum, identity or row-count mismatch fails the affected
  transaction.
- **HIP-3 imports** need `--market-family hip3 --books-only`. They keep the
  namespaced venue symbol and materialize zero public trades.
- **`db import-events`** hashes and tracks every immutable WebSocket Parquet
  part and gap log.
  - `canonical_public_trades` prefers manifest-verified archive trades on an
    exact overlap, and adds live-only trades after the archive cutoff.
  - `canonical_trade_5m_bars` is the shared OHLCV projection.
- **`db import-paper`** copies every paper/shadow event by canonical event hash.
  It rejects a `live` execution mode atomically, and exposes only complete
  five-minute groups in `shadow_completed_5m_bars`.
- **`db paper-trades`** summarizes `shadow_completed_trade_attribution`. That is
  one row per terminal shadow position, built from the fills that occurred, with
  the regime context causally available at the originating intent. It has
  execution_authority=none.
