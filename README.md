# Hypervector

Hypervector is a headless Python CLI for Hyperliquid mainnet research and
execution. One command, `hypervector`, covers:

- market data from Hyperliquid (Binance/Bybit backfill) and archived evidence
  from 0xArchive;
- VectorBT + TA-Lib backtests and grid sweeps;
- Karpathy autotuning, with Optuna TPE as an option;
- strict strategy bundles handed between stages;
- NautilusTrader event-driven validation;
- walk-forward LightGBM metalabel models;
- paper and shadow trading on live mainnet data, with no venue orders;
- the double-armed live cohort backend and its operator tooling.

Commands print JSON (the few exceptions are listed under
[Output contract](#output-contract-and-exit-codes)). There is no terminal UI.

## Install

Python 3.13 is required. In a development checkout:

```sh
uv sync --extra dev --extra ml                  # add --extra optuna for the Optuna sampler
.venv/bin/hypervector --help                    # same as .venv/bin/python -m hypervector --help
.venv/bin/hypervector <group> --help
.venv/bin/hypervector status                    # shortcut for 'system status'
```

`--extra integrations` adds the optional VectorBT adapters. Never run `uv sync`,
`uv run` or `pip` in an armed live checkout. Use its existing
`.venv/bin/python` as it is. Develop execution changes in a separate checkout
with its own venv.

`--help` imports no engine (no pandas, VectorBT, Nautilus, DuckDB or SDK), so it
returns within about 0.07 s.

## Command groups

Nine pillars and four supporting groups. Each group has its own `--help`.

| Group | What it does | Example |
| --- | --- | --- |
| `data` | Hyperliquid bars, funding, L2 recording, HIP-3 roster | `hypervector data history --symbol BTC --timeframe 5m --lookback-days 90` |
| `archive` | Bounded 0xArchive fetches, resumable backfill, coverage audit, trade repair | `hypervector archive audit --symbol BTC --start 2026-09-01T00:00:00Z --end 2026-09-02T00:00:00Z` |
| `backtest` | VectorBT backtest, track sweep, trial board | `hypervector backtest run --strategy crown_stack_long --timeframe 5m` |
| `tune` | Strategy and regime autotuning with a chronological holdout | `hypervector tune strategy --strategy crown_stack_long --objective net_pnl --train-fraction 0.7` |
| `nautilus` | Event-driven validation of a bundle, Parquet catalog | `hypervector nautilus run --export latest --no-network` |
| `paper` | Paper/shadow daemons, cohort observer, reports | `hypervector paper run --export latest --mode shadow --max-live-bars 60` |
| `live` | Live readiness, execution, monitoring, transitions, supervision | `hypervector live check --config <profile.toml>` |
| `regime` | Canonical regime classifier: classify, eval, export, challengers, align | `hypervector regime eval --symbol BTC --timeframe 1m --lookback-days 30` |
| `model` | Walk-forward metalabel training | `hypervector model train --export latest` |
| `export` | Strategy bundles: create, list, show, validate | `hypervector export validate --export latest` |
| `db` | DuckDB research store: build, imports, reports | `hypervector db status` |
| `pipeline` | One foreground run from data to paper hand-off | `hypervector pipeline run --strategy crown_stack_long --dry-run` |
| `system` | Data layout, capabilities, command inventory | `hypervector system status` |

The `live` group lists its commands in four sections:

- **run:** `check`, `start`, `run`, `request`;
- **observe:** `checkpoint`, `monitor`, `audit`, `audit-delta`, `report`, `economics`;
- **transition:** `backup`, `backup-verify`, `validate`, `preflight`, `drain-archive`, `rollback-profile`;
- **supervise:** `supervisor` (`status`, `watch`, `supervise`, `print-launchd`, `resume`).

## End-to-end flow

`pipeline run` runs the whole research flow in one foreground process:

1. **validate**: checks the request and writes nothing.
2. **data**: pins one history window.
3. **search**: `tune` (default) or `sweep`.
4. **export**: validates the bundle strictly.
5. **nautilus**: replays the bundle with a report-only parity block.
6. **model**: optional, with `--train-model`.
7. **paper**: hands off to shadow paper.

It never starts a daemon, never builds a venue client and never reaches `live`.

```sh
hypervector pipeline run --strategy crown_stack_long --timeframe 5m --dry-run   # print the plan, write nothing
hypervector pipeline run --strategy crown_stack_long --timeframe 5m             # run it
hypervector pipeline run --strategy crown_stack_long --timeframe 5m --train-model --paper-bars 60
hypervector pipeline run --strategy crown_stack_long --export latest            # start from a bundle; skip data and search
hypervector pipeline list
hypervector pipeline show latest
```

- **Manifest.** It goes to `<data-root>/runs/pipeline/<pipeline-id>/pipeline.json`
  and is rewritten atomically after every stage. Each stage records its status
  (`ok`, `failed`, `skipped`, `not_started`), artifacts, metrics and the
  equivalent single command.
- **Data window.** Only the data stage may refresh. Every later stage reads the
  same pinned window.
- **Nautilus.** A bundle whose symbol Nautilus cannot model is marked `skipped`
  with reason `unsupported_symbol`, and the run continues.
- **Paper.** By default the paper stage records the next command and nothing
  else. `--paper-bars N` (1..1440) runs a bounded shadow session in the
  foreground instead.
- **Notes.** The manifest always says that the evidence traps (ex-top-3,
  de-selection, both partitions, trigger count) were not computed. A pipeline
  result is untested research, not a reason to commit capital.

The same flow as single commands:

```sh
hypervector data history --symbol BTC --timeframe 5m --lookback-days 90
hypervector tune strategy --strategy crown_stack_long --symbol BTC --timeframe 5m --lookback-days 90
hypervector export list
hypervector export validate --export latest
hypervector nautilus run --export latest --lookback-days 90 --no-network
hypervector model train --export latest --lookback-days 90           # optional
hypervector paper run --export latest --mode shadow --max-live-bars 60
```

`--export REF` (and `--metalabel-bundle REF`) accepts any of:

- a bundle directory;
- a candidate id under `<data-root>/exports/` (or `models/metalabel/`);
- `latest`, the newest bundle that passes strict validation.

A reference that resolves to nothing exits 2 and lists the places it looked.

### Research behaviour worth knowing

- **History loads are cache-first and report their provenance:** served window,
  `coverage_ratio`, `age_seconds`, `stale`/`partial`, cache key and path, fetch
  time, backfill sources and warnings. A cached window is refreshed when its
  last bar is older than `--max-cache-age-hours` (default 24) or it covers less
  than 95% of the lookback. The other flags:
  - `--pin-cache` serves the cached window as it is, to reproduce a run;
  - `--refresh` forces a re-fetch;
  - `--strict-hl-only` skips the Binance/Bybit backfill;
  - `--no-network` (`nautilus run`, `pipeline run`) turns a cache miss into exit 1.
- **Fees.** The default `--fee-model` is `hl_base_taker` everywhere. The presets
  are `hl_base_taker`, `hl_referred_taker`, `hl_vip1_taker`, `hl_vip2_taker`,
  `hl_maker` and `zero`. An unknown name exits 2.
- **Leverage** is refused above the venue cap: BTC 40x, ETH 25x, SOL 20x, HYPE
  10x. Other perps get 10x, or the venue's `maxLeverage` when the caller
  supplies venue metadata (Nautilus reads it from the bundle's
  `meta.instrument`), and never more than the charter's 15x altcoin ceiling.
  CLI backtests supply no metadata, so other perps backtest at 10x.
- **Tuning.** `tune strategy` searches the first `--train-fraction` of bars
  (default 0.7). It ranks by `--objective` (`net_pnl` by default, or `score` or
  `sharpe`) and re-measures the chosen parameters once on the chronological
  holdout. The exported bundle carries the holdout metrics; `--train-fraction 1.0`
  keeps the in-sample mode. Boards go to `<data-root>/logs/research/`. One
  failed trial is recorded, not fatal; a search in which every trial fails
  exits 1. `--sampler optuna` needs the `optuna` extra and exits 2 without it.
- **Nautilus** models BTC, ETH, SOL and HYPE from a built-in table. It models
  any other perp when the bundle's `meta.instrument` holds the Hyperliquid
  universe entry (`szDecimals`, `maxLeverage`). Otherwise `nautilus run` exits
  2 and `nautilus check` reports the bundle as unsupported. Leverage stays
  capped by the charter.
- **Validation and creation.** `export validate` is strict by default (`--loose`
  relaxes it) and exits 1 for an invalid bundle. `backtest sweep` writes its
  best trial as a bundle unless `--no-export` is given.

## Safety and authority

| Authority | Commands | Rule |
| --- | --- | --- |
| live | `live start`, `live run` | Arm only with both `--enabled --i-accept-live-risk`, plus credentials. `live start` checks both flags, loads the profile in observe mode and checks provider dependencies before it hands over to the backend. `live run` resolves `--export`, then checks both flags and credentials, and refuses with exit 2 before any side effect when one is missing. |
| request | `live request` | Dry run by default. `--submit` publishes, and needs both authority flags for every action except `stage_profile`. Publishing is not execution. |
| simulate | `live check` | The flags only change the readiness report (`would_arm`). It never arms anything. |
| passthrough | `live supervisor` | `resume` is a dry run. `resume --yes` needs both authority flags, because it kickstarts the supervise agent, which starts the armed backend. |
| none | every other command | Never builds an execution client or loads the signing key. |

- **Paper and shadow** never construct a venue execution client and never place
  orders. This covers `paper *` and the `pipeline` paper stage.
- **Credentials** are loaded only when needed:
  - the full `.env`, signing key included, loads only for `live start` or
    `live run` given both authority flags;
  - archive fetches and `archive backfill` load only `OXA_API_KEY`;
  - model-aware commands load only the metalabel root variables.
  `live check` reports credential presence as booleans, and no command prints
  a secret value.
- **Dry run unless confirmed:** `paper shadow-reset --yes`,
  `live drain-archive --yes`, `live supervisor resume --yes` and
  `archive repair-trades --apply`.
- **The STOP file** (`data/live/bidirectional_cohort/STOP` for the cohort) is
  the durable operator stop. It always wins.
- Mainnet only. There are no testnet or sandbox flags.
- **No implicit gates.** Weak, negative or zero-trade results exit 0 and are
  reported. Only a technical failure aborts.

## Data root

`--data-root DIR` (default `./data`, gitignored) is accepted before the group,
after it, or after the command. All data-relative defaults resolve under it.

- **Fixed paths.** Commands whose paths come from the cohort profile, launchd or
  the repository refuse a non-default data root with exit 2: `live check`,
  `live start`, `live request`, `live audit-delta`, `live validate`,
  `live backup`, `live backup-verify`, `live rollback-profile` and
  `live supervisor`.
- **Directory creation.** Read-only commands create no directories.
  `system init` creates the layout.
- **Paper and live** never share files.

The layout is in [docs/infra-data-layout.md](docs/infra-data-layout.md).

## Output contract and exit codes

- **stdout.** A finite command prints exactly one JSON document. These commands
  stream JSON lines instead:
  - `data hip3-roster`;
  - `archive backfill` progress (then one summary line);
  - `live monitor --follow`;
  - checkpoint loops run without `--once`.

  `data book-record` writes its snapshots to `cache/book/*.jsonl` and prints one
  summary document when recording ends (with `--once`, one document for the
  snapshot row). Not JSON:
  - `live drain-archive` prints one plain-text line,
    `transition drain dry-run|archived: source=... destination=...`;
  - `live supervisor print-launchd` prints LaunchAgent plist XML;
  - `backtest report --format table` prints a human-readable table.
- **stderr.** Human notes and progress.
- **Errors** that reach the CLI boundary print one JSON document on stderr:
  `{"ok": false, "command": "<group action>", "error_type": "...", "error": "..."}`.
  Failures a handler catches itself (many `db` and `archive` commands,
  `data book-record`, `db import-cohort`) print a reduced document on stderr,
  `{"ok": false, "error": "..."}`, sometimes with extra context fields. A few
  handlers print a plain-text refusal line instead. The exit code is the
  contract.
- **Artifacts.** Stage commands add an `artifacts` object (dataset, board,
  export, validation, model, paper).

| Code | Meaning |
| --- | --- |
| 0 | Completed. A weak result, zero trades or an incomplete audit is still 0. |
| 1 | Technical failure: I/O, network, cache miss under `--no-network`, engine error, every trial failed, invalid bundle in `export validate`, `live check` not ready, failed pipeline stage. |
| 2 | Usage error or refusal before any side effect: bad arguments, unknown strategy or fee model, unresolvable `--export`, missing authority, refused data root, retired command, unsupported Nautilus symbol. |
| 130 | Interrupted (Ctrl-C). |
| other | Codes a tool keeps for itself: `live start` passes the backend's 1, 2 and 4 through; `live preflight` 3 = not ready; `live validate` 3 = book-level advisory (report-only); `live supervisor resume` 0 ready, 1 refused, 2 failed; `live supervisor status` 0 = healthy, 1 = unhealthy (the health report is still printed on stdout); `live monitor` 2 = any OSError, RuntimeError or ValueError, including a missing, stale, wrong-run, wrong-identity or unreadable checkpoint or config (I/O errors are 2 here, not 1). |

`HYPERVECTOR_DEBUG=1` re-raises technical errors with a traceback instead of
printing error JSON.

## Legacy names

Old command names still parse as hidden aliases. They never appear in help.
`system status` lists them under `legacy_aliases` and `retired`.

| Old | Current |
| --- | --- |
| `history`, `hl-funding-fetch`, `book-record`, `book-align` | `data history`, `data funding-fetch`, `data book-record`, `data book-align` |
| `oxa-<kind>-fetch` | `archive <kind>-fetch` |
| `research backtest`, `backtest <options>` | `backtest run` |
| `research sweep-up`, `sweep-up` / `research sweep-down`, `sweep-down` | `backtest sweep --track uptrend` / `--track downtrend` |
| `research report`, `report` | `backtest report` |
| `research autotune`, `autotune` | `tune strategy` |
| `regime autotune`, `hypervelocity-regime-autotune` | `tune regime` |
| `phase2-check`, `phase2-run` | `nautilus check`, `nautilus run` |
| `paper-run`, `paper-check`, `paper-report` | `paper run`, `paper check`, `paper report` |
| `paper shadow-run`, `hypervelocity-shadow-run`, `hypervelocity-shadow-reset` | `paper shadow`, `paper shadow-reset` |
| `research shadow-compare`, `hypervelocity-shadow-compare` | `paper compare` |
| `cohort observe`, `cohort observer-checkpoint`, `cohort observer-audit`, `cohort-observe`, `cohort-observer-checkpoint`, `cohort-observer-audit` | `paper observe`, `paper checkpoint`, `paper audit` |
| `cohort live`, `cohort-live` | `live start` |
| `cohort request`, `cohort checkpoint`, `cohort monitor`, `cohort audit`, `cohort audit-delta`, `cohort supervisor` | `live request`, `live checkpoint`, `live monitor`, `live audit`, `live audit-delta`, `live supervisor` |
| `cohort-request`, `cohort-checkpoint`, `cohort-monitor`, `cohort-live-audit`, `cohort-live-audit-delta`, `cohort-supervisor` | the same, in the same order |
| `live-check`, `live-run`, `live-report` | `live check`, `live run`, `live report` |
| `research economics`, `research-economics` | `live economics` |
| `regime <options>`, `regime-eval`, `regime-export` | `regime classify`, `regime eval`, `regime export` |
| `regime hypervelocity-eval`, `hypervelocity-regime-eval`, `hypervelocity-regime-challengers` | `regime align`, `regime challengers` |
| `metalabel-train` | `model train` |
| `research export`, `export <options>`, `research export-validate`, `export-validate` | `export create`, `export validate` |
| `research db-build`, `research db-status`, `research db-live-event-import`, `research db-shadow-import`, `research db-shadow-trades`, `research hip3-liquidity-profile` | `db build`, `db status`, `db import-events`, `db import-paper`, `db paper-trades`, `db hip3-liquidity` |
| `research-db-build`, `research-db-status`, `research-db-live-event-import`, `research-db-shadow-import`, `research-db-shadow-trades`, `research-hip3-liquidity-profile` | the same, in the same order |
| `cohort research-import`, `cohort-research-import` | `db import-cohort` |
| `infra-init`, `status` | `system init`, `system status` |

Old flag spellings still parse as hidden spellings of the current option:

- `--lookback` → `--lookback-days`; `--force` → `--refresh`;
- `--path` → `--export` or `--decisions`; `--ledger` → `--decisions`;
- `--init-cash`, `--cash` → `--initial-cash`; `--tp-sl-mode` → `--exit-mode`;
- `--forward-horizon` → `--forward-bars`;
- `--interval` → `--timeframe` or `--interval-seconds`; `--poll-interval` → `--interval-seconds`;
- `--timeout` → `--timeout-seconds`; `--output` → `--out`; `--out` (model train) → `--out-dir`;
- `--armed` (live check) → `--i-accept-live-risk`.

Retired names exit 2 with a message that names the replacement:

| Retired | Use instead |
| --- | --- |
| `research` (bare) | `backtest run/sweep/report`, `tune strategy`, `export create/validate`, `db …`, `paper compare`, `live economics` |
| `cohort` (bare) | `live start/request/checkpoint/monitor/audit/audit-delta/supervisor`, `paper observe/checkpoint/audit`, `db import-cohort` |
| `cohort-tui`, `hypervelocity-tui` | `live monitor`, `live checkpoint` or `paper shadow` |
| `cohort dependencies`, `cohort-dependencies` | nothing; `live start` checks provider dependencies itself |
| `research archive-compare`, `research maker-replay`, `research db-journal-append`, `research db-journal-report`, `research db-regime-label-import`, `research db-regime-compare` (and their flat spellings) | nothing; removed (paper fills use `l2_walk_v1`) |

## Verification

```sh
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile                  # default: offline, network forbidden
.venv/bin/python -m pytest tests/ -q -m "integration and not network"      # wheel install and optional integrations
.venv/bin/python -m pytest tests/ -q -m network                            # opt-in: live public venue APIs
.venv/bin/python -m hypervector status
```

## Where to go next

- [AGENTS.md](AGENTS.md): agent rules, safety defaults and the project charter.
- [skills/hypervector-cli/SKILL.md](skills/hypervector-cli/SKILL.md): the
  pillar-by-pillar operating guide.
- [skills/hypervector-regime-detector/SKILL.md](skills/hypervector-regime-detector/SKILL.md):
  the canonical regime engine.
- [docs/guides/](docs/guides/README.md): live transition, monitoring, health and
  acceptance guides.
- [HANDOFF.md](HANDOFF.md): current trading state and open items.
