# Unified CLI and headless service acceptance

The retained filename preserves existing guide links. The terminal UI and
Rust workspace are retired. Current acceptance measures the Python services,
packaged CLI and backend-authored JSON. Historical screen acceptance reports
remain archival evidence rather than current operating procedures.

## Required checks

1. Discover VectorBT/TA-Lib, Nautilus, Karpathy, Hyperliquid, 0xArchive and
   paper/shadow workflows through `hypervector --help` and grouped help.
   Inventory must match the parsers and preserve non-visual aliases.
2. Run status from an absent data root. It must create no directories, load no
   wallet or execution client and distinguish installed packages from
   operational readiness. Model probes must honor explicit data scoping.
3. Build/install a wheel into a fresh environment outside the checkout. Test
   help, real fixture-driven research and unarmed live refusal there. Cohort
   services must resolve packaged modules rather than checkout scripts.
4. Run unit tests with public network access forbidden. Use explicit
   `evidence`, `integration` and `performance` markers for external inputs.
   Missing historical artifacts must not become a successful approval check.
5. Compare ledger recovery and paper summaries with fixed synthetic inputs.
   Recovery memory must remain bounded by a row; report memory is bounded by
   distinct counter values and the requested sample. `--last 0` means no rows.
6. Exercise corrupt/truncated/incomplete appends. A failed recovery must not
   publish partial cadence state. Preserve exact strategy/symbol identity.
7. Prove paper/shadow cannot construct execution clients or submit orders.
   Live startup requires both explicit authority flags, required evidence,
   credentials, STOP checks, backups and reconciliation. No technical change
   creates a new implicit performance gate.
8. Validate run/profile/accounting identity during monitor attachment and
   independent reporting. Monitoring must not restart or own a live backend.
9. Exercise operator request dry runs, atomic publication, collision refusal,
   stale/wrong-run rejection, arming requirements and backend outcome records.
   Publication alone cannot be reported as execution.

## Commands

```sh
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile
.venv/bin/python -m pytest tests/ -q -m evidence
.venv/bin/python -m pytest tests/ -q -m integration
.venv/bin/python -m hypervector status
```

Execution changes belong in an isolated checkout with its own venv. A passing
unit suite does not approve a live transition. Before deployment, supply the
exact selected profile, external providers, models and immutable evidence;
rehearse its native replay and recovery; then use the approved transition and
rollback procedure. Do not rewrite historical signatures or remove operator
STOP files to make a test pass.
