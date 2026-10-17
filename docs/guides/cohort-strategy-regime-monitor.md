# Cohort strategy and regime monitoring

Use backend-authored JSON through the unified CLI. Select the exact profile and
checkpoint for the intended run; the former terminal renderer is retired.

```sh
.venv/bin/python -m hypervector cohort monitor --help
.venv/bin/python -m hypervector cohort monitor --config profile.toml \
  --source-checkpoint snapshot.json --run-id RUN_ID --follow
```

The monitor validates shared run/profile identity and freshness. It owns no
financial backend. Ending the monitor leaves a separately owned backend alone.
It cannot establish fresh venue state from an old checkpoint. Incompatible,
stale or malformed evidence fails explicitly.

To publish an independent report, select a distinct output path:

```sh
.venv/bin/python -m hypervector cohort monitor --config profile.toml \
  --source-checkpoint snapshot.json --run-id RUN_ID --out independent.json
```

`--out` rebuilds reporting from the selected shared evidence and accounting
epoch. Do not point two checkpoint writers at the same output. When shared
reporting is absent, inspect `cohort checkpoint --help` and explicitly select
the profile, ledger and run before starting a separate reporter. Its optional
venue/research features have different IO requirements from monitor attachment.

Inspect provider, asset, direction, source timestamps, recorded indicators,
configured sizing, position/protection evidence and accounting identity.
Strategy evidence at a decision and the latest recorded regime context can have
different ages. Missing evidence remains unavailable. Regime strength and
prerequisite completion are diagnostics, not win probabilities.

The supervisor and live backend have separate lifecycles. Inspect `cohort
supervisor --help` and the [transition guide](cohort-live-transition-and-rollback.md)
for ownership and restart procedures. No monitor command authorizes live startup.
Historical V89 terminal captures remain in dated reviews and Git history; their
binary hashes and screen controls are not current installation instructions.

Validation:

```sh
.venv/bin/python -m pytest tests/test_headless_monitor_cli.py tests/test_incremental_monitor_identity.py tests/test_cohort_monitor_stale_attachment.py tests/test_monitor_validation_edges.py -q
```

A wrong run/profile, cross-epoch accounting, stale attachment accepted as fresh,
or monitoring that restarts execution would falsify the intended contract.
