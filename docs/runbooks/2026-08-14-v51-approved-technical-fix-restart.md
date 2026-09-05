# v51 approved technical-fix same-profile restart

## Scope and authority

This procedure continues the first live v51 trial after deploying only:

- `V51_ENTRY_FRESHNESS_AT_SUBMISSION_V1`
- `V51_CROSS_NAMESPACE_EXPOSURE_TELEMETRY_V1`
- `V51_OPPOSITE_EXIT_PRECEDENCE_V1`
- `V51_REQUIRED_INDEX_OBSERVER_STARTUP_GUARD_V1`

Human approval is recorded in
`docs/research-journal/v51-approved-technical-fixes-flat-boundary-v1.json` and
`docs/research-journal/v51-opposite-exit-precedence-v1.json`. The latter binds
the operator-approved requirement that an eligible executable opposite intent
closes an open position before any competing same-direction intent; it does not
admit stale, observe-only, or otherwise ineligible evidence.
The exact profile is
`multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51`, fingerprint
`30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908`.

No strategy or risk configuration changes are authorized. Entries, exits,
assets, leverage, sizing, stops, targets, and maximum holds remain unchanged.
Let the current HYPE lifecycle reach an authoritative configured exit; do not
manually close HYPE for this deployment. Automatic restart is prohibited.

## Accounting invariant

This is a same-profile implementation restart, not a new trading epoch; reuse the existing accounting epoch:

`data/backups/bidirectional_cohort/accounting_epochs/v51_first_live_f9ab743_2030`

The restart must not reset CURRENT RUN or ALL-TIME metrics. Do not run
`scripts/cohort_accounting_rollover.py`, create another `v51_first_live` epoch,
delete ledgers, truncate journals, or reset observer cursors. The final close
from the current process and every later close remain in the same epoch.

## Pre-boundary verification

Before the position becomes flat, verify the staged implementation without
changing the active process:

```bash
uv run pytest -q \
  tests/test_bidirectional_intents.py \
  tests/test_multi_asset_entry_submission_freshness.py \
  tests/test_multi_asset_shared_account_facts.py \
  tests/test_multi_asset_live_runner.py \
  tests/test_multi_asset_live_runner_transient.py \
  tests/test_v51_technical_fix_restart_runbook.py \
  -m "not network"

uv run ruff check \
  src/hypervector/live/bidirectional_intents.py \
  src/hypervector/live/cohort_entry_submission.py \
  src/hypervector/live/multi_asset_live_runner.py \
  src/hypervector/live/multi_asset_live_runner_support.py \
  tests/test_multi_asset_entry_submission_freshness.py \
  tests/test_multi_asset_shared_account_facts.py

git diff --check
```

A failure stops the deployment. Passing tests validate the bounded mechanics;
they do not establish strategy profitability.

## Flat and order-free boundary

Proceed only when a fresh checkpoint and the venue independently show all six venue positions are flat and zero cohort-owned entry, stop, target, and close
orders remain. The HYPE close must already be reflected in its asset ledger,
cohort ledger, trade reflection, current-run performance, and accounting epoch.

At that boundary:

1. Exit the supervising TUI normally with `q`. Its `finally` path requests an
   orderly backend stop, waits for the backend, publishes the final checkpoint,
   and invokes `scripts/multi_asset_bidirectional_live_audit.py`.
2. Stop the separately supervised checkpoint writer normally from its owning
   terminal. Do not terminate it before the final stopped checkpoint exists.
3. Verify the TUI supervisor, backend, and checkpoint writer have exited. If
   any remain, do not start another backend.
4. Inspect the immutable stopped-run audit and require complete lifecycle
   coverage, the HYPE close, no open positions, and no owned orders.

```bash
ps -axo pid,ppid,etime,command | \
  rg 'multi_asset_bidirectional_canary_tui|multi_asset_bidirectional_live.py|multi_asset_bidirectional_live_checkpoint.py'
```

Any matching active v51 process blocks startup. Do not rerun
`scripts/multi_asset_bidirectional_live_audit.py` if the supervisor already
published the immutable audit for that run ID; verify that artifact instead.

## Required index-source observers

The SP500 and SPCX fresh15 v3 providers are executable only from their exact
prospective journals. Start both unsigned, order-incapable observers from
separate supervised terminals before generating the fresh preflight:

```bash
uv run python scripts/index_hip3_breakout_shadow_observe.py \
  --symbol xyz:SP500

uv run python scripts/index_hip3_breakout_shadow_observe.py \
  --symbol xyz:SPCX
```

Do not delete or reset either cursor. Wait for both status files, cursors, and
decision journals to advance coherently from their preserved boundaries. Any
`observer_status_stale`, identity disagreement, duplicate decision, or missing
prior prospective state blocks preflight and live startup. The launcher guard
rechecks both observer identities and freshness immediately before it creates
the backend process; it does not grant the observers execution authority.

## Fresh same-profile preflight and backup

Choose one collision-free `<UTCSTAMP>` and use it consistently. Generate a
public-wallet-only v51-to-v51 preflight from the final stopped checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --active-config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v51_technical_fix_restart_flat_preflight_<UTCSTAMP>.json
```

Require exit zero and exact report fields `flat_no_orders=true`,
`ledger_reconciled=true`, `open_positions=0`, and `open_orders=0`. Then create
and independently verify the implementation backup:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab

uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <BUNDLE_FROM_PREVIOUS_JSON>
```

Require the exact v51 profile/fingerprint and implementation hash. The live
launcher will also create and verify its mandatory prestart backup; disagreement
between the two backups is a technical failure.

## Explicitly armed same-profile start

Only after every prior check passes, start exactly one backend with the existing
epoch and both human-risk flags:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v51_first_live_f9ab743_2030 \
  --startup-timeout-seconds 600 \
  --enabled \
  --i-accept-live-risk
```

Do not launch a second checkpoint writer if the supervisor already owns one.
The first new checkpoint must have a new run ID but the same v51 profile,
fingerprint, and accounting epoch.

## Post-start acceptance

Wait for all six asset ledgers to advance under the new run. In the TUI verify:

- live backend and checkpoint heartbeat are current;
- six exact assets and seven provider-symbol routes are visible;
- current-run and all-time counts continue the existing epoch;
- no stale-runtime, disconnected-backend, or missing-data panel is present;
- every open position, if one appears, has its venue stop and bound exit plan;
- entry submission age and cross-namespace exposure telemetry are populated.
- the implementation identity contains the approved opposite-exit-precedence
  source revision; the first attributable eligible conflict, when one occurs,
  must close exactly once without a same-cycle reversal.

Publish immutable technical acceptance using the boundary preflight:

```bash
uv run python scripts/v51_poststart_acceptance.py \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --preflight data/logs/research/bidirectional_cohort/v51_technical_fix_restart_flat_preflight_<UTCSTAMP>.json \
  --out data/logs/research/bidirectional_cohort/v51_technical_fix_poststart_acceptance_<UTCSTAMP>.json
```

Acceptance must return zero and report `accepted=true`. Any identity mismatch,
stale checkpoint, missing route, unprotected position, accounting discontinuity,
missing technical-fix telemetry, or venue/ledger disagreement is a failed
deployment. Stop normally; rollback is allowed only at another verified flat
and order-free boundary.

## Confidence and update conditions

Confidence is high that this procedure preserves the exact profile and epoch
because those identities are machine-checked and all three technical changes have
focused tests. The opposite-exit precedence also has an exact loaded-versus-
current router falsifier and focused regression, but its live effect remains
provisional until an attributable conflict occurs. Confidence in live behavior
remains provisional until the new run produces fresh telemetry and the
post-start report accepts. A failed
boundary predicate, backup mismatch, rejected acceptance report, duplicate
process, missing HYPE close, or changed profile fingerprint falsifies readiness
and requires investigation before another start.
