# Revised V89 technical release proposal

The exact package at candidate **e8dbdaff68700bd2fe61c4104e4e4d317f429db0**
contains **60 changed paths: 38 implementation files and 22 tests/fixtures**.
Installation and compatible rollback passed in a separate checkout. Both source
compositions passed all 129 launcher regressions, and their live/monitor command
probes selected the intended binary at a mocked subprocess boundary.
The package is **not installed** and does not authorize trading.

This V2 proposal supersedes the deployment scope and commands in the preserved
V1 proposal. It incorporates the verified prebuilt launcher correction: the
earlier file replacement rehearsal did not establish that the launcher actually
invoked the installed executable. The selected V2 commands explicitly identify
that executable and its SHA256, avoiding the existing Cargo launch dependency.

High confidence applies to the measured offline composition and command behavior.
Actual account state, terminal accuracy, live reliability and financial improvement
remain unverified by these tests. Different source/binary/profile identities,
contradictory recovery or incorrect fresh telemetry would invalidate the affected
finding and require a new review.

| Required proposal field | Decision and evidence |
| --- | --- |
| Recommendation | Select this complete technical package for the final combined review once the original financial report finishes. |
| Why now / observed problem | Retained reproductions identify delayed local entry dispatch, avoidable reporting snapshot writes, staging serialization loss, missing entry-deadline display evidence, and a launcher that can build after backend startup instead of selecting the prepared binary. |
| Evidence reviewed | Prior 602-test Python and 544-test Rust qualifications; deadline/recovery, mapped-reader and staging evidence; prebuilt launch qualification; 20 packaging failure-control tests; exact 60-path installation/rollback; 129 regressions in each resulting composition; four non-executing live/monitor command probes. |
| Applicable market regime | Technical behavior across the unchanged configured routes. No regime rule, performance gate, model, allocation or risk parameter is changed. |
| Proposed live change | Install exactly the manifest's 60 source/test paths and candidate TUI SHA256 `604307380b4b047453e0492a349760e737c58da3a917f37305feb39072af3ea3`. Use the explicit path/hash launcher options. Preserve the current V89 profile. A process transition requires final selected authorization. |
| Expected upside | Enforce the existing local dispatch deadline and recovery contract, reduce measured snapshot writes, preserve staged configuration semantics, show actual backend timing evidence, and select the qualified executable without building during launch. No return, win-rate or trade-frequency increase is established. |
| Main risks | The dispatch check precedes signing/network arrival; marker persistence can fail; malformed telemetry remains an explicit error; growing snapshots still consume memory and can spill; unsupported staging fields can refuse serialization; executable verification retains a check-to-exec race; omitted selection flags retain the development Cargo command. |
| Validation completed | All 60 candidate paths and full source scope match after isolated application. Compatible rollback restores 51 paths and retains exactly nine declared compatibility paths. Both binary replacements match. Both compositions pass 129 related tests and exact command probes. Installed main source and binary remain unchanged. |
| Validation still required | Complete the original 48-case economic report; record the final selected release approval; refresh source/provider/SDK/profile, account/order/owner and native-setting checks; preserve a new pre-transition record and launcher prestart backup; verify fresh same-run checkpoints and all nine TUI views. |
| Success metrics | Exact binary invocation; unchanged data/profile arguments; explicit identity-drift refusal; no unintended process ownership or duplicate recovery; correct dispatch-deadline evidence; preserved exits/protection; fresh operator telemetry and the existing eight-publication/15-minute reporter observation. |
| Failure / rollback triggers | Changed identity, incorrect dispatch/recovery, unexpected exposure/protection, wrong-run or missing telemetry, or measured resource regression requires diagnosis and the explicitly approved containment scope. Retain records and venue protection. Compatible rollback is qualified only at a freshly verified flat/order-free maintenance boundary. |
| Confidence | High for the pinned offline artifacts and exercised boundaries. The full historical report, live account reconciliation and actual TUI acceptance are separate evidence requirements. |
| Explicit approval requested | Deferred to the complete combined review. No deployment, restart, signer, order or live activation is authorized by this document. User-run activation remains subject to the objective's Human control instruction. |

The unchanged profile is
`configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml`, SHA256
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`,
fingerprint `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
It retains BTC/ETH/HYPE long, SOL short, and SPCX/SNDK/Brent both directions.
The equal-allocation economic comparison is separate and inactive.

| Alternative | Benefit | Trade-off |
| --- | --- | --- |
| Leave installed code unchanged | Avoids a transition | Retains the reproduced technical defects and build dependency |
| Restore build caches | Supports the existing Cargo command | Uses limited disk and does not explicitly bind invocation to the reviewed binary |
| Select this combined package | One exact composition with matching commands and rehearsed rollback | Requires coordinated source/binary transition and fresh live acceptance |
| Select a smaller technical subset | Narrows the approved change | Requires an exact composition and rollback review for that different subset |

The prior 602 Python and 544 Rust results are retained qualification evidence,
not new test runs. V2 leaves the old package's 52 changed paths and Rust/Cargo
bytes unchanged and adds eight launcher source/test paths. New integrated
launcher checks cover both candidate and rollback compositions. Tests use mocked
process boundaries and eight unchanged same-machine legacy fixtures; the saved
checkpoint is used only for the existing retired-filename exclusion test.
No prospective financial outcomes are evaluated.

At September 10 17:15 UTC, all 530 pinned provider files and ten SDK files match
their retained source evidence, with no additional non-hidden provider Python
files. Sixty direct references from the prior package and launcher journals
reauthenticate. The packaging operators' measured statement coverage ranges from
86.44% to 95.31%, combining their control tests with actual offline preparation,
rehearsal and command probes. Branch coverage is partial (60% to 85%); this is
not a claim that every operator failure path was unit tested.

The command probe verifies imported project files belong to the rehearsal
checkout, checks the profile and executable hashes, traverses both CLI parsers,
and invokes only a mocked foreground subprocess. It does not load credentials,
run the supervisor or execute a native TUI. These controls prove command
selection, not successful rendering or venue reconciliation.

See [deployment and rollback](deployment-and-rollback.md) and the exact
[manifest](release_manifest.json). Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_combined_deployment_review_20260910_v2/`.
The rehearsal checkout is left in the compatible rollback state and is not a
launch directory. All older packets and source archives remain preserved.

Supporting reviews:
[combined Python qualification](../../reviews/2026-09-10-v89-technical-release-integration.md),
[TUI qualification](../../reviews/2026-09-10-v89-entry-deadline-tui.md),
[prebuilt launch correction](../../reviews/2026-09-10-v89-prebuilt-tui-launch.md),
[venue specifications](../../reviews/2026-09-10-v89-current-venue-specification.md).
Both prospective outcome seals remain unchanged: SNDK/Brent through September
22 04:00 UTC and the seven-asset comparison through September 23 00:00 UTC.
