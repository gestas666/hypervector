# Hypervector: current state

## What it is

Hypervector is a headless Python CLI for Hyperliquid mainnet, run as
`.venv/bin/python -m hypervector`. It covers market data and 0xArchive
evidence, VectorBT/TA-Lib backtests and sweeps, Karpathy (or Optuna) tuning
with a chronological holdout, strict strategy bundles, NautilusTrader
validation, walk-forward metalabel models, paper trading, the canonical regime
engine, and the double-armed live cohort backend with its transition and
supervision tooling.

The operator tools are packaged in `hypervector.operations` and
`hypervector_supervision`; the `scripts/` files are shims or launchd entry
points. Keep the names of `scripts/multi_asset_bidirectional_live.py` (the
supervisor finds the backend by it), `scripts/cohort_backend_supervisor.py`
and `scripts/multi_asset_bidirectional_live_checkpoint.py`.

The operator keeps no old records. Documents describe the current system only.

## Capability only: no strategy is built in

The code holds no trading strategy. Every earlier strategy failed and was
removed with everything that served it: signal builders, live providers, their
validators and contracts, tuned presets, studies, challengers, scorecards, CLI
commands and flags, tests and fixtures. Generic code that carried an old
strategy's name now has a neutral one. The shared per-asset live execution path
is `src/hypervector/live/asset_*.py` (`AssetLiveEngine`, `AssetLiveLedger`),
and the venue adapter is `HyperliquidPerpAdapter`.

A new strategy plugs in at two places. `README.md` ("Adding a strategy")
describes both:

- **Research strategy family.** A module with a `register_family()` function
  that registers `StrategySpec`s (`src/hypervector/strategies/registry.py`).
  List the module in `STRATEGY_FAMILY_MODULES` in
  `src/hypervector/strategies/__init__.py`; it is empty. A spec declares its
  `ExecutionProfile`: post-only maker entries with a time-to-live, fixed
  sizing and leverage, strategy-managed exits, or its own fee model. The
  defaults are the standard path (market IOC, conviction-scaled risk sizing,
  configured stop, target and trail). `backtest run`, `backtest sweep`,
  `tune strategy` and `pipeline run` have no default strategy and exit 2,
  naming the registration point, when the strategy is not registered.
- **Live provider.** A `ProviderRegistration` (id, signal timeframe, readiness
  lookback, collector factory and `ProviderCapability`) added to
  `src/hypervector/live/provider_registry.py`. The only built-in provider is
  the observe-only research market observer. A profile that names an
  unregistered `strategy_id` is refused at load, and a provider row's
  timeframe must equal its registered signal clock (1m, 5m or 15m). Adaptive
  and retention exits take their values from the profile's `adaptive_exit` and
  `retention_exit` tables; there are no presets. Profit-lock policies are
  `none` or `completed_bar_trailing`.

Until a provider is registered, no live profile can run. The generic loader
and `live validate` still bound every value: taker IOC only, sizing ceilings,
stop inside liquidation, STOP beside the ledger, and the authority flags. Live
mode needs at least two assets and one execution symbol.

The profiles under `tests/fixtures/` are synthetic test data. They route
test-only providers registered from `tests/conftest.py` and use placeholder
HIP-3 symbols (`xyz:AAA`...). Never use them as a template.

The regime classifier's defaults (`RegimeClassifierConfig`) are inherited
thresholds and are not tuned for any new strategy.

## Current CLI

13 groups. Pillars: `data`, `archive`, `backtest`, `tune`, `nautilus`, `paper`,
`live`, `regime`, `model`. Supporting: `export`, `db`, `pipeline`, `system`.
`<group> --help` and `<group> <command> --help` are authoritative; `README.md`
holds the group table, output contract, exit codes and legacy-name map, and
`skills/hypervector-cli/SKILL.md` is the operating guide.

- **Arming.** Only `live start` (the cohort) and `live run` (the generic daemon)
  arm, and both need `--enabled --i-accept-live-risk`, as does
  `live supervisor resume --yes`. `live run` places market IOC orders only and
  refuses a strategy that declares post-only entries.
- **Pipeline.** `pipeline run` is one foreground pass from data to the paper
  hand-off, writes `runs/pipeline/<id>/pipeline.json` and never touches `live`.
- **Nautilus** models BTC, ETH, SOL and HYPE built in, and other perps through
  the bundle's `meta.instrument`; the pipeline skips it for any other symbol.
- **Data and fees.** History loads in `data history`, `data book-align`,
  `backtest run/sweep`, `tune strategy` and the `regime` commands report
  provenance and take `--pin-cache`, `--max-cache-age-hours` and `--refresh`.
  `pipeline run` takes `--refresh` and `--no-network`, and only its data stage
  fetches. `nautilus run` takes `--no-network`. `paper run` and `model train`
  take neither; they use `--lookback-days` and the export bundle's window. The
  default fee model is `hl_base_taker`.
- **HIP-3 roster.** `data hip3-roster` polls the HIP-3 markets of a profile
  (`--config`) or explicit `--market dex:ASSET=MAX_LEVERAGE` values; with
  neither it exits 2.
- **Old names** still parse as hidden aliases; retired ones exit 2 and name the
  replacement.

## Trading state: STOPPED

- **Venue.** Flat with no open orders at the 2026-10-06 shutdown, confirmed by
  unsigned core and `xyz` reads.
- **STOP file.** Absent. To restore a durable stop, create
  `data/live/bidirectional_cohort/` and write a one-line reason to its `STOP`.
- **launchd.** `local.hypervector.cohort.supervise`, `.checkpoint`, `.watch`
  and `local.hypervector.research.roster_observer` are disabled and unloaded.
  The installed supervise and checkpoint plists pass a deleted profile, and
  some pass arguments that no longer exist. For a new profile, copy them and
  edit the arguments as "Installed plists" in
  `docs/guides/cohort-live-transition-and-rollback.md` describes: point
  `--config` at the new profile, drop `--disable-asymmetric-forward-observer`
  and `--backtest-lab-root`, and give the roster observer `--config` or
  `--market`.
- **`data/` holds market data only.** It holds `data/cache/` (candles, books,
  events, vendor archives) and the research databases under `data/research/`
  (`market.duckdb`, `hip3_market.duckdb`, `live_event_research.duckdb`,
  `hip3_asset_context/`). Their schema is exactly what the code defines; the
  old-run tables (cohort events and sources, shadow ledger events, portfolio
  revisions) are empty. Every other directory under `data/` is empty, and the
  ledger root `data/live/bidirectional_cohort/` does not exist yet; the ledger
  creates it. The first start of a new profile has no previous identity, so it
  needs no approval and no drain archive. The engine hardcodes this root, so
  profiles must keep `cohort_ledger` and `stop_file` in it.
- **No external provider package.** Live start, validation and backup hash
  only this repository's sources.

## Open items

- **The engine API wallet `hl-api` expires 2026-10-22T12:59:22Z.** Before any
  armed start, the operator approves a new API wallet under a different name
  (for example `hl-api-2`) and puts its key in `.env`. Never re-approve the
  name `hl-api`: that de-registers the signer at once. After expiry, every
  armed start is refused.
- **Live identity.** Every edit under `src/` changes the live implementation
  identity, so the next armed start records a new pre-start bundle and needs
  an explicit operator go-ahead. Profile fingerprints changed with this
  cleanup, so any profile or approval kept outside the repository needs
  re-approval.
- **HIP-3 settlement or halt.** A venue settlement or halt of an open HIP-3
  (`xyz:`) position faults the whole backend, and the restart is then refused.
  While live, watch the venue notices and send `live request --action
  manual_close` before a settlement window.
- **Checkpoint cost.** Checkpoint publication cost grows with run age. On a
  long run, watch `live monitor` freshness. A same-profile restart at a flat
  window resets it.
- **Free disk.** The supervisor alerts below about 14 GiB free and treats less
  than 10 GiB as a problem. 156 GiB were free on 2026-10-20. The Trash holds
  `hypervector-cleanup-20261019/` (about 108 GB of old run data and worktrees)
  and `hypervector-cleanup-20261020/` (old challenger plists, local strategy
  notes, cached study outputs and the exported Hypertrader label rows);
  emptying it is the operator's call. The largest consumers are `data/cache/`
  (about 111 GB) and the research databases (about 62 GB).

## How to verify

```bash
.venv/bin/python -m pytest tests/ -q -n 6 --dist loadfile
.venv/bin/python -m pytest tests/ -q -m "integration and not network"
.venv/bin/python -m hypervector status
```

`--help` must stay under 0.07 s.

## Last verified state

The capability-only cleanup, 2026-10-20:

- Default suite: 6,644 passed, 1 skipped, 0 failed (`-n 6`, about 35 s).
  Synthetic strategies (`tests/synthetic_strategies.py`) and providers
  (`tests/synthetic_live_providers.py`) exercise every generic path.
- `-m "integration and not network" --ignore=tests/test_install.py`:
  2 passed (the SIGTERM stop-latency tests). `-m network` was not run.
- Every module under `src/` imports; `--help` exits 0 for the root, every
  group and every command; `ruff check src tests` passes.
- `--help` 0.06 s; `status` and `export list` exit 0.
