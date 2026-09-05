# V58 SPCX technical-repair same-profile restart

## Status and authority

This procedure is prepared but not authorized. It may begin only after the
operator gives this exact approval:

`APPROVE TRANSITION DRAIN AND VERIFIED V58 CORRECTED CUTOVER`

The approval authorizes an entry drain followed by one verified, same-profile
implementation restart. It does not authorize an immediate close, a strategy
retune, or an accounting reset. Automatic restart is prohibited.

The active identity is:

- run: `bidirectional-live-1787272893887`;
- profile: `multi_asset_growth_first_5000_eight_asset_incremental_v58`;
- fingerprint: `8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b`;
- config: `configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml`;
- accounting epoch:
  `data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r2`.

No configuration change is included. No strategy, side, exit, sizing, leverage,
or risk change is authorized. No retroactive SPCX entry is permitted. The only
loaded-behavior change is the already-regressed, session-aware SPCX source and
seven-day action-free readiness seed described in
`docs/research-journal/v58-spcx-active-runtime-drift-flat-cutover-20260821-v1.json`.

## Accounting invariant

This is a same-profile implementation restart and must reuse the existing V58
accounting epoch:

`data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r2`

The restart must not reset CURRENT RUN or ALL-TIME metrics. Do not run
`scripts/cohort_accounting_rollover.py`, create another V58 epoch, delete or
truncate a ledger, reset a provider cursor, or relabel observer evidence as
live evidence. The BRENTOIL and SP500 closes from the active process and every
later V58 close remain in epoch `r2`.

## Pre-boundary validation

Before approval or drain activation, require a fresh checkpoint with the exact
run/profile/fingerprint, `running_consistent`, zero faults, and venue-native
protection for every open position. Do not restart while BRENTOIL or SP500 is
open.

Re-run the bounded repair and deployment checks against the final worktree:

```bash
uv run pytest -q \
  tests/test_hip3_cash_open_trade_source.py \
  tests/test_hip3_cash_open_gap_provider.py \
  tests/test_hip3_cash_open_gap_reversal_signals.py \
  tests/test_hip3_cash_open_prospective.py \
  tests/test_multi_asset_readiness_seed.py \
  tests/test_multi_asset_bidirectional_observe_script.py \
  tests/test_v58_live_backend_context.py \
  tests/test_v58_spcx_technical_repair_restart_runbook.py

uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
git diff --check
```

Any failure blocks cutover. Passing tests validate mechanics, not SPCX
profitability.

## Approval-gated transition drain

After the exact approval, attach the current read-only cockpit without
restarting the backend:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --refresh-ms 1000
```

On Screen 7 select `TRANSITION DRAIN`, inspect the exact run and profile, press
Enter, and confirm with `y`. Require the backend acknowledgement and a fresh
checkpoint reporting the drain `active` for run
`bidirectional-live-1787272893887`. From activation onward:

- flat symbols must not open a new position;
- BRENTOIL and SP500 retain their exact stops and bound exits;
- no position is force-closed by this deployment procedure;
- no post-activation entry is accepted.

If the request is rejected, bound to another run, or followed by missing
protection, stop the procedure and investigate. Do not create a second request.

## Terminal boundary and immutable audit

The backend completes the drain and stops only after all eight assets are flat
and zero owned entry, stop, target, and close orders remain. Independently
verify the final venue state, every asset ledger, the cohort ledger, and the
latest checkpoint. A ledger-only flat result is insufficient.

Publish one immutable stopped-run audit to a new path:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --run-id bidirectional-live-1787272893887 \
  --out data/logs/research/bidirectional_cohort/v58_spcx_repair_pre_restart_audit_<UTCSTAMP>.json
```

Require complete lifecycle coverage, both final closes, zero open positions,
zero owned orders, zero faults, and the completed drain. Then stop the old
checkpoint writer normally from its owning `hypervector-v58-checkpoint`
terminal and prove that no old live backend or checkpoint writer remains:

```bash
ps -axo pid,ppid,etime,command | \
  rg 'multi_asset_bidirectional_live.py|multi_asset_bidirectional_live_checkpoint.py'
```

Any old matching process blocks restart.

Preview and then archive the completed drain marker. Inspect the preview before
using `--yes`:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1787272893887

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1787272893887 \
  --yes
```

Require byte-identical archive verification and absence of the live
`transition_drain.json` marker before attempting startup.

## Fresh flat preflight and implementation bundle

Generate a collision-free preflight from the final stopped checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --active-config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v58_spcx_repair_flat_preflight_<UTCSTAMP>.json
```

Require exit zero, `flat_no_orders=true`, `ledger_reconciled=true`,
`open_positions=0`, `open_orders=0`, all eight assets, the exact fingerprint,
and unchanged fee, leverage, sizing, route, and exit contracts.

Create and independently verify a new complete-source bundle:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab

uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <V58_CORRECTED_PRESTART_BUNDLE>
```

Require a nonzero implementation file count, exact profile/fingerprint, a
nonempty implementation SHA-256, and independent verification. The live
launcher must create the same implementation identity in its mandatory startup
bundle; a mismatch blocks acceptance.

## Explicit same-profile live start

Start exactly one supervisor with the existing epoch and both live-risk flags:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r2 \
  --startup-timeout-seconds 600 \
  --refresh-ms 1000 \
  --enabled --i-accept-live-risk
```

The first checkpoint must have a new run ID with the same profile,
fingerprint, and `r2` epoch. Startup must adopt zero positions and zero orders.
The initial SPCX projection must be an action-free readiness seed; it must not
replay the historical 2026-08-18 signal.

## Post-start acceptance

After all ten provider-symbol routes emit a new-run evaluation, publish a new
immutable acceptance report:

```bash
uv run python scripts/v58_poststart_acceptance.py \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --stress data/logs/research/bidirectional_cohort/v58_eight_asset_growth_sizing_stress_20260819_v1.json \
  --preflight data/logs/research/bidirectional_cohort/v58_spcx_repair_flat_preflight_<UTCSTAMP>.json \
  --out data/logs/research/bidirectional_cohort/v58_spcx_repair_poststart_acceptance_<UTCSTAMP>.json
```

Require `accepted=true`, a fresh healthy checkpoint, exact eight-asset and
ten-route coverage, zero inherited lifecycle, unchanged fourteen direction
scopes, unchanged exits and risk, no unknown order, and protection for any
legitimate new position. SPCX must no longer remain indefinitely blocked by
`cash_open_trade_bars_incomplete`; any unresolved opening or prior-close gap
must still fail closed.

An attach-only monitor after supervisor detachment is:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r2 \
  --refresh-ms 1000
```

Verify all nine TUI screens, current backend freshness, the new run identity,
continuous epoch metrics, source readiness, open protection, and complete data.

## Failure modes and rollback

Abort before start on any non-flat venue position, any owned or unknown order,
drain archive failure, ledger mismatch, profile or implementation mismatch,
test failure, incomplete bundle, stale checkpoint, or old process. After start,
any retroactive SPCX intent, duplicate or stale cursor, unexpected order,
inherited lifecycle, missing route, changed exit/risk setting, checkpoint fault,
or TUI identity mismatch is a failed cutover.

Do not start a second backend to recover a failed first start. Preserve the
ledger and startup bundle, reconcile venue state, and stop normally. Rollback
to the sealed implementation is permitted only at another verified flat and
order-free boundary and requires renewed explicit approval.

Confidence is high in the diagnosed source defect and local regression suite,
medium-high in the flat-boundary restart mechanics, and unverified for the
first genuine post-restart cash-open decision. Any failed boundary predicate or
post-start acceptance updates that assessment and blocks a success claim.
