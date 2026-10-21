# Hypervector: current state

## What it is

Hypervector is a headless Python CLI for Hyperliquid mainnet, run as
`.venv/bin/python -m hypervector`. It covers market data and 0xArchive
evidence, VectorBT/TA-Lib backtests and sweeps, Karpathy (or Optuna) tuning
with a chronological holdout, strict strategy bundles, NautilusTrader
validation, walk-forward metalabel models, paper/shadow trading, and the
double-armed live cohort backend with its transition and supervision tooling.

The operator tools are packaged in `hypervector.operations` and
`hypervector_supervision`; the `scripts/` files are shims or launchd entry
points. The installed launchd plists run
`scripts/multi_asset_bidirectional_live.py`,
`scripts/cohort_backend_supervisor.py` and
`scripts/multi_asset_bidirectional_live_checkpoint.py`; keep those three
unchanged.

The operator keeps no old records. Documents describe the current system only.

## Clean slate: no profiles

The repository holds no live, rollback or Hypervelocity runtime profile and no
strategy evidence. `configs/` contains only `default.toml` (research defaults).
Every earlier profile version, approval, review and plan was removed because
those strategies failed, and new profiles must start without reference to them.
The code that encoded their results went with them: the per-route evidence
table, the modeled friction contracts, version-specific acceptance checks, the
exit-continuation model and the single-strategy audit studies.

What stays is capability:

- **Building blocks.** The live strategy providers (`src/hypervector/live/*_provider.py`
  and the SOL, Hulk and source-follow engines) and the research signal builders
  (`src/hypervector/strategies/`, `src/hypervector/research/*_signals.py`)
  remain. A new profile composes them or adds new ones.
- **Provider validators check capability only.** A new profile can reuse a
  provider with its own stop, target, hold, entry delay, execution symbols,
  execution sides and exit-policy combination. The per-provider validators
  (`multi_asset_live_provider_validation.py`,
  `multi_asset_special_provider_validation.py`,
  `fixed_route_provider_validation.py`, `hourly_price_contract.py`,
  `multi_asset_route_contract_validation.py`) refuse only what the signal
  cannot compute or bind. That covers the symbols it evaluates, its signal
  timeframe, the sides it emits, the position policy it implements, and
  observer-only scope. It also covers the anchors its intents carry: a
  structural stop needs a stop anchor, and SPCX cash-open needs its absolute
  target. The generic loader and `live validate` still bound every value
  (taker IOC only, sizing ceilings, stop inside liquidation, STOP beside the
  ledger, authority flags). The operator approved this change on 2026-10-20
  and it is on `main`.
- **Profile schema.** `src/hypervector/live/multi_asset_live_config.py` and
  `multi_asset_live_config_parsing.py` define the cohort profile. The profiles
  under `tests/fixtures/` copy retired profiles' values for the tests; never use
  them as a template or starting point.
- **Hypervelocity shadow.** `paper shadow` now requires `--config`. The Python
  contract in `src/hypervector/strategies/hypervelocity_contract.py` is
  authoritative.
- **Evidence registries.** `_EVIDENCE` in
  `src/hypervector/live/multi_asset_strategy_evidence.py` and `_MODELED` in
  `src/hypervector/research/cohort_friction_contracts.py` are empty. Every
  route reports `unreviewed_exact_mapping` and friction parity reports
  `modeled_contract_missing` until reviewed research for a new profile is
  registered there. Both are report-only.
- **Offline checks for a new profile.** `live check`, `live validate --mode
  live --equity <USD>`, `live preflight`, `live backup` and, for a later change,
  `live rollback-profile`. None of them needs authority.

## Current CLI

13 groups. Pillars: `data`, `archive`, `backtest`, `tune`, `nautilus`, `paper`,
`live`, `regime`, `model`. Supporting: `export`, `db`, `pipeline`, `system`.
`<group> --help` and `<group> <command> --help` are authoritative; `README.md`
holds the group table, output contract, exit codes and legacy-name map, and
`skills/hypervector-cli/SKILL.md` is the operating guide.

- **Arming.** Only `live start` (the cohort) and `live run` (the generic daemon)
  arm, and both need `--enabled --i-accept-live-risk`, as does
  `live supervisor resume --yes`.
- **Pipeline.** `pipeline run` is one foreground pass from data to the paper
  hand-off, writes `runs/pipeline/<id>/pipeline.json` and never touches `live`.
- **Nautilus** models BTC, ETH, SOL and HYPE built in, and other perps through
  the bundle's `meta.instrument`; the pipeline skips it for any other symbol.
- **Data and fees.** History loads in `data history`, `data book-align`,
  `backtest run/sweep`, `tune strategy/regime` and the `regime` commands report
  provenance and take `--pin-cache`, `--max-cache-age-hours` and `--refresh`.
  `pipeline run` takes `--refresh` and `--no-network`, and only its data stage
  fetches. `nautilus run` takes `--no-network`. `paper run` and `model train`
  take neither; they use `--lookback-days` and the export bundle's window. The
  default fee model is `hl_base_taker`.
- **Old names** still parse as hidden aliases; retired ones exit 2 and name the
  replacement.

## Trading state: STOPPED

- **Venue.** Flat with no open orders at the 2026-10-06 shutdown, confirmed by
  unsigned core and `xyz` reads.
- **STOP file.** Absent (removed 2026-10-18 at the operator's request). To
  restore a durable stop, write a one-line reason to
  `data/live/bidirectional_cohort/STOP`.
- **launchd.** `local.hypervector.cohort.supervise`, `.checkpoint`, `.watch`
  and `local.hypervector.research.roster_observer` are disabled and unloaded.
  The installed supervise and checkpoint plists still pass the deleted
  profile's path, so they cannot start anything. For a new profile, copy them
  and edit only the `--config` arguments, as "Profile-only rollback" in
  `docs/guides/cohort-live-transition-and-rollback.md` describes.
- **`data/` holds market data only.** `data/cache/` and the research
  databases under `data/research/` (`market.duckdb`, `hip3_market.duckdb`,
  `live_event_research.duckdb`, `hip3_asset_context/`) remain; their old-run
  tables (cohort events and sources, shadow ledger events, portfolio revisions)
  are empty. Every old run's ledgers, drain marker, backups, logs, checkpoints,
  exports, models, sweep board and paper/observer runs were moved to
  `~/.Trash/hypervector-cleanup-20261019/` on 2026-10-19.
- **The ledger root `data/live/bidirectional_cohort/` is empty.** The first
  start of a new profile has no previous identity, so it needs no approval and
  no drain archive. The engine hardcodes this root (supervisor, process lock,
  SOL ledger checks); profiles must keep `cohort_ledger` and `stop_file` in it.
- **Provider dependency.** Live start and validation need the external provider
  package at `../backtest-lab/backtest_lab`.

## Open items

- **The engine API wallet `hl-api` expires 2026-10-22T12:59:22Z.** Before any
  armed start, the operator approves a new API wallet under a different name
  (for example `hl-api-2`) and puts its key in `.env`. Never re-approve the
  name `hl-api`: that de-registers the signer at once. After expiry, every
  armed start is refused.
- **Breakout-filter telemetry labels.** The ETH breakout-transfer and HYPE
  compression collectors still publish their original stop and hold (60 bps
  and 12 h; 80 bps and 8 h to 24 h) in readiness metrics and the `EXIT ... STOP`
  indicator, whatever the profile sets. Only the telemetry is affected; the
  bound execution plan uses the profile's values.
- **HIP-3 settlement or halt.** A venue settlement or halt of an open HIP-3
  (`xyz:`) position faults the whole backend, and the restart is then refused.
  While live, watch the venue notices and send `live request --action
  manual_close` before a settlement window.
- **Checkpoint cost.** Checkpoint publication cost grows with run age. On a
  long run, watch `live monitor` freshness. A same-profile restart at a flat
  window resets it.
- **Free disk.** The supervisor alerts below about 14 GiB free and treats less
  than 10 GiB as a problem. 156 GiB were free on 2026-10-19 while the cleanup
  folder (about 108 GB: old run data and the old worktrees) still sat in the
  Trash; emptying the Trash is the operator's call. The largest remaining
  consumers are `data/cache/` and the research databases.
- **Checkpoint flags.** The asymmetric-forward observer and
  `--eligible-policy-forward` remain in `live checkpoint`; the backend's
  checkpoint command always passes `--disable-asymmetric-forward-observer`.
- **Local strategy notes.** `docs/external/` (git-ignored) still holds the
  manual-position and creator-recipe research inputs behind the removed
  strategies.

## How to verify

```bash
.venv/bin/python -m pytest tests/ -q -n 6 --dist loadfile
.venv/bin/python -m pytest tests/ -q -m "integration and not network"
.venv/bin/python -m hypervector status
```

`--help` must stay under 0.07 s.

## Last verified state

`main` with the capability-only provider validators, 2026-10-20:

- Default suite: 7,676 passed, 0 failed (`-n 6`, about 58 s).
  `tests/test_provider_execution_reuse.py` loads every provider family that has
  a dedicated validator with new execution values, runs a `profile_b.toml`
  variant with new sweep, Donchian and ETH-range exits through `live validate`
  (exit 0), and keeps each technical refusal.
- `-m "integration and not network" --ignore=tests/test_install.py`: 7 passed.
  `-m network` was not run.
- `--help` 0.05 s; `status` and `export list` exit 0.
- `live check --config tests/fixtures/cohort_chain/profile_b.toml` reports only
  the two authority flags as blockers (no STOP file, no drain marker).
  `live validate --mode live --equity 4796` exits 0 on that profile, `live
  rollback-profile --verify` accepts the fixture rollback pair, and an unarmed
  `live start` refuses (exit 2).
- Three recorded fixtures under `tests/fixtures/native_runner_cold_warm_20260911/`
  still name an old evidence path; their bytes are sha256-pinned by its
  `manifest.json`.
