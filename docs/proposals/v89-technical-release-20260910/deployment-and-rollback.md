# Exact technical deployment and compatible rollback

Status: prepared and rehearsed in an isolated checkout. This document grants no
deployment or trading authority. The main source, profile and installed TUI were
preserved. Source installation, process transitions and live activation must
match the operator's explicit selected scope under the active Human control
instruction. Approval records must preserve actual approval, not invented text.

## Static verification available now

Run from `/Users/gestas/Prototypes/hypervector`. These commands read/check only:

```bash
git diff --quiet b3df618 -- src scripts configs tests crates Cargo.toml Cargo.lock
git apply --check data/logs/research/bidirectional_cohort/v89_combined_deployment_review_20260910_v1/install.patch
shasum -a 256 configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml
shasum -a 256 target/release/tui-regime-detector
```

The profile must match `696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`.
The prior binary must match `95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.
Check each path's existing/absent state, bytes and Git mode against the manifest,
including untracked paths; `git diff` alone is insufficient for new files.
The package contains no profile changes. Reconcile unexpected differences;
preserve unrelated work and do not force-apply a patch over it.

## After exact deployment approval

1. Record the approved source, binary and process scope. Revalidate all package
   hashes and the unchanged main code baseline. Verify the official SDK and all
   530 external-provider source hashes against their accepted evidence. Use the
   existing `/Users/gestas/Prototypes/backtest-lab/backtest_lab` provider root;
   do not substitute another namespace package or copy credentials.
2. Refresh process lifetime identities and ownership. A stored PID, old flat
   snapshot, stale checkpoint or absent local process does not establish current
   venue state. Confirm all seven affected symbols are flat and order-free,
   ledgers reconcile, and no old live supervisor/backend owns the lifecycle.
   If exposure exists, use the expressly approved containment/recovery scope;
   the packaging rehearsal does not qualify open-position rollback.
3. Preserve exact current source, binaries, profiles, approval, ledgers and control
   files in a new immutable pre-transition record. A prestart backup captures
   state at the later actual start; this packet's old snapshots do not replace
   it. Do not clear STOP/control files without preserving their contents and
   verifying the approved transition. Do not copy old ledgers over newer history.
4. At the approved maintenance boundary, apply the exact `install.patch`, keeping
   its 52 source/test paths in one inspectable Git change. Stage new paths so the
   complete comparison to `f00b6b8` includes them. Verify every candidate hash and
   mode plus complete `src/scripts/configs/tests/crates/Cargo` scope equality.
   Commit a new scoped change; do not amend, reset or revert unrelated work.
5. Install the retained candidate TUI through a temporary file in the same target
   directory, verify its bytes, then replace the target atomically. Its SHA256
   must be `604307380b4b047453e0492a349760e737c58da3a917f37305feb39072af3ea3`.
   Preserve the prior executable. This binary was qualified from b73 source;
   f00 changes tests and documentation while its runtime/Cargo bytes match.
6. For an expressly authorized user-run startup, use the existing cohort launcher
   with the exact unchanged V89 profile and provider root. Both live flags remain
   required. Let the launcher create and verify its normal prestart bundle and
   record its actual path/hash. Do not construct a separate execution client or
   bypass owner/transition checks to make startup succeed. A source-only approval
   stops before this lifecycle step.
7. Load updated Python code into the actual owned backend and checkpoint writer
   as part of that selected transition. Bind the reporter to the new actual run;
   no second writer may own the same checkpoint. Existing old reporter command
   snapshots are templates only and must not supply stale run/PID ownership.

No live start or process-control command was executed during preparation. The
rehearsal worktree at
`/Users/gestas/Prototypes/hypervector-v89-release-rehearsal-20260910` is left in
the compatible rollback state and is not a launch directory.

## Post-start acceptance

Verify fresh exact run/profile/source identity, all seven provider/symbol rows,
configured directions, native metadata/settings, reconciliation and ownership
of positions and protective orders. A local process starting successfully does
not prove these conditions. Capture all nine TUI views at the actual terminal
size; inspect the exact selected route and retain raw checkpoint/ledger evidence.

The Setups inspector must show the backend's actual entry-deadline stage,
configured limit, counts, age and headroom, or explicit unavailable evidence.
SDK checking precedes signing and network delivery; it does not measure venue
arrival. A trade is not required to manufacture a screen acceptance event.
Existing views and indicators must remain reachable. The prior constructed
100x28, 120x36 and 190x52 buffers are regression evidence, not live screenshots.

For the mapped reader, retain at least eight publications and a 15-minute I/O
observation, with snapshot size and memory recorded as in the existing proposal.
Check fresh same-run economic fields, resource cleanup and explicit spill
behavior. Reduced physical writes do not imply net filesystem space savings.
On the first naturally occurring attributable lifecycle, reconcile clocks,
rounding, fills, protection, exits, fees and funding without forcing an order.

The existing monitor command, once the correct live run is available, is:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml
```

Monitor mode does not own the order backend, but it may start an owned report-only
checkpoint writer if none exists. Quitting it stops that owned writer. The live
TUI supervisor is different: its shutdown path stops its owned backend and
reporter. Do not treat these lifecycle behaviors as interchangeable.

## Compatible rollback

On a verified technical failure, preserve logs, checkpoints, ledger history and
venue-native protection. Use only the approved containment scope. Source or TUI
rollback does not establish a flat account or authorize a new start.

At a freshly verified flat, order-free maintenance boundary, apply the exact
`rollback_compatible.patch` to the matching installed candidate. Restore prior
paths from the retained bundle; remove a candidate-added path only after its
current hash matches and its backup is verified. The patch intentionally keeps
the candidate `src/hypervector/live/sol_order_restart.py` unconditionally.

This reader recognizes client-ID-bound `entry_not_submitted` records. Blindly
restoring the old reader leaves those entries unresolved, even when a later FLAT
record exists. The retained reader matches the previously qualified correction;
the baseline Python source is identical to that used by the four flat-recovery
probes. Those probes used fake venue operations and do not validate open-position
rollback. Never restore the prestart ledger over post-start history.

Verify all 52 declared paths after rollback. Across the complete code/test/config
scope, only `sol_order_restart.py` should differ from baseline `b3df618`. Restore
the retained prior TUI atomically and verify its original hash. The prior display
loses the new timing inspector evidence; backend records remain intact. Restored
baseline code also retains the original diagnosed limitations, so any restart
requires an explicit operator decision and fresh acceptance.
