---
name: hypervector-cli
description: Operate the unified hypervector CLI pillar by pillar - Hyperliquid and 0xArchive data, VectorBT/TA-Lib backtests and sweeps, Karpathy/Optuna tuning, NautilusTrader validation, metalabel models, paper/shadow trading, the double-armed live cohort and its transition tooling, the DuckDB store and the end-to-end pipeline.
---

# Hypervector CLI

Run `.venv/bin/python -m hypervector` (or the installed `hypervector`). Every
group has `--help`, and every command has `<group> <command> --help` with units
and defaults. `README.md` holds the full group table, the output contract, the
exit codes and the legacy-name map.

## Rules that always apply

- **Paper and shadow never place orders.** `paper *` and the pipeline's paper
  stage never build a venue execution client.
- **Live arms only on explicit request.** It needs both `--enabled` and
  `--i-accept-live-risk`. Only `live start` (the cohort) and `live run` (the
  generic daemon) arm; `live supervisor resume --yes` restarts the armed backend.
  A documented live command is not authority to run it. Arm only when the user
  asks in this conversation.
- **The STOP file is the durable operator stop.** Never delete it, and never
  delete a transition-drain marker, without an explicit operator instruction.
- **Never print secrets.** `live check` reports credentials as booleans only.
- **Mainnet only.** No neural-trader.
- **No implicit performance gates.** Weak, negative and zero-trade results exit
  0 and are reported; only technical failure aborts.
- **Working in an armed checkout.** Use its existing `.venv/bin/python`. Never
  run `uv run`, `uv sync` or `pip` there. Develop in a separate checkout with
  its own venv.
- **Implementation identity.** Every `.py` under `src/hypervector` and
  `src/hypervector_supervision`, and every spec JSON, is part of the live
  implementation identity. Any edit means the next armed start records a new
  pre-start bundle and needs an operator go-ahead.
- **Result contract.** Read the JSON on stdout; errors go to stderr, normally
  as one JSON document. Exit codes: 0 done, 1 technical failure, 2 refused
  before any side effect. A few commands keep their own codes (`live start`,
  `live preflight`, `live validate`, `live supervisor status|resume`,
  `live monitor`); `README.md` lists them, and the non-JSON outputs.

## Discovery

```sh
hypervector --help
hypervector status                       # = system status: inventory, capabilities, safety flags, legacy names
hypervector system status --probe-model  # also validate the metalabel bundle
hypervector system init                  # create the data layout under --data-root
hypervector --data-root /tmp/scratch data history --symbol BTC --lookback-days 30
```

`status` creates nothing and probes no wallet. Use `--data-root` to scope a run
away from `./data`. The `live` commands whose paths come from the profile refuse
a non-default root.

## data: Hyperliquid market data

```sh
hypervector data history --symbol BTC --timeframe 5m --lookback-days 90
hypervector data history --symbol ETH --timeframe 1m --lookback-days 30 --pin-cache
hypervector data funding-fetch --symbol BTC --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z
hypervector data book-record --symbol BTC --interval-seconds 2 --max-snapshots 100
hypervector data book-align --book-path data/cache/book/BTC_l2_<YYYYMMDD>.jsonl --symbol BTC --timeframe 1m
hypervector data hip3-roster --max-polls 1
```

- **Cache-first.** Every history load reports its provenance: window,
  `coverage_ratio`, `age_seconds`, `stale`/`partial`, cache key and path,
  backfill sources and warnings.
- **Refresh.** A window is refreshed when its last bar is older than
  `--max-cache-age-hours` (24) or it covers less than 95% of the lookback.
- **Pinning.** `--pin-cache` reproduces a run on the installed window, and
  `--refresh` forces a re-fetch.
- **Backfill.** `--strict-hl-only` keeps Binance/Bybit out, and uses its own
  cache entry.
- **Symbols.** `--symbol` takes a coin as typed: `BTC`, `kPEPE`, `xyz:TSLA`.

## archive: 0xArchive evidence

```sh
hypervector archive candle-fetch --symbol BTC --timeframe 1m --start 2026-09-01T00:00:00Z --end 2026-09-02T00:00:00Z
hypervector archive candle-fetch --market-family hip3 --symbol xyz:SNDK --timeframe 15m --start ... --end ...
hypervector archive trade-fetch --symbol BTC --start ... --end ...
hypervector archive book-fetch  --symbol BTC --depth 20 --start ... --end ...
hypervector archive price-fetch --symbol BTC --start ... --end ...
hypervector archive liquidation-fetch --symbol BTC --start ... --end ...
hypervector archive backfill --symbol BTC --start ... --end ... --workers 4          # resumable; JSONL progress
hypervector archive audit    --symbol BTC --start ... --end ...                      # read-only coverage
hypervector archive repair-trades --bundle <dir>_trades                              # preview; --apply to publish
```

- **API key.** Fetches load only `OXA_API_KEY`, and all arguments are validated
  before any API call.
- **Window bounds.** A window that needs more than `--max-pages` is refused and
  nothing is stored. For `trade-fetch`, `book-fetch` and `liquidation-fetch`,
  `--allow-partial` stores the window under a `_partial` directory that
  backfill, audit and `db build` never read.
  `candle-fetch` and `price-fetch` have no partial option (passing
  `--allow-partial` is a usage error, exit 2); `candle-fetch` derives
  `--max-pages` from the window when it is omitted.
- **Backfill** skips chunks already archived. It exits 0 when complete and 1
  when incomplete.
- **Audit** always exits 0 and reports `complete`, `expected`, `present` and
  every missing bundle start.
- **Trade repair.** `repair-trades --apply` moves the original aside to
  `<bundle>.pre_taker_only_v2`. Rebuild the store afterwards with
  `db build --replace-changed`.

## backtest: VectorBT + TA-Lib

```sh
hypervector backtest run --strategy crown_stack_long --symbol BTC --timeframe 5m --lookback-days 90 --leverage 2
hypervector backtest run --strategy crown_stack_long --exit-mode trail --trail-atr-mult 2.5 --fee-model hl_vip1_taker
hypervector backtest sweep --track uptrend --timeframe 5m          # every trial to the board; best trial exported
hypervector backtest sweep --track downtrend --no-export
hypervector backtest report --source all --limit 20 --format table
```

- **Fees.** The default fee model is `hl_base_taker`; `--fee-model zero` and
  `--no-costs` are for debugging only.
- **Leverage** is refused above the venue cap: BTC 40, ETH 25, SOL 20, others 10.
- **Sweep strategy.** `--strategy` defaults to the track's `trend_ride_*`, then
  `crown_stack_*`. A strategy whose role does not match `--track` exits 2.
- **Report.** `backtest report` is read-only. It ranks RunsDB sweep trials and
  the tune boards under `logs/research/`.

## tune: autotuning with a chronological holdout

```sh
hypervector tune strategy --strategy crown_stack_long --timeframe 5m --n-trials 100
hypervector tune strategy --strategy crown_stack_long --sampler optuna --objective sharpe --train-fraction 0.8
hypervector tune regime --positions positions.csv --n-trials 100 --seed 7 --train-fraction 0.7
```

- **Sampler.** `tune strategy` defaults to Karpathy search, a random-adaptive
  search with elite zoom. `--sampler optuna` (TPE) needs the `optuna` extra and
  exits 2 without it.
- **Holdout.** The search runs on the first `--train-fraction` of bars (0.7),
  ranks by `--objective` (`net_pnl`, `score` or `sharpe`) and re-measures the
  winner once on the holdout. The exported bundle carries holdout metrics
  (`evaluation_window` in `metrics.json`); `--train-fraction 1.0` is in-sample.
- **Board.** It records the seed, data window, costs, search space, code
  identity and report-only warnings. A single trial error is recorded; a search
  in which every trial fails exits 1.
- **Regime tuning.** `tune regime` writes an exclusive-create board under
  `logs/research/regime_autotune_<UTC>.json`, or at `--out`, which must not
  exist yet.

## nautilus: event-driven validation

```sh
hypervector nautilus check --export latest                  # read-only loadout + offline probes
hypervector nautilus run --export latest --no-network       # lookback defaults to the bundle's
hypervector nautilus run --export <candidate-id> --signal-mode precomputed --conviction 0.5
hypervector nautilus catalog --symbol BTC --price-precision 1 --size-precision 5
```

- **Symbols.** BTC, ETH, SOL and HYPE are built in. Any other perp needs
  `meta.instrument` (`szDecimals`, `maxLeverage`) in the bundle; without it
  `nautilus run` exits 2. Charter leverage caps always apply.
- **Signal modes.** `--signal-mode auto` precomputes signals when a causal probe
  agrees, else it replays windowed. `precomputed` fails rather than falling back.
- **Offline runs.** With `--no-network`, a cache miss exits 1.
- **Catalog.** `catalog` writes recorded public events into a Parquet catalog.
  It is opt-in, and the pipeline never runs it.

## paper: paper and shadow (no venue orders)

```sh
hypervector paper check
hypervector paper run --export latest --mode shadow --max-live-bars 60
hypervector paper run --export latest --metalabel-bundle latest --metalabel-mode observe
hypervector paper report --last 5
hypervector paper shadow --config <hypervelocity-profile.toml> --max-live-bars 30   # --config required
hypervector paper shadow-reset                       # dry run; --yes backs up, then resets
hypervector paper compare --shadow-ledger <decisions.jsonl> --positions positions.csv --run-id RUN
hypervector paper observe --config <profile.toml> --max-polls 10     # cohort collectors, zero authority
hypervector paper checkpoint --once
hypervector paper audit --run-id RUN --out-dir data/logs/observer-audits
```

- **Modes.** `shadow` (the default) produces mainnet-honest intents and no venue
  orders; `paper` produces offline synthetic fills.
- **Fills.** They use `l2_walk_v1` while the book is fresher than
  `--max-book-age-ms` and `bar_close` otherwise.
- **Metalabels.** `--metalabel-mode` is `off`, `observe`, `scale` or `filter`.
- **Observer paths.** The observer writes to `paper/cohort/` and its checkpoint
  goes to `runtime/cohort_observer/latest_checkpoint.json`. It never touches
  the live ledger or the live checkpoint.

## live: execution and cohort operations

Run section. Readiness, execution and requests:

```sh
hypervector live check --config <profile.toml>                                              # exit 0 ready, 1 not
hypervector live start --config <profile.toml> --enabled --i-accept-live-risk                 # ARMS: operator request only
hypervector live run --export <bundle> --enabled --i-accept-live-risk --max-notional-usd 50   # ARMS: generic daemon
hypervector live request --inbox <dir> --run-id RUN --profile-fingerprint FP --action manual_close --symbol SOL
```

- **`live check`** reports, as booleans: credential presence, both authority
  flags, the profile loaded in observe mode with its fingerprint, provider
  dependencies, the STOP file and the transition-drain marker. Its `blockers[]`
  says what stands in the way.
- **`live start`** refuses (exit 2) before handing over to the backend when a
  flag is missing, the profile does not load or dependencies fail. After that
  the backend's own codes pass through: 1 run failed, 2 start refused,
  4 degraded.
- **`live run`** trades one strict bundle with a hard per-order notional cap.
  `--export` takes a bundle directory, a candidate id under `exports/` or
  `latest`. It arms only when the venue position for the coin reads flat. Its
  decisions go to `live/decisions/decisions.jsonl`, and `live report` summarizes
  them. It owns the shared live account for its whole run
  (`data/live/shared-account.lock` in the checkout, whatever `--data-root` says),
  so it and the cohort refuse each other. It refuses (exit 2) before any venue
  call when a flag, the credentials or the bundle is missing or unresolvable, or
  another live backend owns the account. A strategy failure on an armed bar is
  recorded as `intent_error` and stops it (exit 1); the run JSON reports the open
  `position_qty` at stop.
- **`live request`** is a dry run by default. Its actions are `manual_enter`,
  `manual_close`, `transition_drain` and `stage_profile` (with `--settings`).
  `--submit` publishes, and needs both authority flags for every action except
  `stage_profile`. Publication is not proof of backend acceptance or venue
  execution.

Observe section. Read-only:

```sh
hypervector live checkpoint --config <profile.toml> --once --venue-portfolio
hypervector live monitor --config <profile.toml> --follow
hypervector live monitor --config <profile.toml> --run-id RUN --out independent.json
hypervector live audit --run-id RUN --out-dir data/logs/cohort-audits
hypervector live audit --history-scope all-time --out data/logs/cohort-audits/all.json
hypervector live audit-delta --before a.json --after b.json --out delta.json
hypervector live economics --checkpoint checkpoint.json --funding BTC_funding.parquet --out economics.json
hypervector live report --last 5
```

- **Checkpoint.** `live checkpoint` requires `--config` and is bound to the
  selected run by default (`--no-current-run-only` lifts that). Never point two
  checkpoint writers at the same `--out`.
- **Monitor.** `live monitor` owns no backend and checks run/profile identity
  and freshness (`--maximum-age-seconds`). It exits 2 for any missing, stale,
  wrong-identity or unreadable checkpoint or config, I/O errors included.
- **Audit.** A current-run `live audit` needs `--run-id`; use
  `--history-scope all-time` for everything.
- **Audit delta.** `live audit-delta` compares two immutable audit prefixes. The
  comparison distinguishes resolved execution, provisional open-lifecycle state,
  and known technical-gap growth. These reports have execution_authority=none.

Transition section. Profile changes, backups and rollback:

```sh
hypervector live backup --config <active.toml>                 # verified pre-change source + ledger backup
hypervector live backup-verify --bundle <printed path>
hypervector live validate --config <candidate.toml> --mode live --equity 5000   # 0 ok, 1 objection, 2 refused, 3 advisory
hypervector live preflight --config <candidate.toml> --active-config <active.toml>   # 0 ready, 3 not ready, 2 refused
hypervector live drain-archive --expected-run-id RUN            # dry run; --yes archives and clears the blocker
hypervector live rollback-profile --current <active.toml> --verify <rollback.toml>
```

None of these arms or starts anything. Follow the full procedure in
`docs/guides/cohort-live-transition-and-rollback.md`.

Supervise section:

```sh
hypervector live supervisor status
hypervector live supervisor resume                                        # dry run after a host reboot
hypervector live supervisor resume --yes --enabled --i-accept-live-risk  # kickstarts the armed supervise agent
```

- **Status.** `live supervisor status` prints the health report and exits 0
  when healthy, 1 when unhealthy.
- **launchd.** The plists run the unchanged `scripts/` entry points. Never
  regenerate installed plists with `print-launchd`; copy them and edit only the
  intended arguments.

## regime and model

```sh
hypervector regime classify --symbol BTC --timeframe 1m --lookback-days 30     # canonical engine (1m)
hypervector regime classify --detector ema --fast 12 --slow 48 --timeframe 5m
hypervector regime eval --symbol BTC --timeframe 1m --lookback-days 30 --forward-bars 15
hypervector model train --export latest --train-days 45 --test-days 15          # --install copies into models/metalabel/
```

The regime commands are covered in `skills/hypervector-regime-detector/SKILL.md`.
`model train` writes `models/metalabel/wf_<strategy>_<time>` under the data root.

## export and db (supporting)

```sh
hypervector export list --symbol BTC
hypervector export show --export latest
hypervector export validate --export latest --require-costed --require-metrics
hypervector export create --track uptrend --symbol BTC --timeframe 5m
hypervector db status
hypervector db build --symbol BTC --start ... --end ...          # verifies manifests; incremental
hypervector db import-events --symbol BTC
hypervector db import-paper
hypervector db import-cohort --ledger-root data/live/bidirectional_cohort
hypervector db paper-trades
hypervector db hip3-liquidity --symbol xyz:TSLA --notional-usd 25 --notional-usd 50
```

- **Bundles.** `export validate` is strict by default (`--loose` relaxes it) and
  exits 1 when invalid. `export list` flags invalid bundles rather than hiding
  them.
- **Database.** `--database` defaults to `<data-root>/research/market.duckdb`.
  DuckDB takes one writer at a time, so run imports sequentially. The store is
  analytical and has execution_authority=none.

## pipeline: the end-to-end flow

```sh
hypervector pipeline run --strategy crown_stack_long --timeframe 5m --dry-run
hypervector pipeline run --strategy crown_stack_long --timeframe 5m --train-model --paper-bars 60
hypervector pipeline run --strategy crown_stack_long --export latest --no-nautilus
hypervector pipeline list
hypervector pipeline show latest
```

- **Stages.** validate, data, search (`--search tune|sweep`), export, nautilus,
  model (`--train-model`), paper.
- **Manifest.** `runs/pipeline/<id>/pipeline.json` is written atomically after
  every stage, and each stage records the single command that reproduces it.
- **Exit codes.** 0 when every requested stage completed, 1 on the first
  technical failure (the manifest is left partial), 2 when refused before any
  work.
- **Nautilus.** An unsupported symbol makes the stage `skipped`. The parity
  block is report-only.
- **Evidence traps.** The pipeline never computes them (ex-top-3, de-selection,
  both partitions, trigger count). Run those checks before any result
  justifies capital.

The same flow as single commands:

```sh
hypervector data history --symbol BTC --timeframe 5m --lookback-days 90
hypervector tune strategy --strategy crown_stack_long --symbol BTC --timeframe 5m --lookback-days 90
hypervector export list
hypervector export validate --export latest
hypervector nautilus run --export latest --lookback-days 90 --no-network
hypervector model train --export latest --lookback-days 90            # optional
hypervector paper run --export latest --mode shadow --max-live-bars 60
```

## Legacy names

Old names still work as hidden aliases, for example `cohort-live-audit-delta`
runs `live audit-delta`, `research sweep-up` runs `backtest sweep --track uptrend`,
and `phase2-run` runs `nautilus run`. Always write the current names.
Retired names (bare `research`/`cohort`, the TUI commands, the removed research
commands) exit 2 with the replacement. The full list is in `README.md`.

## Verification

```sh
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile                  # offline default
.venv/bin/python -m pytest tests/ -q -m "integration and not network"
.venv/bin/python -m pytest tests/ -q -m network                            # opt-in only
.venv/bin/python -m hypervector status
```

Unit tests forbid network access and use temporary data roots. Never write
under `data/` from a test.
