# V89 combined financial and technical release review

The complete historical report and exact installation/rollback rehearsal have
finished. The proposed release is candidate
`564d72e81539afdd3e2979beea4086a655ec4350`: **72 source/test paths**, comprising
46 implementation files and 26 tests/fixtures, plus the qualified TUI executable.
It is **not installed**. Current account readiness and live operation remain
unverified by this offline evidence.

The recommendation is to select this technical correction package while keeping
the existing V89 trading profile. The financial comparison does not establish an
independent advantage from increasing allocation. Its higher dollar returns
coincide with approximately twice the average exposure. Historical performance
is reported as evidence, without adding an implicit strategy rejection gate.

This V3 proposal supersedes V2's source scope, candidate executable and commands.
V2 remains preserved. V3 adds the separately qualified Depth display correction;
Python, Cargo and configuration bytes are unchanged from the V2 candidate.

## Completed economic evidence

The [complete financial report](../../../data/logs/research/bidirectional_cohort/v89_complete_review_presentation_20260910_v2/report.html)
contains 48 historical cases and 144 paired comparisons for July 21 through
September 7, 2026. All cases contain 177 closed trades, no remaining open trades,
and 3.6875 entries per day. These variants reuse one historical observation
window; they are not 48 independent holdouts.

| Allocation and cost assumption | Whole-window net change | Later-period net change |
| --- | ---: | ---: |
| Current sizing, nominal | +$196.85 | -$17.73 |
| Current sizing, adverse slippage | +$95.72 | -$87.24 |
| Current sizing, full HIP-3 fee stress | -$33.44 | -$137.03 |
| Equal caps, nominal | +$491.17 | +$8.87 |
| Equal caps, adverse slippage | +$368.92 | -$51.87 |
| Equal caps, full HIP-3 fee stress | +$92.00 | -$158.60 |

Values are rounded to cents across eight source/timing variants per row.
Core-history variants leave the compared cash outcomes unchanged. XYZ-history
net differences remain below $0.000003. Repaired exit clocks affect exposure
and some drawdowns, while cash remains unchanged. Cost assumptions and allocation
produce the material differences. Full HIP-3 fee stress uses nine basis points
per side as a stress assumption, not a statement of the current account fee.

Nominal closed-trade win rate is 41.81%; adverse slippage lowers it to 40.68%,
and full-fee stress to 37.29%. Low trade frequency does not establish that the
next trade is likely to be a large winner. Future returns and current-regime fit
remain unproven. Higher exposure also increases the measured dollar drawdowns.

High confidence applies to these authenticated historical calculations. Changed
source identities, incorrect cash reconciliation or a newly identified modeling
error would update that assessment. Prospective outcomes remain sealed through
September 22 04:00 UTC for the SNDK/Brent study and September 23 00:00 UTC for
the seven-asset study; neither seal was opened for this review.

## Selected proposal

| Required field | Recommendation and supporting evidence |
| --- | --- |
| Recommendation | Select the exact 72-path technical release and qualified executable, preserving the current V89 profile. Keep equal-allocation results as a research comparison. |
| Why now / observed problem | Reproductions identify delayed local entry dispatch, avoidable reporting snapshot writes, staging serialization loss, missing dispatch-deadline telemetry, a launcher that can build after backend startup, and Depth rendering that omitted explicit book age and hid retained levels below the terminal viewport. |
| Evidence reviewed | Completed 48-case/144-comparison financial report; retained Python/recovery/staging qualifications; prebuilt launcher qualification; 320 related Rust tests; actual native replay of nine views at three sizes; 33 packaging controls; exact candidate and compatible rollback checks, with 129 related regressions in each composition. |
| Applicable market regime | Technical behavior across the unchanged configured routes. No new regime, model, strategy, allocation, leverage or risk rule is proposed. |
| Proposed live change | Install only the manifest's 72 paths and candidate executable SHA256 `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`. Use the explicit executable path/hash command. A live process transition remains a separate user-run action after selected approval and fresh checks. |
| Expected upside | Enforce the existing local dispatch deadline and recovery semantics; reduce measured snapshot writes; preserve staged configuration; show backend timing, dated book age and checkpoint health; expose all retained depth levels through bounded navigation; invoke the tested binary. A financial improvement is not established. |
| Main risks and failure modes | The local dispatch check does not measure network arrival; marker persistence can fail; malformed telemetry is an explicit error; large snapshots can consume memory or spill; unsupported staging fields can refuse serialization; executable validation has a check-to-exec race; native fixture acceptance does not establish current account or Brent presentation. |
| Validation completed | All 72 candidate paths and the full selected source scope match after isolated installation. Compatible rollback restores 63 paths and retains exactly nine declared compatibility paths. Both compositions pass the same 129 regressions and live/monitor command probes. Native replay and numeric reconciliation pass separately. Installed runtime/profile/TUI remain unchanged. |
| Validation still required | Fresh source/provider/SDK/profile, account/order/owner and native-setting reconciliation; exact selected approval; new pre-transition preservation; user-run startup; fresh same-run checkpoints and nine-view TUI acceptance; eight mapped-reader publications and a 15-minute reporting observation. |
| Success metrics | Correct executable and profile; no duplicate ownership or recovery; correct deadline evidence; preserved position/protective-order interpretation; explicit unavailable/stale data; reachable views, panes and retained depth levels; correct same-run financial fields and measured reporting resources. |
| Failure / rollback triggers | Identity drift, incorrect dispatch/recovery, unexpected exposure/protection, wrong-run or missing telemetry, or measured resource regression requires diagnosis and the selected containment scope. Preserve records and venue protection. Compatible rollback is qualified at a fresh flat/order-free maintenance boundary only. |
| Confidence | High for authenticated historical arithmetic, source composition and exercised offline boundaries. Current venue state, live reliability, future profitability and open-position rollback remain unverified. |
| Explicit approval scope | Approval must select candidate `564d72e81539afdd3e2979beea4086a655ec4350`, its 72 manifest paths and executable SHA256, preserving the existing profile. Source installation and any user-run process transition must be clearly identified. This proposal is not an approval record. |

The unchanged profile is
`configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml`, SHA256
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`,
fingerprint `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
It retains BTC/ETH/HYPE long, SOL short, and SPCX/SNDK/Brent both directions.

| Alternative | Benefit | Trade-off |
| --- | --- | --- |
| Leave installed code unchanged | Avoids a transition | Retains reproduced technical and display defects |
| Select this combined technical package | One verified source/binary composition with compatible rollback | Requires coordinated installation and fresh operational acceptance |
| Select a smaller technical subset | Narrows the change | Requires validation of that different composition and rollback |
| Promote equal allocation | Higher historical dollars in this window | Approximately twice the average exposure, higher dollar drawdowns and material later-period stress losses; independent edge is unproven |

## Scope of the technical evidence

The native correction passed 320 distinct related Rust tests, twelve native
Depth checks and fifteen native paging checks. All nine views were visited at
100x28, 120x36 and 190x52. All 24 non-Depth view texts matched the retained
baseline. Seven historical fixture symbols were individually selected, and
4,424 displayed price/size/cumulative/order fields reconciled. The fixture is
September 4 V86 data; it does not include current V89/Brent account acceptance.
The images are reconstructions from real native PTY output, not OS screenshots.

The two 129-test runs exercise the same regression selection on different
compositions; they are not 258 distinct tests. Four command probes traverse both
CLI parsers and verify source imports, executable bytes and profile identity.
Foreground execution and child startup are mocked. The real native replay is
separate and creates no live backend, signer or order client.

The new native source-identity guard has full measured statement/branch coverage.
Across the other packaging operators, statement coverage is 86.44%–95.31% and
branch coverage is 60%–85%. This does not establish that every packaging failure
path is tested. Earlier 602 Python and 544 Rust results remain prior qualification
evidence for their pinned source; they are not counted as fresh combined runs.

The current verification reauthenticates 78 direct references from the V2 and
native journals, all 530 provider files and ten SDK source files, 48 case reports,
the financial manifest/report, thirteen prepared presentation artifacts and the
final HTML. Changed identities or contradictory fresh observations invalidate
the affected qualification. No new historical pipeline was started.

The highest-value next validation is fresh account/order/owner reconciliation,
followed by the approved user-run transition and same-run display/reporting
acceptance. Repeating the completed historical matrix adds no independent
evidence. As of the September 10 afternoon review, the working activation-ready
window remains **16:00–18:00 Eastern**, moderate confidence and conditional on
those checks and the selected approval. Actual startup remains user-run.

See the [exact manifest](release_manifest.json),
[deployment and compatible rollback instructions](deployment-and-rollback.md),
and [native acceptance review](../../reviews/2026-09-10-v89-native-depth-freshness.md).
Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_combined_deployment_review_20260910_v3/`.
No installation, live restart, signer or order is performed by this review.
