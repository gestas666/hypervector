# Combined V89 technical release proposal

Recommend the exact technical package based on source
`f00b6b8d22cf59285a313b7de1166cccecbe52ca` for a separately approved deployment.
It contains 33 implementation files and 19 tests/fixtures, plus the retained
qualified TUI binary. It combines the dispatch deadline, mapped reporting
reader, staging serializer and TUI timing-evidence display corrections.
The package is prepared and rehearsed; it is not installed or authorized to start.

High confidence applies to the measured offline behavior and exact packaging.
Actual live acceptance and improved profitability remain unestablished. Changed
source, dependency or profile hashes, a failed recovery, wrong SDK boundary,
incorrect fresh checkpoint, or failed binary/source verification would update
or invalidate that assessment.

| Required proposal field | Concrete decision and evidence |
| --- | --- |
| Why now / observed problem | An admitted entry can exceed its existing deadline during blocking work; the reporting reader copies avoidable data to disk; staging corrupts direction/slippage/position-policy fields; the installed TUI omits entry-check stage evidence. Each defect has retained reproduction evidence. |
| Evidence reviewed | The 602-test combined Python qualification, 544-test Rust qualification and source archives; deadline mutation/recovery controls; reporting parity and memory/I/O studies; staging round trips; configured TUI buffers; current venue metadata; and this exact installation/rollback rehearsal. |
| Applicable market regime | Technical applicability spans the configured regimes and routes. No new regime rule, model score or performance gate is introduced. |
| Proposed deployment scope | Apply exactly the 52 source/test/fixture paths in `release_manifest.json` and install only the binary whose SHA256 is `604307380b4b047453e0492a349760e737c58da3a917f37305feb39072af3ea3`. Keep the current V89 profile bytes. Any live process transition needs an explicit selected scope and fresh boundary checks. |
| Expected upside | Restore the existing local deadline and recovery contract, reduce measured reporting snapshot writes, preserve staged configuration semantics, and expose the backend's timing evidence in the existing inspector. No increase in trade frequency, win rate or return is established. |
| Main risks and failure modes | Deadline checking precedes signing/network/venue receipt. A durable-marker write failure remains a technical failure. Malformed checkpoint fields may make projection fail. Mapped snapshots still decode growing history and can spill to disk. Stricter staging parity can reject previously unsupported serialization. Old restart code cannot interpret new unsent-entry markers. |
| Validation completed | Exact package applicability to current main; complete candidate source-scope equality after isolated application; all 52 file contents/modes verified; candidate/prior binary replacement and restoration; complete compatible rollback with only the new restart reader retained; unchanged main; and all 530 pinned provider files matching. Existing qualified source/test suites are reused because their relevant source bytes are unchanged. |
| Validation still required | Complete the original 48-case economic report; choose the final deployment scope; refresh account/position/order ownership, native settings, dependency readiness and source/profile identities; retain the launcher's prestart backup; then verify matching fresh checkpoints and all nine TUI views during a supervised user-run transition. Neither metadata compatibility nor offline tests proves these live conditions. |
| Success measurements | No stale local SDK-dispatch check beyond the existing limit; durable non-actions with correct client identity; no unsent-intent resurrection or duplicate recovery; preserved exits/protection; unchanged route/profile identity; staged fingerprints preserved; consistent fresh operator data; and the previously specified reporter memory/I/O observation. A new trade is not required merely to create an acceptance event. |
| Failure / rollback triggers | Source/profile/dependency drift, duplicate dispatch, unresolved or contradictory recovery, wrong/unprotected exposure, missing or wrong-run reporting, or reproducible reporting-memory regression requires diagnosis and the explicitly approved containment scope. Preserve history and venue protection. Use the compatible rollback only at a freshly verified flat/order-free boundary. |
| Confidence | High for the pinned offline contracts and this packaging rehearsal. Live reliability and financial improvement remain unverified. The complete economic matrix and prospective comparisons have not been replaced by engineering test results. |
| Explicit approval scope | Pending: installation of this exact technical package. Backend/reporter/TUI process transitions and live activation must be expressly included in the selected authorization; they are not implied by this document. The active objective's Human control clause requires approval for live execution/deployment changes. This preparation requests no new allocation, leverage or strategy change. |

The current profile is
`configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml`, SHA256
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`,
fingerprint `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
It retains BTC/ETH/HYPE long, SOL short, and SPCX/SNDK/Brent both directions.
The inactive equal-allocation proposal is separate. No profile file, provider
selection, cap, leverage, stop, target or configured deadline changes here.

| Alternative | Benefit | Trade-off |
| --- | --- | --- |
| Keep the installed package | Avoids a transition | Retains the reproduced timing, reporting, staging and display defects |
| Deploy individual fixes | Allows a narrower operator-selected scope | Requires another exact packaging/rollback review for that combination; the old reader commit alone omits required stream-support files |
| Combined qualified package | One integrated source version, paired operator display, one rehearsed compatible rollback | Requires coordinated source/binary ownership and fresh live acceptance |
| Change strategy or allocation now | Could change financial behavior | Not supported by this technical qualification; the original economic comparison remains incomplete |

See [deployment and rollback steps](deployment-and-rollback.md). The exact
review manifest is [release_manifest.json](release_manifest.json). Durable
source/prior copies, both binaries, installation and compatible rollback patches,
and rehearsal evidence are under
`data/logs/research/bidirectional_cohort/v89_combined_deployment_review_20260910_v1/`.

Evidence references:
[combined Python qualification](../../reviews/2026-09-10-v89-technical-release-integration.md),
[TUI qualification](../../reviews/2026-09-10-v89-entry-deadline-tui.md),
[stronger TUI tests and coverage](../../reviews/2026-09-10-v89-entry-deadline-tui-coverage.md),
[current venue specification](../../reviews/2026-09-10-v89-current-venue-specification.md),
[deadline and compatible recovery](../../reviews/2026-09-08-v89-entry-deadline-dispatch-proposal.md).

The prospective outcome seals remain unchanged. SNDK/Brent ends September 22
04:00 UTC; the seven-asset comparison ends September 23 00:00 UTC. No early
outcome, live account state or post-start performance was reconstructed here.
