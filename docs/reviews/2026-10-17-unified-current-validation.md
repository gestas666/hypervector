# Current unified CLI acceptance and integration — 2026-10-17

## Maintained version

The unified CLI is the current application in `/Users/gestas/Prototypes/hypervector`
on `main` after the authorized merge. It retains VectorBT/Rust and required
TA-Lib, Nautilus historical validation, paper/shadow, Karpathy tuning,
Hyperliquid, 0xArchive, models, regime services and operator controls.
No trading service is armed or restarted by this software merge.

## Completed follow-up

- Preserved the original eleven local files in a named Git stash, patch, hashed
  manifest and tar archive under
  `/Users/gestas/.codex/backups/hypervector/20261017-unified-current/`.
  Their compatible supervisor, accounting and shutdown work was committed.
- Split autotuning into configuration/results, sampling, evaluation, search,
  export and artifact modules. Technical trial errors remain recorded; an
  entirely failed search raises with its board location. Negative valid trials
  remain eligible for adaptive search. Nonpositive trial counts fail before IO.
- Separated paper timestamp/causality utilities, configuration contracts and
  identity payload construction. Existing paper replay/identity assertions pass.
- Corrected source-follow collection-only profiles: no inference model loads,
  probabilities or model bundle identity are manufactured. Explicit filtering
  model failures still fail startup. Faithful inference profiles retain their
  configured model behavior.
- Packaged supervision independently as `hypervector_supervision`, preserving
  its isolation from execution-engine imports. The current entry point is
  `hypervector cohort supervisor`; script imports remain compatibility aliases.
- Updated backend process recognition for both legacy scripts and the packaged
  module entry point. Restart, hold, STOP and ownership contracts remain tested.
- Added `hypervector research economics` for the retained immutable accounting
  report. Current transition instructions use the headless CLI.
- Included independent supervision sources in implementation fingerprints when
  shipped beside the trading package. Included both packages in the wheel.
- Default tests deny network access and IO against real `data/live`/`data/paper`
  paths. Available local vendor/provider sources and historical inputs were
  copied into the isolated validation checkout without modifying originals.

## Validation evidence

- Isolated full offline suite before the final source-fingerprint addition:
  **11,126 passed, 3 skipped, 24 warnings, 138.26 seconds**.
- Source fingerprint regression and existing discovery checks: **5 passed**.
- Available provider/vendor integration selection: **65 passed**. This includes
  actual pinned-source loading and source-follow paper behavior with controlled
  clocks/market inputs; no live exchange client was constructed for paper.
- Public live-data checks: **4 passed** (Hyperliquid, Binance, Bybit and the
  cache/provenance pipeline).
- Authenticated 0xArchive check: one bounded page, one validated BTC candle.
  Pagination was intentionally incomplete because the request limit was one;
  this confirms transport/schema behavior, not full historical coverage.
- Installed-wheel smoke: ten command groups, packaged operational entry points,
  VectorBT backtest, TA-Lib SMA, two Karpathy trials, 400-bar Nautilus backtest,
  shadow stop lifecycle and unarmed live refusal passed with network denied.
- Independent supervision import: the trading package is absent from the
  supervisor's imported modules. Compatible local supervisor/accounting work
  passed its ten initial tests and the expanded supervisor regressions.

## Final current-checkout acceptance

- Fast-forwarded original `main` from `32c65f0` through implementation commit
  `e24822c`. All compatible original local work is committed. The old tip,
  original eleven-file stash and backup archive remain available for recovery.
- Preserved the previous `.venv` as `venv-before-merge` in the backup directory.
  Created the current environment at its normal path with
  `uv sync --locked --extra dev --extra ml --extra optuna`; all 112 installed
  packages passed `uv pip check`. The lockfile check passed.
- Full suite in the original checkout: **11,128 passed, 3 skipped, 26 warnings,
  147.88 seconds**. The skips require absent V90 operator-local screen evidence.
  Warnings include upstream pandas/Numba deprecations, not test failures.
- Current guide/monitor/operator validation: **44 passed**. Current guide links
  resolve; stale terminal instructions and two obsolete skill reference files
  were removed. Versioned runbooks and signed historical records remain intact.
- The final wheel was installed outside the source tree. Ten command groups,
  ten packaged operations and four supervisor subcommands passed help checks.
  Real VectorBT, TA-Lib SMA, two Karpathy trials, two Optuna trials, 400-bar
  Nautilus replay, paper/shadow STOP and unarmed live refusal passed with
  network access denied. Optuna float bounds now match their actual step grid.
- Current local model probe loaded the 17-feature calibrated bundle. Default
  status still leaves models unprobed and distinguishes capability presence
  from readiness. No exchange execution client was needed for these checks.
- Undefined/unused-import checks (`ruff --select F401,F811,F821`), Python
  compilation, dependency compatibility and Git whitespace checks passed.
- Final five-sample warm-cache medians: CLI import **0.050 seconds**, help
  **0.064 seconds**, status **0.078 seconds**. Synthetic recovery used **6,650
  traced Python bytes at 2 MiB** and **6,642 bytes at 8 MiB**. The earlier
  same-environment baseline was about 1.143 seconds for import and 1.185 seconds
  for help; recovery previously allocated about 35.4 MB at 8 MiB. These are
  local subprocess/synthetic observations, not production latency or RSS claims.
  Streaming improves recovery allocation; no recovery latency gain is claimed.
- Moved 517,772,182 bytes of retired TUI build output, residual crate metadata
  and stale distribution archives out of the active checkout into recoverable
  backup directories. `dist/` now contains the tested current wheel. No model,
  ledger, vendor source or research dataset was purged.
- STOP, completed drain and credentials file hashes matched the pre-merge
  preservation manifest. No backend or supervisor was started. These checks do
  not establish fresh venue-flat state.

The tested wheel is `dist/hypervector-0.1.0-py3-none-any.whl`, SHA-256
`af7b5e3461dbf06232044f0a6ebfeb120f365944322ab7019ee43e7c161be686`.
Raw command logs/XML, the final profile and wheel smoke results are retained
under the backup directory's `validation/` folder. This acceptance covers the
maintained software workflows; the historical audit failures below still need
profile-specific resolution before any future live deployment.

## Historical evidence and retention decisions

The dated `evidence` selection was exercised: **77 passed, 126 failed** after
supplying available immutable input copies. These are historical provenance,
missing artifact and source/hash contract checks. They are not represented as
passing current deployment approval. The original audit already found stale
source-bound evidence. No approval, journal or signed profile was rewritten to
make old authorization cover new sources. Current positive/negative approval
validation and execution boundaries are tested with controlled fixtures.

Historical approvals and research data remain immutable reference material.
Shelved D1 tooling and experimental research APIs remain inert/compatible,
without default CLI activation. Large historical classes and research scripts
are retained where removing or mechanically splitting them would add risk
without improving the maintained workflow. Their existing size is not a claim
of repository-wide style compliance. Further scientific changes are separate
research work, not a prerequisite for this software consolidation.

Large ignored ledgers/models/vendor data are retained in the original data
layout. No unapproved retention purge was performed. Duplicate maintained
skills, current TUI instructions and execution ownership through the terminal
renderer have been retired. Git history retains removed tracked sources.

## Merge and rollback

The user explicitly authorized making this version current and merging into the
original checkout. The original main tip is retained as
`codex/pre-unified-merge-20261017`; the original local work remains in the named
stash and backup archive even after its compatible changes are integrated.
The old environment is retained before synchronizing the stopped checkout.
The STOP file and completed drain evidence remain present. Deployment requires
new, separately authorized profile/evidence validation and a restart instruction.

Verification commands:

```sh
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile
.venv/bin/python -m pytest tests/ -q -n 4 -m "integration and not network" --ignore=tests/test_install.py
.venv/bin/python -m pytest tests/test_fetchers.py -q -m network
.venv/bin/python -m hypervector --help
.venv/bin/python -m hypervector status
.venv/bin/python scripts/profile_core_runtime.py --samples 5
```
