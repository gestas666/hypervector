# Exact V3 deployment and compatible rollback

This package is prepared and rehearsed in an isolated checkout. It has not been
installed. These instructions grant no deployment or trading authority. The final
approval must name the selected source, binary and process-transition scope.
Preserve the actual approval; do not infer or manufacture an approval record.

## Current static checks

From `/Users/gestas/Prototypes/hypervector`, these commands are read-only:

```bash
git diff --quiet b3df618 -- src scripts configs tests crates Cargo.toml Cargo.lock
git apply --check data/logs/research/bidirectional_cohort/v89_combined_deployment_review_20260910_v3/install.patch
shasum -a 256 configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml
shasum -a 256 target/release/tui-regime-detector
```

Require profile SHA256
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`
and installed prior binary SHA256
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.
Authenticate every declared source file's contents, mode and existing/absent
state against the manifest. Include untracked paths: `git diff` alone does not
prove absence. Preserve unrelated changes and do not force a patch over them.

## After exact deployment approval

1. Revalidate package/source/profile/binary identities and all 530 pinned external
   provider and ten SDK source files against their accepted evidence. The provider
   root is `/Users/gestas/Prototypes/backtest-lab/backtest_lab`. Use the installed
   `.venv/bin/python` interpreter without resolving its symlink or recreating the
   environment/build caches. Do not copy or print credentials.
2. Refresh process lifetime identities and ownership. Obtain fresh evidence that
   all seven affected symbols are flat and order-free, that ledgers reconcile,
   and that no old owner controls the lifecycle. Local process absence or the
   September 8 account snapshot cannot establish current venue flatness.
3. Preserve current source, binaries, profiles, approval, ledgers and control
   files in a new immutable pre-transition record. Inspect and preserve any STOP
   or drain state before an expressly approved transition. The launcher's later
   prestart backup must be recorded separately; this packet is not that backup.
4. Apply the exact `install.patch` at the approved maintenance boundary. Stage all
   72 paths, including new files; compare every candidate hash/mode and the full
   `src/scripts/configs/tests/crates/Cargo` scope against
   `564d72e81539afdd3e2979beea4086a655ec4350`. Commit a new scoped change without
   amending or reverting unrelated work.
5. Copy `binaries/candidate_tui` to a temporary file beside
   `target/release/tui-regime-detector`, verify its bytes and executable mode,
   then replace the target atomically. Preserve the prior executable. Require
   candidate SHA256
   `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.
6. For an expressly approved user-run start, use the exact command below. Let the
   existing launcher validate owner/transition state, create its normal prestart
   bundle, and bind reporting to the actual new run. Do not bypass a refusal,
   construct a separate order client or start a duplicate checkpoint writer.
   Source-only approval stops before this step.

Candidate live command, **only after the approved installation and fresh checks**:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --backtest-lab-root /Users/gestas/Prototypes/backtest-lab/backtest_lab \
  --tui-bin /Users/gestas/Prototypes/hypervector/target/release/tui-regime-detector \
  --tui-bin-sha256 382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1 \
  --enabled --i-accept-live-risk
```

For attachment to that accepted existing run:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --backtest-lab-root /Users/gestas/Prototypes/backtest-lab/backtest_lab \
  --tui-bin /Users/gestas/Prototypes/hypervector/target/release/tui-regime-detector \
  --tui-bin-sha256 382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1
```

Monitor mode does not own the order backend, but it may create an owned
report-only checkpoint writer. Quitting stops that owned writer. The live TUI
supervisor owns its backend and checkpoint writer and stops them on shutdown.
The explicit binary flags are required for these reviewed commands. Omitting
both retains the development Cargo launch path.

## Post-start acceptance

Verify fresh run/profile/source identity, all seven provider/symbol rows,
configured directions, native settings and ownership of positions/protective
orders. Capture all nine TUI views at the actual terminal size and inspect the
selected route against raw same-run checkpoint/ledger evidence. Existing views,
panes and indicators must remain reachable; unavailable data must be explicit.

The Setups inspector must show the backend's actual entry-check stage, configured
deadline, counts, age and headroom. A local SDK-dispatch check does not measure
venue arrival. Historical native PTY acceptance verifies the qualified binary on retained
fixtures, including explicit book age, checkpoint health and reachable depth
levels. Verify those fields against fresh same-run data, including Brent.
Historical replay does not prove live account presentation. Wait for naturally
occurring activity where a lifecycle observation is required.

Retain at least eight mapped-reader publications and a 15-minute I/O observation,
including snapshot size, memory and spill behavior. Verify same-run economic
fields and resource cleanup. On the first naturally occurring attributable
lifecycle, reconcile clocks, precision, fills, protection, exits, fees and funding
without forcing an order. These are technical checks, not new performance gates.

## Compatible rollback

On a technical failure, preserve logs, ledgers, checkpoints and venue-native
protection. Use only the approved containment scope. This package does not qualify
open-position rollback or authorize a replacement start. Recheck flat/order-free
state before the approved rollback maintenance boundary.

Apply only the matching `rollback_compatible.patch`. It restores **63 paths**
and retains exactly the nine paths listed in `compatibility_paths` in the manifest:
the restart reader and eight launcher source/test paths. Candidate-added files
are removed only after their current identity and retained backup match.

The restart reader preserves interpretation of client-ID-bound
`entry_not_submitted` records. Reverting that reader can leave unsent entries
unresolved. The retained launcher paths allow the prior binary to be selected
without Cargo. Do not restore prestart ledgers over newer history.

Verify all 72 declared paths and require the complete source-scope difference
from b3df618 to be exactly those nine compatibility paths. Atomically restore the
retained prior executable and its original hash. The prior display loses the new
entry-timing inspector evidence, dated book-age presentation and bounded Depth
paging; history remains intact. Restored baseline code
also retains its original technical limitations. Restart requires an explicit
operator decision and fresh acceptance.

Compatible rollback live command, **only after that separate approved restart**:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --backtest-lab-root /Users/gestas/Prototypes/backtest-lab/backtest_lab \
  --tui-bin /Users/gestas/Prototypes/hypervector/target/release/tui-regime-detector \
  --tui-bin-sha256 95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f \
  --enabled --i-accept-live-risk
```

To monitor an accepted compatible rollback run, use that same command with
`--mode monitor` and omit `--enabled --i-accept-live-risk`. Keep the prior-binary
hash. Both modes were checked against the actual rollback source/binary
composition using a mocked foreground invocation.

The isolated rehearsal checkout
`/Users/gestas/Prototypes/hypervector-v89-release-rehearsal-20260910-v3`
is left in the compatible rollback state. Do not launch from it. Source and
fixture qualification is bound to this machine and existing historical backup
references; the packet does not claim a self-contained external deployment.
