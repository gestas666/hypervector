---
name: hypervector-cli
description: >
  Operate the Hypervector perpetuals quant engine CLI, VectorBT vectorized backtester,
  Nautilus event-driven engine, Karpathy/Optuna autotuner, and backend-authored TUI cockpits.
  Use when running hypervector commands, backtesting, autotuning, regime evaluation,
  paper/shadow/live checks, metalabel training, or launching the Ratatui TUI cockpit.
---

# Hypervector Perpetuals Quant Engine & Regime Detector CLI

Comprehensive operator skill for **Hypervector** — VectorBT vectorized backtesting, Nautilus event-driven backtesting, Karpathy/Optuna autotuning, LightGBM metalabeling, and backend-authored Ratatui telemetry.

## Hard Safety Rules & Project Charter

1. **Ungated Execution (`SRS_HV1_NO_GATES`)**: Only **technical failure** aborts a trial. No implicit strategy, drawdown, or risk rejection gates unless explicitly configured by the user. Performance, drawdown, trade count, regime confidence, and model scores remain reported trial results rather than implicit abort conditions.
2. **Fail-Closed Safety (`SRS_HV1_HONESTY`)**: Paper/shadow mode **never** constructs live execution clients or places live orders. Default mode is `shadow`. `live-run` is strictly fail-closed and arms **only** on explicit `--enabled --i-accept-live-risk` flags and secret environment variables.
3. **Secret Protection**: Never print secret values (`HYPERVECTOR_HL_WALLET_ADDRESS`, `HYPERVECTOR_HL_API_PRIVATE_KEY`). Only print presence booleans.
4. **Venue Specification (`SRS_HV1_VENUE_SPEC`)**: Strict adherence to Hyperliquid per-asset leverage specifications (BTC 40x max, ETH 25x max, SOL 20x max, Altcoins 10x-15x max).
5. **Mainnet Only**: Mainnet venue parameters only — no testnet path.
6. **TUI Integrity**: TUI is a read-only live telemetry display and paper trading cockpit; CLI owns process lifecycle and execution.

---

## Invocation

Run commands from repo root using `uv`:

```bash
uv run python -m hypervector <command> [options]
```

Or launch the Rust terminal cockpit:

```bash
cargo run -p hypervector-tui --bin tui-regime-detector -- [options]
```

---

## Command Cookbook

### 1. VectorBT Strategy Backtest (Phase 1.5 Vectorized Engine)

Runs high-speed vectorized simulation across 180+ days of 1m/5m data in seconds with venue-restricted leverage scaling, fee presets, and orderbook entry gating:

```bash
# Backtest Crown Stack Long on 5m BTC with 2.0x leverage & Maker fees
uv run python -m hypervector backtest \
  --strategy crown_stack_long \
  --symbol BTC --timeframe 5m \
  --lookback 180 --leverage 2.0 --fee-model hl_maker

# Backtest Open Interest Divergence with Orderbook Gating on 1m BTC
uv run python -m hypervector backtest \
  --strategy oi_divergence_long \
  --symbol BTC --timeframe 1m \
  --lookback 90 --book-gate --max-spread-bps 3.0 \
  --book-path data/cache/book/BTC_l2_20260723.jsonl
```

### 2. Event-Driven Nautilus Backtest (Phase 2 Engine)

Executes event-driven backtesting on strict strategy export bundles:

```bash
uv run python -m hypervector phase2-run \
  --path data/exports/<export_dir> \
  --lookback 180 --conviction 0.5
```

### 3. Ultimate Regime Accuracy Evaluator

Measures directional forward return precision, Sharpe ratio, and persistence across market states:

```bash
# Evaluate 5m BTC dataset (180 days lookback)
uv run python -m hypervector regime-eval --symbol BTC --timeframe 5m --lookback 180

# Evaluate 1m BTC with L2 Orderbook alignment
uv run python -m hypervector regime-eval --symbol BTC --timeframe 1m --book-path data/cache/book/BTC_l2_20260723.jsonl
```

### 4. Karpathy & Optuna Dual Autotuner

Runs continuous stochastic sampling (Karpathy) or Tree-structured Parzen Estimator (Optuna) parameter autotuning:

```bash
# Hybrid Karpathy mutation + Optuna TPE sampler
uv run python -m hypervector autotune --strategy crown_stack_long --sampler hybrid --n-trials 100

# Karpathy random-adaptive mutation sampler on Apex Open Interest Divergence
uv run python -m hypervector autotune --strategy oi_divergence_long --sampler karpathy --n-trials 100
```

### 5. Hypervelocity Shadow Backend and Read-Only TUI

Use one command to supervise the backend and display its telemetry in the TUI:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-tui \
  --config configs/hypervelocity_faithful.toml
```

The Python CLI starts the no-submit backend, waits for its fresh session row,
and opens the TUI in the foreground. Pressing `q` stops the TUI and its child
backend cleanly. Backend output is retained at
`<data-root>/paper/hypervelocity-shadow.log`. A per-data-root process lock
refuses a second Hypervelocity backend.

Normal quit and restart preserves the latest durable Hypervelocity shadow run:
cash, realized PnL, any open position, pending maker entry, cooldown timestamp,
and closed-trade journal are restored from the backend ledger. The backend
validates the execution-spec fingerprint and portfolio equity identity before
restoring active state. Empty accidental launches do not replace that portfolio
identity. Reset is explicit and recoverable only through the command below.

After a target closes, the completed direction is consumed for the current
regime episode. A persistent `TREND_UP` cannot immediately create another long,
and a persistent `TREND_DOWN` cannot immediately create another short. A
non-matching canonical regime must be observed before a later fresh same-side
signal can re-arm. This state is durable across normal restarts and is additive
to the one-completed-bar minimum cooldown. An eligible opposite side after exit
remains available after that minimum cooldown.

When an open target or pending maker entry spans downtime, startup reconciles
only completed, venue-matched Hyperliquid candles after the ledger timestamp.
It may fund, fill, cancel, or close that already-active state, but it cannot
create a new historical entry. Hourly boundaries require the matching public
Hyperliquid funding-history row; missing evidence fails startup explicitly.

The TUI does not execute trades. Trade, position, PnL, cost, policy, regime,
isolated liquidation price, and up-to-20-level depth fields are projections of
backend ledger telemetry. The TUI displays `LIQ PRICE UNAVAILABLE` when an
older ledger lacks that field; it never derives a substitute from leverage or
entry price. The backend remains the execution and persistence authority.

Reset a completed shadow observation window with a recoverable backup:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-shadow-reset --yes
```

Without `--yes`, the reset is a non-mutating dry run. Confirmed resets acquire
the singleton backend lock, copy decisions and the backend log under
`<data-root>/backups/shadow_reset_<UTC>/`, then clear only those two files.
Screen 4 displays the backend-reported active data root and the complete,
shell-quoted reset command for that same root.

### 6. 4-Screen Visual Microstructure Cockpit (`tui-regime-detector`)

Ratatui 0.29 interactive 4-screen cockpit featuring backend telemetry, a live L2 depth stack, a read-only market chart, paper trade journal, and a navigable read-only configuration menu:

```bash
# Interactive playback cockpit (1m execution, 5m primary, 15m context)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m

# Real-time live mode (250ms refresh rate)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m --live --refresh-ms 250
```

#### Cockpit Screen Navigation:
- **`[1]`**: **Dashboard** (backend strategy, position, live L2, PnL, and execution journal).
- **`[2]`**: **Regime Detection** (1m/5m/15m classification and transition audit log).
- **`[3]`**: **Chart** (backend OHLCV candles, volume, aligned regime tape, and strategy execution overlays; read-only).
- **`[4]`**: **Configuration** (selectable effective backend options; read-only).
- On Dashboard, **`[↑/↓]`** or **`[j/k]`** selects a closed trade and **`[Enter]`** opens entry/exit regime, fee, funding, and PnL details.
- On Regime Detection, the same keys select and inspect transition events.
- The canonical regime uses 5m as the authoritative primary. The 1m state
  cannot override 5m `RANGE`, `TRANSITION`, or `UNKNOWN`; it confirms the same
  direction for 5m breakouts. The 15m state is non-veto context.

### 6A. Shared Cohort Live Launcher and Monitor

The monitor must name the exact active profile. It validates the selected
profile ID and fingerprint against the latest armed ledger identity before it
attaches, and it rejects checkpoints from another run:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml
```

The monitor does not start, stop, or replace the live order backend. Screen 2
shows provider readiness, selected/withheld intents, and the backend-authored
regime conflict preference. On a backend started with the current profile,
same-coin conflicts rank causal regime alignment before provider priority. Lone
signals remain ungated and forced regime-only exits are disabled. Screen 9 is
the full backend-authored Regime Command Deck. Quitting the TUI leaves the
backend running.

The frozen ETH/SOL v23 canary executes only the ETH precompression-pullback and
SOL range-onset providers, both directions, after the machine-bound v14 drain
and archive procedure in
`docs/guides/cohort-live-transition-and-rollback-v23.md`. At the verified flat
and order-free boundary, its exact unified live command is:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_eth_sol_canary_v23.toml \
  --enabled --i-accept-live-risk
```

Do not overlap v23 with a v14 owner. A normal transition drain withholds new
v14 entries while preserving its open lifecycle exits and venue-native stops.
Archive the completed drain and verify the new pre-start backup before treating
v23 as the active generation.

Do not restart an armed backend with an open position merely to update the TUI.
Prefer a verified flat restart. If recovery is required while open, first prove
startup adopts the exact venue position, stop, optional target, and persisted
execution plan without duplicate mutation.

### 7. Walk-Forward LightGBM Metalabeling

Train an Isotonic-calibrated LightGBM ensemble on strategy entries:

```bash
uv run python -m hypervector metalabel-train --path data/exports/<export_dir> --install
```

### 8. Inventory & System Status

```bash
uv run python -m hypervector status
```

### 9. Hypervelocity Shadow/Real Reconciliation

Compare one or more explicit backend shadow run IDs with a real-strategy CSV
covering the same UTC observation window:

```bash
uv run python -m hypervector hypervelocity-shadow-compare \
  --shadow-ledger data/paper/decisions/decisions.jsonl \
  --positions path/to/new_real_positions.csv \
  --run-id <long-run-id> --run-id <short-run-id> \
  --entry-tolerance-seconds 120 \
  --out data/logs/research/hypervelocity_shadow_compare.json
```

The command is report-only. It uses live `regime_observation` rows to define
the shadow window, refuses non-overlapping real logs, and reports entry,
direction, RANGE-state, maker submit-to-fill, exit-timing, and price
discrepancies without creating a promotion or execution gate.

### 10. Hypervelocity Regime Evaluation, Retuning, and Challengers

Use chronological evaluation and tuning against explicit recorded-position
labels. Statistical challengers are annotation-only and cannot filter, size,
route, or exit trades:

```bash
uv run python -m hypervector hypervelocity-regime-eval \
  --symbol BTC --timeframe 1m --lookback 180 \
  --positions path/to/positions.csv \
  --out data/logs/research/hypervelocity_regime_eval.json

uv run python -m hypervector hypervelocity-regime-autotune \
  --symbol BTC --timeframe 1m --lookback 180 \
  --positions path/to/positions.csv --n-trials 100 --seed 42 \
  --out data/logs/research/hypervelocity_regime_autotune.json

uv run python -m hypervector hypervelocity-regime-challengers \
  --symbol BTC --timeframe 1m --lookback 180 \
  --forward-horizon 30 --seed 42 --n-splits 3 \
  --out data/logs/research/hypervelocity_regime_challengers.json
```

### 11. Bounded Hyperliquid L2 History from 0xArchive

Configure `OXA_API_KEY` in the gitignored `.env`, then qualify a small UTC
window before widening it:

```bash
uv run python -m hypervector oxa-book-fetch \
  --symbol BTC \
  --start 2026-07-26T23:50:00Z \
  --end 2026-07-26T23:51:00Z \
  --depth 20 --limit 1000 --max-pages 1
```

The command is fixed to Hyperliquid core and stores raw response envelopes,
vendor request IDs, SHA-256 checksums, a manifest, and replay-compatible
`books.jsonl.gz` below `data/cache/vendor/0xarchive/`. It never adds a fabricated
local receive timestamp. A non-null `continuation_cursor` means the explicit
page bound truncated the requested window; it is not success-shaped full
coverage. The measured resumable REST backfill uses compressed hourly bundles;
completed manifests are skipped on restart and incomplete windows fail before
publication.

Acquire matching public trades for the same explicit UTC window:

```bash
uv run python -m hypervector oxa-trade-fetch \
  --symbol BTC \
  --start 2026-07-26T23:50:00Z \
  --end 2026-07-26T23:51:00Z \
  --limit 1000 --max-pages 1
```

Recent 0xArchive trade responses contain participant-side maker and taker
fills. Hypervector preserves every raw row but emits one public trade per
venue `trade_id`, using the `crossed=true` taker row for aggressor direction.
A truncated maker-only participant group is reported as unresolved rather
than guessed. Historical trades never receive a fabricated local receipt time.

Qualify proposed XYZ HIP-3 roster markets through public, read-only venue data:

```bash
uv run python scripts/hip3_market_qualification.py \
  --symbol xyz:SP500 \
  --symbol xyz:SPCX \
  --out data/logs/research/xyz_sp500_spcx_qualification_<timestamp>.json
```

The qualifier explicitly initializes the SDK with the `xyz` perp-dex namespace,
loads no credentials, constructs no exchange client, and grants no execution
authority. A successful report qualifies observation plumbing only. Missing
margin-table details, capped candle history, or unvalidated strategy transfer
remain explicit blockers for a future live adapter.

Qualify the expanded active research roster without treating the requested WTI
idea as an alias for a different oil benchmark:

```bash
uv run python scripts/hip3_market_qualification.py \
  --symbol xyz:SP500 --symbol xyz:SPCX \
  --symbol xyz:SNDK --symbol xyz:GOLD --symbol xyz:BRENTOIL \
  --out data/logs/research/xyz_active_roster_qualification_<timestamp>.json
```

As of the 2026-08-06 venue qualification, no active exact `WTIOIL` symbol was
present. `cash:WTI` was delisted and is historical research only;
`xyz:BRENTOIL` is an independently qualified active oil market, not a WTI
substitute. An omitted HIP-3 `growthMode` remains unresolved fee evidence and
does not block read-only observation, but the qualifier does not calculate a
fee multiplier or declare live readiness from an assumed default.

Publish a backend-owned, read-only current checkpoint for all five active
research markets:

```bash
uv run python scripts/hip3_roster_observer.py \
  --output data/runtime/research/hip3_roster_latest.json \
  --poll-seconds 120
```

The observer loads only the public wallet address and constructs one shared
Info-only SDK client for `xyz`. It publishes exact venue metadata, account
position/order truth, 20 L2 levels, 5/20-level depth and pressure, and explicit
WTI/Brent non-equivalence. Raw account maker/taker rates are separately named;
effective HIP-3 rates also require the active referral discount, deployer fee
scale, growth mode, and conservative aligned-quote status. An omitted
`growthMode` publishes null effective rates with
`effective_fee_status=unresolved_growth_mode`; it does not fabricate a default
or erase the otherwise valid book. Other malformed or partial market reads
make the entire checkpoint `unavailable` with `markets=null`; numeric zeros are
never substituted. The file is report-only, has `execution_authority=none`,
cannot promote a market, and is not consumed by the current live strategy
unless a separate, reviewed integration is later implemented.

Backfill exact HIP-3 L2 history through the distinct builder-perp route family:

```bash
set -a; source .env; set +a
uv run python scripts/oxa_backfill.py \
  --market-family hip3 --books-only \
  --symbol 'xyz:SP500' \
  --start 2026-03-18T13:00:00Z \
  --end 2026-08-06T15:00:00Z \
  --chunk-minutes 60 --workers 2
```

HIP-3 mode is intentionally book-only until typed trade and price clients use
the same route family. It stores data below
`data/cache/vendor/0xarchive/hyperliquid/hip3/<dex:ASSET>/`, preserves raw
response pages and request IDs, publishes SHA-256 evidence, and resumes only
complete identity-matching hourly bundles. Do not pass a namespaced symbol to
the core-perp downloader.

The default retry budget is 10 attempts for network, HTTP 429, and HTTP 5xx
failures, with bounded exponential delays totaling at most about 55 seconds.
Use `--retries` only when an explicit vendor-availability experiment requires a
different budget. A failed long job may be rerun with identical bounds; verified
hourly manifests are skipped rather than downloaded again.

After the requested window finishes, verify every expected directory, manifest,
and declared file checksum with the matching bounds:

```bash
uv run python scripts/oxa_archive_audit.py \
  --market-family hip3 --books-only \
  --symbol 'xyz:SP500' \
  --start 2026-03-18T13:00:00Z \
  --end 2026-08-06T15:00:00Z \
  --out data/logs/research/xyz_sp500_l2_archive_audit.json
```

Zero-row hourly windows remain explicit in the audit. A checksum-complete
archive does not imply continuous venue coverage; inspect and attribute those
empty ranges before using the data in a strategy experiment.

Acquire a paired 90-day BTC L2/trade archive with bounded workers:

```bash
set -a; source .env; set +a
uv run python scripts/oxa_backfill.py \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-27T00:00:00Z \
  --workers 4
```

Verify all expected hourly bundles and each declared SHA-256 after acquisition:

```bash
uv run python scripts/oxa_archive_audit.py \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-27T00:00:00Z \
  --out data/logs/research/oxa_btc_90d_archive_audit.json
```

Materialize the complete verified window once for fast historical queries and
replay. This does not alter paper/live execution:

```bash
uv run python -m hypervector --data-root data research-db-build \
  --symbol BTC \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-28T00:00:00Z

# Keep large HIP-3 book-only research loads separate while the live checkpoint
# periodically writes the primary market database.
uv run python -m hypervector --data-root data research-db-build \
  --database data/research/hip3_market.duckdb \
  --market-family hip3 --books-only \
  --symbol 'xyz:SPCX' \
  --start 2026-05-17T22:00:00Z \
  --end 2026-08-06T15:00:00Z

# Measure causal five-minute visible-book capacity without execution authority.
# Output creation is exclusive: choose a new path rather than overwriting a
# prior evidence report.
uv run python -m hypervector --data-root data \
  research-hip3-liquidity-profile \
  --database data/research/hip3_market.duckdb \
  --symbol 'xyz:SPCX' \
  --notional-usd 25 --notional-usd 50 --notional-usd 75 \
  --output data/logs/research/xyz_spcx_liquidity_profile.json

uv run python -m hypervector --data-root data research-db-status

# Append immutable portfolio hypotheses and decisions one writer at a time.
uv run python -m hypervector --data-root data \
  research-db-journal-append \
  --record docs/research-journal/<hypothesis>-v1.json

uv run python -m hypervector --data-root data \
  research-db-journal-report \
  --hypothesis-id <stable-hypothesis-id>

uv run python -m hypervector --data-root data \
  research-db-live-event-import --symbol BTC

uv run python -m hypervector --data-root data research-db-shadow-import

# Run source-revision writes sequentially; DuckDB permits one local writer.
uv run python -m hypervector --data-root data \
  research-db-regime-label-import \
  --labels data/logs/research/<strict-labels>.parquet \
  --metadata data/logs/research/<strict-metadata>.json

uv run python -m hypervector --data-root data \
  research-db-regime-label-import \
  --labels data/logs/research/<legacy-labels>.parquet \
  --metadata data/logs/research/<legacy-metadata>.json

uv run python -m hypervector --data-root data research-db-regime-compare

uv run python -m hypervector --data-root data research-db-shadow-trades
```

The liquidity command excludes fees unless all fee-evidence flags are supplied
together. For a fee sensitivity, record the point-in-time `userFees` maker,
taker, and referral fields plus the qualification report's deployer fee scale,
growth mode, and aligned-quote status. The command applies Hyperliquid's
published formula and labels the result as current-input sensitivity rather
than historical fee truth. Use a conservative false aligned-quote assumption
when the official status endpoint is unavailable; never silently infer it.

The DuckDB source tables preserve manifest row counts and full depth. Canonical
replay preserves unique L2 boundary observations, deduplicates repeated venue
trade IDs, and enforces half-open bounds at the requested replay window. This
prevents both silent double counting and loss of legitimate hourly-boundary
books. Re-running the build is idempotent only when stored manifest fingerprints
still match.

The shadow and regime-label imports are report-only and carry
`execution_authority=none`. The shadow importer rejects non-paper/non-shadow
rows atomically and materializes only exact five-minute groups. Label imports
verify their immutable generation metadata, accept only the pinned strict and
legacy revisions, enforce the observe-only contract, and reject conflicting
revision/timestamp identities. Run DuckDB writers sequentially; concurrent
imports fail explicitly on the database lock.

Portfolio-research revisions are also report-only. Each tracked source record
declares a stable hypothesis ID, monotonically increasing revision number,
exact superseded revision, decision, confidence, falsifier, limitations, and
SHA-256/byte identity for every evidence file. The database rejects execution
authority, automatic promotion, runtime strategy changes, changed reuse of a
revision number, and broken revision chains. Exact re-appends are idempotent;
later reports recheck whether every evidence file still matches, changed, or
is missing. Run append and report commands sequentially because concurrent
local DuckDB connections fail explicitly on the database lock.

The shadow-trades report reconstructs completed positions from actual fill
lifecycle rows, links the maker intent by client order ID, and attributes only
backend/strict/legacy regime labels available by that intent timestamp. It
reports weighted entry/exit prices, fees, signed funding, gross/net PnL, and
regime disagreements without creating execution or model authority.

The live-event import is also report-only. It retains immutable L2, public
trade, asset-context, and gap source rows; rejects changed part hashes and
conflicting trade identities; and extends `canonical_trade_5m_bars` only with
live identities absent from the manifest-verified archive.

Publish an immutable audit of one source-follow live canary after importing the
latest recorder parts:

```bash
uv run python -m hypervector --data-root data \
  research-db-live-event-import --symbol BTC

uv run python scripts/hypervelocity_source_live_canary_audit.py \
  --decisions data/live/hypervelocity_source_follow/decisions.jsonl \
  --database data/research/market.duckdb \
  --run-id <btc-source-live-run-id> \
  --out data/logs/research/source_follow_live_canary_<UTC>.json
```

The audit is report-only and never changes runtime strategy state. It preserves
sparse and poor results, compares backend OHLCV with independently recorded
public trades, measures per-bar L2 continuity, and refuses to overwrite an
existing evidence artifact. Omit `--run-id` only when the latest identified
ledger run is intentionally the audit target.

The import is required before each checkpoint. The recorder continuously
writes immutable Parquet parts, while DuckDB is a separately refreshed
research projection; a stale projection must remain visible as uncovered bars
rather than being mistaken for a recorder outage.

Measure target-scale forward paths after one live run's RANGE decisions:

```bash
uv run python scripts/hypervelocity_source_range_forward_audit.py \
  --decisions data/live/hypervelocity_source_follow/decisions.jsonl \
  --database data/research/market.duckdb \
  --run-id <btc-source-live-run-id> --symbol BTC \
  --target-price-fraction 0.0026666666666666666 \
  --horizon-minutes 5 --horizon-minutes 15 \
  --horizon-minutes 30 --horizon-minutes 60 \
  --out data/logs/research/source_follow_range_forward_<UTC>.json
```

The command is report-only. It does not infer a trade side, excludes explicit
recorder-gap horizons, censors horizons that have not elapsed, and refuses to
overwrite an existing artifact. Target touches are path diagnostics rather
than hypothetical fills or evidence of a causal entry signal.

Measure every confidence-qualified directional onset before the configured
range gate, including no-submit subminimum challengers:

```bash
uv run python -m hypervector --data-root data \
  research-db-live-event-import --symbol BTC

uv run python scripts/hypervelocity_source_event_forward_audit.py \
  --config configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_canary.toml \
  --decisions data/live/hypervelocity_source_follow/decisions.jsonl \
  --database data/research/market.duckdb \
  --run-id <btc-source-live-run-id> \
  --out data/logs/research/source_follow_event_forward_<UTC>.json
```

This observer is report-only and accepts a quiet run as explicit zero-event
evidence. It derives the range bounds and target fraction from the run's own
configuration-identity row, verifies those measurement fields against the
selected on-disk config, and reports old-versus-current profile fingerprints
separately. Its paths start at the decision reference and do not claim an
order, maker fill, fees, funding, slippage, PnL, or execution authority.

Audit the causal event cadence of one frozen source-follow profile:

```bash
uv run python scripts/hypervelocity_source_event_frequency.py \
  --profile configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_shadow.toml \
  --labels data/logs/research/<pinned-labels>.parquet \
  --labels-metadata data/logs/research/<pinned-labels>.json \
  --candles data/cache/BTC_1m_90d.parquet \
  --out data/logs/research/source_follow_event_frequency_<UTC>.json
```

The command verifies the pinned source revision and rejects candle inputs
containing sources other than `hl` or explicit `hl_gap_fill`. It reports
qualified onset counts and interarrival gaps only; it does not simulate orders,
fills, PnL, or execution authority.

Audit whether creator same-side re-entry is preceded by a raw source-regime
reset hidden by confirmed-state hysteresis:

```bash
uv run python scripts/hypervelocity_source_reentry_raw_reset.py \
  --positions docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv \
  --labels data/logs/research/hypertrader_current_1y_20250728_20260728_labels.parquet \
  --out data/logs/research/hypervelocity_source_reentry_raw_reset_<UTC>.json
```

This command is report-only, joins source labels by causal `available_at`, and
does not grant raw or confirmed labels execution authority.

Acquire venue candles and install an exact strict-Hyperliquid research cache.
Missing vendor minutes are continuity-filled only in the installed cache as
`hl_gap_fill` zero-volume bars; the immutable vendor bundle remains unchanged.

```bash
uv run python -m hypervector --data-root data oxa-candle-fetch \
  --symbol BTC --interval 1m \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-27T00:00:00Z \
  --limit 10000 --max-pages 20 --install-research-cache
```

Replay a verified archive window without constructing thousands of path
arguments:

```bash
uv run python -m hypervector --data-root data hypervelocity-maker-replay \
  --symbol BTC --timeframe 1m --lookback 90 --strict-hl-only \
  --archive-start 2026-04-28T00:00:00Z \
  --archive-end 2026-07-27T00:00:00Z \
  --fill-rule all --initial-equity 10000 \
  --maker-fee-rate 0.00015 --taker-fee-rate 0.00045 \
  --entry-ttl-seconds 300 \
  --labels-out data/logs/research/hypervelocity_oxa_90d_labels.parquet \
  --out data/logs/research/hypervelocity_oxa_90d_fill_comparison.json
```

The archive form verifies manifest identity and SHA-256 before replay, loads
one hourly pair at a time, carries order/position/equity state across hour
boundaries, and compares touch, one-tick book-through, and public-trade-through
fills. Explicit repeated `--book-path` and `--trade-path` arguments remain
available for bounded investigations. The command is report-only.

Conservative labels require the same signal to resolve identically under all
three fill assumptions. Disagreement and right-censored positions stay
unresolved. This maker comparator does not model historical funding,
the authentic venue mark price, depth-aware liquidation fills, authentic queue
rank/cancellations, or genuine local receipt latency. It does model isolated
liquidation from a book-midpoint mark proxy, BBO liquidation execution,
partial-liquidation threshold/cooldown, taker fees, and event-marked drawdown.
Do not interpret its compounded equity as a portfolio forecast.

Compare the original, every single/pair parameter change, and the full BBWP
blueprint while retaining all screening results:

```bash
uv run python -m hypervector --data-root data hypervelocity-archive-compare \
  --symbol BTC --timeframe 1m --lookback 90 --strict-hl-only \
  --positions docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv \
  --archive-start 2026-04-28T00:00:00Z \
  --archive-end 2026-07-27T00:00:00Z \
  --fill-rule all --initial-equity 10000 \
  --maker-fee-rate 0.00015 --taker-fee-rate 0.00045 \
  --entry-ttl-seconds 300 \
  --out data/logs/research/hypervelocity_archive_parameter_comparison_20260727.json
```

The measured 90-day comparison left $0.99-$8.84 from $10,000 across all
shortlisted candidates/fill assumptions, with -99.95% or worse maximum
drawdown. This is research evidence, not a strategy gate or automatic config
promotion.

### 12. Independent Five-Minute L2 Directional Challenger

Run the frozen BTC or SOL development grid on an explicit Hyperliquid DuckDB
window:

```bash
uv run python scripts/low_tf_l2_directional_challenger.py \
  --symbol BTC \
  --database data/research/market.duckdb \
  --start 2025-04-25T00:00:00Z \
  --end 2026-07-28T00:00:00Z \
  --segment development \
  --out data/logs/research/low_tf_l2_directional_btc_development_v1.json
```

The command is immutable and report-only. It aggregates public trades and L2
snapshots inside DuckDB, constructs causal completed-5m features, uses
conservative same-bar barrier ordering, purges overlapping labels from
walk-forward folds, and retains every base-rate, logistic, and LightGBM result
at thresholds 0.55, 0.60, 0.65, and 0.70. Unit-notional screening subtracts
1.5 bps maker entry plus 4.5 bps taker exit. Its bar results do not establish
private maker fills, queue position, slippage, funding, or liquidation safety;
those require the separately frozen event replay.

### 13. Hulk Smash Observer and Explicit Live Canary

Launch the BTC 30-minute Hulk observer and its read-only TUI in one terminal:

```bash
uv run python scripts/hulk_smash_canary_tui.py --mode observe
```

Observe mode loads only the public wallet identity, has no execution authority,
and starts `hulk_smash_observe.py` behind the TUI. It refuses a stale STOP file,
waits for a new run's matching configuration identity, and never accepts ledger
activity from an older process as startup success.

Live remains fail-closed and requires a fresh, explicit operator invocation:

```bash
uv run python scripts/hulk_smash_canary_tui.py \
  --mode live --enabled --i-accept-live-risk
```

The live form is not implied by this documentation and must not be invoked
without current user authorization. Both credential-presence checks, venue
preflight, the singleton account lock, and the frozen canary contract still
apply. Pressing `q`, Ctrl-C, or SIGTERM requests the backend's verified
STOP path. A flat Hulk lifecycle stops flat; an open lifecycle keeps its exact
venue-native stop/target bracket and durable ownership for restart
reconciliation. Quitting the TUI does not force-close a directional trade. If
the stop transition exceeds 120 seconds, the supervisor leaves the live backend
and STOP request intact for inspection instead of terminating a possibly active
venue lifecycle. Publish the stopped-run audit only after venue reconciliation
has subsequently proved the position and owned orders flat.

The TUI consumes `data/live/hulk_smash/decisions.jsonl` and does not simulate
orders, fills, or PnL. It displays measured acknowledgement latency, directional
fill slippage, liquidation distance, and the actual markout horizon. A markout
completed after restart is labeled with its configured target, measured
lateness, and restart provenance. Mixed target/stop fills are attributed as
`mixed_bracket_exit`, never as a full target.

After a live run has stopped and venue reconciliation proves flat, publish an
immutable audit of the exact ledger prefix:

```bash
uv run python scripts/hulk_smash_live_canary_audit.py \
  --decisions data/live/hulk_smash/decisions.jsonl \
  --run-id <hulk-live-run-id> \
  --out data/logs/live/hulk_smash_canary_<UTC>.json
```

The audit has no wallet or order adapter. It selects only an explicitly armed
mainnet run, hashes the stable ledger snapshot, accepts sparse or losing
results, and verifies exact fill-to-fee/slippage/markout identities, target
horizon provenance, liquidation-distance coverage, exit reasons, faults, and
the final flat/open-order state. It refuses to overwrite prior evidence.

### 14. Bidirectional Shared-Account Cohort and Operator TUI

Start the public-data observer and operator TUI through the first-class CLI:

```bash
uv run python -m hypervector cohort-tui --mode observe
```

Run a bounded production-provider parity observer alongside an armed backend
only with a distinct isolated ledger root:

```bash
uv run python scripts/multi_asset_bidirectional_observe.py \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab \
  --ledger-root data/observe/<unique-parity-run> \
  --max-polls 2
```

The override rebinds every observer ledger, STOP path, operator inbox, and
staged profile below that root. It refuses the configured live root, `/`, the
home directory, and the current workspace root. The command remains disarmed,
imports no order-client factory, and exposes no live-arm flags.

Observe mode is the default. It starts
`multi_asset_bidirectional_observe.py`, opens directly on screen 2, and uses the
same production nine-asset collectors and backend ledger schema as live. The
default v25 roster is BTC, ETH, SOL, HYPE, xyz:SP500, xyz:SPCX, xyz:SNDK,
xyz:GOLD, and xyz:BRENTOIL.
It imports no credential or order-client factory, exposes no live-arm flags,
and stamps every row `live_armed=false` with `execution_authority=none`. Every
fresh strategy intent is retained but explicitly withheld as
`observe_mode_no_execution`.

After the fresh disarmed configuration identity is visible, the launcher also
starts `multi_asset_bidirectional_observer_checkpoint.py`. This bounded,
read-only sidecar atomically replaces the TUI's latest checkpoint with only
technical coverage, poll/evaluation cadence, strategy intents, readiness, and
blocker attribution. Screen 1 labels it `FORWARD OBSERVER` and
`SETUP PROCESS ONLY NO OUTCOMES`; absent fills and PnL remain unavailable rather
than becoming measured zeroes.

On normal supervised observe-mode exit, the launcher snapshots the stable
cohort ledger and publishes an immutable report-only audit below
`data/logs/research/bidirectional_cohort/`. The audit separates technical
coverage, causal arrival timing, signal cadence, and per-provider setup
progression. It has no order adapter, rejects armed rows and routed actions,
and does not interpret readiness as win probability or strategy edge.

Reproduce an observer audit manually without execution authority:

```bash
uv run python scripts/multi_asset_bidirectional_observer_audit.py \
  --decisions data/live/bidirectional_cohort/decisions.jsonl \
  --run-id <bidirectional-observe-run-id> \
  --out data/logs/research/bidirectional_cohort/<immutable-audit-name>.json
```

The first observer poll fails closed on missing/duplicate provider coverage or
missing asset candles. Expected v25 coverage is 24 unique provider-symbol
evaluations: Hulk and range-onset across the four core assets, measured
source-follow on BTC, breakout-onset across the four core assets, ETH
precompression pullback, and two HIP-3 Swing/HA plus two HIP-3
breakout-pressure provider groups across five HIP-3 assets. The HYPE challenger
annotates only a fresh transition into authoritative
5m `BREAKOUT`, takes its bidirectional side from the existing hourly structural
direction, and does not confidence-gate from its sparse initial evidence. Setup
readiness is prerequisite completion and blockers, not a model score or win
probability. The same checkpoint also labels post-start provider states with
causal 5/15/30/60-minute candle paths. It reports resolved and non-overlapping
counts separately and never treats those paths as fills, PnL, or expected edge.
Provider `execution_symbols` are explicit operator-selected canary authority,
not a performance gate. The current v25 profile explicitly declares all 24
provider-symbol pairs execution-eligible, but observe mode has no credential or
order authority. The shared router still selects at most one action per asset
by explicit priority and the account is capped at nine concurrent positions,
one per configured asset.
The nine screens are:

1. Portfolio: current lifecycle, paged nine-asset market/L2 pulse, leading
   setup proximity, open positions, and rolling causal evidence.
2. Setups: selectable provider/coin readiness, exact indicators, arrival and
   decision times, routed/withheld actions, and an Enter details inspector.
3. Chart: four paged backend-authored completed-1m candlestick panes covering
   all nine assets.
4. Depth: selectable core and HIP-3 Hyperliquid ladders with up to 20 exact
   venue levels per side, multi-level imbalance, visible book-limited sweep
   cost, order counts, microprice, walls, concentration, spread, receive delta,
   OPI, and bid/ask ratio.
5. Trades: open risk, liquidation, protection, fees/funding, selectable exact
   fills, slippage, acknowledgement latency, markout, and exit attribution.
6. Journal: bounded rolling research evidence with selectable 5/15/30/60-minute
   details. Eligible fired-signal paths and readiness-only setup paths remain
   separate; setup annotations are not fill, cost, PnL, or edge evidence.
7. Control: two-step manual strategy-entry or reduce-only close requests. Rust
   never holds a venue client or secret; the Python backend remains the sole
   validator and execution authority. These are one-off overrides; automatic
   strategies remain active, with only same-cycle re-entry suppressed after a
   manual close. The controls are disabled when disarmed.
8. Regime: synchronized paged multi-asset 1m execution, authoritative 5m
   primary, and non-veto 15m context; range/non-range structure gauges; causal
   EMA/SMA, Cipher A, HARSI, Choppiness, completed MTF bias, regression, TQI,
   and L2-pressure evidence; backend label history; and resolved versus
   non-overlapping forward-path maturity. Left/right selects a coin for the
   Range Lab, which exposes exact 5m BBWP, EMA-gap, strength, coiling, breakout
   volume, individual range-cause predicates, transition age, retained-window
   state counts, and component conflicts. Movement strength is not a model
   probability, and older ledgers render missing anatomy as unavailable.
   Discrete state metrics remain exact integer categories so the audit can
   measure state and onset outcomes. All component weights remain observe-only
   until separately validated.
9. Config: effective-versus-draft restart profile editing. Validation/staging is
   allowed only while disarmed and never hot-mutates or arms the backend.

#### Current V86 seven-asset live profile

V86 displays exactly five crypto assets (`BTC`, `ETH`, `SOL`, `HYPE`, `ZEC`)
followed by two non-crypto assets (`xyz:SPCX`, `xyz:SNDK`). GOLD, SP500, and
BRENTOIL are absent. All nine exact provider-symbol routes remain visible.
Six validated directions retain execution scope: BTC sweep long, ETH range
long, SOL range short, HYPE alignment long, SPCX cash-session long, and SNDK
breakout-pressure short. BTC robust Hulk short, BTC tuned Hulk short, and ZEC
Donchian are `OBSERVE ONLY` and cannot submit an entry. V86 does not silently
replace either retired route: the preregistered ZEC UT-Bot short challenger
failed validation, so promoting it would not be evidence-coherent.

The V85 owner stopped with every asset flat and order-free. Its exact terminal
boundary is preserved in
`data/backups/bidirectional_cohort/legacy_STOP_v85_bidirectional-live-1788487098219.json`.
The V86 accounting epoch begins at `0/0/0` W/L/BE while preserving all prior
backend ledgers and the final V85 checkpoint/preflight. Screen 2 exposes all
nine entry/stop/target/hold and sizing contracts, including the three
observe-only rows; Screen 5 separates current-epoch 0/0/0 from retained
historical data. Every entry IOC remains bounded to 20 bps while reduce-only
closes retain the separate 100 bps liveness envelope.

With current explicit live-risk authorization, and only when no cohort backend
already owns the runtime lock, use the unified one-command start:

```bash
cd /Users/gestas/Prototypes/hypervector && uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v86_failed_routes_retired_f454101e_20260904T1440Z \
  --enabled --i-accept-live-risk
```

The profile fingerprint is
`f454101eadaef46fd026c1a901bb7873bad61d7e7183a4c2e342e477e4e38733`.
Startup remains fail-closed on stale or mismatched epoch identity, missing
credentials, dependency failure, venue reconciliation, backup verification,
or absent fresh telemetry. A successful preflight is point-in-time evidence;
the first fresh V86 checkpoint must still pass post-start monitoring acceptance.

Open lifecycles also show the causal entry structure-alignment score beside
the latest score. When the backend has bound an active target, the reflection
publishes its exact venue OID, limit price, and directional distance from the
venue-synchronous mark; older or incomplete evidence remains unavailable.
Closed reflections retain the entry score. The rolling
   live checkpoint groups resolved net outcomes by exact provider-symbol pair
   at fixed entry thresholds 0.00/0.25/0.50/0.75. This comparison is report-only,
   assigns rejected trades zero hypothetical PnL without capital reallocation,
   and cannot filter, size, route, close, or promote a strategy.

Attach read-only to the active V68 ledger/checkpoint without starting or arming
another backend:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_three_asset_btc_ioc_hardened_candidate_v68.toml
```

Monitor-only attachment also reads the bounded rolling checkpoint when present
at `data/runtime/bidirectional_cohort/latest_checkpoint.json`. It does not start
an analysis or execution process. The V68 view is bound to fingerprint
`9c8df6faa8005290032802d58f7e53ec5cdc5b9605218bc426ee6d3a3b3b60fd`,
shows BTC, HYPE, and SNDK, five provider-symbol routes, and six executable
directional scopes. It excludes SOL, BRENTOIL, GOLD, ETH, SP500, and SPCX from
the portfolio, setup, chart, depth, trade, control, regime, and config
selectors. SNDK long is observation-only; its only executable side is short.
The rejected bidirectional Hulk provider has no V68 execution scope. The Config
view exposes the current effective venue market-order cap: BTC 20 bps, HYPE 100
bps, and SNDK 100 bps.
The dashboard distinguishes fresh, stale, unavailable, running-consistent,
mixed, and post-stop lifecycle evidence; a missing checkpoint never changes
backend facts or becomes an empty success.

V66 run `bidirectional-live-1788257350726` stopped only after an exact flat,
order-free snapshot. Its immutable final audit records zero orders, fills,
closed trades, or faults and unchanged equity. The final source sequence was
sealed as
`data/backups/bidirectional_cohort/legacy_STOP_v66_bidirectional-live-1788257350726.json`
with SHA-256
`6edff32d7a2fdcf973d20bdf960e494efd90c0d5cb8432bca2a1634d12b4aa97`.
Generate current mainnet transition evidence with this Info-only command,
which reconciles all three V68 symbols plus retired SOL and never accepts a
signing key or live-arm flags:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_three_asset_btc_ioc_hardened_candidate_v68.toml \
  --active-config configs/multi_asset_growth_first_5000_three_asset_evidence_scope_repaired_candidate_v67.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v68_btc_ioc_hardening_flat_5000_preflight_<UTC>.json
```

The 2026-09-01 13:20 UTC V68 artifact passed with three configured assets,
three position slots, no transition blockers, and all retained and retired
venue books flat/order-free/ledger-reconciled. Its SHA-256 is
`a89b8c7d27a47b6dd1e0c816711b6a188148198c27d0bd208d04dcb64d53d102`.
Venue state remains mutable, so a later launch must regenerate rather than
silently reuse stale success evidence. Changed-profile startup independently
reconciles all retained symbols through armed adapters and every retired symbol
through Info-only readers before constructing engines.

After current operator live-risk authorization, use the exact unified V68
launcher:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_growth_first_5000_three_asset_btc_ioc_hardened_candidate_v68.toml \
  --enabled --i-accept-live-risk
```

Startup still fails closed on an observer, credential, lock, archive, approval,
pre-start backup, retained venue, retired SOL venue, or runtime identity
mismatch. The approval and preflight grant no execution authority by
themselves; only this explicit invocation carries the two live flags.

The verified current V68 owner is run `bidirectional-live-1788269536520`, with
prestart bundle `prestart_20260901T133216.520331Z_9c8df6faa800` and manifest
SHA-256 `5dc359037a5739fea2c33f15c825540dbe1f351853a5830a7966a7741e69e22c`.
The implementation SHA-256 is
`0e171a0d04a2092d5fae9ca57853c2b0e8a475c3ff85ce73ce1d7d2e5fdc667a`.
While that owner is running, use the monitor command above; a second live
command correctly refuses the singleton backend lock. TUI-owned continuous and
final live checkpoints are explicitly current-run-only, and the normal stopped
run audit is bound to the fresh run with current-run history scope. These bounds
preserve current operational telemetry and the cached portfolio archive without
materializing the multi-gigabyte historical ledgers.

For current run `bidirectional-live-1788269536520`, five additional
execution-incapable lifecycle collectors are bound prospectively to the exact
V68 provider-symbol routes and six configured directions. The frozen research
decisions are in
`configs/research/cohort_improvement_decision_overrides_v68.json`; current route
states are `data/runtime/bidirectional_cohort/v68_*_lifecycle_latest.json`; the
consolidated state is
`data/runtime/bidirectional_cohort/latest_v68_improvement_digest.json`. These
artifacts must never be rebound to another run. After a backend restart, create
new run-specific boundaries and outputs before treating route lifecycle
monitoring as current. The collectors and digest are report-only and cannot
route, pause, close, retune, promote, or change a strategy.

The V68 TUI also reads
`data/runtime/research/hip3_roster_latest.json`. Treat that attachment as
current only while `scripts/hip3_roster_observer.py` is actively publishing an
`available`, `lifecycle=running` checkpoint. The current observer process
handle is `68144`. Its 2026-09-01 refresh covers five HIP3 research markets
with complete 20-by-20 books; SNDK growth mode and effective fee evidence are
resolved. A stopped, unavailable, or older-than-five-minute file is explicitly
stale and must not be described as complete current TUI data.

Independently verify the launch-reported mandatory backup and active nine-screen
TUI projection with:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <launch-reported-prestart-bundle>

cargo test -p hypervector-tui \
  --test v68_current_runtime_qa_test -- --ignored
```

The TUI acceptance traverses paginated setup rows at 120x36 and renders all
nine screens at 120x36, 160x50, and 190x52. The interactive launcher itself
requires at least 100x28 and prints an explicit resize diagnostic below that
hard floor.

Publish one deterministic observer checkpoint manually without stopping or
mutating the running observer:

```bash
uv run python scripts/multi_asset_bidirectional_observer_checkpoint.py \
  --decisions data/live/bidirectional_cohort/decisions.jsonl \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --run-id <bidirectional-observe-run-id> --once
```

The continuous form omits `--once` and defaults to a 30-second interval. It
snapshots only complete JSONL prefixes, reports any dropped in-progress tail,
and replaces one bounded artifact. It cannot promote, pause, filter, size,
retune, or execute a strategy.

The cohort view is responsive from the 120x36 acceptance floor through wide
audit layouts. Dashboard cards use backend-derived margin and position-capacity
gauges; open positions expose liquidation distance, exact stop identity, costs,
and faults. Compact fill rows retain execution quality, while wide mode adds
exact `tid/oid` and complete audit columns. Screen 3 uses four paged native
candlestick panes from backend-authored completed 1-minute OHLCV. Left/right
selects any configured core or HIP-3 asset and Enter opens a focused read-only
chart inspector.
That inspector joins only the selected provider and coin, labels the configured
provider clock as `DECISION TF`, renders completed 1m/5m/15m/30m candles for
that clock, and shows recorded 1m/5m/15m states, readiness, indicators,
blockers, research provenance, and optional source profile. Higher-timeframe
candles are view-only aggregates of consecutive backend-completed 1m bars;
incomplete or gapped buckets are excluded. The inspector does not call the
provider clock an execution timeframe or borrow another provider's evidence;
missing current evidence remains explicitly unavailable.
Tall dashboards add a zero-baseline cumulative closed-PnL trace, chronological
outcome tape, separate long/short W-L and net-PnL ledgers, and observed venue
fill friction. Screen 5 retains portfolio and per-strategy W/L, win rate, net
USD, net return on entry margin, arithmetic average return on entry margin per
closed trade, profit factor, fees, and funding at the 120x36 acceptance floor.
Its closed-trade inspector also renders backend-authored completed-path MFE,
MAE, and peak giveback for ignored provider exits. Missing excursion fields
remain explicitly unavailable; the TUI never derives replacements from the
entry, exit, or current mark.
The operational `CURRENT RUN` row precedes `ALL-TIME`. A matching new run with
no resolved closes is explicitly labeled `FRESH RUN 0/0`; a mismatched run
identity is unavailable rather than displayed as a fabricated reset. All-time
mixed-profile history remains visible as a separately labeled comparison.
When backend process-run provenance is available, the title reports the number
of trade-bearing process windows and explicitly labels them `NOT INDEPENDENT`;
a process restart is not evidence of an independent market sample. These values
come from resolved backend lifecycles; the TUI does not reconstruct or simulate
performance.
The research screen keeps current-profile profit-lock evidence separate from an
explicit `ALL-LIVE ... MIXED CONTRACTS` mechanism view. The latter normalizes
each lifecycle's actual and counterfactual net result by its own entry notional
before computing mean basis-point deltas; it does not pool historical dollars,
claim current-profile PnL, or construct a shared-portfolio path. Both views are
report-only, and an empty current-run sample remains zero even when all-live
mechanism evidence is populated.
The checkpoint also publishes `entry_alignment_mechanism` across all completed
armed-live lifecycles. It keeps exact `breakout_side_relation` attribution
separate from the broader regime `component_stance`, reports missing legacy
telemetry as unavailable, and normalizes comparisons by each trade's return on
entry margin. This evidence cannot gate, resize, close, or promote execution;
small or one-sided groups remain descriptive rather than an entry-direction
edge claim.
All-time trade reflections also retain the maximum-hold context journal and its
regime-aware extension challenger. The challenger extends only
`still_directionally_supported` timer exits, keeps mixed or opposed exits at
the timer, honors the original protective stop, and reports completed-candle
incremental gross PnL separately from executable net PnL. It excludes changed
funding, fees, and fill slippage and therefore cannot authorize an exit-policy
change on its own.
Screen 4 consumes recorded `market_books` rows with up to 20 real venue levels
per side; it never manufactures depth. Older or already-running backends that
report five levels remain valid and receive snapshot-derived imbalance, sweep,
wall, and concentration diagnostics over only those visible levels. Screens 7
and 9 publish only atomic,
run/profile-bound local requests into `operator_commands/`; request outcomes are
read back from the backend ledger. Secrets remain environment-only and are
never rendered or written into a staged profile.
The backend emits one bounded 360-minute initial history and only unseen candles
on later polls. Older ledgers explicitly report unavailable OHLCV; the TUI never
derives candles from mark samples. Terminals below 100x28 receive an explicit
resize diagnostic instead of clipped operational telemetry.

The explicitly armed one-terminal live form is:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk
```

This documented command is not live authorization. Use it only after a fresh,
explicit user approval. The supervisor starts one serialized backend process,
waits for a new matching armed configuration identity, then starts the
read-only checkpoint sidecar and TUI. The sidecar atomically replaces one
bounded aggregate at
`data/runtime/bidirectional_cohort/latest_checkpoint.json`; it cannot submit,
pause, retune, size, or mutate the strategy. Quitting the TUI stops the sidecar
and writes the backend STOP request. After asset shutdown, the supervisor
publishes one final checkpoint before the immutable final audit. If the backend
cannot stop within 30 seconds, the supervisor preserves the process and STOP
file for inspection instead of killing a potentially protected lifecycle.

The backend-only equivalent is:

```bash
uv run python -m hypervector cohort-live \
  --enabled --i-accept-live-risk
```

Both live launch paths converge on the same fail-closed pre-start backup. After
the singleton cohort lock is acquired, but before an authenticated Hyperliquid
adapter is constructed, the backend writes an immutable bundle below
`data/backups/bidirectional_cohort/prestart_<UTC>_<fingerprint>/`. The bundle
contains the target and prior strategy sources, all existing cohort ledgers,
staged profile, bounded `latest_*.json` runtime artifacts, and the complete
bounded Python execution source set from Hypervector plus its local backtest-lab
provider dependency. `pyproject.toml` and `uv.lock` are included. Every source
and gzip archive has byte counts and SHA-256 evidence; a composite
`implementation_identity` binds the implementation file count and exact source
bytes. Startup immediately restores each archive into the hash verifier and
aborts if any copy, identity, or check fails. New live starts refuse an empty
implementation source set. The bundle excludes `.env`, wallet keys, and API
secrets. Large accumulated ledgers may extend live startup preparation; the
unified supervisor allows 900 seconds by default and still refuses startup if
verified fresh telemetry does not appear.

After the verified bundle exists, the backend writes its non-secret provenance
into the new run's authoritative `configuration_identity`: bundle/manifest
paths, manifest SHA-256, strategy-change flag, implementation file count, and
implementation SHA-256. The stopped-run audit preserves the same object. The
TUI restart-profile screen renders `PRESTART VERIFIED` plus matching hash
prefixes and source count. `PRESTART BACKUP UNAVAILABLE` is honest for a legacy
run that predates this field, but it is a startup acceptance failure for a new
run expected to use the gate.

Before editing the active config or shared cohort execution sources, create a
separate credential-free implementation baseline:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab
```

This command loads the config in observe mode and reuses the immutable
pre-start archive format. Require a verified active profile fingerprint,
`strategy_changed_from_latest_ledger=false`, nonzero implementation file count,
nonempty implementation SHA-256, and `execution_authority=none`; then run the
independent pre-start verifier against the exact printed bundle path. The
snapshot proves implementation/profile bytes only. It does not claim the live
run fingerprint, atomically freeze growing ledgers, arm execution, or replace
the mandatory bundle created by a later live startup.

Profile transitions use a separate, default-off backend drain. On screen 7,
select `TRANSITION DRAIN`, press Enter, inspect the confirmation, and press `y`
only after explicit operator authorization. An accepted drain writes
`data/live/bidirectional_cohort/transition_drain.json`, withholds openings on
flat symbols, and continues strategy exits, maximum-hold exits, manual closes,
and venue-native protection. The backend marks the drain completed and stops
only after every lifecycle is flat, signed position size is zero, and all owned
entry/stop/target/close order identities are absent. It does not activate or
start another profile. Missing drain telemetry from an older run is
`UNAVAILABLE`, never inferred inactive.

Evidence-selected v29 is retired as a transition target by append-only research
revision 7. It is a both-side forensic artifact with six executable routes
across five assets;
do not use its archived transition guide to launch it. Its common-window result
was concentrated in SPCX longs, contained negative route components and no SOL
short sample, and its frozen implementation identity no longer matches the
current source tree. v25 remains active until its exact run resolves or a
separately authorized drain reaches a verified flat and order-free boundary.
v28 is retained as a superseded forensic artifact and grants no launch
authority.
Any successor requires a new generation config, current implementation backup,
transition contract, research revision, and renewed explicit live-risk
authorization. Preserve
`configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml`
and `docs/guides/cohort-live-transition-and-rollback-v29.md` for audit history.

Track the inactive v31 HIP-3 route-pruning candidate without changing v25:

```bash
uv run python scripts/v31_route_forward.py
```

For continuous report-only refreshes, run the dedicated monitor. It invokes
only the identity-bound one-shot tracker and defaults to a 120-second cadence:

```bash
uv run python scripts/v31_route_forward_monitor.py --interval-seconds 120
```

The accepted local service label is `com.hypervector.v31.route-forward`; its
merged structured log is
`data/runtime/bidirectional_cohort/v31_route_forward.launchd.log`. Confirm the
service, v25 live owner, and v25 checkpoint owner independently with
`launchctl print`. Starting or stopping this monitor must not restart either
v25 owner.

The monitor also maintains the compact append-only
`data/logs/research/bidirectional_cohort/v31_route_material_changes.jsonl`.
It hash-chains only material route, economic, authority, position-protection,
fault, or identity changes. Timestamp and forward-evaluation-only refreshes are
deduplicated so the journal does not grow every two minutes. A malformed chain
fails explicitly; do not truncate it or silently start another history.

The bounded output at
`data/runtime/bidirectional_cohort/latest_v31_route_forward.json` validates the
exact v25 or v31 profile fingerprint, the revision-one journal declaration,
all six removed/control scorecards, and the complete executable/observe-only
authority map. Under v25 it records a cumulative pretransition baseline. Under
v31 it requires SNDK and BRENTOIL commodity Swing to remain observe-only while
GOLD Swing and all three commodity Breakout controls remain executable. A
profile transition starts a new baseline; do not subtract counters across run
or profile identities. The tracker is report-only, claims no counterfactual
fills or capital reallocation, and cannot transition, route, size, enter,
close, restart, or promote a strategy.

After an explicitly authorized v31 launch and its first complete HIP-3
breakout-pressure evaluation, publish immutable technical acceptance:

```bash
uv run python scripts/v31_poststart_acceptance.py
```

The command accepts only the exact v31 identity with complete new-run market
and provider-metric coverage, finite `imbalance_10` and
`pressure_age_seconds` for all five HIP-3 pressure routes, pressure age within
0–30 seconds, zero runtime faults, inactive transition drain, and protection
for every open position. It writes both acceptance and rejection evidence;
rejection exits with status 2. It is report-only and grants no live,
transition, sizing, or promotion authority. The aggregate checkpoint verifier
does not replace the raw-ledger exact-book and funding-cursor audit required by
`docs/guides/cohort-live-transition-and-rollback-v31.md`.

Close that raw-ledger boundary with the second immutable report:

```bash
uv run python scripts/v31_raw_ledger_acceptance.py
```

It snapshots stable exact-run prefixes, recomputes top-ten imbalance from the
latest admissible exact-symbol book at one common provider cutoff, validates
one typed funding cursor commit per routing cycle, requires contiguous
prior-end/next-start boundaries, and rejects duplicate funding identities. It
returns status 2 for a persisted technical rejection. Both v31 post-start
reports must be accepted before describing the new process as technically
accepted; neither report grants execution or establishes economic edge.

Publish a side-aware, immutable successor triage only from an immutable cohort
audit. The output is report-only and cannot mutate or promote a live route:

```bash
uv run python scripts/cohort_successor_triage.py \
  --audit data/logs/research/bidirectional_cohort/<immutable-v25-audit>.json \
  --out data/logs/research/bidirectional_cohort/<new-triage-name>.json
```

The triage keeps historical long and short evidence separate, treats open
marks as provisional, and requires supportive both-side history, resolved
both-side after-cost live outcomes, positive net PnL without the largest
winner, and an independent positive forward path before advancing a route to
shared-portfolio interaction replay. `PROCEED` does not grant live authority;
`REVISE` and `STOP` do not pause or filter the active ungated trial.

When route-level triage returns `separate_long_short_mechanisms`, publish the
provider-symbol-side composition separately. This ranks exact sides using
side-specific historical labels, current-profile execution, and explicitly
mixed-profile all-live outcomes. It is an experiment frontier rather than a
profile generator or execution gate:

```bash
uv run python scripts/cohort_side_composition.py \
  --audit data/logs/research/bidirectional_cohort/<immutable-v25-audit>.json \
  --out data/logs/research/bidirectional_cohort/<new-side-composition-name>.json
```

The report requires report-only source contracts, keeps current-profile and
mixed-profile economics separate, and requires the research frontier to retain
both long and short components. `repeated_positive_mixed_profile` is a
descriptive ranking tier, not promotion authority. The output cannot create a
config, route, order, size, close, pause, or strategy mutation.

Compare predeclared provider-symbol-side combinations on one fixed-cap shared
account only after the side-composition report exists:

```bash
uv run python scripts/cohort_separate_side_portfolio.py \
  --out data/logs/research/bidirectional_cohort/cohort_separate_side_portfolio_<UTC>.json
```

The command uses exact local HYPE and ETH one-minute bars plus funding and the
frozen twelve-block SOL event evidence. It compares the asymmetric core, a SOL
both-side sensitivity, and the source-symmetric baseline under one-position-
per-symbol, three-slot shared-capital replay. The development cutoff, one-day
purge, and already-opened final block are fixed in the command. Source lifecycle
net outcomes retain their stated fee, funding, and slippage scope; friction is
not harmonized or recomputed. Console output is deliberately limited to
decision metrics while the immutable artifact retains trade-level evidence.
The command selects no winner, grants no execution authority, and cannot alter
the running profile.

Refresh the frozen candidate's bounded prospective live-evidence observer from
the report-only checkpoint projection:

```bash
uv run python scripts/cohort_asymmetric_forward_observer.py
```

The observer derives its entry cutoff from journal revision 1, requires the
checkpoint contract to be report-only with no execution authority, and scores
only resolved venue lifecycles entered at or after that cutoff. It keeps the
candidate sides separate from HYPE-short and ETH-short symmetric controls,
excludes open marks, and does not simulate missed or router-displaced fills.
Its default output is the bounded replace-in-place research snapshot
`data/runtime/bidirectional_cohort/latest_asymmetric_forward_observer.json`.
Use a unique `--out` path below `data/logs/research/` when an immutable review
artifact is required. This observer cannot route, size, enter, close, pause, or
promote a strategy.

Keep canonical v25 SOL range-onset distinct from the retired experimental
provider `sol_aligned_range_relaxed_fixed60_bidirectional_v1`. The latter's
authoritative prospective record is nine resolved all-long paths, 4W/5L,
-113.085491 bps after costs, and PF 0.347245. It remains rejected under
append-only journal revision 2. A generic exact-one-blocker matrix that omits
the provider's 75-minute accepted-entry rearm is not identity-equivalent and
cannot reactivate, rename, or overwrite that result. Canonical v25 range-onset
remains an ungated live trial unless the operator separately authorizes a
profile transition.

The separately frozen SOL continuation observer measures source evaluations
blocked only by `awaiting_new_5m_breakout_onset` after the prospective
2026-08-08 22:50:00Z cutoff. It is report-only and must not loosen the v25
fresh-onset rule:

```bash
uv run python scripts/cohort_forward_one_blocker_challenger.py \
  --ledger-root data/live/bidirectional_cohort \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --data-root data \
  --matrix-template data/logs/research/bidirectional_cohort/v25_execution_opportunity_matrix_exlargest_20260808T2216Z.json \
  --out data/runtime/bidirectional_cohort/latest_sol_breakout_continuation_challenger.json \
  --run-id bidirectional-live-1786182011216 \
  --experiment v14-sol-breakout-continuation-aligned-fixed \
  --once
```

The frozen candidate keeps both sides, requires side-adjusted aligned OPI,
uses a 75-minute accepted-entry spacing, and estimates adverse BBO plus fees,
funding, an 80-bps stop proxy, and a fixed 60-minute exit. It has no order
adapter or promotion authority. Hypothesis-formation evidence is only two
all-long paths; require independent post-cutoff both-side evidence and positive
net return excluding the largest winner before portfolio-interaction replay.

If the Python backend is interrupted while a drain remains active, a normal
start stays refused. Recover only with the same profile and explicit live
authority:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config <exact-active-profile>
```

Recovery creates a new process run ID, preserves the drain's origin run and
request, increments `resume_count`, and remains entry-drained from startup. The
mandatory pre-start bundle captures the old drain JSON before its run binding
changes. A completed drain, different profile, failed backup, missing marker,
or ordinary start without the recovery flag is refused.

Every new cohort live start refuses an active or completed drain marker. After
the drained backend has stopped, preview the recoverable archive operation:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>
```

Then repeat with `--yes` only after verifying the run identity. The command
acquires the live runtime lock, hard-links the exact completed JSON into
`data/backups/bidirectional_cohort/transition_drains/`, verifies identical
bytes, and only then clears the start-blocking live marker. An active backend,
an incomplete drain, an identity mismatch, or an archive failure is refused.

Re-verify any saved bundle without restoring or overwriting live state:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

Use the exact path printed by the backend. The command decompresses and hashes
every archive, reports bounded profile identity, and returns nonzero on any
manifest, path, byte-count, checksum, or implementation-identity mismatch. For
a new bundle, require nonzero `implementation_file_count` and a nonempty
`implementation_sha256`. The frozen flat-boundary transition and rollback
sequence is documented in
`docs/guides/cohort-live-transition-and-rollback.md`.

Every enabled coin and provider declares both long and short, but only each
provider's explicit `execution_symbols` may route an armed action. Fresh
signals from every other provider-symbol pair are journaled with
`provider_symbol_observe_only`. The shared account permits one position per
coin and enforces the active profile's `maximum_positions` value; do not infer
a fixed portfolio cap from an older generation. Screen 8 labels each provider as
`CANARY <symbols>`, `OBSERVE ONLY`, or `EXECUTION SCOPE UNAVAILABLE` for an
older ledger; it never infers missing authority.

### Current v39 runtime and v45 growth-sizing candidate

The current armed generation is v39. Keep its existing positions, provider
deadlines, and venue-native reduce-only orders managed. Do not restart it while
any position or owned order remains. Attach the read-only monitor to the exact
active identity:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --refresh-ms 500
```

The separately versioned v45 candidate has BTC, HYPE, and `xyz:SP500`, four
provider-symbol routes, six explicit long/short scopes, ten account slots but
only three actual simultaneous asset slots, and fixed 5x isolated leverage. It
is not the active runtime. Its isolated observer is zero-authority:

```bash
uv run python scripts/multi_asset_bidirectional_observe.py \
  --config configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml \
  --ledger-root data/observe/v45_candidate_shadow
```

Variable 0.75x/1.00x/1.25x notional tiers remain telemetry-only. Readiness is
prerequisite completion, not win probability, and canonical-regime confidence
is not an approved sizing score. Keep leverage fixed at 5x unless a distinct
collateral/liquidation experiment is designed and validated.

Activate v45 only after v39 and venue are flat and owned-order-free, the old
checkpoint writer has exited, the final v39 state is preserved, and a fresh
$500 v45 preflight reconciles current mainnet fees, books, minimum lots, and
ledger/venue identity. The exact procedure, commands, post-start acceptance,
and rollback predicates are in
`docs/runbooks/2026-08-12-v39-v45-transition-contract.md`. Starting live still
requires both explicit live-risk flags; the observer does not grant authority.

The inactive ETH-transfer v12 candidate is
`configs/multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12.toml`.
It adds only
`eth_breakout_precompression_pullback_bidirectional_v1|ETH` to the v11
execution map, both directions, with a `$25` notional ceiling, isolated 5x,
60-bps venue stop, and fixed 12-hour maximum hold. Its entry readiness must
label `candidate_authority=automatic_execution` only in live mode; observe mode
remains `report_only`. Research evidence remains report-only in either mode.
The candidate is low-confidence, inactive, and may replace v11 only through a
verified-flat transition with a fresh prestart backup. Never hot-restart an
open v11 HYPE lifecycle to load it.
The exact v11-to-v12 drain, fingerprint, backup, acceptance, and rollback
contract is machine-bound in
`docs/guides/cohort-live-transition-and-rollback-v12.md`; do not substitute an
older transition guide for this generation.

During an explicitly authorized v11-to-v14 transition drain, a single
report-only checkpoint writer may use the exact v14 config so Screen 9 shows
v11 as running, v14 as pending, and the open asset as the restart blocker. Do
not attach `--eligible-policy-forward` to that mixed-generation checkpoint:
the ETH observer is source-profile-bound to v11 and must remain separate.
This comparison has no execution authority and must be stopped before drain
archival. The exact command and predicates are in
`docs/guides/cohort-live-transition-and-rollback-v14.md`.

The TUI consumes `data/live/bidirectional_cohort/decisions.jsonl`; it does not
generate signals, infer missing market state, simulate fills, or directly
place orders. Confirmed controls publish narrow local requests that only an
already-armed Python backend may validate and execute.

Publish one deterministic read-only checkpoint manually:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --venue-portfolio \
  --once
```

Attach additional frozen forward observers without replacing the primary
opportunity matrix by repeating the supplemental flag:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --opportunity-matrix data/runtime/bidirectional_cohort/latest_opportunity_matrix.json \
  --supplemental-opportunity-matrix data/runtime/bidirectional_cohort/latest_btc_structural_challenger.json \
  --once
```

Every supplemental file is required when explicitly named. Missing files,
duplicate candidate strategy identities, nested execution authority, strategy
mutation, automatic promotion, or portfolio-PnL claims fail the refresh rather
than silently omitting the observer. If a prior complete live checkpoint
exists, the rolling sidecar retains it and lets the TUI freshness warning
surface prolonged failure; it publishes an unavailable document only when no
complete live checkpoint exists. Screen 6 renders one status line per
independently attributed candidate.

HIP-3 lifecycle identities contain the namespaced symbol followed by the venue
OID, for example `xyz:GOLD:<oid>`. Checkpoint validators must remove the full
recorded `<symbol>:` prefix rather than splitting on the first colon. A stale
checkpoint accompanied by `maximum-hold lifecycle identity is inconsistent`
is a report-only projection fault; verify the live backend separately, repair
and regression-test the namespaced identity parser, then restart only the
checkpoint sidecar.

An attached execution-opportunity matrix also carries checkpoint-bound run
provenance. The sidecar classifies it as `current_run`,
`historical_prior_run`, `different_run`, or `unattributed` from the matrix
evidence run ID and timestamps. Screen 6 renders that relationship before the
matrix statistics, so a retained prior-run research artifact cannot appear to
be evidence generated by the active backend run. Older checkpoints without
this field display `PROVENANCE UNAVAILABLE`; malformed or internally
inconsistent provenance fails TUI projection rather than becoming current-run
evidence.
Current matrices also separate all observed exact-one-blocker hypotheses from
the executable subset and retain every excluded observe-only identity. Screen 6
renders `EXEC HYP <executable>/<observed> // OBSERVE-ONLY <excluded>`; older
matrices display `SCOPE UNAVAILABLE`. Counts, duplicate identities, or an
observe-only identity overlapping an executable hypothesis fail TUI projection
instead of receiving invented replay settings.

The v11 monitor launcher also passes the independent HYPE public-L2 Ridge
observer status at
`data/runtime/research/hype_l2_ridge_observer_latest.json` to the TUI. Start the
read-only view without restarting the live backend:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml \
  --mode monitor \
  --refresh-ms 500
```

Screen 6 validates that the sidecar is report-only and has no execution
authority. Before a post-cutoff HYPE entry exists, it must render
`WARM / WAITING FUTURE HYPE ENTRY`, durable book count, and freshness rather
than numeric prediction zeros. Missing, stale, or malformed sidecar data is an
explicit unavailable state and cannot replace backend trade, portfolio, or
regime telemetry.

With `--eligible-policy-forward`, the checkpoint sidecar reads official public
Hyperliquid `fundingHistory` rows for the exact ETH counterfactual window.
Screen 6 separates gross return, modeled pre-funding net, signed funding, and
after-funding net. It publishes after-funding values only when the full path is
covered by ordered venue settlements. Public API failure remains an explicit
unavailable funding field and cannot suppress the core live checkpoint or be
converted to a numeric zero. This observer has no signing client or execution
authority.

The rolling reader accepts only complete JSONL lines. If it observes an
in-progress trailing append, it drops that suffix from the current snapshot and
reports the byte count. The immutable post-stop audit remains strict and rejects
an incomplete tail rather than silently truncating final evidence.
`--venue-portfolio` uses only the configured public account address and public
Info endpoints. It separates marked total portfolio value from USDC execution
collateral, non-USDC spot value, and vault equity; it never imports a signing
key or changes sizing. A valuation failure is explicit and does not replace the
ledger-backed collateral or lifecycle checkpoint.

For live checkpoints, Screen 6 also consumes the backend-authored
`audit.execution.friction_parity` section. Its summary and selectable `EXEC`
column compare each exact provider-symbol research contract with the shared
live IOC wrapper, then show owned entry-fill fee, slippage, and acknowledgement
deltas. `ALIGNED` describes execution shape only; it is not a profitability or
promotion label. `MISMATCH` remains report-only and cannot gate, pause, retune,
resize, route, or close a trade. Older checkpoints render parity as unavailable
instead of inferring it.

The selected Screen 6 inspector also shows exact compatible-profile live
execution performance for that `strategy_id|symbol`: closed count,
wins/losses/breakeven, win rate, net PnL, net return on summed entry margin,
profit factor, fees, and funding. The backend derives these values from resolved
venue lifecycles; the TUI does not pool unlike coins or reconstruct trades.
When complete direction evidence exists, the same inspector separates long and
short W/L/breakeven, net PnL, and profit factor. Side totals must reconcile to
the exact provider-symbol total. Reduced report-only challenger records with no
side omit the split; mixed known/unknown direction coverage fails publication.
Observer mode omits the field. This sample is explicitly descriptive with
`performance_gate=false` and `balance_gate=false`; it cannot pause, filter,
resize, route, close, or promote a strategy.

The same inspector may include `BBO EPISODE ONSETS // REPORT ONLY`. These
30m/60m rows use the provider's exact configured cadence so a persistent
eligible state is not counted as repeated independent opportunities. They show
onset independent/resolved/eligible counts, after-fee-and-slippage BBO return,
median, leave-largest sensitivity, long/short coverage, and pressure stance.
They do not claim fills, PnL, funding, routing, sizing, or execution authority.
Missing legacy cadence is unavailable; malformed explicit cadence or
unreconciled counts fail projection.

The default live checkpoint launcher also attaches the predeclared asymmetric
portfolio observer from
`docs/research-journal/cohort-asymmetric-shared-portfolio-v1.json`. Screen 6
separates candidate route-sides from the excluded symmetric controls and shows
only venue lifecycles entered at or after that frozen cutoff. The observer is
report-only and cannot route, size, enter, close, pause, or promote. A loaded
checkpoint process does not reload source changes; do not restart it solely to
expose this panel while live positions remain open.

For the current HYPE breakout experiment, the live checkpoint also publishes
`audit.allocation_challenger`. It is a report-only comparison between current
and candidate provider-specific notional, margin, and portfolio maximum margin.
Screen 6 renders it only for the exact target provider-symbol row and labels it
`CANDIDATE NOT ACTIVE`, `NO PROFIT FORECAST`, and `NOT A BALANCE GATE`. It has
no execution, sizing, pause, promotion, or restart authority. The calculation
uses the venue-reported account value at any positive amount; `$500` is not a
threshold. Portfolio reserve telemetry takes the largest effective provider
policy for each coin before applying the maximum-position count, so a provider
override cannot be hidden behind an asset default when caps do not bind.

HYPE entry attribution uses the same completed multitimeframe classifier in
historical and live telemetry. In addition to 1-minute tactical measurements,
the v2 contract retains authoritative 5-minute strength percentile, BBWP,
directional EMA gap, and breakout-volume ratio. These values are report-only;
they do not become entry filters, scores, sizing inputs, or promotion evidence.
The 2026-08-04 development audit measured 1,011 lifecycles and found that none
of the four 5-minute features cleared twice the modeled round-trip cost. The
sealed, previously opened 60-day block was not reopened.

Screen 8 projects causal structure support at entry and now. The checkpoint
compares fixed entry thresholds only within each exact provider-symbol mapping;
it also partitions maximum-hold outcomes and post-exit extension evidence by
that same identity. These are report-only tuning challengers. They cannot gate,
retain, close, resize, or otherwise mutate a live lifecycle.
Screen 6 forward-observer details separately summarize the resolved entry-time
5-minute state and 15-minute context by directional stance. Both rows retain
observed/missing coverage and after-cost outcomes, are explicitly labeled
report-only, and do not turn higher-timeframe context into a veto, filter,
ranking score, sizing input, or promotion rule. Pending paths are excluded from
the outcome buckets until their frozen horizon or stop proxy resolves.
Closed regime-supported extensions also compare the resolved actual exit with
an estimated soft-deadline exit. The timer uses the persisted backend
`opened_at_ms`; exact fills, fees, and funding are reconciled before publication.
The estimate reuses the actual exit fill/reference ratio and fee rate because no
order was submitted at the historical soft boundary. Missing first-class
decision events remain labeled plan-derived. This comparison explicitly carries
`performance_gate=false` and `balance_gate=false`.
Ignored provider-exit policy evidence separately retains resolved lifecycles
and provisional open paths. Its v2 scorecard reports completed-path coverage,
MFE, MAE, and peak giveback by exact provider exit mode, so a favorable
endpoint cannot hide a large surrendered excursion. Open paths and
counterfactual trigger references remain report-only and cannot honor, ignore,
retain, close, resize, or promote an exit.
Opposition persistence uses the fixed descriptive `-0.5` structure threshold
and records one-, three-, and five-completed-decision triggers. Missing decision
minutes break the sequence. `OPP current/max` in the compact lifecycle panel is
telemetry, not an exit instruction or fitted probability.
Resolved outcomes are also partitioned by exact provider-symbol and whether the
one-, three-, or five-decision trigger occurred. They report the actual full
lifecycle after-cost result and do not simulate an early exit.

After a normal supervised live-TUI exit has stopped the owned backend, the
launcher publishes an immutable report-only audit below
`data/logs/research/bidirectional_cohort/`. The audit fingerprints all five
ledgers and reports runtime cadence, readiness, routing, positions, fills,
fees, funding, slippage, latency, markout, drawdown, faults, and
provider/side attribution. It also resolves provider evaluations against
causal completed candles at 5/15/30/60-minute horizons. Fired signals and
readiness-only annotations remain separate; blockers are attributed, startup
seed history is excluded, overlapping paths receive a non-overlapping count,
and missing elapsed candles are technical coverage gaps. These paths assume no
orders, fills, costs, sizing, or PnL and cannot promote or mutate a strategy.
The `signal_outcomes.portfolio_opportunity_dedup` section additionally groups
directional one-blocker readiness annotations by source run, symbol,
decision-minute, and side. It reports raw provider observations, unique causal
paths, cross-provider overlap, opposing-direction competition, reference-price
conflicts, and raw versus non-overlapping after-hurdle path evidence. Opposing
sides remain separate hypotheses. Conflicting reference prices are excluded
from path resolution. Exact source-run, symbol, side, provider, and blocker-set
attribution also publishes decision coverage, interarrival cadence, and
consecutive annotation episodes. Each horizon separately resolves episode
onsets and reports a leave-largest-close mean, preventing a persistent setup or
one extreme move from masquerading as repeatable entry evidence. Episode
onsets remain completed-candle counterfactuals, not orders, fills, PnL, or a
capital-allocation model.
Each new provider evaluation also retains exact machine-readable indicator
metrics; compact display strings are operator aids, not numerical audit inputs.
The stopped-run report summarizes numeric metrics across positive and
nonpositive directional paths and categorical metrics by exact value. It marks
missing/type-changing telemetry as an evidence defect, trains no model, selects
no threshold, and cannot alter execution. The audit records executable and
observe-only provider-symbol sets and rejects any routed action outside the
configuration identity's explicit execution scope.

Publish or reproduce a stopped-run audit manually without execution authority:

```bash
uv run python -m hypervector cohort-live-audit \
  --ledger-root data/live/bidirectional_cohort \
  --run-id <bidirectional-live-run-id> \
  --out data/logs/research/<immutable-audit-name>.json
```

The cohort ledger timestamp is the point-in-time cutoff for every asset ledger,
including the latest run. Rows observed after that cutoff are excluded from
current, compatible-history, and all-time projections. This prevents a close or
entry occurring during sequential multi-file snapshot capture from being mixed
with an earlier cohort portfolio state.

Compare two immutable same-run audit prefixes without manually reconstructing
their changes:

```bash
uv run python -m hypervector cohort-live-audit-delta \
  --before data/logs/research/<earlier-audit>.json \
  --after data/logs/research/<later-audit>.json \
  --out data/logs/research/<immutable-delta>.json
```

The delta command requires the same run, profile, and profile fingerprint plus
monotonic ledger rows and timestamps. It separates resolved execution changes,
provisional open-lifecycle paths, and known technical-gap growth. A removed
open lifecycle without a matching closed identity remains an explicit evidence
gap. It also attributes newly matured causal provider paths and exact
one-blocker near misses by horizon, keeping raw overlapping opportunity counts
separate from independent/non-overlapping cost-clearing evidence. Cumulative
provider evaluation counts cannot move backward. When both prefixes include
portfolio deduplication, the delta also reports newly matured unique paths and
cross-provider duplication separately. Within that section it compares exact
source-run, symbol, side, provider, and blocker episode-onset attribution,
including newly matured independent paths by horizon. A newly introduced
portfolio or episode schema is labeled non-comparable rather than assigned a
fabricated historical delta. A previously resolved episode path cannot
disappear or change in a later prefix of the same run; either condition rejects
the delta as an immutable-evidence violation. These path deltas describe
captured or missed opportunity evidence; they are not hypothetical fills, PnL,
or permission to remove a blocker. The command refuses to overwrite output,
has `execution_authority=none`, and cannot place, close, resize, route, gate, or
promote a strategy. Provisional marks alone do not recommend an economic
journal revision.

When `multi_asset_bidirectional_live_checkpoint.py` is configured with
`--research-database`, its default 600-second background sync uses a short-lived
report-only worker to append all cohort ledgers into DuckDB. The all-time
portfolio archive is rebuilt only when the exact fill identity changes;
otherwise the cached archive is reused. `pending_import` with positive pending
bytes is expected while live ledgers grow between syncs. Missing or truncated
sources are integrity failures, not ordinary lag. A database import, archive
rebuild, checkpoint, or audit never grants strategy or order authority.

Current source emits routine `cohort_research_sync` and
`cohort_historical_projection_refreshed` records as flushed JSON on the shared
stderr log stream. A loaded process predating this behavior remains unchanged
until restarted; do not claim live log acceptance from source tests alone.
After a safe restart, validate that each new routine line independently decodes
as JSON and retains `execution_authority=none`.

These CLI commands resolve to the existing project scripts without weakening
their boundaries. `cohort-live` and `cohort-tui --mode live` refuse unless both
explicit authority flags are present. Observe, monitor, and audit forms never
forward those flags. The audit command remains report-only and requires an
explicit immutable output path or output directory.

---

## Dual Backtesting Architecture

1. **VectorBT Engine (`hypervector backtest` & `hypervector autotune`)**:
   - Used for Phase 1 / Phase 1.5 high-speed vectorized simulation across 180+ days of 1m/5m data in seconds.
   - Calculates portfolio return curves, venue leverage scaling, fee schedules, trailing exit stops, and drives the autotuning engine.

2. **Nautilus Engine (`hypervector phase2-run`)**:
   - Used for Phase 2 event-driven backtesting with order matching, venue fills, and strict export bundle verification.
