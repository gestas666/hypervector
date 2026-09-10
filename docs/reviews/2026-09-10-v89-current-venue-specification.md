# Current seven-asset venue specification compatibility

The unchanged V89 profile and the existing inactive control/equal-allocation
profiles match the public specification sample captured September 10,
07:57:46.032–07:57:47.388 UTC. All seven exact symbols are present, none reports
a delisting flag, configured leverage fits the applicable tier at each cap, and
configured venue maxima match metadata. The installed SDK resolves the same
seven asset IDs and quantity precisions as the independent calculation.

Confidence is high for this captured specification comparison. It does not
establish current account readiness, active market availability, actual order
acceptance, fill quality, fee eligibility, liquidity or future profitability.
No source, profile, sizing, leverage, process lifecycle or installed TUI changed.

| Asset | Configured leverage | Reported maximum | Size decimals | SDK asset ID |
| --- | ---: | ---: | ---: | ---: |
| BTC | 20 | 40 | 5 | 0 |
| ETH | 15 | 25 | 4 | 1 |
| SOL | 15 | 20 | 2 | 5 |
| HYPE | 10 | 10 | 2 | 159 |
| xyz:SPCX | 10 | 20 | 2 | 110076 |
| xyz:SNDK | 10 | 10 | 3 | 110016 |
| xyz:BRENTOIL | 10 | 20 | 2 | 110049 |

The sample contains exactly three successful unsigned public Info requests:
core `meta`, XYZ `meta`, and `perpDexs`. No account, price, funding, signal,
trade or prospective-outcome request was made. The live profile's SHA256 is
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`;
its typed fingerprint remains
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
BTC/ETH/HYPE execute long, SOL short, and the three XYZ assets both directions.
The report independently checks all ten directions in each of three profiles.

The [public metadata contract](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
provides symbol indices, size precision and leverage tables. XYZ is dex index 1;
the [documented asset-ID equation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/asset-ids)
agrees with the installed SDK's actual Info initializer using retained responses.
SDK transport was replaced by an exact response allowlist, websocket startup
disabled, and spot markets excluded with an explicitly empty spot fixture.
No Exchange client or signer was constructed.

The four core assets report explicit margin tiers. Their next boundaries are
$150 million BTC, $100 million ETH, $70 million SOL, and $20 million HYPE.
Both existing allocation caps fall within the first tier. The XYZ response
omits explicit definitions for IDs 10 and 20. The
[published margin-tier rule](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margin-tiers)
defines IDs below 50 as one tier with leverage equal to the ID. The report
labels this source explicitly and rejects contradictory returned definitions.
It conservatively applies the lower leverage at an exact next-tier boundary.
Caps are considered independently; existing position exposure was not read.

Quantity steps are calculated from captured size decimals. Price formatting is
reported using the [venue precision rule](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size),
including the significant-figure constraint and integer exception. This does not
qualify a particular submitted price or quantity. Optional `marginMode` and
`onlyIsolated` fields are absent for these markets and remain explicitly
unreported. The profiles request isolated margin; native account mode and
venue leverage settings still need fresh deployment-time verification.

Validation passes **56 focused offline tests** in both the working study and
its archive, with identical test identities and coverage metrics. The pure
specification module covers 77/77 statements and 32/32 branches; the independent
auditor covers 88/88 statements and 10/10 branches. The report covers 74/78
statements and 18/22 branches. Those are scoped measurements, not system-wide
coverage. Tests exercise captured-input reproduction, malformed metadata,
margin boundaries, changed SDK requests, incorrect namespace offsets, corrupted
route values, and false live-readiness claims. The reused socket audit hook
rejects its intentional connection probe; neither qualification run records
an unexpected network event.

The independent raw-TOML/JSON auditor reconciles 112 market checks and all
30 complete direction rows. The archive contains 275 files; all bytes are
verified before and after testing. All 242 imported Hypervector/SDK modules
resolve within frozen source during archive testing and match their original
bytes. The archive is 556,509 bytes, SHA256
`55cf91a05b046ee222c6f1f6e5380233630912130d432b8c3602c0086367ee15`.
Third-party package versions and the source lockfile are retained. Unchanged
base parser/configuration/execution tests retain their prior qualification;
the complete 602-test suite was not unnecessarily repeated for this read-only
sample. Ruff and size/annotation checks pass for the six replay and test files.

Recommendation: retain this compatibility evidence for the combined technical
deployment review. No new venue-limit, precision or routing correction is
indicated by this sample. Keeping the prior sample would leave the current
specification state unverified; changing caps or leverage has no justification
from these measurements. The complete historical matrix remains the next
economic evidence requirement. At 08:11:29 UTC it has 23/48 receipts, four
active workers and a live reporting handoff, with 10.48 GB free. No local live
backend or TUI matched the process inventory. This does not refresh account
positions or orders. Both prospective outcome seals remain intact.

Changed metadata/profile/source hashes, an independent calculation mismatch,
different SDK mapping, unsupported flags, or a failed archived replay would
update or invalidate the conclusion. Fresh ownership/account/native execution
and TUI acceptance remain outstanding. No deployment approval is requested by
this study; no deployment or live-start authority is created.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_current_venue_specification_20260910_v1/`.
Use `report.json`, `independent_audit.json`, `acceptance.json`,
`archive_import_parity.json`, `capture/`, both qualification directories,
`archive_manifest.json`, `import_manifest.json`, and `study_source.tar.gz`.
