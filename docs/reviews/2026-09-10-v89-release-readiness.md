# V89 operational readiness and pre-transition preservation

Fresh unsigned venue checks, the existing read-only preflight and local ownership
checks pass for the unchanged V89 profile. The selected V3 technical release is
ready for an installation decision. **It remains uninstalled and live execution
has not started.** Same-run live acceptance remains outstanding.

High confidence applies to the retained observations at their recorded times.
They do not form one atomic snapshot, and positions, orders or process ownership
can change afterward. Refresh those checks at the actual maintenance boundary.
Any new exposure/order, owner, setting mismatch or source drift invalidates the
affected readiness finding.

## Fresh observations

| Check | Observed result | Time, September 10 UTC |
| --- | --- | --- |
| Native core positions and orders | No positions; zero open orders | 19:17:32–33 |
| Native XYZ positions and orders | No positions; zero open orders | 19:17:33 |
| Seven-asset Info-only preflight | Exit zero; sizing, visible depth and ledger reconciliation pass; no readiness reasons | Completed 19:18:59 |
| Current live ledger endings | Seven `STOPPED` records, zero position size and no owned order IDs | Inspected 19:20:19 |
| Existing ownership locks | Nine probes find no active owner; file contents and modification times unchanged | 19:20:19 |
| STOP and transition-drain markers | Neither present | 19:20:19 |
| Native saved leverage/margin settings | All seven match the configured values | 19:22:02–04 |
| Canonical local runtime processes | None found; both original research collectors active | 19:27:36 |
| Operator inbox | Zero pending and zero claimed commands | 19:28 UTC |

The live ledger terminal events themselves are dated September 8 14:05:33 UTC.
Their stored `LIVE ARMED` metadata describes the old run; it does not establish
a current process. The current checkpoint is also old. Fresh venue reads and
local ownership checks supply the new operational evidence.

The preflight reports approximately **$4,836.47** account value and withdrawable
balance under `unifiedAccount`. That is a point-in-time account observation, not
a return calculation. The seven configured trade sizes exceed minimum lots and
fit both sides of the displayed 20-level book snapshots. Those book walks are
not promised fills or future liquidity guarantees. No balance or performance
gate was introduced.

| Asset | Configured and observed leverage | Configured and observed margin mode |
| --- | ---: | --- |
| BTC | 20x | Isolated |
| ETH | 15x | Isolated |
| SOL | 15x | Isolated |
| HYPE | 10x | Isolated |
| SPCX | 10x | Isolated |
| SNDK | 10x | Isolated |
| Brent | 10x | Isolated |

The empty-position response does not establish a saved leverage setting. The
separate captures use the documented unsigned `activeAssetData` Info request,
which returns per-user, per-asset leverage data.
[Official API documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals).
Each response was retained before parsing, then independently decoded and checked
against the profile. The response account hashes match the native account reads
and the wallet resolution used by the preflight. Wallet values and signing keys
are not printed; the preflight child environment excludes the signing key.

## Preservation completed

The existing backup implementation completed and verified a new preservation
bundle at **19:27:01 UTC**:

`data/backups/bidirectional_cohort/prestart_20260910T192442.863139Z_39e334fc97f3/`

It contains **1,924 verified files**, including 1,869 implementation files,
with 8,175,290,477 restored bytes and 881,638,405 compressed bytes. Manifest SHA256:
`928ebd40d92c056b62fff7e3f687cbc14ae54b4ddd41f881bae91bdc6ec6df9f`.
The eight current cohort/asset ledger sizes and modification times remain
unchanged across backup creation. Backup verification checks compressed and
restored contents. No live client or backend was created.

The prior installed TUI was separately copied and authenticated at SHA256
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.
All 78 existing operator control/history files were archived and authenticated.
The existing staged profile is preserved in the backup; the selected live command
does not use `--staged-config`. No queued command or control file was cleared.

This was preservation before a possible installation, not a launcher invocation.
The launcher must create its own normal prestart bundle for the eventual new run.
The backup does not replace the actual selected approval or permit rollback over
newer account history.

## Installation decision and remaining acceptance

The [V3 combined recommendation](../proposals/v89-technical-release-20260910-v3/recommendation.md)
and [deployment/rollback instructions](../proposals/v89-technical-release-20260910-v3/deployment-and-rollback.md)
remain the exact selected scope: candidate
`564d72e81539afdd3e2979beea4086a655ec4350`, 72 source/test paths and executable
SHA256 `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.
Profile fingerprint remains
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
No strategy, asset universe, route, allocation, leverage or risk change is added.

The next action is explicit approval of that source/TUI installation, followed
by identity verification, installation and a user-run live start. At that start,
refresh venue and ownership evidence and check the real new run's nine TUI views,
including Brent and the depth-age/deadline fields. Retain eight mapped-reader
publications and at least 15 minutes of reporter/resource observations. The first
naturally occurring trade must reconcile fills, protection, exits, fees and
funding; this cannot be certified from a flat account or forced for acceptance.

The 16:00–18:00 Eastern planning window remains conditional on selected approval,
installation and successful startup checks. The completed historical report and
both prospective outcome seals remain unchanged. No duplicate historical study,
new strategy evaluation or live financial action accompanied these checks.

Evidence:
`data/logs/research/bidirectional_cohort/v89_release_readiness_20260910_v1/`.
