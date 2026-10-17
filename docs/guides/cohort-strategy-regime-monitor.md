# Cohort strategy and regime monitoring

Monitoring reads the checkpoint that the live backend's checkpoint writer
publishes. Select the exact profile and run you mean.

```sh
.venv/bin/python -m hypervector live monitor --help
.venv/bin/python -m hypervector live monitor \
  --config configs/multi_asset_growth_first_5000_review_fixes_v95.toml \
  --source-checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --run-id RUN_ID --follow
```

- **Defaults.** `--source-checkpoint` defaults to
  `<data-root>/runtime/bidirectional_cohort/latest_checkpoint.json`.
- **Validation.** The monitor checks run and profile identity and freshness
  (`--maximum-age-seconds`, default 90). Incompatible, stale or malformed
  evidence fails explicitly.
- **Ownership.** It owns no backend, and ending it leaves the backend alone.
- **Limits.** It cannot recover fresh venue state from an old checkpoint.

To publish an independent report, choose a separate output path:

```sh
.venv/bin/python -m hypervector live monitor --config <profile.toml> \
  --source-checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --run-id RUN_ID --out independent.json
```

`--out` rebuilds the report from the selected shared evidence and accounting
epoch. Never point two checkpoint writers at the same output.

When no shared checkpoint is being published, start a reporter with
`live checkpoint`. Give it the profile, the ledger and the run explicitly:

```sh
.venv/bin/python -m hypervector live checkpoint --config <profile.toml> \
  --ledger-root data/live/bidirectional_cohort --run-id RUN_ID --once
```

`live checkpoint` is bound to the selected run by default. Its optional venue
portfolio and research-database sync (`--venue-portfolio`,
`--research-database`) have their own I/O needs.

## What to inspect

- the provider, asset and direction;
- the source timestamps and recorded indicators;
- the configured sizing;
- position and protection evidence;
- the accounting identity.

Strategy evidence at a decision and the latest recorded regime context can have
different ages. Missing evidence stays unavailable. Regime strength and
prerequisite completion are diagnostics, not win probabilities. See
`skills/hypervector-regime-detector/SKILL.md` for the regime rules.

The supervisor and the live backend have separate lifecycles. See
`live supervisor --help` and the
[transition guide](cohort-live-transition-and-rollback.md) for ownership and
restart. No monitor command authorizes a live start.

## Validation

```sh
.venv/bin/python -m pytest tests/test_headless_monitor_cli.py tests/test_incremental_monitor_identity.py tests/test_cohort_monitor_stale_attachment.py tests/test_monitor_validation_edges.py -q
```

Any of these would break the contract:

- accepting the wrong run or profile;
- cross-epoch accounting;
- a stale attachment accepted as fresh;
- monitoring that restarts execution.
