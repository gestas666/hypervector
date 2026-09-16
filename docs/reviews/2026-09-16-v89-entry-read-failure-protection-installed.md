# Approved V89 entry-protection fix: live installation acceptance

The user explicitly approved installing candidate
`0fa2940c369c2b11cfca1b17e98787d2ad74340e` and activating it through a controlled
restart with the current profile. Its exact contents are installed and pushed
as `9dc9cf66d87d0bf6cd6f5719b2406b1e15ed64b5`.
The [qualified proposal](2026-09-16-v89-entry-read-failure-protection.md)
describes the reproduced missing-stop-attempt failure and bounded correction.

**Observed result:** backend 83722, born 19:15:04.695263 UTC, is live as
`bidirectional-live-1789586105858`. The first native heartbeat was recorded at
19:27:47.307500 UTC. Checkpoints at 19:28:53.321438 and 19:29:28.066953 UTC both
report `running_consistent`, zero faults and protection for every open position.
The second contains eight completed polls. These are dated operational checks,
not a guarantee of uninterrupted future operation.

The same seven-asset V89 profile remains active:
`configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml`, fingerprint
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
Its file SHA256 remains
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`.
Strategy, asset universe, leverage, sizing and profile settings are unchanged.
The approved execution failure path is changed. Other pending deployments were
not included.

## Position and protective-order continuity

Before shutdown, unsigned venue reads and native ownership reconciliation
returned five flat assets and two protected open positions. Backend 67727 then
received SIGTERM; its handler waits for the current operation to finish.
All seven asset ledgers recorded STOPPED, preserving venue-native protection.
Its process exited before source installation and the new start.

| Asset | Restored size | Entry OID | Stop OID | Stop trigger | Venue leverage |
| --- | ---: | ---: | ---: | ---: | --- |
| SPCX | -3.31 | 546992644531 | 546992931088 | 153.41 | 10x isolated |
| Brent | -4.9 | 546683502888 | 546683530230 | 103.18 | 10x isolated |

Native startup adopted SPCX at 19:27:03.998177 UTC and Brent at
19:27:28.255615 UTC. The original opened-at times, complete execution plans,
protective-progress state and target fields also match. All seven startup
prefixes contain nine records each and no order, cancellation, stop, target or
close submission events. Subsequent unsigned venue reconciliation independently
confirmed the same full-size reduce-only stops and leverage. No test trade or
live outage was generated.

## Backup and installed validation

Before installation, the changed baseline source files were archived and the
stopped ledger byte boundaries retained. The normal startup backup then passed
its native compressed/restored hash verification:

- Bundle: `data/backups/bidirectional_cohort/prestart_20260916T191505.858445Z_39e334fc97f3`.
- Manifest SHA256: `6d3b434e1a0ce998c6dc44a0e69b55742cc283bb93d2c23af3afb9387c615705`.
- Implementation: 1,930 files, SHA256 `bb0a45996f63d310760e38936b741eefdfeead5ca614cfceca2087220232b9d6`.
- Scope compared with the prior running backup: exactly two changed files, one
  added recovery module and 1,927 unchanged files. Every current implementation
  source hash matches the new manifest; the three candidate archives match
  their installed bytes. The backup reports `strategy_changed=no`.

The pre-stop shutdown/restart/backup/lock selection passed 115 tests. The
installed candidate passed all 440 execution tests across 52 files in 6.77s.
These overlapping selections are reported separately. Tests denied network and
access to live/runtime/database/configuration/source writes. The earlier
candidate fault injection, coverage and normal-path trace evidence remains
applicable because the installed files match exactly.

## Reporter and TUI acceptance

Old reporter 6596 was stopped after the new native run identity appeared.
Replacement reporter 18490, born 19:28:12.080519 UTC, owns the shared checkpoint
and is explicitly bound to the new run. The user's TUI 42506 was preserved.
The backend and reporter are standalone; closing that monitor leaves the backend
running. The current monitor commands remain in
[the strategy/regime guide](../guides/cohort-strategy-regime-monitor.md).

The pinned installed binary was exercised through a separate network-denied
170x45 terminal, without an operator-command inbox. All nine pages rendered as
distinct frames and the test TUI exited zero. Checks passed for connected,
live-armed and running-consistent status; configured/venue leverage; setup and
regime panels; both owned stop IDs; and configuration `DISK MATCHES RUNTIME`.
The obsolete stopped/local-exits-off labels were absent. Backend identity was
unchanged by the capture. No TUI binary or production dependency was changed.

Raw terminal bytes and decoded frames are retained. The existing deprecated
decoder produced cursor/color artifacts on archived control captures; isolated
[pyte 0.8.2](https://pypi.org/project/pyte/0.8.2/) with wcwidth 0.2.13 was used
for the accepted capture. Its files are hashed separately. A console-summary
field mistake after a successful unsigned read was also corrected; the original
receipt was preserved and the backend was unaffected. Neither verification-tool
issue was treated as a trading-system fault.

**Confidence and limits:** high for exact installation, the tested read-failure
correction and this observed restart. Complete venue outages, ambiguous fill
acknowledgements and future economic performance remain outside this evidence.
A changed source/profile hash, stale or wrong-run telemetry, failed ownership
adoption, duplicate mutation or missing protection would require renewed
investigation. Rollback requires the preserved baseline source and a verified
maintenance boundary; restoring files alone does not replace loaded code.

Evidence:
`data/logs/research/bidirectional_cohort/v89_entry_protection_install_20260916_v1/`.
The continuous research goal remains active. Native-minute continuation and the
existing source/account qualification jobs remain separate unfinished work.
