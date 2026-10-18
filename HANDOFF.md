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
points. Three are sha-pinned and must not change:
`scripts/multi_asset_bidirectional_live.py`,
`scripts/cohort_backend_supervisor.py` and
`scripts/multi_asset_bidirectional_live_checkpoint.py`.

The operator keeps no old records. Documents describe the current system only,
and earlier text is recoverable from the tag `pre-history-purge-20261017`.

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

- **Backend.** The cohort backend is stopped. At shutdown the venue was flat
  with no open orders, confirmed by fresh unsigned core and `xyz` reads.
  Shutdown evidence:
  `data/backups/bidirectional_cohort/operator_shutdown_20261006T173755Z/`.
- **STOP file.** Removed on 2026-10-18 at the operator's request. Its text
  was "Operator-requested shutdown after verified flat drain.
  2026-10-06T17:46:51.998054+00:00". A start is still blocked by the disabled
  launchd agents, the drain marker below and the two authority flags. To
  restore the durable stop, write a one-line reason to
  `data/live/bidirectional_cohort/STOP`.
- **Drain marker.** A completed transition-drain marker is present:
  `data/live/bidirectional_cohort/transition_drain.json`. Its `status` is
  `completed`, its `run_id` is `bidirectional-live-1791308294404` and its
  profile fingerprint is V95's. It blocks the next start until
  `live drain-archive --yes` archives it.
- **launchd.** The agents `local.hypervector.cohort.supervise`, `.checkpoint`
  and `.watch`, and `local.hypervector.research.roster_observer`, are disabled
  and unloaded, and their processes are absent. The installed supervise plist is
  the original V95 one.
- **V95 stays restartable.** These files are unchanged and must stay
  byte-identical while the profiles are kept:
  - V95: `configs/multi_asset_growth_first_5000_review_fixes_v95.toml`,
    fingerprint
    `dd779cce74568e4ba6963d1a19810a7fbcaa7f4279e40f45be83f12286339420`;
  - V94: `configs/multi_asset_growth_first_5000_review_actions_v94.toml`
    (`930117e9…`);
  - rollback: `configs/v95-to-v94-rollback-20260927-v1.toml` (`5fe5a9de…`);
  - the three approvals under `docs/live-approvals/`;
  - the documents they hash-bind under `docs/reviews/` and `docs/plans/`.
- **Restart needs an explicit operator instruction.** The implementation
  identity changed (the CLI rework touched `src/`), so the start records a new
  pre-start bundle. That bundle differs from the last verified one,
  `prestart_20261006T173814.404290Z_dd779cce7456`. A same-profile restart needs
  no new profile-change approval. Nothing in this checkout restarts, arms or
  kickstarts anything.
- **Provider dependency.** Live start and validation need the external provider
  package at `../backtest-lab/backtest_lab`.

## Rehearse a V95 restart offline

None of this needs authority, and nothing starts.

```bash
HV=".venv/bin/python -m hypervector"
V95=configs/multi_asset_growth_first_5000_review_fixes_v95.toml
$HV live check --config "$V95"
$HV live validate --config "$V95" --mode live --equity <USD>
$HV live backup --config "$V95"
$HV live backup-verify --bundle <path printed by live backup>
$HV live drain-archive --expected-run-id bidirectional-live-1791308294404      # preview only
$HV live rollback-profile --current "$V95" --verify configs/v95-to-v94-rollback-20260927-v1.toml
```

Expected results:

- **`live check`** exits 1. Its blockers are exactly the two authority flags
  and the drain marker. The profile loads in observe mode with
  the V95 fingerprint, and provider dependencies are ok.
- **`live validate`** exits 0. Exit 3 is a report-only book-level advisory.
- **`live backup`** reports `status=verified`, `execution_authority=none` and
  `strategy_changed_from_latest_ledger=false`, with a nonzero implementation
  file count. `live backup-verify` then reports `status=verified`.
- **The `drain-archive` preview** names the completed marker and its archive
  destination.

## The restart itself (operator only)

On an explicit instruction, follow "Same-profile restart from a stopped book"
in `docs/guides/cohort-live-transition-and-rollback.md`:

1. `live drain-archive --expected-run-id bidirectional-live-1791308294404 --yes`.
2. Confirm the STOP file is absent (it was removed on 2026-10-18).
3. Publish one checkpoint with `--no-current-run-only --venue-portfolio` and
   require the flat predicate.
4. Start V95 by enabling and bootstrapping the supervise agent, or with
   `live start --config "$V95" --enabled --i-accept-live-risk`.
5. Run `live backup-verify` on the new pre-start bundle printed in the backend
   log.
6. Accept with `live monitor --follow` and `live audit`.

Re-enable the checkpoint, watch and roster agents with the supervise agent.

## How to verify

```bash
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile
.venv/bin/python -m pytest tests/ -q -m "integration and not network"
shasum -a 256 scripts/multi_asset_bidirectional_live.py scripts/cohort_backend_supervisor.py scripts/multi_asset_bidirectional_live_checkpoint.py
.venv/bin/python -m hypervector status
```

`tests/test_v95_restartability.py` pins the profile fingerprints, the script
hashes and the plist argument lists. `--help` must stay under 0.07 s.

## Last verified state

Branch `agent/unified-cli-cleanup-20261017` (checked out here; `main` is still
at `f95f36a`, and the pre-purge tree is tag `pre-history-purge-20261017`):

- Default suite: 7,891 passed, 0 failed (`-n 6`, about 110 s).
- `-m "integration and not network" --ignore=tests/test_install.py`: 7 passed.
  `tests/test_install.py`'s integration cases need the `integrations` extra,
  which is not installed here.
- `-m network` (public Hyperliquid/Binance/Bybit reads): 4 passed.
- A wheel built from a clean export installed into a throwaway venv ran
  `status`, `backtest run`, `tune strategy`, `export list/validate`,
  `nautilus run --no-network`, an offline `pipeline run` through the paper
  hand-off and `regime classify`; `live run` and `live start` refused (exit 2)
  without both authority flags.
- V95 rehearsal: `live check` showed the V95 fingerprint with exactly the
  expected blockers (after the STOP removal: the authority flags and the drain
  marker); `live validate
  --mode live --equity 4796` exited 0 with no problems.
- Startup: `--help` and every group help 0.06 s with no engine imports.
  Against the pre-purge tree: 96-trial sweep 15.5 s → 3.4 s, 2,161-bar
  Nautilus run 14.8 s → 1.4 s, 200k-row paper report 2.3 s / 260 MB → 1.3 s /
  28 MB, 100-trial tune 6.6 s → 5.2 s.

## Open items

- **The engine API wallet `hl-api` expires 2026-10-22T12:59:22Z.** Before any
  restart, the operator approves a new API wallet under a different name (for
  example `hl-api-2`) and puts its key in `.env`. Never re-approve the name
  `hl-api`: that de-registers the signer at once. After expiry, every armed
  start is refused.
- **HIP-3 settlement or halt.** A venue settlement or halt of an open HIP-3
  (`xyz:`) position faults the whole backend, and the restart is then refused.
  This is unfixed. While live, watch the venue notices and send
  `live request --action manual_close` before a settlement window.
- **Checkpoint cost.** Checkpoint publication cost grows with run age, which is
  also unfixed. On a long run, watch `live monitor` freshness. A same-profile
  restart at a flat window resets it.
- **Free disk.** The supervisor alerts below about 14 GiB free and treats less
  than 10 GiB as a problem. Large consumers are `data/backups/` and the research
  stores. Reclaiming space is the operator's call.
- **Checkpoint flags.** The asymmetric-forward observer and
  `--eligible-policy-forward` stay in `live checkpoint` because the installed
  checkpoint plist passes `--disable-asymmetric-forward-observer`. Removing them
  needs a plist edit at an authorized boundary.
- **Merge boundary.** This CLI lands on `main` in the armed checkout only at an
  approved boundary. Merging does not authorize a restart.
