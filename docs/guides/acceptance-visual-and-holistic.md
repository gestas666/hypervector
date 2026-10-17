# CLI and headless service acceptance

This guide keeps its filename so that existing links still resolve. Acceptance
measures the packaged CLI, the Python services and the JSON the backend writes.
There is no terminal UI.

## Required checks

1. **Surface.**
   - `hypervector --help` lists the 13 groups in a fixed order.
   - Every `<group> --help` lists the group's commands.
   - `--help` imports no engine and stays under 0.07 s.
   - Old names parse as hidden aliases. Retired names exit 2 and name their
     replacement.
2. **Status.** `hypervector --data-root <absent dir> status` must:
   - create no directory;
   - load no wallet and build no execution client;
   - report installed capabilities separately from operational readiness;
   - keep model probing (`--probe-model`) within the selected data root.
3. **Install.** Build and install a wheel into a fresh environment outside the
   checkout. There, run help, a fixture-driven research command and an unarmed
   `live start`, which must exit 2. Operator tools must resolve to the packaged
   `hypervector.operations` and `hypervector_supervision` modules.
4. **Offline tests.**
   - Run the default suite with public network access forbidden.
   - `-m "integration and not network"` covers the wheel install.
   - `-m network` is an explicit opt-in.
   - A missing external artifact never counts as a passing check.
5. **Recovery and reports.** Compare ledger recovery and paper summaries on
   fixed synthetic inputs.
   - Recovery memory stays bounded to one row.
   - Report memory is bounded by the distinct counter values and the requested
     sample.
   - `--last 0` means no rows.
6. **Corrupt appends.** Exercise corrupt, truncated and incomplete appends. A
   failed recovery must not publish partial cadence state, and it must keep the
   exact strategy and symbol identity.
7. **Paper and live boundaries.**
   - Paper and shadow cannot construct execution clients or submit orders.
   - `live start` requires both authority flags, an observe-mode profile load
     and provider dependencies before it hands over to the backend.
   - The backend then requires credentials, the STOP check, a verified
     pre-start bundle and venue reconciliation.
   - No change adds an implicit performance gate.
8. **Monitoring.** `live monitor` and `live checkpoint` check run, profile and
   accounting identity. Monitoring never restarts or owns a backend.
9. **Operator requests.** Exercise `live request`:
   - dry runs and atomic publication;
   - collision refusal;
   - rejection of stale or wrong-run requests;
   - the arming requirement;
   - backend outcome records.
   Publication alone is never reported as execution.
10. **Pipeline.** Check these properties:
    - `pipeline run --dry-run` writes nothing.
    - A stage failure exits 1 and leaves a partial manifest.
    - An unsupported Nautilus symbol marks that stage `skipped`.
    - The run imports no execution module.

## Commands

```sh
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile
.venv/bin/python -m pytest tests/ -q -m "integration and not network"
.venv/bin/python -m pytest tests/test_cli_surface.py tests/test_cli_spec_lint.py \
  tests/test_cli_operation_parity.py tests/test_cli_legacy_aliases.py \
  tests/test_cli_pipeline.py tests/test_v95_restartability.py -q -n 2
.venv/bin/python -m hypervector status
```

Execution changes belong in a separate checkout with its own venv. A passing
suite does not approve a live start. Before a deployment, supply:

- the exact profile;
- the external providers (`../backtest-lab`);
- the models.

Then follow [the transition and rollback guide](cohort-live-transition-and-rollback.md).
Never remove a STOP file or rewrite an approval to make a test pass.
