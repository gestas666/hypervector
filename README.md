# Hypervector

A Python CLI for Hyperliquid research and execution. The retained pipeline is
Hyperliquid/0xArchive evidence → VectorBT research and Karpathy tuning → strict
strategy exports → NautilusTrader historical validation → paper/shadow runs.
Explicitly armed live execution uses the existing Hyperliquid adapters and
shared portfolio services.

The terminal UI has been retired. Headless telemetry, accounting, operator
requests and execution services remain in Python. Historical reports and
signed approvals are evidence, rather than current operating instructions.

## Install and discover

Python 3.13 is required. Use an isolated environment for development. Do not
synchronize dependencies in an armed deployment.

```sh
uv sync --extra dev --extra ml
.venv/bin/hypervector --help
.venv/bin/hypervector status
.venv/bin/hypervector research --help
```

`--data-root` is accepted before the workflow, after its group, or after its
command. Cohort profiles bind their own exact ledger/configuration paths;
select an explicit profile and use `--ledger-root` for an isolated observer.
Model discovery respects an explicit data root. An explicit
`HYPERVECTOR_METALABEL_ROOT` remains an intentional override.

## Workflows

| Group | Responsibilities | Example |
| --- | --- | --- |
| `system` | Capabilities and local data layout | `system status` |
| `data` | Hyperliquid history, funding and L2 recording | `data history --symbol BTC --lookback 30` |
| `archive` | Bounded 0xArchive candles, books, trades, prices and liquidations | `archive trade-fetch --help` |
| `research` | VectorBT backtests, Karpathy tuning, sweeps, exports, replay and DuckDB | `research backtest --strategy crown_stack_long` |
| `nautilus` | Export checks and event-driven historical backtests | `nautilus run --path data/exports/example` |
| `paper` | Synthetic paper/shadow sessions and reports | `paper run --path data/exports/example` |
| `cohort` | Production signal observation, live cohort, checkpoints and audits | `cohort observe --config profile.toml --ledger-root data/paper/cohort` |
| `live` | Armed execution of an exported strategy and reports | `live check` |
| `regime` | Causal classification, evaluations and snapshot export | `regime eval --symbol BTC --lookback 30` |
| `model` | Walk-forward metalabel training | `model train --path data/exports/example` |

Non-visual flat commands remain compatibility aliases, including `backtest`,
`autotune`, `phase2-run`, `paper-run`, `history`, `oxa-*-fetch` and `cohort-live`.
Help and inventory are generated from the same packaged option declarations.
Cohort audits default to the selected current run; provide `--run-id`. Use
`--history-scope all-time` only when a full historical audit is intended.

```sh
hypervector research autotune --sampler karpathy --n-trials 100
hypervector paper shadow-run --config configs/hypervelocity_faithful.toml
hypervector paper report --last 5
hypervector cohort checkpoint --config profile.toml --once --current-run-only
hypervector cohort monitor --config profile.toml --follow
hypervector cohort audit --run-id RUN_ID --out-dir data/logs/cohort-audits
hypervector cohort supervisor status
hypervector research economics --checkpoint snapshot.json --funding BTC_funding.parquet --out economics.json
```

The supplied research profiles may reference local exports, models, external
`backtest-lab` providers or frozen approval bundles. Installation alone does
not provide those artifacts or prove operational readiness. Select their paths
explicitly. `status` reports installed capabilities; it does not probe a wallet
or certify a live deployment.

## Safety and operator controls

Paper/shadow paths cannot submit venue orders. Live startup still requires
both `--enabled --i-accept-live-risk`, credentials, valid profile/evidence,
venue reconciliation, pre-start backups and an absent STOP file. No process is
armed or restarted by installation, help, monitoring or status.

`cohort request` replaces the terminal's operator request writer. Supply the
exact run ID, profile fingerprint and existing inbox. Its default prints a
validated dry run. `--submit` publishes a request atomically; live-affecting
requests also require both authority flags. Backend acceptance/outcome remains
separate from publication. Actions are `manual_enter`, `manual_close`,
`transition_drain` and `stage_profile` (with a JSON `--settings` document).

`cohort dependencies` supervises unsigned signal sources for a selected
profile. It stops only children it owns. `cohort monitor` owns no execution
process. Optional `--out` rebuilds an independent checkpoint from the exact
shared source and accounting epoch.

## Verification

```sh
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pytest tests/ -q -m evidence
.venv/bin/python -m pytest tests/ -q -m performance
.venv/bin/python -m pytest tests/test_install.py -q -m integration
```

The default suite forbids network access. Historical `evidence` tests require
operator artifacts that are intentionally outside version control. Optional
VectorBT integrations use `hypervector[integrations]`; Optuna/hybrid samplers
use `hypervector[optuna]`. TA-Lib indicators, Karpathy and the VectorBT Rust accelerator remain
part of the core installation. Technical trial failures are errors; weak
performance is a reported result, without new implicit strategy/risk gates.

## Current checkout and retained history

The original checkout is the maintained unified CLI version on `main` after
verification and merge. Its current handoff is `HANDOFF.md`. Operational
supervision is packaged separately as `hypervector_supervision` so trading
engine import failures cannot disable the independent watcher. Compatibility
scripts continue to call the same packaged services.

Historical approvals, research journals, shelved D1 tooling and experimental
research APIs are retained as provenance and compatibility surfaces. They do
not auto-run or enter the default CLI pipeline. Historical hash checks audit
their dated source/data snapshots; they do not authorize the current source.
See `docs/reviews/2026-10-17-unified-current-validation.md` for acceptance and
retention decisions. Trading remains stopped until separately authorized.
