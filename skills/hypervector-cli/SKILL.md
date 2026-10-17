---
name: hypervector-cli
description: Operate the unified Hyperliquid CLI for VectorBT and TA-Lib research, Nautilus validation, Karpathy tuning, 0xArchive acquisition, and paper/shadow/live services.
---

# Hypervector CLI

Use the installed `hypervector` command or `.venv/bin/python -m hypervector`.
Read `README.md` for the command groups and installation options. Current
acceptance is in `docs/guides/acceptance-visual-and-holistic.md`; its retained
filename is a compatibility link, and its current procedure is headless.

## Authority and truth

- Default execution is paper/shadow. These paths cannot submit venue orders.
- Live operation requires explicit `--enabled --i-accept-live-risk`, valid
  configuration/evidence, credentials, reconciliation and pre-start backup.
  A documented live command does not authorize running it.
- Retain STOP markers. Never print wallet or API secret values.
- Mainnet only. No neural-trader. No implicit performance or drawdown gates.
  Technical failures are errors; weak trials remain measured results.
- Develop execution changes in an isolated checkout and venv. Do not run
  `uv run` or `uv sync` in an armed checkout. Merge/restart only at an approved
  transition boundary.
- Historical profiles do not establish the active deployment. Select the
  exact `--config`; signed approvals and journals are immutable evidence.

## Discovery and data scope

```sh
hypervector --help
hypervector status
hypervector system status --probe-model
hypervector research --help
hypervector --data-root scratch data history --symbol BTC --lookback 30
```

`status` observes installed capabilities and creates no data directory. It
cannot establish venue readiness or profitability. Model probing is explicit;
`--data-root` scopes discovery unless a model-root environment override was
explicitly configured. Cohort configuration paths remain profile-bound.

## Research pipeline

```sh
hypervector research backtest --strategy crown_stack_long --symbol BTC --timeframe 5m --lookback 30
hypervector research autotune --strategy crown_stack_long --sampler karpathy --n-trials 100
hypervector research sweep-up --lookback 30 --export
hypervector research export-validate --path data/exports/example --strict
hypervector nautilus run --path data/exports/example --no-network
hypervector model train --path data/exports/example
```

VectorBT, its Rust accelerator and TA-Lib indicators remain required.
Nautilus is the event-driven historical engine. Karpathy is the default
optimizer. Explicit Optuna/hybrid selection requires `hypervector[optuna]`;
missing dependencies cause a technical error rather than a sampler change.
Other VectorBT adapters are available through `hypervector[integrations]`.
Nautilus `--no-network` requires compatible cached history.

## Hyperliquid and 0xArchive

```sh
hypervector data funding-fetch --help
hypervector data book-record --help
hypervector archive candle-fetch --help
hypervector archive book-fetch --help
hypervector archive trade-fetch --help
hypervector archive price-fetch --help
hypervector archive liquidation-fetch --help
hypervector research db-build --help
```

Acquisition is bounded by explicit timestamps and page limits. Preserve
source provenance, namespaced HIP-3 identities and vendor artifacts. DuckDB
is analytical storage rather than execution authority.

## Paper and cohort services

```sh
hypervector paper run --path data/exports/example --mode shadow
hypervector paper shadow-run --config configs/hypervelocity_faithful.toml
hypervector paper report --last 5
hypervector cohort observe --config profile.toml --ledger-root data/paper/cohort
hypervector cohort dependencies --config profile.toml
hypervector cohort checkpoint --config profile.toml --once --current-run-only
hypervector cohort monitor --config profile.toml --follow
hypervector cohort audit --run-id RUN_ID --out-dir data/logs/cohort-audits
hypervector cohort request --help
```

Monitoring owns no backend. `--out` may publish an independent checkpoint
bound to the shared run/profile and accounting epoch. Optional services stop
only processes they own. Shadow reset is a dry run without `--yes` and retains
recoverable backups when confirmed.

`cohort request` supports manual entry, close, transition drain and profile
staging. Default output is a validated dry run. Publication needs `--submit`;
live-affecting requests also need both authority flags. Publication is not
proof of backend acceptance or venue execution.

Non-visual flat aliases remain, including `cohort-live-audit-delta`. Audit
comparisons distinguish resolved execution, provisional open-lifecycle state,
and known technical-gap growth. These reports have execution_authority=none.

## Verification

```sh
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile
.venv/bin/python -m pytest tests/ -q -m evidence
.venv/bin/python -m pytest tests/ -q -m integration
```

Unit tests forbid network access and use temporary data. Historical evidence
and external-provider checks are explicit opt-ins, not fabricated fixtures.
The Rust TUI and its Cargo workspace have been retired; use JSON telemetry
and the unified CLI. Historical transition runbooks remain archival evidence.
