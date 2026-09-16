# Independent monitor startup without inherited import paths

Installed commit **ad6f94aec8eb397fed0eaf8e0f74c93d21372a66** fixes the independent
monitor's direct-script import failure. Candidate commit is
**eb9be62**. High confidence applies to the reproduced startup defect and tested
fix. A live visual attachment is not claimed: the original backend and shared
reporter stopped before installation.

The older running TUI used executable SHA256 `eada0b1359d6ea16e84dfb3d35b46538f95b6dd04cc1945f1a64d0614b5c3d9e`.
The updated versioned monitor, SHA256
`52df3fbb38a0a91f8e4577bebb7884da537dc8c3c8fd35411751684d7866bc84`, already
includes configured/venue leverage in `LEV C/V` on screens 1 and 5. Its checksum
matches, and both leverage rendering regressions passed again in this session.

Opening the documented independent command in a new Terminal.app window exposed
`ModuleNotFoundError: No module named 'scripts'`. Python executed the launcher
by file path, placing the scripts directory on the import path rather than its
parent. Earlier in-process tests imported the script as a package and therefore
did not exercise that boundary. The same file-path problem also affected the
reporter worker.

The script now uses its sibling import when executed by path and its relative
package import when imported as a module. It does not add global search paths,
load credentials, weaken execution-flag checks or change financial behavior.
Both parent and worker keep their existing argument and ownership contracts.

## Verification and rollback

Seven new subprocess controls remove inherited repository import paths. Six
failed with the observed import exception before the fix; module-mode help was
the passing control. They cover parent and worker help from the repository and
another directory, module invocation, and rejection of both live authority flags.

The complete focused monitor/worker/checkpoint/CLI suite passed **41 tests** in
the isolated candidate and **41 tests** after installation. Ruff and whitespace
checks passed. Installation preserved **5,627 other tracked file contents** and
the versioned executable checksum. Only the monitor script changes; one test file
is added. The recorded reverse patch passes applicability checks.

Previous script bytes are backed up at
`data/backups/cohort_monitor_import/preinstall_20260916T134340350930Z/`.
Evidence, failed and successful test logs, the source patch and installation
manifest are in
`data/logs/research/bidirectional_cohort/v89_monitor_clean_launch_20260916_v1/`.
Rollback requires matching installed bytes before reversing that patch. It does
not require a financial process transition.

## Separate operational interruption

The original supervisor/backend/reporter/TUI were present at **13:37:36 UTC**.
The backend's last native heartbeat is **13:38:31.697664 UTC**. Brent then records
`state_transition=STOPPED` at **13:38:31.699087 UTC**. Passive observers report
backend identity loss at **13:38:39** and **13:38:40 UTC**. At **13:42:44 UTC**,
the original process IDs and matching trading processes were absent. The cause
of the stop is not established; the user was asked whether it was intentional.

The last retained Brent position is **-4.9 at 10x isolated**, observed at
**13:38:27.018191 UTC**. That is dated local evidence, not a current exchange
position or protection verification. The shared checkpoint remains dated
**13:37:38 UTC**, so a fresh independent attachment is unavailable.

The failed new monitor launch occurred before it could create any children.
No financial process was started, stopped, restarted or signalled by this work.
An initial preinstallation audit stopped when it found the original process IDs
absent; the subsequent manifest records that absence explicitly.

Use the authenticated command in the
[monitor guide](../guides/cohort-strategy-regime-monitor.md) when a fresh matching
backend reporter is available. A further clean-environment import failure, wrong
leverage value, stale evidence presented as current, or changed execution authority
would reopen this repair. The outstanding operational work is establishing why
the original session stopped and the current position/protection state.
